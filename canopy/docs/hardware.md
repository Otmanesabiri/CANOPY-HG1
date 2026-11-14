# Canopy GH-1 hardware

## 1. Processor decision (read this first)

The brief asks for a single board built around a publicly available SoC. The board delivered here is a **custom
carrier for the Raspberry Pi Compute Module 4** (Broadcom BCM2711, 4x Cortex-A72 @ 1.5 GHz, 2-8 GB LPDDR4,
optional eMMC, 2.4/5 GHz Wi-Fi + Bluetooth 5.0, Gigabit PHY on the module). That is a deliberate deviation:
the SoC, DDR, PMIC and radio sit on a plug-in module rather than being soldered to this PCB.

Why: a chip-down design needs DDR4/LPDDR4 length-matched routing, PMIC sequencing, 0.5 mm-pitch BGA fan-out,
RF layout and intentional-radiator certification. None of that can be validated without signal-integrity
simulation, a lab and several board spins, so a chip-down layout produced in one pass could not honestly be
called production-ready. The module moves all of it into a part that is already validated, FCC/IC/CE certified
as a radio module, in guaranteed production until at least 2034, and stocked by US distributors (DigiKey,
Newark, Micro Center, PiShop.us, Adafruit, SparkFun).

Chip-down route evaluated and rejected for Rev A, kept as the cost-down path for volume:

| Option | Verdict |
|---|---|
| TI AM6254 (4x A53) via Octavo OSD62x-PM SiP (AM62x + DDR4 in 9x14 mm BGA, DigiKey/Mouser) | Best chip-down fit. 0.5 mm ball pitch needs HDI stack-up plus external PMIC (TPS65219), Wi-Fi module and RF certification. |
| ST STM32MP157 via Octavo OSD32MP15x SiP (1 mm pitch, PMIC inside) | Easy to route, but 2x A7 / <=1 GB is marginal for local speech-to-text. |
| NXP i.MX 8M Plus / bare AM62x / Rockchip chip-down | Full DDR + PMIC design; no advantage over the SiP at this volume. |

Compute need: the LLM runs in Anthropic's cloud, so the local load is sensor polling, SQLite, the web server and
(optionally) wake-word + Whisper speech-to-text + Piper text-to-speech. A quad A72 with 2 GB handles that; 4 GB is
recommended if voice and Zigbee2MQTT are both enabled.

## 2. Block diagram

```
 USB-C (PD) --> STUSB4500 PD sink --> P-FET switch --> VIN 5-20 V --> LMR33640 buck --> +5V (4 A)
     |  D+/D-                                                            |--> CM4, USB ports, amplifier
     v                                                                   '--> AP62250 buck --> +3V3 (2.5 A, enabled by CM4 3V3)
 FSUSB42 mux <-- nRPIBOOT jumper (USB-C data = eMMC flashing; otherwise hub)
     |
 CM4 USB2 ---> USB2514B hub ---> 2x USB-A (TPS2065C switches, ESD)   +  1x internal USB-A (Zigbee coordinator)
 CM4 GbE MDI -------------------> RJ45 with magnetics (Pulse JK0654219NL)
 CM4 SD ------------------------> microSD (CM4 Lite) with TPS22917 power switch      [eMMC variants: on-module]
 CM4 I2S ------------------------> 2x ICS-43434 MEMS microphones, MAX98357A 3 W amplifier -> speaker connector
 CM4 SPI0 -----------------------> RFM95W LoRa (SX1276, 915/868 MHz) -> U.FL
 CM4 I2C1 -----------------------> MCP23017 -> ULN2803A -> 8 sink outputs (relays/contactors/valves)
                                 > ADS1115 (2x 0-3.3 V, 2x 0-10 V), DS3231M RTC, STUSB4500, 2x Qwiic ports
 CM4 UART3 ----------------------> THVD1420 RS-485 (Modbus RTU sensors)
 CM4 GPIO -----------------------> 2x pulse inputs (flow meters), 1-Wire (DS18B20), 4x dry-contact inputs (via MCP23017)
```

## 3. GPIO map (BCM numbering)

