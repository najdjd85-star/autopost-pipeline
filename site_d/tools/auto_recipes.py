"""[매주, 내 PC] 검색량이 큰데 사이트 D에 아직 없는 요리를 골라 무료 Gemini로 레시피를 쓰고, 검사를 통과한 것만 추가한다.

순서
  1. 네이버 검색광고 API(무료)로 요리 이름 검색량을 보고, 아직 없는 요리 후보를 고른다(이미 시도한 이름은 건너뜀).
  2. Gemini가 사이트 형식(재료는 등록된 재료 이름만, 분량은 g/ml까지)으로 레시피를 쓴다.
  3. 기계 검사(build.recipe_problems: 모르는 재료·무게 누락·모호한 분량 등) → Gemini 2차 검토(조리법·분량·시간·식품 안전).
     문제가 나오면 한 번 고쳐 쓰고 다시 검사, 그래도 안 되면 버린다.
  4. 통과한 레시피는 site_d/recipes_auto.json 에 쌓고(recipes_db.py 가 읽는다), 사진을 만든 뒤(fal, 장당 약 $0.003)
     Gemini가 사진이 그 요리처럼 보이는지 확인한다(아니면 한 번 더, 그래도 아니면 사진 없이 둔다).
  영어 번역·빌드·깃 반영은 scripts/update_site_d.py 의 기존 순서가 이어서 한다.

비용: 레시피 작성·검토는 무료 Gemini 키 풀만 쓴다(예전 단일 유료 키는 끈다). 사진만 유료(주 3장 기준 약 $0.01).
실행: venv/Scripts/python.exe -X utf8 site_d/tools/auto_recipes.py [--count 3] [--dry]   (--dry: 저장·사진 없이 결과만 출력)
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import random
import re
import sys
import time
from pathlib import Path

os.environ["GEMINI_INCLUDE_LEGACY_KEY"] = "0"   # 무료 키만

HERE = Path(__file__).resolve().parent
SITE_D = HERE.parent
ROOT = SITE_D.parent
for _p in (ROOT, SITE_D, HERE):
    sys.path.insert(0, str(_p))

AUTO = SITE_D / "recipes_auto.json"
STATE = ROOT / "data" / "output" / "auto_recipes_state.json"
MIN_VOLUME = 3000          # 월 검색량(PC+모바일)이 이보다 작으면 후보에서 뺀다
LEVELS = ("쉬움", "보통", "어려움")
UNAVAILABLE = False      # 이번 실행 중 Gemini(flash)가 응답하지 않았는지(그러면 weekly 가 내일 다시 시도)

SEEDS = ["김치", "찌개", "국", "탕", "볶음", "조림", "무침", "나물", "전", "구이", "찜", "덮밥", "볶음밥", "국수", "비빔밥", "죽",
         "반찬", "밑반찬", "도시락반찬", "술안주", "간식", "다이어트요리", "에어프라이어요리", "제철요리", "명절음식", "장아찌", "파스타", "샐러드"]
DISH = re.compile(r"(찌개|국|탕|볶음|조림|무침|나물|전|구이|찜|덮밥|볶음밥|비빔밥|국수|면|김밥|샐러드|김치|장아찌|죽|밥|떡|튀김|강정|수육|보쌈|스테이크|파스타|리조또|토스트|샌드위치|만두|전골|장|피클|맛탕|부침|말이|쌈|겉절이|냉채|수프)$")
NOISE = re.compile(r"레시피|만드는법|만들기|황금|맛집|칼로리|효능|백종원|배달|가격|밀키트|택배|추천|파는곳|주문|이미지|영어|뜻|종류|재료|양념|소스|부산|서울|대구|강남|홍대|체인|프랜차이즈|편의점|브랜드|\d")


def _norm(name: str) -> str:
    return re.sub(r"\s|\(.*?\)", "", name)


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def candidates(have_names: set, tried: set, n_hints: int = 25) -> list:
    """(검색량, 요리 이름) 후보를 검색량 큰 순으로 돌려준다."""
    import search_demand as sd
    from recipes_db import RECIPES

    hints = SEEDS + random.sample([r["name"] for r in RECIPES], min(n_hints, len(RECIPES)))
    random.shuffle(hints)
    vol: dict = {}
    for i in range(0, len(hints), 5):
        try:
            for it in sd._naver_ad_items(hints[i:i + 5]):
                k, v = it.get("relKeyword", ""), sd._item_volume(it)
                if k and v:
                    vol[k] = max(vol.get(k, 0), v)
        except Exception:  # noqa: BLE001 - 한 묶음 실패는 건너뛴다
            pass
        time.sleep(0.35)
    out = []
    for k, v in vol.items():
        if v < MIN_VOLUME or len(k) < 2 or not DISH.search(k) or NOISE.search(k):
            continue
        if _norm(k) in have_names or _norm(k) in tried:
            continue
        out.append((v, k))
    return sorted(out, reverse=True)


def _similar(name: str, names: list) -> list:
    """이름이 두 글자 이상 겹치는 기존 레시피(중복 판단용으로 Gemini에 보여 준다)."""
    grams = {name[i:i + 2] for i in range(len(name) - 1)}
    scored = sorted(((sum(g in x for g in grams), x) for x in names), key=lambda t: -t[0])
    return [x for s, x in scored if s > 0][:40]


def _known_ingredients() -> list:
    from recipes_data import ALIASES, STAPLES

    return sorted(set(ALIASES) | set(STAPLES))


def _cats_text() -> str:
    from recipes_data import RECIPE_CATS

    return ", ".join(f"{c[0]}({c[1]})" for c in RECIPE_CATS if c[0] != "pet")


RULES = """[작성 규칙]
- 한국 가정에서 실제로 해 먹는 표준 조리법. 출처 불명 변형·과장 금지. 브랜드·식당·유명인 이름 금지.
- 재료 name 은 아래 [등록된 재료] 목록의 이름과 글자까지 똑같아야 한다(예: 마늘은 '다진마늘', 꽈리고추는 '청양고추' 이름에 qty '꽈리고추 200g').
  목록에 없는 핵심 재료가 꼭 필요하면 레시피를 쓰지 말고 {"skip": "이유"} 만 답한다.
