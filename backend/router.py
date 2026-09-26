"""路径规划算法。

规则:
* 基于 Dijkstra 在无向加权图上求最短路, 边的权重为"通过耗时(秒)"。
* 普通通道按距离 / 步行速度计; 扶梯、电梯有固定通过时间,
  并可通过 preference(escalator/elevator) 对另一类竖向交通施加惩罚,
  从而在"同样可达"时优先选择顾客偏好的跨层方式。
* 未营业的店铺不允许作为终点(起点也不允许), 其他类型节点始终可达。
* 不允许把未营业店铺当作路径中间点穿行(闭店即通道关闭)。
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Dict, List, Optional

from .graph import FLOOR_NAMES, MallGraph, Node

# ---- 通过耗时参数(秒) ----
WALK_SPEED_MPS = 1.2        # 平均步行速度 米/秒
ESCALATOR_TIME = 25.0       # 扶梯跨层通过时间(含步行至梯级)
ELEVATOR_TIME = 35.0        # 电梯跨层通过时间(等候+乘梯)
# 偏好惩罚系数: 偏好扶梯时电梯乘惩罚系数, 反之亦然
PREFER_PENALTY = 4.0

CONNECTOR_TIME = {"escalator": ESCALATOR_TIME,
                  "elevator": ELEVATOR_TIME}
CONNECTOR_VERB = {"escalator": "乘坐扶梯", "elevator": "乘坐电梯"}

# 不相邻楼层间竖向移动的相对楼层描述
UP_TEXT, DOWN_TEXT = "上行", "下行"


class RouteError(ValueError):
    """路径规划业务异常。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class RouteSegment:
    kind: str
    instruction: str
    distance: float          # 仅 walk 段有距离
    floor_from: Optional[int]
    floor_to: Optional[int]

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "instruction": self.instruction,
            "distance": round(self.distance, 1),
            "floor_from": self.floor_from,
            "floor_to": self.floor_to,
        }


def edge_cost(kind: str, distance: float, preference: str) -> float:
    """计算一条边的通过成本(秒)。"""
    if kind == "walk":
        return distance / WALK_SPEED_MPS
    base = CONNECTOR_TIME[kind]
    if preference == "escalator" and kind == "elevator":
        return base * PREFER_PENALTY
    if preference == "elevator" and kind == "escalator":
        return base * PREFER_PENALTY
    return base


def _check_poi(graph: MallGraph, node_id: str, role: str) -> Node:
    if node_id not in graph.nodes:
        raise RouteError("NODE_NOT_FOUND", f"{role}不存在: {node_id}")
    node = graph.nodes[node_id]
    if not node.is_poi():
        raise RouteError("INVALID_POI",
                         f"{node.name} 不是可选择的地点")
    if node.type == "shop" and not node.open:
        raise RouteError("DESTINATION_CLOSED",
                         f"「{node.name}」当前未营业, 无法{role}")
    return node


def dijkstra(graph: MallGraph, start: str, goal: str,
             preference: str = "none") -> List[str]:
    """返回节点 id 序列; 不可达时抛出 RouteError。闭店节点被整体剔除。"""
    dist: Dict[str, float] = {start: 0.0}
    prev: Dict[str, Optional[str]] = {start: None}
    pq = [(0.0, start)]
    visited = set()

    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == goal:
            break
        for v, edge in graph.adj[u]:
            # 闭店节点不可穿行(终点/起点在调用前已单独校验)
            vn = graph.nodes[v]
            if vn.type == "shop" and not vn.open and v != goal:
                continue
            nd = d + edge_cost(edge.kind, edge.distance, preference)
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))

    if goal not in prev:
        raise RouteError("NO_ROUTE", "当前条件下没有可达路径")

    path: List[str] = []
    cur: Optional[str] = goal
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return path


def _floor_move_text(f_from: int, f_to: int) -> str:
    # 楼层编号越大越靠上(-1 在 -2 之上)
    if f_to > f_from:
        return UP_TEXT
    return DOWN_TEXT


def _compass(graph: MallGraph, a: str, b: str) -> str:
    """依据渲染坐标给出粗略方位(通道基本为横/纵布局)。"""
    na, nb = graph.nodes[a], graph.nodes[b]
    dx, dy = nb.x - na.x, nb.y - na.y
    if abs(dx) >= abs(dy):
        return "向东" if dx > 0 else "向西"
    return "向南" if dy > 0 else "向北"