| GPIO | Net | Function |
|---|---|---|
| 2 / 3 | I2C_SDA / I2C_SCL | I2C-1: MCP23017 0x20, STUSB4500 0x28, ADS1115 0x48, DS3231M 0x68, Qwiic sensors (SCD41 0x62, BH1750 0x23, SHT4x 0x44) |
| 4 / 5 / 6 | RS485_TX / RX / DE | UART3 + driver enable |
| 7 | AMP_SD | MAX98357A shutdown (pulled low = muted) |
| 8 / 9 / 10 / 11 | LORA_NSS / MISO / MOSI / SCK | SPI0 to RFM95W |
| 12 / 13 / 16 | expansion header | hardware PWM0/PWM1 (e.g. 0-10 V dimming daughterboard), spare |
| 14 / 15 | UART_TX / RX | debug console header |
| 17 / 26 | FLOW1 / FLOW2 | flow-meter pulse inputs (5 V tolerant front end) |
| 18 / 19 / 20 / 21 | I2S BCLK / LRCLK / DIN / DOUT | audio |
| 22 / 24 / 25 | LORA_RST / DIO1 / DIO0 | LoRa control |
| 23 | IOX_INT | MCP23017 interrupt (button, dry contacts) |
| 27 | ONEWIRE | DS18B20 bus, 4.7k pull-up |

MCP23017: GPA0-7 -> OUT1-8; GPB0 user/talk button; GPB1-3 red/green/blue status LED; GPB4-7 DI1-4.
Default output assignment in software: OUT1 irrigation valve, OUT3 ventilation fan, OUT5 heater, OUT6 grow lights
(OUT2/4/7/8 spare for a second zone).

## 4. Field wiring

* **OUT1-8** are open-collector sinks (ULN2803A, 50 V, clamp diodes to V_FIELD). Wire each relay/contactor coil between
  V_FIELD (5-24 V DC from your field supply, landed on J11) and OUTn. Budget <= 250 mA per channel with 3.3 V drive.
  They cannot switch mains or 24 VAC valves directly - use relays/contactors or SSRs rated for the load, in a
  separate enclosure if they carry mains.
* **AIN0/1** 0-3.3 V (capacitive soil probes), **AIN2/3** 0-10 V (industrial transmitters; 20k/10k divider).
* **FLOW1/2**: 5 V hall flow meters (open-collector or push-pull), sensor supply fused at 0.5 A.
* **RS-485**: A/B/GND, 120 ohm termination by jumper JP2, SM712 protection.
* **DI1-4**: dry contacts to GND (float switch, door, frost stat).

## 5. Power budget (5 V rail, 4 A regulator)

| Load | Typical | Peak |
|---|---|---|
| CM4 (Wi-Fi active, 4 cores busy) | 0.9 A | 1.8 A |
| 2x USB-A + internal USB | 0.3 A | 1.75 A (current-limited) |
| 3V3 rail (hub, LoRa TX, sensors) referred to 5 V | 0.15 A | 0.45 A |
| Audio amplifier (4 ohm) | 0.05 A | 0.8 A |
| **Total** | **1.4 A** | **4.8 A (not simultaneous; design limit 4 A)** |

A stock STUSB4500 asks for the highest of 5 V/1.5 A, 15 V/1.5 A, 20 V/1 A that the charger offers, so use a
>= 20 W PD charger with a 15 V or 20 V profile. On a 5 V-only source the board runs but is limited to ~7.5 W.
The NVM can be reprogrammed over I2C (address 0x28) to request e.g. 9 V/3 A.

## 6. Fail-safe behaviour designed into the hardware

* MCP23017 /RESET is driven by the CM4's nEXTRST with a pull-down: whenever the module is in reset, absent, or reset by
  the SoC watchdog, every output is released. ULN2803A inputs float low = relays off.
* The 3V3 peripheral rail is enabled by the CM4's own 3V3, so nothing back-powers the module's I/O.
* The amplifier is muted until the sound driver takes GPIO7 high.

## 7. PCB

150 x 100 mm, 4 layers (F.Cu signal / In1 GND / In2 +3V3 with a +5V region / B.Cu signal + GND pour), 1.6 mm,
0.2 mm tracks, 0.15 mm clearance, 0.6/0.3 mm vias - standard-capability fab. Parts on top except the two bottom-port
microphones. Four M3 mounting holes on a 143 x 93 mm rectangle. See `STATUS.md` for the layout's verification state.

## 8. Files

`hw/design.py` is the source of truth (parts, MPNs, pin-to-net map). `build_sch.py` generates the KiCad 7
hierarchical schematic from it and checks that KiCad's own netlist export matches the database pin for pin;
`build_pcb.py` places the board; `route_prep.py`/`post_route.py` autoroute, pour, run DRC and export `hw/fab/`.
