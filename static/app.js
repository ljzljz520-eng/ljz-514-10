/* 地下商业街导航 - 前端演示页面 */
const SVG_NS = "http://www.w3.org/2000/svg";
const COLORS = {
  subway: "#e8862d",
  shop: "#3f9d6a",
  service: "#9558b8",
  parking: "#3768c4",
  escalator: "#00a3a3",
  elevator: "#d3b020",
  junction: "#aab6c4",
};

let mapData = null;
let activeFloor = "B1";
let route = null;

const $ = (sel) => document.querySelector(sel);
const svg = $("#map");

// ---------- 工具 ----------
function el(name, attrs = {}, text) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text != null) node.textContent = text;
  return node;
}
function getNode(id) {
  return mapData.nodes.find((n) => n.id === id);
}
function nowVal() {
  return $("#time").value || "12:00";
}

// ---------- 数据加载 ----------
async function loadMap() {
  const resp = await fetch(`/api/map?now=${encodeURIComponent(nowVal())}`);
  mapData = await resp.json();
  fillSelects();
  renderFloorTabs();
  renderMap();
}

// ---------- 下拉框 ----------
function fillSelects() {
  const groups = {};
  mapData.floors.forEach((f) => (groups[f.id] = []));
  mapData.nodes
    .filter((n) => n.selectable)
    .forEach((n) => groups[n.floor].push(n));

  for (const select of [$("#start"), $("#end")]) {
    const old = select.value;
    select.innerHTML = "";
    for (const f of mapData.floors) {
      const og = document.createElement("optgroup");
      og.label = f.name;
      groups[f.id]
        .slice()
        .sort((a, b) => a.type.localeCompare(b.type))
        .forEach((n) => {
          const o = document.createElement("option");
          o.value = n.id;
          let prefix = n.type === "subway" ? "🚇 "
            : n.type === "parking" ? "🅿️ "
            : n.type === "service" ? "ℹ️ " : "🛍️ ";
          o.textContent = prefix + n.name + (n.type === "shop" && !n.open ? "（未营业）" : "");
          if (n.type === "shop" && !n.open) o.textContent = "🚫 " + n.name + "（未营业）";
          og.appendChild(o);
        });
      select.appendChild(og);
    }
    if ([...select.options].some((o) => o.value === old)) select.value = old;
  }
  if (!$("#start").value) $("#start").value = "sub_a";
  if (!$("#end").value) $("#end").value = "s4";
  syncEndOptions();
}

// 未营业店铺不能作为终点: 在终点下拉中禁用
function syncEndOptions() {
  $("#end").querySelectorAll("option").forEach((o) => {
    const n = getNode(o.value);
    if (n && n.type === "shop" && !n.open) o.disabled = true;
  });
}

// ---------- 楼层切换 ----------
function renderFloorTabs() {
  const tabs = $("#floorTabs");
  tabs.innerHTML = "";
  mapData.floors.forEach((f) => {
    const b = document.createElement("button");
    b.textContent = f.name;
    b.className = f.id === activeFloor ? "active" : "";
    b.onclick = () => {
      activeFloor = f.id;
      renderFloorTabs();
      renderMap();
    };
    tabs.appendChild(b);
  });
}

// ---------- 地图渲染 ----------
// 计算每条扶梯/电梯竖向井道连通的楼层, 返回 nodeId -> [{floor, kind, onRoute}]
function buildVerticalLinks(routeEdgeSet) {
  const links = {};               // nodeId -> [{floor, kind, onRoute}]
  const seenEdge = new Set();

  mapData.edges.forEach((e) => {
    if (e.kind === "corridor") return;
    const key = `${e.a}|${e.b}|${e.kind}`;
    if (seenEdge.has(key)) return;
    seenEdge.add(key);
    const onRoute = routeEdgeSet.has(key);
    [e.a, e.b].forEach((id) => {
      const other = id === e.a ? e.b : e.a;
      (links[id] = links[id] || []).push({
        floor: getNode(other).floor,
        kind: e.kind,
        onRoute,
      });
    });
  });
  return links;
}

