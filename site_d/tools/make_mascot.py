"""캐릭터 시트(site_d/assets_src/mascot_sheet.png)에서 캐릭터를 오려 투명 배경 PNG 로 만든다(개발용 도구).

결과: site_d/static/mascot/  open.png(문 열린 냉장고), face.png(얼굴·모자 아이콘),
      favicon-32.png, favicon-180.png.  빌드가 dist/assets/mascot/ 로 복사한다.
오리는 방법: 캐릭터를 둘러싼 '윤곽선'을 벽으로 보고, 바깥 배경만 투명하게 한다(윤곽선이 막혀 있어야 한다).
사용: venv/Scripts/python.exe site_d/tools/make_mascot.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "assets_src" / "mascot_sheet.png"
OUT = HERE / "static" / "mascot"


def outside_mask(wall: np.ndarray) -> np.ndarray:
    """가장자리에서 시작해 벽을 넘지 않고 닿는 모든 칸(= 캐릭터 바깥)."""
    out = np.zeros_like(wall, dtype=bool)
    out[0, :], out[-1, :], out[:, 0], out[:, -1] = True, True, True, True
    out &= ~wall
    while True:
        grow = out.copy()
        grow[1:, :] |= out[:-1, :]
        grow[:-1, :] |= out[1:, :]
        grow[:, 1:] |= out[:, :-1]
        grow[:, :-1] |= out[:, 1:]
        grow &= ~wall
        if (grow == out).all():
            return out
        out = grow


def dilate(m: np.ndarray, n: int = 1) -> np.ndarray:
    for _ in range(n):
        g = m.copy()
        g[1:, :] |= m[:-1, :]
        g[:-1, :] |= m[1:, :]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        m = g
    return m


def largest_component(mask: np.ndarray) -> np.ndarray:
    """가장 큰 덩어리만 남긴다(바깥 배경에서 떨어져 나온 조각 제거)."""
    seen = np.zeros_like(mask, dtype=bool)
    best = None
    h, w = mask.shape
    for y in range(h):
        for x in range(w):
            if mask[y, x] and not seen[y, x]:
                comp = np.zeros_like(mask)
                stack = [(y, x)]
                seen[y, x] = comp[y, x] = True
                while stack:
                    cy, cx = stack.pop()
                    for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = comp[ny, nx] = True
                            stack.append((ny, nx))
                if best is None or comp.sum() > best.sum():
                    best = comp
    return best if best is not None else mask


def cut(im: Image.Image, box: tuple, wall_kind: str) -> Image.Image:
    c = im.crop(box).convert("RGB")
    a = np.asarray(c).astype(int)
    lum = (a[..., 0] * 299 + a[..., 1] * 587 + a[..., 2] * 114) // 1000
    if wall_kind == "white":      # 흰 스티커 윤곽선이 있는 캐릭터
        wall = (a.min(axis=2) >= 250)
        wall = dilate(wall, 1)
    else:                          # 짙은 갈색 윤곽선이 있는 캐릭터
        wall = dilate(lum < 140, 1)
    keep = largest_component(~outside_mask(wall))
    # 가장자리의 배경색 테두리(밝은 픽셀)는 한두 겹 벗겨 낸다
    for _ in range(2):
        edge = keep & ~(np.roll(keep, 1, 0) & np.roll(keep, -1, 0) & np.roll(keep, 1, 1) & np.roll(keep, -1, 1))
        if wall_kind == "dark":
            keep &= ~(edge & (lum > 150))
    rgba = np.dstack([np.asarray(c), (keep * 255).astype(np.uint8)])
    out = Image.fromarray(rgba)
    bbox = out.getchannel("A").getbbox()
    return out.crop(bbox)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    im = Image.open(SRC)
    # 문 열린 캐릭터만 쓴다(사과 먹는 캐릭터는 시트에서 오른쪽이 다른 캐릭터에 가려져 있어 깨끗하게 오릴 수 없다)
    opened = cut(im, (440, 92, 1000, 700), "white")
    r = opened.copy()
    r.thumbnail((840, 420))
    r.save(OUT / "open.png", optimize=True)
    print("open", r.size)
    # 얼굴 아이콘: 모자+얼굴(위 칸). 주걱 쪽은 뺀다
    w, hgt = opened.size
    face = opened.crop((int(w * 0.275), int(hgt * 0.02), int(w * 0.80), int(hgt * 0.455)))
    side = max(face.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(face, ((side - face.width) // 2, (side - face.height) // 2), face)
    for n in (32, 180):
        sq.resize((n, n), Image.LANCZOS).save(OUT / f"favicon-{n}.png", optimize=True)
    sq.resize((96, 96), Image.LANCZOS).save(OUT / "face.png", optimize=True)
    print("저장:", OUT)


if __name__ == "__main__":
    main()
