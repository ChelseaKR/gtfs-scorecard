/* Find-as-you-type agency picker, shared by the home page search and the
 * alerts signup form.
 *
 * Data: /data/agency-index.json, a small index the site render writes from the
 * published catalog (pipeline/src/scorecard_pipeline/agency_index.py): one
 * [id, name, slug, place] row per agency with a scorecard page. It is fetched
 * once per page, the first time a picker needs it; the HTTP cache of the
 * browser and the service worker keep it from there. Neither picker reads the
 * full history index (data/artifacts/index.json) any more.
 *
 * Markup: the page supplies a native text input and an empty list, so without
 * JavaScript the field is still an ordinary labeled text box. attach() turns
 * them into the WAI-ARIA 1.2 combobox pattern: the input keeps focus and
 * carries role="combobox", aria-expanded, aria-controls and
 * aria-activedescendant; the list becomes role="listbox" with role="option"
 * rows. Up and Down move through the suggestions, Enter chooses the active
 * one, Escape closes the list, and a polite live region says how many
 * suggestions there are.
 *
 * Words: every sentence a reader sees or hears comes from data-* attributes on
 * the page (see messagesFrom), so this file holds no English copy of its own
 * and the wording is reviewed where the rest of the copy on each page is.
 *
 * Loaded as a classic deferred script ahead of the script of each page; it
 * defines globalThis.ScorecardAgencySearch and nothing else.
 */
