"""Practice structured support investigations using fictional case data."""

import argparse
import json
from pathlib import Path
import sys


DEFAULT_CASES_FILE = Path(__file__).with_name("data") / "cases.json"
REQUIRED_TEXT_FIELDS = (
    "case_id",
    "title",
    "product_area",
    "symptom",
    "request_id",
    "affected_scope",
    "recent_change",
    "customer_impact",
)


class CaseDataError(ValueError):
    """Raised when a case file does not match the expected format."""


def load_cases(path=DEFAULT_CASES_FILE):
    """Read and validate the JSON case list."""
    try:
        with Path(path).open(encoding="utf-8") as case_file:
            data = json.load(case_file)
    except (OSError, json.JSONDecodeError) as error:
        raise CaseDataError(f"Could not read case file: {error}") from error

    if not isinstance(data, list):
        raise CaseDataError("Case file must contain a JSON list.")

    cases = []
    seen_ids = set()
    for index, case in enumerate(data, start=1):
        if not isinstance(case, dict):
            raise CaseDataError(f"Case {index} must be a JSON object.")

        invalid_fields = [
            field
            for field in REQUIRED_TEXT_FIELDS
            if not isinstance(case.get(field), str) or not case[field].strip()
        ]
        if invalid_fields:
            raise CaseDataError(
                f"Case {index} has missing or invalid text fields: "
                f"{', '.join(invalid_fields)}."
            )

        status = case.get("http_status")
        if (
            not isinstance(status, int)
            or isinstance(status, bool)
            or not 100 <= status <= 599
        ):
            raise CaseDataError(
                f"Case {case['case_id']} must have an HTTP status from 100 to 599."
            )

        case_id = case["case_id"].strip()
        if case_id in seen_ids:
            raise CaseDataError(f"Duplicate case ID: {case_id}.")
        seen_ids.add(case_id)

        cleaned_case = {
            field: case[field].strip() for field in REQUIRED_TEXT_FIELDS
        }
        cleaned_case["http_status"] = status
        cases.append(cleaned_case)

    return cases


def _troubleshooting_guidance(status):
    """Return a cautious investigation category and checks for a status code."""
    if status in (401, 403):
        return (
            "Authentication or permission issue observed.",
            [
                "Confirm the affected user or integration and the exact time.",
                "Check token expiry, scopes, and access policy without sharing secrets.",
                "Compare with a known-good request using an approved test account.",
            ],
        )
    if 400 <= status < 500:
        return (
            "Request or client-side issue observed.",
            [
                "Check the endpoint, request format, and required fields.",
                "Confirm whether the issue affects one request or multiple users.",
                "Compare with a successful request from the same workflow.",
            ],
        )
    if status >= 500:
        return (
            "Server or dependency error observed; the cause is not confirmed.",
            [
                "Correlate the request ID in authorized service logs.",
                "Check dependency health, latency, and nearby failures.",
                "Review recent changes and confirm recovery with a new request.",
            ],
        )
    return (
        "The recorded request succeeded; investigate the reported behavior.",
        [
            "Confirm the user's steps, expected result, and actual result.",
            "Check whether the data may be delayed or cached.",
            "Compare the same workflow in an approved test account.",
        ],
    )


def analyze_case(case):
    """Build a troubleshooting plan and draft handoff from one validated case."""
    assessment, checks = _troubleshooting_guidance(case["http_status"])
    if "no recent change" not in case["recent_change"].lower():
        checks.append("Verify the reported recent change and its timing.")

    handoff = (
        f"{case['case_id']} - {case['title']}. "
        f"Impact: {case['customer_impact']} "
        f"Observed: HTTP {case['http_status']} for request "
        f"{case['request_id']}. "
        "Please investigate the attached facts; root cause is not yet confirmed."
    )

    return {
        "case_id": case["case_id"],
        "title": case["title"],
        "product_area": case["product_area"],
        "symptom": case["symptom"],
        "request_id": case["request_id"],
        "http_status": case["http_status"],
        "affected_scope": case["affected_scope"],
        "recent_change": case["recent_change"],
        "customer_impact": case["customer_impact"],
        "assessment": assessment,
        "recommended_checks": checks,
        "handoff_draft": handoff,
    }


def format_report(report):
    """Render a readable case report for a support investigation."""
    lines = [
        f"Case: {report['case_id']} - {report['title']}",
        f"Product area: {report['product_area']}",
        f"Symptom: {report['symptom']}",
        f"Customer impact: {report['customer_impact']}",
        f"Affected scope: {report['affected_scope']}",
        f"Request ID: {report['request_id']}",
        f"Observed HTTP status: {report['http_status']}",
        f"Reported recent change: {report['recent_change']}",
        "",
        f"Starting assessment: {report['assessment']}",
        "",
        "Suggested checks (verify before drawing conclusions):",
    ]
    lines.extend(f"- {check}" for check in report["recommended_checks"])
    lines.extend(["", "Draft engineering handoff:", report["handoff_draft"]])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Practice a structured investigation of a fictional SaaS case."
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="List available fictional cases.",
    )
    parser.add_argument(
        "--case-id",
        help="Analyze a case, for example CASE-1001.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the analysis as JSON.",
    )
    args = parser.parse_args(argv)

    if args.json and not args.case_id:
        parser.error("--json requires --case-id.")
    if not args.list_cases and not args.case_id:
        parser.error("Choose --list-cases or provide --case-id.")

    try:
        cases = load_cases()
    except CaseDataError as error:
        print(str(error), file=sys.stderr)
        return 2

    if args.list_cases:
        for case in cases:
            print(f"{case['case_id']}: {case['title']} ({case['product_area']})")
        return 0

    case = next((item for item in cases if item["case_id"] == args.case_id), None)
    if case is None:
        print(f"Unknown case ID: {args.case_id}", file=sys.stderr)
        return 1

    report = analyze_case(case)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
