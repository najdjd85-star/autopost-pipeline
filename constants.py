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
SHORTS_SIZE = (1080, 1920)   # 9:16 세로
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

# ---- 공정거래위원회 필수 표기 문구 ----
FTC_DISCLOSURE_TEXT = (
    "이 포스팅은 파트너스 활동을 통해 일정 수수료를 제공받을 수 있습니다."
)

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
