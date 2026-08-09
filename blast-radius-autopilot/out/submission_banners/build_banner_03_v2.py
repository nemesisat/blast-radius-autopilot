from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter
ROOT=Path('/Users/adeel.tahir/Desktop/AIProject/DataHubHackathon/blast-radius-autopilot')
OUT=ROOT/'out'/'submission_banners'; UI=ROOT/'out'/'live_ui'; W,H=1800,1200
BG='#080d1b'; PANEL='#111a2d'; INK='#f7f9fc'; MUTED='#a9b5c8'; CYAN='#48d7cb'; GREEN='#52d273'; AMBER='#f5b94d'; RED='#ff5f6d'
BOLD='/System/Library/Fonts/Supplemental/Arial Bold.ttf'; REG='/System/Library/Fonts/Supplemental/Arial.ttf'
def f(p,s): return ImageFont.truetype(p,s)
im=Image.new('RGB',(W,H),BG); d=ImageDraw.Draw(im)
for y in range(H):
 t=y/H; c=(int(8+7*t),int(13+13*t),int(27+24*t)); d.line((0,y,W,y),fill=c)
for x in range(80,1760,120): d.line((x,0,x,H),fill='#0f192c')
for y in range(80,1160,120): d.line((0,y,W,y),fill='#0f192c')
d.rectangle((0,0,W,12),fill=RED)
d.text((90,70),'CATALOG SWEEP',font=f(BOLD,77),fill=INK)
d.text((95,165),'Every candidate ranked. Every result accounted for.',font=f(REG,38),fill=MUTED)
# screenshot card
sh=Image.new('RGBA',im.size,(0,0,0,0)); sd=ImageDraw.Draw(sh); sd.rounded_rectangle((93,317,1178,1062),radius=38,fill=(0,0,0,120)); sh=sh.filter(ImageFilter.GaussianBlur(18)); im.paste(sh,(0,0),sh)
d=ImageDraw.Draw(im); d.rounded_rectangle((75,295,1160,1040),radius=38,fill='#f3f5f8',outline='#263551',width=2)
d.rounded_rectangle((105,320,480,375),radius=16,fill='#e5e9f0'); d.text((130,337),'FLAGSHIP LEDGER  •  13 COLUMNS',font=f(BOLD,18),fill='#24324a')
shot=Image.open(UI/'19_b21_sweep_ledger.png').convert('RGB'); maxw,maxh=1015,620; r=min(maxw/shot.width,maxh/shot.height); shot=shot.resize((int(shot.width*r),int(shot.height*r)),Image.Resampling.LANCZOS); im.paste(shot,(105+(maxw-shot.width)//2,390+(maxh-shot.height)//2))
d=ImageDraw.Draw(im)
d.text((1225,270),'6-CATALOG SYNTHETIC AGGREGATE',font=f(BOLD,21),fill=MUTED)
stats=[('43','CANDIDATE COLUMNS',INK),('25','LANDMINES',RED),('1','NEEDS REVIEW',AMBER),('17','SAFE CANDIDATES',GREEN),('0','DATAHUB WRITES',CYAN)]
y=315
for n,l,c in stats:
 d.rounded_rectangle((1225,y,1725,y+125),radius=24,fill=PANEL,outline='#263551',width=2)
 d.text((1260,y+22),n,font=f(BOLD,51),fill=c); d.text((1375,y+48),l,font=f(BOLD,21),fill=MUTED); y+=145
d.text((1230,1050),'READ-ONLY  •  ZERO DATAHUB MUTATIONS',font=f(BOLD,21),fill=CYAN)
d.text((90,1125),'BLAST RADIUS AUTOPILOT',font=f(BOLD,22),fill='#738099'); d.text((1515,1125),'DATAHUB HACKATHON',font=f(BOLD,20),fill='#738099')
p=OUT/'banner-03-catalog-sweep-v2.png'; im.save(p,optimize=True); print(p)
