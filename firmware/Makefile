INSTALLER_DIR ?= ti_installers
TI_ROOT ?= /opt/ti
MMWAVE_SDK_INSTALL_PATH ?= $(TI_ROOT)/sdk/mmwave_sdk_03_06_02_00-LTS/packages
R4F_CODEGEN_INSTALL_PATH ?= $(TI_ROOT)/cgt-arm/ti-cgt-arm_20.2.7.LTS
XDC_INSTALL_PATH ?= $(TI_ROOT)/xdc/xdctools_3_61_00_16_core
BIOS_INSTALL_PATH ?= $(TI_ROOT)/bios/bios_6_73_01_01/packages
SYSCONFIG_INSTALL_PATH ?= $(TI_ROOT)/sysconfig
XWR68XX_RADARSS_IMAGE_BIN ?= $(TI_ROOT)/sdk/mmwave_sdk_03_06_02_00-LTS/firmware/radarss/xwr6xxx_radarss_rprc.bin
FIRMWARE_DIR ?= iwr6843
RELEASE_DIR ?= releases
RELEASE_NAME ?= l3_dump_vTX2_hwa_window53_12loops_18frames_4ms_temperature_report_20260731.bin

SDK_INSTALLER := $(INSTALLER_DIR)/mmwave_sdk_03_06_02_00-LTS-Linux-x86-Install.bin
R4F_INSTALLER := $(INSTALLER_DIR)/ti_cgt_tms470_20.2.7.LTS_linux-x64_installer.bin
BIOS_INSTALLER := $(INSTALLER_DIR)/bios_6_73_01_01.run
SYSCONFIG_INSTALLER := $(INSTALLER_DIR)/sysconfig-1.10.0_2163-setup.run
XDC_ZIP := $(INSTALLER_DIR)/xdctools_3_61_00_16_core_linux.zip

BUILD_ENV := \
	MMWAVE_SDK_DEVICE=iwr68xx \
	DOWNLOAD_FROM_CCS=yes \
	MMWAVE_SDK_INSTALL_PATH=$(MMWAVE_SDK_INSTALL_PATH) \
	R4F_CODEGEN_INSTALL_PATH=$(R4F_CODEGEN_INSTALL_PATH) \
	XDC_INSTALL_PATH=$(XDC_INSTALL_PATH) \
	BIOS_INSTALL_PATH=$(BIOS_INSTALL_PATH) \
	XWR68XX_RADARSS_IMAGE_BIN=$(XWR68XX_RADARSS_IMAGE_BIN)

REQUIRED_INSTALLERS := \
	mmwave_sdk_03_06_02_00-LTS-Linux-x86-Install.bin \
	ti_cgt_tms470_20.2.7.LTS_linux-x64_installer.bin \
	bios_6_73_01_01.run \
	sysconfig-1.10.0_2163-setup.run \
	xdctools_3_61_00_16_core_linux.zip

.PHONY: help check-host check-installers install-ti-deps-native install-ti-tools-native probe-installers-native build-native clean

help:
	@echo "IWR6843 production firmware helpers"
	@echo ""
	@echo "Targets:"
	@echo "  check-host              Verify the native x86_64 Linux build host"
	@echo "  check-installers        Verify required TI installers are present"
	@echo "  install-ti-deps-native  Install Debian packages required by TI tools"
	@echo "  probe-installers-native Verify the downloaded installer executables"
	@echo "  install-ti-tools-native Install TI SDK/toolchain under TI_ROOT"
	@echo "  build-native            Build the supported production firmware"
	@echo "  clean                   Remove generated TI build outputs"

check-host:
	@set -eu; \
	echo "host_arch=$$(uname -m)"; \
	echo "page_size=$$(getconf PAGE_SIZE)"; \
	test "$$(uname -m)" = "x86_64"

check-installers:
	@set -eu; \
	missing=0; \
	for file in $(REQUIRED_INSTALLERS); do \
		if [ ! -f "$(INSTALLER_DIR)/$$file" ]; then \
			echo "missing: $(INSTALLER_DIR)/$$file"; \
			missing=1; \
		else \
			echo "found:   $(INSTALLER_DIR)/$$file"; \
		fi; \
	done; \
	exit $$missing

