"""사진이 없는 레시피의 완성 요리 사진을 fal.ai Flux(schnell)로 만든다(개발용 도구). 장당 약 $0.001~0.003(1메가픽셀 이하).

결과는 site_d/photos_ai/<슬러그>.jpg 로 저장한다(깃에 포함: 서버가 빌드할 때 필요). 위키미디어 사진(photos.json)이 있는 레시피는 건너뛴다.
빌드는 이 사진을 'AI로 만든 참고 이미지'라고 밝히며 보여 준다.

사용:
  venv/Scripts/python.exe site_d/tools/make_dish_photos.py --only dakgalbi,carbonara     (골라서)
  venv/Scripts/python.exe site_d/tools/make_dish_photos.py --all                         (아직 없는 것 전부)
  venv/Scripts/python.exe site_d/tools/make_dish_photos.py --redo dakgalbi --seed 7      (마음에 안 드는 것만 다시)
  venv/Scripts/python.exe site_d/tools/make_dish_photos.py --sheet 시트.jpg               (확인용 한 장짜리 시트)
"""
from __future__ import annotations

import argparse
import io
import json
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
from recipes_data import RECIPES  # noqa: E402

OUT = HERE / "photos_ai"
FAL_URL = "https://fal.run/fal-ai/flux/schnell"

