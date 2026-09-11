// Drive one Stripe test-mode checkout, and optionally the setup form that
// follows it, for scripts/bundle-testmode.sh.
//
// Test mode only. The card below is Stripe's documented test number and cannot
// move money; this script has no key, reads no key, and prints no key. The
// session id it returns is a `cs_test_...`, which is not a secret.
//
// Everything it says goes to stderr. Exactly one JSON object goes to stdout,
// which is what the shell reads:
//   {"session_id": "cs_test_...", "paid": true,
//    "setup_status": 200, "bundle_id": "...", "setup_body": {...}}
//
// The selectors for Stripe's hosted checkout page (checkout.stripe.com) are
// Stripe's, not ours, and Stripe changes that page without telling anyone. So
// every field is tried against a list of candidates, the one that matched is
// logged, and a miss dumps a screenshot, the page HTML, and every visible
// input's id/name/placeholder into the artifacts directory. Fixing a moved
// selector is then a one-line edit to the list below, not an investigation.
//
// Usage (the shell does this; it is here so it can be run by hand too):
//   node bundle-testmode-checkout.mjs --url <payment link or session url> \
//     --email you@example.com --card 4242424242424242 --artifacts /tmp/pw \
//     [--pay-only | --submit-setup --program NAME --accent '#2c5f70' \
//      --agency-ids 'a, b, c' --deliver-to you@example.com]

import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

const CARD_FIELDS = {
  email: ["#email", "input[name='email']", "input[autocomplete='email']"],
  cardNumber: [
    "#cardNumber",
    "input[name='cardNumber']",
    "input[autocomplete='cc-number']",
    "input[placeholder='1234 1234 1234 1234']",
  ],
  cardExpiry: [
    "#cardExpiry",
    "input[name='cardExpiry']",
    "input[autocomplete='cc-exp']",
    "input[placeholder='MM / YY']",
  ],
  cardCvc: ["#cardCvc", "input[name='cardCvc']", "input[autocomplete='cc-csc']"],
  billingName: [
    "#billingName",
    "input[name='billingName']",
    "input[autocomplete='cc-name']",
    "input[name='name']",
  ],
  billingPostalCode: [
    "#billingPostalCode",
    "input[name='billingPostalCode']",
    "input[autocomplete='billing postal-code']",
    "input[name='postalCode']",
  ],
};

const SUBMIT_CANDIDATES = [
  "button[data-testid='hosted-payment-submit-button']",
  "form button[type='submit']",
  "button.SubmitButton",
];

// The "Card" entry in Checkout's payment-method accordion, as it rendered on
// 2026-09-10 (data-testid, the radio's id, and the accessible label).
const CARD_METHOD_CANDIDATES = [
  "[data-testid='card-accordion-item-button']",
  "#payment-method-accordion-item-title-card",
  "button[aria-label='Pay with card']",
];

