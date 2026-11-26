# syntax=docker/dockerfile:1
# Adapted from https://github.com/astral-sh/uv-docker-example/blob/main/standalone.Dockerfile

# Secret management
FROM segment/chamber:2 AS chamber

# The models: CMAQ, CMAQ-Adjoint, and WRF with WPS, as Debian packages attached
# to their GitHub releases. Each is fetched into its own stage, pinned by URL
# and checksum, and installed from a bind mount on that stage below, so the .deb
# never becomes part of an image layer.
#
# Changing a version changes the model that produces the results, so treat it
# as a possible change to science outputs. To try an unmerged model change,
# replace a stage when building, without editing this file; see "Testing an
# unmerged model change" in docs/guides/development.md. A pin to a `dev-pr`
# pre-release is for testing only, and CI fails if one is merged.

# https://github.com/openmethane/CMAQ: MCIP, ICON and BCON
FROM scratch AS cmaq-deb
ADD --checksum=sha256:c4e21a26bd74363e486765726a6c8b7df46060555fab0f09f42a1d54b7231c24 \
    https://github.com/openmethane/CMAQ/releases/download/v1.1.0/openmethane-cmaq_1.1.0_amd64.deb /

# https://github.com/openmethane/CMAQ-Adjoint: ADJOINT_FWD and ADJOINT_BWD
FROM scratch AS cmaq-adjoint-deb
ADD --checksum=sha256:6ca0028960aec72ff8d8380500c93b776977203bca4129d9cf0d54fe9307486c \
    https://github.com/openmethane/CMAQ-Adjoint/releases/download/v2.2.0/openmethane-cmaq-adjoint_2.2.0_amd64.deb /

# https://github.com/openmethane/build-wrf: WRF and WPS, in /opt/wrf and /opt/wps
FROM scratch AS wrf-deb
ADD --checksum=sha256:e45b2a0aa45fb69a90798ac1444ead2e59d528690e220dcc616f8d92fb771500 \
    https://github.com/openmethane/build-wrf/releases/download/v4.5.1-1/openmethane-wrf_4.5.1-1_amd64.deb /

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
FROM debian:trixie-slim

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

# Install the models. apt installs the libraries, mpich and csh they declare in
# their Depends, so nothing here lists them. The bind mounts mean the .deb files
# are not left in the image. The file names are matched, rather than every .deb,
# because a CMAQ build also makes openmethane-cmaq-dev, which isn't wanted here.
RUN --mount=type=bind,from=cmaq-deb,target=/debs/cmaq \
    --mount=type=bind,from=cmaq-adjoint-deb,target=/debs/cmaq-adjoint \
    --mount=type=bind,from=wrf-deb,target=/debs/wrf <<EOT
set -e
apt-get update -qy
apt-get install -qyy \
    -o APT::Install-Recommends=false \
    -o APT::Install-Suggests=false \
    /debs/cmaq/openmethane-cmaq_*.deb \
    /debs/cmaq-adjoint/openmethane-cmaq-adjoint_*.deb \
    /debs/wrf/openmethane-wrf_*.deb

apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
EOT

# Install the bare minimum software requirements
RUN <<EOT
set -e
apt-get update -qy
apt-get install -qyy \
    -o APT::Install-Recommends=false \
    -o APT::Install-Suggests=false \
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

# Where the WRF step finds them
ENV WRF_INSTALL_DIR=/opt/wrf \
  WPS_INSTALL_DIR=/opt/wps

# The models are also checked at the paths the WRF step and .env.docker* point
# at, in case a package changes where it installs.
COPY docker/check-binaries.sh /usr/local/bin/check-binaries.sh
RUN check-binaries.sh --command mpirun --command csh \
    --package openmethane-cmaq --package openmethane-cmaq-adjoint \
    --package openmethane-wrf \
    /opt/wrf /opt/wps /opt/cmaq/bin \
 && test -x /opt/wrf/main/wrf.exe \
 && test -x /opt/wrf/main/real.exe \
 && test -x /opt/wps/ungrib.exe \
 && test -x /opt/wps/metgrid.exe \
 && test -x /opt/wps/link_grib.csh \
 && test -f /opt/wps/metgrid/METGRID.TBL \
 && test -f /opt/wps/ungrib/Variable_Tables/Vtable.GFS \
 && test -n "$(ls /opt/wrf/run)" \
 && test -x /opt/cmaq/bin/mcip.exe \
 && test -x /opt/cmaq/bin/ICON_CH4only/ICON_CH4only \
 && test -x /opt/cmaq/bin/BCON_CH4only/BCON_CH4only \
 && test -x /opt/cmaq/bin/ADJOINT_FWD \
 && test -x /opt/cmaq/bin/ADJOINT_BWD

# Secret management
COPY --from=chamber /chamber /bin/chamber

# Copy python and the virtual environment
COPY --from=builder --chown=python:python /python /python

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random

# Copy the application from the builder
COPY --from=builder --chown=app:app /app /app

# Install ca-certificates after the application, unlike the packages above, so
# any change to the repo reinstalls it and picks up trust store updates
RUN <<EOT
set -e
apt-get update -qy
apt-get install -qyy \
    -o APT::Install-Recommends=false \
    -o APT::Install-Suggests=false \
    ca-certificates

apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
EOT

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"
# Place the package root in the python import path so files in scripts/ can resolve
ENV PYTHONPATH="/app/src"

# Use the non-root user to run our application
USER app

WORKDIR /app

# tini forwards all signals to real entrypoint
# The debug entrypoint is temporary, and wraps docker-entrypoint.sh to log what
# each container costs. Point this back at docker-entrypoint.sh to remove it.
ENTRYPOINT ["tini", "--", "/app/scripts/docker-entrypoint-debug.sh"]
CMD ["/bin/bash"]
