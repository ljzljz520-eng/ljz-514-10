"""路径规划核心算法。

权重(分钟):
- 通道 corridor : 距离 / 步行速度
- 扶梯 escalator: 层高 / 扶梯速度
- 电梯 elevator : 等待时间 + 层高 / 电梯速度
未营业店铺的边不参与寻路(但允许未营业店铺作为起点)。
"""
from __future__ import annotations

import heapq
import math

from .data import (
    ELEVATOR_WAIT,
    ESC_SPEED,
    FLOOR_ORDER,
    WALK_SPEED,
    MallGraph,
)

TURN_THRESHOLD = 0.35          # 叉积/模长, 低于该值视为直行
U_TURN_THRESHOLD = -0.35


class RouteError(ValueError):
    """寻路业务异常, code 用于前端区分错误类型。"""

    def __init__(self, message, code="bad_request"):
        super().__init__(message)
        self.code = code


def parse_now(now: str | None) -> int | None:
    """把 'HH:MM' 转为当天分钟数, None 表示不校验营业时间。"""
    if now is None or now == "":
        return None
    try:
        h, m = now.split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        raise RouteError("时间格式应为 HH:MM", "invalid_time")
    if not (0 <= h <= 24 and 0 <= m <= 59) or (h == 24 and m != 0):
        raise RouteError("时间超出范围", "invalid_time")
    return h * 60 + m


def edge_cost(e, g: MallGraph) -> float:
    """单边通行时间(分钟)。"""
    if e.kind == "escalator":
        return e.meters / ESC_SPEED
    if e.kind == "elevator":
        return ELEVATOR_WAIT / 60.0 + e.meters / ESC_SPEED
    return e.meters / WALK_SPEED


def _turn_text(vx, vy, px, py) -> str | None:
    """根据前进方向 (px,py)->(vx,vy) 判断转向, 屏幕坐标 y 向下。"""
    pl = math.hypot(px, py)
    vl = math.hypot(vx, vy)
    if pl == 0 or vl == 0:
        return None
    cross = (px * vy - py * vx) / (pl * vl)   # >0: 左转; <0: 右转
    if cross > TURN_THRESHOLD:
        return "左转"
    if cross < -TURN_THRESHOLD:
        return "右转"
    if vx * px + vy * py < 0:
        return "掉头"
    return "直行"


def _build_steps(g: MallGraph, node_chain: list[str],
                 edge_chain: list, walk_seconds: float):
    """把节点链切分为若干段(同楼层通道段 / 垂直交通段), 生成步行指引。"""
    steps = []
    i = 0
    n = len(node_chain)

    while i < n - 1:
        e = edge_chain[i]

        # ---- 垂直交通段 ----
        if e.kind in ("escalator", "elevator"):
            n0, n1 = g.nodes[node_chain[i]], g.nodes[node_chain[i + 1]]
            if e.kind == "escalator":
                secs = round(e.meters / ESC_SPEED * 60)
                steps.append({
                    "type": "escalator",
                    "floor": n0.floor,
                    "text": f"在{n0.name}乘扶梯，由 {n0.floor} 层前往 {n1.floor} 层"
                            f"（约 {secs} 秒）",
                    "seconds": secs,
                })
            else:
                secs = round(ELEVATOR_WAIT + e.meters / ESC_SPEED * 60)
                steps.append({
                    "type": "elevator",
                    "floor": n0.floor,
                    "text": f"在{n0.name}等候并乘坐电梯（含等候约 "
                            f"{int(ELEVATOR_WAIT)} 秒），由 {n0.floor} 层到 {n1.floor} 层"
                            f"（共约 {secs} 秒）",
                    "seconds": secs,
                })
            i += 1
            continue

        # ---- 通道段: 收集连续的 corridor 边 ----
        seg_nodes = [node_chain[i]]
        dist = 0.0
        while i < n - 1 and edge_chain[i].kind == "corridor":
            dist += edge_chain[i].meters
            seg_nodes.append(node_chain[i + 1])
            i += 1

        floor = g.nodes[seg_nodes[0]].floor
        start_name = g.nodes[seg_nodes[0]].name
        end_name = g.nodes[seg_nodes[-1]].name
        secs = round(dist / WALK_SPEED * 60)

        # 在该段内寻找第一个明显转弯(参考方向为段首方向)
        turn = None
        if len(seg_nodes) >= 3:
            p0 = g.nodes[seg_nodes[0]]
            p1 = g.nodes[seg_nodes[1]]
            px, py = p1.x - p0.x, p1.y - p0.y
            for k in range(1, len(seg_nodes) - 1):
                a = g.nodes[seg_nodes[k]]
                b = g.nodes[seg_nodes[k + 1]]
                turn = _turn_text(b.x - a.x, b.y - a.y, px, py)
                if turn in ("左转", "右转", "掉头"):
                    turn = f"，途经{a.name}{turn}"
                    break
            else:
                turn = ""
        else:
            turn = ""

        steps.append({
            "type": "corridor",
            "floor": floor,
            "text": f"在 {floor} 层从{start_name}出发，沿通道步行约 {round(dist)} 米"
                    f"（约 {secs} 秒）到达{end_name}{turn}",
            "meters": round(dist),
            "seconds": secs,
        })

    return steps


