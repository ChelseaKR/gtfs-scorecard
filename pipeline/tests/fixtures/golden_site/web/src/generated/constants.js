// GENERATED — do not edit; run `scorecard render-constants`.
// Source of truth: pipeline/src/scorecard_pipeline/constants_export.py
// (grade bands from score.py, freshness thresholds from metrics.py, category
// and severity labels from site_shell.py, rule links from rule_links.py).
// pipeline/tests/test_generated_constants.py fails CI when this file drifts.

export const STALE_FEED_DAYS = 365;

export const SERVICE_HORIZON_REVIEW_YEARS = 10;

export const GRADE_BANDS = [
  {
    "grade": "A",
    "min_score": 90.0
  },
  {
    "grade": "B",
    "min_score": 80.0
  },
  {
    "grade": "C",
    "min_score": 70.0
  },
  {
    "grade": "D",
    "min_score": 60.0
  },
  {
    "grade": "F",
    "min_score": 0.0
  }
];

export const GRADE_ORDER = [
  "F",
  "D",
  "C",
  "B",
  "A"
];

export const GRADE_RANK = {
  "A": 4,
  "B": 3,
  "C": 2,
  "D": 1,
  "F": 0
};

export const CATEGORY_LABELS = {
  "completeness": "Rider experience",
  "correctness": "Correctness",
  "freshness": "Freshness",
  "realtime": "Realtime quality"
};

export const CATEGORY_ORDER = [
  "correctness",
  "freshness",
  "completeness",
  "realtime"
];

export const SEVERITY_LABELS = {
  "ERROR": "Error",
  "INFO": "Info",
  "WARNING": "Warning"
};

export const TIER_LABELS = {
  "large": "large",
  "medium": "mid-size",
  "small": "small"
};

export const FIX_DOCS_BASE = "https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/fixes/";

export const VALIDATOR_RULES_PAGE = "https://gtfs-validator.mobilitydata.org/rules.html";

export const AUTHORITY_LABELS = {
  "best_practice": "GTFS Best Practices",
  "realtime_reference": "GTFS-Realtime reference",
  "reference": "GTFS Schedule reference",
  "validator": "MobilityData GTFS Validator rules"
};

