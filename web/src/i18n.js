// @ts-check
/**
 * Runtime string catalog for the interactive app.
 *
 * The English strings are generated into ./generated/strings.js from the
 * reviewed catalog (pipeline/src/scorecard_pipeline/locales/app.en.json), so
 * production pages render synchronously with no extra fetch. The only other
 * loadable catalog is the derived en-XA pseudolocale, behind an explicit
 * ?l10n=en-XA request, used to check that layouts survive longer strings.
 * A production language still requires a named language steward; any failure
 * here falls back to English rather than showing a partial locale.
 */
import { STRINGS } from "./generated/strings.js";

const PSEUDOLOCALE = "en-XA";

/** @type {Record<string, string>} */
let active = STRINGS;

/** The locale-preview tag requested for this page view, or "". */
export function localePreviewTag() {
  try {
    return new URLSearchParams(location.search).get("l10n") === PSEUDOLOCALE ? PSEUDOLOCALE : "";
  } catch {
    return "";
  }
}

/** Load the requested preview catalog before first render. No-op in
 *  production; fails closed to English on any error. */
export async function initStrings() {
  const tag = localePreviewTag();
  if (!tag) return;
  try {
    // Relative to /app/, this resolves to the published /locales/ directory
    // both on the deployed site and when web/ is served as the docroot.
    const resp = await fetch(`../locales/app.${tag}.json`);
    if (!resp.ok) return;
    const data = await resp.json();
    if (data && typeof data === "object") {
      active = { ...STRINGS, .../** @type {Record<string, string>} */ (data) };
      document.documentElement.lang = tag;
    }
  } catch {
    /* fail closed: the page stays English */
  }
}

/** A catalog string with {name} placeholders filled in. An unknown key
 *  returns the key itself so a missing entry is visible, not blank.
 *  @param {string} key @param {Record<string, string | number>} [params] */
export function t(key, params) {
  const template = Object.prototype.hasOwnProperty.call(active, key) ? active[key] : STRINGS[key];
  if (typeof template !== "string") return key;
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    params && Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match
  );
}
