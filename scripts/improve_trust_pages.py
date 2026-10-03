"""소개·문의 페이지를 보강하고 개인정보처리방침에 광고/제휴/쿠키 고지를 추가한다 (멱등).

실행: venv/bin/python scripts/improve_trust_pages.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.http import safe_get, safe_post
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

CONTACT_EMAIL = "najdjd85@gmail.com"

SITES = {
    "A": {
        "headline": "정부지원금 안내소",
        "topics": "생계급여, 근로장려금, 기초연금, 청년·육아·주거·고용 지원 등 정부지원금의 신청 조건과 자주 탈락하는 이유",
        "sources": [
            ("복지로", "https://www.bokjiro.go.kr"),
            ("정부24", "https://www.gov.kr"),
            ("보건복지부", "https://www.mohw.go.kr"),
        ],
        "official": "복지로(bokjiro.go.kr)",
    },
    "B": {
        "headline": "통신비 절약 안내소",
        "topics": "알뜰폰 요금제, 선택약정·공시지원금, 인터넷 결합할인, 해외 로밍, 렌탈 서비스와 위약금 등 매달 나가는 고정비를 줄이는 방법",
        "sources": [
            ("스마트초이스", "https://www.smartchoice.or.kr"),
            ("방송통신위원회", "https://www.kcc.go.kr"),
            ("한국소비자원", "https://www.kca.go.kr"),
        ],
        "official": "스마트초이스(smartchoice.or.kr)",
    },
    "C": {
        "headline": "세금·연금 안내소",
        "topics": "연말정산, 종합소득세, 해외주식 양도소득세, 증여·상속세, 국민연금과 개인연금 등 세금 환급과 절세·연금 제도",
        "sources": [
            ("국세청 홈택스", "https://www.hometax.go.kr"),
            ("국세청", "https://www.nts.go.kr"),
            ("국민연금공단", "https://www.nps.or.kr"),
        ],
        "official": "국세청 홈택스(hometax.go.kr)",
    },
}

PRIVACY_AD_SECTION = f"""
<h2>광고 및 쿠키 사용 안내</h2>
<p>본 사이트는 Google 등 제3자 광고 사업자가 광고를 게재할 수 있으며, 이 과정에서 쿠키(cookie)를 사용해 방문자의 이 사이트 및 다른 웹사이트 방문 기록을 바탕으로 광고를 제공할 수 있습니다. Google이 파트너 사이트의 정보를 이용하는 방식은 <a href="https://policies.google.com/technologies/partner-sites" target="_blank" rel="noopener noreferrer">Google 정책 페이지</a>에서 확인할 수 있습니다.</p>
<p>맞춤 광고를 원하지 않으시면 <a href="https://adssettings.google.com" target="_blank" rel="noopener noreferrer">Google 광고 설정</a> 또는 <a href="https://www.aboutads.info" target="_blank" rel="noopener noreferrer">aboutads.info</a>에서 개인 최적화 광고를 해제할 수 있으며, 브라우저 설정에서 쿠키 저장을 거부할 수도 있습니다. 다만 쿠키를 차단하면 일부 기능이 제한될 수 있습니다.</p>
<h2>제휴 마케팅 고지</h2>
<p>일부 글에는 링크프라이스, 쿠팡 파트너스 등 제휴 링크가 포함되어 있으며, 해당 링크를 통해 이용·구매가 이루어지면 사이트 운영자가 일정액의 수수료를 받을 수 있습니다. 제휴 링크는 방문자에게 추가 비용을 발생시키지 않으며, 제휴 링크 클릭 시 제휴사가 자체 쿠키로 방문을 식별할 수 있습니다.</p>
<h2>개인정보 관련 문의</h2>
<p>개인정보 처리와 관련한 문의는 <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>로 보내주세요.</p>
"""


def about_html(cfg: dict, privacy_url: str, contact_url: str) -> str:
    links = " · ".join(
        f'<a href="{url}" target="_blank" rel="noopener noreferrer">{name}</a>' for name, url in cfg["sources"]
    )
    return f"""<h2>{cfg['headline']}</h2>
