"""路径规划算法测试。"""
import pytest

from backend.data import (
    ELEVATOR_WAIT,
    ESC_SPEED,
    WALK_SPEED,
    build_graph,
)
from backend.router import RouteError, edge_cost, find_route, parse_now


@pytest.fixture()
def g():
    return build_graph()


# ---------- 图完整性 ----------
def test_graph_structure(g):
    # 3 层 15 家店 + 其他设施
    floors = {n.floor for n in g.nodes.values()}
    assert floors == {"B1", "B2", "B3"}
    shops = [n for n in g.nodes.values() if n.type == "shop"]
    assert len(shops) == 15
    assert len(g.edges) > 30
    # 无向图邻接对称
    for e in g.edges:
        assert any(b == e.b for _, b in g.adj[e.a])
        assert any(b == e.a for _, b in g.adj[e.b])


def test_all_non_shop_nodes_reachable(g):
    """任意两个非闭店 POI 都可达(电梯+扶梯保证竖向连通)。"""
    ids = [n.id for n in g.nodes.values() if n.type != "junction"]
    # 以地铁 A 口为根做 BFS(闭店边也保留, 因为闭店只是叶子)
    seen = {"sub_a"}
    stack = ["sub_a"]
    while stack:
        u = stack.pop()
        for _, v in g.adj[u]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    assert set(ids) <= seen


# ---------- 营业状态 ----------
def test_shop_open_status(g):
    # s5 装修: 任何时间都不开
    assert g.is_shop_open("s5", 12 * 60) is False
    assert g.is_shop_open("s13", 12 * 60) is False
    # 正常店铺
    assert g.is_shop_open("s1", 12 * 60) is True
    # 非店铺永远可作为终点
    assert g.is_shop_open("svc1", 0) is True


def test_shop_hours_boundaries(g):
    # 星巴克 10:00-22:00
    assert g.is_shop_open("s1", 10 * 60) is True
    assert g.is_shop_open("s1", 9 * 60 + 59) is False
    assert g.is_shop_open("s1", 22 * 60) is True
    assert g.is_shop_open("s1", 22 * 60 + 1) is False


def test_overnight_hours(g):
    # 海底捞 11:00-02:00 跨午夜
    assert g.is_shop_open("s10", 23 * 60) is True
    assert g.is_shop_open("s10", 1 * 60) is True
    assert g.is_shop_open("s10", 3 * 60) is False
    assert g.is_shop_open("s10", 10 * 60) is False


def test_24h_shop(g):
    # 全家 00:00-24:00 全天
    assert g.is_shop_open("s15", 0) is True
    assert g.is_shop_open("s15", 3 * 60) is True
    assert g.is_shop_open("s15", 23 * 60 + 59) is True


# ---------- 寻路: 基础 ----------
def test_same_floor_route(g):
    r = find_route(g, "sub_a", "s6", 12 * 60)
    # A口 -> j1 -> 肯德基
    assert r["node_chain"] == ["sub_a", "j1", "s6"]
    assert r["floors"] == ["B1"]
    assert r["transfers"] == 0
    assert r["total_seconds"] > 0


def test_route_steps_have_text(g):
    r = find_route(g, "sub_a", "s6", 12 * 60)
    assert len(r["steps"]) >= 1
    assert all("text" in s and s["text"] for s in r["steps"])
    assert all(s["floor"] == "B1" for s in r["steps"])


def test_unknown_node(g):
    with pytest.raises(RouteError) as ei:
        find_route(g, "sub_a", "nope", 12 * 60)
    assert ei.value.code == "unknown_node"


def test_same_start_end(g):
    with pytest.raises(RouteError) as ei:
        find_route(g, "s1", "s1", 12 * 60)
    assert ei.value.code == "same_point"


# ---------- 未营业店铺规则 ----------
def test_closed_shop_cannot_be_destination(g):
    # s5 装修中
    with pytest.raises(RouteError) as ei:
        find_route(g, "sub_a", "s5", 12 * 60)
    assert ei.value.code == "destination_closed"


