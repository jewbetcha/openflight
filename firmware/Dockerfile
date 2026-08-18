# x86_64 build environment for the IWR6843 firmware.
#
# TI ships the mmWave SDK and the ARM codegen tools as Linux x86_64 installers
# only, and the installer stubs need 32-bit (i386) support. That rules out
# building on an Apple Silicon Mac or on the Raspberry Pi directly. This image
# supplies that environment so `make -C firmware docker-build` works from macOS
# with nothing installed on the host but Docker.
#
# Verified on Docker 29.4 / Apple Silicon: the emulated guest reports x86_64
# with a 4096-byte page size, and i386 binaries execute -- the two things the
# TI installers need and the reasons the Pi 5 (aarch64, 16 KiB pages) cannot do
# this.
#
# The apt dependency list and the TI installer invocations are NOT duplicated
# here: this calls the same `install-ti-deps-native` and
# `install-ti-tools-native` targets the documented bare-metal path uses, so
# there is one definition of each and they cannot drift.
#
# Build context is the `firmware/` directory. Requires BuildKit (default on
# Docker 23+) for the `RUN --mount` bind mounts, which keep the multi-gigabyte
# installers out of the image layers.
#
# Two stages, so the half that needs no license-gated files can be verified on
# its own:
#   docker build --platform linux/amd64 --target base -t openflight-iwr-sdk-base .

# The platform comes from `docker build --platform linux/amd64` (the
# docker-image target always passes it) rather than being pinned here, which
# keeps the image buildable for a genuine x86_64 host without emulation. The
# guard below turns a forgotten flag into a clear error instead of a confusing
# compiler failure hundreds of layers later.
FROM debian:bookworm AS base

RUN test "$(uname -m)" = "x86_64" || { \
        echo "ERROR: this image must be built for x86_64."; \
        echo "       got $(uname -m); rebuild with --platform linux/amd64"; \
        exit 1; \
    }

# `sudo` is what lets the install targets run unmodified; as root it is a
# passthrough. `make` bootstraps the targets themselves.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates make sudo \
    && rm -rf /var/lib/apt/lists/*

# Debian packages the TI tools need, including i386 multiarch.
#
# Only the Makefile is mounted, not the whole context. With `source=.` any edit
# under firmware/ -- including a comment in this Dockerfile -- changes the mount
# content and invalidates this layer and the multi-gigabyte TI install below.
# Verified: touching the Dockerfile lost the cache on this step.
RUN --mount=type=bind,source=Makefile,target=/ctx/Makefile,ro \
    make -C /ctx install-ti-deps-native \
    && rm -rf /var/lib/apt/lists/*

# Verify the three properties the TI installers depend on, so a bad build
# environment fails here rather than as an inscrutable compiler or installer
# error. The Pi 5 fails the page-size check (16 KiB) and Docker's Rosetta
# backend fails the i386 check.
RUN set -eu; \
    test "$(getconf PAGE_SIZE)" = "4096" || { \
        echo "ERROR: page size is $(getconf PAGE_SIZE), TI installers need 4096"; \
        exit 1; \
    }; \
    /lib/ld-linux.so.2 --help >/dev/null 2>&1 || { \
        echo "ERROR: cannot execute 32-bit i386 binaries."; \
        echo "       TI's installer stubs are 32-bit. If Docker Desktop is set"; \
        echo "       to 'Use Rosetta for x86_64/amd64 emulation', turn it off"; \
        echo "       so QEMU handles i386."; \
        exit 1; \
    }; \
    echo "build environment verified: $(uname -m), $(getconf PAGE_SIZE)-byte pages, i386 OK"

FROM base AS tools

# Install the TI SDK and toolchain under /opt/ti. The installers are
# license-gated and gitignored, so they must be present in the build context at
# firmware/ti_installers/. They are copied to a writable scratch directory
# (the install target chmod +x's them, which a read-only mount forbids) and
# deleted inside the same layer, so only /opt/ti persists.
RUN --mount=type=bind,source=Makefile,target=/ctx/Makefile,ro \
    --mount=type=bind,source=ti_installers,target=/ctx/ti_installers,ro \
    set -eux; \
    mkdir -p /tmp/ti-installers; \
    cp /ctx/ti_installers/* /tmp/ti-installers/; \
    make -C /ctx install-ti-tools-native INSTALLER_DIR=/tmp/ti-installers; \
    rm -rf /tmp/ti-installers

# TI's generateMetaImage.sh converts the linked .xer4f into RPRC format with
# out2rprc.exe under mono. Mono's amd64 JIT cannot emit that code under QEMU
# emulation: the guest maps mono's own code near 0x555555000000 and libc near
# 0x7fffff000000, ~46 TB apart, so a 32-bit relative displacement overflows and
# the JIT aborts ("condition `offset == (gint32)offset' not met", or
# "should not be reached at tramp-amd64.c:606"). The compile itself is fine --
# only this final packaging step fails.
#
# Mono's interpreter emits no native code, so the problem disappears.
# MONO_ENV_OPTIONS is applied by mono at startup, which means TI's scripts run
# unmodified -- no patching of the SDK. out2rprc is a small one-shot ELF
# conversion, so interpreting it costs nothing measurable.
#
# Set AFTER the toolchain install so it cannot affect the installers, which run
# mono themselves.
ENV MONO_ENV_OPTIONS=--interpreter

# The repository is bind-mounted here at run time so build output lands on the
# host in firmware/releases/.
WORKDIR /work

CMD ["make", "-C", "firmware", "build-native"]
