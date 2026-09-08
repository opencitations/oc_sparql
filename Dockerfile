# SPDX-FileCopyrightText: NONE
#
# SPDX-License-Identifier: CC0-1.0

# Base image: Python slim for a lightweight container
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /uvx /bin/

# Define environment variables with default values
# These can be overridden during container runtime
ENV BASE_URL="sparql.opencitations.net" \
    LOG_DIR="/mnt/log_dir/oc_sparql"  \
    SPARQL_ENDPOINT_INDEX="http://qlever-service.default.svc.cluster.local:7011" \
    SPARQL_ENDPOINT_META="http://virtuoso-service.default.svc.cluster.local:8890/sparql" \
    SYNC_ENABLED="true"

# Ensure Python output is unbuffered
ENV PYTHONUNBUFFERED=1 \
    PATH="/website/.venv/bin:$PATH"
# Install system dependencies required for Python package compilation
RUN apt-get update && \
    apt-get install -y \
    git \
    python3-dev \
    build-essential

# Set the working directory for our application
WORKDIR /website

# Install Python dependencies from the lockfile
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

# Copy the application code from the repository to the container
COPY . .

# Expose the port that our service will listen on
EXPOSE 8080

# Start the application with gunicorn instead of python directly
CMD ["uv", "run", "gunicorn", "-c", "gunicorn.conf.py", "sparql_oc:application"]
