// @ts-check
/**
 * The compact "what the paid tier costs" summary, for pages that are not
 * /bundle/ itself (the landing page and /support/ today).
 *
 * Same rule as bundle.js and for the same reason: a price is never in the
 * HTML. Every amount here is read from /bundle/plan.json at view time, so the
 * summary a reader sees on the home page and the plan grid they land on cannot
 * disagree, and switching the tier off is still a data change rather than a
 * copy change across five pages.
 *
 * What this deliberately does NOT render is a checkout link. The buy controls
 * live on /bundle/, behind the page that states delivery, refund, link
 * lifetime, and what a purchase does not buy. A summary elsewhere says "this
 * exists and here is what it costs" and then hands the reader to that page.
 *
 * Markup contract, all of which is present and useful with scripting off:
 *
 *   <div data-plan-summary>
 *     <p data-plan-status>...</p>     <- rewritten to the live commitment
 *     <p><a href="/bundle/">...</a></p>  <- the only control, always static
 *   </div>
 */

/** @param {number} amount @param {string} currency */
function money(amount, currency) {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${amount} ${currency}`;
  }
}

/** The order the tiers are described in everywhere: one-time, then refresh. */
const ORDER = ["bundle_25", "bundle_100", "refresh_mo", "refresh_yr"];

/**
 * One tier tile. Text only: no link, no button, nothing focusable, so adding
 * this block to a page adds no new tab stop and no new accessible name to
 * collide with the page's own controls.
 * @param {string} key @param {Record<string, any>} product @param {string} currency
 */
function tile(key, product, currency) {
  const li = document.createElement("li");
  li.className = "plan-tile";
  li.dataset.plan = key;

  const kicker = document.createElement("p");
  kicker.className = "plan-tile-kicker";
  kicker.textContent = product.interval ? "Subscription" : "One time";

  const name = document.createElement("p");
  name.className = "plan-tile-name";
  name.textContent = String(product.label || key);

  const price = document.createElement("p");
  price.className = "plan-tile-price";
  price.textContent = product.interval
    ? `${money(product.price, currency)} per ${product.interval}`
    : money(product.price, currency);

  li.append(kicker, name, price);
  return li;
}

/**
 * @param {HTMLElement} root
 * @param {Record<string, any>} plan
 */
function render(root, plan) {
  const status = /** @type {HTMLElement | null} */ (root.querySelector("[data-plan-status]"));
  const existing = root.querySelector(".plan-tiles");
  if (existing) existing.remove();

  const products = plan.products || {};
  const currency = String(plan.currency || "USD");
  const sellable = ORDER.filter(
    (key) =>
      products[key] &&
      typeof products[key].price === "number" &&
      plan.paymentsAvailable === true,
  );

  if (sellable.length === 0) {
    if (status) {
      status.textContent =
        "Paid bundles are not available right now. Everything an agency uses, " +
        "including its own board report, is unchanged and free.";
    }
    return;
  }

  const list = document.createElement("ul");
  list.className = "plan-tiles";
  for (const key of sellable) list.appendChild(tile(key, products[key], currency));
  root.insertBefore(list, root.firstChild);

  const days = Number(plan.provisioning_business_days) || 2;
  if (status) {
    status.textContent =
      `Delivered within ${days} business ${days === 1 ? "day" : "days"}, ` +
      "refunded if it is later than that. Buying changes nothing about the " +
      "grades: the bundle's numbers are the ones already on this site.";
  }
}

const roots = /** @type {HTMLElement[]} */ ([
  ...document.querySelectorAll("[data-plan-summary]"),
]);

if (roots.length > 0) {
  fetch("/bundle/plan.json", { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then((plan) => {
      for (const root of roots) render(root, plan);
      document.documentElement.dataset.planSummary = "rendered";
    })
    .catch(() => {
      // An unreadable plan must not leave a stale or invented price standing.
      for (const root of roots) render(root, { paymentsAvailable: false, products: {} });
      document.documentElement.dataset.planSummary = "unavailable";
    });
}
