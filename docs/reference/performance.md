# Performance and hardware

How Open Methane uses the hardware it is given, how to choose `NUM_PROC_TOTAL`
for a new machine, and how to measure what a run actually costs.

Nearly all of the cost of a run is CMAQ: the forward model and the adjoint, run
once each per inversion iteration. The preprocessing stages are comparatively
cheap and mostly single-threaded. So "making a run faster" almost always means
"giving CMAQ the right number of MPI ranks", which is what this page is about.

## How CMAQ uses cores

CMAQ splits the horizontal grid into a `NUM_PROC_COLS` x `NUM_PROC_ROWS` array
of subdomains and runs one MPI rank on each. Every rank advances its own
subdomain and exchanges a halo of cells with its neighbours at each step.

Normally you set only `NUM_PROC_TOTAL`, to the number of cores the run has, and
the shape is derived from the size of the domain — see
[MPI domain decomposition](parameters.md#mpi-domain-decomposition). Two
consequences are worth knowing:

- Splitting the domain further shrinks the work each rank does but grows the
  halo it exchanges, so speedup falls away as ranks are added and eventually
  reverses. There is a best rank count for each domain, and it is not
  "all of them".
- Subdomains are kept to at least `MIN_CELLS_PER_RANK` cells in either
  direction, so a small domain uses fewer ranks than you asked for, down to a
  single rank. The resolved decomposition is logged at INFO when a run starts;
  check it if a run seems not to be using the cores you gave it.

## Choosing `NUM_PROC_TOTAL`

As a starting point, use the number of **physical cores** available to the run:

```shell
NUM_PROC_TOTAL=$(lscpu -p=Core,Socket | grep -v '^#' | sort -u | wc -l)
```

Where `lscpu` is not installed, the `cpus_physical` field of the metrics line
described in [Measuring a run](#measuring-a-run) reports the same number.

Then tune from there by measurement, because the best value depends on the
domain. Four things make the obvious `$(nproc)` the wrong starting point:

**`nproc` counts logical CPUs, not cores.** On a machine with SMT
(hyper-threading) enabled it is twice the core count. See
[SMT](#smt-hyper-threading) below.

**`nproc` ignores CPU quotas.** It reports the size of the affinity mask, not
the cgroup CPU limit. A container started with `--cpus=4` still sees every CPU
on the host, so `$(nproc)` there launches far more ranks than the container is
allowed to run, and they contend for the same fraction of a core.
`--cpuset-cpus` does constrain `nproc`. If you run in a container with a CPU
limit, set `NUM_PROC_TOTAL` from the limit rather than from the machine.

**Something has to run the driver.** The Python process orchestrating the
inversion, the I/O and the operating system all need time. Leaving one core
unallocated is usually cheaper than having every rank wait on the one that is
descheduled.

**More ranks is not always faster.** Past some point the halo exchange costs
more than the extra parallelism saves.

### SMT (hyper-threading)

Two CMAQ ranks on the two threads of one physical core share that core's
floating-point units, its L1 and L2 caches, and its share of memory bandwidth.
CMAQ is largely bandwidth-bound, so running one rank per thread rather than per
core tends to give little benefit and can be slower, while doubling the number
of ranks — and so the memory and the halo exchanges.

- **SMT enabled**: set `NUM_PROC_TOTAL` to the physical core count, which is
  half of `nproc`. The `lscpu` command above gives it directly.
- **SMT disabled**: `nproc` equals the physical core count, so `$(nproc)` is a
  safe value. If you control the machine, this is the simpler configuration —
  on AWS, `CpuOptions ThreadsPerCore=1`.

Rank placement matters too. If ranks are not bound to cores, two can land on
the two threads of one core while another core sits idle, which shows up as
unexplained run-to-run variation. Check what your MPI defaults to and bind
explicitly if it does not.

## Memory

Each rank needs a fixed overhead — the executable, its I/O API buffers, MPI
buffers — plus arrays sized to the cells it owns and the halo around them. So
adding ranks reduces memory *per rank*, but not to zero, and **increases the
total memory the run needs**, because the fixed overhead is paid once per rank
and the halos are duplicated.

This is the opposite of what people usually expect, and it matters when the run
has a hard memory limit: a configuration that fits at 24 ranks can be killed at
48 on the same machine. Under a container memory limit, that arrives as the
process being killed outright, with no error from CMAQ explaining why.

Disk is a separate constraint. `CHK_PATH` holds the checkpoint files the adjoint
reads back, which are large and rewritten every iteration; their size follows
the domain and the number of steps, not the rank count. Put them on fast local
disk with room to spare — see
[Disk fills up during a run](../troubleshooting.md#disk-fills-up-during-a-run).

## Measuring a run

> **Temporary.** The image currently starts through a debugging entrypoint,
> `scripts/docker-entrypoint-debug.sh`, which logs what each container cost.
> It is here to gather data and will be removed once it has, along with this
> section.

Every container started through the image entrypoint logs a line to stdout when
the command starts and another when it finishes, prefixed `[om-metrics]` and
formatted as JSON:

```
[om-metrics] {"event": "finish", "exit_code": 0, "wall_seconds": 4132, "cpu_seconds": 91240.18, "mean_parallelism": 22.08, ...}
```

A start line with no matching finish line means the container died without
getting the chance to exit, most often an out-of-memory kill.

The fields that answer most questions:

| Field | Read it for |
| --- | --- |
| `wall_seconds` | What the step cost. |
| `cpu_seconds`, `mean_parallelism` | Whether the cores were used. `mean_parallelism` is `cpu_seconds / wall_seconds`, so it is the number of cores kept busy on average — compare it against the ranks the run was given. Well below that means ranks were idle, blocked on I/O, or throttled. |
| `cpu_throttled_seconds` | Time spent stopped by a CPU quota. Anything much above zero means the container is asking for more CPU than it is allowed, which is the `nproc` trap above. |
| `cpus_visible`, `cpus_quota` | What the container could see against what it was allowed to use. These differing is the same trap, before it has cost you anything. |
| `cpus_physical` | Cores behind the visible CPUs. Half of `cpus_visible` means SMT is enabled. |
| `memory_anon_bytes` | The memory the processes actually need resident. This is the number to size a machine against. |
| `memory_peak_bytes` | Peak charged to the cgroup. This includes page cache, so for a step that writes checkpoints it runs up to whatever the limit allows and is *not* a measure of memory demand — prefer `memory_anon_bytes`. |
| `memory_events` | `max` above zero means the run was held at its memory limit; `oom_kill` above zero means something was killed. |
| `chk_path_free_bytes` | Space left where the checkpoints go, logged at both ends. |

Some caveats:

- **Memory is sampled**, every `OM_METRICS_INTERVAL` seconds (default 30),
  because by the time the command exits its processes have released everything.
  A spike shorter than the interval can be missed. Lower the interval for short
  steps; for a CMAQ run measured in hours the default is ample.
- **Usage is read from cgroup v2**, and anything the kernel does not provide is
  reported as `null` rather than failing the run. On a host running cgroup v1
  the usage fields are all null. `memory_peak_bytes` additionally needs Linux
  5.19 or newer.
- **The numbers describe the container's cgroup.** Run with `--cgroupns=host`
  they would describe the whole machine instead.
- `wrf-run` and `prior-generate` run from different images and do not log these
  lines.

Set `OM_METRICS=0` to turn the logging off.

### Finding the best rank count for a domain

Timings from one domain do not transfer to another, so measure on the domain
you intend to run:

1. Run a single forward step — `scripts/fourdvar/singlestep.py`, see
   [Debugging the inversion](../troubleshooting.md#debugging-the-inversion) —
   at a few rank counts: 1, then doubling up to the cores you have.
2. For each, record `wall_seconds`, `mean_parallelism` and
   `memory_anon_bytes` from the metrics line, and the resolved decomposition
   from the log.
3. Pick the smallest rank count within a few percent of the best wall time.
   Ranks past that point cost memory and give nothing back.

Fitting `memory_anon_bytes` against rank count gives roughly a straight line:
the intercept is the domain's own memory and the slope is the per-rank
overhead. That turns machine sizing into arithmetic rather than guesswork.

This only needs redoing when the domain, the CMAQ build or the machine changes.

## Reproducibility

Changing the decomposition changes the order in which the parallel arithmetic
is done, so results are not bitwise identical between different rank counts.
The per-step difference is at rounding level, but the inversion is iterative and
L-BFGS-B can take a visibly different path from a slightly different gradient.

For runs you intend to compare against each other, or to publish, pin the
decomposition — set `NUM_PROC_COLS` and `NUM_PROC_ROWS` explicitly, or keep
`NUM_PROC_TOTAL` and the domain fixed — rather than deriving it from whatever
hardware happened to be available.
