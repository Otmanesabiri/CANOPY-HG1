"""Import the autorouter session, add pours, fill, run DRC, export fabrication outputs."""
import pcbnew, os, sys, csv, subprocess, shutil, collections, design
K=design.HERE+'/kicad'; FAB=design.HERE+'/fab'; MM=pcbnew.FromMM; OX=OY=50
b=pcbnew.LoadBoard(K+'/canopy.kicad_pcb')
if os.path.exists(K+'/canopy.ses'):
    assert pcbnew.ImportSpecctraSES(b,K+'/canopy.ses'),'SES import failed'
def zone(net,layer,x0,y0,x1,y1,prio):
    z=pcbnew.ZONE(b); z.SetLayer(layer); z.SetNetCode(b.FindNet(net).GetNetCode()); z.SetAssignedPriority(prio)
    z.SetLocalClearance(MM(0.25)); z.SetMinThickness(MM(0.2)); z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if net!='GND' else pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(MM(0.3)); z.SetThermalReliefSpokeWidth(MM(0.4)); z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    o=z.Outline(); o.NewOutline()
    for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1)): o.Append(MM(x+OX),MM(y+OY))
    b.Add(z)
have_b=any(z.GetLayer()==pcbnew.B_Cu and not z.GetIsRuleArea() for z in b.Zones())
if not have_b:
    zone('GND',pcbnew.B_Cu,0.5,0.5,149.5,99.5,0)
    zone('GND',pcbnew.F_Cu,0.5,0.5,149.5,99.5,0)
    # copper for the high-current path in the power column (autorouted tracks alone are too thin for 3-4 A)
    zone('VBUS',pcbnew.F_Cu,2,73,19,99,3); zone('VIN',pcbnew.F_Cu,2,65.5,13,75.5,4)
    zone('SW_5V',pcbnew.F_Cu,2,57.2,13.5,62,5); zone('+5V',pcbnew.F_Cu,2,47.5,20,57,3)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.BuildConnectivity(); un=b.GetConnectivity().GetUnconnectedCount(False)
tracks=[t for t in b.GetTracks()]; vias=sum(1 for t in tracks if t.Type()==pcbnew.PCB_VIA_T)
print(f'tracks {len(tracks)-vias}  vias {vias}  unconnected ratsnest items {un}')
pcbnew.SaveBoard(K+'/canopy.kicad_pcb',b)
pcbnew.WriteDRCReport(b,design.HERE+'/drc_report.txt',pcbnew.EDA_UNITS_MILLIMETRES,True)
rep=open(design.HERE+'/drc_report.txt').read()
kinds=collections.Counter(l.split(']')[0].strip('[') for l in rep.splitlines() if l.startswith('['))
print('DRC:',[l for l in rep.splitlines() if l.startswith('**')]); print(dict(kinds))
if '--fab' in sys.argv:
    shutil.rmtree(FAB,ignore_errors=True); os.makedirs(FAB+'/gerber')
    L='F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts'
    subprocess.run(['kicad-cli','pcb','export','gerbers','-l',L,'--subtract-soldermask','-o',FAB+'/gerber/',K+'/canopy.kicad_pcb'],check=True,capture_output=True)
    subprocess.run(['kicad-cli','pcb','export','drill','--format','excellon','--excellon-separate-th','--generate-map','--map-format','gerberx2','-o',FAB+'/gerber/',K+'/canopy.kicad_pcb'],check=True,capture_output=True)
    subprocess.run(['kicad-cli','pcb','export','pos','--format','csv','--units','mm','--side','both','-o',FAB+'/canopy-pos.csv',K+'/canopy.kicad_pcb'],check=True,capture_output=True)
    for side,layers in (('top','F.Cu,F.SilkS,F.Mask,Edge.Cuts'),('bottom','B.Cu,B.SilkS,Edge.Cuts'),('inner1','In1.Cu,Edge.Cuts'),('inner2','In2.Cu,Edge.Cuts')):
        subprocess.run(['kicad-cli','pcb','export','svg','-l',layers,'--page-size-mode','2','--exclude-drawing-sheet','-o',f'{FAB}/canopy-{side}.svg',K+'/canopy.kicad_pcb'],check=True,capture_output=True)
    # BOM grouped by MPN
    g=collections.OrderedDict()
    for p in design.PARTS:
        if p['dnp']: continue
        g.setdefault((p['mpn'],p['value'],p['fp']),[]).append(p)
    with open(FAB+'/canopy-bom.csv','w',newline='') as f:
        w=csv.writer(f); w.writerow(['Qty','References','Value','Description','Manufacturer','MPN','Footprint'])
        for (mpn,val,fp),ps in g.items():
            w.writerow([len(ps),' '.join(p['ref'] for p in ps),val,ps[0]['desc'],ps[0]['mfr'],mpn,fp.split(':')[1]])
        for q,ref,val,d,m,mpn in ((2,'(U4 sockets)','100-pin 0.4mm','CM4 mating connector - part of the U4 footprint','Hirose','DF40C-100DS-0.4V(51)'),
                                  (4,'(U4 standoffs)','M2.5 x 1.5 mm','SMT/press-fit spacer for CM4 (3.0 mm stack height uses DF40HC(3.0))','Wurth Elektronik','9774015151R'),
                                  (1,'(BT1 cell)','CR1220','3V lithium coin cell','Panasonic','CR1220')):
            w.writerow([q,ref,val,d,m,mpn,''])
    print('fab outputs:',sorted(os.listdir(FAB+'/gerber'))[:30])
