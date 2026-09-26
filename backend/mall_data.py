# -*- coding: utf-8 -*-
"""地下商业街地图数据。

坐标单位：米（既用于计算通道步行距离，也供前端 SVG 渲染）。
楼层：B1 = 商业层（地铁口、店铺、服务台）；B2 = 商业 + 停车场。

节点类型 type：
  subway    地铁口
  shop      店铺（含营业时间 hours / 暂停营业 force_closed）
  service   服务台
  parking   停车场
  escalator 扶梯（跨层设施，每层一个节点，如 E1_B1 / E1_B2）
  elevator  电梯（跨层设施，每层一个节点，如 L1_B1 / L1_B2）
  junction  通道交汇口（仅用于路网，不可选为起终点）
"""

NODES = {
    # ---------------- B1 层 ----------------
    "M1":    {"name": "地铁A口", "type": "subway",    "floor": "B1", "x": 100, "y": 100},
    "C1":    {"name": "通道口C1", "type": "junction", "floor": "B1", "x": 300, "y": 100},
    "C2":    {"name": "通道口C2", "type": "junction", "floor": "B1", "x": 500, "y": 100},
    "M2":    {"name": "地铁B口", "type": "subway",    "floor": "B1", "x": 700, "y": 100},

    "E1_B1": {"name": "扶梯①",  "type": "escalator", "floor": "B1", "x": 100, "y": 250},
    "F101":  {"name": "咖啡店",  "type": "shop",      "floor": "B1", "x": 300, "y": 250,
              "hours": "07:30-21:00"},
    "S1":    {"name": "服务台",  "type": "service",   "floor": "B1", "x": 500, "y": 250},
    "F102":  {"name": "书店",    "type": "shop",      "floor": "B1", "x": 700, "y": 250,
              "hours": "10:00-22:00"},

    "F103":  {"name": "服装店",  "type": "shop",      "floor": "B1", "x": 100, "y": 400,
              "hours": "10:00-22:00", "force_closed": True},   # 装修暂停营业
    "C3":    {"name": "通道口C3", "type": "junction", "floor": "B1", "x": 300, "y": 400},
    "E2_B1": {"name": "扶梯②",  "type": "escalator", "floor": "B1", "x": 500, "y": 400},
    "L1_B1": {"name": "电梯",    "type": "elevator",  "floor": "B1", "x": 700, "y": 400},

    # ---------------- B2 层 ----------------
    "P1":    {"name": "停车场",  "type": "parking",   "floor": "B2", "x": 100, "y": 100},
    "D1":    {"name": "通道口D1", "type": "junction", "floor": "B2", "x": 300, "y": 100},
    "F201":  {"name": "超市",    "type": "shop",      "floor": "B2", "x": 500, "y": 100,
              "hours": "09:00-21:30"},
    "D2":    {"name": "通道口D2", "type": "junction", "floor": "B2", "x": 700, "y": 100},

    "E1_B2": {"name": "扶梯①",  "type": "escalator", "floor": "B2", "x": 100, "y": 250},
    "F202":  {"name": "母婴店",  "type": "shop",      "floor": "B2", "x": 300, "y": 250,
              "hours": "10:00-21:00"},
    "S2":    {"name": "服务台",  "type": "service",   "floor": "B2", "x": 500, "y": 250},
    "F203":  {"name": "健身房",  "type": "shop",      "floor": "B2", "x": 700, "y": 250,
              "hours": "06:00-23:00"},

    "D3":    {"name": "通道口D3", "type": "junction", "floor": "B2", "x": 100, "y": 400},
    "D4":    {"name": "通道口D4", "type": "junction", "floor": "B2", "x": 300, "y": 400},
    "E2_B2": {"name": "扶梯②",  "type": "escalator", "floor": "B2", "x": 500, "y": 400},
    "L1_B2": {"name": "电梯",    "type": "elevator",  "floor": "B2", "x": 700, "y": 400},
}

# 通道（步行边，距离由坐标自动计算）
CORRIDORS = [
    # B1 横向通道
    ("M1", "C1"), ("C1", "C2"), ("C2", "M2"),
    ("E1_B1", "F101"), ("F101", "S1"), ("S1", "F102"),
    ("F103", "C3"), ("C3", "E2_B1"), ("E2_B1", "L1_B1"),
    # B1 纵向通道
    ("M1", "E1_B1"), ("E1_B1", "F103"),
    ("C1", "F101"), ("F101", "C3"),
    ("C2", "S1"), ("S1", "E2_B1"),
    ("M2", "F102"), ("F102", "L1_B1"),
    # B2 横向通道
    ("P1", "D1"), ("D1", "F201"), ("F201", "D2"),
    ("E1_B2", "F202"), ("F202", "S2"), ("S2", "F203"),
    ("D3", "D4"), ("D4", "E2_B2"), ("E2_B2", "L1_B2"),
    # B2 纵向通道
    ("P1", "E1_B2"), ("E1_B2", "D3"),
    ("D1", "F202"), ("F202", "D4"),
    ("F201", "S2"), ("S2", "E2_B2"),
    ("D2", "F203"), ("F203", "L1_B2"),
]

# 扶梯（连接同一设施在两层间的节点）
ESCALATORS = [("E1_B1", "E1_B2"), ("E2_B1", "E2_B2")]

# 电梯
ELEVATORS = [("L1_B1", "L1_B2")]
