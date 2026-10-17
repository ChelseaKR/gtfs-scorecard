// @ts-check
/**
 * Buy by invoice or purchase order (/invoice/). Two jobs, and no network call
 * that carries anything a reader types:
 *
 * 1. Fill each price on the page from /bundle/plan.json, the one file that owns
 *    every price on this site. The page itself carries no amount, so a price
 *    change is a data change. A plan that cannot be read leaves the static
 *    sentence in place, which tells the reader the quote states the price.
 * 2. Turn the request form into a mailto: link. The text is built from the
 *    labels and typed values of the form, shown in a box the reader can copy
 *    from, and handed to the mail program of the reader. This script sends nothing.
 *
 * All reader-facing wording lives in the HTML (labels and data-msg-* attributes),
 * so this file carries no English copy.
 */

const form = /** @type {HTMLFormElement | null} */ (document.getElementById("invoice-form"));
const status = /** @type {HTMLElement | null} */ (document.getElementById("invoice-status"));
const copyBox = /** @type {HTMLElement | null} */ (document.getElementById("invoice-copy"));
const copyText = /** @type {HTMLTextAreaElement | null} */ (document.getElementById("invoice-text"));
const mailLink = /** @type {HTMLAnchorElement | null} */ (document.getElementById("mail-link"));

/** @param {number} amount @param {string} currency */
function money(amount, currency) {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
  } catch {
    return `${amount} ${currency}`;
  }
}

/** @param {Record<string, any>} plan */
function fillPrices(plan) {
  const products = plan && plan.products ? plan.products : {};
  const currency = String(plan.currency || "USD");
  for (const el of Array.from(document.querySelectorAll("[data-price-for]"))) {
    const product = products[/** @type {HTMLElement} */ (el).dataset.priceFor || ""];
    if (!product || typeof product.price !== "number") continue;
    const { prefix = "", suffix = "" } = /** @type {HTMLElement} */ (el).dataset;
    el.textContent = `${prefix}${money(product.price, currency)}${suffix}`;
  }
}

fetch("/bundle/plan.json", { cache: "no-store" })
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
  .then(fillPrices)
  .catch(() => {
    // The static sentence already says the quote states the price.
  });

/** @param {string} message @param {"ok"|"err"} kind */
function setStatus(message, kind) {
  if (!status) return;
  status.textContent = message;
  status.className = `form-status form-status-${kind}`;
}

/** The visible text of a label, without its (required) marker.
 * @param {Element | null} label */
function labelText(label) {
  if (!label) return "";
  const copy = /** @type {Element} */ (label.cloneNode(true));
  for (const marker of Array.from(copy.querySelectorAll(".req"))) marker.remove();
  return (copy.textContent || "").trim();
}

/** Build the request text from the labels and values of the form.
 * @param {HTMLFormElement} f */
function requestText(f) {
  const lines = [];
  for (const id of ["org", "contact", "reply", "count", "needs"]) {
    const field = /** @type {HTMLInputElement | HTMLTextAreaElement | null} */ (f.querySelector(`#${id}`));
    const value = field ? field.value.trim() : "";
    if (!field || !value) continue;
    lines.push(`${labelText(f.querySelector(`label[for="${id}"]`))}: ${value}`);
  }
  const chosen = Array.from(f.querySelectorAll('input[name="buy"]:checked')).map((box) =>
    labelText(f.querySelector(`label[for="${box.id}"]`)),
  );
  const legend = labelText(f.querySelector("#choose legend"));
  lines.splice(3, 0, `${legend}: ${chosen.join("; ")}`);
  return lines.join("\n");
}

if (form) {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    for (const el of Array.from(form.elements)) el.removeAttribute("aria-invalid");
    const required = Array.from(form.querySelectorAll("[required]"));
    const missing = required.find(
      (el) => !(/** @type {HTMLInputElement} */ (el).value || "").trim() || !(/** @type {HTMLInputElement} */ (el).validity.valid),
    );
    if (missing) {
      missing.setAttribute("aria-invalid", "true");
      setStatus(form.dataset.msgMissing || "", "err");
      /** @type {HTMLElement} */ (missing).focus();
      return;
    }
    const firstBox = /** @type {HTMLInputElement | null} */ (form.querySelector('input[name="buy"]'));
    if (!form.querySelector('input[name="buy"]:checked')) {
      setStatus(form.dataset.msgChoose || "", "err");
      if (firstBox) firstBox.focus();
      return;
    }
    const text = requestText(form);
    if (copyText && copyBox) {
      copyText.value = text;
      copyBox.hidden = false;
    }
    setStatus(form.dataset.msgReady || "", "ok");
    // Keep the recipient and subject that the static link already carries.
    const base = mailLink ? new URL(mailLink.href) : null;
    if (base) {
      const subject = base.searchParams.get("subject") || "";
      location.href = `${base.protocol}${base.pathname}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(text)}`;
    }
  });
}
