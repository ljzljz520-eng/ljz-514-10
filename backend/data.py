"""商场数据模型与地图数据。

包含 3 个楼层(B1/B2/B3)的室内导航图:
- B1: 地铁口 A/B/C、B1 层店铺、服务台、扶梯/电梯
- B2: B2 层店铺、服务台、扶梯/电梯
- B3: 停车场 A/B/C、24 小时便利店、扶梯/电梯
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# ---------- 全局参数 ----------
WALK_SPEED = 75.0          # 通道步行速度 (米/分钟)
ESC_SPEED = 30.0           # 扶梯等效移动速度 (米/分钟)
FLOOR_HEIGHT = 6.0         # 每层层高 (米), 扶梯/电梯的垂直移动距离
ELEVATOR_WAIT = 30.0       # 电梯平均等待时间 (秒)

FLOORS = [
    {"id": "B1", "name": "B1 层", "order": 1},
    {"id": "B2", "name": "B2 层", "order": 2},
    {"id": "B3", "name": "B3 层", "order": 3},
]
FLOOR_ORDER = {"B1": 1, "B2": 2, "B3": 3}

TYPE_LABELS = {
    "subway": "地铁口",
    "shop": "店铺",
    "service": "服务台",
    "parking": "停车场",
    "escalator": "扶梯",
    "elevator": "电梯",
    "junction": "通道节点",
}

# 用于前端下拉框的可选起点/终点类型
SELECTABLE_TYPES = ["subway", "shop", "service", "parking"]


@dataclass
class Node:
    id: str
    name: str
    floor: str
    type: str
    x: float
    y: float
    open: bool = True                 # 店铺是否营业(装修/歇业为 False)
    hours: Optional[str] = None       # 营业时间, 如 "10:00-22:00", 24h 店为 "00:00-24:00"


@dataclass
class Edge:
    a: str
    b: str
    kind: str = "corridor"            # corridor / escalator / elevator
    meters: float = 0.0               # 物理距离(垂直交通按层高计)
    floors: list = field(default_factory=list)  # 该边涉及的楼层(用于扶梯/电梯)


class MallGraph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.adj: dict[str, list[tuple[Edge, str]]] = {}

    def add_node(self, **kw):
        n = Node(**kw)
        self.nodes[n.id] = n
        self.adj.setdefault(n.id, [])
        return n

    def add_edge(self, a, b, kind="corridor", meters=None, floors=None):
        if meters is None:
            na, nb = self.nodes[a], self.nodes[b]
            meters = math.hypot(na.x - nb.x, na.y - nb.y)
        e = Edge(a=a, b=b, kind=kind, meters=round(meters, 2),
                 floors=floors or [])
        self.edges.append(e)
        self.adj[a].append((e, b))
        self.adj[b].append((e, a))
        return e

    # ---------- 营业状态 ----------
    @staticmethod
    def _parse_hours(hours: str, now_minutes: int):
        """解析时间段字符串, 返回 (start, end) 分钟数; 支持跨午夜与 24:00。"""
        start_s, end_s = hours.split("-")

        def to_min(t):
            h, m = t.split(":")
            return int(h) * 60 + int(m)

        start, end = to_min(start_s), to_min(end_s)
        if end <= start:              # 跨午夜(含 24:00 收尾的 24h 写法)
            end += 24 * 60
        if now_minutes < start:
            now_minutes += 24 * 60
        return start <= now_minutes <= end

    def is_shop_open(self, node_id: str, now_minutes: Optional[int] = None) -> bool:
        """判断店铺当前是否营业: open 标记 + 营业时间(可选)。"""
        n = self.nodes[node_id]
        if n.type != "shop":
            return True
        if not n.open:
            return False
        if n.hours and now_minutes is not None:
            return self._parse_hours(n.hours, now_minutes)
        return True

    def floor_of(self, node_id: str) -> str:
        return self.nodes[node_id].floor


def build_graph() -> MallGraph:
    g = MallGraph()

    def shop(id, name, floor, x, y, hours="10:00-22:00", open_=True):
        g.add_node(id=id, name=name, floor=floor, type="shop",
                   x=x, y=y, open=open_, hours=hours)

    # ================= B1 =================
    g.add_node(id="sub_a", name="地铁 A 口", floor="B1", type="subway", x=20, y=130)
    g.add_node(id="sub_b", name="地铁 B 口", floor="B1", type="subway", x=20, y=158)
    g.add_node(id="j1", name="AB 口换乘节点", floor="B1", type="junction", x=70, y=144)
    g.add_node(id="sub_c", name="地铁 C 口", floor="B1", type="subway", x=500, y=144)

    g.add_node(id="j_h1", name="B1 中庭", floor="B1", type="junction", x=260, y=144)
    g.add_node(id="esc1_1", name="1 号扶梯(B1)", floor="B1", type="escalator", x=200, y=104)
    g.add_node(id="esc2_1", name="2 号扶梯(B1)", floor="B1", type="escalator", x=320, y=184)
    g.add_node(id="elv1_1", name="1 号电梯(B1)", floor="B1", type="elevator", x=232, y=100)
    g.add_node(id="svc1", name="B1 服务台", floor="B1", type="service", x=288, y=104)

    for a, b in [("sub_a", "j1"), ("sub_b", "j1"), ("j1", "j_h1"),
                 ("j_h1", "sub_c")]:
        g.add_edge(a, b)
    for p in ("esc1_1", "elv1_1", "svc1", "esc2_1"):
        g.add_edge("j_h1", p)

    shop("s1", "星巴克咖啡", "B1", 120, 60)
    shop("s2", "优衣库", "B1", 175, 55)
    shop("s3", "名创优品", "B1", 250, 55)
    shop("s4", "华为体验店", "B1", 330, 60)
    shop("s5", "巴黎贝甜(装修中)", "B1", 410, 65, open_=False)
    shop("s6", "肯德基", "B1", 140, 230, hours="07:00-22:30")
    shop("s7", "屈臣氏", "B1", 380, 230)
    for s, p in [("s1", "j1"), ("s2", "esc1_1"), ("s3", "j_h1"),
                 ("s4", "svc1"), ("s5", "sub_c"), ("s6", "j1"),
                 ("s7", "esc2_1")]:
        g.add_edge(s, p)

    # ================= B2 =================
    g.add_node(id="j_b2w", name="B2 西通道", floor="B2", type="junction", x=70, y=144)
    g.add_node(id="j_h2", name="B2 中庭", floor="B2", type="junction", x=260, y=144)
    g.add_node(id="j_b2e", name="B2 东通道", floor="B2", type="junction", x=450, y=144)
    g.add_node(id="esc1_2", name="1 号扶梯(B2)", floor="B2", type="escalator", x=200, y=104)
    g.add_node(id="esc2_2", name="2 号扶梯(B2)", floor="B2", type="escalator", x=320, y=184)
    g.add_node(id="elv1_2", name="1 号电梯(B2)", floor="B2", type="elevator", x=232, y=100)
    g.add_node(id="svc2", name="B2 服务台", floor="B2", type="service", x=288, y=104)

    for a, b in [("j_b2w", "j_h2"), ("j_h2", "j_b2e")]:
        g.add_edge(a, b)
    for p in ("esc1_2", "elv1_2", "svc2", "esc2_2"):
        g.add_edge("j_h2", p)

    shop("s8", "西西弗书店", "B2", 120, 60)
    shop("s9", "耐克", "B2", 175, 55, hours="10:00-21:30")
    shop("s10", "海底捞", "B2", 340, 60, hours="11:00-02:00")  # 跨午夜
    shop("s11", "小米之家", "B2", 410, 75)
    shop("s12", "安踏", "B2", 130, 230)
    shop("s13", "撤店招商中", "B2", 250, 235, open_=False)
    shop("s14", "盒马鲜生", "B2", 400, 230, hours="09:00-22:00")
    for s, p in [("s8", "j_b2w"), ("s9", "esc1_2"), ("s10", "svc2"),
                 ("s11", "j_b2e"), ("s12", "j_b2w"), ("s13", "j_h2"),
                 ("s14", "j_b2e")]:
        g.add_edge(s, p)

    # ================= B3(停车场) =================
    g.add_node(id="park_a", name="停车场 A 区", floor="B3", type="parking", x=20, y=144)
    g.add_node(id="park_b", name="停车场 B 区", floor="B3", type="parking", x=500, y=144)
    g.add_node(id="j_h3", name="B3 中庭", floor="B3", type="junction", x=260, y=144)
    g.add_node(id="esc1_3", name="1 号扶梯(B3)", floor="B3", type="escalator", x=200, y=104)
    g.add_node(id="esc2_3", name="2 号扶梯(B3)", floor="B3", type="escalator", x=320, y=184)
    g.add_node(id="elv1_3", name="1 号电梯(B3)", floor="B3", type="elevator", x=232, y=100)
    shop("s15", "全家便利店", "B3", 288, y=104, hours="00:00-24:00")

    for a, b in [("park_a", "j_h3"), ("j_h3", "park_b")]:
        g.add_edge(a, b)
    for p in ("esc1_3", "elv1_3", "esc2_3", "s15"):
        g.add_edge("j_h3", p)

    # ================= 垂直交通(层间连接) =================
    esc1 = ["esc1_1", "esc1_2", "esc1_3"]
    esc2 = ["esc2_1", "esc2_2", "esc2_3"]
    elv = ["elv1_1", "elv1_2", "elv1_3"]
    for chain in (esc1, esc2, elv):
        kind = "escalator" if chain is not elv else "elevator"
        for lo, hi in zip(chain, chain[1:]):
            floors = sorted({g.nodes[lo].floor, g.nodes[hi].floor},
                            key=lambda f: FLOOR_ORDER[f])
            g.add_edge(lo, hi, kind=kind, meters=FLOOR_HEIGHT, floors=floors)

    return g
