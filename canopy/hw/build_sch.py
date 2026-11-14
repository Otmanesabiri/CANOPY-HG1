"""Generate the hierarchical KiCad 7 schematic (label-connected) from design.py."""
import uuid, os, json, sx, design
from collections import defaultdict
OUT=os.path.join(design.HERE,'kicad'); os.makedirs(OUT,exist_ok=True)
PROJ='canopy'; U=lambda s: str(uuid.uuid5(uuid.NAMESPACE_DNS,'canopy.'+s))
ROOT=U('root')
# ---- project-local symbol library (CM4, USB2514B)
def box_symbol(name,pins,ref='U',w=40.64):
    """pins: [(number,name)] split evenly left/right"""
    half=(len(pins)+1)//2; h=half*2.54+2.54; top=h/2
    s=[f'(symbol "{name}" (in_bom yes) (on_board yes)',
       f'(property "Reference" "{ref}" (at {-w/2} {top+1.27} 0) (effects (font (size 1.27 1.27)) (justify left)))',
       f'(property "Value" "{name}" (at 0 {top+1.27} 0) (effects (font (size 1.27 1.27)) (justify left)))',
       '(property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
       '(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
       f'(symbol "{name}_0_1" (rectangle (start {-w/2} {top}) (end {w/2} {-top}) (stroke (width 0.254) (type default)) (fill (type background))))',
       f'(symbol "{name}_1_1"']
    for i,(nu,nm) in enumerate(pins):
        left=i<half; row=i if left else i-half; y=top-2.54-row*2.54
        x=-w/2-5.08 if left else w/2+5.08
        s.append(f'(pin passive line (at {x} {y:.2f} {0 if left else 180}) (length 5.08) (name "{nm}" (effects (font (size 1.0 1.0)))) (number "{nu}" (effects (font (size 1.0 1.0)))))')
    s.append('))'); return '\n'.join(s)
cm4=sorted(design.cm4.items())
odd=[(str(n),nm) for n,nm in cm4 if n%2]; even=[(str(n),nm) for n,nm in cm4 if not n%2]
HUBP=['USBDM_DN1','USBDP_DN1','USBDM_DN2','USBDP_DN2','VDDA33','USBDM_DN3','USBDP_DN3','USBDM_DN4','USBDP_DN4','VDDA33','TEST',
 'PRTPWR1','OCS_N1','CRFILT','VDD33','PRTPWR2','OCS_N2','PRTPWR3','OCS_N3','PRTPWR4','OCS_N4','SDA/NON_REM1','VDD33','SCL/CFG_SEL0',
 'HS_IND/CFG_SEL1','RESET_N','VBUS_DET','SUSP_IND/NON_REM0','VDDA33','USBDM_UP','USBDP_UP','XTALOUT','XTALIN','PLLFILT','RBIAS','VDDA33','VSS(EP)']
open(os.path.join(OUT,'canopy.kicad_sym'),'w').write('(kicad_symbol_lib (version 20220914) (generator canopy)\n'+
  box_symbol('CM4',odd+even,w=60.96)+'\n'+box_symbol('USB2514B',[(str(i+1),n) for i,n in enumerate(HUBP)])+'\n)\n')
def getsym(sym):
    l,n=sym.split(':')
    return sx.flat(l,n,os.path.join(OUT,'canopy.kicad_sym') if l=='canopy' else None)
# ---- resolve pin->net for every part, verify
def resolve(p):
    fs=getsym(p['sym']); pins=sx.pins(fs); res={}; used=set()
    for nu,nm,x,y,a,t in pins:
        net=p['nets'].get(nu)
        if net is None: net=p['nets'].get(nm)
        if net is not None: used.add(nu if nu in p['nets'] else nm)
        res[nu]=(net,x,y,a)
    miss=set(p['nets'])-used
    assert not miss,(p['ref'],'unknown pins',miss)
    return fs,res
NETS=defaultdict(list); RES={}
for p in design.PARTS:
    fs,res=resolve(p); RES[p['ref']]=(fs,res)
    for nu,(net,*_) in res.items():
        if net: NETS[net].append(f"{p['ref']}.{nu}")
