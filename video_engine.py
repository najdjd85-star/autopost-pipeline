"""
30초 세로(9:16) 쇼츠 영상 렌더링 엔진.

edge-tts("ko-KR-InJoonNeural", 1.5배속)로 나레이션을 합성하고, moviepy로
1080x1920 세로 영상을 렌더링한다. 자막은 문장 단위로 잘라 한 번에 한 구간씩
화면에 노출되며(카드뉴스/릴스 스타일), 구간마다 배경 사진이 바뀐다(최대 5장,
Pexels -> Pollinations.ai 하이브리드로 확보).

moviepy 2.x API 사용 (`moviepy.editor`는 v2에서 제거됨 - 최상위 `moviepy`에서
직접 임포트). 렌더링 전체를 try/except로 감싸 ffmpeg/폰트 등 환경 문제가 있어도
파이프라인 나머지 단계(발행/배포)를 막지 않는다.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional

from config import settings
from constants import (
    CAPTION_COLOR,
    CAPTION_FONT_SIZE,
    CAPTION_MAX_LINES,
    CAPTION_STROKE_WIDTH,
    OUTRO_MENTION,
    SHORTS_SIZE,
)
from utils.captions import build_timed_caption_segments, split_into_sentence_segments
from utils.fonts import create_korean_text_clip, strip_emoji_for_video, strip_stage_directions
from utils.http import safe_get
from utils.logger import get_logger
from utils.tts import synthesize_voice_with_timings

logger = get_logger(__name__)

WIDTH, HEIGHT = SHORTS_SIZE

SHORTS_TTS_VOICE = "ko-KR-InJoonNeural"
SHORTS_TTS_RATE = "+50%"  # 1.5배속 - 쇼츠 시청 이탈 방지 + 영상 길이 단축
MAX_IMAGE_SEGMENTS = 5  # 배경 사진은 최대 이만큼만 받고, 컷이 더 많으면 돌려가며(반복) 씀

CAPTION_MAX_WIDTH = WIDTH - 140


def _build_timed_segments(sentence_timings: List[dict], total_duration: float) -> Optional[tuple]:
    return build_timed_caption_segments(
        sentence_timings, total_duration, CAPTION_FONT_SIZE, CAPTION_MAX_WIDTH, CAPTION_MAX_LINES, bold=True
    )


def _split_into_segments(text: str) -> List[str]:
    return split_into_sentence_segments(
        text, CAPTION_FONT_SIZE, CAPTION_MAX_WIDTH, CAPTION_MAX_LINES, bold=True
    )


def _cover_resize_crop(pil_image, width: int, height: int):
    """이미지를 (width, height) 프레임에 꽉 차게(cover) 리사이즈+크롭한다."""
    img_ratio = pil_image.width / pil_image.height
    target_ratio = width / height
    if img_ratio > target_ratio:
        new_height = height
        new_width = max(int(height * img_ratio), width)
    else:
        new_width = width
        new_height = max(int(width / img_ratio), height)
    resized = pil_image.resize((new_width, new_height))
    left = (new_width - width) // 2
    top = (new_height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _fetch_shorts_images(prompt_en: str, count: int) -> List[bytes]:
    """구간별로 쓸 배경 사진을 최대 count장 확보한다 (Pexels 여러 장 -> Pollinations 폴백).

    본문 이미지(image_hybrid_engine)와 달리 쇼츠는 세로(portrait) 사진이 필요하고
    한 프롬프트로 여러 장을 받아야 해서 별도 구현한다.
    """
    images: List[bytes] = []
    if not prompt_en:
        return images

    if settings.pexels_api_key:
        try:
            resp = safe_get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": settings.pexels_api_key},
                params={"query": prompt_en, "per_page": count, "orientation": "portrait"},
                timeout=10,
            )
            if resp is not None and resp.status_code == 200:
                for photo in resp.json().get("photos", [])[:count]:
                    src = photo.get("src", {})
                    img_url = src.get("portrait") or src.get("large2x") or src.get("large")
                    if not img_url:
                        continue
                    img_resp = safe_get(img_url, timeout=15)
                    if img_resp is not None and img_resp.status_code == 200:
                        images.append(img_resp.content)
        except (ValueError, KeyError) as exc:
            logger.info("Pexels 다중 이미지 조회 파싱 실패: %s", exc)

    if len(images) < count:
        from image_hybrid_engine import generate_pollinations_image

        for _ in range(count - len(images)):
            img = generate_pollinations_image(prompt_en, width=1080, height=1920)
            if img is None:
                break
            images.append(img)

    return images


def _build_segment_background(duration: float, image_bytes: Optional[bytes]):
    """한 구간의 배경(사진+어두운 오버레이, 없으면 단색)을 만든다."""
    from moviepy import ColorClip, CompositeVideoClip, ImageClip

    if image_bytes:
        try:
            import numpy as np
            from PIL import Image

            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            pil_img = _cover_resize_crop(pil_img, WIDTH, HEIGHT)
            photo = ImageClip(np.array(pil_img)).with_duration(duration)
            dark_overlay = (
                ColorClip(size=(WIDTH, HEIGHT), color=(0, 0, 0))
                .with_duration(duration)
                .with_opacity(0.45)
            )
            return CompositeVideoClip([photo, dark_overlay], size=(WIDTH, HEIGHT))
        except Exception as exc:  # noqa: BLE001
            logger.warning("쇼츠 구간 배경 이미지 처리 실패, 단색 배경으로 대체: %s", exc)

    return ColorClip(size=(WIDTH, HEIGHT), color=(20, 24, 38)).with_duration(duration)


def render_shorts(
    script_text: str,
    audio_path: Path,
    cta_link: str,
    output_path: Path,
    images: Optional[List[bytes]] = None,
    sentence_timings: Optional[List[dict]] = None,
) -> Optional[Path]:
    """오디오+구간별 자막/이미지를 기반으로 1080x1920 쇼츠 MP4를 렌더링한다.

    sentence_timings(edge-tts SentenceBoundary)가 있으면 실제 발화 시점에 맞춰
    자막 구간 길이를 배분해 목소리와 싱크를 맞춘다. 없으면 문장을 잘라 글자 수
    비율로 오디오 전체 길이에 배분하는 기존 방식으로 대체한다. 구간마다 images
    목록을 돌려가며 배경 사진을 바꾼다.
    """
    try:
        from moviepy import AudioFileClip, CompositeVideoClip, concatenate_videoclips

        audio_path = Path(audio_path)
        if not audio_path.exists():
            logger.warning("쇼츠 렌더링 실패: 오디오 파일 없음 (%s)", audio_path)
            return None

        audio_clip = AudioFileClip(str(audio_path))
        duration = audio_clip.duration or 30
        images = images or []

        timed = _build_timed_segments(sentence_timings or [], duration)
        if timed:
            segments, seg_durations = timed
        else:
            segments = _split_into_segments(script_text)
            # 구간별 길이는 글자 수 비율로 오디오 전체 길이에 맞춰 배분한다.
            total_chars = sum(len(s) for s in segments) or 1
            seg_durations = [max(duration * len(s) / total_chars, 0.8) for s in segments]

        scale = duration / sum(seg_durations)
        seg_durations = [d * scale for d in seg_durations]

        segment_clips = []
        for i, (seg_text, seg_duration) in enumerate(zip(segments, seg_durations)):
            image_bytes = images[i % len(images)] if images else None
            bg = _build_segment_background(seg_duration, image_bytes)
            caption = (
                create_korean_text_clip(
                    text=strip_emoji_for_video(seg_text),
                    font_size=CAPTION_FONT_SIZE,
                    color=CAPTION_COLOR,
                    max_width=CAPTION_MAX_WIDTH,
                    align="center",
                    bold=True,
                    stroke_width=CAPTION_STROKE_WIDTH,
                    stroke_color="black",
                )
                .with_duration(seg_duration)
                .with_position("center")
            )
            segment_clips.append(
                CompositeVideoClip([bg, caption], size=(WIDTH, HEIGHT)).with_duration(seg_duration)
            )

        visual = concatenate_videoclips(segment_clips, method="compose")

        header_badge = (
            create_korean_text_clip(
                text=strip_emoji_for_video("오늘의 핵심 정리"),
                font_size=54,
                color="#ffd166",
                max_width=WIDTH - 120,
                align="center",
            )
            .with_duration(duration)
            .with_position(("center", 120))
        )

        cta_text = cta_link if cta_link else "프로필 링크에서 자세히 보기"
        cta = (
            create_korean_text_clip(
                text=strip_emoji_for_video(f"▶ {cta_text}"),
                font_size=44,
                color="#4f7cff",
                max_width=WIDTH - 100,
                align="center",
                bg_color=(255, 255, 255, 255),
            )
            .with_duration(duration)
            .with_position(("center", HEIGHT - 220))
        )

        final = CompositeVideoClip(
            [visual, header_badge, cta], size=(WIDTH, HEIGHT)
        ).with_duration(duration).with_audio(audio_clip)

        import os

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        final.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            preset="veryfast",
            threads=1,  # 스레드를 늘리면 x264 인코더가 스레드별 참조 프레임 버퍼를
            # 따로 들고 있어서 메모리 사용량이 늘어난다 - RAM이 작은 렌더링 서버에서
            # OOM으로 죽는 걸 실측으로 확인해서 1로 고정한다(속도보다 안정성 우선).
            ffmpeg_params=["-crf", "23"],
        )

        audio_clip.close()
        final.close()
        return output_path
    except Exception as exc:  # noqa: BLE001 - 영상 렌더링 실패는 파이프라인을 막지 않아야 함
        logger.warning("쇼츠 영상 렌더링 실패: %s", exc)
        return None


def build_shorts_video(
    shorts_script: str,
    cta_link: str,
    workdir: Path,
    image_prompt: Optional[str] = None,
) -> Optional[Path]:
    """나레이션 스크립트로부터 TTS(1.5배속) + 렌더링까지 전체 파이프라인을 수행한다.

    image_prompt를 주면(예: draft["image_prompts"]["slot_1"]) 그 주제로 최대
    5장의 배경 사진을 구해 구간마다 바꿔가며 보여준다. 실패하거나 프롬프트가
    없으면 단색 배경으로 대체한다.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    clean_script = strip_stage_directions(shorts_script)
    clean_script = f"{clean_script} {OUTRO_MENTION}".strip()

    audio_path = workdir / "shorts_audio.mp3"
    voice_path, sentence_timings = synthesize_voice_with_timings(
        clean_script, audio_path, voice=SHORTS_TTS_VOICE, rate=SHORTS_TTS_RATE
    )
    if voice_path is None:
        logger.warning("쇼츠 음성 합성 실패 - 영상 생성을 건너뜁니다.")
        return None
    if sentence_timings:
        logger.info("TTS 문장 타이밍 %d개 확보 - 자막을 실제 발화 시점에 동기화", len(sentence_timings))
    else:
        logger.info("TTS 문장 타이밍 없음 - 글자 수 비례 배분 방식으로 대체")

    segment_count = len(_split_into_segments(clean_script))
    images: List[bytes] = []
    if image_prompt:
        try:
            images = _fetch_shorts_images(image_prompt, min(segment_count, MAX_IMAGE_SEGMENTS))
            if images:
                logger.info("쇼츠 배경 이미지 %d장 확보", len(images))
        except Exception as exc:  # noqa: BLE001
            logger.warning("쇼츠 배경 이미지 조회 실패, 단색 배경으로 대체: %s", exc)

    output_path = workdir / "shorts_output.mp4"
    return render_shorts(
        clean_script,
        voice_path,
        cta_link,
        output_path,
        images=images,
        sentence_timings=sentence_timings,
    )
