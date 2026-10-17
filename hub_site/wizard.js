/* ---------- 빠른 확인 ---------- */
/* 판정 기준 연도·중위소득: 서버가 매년 자동 조사·검증해 저장한 data/output/standards.json이 있으면 그 값을 쓴다(없으면 2026년 기본값) */
const STD = D.standards || {year: 2026, median: {1: 2564238, 2: 4199292, 3: 5359036, 4: 6494738, 5: 7556719, 6: 8555952}};
const RULES_YEAR = STD.year;
const MED = [0, 1, 2, 3, 4, 5].map((i) => i === 0 ? 0 : STD.median[i] / 10000); /* 중위소득(만원/월), 1~5인 */
const LO = [0, 0, 1000, 1500, 2200, 3200, 4400, 6000, 8000];
const HI = [0, 1000, 1500, 2200, 3200, 4400, 6000, 8000, Infinity];
const INC_L = ['소득 거의 없음', '1,000만 원 미만', '1,000~1,500만 원', '1,500~2,200만 원', '2,200~3,200만 원', '3,200~4,400만 원', '4,400~6,000만 원', '6,000~8,000만 원', '8,000만 원 이상'];
const AGE_R = {y: [19, 34], m: [35, 59], s: [60, 64], e: [65, 120]};
const LABEL = {y: '19~34세', m: '35~59세', s: '60~64세', e: '65세 이상', single: '혼자', one: '부부(외벌이)', two: '부부(맞벌이)', sp: '한부모+자녀', other: '다른 가족과 함께'};
const QS = [
  {k: 'age', t: '만 나이가 어떻게 되세요?', h: '가장 가까운 구간을 고르세요.', o: [['y', '만 19세 ~ 34세'], ['m', '만 35세 ~ 59세'], ['s', '만 60세 ~ 64세'], ['e', '만 65세 이상']]},
  {k: 'hh', t: '가구는 어떻게 구성되어 있나요?', h: '세금·복지에서 보는 가구 기준입니다.', o: [['single', '혼자 살아요'], ['one', '부부, 한 명만 소득이 있어요'], ['two', '부부, 둘 다 소득이 있어요'], ['sp', '한부모와 자녀가 살아요'], ['other', '부모·형제 등 다른 가족과 살아요']]},
  {k: 'size', t: '함께 사는 가구원은 모두 몇 명인가요?', h: '본인을 포함한 수입니다.', skip: (a) => a.hh === 'single', o: [[2, '2명'], [3, '3명'], [4, '4명'], [5, '5명 이상']]},
  {k: 'inc', t: '가구의 1년 소득(세전)은 어느 정도인가요?', h: '함께 사는 가족 소득을 합친 대략의 금액이면 됩니다.', o: INC_L.map((l, i) => [i, l])},
  {k: 'asset', t: '집·땅·예금 등 가구 재산은 얼마쯤인가요?', h: '전세보증금과 자동차도 포함해 대략 합산하세요.', o: [[0, '1억 2,200만 원 미만'], [1, '1억 2,200만 ~ 2억 4천만 원'], [2, '2억 4천만 원 이상']]},
  {k: 'flags', t: '가구 상황에서 해당하는 것을 모두 고르세요.', h: '없으면 그대로 다음으로 넘어가세요.', multi: true, o: [['rent', '월세로 살고 있어요'], ['apart', '부모님과 따로 살고 있어요'], ['disabled', '장애가 있는 가족이 있어요'], ['pregnant', '임신 중이에요'], ['baby', '만 2세 미만(0~23개월) 아이가 있어요'], ['child9', '만 9세 미만 아이가 있어요'], ['teen', '만 9~17세 자녀가 있어요']]},
  {k: 'flags', t: '지금 상황은 어떠세요? 해당하는 것을 모두 고르세요.', h: '없으면 그대로 결과 보기를 누르세요.', multi: true, last: true, o: [['working', '일하고 있어요 (직장인·자영업)'], ['jobseek', '일자리를 구하는 중이에요'], ['recipient', '기초생활수급(생계·의료급여)을 받고 있어요'], ['student', '대학(원)에 다니고 있어요']]},
];
let step = 0, ans = {flags: []};
function showHome() { setView('home'); }
function showCheck() { setView('check'); step = 0; ans = {flags: []}; renderStep(); pushView('check'); }
$('#open-check').addEventListener('click', showCheck);
$('#logo').addEventListener('click', (e) => { e.preventDefault(); showHome(); });
function skipped(i) { return QS[i] && QS[i].skip && QS[i].skip(ans); }
$('#back').addEventListener('click', () => {
  if (step > 0 && step <= QS.length) { step--; while (step > 0 && skipped(step)) step--; renderStep(); } else showHome();
});