single=[n for n,v in NETS.items() if len(v)<2]
print('parts',len(design.PARTS),'nets',len(NETS),'single-pin nets:',single)
json.dump(NETS,open(os.path.join(OUT,'nets.json'),'w'),indent=1)
# ---- sheets
FONT='(effects (font (size 1.27 1.27))'
def sheet(name,title,page):
    parts=[p for p in design.PARTS if p['sheet']==name]
    libs={}; body=[]
    big=[p for p in parts if len(RES[p['ref']][1])>4]; small=[p for p in parts if len(RES[p['ref']][1])<=4]
    def ext(p):
        r=RES[p['ref']][1]; xs=[v[1] for v in r.values()] or [0]; ys=[v[2] for v in r.values()] or [0]
        ll=max([len(v[0] or '') for v in r.values()]+[4])*1.3+6
        return min(xs)-ll,max(xs)+ll,min(-y for y in ys)-8,max(-y for y in ys)+6
    def place(p,X,Y):
        fs,res=RES[p['ref']]; libs[p['sym']]=fs; X=round(X/2.54)*2.54; Y=round(Y/2.54)*2.54
        e=ext(p); uid=U(p['ref'])
        s=[f'(symbol (lib_id "{p["sym"]}") (at {X:.2f} {Y:.2f} 0) (unit 1) (in_bom {"no" if p["dnp"] else "yes"}) (on_board yes) (dnp no) (uuid {uid})',
           f'(property "Reference" "{p["ref"]}" (at {X:.2f} {Y+e[2]+3:.2f} 0) {FONT}))',
           f'(property "Value" "{p["value"]}" (at {X:.2f} {Y+e[2]+5.2:.2f} 0) {FONT}))',
           f'(property "Footprint" "{p["fp"]}" (at {X:.2f} {Y:.2f} 0) {FONT} hide))',
           f'(property "Datasheet" "~" (at {X:.2f} {Y:.2f} 0) {FONT} hide))',
           f'(property "MPN" "{p["mpn"]}" (at {X:.2f} {Y:.2f} 0) {FONT} hide))',
           f'(property "Manufacturer" "{p["mfr"]}" (at {X:.2f} {Y:.2f} 0) {FONT} hide))',
           f'(property "Description" "{p["desc"]}" (at {X:.2f} {Y:.2f} 0) {FONT} hide))']
        for nu in res: s.append(f'(pin "{nu}" (uuid {U(p["ref"]+"."+nu)}))')
        s.append(f'(instances (project "{PROJ}" (path "/{ROOT}/{U("sheet"+name)}" (reference "{p["ref"]}") (unit 1)))))')
        body.append('\n'.join(s))
        for nu,(net,x,y,a) in res.items():
            px,py=X+x,Y-y
            if net is None:
                body.append(f'(no_connect (at {px:.2f} {py:.2f}) (uuid {U(p["ref"]+nu+"nc")}))'); continue
            ang,j={0:(180,'right'),180:(0,'left'),90:(270,'right'),270:(90,'left')}[a]
            body.append(f'(global_label "{net}" (shape passive) (at {px:.2f} {py:.2f} {ang}) (effects (font (size 1.0 1.0)) (justify {j})) (uuid {U(p["ref"]+nu+"l")}))')
    W=max([420]+[ext(p)[1]-ext(p)[0]+50 for p in parts]); x=25; y=30; rowh=0; mx=[0]
    for p in sorted(big,key=lambda p:-(ext(p)[3]-ext(p)[2])):
        e=ext(p); w=e[1]-e[0]; h=e[3]-e[2]
        if x+w>W-20: x=25; y+=rowh+8; rowh=0
        place(p,x-e[0],y-e[2]); x+=w+6; rowh=max(rowh,h); mx[0]=max(mx[0],x)
    y+=rowh+12; x=25; rowh=0
    for p in small:
        e=ext(p); w=max(e[1]-e[0]-(max([len(v[0] or '') for v in RES[p['ref']][1].values()]+[4])*1.3+6)*2,0)+10.16; h=e[3]-e[2]+2*(max([len(v[0] or '') for v in RES[p['ref']][1].values()]+[4])*1.0)
        if RES[p['ref']][1] and all(v[3] in (0,180) for v in RES[p['ref']][1].values()): w=e[1]-e[0]; h=e[3]-e[2]
        h=max(h,46)
        if x+w>W-20: x=25; y+=rowh+6; rowh=0
        place(p,x+w/2,y+h/2); x+=w+2.54; rowh=max(rowh,h); mx[0]=max(mx[0],x)
    body.append(f'(text "{title}" (at 25 18 0) (effects (font (size 3 3) bold) (justify left bottom)) (uuid {U("t"+name)}))')
    t=[f'(kicad_sch (version 20230121) (generator eeschema)\n(uuid {U("sheet-file"+name)})\n(paper "User" {max(mx[0]+20,300):.0f} {max(y+rowh+45,210):.0f})',
       f'(title_block (title "Canopy GH-1 - {title}") (rev "A0") (company "Canopy GH-1 greenhouse controller"))',
       '(lib_symbols\n'+'\n'.join(sx.dump(v) for v in libs.values())+'\n)']+body+[')']
    open(os.path.join(OUT,f'{name}.kicad_sch'),'w').write('\n'.join(t)+'\n')
root=[f'(kicad_sch (version 20230121) (generator eeschema)\n(uuid {ROOT})\n(paper "A4")',
      '(title_block (title "Canopy GH-1 greenhouse controller") (rev "A0"))','(lib_symbols)']
for i,(n,t) in enumerate(design.SHEETS):
    sheet(n,t,i+2); X=30+(i%3)*85; Y=40+(i//3)*60
    root.append(f'''(sheet (at {X} {Y}) (size 70 40) (fields_autoplaced) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0)) (uuid {U("sheet"+n)})
 (property "Sheetname" "{n}" (at {X} {Y-0.7} 0) {FONT} (justify left bottom)))
 (property "Sheetfile" "{n}.kicad_sch" (at {X} {Y+40.6} 0) {FONT} (justify left top)))
 (instances (project "{PROJ}" (path "/{ROOT}" (page "{i+2}")))))
(text "{t}" (at {X+2} {Y+8} 0) (effects (font (size 1.5 1.5)) (justify left bottom)) (uuid {U("rt"+n)}))''')
root.append('(sheet_instances (path "/" (page "1")))\n)')
open(os.path.join(OUT,'canopy.kicad_sch'),'w').write('\n'.join(root)+'\n')
open(os.path.join(OUT,'sym-lib-table'),'w').write('(sym_lib_table\n (lib (name "canopy")(type "KiCad")(uri "${KIPRJMOD}/canopy.kicad_sym")(options "")(descr ""))\n)\n')
open(os.path.join(OUT,'fp-lib-table'),'w').write('(fp_lib_table\n (lib (name "canopy")(type "KiCad")(uri "${KIPRJMOD}/../lib/canopy.pretty")(options "")(descr ""))\n)\n')
open(os.path.join(OUT,'canopy.kicad_pro'),'w').write(json.dumps({"meta":{"filename":"canopy.kicad_pro","version":1},"sheets":[],"text_variables":{}},indent=1))
