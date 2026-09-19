// @ts-check
/**
 * What a finding costs, as the app words it.
 *
 * Every function here returns plain text. The caller decides the markup and
 * escapes it, so nothing in this file touches the DOM.
 *
 * The rule that shapes all of it: an absence is never drawn as a value. A share
 * is worded only when the block says it is known (an empty reason, a share
 * between 0 and 1, counts that agree with it). Anything else, including a block
 * that contradicts itself, reads as its reason in words. Rider-trips and need
 * are never worded as numbers here at all: the published record states them as
 * not joined here, and a joined number must name its source and its date,
 * which the record does not carry (issue #367, owner decision of 2026-09-17).
 * The agency page adds them from dated snapshots when it renders.
 *
 * The wording is shared with the static pages. It is defined once, in
 * pipeline/src/scorecard_pipeline/consequence.py, and reaches this file through
 * the generated constants; pipeline/tests/test_consequence_web.py walks both
 * implementations over the same inputs.
 */
import { CONSEQUENCE_COPY as COPY } from "./generated/constants.js";
import { formatNumber } from "./locale.js";

/** The denominators a reach can be counted against. `none` is a finding with
 *  no countable share, so it is an absence, never a share of zero. */
const COUNTABLE_BASES = new Set(["stops", "boardable_stops", "routes", "trips"]);

/** How far a stored share may sit from affected / total. The publisher rounds
 *  the share to four places, so anything wider is a record that disagrees with
 *  itself. */
const SHARE_TOLERANCE = 0.00006;

/** @param {string} template @param {Record<string, string>} params */
function fill(template, params) {
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    Object.prototype.hasOwnProperty.call(params, name) ? params[name] : match,
  );
}

/** @param {unknown} value @param {number} minimum */
function isCount(value, minimum) {
  return typeof value === "number" && Number.isInteger(value) && value >= minimum;
}

/** @param {unknown} value @returns {value is Record<string, any>} */
function isObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Round as Python does: a half goes to the even neighbor, so 12.5 is 12 and
 *  13.5 is 14, as on the static pages. Math.round would send both up.
 *  @param {number} value */
