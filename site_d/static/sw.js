/* 냉장고 파먹기: 열어 본 화면(html)·데이터(json)를 폰에 저장해 두고 바로 보여 준다(빠름).
   사이트가 새로 반영되면 /version.json 이 바뀌어서, 저장해 둔 화면을 지우고 새로 받는다(쪽마다 새로고침할 필요 없음).
   서버가 html 을 1년 캐시로 내려 줘도(Cloudways 기본값) 새 버전이 늦게 보이지 않도록 하는 장치이기도 하다.
   버전 확인은 2분에 한 번만, 최대 0.8초만 기다린다. 파일 주소에 해시가 붙은 css/js, 이미지는 브라우저 캐시를 그대로 쓴다. */
var PAGES = "fridge-pages", META = "fridge-meta";
var CHECK_MS = 120000, CHECK_WAIT = 800;

self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });

function keyOf(url) { var u = new URL(url); return u.origin + u.pathname; }   // ?utm_… 같은 꼬리표는 무시한다

function metaGet() {
  return caches.open(META).then(function (c) { return c.match("/__meta"); }).then(function (r) { return r ? r.json() : { v: "", t: 0 }; }).catch(function () { return { v: "", t: 0 }; });
}
function metaPut(m) {
  return caches.open(META).then(function (c) { return c.put("/__meta", new Response(JSON.stringify(m))); }).catch(function () {});
}

// 마지막 확인 후 2분이 지났을 때만 서버의 새 버전 번호를 본다. 달라졌으면 저장해 둔 화면을 모두 지운다.
function ensureFresh() {
  return metaGet().then(function (m) {
    if (Date.now() - m.t < CHECK_MS) { return; }
    var ctl = new AbortController();
    var timer = setTimeout(function () { ctl.abort(); }, CHECK_WAIT);
    return fetch("/version.json", { cache: "no-store", signal: ctl.signal })
      .then(function (r) { clearTimeout(timer); return r.json(); })
      .then(function (j) {
        var wipe = m.v && m.v !== j.v ? caches.delete(PAGES) : Promise.resolve();
        return wipe.then(function () { return metaPut({ v: j.v, t: Date.now() }); });
      })
      .catch(function () { clearTimeout(timer); });   // 느리거나 오프라인이면 저장해 둔 것을 그대로 쓴다
  });
}

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") { return; }
  var url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname === "/version.json") { return; }
  var page = req.mode === "navigate" || /\.(html|json|xml|txt)$/.test(url.pathname) || /\/$/.test(url.pathname);
  if (!page) { return; }
  e.respondWith(
    ensureFresh().then(function () { return caches.open(PAGES); }).then(function (cache) {
      var k = keyOf(req.url);
      return cache.match(k).then(function (hit) {
        if (hit) { return hit; }
        return fetch(req, { cache: "no-cache" }).then(function (res) {
          if (res && res.ok && res.type === "basic") { cache.put(k, res.clone()); }
          return res;
        });
      });
    }).catch(function () { return fetch(req); })
  );
});
