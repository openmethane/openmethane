# Testing

This guide covers running the test suite, the test data it uses, and how to
update that data. For setting up a checkout, see
[Development](development.md).

## How we test

Open Methane is mostly glue between programs we don't maintain: WRF and WPS,
MCIP, ICON and BCON, and CMAQ-Adjoint, which is tested in its own repository.
Whether a program turns its inputs into the right outputs is for its
maintainers to test. Our tests check the glue: the configuration, namelists,
arguments and environment we give each program, the files it reads and
writes, and the Python that reads one program's output and writes the next
one's input.

A stub program stands in for a real one and records the arguments and
environment it was started with, so a test can check them quickly, outside
the image. `tests/unit/wrf` tests the WRF workflow this way. But a stub checks
only what we expect, and we wrote those expectations, so it can't catch a
wrong belief about the program: a variable it ignores or reads under another
name, an attribute it writes differently than we assumed, or an output whose
meaning we misread. Nor can it catch a broken build of the models in the
image. So some tests also run the real programs.

The suite has four kinds of test:

| Kind | What runs | What it checks | Where |
| --- | --- | --- | --- |
| Unit tests | Our Python, with stub programs where a program would run | Our code's output, and the arguments and environment it gives each program | `tests/unit/` |
| Stage tests | One stage of a workflow on the `daily_run` test data bundle, with its programs for real where it runs any | The stage's output, against regression fixtures where it has them | `tests/integration/` folders named for the stage |
| Contract runs | One program, for real, on the inputs our glue makes | The program accepts our inputs and writes what our glue reads; its values against recorded output, so any change in them is seen | `tests/integration/wrf/` |
| Workflow tests | The daily and monthly workflows' steps in order, with the real programs | Each step runs and finds what the step before it wrote | `tests/integration/workflows/` |

When adding a test:

- Test what our code does, not whether a program's output is right for its
  inputs.
- Call the code under test in the test body. Fixtures only arrange, however
  expensive the call: the WRF test runs WRF in its body.
