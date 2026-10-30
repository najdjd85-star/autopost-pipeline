"""사이트를 폰 크기로 열어 재료를 누르고 결과·레시피를 보는 과정을 화면 녹화(webm)로 찍는다(무료, 내 PC).

손가락으로 누르는 자리에 주황색 동그라미가 퍼지도록 해서, 영상에서 '눌렀다'가 보이게 한다.
결과: site_d/promo/out/screens/live.webm + live_marks.json (각 장면이 시작한 시각, 영상 합칠 때 설명 글자를 맞추는 데 쓴다)

사용: venv/Scripts/python.exe -X utf8 site_d/promo/record_demo.py [--url 주소]
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "out" / "screens"
VIEW = {"width": 412, "height": 892}

TAP_JS = """
(() => {
  const css = '.tapdot{position:fixed;width:54px;height:54px;margin:-27px 0 0 -27px;border-radius:50%;background:rgba(224,84,10,.30);border:3px solid rgba(224,84,10,.85);pointer-events:none;z-index:2147483647;animation:tapd .6s ease-out forwards}@keyframes tapd{from{transform:scale(.35);opacity:1}to{transform:scale(1.6);opacity:0}}';
  const add = () => { const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s); };
  if (document.head) add(); else addEventListener('DOMContentLoaded', add);
  addEventListener('click', (e) => {
    const d = document.createElement('div'); d.className = 'tapdot'; d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px';
    document.body.appendChild(d); setTimeout(() => d.remove(), 700);
  }, true);
})();
"""


def run(base: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "_rec"
    shutil.rmtree(tmp, ignore_errors=True)
    marks = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=1, is_mobile=True, has_touch=True, locale="ko-KR",
                                  record_video_dir=str(tmp), record_video_size={"width": 412, "height": 892})
        ctx.add_init_script(TAP_JS)
        page = ctx.new_page()
        t0 = time.time()
        mark = lambda k: marks.__setitem__(k, round(time.time() - t0, 2))  # noqa: E731
        page.goto(base + "/", wait_until="networkidle")
        page.wait_for_timeout(1200)
        mark("type")
        page.locator("#q").click()
        page.wait_for_timeout(500)
        page.keyboard.type("계란", delay=260)
        page.wait_for_timeout(1500)
        page.locator("#q").fill("")
        page.evaluate("document.activeElement && document.activeElement.blur(); window.scrollTo(0,0)")
        page.wait_for_timeout(700)
        mark("pick")
        for n in ("대파", "양파", "계란", "김치", "두부"):
            loc = page.locator("#cats .tile", has_text=n).first
            loc.scroll_into_view_if_needed()
            page.wait_for_timeout(450)
            loc.click()
            page.wait_for_timeout(900)
        mark("result")
        page.locator("#bar button, #bar a").first.click()
        page.wait_for_timeout(2600)
        mark("recipe")
        page.locator("#results a[href*='recipes/']").first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        mark("steps")
        for _ in range(7):
            page.mouse.wheel(0, 260)
            page.wait_for_timeout(500)
        page.wait_for_timeout(1800)
        mark("end")
        ctx.close()
        browser.close()
    vids = sorted(tmp.glob("*.webm"))
    if not vids:
        raise SystemExit("녹화 파일이 만들어지지 않았어요.")
    shutil.copy(vids[-1], OUT / "live.webm")
    (OUT / "live_marks.json").write_text(json.dumps(marks, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print("저장:", OUT / "live.webm", marks)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8791")
    a = ap.parse_args()
    run(a.url.rstrip("/"))
