// @ts-check
/**
 * Self-serve submission form. POSTs the feed to the submission endpoint
 * (window.SCORECARD_SUBMIT_URL), which opens a pull request. Until that
 * endpoint is deployed, the form degrades to the manual walkthrough so the
 * page is never a dead end.
 */

const form = /** @type {HTMLFormElement} */ (document.getElementById("submit-form"));
const status = /** @type {HTMLElement} */ (document.getElementById("form-status"));
const endpoint = /** @type {any} */ (window).SCORECARD_SUBMIT_URL;
const DOCS_URL =
  "https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/add-your-agency.md";

// Prefill from an instant-score "track this feed daily" handoff
// (web/try.html), which links here with ?url=&name=&country=.
{
  const params = new URLSearchParams(location.search);
  const urlField = /** @type {HTMLInputElement | null} */ (
    form?.querySelector('[name="static_gtfs_url"]')
  );
  const nameField = /** @type {HTMLInputElement | null} */ (form?.querySelector('[name="name"]'));
  const countryField = /** @type {HTMLInputElement | null} */ (
    form?.querySelector('[name="country"]')
  );
  if (urlField && params.get("url")) urlField.value = params.get("url") || "";
  if (nameField && params.get("name")) nameField.value = params.get("name") || "";
  const country = String(params.get("country") || "").trim().toUpperCase();
  if (countryField && /^[A-Z]{2}$/.test(country)) countryField.value = country;
}

/** @param {string} message @param {"ok"|"err"|"info"} kind */
function setStatus(message, kind) {
  status.textContent = message;
  status.className = `form-status form-status-${kind}`;
}

/** Only return http(s) URLs; "#" otherwise. @param {string} url */
function safeUrl(url) {
  try {
    const u = new URL(url, location.href);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : "#";
  } catch {
    return "#";
  }
}

/** Show the success message, building the PR link with the DOM (never innerHTML)
 *  so a crafted pr_url from the endpoint can't inject markup. @param {string} prUrl */
function showSubmitted(prUrl) {
  status.textContent = "Thank you. We opened a pull request to add your agency: ";
  const link = document.createElement("a");
  link.href = safeUrl(prUrl);
  link.textContent = "review it here";
  status.appendChild(link);
  status.appendChild(
    document.createTextNode(". It will be scored once a maintainer merges it.")
  );
  status.className = "form-status form-status-ok";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form).entries());

  const urlField = /** @type {HTMLInputElement | null} */ (
    form.querySelector('[name="static_gtfs_url"]')
  );
  const nameField = /** @type {HTMLInputElement | null} */ (form.querySelector('[name="name"]'));
  const countryField = /** @type {HTMLInputElement | null} */ (
    form.querySelector('[name="country"]')
  );
  const subdivisionCodeField = /** @type {HTMLInputElement | null} */ (
    form.querySelector('[name="subdivision_code"]')
  );
  const subdivisionNameField = /** @type {HTMLInputElement | null} */ (
    form.querySelector('[name="subdivision_name"]')
  );
  const typedFields = /** @type {HTMLInputElement[]} */ (
    Array.from(form.querySelectorAll('input[type="url"], input[type="email"]'))
  );
  nameField?.removeAttribute("aria-invalid");
  countryField?.removeAttribute("aria-invalid");
  subdivisionCodeField?.removeAttribute("aria-invalid");
  subdivisionNameField?.removeAttribute("aria-invalid");
  for (const field of typedFields) field.removeAttribute("aria-invalid");
  if (!data.name || !data.static_gtfs_url) {
    setStatus("Please give at least an agency name and a GTFS Schedule URL.", "err");
    const missing = data.name ? urlField : nameField;
    missing?.setAttribute("aria-invalid", "true");
    missing?.focus();
    return;
  }
  for (const field of typedFields) {
    const value = field.value.trim();
    const wrongProtocol = field.type === "url" && !/^https?:\/\//i.test(value);
    if (value && (!field.validity.valid || wrongProtocol)) {
      const example = field.type === "email" ? "name@agency.gov" : "https://example.gov/feed";
      const kind = field.type === "email" ? "email address" : "URL";
      setStatus(`Enter a complete ${kind}, like ${example}.`, "err");
      field.setAttribute("aria-invalid", "true");
      field.focus();
      return;
    }
  }
  if (!data.country) {
    setStatus("Please give the agency's two-letter country code.", "err");
    countryField?.setAttribute("aria-invalid", "true");
    countryField?.focus();
    return;
  }
  if (countryField && !countryField.validity.valid) {
    setStatus("Enter a two-letter ISO country code, like US or CA.", "err");
    countryField.setAttribute("aria-invalid", "true");
    countryField.focus();
    return;
  }
  const country = String(data.country).trim().toUpperCase();
  const subdivisionCode = String(data.subdivision_code || "").trim().toUpperCase();
  const subdivisionName = String(data.subdivision_name || "").trim();
  if (Boolean(subdivisionCode) !== Boolean(subdivisionName)) {
    setStatus(
      "Give both the subdivision code and name, or leave both blank.",
      "err"
    );
    const missing = subdivisionCode ? subdivisionNameField : subdivisionCodeField;
    missing?.setAttribute("aria-invalid", "true");
    missing?.focus();
    return;
  }
  data.country = country;
  data.subdivision_code = subdivisionCode;
  data.subdivision_name = subdivisionName;

  if (!endpoint) {
    setStatus("", "info");
    status.innerHTML =
      "Online submission is not enabled on this deployment yet. You can add your " +
      `agency with the <a href="${DOCS_URL}">ten-minute pull-request walkthrough</a> ` +
      "— it asks for exactly these fields.";
    return;
  }

  const button = /** @type {HTMLButtonElement} */ (form.querySelector(".submit-button"));
  button.disabled = true;
  setStatus("Submitting…", "info");

  try {
    const resp = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const body = await resp.json().catch(() => ({}));
    if (resp.ok && body.ok) {
      form.reset();
      showSubmitted(String(body.pr_url || ""));
    } else {
      setStatus(body.error || "Something went wrong. Please try the manual walkthrough.", "err");
    }
  } catch {
    setStatus("Could not reach the submission service. Please try again later.", "err");
  } finally {
    button.disabled = false;
  }
});
