from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math

ROOT=Path('/Users/adeel.tahir/Desktop/AIProject/DataHubHackathon/blast-radius-autopilot')
OUT=ROOT/'out'/'submission_banners'
OUT.mkdir(parents=True,exist_ok=True)
UI=ROOT/'out'/'live_ui'
W,H=1800,1200
BG='#080d1b'; PANEL='#111a2d'; PANEL2='#17233b'; INK='#f7f9fc'; MUTED='#a9b5c8'
CYAN='#48d7cb'; GREEN='#52d273'; AMBER='#f5b94d'; RED='#ff5f6d'; BLUE='#568cff'
BOLD='/System/Library/Fonts/Supplemental/Arial Bold.ttf'; REG='/System/Library/Fonts/Supplemental/Arial.ttf'; MONO='/System/Library/Fonts/SFNSMono.ttf'

def f(path,size): return ImageFont.truetype(path,size)

def base(accent=CYAN):
    im=Image.new('RGB',(W,H),BG); d=ImageDraw.Draw(im)
    for y in range(H):
        t=y/H
        c=(int(8+7*t),int(13+13*t),int(27+24*t))
        d.line((0,y,W,y),fill=c)
    # restrained graph motif
    for x in range(80,1760,120): d.line((x,0,x,H),fill='#0f192c',width=1)
    for y in range(80,1160,120): d.line((0,y,W,y),fill='#0f192c',width=1)
    d.rectangle((0,0,W,12),fill=accent)
    return im,d

def shadow_box(im,box,radius=32,fill=PANEL,outline='#263551'):
    x1,y1,x2,y2=box
    sh=Image.new('RGBA',im.size,(0,0,0,0)); sd=ImageDraw.Draw(sh)
    sd.rounded_rectangle((x1+18,y1+22,x2+18,y2+22),radius=radius,fill=(0,0,0,120))
    sh=sh.filter(ImageFilter.GaussianBlur(18)); im.paste(sh,(0,0),sh)
    d=ImageDraw.Draw(im); d.rounded_rectangle(box,radius=radius,fill=fill,outline=outline,width=2)

def footer(d,label='BLAST RADIUS AUTOPILOT'):
    d.text((90,1125),label,font=f(BOLD,22),fill='#738099')
    d.text((1515,1125),'DATAHUB HACKATHON',font=f(BOLD,20),fill='#738099')

def fit_screen(im,src,box):
    x1,y1,x2,y2=box; shot=Image.open(src).convert('RGB')
    maxw,maxh=x2-x1,y2-y1; ratio=min(maxw/shot.width,maxh/shot.height)
    shot=shot.resize((int(shot.width*ratio),int(shot.height*ratio)),Image.Resampling.LANCZOS)
    x=x1+(maxw-shot.width)//2; y=y1+(maxh-shot.height)//2
    im.paste(shot,(x,y))

def badge(d,xy,text,color,width=None):
    x,y=xy; w=width or d.textbbox((0,0),text,font=f(BOLD,24))[2]+54
    d.rounded_rectangle((x,y,x+w,y+62),radius=18,fill=color)
    d.text((x+25,y+18),text,font=f(BOLD,22),fill=BG)
    return w

# 1 Hero
im,d=base(CYAN)
d.text((90,105),'BLAST RADIUS',font=f(BOLD,78),fill=INK)
d.text((90,190),'AUTOPILOT',font=f(BOLD,130),fill=CYAN)
d.text((95,360),'DataHub shows the blast radius.',font=f(REG,45),fill=MUTED)
d.text((95,425),'Autopilot defuses it.',font=f(BOLD,53),fill=INK)
shadow_box(im,(950,100,1715,1010),radius=38,fill='#eef1f7')
fit_screen(im,UI/'13_b17_verification_pass_verdict_abovefold.png',(990,145,1675,965))
d=ImageDraw.Draw(im)
badge(d,(95,585),'STATIC PASS',GREEN,265); badge(d,(380,585),'REVIEW REQUIRED',AMBER,320); badge(d,(720,585),'FAIL',RED,175)
d.text((95,700),'Other agents write code.',font=f(BOLD,40),fill=MUTED)
d.text((95,760),'This one checks its own work',font=f(BOLD,45),fill=INK)
d.text((95,820),'and refuses to bluff.',font=f(BOLD,45),fill=CYAN)
footer(d); im.save(OUT/'banner-01-hero-v1.png',optimize=True)

# 2 Proof flow
im,d=base(BLUE)
d.text((90,85),'PROOF-CARRYING MIGRATIONS',font=f(BOLD,63),fill=INK)
d.text((93,170),'A generated fix is only the beginning.',font=f(REG,36),fill=MUTED)
steps=[('01','DETECT','Blast radius'),('02','PATCH','Minimal dbt fix'),('03','ISOLATE','Repository copy'),('04','RECOMPUTE','Same analyzer'),('05','GATE','PASS or refuse')]
for i,(num,title,sub) in enumerate(steps):
    x=70+i*345
    shadow_box(im,(x,340,x+295,715),radius=30,fill=PANEL)
    d=ImageDraw.Draw(im); d.text((x+28,375),num,font=f(BOLD,30),fill=BLUE)
    d.text((x+28,465),title,font=f(BOLD,34),fill=INK)
    d.text((x+28,535),sub,font=f(REG,27),fill=MUTED)
    if i<4:
        d.line((x+295,525,x+340,525),fill=CYAN,width=5)
        d.polygon([(x+340,525),(x+324,515),(x+324,535)],fill=CYAN)
