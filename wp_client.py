"""
멀티 워드프레스(사이트 A/B/C) REST API 통신 클라이언트.

사이트 A/B/C는 각각 독립된 워드프레스 설치이므로, `WordPressClient(site)`로
인스턴스를 만들어 사용한다. Application Password 기반 Basic Auth를 사용한다
(워드프레스 관리자 > 사용자 > 응용프로그램 비밀번호에서 발급).

이 모듈은 config/utils.http에만 의존하는 Layer 1 모듈이다.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional

from config import SiteConfig, get_site
from utils.http import safe_get, safe_post
from utils.logger import get_logger

logger = get_logger(__name__)

# 사이트별 영구 바이럴 계산기 페이지 (부트스트랩 시 1회 생성)
CALCULATOR_PAGES: Dict[str, List[Dict[str, str]]] = {
    "A": [
        {"slug": "calc/subsidy", "title": "정부지원금 모의 계산기"},
    ],
    "B": [
        {"slug": "calc/rent", "title": "통신비 렌탈료 비교 계산기"},
    ],
    "C": [
        {"slug": "calc/refund", "title": "세금환급 예상액 계산기"},
    ],
}


class WordPressClient:
    """단일 사이트(A/B/C)에 대한 워드프레스 REST API 클라이언트."""

    def __init__(self, site: str):
        self.site_key = site.upper().replace("SITE_", "")
        self.config: SiteConfig = get_site(site)

    @property
    def is_configured(self) -> bool:
        return self.config.is_wp_configured

    def _auth_header(self) -> Dict[str, str]:
        token = base64.b64encode(
            f"{self.config.wp_user}:{self.config.wp_pass}".encode("utf-8")
        ).decode("utf-8")
        return {"Authorization": f"Basic {token}"}

    def test_connection(self) -> Dict[str, Any]:
        """글을 쓰거나 만들지 않는, 자격증명 확인용 읽기 전용 호출.

        wp/v2/users/me는 인증된 사용자 정보만 조회하므로 사이트에 아무런
        데이터도 남기지 않는다 (API 연결 진단 전용).
        """
        if not self.is_configured:
            return {"ok": False, "reason": "not_configured"}
        resp = safe_get(self._api_url("wp/v2/users/me"), headers=self._auth_header(), timeout=10)
        if resp is not None and resp.status_code == 200:
            try:
                data = resp.json()
                return {"ok": True, "detail": data.get("name", "")}
            except ValueError:
                return {"ok": True, "detail": ""}
        return {"ok": False, "reason": f"http_{getattr(resp, 'status_code', 'none')}"}

    def _api_url(self, path: str) -> str:
        base = self.config.wp_url.rstrip("/")
        return f"{base}/wp-json/{path.lstrip('/')}"

    # ------------------------------------------------------------------
    # 게시글
    # ------------------------------------------------------------------
    def create_draft_post(
        self, title: str, html_content: str, category: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not self.is_configured:
            logger.warning("[Site %s] 워드프레스 미설정 - 초안 생성을 건너뜁니다.", self.site_key)
            return None

        payload: Dict[str, Any] = {
            "title": title,
            "content": html_content,
            "status": "draft",
        }
        if category:
            payload["categories"] = [category]

        resp = safe_post(
            self._api_url("wp/v2/posts"),
            headers={**self._auth_header(), "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=20,
        )
        if resp is None or resp.status_code not in (200, 201):
            logger.warning(
                "[Site %s] 초안 생성 실패: status=%s",
                self.site_key,
                getattr(resp, "status_code", "N/A"),
            )
            return None
        return resp.json()

    def publish_post(self, post_id: int) -> Optional[Dict[str, Any]]:
        return self.update_post(post_id, status="publish")

    def update_post(self, post_id: int, **fields: Any) -> Optional[Dict[str, Any]]:
        if not self.is_configured:
            logger.warning("[Site %s] 워드프레스 미설정 - 업데이트를 건너뜁니다.", self.site_key)
            return None

        resp = safe_post(
            self._api_url(f"wp/v2/posts/{post_id}"),
            headers={**self._auth_header(), "Content-Type": "application/json"},
            data=json.dumps(fields),
            timeout=20,
        )
        if resp is None or resp.status_code not in (200, 201):
            logger.warning(
                "[Site %s] 포스트(%s) 업데이트 실패: status=%s",
                self.site_key,
                post_id,
                getattr(resp, "status_code", "N/A"),
            )
            return None
        return resp.json()

    def get_recent_posts(self, days: int = 7, per_page: int = 20) -> List[Dict[str, Any]]:
        """최근 N일 이내 발행된 포스트 목록 (뉴스레터용)."""
        if not self.is_configured:
            return []
        resp = safe_get(
            self._api_url("wp/v2/posts"),
            headers=self._auth_header(),
            params={"per_page": per_page, "status": "publish", "orderby": "date", "order": "desc"},
            timeout=15,
        )
        if resp is None or resp.status_code != 200:
            return []
        try:
            return resp.json()
        except ValueError:
            return []

    # ------------------------------------------------------------------
    # 미디어
    # ------------------------------------------------------------------
    def upload_media(
        self, file_bytes: bytes, filename: str, mime_type: str = "image/jpeg"
    ) -> Optional[Dict[str, Any]]:
        if not self.is_configured:
            logger.warning("[Site %s] 워드프레스 미설정 - 미디어 업로드를 건너뜁니다.", self.site_key)
            return None

        headers = {
            **self._auth_header(),
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": mime_type,
        }
        resp = safe_post(
            self._api_url("wp/v2/media"), headers=headers, data=file_bytes, timeout=30
        )
        if resp is None or resp.status_code not in (200, 201):
            logger.warning(
                "[Site %s] 미디어 업로드 실패: status=%s",
                self.site_key,
                getattr(resp, "status_code", "N/A"),
            )
            return None
        return resp.json()

    # ------------------------------------------------------------------
    # 부트스트랩: 영구 바이럴 계산기 페이지
    # ------------------------------------------------------------------
    def create_calculator_pages(self) -> List[Dict[str, Any]]:
        """사이트 초기 구동 시 1회, 영구 바이럴용 계산기 페이지를 생성한다 (idempotent)."""
        if not self.is_configured:
            logger.warning("[Site %s] 워드프레스 미설정 - 계산기 페이지 생성을 건너뜁니다.", self.site_key)
            return []

        created: List[Dict[str, Any]] = []
        for page_def in CALCULATOR_PAGES.get(self.site_key, []):
            existing = safe_get(
                self._api_url("wp/v2/pages"),
                headers=self._auth_header(),
                params={"slug": page_def["slug"].split("/")[-1]},
                timeout=15,
            )
            if existing is not None and existing.status_code == 200 and existing.json():
                logger.info("[Site %s] 계산기 페이지 이미 존재: %s", self.site_key, page_def["slug"])
                continue

            payload = {
                "title": page_def["title"],
                "slug": page_def["slug"].split("/")[-1],
                "status": "publish",
                "content": (
                    f"<div id=\"benefit-calc-root\" data-page=\"{page_def['slug']}\">"
                    f"<h2>{page_def['title']}</h2>"
                    "<p>아래 계산기에 조건을 입력하면 예상 결과를 바로 확인할 수 있습니다.</p>"
                    "</div>"
                ),
            }
            resp = safe_post(
                self._api_url("wp/v2/pages"),
                headers={**self._auth_header(), "Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=20,
            )
            if resp is not None and resp.status_code in (200, 201):
                created.append(resp.json())
            else:
                logger.warning("[Site %s] 계산기 페이지 생성 실패: %s", self.site_key, page_def["slug"])
        return created
