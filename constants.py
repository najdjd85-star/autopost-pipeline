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

# ---- TTS ----
DEFAULT_TTS_VOICE = "ko-KR-InJoonNeural"

# ---- 영상 규격 ----
# 쇼츠는 720x1280으로 낮췄다 - 메모리가 작은(또는 앱별 메모리 상한이 걸린) 서버에서
# 1080x1920 렌더링 중 OOM으로 죽는 것을 실측으로 확인해서, 프레임당 메모리 사용량을
# 줄이기 위함이다(픽셀 수 약 44%로 감소). 쇼츠/릴스 플랫폼에서는 720p도 충분히
# 정상적인 화질이다.
SHORTS_SIZE = (720, 1280)   # 9:16 세로
LONGFORM_SIZE = (1920, 1080)  # 16:9 가로
THUMBNAIL_SIZE = (1000, 1500)  # 카드뉴스 썸네일

# ---- 영상 자막 스타일 (쇼츠/롱폼 공통 - 동일한 톤 유지) ----
CAPTION_FONT_SIZE = 92
CAPTION_COLOR = "#FFC400"
CAPTION_STROKE_WIDTH = 4
CAPTION_MAX_LINES = 2  # 한 컷당 자막은 2줄을 넘기지 않는다

# ---- 영상 마무리 멘트 (쇼츠는 스크립트 끝에, 롱폼은 마지막 챕터 끝에 붙는다) ----
OUTRO_MENTION = "자세한 사항은 고정 댓글 또는 프로필 링크 사이트를 참고하세요."

# ---- 이미지 생성 규격 ----
POLLINATIONS_IMAGE_SIZE = (1200, 675)

# ---- 쿠팡 파트너스 Open API 실패 시(예: 서버가 해외 IP라 차단되는 경우) 대체할
# 사이트별 고정 딥링크. 실시간 키워드 매칭은 아니지만 수수료 자체는 정상 발생한다. ----
COUPANG_FALLBACK_LINKS = {
    "A": "https://link.coupang.com/a/g5bcOwno5c",
    "B": "https://link.coupang.com/a/g5boawUePs",
    "C": "https://link.coupang.com/a/g5bqNuUPCK",
}

# ---- 공정거래위원회 필수 표기 문구 (모든 제휴 카드 - 쿠팡/애드픽/정적 링크 공통) ----
FTC_DISCLOSURE_TEXT = "이 포스팅은 제휴마케팅이 포함된 광고로 커미션을 지급 받습니다."

# ---- 링크프라이스 매체 승인 이벤트 참여 조건상 필수 표기 문구.
# AFF_* 정적 슬롯이 전부 링크프라이스 링크이므로 그 카드에만 붙인다. ----
LINKPRICE_EVENT_DISCLOSURE_TEXT = "이 포스팅은 링크프라이스 이벤트 참여를 위해 작성되었습니다."

# ---- Claude 모델 ----
# claude-3-5-sonnet-20241022는 더 이상 제공되지 않아(404 not_found_error) 최신 균형형 모델로 교체.
CLAUDE_MODEL = "claude-sonnet-5"

# ---- 콘텐츠 생성 필수 JSON 키 (generator.py 응답 스키마 검증용) ----
REQUIRED_GENERATOR_KEYS = (
    "title",
    "fact_summary",
    "html_content",
    "image_prompts",
    "shorts_script",
    "longform_chapters",
    "threads_post",
    "threads_comment",
    "ig_caption",
    "pinterest_desc",
)
