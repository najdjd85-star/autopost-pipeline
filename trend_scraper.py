"""
실시간 트렌드 및 공식 팩트 수집 모듈.

공공데이터포털(보조금24) API, 대한민국 정책브리핑 RSS, 구글 트렌드(한국) 일별
급상승 RSS를 수집해 오늘의 핫토픽 브리핑 텍스트를 만든다. 세 소스 중 일부가
실패해도 나머지로 계속 진행하며, 전부 실패하면 오프라인 스텁 브리핑을 반환한다
(절대 예외를 전파하지 않는다).
"""
from __future__ import annotations

from typing import Dict, List

import feedparser

from config import settings
from constants import SITE_KEYS, SITE_LABELS
from utils.http import safe_get
from utils.logger import get_logger

logger = get_logger(__name__)

POLICY_BRIEFING_RSS = "https://www.korea.kr/rss/policy.xml"
GOOGLE_TRENDS_DAILY_RSS_KR = "https://trends.google.com/trending/rss?geo=KR"
PUBLIC_DATA_SUBSIDY_API = (
    "https://api.odcloud.kr/api/gov24/v3/serviceList"  # 보조금24(정부24) 서비스 목록 API
)

# 사이트별 핵심 키워드 시드 (트렌드 소스가 전부 실패했을 때의 최소 폴백에도 사용)
SITE_SEED_KEYWORDS = {
    "A": [
        "정부지원금", "생계급여", "근로장려금", "청년지원금", "기초연금", "한부모가정 지원금",
        "청년월세 지원", "청년도약계좌", "국민취업지원제도", "에너지바우처", "부모급여",
        "주거급여", "자녀장려금", "긴급복지지원", "국민내일배움카드", "아동수당",
    ],
    "B": [
        "알뜰폰 요금제", "인터넷 결합할인", "정수기 렌탈", "휴대폰 공시지원금", "정수기 렌탈 위약금", "인터넷 해지위약금",
        "선택약정 할인", "자급제폰 구매", "휴대폰 약정 위약금", "해외 로밍 요금제", "eSIM 개통",
        "가족결합 할인", "인터넷 이사 이전설치", "공기청정기 렌탈", "안마의자 렌탈", "중고폰 보상판매",
    ],
    "C": [
        "해외주식 양도세", "미국주식 배당세", "해외주식 손익통산",
        "해외주식 연말 매도 절세", "국내시장 복귀계좌",
        "연말정산 환급", "종합소득세 환급", "국민연금 조기수령", "월세 세액공제", "부가가치세 환급", "기초연금 신청",
        "프리랜서 3.3% 환급", "ISA 비과세 한도", "증여세 공제", "의료비 세액공제",
        "교육비 세액공제", "퇴직금 세금", "상속세 공제", "연금저축 세액공제",
        "국민연금 추납", "국민연금 수령액", "주택연금", "연금소득세 분리과세", "IRP 중도인출",
        "퇴직연금 수령 방법", "국민연금 출산 크레딧",
        "1세대1주택 양도세 비과세", "생애최초 취득세 감면", "종합부동산세", "재산세 납부", "자동차세 연납",
        "간이과세자 부가세 신고", "종합소득세 중간예납", "경정청구 환급",
        "기부금 세액공제", "신용카드 소득공제", "자녀 세액공제", "중소기업 취업청년 소득세 감면",
        "증여세 신고기한", "상속세 배우자공제",
    ],
}


