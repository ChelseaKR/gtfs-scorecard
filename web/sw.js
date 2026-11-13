// @ts-check
/* Offline support (ideation EXP-20): keep the shell and any page a person has
 * visited readable without a connection. A liaison's site visit and the café
 * demo share the same failure mode, weak signal; the honesty rule is that a
 * saved copy must never masquerade as current, so nav.js shows a visible
 * offline note whenever the network is gone.
 *
 * Strategy, deliberately conservative:
 * - Navigations are network first. A deploy is picked up immediately and the
 *   saved copy is served only when the network fails, so the worker can never
 *   pin a reader to an old build.
 * - JSON is network first for the same reason, and because the "checked" dates
 *   in the app come from it: a reader back after weeks away must see today's
 *   data, not last month's for one more load. The saved copy answers only when
 *   the network fails, and the page is told, so nav.js can name its date.
 * - Stylesheets and scripts are stale-while-revalidate: the saved copy renders
 *   at once and refreshes in the background.
 * - The full history index is never saved (173 MB in production, and no phone
 *   should hold that), and neither is any other JSON over the size cap.
 * - Only same-origin requests are considered; nothing cross-origin is touched.
 */
(function () {
  "use strict";
  var CACHE = "scorecard-offline-v3";
  var NEVER_SAVED_JSON = "/data/artifacts/index.json";
  // Above directory.json (8 MB in production), the largest file a page needs
  // offline.
  var MAX_SAVED_JSON_BYTES = 16 * 1024 * 1024;
  var SHELL = ["/src/styles.css", "/src/theme.js", "/src/nav.js"];
  var sw = /** @type {any} */ (self);

  sw.addEventListener("install", function (/** @type {any} */ event) {
    event.waitUntil(
      caches
        .open(CACHE)
        .then(function (cache) {
          return cache.addAll(SHELL);
        })
        .then(function () {
          return sw.skipWaiting();
        })
    );
  });

  sw.addEventListener("activate", function (/** @type {any} */ event) {
    event.waitUntil(
      caches
        .keys()
        .then(function (keys) {
          return Promise.all(
            keys
              .filter(function (key) {
                return key !== CACHE;
              })
              .map(function (key) {
                return caches.delete(key);
              })
          );
        })
        .then(function () {
          return sw.clients.claim();
        })
    );
  });

  function saveCopy(request, response) {
    // Only complete 200s: a 206 range response (the map's tile archive) is
    // not storable, and an error page must never shadow a good copy.
    if (response.status !== 200) return response;
    var copy = response.clone();
    caches.open(CACHE).then(function (cache) {
      cache.put(request, copy);
    });
    return response;
  }

  /* Beyond navigations, only the shell and the data a page reads offline are
   * worth saving: stylesheets and scripts under /src/, and JSON (see below).
   * Tiles and images stay network-only so the cache stays small on a phone. */
  function isShellAsset(pathname) {
    return pathname.indexOf("/src/") === 0;
  }

  function isJson(pathname) {
    return pathname.slice(-5) === ".json";
  }

  function isNeverSaved(pathname) {
    return pathname.slice(-NEVER_SAVED_JSON.length) === NEVER_SAVED_JSON;
  }

  /* Feed data, whose age a reader needs to know. Locale catalogs and map
   * outlines are JSON too, but their age says nothing about the data shown. */
  function isDatedData(pathname) {
    return pathname.indexOf("/data/") === 0 || pathname.indexOf("/api/") === 0;
  }

  /* Takes its own clone of a response, and measures the real size: production
   * serves large JSON gzipped with no Content-Length to go by. */
  function saveJsonCopy(request, response) {
    if (response.status !== 200) return undefined;
    if (Number(response.headers.get("Content-Length")) > MAX_SAVED_JSON_BYTES) return undefined;
    return response
      .clone()
      .blob()
      .then(function (body) {
        if (body.size > MAX_SAVED_JSON_BYTES) return undefined;
        var copy = new Response(body, {
          status: response.status,
          statusText: response.statusText,
          headers: response.headers,
        });
        return caches.open(CACHE).then(function (cache) {
          return cache.put(request, copy);
        });
      });
  }

  /* Tell the page it was given a saved copy. The response's own Date header is
   * when the server sent it, so it is when the copy was saved; it is passed as
   * is, and nav.js names no date when there is none. */
  function announceSavedCopy(clientId, saved) {
    return sw.clients.get(clientId).then(function (client) {
      if (client) {
        client.postMessage({ type: "scorecard-saved-copy", savedAt: saved.headers.get("Date") });
      }
    });
  }

  function networkFirstJson(event, pathname) {
    var request = event.request;
    var network = fetch(request);
    event.waitUntil(
      network
        .then(
          function (response) {
            return saveJsonCopy(request, response);
          },
          function (error) {
            // The page cancelled this one itself; nothing was served to it.
            if ((error && error.name === "AbortError") || !isDatedData(pathname)) return undefined;
            return caches.match(request).then(function (saved) {
              return saved ? announceSavedCopy(event.clientId, saved) : undefined;
            });
          }
        )
        .catch(function () {
          /* A full cache or a closed tab costs the offline copy, nothing more. */
        })
    );
    event.respondWith(
      network.catch(function () {
        return caches.match(request).then(function (saved) {
          return saved || Response.error();
        });
      })
    );
  }

  sw.addEventListener("fetch", function (/** @type {any} */ event) {
    var request = event.request;
    if (request.method !== "GET") return;
    var url = new URL(request.url);
    if (url.origin !== sw.location.origin) return;

    if (request.mode === "navigate") {
      event.respondWith(
        fetch(request)
          .then(function (response) {
            return saveCopy(request, response);
          })
          .catch(function () {
            return caches.match(request).then(function (saved) {
              return (
                saved ||
                new Response(
                  "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">" +
                    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">" +
                    "<title>Offline — GTFS Scorecard</title></head><body>" +
                    "<h1>You are offline</h1><p>This page has not been saved for " +
                    "offline reading yet. Pages you visit while online stay " +
                    "available without a connection.</p></body></html>",
                  { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } }
                )
              );
            });
          })
      );
      return;
    }

    if (isJson(url.pathname)) {
      if (!isNeverSaved(url.pathname)) networkFirstJson(event, url.pathname);
      return;
    }

    if (!isShellAsset(url.pathname)) return;
    event.respondWith(
      caches.match(request).then(function (saved) {
        var refresh = fetch(request)
          .then(function (response) {
            return saveCopy(request, response);
          })
          .catch(function () {
            return saved || Response.error();
          });
        return saved || refresh;
      })
    );
  });
})();
