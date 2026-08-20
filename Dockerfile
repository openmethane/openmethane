# Adapted from https://github.com/astral-sh/uv-docker-example/blob/main/standalone.Dockerfile

# Secret management
FROM segment/chamber:2 AS chamber

# First, build the application in the `/app` directory
FROM ghcr.io/astral-sh/uv:trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Configure the Python directory so it is consistent
ENV UV_PYTHON_INSTALL_DIR=/python

# Only use the managed Python version
ENV UV_PYTHON_PREFERENCE=only-managed

WORKDIR /app

# Install Python before the project for caching
RUN --mount=type=bind,source=.python-version,target=.python-version \
    uv python install

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
# https://github.com/openmethane/CMAQ-Adjoint
FROM ghcr.io/openmethane/cmaq-adjoint:2.0.0

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

# Setup a non-root user
RUN groupadd --system --gid 1000 app \
 && useradd --system --gid 1000 --uid 1000 --create-home app

# Install the bare minimum software requirements on top of cmaq-adjoint
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

# Use the non-root user to run our application
USER app

# /opt/project is chosen because pycharm will automatically mount to this directory
WORKDIR /opt/project

# Secret management
COPY --from=chamber /chamber /bin/chamber

# Copy python and the virtual environment
COPY --from=builder --chown=python:python /python /python

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random

# Copy the application from the builder
COPY --from=builder --chown=app:app /app /opt/project

# Place executables in the environment at the front of the path
ENV PATH="/opt/project/.venv/bin:$PATH"
# Place the package root in the python import path so files in scripts/ can resolve
ENV PYTHONPATH="/opt/project/src"

# tini forwards all signals to real entrypoint
ENTRYPOINT ["tini", "--", "/opt/project/scripts/docker-entrypoint.sh"]
CMD ["/bin/bash"]
