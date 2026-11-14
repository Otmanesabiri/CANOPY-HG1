// Canopy GH-1 enclosure - wall-mount, gasketed, all cables enter through glands on the bottom face.
// Print: PETG or ASA (not PLA - greenhouse heat/UV), 0.2 mm layers, 4 perimeters, 30 % infill, no supports.
//        base: floor down.   lid: outer face down.
// part = "base" | "lid" | "assembly"
part = "assembly";
$fn = 48;

// ---- PCB (must match hw/build_pcb.py)
pcb = [150, 100, 1.6];
pcb_holes = [[3.5, 3.5], [146.5, 3.5], [3.5, 96.5], [146.5, 96.5]];   // board coords, y down from top edge
mic = [[96, 5], [130, 5]];                                            // microphone ports (board coords)
leds = [[121.5, 22]];                                                  // RGB status LEDs centre
// ---- cavity
wall = 3; floor_t = 3; lid_t = 3;
margin_l = 3; margin_top = 3; bay_right = 24; bay_bottom = 46;        // wiring bays: right (terminals) and bottom (plugs, glands)
standoff = 6;                                                          // PCB underside clearance (THT pins, bottom-side mics)
headroom = 26;                                                         // above PCB: stacked USB-A 15.7, RJ45 13.5, CM4 + heatsink
in_x = margin_l + pcb[0] + bay_right; in_y = bay_bottom + pcb[1] + margin_top;
in_z = standoff + pcb[2] + headroom;
out_x = in_x + 2*wall; out_y = in_y + 2*wall; base_h = floor_t + in_z;
r = 6;                                                                 // outer corner radius
boss = 9;                                                              // lid screw boss (M3 heat-set insert, 4.0 x 5.7 mm hole)
glands = [[27, 20.4], [52, 20.4], [77, 16.4], [98, 16.4], [119, 16.4], [140, 16.4], [160, 12.4]]; // [x centre, hole dia]: 2x M20, 4x M16, 1x M12 vent
function bx(x) = wall + margin_l + x;                                  // board -> enclosure coordinates
function by(y) = wall + bay_bottom + (pcb[1] - y);

module rbox(x, y, z, rad) { hull() for (i = [rad, x - rad], j = [rad, y - rad]) translate([i, j, 0]) cylinder(r = rad, h = z); }
module corners() { for (i = [wall + boss/2 - 1, out_x - wall - boss/2 + 1], j = [wall + boss/2 - 1, out_y - wall - boss/2 + 1]) translate([i, j, 0]) children(); }

module base() {
  difference() {
    union() {
      difference() { rbox(out_x, out_y, base_h, r); translate([wall, wall, floor_t]) rbox(in_x, in_y, in_z + 1, r - wall); }
      corners() cylinder(d = boss, h = base_h);                                             // lid screw bosses
      for (h = pcb_holes) translate([bx(h[0]), by(h[1]), 0]) cylinder(d1 = 10, d2 = 7.5, h = floor_t + standoff);   // PCB standoffs
      for (sx = [0, 1], sy = [0, 1]) translate([sx ? out_x : 0, sy ? out_y - 22 : 8, 0])   // wall-mount ears
        mirror([sx ? 0 : 1, 0, 0]) difference() { hull() { cube([1, 14, 4]); translate([9, 7, 0]) cylinder(d = 14, h = 4); } translate([9, 7, -1]) cylinder(d = 5.2, h = 6); }
      translate([wall, wall + bay_bottom - 2.4, floor_t]) cube([in_x, 1.6, 3]);             // low rib: keeps loose wires off the PCB edge
    }
    corners() translate([0, 0, base_h - 7]) cylinder(d = 4.0, h = 8);                      // heat-set insert holes
    for (h = pcb_holes) translate([bx(h[0]), by(h[1]), floor_t + standoff - 6]) cylinder(d = 4.0, h = 7);   // M3 inserts for the PCB
    for (g = glands) translate([wall + g[0], -1, floor_t + in_z/2 + 1]) rotate([-90, 0, 0]) cylinder(d = g[1], h = wall + 2);
    translate([wall - 0.01, wall - 0.01, base_h - 1.6]) difference() {                      // gasket groove for 2 mm EPDM cord
      translate([-0.2, -0.2, 0]) rbox(in_x + 0.4 + 0.02, in_y + 0.4 + 0.02, 2, r - wall + 0.2);
      translate([1.9, 1.9, -1]) rbox(in_x - 3.8, in_y - 3.8, 4, max(r - wall - 1.9, 0.5));
      translate([-1, -1, -1]) cube([in_x + 2, in_y + 2, 1.0]); }
  }
}

module lid() {
  skirt = 6;                                                                                // drip skirt overlapping the base
  difference() {
    union() {
      rbox(out_x + 2*2.4 + 0.8, out_y + 2*2.4 + 0.8, lid_t, r + 2.8);
      translate([0, 0, lid_t]) difference() {                                               // skirt
        rbox(out_x + 2*2.4 + 0.8, out_y + 2*2.4 + 0.8, skirt, r + 2.8);
        translate([2.4, 2.4, -1]) rbox(out_x + 0.8, out_y + 0.8, skirt + 2, r + 0.4); }
      translate([2.8 + wall + 0.5, 2.8 + wall + 0.5, lid_t]) difference() {                 // tongue that compresses the gasket
        rbox(in_x - 1, in_y - 1, 1.6, r - wall); translate([1.6, 1.6, -1]) rbox(in_x - 4.2, in_y - 4.2, 4, max(r - wall - 1.6, 0.5)); }
      for (m = mic) translate([2.8 + bx(m[0]), 2.8 + (out_y - by(m[1])), lid_t])            // acoustic chimneys down to the PCB (add 1 mm foam ring)
        cylinder(d = 7, h = headroom - 1.2);
      translate([2.8 + out_x - 34, 2.8 + out_y - 24, lid_t]) difference() { cylinder(d = 44.5, h = 5); translate([0, 0, -1]) cylinder(d = 40.6, h = 7); }  // 40 mm speaker ring
    }
    for (i = [2.8 + wall + boss/2 - 1, 2.8 + out_x - wall - boss/2 + 1], j = [2.8 + wall + boss/2 - 1, 2.8 + out_y - wall - boss/2 + 1])
      translate([i, j, -1]) { cylinder(d = 3.4, h = lid_t + 4); cylinder(d = 6.2, h = 1 + 1.8); }                           // M3 screws, countersunk heads
    for (m = mic) translate([2.8 + bx(m[0]), 2.8 + (out_y - by(m[1])), -1]) { cylinder(d = 2, h = lid_t + headroom + 2); cylinder(d = 9, h = 1.4); }  // port + recess for adhesive ePTFE acoustic vent
    for (l = leds) translate([2.8 + bx(l[0]) - 7, 2.8 + (out_y - by(l[1])) - 3, 0.6]) cube([14, 6, lid_t]);                  // 0.6 mm light window over the status LEDs
    translate([2.8 + out_x - 34, 2.8 + out_y - 24, -1]) for (a = [0 : 30 : 330], rr = [6, 12, 17]) rotate(a) translate([rr, 0, 0]) cylinder(d = 2.2, h = lid_t + 2);  // speaker grille
  }
}

if (part == "base") base();
else if (part == "lid") lid();
else { base(); translate([-2.8, out_y + 2.8, base_h + lid_t + 12]) mirror([0, 1, 0]) mirror([0, 0, 1]) lid(); }
