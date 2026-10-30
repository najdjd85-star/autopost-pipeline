/* 냉장고 파먹기: 화면(html)·데이터(json)는 열 때마다 서버에 '바뀌었나?'를 먼저 확인한다.
   서버가 html 을 1년 캐시로 내려 줘도(Cloudways 기본값) 쪽마다 새로고침하지 않아도 항상 최신이 보이게 한다.
   바뀌지 않았으면 서버가 304 로 답해서 거의 느려지지 않는다. 파일 주소에 해시가 붙은 css/js, 이미지는 그대로 캐시를 쓴다. */
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") { return; }
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) { return; }
  var page = req.mode === "navigate" || /\.(html|json|xml|txt)$/.test(url.pathname) || /\/$/.test(url.pathname);
  if (!page) { return; }
  e.respondWith(
    fetch(req, { cache: "no-cache" }).catch(function () { return fetch(req); })
  );
});
