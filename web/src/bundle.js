// @ts-check
/**
 * Program report bundle page (/bundle/). Prices and checkout links are never
 * in the HTML: this reads /bundle/plan.json, and unless the server says
 * paymentsAvailable is true it renders the "not yet available" state. A page
 * deployed ahead of the payment rail therefore describes nothing it cannot
 * do, and turning the tier on is a data change, not a copy change.
 *
 * The Offer structured data is now served in the HTML, generated from this
 * same plan.json by site_shell.sync_bundle_offers and gated against it, so a
 * crawler that runs no scripts still reads what the page charges. This module
 * keeps rewriting that one block from its own fetch: the element ids match, so
 * the static block is replaced rather than duplicated, and a plan that says
 * payments are off -- or one that cannot be read at all -- still leaves no
 * offer standing on the page a person is looking at.
 */

/** The Service node in the page head that the Offers attach to. */
const SERVICE_ID = "https://gtfsscorecard.org/bundle/#service";
/** Its page, named on the offers node too, so replacing the server-rendered
 * block with this one does not drop a field the served markup carried. */
const SERVICE_URL = "https://gtfsscorecard.org/bundle/";
/** Also named on this node (not only on the hand-authored Service block that
 * carries it in the page head) so it stands alone as a complete Product:
 * Google Product structured data requires a name plus an offers, review, or
 * aggregateRating, and two script tags sharing an @id are not guaranteed to
 * be read as one node. */
const SERVICE_NAME = "Program report bundle";
const OFFER_SCRIPT_ID = "plan-offers-jsonld";

/** The plan the button at the top of the page sells: the entry bundle. */
const LEAD_PLAN = "bundle_25";
/** The document event web/src/measure.js forwards to GA4 as a conversion
 * step (docs/decisions/0057-bundle-conversion-events.md). It carries plan ids
 * and prices from plan.json and nothing about the reader. */
const COMMERCE_EVENT = "scorecard:commerce";

const grid = /** @type {HTMLElement | null} */ (document.getElementById("plan-grid"));
const notice = /** @type {HTMLElement | null} */ (document.getElementById("plan-notice"));
const fineprint = /** @type {HTMLElement | null} */ (document.getElementById("plan-fineprint"));
const leadPrice = /** @type {HTMLElement | null} */ (document.getElementById("buy-box-price"));
const leadLink = /** @type {HTMLAnchorElement | null} */ (document.getElementById("buy-box-cta"));

/**
 * Announce a step toward a purchase. The measurement script decides whether
 * anything is sent (it sends nothing under an opt-out, Global Privacy Control
 * or Do Not Track) and checks every field before it does.
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
 * Make a link a checkout link for one plan: the Stripe address, the PostHog
 * click event (ADR 0055), and the GA4 begin_checkout step (ADR 0057).
 * @param {HTMLAnchorElement} a @param {string} key @param {number} price @param {string} currency
 */
