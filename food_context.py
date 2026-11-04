"""식비 절약 글의 프롬프트 자료: 사이트 D(냉장고 파먹기)의 재료 가격표와 주제에 맞는 레시피 링크."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List

SITE_D = Path(__file__).resolve().parent / "site_d"
COOK_URL = "https://cook.dailyfixpoint.com/"
_SUFFIX = re.compile(r"(요리|보관법|양념|재료|비용)$")
_CAT_WORDS = (("도시락", "lunchbox"), ("다이어트", "diet"), ("밑반찬", "side"), ("아침", "brunch"), ("한그릇", "rice"))


def _recipes(keyword: str, limit: int = 6) -> List[str]:
    if str(SITE_D) not in sys.path:
        sys.path.append(str(SITE_D))  # 뒤에 붙여서 본 프로젝트 모듈이 가려지지 않게 한다
    from prices import cost_per_serving
    from recipes_db import RECIPES

    people = [r for r in RECIPES if not {"pet", "baby", "kidsnack"} & set(r["cats"])]
    stem = _SUFFIX.sub("", keyword).replace("김장", "김치")
    # 한 글자 재료(무·쌀·귤)는 이름에서 찾으면 '무침' 같은 낱말에 걸려서 재료 목록으로만 찾는다
    hits = [r for r in people if (len(stem) > 1 and stem in r["name"]) or any(i["n"] == stem and not i["opt"] for i in r["ingredients"])]
    if not hits:
        cat = next((c for word, c in _CAT_WORDS if word in keyword), "dinner")
        hits = [r for r in people if cat in r["cats"]]
    hits.sort(key=cost_per_serving)
    return [f'- {r["name"]}: 1인분 재료비 약 {cost_per_serving(r):,}원, {r["minutes"]}분, {COOK_URL}recipes/{r["slug"]}.html\n  순서: {" ".join(r["steps"])}' for r in hits[:limit]]


def prompt_block(keyword: str) -> str:
    live = json.loads((SITE_D / "prices_live.json").read_text(encoding="utf-8"))
    prices = sorted(live["per100g"].items(), key=lambda kv: kv[1])
    price_text = ", ".join(f"{name} {won:,}원" for name, won in prices)
    recipes = "\n".join(_recipes(keyword))
    return (
        "[이번 글 - 식비 절약]\n"
        f"'{keyword}'을(를) 찾은 사람이 식비를 실제로 줄이도록 돕는 글입니다. category는 \"식비 절약\"으로 하세요.\n"
        "- 합격·불합격 인물 비교, 탈락 이야기는 쓰지 마세요. 자격과 신청 방법은 실제 제도를 다룰 때만 씁니다.\n"
        "- 재료값은 아래 가격표와 레시피 재료비만 쓰고, 기준일을 밝히세요. 표에 없는 가격·할인율·절약액은 지어내지 마세요.\n"
        "- 재료비는 쓴 양만 계산한 어림값이고 지역·브랜드에 따라 다르다고 한 번 밝히세요.\n"
        "- 보관 기간과 식품 안전은 '보통'처럼 일반 범위로 쓰고 단정하지 마세요. 상했는지 의심되면 먹지 말라고 안내하세요.\n"
        "- 표와 메뉴 이름만 나열하지 마세요. 재료마다 고르는 법·남기지 않고 쓰는 법을 쓰고, 메뉴마다 아래 순서를 2~3문장으로 줄여 독자가 글만 읽어도 어떻게 만드는지 알게 하세요. 정확한 분량과 전체 순서는 레시피 링크로 안내하세요.\n"
        "- 아래 레시피 중 글에 맞는 것을 3~5개까지 이름 그대로 주소에 연결하세요. 맞는 게 적으면 그만큼만 넣고, 주소를 바꾸거나 없는 레시피를 만들지 마세요.\n"
        f"- 글 끝에 집에 있는 재료로 만들 수 있는 요리를 찾는 곳으로 {COOK_URL} 을 안내하세요. 이 주소로 가는 CTA 버튼 문구는 '내 재료로 메뉴 찾기'로 쓰세요.\n\n"
        f"[재료 가격, 100g당 소매가 어림값 / 기준일 농산물 {live.get('kamis_date')}, 가공품 {live.get('online_date')}]\n{price_text}\n\n"
        f"[연결할 레시피]\n{recipes}\n\n"
    )
