"""
전역 설정 로더.

프로젝트의 모든 모듈은 이 파일을 통해서만 환경설정 값을 읽는다.
    from config import settings

설계 원칙 (중요):
- `.env`가 없거나 어떤 키가 비어 있어도 이 모듈의 `import`는 절대 실패하지 않는다.
  (순수 문자열 읽기 + 기본값만 사용하고, 검증 실패 시에도 예외를 던지지 않는다.)
- 실제 "필수 키가 없다"는 사실을 알리는 것은 `validate_config()`의 책임이며,
  이 함수는 main.py 시작 시점에 명시적으로 호출되어 로그만 남긴다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
OUTPUT_DIR = DATA_DIR / "output"

# .env가 없어도 load_dotenv는 조용히 아무 것도 하지 않고 반환한다 (예외 없음).
load_dotenv(BASE_DIR / ".env", override=False)


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default) or default


def _get_float(key: str, default: float) -> float:
    raw = os.environ.get(key, "")
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class SiteConfig:
    """사이트 A/B/C 공통 워드프레스 + 제휴 링크 설정."""

    key: str
    label: str
    wp_url: str
    wp_user: str
    wp_pass: str
    affiliates: Dict[str, str] = field(default_factory=dict)

    @property
    def is_wp_configured(self) -> bool:
        return bool(self.wp_url and self.wp_user and self.wp_pass)


@dataclass(frozen=True)
class Settings:
    # 공통
    anthropic_api_key: str
    telegram_bot_token: str
    telegram_admin_chat_id: str
    schedule_time: str
    pexels_api_key: str
    google_key_path: str
    auto_publish_timeout_hours: float

    # 뉴스레터
    resend_api_key: str
    sender_email: str
    newsletter_schedule_time: str

    # 네이버 / 공공데이터
    naver_client_id: str
    naver_client_secret: str
    public_data_api_key: str

    # 쿠팡 (선택)
    coupang_access_key: str
    coupang_secret_key: str

    # 애드픽 (선택) - 캠페인 리스트 API용 회원 식별자(affid)
    adpick_affid: str

    # 소셜
    threads_access_token: str
    ig_access_token: str
    ig_user_id: str
    pinterest_access_token: str
    pinterest_board_id: str

    # 유튜브
    youtube_client_secrets_path: str
    youtube_token_path: str
    youtube_api_key: str  # 업로드용 OAuth와 별개인, 검색/조회 전용 단순 API 키

    # 사이트별
    sites: Dict[str, SiteConfig]

    @property
    def coupang_configured(self) -> bool:
        return bool(self.coupang_access_key and self.coupang_secret_key)


def _load_sites() -> Dict[str, SiteConfig]:
    return {
        "A": SiteConfig(
            key="A",
            label="정부지원금",
            wp_url=_get("WP_A_URL"),
            wp_user=_get("WP_A_USER"),
            wp_pass=_get("WP_A_PASS"),
            affiliates={
                "loan": _get("AFF_A_LOAN"),
                "welfare": _get("AFF_A_WELFARE"),
            },
        ),
        "B": SiteConfig(
            key="B",
            label="통신비/렌탈 비교",
            wp_url=_get("WP_B_URL"),
            wp_user=_get("WP_B_USER"),
            wp_pass=_get("WP_B_PASS"),
            affiliates={
                "mvno": _get("AFF_B_MVNO"),
                "rental": _get("AFF_B_RENTAL"),
                "internet": _get("AFF_B_INTERNET"),
            },
        ),
        "C": SiteConfig(
            key="C",
            label="세금환급/연금",
            wp_url=_get("WP_C_URL"),
            wp_user=_get("WP_C_USER"),
            wp_pass=_get("WP_C_PASS"),
            affiliates={
                "refund": _get("AFF_C_REFUND"),
                "pension": _get("AFF_C_PENSION"),
            },
        ),
    }


def load_settings() -> Settings:
    return Settings(
        anthropic_api_key=_get("ANTHROPIC_API_KEY"),
        telegram_bot_token=_get("TELEGRAM_BOT_TOKEN"),
        telegram_admin_chat_id=_get("TELEGRAM_ADMIN_CHAT_ID"),
        schedule_time=_get("SCHEDULE_TIME", "07:00"),
        pexels_api_key=_get("PEXELS_API_KEY"),
        google_key_path=_get("GOOGLE_KEY_PATH", "service_account.json"),
        auto_publish_timeout_hours=_get_float("AUTO_PUBLISH_TIMEOUT_HOURS", 1.0),
        resend_api_key=_get("RESEND_API_KEY"),
        sender_email=_get("SENDER_EMAIL", "newsletter@your-domain.com"),
        newsletter_schedule_time=_get("NEWSLETTER_SCHEDULE_TIME", "Monday 08:00"),
        naver_client_id=_get("NAVER_CLIENT_ID"),
        naver_client_secret=_get("NAVER_CLIENT_SECRET"),
        public_data_api_key=_get("PUBLIC_DATA_API_KEY"),
        coupang_access_key=_get("COUPANG_ACCESS_KEY"),
        coupang_secret_key=_get("COUPANG_SECRET_KEY"),
        adpick_affid=_get("ADPICK_AFFID"),
        threads_access_token=_get("THREADS_ACCESS_TOKEN"),
        ig_access_token=_get("IG_ACCESS_TOKEN"),
        ig_user_id=_get("IG_USER_ID"),
        pinterest_access_token=_get("PINTEREST_ACCESS_TOKEN"),
        pinterest_board_id=_get("PINTEREST_BOARD_ID"),
        youtube_client_secrets_path=_get("YOUTUBE_CLIENT_SECRETS_PATH", "client_secret.json"),
        youtube_token_path=_get("YOUTUBE_TOKEN_PATH", "youtube_token.json"),
        youtube_api_key=_get("YOUTUBE_API_KEY"),
        sites=_load_sites(),
    )


# 모듈 로드 시 1회 생성되는 싱글턴. 부작용 없는 순수 읽기 연산만 수행하므로
# 어떤 키가 비어 있어도 `import config`는 항상 성공한다.
settings = load_settings()

# 디렉토리는 있으면 재사용, 없으면 생성 (이 자체도 예외를 던지지 않도록 방어).
for _d in (DATA_DIR, LOG_DIR, OUTPUT_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def validate_config(s: Settings = settings) -> Dict[str, List[str]]:
    """설정 상태를 점검해 보고서를 반환한다. 어떤 경우에도 예외를 던지지 않는다.

    main.py 시작 시점 및 테스트에서 명시적으로 호출된다 (import 시점에는 호출 안 함).
    """
    required = {
        "ANTHROPIC_API_KEY": s.anthropic_api_key,
    }
    optional = {
        "TELEGRAM_BOT_TOKEN": s.telegram_bot_token,
        "TELEGRAM_ADMIN_CHAT_ID": s.telegram_admin_chat_id,
        "PEXELS_API_KEY": s.pexels_api_key,
        "RESEND_API_KEY": s.resend_api_key,
        "NAVER_CLIENT_ID": s.naver_client_id,
        "NAVER_CLIENT_SECRET": s.naver_client_secret,
        "PUBLIC_DATA_API_KEY": s.public_data_api_key,
        "COUPANG_ACCESS_KEY": s.coupang_access_key,
        "THREADS_ACCESS_TOKEN": s.threads_access_token,
        "IG_ACCESS_TOKEN": s.ig_access_token,
        "PINTEREST_ACCESS_TOKEN": s.pinterest_access_token,
        "GOOGLE_KEY_PATH(파일존재)": s.google_key_path if Path(s.google_key_path).exists() else "",
        "YOUTUBE_API_KEY": s.youtube_api_key,
        "WP_A_URL": s.sites["A"].wp_url,
        "WP_B_URL": s.sites["B"].wp_url,
        "WP_C_URL": s.sites["C"].wp_url,
    }

    report = {
        "missing_required": [k for k, v in required.items() if not v],
        "missing_optional": [k for k, v in optional.items() if not v],
    }

    import logging

    logger = logging.getLogger("config")
    for k in report["missing_required"]:
        logger.warning("[필수 설정 누락] %s -> 이 값을 사용하는 기능은 호출 시 예외를 발생시킵니다.", k)
    for k in report["missing_optional"]:
        logger.info("[선택 설정 누락] %s -> 관련 기능이 자동으로 스킵/폴백됩니다.", k)
    return report


def get_site(site_key: str) -> SiteConfig:
    """'A'/'B'/'C' 또는 'site_a'/'site_b'/'site_c' 어느 표기든 받아들인다."""
    key = site_key.upper()
    if key.startswith("SITE_"):
        key = key.replace("SITE_", "")
    if key not in settings.sites:
        raise KeyError(f"알 수 없는 site 키: {site_key!r} (A/B/C 중 하나여야 합니다)")
    return settings.sites[key]
