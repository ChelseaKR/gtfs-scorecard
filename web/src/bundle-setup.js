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

if (!form) {
  // Nothing to wire.
} else if (!endpoint) {
  enable(false);
  setStatus("The setup service is not deployed yet, so this form cannot submit. Nothing was charged.", "info");
} else if (!/^cs_[A-Za-z0-9_]+$/.test(sessionId)) {
  enable(false);
  setStatus("Open this page from the link Stripe sent you after checkout; it carries your order reference.", "info");
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
        setStatus(
          "Thank you. Your reports are being generated; the download link goes to the address you gave, and it stays valid for 30 days.",
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