- Take the `au_test_config` fixture for configuration (see
  [Configuration](#configuration)).
- Make every check of what the code does a pytest test, so it runs locally
  as it does in CI.
- Put new test data that is binary, or text over 50 KB, in a bundle (see
  [Test data bundles](#test-data-bundles)), not in git.
- Mark the test with what it needs or costs (see [Markers](#markers)).

## Running the tests

The test suite needs the compiled models and command-line tools that only exist
in the container, so the canonical way to run it builds the image and runs
`pytest` inside:

```shell
make docker-test
```

Inside the container, run it directly. On a
[local install](local-install.md), put `uv run` before these `pytest`
commands:

```shell
pytest -r a -v
```

This runs everything, including the WRF integration test, which takes about 5
minutes and downloads the day's FNL analyses, about 3.4 GB, into `data/fnl` the
first time (see [WRF integration tests](#wrf-integration-tests)), and the
daily and monthly workflows for the same day in `tests/integration/workflows`,
which take about 1 and 5 minutes. It leaves out
`tests/integration/fourdvar/`, which runs only when named on the command line.

A single test:

```shell
pytest -v \
  tests/unit/wrf/test_config.py::test_reads_the_production_job_environment
```

Or from the host, without an interactive shell:

```shell
docker run --rm -v "$PWD":/app -v /app/.venv openmethane \
  pytest -v \
  tests/unit/wrf/test_config.py::test_reads_the_production_job_environment
```

Two categories of test will not pass outside the container:

- Tests requiring binaries such as the CMAQ adjoint or `ncatted`.
- Everything under `tests/integration/fourdvar/`, which is left out by default. These
  depend on input data that has not been provided in a reproducible way. They
  should be fixed when possible.

## Markers

A handful of tests do reach third-party services, and are marked `network`.
Deselect them to run offline, or to keep somebody else's outage from failing the
suite:

```shell
pytest -r a -v -m "not network"
```

Markers say what a test needs or costs, so you can leave those tests out:

| Marker | The test |
| --- | --- |
| `network` | Can contact a third-party service when its cache is empty |
| `wrf` | Runs the WRF or WPS programs, which only exist in the image |
| `cmaq` | Runs MCIP, ICON or BCON, which only exist in the image |
| `adjoint` | Runs the CMAQ adjoint, which only exists in the image |
| `slow` | Takes over a minute |

For a quick run:

```shell
pytest -r a -v -m "not slow and not network"
```

Markers are registered in `pyproject.toml`, and a misspelt one on a test fails
collection. A marker that follows from a fixture, like `network` for the FNL
cache, is added in `tests/conftest.py`, so tests using the fixture don't repeat
it.

## Configuration

Tests set their own configuration, so `TARGET` and `.env` files are ignored. A
test that needs configuration takes the `au_test_config` fixture. An error
naming `/nonexistent-test-configuration` means a test read configuration
without it.

## Test data bundles

Test data too large or binary for git is in bundles in the Open Methane public
data store, listed with their hashes in `tests/test-data/bundles.yaml`. A test
that needs one downloads it the first time, through a fixture in
`tests/conftest.py` named after it, and unpacks it into `data/test-cache/`,
where later runs reuse it. `--test-cache` sets another folder. A bundle the
cache doesn't hold yet needs a connection, but our own bundles aren't marked
`network`: unlike a third-party service, a bundle in the data store never
changes.

| Bundle | Fixture | Contents |
| --- | --- | --- |
| `wrf` | `wrf_data` | The WRF step's published output for au-test on 2022-12-07; see [WRF test data](#wrf-test-data) |
| `daily_run` | `daily_run_data` | Inputs and outputs of the other steps of the daily and monthly workflows for the same day, a folder for each kind (`mcip/`, `obs/`, `templates/` and so on), and the au-test domain files. `README.md` inside lists them |

`au_test_config` points the configuration at `daily_run`, except for WRF
output, which is still read from `tests/test-data/wrf`.

A bundle is date-stamped, so changing it doesn't change what older commits
fetch. To change `daily_run`, unpack the current bundle into a folder outside
the repository, make the change, update its README, and pack it again:

```shell
tar -C daily-run-test-data --sort=name --owner=0 --group=0 --numeric-owner \
  -czf daily-run-test-data.$(date +%Y%m%d).tar.gz .
sha256sum daily-run-test-data.$(date +%Y%m%d).tar.gz
```

Upload it to `https://openmethane.s3.amazonaws.com/tests/daily-run/` beside the
old one, and in the same change update its `url`, `sha256` and `made_by` in
`tests/test-data/bundles.yaml`.

## Regression fixtures

Data-producing code is covered by
[pytest-regressions](https://pytest-regressions.readthedocs.io/), comparing
output against fixtures in a folder beside each test module, named after it.
When you change what a step
produces, regenerate the fixtures and read the diff carefully — an unexpected
change in a fixture is usually the bug, not the fixture being stale:

```shell
make test-regen
```

## WRF integration tests

The test in `tests/integration/wrf/` runs `wrf run` with the real WRF and WPS
programs for au-test on 2022-12-07, checks the published output against the
[WRF output contract](../reference/wrf-outputs.md), and compares it with the
`wrf` bundle (see below), so any change to WRF's output fails it. It takes
about 5 minutes and needs the image. To run only it, after `make build`:

```shell
docker run --rm -v "$PWD":/app -v /app/.venv openmethane \
  pytest -r a -v tests/integration/wrf
```

The first run downloads the day's FNL analyses, about 3.4 GB, into `data/fnl`,
and later runs reuse them. When running pytest in a container yourself, as CI
does, `WRF_TEST_FNL_CACHE_PATH` sets another folder in the container to keep
them in.

## WRF test data

The WRF integration test compares its output with the `wrf` bundle,
`https://openmethane.s3.amazonaws.com/tests/wrf/wrf-test-data.<YYYYMMDD>.tar.gz`
in the Open Methane public data store. It holds the WRF step's published output
for the same day, with a README inside saying how it was made. The FNL analyses
aren't in it: the test downloads them from GDEX, and the `test-wrf` CI job
caches them.

The bundle is date-stamped, so changing it doesn't change what older commits
fetch. To change it, unpack the current bundle into a folder outside the
repository, make the change, update its README, and pack it again:

```shell
tar -C wrf-test-data -czf wrf-test-data.$(date +%Y%m%d).tar.gz .
sha256sum wrf-test-data.$(date +%Y%m%d).tar.gz
```

Upload it beside the old one, and in the same change update its `url`,
`sha256` and `made_by` in `tests/test-data/bundles.yaml`. A change that is
meant to change WRF's output needs a new bundle made from its own output, and
review as a change of input meteorology. Make it with `wrf run` and the
settings the test sets in its `wrf_environment` fixture, including `NCPUS=1`:
the rank count changes WRF's output at rounding level. The output of a failed
test is kept under pytest's temporary folder, and in CI is uploaded as the
`wrf-output` artifact.

The unit tests in `tests/unit/wrf/test_namelists.py` do the same for the
namelists, against fixtures in `tests/unit/wrf/test_namelists/`, which
`make test-regen` rewrites.