# 슬러그 -> 영어로 본 완성 요리 장면(그릇·재료를 구체적으로 적어야 엉뚱한 그림이 덜 나온다)
SCENE = {
    "tuna-mayo-bowl": "a rice bowl topped with canned tuna mixed with mayonnaise, shredded seaweed and sesame seeds, a drizzle of soy sauce",
    "egg-ramen": "a bowl of Korean instant ramen noodles in broth topped with a cracked egg and chopped green onions",
    "zucchini-jeon": "golden pan-fried zucchini slices coated in egg batter on a plate with a small soy dipping sauce",
    "stir-fried-zucchini": "stir-fried sliced zucchini with onion and sesame seeds on a white plate",
    "fish-cake-soup": "a pot of Korean fish cake soup with skewered fish cakes, radish and green onions in clear broth",
    "egg-toast": "a Korean street-style egg toast sandwich with fried egg, cabbage and ketchup on grilled bread, cut in half",
    "egg-fried-rice": "egg fried rice with fluffy scrambled egg and chopped green onions in a white bowl",
    "tuna-kimchi-fried-rice": "kimchi fried rice with tuna in a skillet topped with a fried egg and sesame seeds",
    "spam-mayo-bowl": "a rice bowl with pan-fried spam slices, drizzled mayonnaise, shredded seaweed and sesame seeds",
    "jeyuk-bowl": "a rice bowl topped with spicy stir-fried pork, sliced onions and green onions, sesame seeds",
    "bulgogi-bowl": "a rice bowl topped with marinated Korean beef bulgogi, onions and sesame seeds",
    "bibimbap": "Korean bibimbap in a bowl with rice, assorted colorful vegetable namul, minced beef, a fried egg and red gochujang",
    "omurice": "omurice, a rice omelet with a smooth yellow egg on top and ketchup drizzled over it, on a plate",
    "kimchi-jjigae": "bubbling Korean kimchi stew in a small black pot with pork, tofu and green onions",
    "budae-jjigae": "Korean army base stew in a wide pot with sausages, spam, ramen noodles, tofu, kimchi and cheese, bubbling red broth",
    "egg-drop-soup": "a bowl of Korean egg drop soup with ribbons of egg and green onions in clear broth",
    "kimchi-kongnamul-guk": "a bowl of clear soup with bean sprouts and chopped kimchi and green onions",
    "beef-radish-soup": "a bowl of Korean beef and radish soup with clear light red broth and sliced green onions",
    "tteokguk": "Korean rice cake soup tteokguk in a bowl with sliced oval rice cakes, egg strips and seaweed flakes in clear broth",
    "hobak-gochujang-jjigae": "a Korean zucchini and gochujang stew in a small pot with tofu and green onions",
    "gamja-sujebi": "Korean potato sujebi hand-torn dough soup in a bowl with potato slices and zucchini in clear broth",
    "doenjang-gamja-guk": "a bowl of Korean soybean paste soup with potato slices, onion and green onions",
    "bulgogi": "sizzling Korean beef bulgogi with onions and mushrooms in a pan, garnished with sesame seeds",
    "dwaeji-bulgogi": "Korean spicy marinated pork bulgogi stir-fried with onions and green onions on a plate",
    "dakgalbi": "Korean spicy stir-fried chicken dakgalbi in a large pan with cabbage, sweet potato, rice cakes and red chili sauce",
    "kimchi-jjim": "braised aged kimchi with pork belly slices in a pot, red and glossy",
    "duruchigi": "Korean spicy stir-fried pork with kimchi and bean sprouts in a wide pan, red sauce",
    "beef-veg-bokkeum": "stir-fried beef strips with onions, carrots and bell peppers on a white plate",
    "dak-jorim": "Korean soy-braised chicken pieces glazed in dark soy sauce with green onions on a plate",
    "egg-jangjorim": "Korean soy-braised hard-boiled eggs glossy dark brown in a small dish with green chili slices",
    "dubu-buchim": "pan-fried tofu slices golden brown on a plate with a spoonful of soy scallion sauce",
    "gamja-jorim": "soy-glazed braised baby potatoes shiny in a bowl sprinkled with sesame seeds",
    "myeolchi-bokkeum": "Korean stir-fried small dried anchovies with sesame seeds in a small dish, glossy sweet soy glaze",
    "muu-saengchae": "Korean seasoned shredded radish salad in red chili flakes in a white bowl",
    "buchu-muchim": "Korean seasoned garlic chives salad with red chili flakes and sesame seeds in a bowl",
    "mushroom-bokkeum": "stir-fried assorted mushrooms with garlic and sesame seeds in a pan",
    "cabbage-bokkeum": "stir-fried cabbage with a bit of carrot on a white plate",
    "sausage-veg-bokkeum": "stir-fried sausages with onion, bell pepper and ketchup sauce on a plate",
    "spam-gui": "pan-seared spam slices golden brown arranged on a plate with a fried egg",
    "kimchi-jeon": "crispy Korean kimchi pancake kimchijeon golden brown on a plate with dipping sauce",
    "buchu-jeon": "thin crispy Korean garlic chive pancake on a plate cut into pieces with soy dipping sauce",
    "tuna-jeon": "small round pan-fried tuna and vegetable patties golden brown on a plate",
    "cheese-egg-roll": "a Korean rolled omelet gyeran-mari with melted cheese inside, sliced showing spirals, on a plate",
    "dak-soy-bokkeum": "soy-glazed stir-fried chicken pieces with onions and green onions on a plate",
    "sausage-kimchi-bokkeum": "stir-fried sausages and kimchi in a pan, red and glossy, sesame seeds on top",
    "potato-cheese-bake": "baked potato slices topped with melted golden cheese in a small baking dish",
    "ham-egg-jeon": "slices of ham coated in egg batter, pan-fried golden brown on a plate",
    "kimchi-bibim-guksu": "Korean spicy mixed noodles with chopped kimchi, cucumber strips and half a boiled egg, sesame seeds in a bowl",
    "rabokki": "rabokki with chewy rice cakes, instant ramen noodles, fish cake and boiled egg in thick red spicy sauce in a pan",
    "cheese-ramen": "a bowl of ramen noodles topped with melted yellow cheese slice, egg and green onions",
    "kimchi-ramen": "a bowl of red kimchi ramen noodles with chopped kimchi and a green onion topping",
    "gun-mandu": "pan-fried Korean dumplings gun-mandu golden crispy bottoms on a plate with soy vinegar dipping sauce",
    "kimbap": "Korean kimbap rolls sliced into rounds showing colorful fillings of egg, ham, carrot and cucumber, on a plate",
    "jumeokbap": "round Korean rice balls jumeokbap with seaweed pieces, tuna mayo inside, on a plate",
    "french-toast": "golden French toast slices dusted with sugar on a plate",
    "egg-sandwich": "an egg salad sandwich on white bread cut in half showing creamy egg filling",
    "potato-salad": "creamy Korean-style potato salad with cucumber and carrot pieces in a bowl",
    "egg-porridge": "a bowl of Korean egg porridge juk, soft and creamy with green onions and sesame oil",
    "ham-cheese-toast": "a grilled ham, cheese and fried egg toast sandwich cut in half, melted cheese",
    "tofu-salad": "a fresh tofu salad with cubes of tofu, tomatoes, cucumber and sesame dressing in a bowl",
    "chicken-breast-salad": "a chicken breast salad with shredded chicken, cabbage, tomato and cucumber with sesame dressing in a bowl",
    "tofu-steak": "pan-seared tofu steaks glazed with soy sauce glaze on a plate with a few vegetables",
    "cabbage-egg-bokkeum": "stir-fried cabbage and soft scrambled eggs on a white plate",
    "dak-breast-soy-bokkeum": "soy-glazed stir-fried sliced chicken breast with onion and bell pepper on a plate",
    "tomato-spaghetti": "spaghetti with tomato sauce and bacon on a white plate, twirled, parsley on top",
    "cream-spaghetti": "creamy white sauce spaghetti with bacon pieces on a plate, black pepper on top",
    "aglio-olio": "spaghetti aglio e olio with golden garlic slices, chili and shrimp in glossy olive oil on a plate",
    "carbonara": "spaghetti carbonara with crispy bacon, creamy egg sauce and lots of black pepper on a plate",
    "tortilla-pizza": "a crispy tortilla pizza with melted cheese, ham, onion and bell pepper, cut into wedges",
    "bread-pizza": "two open-faced bread pizzas with melted cheese, ham and bell pepper on a plate",
    "omelet": "a fluffy yellow cheese omelet folded in half on a plate with a little ketchup",
    "gambas": "gambas al ajillo, sizzling shrimp in garlic olive oil with chili in a small skillet, with toasted bread",
    "hamburg-steak": "Japanese-style hamburg steak patty with brown glaze sauce on a plate with vegetables",
    "gyudon": "Japanese gyudon, a rice bowl topped with thinly sliced simmered beef and onions, green onions and a soft egg yolk",
    "oyakodon": "Japanese oyakodon, a rice bowl topped with chicken and soft runny scrambled egg and green onions",
    "yaki-udon": "Japanese yaki udon stir-fried thick noodles with cabbage, pork and carrot, sesame seeds",
    "tamagoyaki": "Japanese tamagoyaki, a thick layered rolled omelet sliced into pieces on a plate",
    "kare-rice": "Japanese curry rice with potato, carrot and pork in brown curry sauce over white rice on a plate",
    "eomuk-udon": "a bowl of udon noodle soup with skewered fish cakes, green onions in clear broth",
    "nikujaga": "Japanese nikujaga, simmered beef and potatoes with onion and carrot in a shallow bowl, glossy soy glaze",
    "naeng-somyeon": "cold somen noodles on a plate with ice, cucumber strips, seaweed and a small bowl of dipping sauce",
    "jjajangmyeon": "Korean jjajangmyeon noodles topped with glossy black bean sauce and cucumber strips in a white bowl",
    "jjajang-bap": "rice topped with black bean jjajang sauce with pork and vegetables and a fried egg",
    "mapa-dubu": "mapo tofu, cubes of soft tofu in glossy red spicy sauce with minced pork and green onions in a bowl",
    "jjamppong-ramen": "a bowl of red spicy jjamppong ramen with cabbage, onion and pork slices",
    "shrimp-fried-rice": "Chinese shrimp fried rice with egg, green onions and carrot pieces and whole shrimp, in a bowl",
}

