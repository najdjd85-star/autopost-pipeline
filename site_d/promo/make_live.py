"""화면 녹화(live.webm)를 폰 틀에 넣고 단계별 설명 글자를 입혀 세로 영상(1080x1920)으로 만든다(무료, 내 PC).

먼저 record_demo.py 로 녹화해 둔다. 결과: site_d/promo/out/demo/short_live.mp4

사용: venv/Scripts/python.exe -X utf8 site_d/promo/make_live.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

import render as R  # noqa: E402

HERE = Path(__file__).resolve().parent
SCR = HERE / "out" / "screens"
OUT = HERE / "out" / "demo"
W, H = 1080, 1920


def layout():
    top = 230
    ptop = top + 250
    ph = H - ptop - 150
    pw = int(ph * 390 / 844)
    return top, ptop, pw, ph


def make_bg_and_bezel():
    top, ptop, pw, ph = layout()
    img, d = R.base(W, H)
    bez = 14
    ow, oh = pw + bez * 2, ph + bez * 2
    x = (W - ow) // 2
    shadow = Image.new("RGBA", (ow + 160, oh + 160), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((80, 100, 80 + ow, 100 + oh), 66, fill=(31, 27, 24, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(28))
    img.paste(shadow, (x - 80, ptop - 80), shadow)
    R.footer(d, W, H)
    img.save(OUT / "_bg.png")
    frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(frame)
    fd.rounded_rectangle((x, ptop, x + ow, ptop + oh), 62, fill=(31, 27, 24, 255))
    hole = Image.new("L", (W, H), 0)
    ImageDraw.Draw(hole).rounded_rectangle((x + bez, ptop + bez, x + bez + pw - 1, ptop + bez + ph - 1), 50, fill=255)
    alpha = frame.getchannel("A")
    alpha = Image.composite(Image.new("L", (W, H), 0), alpha, hole)   # 화면 자리는 비워 둔다(영상이 비쳐 보임)
    frame.putalpha(alpha)
    frame.save(OUT / "_bezel.png")
    return x + bez, ptop + bez, pw, ph


def caption(name: str, step, title: str, sub: str) -> Path:
    top = layout()[0]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 글자 바탕(배경색)으로 덮어서 이전 글이 겹쳐 보이지 않게 한다
    d.rectangle((0, top - 30, W, top + 220), fill=R.BG + (255,))
    tx = R.M
    if step:
        d.ellipse((R.M, top, R.M + 84, top + 84), fill=R.ACC)
        d.text((R.M + 42, top + 42), str(step), font=R.font(52, 800), fill=R.WHITE, anchor="mm")
        tx = R.M + 112
    y = R.text_block(d, (tx, top - 4), title, R.font(70, 800), R.INK, W - tx - R.M, 1.2)
    if sub:
        R.text_block(d, (tx, y + 6), sub, R.font(36, 500), R.MUT, W - tx - R.M, 1.4)
    p = OUT / f"_cap_{name}.png"
    img.save(p)
    return p


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    marks = json.loads((SCR / "live_marks.json").read_text(encoding="utf-8"))
    vx, vy, pw, ph = make_bg_and_bezel()
    end = marks["end"]
    segs = [
        ("0", 0.0, marks["type"], None, "냉장고 열었는데 곧 버릴 재료만?", "이렇게 쓰면 바로 해결돼"),
        ("1", marks["type"], marks["pick"], 1, "이름을 쳐도 돼", "재료든 요리 이름이든 치면 바로 찾아줘"),
        ("2", marks["pick"], marks["result"], 2, "재료를 눌러서 담아", "냉장고에 있는 거 아무거나 눌러봐"),
        ("3", marks["result"], marks["recipe"], 3, "지금 되는 요리가 바로 나와", "재료 다 있는 요리부터 보여줘"),
        ("4", marks["recipe"], end, 4, "순서까지 다 정리돼 있어", "분량 그대로 따라 하면 끝"),
    ]
    caps = [(caption(n, st, t, s), a, b) for n, a, b, st, t, s in segs]
    outro = R.outro(W, H, "남은 재료 빨리 처분하고 싶으면", "여기 한번 들어가봐")
    outro.save(OUT / "_outro.png")

    dur = end + 0.3
    inputs = ["-loop", "1", "-i", str(OUT / "_bg.png"), "-i", str(SCR / "live.webm"), "-loop", "1", "-i", str(OUT / "_bezel.png")]
    for p, _a, _b in caps:
        inputs += ["-loop", "1", "-i", str(p)]
    fc = [f"[1:v]scale={pw}:{ph}:flags=lanczos,unsharp=5:5:0.8,setpts=PTS-STARTPTS[v]", f"[0:v][v]overlay={vx}:{vy}[a]", "[a][2:v]overlay=0:0[b]"]
    last = "b"
    for i, (_p, a, b) in enumerate(caps):
        nxt = f"c{i}"
        fc.append(f"[{last}][{3 + i}:v]overlay=0:0:enable='between(t,{a},{b + (0.3 if i == len(caps) - 1 else 0)})'[{nxt}]")
        last = nxt
    main_mp4 = OUT / "_main.mp4"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", f"[{last}]", "-t", f"{dur:.2f}", "-r", "30",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(main_mp4)]
    subprocess.run(cmd, check=True, capture_output=True)
    outro_mp4 = OUT / "_outro.mp4"
    subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", str(OUT / "_outro.png"), "-t", "3", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(outro_mp4)],
                   check=True, capture_output=True)
    lst = OUT / "_list.txt"
    lst.write_text(f"file '{main_mp4.name}'\nfile '{outro_mp4.name}'\n", encoding="utf-8")
    final = OUT / "short_live.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(final)], check=True, capture_output=True)
    print("완성:", final, f"{dur + 3:.1f}초")


if __name__ == "__main__":
    main()