- qty 는 정확한 수치(예: '2큰술(30ml)', '1개(약 200g)', '300g'). '약간·적당량·조금·한 줌' 금지(후추만 예외). 컵은 ml도 함께.
  1컵=200ml, 1큰술=15ml, 1작은술=5ml. grams 는 영양 계산용 무게(g, 물은 0). 튀김 기름·절임 소금·버리는 절임장은 먹게 되는(흡수되는) 양만.
- 선택 재료는 optional=true. steps 는 4~8단계, 각 단계에 불 세기·시간·크기 같은 구체 수치. 단계에 쓰는 재료는 모두 재료 목록에 있어야 한다.
- tips 2~3개(실패 줄이는 요령, 보관법, 대체 재료). 돼지고기·닭고기·해산물은 속까지 익히는 기준을 적는다.
- cats 는 아래 [카테고리] 슬러그 1~3개를 쉼표로. icon 은 이모지 1개. level 은 쉬움/보통/어려움 중 하나.
- slug 는 영문 소문자 로마자 표기와 하이픈(예: 'gochu-jangajji'). desc 는 40~70자 한 문장.
- scene 은 완성 요리 사진 묘사(영어 한 문장, 그릇·색·주재료를 구체적으로, 사람·글자 없이)."""

SHAPE = ('{"slug": "...", "name": "...", "minutes": 30, "level": "쉬움", "servings": 2, "cats": "side,lunchbox", "icon": "🍲", "desc": "...", '
         '"ingredients": [{"name": "...", "qty": "...", "grams": 0, "optional": false}], "steps": ["..."], "tips": ["..."], "scene": "..."}')


def write_recipe(dish: str, similar: list, fix_notes: list | None = None, prev: dict | None = None):
    import gemini_llm

    ask = (f"요리 이름: {dish}\n\n{RULES}\n\n[카테고리]\n{_cats_text()}\n\n[등록된 재료]\n{', '.join(_known_ingredients())}\n\n"
           f"[이미 있는 비슷한 레시피]\n{', '.join(similar) or '(없음)'}\n"
           "위 목록 중 하나와 사실상 같은 요리(이름만 다른 같은 음식)라면 {\"skip\": \"중복: 기존 이름\"} 만 답한다. "
           "검색어가 요리 이름이 아니거나(상품명·지역 맛집 등) 정체가 불분명해도 skip.\n")
    if fix_notes and prev:
        ask += ("\n[앞서 쓴 레시피]\n" + json.dumps(prev, ensure_ascii=False) + "\n[고칠 점]\n- " + "\n- ".join(fix_notes)
                + "\n고칠 점을 모두 반영해 레시피 전체를 다시 쓴다.\n")
    ask += f"\n아래 형식의 JSON 하나로만 답한다:\n{SHAPE}"
    return gemini_llm.generate_json(ask, purpose="auto_recipe", system="당신은 한국 가정식 레시피를 정확하게 쓰는 요리 연구가입니다.",
                                    model="flash", max_output=8192, allow_lite=False)


def review_recipe(rec: dict) -> list:
    """Gemini 2차 검토. 문제 목록(없으면 빈 목록). 검토 자체가 실패하면 ['검토 실패'] 를 돌려 저장하지 않게 한다."""
    import gemini_llm

    ask = ("아래 한국 가정식 레시피를 꼼꼼히 검토하세요.\n"
           "확인할 것: (1) 이 요리의 일반적인 조리법과 맞는가 (2) 인분 수에 비해 재료 양이 맞는가(소금·간장 과다 포함) "
           "(3) 불 세기·시간이 현실적인가 (4) 고기·해산물이 안전하게 익는가 (5) 단계에 쓰인 재료가 모두 재료 목록에 있는가(물 제외) "
           "(6) 재료 무게(| 뒤 g)가 표시 분량과 대략 맞는가.\n"
           "사소한 문체 차이는 문제로 보지 마세요. 실제로 요리를 망치거나 틀린 정보만 적습니다.\n"
           '{"ok": true/false, "problems": ["..."]} 형식의 JSON으로만 답하세요.\n\n' + json.dumps(rec, ensure_ascii=False))
    data = None
    for _ in range(2):   # 일시 오류면 한 번 더
        data = gemini_llm.generate_json(ask, purpose="auto_recipe_review", model="flash", max_output=4096, allow_lite=False)
        if isinstance(data, dict) and "ok" in data:
            break
        time.sleep(20)
    if not isinstance(data, dict) or "ok" not in data:
        global UNAVAILABLE
        UNAVAILABLE = True   # 검토를 못 했으면 저장하지 않고 내일 다시
        return ["검토 실패(Gemini 응답 없음)"]
    probs = [str(p) for p in data.get("problems") or [] if str(p).strip()]
    return [] if data.get("ok") is True else (probs or ["검토에서 불합격(이유 없음)"])


def to_entry(raw: dict, used_slugs: set):
    """Gemini 답을 recipes_auto.json 한 항목으로 바꾼다. 형식이 깨졌으면 (None, 이유)."""
    try:
        parts = []
        for i in raw["ingredients"]:
            name = str(i["name"]).strip()
            qty = str(i["qty"]).replace(";", ",").replace("|", "/").strip()
            g = float(i.get("grams") or 0)
            tag = name + ("?" if i.get("optional") else "")
            parts.append(f"{tag}:{qty}" + (f"|{g:g}" if g > 0 else ""))
        slug = re.sub(r"[^a-z0-9-]+", "-", str(raw["slug"]).lower()).strip("-")[:60] or "recipe"
        base, k = slug, 2
        while slug in used_slugs:
            slug, k = f"{base}-{k}", k + 1
        level = raw["level"] if raw.get("level") in LEVELS else "보통"
        entry = {
            "slug": slug, "name": str(raw["name"]).strip(), "minutes": int(raw["minutes"]), "level": level,
            "servings": max(1, int(raw["servings"])), "cats": str(raw["cats"]).replace(" ", ""), "icon": str(raw.get("icon") or "🍽️")[:2],
            "desc": str(raw["desc"]).strip(), "ingredients": "; ".join(parts),
            "steps": [str(s).strip() for s in raw["steps"] if str(s).strip()], "tips": [str(t).strip() for t in raw["tips"] if str(t).strip()],
            "scene": str(raw.get("scene") or "").strip(),
        }
        return entry, ""
    except (KeyError, TypeError, ValueError) as exc:
        return None, f"형식 오류: {exc}"


def machine_check(entry: dict) -> list:
    import build
    from recipe_fmt import R

    r = R(entry["slug"], entry["name"], entry["minutes"], entry["level"], entry["servings"], entry["cats"], entry["icon"], entry["desc"],
          entry["ingredients"], entry["steps"], entry["tips"])
    probs = build.recipe_problems(r)
    if not entry["scene"]:
        probs.append("scene(사진 묘사) 없음")
    if not 3 <= entry["minutes"] <= 600:
        probs.append(f"조리 시간 {entry['minutes']}분이 비현실적")
    return probs


def _site_still_valid() -> bool:
    """recipes_auto.json 을 넣은 상태로 사이트 전체 데이터 검사(build.validate)가 통과하는지 새 프로세스에서 확인한다."""
    import subprocess

    res = subprocess.run([sys.executable, "-X", "utf8", "-c", "import build; build.validate()"], cwd=str(SITE_D),
                         capture_output=True, text=True, encoding="utf-8", timeout=300)
    return res.returncode == 0


def photo_matches(slug: str, name: str, desc: str) -> bool:
    """만든 사진이 그 요리처럼 보이는지 Gemini(이미지 입력)로 확인한다. 확인이 안 되면 통과로 본다(사진 없음보다 낫게)."""
    import gemini_llm
    from llm_usage import record_gemini

    f = SITE_D / "photos_ai" / f"{slug}.jpg"
    body = {"contents": [{"role": "user", "parts": [
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(f.read_bytes()).decode()}},
        {"text": f"이 사진이 한국 요리 '{name}'({desc}) 완성 사진으로 보기에 자연스러운가요? 전혀 다른 요리처럼 보이면 false. "
                 '{"match": true/false, "why": "짧게"} JSON으로만 답하세요.'}]}],
        "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 512}}
    for model in (gemini_llm.MODELS["flash"], gemini_llm.MODELS["lite"]):
        resp = gemini_llm._call(model, body)
        if resp is None or resp.status_code != 200:
            continue
        try:
            data = resp.json()
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"] if not p.get("thought"))
            meta = data.get("usageMetadata", {})
            record_gemini("auto_recipe_photo", model, meta.get("promptTokenCount", 0), meta.get("candidatesTokenCount", 0))
            return bool(json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())).get("match", True))
        except (ValueError, KeyError, IndexError):
            continue
    return True


def make_photo(entry: dict) -> str:
    import make_dish_photos as mdp

    mdp.SCENE[entry["slug"]] = entry["scene"]
    for seed in (3, 11):
        try:
            mdp.save(entry["slug"], seed)
        except Exception as exc:  # noqa: BLE001
            return f"사진 실패({exc.__class__.__name__})"
        if photo_matches(entry["slug"], entry["name"], entry["desc"]):
            return "사진 완료" if seed == 3 else "사진 완료(두 번째)"
    (SITE_D / "photos_ai" / f"{entry['slug']}.jpg").unlink(missing_ok=True)
    return "사진이 요리와 달라 빼 둠"


def run(count: int = 3, dry: bool = False) -> str:
    global UNAVAILABLE
    import gemini_keys
    import search_demand as sd

    UNAVAILABLE = False
    if not gemini_keys.has_keys():
        return "자동 레시피: Gemini 키 없음, 건너뜀"
    if not sd.naver_ad_configured():
        return "자동 레시피: 네이버 검색광고 키 없음, 건너뜀"
    from recipes_db import RECIPES

    state = _load_json(STATE, {"tried": {}})
    tried = set(state["tried"])
    have = {_norm(r["name"]) for r in RECIPES}
    names = [r["name"] for r in RECIPES]
    used_slugs = {r["slug"] for r in RECIPES}
    auto = _load_json(AUTO, [])
    added, notes = [], []
    for vol, dish in candidates(have, tried)[:count * 4]:
        if len(added) >= count:
            break
        state["tried"][_norm(dish)] = dt.date.today().isoformat()
        raw = write_recipe(dish, _similar(dish, names))
        if not isinstance(raw, dict):   # 일시 오류(503·JSON 깨짐)일 수 있어 한 번 더
            time.sleep(20)
            raw = write_recipe(dish, _similar(dish, names))
        if not isinstance(raw, dict):   # Gemini(flash)가 응답하지 않음 -> 이번엔 멈추고 내일 다시(가벼운 모델로 대충 쓰지 않는다)
            state["tried"].pop(_norm(dish), None)
            notes.append(f"{dish}: Gemini 응답 없음, 내일 다시 시도")
            UNAVAILABLE = True
            break
        if raw.get("skip"):
            notes.append(f"{dish}: 건너뜀({str(raw['skip'])[:40]})")
            continue
        entry, why = to_entry(raw, used_slugs)
        probs = [why] if entry is None else machine_check(entry) or review_recipe(entry)
        if probs and entry is not None:   # 한 번 고쳐 쓰기
            raw2 = write_recipe(dish, _similar(dish, names), probs, entry)
            if isinstance(raw2, dict) and not raw2.get("skip"):
                entry, why = to_entry(raw2, used_slugs)
                probs = [why] if entry is None else machine_check(entry) or review_recipe(entry)
        if UNAVAILABLE:
            state["tried"].pop(_norm(dish), None)
            notes.append(f"{dish}: Gemini 응답 없음, 내일 다시 시도")
            break
        if probs or entry is None:
            notes.append(f"{dish}: 검사 불합격({'; '.join(probs)[:80]})")
            continue
        if _norm(entry["name"]) in have:
            notes.append(f"{dish}: 이미 있는 이름({entry['name']})")
            continue
        entry.update({"added": dt.date.today().isoformat(), "keyword": dish, "volume": vol, "source": "gemini"})
        if dry:
            print(json.dumps(entry, ensure_ascii=False, indent=1))
        else:
            auto.append(entry)
            AUTO.write_text(json.dumps(auto, ensure_ascii=False, indent=1), encoding="utf-8")
            if not _site_still_valid():   # 사이트 전체 검사가 깨지면 이 레시피는 되돌린다(매일 빌드가 멈추지 않게)
                auto.pop()
                AUTO.write_text(json.dumps(auto, ensure_ascii=False, indent=1), encoding="utf-8")
                notes.append(f"{dish}: 사이트 검사 실패로 되돌림")
                continue
            notes.append(f"{entry['name']}: {make_photo(entry)}")
        added.append(entry["name"])
        have.add(_norm(entry["name"]))
        names.append(entry["name"])
        used_slugs.add(entry["slug"])
    if not dry:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    head = f"자동 레시피 {len(added)}개 추가" + (f": {', '.join(added)}" if added else "")
    return head + ("\n  " + "\n  ".join(notes[-8:]) if notes else "")


def weekly(count: int = 3) -> str:
    """7일에 한 번만 run() 한다(update_site_d.py 가 매일 부른다)."""
    state = _load_json(STATE, {"tried": {}})
    try:
        if (dt.date.today() - dt.date.fromisoformat(state.get("last_run", ""))).days < 7:
            return "자동 레시피: 이번 주에 이미 함(7일에 한 번)"
    except ValueError:
        pass
    msg = run(count)
    if UNAVAILABLE:
        return msg + " (Gemini 응답이 없어 내일 다시 시도)"
    state = _load_json(STATE, {"tried": {}})
    state["last_run"] = dt.date.today().isoformat()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return msg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    print(run(a.count, a.dry))


if __name__ == "__main__":
    main()