function parseArgs(argv) {
  const args = { artifacts: "/tmp/bundle-testmode" };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    if (!flag.startsWith("--")) continue;
    const key = flag.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    const next = argv[i + 1];
    if (next === undefined || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}

const log = (...parts) => console.error("[checkout]", ...parts);

async function dump(page, artifacts, label) {
  try {
    await mkdir(artifacts, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const base = join(artifacts, `${label}-${stamp}`);
    await page.screenshot({ path: `${base}.png`, fullPage: true });
    await writeFile(`${base}.html`, await page.content(), "utf8");
    const inputs = await page.$$eval("input, select, button", (nodes) =>
      nodes
        .filter((n) => n.offsetParent !== null)
        .map((n) => ({
          tag: n.tagName.toLowerCase(),
          id: n.id || null,
          name: n.getAttribute("name"),
          type: n.getAttribute("type"),
          placeholder: n.getAttribute("placeholder"),
          testid: n.getAttribute("data-testid"),
          text: (n.textContent || "").trim().slice(0, 40) || null,
        })),
    );
    await writeFile(`${base}.fields.json`, JSON.stringify(inputs, null, 2), "utf8");
    log(`saved ${base}.png, .html and .fields.json`);
    log(`url at failure: ${page.url()}`);
  } catch (err) {
    log(`could not save artifacts: ${err.message}`);
  }
}

// Try each candidate in turn; return the one that matched, or null.
async function firstVisible(page, candidates, timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    for (const selector of candidates) {
      const locator = page.locator(selector).first();
      if ((await locator.count()) > 0 && (await locator.isVisible().catch(() => false))) {
        return { selector, locator };
      }
    }
    await page.waitForTimeout(400);
  }
  return null;
}

async function fillField(page, name, candidates, value, { required = true } = {}) {
  const found = await firstVisible(page, candidates);
  if (!found) {
    if (required) throw new Error(`no field matched for ${name}: tried ${candidates.join(", ")}`);
    log(`${name}: not present on this page, skipping`);
    return false;
  }
  await found.locator.fill(String(value));
  log(`${name}: filled via ${found.selector}`);
  return true;
}

// An expiry that is always in the future without being absurd.
function futureExpiry() {
  const now = new Date();
  const year = (now.getFullYear() + 3) % 100;
  return `12 / ${String(year).padStart(2, "0")}`;
}

async function payHostedCheckout(page, args) {
  log(`opening ${args.url}`);
  await page.goto(args.url, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});

  await fillField(page, "email", CARD_FIELDS.email, args.email, { required: false });

  // Checkout lists payment methods as a collapsed accordion (card, Cash App,
  // Affirm, Klarna, bank), and the card fields do not exist in the page until
  // "Card" is chosen. It renders after load, so wait for either the fields or
  // the accordion rather than looking once: the first real run looked once,
  // found nothing yet, skipped the click, and then failed on cardNumber.
  const cardReady = await firstVisible(page, [...CARD_FIELDS.cardNumber, ...CARD_METHOD_CANDIDATES]);
  if (!cardReady) {
    throw new Error(
      `neither the card fields nor a card payment option appeared: tried ${[
        ...CARD_FIELDS.cardNumber,
        ...CARD_METHOD_CANDIDATES,
      ].join(", ")}`,
    );
  }
  if (CARD_METHOD_CANDIDATES.includes(cardReady.selector)) {
    // The accordion item is covered by a full-width button that takes the
    // click; the radio underneath never receives one, and Playwright refuses a
    // plain click on the radio because that button "intercepts pointer
    // events". A person's click lands on the button, but Playwright cannot
    // synthesise it by coordinates either: a forced click is refused as
    // "outside of the viewport" because the cover has no box of its own. So
    // invoke the button's own click, which runs the handler a real click
    // reaches. The second and third real runs failed on those two attempts.
    const cover = page.locator("[data-testid='card-accordion-item-button']").first();
    const target = (await cover.count()) > 0 ? cover : cardReady.locator;
    await target.evaluate((el) => el.click());
    const radio = page.locator("#payment-method-accordion-item-title-card");
    if ((await radio.count()) > 0 && !(await radio.isChecked().catch(() => true))) {
      await radio.evaluate((el) => el.click());
    }
    log(`selected the card payment method via ${cardReady.selector}`);
  }

  // "Save my information for faster checkout" (Link) is ticked by default and
  // asks for a phone number before Pay will go through. A test purchase has no
  // reason to enrol in Link, so untick it rather than invent a phone number.
  const linkOptIn = page.locator("#enableStripePass");
  if ((await linkOptIn.count()) > 0 && (await linkOptIn.isChecked().catch(() => false))) {
    await linkOptIn.uncheck({ force: true });
    log("unticked the Link opt-in so no phone number is required");
  }

  await fillField(page, "cardNumber", CARD_FIELDS.cardNumber, args.card);
  await fillField(page, "cardExpiry", CARD_FIELDS.cardExpiry, futureExpiry());
  await fillField(page, "cardCvc", CARD_FIELDS.cardCvc, "123");
  await fillField(page, "billingName", CARD_FIELDS.billingName, "Test Mode Walkthrough", {
    required: false,
  });
  await fillField(page, "billingPostalCode", CARD_FIELDS.billingPostalCode, "94110", {
    required: false,
  });

  const submit = await firstVisible(page, SUBMIT_CANDIDATES);
  if (!submit) throw new Error(`no submit button matched: tried ${SUBMIT_CANDIDATES.join(", ")}`);
  log(`submitting via ${submit.selector}`);
  await submit.locator.click();

  // Stripe redirects to the Payment Link's after_completion URL, which carries
  // the session id. A session created through the API redirects to its
  // success_url, which this script sets to the same page.
  await page.waitForURL(/\/bundle\/setup\//, { timeout: 120000 });
  const sessionId = new URL(page.url()).searchParams.get("session_id");
  if (!sessionId) throw new Error(`redirected to ${page.url()} with no session_id`);
  log(`paid; session ${sessionId}`);
  return sessionId;
}

async function submitSetupForm(page, args) {
  // The response body is the only place the bundle id appears; the page shows
  // a thank-you sentence and nothing else.
  const responded = page.waitForResponse(
    (response) => response.url().endsWith("/setup") && response.request().method() === "POST",
    { timeout: 120000 },
  );

  await page.waitForSelector("#setup-form", { timeout: 30000 });
  const disabled = await page.locator("#program_name").isDisabled();
  if (disabled) {
    const status = await page.locator("#form-status").textContent();
    throw new Error(`the setup form is disabled: ${String(status).trim()}`);
  }

  await page.fill("#program_name", String(args.program));
  if (args.accent) await page.fill("#accent", String(args.accent));
  await page.fill("#agency_ids", String(args.agencyIds));
  if (args.deliverTo) await page.fill("#deliver_to", String(args.deliverTo));
  log("setup form filled; submitting");
  await page.locator("#setup-form button[type='submit']").click();

  const response = await responded;
  let body = {};
  try {
    body = await response.json();
  } catch {
    body = { error: "the setup route did not answer with JSON" };
  }
  const status = (await page.locator("#form-status").textContent()) || "";
  log(`setup answered ${response.status()}; page says: ${status.trim()}`);
  return { setup_status: response.status(), setup_body: body, page_status: status.trim() };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.url) throw new Error("--url is required");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
  const page = await context.newPage();
  const result = {};
  try {
    result.session_id = await payHostedCheckout(page, args);
    result.paid = true;
    if (args.submitSetup) {
      Object.assign(result, await submitSetupForm(page, args));
      result.bundle_id = result.setup_body?.bundle_id ?? "";
    }
  } catch (err) {
    await dump(page, args.artifacts, "failure");
    await browser.close();
    log(`failed: ${err.message}`);
    process.exitCode = 1;
    process.stdout.write(`${JSON.stringify({ ...result, error: err.message }, null, 2)}\n`);
    return;
  }
  await browser.close();
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch((err) => {
  console.error("[checkout] unexpected:", err);
  process.exit(1);
});
