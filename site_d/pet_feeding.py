"""반려동물 레시피의 체급별 하루 급여량 계산.

기준: 하루 필요 열량(DER) = 휴식 대사량(RER, 70 × 체중kg^0.75) × 계수(중성화 성견 1.6, 중성화 실내 성묘 1.2).
간식·토핑(집밥 화식 포함)은 하루 열량의 10% 이내로 준다(사료로 영양을 채우고 나머지만 간식으로 주는 일반 권장).
급여 무게는 '이 레시피 전체 열량 ÷ 완성 무게'로 구한 g당 열량으로 바꾼다. 완성 무게는 삶기·굽기·말리기로 줄어드는 양을 반영한 대략치다.
"""
from __future__ import annotations

# 슬러그 -> (동물 dog/cat, 종류 treat 간식 / meal 화식·토핑, 완성 무게 g, 나눈 개수 단위('개'·'조각'·'' = 무게로만))
FEED = {
    "dog-chicken-sweetpotato-jerky": ("dog", "treat", 120, "조각"),
    "dog-chicken-veg-porridge": ("dog", "meal", 540, ""),
    "dog-pumpkin-oat-cookie": ("dog", "treat", 175, "개"),
    "dog-tofu-chicken-ball": ("dog", "treat", 250, "개"),
    "dog-salmon-potato-bite": ("dog", "treat", 200, "개"),
    "dog-beef-veg-stew": ("dog", "meal", 570, ""),
    "dog-egg-sweetpotato-steam": ("dog", "meal", 180, ""),
    "dog-yogurt-banana-ice": ("dog", "treat", 150, "개"),
    "cat-chicken-broth": ("cat", "meal", 330, ""),
    "cat-salmon-treat": ("cat", "treat", 85, ""),
    "cat-chicken-egg-pudding": ("cat", "treat", 175, ""),
    "dog-sweetpotato-chew": ("dog", "treat", 90, "조각"),
    "dog-bugeo-treat": ("dog", "treat", 30, "조각"),
    "dog-duck-jerky": ("dog", "treat", 90, "조각"),
    "cat-chicken-cube": ("cat", "treat", 150, "개"),
    "dog-apple-yogurt-pop": ("dog", "treat", 200, "개"),
    "dog-chicken-cookie": ("dog", "treat", 170, "개"),
    "dog-pumpkin-pudding": ("dog", "treat", 250, ""),
    "dog-beef-pumpkin-meal": ("dog", "meal", 520, ""),
    "dog-salmon-broccoli-meal": ("dog", "meal", 520, ""),
    "dog-beef-jerky": ("dog", "treat", 130, "조각"),
    "dog-apple-chips": ("dog", "treat", 70, ""),
    "dog-carrot-egg-muffin": ("dog", "treat", 250, "개"),
    "dog-blueberry-yogurt-bark": ("dog", "treat", 310, "조각"),
    "dog-duck-sweetpotato-ball": ("dog", "treat", 300, "개"),
    "cat-chicken-pumpkin-mousse": ("cat", "treat", 180, ""),
    "cat-salmon-flake": ("cat", "treat", 90, ""),
    "cat-chicken-bugeo-soup": ("cat", "meal", 330, ""),
}

# (이름, 예시 품종, 체중 범위, 계산에 쓰는 대표 체중kg)
DOG_CLASSES = [
    ("초소형견", "치와와·요크셔테리어·토이푸들", "3kg 이하", 2.5),
    ("소형견", "말티즈·시츄·포메라니안·푸들", "3~7kg", 5),
    ("중형견", "비글·웰시코기·시바견·코카스파니엘", "7~15kg", 11),
    ("대형견", "진돗개·보더콜리·삽살개", "15~30kg", 22),
    ("초대형견", "골든리트리버·래브라도리트리버·셰퍼드", "30kg 이상", 35),
]
CAT_CLASSES = [
    ("작은 고양이", "작은 체구의 성묘", "3kg 안팎", 3),
    ("보통 고양이", "코리안숏헤어·러시안블루·브리티시숏헤어", "4~5kg", 4.5),
    ("큰 고양이", "메인쿤·노르웨이숲·랙돌", "6kg 이상", 7),
]
FACTOR = {"dog": 1.6, "cat": 1.2}
TREAT_SHARE = 0.10


def daily_kcal(kg: float, species: str) -> float:
    return 70 * kg ** 0.75 * FACTOR[species]


def info(r: dict, total_kcal: float) -> dict:
    """레시피의 급여 정보. FEED 에 없는 새 레시피는 이름과 재료 무게로 짐작한다."""
    if r["slug"] in FEED:
        species, kind, finished, unit = FEED[r["slug"]]
    else:
        species = "cat" if "고양이" in r["name"] else "dog"
        kind = "meal" if any(w in r["name"] for w in ("화식", "죽", "수프", "스튜")) else "treat"
        finished = sum(i["g"] for i in r["ingredients"] if i["n"] != "물") * 0.85 or 100
        unit = ""
    pieces = r["servings"] if unit else 0
    return {"species": species, "kind": kind, "finished": finished, "unit": unit, "pieces": pieces,
            "density": total_kcal / finished if finished else 0, "total": total_kcal}


def rows(inf: dict) -> list:
    """체급별 (이름, 예시, 체중, 하루 최대 kcal, 하루 최대 g, 하루 최대 개수 또는 None)."""
    out = []
    classes = DOG_CLASSES if inf["species"] == "dog" else CAT_CLASSES
    for name, ex, rng, kg in classes:
        kcal = daily_kcal(kg, inf["species"]) * TREAT_SHARE
        grams = kcal / inf["density"] if inf["density"] else 0
        grams = min(grams, inf["finished"])
        g = max(5, int(round(grams / 5.0) * 5)) if grams >= 4 else round(grams, 1)
        cnt = None
        if inf["pieces"]:
            per = inf["total"] / inf["pieces"]
            cnt = kcal / per if per else 0
        out.append((name, ex, rng, int(round(kcal)), g, cnt))
    return out


def count_text(c: float) -> str:
    """개수를 0.5 단위로(1개보다 적으면 1/4·1/2)."""
    if c >= 1:
        v = int(c * 2) / 2   # 넘치지 않게 0.5 단위로 내림
        return (str(int(v)) if v == int(v) else f"{v:.1f}")
    if c >= 0.7:
        return "3/4"
    if c >= 0.45:
        return "1/2"
    return "1/4"
