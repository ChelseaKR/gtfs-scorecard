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
  header.addEventListener("click", function (e) {
    if (isOpen() && e.target instanceof Element && e.target.closest("a")) close();
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
 * polite live region, announced to screen readers without stealing focus.
 * The worker also reports each saved data file it answers with, so the note
 * can name the date, and can stay after the network returns: the page keeps
 * showing that older data until it is reloaded. */
(function () {
  "use strict";
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {
      /* An uninstallable worker (old browser, private mode) just means no
         offline copies; the page itself works unchanged. */
    });
  }

  var note = null;
  var servedSavedData = false;
  var oldestSavedAt = null;
  var someSavedDateUnknown = false;

  function savedDay() {
    if (oldestSavedAt === null || someSavedDateUnknown) return null;
    return new Date(oldestSavedAt).toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }
  function setNote(text) {
    if (!note) {
      note = document.createElement("div");
      note.className = "offline-note";
      note.setAttribute("role", "status");
      document.body.insertBefore(note, document.body.firstChild);
    }
    if (note.textContent !== text) note.textContent = text;
  }
  function showOfflineNote() {
    var day = savedDay();
    setNote(
      day
        ? "You are offline. This is a saved copy of the page; its data was saved on " + day + "."
        : "You are offline. This is a saved copy of the page; " +
            "dates shown were current when it was saved."
    );
  }
  function hideOfflineNote() {
    if (servedSavedData) {
      var day = savedDay();
      setNote(
        "You are back online. This page still shows data saved " +
          (day ? "on " + day : "earlier") +
          ". Reload it for current data."
      );
      return;
    }
    if (!note) return;
    note.remove();
    note = null;
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", function (event) {
      if (!event.data || event.data.type !== "scorecard-saved-copy") return;
      servedSavedData = true;
      var savedAt = Date.parse(event.data.savedAt);
      if (isNaN(savedAt)) someSavedDateUnknown = true;
      else if (oldestSavedAt === null || savedAt < oldestSavedAt) oldestSavedAt = savedAt;
      showOfflineNote();
    });
  }

  window.addEventListener("offline", showOfflineNote);
  window.addEventListener("online", hideOfflineNote);
  if (navigator.onLine === false) showOfflineNote();
})();