def build_segments(graph: MallGraph, path: List[str]) -> List[RouteSegment]:
    """把节点序列压缩为"步行段 + 跨层段"指令。"""
    segments: List[RouteSegment] = []
    # 找 path 上的边
    edge_between = {}
    for a, b in zip(path, path[1:]):
        for v, e in graph.adj[a]:
            if v == b:
                edge_between[(a, b)] = e
                break

    i = 0
    n = len(path)
    while i < n - 1:
        a, b = path[i], path[i + 1]
        edge = edge_between[(a, b)]
        if edge.kind in ("escalator", "elevator"):
            na, nb = graph.nodes[a], graph.nodes[b]
            move = _floor_move_text(na.floor, nb.floor)
            segments.append(RouteSegment(
                kind=edge.kind,
                instruction=(f"{CONNECTOR_VERB[edge.kind]}{move}, "
                             f"从 {FLOOR_NAMES[na.floor]} 层前往 "
                             f"{FLOOR_NAMES[nb.floor]} 层"),
                distance=0.0,
                floor_from=na.floor, floor_to=nb.floor,
            ))
            i += 1
        else:
            # 合并连续 walk 边, 直到下一个竖向边/终点
            j = i
            distance = 0.0
            while j < n - 1 and edge_between[(path[j], path[j + 1])].kind == "walk":
                distance += edge_between[(path[j], path[j + 1])].distance
                j += 1
            from_id, to_id = path[i], path[j]
            fn, tn = graph.nodes[from_id], graph.nodes[to_id]
            direction = _compass(graph, from_id, to_id)
            if tn.is_poi() and tn.type != "corridor":
                target = f"到达「{tn.name}」"
            else:
                target = f"前往 {tn.name}"
            segments.append(RouteSegment(
                kind="walk",
                instruction=f"沿 {fn.name} {direction}步行, {target}",
                distance=distance,
                floor_from=fn.floor, floor_to=tn.floor,
            ))
            i = j

    if segments:
        last = graph.nodes[path[-1]]
        segments.append(RouteSegment(
            kind="arrive",
            instruction=f"抵达终点「{last.name}」"
                        + (f"（{last.hours}）" if last.hours else ""),
            distance=0.0,
            floor_from=last.floor, floor_to=last.floor,
        ))
    return segments


def plan_route(graph: MallGraph, start_id: str, goal_id: str,
               preference: str = "none") -> dict:
    """规划路径主入口, 返回可直接序列化的结果。"""
    if start_id == goal_id:
        raise RouteError("SAME_POINT", "起点和终点不能相同")
    start = _check_poi(graph, start_id, "作为起点")
    goal = _check_poi(graph, goal_id, "作为终点")

    path = dijkstra(graph, start_id, goal_id, preference)
    segments = build_segments(graph, path)

    # 统计: 总步行距离 / 跨层方式 / 用时
    walk_meters = 0.0
    connectors: List[str] = []
    floors_passed: List[int] = []
    for a, b in zip(path, path[1:]):
        edge = None
        for v, e in graph.adj[a]:
            if v == b:
                edge = e
                break
        assert edge is not None
        if edge.kind == "walk":
            walk_meters += edge.distance
        else:
            connectors.append(edge.kind)
        f = graph.nodes[a].floor
        if not floors_passed or floors_passed[-1] != f:
            floors_passed.append(f)
    f = graph.nodes[path[-1]].floor
    if not floors_passed or floors_passed[-1] != f:
        floors_passed.append(f)

    total_seconds = 0.0
    for a, b in zip(path, path[1:]):
        for v, e in graph.adj[a]:
            if v == b:
                total_seconds += edge_cost(e.kind, e.distance, preference)
                break

    return {
        "start": start.to_dict(),
        "goal": goal.to_dict(),
        "preference": preference,
        "path": path,
        "segments": [s.to_dict() for s in segments],
        "walk_meters": round(walk_meters, 1),
        "connectors": connectors,
        "floors": floors_passed,
        "estimated_seconds": round(total_seconds),
    }
