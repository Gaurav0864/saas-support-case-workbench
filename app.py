"""Run a local, fictional SaaS support incident investigation lab."""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit


DEFAULT_CASES_FILE = Path(__file__).with_name("data") / "cases.json"
EVENT_FIELDS = ("timestamp", "service", "level", "message", "request_id")
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
        events = case.get("events")
        if not isinstance(events, list) or not events:
            raise CaseDataError(
                f"Case {case_id} must have at least one correlated evidence event."
            )

        cleaned_events = []
        for event_index, event in enumerate(events, start=1):
            if not isinstance(event, dict):
                raise CaseDataError(
                    f"Evidence event {event_index} in case {case_id} must be an object."
                )
            invalid_event_fields = [
                field
                for field in EVENT_FIELDS
                if not isinstance(event.get(field), str) or not event[field].strip()
            ]
            if invalid_event_fields:
                raise CaseDataError(
                    f"Evidence event {event_index} in case {case_id} has missing "
                    f"or invalid fields: {', '.join(invalid_event_fields)}."
                )
            if event["request_id"].strip() != cleaned_case["request_id"]:
                raise CaseDataError(
                    f"Evidence event {event_index} in case {case_id} has a "
                    "request ID that does not match the case."
                )
            cleaned_events.append(
                {field: event[field].strip() for field in EVENT_FIELDS}
            )

        cleaned_case["events"] = cleaned_events
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
        if status == 429:
            return (
                "Rate limit response observed; the cause and recovery are not confirmed.",
                [
                    "Check the response's retry guidance and the integration's retry behavior.",
                    "Compare request volume with the documented limit and affected time window.",
                    "Check whether retries could be increasing the request volume.",
                ],
            )
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

    evidence_summary = " ".join(
        "{} {}: {}".format(event["service"], event["level"], event["message"])
        for event in case["events"]
    )
    handoff = (
        f"{case['case_id']} - {case['title']}. "
        f"Impact: {case['customer_impact']} "
        f"Observed: HTTP {case['http_status']} for request "
        f"{case['request_id']}. Correlated evidence: {evidence_summary} "
        "Please investigate the attached facts; root cause is not yet confirmed."
    )
    customer_update = (
        f"Thanks for reporting this. We understand the impact: "
        f"{case['customer_impact']} "
        f"We are reviewing the reported HTTP {case['http_status']} response "
        f"for request {case['request_id']} and will share an update when we "
        "have verified more."
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
        "evidence_events": case["events"],
        "assessment": assessment,
        "recommended_checks": checks,
        "customer_update_draft": customer_update,
        "handoff_draft": handoff,
    }


def simulate_case(case):
    """Return a synthetic request trace without contacting an external service."""
    request_id = "req-sim-{}".format(uuid.uuid4().hex[:8])
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if timestamp.endswith("+00:00"):
        timestamp = timestamp[:-6] + "Z"

    if case["http_status"] in (401, 403):
        service, level, message = (
            "identity-service",
            "WARN",
            "Authentication failed: token is expired or invalid; credential values redacted.",
        )
    elif case["http_status"] == 429:
        service, level, message = (
            "rate-limiter",
            "WARN",
            "Synthetic request throttled; retry-after guidance was returned.",
        )
    elif case["http_status"] >= 500:
        service, level, message = (
            "content-player",
            "ERROR",
            "Synthetic upstream dependency timed out; root cause is not confirmed.",
        )
    else:
        service, level, message = (
            "application",
            "INFO",
            "Synthetic request completed; compare returned data with the reported behavior.",
        )

    events = [
        {
            "timestamp": timestamp,
            "service": "api-gateway",
            "level": "INFO",
            "message": "Synthetic request received for {}.".format(case["product_area"]),
            "request_id": request_id,
        },
        {
            "timestamp": timestamp,
            "service": service,
            "level": level,
            "message": message,
            "request_id": request_id,
        },
        {
            "timestamp": timestamp,
            "service": "api-gateway",
            "level": "INFO" if case["http_status"] < 400 else "WARN",
            "message": "Synthetic response completed with HTTP {}.".format(
                case["http_status"]
            ),
            "request_id": request_id,
        },
    ]
    return {
        "case_id": case["case_id"],
        "request_id": request_id,
        "http_status": case["http_status"],
        "note": "This is simulated evidence; no external request was made.",
        "events": events,
    }


def format_simulation(simulation):
    """Render a simulated request and its correlated events for the CLI."""
    lines = [
        "Simulated request for {}: HTTP {}".format(
            simulation["case_id"], simulation["http_status"]
        ),
        "Request ID: {}".format(simulation["request_id"]),
        simulation["note"],
        "",
        "Correlated events:",
    ]
    lines.extend(
        "- {timestamp} {service} {level}: {message}".format(**event)
        for event in simulation["events"]
    )
    return "\n".join(lines)


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
        "Evidence timeline (matched by request ID):",
    ]
    lines.extend(
        "- {timestamp} {service} {level}: {message}".format(**event)
        for event in report["evidence_events"]
    )
    lines.extend([
        "",
        f"Starting assessment: {report['assessment']}",
        "",
        "Suggested checks (verify before drawing conclusions):",
    ])
    lines.extend(f"- {check}" for check in report["recommended_checks"])
    lines.extend([
        "",
        "Draft customer update:",
        report["customer_update_draft"],
        "",
        "Draft engineering handoff:",
        report["handoff_draft"],
    ])
    return "\n".join(lines)