def find_route(g: MallGraph, start: str, end: str,
               now_minutes: int | None = None) -> dict:
    """主寻路函数。返回路径、分段指引与统计信息。"""
    if start not in g.nodes:
        raise RouteError(f"起点不存在: {start}", "unknown_node")
    if end not in g.nodes:
        raise RouteError(f"终点不存在: {end}", "unknown_node")
    if start == end:
        raise RouteError("起点与终点相同", "same_point")

    end_node = g.nodes[end]
    if end_node.type == "shop" and not g.is_shop_open(end, now_minutes):
        reason = "店铺未营业" if end_node.open else "店铺歇业/装修中"
        raise RouteError(f"终点「{end_node.name}」当前{reason}，不能作为终点",
                         "destination_closed")

    # 未营业店铺只能作为起点: 除起点外, 闭店邻接边一律剔除
    def edge_usable(e) -> bool:
        for ep in (e.a, e.b):
            n = g.nodes[ep]
            if ep == start:
                continue
            if n.type == "shop" and not g.is_shop_open(ep, now_minutes):
                return False
        return True

    # Dijkstra
    dist = {start: 0.0}
    prev: dict[str, tuple[str, object]] = {}
    pq = [(0.0, start)]
    visited = set()

    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == end:
            break
        for e, v in g.adj[u]:
            if v in visited or not edge_usable(e):
                continue
            nd = d + edge_cost(e, g)
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = (u, e)
                heapq.heappush(pq, (nd, v))

    if end not in dist:
        raise RouteError("两点之间没有可达路径", "no_route")

    # 还原路径
    node_chain = [end]
    edge_chain = []
    cur = end
    while cur != start:
        u, e = prev[cur]
        edge_chain.append(e)
        node_chain.append(u)
        cur = u
    node_chain.reverse()
    edge_chain.reverse()

    walk_meters = round(sum(e.meters for e in edge_chain
                            if e.kind == "corridor"))
    walk_seconds = sum(e.meters / WALK_SPEED * 60 for e in edge_chain
                       if e.kind == "corridor")
    vertical = [e for e in edge_chain if e.kind in ("escalator", "elevator")]
    esc_count = sum(1 for e in vertical if e.kind == "escalator")
    elv_count = sum(1 for e in vertical if e.kind == "elevator")
    vertical_seconds = sum(
        e.meters / ESC_SPEED * 60
        + (ELEVATOR_WAIT if e.kind == "elevator" else 0)
        for e in vertical
    )
    total_seconds = round(walk_seconds + vertical_seconds)

    steps = _build_steps(g, node_chain, edge_chain, walk_seconds)
    floors = []
    for nid in node_chain:
        f = g.nodes[nid].floor
        if not floors or floors[-1] != f:
            floors.append(f)

    return {
        "start": start,
        "end": end,
        "node_chain": node_chain,
        "edges": [
            {"a": e.a, "b": e.b, "kind": e.kind} for e in edge_chain
        ],
        "floors": floors,
        "transfers": len(floors) - 1,
        "walk_meters": walk_meters,
        "escalator_count": esc_count,
        "elevator_count": elv_count,
        "total_seconds": total_seconds,
        "steps": steps,
    }
