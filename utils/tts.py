"""edge-tts 공용 래퍼. video_engine.py / longform_engine.py가 공유한다."""
from __future__ import annotations

import asyncio
import concurrent.futures
from pathlib import Path
from typing import List, Optional, Tuple

import edge_tts

from constants import DEFAULT_TTS_VOICE
from utils.logger import get_logger

logger = get_logger(__name__)


async def _tts_async(text: str, out_path: Path, voice: str, rate: str) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(out_path))


def _run_tts_in_isolated_thread(text: str, out_path: Path, voice: str, rate: str) -> None:
    """항상 새 스레드에서 asyncio.run()을 실행한다.

    synthesize_voice()는 완전한 동기 컨텍스트(CLI)에서도, telegram_bot.py처럼
    이미 asyncio 이벤트 루프가 돌고 있는 컨텍스트에서도 호출된다. 후자의
    경우 그냥 asyncio.run()을 부르면 "cannot be called from a running event
    loop" 에러가 난다. 별도 스레드에서 새 이벤트 루프를 만들면 호출 컨텍스트와
    무관하게 항상 안전하다.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, _tts_async(text, out_path, voice, rate))
        future.result()


def synthesize_voice(
    text: str, out_path: Path, voice: str = DEFAULT_TTS_VOICE, rate: str = "+0%"
) -> Optional[Path]:
    """텍스트를 음성 파일로 합성한다. 실패 시 None을 반환하고 예외는 삼킨다.

    rate: edge-tts 배속 지정 (예: "+50%"는 1.5배속, "-20%"는 0.8배속).
    """
    if not text or not text.strip():
        logger.warning("TTS 입력 텍스트가 비어 있어 합성을 건너뜁니다.")
        return None
    try:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _run_tts_in_isolated_thread(text, out_path, voice, rate)
        return out_path
    except Exception as exc:  # noqa: BLE001 - TTS 실패는 파이프라인을 막지 않아야 함
        logger.warning("TTS 합성 실패 (voice=%s): %s", voice, exc)
        return None


async def _tts_async_with_timings(
    text: str, out_path: Path, voice: str, rate: str
) -> List[dict]:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    timings: List[dict] = []
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                # offset/duration은 100ns 단위 tick이므로 1e7로 나눠 초 단위로 변환.
                timings.append(
                    {
                        "text": chunk["text"],
                        "offset": chunk["offset"] / 1e7,
                        "duration": chunk["duration"] / 1e7,
                    }
                )
    return timings


def _run_tts_with_timings_in_isolated_thread(
    text: str, out_path: Path, voice: str, rate: str
) -> List[dict]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            asyncio.run, _tts_async_with_timings(text, out_path, voice, rate)
        )
        return future.result()


def synthesize_voice_with_timings(
    text: str, out_path: Path, voice: str = DEFAULT_TTS_VOICE, rate: str = "+0%"
) -> Tuple[Optional[Path], List[dict]]:
    """음성 합성과 동시에 문장 단위 타이밍(SentenceBoundary)을 함께 반환한다.

    자막을 실제 발화 시점에 맞춰 보여주기 위한 용도(자막-음성 싱크). 각 항목은
    {"text": 문장, "offset": 시작초, "duration": 길이초}. 음성이 SentenceBoundary를
    지원하지 않거나 실패하면 (path, [])를 반환해 호출측이 기존 방식(글자 수 비례
    분배)으로 대체할 수 있게 한다.
    """
    if not text or not text.strip():
        logger.warning("TTS 입력 텍스트가 비어 있어 합성을 건너뜁니다.")
        return None, []
    try:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        timings = _run_tts_with_timings_in_isolated_thread(text, out_path, voice, rate)
        return out_path, timings
    except Exception as exc:  # noqa: BLE001 - TTS 실패는 파이프라인을 막지 않아야 함
        logger.warning("TTS 합성(타이밍 포함) 실패 (voice=%s): %s", voice, exc)
        return None, []
