// @ts-check
/**
 * Program report bundle page (/bundle/). Prices and checkout links are never
 * in the HTML: this reads /bundle/plan.json, and unless the server says
 * paymentsAvailable is true it renders the "not yet available" state. A page
 * deployed ahead of the payment rail therefore describes nothing it cannot
 * do, and turning the tier on is a data change, not a copy change.
 */

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

/** @param {Record<string, any>} plan */
function render(plan) {
  if (!grid) return;
  grid.replaceChildren();
  const products = plan.products || {};
  const order = ["bundle_25", "bundle_100", "refresh_mo", "refresh_yr"];
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
      `Checkout is open. After paying you set the program name, accent, logo, and up to ${plan.max_agencies || 100} agency ids, and the archive is emailed within ${plan.provisioning_business_days || 2} business days.`,
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
