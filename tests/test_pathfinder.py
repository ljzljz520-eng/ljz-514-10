# -*- coding: utf-8 -*-
"""地下商业街导航系统 —— 后端算法与 API 测试。

运行：python3 -m unittest discover -s tests -v
"""
import http.client
import json
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from pathfinder import (            # noqa: E402
    Mall, is_open, ClosedShopError, UnknownNodeError,
    ESCALATOR_TIME, ELEVATOR_TIME, WALK_SPEED,
)
import server                        # noqa: E402

NOON = "12:00"   # 所有店铺均在营业的参考时间


class TestBusinessStatus(unittest.TestCase):
    """营业状态判断。"""

    def setUp(self):
        self.mall = Mall()

    def test_shop_open_within_hours(self):
        self.assertTrue(is_open(self.mall.nodes["F101"], now=NOON))       # 07:30-21:00

    def test_shop_closed_outside_hours(self):
        self.assertFalse(is_open(self.mall.nodes["F101"], now="23:00"))
        self.assertFalse(is_open(self.mall.nodes["F101"], now="07:00"))

    def test_force_closed_shop(self):
        self.assertFalse(is_open(self.mall.nodes["F103"], now=NOON))      # 暂停营业

    def test_non_shop_always_open(self):
        for nid in ("M1", "S1", "P1"):
            self.assertTrue(is_open(self.mall.nodes[nid], now="03:00"))

    def test_overnight_hours(self):
        node = {"type": "shop", "hours": "22:00-02:00"}
        self.assertTrue(is_open(node, now="23:30"))
        self.assertTrue(is_open(node, now="01:00"))
        self.assertFalse(is_open(node, now="12:00"))


class TestRouting(unittest.TestCase):
    """路径规划算法。"""

    @classmethod
    def setUpClass(cls):
        cls.mall = Mall()

    def test_same_start_and_end(self):
        r = self.mall.find_route("M1", "M1", now=NOON)
        self.assertEqual(r["total_time"], 0)
        self.assertEqual(r["walk_distance"], 0)
        self.assertEqual(len(r["path"]), 1)
        self.assertEqual(r["steps"][-1]["kind"], "arrive")

    def test_same_floor_route(self):
        """同层最短：M1 -> 书店，750 米 / 625 秒，全程步行。"""
        r = self.mall.find_route("M1", "F102", now=NOON)
        self.assertEqual(r["walk_distance"], 750.0)
        self.assertAlmostEqual(r["total_time"], 750.0 / WALK_SPEED, places=1)
        self.assertTrue(all(e["kind"] == "corridor" for e in r["edges"]))
        self.assertTrue(all(p["floor"] == "B1" for p in r["path"]))

    def test_cross_floor_prefers_escalator_when_close(self):
        """地铁A口 -> 停车场：扶梯①最近，应乘扶梯（125+45+125=295 秒）。"""
        r = self.mall.find_route("M1", "P1", now=NOON)
        kinds = [e["kind"] for e in r["edges"]]
        self.assertIn("escalator", kinds)
        self.assertNotIn("elevator", kinds)
        self.assertEqual(r["walk_distance"], 300.0)
        self.assertAlmostEqual(r["total_time"], 300.0 / WALK_SPEED + ESCALATOR_TIME, places=1)
        floors = {p["floor"] for p in r["path"]}
        self.assertEqual(floors, {"B1", "B2"})

    def test_fastest_may_choose_elevator_when_closer(self):
        """地铁B口 -> 健身房：电梯就在旁边，最快路线应选电梯（250+75+125=450 秒）。"""
        r = self.mall.find_route("M2", "F203", now=NOON)
        kinds = [e["kind"] for e in r["edges"]]
        self.assertIn("elevator", kinds)
        self.assertNotIn("escalator", kinds)
        self.assertAlmostEqual(r["total_time"], 450.0 / WALK_SPEED + ELEVATOR_TIME, places=1)

    def test_accessible_mode_uses_elevator_only(self):
        """无障碍模式：地铁A口 -> 停车场 只能绕电梯，且不得出现扶梯。"""
        r = self.mall.find_route("M1", "P1", mode="accessible", now=NOON)
        kinds = [e["kind"] for e in r["edges"]]
        self.assertIn("elevator", kinds)
        self.assertNotIn("escalator", kinds)
        self.assertEqual(r["walk_distance"], 1800.0)
        self.assertAlmostEqual(r["total_time"], 1800.0 / WALK_SPEED + ELEVATOR_TIME, places=1)

    def test_closed_shop_cannot_be_destination(self):
        """未营业店铺（暂停营业 / 已过营业时间）不能作为终点。"""
        with self.assertRaises(ClosedShopError):
            self.mall.find_route("M1", "F103", now=NOON)          # 暂停营业
        with self.assertRaises(ClosedShopError):
            self.mall.find_route("M1", "F101", now="23:00")       # 已打烊

    def test_open_shop_as_destination(self):
        r = self.mall.find_route("M1", "F101", now=NOON)
        self.assertEqual(r["path"][-1]["id"], "F101")

    def test_closed_shop_can_be_start(self):
        """需求只限制终点：从已打烊的店离开应当允许。"""
        r = self.mall.find_route("F103", "M1", now=NOON)
        self.assertEqual(r["path"][0]["id"], "F103")

    def test_unknown_node_raises(self):
        with self.assertRaises(UnknownNodeError):
            self.mall.find_route("M1", "NOPE", now=NOON)
        with self.assertRaises(UnknownNodeError):
            self.mall.find_route("NOPE", "M1", now=NOON)

    def test_bad_mode_raises(self):
        with self.assertRaises(ValueError):
            self.mall.find_route("M1", "M2", mode="teleport", now=NOON)

    def test_path_is_continuous(self):
        """返回路径中相邻节点必须在图上相邻。"""
        r = self.mall.find_route("M2", "F201", now=NOON)
        ids = [p["id"] for p in r["path"]]
        for a, b in zip(ids, ids[1:]):
            neighbors = [n for n, _, _ in self.mall.adj[a]]
            self.assertIn(b, neighbors)

    def test_steps_consistency(self):
        """分段指引：步行段距离之和 = 总步行距离；最后一段为到达。"""
        r = self.mall.find_route("M1", "P1", now=NOON)
        walk_sum = sum(s.get("distance", 0) for s in r["steps"] if s["kind"] == "walk")
        self.assertAlmostEqual(walk_sum, r["walk_distance"], places=1)
        self.assertEqual(r["steps"][-1]["kind"], "arrive")
        self.assertTrue(any(s["kind"] == "escalator" for s in r["steps"]))


