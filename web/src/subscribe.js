// @ts-check
/**
 * The opt-in alerts form. POSTs to the alerts API (infra/alerts) which stores a
 * pending subscriber and emails a confirm link (double opt-in). No account, no
 * client secret: abuse is bounded server-side. If the endpoint is not
 * configured, the form degrades to an explanation.
 *
 * The agency field is the shared find-as-you-type picker (agency-combobox.js),
 * fed by the small agency index rather than the full history index, so the
 * page no longer unpacks tens of megabytes to list names. Nothing is chosen
 * until the reader picks an agency or the every-agency option: an untouched
 * field is an error, not a subscription to every feed. A link from an agency page
 * (?agency=<id>) opens with that agency already chosen.
 *
 * Two steps of the signup are announced to the measurement script as a
 * "scorecard:lead" event (docs/decisions/0083-alert-signup-events.md): the API
 * accepted the form and is sending a confirmation email, and the reader
 * confirmed from that email. Only the name of the step is in the event, never
 * the address or anything else from the form. The alerts API sends a confirmed
 * reader back here as /subscribe.html#confirmed, which shows the confirmation
 * note (by CSS :target, so it shows without scripting too).
 */

const SUBSCRIBE_URL = /** @type {any} */ (window).SCORECARD_SUBSCRIBE_URL || null;
const agencySearch = /** @type {any} */ (window).ScorecardAgencySearch || null;

const form = /** @type {HTMLFormElement} */ (document.getElementById("subscribe-form"));
const status = /** @type {HTMLElement} */ (document.getElementById("form-status"));
const agencyInput = /** @type {HTMLInputElement} */ (document.getElementById("agency"));
const agencyField = /** @type {HTMLElement} */ (document.getElementById("agency-picker"));
const emailInput = /** @type {HTMLInputElement} */ (document.getElementById("email"));
const submitButton = /** @type {HTMLButtonElement | null} */ (form.querySelector('button[type="submit"]'));
const kindInputs = /** @type {NodeListOf<HTMLInputElement>} */ (
  form.querySelectorAll('input[name="kinds"]')
);

/** @type {any} */
let picker = null;
/** The last request the API accepted, so pressing the button again does not
 *  send a second confirmation (the API refuses a repeat within 15 minutes
 *  with a 429). @type {string} */
let lastAccepted = "";
let lastAcceptedMessage = "";
let sending = false;

/** The alerts API also wants a dot and a two-letter ending after the @
 *  (infra/alerts/handler.py EMAIL_RE), which the browser does not check, so
 *  you@agency passed here and came back from the server, seconds later, as a
 *  terse API error. Checked here with the same wording as any other
 *  incomplete address. */
const DOMAIN_WITH_ENDING = /@[^@\s]+\.[A-Za-z]{2,}$/;

function setupPicker() {
  if (!agencySearch || !agencyInput || !agencyField) return;
  picker = agencySearch.attach({
    input: agencyInput,
    listbox: /** @type {HTMLElement} */ (document.getElementById("agency-options")),
    status: /** @type {HTMLElement} */ (document.getElementById("agency-status")),
    messages: agencySearch.messagesFrom(agencyField),
    offerAll: true,
    onChoose: () => {
      if (agencyInput.getAttribute("aria-invalid")) clearInvalid();
    },
  });
  const wanted = new URLSearchParams(window.location.search).get("agency");
  if (wanted) {
    picker.records().then(
      (/** @type {any[]} */ records) => {
        const record = records.find((r) => r.id === wanted);
        if (record && !agencyInput.value) picker.choose(record);
      },
      () => {}
    );
  }
}

/** What the agency field holds once the reader is done with it: a chosen
 *  record, "all", or null when nothing usable is chosen. Text that clearly
 *  names one agency (typed in full, not picked) counts as choosing it.
 *  @returns {Promise<{all: true} | {id: string} | null>} */