def test_after_hours_shop_cannot_be_destination(g):
    # 星巴克早上 8 点没开门
    with pytest.raises(RouteError) as ei:
        find_route(g, "sub_a", "s1", 8 * 60)
    assert ei.value.code == "destination_closed"
    # 中午可到达
    assert find_route(g, "sub_a", "s1", 12 * 60)["end"] == "s1"


def test_closed_shop_allowed_as_start(g):
    # 未营业店铺可作为起点(顾客在店门口要离开)
    r = find_route(g, "s5", "sub_c", 12 * 60)
    assert r["node_chain"][0] == "s5"
    assert r["node_chain"][-1] == "sub_c"


def test_route_does_not_pass_through_closed_shop(g):
    """闭店边被剔除, 路径中不允许经过闭店(起点除外)。"""
    # s13 位于 B2 中庭南侧, 多次随机寻路不应穿过它
    for start, end in [("j_b2w", "j_b2e"), ("s8", "s14"),
                       ("park_a", "s10"), ("sub_a", "s12")]:
        r = find_route(g, start, end, 12 * 60)
        middle = set(r["node_chain"][1:-1])
        assert "s13" not in middle
        assert "s5" not in middle


# ---------- 跨层 ----------
def test_cross_floor_route(g):
    r = find_route(g, "sub_a", "s14", 12 * 60)  # 盒马 B2
    assert r["floors"] == ["B1", "B2"]
    assert r["transfers"] == 1
    kinds = [e["kind"] for e in r["edges"]]
    assert "escalator" in kinds or "elevator" in kinds
    # 指引中必须出现垂直交通段
    assert any(s["type"] in ("escalator", "elevator") for s in r["steps"])


def test_b3_parking_to_b1(g):
    r = find_route(g, "park_a", "sub_c", 12 * 60)
    assert r["floors"][0] == "B3"
    assert r["floors"][-1] == "B1"
    assert r["transfers"] == 2


def test_24h_shop_reachable_at_night(g):
    r = find_route(g, "park_b", "s15", 2 * 60)
    assert r["end"] == "s15"
    # 深夜海底捞仍营业
    r2 = find_route(g, "park_a", "s10", 1 * 60)
    assert r2["end"] == "s10"


def test_elevator_wait_cost(g):
    # 电梯边成本 = 等待 + 层高/扶梯速度
    elv_edge = next(e for e in g.edges
                    if e.a == "elv1_1" and e.b == "elv1_2")
    cost = edge_cost(elv_edge, g)
    assert cost == pytest.approx(ELEVATOR_WAIT / 60 + 6 / ESC_SPEED)


def test_total_time_consistency(g):
    r = find_route(g, "park_a", "s1", 12 * 60)
    recomputed = 0.0
    for einfo in r["edges"]:
        e = next(x for x in g.edges
                 if {x.a, x.b} == {einfo["a"], einfo["b"]} and x.kind == einfo["kind"])
        recomputed += edge_cost(e, g)
    assert r["total_seconds"] == round(recomputed * 60)


def test_walk_meters_only_corridor(g):
    r = find_route(g, "park_a", "sub_b", 12 * 60)
    corridor_meters = sum(
        e.meters for e in g.edges
        if e.kind == "corridor"
        and any({e.a, e.b} == {p["a"], p["b"]} for p in
                ({"a": x["a"], "b": x["b"]} for x in r["edges"]))
    )
    assert r["walk_meters"] == round(corridor_meters)
    assert r["walk_meters"] > 0


# ---------- 时间参数 ----------
def test_parse_now():
    assert parse_now("08:30") == 510
    assert parse_now(None) is None
    assert parse_now("") is None
    with pytest.raises(RouteError):
        parse_now("8点")
    with pytest.raises(RouteError):
        parse_now("25:00")
