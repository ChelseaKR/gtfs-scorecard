// @ts-check
/**
 * The opt-in alerts form. POSTs to the alerts API (infra/alerts) which stores a
 * pending subscriber and emails a confirm link (double opt-in). No account, no
 * client secret: abuse is bounded server-side. If the endpoint is not
 * configured, the form degrades to an explanation.
 */

const SUBSCRIBE_URL = /** @type {any} */ (window).SCORECARD_SUBSCRIBE_URL || null;
const DATA_BASES = [
  /** @type {any} */ (window).SCORECARD_DATA_BASE,
  "data/artifacts",
  "../data/artifacts",
].filter(Boolean);

const form = /** @type {HTMLFormElement} */ (document.getElementById("subscribe-form"));
const status = /** @type {HTMLElement} */ (document.getElementById("form-status"));
const agencySelect = /** @type {HTMLSelectElement} */ (document.getElementById("agency"));
const emailInput = /** @type {HTMLInputElement} */ (document.getElementById("email"));
const kindInputs = /** @type {NodeListOf<HTMLInputElement>} */ (
  form.querySelectorAll('input[name="kinds"]')
);

/** Fetch index.json from the first base that answers, to fill the agency list. */
async function fetchIndex() {
  for (const base of DATA_BASES) {
    try {
      const res = await fetch(`${base}/index.json`);
      if (res.ok) return res.json();
    } catch {
      /* try the next base */
    }
  }
  return null;
}

async function populateAgencies() {
  const index = await fetchIndex();
  if (!index || !index.agencies) return;
  const entries = Object.entries(index.agencies)
    .map(([id, a]) => ({ id, name: /** @type {any} */ (a).name }))
    .sort((x, y) => x.name.localeCompare(y.name));
  for (const { id, name } of entries) {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = name;
    agencySelect.appendChild(opt);
  }
}

/** @param {string} message @param {"ok"|"err"|"info"|""} kind */
function setStatus(message, kind) {
  status.textContent = message;
  status.className = `form-status ${kind ? `form-status-${kind}` : ""}`.trim();
}

if (!SUBSCRIBE_URL) {
  setStatus(
    "Alerts are not enabled on this deployment yet. Check back soon.",
    "info"
  );
  if (form) form.querySelector("button")?.setAttribute("disabled", "true");
} else {
  populateAgencies();
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const email = String(data.get("email") || "").trim();
    const agency = String(data.get("agency") || "");
    const kinds = data.getAll("kinds").map(String);
    emailInput.removeAttribute("aria-invalid");
    for (const input of kindInputs) input.removeAttribute("aria-invalid");
    if (!email || !emailInput.validity.valid) {
      setStatus(
        email ? "Enter a complete email address, like you@agency.gov." : "Enter your email.",
        "err"
      );
      emailInput.setAttribute("aria-invalid", "true");
      emailInput.focus();
      return;
    }
    if (!kinds.length) {
      setStatus("Choose at least one kind of alert.", "err");
      for (const input of kindInputs) input.setAttribute("aria-invalid", "true");
      kindInputs[0]?.focus();
      return;
    }

    const payload = agency ? { email, agencies: [agency], kinds } : { email, all: true, kinds };
    setStatus("Sending…", "");
    form.querySelector("button")?.setAttribute("disabled", "true");
    try {
      const res = await fetch(`${SUBSCRIBE_URL.replace(/\/$/, "")}/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        setStatus(
          body.message || "Check your email to confirm your subscription.",
          "ok"
        );
        form.reset();
      } else if (res.status === 429) {
        setStatus(body.error || "Too many requests. Try again later.", "err");
      } else {
        setStatus(body.error || "Something went wrong. Please try again.", "err");
      }
    } catch {
      setStatus("Could not reach the server. Please try again.", "err");
    } finally {
      form.querySelector("button")?.removeAttribute("disabled");
    }
  });
}
