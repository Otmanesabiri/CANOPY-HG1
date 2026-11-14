import sys,os,json; H=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,H); import sx
t=sx.parse(open(H+'/kicad/canopy.net').read())
nets=[e for e in t if e[0]=='nets'][0][1:]; comps=[e for e in t if e[0]=='components'][0][1:]
got={}
for n in nets:
    name=[q for q in n if q[0]=='name'][0][1].strip('"'); nodes=[q for q in n if q[0]=='node']
    got[name.lstrip('/')]=sorted(f"{[r for r in q if r[0]=='ref'][0][1].strip(chr(34))}.{[r for r in q if r[0]=='pin'][0][1].strip(chr(34))}" for q in nodes)
want={k:sorted(v) for k,v in json.load(open(H+'/kicad/nets.json')).items()}
bad=[k for k in want if got.get(k)!=want[k]]
print('components',len(comps),'| nets in KiCad netlist',len([k for k in got if not k.startswith('unconnected')]),'| design nets',len(want),'| mismatches:',bad[:10], '| unexpected:',[k for k in got if k not in want and not k.startswith('unconnected')][:10])
