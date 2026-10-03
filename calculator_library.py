"""공식 수치로 검증된 계산기 라이브러리.

Claude가 즉석에서 쓰는 계산기는 수식·기준값이 부정확할 수 있어서(실제로 생계급여
위젯이 "대략치"로 단순화돼 있었음), 자주 나오는 주제는 출처가 확인된 수치를 코드에
고정해 둔다. 글 주제에 맞는 키가 있으면 generator가 calculator_type으로 고르고,
본문에는 CALCULATOR_SLOT만 넣게 한 뒤 여기서 위젯을 채워 넣는다.

수치를 바꿀 때는 아래 SOURCES의 기준 연도/출처를 같이 갱신할 것.
"""
from __future__ import annotations

from typing import Dict, Optional

from constants import AFFILIATE_SLOT_MID, CALCULATOR_SLOT

CALCULATOR_CHOICES: Dict[str, str] = {
    "income_tax": "종합소득세 산출세액 계산 (과세표준 입력 → 세율 구간별 세액)",
    "pension_credit": "연금저축·IRP 세액공제 환급액 계산",
    "rent_credit": "월세 세액공제 환급액 계산",
    "early_pension": "국민연금 조기수령(조기노령연금) 감액 계산",
    "basic_pension": "기초연금 선정기준액 이내 여부 확인 (소득인정액 입력)",
    "telecom_saving": "통신비 절감액·위약금 손익분기 계산",
    "us_stock_tax": "해외주식 양도소득세 계산 (연간 손익통산 후 250만원 공제, 22%)",
    "dividend_tax": "해외주식 배당 원천징수 후 수령액 및 금융소득종합과세(2천만원) 확인",
}

_SOURCES = {
    "income_tax": "2026년 귀속 소득세법 기본세율(6~45%) 기준. 세액공제·감면 반영 전 금액입니다.",
    "pension_credit": "2026년 기준 소득세법상 연금계좌 세액공제(연금저축 600만원, IRP 포함 합산 900만원 한도, 공제율 16.5%/13.2%). 고소득자는 한도가 달라질 수 있습니다.",
    "rent_credit": "2026년 기준 소득세법상 월세 세액공제(총급여 8,000만원 이하, 연 한도 1,000만원, 공제율 17%/15%). 무주택 세대주·주택 규모 등 별도 요건이 있습니다.",
    "early_pension": "국민연금공단 안내 기준(조기노령연금은 1년 앞당길 때마다 6%, 최대 30% 감액, 가입기간 10년 이상). 소득활동 여부에 따라 지급이 제한될 수 있습니다.",
    "basic_pension": "보건복지부 2026년 기초연금 선정기준액(단독가구 월 247만원, 부부가구 월 395만 2천원). 소득인정액은 소득평가액과 재산의 소득환산액을 합산한 값입니다.",
    "telecom_saving": "입력한 금액만으로 계산한 단순 산술 결과이며, 실제 요금·할인·위약금 조건은 통신사 안내를 확인하세요.",
    "us_stock_tax": "2026년 기준 해외주식 양도소득세(연간 양도차익·차손 통산 후 기본공제 250만원, 세율 22%(지방소득세 포함), 다음 해 5월 신고). 환율 적용·필요경비 범위 등에 따라 실제 세액이 달라질 수 있습니다.",
    "dividend_tax": "2026년 기준 미국 주식 배당은 현지에서 15% 원천징수되며, 연간 금융소득(이자+배당)이 2,000만원을 넘으면 금융소득종합과세 대상입니다. 실제 과세는 소득 구성에 따라 달라집니다.",
}

_COMMON_JS = (
    "var g=function(k){return document.getElementById(U+'_'+k)};"
    "var v=function(k){return parseFloat(g(k).value)||0};"
    "var f=function(n){return Math.round(n).toLocaleString('ko-KR')};"
    "var out=function(h,ok){var r=g('res');r.innerHTML=h;r.style.color=ok?'#1e3a8a':'#c92a2a';r.style.display='block'};"
)

