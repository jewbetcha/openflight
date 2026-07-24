# openEMS (FDTD electromagnetics) + Python interface, built from source.
#
# There is no conda-forge package for the FDTD "openEMS" (thliebig) and no
# working public GHCR/DockerHub image with the Python interface, so we build
# from source. This image is the environment that all Rev C antenna sims
# (tasks 4-8) run inside. On Apple Silicon + OrbStack this builds and runs
# natively as linux/arm64.
#
# Build (one time, from the repo root):
#   docker build -t openems-local hardware/24ghz-adf590x-fmcw-rev-c/antenna/docker
# Run a sim (repo mounted at /work):
#   docker run --rm -v "$PWD":/work -w /work openems-local \
#       python3 hardware/24ghz-adf590x-fmcw-rev-c/antenna/sim_canary.py
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# python3-venv is required: update_openEMS.sh --python installs the Python
# bindings into a venv at <install_path>/venv.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates build-essential cmake \
        libhdf5-dev libvtk9-dev libboost-all-dev libcgal-dev \
        libtinyxml-dev qtbase5-dev libvtk9-qt-dev \
        python3 python3-dev python3-pip python3-venv python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

# Pinned 2026-07-01: this is the exact commit that was HEAD of thliebig/
# openEMS-Project when this image was first built and verified against
# sim_canary.py. Pinning avoids silent upstream breakage/behavior drift on
# rebuild (there are no release tags to pin to instead). Re-derive and update
# this SHA deliberately (rebuild + re-run sim_canary.py) if openEMS needs to
# be upgraded.
ENV OPENEMS_COMMIT=5e007ea4980518c705e11c783d1844701ecf09bb

# Full clone (not --depth 1) is required so the pinned SHA above is fetchable
# and checkout succeeds.
RUN git clone --recursive \
        https://github.com/thliebig/openEMS-Project.git /opt/openEMS-Project \
    && cd /opt/openEMS-Project \
    && git checkout ${OPENEMS_COMMIT} \
    && git submodule update --init --recursive

# Build the C++ engine + CSXCAD and the Python bindings (into /opt/openEMS
# and the venv at /opt/openEMS/venv).
RUN cd /opt/openEMS-Project && ./update_openEMS.sh /opt/openEMS --python

ENV LD_LIBRARY_PATH=/opt/openEMS/lib
# Put the openEMS venv python (and the FDTD/nf2ff binaries) first on PATH.
ENV PATH=/opt/openEMS/venv/bin:/opt/openEMS/bin:${PATH}

# Fail the image build early if the bindings don't import.
RUN python3 -c "import openEMS, CSXCAD; print('openEMS OK')"

# h5py + matplotlib for NF2FF far-field post-processing (upcoming antenna
# sims). Installed into the same venv the openEMS python bindings live in.
RUN /opt/openEMS/venv/bin/pip install --no-cache-dir h5py matplotlib

WORKDIR /work
CMD ["python3"]
