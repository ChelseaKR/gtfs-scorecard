// @ts-check
/**
 * Program report bundle page (/bundle/). Prices and checkout links are never
 * in the HTML: this reads /bundle/plan.json, and unless the server says
 * paymentsAvailable is true it renders the "not yet available" state. A page
 * deployed ahead of the payment rail therefore describes nothing it cannot
 * do, and turning the tier on is a data change, not a copy change.
 *
 * The same fetch builds the Offer structured data a search engine reads. The
 * <head> of the page carries the Service, breadcrumb, and FAQ nodes
 * statically, with no amount in them; every price a crawler sees is injected
 * here from the same plan the visible cards are built from. So the two can
 * never disagree, and a plan that says payments are off, or one that cannot
 * be read, leaves no offer standing.
 */

/** The Service node in the page head that the Offers attach to. */
const SERVICE_ID = "https://gtfsscorecard.org/bundle/#service";
const OFFER_SCRIPT_ID = "plan-offers-jsonld";

const grid = /** @type {HTMLElement | null} */ (document.getElementById("plan-grid"));
const notice = /** @type {HTMLElement | null} */ (document.getElementById("plan-notice"));
const fineprint = /** @type {HTMLElement | null} */ (document.getElementById("plan-fineprint"));

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
    "@type": "Service",
    "@id": SERVICE_ID,
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

/** @param {Record<string, any>} plan */
function render(plan) {
  const order = ["bundle_25", "bundle_100", "refresh_mo", "refresh_yr"];
  publishOffers(plan, order);
  if (!grid) return;
  grid.replaceChildren();
  const products = plan.products || {};
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
    if (canSell) {
      const p = document.createElement("p");
      const a = document.createElement("a");
      a.className = "submit-button";
      a.href = safeUrl(product.checkout_url);
      a.textContent = "Buy through Stripe";
      p.appendChild(a);
      card.appendChild(p);
    }
    grid.appendChild(card);
  }
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