export const RULE_LINKS = {
  "big_gap_in_service": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#big_gap_in_service-rule"
  },
  "equal_shape_distance_same_coordinates": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#equal_shape_distance_same_coordinates-rule"
  },
  "expired_calendar": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#expired_calendar-rule"
  },
  "fast_travel_between_consecutive_stops": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#fast_travel_between_consecutive_stops-rule"
  },
  "fast_travel_between_far_stops": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#fast_travel_between_far_stops-rule"
  },
  "feed_expiration_date30_days": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#feed_expiration_date30_days-rule"
  },
  "feed_expiration_date7_days": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#feed_expiration_date7_days-rule"
  },
  "invalid_currency_amount": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#invalid_currency_amount-rule"
  },
  "missing_feed_contact_email_and_url": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#missing_feed_contact_email_and_url-rule"
  },
  "missing_recommended_field": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#missing_recommended_field-rule"
  },
  "missing_recommended_file": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#missing_recommended_file-rule"
  },
  "missing_required_column": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#missing_required_column-rule"
  },
  "missing_timepoint_value": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#missing_timepoint_value-rule"
  },
  "mixed_case_recommended_field": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#mixed_case_recommended_field-rule"
  },
  "route_color_contrast": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#route_color_contrast-rule"
  },
  "scorecard_feed_expired": {
    "authority": "GTFS Best Practices",
    "canonical": null,
    "kind": "best_practice",
    "url": "https://gtfs.org/schedule/best-practices/#dataset-publishing-general-practices"
  },
  "scorecard_feed_expiring_soon": {
    "authority": "GTFS Best Practices",
    "canonical": null,
    "kind": "best_practice",
    "url": "https://gtfs.org/schedule/best-practices/#dataset-publishing-general-practices"
  },
  "scorecard_flex_no_booking_rules": {
    "authority": "GTFS Schedule reference",
    "canonical": null,
    "kind": "reference",
    "url": "https://gtfs.org/schedule/reference/#booking_rulestxt"
  },
  "scorecard_missing_feed_info_dates": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": "missing_feed_info_date",
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#missing_feed_info_date-rule"
  },
  "scorecard_missing_headsigns": {
    "authority": "GTFS Best Practices",
    "canonical": null,
    "kind": "best_practice",
    "url": "https://gtfs.org/schedule/best-practices/#tripstxt"
  },
  "scorecard_no_fare_data": {
    "authority": "GTFS Best Practices",
    "canonical": null,
    "kind": "best_practice",
    "url": "https://gtfs.org/schedule/best-practices/#fare_attributestxt"
  },
  "scorecard_no_feed_contact": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": "missing_feed_contact_email_and_url",
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#missing_feed_contact_email_and_url-rule"
  },
  "scorecard_rt_service_alerts_unreachable": {
    "authority": "GTFS-Realtime reference",
    "canonical": null,
    "kind": "realtime_reference",
    "url": "https://gtfs.org/documentation/realtime/reference/#message-alert"
  },
  "scorecard_rt_trip_coverage": {
    "authority": "GTFS-Realtime reference",
    "canonical": null,
    "kind": "realtime_reference",
    "url": "https://gtfs.org/documentation/realtime/reference/#message-tripupdate"
  },
  "scorecard_rt_trip_updates_unreachable": {
    "authority": "GTFS-Realtime reference",
    "canonical": null,
    "kind": "realtime_reference",
    "url": "https://gtfs.org/documentation/realtime/reference/#message-tripupdate"
  },
  "scorecard_rt_vehicle_positions_unreachable": {
    "authority": "GTFS-Realtime reference",
    "canonical": null,
    "kind": "realtime_reference",
    "url": "https://gtfs.org/documentation/realtime/reference/#message-vehicleposition"
  },
  "scorecard_station_no_pathways": {
    "authority": "GTFS Schedule reference",
    "canonical": null,
    "kind": "reference",
    "url": "https://gtfs.org/schedule/reference/#pathwaystxt"
  },
  "scorecard_stop_names_all_caps": {
    "authority": "GTFS Best Practices",
    "canonical": null,
    "kind": "best_practice",
    "url": "https://gtfs.org/schedule/best-practices/#stopstxt"
  },
  "scorecard_wheelchair_accessible_unknown": {
    "authority": "GTFS Schedule reference",
    "canonical": null,
    "kind": "reference",
    "url": "https://gtfs.org/schedule/reference/#tripstxt"
  },
  "scorecard_wheelchair_boarding_unknown": {
    "authority": "GTFS Schedule reference",
    "canonical": null,
    "kind": "reference",
    "url": "https://gtfs.org/schedule/reference/#stopstxt"
  },
  "service_has_no_active_day_of_the_week": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#service_has_no_active_day_of_the_week-rule"
  },
  "service_window_outside_feed_period": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#service_window_outside_feed_period-rule"
  },
  "stop_too_far_from_shape": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#stop_too_far_from_shape-rule"
  },
  "stop_too_far_from_shape_using_user_distance": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#stop_too_far_from_shape_using_user_distance-rule"
  },
  "stop_without_stop_time": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#stop_without_stop_time-rule"
  },
  "trip_coverage_not_active_for_next7_days": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#trip_coverage_not_active_for_next7_days-rule"
  },
  "trip_distance_exceeds_shape_distance_below_threshold": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#trip_distance_exceeds_shape_distance_below_threshold-rule"
  },
  "unknown_column": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#unknown_column-rule"
  },
  "unknown_file": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#unknown_file-rule"
  },
  "unused_shape": {
    "authority": "MobilityData GTFS Validator rules",
    "canonical": null,
    "kind": "validator",
    "url": "https://gtfs-validator.mobilitydata.org/rules.html#unused_shape-rule"
  }
};

