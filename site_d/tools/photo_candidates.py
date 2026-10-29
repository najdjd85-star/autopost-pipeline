"""레시피 사진 후보를 위키미디어 커먼즈에서 모아 비교용 시트를 만든다(개발용 도구, 사이트 빌드에는 쓰이지 않음).

각 레시피마다 검색어로 후보를 4장 받아 작은 썸네일 시트를 만든다. 사람이 시트를 보고 맞는 사진을 고른 뒤
site_d/photos.json 에 파일명을 적고 pick_photos.py 로 내려받는다.
실행: venv/Scripts/python.exe site_d/tools/photo_candidates.py <출력폴더>
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

UA = "FridgeRecipeSite/1.0 (najdjd85@gmail.com)"
API = "https://commons.wikimedia.org/w/api.php"

QUERIES = {
    "kimchi-fried-rice": "kimchi bokkeumbap fried rice",
    "soy-egg-rice": "gyeran bap egg rice soy sauce",
    "tuna-kimchi-stew": "kimchi jjigae",
    "rolled-omelet": "gyeran-mari rolled omelette",
    "steamed-egg": "gyeran-jjim steamed egg",
    "tuna-mayo-bowl": "tuna mayo rice bowl",
    "braised-tofu": "dubu-jorim braised tofu",
    "doenjang-stew": "doenjang-jjigae",
    "egg-ramen": "ramyeon egg",
    "stir-fried-potato": "gamja-bokkeum potato",
    "potato-pancake": "gamja-jeon potato pancake",
    "zucchini-jeon": "hobak-jeon zucchini pancake",
    "stir-fried-zucchini": "stir-fried zucchini namul",
    "bean-sprout-soup": "kongnamul-guk soup",
    "seasoned-bean-sprouts": "kongnamul-muchim",
    "seasoned-spinach": "sigeumchi-namul",
    "beef-seaweed-soup": "miyeokguk seaweed soup",
    "spicy-pork": "jeyuk-bokkeum",
    "pork-kimchi-stir-fry": "kimchi pork stir fry dwaeji",
    "dakdoritang": "dak-bokkeum-tang dakdoritang",
    "fish-cake-stir-fry": "eomuk-bokkeum fish cake",
    "fish-cake-soup": "eomuk-tang odeng",
    "bibim-noodles": "bibim-guksu",
    "janchi-noodles": "janchi-guksu",
    "tteokbokki": "tteokbokki",
    "spam-egg-rice": "spam egg rice",
    "ham-fried-rice": "fried rice ham vegetables",
    "tomato-egg": "tomato egg stir fry",
    "cucumber-salad": "oi-muchim cucumber",
    "tofu-kimchi": "dubu-kimchi",
    "egg-toast": "gilgeori toast egg",
    "soft-tofu-stew": "sundubu-jjigae",
    "dumpling-soup": "mandu-guk dumpling soup",
}

FREE = re.compile(r"^(CC0|Public domain|PD|CC BY|CC-BY|CC BY-SA|CC-BY-SA)", re.I)


def api(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def candidates(query: str, want: int = 4) -> list:
    data = api({
        "action": "query", "generator": "search", "gsrsearch": query + " filetype:bitmap", "gsrnamespace": 6,
        "gsrlimit": 14, "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 640,
    })
    out = []
    for page in sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = clean((meta.get("LicenseShortName") or {}).get("value", ""))
        if info.get("mime") not in ("image/jpeg", "image/png") or info.get("width", 0) < 600 or not FREE.match(lic):
            continue
        out.append({
            "title": page["title"], "thumb": info["thumburl"], "page": info["descriptionurl"], "license": lic,
            "artist": clean((meta.get("Artist") or {}).get("value", ""))[:80],
            "license_url": clean((meta.get("LicenseUrl") or {}).get("value", "")),
        })
        if len(out) >= want:
            break
    return out


def main() -> None:
    outdir = Path(sys.argv[1])
    if len(sys.argv) > 2:  # 검색어를 JSON 파일로 바꿔 일부 레시피만 다시 찾을 때
        QUERIES.clear()
        QUERIES.update(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
    outdir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 14)
    cw, ch = 210, 158
    allc, rows = {}, []
    for slug, q in QUERIES.items():
        try:
            cands = candidates(q)
        except Exception as exc:  # noqa: BLE001
            print(slug, "검색 실패", exc)
            cands = []
        allc[slug] = cands
        thumbs = []
        for c in cands:
            try:
                req = urllib.request.Request(c["thumb"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=40) as r:
                    im = Image.open(io.BytesIO(r.read())).convert("RGB")
                im.thumbnail((cw, ch))
                thumbs.append(im)
            except Exception as exc:  # noqa: BLE001
                print(slug, "썸네일 실패", exc)
                thumbs.append(Image.new("RGB", (cw, ch), "#ccc"))
            time.sleep(0.6)
        rows.append((slug, thumbs))
        print(slug, len(cands), "후보")
        time.sleep(0.5)
    (outdir / "candidates.json").write_text(json.dumps(allc, ensure_ascii=False, indent=1), encoding="utf-8")
    per = 8
    for s in range(0, len(rows), per):
        chunk = rows[s:s + per]
        sheet = Image.new("RGB", (150 + 4 * (cw + 6), len(chunk) * (ch + 6)), "white")
        d = ImageDraw.Draw(sheet)
        for i, (slug, thumbs) in enumerate(chunk):
            y = i * (ch + 6)
            d.text((4, y + 4), slug, fill="black", font=font)
            for j, im in enumerate(thumbs):
                x = 150 + j * (cw + 6)
                sheet.paste(im, (x, y))
                d.rectangle((x, y, x + 20, y + 20), fill="#e8590c")
                d.text((x + 6, y + 2), str(j), fill="white", font=font)
        sheet.save(outdir / f"sheet_{s // per + 1}.jpg", quality=82)
    print("시트 저장:", outdir)


if __name__ == "__main__":
    main()
