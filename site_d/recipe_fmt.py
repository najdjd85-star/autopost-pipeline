"""레시피 작성용 도우미.

재료 한 줄 형식:  이름[?]:표시 분량|무게g
  - 이름 뒤 ? 는 '있으면 더 좋은 선택 재료'.
  - 표시 분량은 정확한 수치로 적는다(예: 물 400ml, 간장 1큰술(15ml), 계란 2개(약 110g)).
  - | 뒤의 숫자는 영양 계산에 쓰는 무게(g). 물은 생략한다.
  - 계량 기준: 1컵=200ml, 1큰술=15ml, 1작은술=5ml.
"""
from __future__ import annotations

from typing import Dict, List


def _parse(ingredients: str) -> List[Dict]:
    items = []
    for part in ingredients.split(";"):
        part = part.strip()
        if not part:
            continue
        name, rest = part.split(":", 1)
        grams = 0.0
        if "|" in rest:
            rest, g = rest.rsplit("|", 1)
            grams = float(g)
        name = name.strip()
        opt = name.endswith("?")
        items.append({"n": name.rstrip("?"), "q": rest.strip(), "g": grams, "opt": opt})
    return items


def R(slug: str, name: str, minutes: int, level: str, servings: int, cats: str, icon: str, desc: str, ingredients: str, steps: List[str], tips: List[str]) -> Dict:
    return {
        "slug": slug, "name": name, "minutes": minutes, "level": level, "servings": servings,
        "cats": [c.strip() for c in cats.split(",") if c.strip()], "icon": icon, "desc": desc,
        "ingredients": _parse(ingredients), "steps": steps, "tips": tips,
    }
