// @ts-check
/**
 * Instant scoring form (infra/instant-score; growth-plans 03-A4). POSTs a
 * GTFS Schedule URL to the try endpoint, polls the job until it lands, and
 * renders the grade, category scores, and top fixes inline — no GitHub
 * account, no wait for an issue comment. Degrades to pointing at the GitHub
 * Issue Form below when the endpoint is not configured on this deployment.
 */
import { CATEGORY_LABELS, CATEGORY_ORDER } from "./generated/constants.js";

const TRY_URL = /** @type {any} */ (window).SCORECARD_TRY_URL || null;
const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 3 * 60 * 1000;

const form = /** @type {HTMLFormElement} */ (document.getElementById("try-form"));
const status = /** @type {HTMLElement} */ (document.getElementById("try-status"));
const result = /** @type {HTMLElement} */ (document.getElementById("try-result"));

/** @param {string} message @param {"ok"|"err"|"info"} kind */
function setStatus(message, kind) {
  status.textContent = message;
  status.className = `form-status form-status-${kind}`;
}

/** Safe text escaping via the DOM (same technique as app.js's esc()). @param {unknown} text */
function esc(text) {
  const div = document.createElement("div");
  div.textContent = String(text);
  return div.innerHTML;
}

/** @param {string} [grade] */
function gradeClass(grade) {
  return `grade-${String(grade || "f").toLowerCase()}`;
}

if (!TRY_URL) {
  setStatus(
    "Instant scoring is not enabled on this deployment yet. Use the form below instead.",
    "info"
  );
  form?.querySelector("button")?.setAttribute("disabled", "true");
} else {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    const url = String(data.url || "").trim();
    const name = String(data.name || "").trim();
    if (!/^https?:\/\/.+/i.test(url)) {
      setStatus("The GTFS Schedule URL should start with http:// or https://.", "err");
      return;
    }

    result.hidden = true;
    result.innerHTML = "";
    const button = /** @type {HTMLButtonElement} */ (form.querySelector(".submit-button"));
    button.disabled = true;
    setStatus("Starting the scorer…", "info");

    try {
      const resp = await fetch(TRY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, name }),
      });
      const body = await resp.json().catch(() => ({}));
      if (resp.status === 429) {
        setStatus(body.error || "Too many requests. Try again in a bit.", "err");
        return;
      }
      if (!resp.ok || !body.job_id) {
        setStatus(body.error || "Something went wrong. Please try again.", "err");
        return;
      }
      setStatus(
        "Downloading your feed and running the validator. This takes about a minute…",
        "info"
      );
      await poll(body.job_id, url, name);
    } catch {
      setStatus("Could not reach the scoring service. Please try again later.", "err");
    } finally {
      button.disabled = false;
    }
  });
}

/** @param {string} jobId @param {string} url @param {string} name */
async function poll(jobId, url, name) {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  const base = TRY_URL.replace(/\/$/, "");
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    /** @type {any} */
    let job;
    try {
      const resp = await fetch(`${base}/score/${encodeURIComponent(jobId)}`);
      job = await resp.json();
    } catch {
      continue; // a transient network blip; keep polling until the deadline
    }
    if (job.status === "done") {
      setStatus("Done.", "ok");
      await showResult(job, url, name);
      return;
    }
    if (job.status === "error") {
      setStatus(job.message || "We could not score that feed.", "err");
      return;
    }
  }
  setStatus(
    "This is taking longer than expected. Check back in a minute, or try the GitHub form below.",
    "err"
  );
}

/** @param {any} job @param {string} url @param {string} name */
async function showResult(job, url, name) {
  /** @type {any} */
  let artifact = null;
  if (job.result_url) {
    try {
      const resp = await fetch(job.result_url);
      if (resp.ok) artifact = await resp.json();
    } catch {
      /* fall back to the grade-only summary below */
    }
  }
  const trackUrl = `submit.html?url=${encodeURIComponent(url)}${name ? `&name=${encodeURIComponent(name)}` : ""}`;

  if (!artifact) {
    result.innerHTML = `
      <h2 class="section-title" id="try-result-h" tabindex="-1">Overall grade: ${esc(job.grade || "—")}</h2>
      <p><a href="${esc(job.result_url || "#")}">View the full result</a></p>
      <p class="field"><a class="submit-button" href="${esc(trackUrl)}">Track this feed daily</a></p>`;
  } else {
    const cats = CATEGORY_ORDER.map((key) => {
      const cat = artifact.categories?.[key];
      const label = esc(CATEGORY_LABELS[key] || key);
      if (!cat || cat.status !== "measured") return `<dt>${label}</dt><dd>not yet measured</dd>`;
      return `<dt>${label}</dt><dd>${esc(Math.round(cat.score))}/100</dd>`;
    }).join("");
    const fixes = (artifact.top_fixes || [])
      .slice(0, 3)
      .map((f) => `<li>${esc(f.fix)} <span class="hint">(${esc(f.effort)})</span></li>`)
      .join("");
    result.innerHTML = `
      <h2 class="section-title" id="try-result-h" tabindex="-1">Overall grade:
        <span class="grade-chip ${gradeClass(artifact.overall?.grade)}">${esc(artifact.overall?.grade || "—")}<span class="visually-hidden"> grade</span></span>
        (${esc(String(artifact.overall?.score ?? "—"))}/100)</h2>
      <dl>${cats}</dl>
      ${fixes ? `<h3>Top things to fix</h3><ol>${fixes}</ol>` : "<p>Nothing urgent turned up. This feed passed every check we translate into fixes.</p>"}
      <p><a href="${esc(job.result_url || "#")}">View the full JSON result</a></p>
      <p class="field"><a class="submit-button" href="${esc(trackUrl)}">Track this feed daily</a></p>`;
  }
  result.hidden = false;
  /** @type {HTMLElement | null} */ (result.querySelector("#try-result-h"))?.focus();
}
