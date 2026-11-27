# Testing

This guide covers running the test suite, the test data it uses, and how to
update that data. For setting up a checkout, see
[Development](development.md).

## Running the tests

The test suite needs the compiled models and command-line tools that only exist
in the container, so the canonical way to run it builds the image and runs
`pytest` inside:

```shell
make docker-test
```

Inside the container (or on a machine with everything installed), run it
directly:

```shell
uv run python -m pytest -r a -v
```

This runs everything, including the WRF integration test, which takes about 5
minutes and downloads the day's FNL analyses, about 3.4 GB, into `data/fnl` the
first time (see [WRF integration tests](#wrf-integration-tests)), and the
daily and monthly workflows for the same day in `tests/integration/workflows`,
which take about 1 and 5 minutes. It leaves out
`tests/integration/fourdvar/`, which runs only when named on the command line.

A single test:

```shell
uv run python -m pytest -v \
  tests/unit/cmaq_preprocess/test_wrf.py::test_name
```

Or from the host, without an interactive shell:

```shell
docker run --rm -v "$PWD":/app -v /app/.venv openmethane \
  uv run python -m pytest -v \
  tests/unit/cmaq_preprocess/test_wrf.py::test_name
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
uv run python -m pytest -r a -v -m "not network"
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
uv run python -m pytest -r a -v -m "not slow and not network"
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
`tests/conftest.py` named after it (`wrf_data` for `wrf`), and unpacks it into `data/test-cache/`, where later runs
reuse it. `--test-cache` sets another folder. A bundle the cache doesn't hold
yet needs a connection, but our own bundles aren't marked `network`: unlike a
third-party service, a bundle in the data store never changes.

## Regression fixtures

Data-producing code is covered by
[pytest-regressions](https://pytest-regressions.readthedocs.io/), comparing
output against fixtures in `tests/test-data/`. When you change what a step
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
  python -m pytest -r a -v tests/integration/wrf
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
