# -*- coding: utf-8 -*-
"""地下商业街路径规划核心算法。

图模型：
  节点 = 地铁口 / 店铺 / 服务台 / 停车场 / 扶梯 / 电梯 / 通道口
  边   = 通道（步行）、扶梯、电梯
权重：时间（秒）
  通道 = 距离 / 步行速度；扶梯 / 电梯 = 固定耗时
模式：
  fastest    最快路线（扶梯 + 电梯均可用）
  accessible 无障碍（仅电梯，适合轮椅 / 婴儿车 / 大件行李）
营业状态：
  未营业的店铺不能作为终点（可作为起点，例如顾客从刚打烊的店离开）。
"""
from __future__ import annotations

import heapq
import math
from datetime import datetime

from mall_data import NODES, CORRIDORS, ESCALATORS, ELEVATORS

WALK_SPEED = 1.2       # 步行速度（米/秒）
ESCALATOR_TIME = 45.0  # 扶梯运行耗时（秒）
ELEVATOR_TIME = 75.0   # 电梯候梯 + 运行耗时（秒）

MODE_FASTEST = "fastest"
MODE_ACCESSIBLE = "accessible"
MODES = (MODE_FASTEST, MODE_ACCESSIBLE)


class UnknownNodeError(ValueError):
    """起点或终点不存在。"""


class ClosedShopError(ValueError):
    """终点店铺未营业。"""


class NoRouteError(ValueError):
    """两点之间不存在可达路径。"""


def _parse_hhmm(text):
    h, m = text.split(":")
    return int(h) * 60 + int(m)


def is_open(node, now=None):
    """判断节点当前是否可用（营业）。

    - 非店铺（地铁口 / 服务台 / 停车场等）始终可用；
    - 店铺标记 force_closed（如装修暂停营业）则不可用；
    - 店铺设置 hours（如 "10:00-22:00"，支持跨零点）按时间判断；
    - now 可传 "HH:MM" 字符串或 datetime，便于测试与演示。
    """
    if node.get("type") != "shop":
        return True
    if node.get("force_closed"):
        return False
    hours = node.get("hours")
    if not hours:
        return True
    if now is None:
        now = datetime.now()
    cur = now.hour * 60 + now.minute if isinstance(now, datetime) else _parse_hhmm(now)
    start_s, end_s = hours.split("-")
    start, end = _parse_hhmm(start_s), _parse_hhmm(end_s)
    if end <= start:  # 跨零点，如 "22:00-02:00"
        return cur >= start or cur < end
    return start <= cur < end