async function chosenAgency() {
  if (!picker) {
    // The picker script did not load: the field is a plain text box, so take
    // what was typed as a feed id, the way the API reads it.
    const typed = agencyInput.value.trim();
    return typed ? { id: typed } : null;
  }
  const choice = picker.choice();
  if (choice) return choice.all ? { all: true } : { id: choice.id };
  if (!agencyInput.value.trim()) return null;
  if (picker.allMatches()) return { all: true };
  try {
    const record = await picker.clearMatch();
    if (record) {
      picker.choose(record);
      return { id: record.id };
    }
  } catch {
    /* the index did not load; treated as nothing chosen */
  }
  return null;
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

/** The form's own sentences for problems, from data-msg-* attributes on the
 *  form, so the wording is reviewed with the rest of the page's copy. */
const SENTENCES = {
  email: form.dataset.msgEmail || "",
  kinds: form.dataset.msgKinds || "",
  cooldown: form.dataset.msgCooldown || "",
  rate: form.dataset.msgRate || "",
  other: form.dataset.msgOther || "",
};

/** Turn a refusal from the alerts API into the form's own sentence and the
 *  field it is about. The API's text ("invalid agency id: 'x'") is written for
 *  developers and is never shown. The API names the field in `code`
 *  (infra/alerts/handler.py); a reply without one, from the API as deployed
 *  before that, is read by its text.
 *  @param {number} statusCode @param {any} reply
 *  @returns {{message: string, field: HTMLElement | null}} */
function refusal(statusCode, reply) {
  const text = String((reply && reply.error) || "");
  let code = String((reply && reply.code) || "");
  if (!code) {
    if (/email is required/i.test(text)) code = "email";
    else if (/agenc/i.test(text)) code = "agency";
    else if (/kind/i.test(text)) code = "kinds";
    else if (/confirmation email was just sent/i.test(text)) code = "cooldown";
    else if (statusCode === 429) code = "rate";
  }
  switch (code) {
    case "email":
      return { message: SENTENCES.email, field: emailInput };
    case "agency":
      return { message: agencyField?.dataset.msgRequired || SENTENCES.other, field: agencyInput };
    case "kinds":
      return { message: SENTENCES.kinds, field: kindInputs[0] || null };
    case "cooldown":
      return { message: SENTENCES.cooldown, field: null };
    case "rate":
      return { message: SENTENCES.rate, field: null };
    default:
      return { message: SENTENCES.other, field: null };
  }
}

/** @param {boolean} busy */
function setSending(busy) {
  sending = busy;
  if (busy) {
    form.setAttribute("aria-busy", "true");
    submitButton?.setAttribute("disabled", "true");
    submitButton?.classList.add("is-sending");
  } else {
    form.removeAttribute("aria-busy");
    submitButton?.removeAttribute("disabled");
    submitButton?.classList.remove("is-sending");
  }
}

/** Tell web/src/measure.js that a step of the signup happened. The detail
 *  carries the name of the step and nothing else.
 *  @param {"alert_signup_requested" | "alert_signup_confirmed"} step */
function announce(step) {
  document.dispatchEvent(new CustomEvent("scorecard:lead", { detail: { event: step } }));
}

/** A reader the alerts API sent back after pressing the confirm button. The
 *  marker is taken out of the address once read, so reloading the page neither
 *  shows the note again nor counts the confirmation twice. */
function showConfirmed() {
  const note = document.getElementById("confirmed");
  if (!note || window.location.hash !== "#confirmed") return;
  note.classList.add("is-shown");
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  note.focus();
  announce("alert_signup_confirmed");
}

showConfirmed();
setupPicker();

if (!SUBSCRIBE_URL) {
  setStatus(
    "Alerts are not enabled on this deployment yet. Check back soon.",
    "info"
  );
  if (form) submitButton?.setAttribute("disabled", "true");
} else {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    // One request at a time: a second press, or Enter in a field while the
    // first request is out, does nothing.
    if (sending) return;
    const data = new FormData(form);
    const email = String(data.get("email") || "").trim();
    const kinds = data.getAll("kinds").map(String);
    clearInvalid();
    if (!email || !emailInput.validity.valid || !DOMAIN_WITH_ENDING.test(email)) {
      setStatus(email ? SENTENCES.email : "Enter your email.", "err");
      flagInvalid(emailInput);
      emailInput.focus();
      return;
    }
    setSending(true);
    const agency = await chosenAgency();
    if (!agency) {
      setSending(false);
      setStatus(agencyField?.dataset.msgRequired || "", "err");
      flagInvalid(agencyInput);
      agencyInput.focus();
      return;
    }
    if (!kinds.length) {
      setSending(false);
      setStatus(SENTENCES.kinds, "err");
      for (const input of kindInputs) flagInvalid(input);
      kindInputs[0]?.focus();
      return;
    }

    const payload =
      "all" in agency ? { email, all: true, kinds } : { email, agencies: [agency.id], kinds };
    const body = JSON.stringify(payload);
    if (body === lastAccepted) {
      // Already accepted from this page: say so again instead of asking the
      // API for a second confirmation email it would refuse.
      setSending(false);
      setStatus(lastAcceptedMessage, "ok");
      return;
    }
    setStatus("Sending…", "");
    try {
      const res = await fetch(`${SUBSCRIBE_URL.replace(/\/$/, "")}/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
      const reply = await res.json().catch(() => ({}));
      if (res.ok) {
        lastAccepted = body;
        lastAcceptedMessage = reply.message || "Check your email to confirm your subscription.";
        setStatus(lastAcceptedMessage, "ok");
        // "pending" is a new request with a confirmation email on its way. An
        // address that was already subscribed is not a new signup.
        if (reply.status === "pending") announce("alert_signup_requested");
      } else {
        const { message, field } = refusal(res.status, reply);
        setStatus(message, "err");
        if (field) {
          // The kinds are one group: mark every box, as the check above does.
          if (field === kindInputs[0]) for (const input of kindInputs) flagInvalid(input);
          else flagInvalid(field);
          field.focus();
        }
      }
    } catch {
      setStatus("Could not reach the server. Please try again.", "err");
    } finally {
      setSending(false);
    }
  });
}
