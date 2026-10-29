"""홍보용 카드뉴스(1080x1350)와 세로 영상 장면(1080x1920)을 그리는 모듈. 전부 내 PC에서 무료로 만든다(Pillow).

사이트 데이터(레시피·사진·영양·인기 순위)와 캐릭터를 그대로 써서 사이트와 같은 색·글꼴로 찍는다.
같은 함수가 (W, H) 를 받아 카드뉴스와 쇼츠 장면을 모두 그린다.
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent.parent          # site_d
sys.path.insert(0, str(HERE))

from nutrition_data import compute  # noqa: E402
from recipes_data import RECIPES, STAPLES  # noqa: E402

BY_SLUG = {r["slug"]: r for r in RECIPES}
MASCOT = HERE / "static" / "mascot"
FONT_PATH = "C:/Windows/Fonts/NotoSansKR-VF.ttf"
SITE_URL = "cook.dailyfixpoint.com"
BRAND = "냉장고 파먹기"

BG = (250, 248, 244)
INK = (31, 27, 24)
ACC = (224, 84, 10)
ACC_SOFT = (253, 240, 230)
MUT = (133, 124, 115)
LINE = (235, 229, 220)
WHITE = (255, 255, 255)
CHIP = (243, 238, 231)


@lru_cache(maxsize=64)
def font(size: int, wght: int = 500) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT_PATH, size)
    try:
        f.set_variation_by_axes([wght])
    except Exception:  # noqa: BLE001 - 가변 글꼴이 아니면 기본 굵기
        pass
    return f


# ----------------------------------------------------------------- 사진
def load_photos() -> dict:
    cc = json.loads((HERE / "photos.json").read_text(encoding="utf-8"))
    photos = {k: dict(v, dir="photos") for k, v in cc.items()}
    for f in sorted((HERE / "photos_ai").glob("*.jpg")):
        if not f.name.startswith("_") and f.stem not in photos:
            photos[f.stem] = {"file": f.name, "dir": "photos_ai", "ai": True}
    return photos


PHOTOS = load_photos()


def photo_of(slug: str) -> Optional[Image.Image]:
    p = PHOTOS.get(slug)
    return Image.open(HERE / p["dir"] / p["file"]).convert("RGB") if p else None


def credit_of(slug: str) -> str:
    p = PHOTOS.get(slug) or {}
    if p.get("ai") or not p:
        return "AI로 만든 참고 이미지"
    return f'사진: {p.get("artist", "")} · {p.get("license", "")}'


def fill(img: Image.Image, w: int, h: int) -> Image.Image:
    """가로세로 비율을 맞춰 꽉 채워 자른다."""
    r = max(w / img.width, h / img.height)
    im = img.resize((int(img.width * r) + 1, int(img.height * r) + 1), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def rounded(img: Image.Image, radius: int) -> Image.Image:
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius, fill=255)
    img.putalpha(mask)
    return img


# ----------------------------------------------------------------- 글자
def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, width: int) -> List[str]:
    """단어 단위로 줄바꿈하고, 한 단어가 너무 길면 글자 단위로 자른다."""
    lines, cur = [], ""
    for word in text.split(" "):
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = ""
        for ch in word:
            if draw.textlength(cur + ch, font=fnt) <= width:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
    if cur:
        lines.append(cur)
    return lines


def text_block(draw, xy, text, fnt, fill_, width, line_gap=1.35) -> int:
    """줄바꿈해서 그리고 끝난 y 를 돌려준다."""
    x, y = xy
    for ln in wrap(draw, text, fnt, width):
        draw.text((x, y), ln, font=fnt, fill=fill_)
        y += int(fnt.size * line_gap)
    return y


def block_height(draw, text, fnt, width, line_gap=1.35) -> int:
    return len(wrap(draw, text, fnt, width)) * int(fnt.size * line_gap)


def pill(draw, xy, text, fnt, fg, bg, pad=(28, 14)) -> tuple:
    x, y = xy
    w = int(draw.textlength(text, font=fnt)) + pad[0] * 2
    h = fnt.size + pad[1] * 2
    draw.rounded_rectangle((x, y, x + w, y + h), h // 2, fill=bg)
    draw.text((x + pad[0], y + pad[1] - 2), text, font=fnt, fill=fg)
    return x + w, y + h


# ----------------------------------------------------------------- 공통 틀
M = 72  # 가장자리 여백


def base(W: int, H: int, page: Optional[tuple] = None, header: bool = True) -> tuple:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    if header:
        face = Image.open(MASCOT / "face.png").convert("RGBA").resize((60, 60), Image.LANCZOS)
        top = 70 if H > 1500 else 54
        img.paste(face, (M, top), face)
        d.text((M + 76, top + 8), BRAND, font=font(34, 800), fill=INK)
        if page:
            t = f"{page[0]} / {page[1]}"
            d.text((W - M - d.textlength(t, font=font(30, 600)), top + 12), t, font=font(30, 600), fill=MUT)
    return img, d


def footer(d, W, H, text: str = None, credit: str = ""):
    if credit:
        d.text((M, H - 70), credit, font=font(24, 400), fill=MUT)
    t = text or SITE_URL
    d.text((W - M - d.textlength(t, font=font(28, 600)), H - 72), t, font=font(28, 600), fill=MUT)


def paste_round(img, pic, xy, size, radius=40):
    pic = rounded(fill(pic, *size), radius)
    img.paste(pic, xy, pic)


def collage(img, pics: List[Image.Image], xy, size, gap=16, radius=36):
    """사진 1~3장을 한 영역에 배치한다."""
    x, y = xy
    w, h = size
    if len(pics) == 1:
        paste_round(img, pics[0], xy, size, radius)
    elif len(pics) == 2:
        pw = (w - gap) // 2
        for i, p in enumerate(pics):
            paste_round(img, p, (x + i * (pw + gap), y), (pw, h), radius)
    else:
        lw = int(w * 0.58)
        paste_round(img, pics[0], xy, (lw, h), radius)
        rh = (h - gap) // 2
        paste_round(img, pics[1], (x + lw + gap, y), (w - lw - gap, rh), radius)
        paste_round(img, pics[2], (x + lw + gap, y + rh + gap), (w - lw - gap, h - rh - gap), radius)


# ----------------------------------------------------------------- 장면(슬라이드)
def cover(W, H, kicker, title, sub, slugs, page=None, hint="넘겨서 보기  →"):
    img, d = base(W, H, page)
    top = 190 if H < 1500 else 230
    ph = int(H * (0.42 if H < 1500 else 0.36))
    pics = [p for p in (photo_of(s) for s in slugs[:3]) if p]
    if pics:
        collage(img, pics, (M, top), (W - 2 * M, ph))
    y = top + ph + 56
    y = pill(d, (M, y), kicker, font(36, 700), ACC, ACC_SOFT)[1] + 34
    f = font(96 if H < 1500 else 108, 800)
    y = text_block(d, (M, y), title, f, INK, W - 2 * M, 1.22)
    y += 14
    text_block(d, (M, y), sub, font(40, 500), MUT, W - 2 * M, 1.45)
    d.text((M, H - 118), hint, font=font(36, 700), fill=ACC)
    footer(d, W, H, credit=credit_of(slugs[0]) if len(slugs) == 1 and pics else "")
    return img


def rank_item(W, H, rank, slug, page=None, caption=""):
    r = BY_SLUG[slug]
    img, d = base(W, H, page)
    top = 190 if H < 1500 else 230
    ph = int(H * (0.44 if H < 1500 else 0.40))
    pic = photo_of(slug)
    if pic:
        paste_round(img, pic, (M, top), (W - 2 * M, ph), 44)
    cx, cy = M + 70, top + ph
    d.ellipse((cx - 70, cy - 70, cx + 70, cy + 70), fill=INK)
    d.text((cx, cy - 4), str(rank), font=font(86, 800), fill=WHITE, anchor="mm")
    y = top + ph + 120
    y = text_block(d, (M, y), r["name"], font(104, 800), INK, W - 2 * M, 1.2) + 4
    per = compute(slug)["per"]
    d.text((M, y), f'{r["minutes"]}분 · {r["level"]} · 1인분 {per["kcal"]}kcal', font=font(40, 600), fill=ACC)
    y += 72
    foods = [i["n"] for i in r["ingredients"] if not i["opt"] and i["n"] not in STAPLES and i["n"] != "물"]
    text_block(d, (M, y), "재료  " + " · ".join(foods[:6]), font(38, 500), MUT, W - 2 * M, 1.5)
    footer(d, W, H, credit=credit_of(slug))
    return img


def ingredients_slide(W, H, slug, page=None):
    r = BY_SLUG[slug]
    img, d = base(W, H, page)
    y = 200 if H < 1500 else 250
    d.text((M, y), "재료", font=font(88, 800), fill=INK)
    d.text((M + 190, y + 40), f'{r["servings"]}인분 기준', font=font(38, 600), fill=ACC)
    y += 150
    items = [i for i in r["ingredients"] if i["n"] != "물" or True]
    row = 88 if H < 1500 else 92
    cap = max(5, (H - 190 - y - 24) // row)  # 아래 안내문과 겹치지 않는 만큼만
    shown = items[:cap]
    d.rounded_rectangle((M, y, W - M, y + row * len(shown) + 24), 36, fill=WHITE, outline=LINE, width=2)
    yy = y + 12
    for i in shown:
        name = i["n"] + (" (선택)" if i["opt"] else "")
        q = i["q"].split("(")[0].strip() or i["q"]
        d.text((M + 40, yy + 20), name, font=font(42, 700), fill=INK)
        d.text((W - M - 40, yy + 22), q, font=font(40, 500), fill=ACC, anchor="ra")
        yy += row
        if i is not shown[-1]:
            d.line((M + 40, yy, W - M - 40, yy), fill=LINE, width=2)
    if len(items) > cap:
        d.text((M, yy + 40), f"외 {len(items) - cap}가지는 사이트에서 확인", font=font(34, 600), fill=MUT)
    d.text((M, H - 118), "1컵 200ml · 1큰술 15ml · 1작은술 5ml 기준", font=font(30, 500), fill=MUT)
    footer(d, W, H)
    return img


def steps_slides(W, H, slug, start_page=1, total=None) -> List[Image.Image]:
    """조리 순서를 한 장에 들어갈 만큼씩 나눠 여러 장으로 만든다."""
    r = BY_SLUG[slug]
    avail_top = 210 if H < 1500 else 260
    avail = H - avail_top - 170
    probe = ImageDraw.Draw(Image.new("RGB", (W, 10)))
    f = font(42, 500)
    tw = W - 2 * M - 120
    pages, cur, used = [], [], 0
    for n, st in enumerate(r["steps"], 1):
        hgt = block_height(probe, st, f, tw, 1.42) + 56
        if cur and used + hgt > avail:
            pages.append(cur)
            cur, used = [], 0
        cur.append((n, st))
        used += hgt
    if cur:
        pages.append(cur)
    out = []
    for k, group in enumerate(pages):
        page = (start_page + k, total) if total else None
        img, d = base(W, H, page)
        y = avail_top - 40
        d.text((M, y), "만드는 순서", font=font(60, 800), fill=INK)
        y += 120
        for n, st in group:
            d.ellipse((M, y, M + 76, y + 76), fill=INK)
            d.text((M + 38, y + 36), str(n), font=font(40, 800), fill=WHITE, anchor="mm")
            yy = text_block(d, (M + 110, y + 2), st, f, INK, tw, 1.42)
            y = max(yy, y + 76) + 40
        footer(d, W, H)
        out.append(img)
    return out


def info_slide(W, H, slug, page=None):
    r = BY_SLUG[slug]
    per = compute(slug)["per"]
    img, d = base(W, H, page)
    y = 200 if H < 1500 else 250
    d.text((M, y), "한눈에 보기", font=font(80, 800), fill=INK)
    y += 140
    stats = [("열량", f'{per["kcal"]}', "kcal"), ("단백질", f'{per["protein"]}', "g"), ("나트륨", f'{per["sodium"]:,}', "mg")]
    bw = (W - 2 * M - 2 * 24) // 3
    for i, (lab, val, unit) in enumerate(stats):
        x = M + i * (bw + 24)
        d.rounded_rectangle((x, y, x + bw, y + 230), 32, fill=WHITE, outline=LINE, width=2)
        d.text((x + bw // 2, y + 52), lab, font=font(32, 600), fill=MUT, anchor="ma")
        d.text((x + bw // 2, y + 112), val, font=font(60 if len(val) < 5 else 50, 800), fill=INK, anchor="ma")
        d.text((x + bw // 2, y + 182), unit, font=font(30, 600), fill=ACC, anchor="ma")
    y += 230 + 24
    d.text((M, y), "1인분 기준 · 식품성분표 평균 기반 추정치", font=font(28, 500), fill=MUT)
    y += 90
    d.text((M, y), "요리 팁", font=font(52, 800), fill=INK)
    y += 90
    for tip in r["tips"][:2]:
        d.rounded_rectangle((M, y, W - M, y + 24), 0, fill=BG)
        yy = text_block(d, (M + 36, y), "· " + tip, font(40, 500), INK, W - 2 * M - 40, 1.45)
        y = yy + 22
    footer(d, W, H)
    return img


def outro(W, H, line1="냉장고에 있는 재료로", line2="오늘 뭐 해 먹지?", page=None):
    img, d = base(W, H, page)
    mh = int(H * 0.34)
    m = Image.open(MASCOT / "open.png").convert("RGBA")
    m = m.resize((int(m.width * mh / m.height), mh), Image.LANCZOS)
    top = 220 if H < 1500 else 300
    img.paste(m, ((W - m.width) // 2, top), m)
    y = top + mh + 50
    for t, f, c in ((line1, font(48, 600), MUT), (line2, font(80, 800), INK)):
        d.text((W // 2, y), t, font=f, fill=c, anchor="ma")
        y += f.size + 18
    y += 20
    t = f"{SITE_URL}"
    f = font(46, 800)
    w = int(d.textlength(t, font=f)) + 80
    d.rounded_rectangle(((W - w) // 2, y, (W + w) // 2, y + 110), 55, fill=INK)
    d.text((W // 2, y + 55), t, font=f, fill=WHITE, anchor="mm")
    d.text((W // 2, y + 150), "재료만 누르면 만들 수 있는 요리가 나와요", font=font(34, 500), fill=MUT, anchor="ma")
    d.text((W // 2, H - 110), "프로필 링크에서 바로 써 보세요", font=font(34, 700), fill=ACC, anchor="ma")
    return img
