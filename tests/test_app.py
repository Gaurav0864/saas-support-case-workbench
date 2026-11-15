import io
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from app import (
    CaseDataError,
    analyze_case,
    create_server,
    load_cases,
    main,
    simulate_case,
)


class SupportCaseWorkbenchTests(unittest.TestCase):
    def test_sample_cases_load_and_server_error_gets_cautious_checks(self):
        cases = load_cases()
        case = next(item for item in cases if item["case_id"] == "CASE-1001")

        report = analyze_case(case)

        self.assertIn("cause is not confirmed", report["assessment"])
        self.assertTrue(any("request ID" in check for check in report["recommended_checks"]))
        self.assertIn("req-demo-a17", report["handoff_draft"])

    def test_authentication_case_does_not_recommend_sharing_secrets(self):
        case = next(
            item for item in load_cases() if item["case_id"] == "CASE-1002"
        )

        report = analyze_case(case)

        self.assertIn("Authentication", report["assessment"])
        self.assertTrue(
            any("without sharing secrets" in check for check in report["recommended_checks"])
        )

    def test_rate_limit_case_gets_retry_and_volume_checks(self):
        case = next(
            item for item in load_cases() if item["case_id"] == "CASE-1004"
        )

        report = analyze_case(case)

        self.assertIn("Rate limit", report["assessment"])
        self.assertTrue(any("retry" in check for check in report["recommended_checks"]))
        self.assertEqual(len(report["evidence_events"]), 2)

    def test_simulation_uses_one_fresh_id_for_all_events(self):
        case = next(
            item for item in load_cases() if item["case_id"] == "CASE-1004"
        )

        first = simulate_case(case)
        second = simulate_case(case)

        self.assertEqual(first["http_status"], 429)
        self.assertTrue(first["request_id"].startswith("req-sim-"))
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertEqual(
            {event["request_id"] for event in first["events"]},
            {first["request_id"]},
        )
        self.assertIn("no external request", first["note"])

    def test_case_loader_rejects_boolean_http_status(self):
        invalid_case = {
            "case_id": "CASE-X",
            "title": "Bad status",
            "product_area": "API",
            "symptom": "A request failed.",
            "request_id": "req-x",
            "http_status": True,
            "affected_scope": "One user",
            "recent_change": "Unknown",
            "customer_impact": "Work is delayed.",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            case_path = Path(temp_dir) / "cases.json"
            case_path.write_text(json.dumps([invalid_case]), encoding="utf-8")

            with self.assertRaisesRegex(CaseDataError, "HTTP status"):
                load_cases(case_path)

    def test_case_loader_rejects_evidence_with_unmatched_request_id(self):
        invalid_case = load_cases()[0]
        invalid_case["events"][0]["request_id"] = "req-unrelated"
        with tempfile.TemporaryDirectory() as temp_dir:
            case_path = Path(temp_dir) / "cases.json"
            case_path.write_text(json.dumps([invalid_case]), encoding="utf-8")

            with self.assertRaisesRegex(CaseDataError, "does not match the case"):
                load_cases(case_path)

    def test_cli_lists_cases(self):
        with patch("sys.stdout"):
            result = main(["--list-cases"])

        self.assertEqual(result, 0)

    def test_cli_reports_unknown_case(self):
        with patch("sys.stderr"):
            result = main(["--case-id", "CASE-MISSING"])

        self.assertEqual(result, 1)

    def test_browser_lists_cases_and_shows_report(self):
        server = create_server(load_cases(), port=0)
        thread = Thread(target=server.serve_forever)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        base_url = "http://127.0.0.1:{}".format(server.server_address[1])

        with urlopen(base_url) as response:
            case_list = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
        self.assertIn("Turn a support report into a useful next step", case_list)
        self.assertIn("Choose an incident", case_list)
        self.assertIn("CASE-1001", case_list)
        self.assertIn("Training content fails to load", case_list)
        self.assertIn('href="/cases/CASE-1001"', case_list)
        self.assertIn("CASE-1004", case_list)
        self.assertNotIn("{{CASE_CARDS}}", case_list)

        with urlopen(base_url + "/static/style.css") as response:
            stylesheet = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("text/css", response.headers["Content-Type"])
        self.assertIn(".case-grid", stylesheet)

        with urlopen(base_url + "/static/app.js") as response:
            script = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
        self.assertIn("/api/simulations/", script)

        with urlopen(base_url + "/cases/CASE-1001") as response:
            report_page = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
        self.assertIn("Request timeline", report_page)
        self.assertIn("req-demo-a17", report_page)
        self.assertIn("Run simulated request", report_page)
        self.assertIn("cause is not confirmed", report_page)
        self.assertIn("Customer update", report_page)
        self.assertIn("Engineering handoff", report_page)

        request = Request(
            base_url + "/api/simulations/CASE-1001",
            data=b"",
            method="POST",
        )
        with urlopen(request) as response:
            simulation = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
        self.assertEqual(simulation["http_status"], 502)
        self.assertTrue(simulation["request_id"].startswith("req-sim-"))
        self.assertEqual(
            {event["request_id"] for event in simulation["events"]},
            {simulation["request_id"]},
        )

        with self.assertRaises(HTTPError) as error:
            urlopen(base_url + "/cases/CASE-MISSING")
        self.assertEqual(error.exception.code, 404)

    def test_cli_can_print_simulation_as_json(self):
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            result = main(["--case-id", "CASE-1004", "--simulate", "--json"])

        simulation = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(simulation["http_status"], 429)
        self.assertIn("req-sim-", simulation["request_id"])


if __name__ == "__main__":
    unittest.main()
