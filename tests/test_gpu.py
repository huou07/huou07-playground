import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy import gpu
from web import app


class IntelGpuTests(unittest.TestCase):
    def test_stream_parser_uses_last_complete_sample(self):
        output = '[{"engines":{"Render/3D":{"busy":0}}},\n{"engines":{"Render/3D":{"busy":12.5},"Video":{"busy":3}}},\n{"engines":'
        self.assertEqual(gpu.last_json_sample(output), {"engines": {"Render/3D": {"busy": 12.5}, "Video": {"busy": 3}}})

    def test_collector_reports_engine_activity_and_idle_frequency_as_unknown(self):
        output = '[{"engines":{"Render/3D":{"busy":0},"Video":{"busy":17.5}},"frequency":{"actual":0},"rc6":{"value":98.2}}]'
        class Driver:
            name = "i915"
            def resolve(self):
                return self

        class Card:
            name = "card0"
            def __truediv__(self, suffix):
                return Driver()

        with patch.object(Path, "glob", return_value=[Card()]):
            result = gpu.collect_gpu(binary="intel_gpu_top", run=lambda *args, **kwargs: type("Result", (), {"stdout": output, "returncode": 124})())
        self.assertEqual(result, {"available": True, "usage_percent": 17.5, "engines": {"Render/3D": 0, "Video": 17.5}, "frequency_mhz": None, "rc6_percent": 98.2})

    def test_api_sanitizes_and_rejects_stale_intel_sample(self):
        with tempfile.TemporaryDirectory() as temporary:
            sample_file = Path(temporary) / "sample.json"
            sample_file.write_text(json.dumps({"available": True, "sampled_at": time.time(), "usage_percent": 30.25, "engines": {"Render/3D": 30.25, "bad": 101}, "frequency_mhz": 650, "rc6_percent": 90}))
            with patch.dict("os.environ", {"GPU_FILE": str(sample_file)}):
                result = app.intel_gpu_metrics()
            self.assertEqual(result["model"], "Intel integrated graphics (i915)")
            self.assertEqual(result["engines"], {"Render/3D": 30.2})
            self.assertEqual(result["frequency_mhz"], 650)
            sample_file.write_text(json.dumps({"available": True, "sampled_at": time.time() - 100, "usage_percent": 30}))
            with patch.dict("os.environ", {"GPU_FILE": str(sample_file)}):
                self.assertFalse(app.intel_gpu_metrics()["available"])


if __name__ == "__main__":
    unittest.main()
