"""
Claude(generator.py)는 전혀 호출하지 않고, 나머지 외부 API 연동만 점검하는
진단 스크립트. 전부 읽기 전용/무료성 호출이라 콘텐츠 발행이나 메일 발송 같은
부작용이 없고, Anthropic 토큰도 전혀 소모하지 않는다.

사용법:
    venv\\Scripts\\python.exe scripts\\check_apis.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from competitor_analyzer import search_naver_blogs  # noqa: E402
from config import settings  # noqa: E402
from keyword_expander import NAVER_AUTOCOMPLETE_URL  # noqa: E402
from smart_affiliate_matcher import build_coupang_deeplink  # noqa: E402
from trend_scraper import (  # noqa: E402
    GOOGLE_TRENDS_DAILY_RSS_KR,
    POLICY_BRIEFING_RSS,
    fetch_public_data_subsidies,
)
from utils.http import safe_get  # noqa: E402
from video_trend_analyzer import get_trending_videos  # noqa: E402
from wp_client import WordPressClient  # noqa: E402

OK, SKIP, ERR = "OK", "SKIP", "ERR"
ICON = {OK: "✅", SKIP: "⏭️ ", ERR: "❌"}


def _result(status: str, name: str, detail: str = "") -> Dict[str, str]:
    return {"status": status, "name": name, "detail": detail}


# ---------------------------------------------------------------------------
# 개별 점검 함수 (전부 읽기 전용 / 무료성 호출)
# ---------------------------------------------------------------------------
def check_wordpress(site_key: str) -> Dict[str, str]:
    wp = WordPressClient(site_key)
    name = f"WordPress Site {site_key}"
    if not wp.is_configured:
        return _result(SKIP, name, "WP_*_URL/USER/PASS 미설정")
    result = wp.test_connection()
    if result["ok"]:
        return _result(OK, name, f"인증 성공 (사용자: {result.get('detail','')})")
    return _result(ERR, name, result.get("reason", ""))


def check_telegram() -> Dict[str, str]:
    name = "Telegram Bot"
    if not settings.telegram_bot_token:
        return _result(SKIP, name, "TELEGRAM_BOT_TOKEN 미설정")
    resp = safe_get(f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe", timeout=10)
    if resp is not None and resp.status_code == 200:
        bot_info = resp.json().get("result", {})
        return _result(OK, name, f"봇 확인됨 (@{bot_info.get('username','')})")
    if resp is not None and resp.status_code == 401:
        return _result(ERR, name, "토큰이 올바르지 않습니다 (401)")
    return _result(ERR, name, f"status={getattr(resp,'status_code','N/A')}")


def check_pexels() -> Dict[str, str]:
    name = "Pexels API"
    if not settings.pexels_api_key:
        return _result(SKIP, name, "PEXELS_API_KEY 미설정 (Pollinations.ai로 자동 폴백됨)")
    resp = safe_get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": settings.pexels_api_key},
        params={"query": "test", "per_page": 1},
        timeout=10,
    )
    if resp is not None and resp.status_code == 200:
        return _result(OK, name, "정상 응답")
    return _result(ERR, name, f"status={getattr(resp,'status_code','N/A')}")


def check_naver_search_api() -> Dict[str, str]:
    name = "네이버 검색 API (NAVER API HUB, 블로그)"
    if not (settings.naver_client_id and settings.naver_client_secret):
        return _result(SKIP, name, "NAVER_CLIENT_ID/SECRET 미설정")
    results = search_naver_blogs("테스트", display=1)
    if results:
        return _result(OK, name, f"검색 결과 {len(results)}건 수신")
    return _result(ERR, name, "결과 없음 또는 인증 실패 (로그 확인 필요)")


def check_naver_autocomplete() -> Dict[str, str]:
    name = "네이버 자동완성 (비공식)"
    resp = safe_get(NAVER_AUTOCOMPLETE_URL, params={"q": "테스트", "con": 1}, timeout=6)
    if resp is not None and resp.status_code == 200:
        return _result(OK, name, "응답 수신 (비공식 API - 접미사 휴리스틱이 항상 폴백으로 병행됨)")
    return _result(ERR, name, "응답 실패 - 접미사 휴리스틱 폴백만 사용됩니다")


def check_public_data_portal() -> Dict[str, str]:
    name = "공공데이터포털 (보조금24)"
    if not settings.public_data_api_key:
        return _result(SKIP, name, "PUBLIC_DATA_API_KEY 미설정")
    items = fetch_public_data_subsidies(limit=1)
    if items:
        return _result(OK, name, f"{len(items)}건 수신")
    return _result(ERR, name, "응답 없음 (키/쿼터 확인 필요)")


def check_free_rss_sources() -> List[Dict[str, str]]:
    results = []
    for name, url in (
        ("정책브리핑 RSS", POLICY_BRIEFING_RSS),
        ("구글 트렌드 RSS", GOOGLE_TRENDS_DAILY_RSS_KR),
    ):
        resp = safe_get(url, timeout=8)
        if resp is not None and resp.status_code == 200:
            results.append(_result(OK, name, "접근 가능 (키 불필요)"))
        else:
            results.append(_result(ERR, name, "접근 실패 - trend_scraper가 자동으로 건너뜁니다"))
    return results


def check_coupang() -> Dict[str, str]:
    name = "쿠팡 파트너스 Open API"
    if not settings.coupang_configured:
        return _result(SKIP, name, "COUPANG_ACCESS_KEY/SECRET_KEY 미설정 (선택 기능)")
    product = build_coupang_deeplink("테스트")
    if product:
        return _result(OK, name, f"딥링크 생성 성공: {product.get('name','')[:30]}")
    return _result(ERR, name, "딥링크 생성 실패 (키/서명 확인 필요)")


def check_resend() -> Dict[str, str]:
    name = "Resend (이메일)"
    if not settings.resend_api_key:
        return _result(SKIP, name, "RESEND_API_KEY 미설정")
    resp = safe_get(
        "https://api.resend.com/domains",
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        timeout=10,
    )
    if resp is not None and resp.status_code == 200:
        return _result(OK, name, "인증 성공 (메일 발송 없음)")
    return _result(ERR, name, f"status={getattr(resp,'status_code','N/A')}")


def check_meta_graph(token_name: str, token: str, api_base: str, fields: str = "id,username") -> Dict[str, str]:
    if not token:
        return _result(SKIP, token_name, "토큰 미설정")
    resp = safe_get(f"{api_base}/me", params={"fields": fields, "access_token": token}, timeout=10)
    if resp is not None and resp.status_code == 200:
        data = resp.json()
        return _result(OK, token_name, f"인증 성공 (id={data.get('id','')})")
    status = getattr(resp, "status_code", "N/A")
    body = getattr(resp, "text", "")[:200] if resp is not None else ""
    return _result(ERR, token_name, f"status={status} {body}")


def check_pinterest() -> Dict[str, str]:
    name = "Pinterest API"
    if not settings.pinterest_access_token:
        return _result(SKIP, name, "PINTEREST_ACCESS_TOKEN 미설정")
    resp = safe_get(
        "https://api.pinterest.com/v5/user_account",
        headers={"Authorization": f"Bearer {settings.pinterest_access_token}"},
        timeout=10,
    )
    if resp is not None and resp.status_code == 200:
        return _result(OK, name, "인증 성공")
    return _result(ERR, name, f"status={getattr(resp,'status_code','N/A')}")


def check_google_service_account() -> Dict[str, str]:
    name = "Google 서비스 계정 (서치콘솔/색인)"
    key_path = Path(settings.google_key_path)
    if not key_path.exists():
        return _result(SKIP, name, f"{key_path} 파일 없음")
    try:
        from google.oauth2 import service_account

        service_account.Credentials.from_service_account_file(str(key_path))
        return _result(OK, name, "키 파일 파싱 성공 (실제 API 호출은 하지 않음)")
    except Exception as exc:  # noqa: BLE001
        return _result(ERR, name, f"키 파일 파싱 실패: {exc}")


def check_youtube_oauth() -> Dict[str, str]:
    name = "YouTube OAuth 토큰"
    secrets_path = Path(settings.youtube_client_secrets_path)
    token_path = Path(settings.youtube_token_path)
    if not secrets_path.exists() or not token_path.exists():
        return _result(SKIP, name, f"{secrets_path.name} 또는 {token_path.name} 없음")
    return _result(OK, name, "두 파일 모두 존재 (실제 업로드 시 토큰 유효성 검증됨)")


def check_youtube_trend_search() -> Dict[str, str]:
    name = "YouTube 트렌드 검색 (YOUTUBE_API_KEY)"
    if not settings.youtube_api_key:
        return _result(SKIP, name, "YOUTUBE_API_KEY 미설정 - 트렌드 참고 없이 진행됨")
    trends = get_trending_videos("생계급여", months=3, max_results=5)
    total = len(trends.get("shorts", [])) + len(trends.get("longform", []))
    if total > 0:
        return _result(OK, name, f"관련 영상 {total}건 조회 성공")
    return _result(ERR, name, "결과 0건 (키/쿼터 확인 필요)")


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 64)
    print(" 공통 API 연결 진단 (Claude/generator.py는 호출하지 않음 - 토큰 0 소모)")
    print("=" * 64)

    checks: List[Dict[str, str]] = []
    checks.append(check_wordpress("A"))
    checks.append(check_wordpress("B"))
    checks.append(check_wordpress("C"))
    checks.append(check_telegram())
    checks.append(check_pexels())
    checks.append(check_naver_search_api())
    checks.append(check_naver_autocomplete())
    checks.append(check_public_data_portal())
    checks.extend(check_free_rss_sources())
    checks.append(check_coupang())
    checks.append(check_resend())
    checks.append(
        check_meta_graph(
            "Instagram API (Instagram Login)",
            settings.ig_access_token,
            "https://graph.instagram.com/v25.0",
            fields="id,username,account_type",
        )
    )
    checks.append(check_meta_graph("Threads API", settings.threads_access_token, "https://graph.threads.net/v1.0"))
    checks.append(check_pinterest())
    checks.append(check_google_service_account())
    checks.append(check_youtube_oauth())
    checks.append(check_youtube_trend_search())

    for c in checks:
        icon = ICON[c["status"]]
        print(f"{icon} [{c['status']:4}] {c['name']:<32} {c['detail']}")

    ok = sum(1 for c in checks if c["status"] == OK)
    skip = sum(1 for c in checks if c["status"] == SKIP)
    err = sum(1 for c in checks if c["status"] == ERR)
    print("-" * 64)
    print(f"OK {ok} / SKIP(미설정) {skip} / ERROR {err}  (총 {len(checks)}개 항목)")
    print("Claude API는 호출하지 않았습니다 - 이 진단으로는 토큰이 전혀 소모되지 않습니다.")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
