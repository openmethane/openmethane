# Development

This guide is for contributing changes to Open Methane. If you only want to run
the model, see the [Quickstart](quickstart.md).

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) for Python
  dependency management.
- [Docker](https://www.docker.com/) 23 or later. Almost all development happens
  in the container, because the compiled models live there.

```shell
git clone git@github.com:openmethane/openmethane.git
cd openmethane
uv sync
```

`uv sync` creates a `.venv` with the locked dependencies, which is enough for
linting, unit tests that don't touch the models, and editor tooling.

> [!NOTE]
> Building the `openmethane` image downloads the CMAQ, CMAQ-Adjoint, and WRF and
> WPS packages from GitHub releases. They are public and need no
> authentication, but the first `make build` on a machine takes a while.

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
first time (see [WRF integration tests](#wrf-integration-tests)). It leaves out
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

Tests set their own configuration, so `TARGET` and `.env` files are ignored. A
test that needs configuration takes the `au_test_config` fixture. An error
naming `/nonexistent-test-configuration` means a test read configuration
without it.

Test data too large or binary for git is in bundles in the Open Methane public
data store, listed with their hashes in `tests/test-data/bundles.yaml`. A test
that needs one downloads it the first time, through a fixture in
`tests/conftest.py` named after it (`wrf_data` for `wrf`), and unpacks it into `data/test-cache/`, where later runs
reuse it. `--test-cache` sets another folder. A bundle the cache doesn't hold
yet needs a connection, but our own bundles aren't marked `network`: unlike a
third-party service, a bundle in the data store never changes.

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

Two categories of test will not pass outside the container:

- Tests requiring binaries such as the CMAQ adjoint or `ncatted`.
- Everything under `tests/integration/fourdvar/`, which is left out by default. These
  depend on input data that has not been provided in a reproducible way. They
  should be fixed when possible.

### Regression fixtures

Data-producing code is covered by
[pytest-regressions](https://pytest-regressions.readthedocs.io/), comparing
output against fixtures in `tests/test-data/`. When you change what a step
produces, regenerate the fixtures and read the diff carefully — an unexpected
change in a fixture is usually the bug, not the fixture being stale:

```shell
make test-regen
```

### WRF integration tests

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

### WRF test data

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

## Linting and formatting

```shell
uv run ruff check .
uv run ruff format .    # or: make format
```

## Running the workflows locally

`scripts/docker-e2e-daily.sh` and `scripts/docker-e2e-monthly.sh` run a complete
daily or monthly workflow as a sequence of containers, mirroring production.

By default they pull the published `stable` images. To exercise your local
changes, build first — this assumes `openmethane` and `openmethane-prior` are
checked out in the same parent folder:

```shell
BUILD_LOCAL_DOCKER=true bash scripts/docker-e2e-daily.sh
```

Individual images can also be overridden with `OPENMETHANE_IMAGE` and
`OPENMETHANE_PRIOR_IMAGE`, which is useful for testing one changed component
against known-good versions of the others.

Alerts have their own pair of scripts, `scripts/docker-alerts-baseline.sh` and
`scripts/docker-create-alerts.sh`, which read the outputs of completed daily
runs.

All four share `scripts/docker-common.sh`, which holds the image names, defaults
and helpers. Every variable in it is set with `:-`, so anything already in the
environment wins — that is how the overrides above take effect.

These scripts default to the `au-test` 10 x 10 domain and store data in
`/tmp/openmethane-e2e`. They work on the full domain, but will take many, many
hours on consumer hardware.

For a shell in the container to run steps by hand:

```shell
make start
```

Individual steps can also be run through `make`:

```shell
make prepare-templates
```

See [Scripts](../reference/scripts.md) for the full inventory.

## Editor setup

Because the compiled models only exist inside the container, an editor is most
useful when its interpreter also runs inside the container. Otherwise imports
resolve but nothing runs.

The details you need for any editor:

| Setting | Value                                        |
| --- |----------------------------------------------|
| Interpreter | `/app/.venv/bin/python` (Python 3.12)        |
| Working directory | `/app`                               |
| Repository mount | your checkout → `/app`               |
| `PYTHONPATH` | `/app/src`, already set in the image |

Mounting your checkout over `/app` is what makes edits take effect
without rebuilding — the image ships a copy of the code, and the mount shadows
it. The virtual environment lives at `/app/.venv`, inside that path, so the
mount would shadow it too. Keep it by mounting an anonymous volume over the
`.venv` directory (`-v /app/.venv`), which is what the `make` targets do.

### VS Code

Install the
[Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
extension, then add `.devcontainer/devcontainer.json`:

```json
{
  "name": "openmethane",
  "image": "openmethane",
  "workspaceFolder": "/app",
  "workspaceMount": "source=${localWorkspaceFolder},target=/app,type=bind",
  "mounts": ["target=/app/.venv,type=volume"],
  "customizations": {
    "vscode": {
      "settings": {
        "python.defaultInterpreterPath": "/app/.venv/bin/python"
      },
      "extensions": ["ms-python.python", "charliermarsh.ruff"]
    }
  }
}
```

Then run **Dev Containers: Reopen in Container** from the command palette.

Use `"image": "ghcr.io/openmethane/openmethane:stable"` instead to skip building
locally — you can still edit and run the Python code.

Tests run as normal once attached, without the `docker run` wrapper:

```shell
python -m pytest -r a -v
```

The `/app/.venv` volume keeps the container's virtual environment from being
shadowed by the workspace mount. To also mount data or credentials from the
host, mirroring what `make start` does, add them to the same `mounts` list:

```json
"mounts": [
  "target=/app/.venv,type=volume",
  "source=${localEnv:HOME}/.cdsapirc,target=/root/.cdsapirc,type=bind"
]
```

### Other editors

Any editor with container support can use the same values from the table above.
PyCharm Professional does this through a
[remote interpreter](https://www.jetbrains.com/help/pycharm/using-docker-as-a-remote-interpreter.html),
though the feature is not available in the free Community edition and creates a
new container per run.

`.vscode/settings.json`, `.vscode/launch.json` and `.idea/` are gitignored, so
personal editor configuration stays out of the repository. `.devcontainer/` is
not ignored — it is shared configuration, so commit it if you add it.

## Logging

Use `get_logger` from `openmethane.util.logger` rather than configuring
`logging` directly — it handles the `LOG_LEVEL` and `LOG_FILE` environment
variables consistently across the project. See
[Troubleshooting](../troubleshooting.md#logging).

A new command with its own entry point can instead use
`logging.getLogger(__name__)` in each module and call
`configure_logging` from `openmethane.util.logging` once, in the entry point.
That module reads `LOG_LEVEL` when it is called rather than on import.

## Shared utilities

These modules in `openmethane.util` read no configuration on import, so any
part of the project can use them. Prefer them in new code.

| Module | Use it to |
| --- | --- |
| `process` | Run an external program with `run_program`: a list of arguments, output to a log file, failure from the exit code and an optional success line, never from stderr |
| `download` | Download files with `download` or `fetch_missing`: retries with backoff, and a file only appears once it is complete |
| `logging` | Configure logging once, from an entry point |
| `decomposition` | Split a grid across MPI ranks with `solve_decomposition`, given the model's halo width |

## Code review

Review isn't only for catching bugs. It keeps the team aware of how the
project is changing and builds agreement on decisions. Not every pull request
benefits from that. The author of a pull request decides whether it needs a
human review, and says so on the first line of the description, where it
shows up in email notifications:

```markdown
**Review:** needed — changes science outputs: the default SWIR AOD cutoff drops more soundings
```

```markdown
**Review:** not needed — patch dependency updates, CI passing; merging Thursday unless someone objects
```

Always give a reason. The reason lets everyone else check the decision at a
glance, and shows over time whether these categories need adjusting.

The lists below are a guide, not rules, and some judgement is still needed.
When a change doesn't clearly fit, ask: would the rest of the team want to
know about this, or have a say in it? If so, it needs review.

### Review needed

- **Changes to science outputs.** Any change to the posterior emissions, or to
  what feeds them (observation files, the observation operator, ICON and
  BCON, the prior handling, the cost function, the minimiser and its
  defaults), needs review, however small the fix that causes it. So does a
  change to the alerts.
- **Refactors that change structure or behaviour across more than one file.**
- **New concepts or features**, including new data sources, control
  variables, diagnostics, output files and methodology decisions. A new
  feature needs review even when existing outputs don't change.
- **Documentation changes.** If something is worth documenting, it's worth
  the rest of the team knowing about it and agreeing with it. This doesn't
  include fixes to typos, grammar or formatting, which are mechanical changes.
- **Changes that make a daily or monthly run fail, or stop failing, where it
  didn't before.** Make sure whoever looks after production runs knows about
  these.

### Review not needed

- **Infrastructure changes** made by the person who looks after the
  infrastructure.
- **Mechanical changes**, such as small corrections and bug fixes whose
  correctness is established by tests, tool-generated changes such as
  running a formatter, and fixes to typos, grammar or formatting in
  documentation. Being mechanical is what matters here, not size: a
  formatter run that touches every file is still mechanical.
- **Changes to tests only**, such as a new regression test, as long as the
  code under test doesn't change.
- **Minor or patch dependency updates.** Major version updates need review.
- **Small changes to logging, warnings, types and project settings.**
- **Experiments that won't be merged.** Say so on the first line, for example
  `**Review:** not needed — experiment, not for merge`. Discussion of the
  results belongs in the issue the experiment is for.

### Science code isn't the same as science outputs

A change can touch science code without changing any outputs. For example,
it can fix a crash in a path that never produced results, or make the run
fail on bad input instead of producing NaNs. These changes don't need review,
but the reason has to give the evidence that the outputs don't change, not
just say so. If you can't write that sentence, choose "needed".

### Agent review before a pull request

If you use an agent such as Claude Code to prepare a change, `CLAUDE.md`
asks it to review anything that isn't mechanical with a fresh reviewer
(`.claude/agents/reviewer.md`) before it opens the pull request. The agent
fixes clear problems itself and brings anything else to you. For riskier
changes it offers a second, independent review. Each review costs tokens, so
you can tell the agent to skip it. This is part of
preparing the change, not a substitute for human review: it doesn't change
whether a pull request needs review.

### Not needed doesn't mean merged immediately

For a "not needed" pull request, say when you'll merge it. This gives
everyone a chance to ask for a review before then. Anyone can switch a pull
request to "needed", and then it waits for a review as usual.

### Examples

| Pull request | First line |
|---|---|
| [#243](https://github.com/openmethane/openmethane/pull/243) | **Review:** not needed — automated `uv format` across the codebase, plus fixes for warnings from the test suite |
| [#257](https://github.com/openmethane/openmethane/pull/257) | **Review:** not needed — tests only: a regression guard for #236; no source code changes |
| [#287](https://github.com/openmethane/openmethane/pull/287) | **Review:** not needed — security fix: removes the compromised eMudhra CA roots from the image; minor dependency updates, CI passing |
| [#292](https://github.com/openmethane/openmethane/pull/292) | **Review:** not needed — experiment, not for merge |
| [#280](https://github.com/openmethane/openmethane/pull/280) | **Review:** needed — changes science outputs: the default SWIR AOD cutoff drops more soundings |
| [#291](https://github.com/openmethane/openmethane/pull/291) | **Review:** needed — changes science outputs: each daily BCON now has a record at every CAMS time instead of one snapshot |
| [#281](https://github.com/openmethane/openmethane/pull/281) | **Review:** needed — new feature: cost decomposition in the logs and gradient files in the archive; existing outputs unchanged |

#281 doesn't change any existing outputs, but it adds new ones and a new
diagnostic for the team to rely on, so it still needs review.

## Changelog

Every pull request adds a file to `changelog/`, following
[towncrier](https://towncrier.readthedocs.io/) conventions. Name it
`{PR_NUMBER}.{type}.md`, where type is one of `breaking`, `feature`,
`improvement`, `fix`, `docs`, `deprecation` or `trivial`.

Preview how the next release's notes will read:

```shell
make changelog-draft
```

## Docker images

A Docker image is built and pushed to the GitHub Container Registry for every
push to `main` and for each pull request. See
[the package list](https://github.com/orgs/openmethane/packages) for what is
available.

Pull request builds are tagged `pr-{NUMBER}`, which is handy for reproducing a
reviewer's problem exactly:

```shell
OPENMETHANE_IMAGE=ghcr.io/openmethane/openmethane:pr-201 \
  bash scripts/docker-e2e-daily.sh
```

### Testing an unmerged model change

The `Dockerfile` installs CMAQ, CMAQ-Adjoint, and WRF with WPS, from named
stages, `cmaq-deb`, `cmaq-adjoint-deb` and `wrf-deb`, which fetch each package
from a GitHub release, pinned by URL and checksum. BuildKit can replace a named stage when building, so an
image with an unmerged model change needs no edit to the `Dockerfile`.

**Locally**, take the package from the model pull request's CI run. The artifact
is called `debs`. `<branch>` is the model pull request's branch:

```shell
RUN_ID=$(gh run list -R openmethane/CMAQ-Adjoint --branch <branch> --workflow build.yaml \
  --status success --limit 1 --json databaseId -q '.[0].databaseId')
gh run download "$RUN_ID" -R openmethane/CMAQ-Adjoint -n debs -D debs/cmaq-adjoint

docker build --build-context cmaq-adjoint-deb=./debs/cmaq-adjoint -t openmethane:dev .
```

The same works for WRF and WPS, with `-R openmethane/build-wrf`, `-D debs/wrf`
and `--build-context wrf-deb=./debs/wrf`, and for CMAQ, with `-R openmethane/CMAQ`,
`-D debs/cmaq` and `--build-context cmaq-deb=./debs/cmaq`. A CMAQ run also downloads
`openmethane-cmaq-dev`, which the image doesn't install and ignores. The
`debs/` folder is in `.gitignore` and `.dockerignore`.

**In CI, or in AWS**, the model repository's `Publish dev build` workflow
attaches the package to a pre-release tagged `dev-pr<PR>-<sha7>`. Run it on the
model pull request's branch:

```shell
gh workflow run dev-build.yaml -R openmethane/CMAQ-Adjoint --ref <branch>
```

The workflow's job summary lists the `ADD --checksum=… <url> /` line to paste
into the matching stage of the `Dockerfile`. Pin it in the Open Methane pull
request, and its CI builds and pushes the pull request image as usual, ready to
run in AWS.

**A dev pin can't be merged.** CI fails if the `Dockerfile` downloads from a
`dev-pr` release, and the model repository deletes the pre-release when its pull
request closes. Move the pin to a real release before merging, and treat the
change as a possible change to science outputs.

### Checking what an image contains

```shell
docker run --rm --entrypoint dpkg-query ghcr.io/openmethane/openmethane:latest \
  -W 'openmethane-*'
```

lists the version of each model package in an image. The build also runs
`docker/check-binaries.sh`, which fails if a model binary can't find a library,
or `mpirun` or `csh` is missing.

## Preparing a release

When changes on `main` should go to production or be released publicly:

1. Visit the
   [Create release](https://github.com/openmethane/openmethane/actions/workflows/release.yaml)
   action.
2. Click "Run workflow", leaving `main` selected.
3. Based on the contents of `changelog/`, choose patch, minor or major.
4. Run it.

The workflow will:

- bump the project version to the next semver version
- tag the repository `vX.Y.Z`
- fold the changelog entries into `docs/changelog.md`
- prepare a GitHub Release with those notes
- build and push a container image with the same version tag
