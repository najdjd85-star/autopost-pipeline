"""허브 계산기 페이지(dailyfixpoint.com/calc/...). 공식이 법·수학으로 정해진 계산만 다룬다.

AI가 쓴 글이 아니라 직접 쓰는 도구라 검색 유입과 사이트 가치의 근거가 된다. 숫자 예시는 아래 공식으로 미리 계산해 적었다.
기준이 해마다 바뀌는 값(최저임금 등)은 BASIS에 모아 두고, 바뀌면 여기만 고친다.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

BASIS = {"min_wage": 10320, "min_wage_year": 2026, "tax": 15.4, "updated": "2026-11-07"}

CSS = """<style>
.calc{background:#fff;border:1px solid #e4e3de;border-radius:16px;padding:18px;margin:18px 0}
.calc label{display:block;font-size:14px;font-weight:600;margin:12px 0 4px}
.calc input,.calc select{width:100%;box-sizing:border-box;font-size:17px;padding:11px 12px;border:1px solid #cfcec7;border-radius:10px;background:#fff;color:#1d1d1b}
.calc .row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.calc .seg{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}.calc .seg label{margin:0;font-weight:500;display:flex;align-items:center;gap:6px;border:1px solid #cfcec7;border-radius:999px;padding:6px 12px}
.calc .seg input{width:auto}
.calc button{margin-top:16px;width:100%;font-size:16px;font-weight:700;padding:13px;border:0;border-radius:12px;background:#1d1d1b;color:#fff;cursor:pointer}
.res{display:none;margin-top:16px;padding:14px;border-radius:12px;background:#f6f6f4}
.res.on{display:block}.res dl{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin:0}.res dt{color:#5f5e5a}.res dd{margin:0;text-align:right;font-weight:700}
.res .big{font-size:24px;color:#185fa5}
.res table{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}.res th,.res td{border-bottom:1px solid #e4e3de;padding:6px 4px;text-align:right}.res th:first-child,.res td:first-child{text-align:left}
.note2{font-size:13px;color:#8a8985}
.clist{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;padding:0;list-style:none}
.clist li{background:#fff;border:1px solid #e4e3de;border-radius:14px;padding:14px}.clist b{display:block}.clist span{font-size:14px;color:#5f5e5a}
@media (prefers-color-scheme:dark){.calc,.clist li{background:#252523;border-color:#383835}.calc input,.calc select{background:#1b1b19;color:#f1efe8;border-color:#4a4a46}.res{background:#1b1b19}.res .big{color:#85b7eb}.calc button{background:#f1efe8;color:#1b1b19}}
</style>"""

JS_COMMON = """<script>
function num(id){var v=document.getElementById(id).value.replace(/[^0-9.]/g,'');return v?parseFloat(v):0;}
function won(n){return Math.round(n).toLocaleString('ko-KR')+'원';}
function pick(name){var e=document.querySelector('input[name="'+name+'"]:checked');return e?e.value:'';}
document.querySelectorAll('input[data-money]').forEach(function(e){e.addEventListener('input',function(){var d=e.value.replace(/[^0-9]/g,'');e.value=d?parseInt(d,10).toLocaleString('ko-KR'):'';});});
function show(id,html){var r=document.getElementById(id);r.innerHTML=html;r.classList.add('on');}
</script>"""


def _faq(items: List[Tuple[str, str]]) -> str:
    return "<h2>자주 묻는 질문</h2>" + "".join(f"<h3>{q}</h3><p>{a}</p>" for q, a in items)


def _tax_seg(name: str) -> str:
    return (f'<label>이자 세금</label><div class="seg"><label><input type="radio" name="{name}" value="15.4" checked>일반과세 15.4%</label>'
            f'<label><input type="radio" name="{name}" value="0">비과세</label></div>')


CALCS: Dict[str, Dict[str, str]] = {}

CALCS["loan-interest"] = {
    "title": "대출이자 계산기",
    "desc": "대출금, 금리, 기간을 넣으면 원리금균등·원금균등·만기일시 상환 방식별 월 상환액과 총이자를 계산합니다.",
    "body": f"""<p>대출을 받기 전에 매달 얼마를 갚고, 다 갚을 때까지 이자가 모두 얼마인지 계산해 보세요. 상환 방식에 따라 같은 금리에서도 총이자가 크게 달라집니다.</p>
<div class="calc"><label for="p">대출금(원)</label><input id="p" inputmode="numeric" data-money value="100,000,000">
<div class="row"><div><label for="r">연 금리(%)</label><input id="r" inputmode="decimal" value="4"></div><div><label for="n">기간(개월)</label><input id="n" inputmode="numeric" value="360"></div></div>
<label>상환 방식</label><div class="seg"><label><input type="radio" name="m" value="a" checked>원리금균등</label><label><input type="radio" name="m" value="b">원금균등</label><label><input type="radio" name="m" value="c">만기일시</label></div>
<button type="button" onclick="calc()">계산하기</button><div class="res" id="out" aria-live="polite"></div></div>
<h2>상환 방식별 차이</h2>
<p><b>원리금균등</b>은 매달 같은 금액을 갚습니다. 처음에는 이자 비중이 크고 갈수록 원금 비중이 커집니다. 가계 계획을 세우기 쉬워 주택담보대출에서 많이 씁니다.</p>
<p><b>원금균등</b>은 원금을 매달 같은 금액씩 갚고, 남은 원금에 대한 이자를 더해 냅니다. 첫 달 부담이 가장 크고 점점 줄어들며, 세 방식 중 총이자가 가장 적습니다.</p>
<p><b>만기일시</b>는 매달 이자만 내다가 만기에 원금을 한 번에 갚습니다. 월 부담은 가장 작지만 원금이 줄지 않아 총이자가 가장 많습니다. 신용대출이나 전세자금대출에서 많이 씁니다.</p>
<h2>계산 방법</h2>
<p>월 금리는 연 금리를 12로 나눈 값입니다. 원리금균등의 월 상환액은 대출금 × 월 금리 × (1+월 금리)<sup>기간</sup> ÷ ((1+월 금리)<sup>기간</sup> − 1)입니다. 원금균등의 총이자는 대출금 × 월 금리 × (기간+1) ÷ 2이고, 만기일시의 총이자는 대출금 × 월 금리 × 기간입니다.</p>
<h2>예시: 1억 원, 연 4%, 30년(360개월)</h2>
<ul><li>원리금균등: 매달 약 477,415원, 총이자 약 71,869,506원</li><li>원금균등: 첫 달 약 611,111원(이후 줄어듦), 총이자 약 60,166,667원</li><li>만기일시: 매달 이자 약 333,333원, 총이자 120,000,000원</li></ul>
<p>같은 조건에서 원금균등은 원리금균등보다 총이자가 약 1,170만 원 적지만, 첫 달 부담은 약 13만 원 더 큽니다.</p>
""" + _faq([
        ("어떤 방식이 가장 유리한가요?", "총이자만 보면 원금균등이 가장 적습니다. 다만 초반 상환액이 커서, 매달 같은 금액이 필요하면 원리금균등이 현실적입니다. 만기일시는 곧 갚을 계획이 있는 단기 대출에 맞습니다."),
        ("변동금리면 계산이 어떻게 되나요?", "금리가 바뀌는 시점부터 남은 원금과 남은 기간으로 다시 계산합니다. 바뀐 금리를 넣고 남은 원금과 남은 개월 수로 다시 계산해 보세요."),
        ("중도상환하면 이자가 줄어드나요?", "원금을 먼저 갚으면 그만큼 이후 이자가 줄어듭니다. 대신 대출 후 일정 기간(보통 3년) 안에는 중도상환수수료가 붙을 수 있으니 약정서를 확인하세요."),
    ]),
    "script": """<script>
function calc(){var P=num('p'),y=num('r')/100,n=Math.round(num('n')),m=pick('m'),r=y/12;if(!P||!n){return;}
var rows=[],bal=P,tot=0,first=0;
for(var k=1;k<=n;k++){var it=bal*r,pr;
 if(m==='a'){var M=r?P*r*Math.pow(1+r,n)/(Math.pow(1+r,n)-1):P/n;pr=M-it;}
 else if(m==='b'){pr=P/n;} else {pr=(k===n)?P:0;}
 var pay=pr+it;if(k===1){first=pay;}tot+=it;bal-=pr;if(k<=12||k===n){rows.push([k,pay,pr,it,Math.max(bal,0)]);}}
var t='<table><tr><th>회차</th><th>상환액</th><th>원금</th><th>이자</th><th>남은 원금</th></tr>'+rows.map(function(x){return '<tr><td>'+x[0]+'</td><td>'+won(x[1])+'</td><td>'+won(x[2])+'</td><td>'+won(x[3])+'</td><td>'+won(x[4])+'</td></tr>';}).join('')+'</table>';
show('out','<dl><dt>첫 달 상환액</dt><dd class="big">'+won(first)+'</dd><dt>총이자</dt><dd>'+won(tot)+'</dd><dt>총상환액</dt><dd>'+won(P+tot)+'</dd></dl>'+t+'<p class="note2">1~12회차와 마지막 회차를 보여 줍니다.</p>');}
</script>""",
}

CALCS["savings-interest"] = {
    "title": "적금 이자 계산기",
    "desc": "월 납입액, 기간, 금리를 넣으면 단리·월복리 적금의 세전·세후 이자와 만기 수령액을 계산합니다.",
    "body": f"""<p>적금 금리가 연 4%여도 실제로 받는 이자는 생각보다 적습니다. 매달 넣는 돈마다 예치 기간이 다르기 때문입니다. 만기에 실제로 받을 금액을 계산해 보세요.</p>
<div class="calc"><label for="m">월 납입액(원)</label><input id="m" inputmode="numeric" data-money value="500,000">
<div class="row"><div><label for="n">기간(개월)</label><input id="n" inputmode="numeric" value="12"></div><div><label for="r">연 금리(%)</label><input id="r" inputmode="decimal" value="4"></div></div>
<label>이자 방식</label><div class="seg"><label><input type="radio" name="k" value="s" checked>단리</label><label><input type="radio" name="k" value="c">월복리</label></div>
{_tax_seg("t")}<button type="button" onclick="calc()">계산하기</button><div class="res" id="out" aria-live="polite"></div></div>
<h2>계산 방법</h2>
<p><b>단리 적금</b>: 첫 달에 넣은 돈은 12개월, 마지막 달에 넣은 돈은 1개월만 이자가 붙습니다. 그래서 이자 = 월 납입액 × 연 금리 ÷ 12 × 기간 × (기간+1) ÷ 2입니다.</p>
<p><b>월복리 적금</b>: 매달 붙은 이자에도 다시 이자가 붙습니다. 회차마다 월 납입액 × ((1+연 금리÷12)<sup>남은 개월</sup> − 1)을 더합니다.</p>
<p>이자에는 이자소득세 14%와 지방소득세 1.4%를 합친 15.4%가 붙습니다. 비과세종합저축처럼 세금이 없는 상품이면 비과세를 고르세요.</p>
<h2>예시: 월 50만 원, 12개월, 연 4%</h2>
<ul><li>단리: 세전 이자 130,000원, 세금 20,020원, 세후 이자 109,980원, 만기 수령액 6,109,980원</li><li>월복리: 세전 이자 약 131,602원</li></ul>
<p>연 4% 적금의 실제 이자는 같은 돈을 처음부터 예금에 넣었을 때의 절반 정도입니다. 금리만 보고 예금과 비교하지 마세요.</p>
""" + _faq([
        ("적금과 예금 중 어느 쪽이 이자가 많나요?", "목돈이 이미 있다면 같은 금리에서 예금이 이자가 많습니다. 적금은 매달 모으는 습관과 목돈 만들기에 맞습니다."),
        ("중도해지하면 어떻게 되나요?", "약정 금리보다 낮은 중도해지 금리가 적용되는 경우가 대부분입니다. 상품 설명서의 중도해지 이율을 확인하세요."),
        ("특판 적금 금리가 높은데 무조건 좋은가요?", "월 납입 한도가 작거나 우대 조건(카드 실적, 자동이체 등)을 다 채워야 최고 금리가 되는 경우가 많습니다. 기본 금리로도 계산해 보세요."),
    ]),
    "script": """<script>
function calc(){var M=num('m'),n=Math.round(num('n')),y=num('r')/100,tx=parseFloat(pick('t'))/100;if(!M||!n){return;}
var i=0;if(pick('k')==='s'){i=M*y/12*n*(n+1)/2;}else{for(var k=1;k<=n;k++){i+=M*(Math.pow(1+y/12,k)-1);}}
var tax=Math.floor(i*tx),net=i-tax;
show('out','<dl><dt>원금 합계</dt><dd>'+won(M*n)+'</dd><dt>세전 이자</dt><dd>'+won(i)+'</dd><dt>세금</dt><dd>'+won(tax)+'</dd><dt>세후 이자</dt><dd>'+won(net)+'</dd><dt>만기 수령액</dt><dd class="big">'+won(M*n+net)+'</dd></dl>');}
</script>""",
}

CALCS["deposit-interest"] = {
    "title": "예금 이자 계산기",
    "desc": "예치 금액, 기간, 금리를 넣으면 정기예금의 단리·월복리 세전·세후 이자와 만기 수령액을 계산합니다.",
    "body": f"""<p>목돈을 정기예금에 넣으면 만기에 얼마를 받는지, 세금을 떼고 나면 이자가 얼마인지 계산해 보세요.</p>
<div class="calc"><label for="p">예치 금액(원)</label><input id="p" inputmode="numeric" data-money value="10,000,000">
<div class="row"><div><label for="n">기간(개월)</label><input id="n" inputmode="numeric" value="12"></div><div><label for="r">연 금리(%)</label><input id="r" inputmode="decimal" value="3.5"></div></div>
<label>이자 방식</label><div class="seg"><label><input type="radio" name="k" value="s" checked>단리</label><label><input type="radio" name="k" value="c">월복리</label></div>
{_tax_seg("t")}<button type="button" onclick="calc()">계산하기</button><div class="res" id="out" aria-live="polite"></div></div>
<h2>계산 방법</h2>
<p><b>단리</b>: 이자 = 예치 금액 × 연 금리 × 기간(개월) ÷ 12. 대부분의 정기예금이 단리입니다.</p>
<p><b>월복리</b>: 만기 금액 = 예치 금액 × (1 + 연 금리 ÷ 12)<sup>기간</sup>. 이자에 다시 이자가 붙어 기간이 길수록 단리와 차이가 커집니다.</p>
<p>이자에는 15.4%(이자소득세 14% + 지방소득세 1.4%)의 세금이 붙습니다.</p>
<h2>예시: 1,000만 원, 12개월, 연 3.5%</h2>
<ul><li>단리: 세전 이자 350,000원, 세금 53,900원, 세후 이자 296,100원</li><li>월복리: 세전 이자 약 355,670원</li></ul>
""" + _faq([
        ("예금자보호는 얼마까지인가요?", "예금자보호 한도는 금융회사별로 원금과 이자를 합쳐 정해진 금액까지입니다. 한도는 법 개정으로 바뀔 수 있으니 예금보험공사에서 최신 기준을 확인하세요."),
        ("이자를 매달 받는 게 유리한가요?", "매달 받는 월이자 지급식은 만기 일시 지급보다 이자가 조금 적거나 같습니다. 생활비로 쓸 게 아니라면 만기 일시 지급이 보통 유리합니다."),
        ("파킹통장과 비교하면 어떤가요?", "파킹통장은 언제든 뺄 수 있지만 금리가 바뀔 수 있습니다. 쓸 일이 없는 돈은 예금, 비상금은 파킹통장으로 나누는 방법이 많이 쓰입니다."),
    ]),
    "script": """<script>
function calc(){var P=num('p'),n=Math.round(num('n')),y=num('r')/100,tx=parseFloat(pick('t'))/100;if(!P||!n){return;}
var i=pick('k')==='s'?P*y*n/12:P*(Math.pow(1+y/12,n)-1);var tax=Math.floor(i*tx);
show('out','<dl><dt>세전 이자</dt><dd>'+won(i)+'</dd><dt>세금</dt><dd>'+won(tax)+'</dd><dt>세후 이자</dt><dd>'+won(i-tax)+'</dd><dt>만기 수령액</dt><dd class="big">'+won(P+i-tax)+'</dd></dl>');}
</script>""",
}

CALCS["severance-pay"] = {
    "title": "퇴직금 계산기",
    "desc": "입사일, 마지막 근무일, 최근 3개월 임금을 넣으면 근로자퇴직급여 보장법 기준 법정 퇴직금을 계산합니다.",
    "body": f"""<p>1년 이상 일하고 그만두면 법정 퇴직금을 받습니다. 퇴직 전 3개월 동안 받은 임금으로 1일 평균임금을 구하고, 재직 기간을 곱해 계산합니다.</p>
<div class="calc"><div class="row"><div><label for="s">입사일</label><input id="s" type="date" value="2023-11-01"></div><div><label for="e">마지막 근무일</label><input id="e" type="date" value="2026-10-31"></div></div>
<label for="w">퇴직 전 3개월 임금 총액(세전, 원)</label><input id="w" inputmode="numeric" data-money value="9,000,000">
<div class="row"><div><label for="b">연간 상여금(원)</label><input id="b" inputmode="numeric" data-money value="0"></div><div><label for="a">연차수당(1년 치, 원)</label><input id="a" inputmode="numeric" data-money value="0"></div></div>
<button type="button" onclick="calc()">계산하기</button><div class="res" id="out" aria-live="polite"></div></div>
<h2>계산 방법</h2>
<p>1일 평균임금 = (퇴직 전 3개월 임금 총액 + 연간 상여금 × 3/12 + 연차수당 × 3/12) ÷ 퇴직 전 3개월의 달력 일수</p>
<p>퇴직금 = 1일 평균임금 × 30일 × 재직일수 ÷ 365</p>
<p>3개월 임금에는 기본급과 정기적으로 받은 수당을 넣고, 실비 성격의 돈(출장비 등)은 빼세요. 평균임금이 통상임금보다 적으면 통상임금으로 계산합니다.</p>
<h2>예시: 월급 300만 원, 2023년 11월 1일 입사, 2026년 10월 31일까지 근무</h2>
<p>재직일수 1,096일, 퇴직 전 3개월(8월 1일~10월 31일) 92일. 1일 평균임금은 900만 원 ÷ 92일 = 약 97,826원이고, 퇴직금은 97,826원 × 30 × 1,096 ÷ 365 = 약 8,812,388원입니다.</p>
""" + _faq([
        ("1년을 못 채우면 퇴직금이 없나요?", "법정 퇴직금은 계속 근로기간 1년 이상, 4주 평균 주 15시간 이상 일한 경우에 받습니다. 1년 미만이면 법정 퇴직금 대상이 아닙니다."),
        ("퇴직금에도 세금이 붙나요?", "퇴직소득세가 붙습니다. 근속연수가 길수록 공제가 커서 실제 세금은 일반 소득보다 낮은 편입니다. IRP로 받으면 세금을 미뤘다가 연금으로 받을 때 줄일 수 있습니다."),
        ("DC형 퇴직연금이면 이 계산이 맞나요?", "DC형은 회사가 매년 연봉의 12분의 1 이상을 계좌에 넣고 운용 결과에 따라 받는 금액이 달라집니다. 이 계산기는 퇴직금 제도와 DB형 기준입니다."),
        ("언제까지 받아야 하나요?", "회사는 퇴직일로부터 14일 안에 지급해야 합니다. 당사자끼리 합의하면 늦출 수 있습니다. 받지 못하면 고용노동부에 진정할 수 있습니다."),
    ]),
    "script": """<script>
function calc(){var s=new Date(document.getElementById('s').value),e=new Date(document.getElementById('e').value);if(isNaN(s)||isNaN(e)||e<s){return;}
var day=86400000,days=Math.round((e-s)/day)+1;var q=new Date(e.getTime()+day);q.setMonth(q.getMonth()-3);var qd=Math.round((e-q)/day)+1;
var avg=(num('w')+num('b')*3/12+num('a')*3/12)/qd;var pay=avg*30*days/365;
var warn=days<365?'<p class="note2">재직 기간이 1년 미만이라 법정 퇴직금 대상이 아닙니다(참고로 계산만 보여 드립니다).</p>':'';
show('out','<dl><dt>재직일수</dt><dd>'+days.toLocaleString('ko-KR')+'일</dd><dt>퇴직 전 3개월 일수</dt><dd>'+qd+'일</dd><dt>1일 평균임금</dt><dd>'+won(avg)+'</dd><dt>예상 퇴직금(세전)</dt><dd class="big">'+won(pay)+'</dd></dl>'+warn);}
</script>""",
}

CALCS["weekly-holiday-pay"] = {
    "title": "주휴수당 계산기",
    "desc": f"시급과 주당 근무시간을 넣으면 주휴수당과 주휴수당을 포함한 월급을 계산합니다. {BASIS['min_wage_year']}년 최저임금 시간당 {BASIS['min_wage']:,}원 기준.",
    "body": f"""<p>한 주에 15시간 이상 일하고 정해진 근무일을 모두 나가면, 쉬는 날에도 하루치 임금(주휴수당)을 받습니다. 아르바이트도 똑같이 적용됩니다.</p>
<div class="calc"><div class="row"><div><label for="h">시급(원)</label><input id="h" inputmode="numeric" data-money value="{BASIS['min_wage']:,}"></div><div><label for="w">한 주 근무시간</label><input id="w" inputmode="decimal" value="20"></div></div>
<button type="button" onclick="calc()">계산하기</button><div class="res" id="out" aria-live="polite"></div></div>
<h2>계산 방법</h2>
<p>주휴시간 = 한 주 근무시간 ÷ 40 × 8 (40시간 이상이면 8시간). 주휴수당 = 주휴시간 × 시급입니다.</p>
<p>월로 바꿀 때는 한 달을 평균 약 4.345주(365일 ÷ 7 ÷ 12)로 보고, 월 근무시간은 시간 단위로 반올림합니다. 주 40시간이면 (40+8)시간 × 4.345 = 약 209시간이 한 달 근무시간이 되고, {BASIS['min_wage_year']}년 최저임금으로 계산한 월급은 209시간 × {BASIS['min_wage']:,}원 = {209 * BASIS['min_wage']:,}원입니다.</p>
<h2>예시: 시급 {BASIS['min_wage']:,}원, 주 20시간</h2>
<p>주휴시간은 20 ÷ 40 × 8 = 4시간, 주휴수당은 한 주에 {4 * BASIS['min_wage']:,}원입니다. 한 달로 바꾸면 약 179,371원이 더해집니다.</p>
""" + _faq([
        ("주 15시간이 안 되면요?", "4주 평균 한 주 근무시간이 15시간 미만이면 주휴수당 대상이 아닙니다."),
        ("결근하면 주휴수당이 없나요?", "그 주에 정해진 근무일을 모두 나가야 받습니다. 지각이나 조퇴는 결근이 아니어서 주휴수당이 사라지지 않습니다."),
        ("주휴수당을 안 주면 어떻게 하나요?", "임금체불에 해당합니다. 근무 기록(근로계약서, 출퇴근 기록, 급여 내역)을 모아 고용노동부에 진정할 수 있습니다."),
    ]),
    "script": """<script>
function calc(){var h=num('h'),w=num('w');if(!h||!w){return;}
var hol=w>=15?Math.min(w,40)/40*8:0,pay=hol*h,wk=365/7/12;
var msg=w<15?'<p class="note2">주 15시간 미만이라 주휴수당 대상이 아닙니다.</p>':'';
show('out','<dl><dt>주휴시간</dt><dd>'+hol.toFixed(1)+'시간</dd><dt>주휴수당(1주)</dt><dd class="big">'+won(pay)+'</dd><dt>주휴수당(월 환산)</dt><dd>'+won(pay*wk)+'</dd><dt>주휴 포함 월급</dt><dd>'+won(Math.round((w+hol)*wk)*h)+'</dd></dl>'+msg);}
</script>""",
}

CALCS["vat"] = {
    "title": "부가세 계산기",
    "desc": "공급가액이나 합계금액을 넣으면 부가가치세 10%와 나머지 금액을 계산합니다.",
    "body": """<p>견적서나 세금계산서를 쓸 때 공급가액과 부가세를 나눠야 할 때가 많습니다. 어느 쪽 금액을 알고 있는지 고르고 넣으세요.</p>
<div class="calc"><label>아는 금액</label><div class="seg"><label><input type="radio" name="k" value="s" checked>공급가액(부가세 별도)</label><label><input type="radio" name="k" value="t">합계금액(부가세 포함)</label></div>
<label for="a">금액(원)</label><input id="a" inputmode="numeric" data-money value="1,100,000">
<button type="button" onclick="calc()">계산하기</button><div class="res" id="out" aria-live="polite"></div></div>
<h2>계산 방법</h2>
<p>부가가치세는 공급가액의 10%입니다. 공급가액을 알면 부가세 = 공급가액 × 0.1, 합계 = 공급가액 × 1.1입니다. 합계금액만 알면 공급가액 = 합계 ÷ 1.1이고, 부가세는 합계에서 공급가액을 뺀 금액입니다.</p>
<h2>예시</h2>
<ul><li>공급가액 1,000,000원 → 부가세 100,000원, 합계 1,100,000원</li><li>합계 1,100,000원 → 공급가액 1,000,000원, 부가세 100,000원</li></ul>
<p>간이과세자는 업종별 부가가치율을 곱해 내야 할 세금을 따로 계산하므로 이 계산과 다릅니다.</p>
""" + _faq([
        ("1원 단위는 어떻게 하나요?", "합계에서 공급가액을 구할 때 소수점이 생기면 보통 공급가액을 원 단위로 맞추고 나머지를 부가세로 둡니다. 세금계산서에 적는 금액은 거래처와 같은 방식으로 맞추세요."),
        ("부가세 신고는 언제 하나요?", "개인 일반과세자는 1월(지난해 7~12월분)과 7월(1~6월분)에 확정신고를 하고, 간이과세자는 1월에 한 해 치를 신고합니다."),
    ]),
    "script": """<script>
function calc(){var a=num('a');if(!a){return;}var s,v,t;
if(pick('k')==='s'){s=a;v=Math.floor(a*0.1);t=s+v;}else{t=a;s=Math.round(a/1.1);v=t-s;}
show('out','<dl><dt>공급가액</dt><dd>'+won(s)+'</dd><dt>부가세(10%)</dt><dd class="big">'+won(v)+'</dd><dt>합계</dt><dd>'+won(t)+'</dd></dl>');}
</script>""",
}

# 계산기마다 관련 글을 찾을 낱말과 공식 사이트
LINKS = {
    "loan-interest": (("대출", "중도상환", "금리인하"), ("금융감독원 파인", "https://fine.fss.or.kr")),
    "savings-interest": (("적금", "파킹통장", "예금"), ("금융감독원 파인", "https://fine.fss.or.kr")),
    "deposit-interest": (("예금", "파킹통장", "적금"), ("예금보험공사", "https://www.kdic.or.kr")),
    "severance-pay": (("퇴직금", "퇴직연금", "퇴직소득"), ("고용노동부", "https://www.moel.go.kr")),
    "weekly-holiday-pay": (("주휴", "최저임금", "실업급여", "근로"), ("고용노동부", "https://www.moel.go.kr")),
    "vat": (("부가세", "부가가치세", "간이과세"), ("국세청 홈택스", "https://www.hometax.go.kr")),
}


def page_body(slug: str, related: List[Tuple[str, str]]) -> str:
    c = CALCS[slug]
    oname, ourl = LINKS[slug][1]
    rel = "".join(f'<li><a href="{u}">{t}</a></li>' for t, u in related)
    others = "".join(f'<li><a href="/calc/{s}/">{x["title"]}</a></li>' for s, x in CALCS.items() if s != slug)
    return (CSS + c["body"]
            + (f"<h2>함께 보면 좋은 글</h2><ul>{rel}</ul>" if rel else "")
            + f'<h2>다른 계산기</h2><ul>{others}</ul>'
            + f'<p class="note2">계산 결과는 참고용 어림값입니다. 실제 금액은 상품 약정, 회사 규정, 세법 적용에 따라 달라질 수 있으니 '
            + f'<a href="{ourl}" target="_blank" rel="noopener">{oname}</a> 등 공식 기관에서 확인하세요. 기준일 {BASIS["updated"]}.</p>'
            + JS_COMMON + c["script"])


def index_body() -> str:
    items = "".join(f'<li><a href="/calc/{s}/"><b>{c["title"]}</b></a><span>{c["desc"]}</span></li>' for s, c in CALCS.items())
    return (CSS + "<p>대출이자, 예금·적금 이자, 퇴직금, 주휴수당, 부가세처럼 자주 찾는 계산을 한곳에 모았습니다. 공식은 각 페이지에 그대로 적어 두었습니다.</p>"
            + f'<ul class="clist">{items}</ul>')