function renderStep() {
  const w = $('#wiz');
  while (step < QS.length && skipped(step)) { if (QS[step].k === 'size') ans.size = 1; step++; }
  if (step >= QS.length) return renderResult();
  const q = QS[step];
  $('#back-t').textContent = step ? '이전 질문' : '홈으로';
  const on = (v) => q.multi ? ans.flags.includes(v) : ans[q.k] === v;
  w.innerHTML = `<div class="pr"><span style="width:${(step + 1) / QS.length * 100}%"></span></div><p class="stp">${step + 1} / ${QS.length}</p><h1 class="q">${q.t}</h1><p class="hint">${q.h}</p>` +
    q.o.map(([v, l]) => `<button class="opt${on(v) ? ' on' : ''}" data-v="${v}">${q.multi ? '<span class="box">' + (on(v) ? '✓' : '') + '</span>' : ''}${l}</button>`).join('') +
    (q.multi ? `<button class="go" id="go">${q.last ? '결과 보기' : '다음'}</button>` : '');
  w.querySelectorAll('.opt').forEach((b) => b.addEventListener('click', () => {
    const raw = b.dataset.v, v = isNaN(raw) ? raw : Number(raw);
    if (q.multi) { const i = ans.flags.indexOf(v); i >= 0 ? ans.flags.splice(i, 1) : ans.flags.push(v); renderStep(); }
    else { ans[q.k] = v; if (q.k === 'hh' && v === 'single') ans.size = 1; step++; renderStep(); window.scrollTo(0, 0); }
  }));
  if (q.multi) $('#go').addEventListener('click', () => { step++; renderStep(); window.scrollTo(0, 0); });
}