// 在扶梯/电梯节点下方绘制可到达楼层胶囊(跨层连接可视化)
function drawVerticalBadge(n, entries) {
  // 去重后按楼层排序展示(本图中各井道只跨相邻楼层)
  const floors = [];
  entries.forEach((t) => {
    if (!floors.some((f) => f.floor === t.floor)) floors.push(t);
  });
  floors.sort((p, q) => p.floor.localeCompare(q.floor));
  const onRoute = floors.some((f) => f.onRoute);
  const glyph = floors[0].kind === "escalator" ? "🪜" : "🛗";
  const text = `${glyph} ${floors.map((f) => f.floor).join("/")}`;
  const tx = n.x;
  const ty = n.y + 20;
  const w = text.length * 5.6 + 8;

  svg.appendChild(
    el("rect", {
      x: tx - w / 2, y: ty - 7.5, width: w, height: 11, rx: 5.5,
      class: `vlink${onRoute ? " on-route" : ""} vlink-${floors[0].kind}`,
    })
  );
  svg.appendChild(
    el("text", {
      x: tx, y: ty + 2.5,
      class: `vlink-text${onRoute ? " on-route" : ""}`
        + (floors[0].kind === "elevator" ? " vlink-elevator-text" : ""),
    }, text)
  );
}

function renderMap() {
  svg.innerHTML = "";
  const floorNodes = new Set(
    mapData.nodes.filter((n) => n.floor === activeFloor).map((n) => n.id)
  );
  const routeEdgeSet = new Set(
    (route ? route.edges : []).map((e) => `${e.a}|${e.b}|${e.kind}`)
  );
  const routeNodeSet = new Set(
    route ? [route.start, ...route.node_chain] : []
  );
  const verticalLinks = buildVerticalLinks(routeEdgeSet);

  // 底图边: 仅绘制本层通道(层间垂直边以节点胶囊形式展示)
  mapData.edges.forEach((e) => {
    const a = getNode(e.a);
    const b = getNode(e.b);
    if (e.kind !== "corridor") return;
    if (a.floor !== activeFloor || b.floor !== activeFloor) return;
    svg.appendChild(
      el("line", {
        x1: a.x, y1: a.y, x2: b.x, y2: b.y,
        class: `edge ${e.kind}`,
      })
    );
  });

  // 路线高亮
  if (route) {
    route.edges.forEach((e) => {
      const a = getNode(e.a);
      const b = getNode(e.b);
      if (e.kind === "corridor") {
        // 通道边只在对应楼层画
        if (a.floor !== activeFloor) return;
        svg.appendChild(
          el("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "route-edge" })
        );
      } else {
        // 垂直段无法跨楼层连线: 在本层端点用红色短桩提示乘梯方向
        const local = a.floor === activeFloor ? a
          : b.floor === activeFloor ? b : null;
        if (!local) return;
        const other = local === a ? b : a;
        const dx = local.x === other.x ? 0 : Math.sign(other.x - local.x);
        const dy = 14;
        svg.appendChild(
          el("line", {
            x1: local.x, y1: local.y,
            x2: local.x + dx * 8, y2: local.y + dy,
            class: "route-edge",
          })
        );
      }
    });
    // 节点链上的通行顺序小圆点
    route.node_chain.forEach((id, idx) => {
      const n = getNode(id);
      if (n.floor !== activeFloor) return;
      svg.appendChild(
        el("circle", { cx: n.x, cy: n.y, r: 2.4, fill: "#e23e57" })
      );
    });
  }

  // 节点
  mapData.nodes
    .filter((n) => n.floor === activeFloor)
    .forEach((n) => {
      const inRoute = routeNodeSet.has(n.id);
      const isJunction = n.type === "junction";

      if (inRoute && n.id === route.start) {
        svg.appendChild(el("circle", { cx: n.x, cy: n.y, r: 10, class: "start-ring" }));
      }
      if (inRoute && n.id === route.end) {
        svg.appendChild(el("circle", { cx: n.x, cy: n.y, r: 10, class: "end-ring" }));
      }

      const r = isJunction ? 3 : 6.5;
      let fill = COLORS[n.type] || "#888";
      if (n.type === "shop" && n.open === false) fill = COLORS.junction;
      svg.appendChild(
        el("circle", {
          cx: n.x, cy: n.y, r,
          fill,
          class: "node-mark",
          "data-id": n.id,
        })
      );

      if (!isJunction) {
        // 点击热区
        const hit = el("circle", { cx: n.x, cy: n.y, r: 11, class: "node-hit" });
        hit.addEventListener("click", () => onNodeClick(n));
        svg.appendChild(hit);

        const labelClass =
          n.type === "shop" && n.open === false ? "node-label closed" : "node-label";
        svg.appendChild(
          el("text", { x: n.x, y: n.y - 10, class: labelClass }, n.name)
        );

        // 扶梯/电梯节点: 显示跨楼层连接
        if (verticalLinks[n.id]) {
          drawVerticalBadge(n, verticalLinks[n.id]);
        }
      }
    });
}

// 点击图标: 可选点 -> 设为终点(闭店则提示)
function onNodeClick(n) {
  if (!n.selectable) return;
  if (n.type === "shop" && n.open === false) {
    showError(`「${n.name}」未营业，不能作为终点。可将其设为起点。`);
    return;
  }
  $("#end").value = n.id;
  planRoute();
}

// ---------- 查询路线 ----------
async function planRoute(keepFloor = false) {
  hideError();
  const start = $("#start").value;
  const end = $("#end").value;
  if (!start || !end) return;

  const resp = await fetch("/api/route", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ start, end, now: nowVal() }),
  });
  const data = await resp.json();
  if (!resp.ok) {
    route = null;
    $("#resultCard").hidden = true;
    showError(data.error);
    renderMap();
    return;
  }
  route = data;
  renderResult(data);
  if (!keepFloor) {
    // 切换到起点所在楼层展示
    activeFloor = getNode(start).floor;
  }
  renderFloorTabs();
  renderMap();
}