function roundHalfEven(value) {
  const floor = Math.floor(value);
  const rest = value - floor;
  if (rest > 0.5) return floor + 1;
  if (rest < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

/** @param {number} share a fraction between 0 and 1, for a partial share only */
function percentPhrase(share) {
  const pct = share * 100;
  if (pct < 1) return COPY.reach.percent_under_one;
  if (pct >= 99.5) return COPY.reach.percent_nearly_all;
  return fill(COPY.reach.percent_about, { percent: String(roundHalfEven(pct)) });
}

/** Whether a reach block states a share the reader can rely on: known basis,
 *  an empty reason, whole-number counts that agree with each other, and a share
 *  that matches them. Anything short of all of that is an absence.
 *  @param {unknown} reach */
export function reachIsKnown(reach) {
  if (!isObject(reach)) return false;
  if (!COUNTABLE_BASES.has(reach.basis)) return false;
  if (typeof reach.basis_label !== "string" || !reach.basis_label.trim()) return false;
  if (reach.reason !== "") return false;
  if (!isCount(reach.affected, 0) || !isCount(reach.total, 1)) return false;
  if (reach.affected > reach.total) return false;
  if (typeof reach.share !== "number" || !Number.isFinite(reach.share)) return false;
  return Math.abs(reach.share - reach.affected / reach.total) <= SHARE_TOLERANCE;
}

/** One sentence for the reach of a finding: what fixing it covers, or the
 *  reason no share is stated.
 *  @param {unknown} reach */
export function reachSentence(reach) {
  if (!reachIsKnown(reach)) {
    const block = isObject(reach) ? reach : {};
    const reason = typeof block.reason === "string" ? block.reason : "";
    if (Object.prototype.hasOwnProperty.call(COPY.reach_absence, reason))
      return COPY.reach_absence[reason];
    const label = typeof block.basis_label === "string" && block.basis_label.trim();
    return fill(COPY.reach.not_published, { basis: label || COPY.reach.network_noun });
  }
  const reachBlock = /** @type {Record<string, any>} */ (reach);
  const params = {
    total: formatNumber(reachBlock.total),
    affected: formatNumber(reachBlock.affected),
    basis: reachBlock.basis_label,
  };
  if (reachBlock.affected === 0) return fill(COPY.reach.none_affected, params);
  if (reachBlock.affected === reachBlock.total) return fill(COPY.reach.all_affected, params);
  return fill(COPY.reach.partial, { ...params, share: percentPhrase(reachBlock.share) });
}

/** The reach sentence for one finding, or null when the record carries no
 *  consequence block for it (a scorecard published before schema 1.19).
 *  @param {any} finding */
export function findingReach(finding) {
  const block = finding?.consequence;
  if (!isObject(block) || !isObject(block.reach)) return null;
  return { text: reachSentence(block.reach), known: reachIsKnown(block.reach) };
}

/** The consequence block shared by a whole record. Ridership and need belong
 *  to the feed, not to one finding, so every block on a record says the same
 *  thing about them; the first one found speaks for all.
 *  @param {any} artifact */
export function feedConsequence(artifact) {
  /** @type {any[]} */
  const findings = [...(Array.isArray(artifact?.top_fixes) ? artifact.top_fixes : [])];
  for (const category of Object.values(artifact?.categories || {})) {
    const list = /** @type {any} */ (category)?.findings;
    if (Array.isArray(list)) findings.push(...list);
  }
  for (const finding of findings) {
    const block = finding?.consequence;
    if (isObject(block) && isObject(block.ridership) && isObject(block.served_area_need))
      return block;
  }
  return null;
}

/** One feed-level line: the reason a value is not shown here, and whether the
 *  agency page can supply it. A value that arrives without a source and date is
 *  treated the same way, as not shown.
 *  @param {any} block
 *  @param {Record<string, string>} absence
 *  @param {string} unknown
 *  @param {string} valueKey
 *  @param {string} notJoined */
function contextLine(block, absence, unknown, valueKey, notJoined) {
  if (!isObject(block)) return { text: unknown, pointsToAgencyPage: false };
  const reason = typeof block.reason === "string" ? block.reason : "";
  if (reason === "" && block[valueKey] !== null && block[valueKey] !== undefined) {
    // The record holds a value but no source or snapshot date beside it, and a
    // joined number must carry both. It is not shown.
    return { text: absence.undated_snapshot, pointsToAgencyPage: true };
  }
  if (reason === "not_joined_here") return { text: notJoined, pointsToAgencyPage: true };
  if (Object.prototype.hasOwnProperty.call(absence, reason))
    return { text: absence[reason], pointsToAgencyPage: false };
  return { text: unknown, pointsToAgencyPage: false };
}

/** The two feed-level lines under the fixes: annual rider-trips and transit
 *  need, each as the reason it is not shown here. `notJoined` carries the app's
 *  own wording for a record that leaves the join to the agency page.
 *  @param {any} consequence
 *  @param {{ridership: string, need: string}} notJoined */
export function feedContext(consequence, notJoined) {
  const ridership = contextLine(
    consequence?.ridership,
    COPY.ridership_absence,
    COPY.ridership_unknown,
    "annual_rider_trips",
    notJoined.ridership,
  );
  const need = contextLine(
    consequence?.served_area_need,
    COPY.need_absence,
    COPY.need_unknown,
    "tier",
    notJoined.need,
  );
  return {
    ridership: ridership.text,
    need: need.text,
    pointsToAgencyPage: ridership.pointsToAgencyPage || need.pointsToAgencyPage,
  };
}

/** The heading and closing sentence the static pages use, so both surfaces say
 *  the same thing. */
export const CONTEXT_HEADING = COPY.heading;
export const NOT_A_RANKING = COPY.not_a_ranking;
