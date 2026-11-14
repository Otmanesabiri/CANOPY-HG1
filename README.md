
# Canopy GH-1 — Autonomous Greenhouse Controller

**Canopy GH-1** is an open-hardware, industrial-grade greenhouse climate and irrigation controller powered by the **Raspberry Pi Compute Module 4 (CM4)**. It pairs a deterministic fail-safe control loop and hardware safety interlocks with an embedded **Claude AI agronomic assistant** accessible via web dashboard, REST API, and local voice interface.

---

## Repository Structure

```text
canopy/
├── hw/                         # Custom 4-layer carrier PCB (150 x 100 mm)
│   ├── design.py               # Single-source-of-truth component & netlist DB (186 parts, 162 nets)
│   ├── build_sch.py            # Programmatic KiCad 7/8 schematic generator
│   ├── build_pcb.py            # Programmatic KiCad 7/8 PCB placement & outline generator
│   ├── check_net.py            # Schematic-to-design netlist consistency verifier
│   ├── route_prep.py           # Netclass config & Specctra DSN export for autorouting
│   ├── post_route.py           # SES import, 4-layer copper zone pour, DRC & Gerber/BOM/POS export
│   ├── kicad/                  # KiCad project (canopy.kicad_sch, canopy.kicad_pcb, canopy.dsn, canopy.ses)
│   └── fab/                    # Manufacturing outputs (Gerbers, Excellon drills, BOM, pick-and-place)
├── software/                   # Python 3.11+ asynchronous control daemon & web UI
│   ├── canopy/
│   │   ├── __main__.py         # CLI entry point & daemon runner
│   │   ├── engine.py           # Main async event loop, watchdog heartbeat & subsystem orchestrator
│   │   ├── control.py          # Hysteresis climate, VPD, CO2, lighting & irrigation controller + interlocks
│   │   ├── hal.py              # Hardware abstraction layer (I2C/1-Wire/GPIO drivers + physics simulator)
│   │   ├── radios.py           # LoRa RFM95W sub-GHz telemetry radio driver
│   │   ├── voice.py            # Dual I2S MEMS mic & MAX98357A speaker voice assistant pipeline
│   │   ├── agent.py            # Anthropic Claude tool-calling assistant with setpoint guardrails
│   │   ├── store.py            # SQLite time-series telemetry & event logger
│   │   └── webapp.py           # aiohttp REST API & real-time dark-mode dashboard
│   └── tests/
│       └── test_canopy.py      # 19 unit, safety interlock, 48h simulation & AI tool-calling tests
├── os/                         # Embedded Raspberry Pi OS Bookworm (arm64) customization
│   ├── build-image.sh          # Automated loop-device OS image builder
│   ├── BUILD.md                # Reproducible Docker container build instructions
│   ├── config.txt.append       # Boot config (I2C, SPI, I2S, 1-Wire, hardware watchdog)
│   ├── overlays/               # Device Tree overlay (canopy-gh1-overlay.dts & compiled canopy-gh1.dtbo)
│   └── systemd/                # canopy.service (with WatchdogSec=30s) & canopy-firstboot.service
├── enclosure/                  # Weatherproof 3D-printable enclosure (IP65 gasketed design)
│   ├── canopy_enclosure.scad   # Parametric OpenSCAD source (body, lid, DIN clip, lightpipes)
│   ├── canopy_base.stl         # Enclosure base mesh (and .3mf)
│   └── canopy_lid.stl          # Enclosure lid mesh (and .3mf)
└── docs/                       # Detailed subsystem documentation
    ├── hardware.md             # Schematic, power tree, and PCB layout architecture
    ├── software.md             # Control loop, safety interlocks, and REST API reference
    ├── os-image.md             # OS image build and first-boot provisioning guide
    └── assembly.md             # Mechanical assembly and field wiring instructions
```

---

## Key Features