_SPECS = {
    "income_tax": {
        "title": "🧮 종합소득세 산출세액 계산기",
        "fields": [("num", "base", "과세표준 (원)", "예: 60000000", "")],
        "js": (
            "var b=v('base');"
            "var T=[[14000000,0.06,0],[50000000,0.15,1260000],[88000000,0.24,5760000],"
            "[150000000,0.35,15440000],[300000000,0.38,19940000],[500000000,0.40,25940000],"
            "[1000000000,0.42,35940000],[Infinity,0.45,65940000]];"
            "var t=T[0];for(var i=0;i<T.length;i++){if(b<=T[i][0]){t=T[i];break}}"
            "var tax=Math.max(0,Math.floor(b*t[1]-t[2]));"
            "var loc=Math.floor(tax*0.1);"
            "out('적용 세율 '+Math.round(t[1]*100)+'% 구간 · 산출세액 약 <b>'+f(tax)+'원</b> (지방소득세 10% 포함 시 약 '+f(tax+loc)+'원)',true);"
        ),
    },
    "pension_credit": {
        "title": "🧮 연금저축·IRP 세액공제 환급액 계산기",
        "fields": [
            ("num", "ps", "연금저축 연 납입액 (원)", "예: 6000000", ""),
            ("num", "irp", "IRP 연 납입액 (원)", "예: 3000000", ""),
            ("sel", "rate", "총급여 구간", "", [("0.165", "5,500만원 이하 (공제율 16.5%)"), ("0.132", "5,500만원 초과 (공제율 13.2%)")]),
        ],
        "js": (
            "var ps=Math.min(v('ps'),6000000);"
            "var tot=Math.min(ps+v('irp'),9000000);"
            "var rate=parseFloat(g('rate').value);"
            "out('공제 대상 금액 '+f(tot)+'원 · 예상 세액공제 <b>'+f(tot*rate)+'원</b>',true);"
        ),
    },
    "rent_credit": {
        "title": "🧮 월세 세액공제 환급액 계산기",
        "fields": [
            ("num", "rent", "연간 월세 납부액 (원)", "예: 7200000", ""),
            ("sel", "rate", "총급여 구간", "", [("0.17", "5,500만원 이하 (공제율 17%)"), ("0.15", "5,500만원 초과 ~ 8,000만원 이하 (공제율 15%)"), ("0", "8,000만원 초과 (공제 대상 아님)")]),
        ],
        "js": (
            "var rate=parseFloat(g('rate').value);"
            "if(rate===0){out('총급여 8,000만원을 넘으면 월세 세액공제 대상이 아닙니다.',false);return}"
            "var el=Math.min(v('rent'),10000000);"
            "out('공제 대상 금액 '+f(el)+'원 · 예상 세액공제 <b>'+f(el*rate)+'원</b>',true);"
        ),
    },
    "early_pension": {
        "title": "🧮 국민연금 조기수령 감액 계산기",
        "fields": [
            ("num", "base", "정상 수급 시 예상 월 연금액 (원)", "예: 1000000", ""),
            ("sel", "yrs", "앞당기는 기간", "", [("1", "1년 (6% 감액)"), ("2", "2년 (12% 감액)"), ("3", "3년 (18% 감액)"), ("4", "4년 (24% 감액)"), ("5", "5년 (30% 감액)")]),
        ],
        "js": (
            "var y=parseInt(g('yrs').value);"
            "var base=v('base');var m=base*(1-0.06*y);"
            "out('감액률 '+(6*y)+'% · 조기수령 시 월 약 <b>'+f(m)+'원</b> (월 '+f(base-m)+'원, 연 '+f((base-m)*12)+'원 감액, 평생 유지)',true);"
        ),
    },
    "basic_pension": {
        "title": "🧮 기초연금 선정기준액 확인 계산기",
        "fields": [
            ("num", "inc", "월 소득인정액 (원)", "예: 2000000", ""),
            ("sel", "lim", "가구 유형", "", [("2470000", "단독가구 (기준 월 247만원)"), ("3952000", "부부가구 (기준 월 395만 2천원)")]),
        ],
        "js": (
            "var inc=v('inc');var lim=parseFloat(g('lim').value);"
            "if(inc<=lim){out('✅ 소득인정액 '+f(inc)+'원은 선정기준액 '+f(lim)+'원 이하입니다. 다른 요건(만 65세 이상 등)과 함께 신청을 검토해보세요.',true)}"
            "else{out('⚠️ 소득인정액 '+f(inc)+'원이 선정기준액 '+f(lim)+'원을 넘습니다. 소득인정액 산정이 정확한지 복지로 모의계산으로 확인해보세요.',false)}"
        ),
    },
    "us_stock_tax": {
        "title": "🧮 해외주식 양도소득세 계산기 (250만원 공제)",
        "fields": [
            ("num", "gain", "연간 양도차익 합계 - 이익 본 거래 (원)", "예: 15000000", ""),
            ("num", "loss", "연간 양도차손 합계 - 손실 본 거래 (원, 없으면 0)", "예: 3000000", "0"),
            ("num", "exp", "필요경비 - 매매수수료 등 (원, 없으면 0)", "예: 200000", "0"),
        ],
        "js": (
            "var net=v('gain')-v('loss')-v('exp');"
            "if(net<=2500000){out('손익통산 후 순차익 '+f(net)+'원은 기본공제 250만원 이하라 <b>납부할 양도세가 없습니다</b>.',true);return}"
            "var base=net-2500000;"
            "out('손익통산 순차익 '+f(net)+'원 − 기본공제 250만원 = 과세표준 '+f(base)+'원 · 예상 양도세 <b>'+f(base*0.22)+'원</b> (22%, 지방소득세 포함)',true);"
        ),
    },
    "dividend_tax": {
        "title": "🧮 미국주식 배당 세후 수령액 계산기",
        "fields": [
            ("num", "div", "연간 세전 배당금 (원)", "예: 5000000", ""),
            ("num", "oth", "그 외 금융소득 - 예금이자·국내배당 등 (원, 없으면 0)", "예: 3000000", "0"),
        ],
        "js": (
            "var d=v('div');var t=d*0.15;"
            "var h='미국 원천징수 15% '+f(t)+'원 · 세후 수령액 <b>'+f(d-t)+'원</b>';"
            "var s=d+v('oth');"
            "if(s>20000000){h+='<br>⚠️ 금융소득 합계 '+f(s)+'원이 2,000만원을 넘어 금융소득종합과세 대상입니다. 초과분은 종합소득세율이 적용되며 외국납부세액공제를 받을 수 있습니다.'}"
            "else{h+='<br>✅ 금융소득 합계 '+f(s)+'원으로 2,000만원 이하라 종합과세 대상이 아닙니다.'}"
            "out(h,true);"
        ),
    },
    "telecom_saving": {
        "title": "🧮 통신비 절감액 계산기",
        "fields": [
            ("num", "cur", "현재 월 통신비 (원)", "예: 80000", ""),
            ("num", "new", "변경 후 월 요금 (원)", "예: 35000", ""),
            ("num", "pen", "해지 시 내야 할 위약금 (원, 없으면 0)", "예: 0", "0"),
        ],
        "js": (
            "var s=v('cur')-v('new');var p=v('pen');"
            "if(s<=0){out('변경 후 요금이 현재보다 같거나 비싸서 절감 효과가 없습니다.',false);return}"
            "var h='월 <b>'+f(s)+'원</b>, 연 <b>'+f(s*12)+'원</b> 절감';"
            "if(p>0){h+=' · 위약금 '+f(p)+'원은 약 '+Math.ceil(p/s)+'개월이면 회수'}"
            "out(h,true);"
        ),
    },
}

