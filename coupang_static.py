"""쿠팡 파트너스 고정 상품 링크(새 계정). Open API 키가 나오기 전까지는 이 링크만 쓴다.

글 제목·키워드에서 독자가 살 만한 상품을 골라 카드 한 장을 만든다. 맞는 상품이 없으면 돈·살림 주제 글에
무난한 가계부·책을 번갈아 쓴다(같은 글은 항상 같은 상품이 나오게 글자 합으로 정한다).
쿠팡 단축 링크는 뒤에 추적 파라미터를 붙이지 않는다(붙이면 링크가 깨질 수 있다).
상품을 늘리려면 PRODUCTS에 한 줄을 추가하면 된다.
"""
from __future__ import annotations

from typing import Dict, Optional

PRODUCTS = [
    {
        "key": "handwarmer",
        "name": "핫팩",
        "desc": "추운 날 외출 준비물",
        "url": "https://link.coupang.com/a/ietkrdq9wO",
        "words": ("난방", "에너지", "바우처", "겨울", "한파", "도시가스", "가스", "전기요금", "월동", "연탄"),
    },
    {
        "key": "kids_gloves",
        "name": "키즈 장갑",
        "desc": "아이 겨울 준비물",
        "url": "https://link.coupang.com/a/ietnFDb4sC",
        "words": ("아동", "양육", "육아", "보육", "영유아", "부모급여", "출산", "어린이", "자녀", "아이", "학부모", "학교", "장학", "방과후", "청소년", "교육"),
    },
    {
        "key": "water",
        "name": "생수",
        "desc": "자주 사는 생필품",
        "url": "https://link.coupang.com/a/ietpkl3ulo",
        "words": ("기초생활", "긴급복지", "생계", "차상위", "수급", "주거급여", "생활비", "생필품"),
    },
    {
        "key": "tissue",
        "name": "화장지",
        "desc": "자주 사는 생필품",
        "url": "https://link.coupang.com/a/ietqOkSUcm",
        "words": ("렌탈", "렌털", "이사", "자취", "살림", "정수기", "청소"),
    },
    {
        "key": "egg",
        "name": "계란",
        "desc": "장바구니 필수 식품",
        "url": "https://link.coupang.com/a/iets8XvF4m",
        "words": ("물가", "식비", "장바구니", "농식품", "식품", "급식", "푸드", "밥상"),
    },
    {
        "key": "budget_book",
        "name": "가계부",
        "desc": "지출을 적어 보는 첫걸음",
        "url": "https://link.coupang.com/a/ietvbA940W",
        "words": ("적금", "저축", "연금", "세금", "환급", "연말정산", "소득", "공제", "절약", "통신비", "요금", "irp", "isa", "계좌", "대출", "월세", "도약", "내일저축", "근로장려", "자산", "지원금"),
    },
    {
        "key": "book",
        "name": "책",
        "desc": "돈 공부 시작할 때",
        "url": "https://link.coupang.com/a/ietwvhq45c",
        "words": ("투자", "재테크", "청약", "주식", "펀드", "노후", "은퇴", "상속", "증여", "신용", "양도세", "배당"),
    },
    {
        "key": "power_bank",
        "name": "보조배터리",
        "desc": "외출·여행 필수 준비물",
        "url": "https://link.coupang.com/a/ieyQpiTPxs",
        "words": ("스마트폰", "휴대폰", "알뜰폰", "통신", "요금제", "데이터", "출장", "여행", "해외", "공항"),
    },
    {
        "key": "carrier",
        "name": "캐리어",
        "desc": "여행 준비물",
        "url": "https://link.coupang.com/a/ieyTek6n2O",
        "words": ("여행", "해외여행", "출국", "공항", "관광", "휴가"),
    },
    {
        "key": "travel_adapter",
        "name": "여행용 멀티어댑터",
        "desc": "해외 여행 준비물",
        "url": "https://link.coupang.com/a/ieyWrNy5cq",
        "words": ("해외", "출국", "해외여행", "유학", "워킹홀리데이"),
    },
    {
        "key": "passport_case",
        "name": "여권 지갑 케이스",
        "desc": "여권 챙길 때",
        "url": "https://link.coupang.com/a/ieyZCLOq3E",
        "words": ("여권", "출국", "해외", "비자", "출입국"),
    },
    {
        "key": "korean_snack_set",
        "name": "한국 컵라면·간식 세트",
        "desc": "해외에서 그리운 맛",
        "url": "https://link.coupang.com/a/iey4tUkxAO",
        "words": ("재외", "해외 거주", "유학생", "외국인", "교민", "워킹홀리데이"),
    },
    {
        "key": "dog_pad",
        "name": "강아지 배변패드",
        "desc": "반려견 필수 용품",
        "url": "https://link.coupang.com/a/iezvqUkTee",
        "words": ("반려", "반려동물", "반려견", "강아지", "펫", "동물등록", "유기동물", "동물병원"),
    },
    {
        "key": "dog_snack",
        "name": "강아지 간식",
        "desc": "반려견 간식",
        "url": "https://link.coupang.com/a/iezxn2D456",
        "words": ("반려", "반려동물", "반려견", "강아지", "펫"),
    },
    {
        "key": "cat_litter",
        "name": "고양이 모래",
        "desc": "반려묘 필수 용품",
        "url": "https://link.coupang.com/a/iezy78hdIq",
        "words": ("반려", "반려동물", "반려묘", "고양이", "펫", "동물등록"),
    },
    {
        "key": "cat_snack",
        "name": "고양이 간식",
        "desc": "반려묘 간식",
        "url": "https://link.coupang.com/a/iezAbeyTme",
        "words": ("반려", "반려동물", "반려묘", "고양이", "펫"),
    },
    {
        "key": "pet_wipes",
        "name": "반려동물 물티슈",
        "desc": "반려동물 위생 용품",
        "url": "https://link.coupang.com/a/iezCiIo7dQ",
        "words": ("반려", "반려동물", "펫"),
    },
    {
        "key": "tumbler",
        "name": "텀블러",
        "desc": "출근길 필수템",
        "url": "https://link.coupang.com/a/iezD5RCIHk",
        "words": ("직장인", "출근", "친환경", "탄소", "카페", "에너지 절약", "에너지절약", "텀블러"),
    },
    {
        "key": "sanitizer",
        "name": "손소독제",
        "desc": "위생·건강 필수품",
        "url": "https://link.coupang.com/a/iezF66NKXQ",
        "words": ("감염", "독감", "예방접종", "백신", "위생", "건강검진", "의료", "병원", "질병", "건강보험"),
    },
    {
        "key": "kids_snack",
        "name": "아이 간식",
        "desc": "아이 간식 걱정될 때",
        "url": "https://link.coupang.com/a/iezHPwh3fM",
        "words": ("어린이집", "유치원", "보육", "양육", "급식", "아이", "자녀"),
    },
    {
        "key": "wet_wipes",
        "name": "물티슈",
        "desc": "육아 필수품",
        "url": "https://link.coupang.com/a/iezKgAz2gC",
        "words": ("영유아", "출산", "신생아", "부모급여", "육아", "아동수당", "임신"),
    },
    {
        "key": "colored_pencils",
        "name": "색연필",
        "desc": "아이 학용품",
        "url": "https://link.coupang.com/a/iezNauOeSi",
        "words": ("초등", "학교", "학부모", "방과후", "교육", "장학", "입학", "돌봄"),
    },
]

_FALLBACK_KEYS = ("budget_book", "book")


def pick_static_product(text: str) -> Optional[Dict[str, str]]:
    """글 제목·키워드(text)와 가장 잘 맞는 상품을 돌려준다. 없으면 가계부·책 중 하나."""
    low = (text or "").lower()
    best, best_score, tied = None, 0, []
    for p in PRODUCTS:
        score = sum(1 for w in p["words"] if w in low)
        if score > best_score:
            best, best_score, tied = p, score, [p]
        elif score == best_score and score > 0:
            tied.append(p)
    if len(tied) > 1:  # 점수가 같으면 글마다 다른 상품이 나오도록 글자 합으로 고른다(같은 글은 늘 같은 상품)
        best = tied[sum(ord(c) for c in low) % len(tied)]
    if best is None:
        key = _FALLBACK_KEYS[sum(ord(c) for c in low) % len(_FALLBACK_KEYS)]
        best = next(p for p in PRODUCTS if p["key"] == key)
    return {"name": best["name"], "desc": best["desc"], "url": best["url"], "image": "", "price": "", "static": "1"}
