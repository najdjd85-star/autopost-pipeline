"""모든 레시피를 모은다. 본문은 recipes_part1.py, recipes_part2.py … 에 나눠 적는다(각 파일은 ITEMS 리스트를 둔다)."""
from __future__ import annotations

import importlib
from typing import Dict, List

RECIPES: List[dict] = []
for _n in range(1, 20):
    try:
        RECIPES += importlib.import_module(f"recipes_part{_n}").ITEMS
    except ModuleNotFoundError:
        pass

BY_SLUG: Dict[str, dict] = {r["slug"]: r for r in RECIPES}
RECIPE_ICON: Dict[str, str] = {r["slug"]: r["icon"] for r in RECIPES}
