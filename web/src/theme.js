// @ts-check
/**
 * 1.4.8 colour-selection mechanism. A small, persisted control that lets a
 * reader choose the page theme. Each theme re-points the CSS custom properties
 * (in styles.css and the landing page's inline tokens) via a data-theme
 * attribute on <html>, and every theme clears WCAG AAA contrast
 * (verified by pipeline/scripts/check_contrast.py).
 *
 * No build step, no framework: this script runs on the landing page, the SPA,
 * the standalone HTML pages, and the prerendered pages from render_site.py.
 * It mounts an accessible menu into #theme-control if that element exists, and
 * otherwise appends its own host to the footer so every page gets the control.
 */
(function () {
  "use strict";

  var THEME_KEY = "scorecard-theme";
  /** Order matters: it drives the cycle and the menu. "system" follows the OS. */
  var THEMES = [
    { id: "system", label: "System" },
    { id: "light", label: "Light" },
    { id: "contrast", label: "High contrast" },
    { id: "dark", label: "Dark" },
  ];
  var IDS = THEMES.map(function (t) {
    return t.id;
  });

  /** @returns {string} the saved theme id, or "system" when none/invalid. */
  function saved() {
    try {
      var v = localStorage.getItem(THEME_KEY);
      return v && IDS.indexOf(v) >= 0 ? v : "system";
    } catch (e) {
      return "system";
    }
  }

  /** Apply a theme id to <html>. "system" clears the attribute so the
   *  prefers-color-scheme media query in CSS takes over. @param {string} id */
  function apply(id) {
    var root = document.documentElement;
    if (id === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", id);
  }

  /** Persist and apply a theme id. @param {string} id */
  function set(id) {
    if (IDS.indexOf(id) < 0) id = "system";
    try {
      if (id === "system") localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, id);
    } catch (e) {
      /* storage disabled: the choice just won't persist */
    }
    apply(id);
  }

  function labelFor(id) {
    for (var i = 0; i < THEMES.length; i++) if (THEMES[i].id === id) return THEMES[i].label;
    return "System";
  }

  // Apply the saved theme as early as this script runs (the landing page also
  // applies it inline in <head> to avoid a flash).
  apply(saved());

  /** Build the labelled menu control and wire it up. @param {HTMLElement} host */
  function mount(host) {
    host.classList.add("theme-control");
    var current = saved();

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "theme-toggle";
    btn.setAttribute("aria-haspopup", "menu");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-controls", "theme-menu");
    btn.id = "theme-toggle-btn";
    btn.innerHTML =
      '<span aria-hidden="true">&#9681;</span> ' +
      '<span class="theme-toggle-label">Theme: ' +
      labelFor(current) +
      "</span>";

    var menu = document.createElement("div");
    menu.id = "theme-menu";
    menu.className = "theme-menu";
    menu.setAttribute("role", "menu");
    menu.setAttribute("aria-label", "Choose a colour theme");
    menu.hidden = true;

    THEMES.forEach(function (t) {
      var item = document.createElement("button");
      item.type = "button";
      item.className = "theme-item";
      item.setAttribute("role", "menuitemradio");
      item.setAttribute("aria-checked", String(t.id === current));
      item.tabIndex = -1;
      item.dataset.theme = t.id;
      item.textContent = t.label;
      menu.appendChild(item);
    });

    host.appendChild(btn);
    host.appendChild(menu);

    function closeMenu() {
      menu.hidden = true;
      btn.setAttribute("aria-expanded", "false");
    }
    /** @param {"selected" | "first" | "last"} [focusTarget] */
    function openMenu(focusTarget) {
      menu.hidden = false;
      btn.setAttribute("aria-expanded", "true");
      var items = Array.prototype.slice.call(menu.querySelectorAll(".theme-item"));
      var target = null;
      if (focusTarget === "first") target = items[0];
      else if (focusTarget === "last") target = items[items.length - 1];
      else target = menu.querySelector('[aria-checked="true"]') || items[0];
      if (target instanceof HTMLElement) target.focus();
    }

    btn.addEventListener("click", function () {
      if (menu.hidden) openMenu();
      else closeMenu();
    });

    menu.addEventListener("click", function (e) {
      var target = e.target;
      if (!(target instanceof HTMLElement)) return;
      var item = target.closest(".theme-item");
      if (!(item instanceof HTMLElement) || !item.dataset.theme) return;
      var id = item.dataset.theme;
      set(id);
      for (var i = 0; i < menu.children.length; i++) {
        var c = menu.children[i];
        c.setAttribute("aria-checked", String(c.dataset.theme === id));
      }
      var lbl = btn.querySelector(".theme-toggle-label");
      if (lbl) lbl.textContent = "Theme: " + labelFor(id);
      closeMenu();
      btn.focus();
    });

    // Follow the ARIA menu-button pattern: arrows can open the menu, arrows
    // wrap between choices, Home/End jump, and Escape returns focus to the
    // trigger. Native button handling keeps Enter/Space selection intact.
    host.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !menu.hidden) {
        e.preventDefault();
        // The mobile navigation also listens for Escape on document. Keep this
        // Escape scoped to the theme menu so it cannot steal restored focus.
        e.stopPropagation();
        closeMenu();
        btn.focus();
        return;
      }
      if (menu.hidden && e.target === btn && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
        e.preventDefault();
        openMenu(e.key === "ArrowUp" ? "last" : "first");
        return;
      }
      if (menu.hidden) return;
      var items = Array.prototype.slice.call(menu.querySelectorAll(".theme-item"));
      var idx = items.indexOf(document.activeElement);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        var next = e.key === "ArrowDown" ? idx + 1 : idx - 1;
        if (next < 0) next = items.length - 1;
        if (next >= items.length) next = 0;
        if (items[next]) items[next].focus();
      } else if (e.key === "Home" || e.key === "End") {
        e.preventDefault();
        var edge = e.key === "Home" ? items[0] : items[items.length - 1];
        if (edge) edge.focus();
      } else if (e.key === "Tab") {
        // Let the browser advance normally, but do not leave a visually open
        // menu behind once focus moves to the next control.
        closeMenu();
      }
    });

    document.addEventListener("click", function (e) {
      if (!host.contains(/** @type {Node} */ (e.target))) closeMenu();
    });
  }

  function init() {
    var host = document.getElementById("theme-control");
    if (!host) {
      // No reserved slot: append our own to the first footer so every page,
      // including the standalone ones, still gets the control.
      var footer = document.querySelector("footer .wrap, .site-footer .wrap, footer");
      if (!footer) return;
      host = document.createElement("p");
      host.id = "theme-control";
      host.className = "theme-control-footer";
      footer.appendChild(host);
    }
    mount(/** @type {HTMLElement} */ (host));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
