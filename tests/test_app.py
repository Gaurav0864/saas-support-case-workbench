import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import CaseDataError, analyze_case, load_cases, main


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

    def test_cli_lists_cases(self):
        with patch("sys.stdout"):
            result = main(["--list-cases"])

        self.assertEqual(result, 0)

    def test_cli_reports_unknown_case(self):
        with patch("sys.stderr"):
            result = main(["--case-id", "CASE-MISSING"])

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
