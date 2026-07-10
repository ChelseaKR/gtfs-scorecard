const form = /** @type {HTMLFormElement} */ (document.getElementById("agency-search-es"));
const input = /** @type {HTMLInputElement} */ (document.getElementById("agency-es"));
const options = /** @type {HTMLDataListElement} */ (document.getElementById("agency-options-es"));
const status = /** @type {HTMLElement} */ (document.getElementById("agency-status-es"));
const button = /** @type {HTMLButtonElement} */ (form.querySelector("button"));

/** @type {Map<string, string>} */
const agencies = new Map();

function message(key) {
  return form.dataset[key] || "";
}

async function loadAgencies() {
  try {
    const response = await fetch("/data/artifacts/directory.json");
    if (!response.ok) throw new Error(`directory ${response.status}`);
    const payload = await response.json();
    const rows = Array.isArray(payload.agencies) ? payload.agencies : [];
    for (const row of rows) {
      if (!row || !row.id || !row.name) continue;
      const name = String(row.name);
      agencies.set(name.toLocaleLowerCase("es"), String(row.id));
      const option = document.createElement("option");
      option.value = name;
      options.append(option);
    }
    status.textContent = message("ready");
    button.disabled = false;
  } catch {
    status.textContent = message("error");
    status.className = "form-status form-status-err";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  input.removeAttribute("aria-invalid");
  const id = agencies.get(input.value.trim().toLocaleLowerCase("es"));
  if (!id) {
    input.setAttribute("aria-invalid", "true");
    status.textContent = message("missing");
    status.className = "form-status form-status-err";
    input.focus();
    return;
  }
  window.location.assign(`/agency/${encodeURIComponent(id)}/`);
});

loadAgencies();
