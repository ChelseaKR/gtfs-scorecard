// @ts-check
/** Locale-aware presentation primitives shared by the no-build frontend. */

const FALLBACK_LOCALE = "en";
const RTL_LANGUAGES = new Set(["ar", "ckb", "dv", "fa", "he", "ps", "sd", "ur"]);
/** @type {Map<string, Intl.DateTimeFormat>} */
const DATE_FORMATTERS = new Map();
/** @type {Map<string, Intl.NumberFormat>} */
const NUMBER_FORMATTERS = new Map();
/** @type {Map<string, Intl.Collator>} */
const COLLATORS = new Map();

/** Return a valid BCP 47 locale, preferring the language declared by the page. */
export function pageLocale() {
  const declared = document.documentElement.lang.trim();
  const candidate = declared || navigator.languages?.[0] || navigator.language || FALLBACK_LOCALE;
  try {
    return new Intl.Locale(candidate).toString();
  } catch {
    return FALLBACK_LOCALE;
  }
}

/** @param {string} locale @returns {"ltr"|"rtl"} */
export function localeDirection(locale) {
  try {
    const parsed = new Intl.Locale(locale);
    const direction = /** @type {any} */ (parsed).textInfo?.direction;
    if (direction === "ltr" || direction === "rtl") return direction;
    return RTL_LANGUAGES.has(parsed.language) ? "rtl" : "ltr";
  } catch {
    return "ltr";
  }
}

/** Keep the root direction aligned with its declared language. */
export function applyDocumentDirection() {
  document.documentElement.dir = localeDirection(pageLocale());
}

/** @param {string} iso @param {string} [locale] @returns {string} */
export function formatDate(iso, locale = pageLocale()) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso));
  if (!match) return String(iso);
  const [, year, month, day] = match;
  // Noon avoids a calendar-date shift in time zones on either side of UTC.
  const date = new Date(Number(year), Number(month) - 1, Number(day), 12);
  if (Number.isNaN(date.getTime())) return String(iso);
  let formatter = DATE_FORMATTERS.get(locale);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(locale, {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
    DATE_FORMATTERS.set(locale, formatter);
  }
  return formatter.format(date);
}

/** @param {number} value @param {string} [locale] @returns {string} */
export function formatNumber(value, locale = pageLocale()) {
  let formatter = NUMBER_FORMATTERS.get(locale);
  if (!formatter) {
    formatter = new Intl.NumberFormat(locale);
    NUMBER_FORMATTERS.set(locale, formatter);
  }
  return formatter.format(value);
}

/** @param {string} left @param {string} right @param {string} [locale] */
export function compareText(left, right, locale = pageLocale()) {
  let collator = COLLATORS.get(locale);
  if (!collator) {
    collator = new Intl.Collator(locale, { sensitivity: "base", numeric: true });
    COLLATORS.set(locale, collator);
  }
  return collator.compare(left, right);
}

applyDocumentDirection();
