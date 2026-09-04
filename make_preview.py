#!/usr/bin/env python3
"""Generate preview.jpg — the 1200x630 card WhatsApp/Slack/Twitter show for the link.

Run manually when the branding changes; it is not part of the data pipeline.
Text is kept large and short because these render as small thumbnails in chat.
"""
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
PURPLE, DEEP, ACCENT = (61, 25, 91), (24, 12, 36), (201, 166, 255)

def font(name, size):
    for p in (f"/System/Library/Fonts/Supplemental/{name}.ttf",
              f"/Library/Fonts/{name}.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()

img = Image.new("RGB", (W, H), PURPLE)
d = ImageDraw.Draw(img)

# diagonal gradient, purple -> near-black
for y in range(H):
    for_x = y / H
    d.line([(0, y), (W, y)], fill=tuple(
        int(PURPLE[i] + (DEEP[i] - PURPLE[i]) * for_x) for i in range(3)))

# faint pitch arc, bottom-right — texture, not decoration people have to read
d.ellipse([W - 340, H - 250, W + 200, H + 290], outline=(255, 255, 255), width=3)
d.ellipse([W - 190, H - 110, W + 50, H + 130], outline=(255, 255, 255), width=3)

d.text((70, 92), "ENGLISH PREMIER LEAGUE", font=font("Arial Bold", 26), fill=ACCENT)
d.text((70, 150), "Premier League", font=font("Arial Black", 92), fill=(255, 255, 255))
d.text((70, 250), "Tracker", font=font("Arial Black", 92), fill=(255, 255, 255))

d.text((70, 388), "Table · Fixtures · Live scores · Highlights",
       font=font("Arial Bold", 36), fill=(236, 228, 244))
d.text((70, 440), "Every kickoff converted to your own timezone.",
       font=font("Arial", 32), fill=(190, 178, 205))

d.rectangle([70, 520, 74, 566], fill=ACCENT)
d.text((92, 524), "No ads · no tracking · no sign-in",
       font=font("Arial Bold", 30), fill=(214, 202, 228))

img.save("preview.jpg", "JPEG", quality=86, optimize=True)
print(f"wrote preview.jpg  {W}x{H}")
