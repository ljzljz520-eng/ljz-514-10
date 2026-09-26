# 地下商业街导航系统

顾客选择**地铁口、店铺、服务台、停车场**，系统根据**楼层、扶梯、电梯、通道距离和营业状态**规划最优路径；**未营业的店铺不能作为终点**。

纯 Python 标准库实现（零第三方依赖），包含后端算法、单元/集成测试与前端 SVG 演示页面。

## 快速开始

```bash
# 启动服务（默认 8000 端口）
python3 backend/server.py

# 浏览器打开
http://localhost:8000
```

```bash
# 运行全部测试（24 个用例）
python3 -m unittest discover -s tests -v
```

## 项目结构

```
backend/
  mall_data.py    地图数据：B1/B2 两层，节点（地铁口/店铺/服务台/停车场/扶梯/电梯/通道口）、
                  通道边、扶梯、电梯、店铺营业时间
  pathfinder.py   图模型 + Dijkstra 最短路 + 营业状态校验 + 中文分段指引生成
  server.py       HTTP API 与静态页面服务（http.server）
tests/
  test_pathfinder.py  算法测试 + API 集成测试（unittest）
frontend/
  index.html      演示页面：双层 SVG 地图、起终点选择、模式切换、路径动画、分段指引
```

## 路径规划模型

| 要素 | 建模 |
|------|------|
| 通道 | 步行边，权重 = 距离(米) / 1.2(m/s) |
| 扶梯 | 跨层边，固定 45 秒 |
| 电梯 | 跨层边，固定 75 秒（含候梯） |
| 楼层 | 设施按层拆节点（如 `E1_B1`/`E1_B2`），跨层边连接 |
| 营业状态 | 店铺按 `hours`（支持跨零点）与 `force_closed` 判定；未营业店铺**不能作为终点**（可作为起点，如顾客从刚打烊的店离开） |

规划模式：

- `fastest` 最快路线：扶梯、电梯均可用，系统自动权衡（如地铁B口→健身房会选更近的电梯）
- `accessible` 无障碍：仅电梯，适合轮椅/婴儿车/大件行李

## API

| 接口 | 说明 |
|------|------|
| `GET /api/map[?now=HH:MM]` | 地图数据（节点、通道、扶梯、电梯、店铺营业状态） |
| `GET /api/pois[?now=HH:MM]` | 可选起终点，按类型分组，店铺含 `open`/`hours` |
| `GET /api/route?start=..&end=..&mode=fastest\|accessible[&now=HH:MM]` | 路径规划 |

`GET /api/route` 返回：

```json
{
  "total_time": 295.0,        // 总耗时（秒）
  "walk_distance": 300.0,     // 步行距离（米）
  "path": [ {"id":"M1","name":"地铁A口","floor":"B1","x":100,"y":100}, ... ],
  "edges": [ {"from":"M1","to":"E1_B1","kind":"corridor"}, ... ],
  "steps": [ {"kind":"walk","instruction":"从「地铁A口」出发，沿B1层通道步行 150 米…"}, ... ]
}
```

错误（HTTP 400）：`{"error": "「服装店」当前未营业，不能作为终点"}`

示例：

```bash
curl "http://localhost:8000/api/route?start=M1&end=P1&mode=fastest&now=12:00"
curl "http://localhost:8000/api/route?start=S1&end=F201&mode=accessible"
```

## 测试覆盖

- **营业状态**：营业时间内/外、暂停营业、跨零点、非店铺全天可用
- **路径规划**：同层最短、跨层选扶梯、距离权衡选电梯、无障碍仅电梯、
  起终点相同、路径连续性、分段指引一致性
- **终点约束**：未营业（暂停营业/已打烊）店铺作为终点抛 `ClosedShopError`；作为起点允许
- **异常**：节点不存在、非法模式
- **API 集成**：真实起服务发请求，验证 200/400 与各接口字段

## 前端演示

- 双层 SVG 地图（B1 商业层 / B2 商业·停车层），未营业店铺灰色标注
- 终点下拉框中未营业店铺自动禁用；可设置“演示时间”体验不同营业状态
- 路线红色动画高亮，右侧输出中文分段指引与总用时/步行距离
- 快捷演示按钮：含无障碍模式与“未营业店铺报错”场景
