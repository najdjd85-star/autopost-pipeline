"""
한글 지원 폰트 경로 탐색 유틸리티.

moviepy의 TextClip은 font를 지정하지 않으면 시스템 기본 폰트(한글 글리프가
없는 경우가 많음)를 사용해 한글 자막이 깨진 도형으로 렌더링된다. 이 모듈은
Windows(개발)/Ubuntu(배포) 양쪽에서 흔히 쓰이는 한글 폰트 경로를 순서대로
찾아 반환한다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, List, Optional, Tuple

from config import BASE_DIR
from utils.logger import get_logger

logger = get_logger(__name__)

# 프로젝트에 폰트 파일을 직접 포함시켜, 서버에 sudo 권한이 없어 시스템 폰트를
# 설치할 수 없는 환경(예: 관리형 호스팅)에서도 항상 한글이 정상 렌더링되게 한다.
# 그래도 혹시 이 파일들이 없으면 기존 시스템 폰트 경로들로 순서대로 폴백한다.
_BUNDLED_REGULAR = BASE_DIR / "assets" / "fonts" / "NanumGothic-Regular.ttf"
_BUNDLED_BOLD = BASE_DIR / "assets" / "fonts" / "NanumGothic-Bold.ttf"

_CANDIDATES = [
    str(_BUNDLED_REGULAR),
    r"C:\Windows\Fonts\malgun.ttf",  # Windows 기본 - 맑은 고딕
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # Ubuntu: sudo apt install fonts-nanum
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Ubuntu: fonts-noto-cjk
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]

_BOLD_CANDIDATES = [
    str(_BUNDLED_BOLD),
    r"C:\Windows\Fonts\malgunbd.ttf",  # Windows 기본 - 맑은 고딕 Bold
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]

_resolved: Optional[str] = None
_resolved_bold: Optional[str] = None
_warned = False


def get_korean_font() -> Optional[str]:
    """한글 렌더링이 가능한 폰트 파일 경로를 반환한다 (없으면 None).

    결과는 1회 탐색 후 캐시되며, 찾지 못한 경우 딱 1번만 경고 로그를 남긴다.
    """
    global _resolved, _warned
    if _resolved is not None:
        return _resolved

    for path in _CANDIDATES:
        if Path(path).exists():
            _resolved = path
            return path

    if not _warned:
        logger.warning(
            "한글 지원 폰트를 찾지 못했습니다(%s 등 확인) - 영상 자막의 한글이 깨져 보일 수 있습니다. "
            "Ubuntu 배포 시 `sudo apt install fonts-nanum`으로 설치하세요.",
            _CANDIDATES[0],
        )
        _warned = True
    return None


def get_korean_font_bold() -> Optional[str]:
    """굵은(Bold) 한글 폰트 경로를 반환한다. 없으면 일반 폰트로 대체한다."""
    global _resolved_bold
    if _resolved_bold is not None:
        return _resolved_bold

    for path in _BOLD_CANDIDATES:
        if Path(path).exists():
            _resolved_bold = path
            return path

    _resolved_bold = get_korean_font()
    return _resolved_bold


# 맑은 고딕/나눔고딕 등 일반 한글 폰트에는 컬러 이모지 글리프가 없어, moviepy
# TextClip에 이모지를 그대로 넣으면 깨진 네모(tofu)로 렌더링된다. 텔레그램
# 메시지 등 이모지가 정상 표시되는 곳에는 영향 없고, 영상 자막에만 적용한다.
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # 각종 이모지/기호 (📌, 👉, 🔥 등 포함)
    "\U00002600-\U000027BF"  # 기타 기호/딩벳
    "\U0001F1E6-\U0001F1FF"  # 국기
    "\U00002700-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "️"  # variation selector (이모지 표시 지시자)
    "]+",
    flags=re.UNICODE,
)


def strip_emoji_for_video(text: str) -> str:
    """영상 자막용으로 이모지를 제거한 텍스트를 반환한다 (한글/영문/숫자는 그대로)."""
    if not text:
        return text
    return re.sub(r"\s+", " ", _EMOJI_PATTERN.sub("", text)).strip()


# Claude가 나레이션 대본에 "(0-3초)", "(장면 1)", "나레이터:" 같은 연출 메모를
# 섞어 쓰는 경우를 대비한 방어적 후처리 (generator.py 프롬프트에서도 금지하지만,
# TTS/자막에 그대로 노출되면 눈에 띄게 어색하므로 이중으로 걸러낸다).
_STAGE_DIRECTION_PATTERN = re.compile(
    r"\(\s*\d+\s*[-~]\s*\d+\s*초\s*\)|\(\s*장면\s*\d*\s*\)|^\s*나레이터\s*[:：]\s*",
    flags=re.MULTILINE,
)


def strip_stage_directions(text: str) -> str:
    """나레이션 대본에서 시간 지시문/연출 메모를 제거한다."""
    if not text:
        return text
    cleaned = _STAGE_DIRECTION_PATTERN.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _load_font(font_size: int, bold: bool = False):
    from PIL import ImageFont

    font_path = get_korean_font_bold() if bold else get_korean_font()
    try:
        return ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default(font_size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def _wrap_lines(draw, font, text: str, max_width: Optional[int]) -> List[str]:
    """텍스트를 max_width 안에 들어가도록 줄바꿈한 줄 목록으로 만든다."""

    def _text_width(s: str) -> int:
        bbox = draw.textbbox((0, 0), s, font=font)
        return bbox[2] - bbox[0]

    lines: List[str] = []
    for raw_line in (text or "").split("\n"):
        if max_width is None:
            lines.append(raw_line)
            continue
        words = raw_line.split(" ")
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if current and _text_width(trial) > max_width:
                lines.append(current)
                current = word
            else:
                current = trial
        lines.append(current)
    return lines or [""]


def count_wrapped_lines(text: str, font_size: int, max_width: int, bold: bool = False) -> int:
    """주어진 폰트 크기/너비로 렌더링했을 때 몇 줄이 되는지 계산한다.

    영상 자막을 "한 컷당 N줄 이내"로 제한할 때, 실제로 렌더링하기 전에
    줄 수를 미리 알아야 컷을 더 잘게 나눌지 판단할 수 있어 사용한다.
    """
    from PIL import Image, ImageDraw

    font = _load_font(font_size, bold=bold)
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    return len(_wrap_lines(dummy_draw, font, text, max_width))


def create_korean_text_clip(
    text: str,
    font_size: int,
    color: str = "white",
    max_width: Optional[int] = None,
    align: str = "center",
    bg_color: Optional[Tuple[int, int, int, int]] = None,
    bold: bool = False,
    stroke_width: int = 0,
    stroke_color: str = "black",
) -> Any:
    """한글 자막을 PIL로 직접 렌더링해 moviepy ImageClip으로 반환한다.

    moviepy의 TextClip은 특정 한글 문자(예: '오'->'우', '의'->'이')를 깨뜨려
    렌더링하는 버그가 있어(실측으로 확인됨), 순수 PIL(ImageDraw.text)로 직접
    그린 뒤 numpy 배열을 ImageClip에 넘기는 방식으로 우회한다. PIL 직접 렌더링은
    정상 동작함을 별도로 검증했다.
    """
    import numpy as np
    from moviepy import ImageClip
    from PIL import Image, ImageDraw

    font = _load_font(font_size, bold=bold)

    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    lines = _wrap_lines(dummy_draw, font, text, max_width)

    def _text_width(s: str) -> int:
        bbox = dummy_draw.textbbox((0, 0), s, font=font, stroke_width=stroke_width)
        return bbox[2] - bbox[0]

    try:
        ascent, descent = font.getmetrics()
    except Exception:  # noqa: BLE001
        ascent, descent = font_size, int(font_size * 0.2)
    line_height = ascent + descent + 8

    widths = [_text_width(line) for line in lines]
    content_width = max_width or (max(widths) if widths else 10)
    content_height = line_height * len(lines)

    pad = stroke_width  # 테두리가 잘리지 않도록 여백 확보
    img = Image.new(
        "RGBA",
        (max(content_width + pad * 2, 1), max(content_height + pad * 2, 1)),
        bg_color or (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(img)

    y = pad
    for line, w in zip(lines, widths):
        if align == "right":
            x = content_width - w
        elif align == "left":
            x = 0
        else:
            x = (content_width - w) / 2
        draw.text(
            (x + pad, y),
            line,
            font=font,
            fill=color,
            stroke_width=stroke_width,
            stroke_fill=stroke_color if stroke_width else None,
        )
        y += line_height

    arr = np.array(img)
    return ImageClip(arr, transparent=True)
