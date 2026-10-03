"""사이트별 고정 계산기 페이지를 만든다 (상위 '계산기' 페이지 + 계산기별 하위 페이지, 멱등).

위젯은 calculator_library의 검증된 계산기를 그대로 쓰고, 그 앞뒤에 계산 방법·유의사항·FAQ 설명 글을
붙여 얇은 페이지가 되지 않게 한다. 페이지 내비게이션은 wp:page-list 블록이라 자동 노출된다.

실행: venv/bin/python scripts/create_calculator_pages.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calculator_library import _render
from smart_affiliate_matcher import add_source_footer
from utils.http import safe_get, safe_post
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

PARENT_SLUG = "calculators"

PAGES: Dict[str, List[Dict[str, Any]]] = {
    "A": [
        {
            "key": "basic_pension",
            "slug": "basic-pension-calculator",
            "title": "기초연금 선정기준액 확인 계산기",
            "summary": "월 소득인정액이 2026년 선정기준액 이하인지 바로 확인합니다.",
            "intro": "기초연금은 만 65세 이상 어르신 중 가구의 월 소득인정액이 선정기준액 이하일 때 받을 수 있습니다. 아래 계산기에 월 소득인정액을 넣으면 단독가구·부부가구 기준과 비교해 줍니다.",
            "how": "<li>2026년 선정기준액은 단독가구 월 247만원, 부부가구 월 395만 2천원입니다(보건복지부 발표).</li><li>소득인정액은 근로·사업·연금 등을 반영한 <strong>소득평가액</strong>에 부동산·금융재산 등을 월 소득으로 환산한 <strong>재산의 소득환산액</strong>을 더한 값입니다.</li><li>부부가구는 부부 합산 소득인정액으로 비교합니다.</li>",
            "notes": "이 계산기는 소득인정액을 이미 알고 있을 때 선정기준액과 비교하는 도구입니다. 소득인정액 자체를 정확히 산정하려면 복지로의 기초연금 모의계산을 이용하세요. 기초연금은 소득인정액 외에 연령·거주 요건 등도 함께 봅니다.",
            "faq": [
                ("소득인정액은 어디서 확인하나요?", "복지로 또는 국민연금공단의 기초연금 모의계산에서 소득·재산 정보를 입력해 산정해 볼 수 있습니다."),
                ("기준액 이하면 무조건 받을 수 있나요?", "아닙니다. 만 65세 이상이어야 하고 그 밖의 요건도 충족해야 하며, 최종 판정은 신청 후 공단 심사로 결정됩니다."),
            ],
        }
    ],
    "B": [
        {
            "key": "telecom_saving",
            "slug": "telecom-saving-calculator",
            "title": "통신비 절감액 계산기",
            "summary": "요금제를 바꿨을 때 절감액과 위약금 회수 기간을 계산합니다.",
            "intro": "현재 통신비와 바꾸려는 요금을 입력하면 월·연 절감액을, 해지 위약금이 있다면 몇 개월이면 본전을 찾는지 계산해 줍니다. 알뜰폰으로 옮기거나 요금제를 낮추기 전에 손익을 먼저 확인해 보세요.",
            "how": "<li>월 절감액 = 현재 월 통신비 − 변경 후 월 요금</li><li>연 절감액 = 월 절감액 × 12</li><li>위약금 회수 기간(개월) = 위약금 ÷ 월 절감액(올림)</li>",
            "notes": "입력한 금액만으로 계산한 단순 산술입니다. 실제로는 약정·결합할인·단말 할부금·프로모션 종료 후 요금 인상 등이 달라질 수 있으니, 변경 전에 통신사 또는 스마트초이스의 요금 비교와 위약금 안내를 함께 확인하세요.",
            "faq": [
                ("위약금이 얼마인지는 어떻게 알 수 있나요?", "가입한 통신사 고객센터나 앱에서 약정 해지 시 위약금을 조회할 수 있습니다."),
                ("프로모션 요금이 끝나면 어떻게 계산하나요?", "프로모션 종료 후의 정상 요금을 '변경 후 월 요금'에 넣어 장기 기준 절감액을 확인해 보세요."),
            ],
        }
    ],
    "C": [
        {
            "key": "us_stock_tax",
            "slug": "us-stock-tax-calculator",
            "title": "해외주식 양도소득세 계산기 (250만원 공제)",
            "summary": "연간 손익통산 후 예상 양도세를 계산합니다.",
            "intro": "해외주식을 팔아 이익이 났다면 다음 해 5월에 양도소득세를 신고·납부해야 합니다. 연간 양도차익과 양도차손을 입력하면 250만원 기본공제 후 예상 세액을 계산해 줍니다.",
            "how": "<li>순차익 = 양도차익 합계 − 양도차손 합계 − 필요경비(매매수수료 등)</li><li>과세표준 = 순차익 − 기본공제 250만원</li><li>세액 = 과세표준 × 22%(소득세 20% + 지방소득세 2%)</li><li>예) 순차익 1,000만원 → (1,000만 − 250만) × 22% = 165만원</li>",
            "notes": "같은 과세연도(1/1~12/31) 안의 손익만 통산되며 손실은 다음 해로 이월되지 않습니다. 신고·납부는 다음 해 5월 1일~31일에 홈택스에서 직접 하며, 증권사가 원천징수하지 않습니다. 양도가액과 취득가액은 거래 시점의 환율로 원화 환산하므로 달러 기준 손익과 실제 과세표준이 다를 수 있습니다.",
            "faq": [
                ("배당금도 250만원 공제에 포함되나요?", "아닙니다. 배당소득은 양도소득과 별개의 세목이며 250만원 기본공제 대상이 아닙니다."),
                ("순차익이 250만원 이하면 세금이 없나요?", "과세표준이 0원이라 낼 세금은 없습니다. 신고 방법은 국세청 안내를 확인하세요."),
            ],
        },
        {
            "key": "dividend_tax",
            "slug": "us-dividend-tax-calculator",
            "title": "미국주식 배당 세후 수령액 계산기",
            "summary": "원천징수 15% 후 수령액과 금융소득종합과세 여부를 확인합니다.",
            "intro": "미국 주식·ETF의 배당금은 현지에서 먼저 15%가 원천징수된 뒤 들어옵니다. 연간 배당금과 다른 금융소득을 넣으면 세후 수령액과 금융소득종합과세(2천만원) 대상 여부를 알려 줍니다.",
            "how": "<li>원천징수세액 = 세전 배당금 × 15%, 세후 수령액 = 세전 배당금 − 원천징수세액</li><li>이자+배당 등 금융소득이 연 2,000만원 이하면 국내에서 추가로 낼 세금은 없습니다.</li><li>2,000만원을 넘으면 금융소득종합과세 대상이 되어 초과분이 다른 소득과 합산되며, 외국납부세액공제를 받을 수 있습니다.</li>",
            "notes": "배당소득은 양도소득세의 250만원 공제 대상이 아닙니다. 실제 종합과세 세액은 다른 소득 구성에 따라 크게 달라지므로 대상에 가까운 경우 국세청 안내 또는 세무 전문가 확인을 권합니다.",
            "faq": [
                ("ETF 분배금도 배당과 같이 계산하나요?", "ETF 분배금도 배당소득으로 분류되며 금융소득 합계에 포함됩니다."),
                ("국내 주식 배당은 어떻게 되나요?", "이 계산기는 미국 주식 배당(15% 원천징수)을 기준으로 합니다. 국내 배당은 원천징수율이 다르니 별도로 확인하세요."),
            ],
        },
        {
            "key": "income_tax",
            "slug": "income-tax-calculator",
            "title": "종합소득세 산출세액 계산기",
            "summary": "과세표준 구간별 세율로 종합소득세 산출세액을 계산합니다.",
            "intro": "종합소득세 과세표준을 입력하면 6~45% 누진세율 구간에 따라 산출세액과 지방소득세 포함 금액을 보여 줍니다. 세액공제·감면 전 금액이므로 신고 전 대략적인 규모를 가늠하는 용도로 쓰세요.",
            "how": "<li>산출세액 = 과세표준 × 세율 − 누진공제액</li><li>1,400만원 이하 6% / 5,000만원 이하 15%(누진공제 126만원) / 8,800만원 이하 24%(576만원) / 1.5억원 이하 35%(1,544만원)</li><li>3억원 이하 38%(1,994만원) / 5억원 이하 40%(2,594만원) / 10억원 이하 42%(3,594만원) / 10억원 초과 45%(6,594만원)</li><li>지방소득세는 산출세액의 10%입니다.</li>",
            "notes": "과세표준은 총수입에서 필요경비·소득공제 등을 뺀 금액이며, 실제 납부세액은 세액공제·감면·기납부세액에 따라 달라집니다. 예) 과세표준 6,000만원 → 6,000만 × 24% − 576만 = 864만원.",
            "faq": [
                ("과세표준은 어떻게 구하나요?", "총수입에서 필요경비(또는 근로소득공제)와 각종 소득공제를 뺀 금액입니다. 홈택스의 모의계산을 활용할 수 있습니다."),
                ("프리랜서 3.3% 원천징수는 어떻게 되나요?", "원천징수된 세액은 이미 낸 세금으로 정산됩니다. 최종 세액에서 이를 빼고 더 내거나 환급받습니다."),
            ],
        },
        {
            "key": "pension_credit",
            "slug": "pension-tax-credit-calculator",
            "title": "연금저축·IRP 세액공제 환급액 계산기",
            "summary": "납입액과 총급여 구간으로 예상 세액공제액을 계산합니다.",
            "intro": "연금저축과 IRP에 납입한 금액은 일정 한도까지 세액공제를 받을 수 있습니다. 납입액과 총급여 구간을 넣으면 예상 환급액을 계산해 줍니다.",
            "how": "<li>세액공제 대상 금액: 연금저축은 연 600만원, IRP를 합산하면 연 900만원까지</li><li>공제율: 총급여 5,500만원 이하 16.5%, 초과 13.2%(지방소득세 포함)</li><li>예) 연금저축 600만원 + IRP 300만원, 16.5% 구간 → 900만원 × 16.5% = 148.5만원</li>",
            "notes": "고소득자는 한도가 달라질 수 있고, 공제받은 금액은 나중에 연금으로 받을 때 연금소득세가 부과됩니다. 중도 해지 시에는 기타소득세가 적용될 수 있으니 조건을 확인하세요.",
            "faq": [
                ("공제율 구분 기준은 무엇인가요?", "일반적으로 총급여 5,500만원(종합소득금액 4,500만원) 이하이면 16.5%, 초과하면 13.2%를 적용합니다."),
                ("연말정산에서 어떻게 반영하나요?", "금융회사가 제출하는 납입 자료가 국세청 연말정산 간소화 서비스에 반영됩니다."),
            ],
        },
        {
            "key": "rent_credit",
            "slug": "rent-tax-credit-calculator",
            "title": "월세 세액공제 환급액 계산기",
            "summary": "연 월세 납부액과 총급여 구간으로 예상 환급액을 계산합니다.",
            "intro": "무주택 근로자가 낸 월세는 일정 한도까지 세액공제를 받을 수 있습니다. 연간 월세와 총급여 구간을 선택하면 예상 환급액을 계산해 줍니다.",
            "how": "<li>대상: 총급여 8,000만원 이하 무주택 세대주 등(주택·세대 요건 별도)</li><li>공제율: 총급여 5,500만원 이하 17%, 5,500만원 초과 15%</li><li>한도: 연 월세 1,000만원까지 → 최대 17% 기준 170만원</li>",
            "notes": "주택 규모, 임대차계약서의 전입신고, 세대주 요건 등 별도 조건이 있어 이 계산기는 금액 규모를 가늠하는 용도입니다. 제도는 개정될 수 있으니 국세청 안내를 확인하세요.",
            "faq": [
                ("월세 이체 증빙이 필요한가요?", "월세 납부 사실을 확인할 수 있는 증빙(계좌이체 내역 등)과 임대차계약서 사본 등이 필요합니다."),
                ("놓쳤다면 지금이라도 받을 수 있나요?", "경정청구 제도로 지난 신고분을 정정해 환급받을 수 있는 경우가 있으니 국세청 안내를 확인하세요."),
            ],
        },
        {
            "key": "early_pension",
            "slug": "early-pension-calculator",
            "title": "국민연금 조기수령 감액 계산기",
            "summary": "조기노령연금을 앞당겨 받을 때의 감액 규모를 계산합니다.",
            "intro": "국민연금은 정해진 수급 시작 나이보다 최대 5년 일찍 받을 수 있지만 그만큼 연금액이 줄어듭니다. 정상 수급 시 예상 월 연금액과 앞당기는 기간을 넣으면 감액 규모를 보여 줍니다.",
            "how": "<li>1년 앞당길 때마다 6%씩 감액되어 5년이면 최대 30% 감액</li><li>조기수령 월 연금액 = 정상 월 연금액 × (1 − 6% × 앞당긴 연수)</li><li>예) 월 100만원, 3년 앞당김 → 18% 감액, 월 82만원</li>",
            "notes": "조기노령연금은 가입기간이 10년 이상이고 본인이 신청해야 하며, 한번 선택하면 감액률이 평생 유지됩니다. 소득이 있는 업무에 종사하면 지급이 제한될 수 있으니 국민연금공단 안내를 확인하세요.",
            "faq": [
                ("앞당기는 게 유리한가요?", "수명과 소득 상황에 따라 달라 일률적으로 말하기 어렵습니다. 감액 규모와 총 수령액을 비교해 신중히 결정하세요."),
                ("취소할 수 있나요?", "한번 조기수령을 선택하면 되돌리기 어렵습니다. 신청 전 공단에서 예상 연금액을 조회해 보세요."),
            ],
        },
    ],
}


def _find_page(wp: WordPressClient, slug: str) -> Optional[Dict[str, Any]]:
    resp = safe_get(
        wp._api_url("wp/v2/pages"),
        headers=wp._auth_header(),
        params={"slug": slug, "status": "publish,draft", "_fields": "id,link"},
        timeout=15,
    )
    if resp is not None and resp.status_code == 200 and resp.json():
        return resp.json()[0]
    return None


def _upsert(wp: WordPressClient, slug: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = _find_page(wp, slug)
    url = wp._api_url(f"wp/v2/pages/{existing['id']}") if existing else wp._api_url("wp/v2/pages")
    resp = safe_post(
        url,
        headers={**wp._auth_header(), "Content-Type": "application/json"},
        data=json.dumps({**payload, "slug": slug, "status": "publish"}),
        timeout=30,
    )
    if resp is not None and resp.status_code in (200, 201):
        return resp.json()
    logger.warning("페이지 저장 실패: %s (%s)", slug, getattr(resp, "status_code", "N/A"))
    return None


def _child_html(site: str, page: Dict[str, Any]) -> str:
    faq = "".join(
        f'<details style="margin:8px 0;"><summary style="cursor:pointer;font-weight:bold;">{q}</summary><p>{a}</p></details>'
        for q, a in page["faq"]
    )
    html = (
        f"<p>{page['intro']}</p>"
        f"{_render(page['key'])}"
        f"<h2>계산 방법과 기준</h2><ul>{page['how']}</ul>"
        f"<h2>알아두세요</h2><p>{page['notes']}</p>"
        f"<h2>자주 묻는 질문</h2>{faq}"
    )
    return add_source_footer(html, site)


def run(site: str) -> None:
    wp = WordPressClient(site)
    if not wp.is_configured:
        return
    pages = PAGES[site]

    intro = (
        "<p>자주 헷갈리는 계산을 직접 해볼 수 있는 모의 계산기 모음입니다. 모든 계산기는 공식 기준을 바탕으로 한 "
        "참고용이며, 실제 결과는 해당 기관에서 확인해 주세요.</p>"
    )
    parent = _upsert(wp, PARENT_SLUG, {"title": "계산기", "content": intro})
    if not parent:
        return
    items = []
    for page in pages:
        saved = _upsert(
            wp,
            page["slug"],
            {"title": page["title"], "content": _child_html(site, page), "parent": parent["id"]},
        )
        logger.info("[Site %s] %s -> %s", site, page["slug"], saved["link"] if saved else "FAIL")
        if saved:
            items.append(f'<li><a href="{saved["link"]}"><strong>{page["title"]}</strong></a> - {page["summary"]}</li>')
    _upsert(wp, PARENT_SLUG, {"title": "계산기", "content": intro + f"<ul>{''.join(items)}</ul>"})


if __name__ == "__main__":
    for key in ("A", "B", "C"):
        run(key)

