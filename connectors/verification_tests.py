import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import verification


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        self.store = Path(self.tmp.name) / "verification"
        self.env = patch.dict(os.environ, {"NEWAL_VERIFICATION_HOME": str(self.store)}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_command_exit_zero_is_verified_and_failure_is_failed(self):
        good = verification.record(self.root, "bash", "exec", True, {"exit": 0}, {"command": "secret command"})
        bad = verification.record(self.root, "bash", "exec", True, {"exit": 2}, {"command": "secret command"})
        self.assertEqual(good["status"], "verified")
        self.assertEqual(bad["status"], "failed")

    def test_effectful_success_requires_independent_verification(self):
        self.assertEqual(
            verification.classify("github_update_file", "connector_write", True, {}, {"token": "secret"}),
            "needs_verification",
        )
        self.assertEqual(
            verification.classify("mcp__github__create_issue", "mcp", True, {}, {"body": "private"}),
            "needs_verification",
        )
        self.assertEqual(
            verification.classify("phone", "meta", True, {}, {"action": "tap"}),
            "needs_verification",
        )

    def test_read_actions_are_neutral(self):
        self.assertEqual(verification.classify("read", "read", True, {}, {}), "neutral")
        self.assertEqual(verification.classify("phone", "meta", True, {}, {"action": "screen"}), "neutral")

    def test_project_check_is_strong_evidence(self):
        row = verification.record_project_check(self.root, "pytest -q secret", True, 0)
        self.assertEqual(row["status"], "verified")
        status = verification.status(self.root)
        self.assertEqual(status["counts"]["verified"], 1)
        raw = verification._path(self.root).read_text(encoding="utf-8")
        self.assertNotIn("pytest -q secret", raw)

    def test_ledger_never_stores_arguments_or_output(self):
        verification.record(
            self.root,
            "github_update_file",
            "connector_write",
            True,
            {"ok": True},
            {"token": "TOP-SECRET", "content": "PRIVATE-CONTENT"},
        )
        raw = verification._path(self.root).read_text(encoding="utf-8")
        self.assertNotIn("TOP-SECRET", raw)
        self.assertNotIn("PRIVATE-CONTENT", raw)
        parsed = json.loads(raw.strip())
        self.assertNotIn("args", parsed)
        self.assertNotIn("output", parsed)

    def test_feedback_only_blocks_unverified_success_claims(self):
        row = {"status": "needs_verification"}
        self.assertIn("Verification required", verification.feedback(row))
        self.assertEqual(verification.feedback({"status": "verified"}), "")


if __name__ == "__main__":
    unittest.main()
