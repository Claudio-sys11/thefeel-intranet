# -*- coding: utf-8 -*-
"""더필코리아 로고(TF 모노그램) 자산 생성: logo.svg / logo.png / app.ico
업로드된 로고를 동일한 격자(블록) 디자인으로 재현한다."""
import os
import io
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")
os.makedirs(STATIC, exist_ok=True)

# 흰색 블록 격자 (cols=9 x rows=8). 1 = 흰색
# 좌측 'T'(틱 + 세로기둥 + 상단보) + 우측 'F'(세로기둥 + 상단가지 + 중간가지) = TF 모노그램
GRID = [
    "0101111111",
    "0001100011",
    "0001101011",
    "0001101111",
    "0001100011",
    "0001100011",
    "0001100011",
    "0001100011",
]
COLS = 10
ROWS = 8
BG_TOP = (59, 19, 120)     # #3b1378
BG_BOT = (26, 7, 64)       # #1a0740
INDIGO = (42, 10, 94)      # #2a0a5e (solid)
WHITE = (255, 255, 255)


def draw(size):
    """size x size 정사각 로고 이미지를 그린다(둥근 모서리 배지 + 흰 마크)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 대각 그라데이션 배경
    grad = Image.new("RGB", (size, size), BG_BOT)
    gd = grad.load()
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        for x in range(size):
            gd[x, y] = (r, g, b)
    # 둥근 모서리 마스크
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    radius = int(size * 0.26)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)
    # 흰색 마크
    d = ImageDraw.Draw(img)
    cell = size * 0.064
    offx = (size - cell * COLS) / 2
    offy = (size - cell * ROWS) / 2
    for r, row in enumerate(GRID):
        for c, ch in enumerate(row):
            if ch == "1":
                x0 = offx + c * cell
                y0 = offy + r * cell
                d.rectangle([x0, y0, x0 + cell, y0 + cell], fill=WHITE)
    return img


def make_svg():
    cell = 8
    offx = (100 - cell * COLS) / 2
    offy = (100 - cell * ROWS) / 2
    rects = []
    for r, row in enumerate(GRID):
        for c, ch in enumerate(row):
            if ch == "1":
                rects.append(
                    f'<rect x="{offx + c*cell:.0f}" y="{offy + r*cell:.0f}" '
                    f'width="{cell}" height="{cell}" fill="#fff"/>'
                )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#3b1378"/>
      <stop offset="1" stop-color="#1a0740"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="100" height="100" rx="26" fill="url(#bg)"/>
  {''.join(rects)}
</svg>
'''
    with open(os.path.join(STATIC, "logo.svg"), "w", encoding="utf-8") as f:
        f.write(svg)


def from_source(src):
    """사용자가 제공한 원본 로고 이미지를 그대로 사용 (수정 없이 정확히 일치)."""
    import base64
    img = Image.open(src).convert("RGBA")
    img.resize((512, 512), Image.LANCZOS).save(os.path.join(STATIC, "logo.png"))
    img.resize((256, 256), Image.LANCZOS).save(
        os.path.join(BASE, "app.ico"),
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    buf = io.BytesIO()
    img.resize((256, 256), Image.LANCZOS).save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">'
           f'<image width="100" height="100" href="data:image/png;base64,{b64}"/></svg>')
    with open(os.path.join(STATIC, "logo.svg"), "w", encoding="utf-8") as f:
        f.write(svg)
    print("원본 로고 그대로 적용: static/logo_source.png → logo.png / logo.svg / app.ico")


if __name__ == "__main__":
    # static/logo_source.png 가 있으면 그 파일을 그대로 로고로 사용, 없으면 격자 생성
    src = os.path.join(STATIC, "logo_source.png")
    if os.path.exists(src):
        from_source(src)
    else:
        draw(1024).save(os.path.join(STATIC, "logo.png"))
        make_svg()
        draw(256).save(os.path.join(BASE, "app.ico"),
                       sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        print("생성 완료(격자): static/logo.svg, static/logo.png, app.ico")