install-ti-deps-native:
	sudo dpkg --add-architecture i386
	sudo apt-get update
	sudo apt-get install -y build-essential make mono-runtime libc6:i386 libstdc++6:i386 zlib1g:i386 bison flex unzip rsync file

probe-installers-native: check-installers
	@set -u; \
	chmod +x "$(SDK_INSTALLER)" "$(R4F_INSTALLER)" "$(BIOS_INSTALLER)" "$(SYSCONFIG_INSTALLER)"; \
	for installer in "$(SDK_INSTALLER)" "$(R4F_INSTALLER)" "$(BIOS_INSTALLER)" "$(SYSCONFIG_INSTALLER)"; do \
		echo "=== $$installer --help ==="; \
		"$$installer" --help >/tmp/installer-help.txt 2>&1; \
		rc=$$?; \
		echo "exit=$$rc"; \
		sed -n '1,24p' /tmp/installer-help.txt; \
	done

install-ti-tools-native: check-installers
	sudo mkdir -p "$(TI_ROOT)/sdk" "$(TI_ROOT)/cgt-arm" "$(TI_ROOT)/bios" "$(TI_ROOT)/xdc" "$(SYSCONFIG_INSTALL_PATH)"
	chmod +x "$(SDK_INSTALLER)" "$(R4F_INSTALLER)" "$(BIOS_INSTALLER)" "$(SYSCONFIG_INSTALLER)"
	sudo "$(SDK_INSTALLER)" --mode unattended --prefix "$(TI_ROOT)/sdk" --disable-components TI_CGT_C6000,TI_CGT_ARM,DSPLIB_C64Px,DSPLIB_C674x,MATHLIB_C674x,XDCtools,SYS_BIOS
	sudo "$(R4F_INSTALLER)" --mode unattended --prefix "$(TI_ROOT)/cgt-arm"
	sudo "$(BIOS_INSTALLER)" --mode unattended --prefix "$(TI_ROOT)/bios"
	sudo "$(SYSCONFIG_INSTALLER)" --mode unattended --prefix "$(SYSCONFIG_INSTALL_PATH)"
	sudo unzip -q -o "$(XDC_ZIP)" -d "$(TI_ROOT)/xdc"
	test -d "$(MMWAVE_SDK_INSTALL_PATH)"
	test -x "$(R4F_CODEGEN_INSTALL_PATH)/bin/armcl"
	test -d "$(BIOS_INSTALL_PATH)"
	test -x "$(XDC_INSTALL_PATH)/xdc"
	test -f "$(XWR68XX_RADARSS_IMAGE_BIN)"

build-native:
	$(BUILD_ENV) $(MAKE) -C "$(FIRMWARE_DIR)" cleanApp
	$(BUILD_ENV) $(MAKE) -C "$(FIRMWARE_DIR)" bin L3_VARIANT_DEFS="--define=N_TX=3 --define=LOOPS=12 --define=RING_FRAMES=18 --define=HWA_POST_TRIGGER_FRAMES=12 --define=ENABLE_HWA_SMOKE=1 --define=SNAPSHOT_DUMP=1 --define=HWA_CHAINED_SNAPSHOT_RING=1 --define=SNAPSHOT_DYNAMIC_WINDOWS=1 --define=SNAPSHOT_BIN_START=20 --define=SNAPSHOT_MIDDLE_BIN_START=32 --define=SNAPSHOT_LATE_BIN_START=47 --define=SNAPSHOT_BINS=53"
	mkdir -p "$(RELEASE_DIR)"
	cp "$(FIRMWARE_DIR)/l3_dump.bin" "$(RELEASE_DIR)/$(RELEASE_NAME)"
	sha256sum "$(RELEASE_DIR)/$(RELEASE_NAME)"

clean:
	$(BUILD_ENV) $(MAKE) -C "$(FIRMWARE_DIR)" cleanApp
