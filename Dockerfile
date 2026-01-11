# Secret management
FROM segment/chamber:2 AS chamber

# Build the required dependencies
FROM continuumio/miniconda3 as builder

# Install and package up the conda environment
# Creates a standalone environment in /opt/venv
COPY environment.yml /opt/environment.yml
RUN conda env create -f /opt/environment.yml
RUN conda install -c conda-forge conda-pack
RUN conda-pack -n openmethane -o /tmp/env.tar && \
  mkdir /opt/venv && cd /opt/venv && \
  tar xf /tmp/env.tar && \
  rm /tmp/env.tar

# We've put venv in same path it'll be in final image,
# so now fix up paths:
RUN /opt/venv/bin/conda-unpack

# Install the python dependencies using uv
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/
ENV UV_PYTHON_DOWNLOADS=0 \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1

# This is deliberately outside of the work directory
# so that the local directory can be mounted as a volume of testing
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /opt/project
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --active --no-install-project
COPY . /opt/project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --active

# Then, use a final image without uv for our runtime environment
FROM debian:bookworm-slim

# Setup a non-root user
RUN groupadd --system --gid 1000 app \
 && useradd --system --gid 1000 --uid 1000 --create-home app

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

# Configure Python
ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random

# This is deliberately outside of the work directory
# so that the local directory can be mounted as a volume of testing
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Preference the environment libraries over the system libraries
ENV LD_LIBRARY_PATH="/opt/venv/lib:${LD_LIBRARY_PATH}"

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
    csh \
    make \
    nano \
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

# Copy across the virtual environment
COPY --from=builder /opt/venv /opt/venv

# Copy in CMAQ binaries
# https://github.com/openmethane/docker-cmaq
COPY --from=ghcr.io/openmethane/cmaq:5.0.2 /opt/cmaq /opt/cmaq

# Copy the application from the builder
COPY --from=builder --chown=nonroot:nonroot /opt/project /opt/project

# tini forwards all signals to real entrypoint
ENTRYPOINT ["tini", "--", "/opt/project/scripts/docker-entrypoint.sh"]
CMD ["/bin/bash"]
