"""홍보 영상 오프닝용 AI 이미지(곧 버릴 시든 재료를 쓰레기통에 넣는 장면)를 fal.ai Flux 로 만든다(장당 약 $0.003).

사용: venv/Scripts/python.exe -X utf8 site_d/promo/make_open_image.py [--seed 1] [--n 3]
결과: site_d/promo/out/screens/open_ai_<seed>.png (마음에 드는 것을 open_ai.png 로 복사해서 영상에 쓴다)
"""
from __future__ import annotations

import argparse
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
PROMPT = ("a person's hand dropping a bunch of wilted limp green onions, soggy brown lettuce, shriveled carrots and moldy tomatoes into a kitchen trash bin, "
          "an open refrigerator glowing behind in a dim kitchen, close-up, vertical composition, realistic photograph, cinematic cool lighting, shallow depth of field, "
          "no text, no watermark, no face")


def make(seed: int) -> Path:
    r = requests.post(
        "https://fal.run/fal-ai/flux/schnell",
        headers={"Authorization": f"Key {settings.fal_api_key}", "Content-Type": "application/json"},
        json={"prompt": PROMPT, "image_size": {"width": 720, "height": 1280}, "num_images": 1, "num_inference_steps": 4, "seed": seed, "enable_safety_checker": True},
        timeout=120,
    )
    r.raise_for_status()
    im = Image.open(io.BytesIO(requests.get(r.json()["images"][0]["url"], timeout=120).content)).convert("RGB")
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"open_ai_{seed}.png"
    im.save(p)
    return p


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args()
    for s in range(a.seed, a.seed + a.n):
        print(make(s))