function checkoutLink(a, key, price, currency) {
  // The last thing this site can see of a purchase is this click; the
  // checkout itself happens on Stripe. web/src/measure.js reports it to
  // PostHog under this event name with the plan id, and nothing else about
  // the reader (docs/decisions/0055-cookieless-site-measurement.md), and to
  // GA4 as begin_checkout with the plan id and its price.
  a.setAttribute("data-measure", "bundle_checkout_click");
  a.setAttribute("data-measure-plan", key);
  a.addEventListener("click", () => announce("begin_checkout", currency, [{ item_id: key, price }]));
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
 * One Offer per sellable product, in the order the cards use. Built only from
 * fields the plan actually carries: a product with no numeric price, no https
 * checkout link, or a plan with payments switched off contributes nothing.
 *
 * Machine-readable values only, so nothing here is copy a reader sees: the
 * cadence rides in category and in a UnitPriceSpecification rather than in a
 * sentence.
 * @param {Record<string, any>} plan @param {string[]} order
 */
function offerNodes(plan, order) {
  if (plan.paymentsAvailable !== true) return [];
  const products = plan.products || {};
  const currency = String(plan.currency || "USD");
  const nodes = [];
  for (const key of order) {
    const product = products[key];
    if (!product || typeof product.price !== "number") continue;
    const url = safeUrl(product.checkout_url);
    if (!url.startsWith("https:")) continue;
    /** @type {Record<string, any>} */
    const offer = {
      "@type": "Offer",
      name: String(product.label || key),
      price: String(product.price),
      priceCurrency: currency,
      availability: "https://schema.org/InStock",
      url,
      category: product.interval ? "subscription" : "one-time",
    };
    if (product.interval) {
      offer.priceSpecification = {
        "@type": "UnitPriceSpecification",
        price: String(product.price),
        priceCurrency: currency,
        billingDuration: 1,
        billingIncrement: 1,
        unitCode: product.interval === "year" ? "ANN" : "MON",
      };
    }
    nodes.push(offer);
  }
  return nodes;
}

/**
 * Attach the offers to the static Service node by @id, so the two blocks merge
 * into one entity rather than describing two services. Re-runs replace the
 * block, and a plan with nothing to sell removes it: a stale offer is the one
 * outcome this must never leave behind.
 * @param {Record<string, any>} plan @param {string[]} order
 */
function publishOffers(plan, order) {
  const existing = document.getElementById(OFFER_SCRIPT_ID);
  if (existing) existing.remove();
  const nodes = offerNodes(plan, order);
  if (nodes.length === 0) return;
  const prices = nodes.map((offer) => Number(offer.price));
  const node = {
    "@context": "https://schema.org",
    "@type": ["Service", "Product"],
    "@id": SERVICE_ID,
    name: SERVICE_NAME,
    url: SERVICE_URL,
    offers:
      nodes.length === 1
        ? nodes[0]
        : {
            "@type": "AggregateOffer",
            priceCurrency: String(plan.currency || "USD"),
            lowPrice: String(Math.min(...prices)),
            highPrice: String(Math.max(...prices)),
            offerCount: nodes.length,
            offers: nodes,
          },
  };
  const script = document.createElement("script");
  script.id = OFFER_SCRIPT_ID;
  script.type = "application/ld+json";
  // textContent is not parsed as markup, and escaping "<" keeps the block safe
  // even if a label or link ever carried one.
  script.textContent = JSON.stringify(node).replace(/</g, "\\u003c");
  document.head.appendChild(script);
}

/**
 * The price and checkout button at the top of the page, for the entry bundle.
 * Whenever the plan cannot sell that bundle they keep their static sentence
 * and stay a link to the plan list, so the top of the page never offers what
 * the list below cannot.
 * @param {Record<string, any>} plan
 */
function renderLead(plan) {
  if (!leadPrice || !leadLink || leadLink.hasAttribute("data-measure")) return;
  const product = (plan.products || {})[LEAD_PLAN];
  if (plan.paymentsAvailable !== true || !product || typeof product.price !== "number") return;
  const url = safeUrl(product.checkout_url);
  if (!url.startsWith("https:")) return;
  const currency = String(plan.currency || "USD");
  const price = money(product.price, currency);
  const cadence = product.interval ? `per ${product.interval}` : "paid once";
  leadPrice.textContent = `${String(product.label || LEAD_PLAN)}: ${price}, ${cadence}.`;
  leadLink.href = url;
  leadLink.textContent = `Buy for ${price} through Stripe`;
  checkoutLink(leadLink, LEAD_PLAN, product.price, currency);
}

/** @param {Record<string, any>} plan */
function render(plan) {
  const order = ["bundle_25", "bundle_100", "refresh_mo", "refresh_yr"];
  publishOffers(plan, order);
  renderLead(plan);
  if (!grid) return;
  grid.replaceChildren();
  const products = plan.products || {};
  const currency = String(plan.currency || "USD");
  /** @type {Array<{ item_id: string, price: number }>} */
  const shown = [];
  for (const key of order) {
    const product = products[key];
    if (!product) continue;
    const card = document.createElement("section");
    card.className = "support-path";
    card.setAttribute("aria-labelledby", `plan-${key}-h`);
    const kicker = document.createElement("p");
    kicker.className = "support-path-kicker";
    kicker.textContent = product.interval ? "Subscription" : "One time";
    const h = document.createElement("h2");
    h.id = `plan-${key}-h`;
    h.textContent = String(product.label || key);
    const price = document.createElement("p");
    price.className = "plan-price";
    const canSell = plan.paymentsAvailable === true && typeof product.price === "number" && product.checkout_url;
    if (canSell) {
      price.textContent = product.interval
        ? `${money(product.price, plan.currency || "USD")} per ${product.interval}`
        : money(product.price, plan.currency || "USD");
    } else {
      price.textContent = "Not yet available";
    }
    card.append(kicker, h, price);
    // A subscription renews a bundle: it covers the agencies that bundle
    // covered and it does not include one. The server enforces that before it
    // consumes the checkout, so a buyer with no bundle is refused rather than
    // charged for nothing — but being refused after paying is a worse way to
    // learn it than reading it here, which is why this sits on the card and
    // not only in the steps further down the page. (No quoted prose in this
    // comment: the l10n ratchet in pipeline/tests/test_l10n_readiness.py
    // counts quoted literals with a regex that cannot tell code from a
    // comment, so a quotation here would be counted as untranslated copy.)
    if (product.interval) {
      const renews = document.createElement("p");
      renews.className = "fineprint";
      renews.textContent = "Renews a bundle you have already bought, and covers the same agencies as that bundle. Buy a bundle first.";
      card.appendChild(renews);
    }
    if (canSell) {
      const p = document.createElement("p");
      const a = document.createElement("a");
      a.className = "submit-button";
      a.href = safeUrl(product.checkout_url);
      a.textContent = "Buy through Stripe";
      checkoutLink(a, key, product.price, currency);
      p.appendChild(a);
      card.appendChild(p);
      shown.push({ item_id: key, price: product.price });
    }
    grid.appendChild(card);
  }
  // The plans a reader can buy were shown: the GA4 view_item, valued at the
  // first of them, the entry bundle.
  announce("view_item", currency, shown);
  if (plan.paymentsAvailable === true) {
    setNotice(
      `Checkout is open. After paying you set the program name, accent, logo, and the agency ids your plan covers, and the archive is emailed within ${plan.provisioning_business_days || 2} business days — refunded if it is later than that.`,
      "info",
    );
  } else {
    setNotice(
      "Paid bundles are not yet available. The free single-agency report is unchanged: open any agency page and choose the board one-pager, or generate the file yourself.",
      "info",
    );
  }
  if (fineprint) fineprint.hidden = plan.paymentsAvailable !== true;
}

fetch("/bundle/plan.json", { cache: "no-store" })
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
  .then(render)
  .catch(() => {
    render({ paymentsAvailable: false, products: {} });
    setNotice("Could not read the current plan. Nothing is for sale until it can be read.", "err");
  });
