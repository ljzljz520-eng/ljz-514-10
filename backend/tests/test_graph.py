"""图模型构建与基础约束的测试。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.graph import (  # noqa: E402
    Edge, MallGraph, Node, build_default_mall,
)


class TestDefaultMall(unittest.TestCase):
    def setUp(self):
        self.g = build_default_mall()

    def test_expected_node_counts(self):
        """示例地图包含 B1/B2 各节点。"""
        floors = {n.floor for n in self.g.nodes.values()}
        self.assertEqual(floors, {-1, -2})
        # 4 类顾客可选 POI 均存在
        types = {n.type for n in self.g.nodes.values()}
        for t in ("entrance", "shop", "service", "parking",
                  "escalator", "elevator", "corridor"):
            self.assertIn(t, types)

    def test_places_only_returns_pois(self):
        for n in self.g.places():
            self.assertIn(n.type,
                          ("entrance", "shop", "service", "parking"))

    def test_places_filter_by_type(self):
        shops = self.g.places("shop")
        self.assertTrue(shops)
        self.assertTrue(all(n.type == "shop" for n in shops))
        self.assertEqual(len(self.g.places("parking")), 2)
        self.assertEqual(len(self.g.places("entrance")), 2)
        self.assertEqual(len(self.g.places("service")), 1)

    def test_closed_shops_exist(self):
        closed = [n for n in self.g.places("shop") if not n.open]
        self.assertEqual({n.id for n in closed}, {"s3", "s7"})

    def test_graph_is_undirected(self):
        """每条边在两个端点的邻接表中都存在。"""
        deg = {nid: 0 for nid in self.g.nodes}
        for e in self.g.edges:
            deg[e.a] += 1
            deg[e.b] += 1
        for nid, count in deg.items():
            self.assertEqual(len(self.g.adj[nid]), count)
            self.assertGreaterEqual(count, 1)

    def test_walk_edges_horizontal_and_priced(self):
        for e in self.g.edges:
            if e.kind == "walk":
                self.assertEqual(self.g.nodes[e.a].floor,
                                 self.g.nodes[e.b].floor)
                self.assertGreater(e.distance, 0)

    def test_vertical_edges_cross_floors(self):
        verts = [e for e in self.g.edges
                 if e.kind in ("escalator", "elevator")]
        self.assertEqual(len(verts), 3)  # 2 扶梯 + 1 电梯
        for e in verts:
            self.assertNotEqual(self.g.nodes[e.a].floor,
                                self.g.nodes[e.b].floor)


class TestGraphConstraints(unittest.TestCase):
    def test_duplicate_node_rejected(self):
        g = MallGraph()
        g.add_node(Node("x", "X", "corridor", -1, 0, 0))
        with self.assertRaises(ValueError):
            g.add_node(Node("x", "X2", "corridor", -1, 1, 1))

    def test_edge_requires_existing_endpoints(self):
        g = MallGraph()
        g.add_node(Node("x", "X", "corridor", -1, 0, 0))
        with self.assertRaises(ValueError):
            g.add_edge("x", "y", "walk")

    def test_walk_cannot_cross_floors(self):
        g = MallGraph()
        g.add_node(Node("a", "A", "corridor", -1, 0, 0))
        g.add_node(Node("b", "B", "corridor", -2, 0, 0))
        with self.assertRaises(ValueError):
            g.add_edge("a", "b", "walk", 10)

    def test_connector_cannot_stay_on_floor(self):
        g = MallGraph()
        g.add_node(Node("a", "A", "escalator", -1, 0, 0))
        g.add_node(Node("b", "B", "escalator", -1, 10, 0))
        with self.assertRaises(ValueError):
            g.add_edge("a", "b", "escalator")

    def test_walk_distance_auto_from_coords(self):
        g = MallGraph()
        g.add_node(Node("a", "A", "corridor", -1, 0, 0))
        g.add_node(Node("b", "B", "corridor", -1, 100, 0))
        e = g.add_edge("a", "b", "walk")
        self.assertAlmostEqual(e.distance, 30.0, places=1)


if __name__ == "__main__":
    unittest.main()