_FIELD_STYLE = "width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:8px;font-size:16px;box-sizing:border-box;"


def _render(key: str) -> str:
    spec = _SPECS[key]
    uid = f"wc_{key}"
    parts = [
        '<div class="benefit-calc" style="background:#f7f9fc;border:1px solid #dce4f0;'
        'border-radius:14px;padding:22px;margin:24px 0;">',
        f'<p style="font-weight:bold;font-size:17px;margin:0 0 14px;">{spec["title"]}</p>',
    ]
    for field in spec["fields"]:
        kind, fid, label = field[0], field[1], field[2]
        parts.append(
            f'<div style="margin-bottom:12px;"><label for="{uid}_{fid}" '
            f'style="display:block;font-size:13px;font-weight:bold;color:#475569;margin-bottom:5px;">{label}</label>'
        )
        if kind == "num":
            parts.append(
                f'<input type="number" id="{uid}_{fid}" placeholder="{field[3]}" value="{field[4]}" '
                f'inputmode="numeric" style="{_FIELD_STYLE}"></div>'
            )
        else:
            options = "".join(f'<option value="{val}">{text}</option>' for val, text in field[4])
            parts.append(f'<select id="{uid}_{fid}" style="{_FIELD_STYLE}">{options}</select></div>')
    parts.append(
        f'<button type="button" id="{uid}_btn" style="width:100%;background:#2563eb;color:#fff;'
        'padding:12px;border:none;border-radius:8px;font-size:16px;font-weight:bold;cursor:pointer;">계산하기</button>'
    )
    parts.append(
        f'<p id="{uid}_res" style="display:none;margin:14px 0 0;padding:14px;background:#eff6ff;'
        'border:1px solid #bfdbfe;border-radius:8px;font-size:15px;font-weight:bold;line-height:1.6;"></p></div>'
    )
    script = (
        f"(function(){{var U='{uid}';{_COMMON_JS}"
        f"g('btn').addEventListener('click',function(){{{spec['js']}}});}})();"
    )
    parts.append(f"<script>{script}</script>")
    parts.append(
        '<p class="calc-disclaimer" style="font-size:12px;color:#888;margin:8px 0 20px;line-height:1.6;">'
        f"※ {_SOURCES[key]} 참고용 모의 계산이며 실제 결과와 다를 수 있으니 공식 기관에서 확인하세요.</p>"
    )
    return "".join(parts)


def inject_calculator(html: str, calc_type: Optional[str]) -> str:
    """CALCULATOR_SLOT을 검증된 계산기로 치환한다. 해당 키가 없으면 슬롯만 제거한다."""
    if not html:
        return html
    if calc_type not in _SPECS:
        return html.replace(CALCULATOR_SLOT, "")

    widget = _render(calc_type)
    if CALCULATOR_SLOT in html:
        return html.replace(CALCULATOR_SLOT, widget, 1)
    if "benefit-calc" not in html and AFFILIATE_SLOT_MID in html:
        return html.replace(AFFILIATE_SLOT_MID, widget + AFFILIATE_SLOT_MID, 1)
    return html
