"""홍보 게시물 묶음(카드뉴스 장 수·쇼츠 장면·매체별 문구)을 만든다. 모두 사이트 데이터로 자동 생성한다."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image

import render as R
from render import BY_SLUG, HERE, SITE_URL

CARD = (1080, 1350)
SHORT = (1080, 1920)
HASH_BASE = ["#냉장고파먹기", "#자취요리", "#집밥", "#간단요리", "#레시피"]


# ----------------------------------------------------------------- 데이터
def trending(n: int = 3) -> Tuple[List[str], str]:
    d = json.loads((HERE / "trending.json").read_text(encoding="utf-8"))
    return [i["slug"] for i in d["items"] if i["slug"] in BY_SLUG][:n], d.get("date", "")


def popularity() -> Dict[str, int]:
    f = HERE / "popularity.json"
    return json.loads(f.read_text(encoding="utf-8")).get("volumes", {}) if f.exists() else {}


def recipes_for(foods: set, n: int = 3, exclude: set = ()) -> List[str]:
    """고른 재료(양념 제외)만으로 만들 수 있는 레시피를 인기 순으로 n개."""
    vol = popularity()
    ok = []
    for r in R.RECIPES:
        need = {i["n"] for i in r["ingredients"] if not i["opt"] and i["n"] not in R.STAPLES and i["n"] != "물"}
        if need and need <= foods and r["slug"] not in exclude:
            ok.append(r["slug"])
    ok.sort(key=lambda s: -vol.get(s, 0))
    return ok[:n]


# ----------------------------------------------------------------- 장면 만들기(카드·쇼츠 공통)
def scenes_top3(size, paged: bool) -> List[Image.Image]:
    slugs, date = trending(3)
    W, H = size
    total = 5 if paged else None
    pg = lambda i: (i, total) if paged else None  # noqa: E731
    sub = (date[5:].replace("-", "/") + " 네이버 검색 기준" if date else "네이버 검색 기준")
    out = [R.cover(W, H, "오늘 많이 찾은 요리", "TOP 3", sub, slugs, pg(1))]
    for k, s in enumerate(slugs, 1):
        out.append(R.rank_item(W, H, k, s, pg(k + 1)))
    out.append(R.outro(W, H, "재료만 누르면 레시피가 나와요", "냉장고 파먹기", pg(5)))
    return out


def scenes_recipe(slug: str, size, paged: bool) -> List[Image.Image]:
    W, H = size
    r = BY_SLUG[slug]
    steps = R.steps_slides(W, H, slug)
    total = (4 + len(steps)) if paged else None
    pg = lambda i: (i, total) if paged else None  # noqa: E731
    out = [R.cover(W, H, "1분 레시피", r["name"], f'{r["minutes"]}분 · {r["level"]} · {r["servings"]}인분', [slug], pg(1)),
           R.ingredients_slide(W, H, slug, pg(2))]
    for k, im in enumerate(R.steps_slides(W, H, slug, 3, total)):
        out.append(im)
    out.append(R.info_slide(W, H, slug, pg(3 + len(steps))))
    out.append(R.outro(W, H, "재료만 누르면 레시피가 나와요", "냉장고 파먹기", pg(4 + len(steps))))
    return out


def scenes_combo(foods: List[str], size, paged: bool) -> Tuple[List[Image.Image], List[str]]:
    W, H = size
    slugs = recipes_for(set(foods) | {"밥"}, 3)
    total = (len(slugs) + 2) if paged else None
    pg = lambda i: (i, total) if paged else None  # noqa: E731
    title = " + ".join(foods) + " 있으면"
    out = [R.cover(W, H, "냉장고 털이", title, f"이 요리 {len(slugs)}가지 만들 수 있어요", slugs, pg(1))]
    for k, s in enumerate(slugs, 1):
        out.append(R.rank_item(W, H, k, s, pg(k + 1)))
    out.append(R.outro(W, H, "내 냉장고 재료로 찾아보세요", "냉장고 파먹기", pg(len(slugs) + 2)))
    return out, slugs


# ----------------------------------------------------------------- 매체별 문구
def link(slug: str, platform: str, campaign: str) -> str:
    base = f"https://{SITE_URL}/" + (f"recipes/{slug}.html" if slug else "")
    return f"{base}?utm_source={platform}&utm_medium=social&utm_campaign={campaign}"


def captions_recipe(slug: str) -> Dict[str, str]:
    r = BY_SLUG[slug]
    per = R.compute(slug)["per"]
    foods = [i["n"] for i in r["ingredients"] if not i["opt"] and i["n"] not in R.STAPLES and i["n"] != "물"][:4]
    tags = " ".join(HASH_BASE + [f"#{r['name']}", f"#{r['name']}만들기"])
    ai = "※ 사진은 AI로 만든 참고 이미지예요."
    ing = ", ".join(foods)
    return {
        "threads": f"{ing} 있으면 {r['name']} 하나 뚝딱이에요.\n{r['minutes']}분이면 되고 1인분 {per['kcal']}kcal 정도예요.\n분량이랑 순서는 정리해 뒀어요 👉 {link(slug, 'threads', 'recipe')}",
        "instagram": f"{r['name']} 🍳\n{ing}만 있으면 {r['minutes']}분 완성!\n1인분 {per['kcal']}kcal · 정확한 분량(ml·g)과 순서를 넘겨서 확인하세요.\n\n더 많은 레시피는 프로필 링크에서 → {SITE_URL}\n{ai}\n\n{tags}",
        "youtube_title": f"{r['name']} 만드는 법 | {r['minutes']}분 집밥 #shorts",
        "youtube_desc": f"{r['name']} 레시피 ({r['minutes']}분, 1인분 {per['kcal']}kcal)\n정확한 분량과 순서: {link(slug, 'youtube', 'recipe')}\n냉장고 속 재료로 만들 수 있는 요리 찾기: https://{SITE_URL}/\n{ai}\n{tags}",
        "tiktok": f"{r['name']} {r['minutes']}분 컷 🍳 재료·분량은 프로필 링크에서!\n{ai}\n{tags}",
    }


def captions_top3(slugs: List[str], date: str) -> Dict[str, str]:
    names = ", ".join(BY_SLUG[s]["name"] for s in slugs)
    d = date[5:].replace("-", "/") if date else "오늘"
    tags = " ".join(HASH_BASE + ["#오늘뭐먹지", "#인기레시피"])
    return {
        "threads": f"{d} 기준 사람들이 제일 많이 찾은 요리는 {names} 순이래요.\n오늘 저녁 고민이면 참고해 보세요 👉 {link('', 'threads', 'top3')}",
        "instagram": f"오늘 많이 찾은 요리 TOP 3 🔥\n{names}\n({d} 네이버 검색 기준)\n\n재료만 누르면 만들 수 있는 요리가 나와요 → 프로필 링크\n※ 사진은 AI로 만든 참고 이미지예요.\n\n{tags}",
        "youtube_title": f"오늘 많이 찾은 요리 TOP 3 ({d}) #shorts",
        "youtube_desc": f"{names}\n내 냉장고 재료로 만들 수 있는 요리 찾기: {link('', 'youtube', 'top3')}\n※ 사진은 AI로 만든 참고 이미지예요.\n{tags}",
        "tiktok": f"오늘 많이 찾은 요리 TOP3 🔥 {names}\n{tags}",
    }


def captions_combo(foods: List[str], slugs: List[str]) -> Dict[str, str]:
    names = ", ".join(BY_SLUG[s]["name"] for s in slugs)
    f = " + ".join(foods)
    tags = " ".join(HASH_BASE + ["#냉털", "#자취생요리"])
    return {
        "threads": f"냉장고에 {f}만 있어도 {names} 가능해요.\n뭐 먹지 싶을 때 재료 눌러서 찾아보세요 👉 {link('', 'threads', 'combo')}",
        "instagram": f"{f} 있으면 이 요리 {len(slugs)}가지! 🧊\n{names}\n\n내 냉장고 재료로 찾기 → 프로필 링크\n※ 사진은 AI로 만든 참고 이미지예요.\n\n{tags}",
        "youtube_title": f"{f} 있으면 만들 수 있는 요리 {len(slugs)}가지 #shorts",
        "youtube_desc": f"{names}\n{link('', 'youtube', 'combo')}\n※ 사진은 AI로 만든 참고 이미지예요.\n{tags}",
        "tiktok": f"{f}만 있으면? {names} 🧊\n{tags}",
    }


# ----------------------------------------------------------------- 영상(ffmpeg)
def make_video(scenes: List[Image.Image], durations: List[float], out: Path, fade: float = 0.4, fps: int = 30) -> None:
    """장면 그림들을 서로 겹쳐 넘어가는(페이드) 세로 영상으로 만든다. 소리는 무음 트랙을 붙인다."""
    tmp = out.parent / f".{out.stem}_frames"
    tmp.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for i, im in enumerate(scenes):
        p = tmp / f"s{i:02d}.png"
        im.save(p)
        cmd += ["-i", str(p)]
    cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    n = len(scenes)
    parts = []
    for i, d in enumerate(durations):
        frames = int((d + fade) * fps)
        parts.append(f"[{i}:v]zoompan=z='min(zoom+0.0004,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps={fps},setsar=1[v{i}]")
    last, acc = "v0", durations[0]
    for i in range(1, n):
        off = acc - fade * i + 0.0
        label = f"x{i}"
        parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={fade}:offset={max(off, 0):.2f}[{label}]")
        last = label
        acc += durations[i]
    total = sum(durations) - fade * (n - 1)
    parts.append(f"[{last}]format=yuv420p[vout]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", f"{n}:a", "-t", f"{total:.2f}",
            "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    for f in tmp.glob("*.png"):
        f.unlink()
    tmp.rmdir()
