BODY="M100 22 C 108 58 158 92 158 146 C 158 180 132 204 100 204 C 68 204 42 180 42 146 C 42 112 70 96 82 70 C 88 56 92 44 100 22 Z"
FLICK="M134 54 C 142 66 145 78 140 90 C 133 82 130 70 134 54 Z"
INK="#0E1320"; GLOW="#7FE3D6"; CORE="#F4FFFD"; DEEP="#1F8F86"; EMBER="#FFB86B"

def defs(p, mid=GLOW, core=CORE, edge=DEEP, halo=GLOW, ho=0.4):
    return (f'<defs><radialGradient id="{p}-h" cx="50%" cy="58%" r="50%"><stop offset="0%" stop-color="{halo}" stop-opacity="{ho}"/><stop offset="100%" stop-color="{halo}" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="{p}-b" cx="50%" cy="68%" r="62%"><stop offset="0%" stop-color="{core}"/><stop offset="50%" stop-color="{mid}"/><stop offset="100%" stop-color="{edge}"/></radialGradient></defs>')

def base(p, halo=True, flick=True, **k):
    s=defs(p,**k)
    if halo: s+=f'<circle cx="100" cy="140" r="100" fill="url(#{p}-h)"/>'
    s+=f'<path d="{BODY}" fill="url(#{p}-b)"/>'
    if flick: s+=f'<path d="{FLICK}" fill="{k.get("mid",GLOW)}" opacity="0.7"/>'
    return s

def eyes(y=146, rx=7, ry=11, dx=0, hl=True):
    s=f'<ellipse cx="{82+dx}" cy="{y}" rx="{rx}" ry="{ry}" fill="{INK}"/><ellipse cx="{118+dx}" cy="{y}" rx="{rx}" ry="{ry}" fill="{INK}"/>'
    if hl: s+=f'<circle cx="{84.5+dx}" cy="{y-5}" r="2.2" fill="#FFFFFF"/><circle cx="{120.5+dx}" cy="{y-5}" r="2.2" fill="#FFFFFF"/>'
    return s

def expr(name, p):
    if name=="idle": return base(p)+eyes()
    if name=="listening":
        return base(p,mid="#8FF0E2",core="#FFFFFF",ho=0.55)+eyes(144,9,14)+\
          f'<path d="M170 124 q 10 20 0 40" stroke="{GLOW}" stroke-width="5" fill="none" stroke-linecap="round"/><path d="M184 112 q 12 32 0 64" stroke="{GLOW}" stroke-width="5" fill="none" stroke-linecap="round" opacity="0.6"/>'
    if name=="thinking":
        return base(p)+eyes(138,6,9,6,False)+\
          f'<circle cx="160" cy="80" r="4" fill="{GLOW}" opacity="0.5"/><circle cx="172" cy="64" r="5" fill="{GLOW}" opacity="0.75"/><circle cx="184" cy="46" r="6" fill="{GLOW}"/>'
    if name=="speaking":
        return base(p)+eyes(142)+f'<ellipse cx="100" cy="172" rx="10" ry="7" fill="{INK}"/>'
    if name=="happy":
        return base(p,halo=True,halo_c=None) if False else (defs(p,halo=EMBER,ho=0.28)+f'<circle cx="100" cy="140" r="100" fill="url(#{p}-h)"/><path d="{BODY}" fill="url(#{p}-b)"/><path d="{FLICK}" fill="{GLOW}" opacity="0.7"/>'+\
          f'<path d="M73 152 q 9 -16 18 0" stroke="{INK}" stroke-width="6" fill="none" stroke-linecap="round"/><path d="M109 152 q 9 -16 18 0" stroke="{INK}" stroke-width="6" fill="none" stroke-linecap="round"/>'+\
          f'<circle cx="68" cy="166" r="7" fill="{EMBER}" opacity="0.6"/><circle cx="132" cy="166" r="7" fill="{EMBER}" opacity="0.6"/>')
    if name=="sleepy":
        return base(p,halo=False,flick=False,mid="#4E9C95",core="#BFD9D6",edge="#1D4F4B")+\
          f'<path d="M74 150 h16" stroke="{INK}" stroke-width="5" stroke-linecap="round"/><path d="M110 150 h16" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>'+\
          f'<text x="150" y="86" font-size="22" fill="{GLOW}" opacity="0.6" font-family="IBM Plex Mono, DejaVu Sans Mono, monospace">z</text><text x="166" y="60" font-size="30" fill="{GLOW}" font-family="IBM Plex Mono, DejaVu Sans Mono, monospace">z</text>'
EXPRS=["idle","listening","thinking","speaking","happy","sleepy"]

SIDE="M78 24 C 90 60 146 96 146 148 C 146 182 124 204 100 204 C 74 204 56 184 56 150 C 56 112 80 96 82 70 C 83 56 80 40 78 24 Z"
def view(v,p):
    if v=="front": return expr("idle",p)
    if v=="threequarter":
        return base(p,flick=False)+f'<path d="M66 60 C 58 72 55 84 60 96 C 67 88 70 76 66 60 Z" fill="{GLOW}" opacity="0.6"/>'+\
          f'<ellipse cx="96" cy="146" rx="7" ry="11" fill="{INK}"/><ellipse cx="128" cy="146" rx="5" ry="11" fill="{INK}"/><circle cx="98.5" cy="141" r="2.2" fill="#fff"/><circle cx="129.5" cy="141" r="1.8" fill="#fff"/>'
    if v=="side":
        return defs(p)+f'<circle cx="100" cy="140" r="100" fill="url(#{p}-h)"/><path d="{SIDE}" fill="url(#{p}-b)"/>'+\
          f'<ellipse cx="132" cy="146" rx="4" ry="11" fill="{INK}"/><circle cx="133" cy="141" r="1.6" fill="#fff"/>'
    if v=="back":
        return base(p,flick=False)+f'<path d="M66 54 C 58 66 55 78 60 90 C 67 82 70 70 66 54 Z" fill="{GLOW}" opacity="0.7"/>'+\
          f'<ellipse cx="100" cy="176" rx="30" ry="10" fill="{DEEP}" opacity="0.35"/>'

def svg(inner, w=200, h=240, vb="0 0 200 240", bg=None, extra=""):
    b=f'<rect x="-1000" y="-1000" width="3000" height="3000" fill="{bg}"/>' if bg else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{w}" height="{h}">{b}{inner}{extra}</svg>'

def eyes_only(p):
    return (f'<defs><radialGradient id="{p}" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="{GLOW}" stop-opacity="0.35"/><stop offset="100%" stop-color="{GLOW}" stop-opacity="0"/></radialGradient></defs>'
      f'<ellipse cx="68" cy="100" rx="40" ry="52" fill="url(#{p})"/><ellipse cx="132" cy="100" rx="40" ry="52" fill="url(#{p})"/>'
      f'<ellipse cx="68" cy="100" rx="18" ry="30" fill="{GLOW}"/><ellipse cx="132" cy="100" rx="18" ry="30" fill="{GLOW}"/>'
      f'<ellipse cx="72" cy="90" rx="6" ry="9" fill="{CORE}"/><ellipse cx="136" cy="90" rx="6" ry="9" fill="{CORE}"/>')
