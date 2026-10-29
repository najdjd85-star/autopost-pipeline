"""냉장고 파먹기(사이트 D) 정적 사이트 빌드. 서버·AI 호출 없이 site_d/dist 에 HTML을 만든다.

실행: venv/Scripts/python.exe site_d/build.py            (dist 생성)
      SITE_D_BASE=https://주소 venv/Scripts/python.exe site_d/build.py   (사이트맵·canonical 주소 지정)
미리보기: venv/Scripts/python.exe -m http.server 8791 --directory site_d/dist
"""
from __future__ import annotations

import html
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from nutrition_data import GRAMS, compute  # noqa: E402
from recipes_data import ALIASES, CATEGORIES, EMOJI, RECIPE_ICON, RECIPES, STAPLES  # noqa: E402

BASE = os.environ.get("SITE_D_BASE", "https://fridge.dailyfixpoint.com").rstrip("/")
SITE_NAME = "냉장고 파먹기"
DIST = HERE / "dist"
COUPANG_DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
FTC_DISCLOSURE = "이 사이트에는 제휴마케팅이 포함된 링크가 있으며 구매 시 커미션을 지급받을 수 있습니다."
REL = "sponsored nofollow noopener noreferrer"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def load_affiliate() -> dict:
    data = json.loads((HERE / "affiliate.json").read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_") and v}


def validate() -> None:
    """레시피 데이터가 앱에서 깨지지 않는지 검사한다(모르는 재료 이름, 빈 순서, 중복 슬러그)."""
    known = set(ALIASES) | set(STAPLES)
    slugs, problems = set(), []
    for r in RECIPES:
        if r["slug"] in slugs:
            problems.append(f"슬러그 중복: {r['slug']}")
        slugs.add(r["slug"])
        if len(r["steps"]) < 3:
            problems.append(f"{r['name']}: 순서가 너무 짧음")
        for i in r["ingredients"]:
            if i["n"] not in known:
                problems.append(f"{r['name']}: 알 수 없는 재료 '{i['n']}' (ALIASES에 추가 필요)")
    for r in RECIPES:
        if r["slug"] not in GRAMS:
            problems.append(f"{r['name']}: 영양 데이터(GRAMS) 없음")
            continue
        grams = GRAMS[r["slug"]][1]
        for i in r["ingredients"]:
            if i["n"] not in ("물", "소금", "후추") and i["n"] not in grams:
                problems.append(f"{r['name']}: 영양 계산에 '{i['n']}' 사용량 없음")
        for n in grams:
            if n not in {i["n"] for i in r["ingredients"]}:
                problems.append(f"{r['name']}: 영양 데이터에만 있는 재료 '{n}'")
        if r["slug"] not in RECIPE_ICON:
            problems.append(f"{r['name']}: 아이콘 없음")
    listed = {n for names in CATEGORIES.values() for n in names}
    for n in ALIASES:
        if n not in EMOJI:
            problems.append(f"이모지 없음: {n}")
        if n not in listed:
            problems.append(f"분류에 없는 재료: {n}")
    for n in listed:
        if n not in ALIASES:
            problems.append(f"ALIASES에 없는 분류 재료: {n}")
    if problems:
        raise SystemExit("데이터 오류:\n- " + "\n- ".join(problems))


def disclosure(has_links: bool) -> str:
    return f"<p>{esc(FTC_DISCLOSURE)}<br>{esc(COUPANG_DISCLOSURE)}</p>" if has_links else ""


def related(recipe: dict, limit: int = 4) -> list:
    mine = {i["n"] for i in recipe["ingredients"] if i["n"] not in STAPLES}
    scored = []
    for o in RECIPES:
        if o["slug"] == recipe["slug"]:
            continue
        theirs = {i["n"] for i in o["ingredients"] if i["n"] not in STAPLES}
        scored.append((len(mine & theirs), -o["minutes"], o))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [o for s, _m, o in scored[:limit] if s > 0]


def recipe_page(tpl: str, r: dict, aff: dict) -> str:
    ing_html = "".join(
        f'<li><span>{esc(i["n"])}{" (선택)" if i["opt"] else ""}</span><span class="q">{esc(i["q"])}</span></li>' for i in r["ingredients"]
    )
    buy_items = [(i["n"], aff[i["n"]]) for i in r["ingredients"] if i["n"] in aff]
    buy = ""
    if buy_items:
        links = "".join(f'<a class="buy" href="{esc(u)}" target="_blank" rel="{REL}">{esc(n)} 쿠팡에서 보기</a> ' for n, u in buy_items)
        buy = f'<div class="panel"><strong>재료가 모자라면</strong><div class="chips" style="margin-top:8px">{links}</div></div>'
    steps = "".join(f"<li>{esc(s)}</li>" for s in r["steps"])
    tip = f'<div class="tip">💡 {esc(r["tip"])}</div>' if r.get("tip") else ""
    rel = "".join(f'<a class="chip" href="{esc(o["slug"])}.html" style="text-decoration:none">{esc(o["name"])}</a>' for o in related(r))
    nut = compute(r["slug"])
    per = nut["per"]
    nut_rows = "".join(
        f'<tr><td>{esc(x["n"])}</td><td class="num">{x["g"]:g}g</td><td class="num">{x["kcal"]} kcal</td></tr>'
        for x in nut["rows"]
        if x["kcal"] > 0
    )
    carb_base = {"밥", "라면", "소면", "떡", "만두", "식빵"}
    rice_note = "" if carb_base & {x["n"] for x in nut["rows"]} else "밥이나 면은 포함하지 않았어요(밥 1공기는 약 315kcal). "
    nutrition = (
        '<h2>칼로리 표</h2><div class="panel nutri">'
        f'<div class="kcal-big"><strong>{per["kcal"]}</strong> kcal <span>1인분 기준{f" · 총 {nut['servings']}인분 분량" if nut["servings"] > 1 else ""}</span></div>'
        f'<div class="macro"><span>탄수화물 <b>{per["carb"]}g</b></span><span>단백질 <b>{per["protein"]}g</b></span><span>지방 <b>{per["fat"]}g</b></span></div>'
        f'<table><thead><tr><th>재료</th><th class="num">사용량</th><th class="num">열량</th></tr></thead><tbody>{nut_rows}'
        f'<tr class="sum"><td>전체 합계</td><td class="num"></td><td class="num">{nut["total_kcal"]} kcal</td></tr></tbody></table>'
        '<p class="note">식품성분표의 일반적인 평균값으로 계산한 추정치예요(선택 재료 포함). '
        f'{rice_note}브랜드·부위·양에 따라 달라질 수 있으니 참고용으로만 봐주세요. 질환이나 식단 관리가 필요하면 전문가와 상의하세요.</p></div>'
    )
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": r["name"],
        "description": r["desc"],
        "totalTime": f"PT{r['minutes']}M",
        "recipeYield": f'{nut["servings"]}인분',
        "nutrition": {"@type": "NutritionInformation", "calories": f'{per["kcal"]} kcal', "servingSize": "1인분",
                      "carbohydrateContent": f'{per["carb"]} g', "proteinContent": f'{per["protein"]} g', "fatContent": f'{per["fat"]} g'},
        "recipeIngredient": [f'{i["n"]} {i["q"]}' for i in r["ingredients"]],
        "recipeInstructions": [{"@type": "HowToStep", "text": s} for s in r["steps"]],
        "recipeCategory": "집밥",
        "recipeCuisine": "한식",
    }
    out = tpl
    for k, v in {
        "SITE_NAME": SITE_NAME, "BASE": BASE, "NAME": esc(r["name"]), "SLUG": r["slug"], "MINUTES": str(r["minutes"]),
        "LEVEL": esc(r["level"]), "DESC": esc(r["desc"]), "INGREDIENTS": ing_html, "BUY": buy, "STEPS": steps, "TIP": tip,
        "RELATED": rel, "DISCLOSURE": disclosure(bool(buy_items)),
        "ICON": RECIPE_ICON[r["slug"]], "SERVINGS": f'{nut["servings"]}인분', "NUTRITION": nutrition,
        "JSONLD": json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def main() -> None:
    validate()
    aff = load_affiliate()
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    (DIST / "recipes").mkdir()
    for name in ("style.css", "app.js"):
        shutil.copy(HERE / "static" / name, DIST / "assets" / name)

    data = {
        "staples": STAPLES,
        "emoji": EMOJI,
        "aliases": ALIASES,
        "categories": CATEGORIES,
        "affiliate": aff,
        "recipes": [
            {"slug": r["slug"], "name": r["name"], "minutes": r["minutes"], "level": r["level"], "desc": r["desc"],
             "icon": RECIPE_ICON[r["slug"]], "kcal": compute(r["slug"])["per"]["kcal"],
             "ingredients": [{"n": i["n"], "opt": i["opt"]} for i in r["ingredients"]]}
            for r in RECIPES
        ],
    }
    intro = (
        "<h2>이렇게 쓰세요</h2><p>냉장고에 있는 재료를 눌러 고르면, 부족한 재료가 없는 요리와 1~2가지만 더 있으면 되는 요리를 나눠서 보여드려요. "
        "소금·간장 같은 기본 양념은 집에 있다고 보고 계산하고, 없다면 체크를 풀면 됩니다.</p>"
        "<h2>모든 레시피</h2><div class=\"chips\">"
        + "".join(f'<a class="chip" href="recipes/{r["slug"]}.html" style="text-decoration:none">{esc(r["name"])}</a>' for r in RECIPES)
        + "</div>"
    )
    index = (HERE / "templates" / "index.html").read_text(encoding="utf-8")
    for k, v in {
        "SITE_NAME": SITE_NAME, "BASE": BASE, "COUNT": str(len(RECIPES)), "INTRO": intro,
        "DISCLOSURE": disclosure(bool(aff)), "DATA": json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        index = index.replace("{{" + k + "}}", v)
    (DIST / "index.html").write_text(index, encoding="utf-8")

    tpl = (HERE / "templates" / "recipe.html").read_text(encoding="utf-8")
    for r in RECIPES:
        (DIST / "recipes" / f"{r['slug']}.html").write_text(recipe_page(tpl, r, aff), encoding="utf-8")

    urls = [f"{BASE}/"] + [f"{BASE}/recipes/{r['slug']}.html" for r in RECIPES]
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(f"<url><loc>{u}</loc></url>" for u in urls) + "\n</urlset>\n"
    (DIST / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    print(f"빌드 완료: 레시피 {len(RECIPES)}개, 제휴 링크가 있는 재료 {len(aff)}개 -> {DIST}")


if __name__ == "__main__":
    main()
