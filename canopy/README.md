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
