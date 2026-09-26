# 地下商业街智能导航系统

顾客可选择 **地铁口 / 店铺 / 服务台 / 停车场** 作为起终点，系统根据
**楼层、扶梯、电梯、通道距离和店铺营业状态** 规划最优步行路径；
**未营业的店铺不能作为终点（也不会作为途经点穿行）**。

- 后端：Python 3.10+ 标准库（零第三方依赖），Dijkstra 路径算法
- 前端：原生 HTML / CSS / JavaScript（SVG 地图，无构建步骤）
- 测试：内置 `unittest`（38 个用例），同样兼容 `pytest`

## 目录结构

```
.
├── run.py                 # 一键启动 Web 服务
├── run_tests.py           # 一键运行测试
├── backend/
│   ├── graph.py           # 图模型: 节点/边/楼层/营业状态/示例地图(B1+B2)
│   ├── router.py          # Dijkstra 算法、扶梯/电梯偏好、路径指令
│   ├── server.py          # REST API + 静态页面(标准库 http.server)
│   └── tests/
│       ├── test_graph.py    # 图结构与约束(10 例)
│       ├── test_router.py   # 路径算法与营业规则(16 例)
│       └── test_server.py   # REST API 端到端(6 例)
└── frontend/
    ├── index.html         # 演示页面
    ├── style.css
    └── app.js
```

## 快速开始

```bash
python3 run.py            # 默认 8000 端口, 可用 python3 run.py 9000 更换
```

浏览器打开 <http://127.0.0.1:8000> ：

1. 在左侧列表（或地图上）选择**起点**和**终点**（点「起 / 终」按钮）；
2. 选择跨层偏好：**自动 / 优先扶梯 / 优先电梯**；
3. 右侧显示总步行距离、预计用时、跨层方式与逐步导航，地图金色高亮路径；
4. 顶部楼层标签可切换 **B1 / B2 / 跨层示意**。

示例地图中 **海底捞(s3)**、**万达影城(s7)** 为未营业店铺，无法选为终点。

运行测试：

```bash
python3 run_tests.py
# 或安装 pytest 后: pytest backend/tests
```

## 算法说明

- 图为无向加权图；边类型：`walk`（水平通道）、`escalator`（扶梯）、`elevator`（电梯）。
- Dijkstra 以**通过耗时（秒）**为权重：
  - 步行 = 通道距离 ÷ 1.2 m/s；
  - 扶梯跨层固定 25 秒，电梯跨层固定 35 秒（含等候）；
  - 当顾客选择偏好（扶梯/电梯）时，另一类竖向交通的耗时按 4 倍惩罚，
    从而在可达前提下优先使用偏好设施。
- 搜索过程中直接跳过未营业店铺节点，因此闭店既不能作为终点，也不会被穿行。
- 输出的节点序列被压缩合并为「沿通道步行 → 乘扶梯/电梯跨层 → 到达」的
  中文分段指令，含方位、楼层变化、分段距离与总用时。

## REST API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/map` | 全部楼层、节点、边 |
| GET | `/api/places?type=shop` | 可选地点（可按类型过滤） |
| POST | `/api/route` | 规划路径 |

`POST /api/route` 请求体：

```json
{ "start": "metro_a", "goal": "park_a", "preference": "escalator" }
```

`preference` 取值：`none` / `escalator` / `elevator`。
业务错误以 HTTP 400 返回，例如：

```json
{ "error": { "code": "DESTINATION_CLOSED", "message": "「海底捞」当前未营业, 无法作为终点" } }
```

错误码：`NODE_NOT_FOUND` / `INVALID_POI` / `SAME_POINT` /
`DESTINATION_CLOSED` / `NO_ROUTE` / `BAD_JSON`。
