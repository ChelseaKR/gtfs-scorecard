// @ts-check
/**
 * After checkout for the history tables (/data/history/setup/, ADR 0063).
 * Stripe redirects here with ?session_id=... after a successful Checkout. This
 * posts that reference, and nothing else, to the program-bundle API
 * (window.SCORECARD_BUNDLE_URL), which confirms the payment with Stripe,
 * records a 30-day capability for the newest monthly export, emails the link,
 * and answers with it. There is no form: the purchase names everything.
 *
 * A reload is safe. The server answers the same link again for a checkout it
 * has already delivered, so this page never tells a buyer who has paid that
 * nothing happened.
 */

const status = /** @type {HTMLElement | null} */ (document.getElementById("setup-status"));
const line = /** @type {HTMLElement | null} */ (document.getElementById("download-line"));
const link = /** @type {HTMLAnchorElement | null} */ (document.getElementById("download-link"));
const note = /** @type {HTMLElement | null} */ (document.getElementById("download-note"));
const retry = /** @type {HTMLButtonElement | null} */ (document.getElementById("retry"));
const endpoint = /** @type {any} */ (window).SCORECARD_BUNDLE_URL;
const sessionId = new URLSearchParams(location.search).get("session_id") || "";

/**
 * Report the purchase once as the GA4 purchase event, by the SHA-256 of the
 * order reference (docs/decisions/0057-bundle-conversion-events.md); the
 * reference itself never leaves this function.
 * @param {string} reference
 */
async function reportPurchase(reference) {
  const subtle = window.crypto && window.crypto.subtle;
  if (!subtle || !/^cs_[A-Za-z0-9_]+$/.test(reference)) return;
  const digest = await subtle.digest("SHA-256", new TextEncoder().encode(reference));
  const order = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 32);
  document.dispatchEvent(
    new CustomEvent("scorecard:commerce", { detail: { event: "purchase", transaction_id: order } }),
  );
}

reportPurchase(sessionId).catch(() => {
  // Measurement never surfaces an error to a buyer.
});

/** @param {string} message @param {"ok"|"err"|"info"} kind */
function setStatus(message, kind) {
  if (!status) return;
  status.textContent = message;
  status.className = `form-status form-status-${kind}`;
}

/** Only return https URLs; "" otherwise. @param {unknown} url */
function safeUrl(url) {
  try {
    const u = new URL(String(url));
    return u.protocol === "https:" ? u.href : "";
  } catch {
    return "";
  }
}

async function collect() {
  if (retry) retry.hidden = true;
  setStatus("Confirming your payment with Stripe…", "info");
  try {
    const resp = await fetch(`${String(endpoint).replace(/\/$/, "")}/setup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
    const body = await resp.json().catch(() => ({}));
    const url = safeUrl(body.download_url);
    if (resp.ok && body.ok && url && link && line) {
      link.href = url;
      line.hidden = false;
      const month = typeof body.month === "string" ? body.month : "";
      const days = typeof body.expires_in_days === "number" ? body.expires_in_days : 30;
      setStatus(month ? `Payment confirmed. This is the ${month} build.` : "Payment confirmed.", "ok");
      if (note) {
        note.textContent = body.emailed === false
          ? `The link could not be emailed, so keep this page: the link above works for ${days} days.`
          : `The same link was emailed to the address you paid with and works for ${days} days.`;
        note.hidden = false;
      }
      return;
    }
    setStatus(String(body.error || `The service answered ${resp.status}. Nothing was charged twice; try again.`), "err");
  } catch {
    setStatus("Could not reach the setup service. Your payment is safe; try again in a minute.", "err");
  }
  if (retry) retry.hidden = false;
}

// The two cannot-run states say different things depending on whether Stripe
// put an order reference in the address of this page, because that reference
// is the evidence that a payment happened. Telling a buyer who has just paid
// that nothing was charged is the one sentence this page must never say.
if (!endpoint) {
  setStatus(
    sessionId
      ? "Your payment went through, but the setup service cannot be reached, so the link cannot be shown yet. Nothing is lost. Keep the full web address of this page, which carries your order reference, and reply to the receipt Stripe emailed you; the link will be sent by hand."
      : "The setup service is not deployed yet, so this page cannot show a link. Nothing has been charged.",
    "info",
  );
} else if (!/^cs_[A-Za-z0-9_]+$/.test(sessionId)) {
  setStatus(
    "This page needs the order reference Stripe adds to its address after checkout, and this address does not carry one. If you have already paid and lost that page, reply to the receipt Stripe emailed you and the link will be sent by hand. Do not pay again.",
    "info",
  );
} else {
  if (retry) retry.addEventListener("click", () => { collect(); });
  collect();
}