<p>데일리픽스포인트 {cfg['headline']}는 {cfg['topics']}를 알기 쉽게 정리해 전하는 정보 사이트입니다. 제도 이름은 알아도 내가 대상인지, 어떤 조건에서 탈락하는지 한눈에 보기 어려운 경우가 많아서, 공식 기준을 바탕으로 실제로 헷갈리는 지점을 중심으로 풀어 씁니다.</p>
<h2>콘텐츠 작성 원칙</h2>
<ul>
<li><strong>공식 자료 우선</strong>: 금액·소득 기준·세율·기한 등은 공공기관 안내를 기준으로 정리하며, 확실하지 않은 수치는 단정하지 않고 공식 사이트 확인을 안내합니다. 주요 참고처: {links}</li>
<li><strong>작성 방식 공개</strong>: 본 사이트의 글은 AI 도구의 도움을 받아 작성됩니다. 다만 위 공식 자료를 기준으로 정리하며, 가상 인물이 등장하는 사례는 이해를 돕기 위한 예시입니다.</li>
<li><strong>기준일 표기</strong>: 제도와 수치는 바뀔 수 있어 각 글은 게시일 기준 정보입니다. 최신 내용은 글 하단의 공식 사이트에서 확인해 주세요.</li>
<li><strong>오류 정정</strong>: 잘못된 내용을 발견하시면 <a href="{contact_url}">문의하기</a>로 알려 주세요. 확인 후 수정합니다.</li>
</ul>
<h2>이용 시 유의사항</h2>
<p>본 사이트의 정보는 일반적인 안내이며 개인별 자격·금액·세액을 보장하지 않습니다. 정확한 판정은 반드시 {cfg['official']} 등 해당 기관에서 확인하시기 바랍니다. 글에 포함된 계산기는 이해를 돕는 참고용 모의 계산입니다.</p>
<h2>광고 및 제휴 고지</h2>
<p>일부 글에는 제휴 링크가 포함되어 수수료가 발생할 수 있으며, 향후 광고가 게재될 수 있습니다. 광고·제휴 여부와 관계없이 글의 내용은 공식 기준에 따라 작성합니다. 자세한 내용은 <a href="{privacy_url}">개인정보처리방침</a>을 참고해 주세요.</p>
<p>운영: 데일리픽스포인트 · 문의: <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></p>
"""


def contact_html(privacy_url: str) -> str:
    return f"""<h2>문의하기</h2>
<p>사이트 운영, 콘텐츠 오류 제보, 제휴 문의는 아래 이메일로 보내 주세요.</p>
<p><strong>이메일</strong>: <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></p>
<h2>문의 유형별 안내</h2>
<ul>
<li><strong>오류 제보</strong>: 해당 글의 주소, 수정이 필요한 문장, 근거가 되는 공식 자료 링크를 함께 보내 주시면 확인이 빠릅니다.</li>
<li><strong>제휴·광고 문의</strong>: 회사명과 제안 내용을 간단히 적어 주세요.</li>
<li><strong>개인정보·저작권 문의</strong>: 요청 내용과 해당 글 주소를 알려 주세요. 처리 방침은 <a href="{privacy_url}">개인정보처리방침</a>에서 확인할 수 있습니다.</li>
</ul>
<p>개인별 지원금 수급 여부, 세금 신고 대행, 상담은 제공하지 않습니다. 해당 사항은 공식 기관에 문의해 주세요.</p>
"""


def _find_page(wp: WordPressClient, slug_candidates: list[str]) -> dict | None:
    for slug in slug_candidates:
        resp = safe_get(
            wp._api_url("wp/v2/pages"),
            headers=wp._auth_header(),
            params={"slug": slug, "context": "edit", "status": "publish"},
            timeout=15,
        )
        if resp is not None and resp.status_code == 200 and resp.json():
            return resp.json()[0]
    return None


def _update(wp: WordPressClient, page_id: int, content: str) -> bool:
    resp = safe_post(
        wp._api_url(f"wp/v2/pages/{page_id}"),
        headers={**wp._auth_header(), "Content-Type": "application/json"},
        data=json.dumps({"content": content}),
        timeout=20,
    )
    return resp is not None and resp.status_code in (200, 201)


def run(site: str) -> None:
    wp = WordPressClient(site)
    cfg = SITES[site]
    about = _find_page(wp, [quote("소개").lower(), "소개"])
    contact = _find_page(wp, [quote("문의하기").lower(), "문의하기"])
    privacy = _find_page(wp, ["privacy-policy", "privacy-policy-2"])

    privacy_url = privacy["link"] if privacy else "/"
    contact_url = contact["link"] if contact else "/"
    if about:
        logger.info(
            "[Site %s] 소개 페이지 갱신: %s", site, _update(wp, about["id"], about_html(cfg, privacy_url, contact_url))
        )
    if contact:
        logger.info("[Site %s] 문의 페이지 갱신: %s", site, _update(wp, contact["id"], contact_html(privacy_url)))
    if privacy:
        raw = privacy.get("content", {}).get("raw", "")
        if "광고 및 쿠키 사용 안내" in raw:
            logger.info("[Site %s] 개인정보처리방침: 이미 광고 고지 있음 - 건너뜀", site)
        else:
            logger.info(
                "[Site %s] 개인정보처리방침 광고 고지 추가: %s",
                site,
                _update(wp, privacy["id"], raw + "\n" + PRIVACY_AD_SECTION),
            )


if __name__ == "__main__":
    for key in ("A", "B", "C"):
        run(key)