# 주제 풀 확장 - gov(A)/life(B)는 시드가 16개뿐이라 같은 주제가 금방 돌아왔다.
# 검증된 팩트 시트가 없는 키워드라서 topic_planner가 "수치 지어내지 말 것" 주의 문구를 붙인다.
EXPANDED_SEED_KEYWORDS = {
    "A": [
        "국가장학금", "청년내일저축계좌", "첫만남이용권", "장애인연금", "문화누리카드",
        "국민행복카드 임신 출산 바우처", "노인일자리 사업", "청년 버팀목 전세대출", "소상공인 정책자금",
        "산후조리비 지원", "난방비 지원", "다자녀 가구 혜택", "자립준비청년 지원", "한부모 아이돌봄서비스",
        # --- 주택·분양·주거금융 ---
        "공공분양 신청자격", "신혼부부 특별공급", "생애최초 특별공급", "다자녀 특별공급", "노부모 부양 특별공급",
        "청약통장 가입 조건", "주택청약종합저축 납입", "청약 가점 계산", "신혼희망타운", "공공임대주택 종류",
        "행복주택 신청자격", "국민임대 소득기준", "통합공공임대", "전세임대주택", "매입임대주택",
        "신생아 특례대출", "디딤돌대출 조건", "신혼부부 전세자금대출", "전세보증금 반환보증", "전세사기 피해자 지원",
        "LH 청약플러스 사용법", "분양가상한제 아파트", "청약 당첨 후 절차", "무순위 청약", "주거안정 월세대출",
        # --- 일·육아·건강·교육 ---
        "육아휴직급여", "출산휴가 급여", "고용보험 청년 지원", "학자금대출 조건", "재난적의료비 지원",
        "본인부담상한제", "산정특례 제도", "의료급여 수급자", "장기요양등급 신청", "장애인 활동지원",
        "노인 맞춤돌봄서비스", "치매 치료비 지원", "청년 일자리도약장려금", "소상공인 재기지원", "긴급복지 의료지원",
    ],
    "B": [
        "통신사 멤버십 활용", "알뜰폰 번호이동 방법", "휴대폰 분실 보험", "인터넷 설치 사은품",
        "정수기 렌탈 비교", "비데 렌탈", "공기청정기 필터 교체", "TV 인터넷 결합상품",
        "통신비 카드 할인", "스마트워치 요금제", "청소년 요금제", "시니어 요금제", "데이터 쉐어링",
        "해외 eSIM 비교", "중고폰 개통 방법", "인터넷 속도 느림 해결", "와이파이 공유기 고르는 법",
        # --- 교통·에너지·공과금 ---
        "K-패스 환급", "기후동행카드", "알뜰교통카드", "대중교통 정기권 비교",
        "전기요금 절약", "에너지캐시백", "도시가스 요금 할인", "전기요금 누진세 구간", "공과금 카드 할인",
        "난방비 절약 방법", "에너지효율 1등급 가전", "수도요금 감면",
        # --- 보험·금융 ---
        "실손보험 청구 방법", "실손보험 리모델링", "자동차보험 다이렉트 비교", "운전자보험 필요성", "신용점수 올리는 법",
        "금리인하요구권", "중도상환수수료", "파킹통장 비교", "체크카드 vs 신용카드", "카드 연회비 아끼기",
        "주거래은행 혜택", "대출 갈아타기",
        # --- 생활 소비 ---
        "구독서비스 정리", "OTT 요금 절약", "배달비 줄이는 법", "장보기 절약 방법", "주유비 절약 카드",
        "중고거래 안전하게", "폐가전 무상수거", "가전 구독 vs 구매", "이사비용 절약", "자취 생활비 줄이기",
        "가계부 쓰는 법", "고정비 줄이기", "병원비 절약 방법", "해외직구 관세", "항공권 싸게 사는 법",
    ],
    "C": [
        # --- 개인사업자·자영업·가맹점 ---
        "사업자등록 방법", "간이과세 vs 일반과세", "개인사업자 종합소득세 신고", "복식부기 vs 간편장부", "사업 경비 인정 항목",
        "전자세금계산서 발행", "현금영수증 의무발행", "사업용 계좌 신고", "배달앱 매출 세금", "프랜차이즈 가맹점 세금",
        "가맹점 카드수수료", "노란우산공제", "소상공인 부가세 감면", "사업자 4대보험", "원천세 신고",
        "지급명세서 제출", "폐업 시 세금", "부가세 환급 사업자",
        # --- 법인·절세 ---
        "법인 설립 절차", "법인 vs 개인사업자", "법인세 절세 방법", "업무용 승용차 비용처리", "접대비 한도",
        "가지급금 인정이자", "대표이사 급여 설정", "임원 퇴직금 규정", "법인 배당소득세", "법인 결손금 이월공제",
        "법인 폐업 청산", "가업승계 증여세", "법인세 중간예납",
        # --- 세액공제·감면 ---
        "고용증대 세액공제", "통합고용세액공제", "창업중소기업 세액감면", "중소기업 특별세액감면",
        "연구인력개발비 세액공제", "통합투자세액공제",
        # --- 부동산·금융 세금 ---
        "주택임대사업자 세금", "다주택자 양도세", "상가 임대소득 세금", "부동산 증여 취득세", "취득세 계산",
        "임대소득 분리과세", "양도세 장기보유특별공제", "종합소득세 건강보험료", "금융소득종합과세",
    ],
}
UNVERIFIED_SEEDS = {kw for kws in EXPANDED_SEED_KEYWORDS.values() for kw in kws}
for _site, _extra in EXPANDED_SEED_KEYWORDS.items():
    SITE_SEED_KEYWORDS[_site] = SITE_SEED_KEYWORDS[_site] + [k for k in _extra if k not in SITE_SEED_KEYWORDS[_site]]


