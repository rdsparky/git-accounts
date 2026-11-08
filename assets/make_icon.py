"""Draws assets/gitaccounts.ico (a toggle switch between two account dots). Needs Pillow; run once."""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((40, 40, S - 40, S - 40), radius=210, fill=(29, 31, 36, 255))
# toggle track
d.rounded_rectangle((150, 380, S - 150, 644), radius=132, fill=(42, 111, 219, 255))
# left account (work, orange) and right knob (personal, white with blue ring)
d.ellipse((190, 420, 374, 604), fill=(183, 121, 31, 255))
d.ellipse((S - 150 - 250, 392, S - 150 - 10, 632), fill=(255, 255, 255, 255))
# person glyph inside the knob
cx, cy = S - 150 - 130, 512
d.ellipse((cx - 38, cy - 78, cx + 38, cy - 2), fill=(42, 111, 219, 255))
d.pieslice((cx - 72, cy + 6, cx + 72, cy + 150), 180, 360, fill=(42, 111, 219, 255))
# small git-commit glyph above the switch
g = (230, 232, 236, 255)
d.line((300, 230, S - 300, 230), fill=g, width=30)
d.ellipse((S // 2 - 70, 160, S // 2 + 70, 300), fill=(29, 31, 36, 255), outline=g, width=30)
# label dots below: work (orange) / personal (blue)
d.rounded_rectangle((300, 760, 480, 820), radius=30, fill=(183, 121, 31, 255))
d.rounded_rectangle((S - 480, 760, S - 300, 820), radius=30, fill=(42, 111, 219, 255))

out = Path(__file__).with_name("gitaccounts.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.resize((256, 256), Image.LANCZOS).save(out.with_suffix(".png"))
print(out)
