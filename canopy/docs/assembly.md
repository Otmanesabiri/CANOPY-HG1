# Enclosure and assembly

`enclosure/canopy_enclosure.scad` is parametric; `canopy_base` and `canopy_lid` are provided as STL and 3MF.

* Material: ASA or PETG (PLA softens in a greenhouse). 0.2 mm layers, 4 perimeters, 30 % infill, no supports.
  Base prints floor-down (215 x 155 x 37 mm including ears), lid prints outer-face-down (189 x 161 x 28 mm).
* Sealing: 2 mm EPDM cord in the base groove, compressed by the lid tongue; lid skirt sheds drips. All cables leave
  through the bottom face: 2x M20 glands (USB-C power, Ethernet - use split-seal inserts for pre-terminated cables),
  4x M16 glands (field wiring), 1x M12 breathable vent plug (pressure equalisation, limits condensation).
* Hardware: 8x M3 x 5.7 heat-set inserts (4 lid bosses, 4 PCB posts), 4x M3x10 countersunk (lid), 4x M3x6 (PCB),
  40 mm 4 ohm 3 W Mylar-cone speaker glued into the lid ring, 2x 9 mm adhesive ePTFE acoustic vents over the
  microphone ports, 1 mm foam rings between the lid chimneys and the PCB.
* Mount on a wall or post with the glands pointing down, out of direct irrigation spray and direct sun.
* Target is splash/dust protection (IP54-class by design intent). It has **not** been ingress-tested, and FDM parts
  need sealing (e.g. a coat of acrylic/epoxy on the outside) to be reliably water-tight.

The internal USB-A port is vertical; a Zigbee stick taller than ~20 mm needs a short USB extension and sits in the
wiring bay. A CM4 heatsink up to 10 mm tall fits under the lid.