d.rounded_rectangle((150,805,1650,1010),radius=32,fill='#0e2830',outline='#1c6a65',width=2)
d.text((210,850),'STATIC VERIFICATION PASS',font=f(BOLD,36),fill=GREEN)
d.text((210,918),'Breaks 2 → 0   •   Coverage 3 of 3   •   Patched files 2 of 2',font=f(BOLD,31),fill=INK)
footer(d,'DETECT  •  PATCH  •  ISOLATE  •  RECOMPUTE  •  PROVE  •  GATE'); im.save(OUT/'banner-02-proof-flow-v1.png',optimize=True)

# 3 Sweep
im,d=base(RED)
d.text((90,80),'CATALOG SWEEP',font=f(BOLD,77),fill=INK)
d.text((95,175),'Every candidate ranked. Every result accounted for.',font=f(REG,38),fill=MUTED)
shadow_box(im,(75,285,1160,1030),radius=38,fill='#f3f5f8')
fit_screen(im,UI/'19_b21_sweep_ledger.png',(110,320,1125,995))
d=ImageDraw.Draw(im)
stats=[('43','CANDIDATE COLUMNS',INK),('25','LANDMINES',RED),('1','NEEDS REVIEW',AMBER),('17','SAFE CANDIDATES',GREEN),('0','DATAHUB WRITES',CYAN)]
y=300
for n,l,c in stats:
    d.rounded_rectangle((1225,y,1725,y+125),radius=24,fill=PANEL,outline='#263551',width=2)
    d.text((1260,y+22),n,font=f(BOLD,51),fill=c); d.text((1375,y+48),l,font=f(BOLD,21),fill=MUTED); y+=145
d.text((1230,1035),'SYNTHETIC CATALOG RUN',font=f(BOLD,23),fill='#7e8ba1')
footer(d); im.save(OUT/'banner-03-catalog-sweep-v1.png',optimize=True)

# 4 Refusal model
im,d=base(AMBER)
d.text((90,80),'SAFE AUTOMATION NEEDS',font=f(BOLD,54),fill=MUTED)
d.text((90,155),'THE RIGHT TO REFUSE.',font=f(BOLD,83),fill=INK)
cards=[('PASS',GREEN,'Known blast radius removed','Automatic metadata write permitted'),('REVIEW REQUIRED',AMBER,'Evidence or manual work remains','Human may approve metadata only'),('FAIL',RED,'Migration could not be proven','No approval route. Zero writes.')]
for i,(title,c,line1,line2) in enumerate(cards):
    x=70+i*575
    shadow_box(im,(x,360,x+525,920),radius=34,fill=PANEL)
    d=ImageDraw.Draw(im); d.rounded_rectangle((x+35,410,x+490,505),radius=24,fill=c)
    sz=30 if title=='REVIEW REQUIRED' else 38
    d.text((x+65,440),title,font=f(BOLD,sz),fill=BG)
    d.text((x+40,600),line1,font=f(BOLD,27),fill=INK)
    # wrap second line manually
    if title=='REVIEW REQUIRED':
        d.text((x+40,690),'Human may approve',font=f(REG,27),fill=MUTED); d.text((x+40,730),'metadata only',font=f(REG,27),fill=MUTED)
    else:
        d.text((x+40,690),line2,font=f(REG,27),fill=MUTED)
d.text((90,1005),'No query executed  •  No warehouse contacted  •  No data read',font=f(BOLD,30),fill=AMBER)
footer(d); im.save(OUT/'banner-04-refusal-model-v1.png',optimize=True)

# 5 Audit graph
im,d=base(CYAN)
d.text((90,75),'THE EVIDENCE OUTLIVES THE RUN',font=f(BOLD,61),fill=INK)
d.text((95,165),'Human approval is recorded in the DataHub graph.',font=f(REG,37),fill=MUTED)
shadow_box(im,(70,275,1065,1015),radius=38,fill='#f2f4f8')
fit_screen(im,UI/'16_b20_3_approval_audit_viewport.png',(105,310,1030,980))
d=ImageDraw.Draw(im)
props=[('APPROVED BY','reviewer@example.com'),('APPROVED AT','timestamp'),('MANIFEST','single-use identifier'),('VERDICT','REVIEW_REQUIRED'),('WRITES','8 succeeded'),('FAILURES','0 recorded')]
y=280
for a,b in props:
    d.rounded_rectangle((1130,y,1725,y+104),radius=22,fill=PANEL,outline='#263551',width=2)
    d.text((1160,y+18),a,font=f(BOLD,19),fill=CYAN)
    d.text((1160,y+52),b,font=f(BOLD,27),fill=INK); y+=120
d.text((1135,1030),'A human approved metadata write-back.',font=f(BOLD,24),fill=MUTED)
d.text((1135,1065),'The verdict remained REVIEW REQUIRED.',font=f(BOLD,24),fill=AMBER)
footer(d); im.save(OUT/'banner-05-datahub-audit-v1.png',optimize=True)

print('\n'.join(str(p) for p in sorted(OUT.glob('banner-*.png'))))
