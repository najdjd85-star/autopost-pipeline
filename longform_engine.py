"""
5~7분 가로(16:9) 롱폼 영상 렌더링 엔진.

챕터별로 Pexels 스톡 영상을 다운로드하고, edge-tts로 나레이션을 합성한 뒤,
크로스페이드 전환 + 좌상단 챕터 바 + 하단 자막을 합성하여 1920x1080 MP4로
출력한다. moviepy 2.x API 사용.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from config import settings
from constants import (
    CAPTION_COLOR,
    CAPTION_FONT_SIZE,
    CAPTION_MAX_LINES,
    CAPTION_STROKE_WIDTH,
    DEFAULT_TTS_VOICE,
    LONGFORM_SIZE,
    OUTRO_MENTION,
)
from utils.captions import build_timed_caption_segments, split_into_sentence_segments
from utils.fonts import create_korean_text_clip, strip_emoji_for_video, strip_stage_directions
from utils.http import safe_get
from utils.logger import get_logger
from utils.tts import synthesize_voice_with_timings

logger = get_logger(__name__)

WIDTH, HEIGHT = LONGFORM_SIZE
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"
CROSSFADE_DURATION = 0.6

CAPTION_MAX_WIDTH = int(WIDTH * 0.85)
# 자막 폰트가 커진 데다(최대 2줄) 하단에 CTA 배너까지 얹히므로, 겹치지 않도록
# 충분히 위로 올린다.
CAPTION_Y = HEIGHT - 380


def search_stock_video(query_en: str) -> Optional[bytes]:
    """Pexels Video API로 챕터 주제에 맞는 가로 스톡 영상을 검색해 바이트로 반환한다."""
    if not settings.pexels_api_key:
        logger.info("PEXELS_API_KEY 미설정 - 스톡 영상 검색을 건너뜁니다.")
        return None

    resp = safe_get(
        PEXELS_VIDEO_SEARCH_URL,
        headers={"Authorization": settings.pexels_api_key},
        params={"query": query_en, "per_page": 1, "orientation": "landscape"},
        timeout=12,
    )
    if resp is None or resp.status_code != 200:
        return None

    try:
        videos = resp.json().get("videos", [])
        if not videos:
            return None
        files = sorted(
            videos[0].get("video_files", []),
            key=lambda f: f.get("width", 0),
            reverse=True,
        )
        hd_files = [f for f in files if 1200 <= f.get("width", 0) <= 1920] or files
        if not hd_files:
            return None
        video_url = hd_files[0]["link"]
        video_resp = safe_get(video_url, timeout=30)
        if video_resp is None or video_resp.status_code != 200:
            return None
        return video_resp.content
    except (ValueError, KeyError, IndexError) as exc:
        logger.warning("Pexels 영상 응답 처리 실패: %s", exc)
        return None


def _build_chapter_clip(chapter: Dict[str, str], index: int, total: int, workdir: Path):
    """단일 챕터 클립(배경영상+나레이션+챕터바+자막)을 만든다. 실패 시 None."""
    from moviepy import AudioFileClip, ColorClip, CompositeVideoClip, VideoFileClip

    title = chapter.get("title", f"챕터 {index + 1}")
    script = strip_stage_directions(chapter.get("script", ""))
    if index == total - 1:
        script = f"{script} {OUTRO_MENTION}".strip()
    stock_query = chapter.get("stock_query_en", title)

    audio_path = workdir / f"chapter_{index}_audio.mp3"
    voice_path, sentence_timings = synthesize_voice_with_timings(script, audio_path, voice=DEFAULT_TTS_VOICE)
    if voice_path is None:
        logger.warning("챕터 %s 나레이션 합성 실패 - 이 챕터를 건너뜁니다.", index + 1)
        return None

    audio_clip = AudioFileClip(str(voice_path))
    duration = max(audio_clip.duration or 5, 3)

    video_bytes = search_stock_video(stock_query)
    background = None
    if video_bytes:
        raw_path = workdir / f"chapter_{index}_bg.mp4"
        raw_path.write_bytes(video_bytes)
        try:
            bg_clip = VideoFileClip(str(raw_path))
            bg_clip = bg_clip.resized(height=HEIGHT)
            if bg_clip.duration < duration:
                from moviepy.video.fx import Loop

                bg_clip = bg_clip.with_effects([Loop(duration=duration)])
            background = bg_clip.with_duration(duration)
        except Exception as exc:  # noqa: BLE001
            logger.warning("챕터 %s 스톡 영상 처리 실패, 단색 배경으로 대체: %s", index + 1, exc)
            background = None

    if background is None:
        background = ColorClip(size=(WIDTH, HEIGHT), color=(15, 20, 30)).with_duration(duration)

    chapter_bar = (
        create_korean_text_clip(
            text=strip_emoji_for_video(f"CH.{index + 1}/{total}  {title}"),
            font_size=36,
            color="white",
            max_width=int(WIDTH * 0.5),
            align="left",
        )
        .with_duration(duration)
        .with_position((40, 30))
    )

    # 자막: 쇼츠와 동일한 스타일(진한 노랑+굵게+테두리)로, 실제 발화 시점에 맞춰
    # 문장 단위로 잘라 순서대로 노출한다(SentenceBoundary 타이밍 기반 싱크).
    timed = build_timed_caption_segments(
        sentence_timings, duration, CAPTION_FONT_SIZE, CAPTION_MAX_WIDTH, CAPTION_MAX_LINES, bold=True
    )
    if timed:
        seg_texts, seg_durations = timed
    else:
        seg_texts = split_into_sentence_segments(
            script, CAPTION_FONT_SIZE, CAPTION_MAX_WIDTH, CAPTION_MAX_LINES, bold=True
        )
        total_chars = sum(len(s) for s in seg_texts) or 1
        seg_durations = [max(duration * len(s) / total_chars, 0.8) for s in seg_texts]

    scale = duration / sum(seg_durations)
    seg_durations = [d * scale for d in seg_durations]

    caption_clips = []
    t_cursor = 0.0
    for seg_text, seg_duration in zip(seg_texts, seg_durations):
        caption_clips.append(
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
            .with_start(t_cursor)
            .with_duration(seg_duration)
            .with_position(("center", CAPTION_Y))
        )
        t_cursor += seg_duration

    clip = CompositeVideoClip(
        [background, chapter_bar, *caption_clips], size=(WIDTH, HEIGHT)
    ).with_duration(duration).with_audio(audio_clip)

    return clip


def render_longform(
    chapters: List[Dict[str, str]], output_path: Path, cta_link: str = ""
) -> Optional[Path]:
    """챕터 리스트로부터 최종 1920x1080 MP4를 렌더링한다.

    cta_link(발행된 워드프레스 글 URL)를 주면 쇼츠와 동일한 스타일의 하단
    CTA 배너를 영상 전체에 걸쳐 노출한다(실제 발행 단계에서만 URL이 존재하므로
    미리보기 단계에서는 빈 문자열을 넘겨 노출하지 않는다).
    """
    if not chapters:
        logger.warning("롱폼 렌더링 실패: 챕터가 비어 있습니다.")
        return None

    output_path = Path(output_path)
    workdir = output_path.parent
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        from moviepy import CompositeVideoClip, concatenate_videoclips
        from moviepy.video.fx import CrossFadeIn, CrossFadeOut

        clips = []
        total = len(chapters)
        for i, chapter in enumerate(chapters):
            clip = _build_chapter_clip(chapter, i, total, workdir)
            if clip is None:
                continue
            if i > 0:
                clip = clip.with_effects([CrossFadeIn(CROSSFADE_DURATION)])
            if i < total - 1:
                clip = clip.with_effects([CrossFadeOut(CROSSFADE_DURATION)])
            clips.append(clip)

        if not clips:
            logger.warning("모든 챕터 클립 생성 실패 - 롱폼 영상을 만들 수 없습니다.")
            return None

        import os

        final = concatenate_videoclips(clips, method="compose", padding=-CROSSFADE_DURATION)

        if cta_link:
            final_audio = final.audio
            cta = (
                create_korean_text_clip(
                    text=strip_emoji_for_video(f"▶ {cta_link}"),
                    font_size=36,
                    color="#4f7cff",
                    max_width=int(WIDTH * 0.6),
                    align="center",
                    bg_color=(255, 255, 255, 255),
                )
                .with_duration(final.duration)
                .with_position(("center", HEIGHT - 80))
            )
            final = CompositeVideoClip(
                [final, cta], size=(WIDTH, HEIGHT)
            ).with_duration(final.duration).with_audio(final_audio)

        final.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            preset="veryfast",
            threads=1,  # video_engine.py와 동일한 이유 - 인코더 스레드가 늘수록
            # 스레드별 참조 프레임 버퍼가 늘어 메모리를 더 쓴다. 롱폼은 쇼츠보다
            # 훨씬 길어 영향이 더 크므로 반드시 1로 고정한다.
            ffmpeg_params=["-crf", "23"],
        )
        final.close()
        return output_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("롱폼 영상 렌더링 실패: %s", exc)
        return None


def build_longform_video(
    longform_chapters: List[Dict[str, str]], workdir: Path, cta_link: str = ""
) -> Optional[Path]:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    output_path = workdir / "longform_output.mp4"
    return render_longform(longform_chapters, output_path, cta_link=cta_link)
