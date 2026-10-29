"""홍보 샘플 10건(카드뉴스 5 + 쇼츠 5)을 site_d/promo/out/sample/ 에 만든다(무료, 내 PC).

사용: venv/Scripts/python.exe -X utf8 site_d/promo/make_samples.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402

import posts as P  # noqa: E402

OUT = Path(__file__).resolve().parent / "out" / "sample"


def save_card(name: str, slides, caps: dict) -> None:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    for i, im in enumerate(slides, 1):
        im.save(d / f"{i:02d}.png", optimize=True)
    write_caps(d, caps)
    sheet(d, slides)
    print("카드뉴스", name, len(slides), "장")


def save_short(name: str, slides, caps: dict) -> None:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    durs = []
    for i, _ in enumerate(slides):
        durs.append(2.4 if i == 0 else (2.6 if i == len(slides) - 1 else 3.6))
    P.make_video(slides, durs, d / "video.mp4")
    write_caps(d, caps)
    print("쇼츠", name, f"{sum(durs) - 0.4 * (len(slides) - 1):.1f}초")


def write_caps(d: Path, caps: dict) -> None:
    txt = ""
    for k, v in caps.items():
        txt += f"===== {k} =====\n{v}\n\n"
    (d / "captions.txt").write_text(txt, encoding="utf-8")


def sheet(d: Path, slides) -> None:
    w = 270
    h = int(w * slides[0].height / slides[0].width)
    s = Image.new("RGB", (w * len(slides) + 12 * (len(slides) + 1), h + 24), (225, 220, 212))
    for i, im in enumerate(slides):
        s.paste(im.resize((w, h), Image.LANCZOS), (12 + i * (w + 12), 12))
    s.save(d / "_sheet.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tslugs, tdate = P.trending(3)
    save_card("01_card_top3", P.scenes_top3(P.CARD, True), P.captions_top3(tslugs, tdate))
    save_short("02_short_top3", P.scenes_top3(P.SHORT, False), P.captions_top3(tslugs, tdate))
    for n, slug in ((3, "kimchi-jjigae"), (5, "carbonara"), (9, "tteokbokki")):
        save_card(f"{n:02d}_card_{slug}", P.scenes_recipe(slug, P.CARD, True), P.captions_recipe(slug))
    for n, slug in ((4, "kimchi-jjigae"), (6, "dakgalbi"), (10, "kimbap")):
        save_short(f"{n:02d}_short_{slug}", P.scenes_recipe(slug, P.SHORT, False), P.captions_recipe(slug))
    foods = ["계란", "김치"]
    sl, slugs = P.scenes_combo(foods, P.CARD, True)
    save_card("07_card_combo_egg_kimchi", sl, P.captions_combo(foods, slugs))
    sl, slugs = P.scenes_combo(foods, P.SHORT, False)
    save_short("08_short_combo_egg_kimchi", sl, P.captions_combo(foods, slugs))


if __name__ == "__main__":
    main()
