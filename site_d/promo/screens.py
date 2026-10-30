"""홍보용 실제 화면 캡처(스크린샷 5장)를 사이트에서 직접 찍는다(무료, 내 PC).

playwright + 설치된 Chrome 으로 폰 크기(390x844)에서 사이트를 열어 재료를 누르고 결과·레시피를 보여 주는 장면을 찍는다.
기본 주소는 내 PC 미리보기 서버(http://127.0.0.1:8791, site_d/dist). 공개 사이트로 찍으려면 --url https://cook.dailyfixpoint.com

사용:
  venv/Scripts/python.exe -X utf8 site_d/promo/screens.py [--url 주소]
결과: site_d/promo/out/screens/ (shot1_search.png, shot2_pick.png, shot3_result.png, shot4_recipe.png, shot5_steps.png)
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "out" / "screens"
VIEW = {"width": 390, "height": 844}


def tap_tile(page, name: str) -> None:
    page.locator("#cats .tile", has_text=name).first.click()
    page.wait_for_timeout(350)


def run(base: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=3, is_mobile=True, has_touch=True, locale="ko-KR")
        page = ctx.new_page()
        page.goto(base + "/", wait_until="networkidle")
        page.wait_for_timeout(900)
        # 1) 처음 화면 + 검색창에 입력
        page.locator("#q").click()
        page.keyboard.type("계란", delay=160)
        page.wait_for_timeout(700)
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "shot1_search.png"))
        page.locator("#q").fill("")
        page.locator("#q").blur()
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(300)
        # 2) 재료 누르기
        for n in ("계란", "김치", "두부", "대파", "양파"):
            tap_tile(page, n)
        page.evaluate("document.querySelector('#cats .aisle').scrollIntoView({block:'start'})")   # 고른 재료가 어두운 칸으로 보이는 화면
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "shot2_pick.png"))
        # 3) 결과
        page.evaluate("var e=document.getElementById('selected'); window.scrollTo(0, e.getBoundingClientRect().top + window.scrollY - 200)")   # 내가 고른 재료 + 바로 되는 요리
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / "shot3_result.png"))
        # 4) 레시피 페이지
        link = page.locator("#results a[href*='recipes/']").first
        link.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / "shot4_recipe.png"))
        page.evaluate("document.querySelector('ol.steps').scrollIntoView({block:'start'})")
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / "shot5_steps.png"))
        ctx.close()
        browser.close()
    print("저장:", OUT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8791")
    a = ap.parse_args()
    run(a.url.rstrip("/"))
