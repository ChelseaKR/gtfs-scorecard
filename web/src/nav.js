// @ts-check
/* Mobile menu toggle for the primary nav. On wide screens the nav cluster is
 * always visible and this does nothing; on narrow screens it opens/closes the
 * drop panel. The button carries aria-expanded; Escape and an outside click
 * close it. Keyboard users tab straight into the links when open. */
(function () {
  "use strict";
  var header = document.querySelector(".site-header");
  var btn = header && header.querySelector(".nav-menu-btn");
  if (!header || !(btn instanceof HTMLElement)) return;

  function isOpen() {
    return header.classList.contains("nav-open");
  }
  function close() {
    header.classList.remove("nav-open");
    btn.setAttribute("aria-expanded", "false");
  }
  function open() {
    header.classList.add("nav-open");
    btn.setAttribute("aria-expanded", "true");
  }

  btn.addEventListener("click", function () {
    isOpen() ? close() : open();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && isOpen()) {
      close();
      btn.focus();
    }
  });
  document.addEventListener("click", function (e) {
    if (isOpen() && e.target instanceof Node && !header.contains(e.target)) close();
  });
})();

/* Offline support (ideation EXP-20). nav.js is the one script every page
 * loads, so the service worker registers here, and the honesty half lives
 * here too: whenever the network is gone, a visible note says the page is a
 * saved copy, so cached data never masquerades as current. The note is a
 * polite live region, announced to screen readers without stealing focus. */
(function () {
  "use strict";
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {
      /* An uninstallable worker (old browser, private mode) just means no
         offline copies; the page itself works unchanged. */
    });
  }

  var note = null;
  function showOfflineNote() {
    if (note) return;
    note = document.createElement("div");
    note.className = "offline-note";
    note.setAttribute("role", "status");
    note.textContent =
      "You are offline. This is a saved copy of the page; " +
      "dates shown were current when it was saved.";
    document.body.insertBefore(note, document.body.firstChild);
  }
  function hideOfflineNote() {
    if (!note) return;
    note.remove();
    note = null;
  }

  window.addEventListener("offline", showOfflineNote);
  window.addEventListener("online", hideOfflineNote);
  if (navigator.onLine === false) showOfflineNote();
})();
