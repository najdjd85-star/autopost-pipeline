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
IMAGE_SLOT_2 = "<!-- IMAGE_SLOT_2 -->"
IMAGE_SLOTS = (IMAGE_SLOT_1, IMAGE_SLOT_2)

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
    SITE_A: "정부지원금",
    SITE_B: "통신비/렌탈 비교",
    SITE_C: "세금환급/연금",
}

SITE_BADGES = {
    SITE_A: "🏛️ 지원금",
    SITE_B: "📶 통신/렌탈",
    SITE_C: "💰 세금환급",
}

# ---- 사이트별 "공식 신청/조회 사이트" CTA용 실제 URL (전부 정부/공공기관 운영,
# 확인된 진짜 주소) - generator.py가 프롬프트에 그대로 박아서 Claude가
# href="#" 같은 가짜 링크를 만들지 않게 한다. ----
SITE_OFFICIAL_URLS = {
    SITE_A: "https://www.bokjiro.go.kr",  # 복지로 - 보건복지부 복지서비스 모의계산
    SITE_B: "https://www.smartchoice.or.kr",  # 스마트초이스 - 과기정통부·KTOA 통신요금 비교
    SITE_C: "https://www.hometax.go.kr",  # 홈택스 - 국세청 세금 환급/신고
}

THUMBNAIL_SIZE = (1000, 1500)  # 카드뉴스 썸네일

# ---- 이미지 생성 규격 ----
POLLINATIONS_IMAGE_SIZE = (1200, 675)

# ---- 쿠팡 파트너스 Open API 실패 시(예: 서버가 해외 IP라 차단되는 경우) 대체할
# 고정 딥링크. 세 사이트 다 동일한 "쿠팡 홈" 일반 링크를 쓴다 - 예전에는
# 사이트별로 서로 다른 특정 상품(생수 등) 딥링크였는데, 글 주제와 무관한
# 상품이 계속 노출되는 문제가 실측으로 확인되어 일반 링크로 통일했다. ----
COUPANG_FALLBACK_LINKS = {
    "A": "https://link.coupang.com/a/hfBRjMrEgC",
    "B": "https://link.coupang.com/a/hfBRjMrEgC",
    "C": "https://link.coupang.com/a/hfBRjMrEgC",
}

# ---- 공정거래위원회 필수 표기 문구 (모든 제휴 카드 - 쿠팡/애드픽/정적 링크 공통) ----
FTC_DISCLOSURE_TEXT = "이 포스팅은 제휴마케팅이 포함된 광고로 커미션을 지급 받습니다."

# ---- 링크프라이스 매체 승인 이벤트 참여 조건상 필수 표기 문구.
# AFF_* 정적 슬롯이 전부 링크프라이스 링크이므로 그 카드에만 붙인다. ----
LINKPRICE_EVENT_DISCLOSURE_TEXT = "이 포스팅은 링크프라이스 이벤트 참여를 위해 작성되었습니다."

# ---- 쿠팡 파트너스 운영정책상 필수 표기 문구(정확히 이 문구를 요구함).
# 쿠팡 카드가 실제로 삽입된 글에만 붙인다. ----
COUPANG_DISCLOSURE_TEXT = (
    "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
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
    "fact_summary",
    "html_content",
    "image_prompts",
    "threads_post",
    "threads_comment",
    "pinterest_desc",
)
