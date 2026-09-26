"""路径规划算法的测试。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.graph import build_default_mall  # noqa: E402
from backend.router import (  # noqa: E402
    RouteError, build_segments, dijkstra, edge_cost, plan_route,
)


class TestPlanRoute(unittest.TestCase):
    def setUp(self):
        self.g = build_default_mall()

    # ---- 基本规划 ----
    def test_same_floor_basic_route(self):
        r = plan_route(self.g, "s1", "s2", "none")
        # 起点终点都在 B1
        self.assertTrue(all(f == -1 for f in r["floors"]))
        self.assertGreater(r["walk_meters"], 0)
        self.assertEqual(r["connectors"], [])
        self.assertIn("s1", r["path"])
        self.assertEqual(r["path"][-1], "s2")

    def test_cross_floor_includes_connector(self):
        r = plan_route(self.g, "metro_a", "park_a", "none")
        self.assertEqual(r["floors"], [-1, -2])
        self.assertTrue(
            any(c in ("escalator", "elevator") for c in r["connectors"]))
        # 指令中必须出现一次跨层段
        kinds = [s["kind"] for s in r["segments"]]
        self.assertIn("arrive", kinds)
        self.assertTrue(
            any(k in ("escalator", "elevator") for k in kinds))

    def test_parking_to_shop_east(self):
        r = plan_route(self.g, "park_b", "s11", "none")
        self.assertEqual(r["path"][0], "park_b")
        self.assertEqual(r["path"][-1], "s11")
        self.assertEqual(r["floors"], [-2, -1])

    # ---- 营业状态规则 ----
    def test_closed_shop_cannot_be_goal(self):
        # s3 海底捞、s7 万达影城 未营业
        with self.assertRaises(RouteError) as cm:
            plan_route(self.g, "metro_a", "s3", "none")
        self.assertEqual(cm.exception.code, "DESTINATION_CLOSED")
        with self.assertRaises(RouteError):
            plan_route(self.g, "metro_b", "s7", "none")

    def test_closed_shop_cannot_be_start(self):
        with self.assertRaises(RouteError) as cm:
            plan_route(self.g, "s7", "metro_a", "none")
        self.assertEqual(cm.exception.code, "DESTINATION_CLOSED")

    def test_open_shop_can_be_goal(self):
        r = plan_route(self.g, "metro_a", "s4", "none")
        self.assertEqual(r["goal"]["id"], "s4")

    def test_closed_shop_not_used_as_cut_through(self):
        """闭店即便在两点之间也不能被穿行。"""
        r = plan_route(self.g, "s2", "s5", "none")
        self.assertNotIn("s3", r["path"])
        self.assertNotIn("s7", r["path"])

    # ---- 输入校验 ----
    def test_missing_node(self):
        with self.assertRaises(RouteError) as cm:
            plan_route(self.g, "nope", "s1", "none")
        self.assertEqual(cm.exception.code, "NODE_NOT_FOUND")

    def test_same_start_goal(self):
        with self.assertRaises(RouteError) as cm:
            plan_route(self.g, "s1", "s1", "none")
        self.assertEqual(cm.exception.code, "SAME_POINT")

    def test_non_poi_rejected(self):
        # 通道交叉口不能作为顾客选择的起终点
        with self.assertRaises(RouteError) as cm:
            plan_route(self.g, "j1_b1", "s1", "none")
        self.assertEqual(cm.exception.code, "INVALID_POI")

    # ---- 扶梯 / 电梯偏好 ----
    def test_escalator_preference_picks_escalator(self):
        r = plan_route(self.g, "metro_b", "park_a", "escalator")
        self.assertIn("escalator", r["connectors"])
        self.assertNotIn("elevator", r["connectors"])

    def test_elevator_preference_picks_elevator(self):
        r = plan_route(self.g, "metro_b", "park_a", "elevator")
        self.assertEqual(r["connectors"], ["elevator"])

    def test_preference_changes_path(self):
        """不同偏好下跨层节点应不同。"""
        esc = plan_route(self.g, "metro_b", "park_a", "escalator")
        ele = plan_route(self.g, "metro_b", "park_a", "elevator")
        self.assertIn("esc1_b2", esc["path"])
        self.assertIn("elev_b2", ele["path"])
        self.assertNotEqual(esc["path"], ele["path"])

    # ---- 最优性 ----
    def test_dijkstra_matches_independent_cost(self):
        """返回路径的成本(取整)等于独立累加的边成本。"""
        r = plan_route(self.g, "metro_a", "park_b", "none")
        total = 0.0
        for a, b in zip(r["path"], r["path"][1:]):
            for v, e in self.g.adj[a]:
                if v == b:
                    total += edge_cost(e.kind, e.distance, "none")
        self.assertEqual(round(total), r["estimated_seconds"])

    def test_nearest_escalator_preferred_by_default(self):
        """无偏好时地铁口A 去 B2 应走更近的 1 号扶梯而非电梯。"""
        r = plan_route(self.g, "metro_a", "park_a", "none")
        self.assertIn("esc1_b1", r["path"])
        self.assertNotIn("elev_b1", r["path"])

    # ---- 指令与统计 ----
    def test_segments_well_formed(self):
        r = plan_route(self.g, "park_b", "metro_a", "none")
        segs = r["segments"]
        self.assertEqual(segs[-1]["kind"], "arrive")
        for s in segs:
            self.assertTrue(s["instruction"])
            if s["kind"] == "walk":
                self.assertGreater(s["distance"], 0)
        # 总步行距离 == 所有 walk 段之和
        self.assertAlmostEqual(
            r["walk_meters"],
            sum(s["distance"] for s in segs if s["kind"] == "walk"),
            places=1)

    def test_cross_floor_instruction_text(self):
        r = plan_route(self.g, "park_a", "metro_a", "none")  # B2 -> B1
        cross = [s for s in r["segments"]
                 if s["kind"] in ("escalator", "elevator")][0]
        self.assertIn("上行", cross["instruction"])
        self.assertIn("B1", cross["instruction"])

    def test_service_desk_reachable(self):
        r = plan_route(self.g, "metro_b", "svc1", "none")
        self.assertEqual(r["goal"]["type"], "service")


class TestUnreachable(unittest.TestCase):
    def test_disconnected_graph_raises(self):
        """构造孤岛, 验证 NO_ROUTE。"""
        g = build_default_mall()
        from backend.graph import Node
        g.add_node(Node("island", "孤岛店", "shop", -1, 999, 999,
                        open=True))
        with self.assertRaises(RouteError) as cm:
            plan_route(g, "s1", "island", "none")
        self.assertEqual(cm.exception.code, "NO_ROUTE")

    def test_dijkstra_direct(self):
        g = build_default_mall()
        path = dijkstra(g, "elev_b1", "elev_b2", "none")
        self.assertEqual(path, ["elev_b1", "elev_b2"])
        segs = build_segments(g, path)
        self.assertEqual(len(segs), 2)  # 跨层段 + 到达段
        self.assertEqual(segs[0].kind, "elevator")
        self.assertEqual(segs[1].kind, "arrive")


if __name__ == "__main__":
    unittest.main()
