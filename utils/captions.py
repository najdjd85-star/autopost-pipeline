"""쇼츠/롱폼이 공유하는 자막 분할 + 음성 동기화 유틸리티.

문장을 "한 컷당 최대 N줄"에 맞춰 쪼개고, edge-tts의 문장 단위 타이밍
(SentenceBoundary)이 있으면 그 실제 발화 구간에 맞춰 각 자막 컷의 노출
시간을 배분한다(캡션-음성 싱크). 쇼츠(video_engine.py)와 롱폼
(longform_engine.py)이 동일한 로직을 공유하도록 여기로 분리했다.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from utils.fonts import count_wrapped_lines


def split_text_to_fit(text: str, font_size: int, max_width: int, max_lines: int, bold: bool = True) -> List[str]:
    """한 덩어리의 텍스트를, 렌더링했을 때 max_lines를 넘지 않도록 단어 단위로 쪼갠다."""
    words = text.split()
    if not words:
        return [text]

    chunks: List[str] = []
    current: List[str] = []
    for word in words:
        trial = current + [word]
        trial_text = " ".join(trial)
        if current and count_wrapped_lines(trial_text, font_size, max_width, bold=bold) > max_lines:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current = trial
    if current:
        chunks.append(" ".join(current))
    return chunks or [text]


def split_into_sentence_segments(
    text: str, font_size: int, max_width: int, max_lines: int, bold: bool = True
) -> List[str]:
    """나레이션을 문장 단위로 자르고, 한 컷당 자막이 max_lines줄을 넘으면 추가로 더 잘게 쪼갠다."""
    text = (text or "").strip()
    if not text:
        return [""]

    sentences = [s.strip() for s in re.split(r"(?<=[.!?다요죠])\s+", text) if s.strip()]
    if not sentences:
        sentences = [text]

    segments: List[str] = []
    for sentence in sentences:
        segments.extend(split_text_to_fit(sentence, font_size, max_width, max_lines, bold=bold))
    return segments or [text]


def build_timed_caption_segments(
    sentence_timings: List[dict],
    total_duration: float,
    font_size: int,
    max_width: int,
    max_lines: int,
    bold: bool = True,
) -> Optional[Tuple[List[str], List[float]]]:
    """edge-tts SentenceBoundary 타이밍을 기반으로 (자막목록, 구간길이목록)을 만든다.

    문장 하나가 여러 캡션 컷으로 쪼개지면, 그 문장에 배정된 실제 발화 구간
    길이를 글자 수 비례로 나눠 쓴다 - 전체 오디오 길이에 균등 비례하던 방식보다
    실제 목소리와의 싱크가 훨씬 정확하다. sentence_timings가 없으면 None을
    반환해 호출측이 기존 방식(글자 수 비례 분배)으로 대체하게 한다.
    """
    if not sentence_timings:
        return None

    segments: List[str] = []
    durations: List[float] = []
    n = len(sentence_timings)
    for i, st in enumerate(sentence_timings):
        start = st["offset"]
        end = sentence_timings[i + 1]["offset"] if i + 1 < n else total_duration
        sentence_duration = max(end - start, 0.05)

        chunks = split_text_to_fit(st["text"], font_size, max_width, max_lines, bold=bold)
        total_chars = sum(len(c) for c in chunks) or 1
        for chunk in chunks:
            segments.append(chunk)
            durations.append(sentence_duration * (len(chunk) / total_chars))

    if not segments:
        return None
    return segments, durations
