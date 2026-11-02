import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from capturar import capture, summarize

FIXTURE = Path(__file__).resolve().parents[1] / "ejemplos/posiciones-sinteticas.json"


class CaptureTests(unittest.TestCase):
    def test_missing_speed_is_distinct_from_zero_and_invalid(self):
        summary = summarize(FIXTURE.read_bytes())
        self.assertEqual(summary["vehicles"], 3)
        self.assertEqual(summary["speed_m_s"], {"valido": 1, "ausente": 1, "invalido": 1})
        self.assertEqual(summary["position"], {"valido": 2, "ausente": 0, "invalido": 1})

    def test_header_time_does_not_fill_observation_time(self):
        feed = {"header": {"timestamp": "1793520000"}, "entity": [{"vehicle": {}}]}
        summary = summarize(json.dumps(feed))
        self.assertEqual(summary["feed_timestamp"], "1793520000")
        self.assertEqual(summary["observed_at"]["ausente"], 1)

    def test_roundtrip_preserves_bytes_and_distinct_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            first, record = capture(temp, file=FIXTURE)
            second, _ = capture(temp, file=FIXTURE)
            self.assertNotEqual(first, second)
            self.assertEqual((first / "original.json").read_bytes(), FIXTURE.read_bytes())
            self.assertEqual(record["sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
            self.assertEqual(json.loads((first / "manifest.json").read_text(encoding="utf-8")), record)

    def test_invalid_response_is_preserved_and_marked_failed(self):
        with tempfile.TemporaryDirectory() as temp:
            bad = Path(temp) / "bad.html"
            bad.write_bytes(b"<html>Servicio no disponible</html>")
            run, record = capture(temp, file=bad)
            self.assertEqual(record["status"], "error")
            self.assertNotIn("summary", record)
            self.assertEqual((run / "original.json").read_bytes(), bad.read_bytes())

    def test_empty_feed_and_wrong_structure_are_distinct(self):
        self.assertEqual(summarize('{"header":{},"entity":[]}')["vehicles"], 0)
        for raw in ('[]', '{}', '{"header":{},"entity":{}}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                summarize(raw)

    def test_malformed_entities_and_nonfinite_values(self):
        feed = {"header": {}, "entity": [None, {"alert": {}}, {"vehicle": []},
            {"vehicle": {"timestamp": True, "position": {"latitude": True, "longitude": 0, "speed": float("nan")}}}]}
        summary = summarize(json.dumps(feed))
        self.assertEqual(summary["malformed_entities"], 2)
        self.assertEqual(summary["other_entities"], 1)
        for field in ("position", "observed_at", "speed_m_s"):
            self.assertEqual(summary[field]["invalido"], 1)

    def test_oversize_is_not_saved_as_complete_capture(self):
        with tempfile.TemporaryDirectory() as temp, patch("capturar.MAX_BYTES", 8):
            run, record = capture(temp, file=FIXTURE)
            self.assertEqual(record["status"], "error")
            self.assertFalse((run / "original.json").exists())
            self.assertNotIn("sha256", record)

    def test_network_failure_does_not_become_an_empty_feed(self):
        with tempfile.TemporaryDirectory() as temp, patch("capturar.urllib.request.urlopen", side_effect=TimeoutError("tiempo agotado")):
            run, record = capture(temp, url="https://example.invalid/posiciones")
            self.assertEqual(record["status"], "error")
            self.assertNotIn("summary", record)
            self.assertFalse((run / "original.json").exists())
            self.assertTrue((run / "manifest.json").exists())

    def test_http_success_and_error_are_recorded(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/ok":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(FIXTURE.read_bytes())
                else:
                    self.send_error(503)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                base = f"http://127.0.0.1:{server.server_port}"
                _, ok = capture(temp, url=base + "/ok")
                _, failed = capture(temp, url=base + "/failed")
                self.assertEqual(ok["http_status"], 200)
                self.assertEqual(ok["summary"]["vehicles"], 3)
                self.assertEqual(failed["status"], "error")
                self.assertNotIn("summary", failed)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
