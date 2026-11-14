# Canopy GH-1: OS Image Build & Packaging Guide

This document describes how to build the reproducible, bootable Raspberry Pi OS image for the **Canopy GH-1** commercial greenhouse controller.

---

## 1. Prerequisites

The build script `os/build-image.sh` generates a partitioned, loopback-mounted disk image based on **Raspberry Pi OS Lite (64-bit)** with the custom Canopy hardware device tree overlay, systemd services, and dependencies pre-installed.

### Host Dependencies (Linux / Ubuntu / Debian)
```bash
sudo apt-get update && sudo apt-get install -y \
  curl xz-utils parted e2fsprogs dosfstools \
  device-tree-compiler rsync qemu-user-static binfmt-support
```

---

## 2. Containerized Reproducible Build

To build the image on any host (including Windows / macOS via Docker Desktop) without polluting the host environment, execute `build-image.sh` inside a privileged container with loop device access:

```bash
docker run --rm --privileged \
  -v "/dev:/dev" \
  -v "$(pwd):/repo" \
  -e BASE_IMAGE_URL="https://downloads.raspberrypi.com/raspios_lite_arm64_latest" \
  -e VOICE=0 \
  ubuntu:24.04 bash -c "
    apt-get update && apt-get install -y --no-install-recommends \
      curl xz-utils parted e2fsprogs dosfstools device-tree-compiler \
      rsync qemu-user-static binfmt-support ca-certificates udev
    /repo/os/build-image.sh
  "
```

*Note: Set `VOICE=1` if you want local neural speech synthesis (Piper) and offline speech recognition (faster-whisper) pre-baked into the image (adds ~1.5 GB).*

---

## 3. Device Tree Compilation

The custom carrier overlay `os/overlays/canopy-gh1-overlay.dts` maps:
- **I2C0 / I2C1:** DS3231 RTC (`0x68`), ADS1115 ADC (`0x48`), STUSB4500 USB PD (`0x28`).
- **SPI0:** SX1262 LoRa transceiver (`spidev0.0`).
- **UART3:** MAX13487 RS-485 transceiver (`/dev/ttyAMA3`).
- **1-Wire:** W1-GPIO on BCM pin 27 for DS18B20 digital soil probes.
- **GPIO / Relays:** ULN2803A relay sink channels and digital inputs.

To compile manually with `dtc`:
```bash
dtc -@ -I dts -O dtb -o os/overlays/canopy-gh1.dtbo os/overlays/canopy-gh1-overlay.dts
```

---

## 4. First-Boot & Provisioning Workflow

1. **Bootloader Configuration:** `config.txt.append` enables 64-bit kernel, hardware watchdog (`dtparam=watchdog=on`), USB 2.0 host controller (`dwc2,dr_mode=host`), and loads `canopy-gh1.dtbo`.
2. **First-Boot Service (`canopy-firstboot.service`):**
   - Automatically detects CPU serial number from `/proc/device-tree/serial-number`.
   - Sets unique hostname: `canopy-[serial]`.
   - Generates a cryptographic dashboard token and stores it in `/etc/canopy/canopy.env` (`chmod 640`).
   - Displays connection URL and token in `/etc/issue.d/canopy.issue`.
3. **Daemon Service (`canopy.service`):**
   - Runs `python -m canopy -c /etc/canopy/config.yaml`.
   - Sandboxed systemd unit with strict filesystem protection (`ProtectSystem=strict`, `ProtectHome=yes`, `NoNewPrivileges=yes`).
   - Integrated hardware watchdog: notifies systemd every control loop cycle (`sd_notify("WATCHDOG=1")`). If the control loop hangs for >60s, systemd restarts the daemon. If the kernel panics, the SoC hardware watchdog resets the CM4, forcing all ULN2803A relay sinks to de-energize safely.

---

## 5. Flashing to SD Card / eMMC

1. Open **Raspberry Pi Imager**.
2. Select **Use Custom Image** and choose `canopy-gh1-*.img.xz`.
3. In the customisation dialog:
   - Configure local Wi-Fi SSID and passphrase (optional if using GbE Ethernet).
   - Set admin username and public SSH key.
4. Flash the target SD card or CM4 eMMC storage.
5. Insert into the Canopy GH-1 carrier board and apply 12–24V DC or USB-C PD power.
