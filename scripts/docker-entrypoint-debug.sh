#!/bin/bash
# Temporary debugging entrypoint
#
# Wraps the real entrypoint to log what a container cost in time, CPU and
# memory, so that NUM_PROC_TOTAL and instance sizes can be chosen from measured
# numbers rather than guessed. See docs/reference/performance.md.
#
# This is here to gather data and is meant to be removed once it has. To remove
# it: delete this file and its test, point ENTRYPOINT in the Dockerfile back at
# docker-entrypoint.sh, and drop the "Measuring a run" section of the
# performance reference.

ENTRYPOINT="$(dirname "$0")/docker-entrypoint.sh"

# Usage is read from the cgroup, which only cgroup v2 is handled for: anything
# it does not provide is reported as null rather than failing the run.
CGROUP=/sys/fs/cgroup
METRICS_ENABLED=${OM_METRICS:-1}
# Memory has to be sampled while the command runs, since by the time it exits
# its processes have handed everything back.
METRICS_INTERVAL=${OM_METRICS_INTERVAL:-30}

MEMORY_HIGH_WATER=$(mktemp 2>/dev/null)
SAMPLER_PID=""
CHILD_PID=""
START_SECONDS=""
START_CPU_USEC=""
START_THROTTLED_USEC=""


# First line of a cgroup file, or nothing if the kernel does not provide it.
cgroup_value() {
  [ -r "${CGROUP}/$1" ] && head -n 1 "${CGROUP}/$1"
}

# One key out of a "key value" cgroup file such as memory.stat.
cgroup_field() {
  [ -r "${CGROUP}/$1" ] && awk -v key="$2" '$1 == key { print $2; exit }' "${CGROUP}/$1"
}

# A JSON number, or null when the value could not be read.
number() {
  echo "${1:-null}"
}

# Microseconds as seconds, to two decimal places.
seconds() {
  [ -n "$1" ] && awk -v usec="$1" 'BEGIN { printf "%.2f", usec / 1000000 }'
}

# Difference between a counter now and where it started.
since_start() {
  local now=$1 start=$2
  [ -n "$now" ] && [ -n "$start" ] && echo $((now - start))
}

# Space left on the filesystem holding a path.
free_bytes() {
  [ -n "$1" ] && [ -d "$1" ] && df -B1 --output=avail "$1" 2>/dev/null | tail -n 1 | tr -d ' '
}


# Track the highest anonymous memory the cgroup reaches. This is what the
# processes actually need resident, as opposed to memory.peak, which counts the
# page cache that writing checkpoints leaves behind.
sample_memory() {
  # A forked copy of this shell, so it carries the traps set below and must not
  # run them.
  trap - SIGTERM SIGINT SIGQUIT SIGHUP EXIT

  local high_water=0 anon
  while true; do
    anon=$(cgroup_field memory.stat anon)
    if [ -n "$anon" ] && [ "$anon" -gt "$high_water" ]; then
      high_water=$anon
      echo "$high_water" > "$MEMORY_HIGH_WATER"
    fi
    sleep "$METRICS_INTERVAL"
  done
}


log_start() {
  [ "$METRICS_ENABLED" = "0" ] && return 0

  START_SECONDS=$SECONDS
  START_CPU_USEC=$(cgroup_field cpu.stat usage_usec)
  START_THROTTLED_USEC=$(cgroup_field cpu.stat throttled_usec)

  # Cores the CPU quota allows, which is not the number of CPUs visible: a
  # container limited with --cpus still sees every CPU on the machine.
  local quota period cpus_quota
  read -r quota period <<< "$(cgroup_value cpu.max)"
  [ "$quota" = "max" ] && quota=""
  [ -n "$quota" ] && cpus_quota=$(awk -v q="$quota" -v p="$period" 'BEGIN { printf "%.2f", q / p }')

  local memory_limit
  memory_limit=$(cgroup_value memory.max)
  [ "$memory_limit" = "max" ] && memory_limit=""

  # Physical cores behind the visible CPUs, which is half of them under SMT.
  local cpus_physical
  cpus_physical=$(awk -F': ' '
    /^physical id/ { socket = $2 }
    /^core id/ { cores[socket ":" $2] = 1 }
    END { if (length(cores)) print length(cores) }' /proc/cpuinfo 2>/dev/null)

  echo "[om-metrics] {\"event\": \"start\"\
, \"cpus_visible\": $(number "$(nproc 2>/dev/null)")\
, \"cpus_physical\": $(number "$cpus_physical")\
, \"cpus_quota\": $(number "$cpus_quota")\
, \"memory_limit_bytes\": $(number "$memory_limit")\
, \"chk_path_free_bytes\": $(number "$(free_bytes "${CHK_PATH:-}")")}"

  if [ -n "$MEMORY_HIGH_WATER" ] && [ -n "$(cgroup_field memory.stat anon)" ]; then
    sample_memory &
    SAMPLER_PID=$!
  fi
}

log_finish() {
  [ "$METRICS_ENABLED" = "0" ] && return 0
  [ -n "$START_SECONDS" ] || return 0

  local wall cpu_usec cpu_seconds parallelism events
  wall=$((SECONDS - START_SECONDS))

  cpu_usec=$(since_start "$(cgroup_field cpu.stat usage_usec)" "$START_CPU_USEC")
  cpu_seconds=$(seconds "$cpu_usec")

  # Cores kept busy on average. Compare it against the ranks the run was given:
  # well below means they were idle, blocked on I/O, or throttled.
  [ -n "$cpu_usec" ] && [ "$wall" -gt 0 ] && parallelism=$(
    awk -v usec="$cpu_usec" -v wall="$wall" 'BEGIN { printf "%.2f", usec / 1000000 / wall }')

  # How often the cgroup was held at its memory limit, or had something killed.
  events=$(awk '{ printf "%s\"%s\": %s", (NR > 1 ? ", " : "{"), $1, $2 } END { print (NR ? "}" : "null") }' \
    "${CGROUP}/memory.events" 2>/dev/null)

  echo "[om-metrics] {\"event\": \"finish\"\
, \"exit_code\": $1\
, \"wall_seconds\": ${wall}\
, \"cpu_seconds\": $(number "$cpu_seconds")\
, \"mean_parallelism\": $(number "$parallelism")\
, \"cpu_throttled_seconds\": $(number "$(seconds "$(since_start "$(cgroup_field cpu.stat throttled_usec)" "$START_THROTTLED_USEC")")")\
, \"memory_anon_bytes\": $(number "$(head -n 1 "$MEMORY_HIGH_WATER" 2>/dev/null)")\
, \"memory_peak_bytes\": $(number "$(cgroup_value memory.peak)")\
, \"memory_events\": ${events:-null}\
, \"chk_path_free_bytes\": $(number "$(free_bytes "${CHK_PATH:-}")")}"
}


# Pass signals on to the entrypoint, which is waited on rather than run in the
# foreground so that they arrive while it is still running.
forward_signal() {
  [ -n "$CHILD_PID" ] && kill -TERM "$CHILD_PID" 2>/dev/null
}

on_exit() {
  local status=$?

  [ -n "$SAMPLER_PID" ] && kill "$SAMPLER_PID" 2>/dev/null
  log_finish "$status"
  rm -f "$MEMORY_HIGH_WATER"

  exit "$status"
}

trap forward_signal SIGTERM SIGINT SIGQUIT SIGHUP
trap on_exit EXIT


log_start

"$ENTRYPOINT" "$@" &
CHILD_PID=$!
wait "$CHILD_PID"

exit $?
