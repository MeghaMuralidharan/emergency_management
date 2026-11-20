document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".message").forEach((el) => {
    setTimeout(() => { el.classList.add("fade-out"); }, 4200);
  });
});

/* Live search for directory pages: filters as you type, no button press needed. */
(function () {
  var form = document.querySelector(".dir-search");
  var results = document.getElementById("dir-results");
  if (!form || !results || !window.fetch) return;
  var input = form.querySelector("input[name=q]");
  var clear = form.querySelector(".dir-clear");
  var timer = null, seq = 0;

  function run() {
    var mine = ++seq;
    var url = location.pathname + "?" + new URLSearchParams(new FormData(form)).toString();
    fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        if (mine !== seq) return; // a newer search already started
        var doc = new DOMParser().parseFromString(html, "text/html");
        var fresh = doc.getElementById("dir-results");
        if (fresh) results.innerHTML = fresh.innerHTML;
        var toggle = doc.querySelector(".view-toggle"), cur = document.querySelector(".view-toggle");
        if (toggle && cur) cur.innerHTML = toggle.innerHTML;
        history.replaceState(null, "", url);
      })
      .catch(function () { form.submit(); }); // fall back to a normal page load
  }

  var selects = form.querySelectorAll("select");
  function syncClear() {
    var any = !!(input && input.value);
    selects.forEach(function (s) { if (s.value) any = true; });
    if (clear) clear.hidden = !any;
  }
  selects.forEach(function (s) { s.addEventListener("change", function () { syncClear(); clearTimeout(timer); run(); }); });
  if (input) input.addEventListener("input", function () {
    syncClear();
    clearTimeout(timer);
    timer = setTimeout(run, 250);
  });
  form.addEventListener("submit", function (e) { e.preventDefault(); clearTimeout(timer); run(); });
  if (clear) clear.addEventListener("click", function (e) {
    e.preventDefault(); if (input) { input.value = ""; input.focus(); } selects.forEach(function (s) { s.value = ""; }); clear.hidden = true; run();
  });
})();

/* Expand / shrink the admin sidebar. The choice is remembered, except on the
   "view as" preview pages, which always open shrunk to leave room for the preview. */
(function () {
  var shell = document.querySelector(".app-shell");
  var btn = document.querySelector(".side-toggle");
  if (!shell || !btn) return;
  var preview = shell.hasAttribute("data-preview");
  var KEY = "sidebarCollapsed", stored = null;
  try { stored = localStorage.getItem(KEY); } catch (e) {}
  var collapsed = preview ? true : stored === "1";
  function apply() {
    shell.classList.toggle("collapsed", collapsed);
    btn.setAttribute("aria-expanded", String(!collapsed));
    btn.title = collapsed ? "Expand menu" : "Shrink menu";
    btn.querySelector(".tg-icon").textContent = collapsed ? "\u203A" : "\u2039";
    btn.querySelector(".tg-label").textContent = collapsed ? "Expand menu" : "Shrink menu";
  }
  apply();
  btn.addEventListener("click", function () {
    collapsed = !collapsed;
    apply();
    if (!preview) { try { localStorage.setItem(KEY, collapsed ? "1" : "0"); } catch (e) {} }
  });
})();

/* Add ward / room form: suggest how many beds the chosen type usually has. */
(function () {
  var cat = document.querySelector('select[name="category"]');
  var cap = document.querySelector('input[name="capacity"]');
  if (!cat || !cap) return;
  var D = { "ICU": 1, "Shared ICU": 4, "Ward": 10, "Room": 2, "Personal Room": 1, "VIP Room": 1, "Emergency": 6 };
  var touched = !!cap.value;
  cap.addEventListener("input", function () { touched = true; });
  cat.addEventListener("change", function () { if (!touched && D[cat.value]) cap.value = D[cat.value]; });
})();
