"""Minimal KiCad s-expression + symbol-library helpers."""
import re, os, functools
SYM='/usr/share/kicad/symbols'
def parse(t):
    tok=re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',t); st=[[]]
    for k in tok:
        if k=='(': st.append([])
        elif k==')': l=st.pop(); st[-1].append(l)
        else: st[-1].append(k)
    return st[0][0]
def dump(x,ind=0):
    if isinstance(x,str): return x
    s='('+' '.join(dump(i,ind+1) for i in x)+')'
    return s
@functools.lru_cache(None)
def lib(name,path=None):
    p=path or f'{SYM}/{name}.kicad_sym'
    t=parse(open(p).read())
    return {e[1].strip('"'):e for e in t if isinstance(e,list) and e[0]=='symbol'}
def flat(libname,sym,path=None):
    """Return flattened symbol sexpr named 'lib:sym' (resolving extends)."""
    L=lib(libname,path); s=L[sym]
    ext=[e for e in s if isinstance(e,list) and e[0]=='extends']
    if ext:
        par=ext[0][1].strip('"'); base=flat(libname,par,path)
        props={e[1]:e for e in s if isinstance(e,list) and e[0]=='property'}
        out=[]
        for e in base[2:]:
            if isinstance(e,list) and e[0]=='property' and e[1] in props: out.append(props[e[1]])
            elif isinstance(e,list) and e[0]=='symbol':
                e=list(e); e[1]='"'+e[1].strip('"').replace(par,sym,1)+'"'; out.append(e)
            else: out.append(e)
        return ['symbol',f'"{libname}:{sym}"']+out
    return ['symbol',f'"{libname}:{sym}"']+[e for e in s[2:]]
def pins(fs):
    """[(number,name,x,y,angle,type)] for a flattened symbol"""
    r=[]
    def walk(e):
        for c in e:
            if isinstance(c,list):
                if c[0]=='pin':
                    at=[q for q in c if isinstance(q,list) and q[0]=='at'][0]
                    nm=[q for q in c if isinstance(q,list) and q[0]=='name'][0][1].strip('"')
                    nu=[q for q in c if isinstance(q,list) and q[0]=='number'][0][1].strip('"')
                    r.append((nu,nm,float(at[1]),float(at[2]),int(float(at[3])) if len(at)>3 else 0,c[1]))
                elif c[0]=='symbol': walk(c)
    walk(fs); return r
def prop(fs,k):
    for e in fs:
        if isinstance(e,list) and e[0]=='property' and e[1].strip('"')==k: return e[2].strip('"')
