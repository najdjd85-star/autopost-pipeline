"""레시피 조리 순서별 참고 이미지를 fal.ai Flux(schnell)로 만든다(개발용 도구). 장당 $0.003(1메가픽셀 이하 기준).

순서 글에서 '동작'(썰기·볶기·끓이기…)과 그 단계에 나오는 재료를 찾아 영어 프롬프트를 자동으로 만든다.
결과는 site_d/stepimgs/<슬러그>-<순서번호>.jpg 에 저장하고, 프롬프트는 prompts.json 에 남긴다(다시 만들 때 참고).

사용:
  venv/Scripts/python.exe site_d/tools/make_step_images.py --only kimchi-fried-rice:2,spicy-pork:1   (골라서)
  venv/Scripts/python.exe site_d/tools/make_step_images.py --all                                  (아직 없는 것 전부)
  venv/Scripts/python.exe site_d/tools/make_step_images.py --redo tteokbokki:2 --seed 11            (마음에 안 드는 장만 다시)
  venv/Scripts/python.exe site_d/tools/make_step_images.py --sheets <폴더>                           (확인용 시트)
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from recipes_data import ALIASES, RECIPES, STAPLES  # noqa: E402

OUT = HERE / "stepimgs"
FAL_URL = "https://fal.run/fal-ai/flux/schnell"

ING_EN = {
    "밥": "cooked rice", "김치": "kimchi", "계란": "eggs", "대파": "green onions", "양파": "onion", "감자": "potatoes", "당근": "carrot",
    "애호박": "zucchini", "콩나물": "bean sprouts", "시금치": "spinach", "오이": "cucumber", "토마토": "tomatoes", "양배추": "cabbage",
    "무": "Korean radish", "두부": "tofu", "순두부": "soft tofu", "돼지고기": "pork", "소고기": "beef", "닭": "chicken pieces",
    "햄": "sliced canned ham", "참치캔": "canned tuna", "어묵": "fish cake", "멸치": "dried anchovies", "미역": "seaweed", "떡": "rice cakes",
    "만두": "dumplings", "식빵": "bread slices", "소면": "thin wheat noodles", "라면": "instant ramen noodles", "마요네즈": "mayonnaise",
    "김": "seasoned laver", "부침가루": "pancake flour", "고추장": "red chili paste", "된장": "soybean paste", "식용유": "cooking oil",
    "참기름": "sesame oil", "설탕": "sugar", "간장": "soy sauce", "고춧가루": "red chili powder", "다진마늘": "minced garlic",
    "통깨": "sesame seeds", "식초": "vinegar", "소금": "salt", "후추": "pepper",
}
DISH_EN = {
    "kimchi-fried-rice": "kimchi fried rice", "soy-egg-rice": "egg rice bowl with soy sauce", "tuna-kimchi-stew": "kimchi stew with tuna",
    "rolled-omelet": "Korean rolled omelet", "steamed-egg": "Korean steamed egg", "tuna-mayo-bowl": "tuna mayo rice bowl",
    "braised-tofu": "braised tofu in red sauce", "doenjang-stew": "soybean paste stew", "egg-ramen": "ramen with egg",
    "stir-fried-potato": "stir-fried potato strips", "potato-pancake": "potato pancake", "zucchini-jeon": "zucchini egg pancakes",
    "stir-fried-zucchini": "stir-fried zucchini", "bean-sprout-soup": "bean sprout soup", "seasoned-bean-sprouts": "seasoned bean sprouts",
    "seasoned-spinach": "seasoned spinach", "beef-seaweed-soup": "beef seaweed soup", "spicy-pork": "spicy stir-fried pork",
    "pork-kimchi-stir-fry": "stir-fried pork and kimchi", "dakdoritang": "spicy braised chicken", "fish-cake-stir-fry": "stir-fried fish cake",
    "fish-cake-soup": "fish cake soup", "bibim-noodles": "spicy cold noodles", "janchi-noodles": "warm banquet noodles",
    "tteokbokki": "tteokbokki", "spam-egg-rice": "ham and fried egg over rice", "ham-fried-rice": "ham vegetable fried rice",
    "tomato-egg": "tomato and egg stir-fry", "cucumber-salad": "seasoned cucumber salad", "tofu-kimchi": "tofu with stir-fried kimchi",
    "egg-toast": "Korean egg toast", "soft-tofu-stew": "soft tofu stew", "dumpling-soup": "dumpling soup",
}
# (한글 정규식, 영어 장면). 앞에서부터 처음 맞는 것을 쓴다.
ACTIONS = [
    (r"마무리|올립니다|올려|담습니다|담아|접시에|그릇에 담", "the finished {dish} served in a bowl, steam rising"),
    (r"데쳐|데칩니다|삶", "boiling {ings} in a pot of water"),
    (r"불려|담가|불린", "soaking {ings} in water in a bowl"),
    (r"끓", "{ings} simmering in a pot"),
    (r"졸", "{ings} simmering in a thick red sauce in a pan"),
    (r"볶", "stir-frying {ings} in a pan"),
    (r"굽|부칩니다|부쳐|부치", "pan-frying {ings} in a skillet"),
    (r"섞|무치|무칩|버무|풀어|풉니다|재웁", "mixing {ings} in a bowl"),
    (r"썰|썹니다|다집니다|다져|송송|채 썰", "chopping {ings} on a wooden cutting board with a knife"),
    (r"돌려|전자레인지", "cooking {ings} in a microwave-safe bowl"),
]


def ingredients_in(step: str, recipe: dict) -> list:
    found = []
    for i in recipe["ingredients"]:
        names = ALIASES.get(i["n"], [i["n"]]) + [i["n"]]
        if any(len(n) >= 2 and n in step for n in names) or (i["n"] in ("밥", "무", "김", "떡") and re.search(rf"(^|\s){i['n']}[을를은는이가에]?(\s|$)", step)):
            if i["n"] not in STAPLES:  # 양념은 장면에 넣지 않는다(재료가 없으면 요리 이름으로 대체)
                found.append(ING_EN.get(i["n"], i["n"]))
    return found[:3]


def prompt_for(recipe: dict, step: str) -> str:
    dish = DISH_EN[recipe["slug"]]
    ings = ", ".join(ingredients_in(step, recipe)) or dish
    scene = f"preparing {ings}"
    for pat, tmpl in ACTIONS:
        if re.search(pat, step):
            scene = tmpl.format(ings=ings, dish=dish)
            break
    return f"{scene}, Korean home cooking, close-up overhead food photography, warm natural light, wooden table, realistic, no text, no people"


def generate(prompt: str, seed: int) -> bytes:
    r = requests.post(
        FAL_URL,
        headers={"Authorization": f"Key {settings.fal_api_key}", "Content-Type": "application/json"},
        json={"prompt": prompt, "image_size": {"width": 768, "height": 512}, "num_images": 1, "num_inference_steps": 4, "seed": seed, "enable_safety_checker": True},
        timeout=60,
    )
    r.raise_for_status()
    url = r.json()["images"][0]["url"]
    return requests.get(url, timeout=60).content


def save(slug: str, idx: int, prompt: str, seed: int) -> None:
    raw = generate(prompt, seed)
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((640, 640))
    im.save(OUT / f"{slug}-{idx}.jpg", quality=80, optimize=True)


def sheets(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 13)
    files = sorted(OUT.glob("*.jpg"), key=lambda p: (p.stem.rsplit("-", 1)[0], int(p.stem.rsplit("-", 1)[1])))
    per, cols, tw, th = 24, 6, 230, 154
    for s in range(0, len(files), per):
        chunk = files[s:s + per]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (tw + 4), rows * (th + 20)), "white")
        d = ImageDraw.Draw(sheet)
        for i, f in enumerate(chunk):
            x, y = (i % cols) * (tw + 4), (i // cols) * (th + 20)
            im = Image.open(f).convert("RGB")
            im.thumbnail((tw, th))
            sheet.paste(im, (x, y + 18))
            d.text((x + 2, y + 1), f.stem, fill="black", font=font)
        sheet.save(outdir / f"steps_{s // per + 1}.jpg", quality=80)
    print("시트", (len(files) + per - 1) // per, "장 저장:", outdir)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    args = sys.argv[1:]
    if "--sheets" in args:
        sheets(Path(args[args.index("--sheets") + 1]))
        return
    if not settings.fal_api_key:
        raise SystemExit("FAL_API_KEY 가 .env 에 없습니다.")
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else 7
    by_slug = {r["slug"]: r for r in RECIPES}
    jobs = []
    if "--all" in args:
        jobs = [(r["slug"], i + 1) for r in RECIPES for i in range(len(r["steps"])) if not (OUT / f"{r['slug']}-{i + 1}.jpg").exists()]
    for flag in ("--only", "--redo"):
        if flag in args:
            for part in args[args.index(flag) + 1].split(","):
                slug, n = part.split(":")
                jobs.append((slug, int(n)))
    pf = OUT / "prompts.json"
    prompts = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}
    done = 0
    for slug, n in jobs:
        r = by_slug[slug]
        p = prompt_for(r, r["steps"][n - 1])
        try:
            save(slug, n, p, seed)
            prompts[f"{slug}-{n}"] = {"prompt": p, "seed": seed}
            done += 1
            print(f"{slug}-{n}: {p[:90]}")
        except Exception as exc:  # noqa: BLE001
            print(f"{slug}-{n}: 실패 {exc}")
        time.sleep(0.3)
    pf.write_text(json.dumps(prompts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"완료 {done}/{len(jobs)}장 (약 ${done * 0.003:.3f})")


if __name__ == "__main__":
    main()
