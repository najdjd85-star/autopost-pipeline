"""화면 녹화(live.webm)를 폰 틀에 넣고 단계별 설명 글자·오프닝 실사 클립·음성을 입혀 세로 영상(1080x1920)으로 만든다(무료, 내 PC).

순서: 오프닝(재료 버리는 AI 이미지 + 후킹 글자) → 사이트 사용 화면(폰 틀, 결과 구간 확대) → 끝 장면(행동 유도).
먼저 narrate.py(음성), record_demo.py(녹화)를 실행해 둔다. 결과: site_d/promo/out/demo/short_live.mp4(소리 없음), short_live_voice.mp4(소리 있음)

오프닝은 AI 이미지(make_open_image.py 로 만들어 open_ai.png 로 둔다)이다.

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
STOCK = SCR / "stock"
W, H = 1080, 1920
VW, VH = 412, 892   # 녹화 해상도


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
    ImageDraw.Draw(frame).rounded_rectangle((x, ptop, x + ow, ptop + oh), 62, fill=(31, 27, 24, 255))
    hole = Image.new("L", (W, H), 0)
    ImageDraw.Draw(hole).rounded_rectangle((x + bez, ptop + bez, x + bez + pw - 1, ptop + bez + ph - 1), 50, fill=255)
    alpha = Image.composite(Image.new("L", (W, H), 0), frame.getchannel("A"), hole)   # 화면 자리는 비워 둔다(영상이 비쳐 보임)
    frame.putalpha(alpha)
    frame.save(OUT / "_bezel.png")
    return x + bez, ptop + bez, pw, ph


def caption(name: str, step, title: str, sub: str) -> Path:
    top = layout()[0]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((0, top - 30, W, top + 220), fill=R.BG + (255,))   # 이전 글이 겹쳐 보이지 않게 배경색으로 덮는다
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


def hook_text() -> Path:
    """오프닝 위에 올리는 후킹 글자(아래쪽 어둡게 + 흰 글자)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        grad.putpixel((0, y), int(max(0, (y - H * 0.50) / (H * 0.50)) * 190))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    shade.putalpha(grad.resize((W, H)))
    img.alpha_composite(shade)
    d = ImageDraw.Draw(img)
    y = int(H * 0.70)
    for t, c in (("냉장고 열었는데", R.WHITE), ("곧 버릴 재료만 잔뜩?", (255, 196, 80))):
        d.text((W // 2, y), t, font=R.font(112, 800), fill=c, anchor="ma", stroke_width=7, stroke_fill=(0, 0, 0))
        y += 150
    p = OUT / "_hooktext.png"
    img.save(p)
    return p


def run(cmd: list) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("ffmpeg 실패:\n" + r.stderr[-1500:])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    marks = json.loads((SCR / "live_marks.json").read_text(encoding="utf-8"))
    nar = json.loads((SCR / "narr.json").read_text(encoding="utf-8")) if (SCR / "narr.json").exists() else {}
    vx, vy, pw, ph = make_bg_and_bezel()
    for f in ("_open.mp4", "_main.mp4", "_outro.mp4"):
        (OUT / f).unlink(missing_ok=True)

    # 1) 오프닝: 곧 버릴 재료를 쓰레기통에 넣는 AI 이미지(천천히 다가가는 움직임) + 후킹 글자
    have_open = (SCR / "open_ai.png").exists()
    d0 = max(2.4, nar.get("hook", 2.4) + 0.35) if have_open else 0.0
    if have_open:
        frames = int(d0 * 30)
        fc = (f"[0:v]scale=1620:2880:flags=lanczos,zoompan=z='1.0+0.16*on/{frames}':x='iw/2-(iw/zoom/2)+4*sin(on/5)':y='ih/2-(ih/zoom/2)+4*cos(on/6)':d={frames}:s=1080x1920:fps=30,"
              "eq=brightness=-0.07:saturation=1.05[c];[c][1:v]overlay=0:0[o]")
        run(["ffmpeg", "-y", "-loop", "1", "-i", str(SCR / "open_ai.png"), "-loop", "1", "-i", str(hook_text()), "-filter_complex", fc, "-map", "[o]",
             "-t", f"{d0:.2f}", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(OUT / "_open.mp4")])

    # 2) 사용 화면: 입력을 시작하기 조금 전부터. 결과 구간은 '재료 다 있어요 / 없는 재료 사러가기' 쪽으로 확대
    ts = max(0.0, marks["type"] - 0.4)
    end = marks["end"]
    main_len = end - ts + 0.3
    rel = {k: marks[k] - ts for k in ("type", "pick", "result", "recipe")}
    segs = [("1", 0.0, rel["pick"], 1, "이름을 쳐도 돼", "재료든 요리 이름이든 치면 바로 찾아줘"),
            ("2", rel["pick"], rel["result"], 2, "재료를 톡톡 눌러서 담아", "냉장고에 있는 거 아무거나 눌러봐"),
            ("3", rel["result"], rel["recipe"], 3, "지금 되는 요리가 바로 나와", "재료 다 있는 요리부터 보여줘"),
            ("4", rel["recipe"], main_len, 4, "순서까지 다 정리돼 있어", "분량 그대로 따라 하면 끝")]
    caps = [(caption(n, st, t, s), a, b) for n, a, b, st, t, s in segs]
    za, zb = marks.get("zoom_a", 0) - ts, marks.get("zoom_b", 0) - ts
    cx, cy = marks.get("zoom_cx", VW / 2), marks.get("zoom_cy", VH / 2)
    if zb > za:
        zexp = f"(1+0.5*between(t,{za:.2f},{zb:.2f})*min(1,(t-{za:.2f})/0.5)*min(1,({zb:.2f}-t)/0.5))"
        zoom = (f"scale=w='trunc({VW}*{zexp}/2)*2':h='trunc({VH}*{zexp}/2)*2':eval=frame,"
                f"crop={VW}:{VH}:x='min(max({cx:.1f}*iw/{VW}-{VW / 2},0),iw-{VW})':y='min(max({cy:.1f}*ih/{VH}-{VH / 2},0),ih-{VH})',")
    else:
        zoom = ""
    inputs = ["-loop", "1", "-i", str(OUT / "_bg.png"), "-i", str(SCR / "live.webm"), "-loop", "1", "-i", str(OUT / "_bezel.png")]
    for p, _a, _b in caps:
        inputs += ["-loop", "1", "-i", str(p)]
    fc = [f"[1:v]trim=start={ts:.2f},setpts=PTS-STARTPTS,{zoom}scale={pw}:{ph}:flags=lanczos,unsharp=5:5:0.8[v]",
          f"[0:v][v]overlay={vx}:{vy}[a]", "[a][2:v]overlay=0:0[b]"]
    last = "b"
    for i, (_p, a, b) in enumerate(caps):
        fc.append(f"[{last}][{3 + i}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[c{i}]")
        last = f"c{i}"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", f"[{last}]", "-t", f"{main_len:.2f}", "-r", "30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(OUT / "_main.mp4")])

    # 3) 끝 장면: 행동 유도 + 살짝 커지는 효과
    outro = R.outro(W, H, "오늘 저녁 뭐 먹지 고민 말고", "프로필 링크 클릭!")
    outro.save(OUT / "_outro.png")
    outro_len = max(3.2, nar.get("outro", 0) + 0.9)
    frames = int(outro_len * 30)
    run(["ffmpeg", "-y", "-loop", "1", "-i", str(OUT / "_outro.png"), "-vf", f"zoompan=z='min(1.0+0.0009*on,1.07)':d={frames}:s=1080x1920:fps=30",
         "-t", f"{outro_len:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(OUT / "_outro.mp4")])

    parts = [f for f in ("_open.mp4", "_main.mp4", "_outro.mp4") if (OUT / f).exists()]
    (OUT / "_list.txt").write_text("".join(f"file '{f}'\n" for f in parts), encoding="utf-8")
    final = OUT / "short_live.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(OUT / "_list.txt"), "-c", "copy", str(final)])
    total = d0 + main_len + outro_len

    # 4) 음성
    lines = [(k, SCR / f"narr_{k}.mp3") for k in ("hook", "type", "pick", "result", "recipe", "outro") if (SCR / f"narr_{k}.mp3").exists()]
    if lines:
        starts = {"hook": 0.15, "type": d0 + rel["type"] + 0.15, "pick": d0 + rel["pick"] + 0.1, "result": d0 + rel["result"] + 0.35,
                  "recipe": d0 + rel["recipe"] + 0.3, "outro": d0 + main_len + 0.15}
        cmd = ["ffmpeg", "-y", "-i", str(final)]
        for _k, f in lines:
            cmd += ["-i", str(f)]
        pf = [f"[{i + 1}:a]adelay={int(starts[k] * 1000)}|{int(starts[k] * 1000)}[a{i}]" for i, (k, _f) in enumerate(lines)]
        mix = "".join(f"[a{i}]" for i in range(len(lines))) + f"amix=inputs={len(lines)}:normalize=0:duration=longest,volume=1.4[aout]"
        voiced = OUT / "short_live_voice.mp4"
        run(cmd + ["-filter_complex", ";".join(pf + [mix]), "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", str(voiced)])
        print("음성 영상:", voiced)
    print("완성:", final, f"{total:.1f}초")


if __name__ == "__main__":
    main()
