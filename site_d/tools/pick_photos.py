"""고른 사진을 내려받아 site_d/photos/ 에 저장하고 출처 정보를 site_d/photos.json 에 적는다.

photo_candidates.py 로 만든 candidates.json 두 개(첫 검색, 재검색)에서 사람이 시트를 보고 고른 번호만 받는다.
실행: venv/Scripts/python.exe site_d/tools/pick_photos.py <첫검색폴더> <재검색폴더>
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent.parent
UA = "FridgeRecipeSite/1.0 (najdjd85@gmail.com)"

# slug -> (후보 묶음 0=첫 검색 1=재검색, 후보 번호). 맞는 사진이 없는 요리는 넣지 않는다(화면에서 아이콘으로 대체).
CHOICES = {
    "kimchi-fried-rice": (0, 0), "soy-egg-rice": (0, 2), "tuna-kimchi-stew": (0, 3), "rolled-omelet": (0, 0),
    "steamed-egg": (0, 0), "braised-tofu": (0, 1), "doenjang-stew": (0, 2), "potato-pancake": (0, 2),
    "bean-sprout-soup": (0, 0), "seasoned-bean-sprouts": (0, 1), "seasoned-spinach": (0, 0),
    "beef-seaweed-soup": (0, 0), "spicy-pork": (0, 2), "dakdoritang": (0, 0), "fish-cake-stir-fry": (0, 1),
    "bibim-noodles": (0, 0), "janchi-noodles": (0, 0), "tteokbokki": (0, 0), "spam-egg-rice": (0, 3),
    "ham-fried-rice": (0, 1), "tomato-egg": (0, 0), "cucumber-salad": (0, 1), "tofu-kimchi": (0, 3),
    "soft-tofu-stew": (0, 0), "dumpling-soup": (0, 2),
    "stir-fried-potato": (1, 1), "pork-kimchi-stir-fry": (1, 2),
}


def main() -> None:
    sets = [json.loads((Path(d) / "candidates.json").read_text(encoding="utf-8")) for d in sys.argv[1:3]]
    out_dir = HERE / "photos"
    out_dir.mkdir(exist_ok=True)
    credits = {}
    for slug, (which, idx) in CHOICES.items():
        c = sets[which][slug][idx]
        req = urllib.request.Request(c["thumb"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            im = Image.open(io.BytesIO(r.read())).convert("RGB")
        im.thumbnail((640, 640))
        im.save(out_dir / f"{slug}.jpg", quality=85, optimize=True)
        credits[slug] = {
            "file": f"{slug}.jpg", "title": c["title"].replace("File:", ""), "page": c["page"], "artist": c["artist"] or "작성자 정보는 원본 페이지 참고",
            "license": c["license"], "license_url": c["license_url"],
        }
        print(slug, im.size, c["license"])
        time.sleep(0.6)
    (HERE / "photos.json").write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")
    print("사진", len(credits), "개 저장")


if __name__ == "__main__":
    main()
