"""Build the PCB from the KiCad netlist: placement, outline, planes.  Stage 'place' writes canopy_unrouted.kicad_pcb + DSN."""
import pcbnew, os, sys, json, math, design, sx
H=design.HERE; K=H+'/kicad'; F='/usr/share/kicad/footprints/'
mm=pcbnew.ToMM; MM=pcbnew.FromMM; V=lambda x,y: pcbnew.VECTOR2I(MM(x+OX),MM(y+OY))
OX,OY=50,50; BW,BH=150,100
MANUAL={ # ref: (x, y, rot, side) - x,y = centre of footprint bounding box, mm from board top-left
 'U4':(33.5,27,90,'F'),'J1':(14,96,0,'F'),'J6':(38,90.6,0,'F'),'J4':(66,91.2,0,'F'),'J10':(91,96,0,'F'),'J11':(115,96,0,'F'),
 'J13':(129,96,0,'F'),'J16':(146,23,90,'F'),'J17':(146,50,90,'F'),'J12':(146,74,90,'F'),'J5':(92,62,0,'F'),'J7':(56,60,0,'F'),
 'J14':(72,4.5,180,'F'),'J15':(82,4.5,180,'F'),'J8':(118,6,180,'F'),'J9':(94,16,0,'F'),'J2':(64,12,0,'F'),'J3':(66,38,0,'F'),
 'JP1':(2.6,30,0,'F'),'SW1':(3.2,40,90,'F'),'U1':(8,83,0,'F'),'Q1':(8,76.5,0,'F'),'D1':(9,89.5,0,'F'),'D2':(15,73,0,'F'),
 'U2':(9,63,0,'F'),'L1':(9,54,0,'F'),'U3':(67,52,0,'F'),'L2':(73.5,52.5,0,'F'),'U5':(24,50.5,0,'F'),'U6':(22,76.5,0,'F'),
 'U7':(68,65,0,'F'),'Y1':(76,63,0,'F'),'U8':(55,71.5,0,'F'),'U10':(79.5,71.5,0,'F'),'U9':(61.5,78,0,'F'),'U11':(69.5,78,0,'F'),
 'F1':(86,55,0,'F'),'U12':(46.5,51,0,'F'),'U13':(108,12,0,'F'),'MK1':(96,5,0,'B'),'MK2':(130,5,0,'B'),'U14':(80,20,0,'F'),
 'U15':(106,30,0,'F'),'U16':(92,80,0,'F'),'SW2':(120,30,0,'F'),'D5':(118,22,90,'F'),'D6':(121.5,22,90,'F'),'D7':(125,22,90,'F'),
 'D3':(3,14,90,'F'),'D4':(3,20,90,'F'),'U17':(134,72,0,'F'),'U18':(124,86,0,'F'),'D8':(131,87,0,'F'),'JP2':(137,86,0,'F'),
 'U19':(99,44,0,'F'),'BT1':(116,47,0,'F'),'F2':(136,7,0,'F'),
 'H1':(3.5,3.5,0,'F'),'H2':(146.5,3.5,0,'F'),'H3':(3.5,96.5,0,'F'),'H4':(146.5,96.5,0,'F')}
POWER={'GND','+5V','+3V3','CM4_3V3','VBUS','VIN','V_FIELD','+5V_SENS'}
def load(fp):
    l,n=fp.split(':'); return pcbnew.FootprintLoad(H+'/lib/canopy.pretty' if l=='canopy' else F+l+'.pretty',n)
def bbox(f):
    b=f.GetBoundingBox(False,False); return (mm(b.GetLeft())-OX,mm(b.GetTop())-OY,mm(b.GetRight())-OX,mm(b.GetBottom())-OY)
