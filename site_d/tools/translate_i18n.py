"""사이트 D 번역기: 한국어 데이터를 Gemini 무료 키 풀로 번역해 site_d/i18n/<언어>/*.json 에 저장한다.

- 무료 키만 쓴다(예전 단일 키 GOOGLE_AI_STUDIO_API_KEY 는 요금이 붙을 수 있어 이 도구에서는 끈다).
- 원문이 바뀐 항목만 다시 번역한다(원문 해시를 같이 저장). 중간에 멈춰도 다시 실행하면 이어서 한다.
- 번역 결과는 구조(단계 수·팁 수)가 원문과 같은지 검사하고, 어긋나면 그 묶음을 다시 시도한다.

사용:
  venv/Scripts/python.exe -X utf8 site_d/tools/translate_i18n.py --lang en --what ingredients,quantities,recipes
  옵션: --limit N(레시피 N개만 시험)  --batch N(한 번에 보낼 레시피 수, 기본 6)  --model 이름
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

os.environ["GEMINI_INCLUDE_LEGACY_KEY"] = "0"   # 무료 키만(config 를 불러오기 전에 정한다)

HERE = Path(__file__).resolve().parent
SITE_D = HERE.parent
ROOT = SITE_D.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SITE_D))

import requests  # noqa: E402

import gemini_keys  # noqa: E402

LANG_NAMES = {"en": "English"}
MODEL = "gemini-flash-latest"
FALLBACK_MODEL = "gemini-flash-lite-latest"
STYLE = (
    "You are translating a Korean home-cooking recipe site into natural, friendly American English for home cooks. "
    "Keep the instructions short, clear and idiomatic (imperative voice for steps). Keep every number, unit, temperature and time exactly. "
    "Use these conventions: 1컵=1 cup (200 ml), 큰술=tbsp, 작은술=tsp, 꼬집=pinch, 약간=a little, 송송 썰다=slice thinly, 다지다=mince, 채 썰다=cut into thin strips. "
    "Korean dish names: give the common English name or romanization with a short descriptor when helpful, e.g. 김치찌개 -> 'Kimchi Stew (Kimchi Jjigae)'. "
    "Do not add or drop sentences, and do not add commentary. Return only JSON."
)


def sha(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


def load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_json(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def call_gemini(prompt: str, model: str = MODEL, retries: int = 6) -> object:
    """JSON 으로 답을 받아 파이썬 값으로 돌려준다. 키 회전·한도 대기는 gemini_keys 가 처리하고, 모든 키가 쉬면 기다렸다 다시 한다."""
    body = {
        "systemInstruction": {"parts": [{"text": STYLE}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "maxOutputTokens": 32000},
    }
    last = ""
    for attempt in range(retries):
        def req(key: str):
            try:
                return requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=180,
                )
            except requests.RequestException:
                return None

        resp = gemini_keys.call_with_rotation(req)
        if resp is not None and resp.status_code == 200:
            try:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            except (KeyError, IndexError, ValueError) as exc:
                last = f"응답 해석 실패: {exc}"
        elif resp is None:
            last = "모든 키가 쉬는 중이거나 연결 실패"
        else:
            last = f"HTTP {resp.status_code}: {resp.text[:200]}"
        wait = 70 if resp is None or resp.status_code == 429 else 8
        print(f"   (재시도 {attempt + 1}/{retries}: {last[:120]} → {wait}초 대기)", flush=True)
        time.sleep(wait)
    raise SystemExit(f"번역 호출 실패: {last}")


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# ---------------------------------------------------------------- 재료 이름
def do_ingredients(lang: str, out_dir: Path, model: str) -> None:
    from recipes_data import ALIASES, STAPLES

    path = out_dir / "ingredients.json"
    have = load_json(path)
    names = list(ALIASES) + [s for s in STAPLES if s not in ALIASES and s != "물"] + ["물"]
    todo = [n for n in names if n not in have]
    print(f"재료 이름: 전체 {len(names)}개, 새로 번역 {len(todo)}개")
    for grp in chunks(todo, 60):
        rows = [{"ko": n, "ko_aliases": ALIASES.get(n, [])} for n in grp]
        prompt = (
            f"Translate these Korean cooking ingredient names into {LANG_NAMES[lang]}. For each item return an object "
            '{"ko": <same Korean name>, "name": <the standard English name, lower case unless a proper noun, singular for countable items (e.g. "egg", "onion")>, '
            '"aliases": [<other English words a home cook might type to find it: synonyms, plural form, spelling variants, brand-neutral terms; 2-6 items; lower case>]}. '
            'If the Korean item is a prepared product (e.g. 김치, 어묵, 스팸), use the common English name such as "kimchi", "fish cake", "Spam". '
            "Use 'ground X' or 'X powder' where the Korean says 가루. Return a JSON array in the same order.\n\n" + json.dumps(rows, ensure_ascii=False)
        )
        res = call_gemini(prompt, model)
        if not isinstance(res, list):
            raise SystemExit("재료 응답 형식 오류")
        got = {x.get("ko"): x for x in res if isinstance(x, dict)}
        for n in grp:
            x = got.get(n)
            if x and isinstance(x.get("name"), str) and x["name"].strip():
                have[n] = {"name": x["name"].strip(), "aliases": [a.strip().lower() for a in x.get("aliases", []) if isinstance(a, str) and a.strip()]}
        save_json(path, have)
        print(f"  저장: {len(have)}/{len(names)}", flush=True)
    miss = [n for n in names if n not in have]
    if miss:
        print("  번역 못한 재료:", miss)


# ---------------------------------------------------------------- 분량 문구
def do_quantities(lang: str, out_dir: Path, model: str) -> None:
    from recipes_db import RECIPES

    path = out_dir / "quantities.json"
    have = load_json(path)
    uniq = sorted({i["q"] for r in RECIPES for i in r["ingredients"]})
    todo = [q for q in uniq if q not in have]
    print(f"분량 문구: 고유 {len(uniq)}개, 새로 번역 {len(todo)}개")
    for grp in chunks(todo, 90):
        prompt = (
            "Translate these Korean ingredient quantity phrases from recipes into concise English. Keep numbers and fractions as written (1/2 stays 1/2), "
            "use 'tbsp', 'tsp', 'cup', 'g', 'ml'. 개 = 'piece' (omit the word when it is obviously a whole item, e.g. '1개' -> '1', '2개(약 110g)' -> '2 (about 110 g)'), "
            "공기 = 'bowl', 모 = 'block', 대 = 'stalk', 쪽 = 'clove', 장 = 'sheet', 줌 = 'handful', 봉지 = 'pack', 캔 = 'can', 마리 = 'whole', 꼬집 = 'pinch', 약간 = 'a little', "
            "송송 썬 것 = 'thinly sliced', 다진 것 = 'minced', 채 썬 것 = 'cut into thin strips', 약 = 'about'. Put a space between number and unit. "
            "Return a JSON object mapping each Korean phrase (exactly as given) to its English phrase.\n\n" + json.dumps(grp, ensure_ascii=False)
        )
        res = call_gemini(prompt, model)
        if not isinstance(res, dict):
            raise SystemExit("분량 응답 형식 오류")
        for q in grp:
            v = res.get(q)
            if isinstance(v, str) and v.strip():
                have[q] = v.strip()
        save_json(path, have)
        print(f"  저장: {len(have)}/{len(uniq)}", flush=True)
    print("  번역 못한 분량:", [q for q in uniq if q not in have])


# ---------------------------------------------------------------- 레시피
def recipe_src(r: dict) -> dict:
    return {"name": r["name"], "desc": r["desc"], "steps": r["steps"], "tips": r["tips"]}


def do_recipes(lang: str, out_dir: Path, model: str, limit: int, batch: int) -> None:
    from recipes_db import RECIPES

    path = out_dir / "recipes.json"
    have = load_json(path)
    todo = [r for r in RECIPES if have.get(r["slug"], {}).get("h") != sha(json.dumps(recipe_src(r), ensure_ascii=False))]
    if limit:
        todo = todo[:limit]
    print(f"레시피: 전체 {len(RECIPES)}개, 새로 번역 {len(todo)}개")
    ings = load_json(out_dir / "ingredients.json")
    done = 0
    for grp in chunks(todo, batch):
        rows = []
        for r in grp:
            rows.append({"slug": r["slug"], **recipe_src(r),
                         "ingredient_names_in_english": {i["n"]: ings.get(i["n"], {}).get("name", i["n"]) for i in r["ingredients"]}})
        prompt = (
            "Translate each recipe below. Return a JSON array in the same order; each item: "
            '{"slug": <same>, "name": <English dish name>, "desc": <English>, "steps": [<English step per Korean step, same count and order>], "tips": [<English tip per Korean tip, same count and order>]}. '
            "In steps and tips, name each ingredient with the English word given in ingredient_names_in_english (use that exact word, singular form, so the site can attach amounts to it). "
            "Each step must stay one string with the same sentences as the Korean one.\n\n" + json.dumps(rows, ensure_ascii=False)
        )
        for attempt in range(3):
            res = call_gemini(prompt, model)
            good = {}
            if isinstance(res, list):
                for x in res:
                    if not isinstance(x, dict):
                        continue
                    r = next((q for q in grp if q["slug"] == x.get("slug")), None)
                    if not r:
                        continue
                    ok = (isinstance(x.get("name"), str) and isinstance(x.get("desc"), str)
                          and isinstance(x.get("steps"), list) and len(x["steps"]) == len(r["steps"]) and all(isinstance(s, str) and s.strip() for s in x["steps"])
                          and isinstance(x.get("tips"), list) and len(x["tips"]) == len(r["tips"]) and all(isinstance(s, str) and s.strip() for s in x["tips"])
                          and not re.search(r"[가-힣]", x["name"] + x["desc"] + "".join(x["steps"]) + "".join(x["tips"])))
                    if ok:
                        good[r["slug"]] = {"name": x["name"].strip(), "desc": x["desc"].strip(), "steps": [s.strip() for s in x["steps"]],
                                           "tips": [s.strip() for s in x["tips"]], "h": sha(json.dumps(recipe_src(r), ensure_ascii=False))}
            have.update(good)
            save_json(path, have)
            grp = [r for r in grp if r["slug"] not in good]
            if not grp:
                break
            rows = [row for row in rows if row["slug"] in {r["slug"] for r in grp}]
            prompt = prompt.split("\n\n", 1)[0] + "\n\n" + json.dumps(rows, ensure_ascii=False)
            print(f"   다시 시도할 레시피 {len(grp)}개", flush=True)
        done += batch
        print(f"  저장: {len(have)}/{len(RECIPES)}", flush=True)
    print("  번역 못한 레시피:", [r["slug"] for r in RECIPES if r["slug"] not in have][:20])


# ---------------------------------------------------------------- 화면 문구 · 제휴 버튼 이름
UI_FIXED = {"냉장고 파먹기": "Fridge Raid", "·": ",", "약 {c}원": "about ₩{c}"}


def do_ui(lang: str, out_dir: Path, model: str, keys_file: str) -> None:
    keys = json.loads(Path(keys_file).read_text(encoding="utf-8"))
    path = out_dir / "ui.json"
    have = load_json(path)
    have.update({k: v for k, v in UI_FIXED.items() if k in keys})
    todo = [k for k in keys if k not in have]
    print(f"화면 문구: 전체 {len(keys)}개, 새로 번역 {len(todo)}개")
    for grp in chunks(todo, 40):
        prompt = (
            "Translate these Korean UI strings of a fridge-ingredient recipe finder website (site name: 'Fridge Raid') into natural, friendly English. "
            "Rules: keep every {placeholder} (e.g. {n}, {m}, {{NAME}}, {won}) exactly as is; keep HTML tags (<b>, <small>), emoji and arrows (←, ↓, ▴, ▾); "
            "do not use double quotes (\") anywhere (use single quotes or none); keep it concise (button labels short). "
            "Currency is Korean won: write amounts as ₩. 가나다순 = 'A–Z order', 초성 = 'first letter' (the English site groups recipes by first letter and has no Korean consonant search; "
            "say 'you can also type Korean names' where the Korean mentions 초성 search), 양념통 = 'spice rack', 냉털/냉장고 파먹기 = 'cleaning out the fridge'. "
            "Short nav labels for a narrow phone screen: '🧊 재료로 찾기' -> '🧊 Ingredients', '☰ 카테고리' -> '☰ Categories', '📖 모든 레시피' -> '📖 All recipes'. "
            "Dish-type words: 덮밥 'Rice bowls', 볶음밥 'Fried rice', 비빔밥 'Bibimbap', 죽 'Porridge', 국밥 'Soup with rice', 면·국수 'Noodles', 전·부침 'Pancakes (jeon)', 찌개·전골 'Stews & hot pots', 탕 'Soups (tang)', 국·수프 'Soups', 분식 'Street snacks', 구이·튀김 'Grilled & fried', 볶음 'Stir-fries', 조림·찜 'Braised & steamed', 기타 'Other'. "
            "Return a JSON object mapping each Korean string (exactly as given) to its English translation.\n\n" + json.dumps(grp, ensure_ascii=False)
        )
        res = call_gemini(prompt, model)
        if not isinstance(res, dict):
            raise SystemExit("화면 문구 응답 형식 오류")
        for k in grp:
            v = res.get(k)
            if isinstance(v, str) and v.strip() and not re.search(r"[가-힣]", re.sub(r"ㄱㅊ|ㄱㄴㄷ", "", v)):
                have[k] = v.strip()
        save_json(path, have)
        print(f"  저장: {len(have)}/{len(keys)}", flush=True)
    print("  번역 못한 문구:", [k for k in keys if k not in have])


def do_labels(lang: str, out_dir: Path, model: str) -> None:
    aff = json.loads((SITE_D / "affiliate.json").read_text(encoding="utf-8"))
    labels = set((aff.get("ingredient_labels") or {}).values())
    for t in (aff.get("tools") or {}).values():
        labels.add(t.get("label", ""))
    for key in ("extras", "variants", "category_products"):
        for xs in (aff.get(key) or {}).values():
            labels |= {x.get("label", "") for x in xs}
    labels = sorted(x for x in labels if x)
    path = out_dir / "labels.json"
    have = load_json(path)
    todo = [x for x in labels if x not in have]
    print(f"제휴 버튼 이름: 전체 {len(labels)}개, 새로 번역 {len(todo)}개")
    for grp in chunks(todo, 60):
        prompt = ("Translate these Korean grocery / kitchen product names (used on 'buy' buttons) into short natural English product names. Keep brand names. "
                  "Return a JSON object mapping each Korean name (exactly as given) to English.\n\n" + json.dumps(grp, ensure_ascii=False))
        res = call_gemini(prompt, model)
        if isinstance(res, dict):
            for k in grp:
                v = res.get(k)
                if isinstance(v, str) and v.strip():
                    have[k] = v.strip()
        save_json(path, have)
    print("  번역 못한 이름:", [x for x in labels if x not in have])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="en")
    ap.add_argument("--what", default="ingredients,quantities,recipes")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=6)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--keys", default="")
    a = ap.parse_args()
    out_dir = SITE_D / "i18n" / a.lang
    for w in a.what.split(","):
        if w == "ingredients":
            do_ingredients(a.lang, out_dir, a.model)
        elif w == "quantities":
            do_quantities(a.lang, out_dir, a.model)
        elif w == "ui":
            do_ui(a.lang, out_dir, a.model, a.keys)
        elif w == "labels":
            do_labels(a.lang, out_dir, a.model)
        elif w == "recipes":
            do_recipes(a.lang, out_dir, a.model, a.limit, a.batch)
        else:
            raise SystemExit(f"알 수 없는 항목: {w}")


if __name__ == "__main__":
    main()
