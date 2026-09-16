"""
공용 HTTP 클라이언트 래퍼.

프로젝트의 다른 모든 모듈은 `requests`를 직접 호출하지 않고 이 모듈의
`safe_get`/`safe_post`를 통해서만 네트워크에 접근한다. 이렇게 하면 "외부 API가
죽어도 파이프라인 전체가 죽지 않는다"는 우아한 저하(graceful degradation)
원칙을 한 곳에서 강제할 수 있다.

두 함수 모두 성공 시 `requests.Response`를, 실패(타임아웃/연결오류/HTTP예외) 시
`None`을 반환하며 절대 예외를 전파하지 않는다.
"""
from __future__ import annotations

from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT = 10
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutopostPipeline/1.0"
}


def get_session(retries: int = 3, backoff: float = 0.5) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET", "POST", "PUT"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(DEFAULT_HEADERS)
    return session


_SESSION = get_session()


def safe_get(url: str, *, timeout: int = DEFAULT_TIMEOUT, **kwargs: Any) -> Optional[requests.Response]:
    try:
        resp = _SESSION.get(url, timeout=timeout, **kwargs)
        return resp
    except requests.RequestException as exc:
        logger.warning("GET 실패 (%s): %s", url, exc)
        return None


def safe_post(url: str, *, timeout: int = DEFAULT_TIMEOUT, **kwargs: Any) -> Optional[requests.Response]:
    try:
        resp = _SESSION.post(url, timeout=timeout, **kwargs)
        return resp
    except requests.RequestException as exc:
        logger.warning("POST 실패 (%s): %s", url, exc)
        return None


def safe_put(url: str, *, timeout: int = DEFAULT_TIMEOUT, **kwargs: Any) -> Optional[requests.Response]:
    try:
        resp = _SESSION.put(url, timeout=timeout, **kwargs)
        return resp
    except requests.RequestException as exc:
        logger.warning("PUT 실패 (%s): %s", url, exc)
        return None