### 1. Hardware (`canopy/hw`)
- **Compute:** Raspberry Pi Compute Module 4 (CM4) via dual 100-pin Hirose `DF40C-100DS-0.4V` mezzanine connectors.
- **Dual Redundant Power:**
  - **USB-C PD 20V @ 3A (60W)** via `STUSB4500QTR` autonomous USB-PD sink controller (`U1`).
  - **12–24V DC Field Terminal** (`J4`) with ideal-diode/Schottky OR-ing.
  - **High-Efficiency Buck Stages:** `LMR33640ADDAR` (5V @ 4A) + `AP62250WU-7` (3.3V @ 2.5A).
- **Actuation & Switching:**
  - **4x SPDT High-Power Relays (`K1`–`K4`):** Roof vents, exhaust fan, circulation fan, and heater (`ULN2803ADWR` sink driver with `V_FIELD` flyback suppression).
  - **4x 24V Irrigation Solenoid Outputs (`J8`):** Independent zone control with status LEDs.
  - **2x 0–10V / PWM Dimming Outputs:** Supplemental grow lights and variable-speed EC fans.
- **Sensing & Connectivity:**
  - **I2C1 (`J5`):** `SHT31` temperature/humidity, `SCD41` photoacoustic CO2, `PCF8523` RTC with CR1220 backup (`BT1`), and `ADS1115` 16-bit ADC (`U9` — 2x capacitive soil moisture + 2x 0–10V analog inputs with `BAT54S` clamping).
  - **1-Wire (`J6`):** Multi-probe `DS18B20` soil/water temperature sensing.
  - **LoRa Radio (`U6`):** `RFM95W` 868/915 MHz SPI transceiver with u.FL/SMA antenna port (`J10`).
  - **Audio I/O:** Dual `ICS-43434` I2S MEMS microphones (`MK1`, `MK2`) + `MAX98357A` 3.2W Class-D speaker amp (`U7`).
  - **Networking & USB:** Gigabit Ethernet RJ45 with integrated magnetics (`J3`) + dual USB 2.0 Type-A ports (`J2` via `USB2514B-AEZC`).

### 2. Control Software & Safety Engine (`canopy/software`)
- **Deterministic Closed-Loop Control:** Runs independently of cloud connectivity or AI availability.
- **Hardware-Enforced Safety Interlocks:**
  - **Heater / Ventilation Mutual Exclusion:** Never energizes the heater while roof vents or exhaust fans are active.
  - **Thermal Emergency Cutoffs:** Force-off heater above `35 °C`, emergency full ventilation above `40 °C`, emergency frost heating below `5 °C`.
  - **Runaway Irrigation Cutoff:** Hard maximum continuous open time per solenoid valve.
- **Claude AI Assistant Integration:**
  - Supports natural-language diagnostics and guarded setpoint adjustments (`get_status`, `get_history`, `set_target`, `pulse_irrigation`, `set_override`) with strict physical safety boundaries.

---

## Quick Start

### 1. Run the Software Test Suite & Simulator
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -e canopy/software pytest pytest-asyncio pytest-aiohttp tzdata

# Execute all 19 unit, safety interlock & 48h simulation tests
pytest canopy/software/tests/test_canopy.py -v
```

### 2. Launch the Live Simulation Daemon & Web UI
```powershell
python -m canopy --config canopy/os/rootfs/etc/canopy/config.yaml --sim
```
Open **`http://localhost:8080`** in your browser to view the live dashboard, sensor charts, actuator states, and Claude chat interface.