def create_server(cases, host="127.0.0.1", port=8000):
    """Create the local incident-lab server."""
    cases_by_id = {case["case_id"]: case for case in cases}
    project_dir = Path(__file__).parent
    templates_dir = project_dir / "templates"
    static_dir = project_dir / "static"

    def render_template(template_name, values):
        template = (templates_dir / template_name).read_text(encoding="utf-8")
        for name, value in values.items():
            template = template.replace("{{" + name + "}}", value)
        return template

    class CaseRequestHandler(BaseHTTPRequestHandler):
        def _send_bytes(self, status, content_type, body):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, status, content):
            self._send_bytes(
                status, "text/html; charset=utf-8", content.encode("utf-8")
            )

        def _send_json(self, status, data):
            body = json.dumps(data).encode("utf-8")
            self._send_bytes(status, "application/json; charset=utf-8", body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path.startswith("/static/"):
                static_name = path[len("/static/"):]
                content_types = {
                    "app.js": "text/javascript; charset=utf-8",
                    "style.css": "text/css; charset=utf-8",
                }
                content_type = content_types.get(static_name)
                if content_type is not None:
                    try:
                        body = (static_dir / static_name).read_bytes()
                    except OSError as error:
                        self._send_json(500, {"error": str(error)})
                        return
                    self._send_bytes(200, content_type, body)
                    return

            if path == "/":
                case_cards = "".join(
                    "<article class=\"case\"><span class=\"tag\">{}</span>"
                    "<h2>{}</h2><p>{}</p><p><span class=\"status\">HTTP {}</span>"
                    " &middot; {}</p><a href=\"/cases/{}\">Open investigation &rarr;</a>"
                    "</article>".format(
                        escape(case["product_area"]),
                        escape(case["title"]),
                        escape(case["symptom"]),
                        case["http_status"],
                        escape(case["case_id"]),
                        quote(case["case_id"], safe=""),
                    )
                    for case in cases
                )
                content = render_template("index.html", {"CASE_CARDS": case_cards})
                self._send_html(200, content)
                return

            if path.startswith("/cases/"):
                case_id = unquote(path[len("/cases/"):])
                case = cases_by_id.get(case_id)
                if case is not None:
                    report = analyze_case(case)
                    checks = "".join(
                        "<li>{}</li>".format(escape(check))
                        for check in report["recommended_checks"]
                    )
                    events = "".join(
                        "<li><time>{}</time> &middot; <strong>{}</strong> "
                        "<span class=\"tag\">{}</span><br>{}</li>".format(
                            escape(event["timestamp"]),
                            escape(event["service"]),
                            escape(event["level"]),
                            escape(event["message"]),
                        )
                        for event in report["evidence_events"]
                    )
                    values = {
                        "CASE_ID": escape(report["case_id"]),
                        "HTTP_STATUS": str(report["http_status"]),
                        "TITLE": escape(report["title"]),
                        "SYMPTOM": escape(report["symptom"]),
                        "CUSTOMER_IMPACT": escape(report["customer_impact"]),
                        "AFFECTED_SCOPE": escape(report["affected_scope"]),
                        "RECENT_CHANGE": escape(report["recent_change"]),
                        "REQUEST_ID": escape(report["request_id"]),
                        "EVIDENCE_EVENTS": events,
                        "CHECKS": checks,
                        "ASSESSMENT": escape(report["assessment"]),
                        "CUSTOMER_UPDATE": escape(report["customer_update_draft"]),
                        "HANDOFF": escape(report["handoff_draft"]),
                        "CASE_ID_ATTRIBUTE": escape(report["case_id"]),
                    }
                    content = render_template("case.html", values)
                    self._send_html(200, content)
                    return

            content = render_template("not_found.html", {})
            self._send_html(404, content)

        def do_POST(self):
            path = urlsplit(self.path).path
            prefix = "/api/simulations/"
            if path.startswith(prefix):
                case_id = unquote(path[len(prefix):])
                case = cases_by_id.get(case_id)
                if case is not None:
                    self._send_json(200, simulate_case(case))
                    return
            self._send_json(404, {"error": "Incident not found."})

    return ThreadingHTTPServer((host, port), CaseRequestHandler)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Investigate fictional SaaS incidents with sample evidence and "
            "local simulations."
        )
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
        "--simulate",
        action="store_true",
        help="Run a synthetic local request for the selected --case-id.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the browser app at http://127.0.0.1:8000.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the analysis as JSON.",
    )
    args = parser.parse_args(argv)

    if args.json and not args.case_id:
        parser.error("--json requires --case-id.")
    if args.simulate and (not args.case_id or args.list_cases):
        parser.error("--simulate requires --case-id and cannot be combined with --list-cases.")
    if args.serve and (args.list_cases or args.case_id or args.simulate):
        parser.error("--serve cannot be combined with CLI case options.")
    if not args.list_cases and not args.case_id and not args.serve:
        parser.error("Choose --list-cases, --serve, or provide --case-id.")

    try:
        cases = load_cases()
    except CaseDataError as error:
        print(str(error), file=sys.stderr)
        return 2

    if args.serve:
        server = create_server(cases)
        print("Serving support cases at http://127.0.0.1:8000", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0

    if args.list_cases:
        for case in cases:
            print(f"{case['case_id']}: {case['title']} ({case['product_area']})")
        return 0

    case = next((item for item in cases if item["case_id"] == args.case_id), None)
    if case is None:
        print(f"Unknown case ID: {args.case_id}", file=sys.stderr)
        return 1

    if args.simulate:
        simulation = simulate_case(case)
        if args.json:
            print(json.dumps(simulation, indent=2))
        else:
            print(format_simulation(simulation))
        return 0

    report = analyze_case(case)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
