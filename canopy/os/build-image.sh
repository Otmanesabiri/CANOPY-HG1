#!/usr/bin/env bash
# Build the Canopy GH-1 OS image: Raspberry Pi OS Lite (64-bit) + board overlay + Canopy services.
# Run as root on a Debian/Ubuntu host (x86-64 or arm64):   sudo ./build-image.sh
# Needs: curl xz-utils parted e2fsprogs dosfstools device-tree-compiler rsync, and on x86 qemu-user-static + binfmt-support.
# NOT YET RUN END-TO-END by the author of this script - see docs/STATUS.md.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(dirname "$HERE")
BASE_URL=${BASE_IMAGE_URL:-https://downloads.raspberrypi.com/raspios_lite_arm64_latest}
BASE_SHA256=${BASE_IMAGE_SHA256:-}          # set this for reproducible / verified builds
VOICE=${VOICE:-0}                            # VOICE=1 also installs faster-whisper, openWakeWord and Piper (~1.5 GB)
OUT=${OUT:-$HERE/out}; WORK=$OUT/work; IMG=$OUT/canopy-gh1-$(cat "$REPO/VERSION" 2>/dev/null || echo dev).img
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
for t in curl xz parted losetup resize2fs e2fsck dtc rsync chroot; do command -v $t >/dev/null || { echo "missing tool: $t" >&2; exit 1; }; done
mkdir -p "$WORK/mnt"
cleanup() { set +e; for m in dev/pts dev proc sys boot/firmware ""; do mountpoint -q "$WORK/mnt/$m" && umount "$WORK/mnt/$m"; done; [ -n "${LOOP:-}" ] && losetup -d "$LOOP"; }
trap cleanup EXIT

echo "== fetch base image"
[ -f "$OUT/base.img.xz" ] || curl -fL --retry 3 -o "$OUT/base.img.xz" "$BASE_URL"
if [ -n "$BASE_SHA256" ]; then echo "$BASE_SHA256  $OUT/base.img.xz" | sha256sum -c -; else echo "WARNING: BASE_IMAGE_SHA256 not set - base image is not verified" >&2; fi
xz -dc "$OUT/base.img.xz" > "$IMG"

echo "== grow root partition by 2 GiB"
truncate -s +2G "$IMG"; parted -s "$IMG" resizepart 2 100%
LOOP=$(losetup --show -fP "$IMG"); e2fsck -fy "${LOOP}p2" || true; resize2fs "${LOOP}p2"
mount "${LOOP}p2" "$WORK/mnt"; mount "${LOOP}p1" "$WORK/mnt/boot/firmware"

echo "== board support"
dtc -@ -I dts -O dtb -o "$WORK/mnt/boot/firmware/overlays/canopy-gh1.dtbo" "$HERE/overlays/canopy-gh1-overlay.dts"
grep -q "Canopy GH-1" "$WORK/mnt/boot/firmware/config.txt" || cat "$HERE/config.txt.append" >> "$WORK/mnt/boot/firmware/config.txt"
rsync -a "$HERE/rootfs/" "$WORK/mnt/"
mkdir -p "$WORK/mnt/opt/canopy/src"; rsync -a --delete --exclude tests --exclude '__pycache__' "$REPO/software/" "$WORK/mnt/opt/canopy/src/"
mkdir -p "$WORK/mnt/etc/systemd/system.conf.d" "$WORK/mnt/etc/systemd/journald.conf.d"
printf '[Manager]\nRuntimeWatchdogSec=15\nRebootWatchdogSec=2min\n' > "$WORK/mnt/etc/systemd/system.conf.d/10-watchdog.conf"   # SoC watchdog: a hung kernel resets, nEXTRST drops all relays
printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=32M\n' > "$WORK/mnt/etc/systemd/journald.conf.d/10-canopy.conf"            # spare the SD card
touch "$WORK/mnt/boot/firmware/ssh"

echo "== install inside the image"
for m in proc sys dev dev/pts; do mount --bind /$m "$WORK/mnt/$m"; done
if [ "$(uname -m)" != aarch64 ]; then
  [ -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ] || { echo "install qemu-user-static and binfmt-support" >&2; exit 1; }
fi
cp /etc/resolv.conf "$WORK/mnt/etc/resolv.conf.build"; mv "$WORK/mnt/etc/resolv.conf" "$WORK/mnt/etc/resolv.conf.orig" 2>/dev/null || true; cp /etc/resolv.conf "$WORK/mnt/etc/resolv.conf"
chroot "$WORK/mnt" /bin/bash -euxo pipefail <<CHROOT
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends python3-venv python3-dev build-essential i2c-tools libgpiod-dev alsa-utils mosquitto mosquitto-clients avahi-daemon
id canopy >/dev/null 2>&1 || useradd --system --home /var/lib/canopy --shell /usr/sbin/nologin canopy
for g in i2c spi gpio audio dialout; do getent group \$g >/dev/null && usermod -aG \$g canopy; done
python3 -m venv /opt/canopy/venv
/opt/canopy/venv/bin/pip install --no-cache-dir "/opt/canopy/src[board]"
if [ "$VOICE" = 1 ]; then /opt/canopy/venv/bin/pip install --no-cache-dir "/opt/canopy/src[voice]" piper-tts; fi
chown -R root:canopy /etc/canopy; chmod 750 /etc/canopy
systemctl enable canopy-firstboot.service canopy.service avahi-daemon.service
systemctl disable mosquitto.service || true      # enabled by the user together with Zigbee2MQTT
apt-get clean; rm -rf /var/lib/apt/lists/*
CHROOT
rm -f "$WORK/mnt/etc/resolv.conf" "$WORK/mnt/etc/resolv.conf.build"; mv "$WORK/mnt/etc/resolv.conf.orig" "$WORK/mnt/etc/resolv.conf" 2>/dev/null || true
cleanup; trap - EXIT; LOOP=
xz -T0 -6 -f "$IMG"; sha256sum "$IMG.xz" | tee "$IMG.xz.sha256"
echo "== done: $IMG.xz   (flash with Raspberry Pi Imager; set Wi-Fi, user and SSH key in its customisation dialog)"
