"""사이트 사용법(실제 화면) 홍보물 만들기: 카드뉴스 6장 + 세로 영상 1개 + 매체별 문구. 먼저 screens.py 로 화면을 찍어 둔다(무료, 내 PC).

사용: venv/Scripts/python.exe -X utf8 site_d/promo/make_demo.py      결과: site_d/promo/out/demo/
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import posts as P  # noqa: E402

OUT = Path(__file__).resolve().parent / "out" / "demo"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cards = P.scenes_demo(P.CARD, True)
    for i, im in enumerate(cards, 1):
        im.save(OUT / f"card_{i:02d}.png", optimize=True)
    shorts = P.scenes_demo(P.SHORT, False)
    durs = [2.6] + [3.6] * (len(shorts) - 2) + [2.8]
    P.make_video(shorts, durs, OUT / "short.mp4")
    caps = P.captions_demo()
    (OUT / "captions.txt").write_text("\n\n".join(f"===== {k} =====\n{v}" for k, v in caps.items()), encoding="utf-8")
    print("카드뉴스", len(cards), "장, 쇼츠", f"{sum(durs):.1f}초 ->", OUT)


if __name__ == "__main__":
    main()
