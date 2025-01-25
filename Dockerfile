# Copyright (C) 2025 Roberto Rossini <roberros@uio.no>
#
# SPDX-License-Identifier: MIT

ARG CUDA_VERSION=12.6.3
ARG BASE_IMAGE=base-ubuntu24.04

FROM ubuntu:24.04 AS micromamba-dl

# Feel free to override these as needed through --build-arg
ARG MICROMAMBA_VERSION=2.0.5
ARG MICROMAMBA_AMD64_SHA256=bfc2e3a414d651af7508c49998a12b5cf3c7029d56c5ef37c9a3248cd7faef78
ARG MICROMAMBA_ARM64_SHA256=aa31dd8eca5befa5bf0a0c976d8765dcf0080eb7c7e95ee1c2286191298f5ff9
ARG MICROMAMBA_PPC64LE_SHA256=4250e416f7e78e970491d685f35ce469882f637406e86b2d2cf6c8c7c2c21e0a

RUN apt-get update \
&& apt-get install \
    --no-install-recommends \
    --no-install-suggests \
    -y \
    ca-certificates \
    curl \
    tar \
    lbzip2 \
&& rm -rf /var/lib/apt/lists/*

ARG MICROMAMBA_BASE_URL='https://micro.mamba.pm/api/micromamba'

ARG TARGETARCH

RUN if [ -z "$TARGETARCH" ]; then echo "Missing TARGETARCH --build-arg" && exit 1; fi

RUN \
if   [ "$TARGETARCH" = amd64 ]; then \
  curl -L "$MICROMAMBA_BASE_URL/linux-64/2.0.5" -o /tmp/micromamba.tar.bz2 \
  && echo "$MICROMAMBA_AMD64_SHA256  /tmp/micromamba.tar.bz2" > /tmp/checksum.sha256; \
elif [ "$TARGETARCH" = arm64 ]; then \
  curl -L "$MICROMAMBA_BASE_URL/linux-aarch64/2.0.5" -o /tmp/micromamba.tar.bz2 \
  && echo "$MICROMAMBA_ARM64_SHA256  /tmp/micromamba.tar.bz2" > /tmp/checksum.sha256; \
elif [ "$TARGETARCH" = ppc64le ]; then \
  curl -L "$MICROMAMBA_BASE_URL/linux-ppc64le/2.0.5" -o /tmp/micromamba.tar.bz2 \
  && echo "$MICROMAMBA_PPC64LE_SHA256  /tmp/micromamba.tar.bz2" > /tmp/checksum.sha256; \
else \
  1>&2 echo "Architecture '$TARGETARCH' is not currently supported!" \
  && 1>&2 echo "Known arch are amd64, arm64, and ppc64le." \
  && exit 1; \
fi \
&& sha256sum -c /tmp/checksum.sha256 \
&& mkdir /tmp/micromamba \
&& tar -C /tmp/micromamba -xf /tmp/micromamba.tar.bz2 \
&& rm /tmp/checksum.sha256 /tmp/micromamba.tar.bz2


ARG CUDA_VERSION
ARG BASE_IMAGE

FROM nvidia/cuda:${CUDA_VERSION}-${BASE_IMAGE} AS base

ENV MAMBA_ROOT_PREFIX=/opt/micromamba

COPY --from=micromamba-dl /tmp/micromamba/bin/micromamba /usr/local/bin/micromamba
COPY --from=micromamba-dl /tmp/micromamba/info/licenses /usr/local/share/

ARG COLABFOLD_VERSION=1.5.5

RUN CONDA_OVERRIDE_CUDA="$(echo "$CUDA_VERSION" | cut -d . -f 1-2)" \
    micromamba create \
      -n colabfold \
      -c conda-forge \
      -c bioconda \
      -y \
      "colabfold=$COLABFOLD_VERSION" \
      "jaxlib==*=cuda*" \
&& micromamba clean --all -y

ENV PATH="/opt/micromamba/envs/colabfold/bin:$PATH"
ENV MPLBACKEND=Agg
ENV MPLCONFIGDIR /tmp/cache
ENV XDG_CACHE_HOME /tmp/cache

# https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
LABEL org.opencontainers.image.authors='Roberto Rossini <roberros@uio.no>'
LABEL org.opencontainers.image.url='https://github.com/robomics/alphafold-playground'
LABEL org.opencontainers.image.documentation='https://github.com/robomics/alphafold-playground'
LABEL org.opencontainers.image.source='https://github.com/robomics/alphafold-playground'
LABEL org.opencontainers.image.licenses='MIT'
LABEL org.opencontainers.image.title='colabfold'
LABEL org.opencontainers.image.description='Dockerized version of github.com/sokrypton/ColabFold'
