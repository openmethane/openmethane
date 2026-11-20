# Adapted from https://github.com/astral-sh/uv-docker-example/blob/main/standalone.Dockerfile

# Secret management
FROM segment/chamber:2 AS chamber

# WRF and WPS, from https://github.com/openmethane/docker-wrf. Pinned by digest
# because docker-wrf overwrites the 4.5.1 tag on every push to main. Changing
# the digest changes the model that produces the meteorology, so treat it as a
# possible change to science outputs: compare WRF output before and after.
FROM ghcr.io/openmethane/wrf:4.5.1@sha256:7cd949adef3bc1172a139f6d472e050aceba8296dbd78d743e1737a831249759 AS wrf

# Stage only the files needed to run WPS, real.exe and wrf.exe, at the paths
# they have in the wrf image. This leaves out the sources, object files and
# unused programs, about 465 MB. cp -L follows symlinks: some files in run/
# link into the build tree, and the WPS programs link into their src/ folders.
FROM wrf AS wrf-runtime
RUN <<EOT
set -eu
mkdir -p /staging/wrf/main /staging/wrf/run \
    /staging/wps/geogrid /staging/wps/metgrid /staging/wps/ungrib

cp /opt/wrf/main/wrf.exe /opt/wrf/main/real.exe /staging/wrf/main/
# run/ links the programs from main/; only its data files are needed. The
# `+` form makes find fail if cp does, so a dangling link fails the build.
find /opt/wrf/run -mindepth 1 -maxdepth 1 ! -name '*.exe' \
    -exec cp -L -t /staging/wrf/run/ {} +

cp -L /opt/wps/geogrid.exe /opt/wps/ungrib.exe /opt/wps/metgrid.exe \
    /opt/wps/link_grib.csh /staging/wps/
cp -L /opt/wps/geogrid/GEOGRID.TBL* /staging/wps/geogrid/
cp -L /opt/wps/metgrid/METGRID.TBL* /staging/wps/metgrid/
cp -rL /opt/wps/ungrib/Variable_Tables /staging/wps/ungrib/
EOT

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
FROM ghcr.io/openmethane/cmaq-adjoint:2.0.1

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

# The libraries the WRF and WPS binaries link against directly, and
# the programs they run (mpirun, and csh for link_grib.csh). Installed by name
# rather than relying on the cmaq-adjoint base happening to have them.
# docker/check-binaries.sh, run below, fails the build if this list falls
# behind the binaries.
RUN <<EOT
set -e
apt-get update -qy
apt-get install -qyy \
    -o APT::Install-Recommends=false \
    -o APT::Install-Suggests=false \
    libgfortran5 \
    libmpich12 \
    libnetcdf22 \
    libnetcdff7 \
    libpng16-16t64 \
    mpich \
    csh

apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
EOT

COPY --from=wrf-runtime /staging/wrf /opt/wrf
COPY --from=wrf-runtime /staging/wps /opt/wps

COPY docker/check-binaries.sh /usr/local/bin/check-binaries.sh
RUN check-binaries.sh --command mpirun --command csh \
    /opt/wrf /opt/wps /opt/cmaq/bin

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
