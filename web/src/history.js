// @ts-check
/**
 * The scorecard history tables page (/data/history/, ADR 0063). The price and
 * the checkout link are never in the HTML: this reads /data/history/plan.json,
 * and unless the server says paymentsAvailable is true it renders the "not yet
 * available" state. The same shape as web/src/bundle.js for the bundle page,
 * for the same reason: a page deployed ahead of its payment rail describes
 * nothing it cannot do, and turning the tier on is a data change.
 *
 * The Offer structured data is served in the HTML, generated from the same
 * plan.json by site_shell.sync_history_offers and gated against it; this module
 * rewrites that one block from its own fetch, so the page carries exactly one
 * offers block with or without scripting.
 */

const SERVICE_ID = "https://gtfsscorecard.org/data/history/#service";
const SERVICE_URL = "https://gtfsscorecard.org/data/history/";
const SERVICE_NAME = "Scorecard history tables";
const OFFER_SCRIPT_ID = "plan-offers-jsonld";
const PLAN_URL = "/data/history/plan.json";
/** The one plan this page sells. */
const PLAN = "history_once";
/** The document event web/src/measure.js forwards to GA4 as a conversion
 * step (docs/decisions/0057-bundle-conversion-events.md). */
const COMMERCE_EVENT = "scorecard:commerce";

const grid = /** @type {HTMLElement | null} */ (document.getElementById("plan-grid"));
const notice = /** @type {HTMLElement | null} */ (document.getElementById("plan-notice"));
const fineprint = /** @type {HTMLElement | null} */ (document.getElementById("plan-fineprint"));
const leadPrice = /** @type {HTMLElement | null} */ (document.getElementById("buy-box-price"));
const leadLink = /** @type {HTMLAnchorElement | null} */ (document.getElementById("buy-box-cta"));

/**
 * @param {"view_item" | "begin_checkout"} event
 * @param {string} currency
 * @param {Array<{ item_id: string, price: number }>} items
 */
function announce(event, currency, items) {
  if (items.length === 0) return;
  document.dispatchEvent(
    new CustomEvent(COMMERCE_EVENT, {
      detail: { event, currency, amount: items[0].price, items },
    }),
  );
}

/**
 * Make a link a checkout link: the Stripe address and the GA4 begin_checkout
 * step (ADR 0057). No PostHog click event: the one the privacy statement names
 * is the bundle page's, and this page adds none until the statement does.
 * @param {HTMLAnchorElement} a @param {number} price @param {string} currency
 */
function checkoutLink(a, price, currency) {
  a.addEventListener("click", () => announce("begin_checkout", currency, [{ item_id: PLAN, price }]));
}

/** @param {string} message @param {"info"|"err"} kind */
function setNotice(message, kind) {
  if (!notice) return;
  notice.textContent = message;
  notice.className = `form-status form-status-${kind === "err" ? "err" : "ok"}`;
  notice.hidden = false;
}

/** Only return https URLs; "#" otherwise. @param {unknown} url */
function safeUrl(url) {
  try {
    const u = new URL(String(url), location.href);
    return u.protocol === "https:" ? u.href : "#";
  } catch {
    return "#";
  }
}

/** @param {number} amount @param {string} currency */
function money(amount, currency) {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
  } catch {
    return `${amount} ${currency}`;
  }
}

/**
 * The sellable product, or null. The same refusals the generator applies to the
 * same file: payments on, a numeric price, an https checkout link.
 * @param {Record<string, any>} plan
 */
function sellable(plan) {
  if (plan.paymentsAvailable !== true) return null;
  const product = (plan.products || {})[PLAN];
  if (!product || typeof product.price !== "number") return null;
  const url = safeUrl(product.checkout_url);
  if (!url.startsWith("https:")) return null;
  return { product, url, currency: String(plan.currency || "USD") };
}

/** @param {Record<string, any>} plan */
function publishOffers(plan) {
  const existing = document.getElementById(OFFER_SCRIPT_ID);
  if (existing) existing.remove();
  const sale = sellable(plan);
  if (!sale) return;
  const node = {
    "@context": "https://schema.org",
    "@type": ["Service", "Product"],
    "@id": SERVICE_ID,
    name: SERVICE_NAME,
    url: SERVICE_URL,
    offers: {
      "@type": "Offer",
      name: String(sale.product.label || PLAN),
      price: String(sale.product.price),
      priceCurrency: sale.currency,
      availability: "https://schema.org/InStock",
      url: sale.url,
      category: "one-time",
    },
  };
  const script = document.createElement("script");
  script.id = OFFER_SCRIPT_ID;
  script.type = "application/ld+json";
  script.textContent = JSON.stringify(node).replace(/</g, "\\u003c");
  document.head.appendChild(script);
}

/** @param {Record<string, any>} plan */
function render(plan) {
  publishOffers(plan);
  const sale = sellable(plan);
  if (leadPrice && leadLink && sale && !leadLink.hasAttribute("data-rendered")) {
    leadLink.setAttribute("data-rendered", "1");
    const price = money(sale.product.price, sale.currency);
    leadPrice.textContent = `${String(sale.product.label || PLAN)}: ${price}, paid once.`;
    leadLink.href = sale.url;
    leadLink.textContent = `Buy for ${price} through Stripe`;
    checkoutLink(leadLink, sale.product.price, sale.currency);
  }
  if (!grid) return;
  grid.replaceChildren();
  const product = (plan.products || {})[PLAN];
  if (product) {
    const card = document.createElement("section");
    card.className = "support-path";
    card.setAttribute("aria-labelledby", `plan-${PLAN}-h`);
    const kicker = document.createElement("p");
    kicker.className = "support-path-kicker";
    kicker.textContent = "One time";
    const h = document.createElement("h2");
    h.id = `plan-${PLAN}-h`;
    h.textContent = String(product.label || PLAN);
    const price = document.createElement("p");
    price.className = "plan-price";
    price.textContent = sale ? money(sale.product.price, sale.currency) : "Not yet available";
    card.append(kicker, h, price);
    if (sale) {
      const p = document.createElement("p");
      const a = document.createElement("a");
      a.className = "submit-button";
      a.href = sale.url;
      a.textContent = "Buy through Stripe";
      checkoutLink(a, sale.product.price, sale.currency);
      p.appendChild(a);
      card.appendChild(p);
      announce("view_item", sale.currency, [{ item_id: PLAN, price: sale.product.price }]);
    }
    grid.appendChild(card);
  }
  if (sale) {
    setNotice("Checkout is open. After paying, the page you land on shows your download link, and the same link is emailed to you. It stays valid for 30 days.", "info");
  } else {
    setNotice("The history tables are not yet on sale. Every dated scorecard they are built from is free at its own address, and the export command is open source.", "info");
  }
  if (fineprint) fineprint.hidden = !sale;
}

fetch(PLAN_URL, { cache: "no-store" })
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
  .then(render)
  .catch(() => {
    render({ paymentsAvailable: false, products: {} });
    setNotice("Could not read the current plan. Nothing is for sale until it can be read.", "err");
  });
