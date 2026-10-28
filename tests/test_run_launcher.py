"""Regression tests for run.py single-instance server handling."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import run


class RunLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pid_file = Path(self.temp_dir.name) / ".sylex-server.pid"
        self.pid_patch = patch.object(run, "SERVER_PID_FILE", str(self.pid_file))
        self.pid_patch.start()

    def tearDown(self):
        self.pid_patch.stop()
        self.temp_dir.cleanup()

    def test_missing_pid_file_means_no_previous_session(self):
        self.assertFalse(run.stop_previous_server())

    def test_unrelated_reused_pid_is_never_terminated(self):
        self.pid_file.write_text("4321", encoding="utf-8")
        with patch.object(run, "_process_exists", return_value=True), patch.object(
            run, "_is_sylex_server", return_value=False
        ), patch.object(run.subprocess, "run") as terminate:
            stopped = run.stop_previous_server()

        self.assertFalse(stopped)
        self.assertFalse(self.pid_file.exists())
        terminate.assert_not_called()

    def test_recorded_sylex_server_is_terminated_before_restart(self):
        self.pid_file.write_text("4321", encoding="utf-8")
        with patch.object(run.os, "name", "nt"), patch.object(
            run, "_process_exists", side_effect=[True, False, False]
        ), patch.object(run, "_is_sylex_server", return_value=True), patch.object(
            run.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
        ) as terminate:
            stopped = run.stop_previous_server()

        self.assertTrue(stopped)
        self.assertFalse(self.pid_file.exists())
        self.assertEqual(terminate.call_args.args[0], ["taskkill", "/PID", "4321", "/T", "/F"])


if __name__ == "__main__":
    unittest.main()
