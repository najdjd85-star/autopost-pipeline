"""
프로젝트 전역에서 공유되는 상수 모음.

여기 정의된 슬롯 플레이스홀더 토큰은 generator.py가 콘텐츠를 생성할 때 본문에
삽입하고, image_hybrid_engine.py / smart_affiliate_matcher.py가 그대로 찾아서
치환한다. 문자열을 각 파일에 따로 하드코딩하면 오타로 계약이 깨지기 쉬우므로
반드시 이 모듈을 통해서만 참조한다.

이 파일은 프로젝트 내부의 다른 모듈을 임포트하지 않는 최하단 리프(leaf) 모듈이다.
"""

# ---- 이미지 슬롯 플레이스홀더 (generator.py가 html_content 안에 삽입) ----
IMAGE_SLOT_1 = "<!-- IMAGE_SLOT_1 -->"

# ---- 검증된 계산기 라이브러리 슬롯 (calculator_library.py가 치환) ----
CALCULATOR_SLOT = "<!-- CALCULATOR_SLOT -->"

# ---- 제휴(CPA/쿠팡) 슬롯 플레이스홀더 ----
AFFILIATE_SLOT_TOP = "<!-- AFFILIATE_SLOT_TOP -->"
AFFILIATE_SLOT_MID = "<!-- AFFILIATE_SLOT_MID -->"
AFFILIATE_SLOT_BOT = "<!-- AFFILIATE_SLOT_BOT -->"
AFFILIATE_SLOTS = {
    "top": AFFILIATE_SLOT_TOP,
    "mid": AFFILIATE_SLOT_MID,
    "bot": AFFILIATE_SLOT_BOT,
}

# ---- 사이트 식별자 ----
SITE_A = "A"  # 정부지원금
SITE_B = "B"  # 통신비/렌탈 비교
SITE_C = "C"  # 세금환급/연금
SITE_KEYS = (SITE_A, SITE_B, SITE_C)

SITE_CLI_ALIASES = {
    "site_a": SITE_A,
    "site_b": SITE_B,
    "site_c": SITE_C,
}

SITE_LABELS = {
    SITE_A: "정부지원금·주거(청약·임대)·복지",
    SITE_B: "생활비 절약(통신·교통·에너지·보험·금융)",
    SITE_C: "세금·절세(개인·사업자·법인)",
}

SITE_BADGES = {
    SITE_A: "🏛️ 지원금",
    SITE_B: "💡 생활비 절약",
    SITE_C: "💰 세금환급",
}

# ---- 사이트별 워드프레스 카테고리 - generator.py가 이 중 하나를 글 주제에 맞게
# 골라 반환하고, telegram_bot.py가 발행 시 그대로 넘긴다. 전부 "Uncategorized"로
# 쌓이던 문제(발행 코드가 카테고리를 아예 안 넘겨서 생긴 버그) 수정의 일환. ----
SITE_CATEGORIES = {
    SITE_A: ("복지·지원금", "주거지원", "연금", "청년지원", "육아·출산", "고용·교육", "주택청약·분양", "임대·주거금융", "건강·의료"),
    SITE_B: ("통신비", "렌탈", "인터넷·결합", "해외로밍", "교통비", "에너지·공과금", "보험·금융", "생활비 절약"),
    SITE_C: ("연말정산", "종합소득세", "국민연금", "해외주식 세금", "증여·상속", "절세계좌", "부동산 세금", "개인연금·퇴직", "개인사업자", "법인·절세"),
}

# ---- 사이트별 "공식 신청/조회 사이트" CTA용 실제 URL (전부 정부/공공기관 운영,
# 확인된 진짜 주소) - generator.py가 프롬프트에 그대로 박아서 Claude가
# href="#" 같은 가짜 링크를 만들지 않게 한다. ----
SITE_OFFICIAL_URLS = {
    SITE_A: "https://www.bokjiro.go.kr",  # 복지로 - 보건복지부 복지서비스 모의계산
    SITE_B: "https://www.smartchoice.or.kr",  # 스마트초이스 - 과기정통부·KTOA 통신요금 비교
    SITE_C: "https://www.hometax.go.kr",  # 홈택스 - 국세청 세금 환급/신고
}

# ---- 사이트별 "참고 출처" 공식 기관 (글 하단 출처 박스와 소개 페이지에서 공유) ----
SITE_SOURCES = {
    SITE_A: (
        ("복지로", "https://www.bokjiro.go.kr"),
        ("정부24", "https://www.gov.kr"),
        ("보건복지부", "https://www.mohw.go.kr"),
    ),
    SITE_B: (
        ("스마트초이스", "https://www.smartchoice.or.kr"),
        ("방송통신위원회", "https://www.kcc.go.kr"),
        ("한국소비자원", "https://www.kca.go.kr"),
    ),
    SITE_C: (
        ("국세청 홈택스", "https://www.hometax.go.kr"),
        ("국세청", "https://www.nts.go.kr"),
        ("국민연금공단", "https://www.nps.or.kr"),
    ),
}