/* ---------- 판정 규칙 (2026년 기준, 예시 로직) ---------- */
function pcts(a) { const m = MED[Math.min(a.size || 1, 5)]; return {lo: LO[a.inc] / 12 / m * 100, hi: HI[a.inc] / 12 / m * 100}; }
const Y = (r) => ({s: 'y', r}), M = (r) => ({s: 'm', r}), N = (r) => ({s: 'n', r});
const BASIC_M = '소득인정액(소득+재산 환산액)으로 판정합니다. 복지로 모의계산으로 확인하세요.';
function basicRule(a, th, recipientKnown) {
  const p = pcts(a);
  if (recipientKnown && a.flags.includes('recipient')) return Y('이미 받고 계신 제도예요. 소득·재산이 바뀌면 주민센터에 알려 주세요.');
  if (p.lo >= th * 1.7) return N('가구 소득이 선정기준을 크게 넘는 구간입니다(근로소득 공제를 감안해도 어렵습니다).');
  if (p.hi <= th * 0.75 && a.asset === 0) return M('소득·재산이 낮은 구간이라 확인해 볼 만합니다. 부양가족·근로능력·재산 환산 등 다른 요건이 있어 ' + BASIC_M);
  if (a.asset === 2) return M('재산 환산액이 커서 확인이 필요합니다. ' + BASIC_M);
  return M(BASIC_M);
}
const PROGS = [
  {k: 'eitc', n: '근로장려금', kw: '근로장려금', off: ['https://www.hometax.go.kr', '홈택스에서 확인'], fn: (a, has) => {
    const T = {single: 2200, one: 3200, two: 4400, sp: 3200}[a.hh];
    if (!T) return M('가구 유형(단독·홑벌이·맞벌이)에 따라 소득 기준이 달라 확인이 필요합니다.');
    if (a.asset === 2) return N('가구 재산이 2억 4천만 원 이상이면 대상에서 제외됩니다.');
    if (!has('working') || a.inc === 0) return M('근로·사업소득이 있어야 받을 수 있습니다. 소득이 있다면 기준 안에 들 수 있습니다.');
    if (HI[a.inc] <= T) return Y('소득과 재산 기준 안에 들어갈 수 있는 구간입니다.' + (a.asset === 1 ? ' 재산이 1억 7천만 원 이상이면 지급액이 줄 수 있습니다.' : ''));
    return N('가구 소득이 기준을 넘는 구간입니다.');
  }},
  {k: 'child_eitc', n: '자녀장려금', kw: '자녀장려금', off: ['https://www.hometax.go.kr', '홈택스에서 확인'], fn: (a, has) => {
    if (!(has('child9') || has('teen'))) return N('만 18세 미만 부양 자녀가 있는 가구가 대상입니다.');
    if (a.hh === 'single') return M('자녀가 있는 가구 유형을 다시 확인해 보세요.');
    if (a.asset === 2) return N('가구 재산이 2억 4천만 원 이상이면 대상에서 제외됩니다.');
    if (HI[a.inc] <= 6000) return Y('부부합산 연소득 7,000만 원 미만 구간에 들어갈 수 있습니다.');
    if (LO[a.inc] >= 8000) return N('가구 소득이 기준을 넘는 구간입니다.');
    return M('소득이 기준선(7,000만 원) 근처라 정확한 확인이 필요합니다.');
  }},
  {k: 'pension', n: '기초연금', kw: '기초연금', off: ['https://www.bokjiro.go.kr', '복지로에서 확인'], fn: (a) => {
    if (a.age !== 'e') return N('만 65세 이상이 대상입니다.');
    const two = (a.size || 1) >= 2;
    if (HI[a.inc] <= (two ? 2200 : 1500) && a.asset === 0) return Y('소득과 재산이 낮은 구간이라 선정기준 안에 들 가능성이 큽니다. 소득인정액으로 판정하니 복지로 모의계산도 해 보세요.');
    if (LO[a.inc] >= (two ? 8000 : 6000)) return N('소득이 높은 구간이라 선정기준액을 넘을 가능성이 큽니다.');
    return M('소득인정액에는 재산 환산액이 포함되고 근로소득은 일부 공제됩니다. 복지로 모의계산으로 확인하세요.');
  }},
  {k: 'rent', n: '청년월세 특별지원', kw: '청년월세', off: ['https://www.bokjiro.go.kr', '복지로에서 확인'], fn: (a, has) => {
    if (a.age !== 'y') return N('만 19세~34세 청년이 대상입니다.');
    if (!has('rent')) return N('월세로 살고 있는 경우가 대상입니다.');
    if (a.asset >= 1) return N('청년가구 재산이 1억 2,200만 원 이하여야 합니다.');
    if (a.hh !== 'single') return M('가구 구성에 따라 소득 기준이 달라져 확인이 필요합니다.');
    if (LO[a.inc] >= 2200) return N('소득이 기준을 넘을 가능성이 큰 구간입니다.');
    if (HI[a.inc] <= 1500 && has('apart')) return Y('나이·월세·소득·재산 조건에 맞을 가능성이 있는 구간입니다.');
    return M(HI[a.inc] > 1500 ? '소득이 기준선 근처라 정확한 확인이 필요합니다.' : '부모님과 따로 사는지에 따라 원가구 기준을 함께 봅니다.');
  }},
  {k: 'parent', n: '부모급여', kw: '부모급여', off: ['https://www.gov.kr', '정부24에서 확인'], fn: (a, has) => has('baby') ? Y('만 2세 미만 아이가 있으면 소득·재산과 관계없이 받을 수 있습니다.') : N('0~23개월 아이가 있는 가구가 대상입니다.')},
  {k: 'child_allow', n: '아동수당', kw: '아동수당', off: ['https://www.bokjiro.go.kr', '복지로에서 확인'], fn: (a, has) => has('child9') || has('baby') ? Y('만 9세 미만 아동이면 소득·재산과 관계없이 받을 수 있습니다(거주 지역에 따라 금액이 달라집니다).') : N('만 9세 미만 아동이 있는 가구가 대상입니다.')},
  {k: 'preg', n: '임신·출산 진료비 바우처', kw: '임신', off: ['https://www.gov.kr', '정부24에서 확인'], fn: (a, has) => has('pregnant') ? Y('임신 중이라면 대상이 될 수 있습니다. 건강보험공단 등에서 바우처를 신청하세요.') : N('임신 중인 경우가 대상입니다.')},
  {k: 'livelihood', n: '생계급여', kw: '생계급여', off: ['https://www.bokjiro.go.kr', '복지로에서 확인'], fn: (a) => basicRule(a, 32, true)},
  {k: 'housing', n: '주거급여', kw: '주거급여', off: ['https://www.bokjiro.go.kr', '복지로에서 확인'], fn: (a) => basicRule(a, 48, false)},
  {k: 'medical', n: '의료급여', kw: '의료급여', off: ['https://www.bokjiro.go.kr', '복지로에서 확인'], fn: (a) => basicRule(a, 40, true)},
  {k: 'edu', n: '교육급여', kw: '교육급여', off: ['https://www.bokjiro.go.kr', '복지로에서 확인'], fn: (a, has) => (has('child9') || has('teen')) ? basicRule(a, 50, false) : N('초·중·고 학생이 있는 가구가 대상입니다.')},
  {k: 'energy', n: '에너지바우처', kw: '에너지바우처', off: ['https://www.bokjiro.go.kr', '복지로에서 확인'], fn: (a, has) => {
    const vuln = a.age === 'e' || has('baby') || has('disabled') || has('pregnant') || a.hh === 'sp';
    if (has('recipient')) return vuln ? Y('생계·의료급여 수급자 중 노인·영유아·장애인·임산부·한부모 가구 등이 대상입니다.') : M('수급자 중 노인·영유아·장애인·임산부 등 취약계층이 대상이라 가구원 구성을 확인해야 합니다.');
    return N('생계·의료급여 수급자 중 에너지 취약계층이 대상입니다.');
  }},
  {k: 'sp', n: '한부모가족 지원', kw: '한부모', off: ['https://www.bokjiro.go.kr', '복지로에서 확인'], fn: (a, has) => {
    if (a.hh !== 'sp') return N('한부모 가구가 대상입니다.');
    if (!(has('baby') || has('child9') || has('teen'))) return M('만 18세 미만 자녀를 양육하는 경우가 대상입니다. 자녀 나이를 확인하세요.');
    const p = pcts(a);
    if (p.hi <= 55) return Y('기준 중위소득 65% 이하 구간에 들어갈 가능성이 큽니다.');
    if (p.lo >= 100) return N('가구 소득이 기준(중위소득 65%)을 크게 넘는 구간입니다.');
    return M('소득이 기준(중위소득 65%) 근처라 정확한 확인이 필요합니다.');
  }},
  {k: 'job', n: '국민취업지원제도', kw: '국민취업지원', off: ['https://www.work24.go.kr', '고용24에서 확인'], fn: (a, has) => has('jobseek') ? M('구직 중이라면 대상이 될 수 있습니다. 소득·재산·취업 경험에 따라 유형이 나뉘니 고용센터에서 확인하세요.') : N('구직 중인 경우가 대상입니다.')},
  {k: 'learn', n: '국민내일배움카드', kw: '내일배움', off: ['https://www.hrd.go.kr', 'HRD-Net에서 확인'], fn: (a, has) => (has('jobseek') || has('working')) ? Y('구직자뿐 아니라 재직자·자영업자도 요건을 충족하면 발급받을 수 있습니다(일부 대기업·공무원 등 제외).') : N('구직자·재직자·자영업자가 대상입니다.')},
  {k: 'rent_credit', n: '월세 세액공제', kw: '월세', off: ['https://www.hometax.go.kr', '홈택스에서 확인'], fn: (a, has) => {
    if (!has('rent')) return N('월세로 사는 무주택 세대주가 대상입니다.');
    if (!has('working')) return M('총급여가 있는 근로자가 대상입니다. 소득 형태를 확인하세요.');
    if (LO[a.inc] >= 8000) return N('총급여 8,000만 원 이하가 대상입니다.');
    return Y('총급여 8,000만 원 이하 무주택 세대주가 대상입니다(5,500만 원 이하 17%, 초과 15%). 주택 규모 요건은 확인하세요.');
  }},
  {k: 'child_credit', n: '자녀 세액공제', kw: '자녀 세액', off: ['https://www.hometax.go.kr', '홈택스에서 확인'], fn: (a, has) => {
    if (!(has('teen') || has('child9'))) return N('8세 이상 기본공제 대상 자녀가 있어야 합니다.');
    if (!has('working')) return M('세금을 내는 소득이 있어야 공제받을 수 있습니다.');
    return has('teen') ? Y('8세 이상 자녀가 대상입니다(2026년 첫째 25만 원, 둘째 30만 원, 셋째 이후 40만 원).') : M('8세 이상 자녀가 대상이라 아이 나이를 확인해야 합니다.');
  }},
  {k: 'pension_credit', n: '연금저축·IRP 세액공제', kw: '연금저축', off: ['https://www.hometax.go.kr', '홈택스에서 확인'], fn: (a, has) => has('working') ? Y('연금저축·IRP에 납입하면 세액공제를 받을 수 있습니다(총급여 5,500만 원 이하 16.5%, 초과 13.2%).') : M('세금을 내는 소득이 있어야 공제받을 수 있습니다.')},
  {k: 'isa', n: 'ISA 서민형 (비과세 400만 원)', kw: 'ISA', fn: (a, has) => {
    if (!has('working')) return M('서민형은 근로소득 5천만 원 이하 또는 종합소득 3,800만 원 이하가 대상입니다. 소득 증빙을 확인하세요. 일반형(200만 원)은 누구나 가입할 수 있습니다.');
    if (LO[a.inc] >= 6000) return N('서민형 소득 기준(근로소득 5천만 원 이하)을 넘는 구간입니다. 일반형은 누구나 가입할 수 있습니다.');
    if (HI[a.inc] <= 4400) return Y('근로소득 5천만 원 이하 서민형 요건에 들어갈 수 있습니다.');
    return M('소득이 기준선(5천만 원) 근처라 정확한 확인이 필요합니다.');
  }},
  {k: 'sme', n: '중소기업 취업청년 소득세 감면', kw: '중소기업 취업청년', off: ['https://www.hometax.go.kr', '홈택스에서 확인'], fn: (a, has) => (a.age === 'y' && has('working')) ? M('중소기업 취업자인지, 제외 업종인지 확인이 필요합니다. 근로소득세 90%를 5년간(연 200만 원 한도) 감면받을 수 있습니다.') : N('만 15~34세 중소기업 취업자가 대상입니다.')},
];
function evaluate(a) {
  const has = (f) => a.flags.includes(f);
  return PROGS.map((p) => Object.assign({k: p.k, n: p.n, kw: p.kw, off: p.off}, p.fn(a, has)));
}