class Mall:
    """地下商业街图模型 + 路径规划。"""

    def __init__(self, nodes=None, corridors=None, escalators=None, elevators=None):
        self.nodes = dict(NODES if nodes is None else nodes)
        self.adj = {nid: [] for nid in self.nodes}  # nid -> [(nbr, kind, time, dist)]
        for a, b in (CORRIDORS if corridors is None else corridors):
            d = self._distance(a, b)
            self._add_edge(a, b, "corridor", d / WALK_SPEED)
        for a, b in (ESCALATORS if escalators is None else escalators):
            self._add_edge(a, b, "escalator", ESCALATOR_TIME)
        for a, b in (ELEVATORS if elevators is None else elevators):
            self._add_edge(a, b, "elevator", ELEVATOR_TIME)

    # ---------------- 建图 ----------------
    def _distance(self, a, b):
        na, nb = self.nodes[a], self.nodes[b]
        return math.hypot(na["x"] - nb["x"], na["y"] - nb["y"])

    def _add_edge(self, a, b, kind, time_cost):
        if a not in self.nodes or b not in self.nodes:
            raise UnknownNodeError(f"边引用了不存在的节点: {a}-{b}")
        self.adj[a].append((b, kind, time_cost))
        self.adj[b].append((a, kind, time_cost))

    # ---------------- 查询 ----------------
    def list_pois(self, now=None):
        """可选起终点列表（按类型分组），店铺附带营业状态。"""
        groups = {"subway": [], "shop": [], "service": [], "parking": []}
        for nid, n in self.nodes.items():
            t = n["type"]
            if t not in groups:
                continue
            item = {"id": nid, "name": n["name"], "floor": n["floor"]}
            if t == "shop":
                item["open"] = is_open(n, now)
                item["hours"] = n.get("hours", "全天")
            groups[t].append(item)
        return groups

    # ---------------- 路径规划 ----------------
    def find_route(self, start, end, mode=MODE_FASTEST, now=None):
        """规划 start -> end 的最优路径，返回路径、分段指引、总耗时与步行距离。"""
        for nid, role in ((start, "起点"), (end, "终点")):
            if nid not in self.nodes:
                raise UnknownNodeError(f"{role}不存在: {nid}")
        if mode not in MODES:
            raise ValueError(f"未知的规划模式: {mode}")
        end_node = self.nodes[end]
        if not is_open(end_node, now):
            raise ClosedShopError(f"「{end_node['name']}」当前未营业，不能作为终点")

        allowed = ({"corridor", "elevator"} if mode == MODE_ACCESSIBLE
                   else {"corridor", "escalator", "elevator"})
        path, kinds, total_time = self._dijkstra(start, end, allowed)
        walk_dist = sum(self._distance(path[i], path[i + 1])
                        for i, k in enumerate(kinds) if k == "corridor")
        return {
            "start": start,
            "end": end,
            "mode": mode,
            "total_time": round(total_time, 1),       # 秒
            "walk_distance": round(walk_dist, 1),     # 米
            "path": [dict(id=nid, **{k: self.nodes[nid][k]
                                     for k in ("name", "type", "floor", "x", "y")})
                     for nid in path],
            "edges": [{"from": path[i], "to": path[i + 1], "kind": kinds[i]}
                      for i in range(len(kinds))],
            "steps": self._build_steps(path, kinds),
        }

    def _dijkstra(self, start, end, allowed_kinds):
        dist = {start: 0.0}
        prev = {}  # node -> (prev_node, edge_kind)
        pq = [(0.0, 0, start)]
        seq = 1
        while pq:
            d, _, u = heapq.heappop(pq)
            if d > dist.get(u, math.inf):
                continue
            if u == end:
                break
            for v, kind, tcost in self.adj[u]:
                if kind not in allowed_kinds:
                    continue
                nd = d + tcost
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    prev[v] = (u, kind)
                    heapq.heappush(pq, (nd, seq, v))
                    seq += 1
        if end not in dist:
            raise NoRouteError(
                f"从「{self.nodes[start]['name']}」到「{self.nodes[end]['name']}」没有可达路径")
        path, kinds = [end], []
        node = end
        while node != start:
            pnode, kind = prev[node]
            kinds.append(kind)
            path.append(pnode)
            node = pnode
        path.reverse()
        kinds.reverse()
        return path, kinds, dist[end]

    def _build_steps(self, path, kinds):
        """把边序列合并为分段中文指引（连续步行合并为一段）。"""
        steps = []
        i, n = 0, len(kinds)
        while i < n:
            if kinds[i] == "corridor":
                j, dist = i, 0.0
                while j < n and kinds[j] == "corridor":
                    dist += self._distance(path[j], path[j + 1])
                    j += 1
                frm, to = self.nodes[path[i]], self.nodes[path[j]]
                steps.append({
                    "kind": "walk", "floor": frm["floor"],
                    "from": path[i], "to": path[j],
                    "distance": round(dist, 1), "time": round(dist / WALK_SPEED, 1),
                    "instruction": f"从「{frm['name']}」出发，沿{frm['floor']}层通道步行 "
                                   f"{dist:.0f} 米，到达「{to['name']}」",
                })
                i = j
            else:
                frm, to = self.nodes[path[i]], self.nodes[path[i + 1]]
                kind = kinds[i]
                tcost = ESCALATOR_TIME if kind == "escalator" else ELEVATOR_TIME
                label = "扶梯" if kind == "escalator" else "电梯"
                steps.append({
                    "kind": kind, "from": path[i], "to": path[i + 1],
                    "from_floor": frm["floor"], "to_floor": to["floor"],
                    "time": tcost,
                    "instruction": f"在「{frm['name']}」乘{label}，"
                                   f"从{frm['floor']}层前往{to['floor']}层（约{tcost:.0f}秒）",
                })
                i += 1
        dest = self.nodes[path[-1]]
        steps.append({"kind": "arrive",
                      "instruction": f"到达目的地「{dest['name']}」（{dest['floor']}层）"})
        return steps