# ---- 주제별 공식 사이트(글 하단 "공식 신청" 버튼 + 출처 박스). 키워드에 아래 낱말이 있으면 그 기관으로 연결한다.
# 사이트 기본값은 위 SITE_OFFICIAL_URLS. 확실히 아는 공식 주소만 넣는다(모르면 넣지 않고 사이트 기본값 사용). ----
OFFICIAL_URL_RULES = {
    SITE_A: (
        ("청약|분양|특별공급|신혼희망타운|무순위", "청약홈", "https://www.applyhome.co.kr"),
        ("공공임대|영구임대|행복주택|국민임대|통합공공임대|전세임대|매입임대|장기전세|LH", "LH청약플러스", "https://apply.lh.or.kr"),
        ("디딤돌|버팀목|전세자금|전세보증금|신생아 특례|월세대출|주택도시기금", "주택도시기금", "https://nhuf.molit.go.kr"),
        ("전세사기", "국토교통부", "https://www.molit.go.kr"),
        ("학자금|장학금", "한국장학재단", "https://www.kosaf.go.kr"),
        ("육아휴직|출산휴가|고용보험|실업급여|일자리도약", "고용보험", "https://www.ei.go.kr"),
        ("재난적의료비|본인부담상한|산정특례|의료급여|치매", "국민건강보험공단", "https://www.nhis.or.kr"),
        ("장기요양", "노인장기요양보험", "https://www.longtermcare.or.kr"),
    ),
    SITE_B: (
        ("전기요금|에너지캐시백|누진|공과금", "한전 사이버지점", "https://cyber.kepco.co.kr"),
        ("실손|자동차보험|운전자보험", "보험다모아", "https://e-insmarket.or.kr"),
        ("신용점수|금리인하|대출 갈아타기|중도상환|파킹통장|체크카드|연회비|주거래은행", "금융감독원 파인", "https://fine.fss.or.kr"),
        ("K-패스|기후동행|알뜰교통|정기권|교통", "정부24", "https://www.gov.kr"),
        ("구독|OTT|배달|장보기|주유|중고거래|폐가전|이사|가계부|고정비|병원비|직구|항공권|자취|난방비|수도요금|에너지효율|가전", "정부24", "https://www.gov.kr"),
    ),
    SITE_C: (
        ("노란우산", "노란우산", "https://www.8899.or.kr"),
        ("법인 설립|법인 폐업|청산", "인터넷등기소", "https://www.iros.go.kr"),
        ("국민연금", "국민연금공단", "https://www.nps.or.kr"),
        ("주택연금", "한국주택금융공사", "https://www.hf.go.kr"),
        ("세액감면|세액공제|통합투자|연구인력|법인세|접대비|가지급금|업무용 승용차|법인", "국세청", "https://www.nts.go.kr"),
    ),
}


def official_for(site: str, keyword: str):
    """키워드에 맞는 공식 기관 (이름, 주소). 맞는 규칙이 없으면 None(사이트 기본값을 쓴다)."""
    import re as _re

    for pat, name, url in OFFICIAL_URL_RULES.get(site, ()):
        if _re.search(pat, keyword or ""):
            return name, url
    return None


def official_url_for(site: str, keyword: str) -> str:
    hit = official_for(site, keyword)
    return hit[1] if hit else SITE_OFFICIAL_URLS.get(site, "")


THUMBNAIL_SIZE = (1000, 1500)  # 카드뉴스 썸네일

# ---- 이미지 생성 규격 ----
POLLINATIONS_IMAGE_SIZE = (1200, 675)

# ---- 쿠팡 파트너스 Open API 사용 여부. 계정을 바꾸면서 새 계정의 API 키가 나올 때까지 끈다(고정 링크만 사용).
# 새 키를 .env에 넣은 뒤 COUPANG_API_ENABLED=1로 켠다. 고정 상품 링크는 coupang_static.py. ----
import os as _os

COUPANG_API_ENABLED = _os.environ.get("COUPANG_API_ENABLED", "0") == "1"

# ---- 공정거래위원회 필수 표기 문구 (제휴 카드가 있는 글) ----
FTC_DISCLOSURE_TEXT = "이 포스팅은 제휴마케팅이 포함된 광고로 커미션을 지급 받습니다."

# ---- 쿠팡 파트너스 운영정책상 필수 표기 문구(정확히 이 문구를 요구함).
# 쿠팡 카드가 실제로 삽입된 글에만 붙인다. ----
COUPANG_DISCLOSURE_TEXT = (
    "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
)

# ---- 모의 계산기 면책 문구 (generator가 만든 benefit-calc 위젯 바로 아래에 코드로 삽입) ----
CALCULATOR_DISCLAIMER_TEXT = (
    "※ 위 계산기는 이해를 돕기 위한 참고용 모의 계산이며, 실제 자격 판정·금액과 다를 수 있습니다. "
    "정확한 결과는 반드시 해당 공식 기관 사이트에서 확인하세요."
)

# ---- Claude 모델 ----
# claude-3-5-sonnet-20241022는 더 이상 제공되지 않아(404 not_found_error) 최신 균형형 모델로 교체.
CLAUDE_MODEL = "claude-sonnet-5"

# ---- 콘텐츠 생성 필수 JSON 키 (generator.py 응답 스키마 검증용) ----
# 영상(쇼츠/롱폼) 렌더링을 지원하지 않으므로 shorts_script/longform_chapters는
# 요구하지 않는다 - 어차피 안 쓸 콘텐츠를 Claude에게 만들게 해서 토큰을
# 낭비할 이유가 없다.
REQUIRED_GENERATOR_KEYS = (
    "title",
    "category",
    "calculator_type",
    "slug",
    "fact_summary",
    "html_content",
    "image_prompts",
    "threads_post",
    "threads_comment",
    "pinterest_desc",
)
