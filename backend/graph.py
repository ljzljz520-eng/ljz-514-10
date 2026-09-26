"""地下商业街地图的图模型。

节点(Node)类型:
    entrance  地铁口
    shop      店铺(带营业状态)
    service   服务台
    parking   停车场
    corridor  通道交叉口
    escalator 扶梯口(竖向节点, 同井道两层节点之间由 kind=escalator 的边相连)
    elevator  电梯厅(同上)

边(Edge)类型:
    walk       普通通道, distance 为水平步行距离(米)
    escalator  扶梯连接(跨越楼层)
    elevator   电梯连接(跨越楼层)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# 楼层编号 -> 展示名称
FLOOR_NAMES: Dict[int, str] = {-2: "B2", -1: "B1"}

# 前端坐标(px)换算实际距离(米)的比例尺, 仅用于自动生成 walk 边长度
PX_TO_METER = 0.3

VALID_NODE_TYPES = {
    "entrance", "shop", "service", "parking",
    "corridor", "escalator", "elevator",
}
VALID_EDGE_KINDS = {"walk", "escalator", "elevator"}


@dataclass
class Node:
    id: str
    name: str
    type: str
    floor: int
    x: float
    y: float
    open: bool = True            # 仅店铺有意义: 是否营业
    hours: str = ""              # 营业时间说明
    meta: dict = field(default_factory=dict)

    def is_poi(self) -> bool:
        """顾客可直接选择的目的地(地铁口/店铺/服务台/停车场)。"""
        return self.type in ("entrance", "shop", "service", "parking")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "floor": self.floor,
            "floor_name": FLOOR_NAMES.get(self.floor, str(self.floor)),
            "x": self.x,
            "y": self.y,
            "open": self.open,
            "hours": self.hours,
            "meta": self.meta,
        }


@dataclass
class Edge:
    a: str
    b: str
    kind: str
    distance: float = 0.0       # walk: 米; 竖向边记 0

    def to_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "kind": self.kind,
                "distance": round(self.distance, 1)}


class MallGraph:
    """无向加权图。"""

    def __init__(self) -> None:
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self.adj: Dict[str, List[Tuple[str, Edge]]] = {}

    # ---- 构建 ----
    def add_node(self, node: Node) -> None:
        if node.type not in VALID_NODE_TYPES:
            raise ValueError(f"未知节点类型: {node.type}")
        if node.id in self.nodes:
            raise ValueError(f"节点 id 重复: {node.id}")
        self.nodes[node.id] = node
        self.adj[node.id] = []

    def add_edge(self, a: str, b: str, kind: str,
                 distance: float | None = None) -> Edge:
        if a not in self.nodes or b not in self.nodes:
            raise ValueError(f"边端点不存在: {a} <-> {b}")
        if kind not in VALID_EDGE_KINDS:
            raise ValueError(f"未知边类型: {kind}")
        if kind == "walk":
            if distance is None:
                na, nb = self.nodes[a], self.nodes[b]
                distance = round(
                    math.hypot(na.x - nb.x, na.y - nb.y) * PX_TO_METER, 1)
            if self.nodes[a].floor != self.nodes[b].floor:
                raise ValueError("walk 边不能跨越楼层")
        else:
            # 竖向交通必须连接不同楼层
            if self.nodes[a].floor == self.nodes[b].floor:
                raise ValueError(f"{kind} 边必须跨越楼层: {a}<->{b}")
            distance = 0.0
        edge = Edge(a, b, kind, distance or 0.0)
        self.edges.append(edge)
        self.adj[a].append((b, edge))
        self.adj[b].append((a, edge))
        return edge

    # ---- 查询 ----
    def places(self, node_type: str | None = None) -> List[Node]:
        """顾客可选择的地点(POI)。"""
        result = [n for n in self.nodes.values() if n.is_poi()]
        if node_type:
            result = [n for n in result if n.type == node_type]
        return sorted(result, key=lambda n: (n.type, n.floor, n.id))

    def to_dict(self) -> dict:
        return {
            "floors": [{"floor": f, "name": FLOOR_NAMES[f]}
                       for f in sorted(FLOOR_NAMES, reverse=True)],
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }


def build_default_mall() -> MallGraph:
    """构建示例地下商业街: B1(商铺层) + B2(停车场层)。

    B1 平面示意(坐标仅用于前端渲染与通道长度估算)::

        地铁口A                                     地铁口B
          |  星巴克  优衣库 海底捞  苹果 名创            |
          o----o------o------o------o------o----o      主通道(y=200)
          |  1号扶梯      电梯厅      2号扶梯  |
          |  肯德基  万达影城 服务台 屈臣氏 华为 绿茶    南侧铺位
        B2: 停车场A == 1号扶梯/电梯厅/2号扶梯 == 停车场B
    """
    g = MallGraph()
    N = Node

    # ---------------- B1 层 (floor = -1) ----------------
    # 主通道脊椎节点(西 -> 东), 其中包含扶梯口/电梯厅
    b1_spine = [
        ("b1_w",   "B1西通道口",   "corridor", 120, 200),
        ("esc1_b1", "1号扶梯·B1", "escalator", 300, 200),
        ("j1_b1",  "B1中央通道口", "corridor", 420, 200),
        ("elev_b1", "电梯厅·B1",  "elevator", 540, 200),
        ("j2_b1",  "B1东通道口",   "corridor", 660, 200),
        ("esc2_b1", "2号扶梯·B1", "escalator", 780, 200),
        ("b1_e",   "B1东端通道口", "corridor", 880, 200),
    ]
    for nid, name, typ, x, y in b1_spine:
        g.add_node(N(nid, name, typ, -1, x, y))

    # 地铁口
    g.add_node(N("metro_a", "地铁口A", "entrance", -1, 90, 100,
                 hours="06:00-23:30"))
    g.add_node(N("metro_b", "地铁口B", "entrance", -1, 900, 100,
                 hours="06:00-23:30"))
    # 服务台
    g.add_node(N("svc1", "顾客服务台", "service", -1, 420, 300,
                 hours="10:00-22:00"))

    # 北侧店铺(y=110)  (id, 名称, 接入通道节点, 营业中, 营业时间)
    north_shops = [
        ("s1", "星巴克",   "b1_w",    True,  "07:30-22:00"),
        ("s2", "优衣库",   "esc1_b1", True,  "10:00-22:00"),
        ("s3", "海底捞",   "j1_b1",   False, "暂停营业(装修)"),
        ("s4", "苹果店",   "elev_b1", True,  "10:00-22:00"),
        ("s5", "名创优品", "j2_b1",   True,  "10:00-21:30"),
    ]
    # 南侧店铺/服务(y=290 一带)
    south_shops = [
        ("s6",  "肯德基",   "b1_w",    True,  "07:00-22:30"),
        ("s7",  "万达影城", "esc1_b1", False, "10:00-次日02:00(设备维护)"),
        ("s8",  "屈臣氏",   "elev_b1", True,  "10:00-22:00"),
        ("s10", "华为体验店", "j2_b1", True,  "10:00-22:00"),
        ("s11", "绿茶餐厅", "esc2_b1", True,  "10:00-21:30"),
    ]
    shop_x = {"s1": 150, "s2": 300, "s3": 420, "s4": 540, "s5": 660,
              "s6": 150, "s7": 300, "s8": 540, "s10": 660, "s11": 820}
    for nid, name, door, is_open, hours in north_shops:
        g.add_node(N(nid, name, "shop", -1, shop_x[nid], 110,
                     open=is_open, hours=hours))
    for nid, name, door, is_open, hours in south_shops:
        g.add_node(N(nid, name, "shop", -1, shop_x[nid], 290,
                     open=is_open, hours=hours))

    # ---------------- B2 层 (floor = -2, 停车场) ----------------
    b2_spine = [
        ("b2_w",   "B2西通道口",   "corridor", 180, 560),
        ("esc1_b2", "1号扶梯·B2", "escalator", 300, 560),
        ("j3_b2",  "B2中央通道口", "corridor", 420, 560),
        ("elev_b2", "电梯厅·B2",  "elevator", 540, 560),
        ("j4_b2",  "B2东通道口",   "corridor", 660, 560),
        ("esc2_b2", "2号扶梯·B2", "escalator", 780, 560),
        ("b2_e",   "B2东端通道口", "corridor", 860, 560),
    ]
    for nid, name, typ, x, y in b2_spine:
        g.add_node(N(nid, name, typ, -2, x, y))
    g.add_node(N("park_a", "停车场A区", "parking", -2, 140, 650,
                 hours="24小时"))
    g.add_node(N("park_b", "停车场B区", "parking", -2, 860, 650,
                 hours="24小时"))

    # ---------------- 通道连接 ----------------
    def walk_seq(ids: List[str]) -> None:
        for a, b in zip(ids, ids[1:]):
            g.add_edge(a, b, "walk")

    walk_seq(["b1_w", "esc1_b1", "j1_b1", "elev_b1",
              "j2_b1", "esc2_b1", "b1_e"])
    walk_seq(["b2_w", "esc1_b2", "j3_b2", "elev_b2",
              "j4_b2", "esc2_b2", "b2_e"])

    # 地铁口/服务台/店铺 接入主通道
    g.add_edge("metro_a", "b1_w", "walk")
    g.add_edge("metro_b", "b1_e", "walk")
    g.add_edge("svc1", "j1_b1", "walk")
    for nid, _, door, _, _ in north_shops + south_shops:
        g.add_edge(nid, door, "walk")
    g.add_edge("park_a", "b2_w", "walk")
    g.add_edge("park_b", "b2_e", "walk")

    # ---------------- 竖向交通: 扶梯 / 电梯 ----------------
    g.add_edge("esc1_b1", "esc1_b2", "escalator")
    g.add_edge("esc2_b1", "esc2_b2", "escalator")
    g.add_edge("elev_b1", "elev_b2", "elevator")

    return g
