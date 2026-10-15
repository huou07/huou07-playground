import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("boundary_probe", ROOT / "deploy/security/dsh-boundary-probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
auth_spec = importlib.util.spec_from_file_location("owner_auth_preflight", ROOT / "deploy/security/owner-auth-preflight.py")
preflight = importlib.util.module_from_spec(auth_spec)
auth_spec.loader.exec_module(preflight)


class DshBoundaryTests(unittest.TestCase):
    def test_owner_login_preflight_requires_distinct_configured_passwords(self):
        environment = {b"OPENCODE_PUBLIC_USERNAME": b"owner", b"OPENCODE_PUBLIC_PASSWORD": b"owner-fixture",
                       b"OPENCODE_BACKEND_USERNAME": b"worker", b"OPENCODE_BACKEND_PASSWORD": b"worker-fixture"}
        preflight.validate_environment(environment)
        environment[b"OPENCODE_BACKEND_PASSWORD"] = b"owner-fixture"
        with self.assertRaisesRegex(RuntimeError, "must differ"):
            preflight.validate_environment(environment)
        with self.assertRaisesRegex(RuntimeError, "configured"):
            preflight.validate_environment({})

    def test_permission_probe_opens_but_never_reads_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture"
            path.write_text("not-a-live-secret")
            with patch.object(os, "read", side_effect=AssertionError("must not read")):
                self.assertTrue(probe.can_open(path))
            link = Path(directory) / "link"
            link.symlink_to(path)
            self.assertFalse(probe.can_open(link))

    def test_wrong_identity_cannot_produce_worker_evidence(self):
        with patch.object(os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(SystemExit, "refusing another identity"):
                probe.probe()

    def test_launch_probe_does_not_redeem_or_read_token_response(self):
        connection = Mock()
        response = connection.getresponse.return_value
        response.getheader.return_value = "http://127.0.0.1:3080/?token=fixture"
        with patch.object(probe.http.client, "HTTPConnection", return_value=connection):
            self.assertTrue(probe.launch_endpoint_exposes_token())
        connection.request.assert_called_once_with("GET", "/api/apps/launch?name=DeepSeek+Harness")
        response.read.assert_not_called()
        connection.close.assert_called_once()