def fetch_public_data_subsidies(limit: int = 20) -> List[Dict[str, str]]:
    """공공데이터포털 보조금24 API에서 지원사업 목록을 가져온다."""
    if not settings.public_data_api_key:
        logger.info("PUBLIC_DATA_API_KEY 미설정 - 공공데이터포털 조회를 건너뜁니다.")
        return []

    resp = safe_get(
        PUBLIC_DATA_SUBSIDY_API,
        params={
            "page": 1,
            "perPage": limit,
            "returnType": "JSON",
            "serviceKey": settings.public_data_api_key,
        },
        timeout=10,
    )
    if resp is None or resp.status_code != 200:
        logger.warning("공공데이터포털 응답 실패 - 건너뜁니다.")
        return []

    try:
        data = resp.json()
        items = data.get("data", [])
        return [
            {
                "title": item.get("servNm", ""),
                "summary": item.get("servDgst", ""),
                "url": item.get("servDtlLink", ""),
            }
            for item in items
        ]
    except (ValueError, AttributeError) as exc:
        logger.warning("공공데이터포털 응답 파싱 실패: %s", exc)
        return []


def fetch_policy_briefing_rss(limit: int = 20) -> List[Dict[str, str]]:
    """대한민국 정책브리핑 RSS 피드를 파싱한다."""
    try:
        feed = feedparser.parse(POLICY_BRIEFING_RSS)
        entries = feed.entries[:limit] if getattr(feed, "entries", None) else []
        return [
            {
                "title": e.get("title", ""),
                "summary": e.get("summary", ""),
                "url": e.get("link", ""),
            }
            for e in entries
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("정책브리핑 RSS 파싱 실패: %s", exc)
        return []


def fetch_google_trends_daily_kr(limit: int = 20) -> List[Dict[str, str]]:
    """구글 트렌드 한국 일별 급상승 검색어 RSS를 파싱한다."""
    try:
        feed = feedparser.parse(GOOGLE_TRENDS_DAILY_RSS_KR)
        entries = feed.entries[:limit] if getattr(feed, "entries", None) else []
        return [{"title": e.get("title", ""), "url": e.get("link", "")} for e in entries]
    except Exception as exc:  # noqa: BLE001
        logger.warning("구글 트렌드 RSS 파싱 실패: %s", exc)
        return []


def _filter_keywords_for_site(
    site: str, subsidies: List[Dict[str, str]], briefings: List[Dict[str, str]], trends: List[Dict[str, str]]
) -> List[str]:
    seeds = SITE_SEED_KEYWORDS.get(site, [])
    keywords: List[str] = list(seeds)

    combined_titles = (
        [s["title"] for s in subsidies]
        + [b["title"] for b in briefings]
        + [t["title"] for t in trends]
    )
    for title in combined_titles:
        if not title:
            continue
        for seed in seeds:
            # 시드 키워드의 핵심 토큰이 제목에 등장하면 관련 트렌드로 채택
            if any(tok in title for tok in seed.split()):
                keywords.append(title.strip())
                break

    # 중복 제거, 순서 유지
    seen = set()
    unique_keywords = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            unique_keywords.append(k)
    return unique_keywords[:15]


def fetch_today_hot_topics(site: str) -> Dict[str, object]:
    """오늘의 핫토픽 브리핑을 만든다. 항상 dict를 반환하며 예외를 던지지 않는다."""
    site = site.upper().replace("SITE_", "")
    if site not in SITE_KEYS:
        site = "A"

    subsidies = fetch_public_data_subsidies()
    briefings = fetch_policy_briefing_rss()
    trends = fetch_google_trends_daily_kr()

    keywords = _filter_keywords_for_site(site, subsidies, briefings, trends)

    if not keywords:
        logger.info("[Site %s] 모든 트렌드 소스 실패 - 오프라인 폴백 키워드 사용", site)
        keywords = SITE_SEED_KEYWORDS.get(site, ["정부지원금"])

    label = SITE_LABELS.get(site, site)
    briefing_lines = [f"[{label}] 오늘의 핫토픽 키워드: {', '.join(keywords[:8])}"]
    for b in briefings[:3]:
        if b.get("title"):
            briefing_lines.append(f"- 정책브리핑: {b['title']}")
    for s in subsidies[:3]:
        if s.get("title"):
            briefing_lines.append(f"- 지원사업: {s['title']}")

    return {
        "site": site,
        "keywords": keywords,
        "briefing_text": "\n".join(briefing_lines),
        "sources": {
            "subsidies": subsidies,
            "briefings": briefings,
            "trends": trends,
        },
    }
