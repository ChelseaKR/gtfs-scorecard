// GENERATED — do not edit; run `scorecard render-constants`.
// Source of truth: pipeline/src/scorecard_pipeline/constants_export.py
// (grade bands from score.py, STALE_FEED_DAYS from metrics.py, category and
// severity labels from site_shell.py, rule links from rule_links.py).
// pipeline/tests/test_generated_constants.py fails CI when this file drifts.

export const STALE_FEED_DAYS = 365;

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