from dish_scenes_extra import NO_PHOTO, SCENE_EXTRA, SCENE_OVERRIDE  # noqa: E402

SCENE.update(SCENE_EXTRA)
from dish_scenes_batch2 import SCENES as _SCENES2  # noqa: E402

SCENE.update(_SCENES2)
from dish_scenes_batch3 import SCENES as _SCENES3  # noqa: E402

SCENE.update(_SCENES3)
from dish_scenes_batch4 import SCENES as _SCENES4  # noqa: E402

SCENE.update(_SCENES4)
from dish_scenes_batch5 import SCENES as _SCENES5  # noqa: E402

SCENE.update(_SCENES5)
SCENE.update(SCENE_OVERRIDE)
from dish_scenes_fix import FIX as _FIX  # noqa: E402

SCENE.update(_FIX)

STYLE = ("appetizing food photograph, overhead 45-degree angle, Korean home cooking, served on a ceramic dish on a light wooden table, "
         "soft natural window light, shallow depth of field, realistic, high detail, no text, no watermark, no people")


def prompt_for(slug: str) -> str:
    return f"{SCENE[slug]}. {STYLE}"


def generate(prompt: str, seed: int) -> bytes:
    r = requests.post(
        FAL_URL,
        headers={"Authorization": f"Key {settings.fal_api_key}", "Content-Type": "application/json"},
        json={"prompt": prompt, "image_size": {"width": 768, "height": 576}, "num_images": 1, "num_inference_steps": 4, "seed": seed, "enable_safety_checker": True},
        timeout=90,
    )
    r.raise_for_status()
    return requests.get(r.json()["images"][0]["url"], timeout=90).content