function renderResult(r) {
  $("#resultCard").hidden = false;
  const mins = Math.floor(r.total_seconds / 60);
  const secs = r.total_seconds % 60;
  const floorText = r.floors.join(" → ");
  $("#stats").innerHTML = `
    <div class="stat"><b>${r.walk_meters} 米</b><span>通道步行距离</span></div>
    <div class="stat"><b>${mins} 分 ${secs} 秒</b><span>预计总耗时</span></div>
    <div class="stat"><b>${floorText}</b><span>途经楼层</span></div>
    <div class="stat"><b>${r.transfers} 次</b><span>楼层转换</span></div>
    <div class="stat"><b>${r.escalator_count} 段</b><span>乘坐扶梯</span></div>
    <div class="stat"><b>${r.elevator_count} 段</b><span>乘坐电梯</span></div>`;

  const ol = $("#steps");
  ol.innerHTML = "";
  r.steps.forEach((s) => {
    const li = document.createElement("li");
    li.className = s.type === "escalator" ? "esc"
      : s.type === "elevator" ? "elv" : "";
    li.textContent = s.text;
    ol.appendChild(li);
  });
}

function showError(msg) {
  const box = $("#error");
  box.textContent = "⚠️ " + msg;
  box.hidden = false;
}
function hideError() {
  $("#error").hidden = true;
}

// ---------- 事件 ----------
$("#plan").addEventListener("click", planRoute);
$("#time").addEventListener("change", async () => {
  // 时间变化后重新拉取营业状态, 并按新时间重算路线, 避免路线与终点状态矛盾
  await refreshAfterTimeChange();
});
document.querySelectorAll(".quick-times button").forEach((b) => {
  b.addEventListener("click", async () => {
    $("#time").value = b.dataset.t;
    await refreshAfterTimeChange();
  });
});
$("#start").addEventListener("change", hideError);
$("#end").addEventListener("change", hideError);

async function refreshAfterTimeChange() {
  const s = $("#start").value;
  const e = $("#end").value;
  const hadRoute = route !== null;
  // 先清掉按旧时间算出的路线, 防止重算间隙展示与营业状态矛盾的路线
  route = null;
  await loadMap();
  $("#start").value = s;
  // 若原终点变为闭店(选项被禁用), 回退到第一个可用终点
  const endOpt = [...$("#end").options].find((o) => o.value === e && !o.disabled);
  const newEnd = endOpt ? e
    : $("#end").querySelector("option:not(:disabled)")?.value || "s4";
  $("#end").value = newEnd;
  syncEndOptions();
  if (hadRoute || e !== newEnd) {
    // 已有路线时按新时间重算; 无路线但终点被迫回退时也规划一次, 保证选择与展示一致
    await planRoute(true);
  } else {
    renderMap();
  }
}

// ---------- 启动 ----------
(function init() {
  const d = new Date();
  $("#time").value =
    String(d.getHours()).padStart(2, "0") + ":" +
    String(d.getMinutes()).padStart(2, "0");
  loadMap();
})();