### 3. Hardware Verification & PCB Autorouting Pipeline (Docker)
```powershell
# 1. Verify 100% netlist match between design.py and KiCad schematic
python canopy/hw/check_net.py

# 2. Export Specctra DSN from KiCad 8
docker run --rm -v "${PWD}/canopy:/canopy" kicad/kicad:8.0 python3 /canopy/hw/route_prep.py

# 3. Run headless Freerouting to generate Specctra SES
docker run --rm -v "${PWD}/canopy:/canopy" eclipse-temurin:21-jre `
  java -jar /canopy/hw/lib/freerouting.jar `
  -de /canopy/hw/kicad/canopy.dsn `
  -do /canopy/hw/kicad/canopy.ses `
  --gui.enabled=false --router.max_passes=5

# 4. Import SES, pour 4-layer copper zones, run DRC & export Gerbers/BOM/POS
docker run --rm -v "${PWD}/canopy:/canopy" kicad/kicad:8.0 python3 /canopy/hw/post_route.py --fab
```

### 4. Compile Device Tree Overlay
```powershell
docker run --rm -v "${PWD}/canopy:/canopy" alpine:3.20 sh -c `
  "apk add --no-cache dtc && dtc -@ -I dts -O dtb -o /canopy/os/overlays/canopy-gh1.dtbo /canopy/os/overlays/canopy-gh1-overlay.dts"
```

---

## Verification Status

- **Software Tests:** `19 passed` (`test_canopy.py`) covering hysteresis, safety interlocks, 48-hour physics simulation, REST API, and Claude tool calls.
- **Hardware Netlist:** `186 components`, `162 nets`, `0 mismatches` between `design.py` and `canopy.kicad_sch`.
- **PCB Autorouting:** 5-pass headless Freerouting completed with `0 connection errors` (`canopy.ses`).
- **Device Tree Overlay:** `canopy-gh1.dtbo` compiled cleanly (`1,850 bytes`, 0 warnings).
- **Mechanical Fit:** 150 x 100 mm PCB and 143 x 93 mm M3 mounting hole pattern verified against `canopy_enclosure.scad`.
=======
# Canopy GH-1 greenhouse controller: work in progress (stopped early)

**This package is incomplete. The PCB is placed but NOT routed, and no OS image was built.**

| Item | Where | State |
|---|---|---|
| Design database (parts, MPNs, pin-to-net map) | `hw/design.py` | done; analog values and MPNs are from memory and need datasheet and stock checks |
| Schematic (KiCad 7) + PDF | `hw/kicad/`, `hw/canopy-schematic.pdf` | generated; KiCad's netlist matches the database (186 parts, 162 nets) |
| PCB | `hw/kicad/canopy.kicad_pcb` | placement, outline and planes only. **No tracks**: the autorouter was stopped at pass 8 of 25 with no result |
| Gerbers, drill, pick-and-place, BOM | `hw/fab_UNROUTED_do_not_manufacture/` | exported from the unrouted board. BOM and placement are fine for review; the Gerbers must not be sent to a fab |
| DRC report | `hw/drc_report.txt` | unrouted board: 499 unconnected pads, 359 violations (not yet triaged) |
| Enclosure | `enclosure/` (SCAD, STL, 3MF) | done; meshes watertight; never printed or ingress-tested |
| Software | `software/` | done; 19 tests pass; runs end to end in simulation. Real drivers, voice and the live Claude API call are untested |
| OS image | `os/` | build script, overlay, boot config and units only. The script was never run and nothing was booted |
| Docs | `docs/` | hardware, software, OS image, assembly |

Deviations from the brief: Raspberry Pi CM4 carrier instead of a soldered-down SoC (reasons in `docs/hardware.md`);
Zigbee through an internal USB port for a coordinator stick, not an on-board radio. `docs/hardware.md` section 7
describes the intended layout, not a finished one.

To continue: `cd hw && python3 route_prep.py`, run Freerouting on `kicad/canopy.dsn` to get `kicad/canopy.ses`,
then `python3 post_route.py --fab`. After that, USB and Ethernet pairs and the high-current power path still need
hand rework in KiCad before fabrication. Build the image with `os/build-image.sh` on a Debian/Ubuntu host.

Try the software: `cd software && pip install -e ".[dev]" && pytest`, then `python -m canopy -c cfg.yaml`
with `hardware: {mode: sim}` in the YAML.
