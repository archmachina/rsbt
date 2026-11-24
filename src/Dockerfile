

# test_BUILD_OPTS --build-arg use_image=testing
ARG use_image=base

################
# Base image
FROM python:3.13-slim AS base

# git is required at runtime by rsbt's Util.git_* helpers, and by this
# image's own test suite, which exercises them against real git repos
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Work directory
RUN mkdir -p /work/bin && chmod 777 /work
WORKDIR /work
ENV HOME=/work

# Create local user account
RUN groupadd -g 1000 -r user && \
  useradd -u 1000 -g 1000 -d /work user
USER 1000:1000

# git needs an identity to create commits, which the test suite does
# against throwaway repos under a temp directory
RUN git config --global user.email "test@example.com" && \
    git config --global user.name "rsbt tests" && \
    git config --global init.defaultBranch main

# Set up python venv
RUN python3 -m venv /work/env && \
    /work/env/bin/pip install --no-cache-dir --upgrade pip
ENV PATH="/work/env/bin:$PATH"

# Install the package's own runtime dependencies
COPY requirements.txt /work/
RUN python3 -m pip install --no-cache-dir -r /work/requirements.txt && \
    rm -f /work/requirements.txt

COPY rsbt /work/rsbt
ENV PYTHONPATH=/work

################
# Testing image - the last stage, so a plain "docker build" produces this.
# Used as a lint/test gate: install the test requirements, then lint. Run
# the built image (its entrypoint runs pytest) to also execute the tests.
FROM base AS testing

COPY tests/requirements.txt /work/test-requirements.txt
RUN python3 -m pip install --no-cache-dir -r /work/test-requirements.txt && \
    rm -f /work/test-requirements.txt

COPY tests /work/tests

COPY tests/entrypoint /work/bin/test-entrypoint
ENTRYPOINT [ "/work/bin/test-entrypoint" ]