class TestApi(unittest.TestCase):
    """HTTP API 集成测试（真实起服务、发请求）。"""

    @classmethod
    def setUpClass(cls):
        cls.srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body

    def _get_json(self, path):
        status, body = self._get(path)
        return status, json.loads(body.decode("utf-8"))

    def test_index_page(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("地下商业街".encode("utf-8"), body)

    def test_pois_grouped_with_open_status(self):
        status, data = self._get_json("/api/pois?now=12:00")
        self.assertEqual(status, 200)
        self.assertIn("subway", data)
        self.assertIn("shop", data)
        shops = {s["id"]: s for s in data["shop"]}
        self.assertFalse(shops["F103"]["open"])     # 暂停营业
        self.assertTrue(shops["F101"]["open"])      # 营业中

    def test_route_ok(self):
        status, data = self._get_json("/api/route?start=M1&end=P1&mode=fastest&now=12:00")
        self.assertEqual(status, 200)
        self.assertGreater(data["total_time"], 0)
        self.assertEqual(data["path"][0]["id"], "M1")
        self.assertEqual(data["path"][-1]["id"], "P1")

    def test_route_closed_shop_returns_400(self):
        status, data = self._get_json("/api/route?start=M1&end=F103&now=12:00")
        self.assertEqual(status, 400)
        self.assertIn("未营业", data["error"])

    def test_route_unknown_node_returns_400(self):
        status, data = self._get_json("/api/route?start=M1&end=XXX")
        self.assertEqual(status, 400)
        self.assertIn("不存在", data["error"])

    def test_route_missing_param_returns_400(self):
        status, data = self._get_json("/api/route?start=M1")
        self.assertEqual(status, 400)
        self.assertIn("缺少参数", data["error"])

    def test_map_contains_floors_and_lifts(self):
        status, data = self._get_json("/api/map?now=12:00")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["escalators"]), 2)
        self.assertEqual(len(data["elevators"]), 1)
        floors = {n["floor"] for n in data["nodes"].values()}
        self.assertEqual(floors, {"B1", "B2"})


if __name__ == "__main__":
    unittest.main()
