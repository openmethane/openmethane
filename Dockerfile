# Adapted from https://github.com/astral-sh/uv-docker-example/blob/main/standalone.Dockerfile

# Secret management
FROM segment/chamber:2 AS chamber

# First, build the application in the `/app` directory
FROM ghcr.io/astral-sh/uv:bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Configure the Python directory so it is consistent
ENV UV_PYTHON_INSTALL_DIR=/python

# Only use the managed Python version
ENV UV_PYTHON_PREFERENCE=only-managed

# Install Python before the project for caching
RUN uv python install 3.11

# Install the virtual environment outside the work directory so the local
# prpject directory can be mounted as a volume during testing.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# install dependencies from pyproject.toml without the app, to create a
# cacheable layer that changes less frequently than the app code
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# install the app + dependencies using the uv cache from the previous step
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Then, use a final image without uv for our runtime environment
# https://github.com/openmethane/docker-cmaq-adj
FROM ghcr.io/openmethane/cmaq-adj

# These will be overwritten in GHA due to https://github.com/docker/metadata-action/issues/295
# These must be duplicated in .github/workflows/build_docker.yaml
LABEL org.opencontainers.image.title="Open Methane"
LABEL org.opencontainers.image.description="Open Methane model and tools"
LABEL org.opencontainers.image.authors="Peter Rayner <peter.rayner@superpowerinstitute.com.au>, Jared Lewis <jared.lewis@climate-resource.com>"
LABEL org.opencontainers.image.vendor="The Superpower Institute"

# OPENMETHANE_VERSION will be overridden in release builds with semver vX.Y.Z
ARG OPENMETHANE_VERSION=development
# Make the $OPENMETHANE_VERSION available as an env var inside the container
ENV OPENMETHANE_VERSION=$OPENMETHANE_VERSION

LABEL org.opencontainers.image.version="${OPENMETHANE_VERSION}"

# Setup the environment variables required to run the project
# These can be overwritten at runtime
ENV TARGET=docker

# Install the bare minimum software requirements on top of bookworm-slim
RUN <<EOT
apt-get update -qy
apt-get install -qyy \
    -o APT::Install-Recommends=false \
    -o APT::Install-Suggests=false \
    ca-certificates \
    build-essential \
    csh \
    nco \
    jq \
    curl \
    tree \
    tini

apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
EOT

# /opt/project is chosen because pycharm will automatically mount to this directory
WORKDIR /opt/project

# Secret management
COPY --from=chamber /chamber /bin/chamber

# Copy python and the virtual environment
COPY --from=builder --chown=python:python /python /python
COPY --from=builder --chown=python:python /opt/venv /opt/venv

# Copy the application from the builder
COPY --from=builder --chown=nonroot:nonroot /app /opt/project

# Put the venv at the start of the path so binaries there are preferenced
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
# Place the package root in the python import path so files in scripts/ can resolve
ENV PYTHONPATH="/opt/project/src"

# tini forwards all signals to real entrypoint
ENTRYPOINT ["tini", "--", "/opt/project/scripts/docker-entrypoint.sh"]
CMD ["/bin/bash"]
