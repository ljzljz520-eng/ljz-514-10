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

  // 底图边
  mapData.edges.forEach((e) => {
    const a = getNode(e.a);
    const b = getNode(e.b);
    if (e.kind === "corridor") {
      if (a.floor !== activeFloor || b.floor !== activeFloor) return;
    } else if (!floorNodes.has(e.a) || !floorNodes.has(e.b)) {
      return; // 垂直交通边仅当两端节点都在本层时不绘制; 这里不会发生(层间边两端不同层)
    }
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
      // 通道边只在对应楼层画; 垂直边在涉及的楼层都画(同坐标点时长度为0无妨)
      if (e.kind === "corridor" && a.floor !== activeFloor) return;
      if (e.kind !== "corridor") {
        if (a.floor !== activeFloor && b.floor !== activeFloor) return;
      }
      const draw = e.kind === "corridor";
      if (draw) {
        svg.appendChild(
          el("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "route-edge" })
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
async function planRoute() {
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
  // 切换到起点所在楼层展示
  activeFloor = getNode(start).floor;
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
  // 时间变化后重新拉取营业状态
  await loadMapKeepSelection();
});
document.querySelectorAll(".quick-times button").forEach((b) => {
  b.addEventListener("click", async () => {
    $("#time").value = b.dataset.t;
    await loadMapKeepSelection();
  });
});
$("#start").addEventListener("change", hideError);
$("#end").addEventListener("change", hideError);

async function loadMapKeepSelection() {
  const s = $("#start").value;
  const e = $("#end").value;
  await loadMap();
  $("#start").value = s;
  // 若原终点变为闭店, 自动回退到第一个可用项
  const endOpt = [...$("#end").options].find((o) => o.value === e && !o.disabled);
  $("#end").value = endOpt ? e : "s4";
  syncEndOptions();
}

// ---------- 启动 ----------
(function init() {
  const d = new Date();
  $("#time").value =
    String(d.getHours()).padStart(2, "0") + ":" +
    String(d.getMinutes()).padStart(2, "0");
  loadMap();
})();
