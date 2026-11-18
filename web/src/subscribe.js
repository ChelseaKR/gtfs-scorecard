// @ts-check
/**
 * The opt-in alerts form. POSTs to the alerts API (infra/alerts) which stores a
 * pending subscriber and emails a confirm link (double opt-in). No account, no
 * client secret: abuse is bounded server-side. If the endpoint is not
 * configured, the form degrades to an explanation.
 */

import { compareText } from "./locale.js";

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
      // Await here so a 200 that is not JSON (an HTML fallback page) is caught
      // and the next base is tried, as fetchJson in app.js does.
      if (res.ok) return await res.json();
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
    .sort((x, y) => compareText(x.name, y.name));
  for (const { id, name } of entries) {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = name;
    agencySelect.appendChild(opt);
  }
}

/** Mark one field as the field in error and tie the status message to it.
 *  With the message named in aria-describedby, a screen reader reads it
 *  together with the field once focus lands there, instead of leaving it in
 *  a live region that the move of focus can talk over.
 *  @param {HTMLElement | null | undefined} field */
function flagInvalid(field) {
  if (!field) return;
  field.setAttribute("aria-invalid", "true");
  const ids = (field.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
  if (!ids.includes(status.id)) ids.push(status.id);
  field.setAttribute("aria-describedby", ids.join(" "));
}

/** Undo flagInvalid on every field, before the form is checked again. */
function clearInvalid() {
  for (const field of form.querySelectorAll("[aria-invalid]")) {
    field.removeAttribute("aria-invalid");
    const ids = (field.getAttribute("aria-describedby") || "")
      .split(/\s+/)
      .filter((id) => id && id !== status.id);
    if (ids.length) field.setAttribute("aria-describedby", ids.join(" "));
    else field.removeAttribute("aria-describedby");
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
    clearInvalid();
    if (!email || !emailInput.validity.valid) {
      setStatus(
        email ? "Enter a complete email address, like you@agency.gov." : "Enter your email.",
        "err"
      );
      flagInvalid(emailInput);
      emailInput.focus();
      return;
    }
    if (!kinds.length) {
      setStatus("Choose at least one kind of alert.", "err");
      for (const input of kindInputs) flagInvalid(input);
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
