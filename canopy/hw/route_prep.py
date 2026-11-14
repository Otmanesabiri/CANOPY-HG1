import pcbnew, json, design
K=design.HERE+'/kicad'
def cls(name,w,cl=0.15,via=0.5,drill=0.25):
    return {"name":name,"track_width":w,"clearance":cl,"via_diameter":via,"via_drill":drill,"bus_width":12,"diff_pair_gap":0.2,"diff_pair_via_gap":0.25,"diff_pair_width":0.2,"line_style":0,"microvia_diameter":0.3,"microvia_drill":0.1,"wire_width":6,"pcb_color":"rgba(0, 0, 0, 0.000)","schematic_color":"rgba(0, 0, 0, 0.000)"}
power=['VIN','SW_5V','SW_3V3','V_FIELD','+5V_SENS','USB1_VBUS','USB2_VBUS','USB3_VBUS']+[f'OUT{i}' for i in range(1,9)]
pro={"meta":{"filename":"canopy.kicad_pro","version":1},"sheets":[],"text_variables":{},
 "board":{"design_settings":{"rules":{"min_clearance":0.15,"min_track_width":0.15,"min_via_diameter":0.5,"min_through_hole_diameter":0.25,"min_copper_edge_clearance":0.3,"min_hole_clearance":0.25,"min_hole_to_hole":0.25,"min_via_annular_width":0.1,"solder_mask_to_copper_clearance":0.0},
   "track_widths":[0.0,0.15,0.2,0.5],"via_dimensions":[{"diameter":0.0,"drill":0.0},{"diameter":0.5,"drill":0.25},{"diameter":0.7,"drill":0.35}]}},
 "net_settings":{"classes":[cls("Default",0.15,0.15,0.5,0.25),cls("Power",0.5,0.15,0.7,0.35)],"meta":{"version":3},
   "netclass_patterns":[{"netclass":"Power","pattern":n} for n in power]}}
json.dump(pro,open(K+'/canopy.kicad_pro','w'),indent=1)
b=pcbnew.LoadBoard(K+'/canopy.kicad_pcb')
print('netclass check:',b.FindNet('+5V').GetNetClassName(),b.FindNet('I2C_SDA').GetNetClassName())
for z in list(b.Zones()):
    if (z.GetLayer()==pcbnew.B_Cu and not z.GetIsRuleArea()) or (z.GetIsRuleArea() and not z.GetDoNotAllowTracks()):
        b.Remove(z)   # B.Cu pour and copper-pour-only rule areas are handled during zone fill in post_route.py
ok=pcbnew.ExportSpecctraDSN(b,K+'/canopy.dsn')
dsn=open(K+'/canopy.dsn').read().replace('(circle F.Cu 1000 0 -710)','(circle F.Cu 600 0 -710)').replace('(circle B.Cu 1000 0 -710)','(circle B.Cu 600 0 -710)')
open(K+'/canopy.dsn','w').write(dsn)
print('dsn',ok)
