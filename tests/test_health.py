"""健康检查核心逻辑：真实 HEAD 探测 + 连续失败/恢复状态机 + 不阻塞调用方。"""
from __future__ import annotations

import http.server
import queue
import sys
import threading
import time
from pathlib import Path

import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.health import HealthMonitor, HealthResult, probe_once  # noqa: E402


class _HeadHandler(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", "15")
        self.end_headers()

    def log_message(self, *_a):
        pass


class ProbeTest(unittest.TestCase):
    def test_probe_once_head_success(self):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _HeadHandler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            port = srv.server_address[1]
            r = probe_once(f"http://127.0.0.1:{port}/__dufs__/health", timeout=2)
            self.assertTrue(r.ok, r.detail)
            self.assertIn("HTTP 200", r.detail)
            self.assertGreaterEqual(r.latency_ms, 0)
        finally:
            srv.shutdown()
            srv.server_close()
            t.join(timeout=1)

    def test_probe_connection_failure_is_not_ok(self):
        r = probe_once("http://127.0.0.1:1/__dufs__/health", timeout=1)
        self.assertFalse(r.ok)
        self.assertTrue(r.detail)


class MonitorStateTest(unittest.TestCase):
    def test_three_failures_then_recovery(self):
        m = HealthMonitor(lambda: "", lambda *a: None, failure_threshold=3)
        self.assertIsNone(m.evaluate(True, "ok"))
        self.assertIsNone(m.evaluate(False, "fail1"))
        self.assertIsNone(m.evaluate(False, "fail2"))
        event = m.evaluate(False, "fail3")
        self.assertEqual(event, ("health_fail", "fail3"))
        self.assertIsNone(m.evaluate(False, "fail4"))
        event = m.evaluate(True, "ok")
        self.assertEqual(event, ("health_ok", "ok"))
        self.assertIsNone(m.evaluate(True, "ok"))

    def test_monitor_emits_thread_events(self):
        events: queue.Queue = queue.Queue()
        state = {"i": 0}

        def fake_probe(_url, _timeout):
            state["i"] += 1
            ok = state["i"] >= 4
            return HealthResult(ok, "ok" if ok else "timeout", 1.0)

        m = HealthMonitor(lambda: "http://127.0.0.1:1/x",
                          lambda kind, detail: events.put((kind, detail)),
                          interval=0.01, timeout=0.1, failure_threshold=3,
                          probe=fake_probe)
        m.start()
        try:
            first = events.get(timeout=1)
            second = events.get(timeout=1)
        finally:
            m.stop()
        self.assertEqual(first[0], "health_fail")
        self.assertEqual(second[0], "health_ok")

    def test_start_returns_before_slow_probe_finishes(self):
        entered = threading.Event()
        release = threading.Event()

        def slow_probe(_url, _timeout):
            entered.set()
            release.wait(1.0)
            return HealthResult(True, "ok", 1.0)

        m = HealthMonitor(lambda: "http://127.0.0.1:1/x", lambda *a: None,
                          interval=0.01, timeout=0.1, probe=slow_probe)
        t0 = time.perf_counter()
        m.start()
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 0.2, "start() 不应阻塞调用方线程")
        self.assertTrue(entered.wait(0.5), "探测应已进入后台线程")
        release.set()
        m.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
