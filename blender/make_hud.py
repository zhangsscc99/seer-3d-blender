"""生成完整 UV 使用的实验室线框诊断屏。"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1536, 900
img = Image.new('RGB', (W, H), (5, 23, 39))
d = ImageDraw.Draw(img)
CY, DIM, WHITE = (82, 199, 222), (29, 76, 98), (167, 224, 232)
font = ImageFont.load_default(size=22)
small = ImageFont.load_default(size=16)
for x in range(0, W, 48):
    d.line((x, 0, x, H), fill=(10, 33, 49))
for y in range(0, H, 48):
    d.line((0, y, W, y), fill=(10, 33, 49))
d.rounded_rectangle((15, 15, W-15, H-15), radius=30, outline=CY, width=4)
d.text((48, 38), 'SEER / INVENTION LAB     -     SPECIMEN ANALYSIS', fill=WHITE, font=font)
d.text((1200, 42), 'SYSTEM ONLINE', fill=CY, font=small)
for box in [(44,100,410,550),(440,100,990,550),(1020,100,1490,550),(44,580,650,850),(680,580,1490,850)]:
    d.rounded_rectangle(box, radius=12, outline=DIM, width=3)
for i, label in enumerate(['CELL STATUS','ENERGY LEVEL','OXYGEN','TEMPERATURE','SIGNAL','STABILITY']):
    y=140+i*64
    d.text((65,y),label,fill=WHITE,font=small)
    for k in range(17):
        d.rectangle((65+k*18,y+26,75+k*18,y+34),fill=CY if k < 10+i else DIM)
# 两个人形机械结构，细线显示，不使用实心大色块。
for cx in (590,830):
    d.ellipse((cx-32,155,cx+32,219),outline=WHITE,width=3)
    d.polygon([(cx-35,240),(cx+35,240),(cx+50,340),(cx-50,340)],outline=CY,width=3)
    for side in (-1,1):
        d.line([(cx+side*35,248),(cx+side*72,300),(cx+side*62,365)],fill=WHITE,width=4)
        d.line([(cx+side*24,340),(cx+side*34,415),(cx+side*47,470)],fill=WHITE,width=4)
    for yy in range(255,338,16):
        d.line((cx-32,yy,cx+32,yy),fill=DIM,width=2)
    d.ellipse((cx-76,480,cx+76,502),outline=DIM,width=2)
for r in (50,78,110,139):
    d.arc((1250-r,302-r,1250+r,302+r),15,330,fill=CY if r%2 else WHITE,width=3)
for i in range(36):
    a=i*math.tau/36
    d.line((1250+145*math.cos(a),302+145*math.sin(a),1250+156*math.cos(a),302+156*math.sin(a)),fill=DIM,width=3)
d.text((1120,490),'CORE 01 / SYNC 99.8%',fill=WHITE,font=font)
for i in range(4):
    pts=[(75+j*8,635+i*48+12*math.sin(j*0.45+i)) for j in range(66)]
    d.line(pts,fill=CY if i%2 else DIM,width=2)
for i,line in enumerate(['SPECIMEN  0007     SEQUENCE / ACTIVE','SCAN COMPLETE     128 / 128','MATERIAL DENSITY  0.8472','LIFE SUPPORT      NOMINAL','NEXT CYCLE        00:24:08']):
    d.text((710,610+i*42),line,fill=WHITE if i==0 else CY,font=font)
img.save(Path(__file__).with_name('hud.png'))
print('hud ok')
