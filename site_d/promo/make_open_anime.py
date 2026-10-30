"""홍보 영상 오프닝용 애니풍 이미지 2장(재료 버리는 장면 / 절망하는 캐릭터)을 사이트 캐릭터(냉장고 요리사)를 참고해서 fal.ai Flux Kontext 로 만든다(장당 약 $0.04).

사용: venv/Scripts/python.exe -X utf8 site_d/promo/make_open_anime.py [--seed 1]
결과: site_d/promo/out/screens/anime_throw.png, anime_despair.png (영상 오프닝에서 쓴다)
"""
from __future__ import annotations

import argparse
import base64
import io
import sys
from pathlib import Path

import requests
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402

OUT = HERE / "out" / "screens"
MASCOT = HERE.parent / "static" / "mascot" / "open.png"
STYLE = ("cute flat cartoon illustration, thick dark outlines, pastel colors, sticker style, same character design, vertical 9:16 composition, "
         "clean cream background, no text, no watermark")
PROMPTS = {
    "anime_throw": ("Redraw the same cute refrigerator chef character (with the chef hat), now angrily hurling a bunch of wilted limp brown vegetables "
                    "(droopy green onion, shriveled carrot, soggy lettuce) into a trash can, motion lines, flying vegetables, dramatic energetic pose, " + STYLE),
    "anime_despair": ("Redraw the same cute refrigerator chef character (with the chef hat) in total despair: huge sad eyes with streaming tears, blue gloom lines on the face, "
                      "sweat drops, mouth wobbling, holding a limp wilted vegetable in one hand, hunched over, " + STYLE),
}


def data_uri() -> str:
    im = Image.open(MASCOT).convert("RGBA")
    bg = Image.new("RGBA", im.size, (250, 248, 244, 255))
    bg.alpha_composite(im)
    buf = io.BytesIO()
    bg.convert("RGB").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def make(name: str, prompt: str, seed: int, uri: str) -> Path:
    r = requests.post(
        "https://fal.run/fal-ai/flux-pro/kontext",
        headers={"Authorization": f"Key {settings.fal_api_key}", "Content-Type": "application/json"},
        json={"prompt": prompt, "image_url": uri, "aspect_ratio": "9:16", "seed": seed, "output_format": "png", "safety_tolerance": "2"},
        timeout=180,
    )
    if r.status_code != 200:
        raise SystemExit(f"{name} 실패: {r.status_code} {r.text[:300]}")
    img = Image.open(io.BytesIO(requests.get(r.json()["images"][0]["url"], timeout=120).content)).convert("RGB")
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}_{seed}.png"
    img.save(p)
    print(p, img.size)
    return p


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    uri = data_uri()
    for n, pr in PROMPTS.items():
        make(n, pr, a.seed, uri)
