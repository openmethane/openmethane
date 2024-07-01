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

MAINTAINER Jared Lewis <jared.lewis@climate-resource.com>

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
ENV TARGET=docker

RUN apt-get update && \
    apt-get install -y csh make nano && \
    rm -rf /var/lib/apt/lists/*

# /opt/project is chosen because pycharm will automatically mount to this directory
WORKDIR /opt/project

# Secret management
COPY --from=chamber /chamber /bin/chamber

# Copy across the virtual environment
COPY --from=builder /opt/venv /opt/venv

# Copy in CMAQ binaries
# https://github.com/openmethane/docker-cmaq
# TODO: temporarily pinned staging builds until this is verified to work
# Otherwise the CI will be broken for main
COPY --from=ghcr.io/openmethane/cmaq:pr-6 /opt/cmaq /opt/cmaq

# Install the local package in editable mode
# Requires scaffolding the src directories
COPY pyproject.toml poetry.lock README.md ./
RUN mkdir -p src/fourdvar src/obs_preprocess && touch src/fourdvar/__init__.py src/obs_preprocess/__init__.py
RUN pip install -e .

# Copy in the rest of the project
# For testing it might be easier to mount $(PWD):/opt/project so that local changes are reflected in the container
COPY . /opt/project


CMD ["/bin/bash"]