"""사이트 D 안내 쪽(소개·문의·개인정보처리방침) 본문. 언어별로 (제목, 설명, 본문 HTML). {count} = 레시피 수, {email} = 문의 메일.

여기 적는 내용은 실제 운영 방식과 같아야 한다. 데이터 출처나 작성 방식이 바뀌면 함께 고친다.
"""
from __future__ import annotations

UPDATED = "2026-11-04"

PAGES = {
    "about": {
        "ko": ("소개", "냉장고 파먹기가 어떤 사이트인지, 레시피·영양·재료비 정보를 어떻게 만드는지 안내합니다.", """
<p>냉장고 파먹기는 집에 있는 재료를 고르면 지금 만들 수 있는 요리를 찾아 주는 무료 사이트예요. 장을 다시 보기 전에 냉장고에 남은 재료부터 쓰고, 버리는 음식을 줄이는 데 도움이 되려고 만들었어요.</p>
<h2>할 수 있는 일</h2>
<ul>
<li><b>재료로 찾기</b>: 재료를 누르면 바로 만들 수 있는 요리와 1~2가지만 더 있으면 되는 요리를 나눠서 보여 줘요.</li>
<li><b>오늘의 추천식단</b>: 1~5인 가족 기준 하루 식단과 장보기 목록을 날씨·요일·계절에 맞춰 추천해요. 하루 약 1,500kcal 다이어트 식단도 있어요.</li>
<li><b>레시피 {count}개</b>: 그램·밀리리터로 적은 분량, 단계별 순서, 1인분 영양성분과 예상 재료비를 함께 보여 줘요.</li>
<li><b>유아식·반려동물 요리</b>: 주의사항을 함께 적고, 강아지·고양이 요리에는 크기별 하루 급여량을 계산해 두었어요.</li>
</ul>
<h2>정보를 만드는 방법</h2>
<ul>
<li><b>레시피</b>: 널리 쓰이는 일반 조리법을 바탕으로 AI 도구를 활용해 작성했어요. 모호한 분량, 빠진 재료, 너무 짧은 조리 순서는 자동 검사로 걸러 내요. 모든 레시피를 직접 조리해 검증한 것은 아니므로, 재료 상태와 불 세기에 맞춰 조절해 주세요.</li>
<li><b>영양성분</b>: 재료별 식품성분표 평균값으로 계산한 추정치예요. 의학적 식단 관리에는 전문가와 상의해 주세요.</li>
<li><b>재료비</b>: KAMIS(한국농수산식품유통공사) 소매가격과 통계청 온라인수집가격을 반영하고, 나머지는 평균가 추정치를 써요. 사용한 양만 계산한 어림값이에요.</li>
<li><b>인기 요리·날씨</b>: 네이버 검색 데이터와 기상청 단기예보를 사용해요.</li>
<li><b>반려동물 급여량</b>: 휴식 대사량(70 × 체중kg^0.75)으로 구한 하루 필요 열량의 10%를 간식·토핑 한도로 잡아 계산한 참고값이에요. 수의사의 진료를 대신하지 않아요.</li>
<li><b>사진</b>: 위키미디어 커먼즈의 CC 라이선스 사진(출처는 레시피에 표기)이거나 AI로 만든 참고 이미지이며, 실제 완성 모습과 다를 수 있어요.</li>
<li><b>영어판</b>: AI 번역을 사용했어요.</li>
</ul>
<h2>광고와 제휴 고지</h2>
<p>이 사이트는 무료로 운영하기 위해 광고(Google 애드센스)를 게재할 수 있고, 쿠팡 파트너스 활동의 일환으로 일정액의 수수료를 제공받아요. 구매 링크를 통해 사도 구매자가 추가로 내는 비용은 없어요. 광고와 제휴는 레시피 내용에 영향을 주지 않아요.</p>
<h2>운영</h2>
<p>냉장고 파먹기는 <a href="https://dailyfixpoint.com/">데일리픽스 포인트</a>에서 운영해요. 레시피 오류나 제안은 <a href="contact.html">문의</a>로 알려 주세요. 확인 후 고칠게요.</p>
"""),
        "en": ("About", "What Fridge Raid is and how its recipes, nutrition and cost figures are made.", """
<p>Fridge Raid is a free site that finds dishes you can make with what is already in your fridge. It was built to help people use up ingredients before shopping again and throw away less food.</p>
<h2>What you can do here</h2>
<ul>
<li><b>Search by ingredient</b>: tap your ingredients to see dishes you can make now and dishes that need only one or two more.</li>
<li><b>Today's meal plan</b>: a daily menu and shopping list for 1 to 5 people, adjusted to weather, weekday and season, plus a diet plan of about 1,500 kcal.</li>
<li><b>{count} recipes</b>: amounts in grams and milliliters, step-by-step instructions, nutrition per serving and an estimated ingredient cost.</li>
<li><b>Baby food and pet recipes</b>: with safety notes, and daily feeding amounts by size for dogs and cats.</li>
</ul>
<h2>How the information is made</h2>
<ul>
<li><b>Recipes</b>: written with the help of AI tools, based on widely used home cooking methods. Automated checks catch vague amounts, missing ingredients and steps that are too short. Not every recipe has been cooked and tested by us, so please adjust to your ingredients and stove.</li>
<li><b>Nutrition</b>: estimates calculated from average food composition values. Talk to a professional for medical diets.</li>
<li><b>Ingredient cost</b>: Korean retail prices from KAMIS and Statistics Korea, with estimated averages for the rest. It only counts the amount used.</li>
<li><b>Popular dishes and weather</b>: Naver search data and the Korea Meteorological Administration forecast.</li>
<li><b>Pet feeding amounts</b>: reference values using 10% of daily energy needs, based on resting energy of 70 x weight(kg)^0.75. They do not replace veterinary advice.</li>
<li><b>Photos</b>: Creative Commons photos from Wikimedia Commons (credited on each recipe) or AI-generated reference images, which may differ from the real dish.</li>
<li><b>English pages</b>: translated with AI.</li>
</ul>
<h2>Ads and affiliate disclosure</h2>
<p>To stay free, this site may show ads (Google AdSense) and earns a commission as part of the Coupang Partners program. Buying through a link costs you nothing extra. Ads and affiliate links do not affect recipe content.</p>
<h2>Who runs this site</h2>
<p>Fridge Raid is run by <a href="https://dailyfixpoint.com/">Daily Fix Point</a>. Please report recipe errors or suggestions on the <a href="contact.html">contact page</a>.</p>
"""),
    },
    "contact": {
        "ko": ("문의", "레시피 오류 제보, 정정 요청, 제휴·광고 문의 방법을 안내합니다.", """
<p>레시피 오류 제보, 정정 요청, 추가하면 좋을 요리 제안, 제휴·광고 문의를 받아요. 아래 이메일로 보내 주세요.</p>
<h2>이메일</h2>
<p><a href="mailto:{email}">{email}</a></p>
<h2>문의할 때 적어 주시면 좋은 내용</h2>
<ul>
<li>오류 제보: 레시피 이름이나 주소, 잘못된 부분</li>
<li>사진·저작권 문의: 해당 쪽 주소와 권리 관계를 확인할 수 있는 내용</li>
<li>제휴·광고 문의: 회사(또는 서비스) 이름과 제안 내용</li>
</ul>
<p>답변에는 며칠이 걸릴 수 있어요. 건강 상태나 반려동물 진료에 대한 개별 상담은 제공하지 않으니 의사나 수의사와 상의해 주세요.</p>
"""),
        "en": ("Contact", "How to report recipe errors, request corrections or ask about partnerships.", """
<p>We welcome recipe error reports, correction requests, dish suggestions and partnership inquiries. Please email us.</p>
<h2>Email</h2>
<p><a href="mailto:{email}">{email}</a></p>
<h2>What to include</h2>
<ul>
<li>Errors: the recipe name or address and what is wrong</li>
<li>Photos and copyright: the page address and details of the rights involved</li>
<li>Partnerships and ads: your company or service name and proposal</li>
</ul>
<p>A reply may take a few days. We cannot give individual health or veterinary advice, so please consult a doctor or vet.</p>
"""),
    },
    "privacy": {
        "ko": ("개인정보처리방침", "냉장고 파먹기의 개인정보 처리와 광고·쿠키 사용을 안내합니다.", """
<p>냉장고 파먹기(이하 '사이트')는 회원 가입 없이 쓸 수 있고, 이름이나 연락처를 입력받지 않아요. 이 방침은 사이트를 이용할 때 처리될 수 있는 정보를 안내합니다.</p>
<h2>1. 처리하는 정보와 목적</h2>
<ul>
<li><b>문의 메일</b>: 이메일로 문의하면 보내신 주소와 내용을 답변 목적으로만 사용하고, 처리가 끝나면 지체 없이 삭제해요.</li>
<li><b>접속 기록</b>: 서버가 자동으로 남기는 IP 주소, 브라우저 종류, 접속 시각 등을 보안과 장애 대응 목적으로 사용해요.</li>
</ul>
<h2>2. 브라우저에만 저장되는 정보</h2>
<p>고른 재료, 언어, 식단 인원과 지역 설정은 이용자 기기의 브라우저 저장소(localStorage)에만 저장되고 서버로 보내지 않아요. 브라우저에서 사이트 데이터를 지우면 함께 삭제돼요.</p>
<h2>3. 광고와 쿠키</h2>
<ul>
<li>사이트는 Google 애드센스 광고를 게재할 수 있어요. Google을 포함한 제3자 공급업체는 쿠키를 사용해 이용자가 이 사이트나 다른 웹사이트를 방문한 기록을 바탕으로 광고를 게재해요.</li>
<li>Google은 광고 쿠키로 이용자와 파트너 사이트 방문 기록에 따라 광고를 보여 줄 수 있어요. 자세한 내용은 <a href="https://policies.google.com/technologies/partner-sites?hl=ko" target="_blank" rel="noopener">Google 파트너 사이트의 데이터 사용 방식</a>에서 볼 수 있어요.</li>
<li>맞춤 광고는 <a href="https://adssettings.google.com/" target="_blank" rel="noopener">Google 광고 설정</a>에서 끌 수 있고, <a href="https://www.aboutads.info/" target="_blank" rel="noopener">aboutads.info</a>에서 다른 공급업체의 쿠키도 거부할 수 있어요.</li>
<li>브라우저 설정에서 쿠키 저장을 거부할 수 있어요. 이 경우에도 사이트의 주요 기능은 쓸 수 있어요.</li>
</ul>
<h2>4. 외부 서비스</h2>
<ul>
<li><b>Google 애널리틱스</b>: 방문 수, 본 쪽, 유입 경로, 기기 종류 같은 통계를 쿠키로 수집해 사이트 개선에 써요. 이름 같은 개인을 알아보는 정보는 수집하지 않아요. <a href="https://tools.google.com/dlpage/gaoptout?hl=ko" target="_blank" rel="noopener">차단 부가기능</a>으로 거부할 수 있어요.</li>
<li><b>쿠팡 파트너스</b>: 구매 링크를 누르면 쿠팡으로 이동하며, 이후 정보 처리는 쿠팡의 방침을 따라요.</li>
<li><b>글꼴 전송(jsDelivr)</b>: 글꼴 파일을 받을 때 이용자의 IP 주소가 해당 서비스에 전달될 수 있어요.</li>
</ul>
<h2>5. 제3자 제공</h2>
<p>사이트는 이용자의 개인정보를 판매하거나 제3자에게 제공하지 않아요. 법령에 따른 요청이 있는 경우는 예외예요.</p>
<h2>6. 이용자의 권리와 문의</h2>
<p>보내신 문의 내용의 열람·정정·삭제를 요청할 수 있어요. 개인정보 관련 문의: <a href="mailto:{email}">{email}</a> (데일리픽스 포인트 운영자)</p>
<h2>7. 변경과 시행일</h2>
<p>내용이 바뀌면 이 쪽에 알려요. 시행일: {updated}</p>
"""),
        "en": ("Privacy Policy", "How Fridge Raid handles personal information, ads and cookies.", """
<p>Fridge Raid (the "site") can be used without an account and does not ask for your name or contact details. This policy explains what information may be processed when you use it.</p>
<h2>1. Information we process</h2>
<ul>
<li><b>Contact emails</b>: if you email us, your address and message are used only to reply and are deleted once handled.</li>
<li><b>Access logs</b>: servers automatically record IP address, browser type and access time, used for security and troubleshooting.</li>
</ul>
<h2>2. Stored only in your browser</h2>
<p>Your selected ingredients, language, and meal plan settings are kept in your browser's local storage and are not sent to our server. Clearing site data removes them.</p>
<h2>3. Ads and cookies</h2>
<ul>
<li>This site may show Google AdSense ads. Third-party vendors, including Google, use cookies to serve ads based on your prior visits to this site or other websites.</li>
<li>Google's use of advertising cookies enables it and its partners to serve ads based on those visits. See <a href="https://policies.google.com/technologies/partner-sites" target="_blank" rel="noopener">how Google uses data from partner sites</a>.</li>
<li>You can turn off personalized ads in <a href="https://adssettings.google.com/" target="_blank" rel="noopener">Google Ads Settings</a>, and opt out of other vendors' cookies at <a href="https://www.aboutads.info/" target="_blank" rel="noopener">aboutads.info</a>.</li>
<li>You can also block cookies in your browser. The main features of the site will still work.</li>
</ul>
<h2>4. External services</h2>
<ul>
<li><b>Google Analytics</b>: uses cookies to collect statistics such as visits, pages viewed, traffic sources and device type, which we use to improve the site. It does not collect your name or similar identifying details. You can opt out with the <a href="https://tools.google.com/dlpage/gaoptout" target="_blank" rel="noopener">browser add-on</a>.</li>
<li><b>Coupang Partners</b>: buy links take you to Coupang, whose own policy applies from then on.</li>
<li><b>Font delivery (jsDelivr)</b>: your IP address may reach this service when font files load.</li>
</ul>
<h2>5. Sharing with third parties</h2>
<p>We do not sell or share your personal information with third parties, except where required by law.</p>
<h2>6. Your rights and contact</h2>
<p>You can ask to view, correct or delete messages you sent us. Privacy contact: <a href="mailto:{email}">{email}</a> (operator of Daily Fix Point)</p>
<h2>7. Changes and effective date</h2>
<p>Changes will be posted on this page. Effective date: {updated}</p>
"""),
    },
}
