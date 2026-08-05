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

> [!WARNING]
> Building the `openmethane` Docker image requires access to the private
> CMAQ-Adjoint base image (`ghcr.io/openmethane/cmaq-adjoint`). Without it you
> can still develop against the published images, but `make build` and anything
> depending on it will fail. If this affects you, please create an issue or
> contact the team at inquiries@openmethane.org.
>
> Once you have access,
> [authenticate with the GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic)
> before building.

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
  --ignore=tests/integration/fourdvar
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
repository under `tests/test-data/` and `data/`, so tests do not depend on
network access or on a previous run's output.

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

## Linting and formatting

```shell
uv run ruff check .
uv run ruff format .    # or: make format
```

## Running the workflows locally

`scripts/docker-e2e-daily.sh` and `scripts/docker-e2e-monthly.sh` run a complete
daily or monthly workflow as a sequence of containers, mirroring production.

By default they pull the published `stable` images. To exercise your local
changes, build first — this assumes `openmethane`, `openmethane-prior` and
`setup-wrf` are checked out in the same parent folder:

```shell
BUILD_LOCAL_DOCKER=true bash scripts/docker-e2e-daily.sh
```

Individual images can also be overridden with `OPENMETHANE_IMAGE`,
`OPENMETHANE_PRIOR_IMAGE` and `SETUP_WRF_IMAGE`, which is useful for testing one
changed component against known-good versions of the others.

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

Use `"image": "ghcr.io/openmethane/openmethane:stable"` instead if you cannot
build locally — you can still edit and run the Python code, since only the image
build needs the private base image.

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