export const UNIVERSAL_GUIDANCE = {
  "category_notes": {
    "completeness": "GTFS Best Practices for rider-facing fields. MobilityData grading covers stop names and headsigns.",
    "correctness": "GTFS Schedule best practices, checked by the MobilityData validator. MobilityData grading covers stop locations, route names, and colors. Google Transit requires a feed to pass validation for publication.",
    "freshness": "GTFS Schedule best practices call for a dataset that stays current. An expired calendar can remove service from Google Transit and other rider trip planners.",
    "realtime": "GTFS-Realtime best practices: a stable URL, high uptime, and frequent updates."
  },
  "name": "GTFS and rider-information guidance",
  "note": "The scorecard is a data-quality lens, not a compliance determination. Its universal references describe good GTFS and useful rider information.",
  "references": [
    {
      "name": "GTFS Schedule Best Practices",
      "url": "https://gtfs.org/schedule/best-practices/"
    },
    {
      "name": "GTFS-Realtime Best Practices",
      "url": "https://gtfs.org/realtime/best-practices/"
    },
    {
      "name": "MobilityData grading scheme",
      "url": "https://github.com/MobilityData/gtfs-grading-scheme"
    },
    {
      "name": "Google Transit publication guidance",
      "url": "https://support.google.com/transitpartners/answer/1111481"
    }
  ],
  "scope": "all"
};

export const US_NTD_GUIDANCE = {
  "category_notes": {
    "correctness": "FTA NTD readiness also checks that the published feed is valid.",
    "freshness": "FTA NTD readiness also checks that the published feed is current."
  },
  "kind": "requirement",
  "name": "FTA National Transit Database GTFS requirement",
  "note": "For US NTD reporters with qualifying service, the federal requirement calls for a public, valid, current GTFS feed and annual certification. For RY2026, the submission also needs a stable agency_id for each represented reporter, crosswalked to its NTD ID on P-50.",
  "scope": "US",
  "url": "https://www.transit.dot.gov/ntd"
};

export const JURISDICTION_GUIDANCE = {
  "US-CA": {
    "kind": "guideline",
    "name": "California Transit Data Guidelines",
    "note": "Caltrans' published quality guidelines and compliance checklist; this rubric is anchored to them.",
    "scope": "US-CA",
    "url": "https://dot.ca.gov/cal-itp/california-transit-data-guidelines"
  }
};

export const SUPPORT_RESOURCES = {
  "US-CO": {
    "kind": "support",
    "name": "CDOT Digital Transit Mobility",
    "note": "Colorado's program coordinating GTFS data across transit providers.",
    "scope": "US-CO",
    "url": "https://www.codot.gov/programs/innovativemobility/mobility-technology/digital-transit-mobility"
  },
  "US-MI": {
    "kind": "support",
    "name": "Michigan Public Transit Open Data Program",
    "note": "MDOT's program helping agencies produce and maintain GTFS and GTFS-Flex.",
    "scope": "US-MI",
    "url": "https://miruralmobility.org/"
  },
  "US-MN": {
    "kind": "support",
    "name": "MnDOT Transit",
    "note": "Minnesota's statewide transit program and data resources.",
    "scope": "US-MN",
    "url": "https://www.dot.state.mn.us/transit/"
  },
  "US-OR": {
    "kind": "support",
    "name": "Oregon ODOT Public Transportation",
    "note": "ODOT's Public Transportation Division, which supports statewide GTFS.",
    "scope": "US-OR",
    "url": "https://www.oregon.gov/odot/rptd/pages/index.aspx"
  },
  "US-WA": {
    "kind": "support",
    "name": "WSDOT Transportation Data",
    "note": "WSDOT builds and publishes GTFS for Washington transit agencies.",
    "scope": "US-WA",
    "url": "https://wsdot.wa.gov/about/transportation-data"
  }
};

export const US_STATE_SUBDIVISION_CODES = {
  "California": "US-CA",
  "Colorado": "US-CO",
  "Michigan": "US-MI",
  "Minnesota": "US-MN",
  "Oregon": "US-OR",
  "Washington": "US-WA"
};