def save(slug: str, seed: int) -> None:
    raw = generate(prompt_for(slug), seed)
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((720, 720))
    OUT.mkdir(exist_ok=True)
    im.save(OUT / f"{slug}.jpg", quality=82, optimize=True)


def todo() -> list:
    cc = json.loads((HERE / "photos.json").read_text(encoding="utf-8"))
    return [r["slug"] for r in RECIPES if r["slug"] not in cc and r["slug"] not in NO_PHOTO]


def sheet(path: Path, slugs: list) -> None:
    cols = 4
    w, h = 360, 270
    rows = (len(slugs) + cols - 1) // cols
    img = Image.new("RGB", (cols * w, rows * (h + 22)), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    names = {r["slug"]: r["name"] for r in RECIPES}
    for i, s in enumerate(slugs):
        f = OUT / f"{s}.jpg"
        x, y = (i % cols) * w, (i // cols) * (h + 22)
        if f.exists():
            im = Image.open(f).convert("RGB")
            im.thumbnail((w, h))
            img.paste(im, (x, y))
        d.text((x + 4, y + h + 2), names[s], fill="black", font=font)
    img.save(path, quality=85)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--redo")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--sheet")
    a = ap.parse_args()
    if a.sheet:
        sheet(Path(a.sheet), [s for s in todo() if (OUT / f"{s}.jpg").exists()])
        return
    if not settings.fal_api_key:
        raise SystemExit("FAL_API_KEY 가 없습니다.")
    if a.redo:
        slugs = a.redo.split(",")
    elif a.only:
        slugs = [s for s in a.only.split(",") if not (OUT / f"{s}.jpg").exists()]
    elif a.all:
        slugs = [s for s in todo() if not (OUT / f"{s}.jpg").exists()]
    else:
        raise SystemExit("--only / --all / --redo / --sheet 중 하나를 고르세요.")
    missing = [s for s in slugs if s not in SCENE]
    if missing:
        raise SystemExit(f"장면 설명이 없는 레시피: {missing}")
    for n, s in enumerate(slugs, 1):
        try:
            save(s, a.seed)
            print(f"[{n}/{len(slugs)}] {s} 완료", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[{n}/{len(slugs)}] {s} 실패: {exc}", flush=True)
        time.sleep(0.3)


if __name__ == "__main__":
    main()
