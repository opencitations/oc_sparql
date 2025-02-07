# OpenCitations SPARQL Service

This repository contains the SPARQL service for OpenCitations, allowing users to query the OpenCitations datasets using SPARQL.

## Overview

The service provides two main SPARQL endpoints:

- **Index endpoint** (`/index`): For querying the OpenCitations Index database
- **Meta endpoint** (`/meta`): For querying the OpenCitations Meta database

## Features

- SPARQL query interface powered by YASQE/YASR
- Support for both GET and POST SPARQL queries 
- SPARQL Update queries are not permitted
- Request logging
- Docker deployment ready

## Configuration

### Environment Variables

The service requires the following environment variables:

```env
SPARQL_BASE_URL=sparql.opencitations.net
SPARQL_ENDPOINT_INDEX=http://qlever-service.default.svc.cluster.local:7011  
SPARQL_ENDPOINT_META=http://virtuoso-service.default.svc.cluster.local:8890/sparql
```

### Dockerfile

You can change these variables in the Dockerfile:

```dockerfile
# Base image: Python slim for a lightweight container
FROM python:3.11-slim

# Define environment variables with default values
# These can be overridden during container runtime
ENV SPARQL_BASE_URL="sparql.opencitations.net" \
    SPARQL_ENDPOINT_INDEX="http://qlever-service.default.svc.cluster.local:7011" \
    SPARQL_ENDPOINT_META="http://virtuoso-service.default.svc.cluster.local:8890/sparql"

# Install system dependencies required for Python package compilation
# We clean up apt cache after installation to reduce image size
RUN apt-get update && \
    apt-get install -y \
    git \
    python3-dev \
    build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory for our application
WORKDIR /website

# Clone the specific branch (sparql) from the repository
# The dot at the end means clone into current directory
RUN git clone --single-branch --branch main https://github.com/opencitations/oc_sparql .

# Install Python dependencies from requirements.txt
RUN pip install -r requirements.txt

# Expose the port that our service will listen on
EXPOSE 8080

# Start the application
# The Python script will now read environment variables for SPARQL configurations
CMD ["python3", "sparql_oc.py"]
```