(function (root) {
  "use strict";

  var INDEX_URL = "/data/agency-index.json";
  var DEFAULT_LIMIT = 8;
  var DEFAULT_MIN_CHARS = 2;
  var DEBOUNCE_MS = 100;

  /* Same collation as compareText in locale.js (this classic script cannot
   * import that module): the language of the page, base sensitivity, numeric. */
  var pageLang =
    (typeof document !== "undefined" && document.documentElement && document.documentElement.lang) || "en";
  var collator =
    typeof Intl === "object" && typeof Intl.Collator === "function"
      ? new Intl.Collator(pageLang, { sensitivity: "base", numeric: true })
      : null;

  function compareNames(left, right) {
    if (collator) return collator.compare(left, right);
    return left < right ? -1 : left > right ? 1 : 0;
  }

  /* Fold text for matching: no case, no accents, apostrophes dropped (any of
   * the apostrophe characters agency names use), an ampersand read as the
   * word and, and every other run of punctuation or space collapsed to one
   * space. Saint Marys, typed with or without its modifier-letter apostrophe
   * and in any case, folds to one key. The tests in
   * pipeline/tests/test_agency_index.py pin the exact results. */
  function fold(text) {
    var value = String(text == null ? "" : text);
    if (typeof value.normalize === "function") value = value.normalize("NFKD");
    return value
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/[\u0027\u2018\u2019\u02bc\u0060\u00b4]/g, "")
      .replace(/[^\p{L}\p{N}]+/gu, " ")
      .trim();
  }

  /* The folded text with no spaces at all, so B.C. Transit (folded to
   * b c transit) and BC Transit (bc transit) still meet. */
  function squash(folded) {
    return folded.replace(/ /g, "");
  }

  /* Turn the published payload into records ready to match. Accepts the
   * compact rows of the index and, defensively, plain {id, name} objects. */
  function prepare(payload) {
    if (!payload || !Array.isArray(payload.agencies)) return [];
    var fields = Array.isArray(payload.fields) ? payload.fields : ["id", "name", "slug", "place"];
    var at = {
      id: fields.indexOf("id"),
      name: fields.indexOf("name"),
      slug: fields.indexOf("slug"),
      place: fields.indexOf("place"),
    };
    var records = [];
    payload.agencies.forEach(function (row) {
      var raw = Array.isArray(row)
        ? {
            id: row[at.id],
            name: row[at.name],
            slug: at.slug >= 0 ? row[at.slug] : "",
            place: at.place >= 0 ? row[at.place] : "",
          }
        : row || {};
      var id = typeof raw.id === "string" ? raw.id : "";
      var name = typeof raw.name === "string" ? raw.name : "";
      if (!/^[a-z0-9][a-z0-9_-]*$/.test(id) || !name.trim()) return;
      var key = fold(name);
      var abbreviations = [];
      var abbreviation = /\(([^)]*)\)/g;
      var found;
      while ((found = abbreviation.exec(name))) {
        var folded = fold(found[1]);
        if (folded) abbreviations.push(folded);
      }
      records.push({
        id: id,
        name: name,
        slug: typeof raw.slug === "string" && raw.slug ? raw.slug : id,
        place: typeof raw.place === "string" ? raw.place : "",
        key: key,
        squashed: squash(key),
        main: fold(name.replace(/\([^)]*\)/g, " ")),
        words: key.split(" "),
        abbreviations: abbreviations,
        squashedAbbreviations: abbreviations.map(squash),
        idKey: fold(id),
      });
    });
    return records;
  }

  function startsWithAny(list, prefix) {
    for (var i = 0; i < list.length; i += 1) {
      if (list[i].indexOf(prefix) === 0) return true;
    }
    return false;
  }

  /* How well one record answers a folded query; lower is better, -1 is no
   * match at all.
   *   0  the whole name, or the feed id, exactly
   *   1  the name without its parenthetical, or one of its abbreviations
   *   2  the name starts with the query
   *   3  a word or an abbreviation starts with the query
   *   4  every query word starts some word of the name, in any order
   *   5  the query appears anywhere in the name
   *   6  the query appears anywhere in the feed id */
  function tier(record, query, squashedQuery, tokens) {
    if (query === record.key || query === record.idKey || squashedQuery === record.squashed) return 0;
    if (query === record.main || record.squashedAbbreviations.indexOf(squashedQuery) >= 0) return 1;
    if (record.key.indexOf(query) === 0) return 2;
    if (startsWithAny(record.words, query) || startsWithAny(record.abbreviations, query)) return 3;
    if (
      tokens.length > 1 &&
      tokens.every(function (token) {
        return startsWithAny(record.words, token);
      })
    ) {
      return 4;
    }
    if (record.key.indexOf(query) >= 0 || record.squashed.indexOf(squashedQuery) >= 0) return 5;
    if (record.idKey.indexOf(query) >= 0) return 6;
    return -1;
  }

  /* Ranked matches for a query: {matches: the best `limit`, total: how many
   * matched at all}. Ties go alphabetically by name, then by id. */
  function rank(records, query, limit) {
    var folded = fold(query);
    if (!folded) return { matches: [], total: 0 };
    var squashedQuery = squash(folded);
    var tokens = folded.split(" ");
    var scored = [];
    records.forEach(function (record) {
      var value = tier(record, folded, squashedQuery, tokens);
      if (value >= 0) scored.push({ record: record, tier: value });
    });
    scored.sort(function (left, right) {
      return (
        left.tier - right.tier ||
        compareNames(left.record.name, right.record.name) ||
        compareNames(left.record.id, right.record.id)
      );
    });
    return {
      matches: scored.slice(0, typeof limit === "number" ? limit : DEFAULT_LIMIT).map(function (item) {
        return item.record;
      }),
      total: scored.length,
    };
  }

  /* The one agency a query clearly names, or null when it names none or more
   * than one. Clear means: the only record whose full name, name without the
   * parenthetical, abbreviation or feed id equals the query, or else the only
   * record that matches at all. Two feeds that share a name are never a clear
   * match, so that query goes to the results page instead of guessing. */
  function clearMatch(records, query) {
    var folded = fold(query);
    if (!folded) return null;
    var squashedQuery = squash(folded);
    var tokens = folded.split(" ");
    var exact = [];
    var near = [];
    var any = [];
    records.forEach(function (record) {
      var value = tier(record, folded, squashedQuery, tokens);
      if (value === 0) exact.push(record);
      if (value === 0 || value === 1) near.push(record);
      if (value >= 0 && any.length < 2) any.push(record);
    });
    if (exact.length === 1) return exact[0];
    if (exact.length > 1) return null;
    if (near.length === 1) return near[0];
    if (near.length > 1) return null;
    return any.length === 1 ? any[0] : null;
  }

  var loading = null;

  /* Fetch and prepare the index once per page. A failed fetch is forgotten so
   * the next keystroke can try again. */
  function loadIndex(url) {
    if (loading) return loading;
    loading = fetch(url || INDEX_URL, { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) throw new Error("agency-index:" + response.status);
        return response.json();
      })
      .then(function (payload) {
        var records = prepare(payload);
        if (!records.length) throw new Error("agency-index:empty");
        return records;
      })
      .catch(function (error) {
        loading = null;
        throw error;
      });
    return loading;
  }

  function fill(template, values) {
    return String(template || "").replace(/\{(\w+)\}/g, function (whole, name) {
      return Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : whole;
    });
  }

  /* Read the wording of a picker from data-* attributes on the element:
   *   data-msg-short    fewer than the minimum characters typed
   *   data-msg-loading  the index is still on its way
   *   data-msg-none     nothing matches
   *   data-msg-one      exactly one suggestion ({count} is filled in)
   *   data-msg-many     several suggestions ({count}, {total})
   *   data-msg-more     several suggestions, more than shown ({count}, {total})
   *   data-msg-closed   the list was closed with Escape
   *   data-msg-error    the index could not load
   *   data-msg-detail   the second line of an option ({id})
   *   data-msg-all      the label of an every-agency option, if the picker offers one */
  function messagesFrom(element) {
    var data = (element && element.dataset) || {};
    return {
      short: data.msgShort || "",
      loading: data.msgLoading || "",
      none: data.msgNone || "",
      one: data.msgOne || "",
      many: data.msgMany || "",
      more: data.msgMore || data.msgMany || "",
      closed: data.msgClosed || "",
      error: data.msgError || "",
      detail: data.msgDetail || "{id}",
      all: data.msgAll || "",
    };
  }

  /* Turn a text input and an empty list into a combobox.
   * options:
   *   input, listbox      the elements (required)
   *   status              a live region for counts and errors (optional)
   *   messages            from messagesFrom()
   *   offerAll            true to offer an every-agency option first
   *   limit, minChars     suggestion count and the shortest query searched
   *   indexUrl            override the index location (tests)
   *   onChoose(choice)    called with a record, or {all: true}
   *   onClear()           called when typing undoes an earlier choice
   * Returns a small controller: {close, choose, choice, records, clearMatch}. */
  function attach(options) {
    var input = options.input;
    var listbox = options.listbox;
    var status = options.status || null;
    var messages = options.messages || messagesFrom(null);
    var limit = options.limit || DEFAULT_LIMIT;
    var minChars = options.minChars || DEFAULT_MIN_CHARS;
    var offerAll = Boolean(options.offerAll && messages.all);
    var idleMessage = status ? status.textContent : "";
    var shown = [];
    var active = -1;
    var timer = 0;
    var generation = 0;
    var choice = null;
    var listId = listbox.id || input.id + "-listbox";
    listbox.id = listId;

    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", listId);
    input.setAttribute("autocomplete", "off");
    input.setAttribute("autocapitalize", "off");
    input.setAttribute("spellcheck", "false");
    listbox.setAttribute("role", "listbox");
    if (!listbox.hasAttribute("aria-label") && !listbox.hasAttribute("aria-labelledby") && input.labels && input.labels[0]) {
      if (!input.labels[0].id) input.labels[0].id = input.id + "-label";
      listbox.setAttribute("aria-labelledby", input.labels[0].id);
    }
    listbox.hidden = true;

    function say(message) {
      if (status) status.textContent = message;
    }

    function records() {
      return loadIndex(options.indexUrl);
    }

    function setActive(index) {
      var rows = listbox.querySelectorAll('[role="option"]');
      active = rows.length ? (index + rows.length) % rows.length : -1;
      for (var i = 0; i < rows.length; i += 1) {
        var on = i === active;
        rows[i].setAttribute("aria-selected", on ? "true" : "false");
        rows[i].classList.toggle("is-active", on);
      }
      if (active >= 0) {
        input.setAttribute("aria-activedescendant", rows[active].id);
        if (typeof rows[active].scrollIntoView === "function") rows[active].scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function close() {
      window.clearTimeout(timer);
      timer = 0;
      generation += 1;
      shown = [];
      active = -1;
      listbox.hidden = true;
      listbox.replaceChildren();
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }

    function optionFor(item, index) {
      var row = document.createElement("li");
      row.id = listId + "-option-" + index;
      row.setAttribute("role", "option");
      row.setAttribute("aria-selected", "false");
      row.className = "agency-option";
      var name = document.createElement("span");
      name.className = "agency-option-name";
      if (item.all) {
        name.textContent = messages.all;
        row.classList.add("agency-option-all");
        row.appendChild(name);
        return row;
      }
      var label = document.createElement("bdi");
      label.textContent = item.name;
      name.appendChild(label);
      var detail = document.createElement("span");
      detail.className = "agency-option-detail";
      if (item.place) {
        var place = document.createElement("span");
        place.textContent = item.place;
        var dot = document.createElement("span");
        dot.setAttribute("aria-hidden", "true");
        dot.textContent = " \u00b7 ";
        detail.append(place, dot);
      }
      detail.append(fill(messages.detail, { id: item.id }));
      row.append(name, detail);
      return row;
    }

    function show(items, total, announce) {
      shown = items;
      listbox.replaceChildren();
      items.forEach(function (item, index) {
        listbox.appendChild(optionFor(item, index));
      });
      active = -1;
      input.removeAttribute("aria-activedescendant");
      var open = items.length > 0;
      listbox.hidden = !open;
      input.setAttribute("aria-expanded", open ? "true" : "false");
      if (!announce) return;
      // Counts are agencies: the every-agency option is not one of them.
      var count = items.filter(function (item) {
        return !item.all;
      }).length;
      if (!count && open) say(idleMessage);
      else if (!count) say(messages.none);
      else if (count === 1) say(fill(messages.one, { count: 1, total: total }));
      else say(fill(total > count ? messages.more : messages.many, { count: count, total: total }));
    }

    function allMatches(query) {
      if (!offerAll) return false;
      var folded = fold(query);
      if (!folded) return true;
      var label = fold(messages.all);
      return label.indexOf(folded) === 0 || label.split(" ").indexOf(folded) >= 0;
    }

    /* Search and show suggestions for the current text. `explicit` is true
     * when the reader asked for the list (Down arrow) rather than typed. */
    function update(explicit) {
      // A Down press can arrive while a keystroke is still waiting out the
      // debounce; this search replaces that one rather than racing it.
      window.clearTimeout(timer);
      timer = 0;
      var query = input.value;
      var folded = fold(query);
      generation += 1;
      var mine = generation;
      if (folded.length < minChars) {
        if (explicit && offerAll && allMatches(query)) {
          // Only the every-agency option: no count to announce, since the
          // option itself is read as it becomes active.
          show([{ all: true }], 1, false);
          say(idleMessage);
          return Promise.resolve();
        }
        close();
        say(query.trim() ? messages.short : idleMessage);
        return Promise.resolve();
      }
      say(messages.loading);
      return records().then(
        function (list) {
          if (mine !== generation) return;
          var result = rank(list, query, limit);
          var items = result.matches.slice();
          var total = result.total;
          if (allMatches(query)) {
            items.unshift({ all: true });
            if (items.length > limit) items.pop();
          }
          show(items, total, true);
        },
        function () {
          if (mine !== generation) return;
          close();
          say(messages.error);
        }
      );
    }

    function choose(item) {
      if (!item) return;
      choice = item.all ? { all: true } : item;
      input.value = item.all ? messages.all : item.name;
      close();
      say(idleMessage);
      if (typeof options.onChoose === "function") options.onChoose(choice);
    }

    input.addEventListener("input", function () {
      if (choice) {
        choice = null;
        if (typeof options.onClear === "function") options.onClear();
      }
      window.clearTimeout(timer);
      generation += 1;
      timer = window.setTimeout(function () {
        timer = 0;
        update(false);
      }, DEBOUNCE_MS);
    });

    input.addEventListener("keydown", function (event) {
      // A list still showing while new typing waits out the debounce is stale:
      // keys act on the text as it is now, not on the old suggestions.
      var open = !listbox.hidden && shown.length > 0 && !timer;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (!open) {
          update(true).then(function () {
            if (!event.altKey && shown.length) setActive(0);
          });
        } else if (!event.altKey) {
          setActive(active + 1);
        }
      } else if (event.key === "ArrowUp") {
        if (!open) return;
        event.preventDefault();
        setActive(active < 0 ? shown.length - 1 : active - 1);
      } else if (event.key === "Enter") {
        if (open && active >= 0) {
          event.preventDefault();
          choose(shown[active]);
        }
      } else if (event.key === "Escape") {
        if (open || timer) {
          event.preventDefault();
          close();
          say(messages.closed || idleMessage);
        }
      } else if (event.key === "Tab") {
        close();
      }
    });

    /* Keep focus in the input while a pointer picks an option. */
    listbox.addEventListener("mousedown", function (event) {
      event.preventDefault();
    });
    listbox.addEventListener("click", function (event) {
      var row = event.target instanceof Element ? event.target.closest('[role="option"]') : null;
      if (!row) return;
      var index = Array.prototype.indexOf.call(listbox.children, row);
      if (index >= 0) choose(shown[index]);
    });

    input.addEventListener("blur", function () {
      close();
    });

    return {
      close: close,
      choose: choose,
      choice: function () {
        return choice;
      },
      records: records,
      /* The agency the current text clearly names, once the index is loaded. */
      clearMatch: function () {
        return records().then(function (list) {
          return clearMatch(list, input.value);
        });
      },
      allMatches: function () {
        return offerAll && fold(input.value) === fold(messages.all);
      },
    };
  }

  root.ScorecardAgencySearch = {
    INDEX_URL: INDEX_URL,
    fold: fold,
    prepare: prepare,
    rank: rank,
    clearMatch: clearMatch,
    loadIndex: loadIndex,
    messagesFrom: messagesFrom,
    attach: attach,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
