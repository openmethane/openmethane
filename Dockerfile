# Secret management
FROM segment/chamber:2 AS chamber

# Build the reqired depencies
FROM continuumio/miniconda3 as builder

# Install and package up the conda environment
# Creates a standalone environment in /opt/venv
COPY environment.yml /opt/environment.yml
RUN conda env create -f /opt/environment.yml
RUN conda install -c conda-forge conda-pack poetry=1.8.2
RUN conda-pack -n openmethane -o /tmp/env.tar && \
  mkdir /opt/venv && cd /opt/venv && \
  tar xf /tmp/env.tar && \
  rm /tmp/env.tar

# We've put venv in same path it'll be in final image,
# so now fix up paths:
RUN /opt/venv/bin/conda-unpack

# Install the python dependencies using poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_HOME='/opt/venv' \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# This is deliberately outside of the work directory
# so that the local directory can be mounted as a volume of testing
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /opt/venv

COPY pyproject.toml poetry.lock ./
RUN touch README.md

# This installs the python dependencies into /opt/venv
RUN --mount=type=cache,target=$POETRY_CACHE_DIR \
    /opt/conda/bin/poetry install --no-ansi --no-root

# Container for running the project
# This isn't a hyper optimised container but it's a good starting point
FROM debian:bookworm

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
ENV TARGET=docker \
    STORE_PATH=/opt/project/data \
    DOMAIN_NAME=aust-test \
    DOMAIN_VERSION=v1 \
    START_DATE=2022-07-22 \
    END_DATE=2022-07-22

RUN apt-get update && \
    apt-get install -y csh make nano jq curl tree awscli tini && \
    rm -rf /var/lib/apt/lists/*

# /opt/project is chosen because pycharm will automatically mount to this directory
WORKDIR /opt/project

# Secret management
COPY --from=chamber /chamber /bin/chamber

# Copy across the virtual environment
COPY --from=builder /opt/venv /opt/venv

# Copy in CMAQ binaries
# https://github.com/openmethane/docker-cmaq
COPY --from=ghcr.io/openmethane/cmaq:5.0.2 /opt/cmaq /opt/cmaq

# Install the local package in editable mode
# Requires scaffolding the src directories
COPY pyproject.toml poetry.lock README.md ./
RUN mkdir -p src/fourdvar src/obs_preprocess src/cmaq_preprocess src/util && \
    touch src/fourdvar/__init__.py src/obs_preprocess/__init__.py src/cmaq_preprocess/__init__.py src/util/__init__.py
RUN pip install -e .

# Copy in the rest of the project
# For testing it might be easier to mount $(PWD):/opt/project so that local changes are reflected in the container
COPY . /opt/project

# tini forwards all signals to real entrypoint
ENTRYPOINT ["tini", "--", "/opt/project/scripts/docker-entrypoint.sh"]
CMD ["/bin/bash"]