def put(f,x,y,rot,side):
    f.SetPosition(pcbnew.VECTOR2I(0,0)); f.SetOrientationDegrees(rot)
    if side=='B' and f.GetLayer()==pcbnew.F_Cu: f.Flip(pcbnew.VECTOR2I(0,0),False)
    b=f.GetBoundingBox(False,False); cx=(b.GetLeft()+b.GetRight())/2; cy=(b.GetTop()+b.GetBottom())/2
    f.SetPosition(pcbnew.VECTOR2I(int(MM(x+OX)-cx),int(MM(y+OY)-cy)))
def build():
    net=json.load(open(K+'/nets.json')); pin2net={pn:n for n,pl in net.items() for pn in pl}
    b=pcbnew.BOARD(); b.SetCopperLayerCount(4)
    ds=b.GetDesignSettings(); ds.m_TrackMinWidth=MM(0.15); ds.m_MinClearance=MM(0.15); ds.m_ViasMinSize=MM(0.5); ds.m_MinThroughDrill=MM(0.25)
    ds.m_CopperEdgeClearance=MM(0.3)
    nets={}
    for n in net:
        ni=pcbnew.NETINFO_ITEM(b,n); b.Add(ni); nets[n]=ni
    fps={}; rects={'F':[],'B':[]}
    def add(p,x,y,rot,side):
        f=load(p['fp']); f.SetReference(p['ref']); f.SetValue(p['value']); b.Add(f); put(f,x,y,rot,side)
        for pad in f.Pads():
            n=pin2net.get(f"{p['ref']}.{pad.GetNumber()}")
            if n: pad.SetNet(nets[n])
            elif p['ref']=='J7' and pad.GetNumber() in('10','11'): pad.SetNet(nets['GND'])
        fps[p['ref']]=f; bb=bbox(f); rects[side].append(bb)
        if any(pd.GetAttribute()==pcbnew.PAD_ATTRIB_PTH or pd.GetAttribute()==pcbnew.PAD_ATTRIB_NPTH for pd in f.Pads()): rects['B' if side=='F' else 'F'].append(bb) if p['ref']!='U4' else None
        return f
    parts={p['ref']:p for p in design.PARTS}
    for r,(x,y,rot,s) in MANUAL.items(): add(parts[r],x,y,rot,s)
    rects['F']+= [(94,3,98,7),(128,3,132,7)]  # keep top clear above mic ports
    # --- greedy auto-placement of passives next to the pad they serve
    def free(bb,side='F',m=0.3):
        if bb[0]<1.2 or bb[1]<1.2 or bb[2]>BW-1.2 or bb[3]>BH-1.2: return False
        return not any(bb[0]<r[2]+m and bb[2]>r[0]-m and bb[1]<r[3]+m and bb[3]>r[1]-m for r in rects[side])
    def target(p,prev):
        mynets=set(p['nets'].values())
        for sig in (True,False):
            for n in p['nets'].values():
                if (n in POWER)==sig: continue
                for pn in net[n]:
                    r,pinno=pn.split('.',1)
                    if r in fps and r!=p['ref']:
                        for pad in fps[r].Pads():
                            if pad.GetNumber()==pinno: return mm(pad.GetPosition().x)-OX,mm(pad.GetPosition().y)-OY
            # power-only part: nearest pad of preceding IC on any of my nets
            if sig and prev in fps:
                c=[pad for pad in fps[prev].Pads() if pad.GetNetname() in mynets-{'GND'}] or list(fps[prev].Pads())
                pad=c[0]; return mm(pad.GetPosition().x)-OX,mm(pad.GetPosition().y)-OY
        return None
    prev=None; todo=[]
    for p in design.PARTS:
        if p['ref'] in MANUAL: prev=p['ref']; continue
        todo.append((p,prev))
    for rnd in range(3):
        rest=[]
        for p,prev in todo:
            t=target(p,prev)
            if t is None: rest.append((p,prev)); continue
            f=load(p['fp']); best=None
            for rot in (0,90):
                put(f,0,0,rot,'F'); bb0=bbox(f); w=bb0[2]-bb0[0]; h=bb0[3]-bb0[1]
                for rad in [i*0.5 for i in range(2,60)]:
                    for k in range(max(8,int(rad*8))):
                        a=2*math.pi*k/max(8,int(rad*8)); x=round((t[0]+rad*math.cos(a))*4)/4; y=round((t[1]+rad*math.sin(a))*4)/4
                        if free((x-w/2,y-h/2,x+w/2,y+h/2)):
                            if best is None or rad<best[0]: best=(rad,x,y,rot)
                            break
                    if best and best[0]<=rad: break
            assert best,p['ref']
            add(p,best[1],best[2],best[3],'F')
        todo=rest
    assert not todo,[p['ref'] for p,_ in todo]
    # --- outline (rounded rectangle)
    r=3
    def seg(x1,y1,x2,y2):
        s=pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetStart(V(x1,y1)); s.SetEnd(V(x2,y2)); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(0.1)); b.Add(s)
    def arc(cx,cy,sx_,sy_,ex,ey):
        s=pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_ARC); s.SetCenter(V(cx,cy)); s.SetStart(V(sx_,sy_)); s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90,pcbnew.DEGREES_T),True); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(0.1)); b.Add(s)
    seg(r,0,BW-r,0); seg(BW,r,BW,BH-r); seg(BW-r,BH,r,BH); seg(0,BH-r,0,r)
    arc(r,r,0,r,r,0); arc(BW-r,r,BW-r,0,BW,r); arc(BW-r,BH-r,BW,BH-r,BW-r,BH); arc(r,BH-r,r,BH,0,BH-r)
    # --- zones
    def zone(netname,layer,pts,prio=0,keepout=False):
        z=pcbnew.ZONE(b); z.SetLayer(layer)
        if keepout:
            z.SetIsRuleArea(True); z.SetDoNotAllowCopperPour(True); z.SetDoNotAllowTracks(False); z.SetDoNotAllowVias(False); z.SetDoNotAllowPads(False); z.SetDoNotAllowFootprints(False)
            ls=pcbnew.LSET(); [ls.AddLayer(l) for l in (pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.In2_Cu,pcbnew.B_Cu)]; z.SetLayerSet(ls)
        else:
            z.SetNetCode(nets[netname].GetNetCode()); z.SetAssignedPriority(prio); z.SetLocalClearance(MM(0.25)); z.SetMinThickness(MM(0.2))
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL); z.SetThermalReliefGap(MM(0.3)); z.SetThermalReliefSpokeWidth(MM(0.4))
        o=z.Outline(); o.NewOutline()
        for x,y in pts: o.Append(MM(x+OX),MM(y+OY))
        b.Add(z); return z
    full=[(0.5,0.5),(BW-0.5,0.5),(BW-0.5,BH-0.5),(0.5,BH-0.5)]
    zone('GND',pcbnew.In1_Cu,full); zone('+3V3',pcbnew.In2_Cu,full,0)
    zone('+5V',pcbnew.In2_Cu,[(1,38),(62,38),(62,60),(100,60),(100,99),(1,99)],1)
    zone('GND',pcbnew.B_Cu,full)
    # Wi-Fi antenna: no copper pour under either short end of the CM4 (antenna end to be confirmed, see docs)
    zone(None,pcbnew.F_Cu,[(6,7),(15,7),(15,47),(6,47)],keepout=True); zone(None,pcbnew.F_Cu,[(52,7),(61,7),(61,47),(52,47)],keepout=True)
    t=pcbnew.PCB_TEXT(b); t.SetText('Canopy GH-1  rev A0'); t.SetLayer(pcbnew.F_SilkS); t.SetPosition(V(110,60)); t.SetTextSize(pcbnew.VECTOR2I(MM(1.5),MM(1.5))); t.SetTextThickness(MM(0.25)); b.Add(t)
    b.SetFileName(K+'/canopy.kicad_pcb'); pcbnew.SaveBoard(K+'/canopy.kicad_pcb',b)
    return b
if __name__=='__main__':
    b=build(); print('footprints',len(b.GetFootprints()),'nets',b.GetNetCount())
