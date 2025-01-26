<!--
Copyright (C) 2025 Roberto Rossini <roberros@uio.no>

SPDX-License-Identifier: MIT
-->

# Building the Docker image

This document contains simple instructions on how to build the Dockerfile contained in this repository

The instructions assume that you have access to a machine with docker already installed and running.
Note that on Linux you may also need root permissions.

## Picking the correct CUDA version

Before building the Dockerfile, it is important to ensure that the CUDA libraries installed inside the container
are compatible with the Nvidia drivers installed on the machine where the container will be deployed.

If you know what you are doing, you can skip reading the rest of the section.

Otherwise, here are some simple instructions:

1. Check the version of the drivers installed on the target machine by e.g. running `nvidia-smi` in a terminal
2. Consult [this](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html#id5) compatibility table to find a compatible CUDA version
3. Head over to the [nvidia/cuda](https://hub.docker.com/r/nvidia/cuda/tags) page on DockerHub and search for tags matching `base-ubuntu24.04`
4. Find the most recent version that is compatible with your machine according to the table from point #2
5. Extract the version component from the tag (e.g. tag `12.6.3-base-ubuntu24.04` corresponds to version 12.6.3)

The version obtained following the above procedure corresponds to the `CUDA_VERSION` used in later steps.

## Building the Docker image

Commands listed in this section should be executed from the root of this repository.

### Building the image with default settings

```bash
docker build . -t colabfold:latest --load
```

This will build a docker image with the colabfold version listed in the Dockerfile (look for a line starting with `ARG COLABFOLD_VERSION=`).

### Changing colabfold version

Replace `x.x.x` with one of the versions available through bioconda - [link](https://anaconda.org/bioconda/colabfold).

```bash
docker build . -t colabfold:x.x.x --load --build-arg='COLABFOLD_VERSION=x.x.x'
```

### Changing the base image

See [nvidia/cuda](https://hub.docker.com/r/nvidia/cuda/tags) for the list of available bases.

```bash
docker build . -t colabfold:latest --load --build-arg='BASE_IMAGE=base-ubuntu22.04'
```

### Closing notes

The above instructions assume that the machine building the Dockerfile and the machine where the image is deployed have the same architecture.
You can check the architecture used by the docker daemon by running `docker info` in a terminal and looking for the `Architecture` field.
Otherwise, you can check the output of `uname -p` on macOS or `python -c 'import platform; print(platform.machine())'` on Linux.

If the architectures differ, then things become a bit involved, and it is not easy to provide a recipe with the steps to be performed.

In general, you have to configure your builder machine to support multi-platform builds (see [here](https://docs.docker.com/build/building/multi-platform/), this is the tricky part),
and then pass the target platform to `docker build` using the `--platform` option.

## Exporting the image

This is only necessary if the build and deployment machines are different.

This section assumes you are running the instructions on macOS or Linux.

If you are planning to deploy the container in an HPC cluster, you most likely won't have access to docker and will have to use Singularity/Apptainer (see next section).

### Export the Docker image

Exporting the image:

```bash
# Run this on the machine used to build the Dockerfile
docker save colabfold:latest | pigz -9 -p 8 > /tmp/colabfold.tar.gz
```

If you don't have `pigz` installed, replace that with `gzip` and drop `-p 8` (note that this will take a while).

Send the `.tar` to the machine where you intend to deploy the container with e.g. `rsync`, then run the following:

```bash
# Run this on this on the deployment machine
gzip -dc /tmp/colabfold.tar.gz | docker load
```

Test that the image was correctly loaded in the registry:

```console
user@dev:/tmp$ docker run --rm colabfold:latest python -c "from importlib.metadata import version; print(f\"colabfold-v{version('colabfold')}\")"

colabfold-v1.5.5
```

### Build a Singularity/Apptainer image

```bash
# Run this on the machine used to build the Dockerfile
singularity build -F /tmp/colabfold.img docker-daemon://colabfold:latest
```

Send the `.img` to the machine where you intend to deploy the container with e.g. `rsync` and run the following:

```console
# Run this on this on the deployment machine
user@dev:/tmp$ singularity run /tmp/colabfold.img python -c "from importlib.metadata import version; print(f\"colabfold-v{version('colabfold')}\")"

colabfold-v1.5.5
```

## Create and populate the cache directory

From this point onward instructions assume you are using Singularity/Apptainer.

If you instead are using docker, simply replace `singularity run --nv -B` with `docker run --user "$(id -u)" --gpus=all --rm -v` and also replace `/tmp/colabfold.img` with `colabfold:latest`.

### Downloading AlphaFold2 Weights

First pick a folder that will be used to store data required by colabfold. I am going to use `$HOME/colabfold`.

```bash
mkdir -p "$HOME/colabfold"
singularity run -B "$HOME/colabfold:/tmp/cache" /tmp/colabfold.img python -m colabfold.download
```

### Set up database to run MSA locally

This step will download a lot of data and requires plenty of storage to be available (1+ TB).

```bash
git clone https://github.com/sokrypton/ColabFold.git /tmp/colabfold
cd /tmp/colabfold
git checkout v1.5.5
mkdir -p "$HOME/colabfold/msa_db/"
MMSEQS_NO_INDEX=1 ./setup_databases.sh "$HOME/colabfold/msa_db/"
```
