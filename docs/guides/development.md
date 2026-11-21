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
> Building the `openmethane` image pulls `ghcr.io/openmethane/cmaq-adjoint` as
> its base. That image is public and needs no authentication, but it is large,
> so the first `make build` on a machine takes a while.

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
TARGET=docker-test uv run python -m pytest -r a -v tests \
  --ignore=tests/integration/fourdvar -m "not wrf_integration"
```

A single test:

```shell
TARGET=docker-test uv run python -m pytest -v \
  tests/unit/cmaq_preprocess/test_wrf.py::test_name
```

Or from the host, without an interactive shell:

```shell
docker run --rm -v $(PWD):/app -v /app/.venv openmethane \
  TARGET=docker-test uv run python -m pytest -v \
  tests/unit/cmaq_preprocess/test_wrf.py::test_name
```

Always set `TARGET=docker-test`. That target points at test data tracked in the
repository under `tests/test-data/` and `data/`, so tests do not depend on a
previous run's output.

A handful of tests do reach third-party services, and are marked `network`.
Deselect them to run offline, or to keep somebody else's outage from failing the
suite:

```shell
TARGET=docker-test uv run python -m pytest -r a -v tests \
  --ignore=tests/integration/fourdvar -m "not network and not wrf_integration"
```

Two categories of test will not pass outside the container:

- Tests requiring binaries such as the CMAQ adjoint or `ncatted`.
- Everything under `tests/integration/fourdvar/`, which is excluded above. These
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

Tests marked `wrf_integration`, in `tests/integration/wrf/`, run the real WRF
and WPS programs for au-test on 2022-12-07 and check the published output
against the [WRF output contract](../reference/wrf-outputs.md). They take about
5 minutes and need the image, so `make test` leaves them out. Run them with:

```shell
make test-wrf
```

The first run downloads the day's FNL analyses, about 3.4 GB, into `data/fnl`,
and later runs reuse them. When running pytest in a container yourself, as CI
does, `WRF_TEST_FNL_CACHE_PATH` sets another folder in the container to keep
them in.

### WRF test data

The `test-wrf` CI job runs the WRF integration tests, then runs WRF again and
compares the output with setup-wrf's for the same day, until production has
moved off setup-wrf
([#323](https://github.com/openmethane/openmethane/issues/323)). setup-wrf's output is in a bundle in
the Open Methane public data store,
`https://openmethane.s3.amazonaws.com/tests/wrf/wrf-test-data.<YYYYMMDD>.tar.gz`,
with a README inside saying how it was made. The FNL analyses aren't in it:
the job downloads them from GDEX and caches them.

The bundle is date-stamped, so changing it doesn't change what older commits
fetch. To change it, unpack the current bundle into a folder outside the
repository, make the change, update its README, and pack it again:

```shell
tar -C wrf-test-data -czf wrf-test-data.$(date +%Y%m%d).tar.gz .
```

Upload it beside the old one and point `WRF_TEST_DATA_URL` in
`.github/workflows/build_docker.yaml` at it, in the same change.

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
TARGET=docker-test python -m pytest -r a -v tests \
  --ignore=tests/integration/fourdvar
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
