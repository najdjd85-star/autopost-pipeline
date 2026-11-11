"""모든 레시피를 모은다. 본문은 recipes_part1.py, recipes_part2.py … 에 나눠 적는다(각 파일은 ITEMS 리스트를 둔다)."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Dict, List

RECIPES: List[dict] = []
for _n in range(1, 40):
    try:
        RECIPES += importlib.import_module(f"recipes_part{_n}").ITEMS
    except ModuleNotFoundError:
        pass

# 매주 자동으로 추가되는 레시피(tools/auto_recipes.py 가 무료 Gemini로 작성·검사해 recipes_auto.json 에 쌓는다)
_AUTO = Path(__file__).resolve().parent / "recipes_auto.json"
if _AUTO.exists():
    from recipe_fmt import R

    _have = {r["slug"] for r in RECIPES}
    for _a in json.loads(_AUTO.read_text(encoding="utf-8")):
        if _a["slug"] not in _have:
            RECIPES.append(R(_a["slug"], _a["name"], _a["minutes"], _a["level"], _a["servings"], _a["cats"], _a["icon"], _a["desc"],
                             _a["ingredients"], _a["steps"], _a["tips"]))

BY_SLUG: Dict[str, dict] = {r["slug"]: r for r in RECIPES}
RECIPE_ICON: Dict[str, str] = {r["slug"]: r["icon"] for r in RECIPES}
