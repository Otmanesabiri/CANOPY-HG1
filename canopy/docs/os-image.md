# OS image

The image is Raspberry Pi OS Lite (64-bit) with the board overlay, boot configuration, the Canopy service in a
virtualenv, a first-boot provisioning unit and the hardware watchdog enabled.

```
sudo apt install curl xz-utils parted dosfstools e2fsprogs device-tree-compiler rsync qemu-user-static binfmt-support
sudo BASE_IMAGE_SHA256=<sha256 from raspberrypi.com> ./os/build-image.sh        # VOICE=1 adds speech packages
# -> os/out/canopy-gh1-0.1.0.img.xz
```

Flash with Raspberry Pi Imager ("Use custom"), setting Wi-Fi, a user and an SSH key in its customisation dialog.
For eMMC modules fit the **USB BOOT** jumper, connect the USB-C port to a PC, run `rpiboot`, flash, remove the jumper.

First boot sets the hostname to `canopy-<serial>`, generates the dashboard token (shown on the console and stored
in `/etc/canopy/canopy.env`) and starts the service on port 8080. Add your `ANTHROPIC_API_KEY` to that file and
`sudo systemctl restart canopy`.

What the image configures (`os/config.txt.append`, `os/overlays/canopy-gh1-overlay.dts`):

| Function | Mechanism |
|---|---|
| I2C-1, SPI0 (one chip-select), UART3 | stock `dtparam` / `dtoverlay=spi0-1cs` / `uart3` |
| RTC | `dtoverlay=i2c-rtc,ds3231` |
| 1-Wire on GPIO27 | `dtoverlay=w1-gpio,gpiopin=27` |
| Sound card (MAX98357A + ICS-43434) | custom overlay binding the in-tree Google voiceHAT driver with SD_MODE on GPIO7 |
| RS-485 direction on GPIO6 | custom overlay fragment on `uart3` (`rts-gpios`, `linux,rs485-enabled-at-boot-time`) |
| Watchdog | `dtparam=watchdog=on` + systemd `RuntimeWatchdogSec=15`; service `WatchdogSec=60` |
| Relays, ADC, IO expander | driven from user space over I2C (no kernel driver bound) |

Zigbee: plug a coordinator stick into the internal USB port, install Zigbee2MQTT per its documentation, enable
`mosquitto`, and set `mqtt.enabled: true`.