/* ---------- 2단계: 공공데이터(보조금24) 후보 ---------- */
const TG = ['farm', 'biz', 'vet', 'foreign', 'art', 'disabled', 'pregnant', 'newborn', 'child', 'student', 'senior', 'youth', 'sp', 'job', 'low'];
const BRK = [[0, 50], [50, 75], [75, 100], [100, 200], [200, 1e9]];
function userMask(a) {
  const has = (f) => a.flags.includes(f), p = pcts(a), s = new Set();
  if (has('disabled')) s.add('disabled');
  if (has('pregnant')) s.add('pregnant');
  if (has('baby') || has('pregnant')) s.add('newborn');
  if (has('baby') || has('child9') || has('teen')) s.add('child');
  if (has('student')) s.add('student');
  if (a.age === 'e' || a.age === 's') s.add('senior');
  if (a.age === 'y') s.add('youth');
  if (a.hh === 'sp') s.add('sp');
  if (has('jobseek')) s.add('job');
  if (has('recipient') || p.lo <= 60) s.add('low');
  return TG.reduce((m, t, i) => s.has(t) ? m | (1 << i) : m, 0);
}
function candidates(a) {
  const um = userMask(a), p = pcts(a), ar = AGE_R[a.age];
  return D.cand.filter((r) => {
    const [, , , , , , , lo, hi, inc, tg] = r;
    if (lo !== null && hi !== null && !(ar[1] >= lo && ar[0] <= hi)) return false;
    if (inc !== 0 && inc !== 31 && !BRK.some((b, i) => (inc >> i) & 1 && p.lo <= b[1] && p.hi >= b[0])) return false;
    if (tg !== 0 && (tg & um) === 0) return false;
    return true;
  });
}

