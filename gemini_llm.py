"""무료 Gemini(키 여러 개 순환)로 처리하는 가벼운 글 작업.

Claude 비용을 줄이려고, 품질 차이가 작은 일(스레드 일상 글, 뉴스레터 요약, 상위 글 구조 분석, 순위 방어 리라이팅 초안)은
먼저 Gemini로 시도하고, 실패하면 None을 돌려 호출부가 기존 Claude 호출로 대신하게 한다(서비스가 멈추지 않게).
본문 글 생성과 공식 기준 조사(웹 검색)는 정확성이 중요해 Claude에 그대로 둔다.

- 키: .env 의 GEMINI_API_KEYS (gemini_keys.py가 한도 초과·오류 키를 쉬게 하며 돌려 쓴다)
- 끄기: GEMINI_LLM_ENABLED=0 이면 Gemini를 쓰지 않고 바로 Claude로 간다.
- 사용 기록: api_usage.jsonl 에 kind="gemini"로 남는다(무료라 Claude 예산·호출 수에는 넣지 않는다).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Optional

import requests

import gemini_keys
from llm_usage import record_gemini
from utils.logger import get_logger

logger = get_logger(__name__)

MODELS = {"flash": "gemini-flash-latest", "lite": "gemini-flash-lite-latest"}
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def enabled() -> bool:
    return os.environ.get("GEMINI_LLM_ENABLED", "1").strip() != "0" and gemini_keys.has_keys()


class _TimedOut:
    """시간 초과를 504처럼 돌려줘서 키 순환을 멈추게 한다(모델 서버가 느린 것이라 키를 바꿔도 소용없고, 키마다 3분씩 기다리게 된다)."""
    status_code = 504
    text = "timeout"


def _call(model: str, body: dict) -> Optional[requests.Response]:
    def req(key: str):
        try:  # 키는 주소가 아니라 헤더로 보낸다(로그에 키가 남지 않게)
            return requests.post(URL.format(model=model), headers={"x-goog-api-key": key}, json=body, timeout=180)
        except requests.Timeout:
            logger.info("Gemini %s 응답 시간 초과 - 다른 키는 건너뛰고 다음 방법으로", model)
            return _TimedOut()
        except requests.RequestException as exc:
            logger.info("Gemini 요청 실패(네트워크): %s", exc)
            return None

    return gemini_keys.call_with_rotation(req)


def generate(prompt: str, *, purpose: str, system: str = "", site: Optional[str] = None, model: str = "flash",
             json_mode: bool = False, max_output: int = 8192, allow_lite: bool = True) -> Optional[str]:
    """글을 만들어 돌려준다. 키가 없거나 모든 키·모델이 실패하면 None(호출부가 Claude로 대신한다).

    flash가 바쁘거나(503) 막히면 lite로 한 번 더 시도한다. 응답이 한도에 걸려 잘렸으면 실패로 본다."""
    if not enabled():
        return None
    order = [MODELS[model]] + ([MODELS["lite"]] if model == "flash" and allow_lite else [])  # allow_lite=False: 품질이 중요해 lite로 대신하지 않음
    for name in order:
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_output},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        started = time.time()
        resp = _call(name, body)
        if resp is None or resp.status_code != 200:
            logger.info("[Gemini] %s %s 실패(HTTP %s) - 다음 방법으로", purpose, name, getattr(resp, "status_code", "없음"))
            continue
        try:
            data = resp.json()
            cand = data["candidates"][0]
            text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
        except (ValueError, KeyError, IndexError) as exc:
            logger.info("[Gemini] %s 응답 해석 실패: %s", purpose, exc)
            continue
        finish = cand.get("finishReason", "")
        meta = data.get("usageMetadata", {})
        record_gemini(purpose, name, meta.get("promptTokenCount", 0), meta.get("candidatesTokenCount", 0),
                      site=site, finish=finish, seconds=time.time() - started)
        if finish != "STOP" or not text.strip():
            logger.info("[Gemini] %s 응답이 완결되지 않음(%s) - 다음 방법으로", purpose, finish)
            continue
        return text
    return None


def generate_json(prompt: str, **kw: Any) -> Optional[Any]:
    """JSON으로 답을 받아 파이썬 값으로 돌려준다. 해석이 안 되면 None."""
    text = generate(prompt, json_mode=True, **kw)
    if text is None:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except ValueError:
        logger.info("[Gemini] %s JSON 해석 실패", kw.get("purpose"))
        return None
