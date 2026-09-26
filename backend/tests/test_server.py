"""REST API 端到端测试(真实启动本地 HTTP 服务)。"""
import json
import os
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.server import Handler  # noqa: E402


class ServerTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=5) as r:
            return json.loads(r.read().decode())

    def post(self, path, payload):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode())
        except HTTPError as e:
            return e.code, json.loads(e.read().decode())


class TestApi(ServerTestBase):
    def test_map_payload(self):
        data = self.get("/api/map")
        self.assertEqual({f["floor"] for f in data["floors"]}, {-1, -2})
        self.assertTrue(data["nodes"])
        self.assertTrue(data["edges"])

    def test_places_filter(self):
        data = self.get("/api/places?type=shop")
        self.assertTrue(all(p["type"] == "shop" for p in data["places"]))
        closed = [p for p in data["places"] if not p["open"]]
        self.assertEqual({p["id"] for p in closed}, {"s3", "s7"})

    def test_route_success(self):
        status, data = self.post("/api/route", {
            "start": "metro_a", "goal": "park_b",
            "preference": "escalator"})
        self.assertEqual(status, 200)
        route = data["route"]
        self.assertEqual(route["start"]["id"], "metro_a")
        self.assertIn("escalator", route["connectors"])
        self.assertTrue(route["segments"])

    def test_route_closed_shop_returns_400(self):
        status, data = self.post("/api/route", {
            "start": "metro_a", "goal": "s3"})
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "DESTINATION_CLOSED")

    def test_route_bad_json(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/route",
            data=b"not-json", method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("应返回 400")
        except HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_index_page_served(self):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/", timeout=5) as r:
            body = r.read().decode()
        self.assertIn("地下商业街", body)


if __name__ == "__main__":
    unittest.main()