/* ---------- 결과 화면 ---------- */
function postLink(k) { return D.program_posts[k] || ''; }
function resCard(x) {
  const bd = {y: ['b-y', '해당 가능성 높음'], m: ['b-m', '확인 필요'], n: ['b-n', '해당 어려움']}[x.s];
  const post = postLink(x.k);
  const main = post ? `<a class="lb pri" href="${post}">자세한 글 보기 ›</a>` : `<button class="lb pri" data-kw="${esc(x.kw)}" type="button">관련 글 찾기 ›</button>`;
  const off = x.off ? `<a class="lb sec" href="${x.off[0]}" target="_blank" rel="noopener">${x.off[1]}</a>` : '';
  const links = x.s === 'n' ? '' : `<div class="lk">${main}${off}</div>`;
  return `<div class="res"><div class="rt"><span class="rn">${x.n}</span><span class="bd ${bd[0]}">${bd[1]}</span></div><p class="rd" style="margin-bottom:${links ? 10 : 0}px">${x.r}</p>${links}</div>`;
}
function candCard(r) {
  return `<div class="res"><div class="rt"><span class="rn" style="font-size:15px">${esc(r[1])}</span></div><p class="mt" style="margin:0 0 6px">${esc(r[2])}${r[3] ? ' · ' + esc(r[3]) : ''}</p>${r[4] ? `<p class="rd" style="margin-bottom:10px">${esc(r[4])}</p>` : ''}<div class="lk"><a class="lb sec" style="flex:1" href="${esc(r[5])}" target="_blank" rel="noopener">상세 조건 확인 (정부24)</a></div></div>`;
}
let candShown = 8, candList = [];
function renderCands() {
  $('#cands').innerHTML = candList.slice(0, candShown).map(candCard).join('');
  $('#candmore').style.display = candList.length > candShown ? 'block' : 'none';
}
function renderResult() {
  $('#back-t').textContent = '답 수정하기';
  const r = evaluate(ans);
  const y = r.filter((x) => x.s === 'y'), m = r.filter((x) => x.s === 'm'), n = r.filter((x) => x.s === 'n');
  const sum = [LABEL[ans.age], LABEL[ans.hh] + (ans.size > 1 ? ' · ' + (ans.size === 5 ? '5명 이상' : ans.size + '명') : ''), INC_L[ans.inc], ['재산 1.22억 미만', '재산 1.22~2.4억', '재산 2.4억 이상'][ans.asset]].join(' · ');
  candList = candidates(ans); candShown = 8;
  $('#wiz').innerHTML = `<h1 class="q" style="margin-top:6px">확인 결과</h1><div class="sum">${sum}<br>직접 검증한 ${PROGS.length}개 제도(${RULES_YEAR}년 기준)를 바탕으로 한 대략적인 안내입니다.</div>` +
    (y.length ? `<p class="sub2" style="color:var(--ok)">해당 가능성이 높아요 (${y.length})</p>` + y.map(resCard).join('') : '') +
    (m.length ? `<p class="sub2" style="color:var(--warn)">확인이 필요해요 (${m.length})</p>` + m.map(resCard).join('') : '') +
    (!y.length && !m.length ? '<div class="res"><p class="rd" style="margin:0">입력하신 조건에서는 대상이 되는 대표 제도를 찾지 못했습니다. 아래 후보 제도를 살펴보세요.</p></div>' : '') +
    (n.length ? `<details class="dt"><summary>해당이 어려운 제도 (${n.length})</summary>${n.map((x) => `<p class="nrow"><b>${x.n}</b><span>${x.r}</span></p>`).join('')}</details>` : '') +
    `<p class="sub2" style="margin-top:26px;color:var(--acc)">이런 제도도 살펴보세요</p><p class="hint" style="margin-bottom:10px">정부 공공데이터(보조금24)에서 입력하신 나이·소득·상황에 맞을 수 있는 제도를 인기순으로 골랐어요. 후보일 뿐이라 조건은 꼭 상세 페이지에서 확인하세요. (후보 ${candList.length}개)</p><div id="cands"></div><button class="more" id="candmore">후보 더 보기</button>` +
    `<p class="disc">참고용 안내이며 지원 여부를 확정하지 않습니다. 재산 환산, 가구원 구성, 지자체 기준 등 입력하지 않은 요소에 따라 달라질 수 있으니 신청 전 해당 기관에서 꼭 확인하세요. 소득·금액 기준은 2026년 기준이며 해마다 바뀝니다.</p><button class="go" id="again" style="background:var(--card);color:var(--text);border:1px solid var(--line2)">처음부터 다시 하기</button>`;
  renderCands();
  $('#candmore').addEventListener('click', () => { candShown += 8; renderCands(); });
  $('#again').addEventListener('click', showCheck);
  $('#wiz').querySelectorAll('button[data-kw]').forEach((b) => b.addEventListener('click', () => { $('#q').value = b.dataset.kw; runSearch(b.dataset.kw, '#serr'); }));
}
