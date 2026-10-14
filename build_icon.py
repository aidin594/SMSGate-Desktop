"""Generate the bundled native Windows icon; build uses the checked-in files."""
from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent / 'assets'
HERE.mkdir(parents=True, exist_ok=True)
S=1024
im=Image.new('RGBA',(S,S),(0,0,0,0))
d=ImageDraw.Draw(im)
# Modern app icon: saturated indigo gradient, soft inset and white chat glyph.
for y in range(84,952):
    fraction=(y-84)/868
    a=(91,65,220);b=(50,90,203)
    color=tuple(round(a[i]*(1-fraction)+b[i]*fraction) for i in range(3))+(255,)
    # Rounded rectangular stripe mask applied later to avoid sharp edges.
    d.line((84,y,940,y), fill=color,width=1)
mask=Image.new('L',(S,S),0)
md=ImageDraw.Draw(mask)
md.rounded_rectangle((58,58,966,966),radius=235,fill=255)
im.putalpha(mask)
d=ImageDraw.Draw(im)
# Inner subtle trim + legible stylised message bubble.
d.rounded_rectangle((83,83,942,942),radius=215,outline=(255,255,255,45),width=6)
d.rounded_rectangle((218,257,808,690),radius=128,fill=(255,255,255,255))
d.polygon([(327,663),(317,803),(482,681)],fill=(255,255,255,255))
# Minimal message bars (large enough to survive small icon sizes)
d.rounded_rectangle((332,394,696,437),radius=21,fill=(79,71,187,255))
d.rounded_rectangle((332,493,608,536),radius=21,fill=(79,71,187,255))
d.ellipse((712,695,827,810),fill=(75,219,191,255))
# pre-resize slightly sharp to improve small sizes.
resample=Image.Resampling.LANCZOS
im.save(HERE/'SMSGateDesk.png')
im.save(HERE/'SMSGateDesk.ico',format='ICO',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print('Generated PNG and Windows multi-size ICO')
