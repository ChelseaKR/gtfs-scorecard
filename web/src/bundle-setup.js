// @ts-check
/**
 * Post-checkout setup form (/bundle/setup/). Stripe redirects here with
 * ?session_id=... after a successful Checkout. The form POSTs the program
 * details plus that session id to the program-bundle API
 * (window.SCORECARD_BUNDLE_URL), which confirms the payment with Stripe
 * before anything is built. Until that endpoint is deployed, or if the page
 * is reached without a session id, the form is disabled and says why.
 */

const form = /** @type {HTMLFormElement | null} */ (document.getElementById("setup-form"));
const status = /** @type {HTMLElement | null} */ (document.getElementById("form-status"));
const endpoint = /** @type {any} */ (window).SCORECARD_BUNDLE_URL;
const sessionId = new URLSearchParams(location.search).get("session_id") || "";

/** @param {string} message @param {"ok"|"err"|"info"} kind */
function setStatus(message, kind) {
  if (!status) return;
  status.textContent = message;
  status.className = `form-status form-status-${kind}`;
}

/** @param {boolean} on */
function enable(on) {
  if (!form) return;
  for (const el of Array.from(form.elements)) {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLButtonElement) {
      el.disabled = !on;
    }
  }
}

// The two disabled states say different things depending on whether Stripe
// put an order reference in the address of this page, because that reference
// is the evidence that a payment happened. Telling a buyer who has just paid
// that nothing was charged is the one sentence this page must never say:
// it is false, and it is the sentence most likely to stop them chasing an
// order that did go through.
//
// Each message is one literal and carries no apostrophes. The l10n ratchet in
// pipeline/tests/test_l10n_readiness.py counts quoted literals with a regex
// that an apostrophe inside a double-quoted string derails, and copy split
// across concatenated fragments can slip past it: written this way the count
// is honest and the baseline moves on purpose.
if (!form) {
  // Nothing to wire.
} else if (!endpoint) {
  enable(false);
  setStatus(
    sessionId
      ? "Your payment went through, but the setup service cannot be reached, so this form cannot submit yet. Nothing is lost. Keep the full web address of this page, which carries your order reference, and send it through gtfsscorecard.org/support, or reply to the receipt Stripe emailed you, and the bundle will be set up by hand."
      : "The setup service is not deployed yet, so this form cannot submit. Nothing has been charged.",
    "info",
  );
} else if (!/^cs_[A-Za-z0-9_]+$/.test(sessionId)) {
  enable(false);
  setStatus(
    "This page needs the order reference Stripe adds to its address after checkout, and this address does not carry one. If you have already paid and lost that page, reply to the receipt Stripe emailed you, or write through gtfsscorecard.org/support, and the bundle will be set up by hand. Do not pay again.",
    "info",
  );
} else {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    const ids = String(data.agency_ids || "").trim();
    if (!String(data.program_name || "").trim() || !ids) {
      setStatus("Please give the program name and at least one agency id.", "err");
      return;
    }
    // A ceiling across every plan, not a promise about the plan this buyer
    // paid for. The page does not know which price was paid; the server does.
    // It answers a list over that cap with the limit of the plan bought, before
    // it consumes the checkout, so the buyer can trim and resend. This number
    // must equal the largest value in PLAN_AGENCY_CAPS
    // (infra/program-bundle/common.py); test_bundle_setup_ceiling.py holds it.
    if (ids.split(/[\s,]+/).filter(Boolean).length > 100) {
      setStatus("No bundle covers more than 100 agencies. Trim the list and send it again.", "err");
      return;
    }
    enable(false);
    setStatus("Confirming your payment and starting the build…", "info");
    try {
      const resp = await fetch(`${String(endpoint).replace(/\/$/, "")}/setup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          program_name: data.program_name,
          accent: data.accent || "",
          logo: data.logo || "",
          agency_ids: ids,
          deliver_to: data.deliver_to || "",
        }),
      });
      const body = await resp.json().catch(() => ({}));
      if (resp.ok && body.ok) {
        // `body.promise` is the server's sentence, carrying the date it
        // computed and stored against this order. It is deliberately not
        // recomputed here: the two-business-day commitment carries a refund,
        // and a second implementation of it in another language would
        // disagree the first time a public holiday fell between them.
        const promise = typeof body.promise === "string" ? body.promise : "";
        setStatus(
          `Thank you. Your reports are being generated and the download link goes to the address you gave. ${promise} The link stays valid for 30 days.`.replace(/\s+/g, " ").trim(),
          "ok",
        );
        return;
      }
      enable(true);
      setStatus(String(body.error || `The service answered ${resp.status}. Nothing was charged twice; try again.`), "err");
    } catch {
      enable(true);
      setStatus("Could not reach the setup service. Your payment is safe; try again in a minute.", "err");
    }
  });
}
