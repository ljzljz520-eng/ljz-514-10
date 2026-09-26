/* 地下商业街导航 - 前端逻辑(原生 JS, 无依赖) */
const SVG_NS = "http://www.w3.org/2000/svg";
const TYPE_COLORS = {
  entrance: "#60a5fa", shop: "#4ade80", service: "#f472b6",
  parking: "#c084fc", escalator: "#f59e0b", elevator: "#22d3ee",
  corridor: "#54647d",
};
const TYPE_ICON = {
  entrance: "🚇", shop: "🛒", service: "ℹ️", parking: "🅿️",
  escalator: "🪜", elevator: "🛗",
};
const PREF_NAME = { none: "自动选择", escalator: "优先扶梯", elevator: "优先电梯" };

const state = {
  floors: [], nodes: {}, edges: [], places: [],
  start: null, goal: null, selected: null,
  floorView: "-1", route: null,
};

const $ = (id) => document.getElementById(id);
const svg = $("map");

function el(tag, attrs = {}, text) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
}
function nodeFloor(id) { return state.nodes[id]?.floor; }
function isConnectorEdge(e) { return e.kind === "escalator" || e.kind === "elevator"; }

/* ---------------- 数据加载 ---------------- */
async function init() {
  const [mapRes, placeRes] = await Promise.all([
    fetch("/api/map").then(r => r.json()),
    fetch("/api/places").then(r => r.json()),
  ]);
  state.floors = mapRes.floors;
  mapRes.nodes.forEach(n => { state.nodes[n.id] = n; });
  state.edges = mapRes.edges;
  state.places = placeRes.places;
  bindEvents();
  renderPlaceList("");
  renderMap();
}

function bindEvents() {
  document.querySelectorAll(".floor-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".floor-tab").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.floorView = btn.dataset.floor;
      renderMap();
    });
  });
  document.querySelectorAll('input[name="pref"]').forEach(r =>
    r.addEventListener("change", () => { if (state.start && state.goal) requestRoute(); }));
  $("search").addEventListener("input", e => renderPlaceList(e.target.value.trim()));
  $("clearBtn").addEventListener("click", clearRoute);
}

/* ---------------- 地点列表 ---------------- */
function renderPlaceList(keyword) {
  const box = $("placeList");
  box.innerHTML = "";
  const order = { entrance: 0, parking: 1, service: 2, shop: 3 };
  const list = state.places
    .filter(p => !keyword || p.name.includes(keyword) || p.hours.includes(keyword))
    .sort((a, b) => order[a.type] - order[b.type] || a.floor - b.floor);

  for (const p of list) {
    const row = document.createElement("div");
    row.className = "place-item" + (p.open ? "" : " closed") +
      (state.selected === p.id ? " selected" : "");

    const icon = document.createElement("div");
    icon.className = "picon";
    icon.style.background = p.open ? TYPE_COLORS[p.type] + "33" : "#47556933";
    icon.textContent = TYPE_ICON[p.type] || "·";

    const info = document.createElement("div");
    info.className = "pinfo";
    info.innerHTML = `<div class="pname">${p.name}</div>
      <div class="pmeta">${p.floor_name} · ${p.hours || "—"}</div>`;

    row.appendChild(icon);
    row.appendChild(info);

    if (!p.open) {
      const b = document.createElement("span");
      b.className = "badge-closed";
      b.textContent = "未营业";
      b.title = p.hours;
      row.appendChild(b);
      row.addEventListener("click", () =>
        showHint(`「${p.name}」当前未营业，不能作为终点或途经点。`, true));
    } else {
      const btns = document.createElement("div");
      btns.className = "role-btns";
      const bs = document.createElement("button");
      bs.className = "set-start" + (state.start === p.id ? " active" : "");
      bs.textContent = "起";
      bs.onclick = (ev) => { ev.stopPropagation(); setStart(p.id); };
      const bg = document.createElement("button");
      bg.className = "set-goal" + (state.goal === p.id ? " active" : "");
      bg.textContent = "终";
      bg.onclick = (ev) => { ev.stopPropagation(); setGoal(p.id); };
      btns.append(bs, bg);
      row.appendChild(btns);
      row.addEventListener("click", () => {
        state.selected = p.id;
        switchFloorTo(p.floor);
        renderPlaceList($("search").value.trim());
        renderMap();
        showHint(`已选中「${p.name}」，点击右侧「起/终」按钮设定。`);
      });
    }
    box.appendChild(row);
  }
}

/* ---------------- 起终点 ---------------- */
function setStart(id) {
  if (state.goal === id) state.goal = null;
  state.start = id;
  state.selected = id;
  afterEndpointChange(id);
}
function setGoal(id) {
  if (!id || !state.nodes[id].open) return;
  if (state.start === id) state.start = null;
  state.goal = id;
  state.selected = id;
  afterEndpointChange(id);
}
function afterEndpointChange(id) {
  switchFloorTo(state.nodes[id].floor);
  updateEndpointLabels();
  renderPlaceList($("search").value.trim());
  renderMap();
  if (state.start && state.goal) requestRoute();
  else resetRoutePanel();
}
function clearRoute() {
  state.start = state.goal = state.selected = null;
  state.route = null;
  $("search").value = "";
  updateEndpointLabels();
  renderPlaceList("");
  renderMap();
  resetRoutePanel();
  showHint("在列表或地图上点击地点，再点「起 / 终」按钮设定。");
}
function switchFloorTo(floor) {
  const key = String(floor);
  state.floorView = key;
  document.querySelectorAll(".floor-tab").forEach(b =>
    b.classList.toggle("active", b.dataset.floor === key));
}
function updateEndpointLabels() {
  $("startLabel").textContent = state.start ? state.nodes[state.start].name : "未选择";
  $("goalLabel").textContent = state.goal ? state.nodes[state.goal].name : "未选择";
}
function showHint(text, isError = false) {
  const h = $("hint");
  h.textContent = text;
  h.classList.toggle("error", isError);
}

/* ---------------- 地图渲染 ---------------- */
function renderMap() {
  svg.innerHTML = "";
  const view = state.floorView;
  const showAll = view === "all";
  const floor = showAll ? null : Number(view);

  // 楼层底色与标签
  if (showAll) {
    svg.appendChild(el("rect", { class: "floor-band", x: 60, y: 50, width: 870, height: 290, rx: 16 }));
    svg.appendChild(el("text", { class: "floor-tag", x: 78, y: 78 }, "B1 商铺层"));
    svg.appendChild(el("rect", { class: "floor-band", x: 60, y: 510, width: 870, height: 200, rx: 16 }));
    svg.appendChild(el("text", { class: "floor-tag", x: 78, y: 538 }, "B2 停车场层"));
  }

  const edgeLayer = el("g");
  const routeLayer = el("g");
  const nodeLayer = el("g");
  svg.append(edgeLayer, routeLayer, nodeLayer);

  const pathSet = new Set();
  if (state.route) {
    const p = state.route.path;
    for (let i = 0; i < p.length - 1; i++) pathSet.add(p[i] + "|" + p[i + 1]);
  }

  // 边
  for (const e of state.edges) {
    const a = state.nodes[e.a], b = state.nodes[e.b];
    const connector = isConnectorEdge(e);
    if (connector && !showAll) continue;
    if (!connector && !showAll && (a.floor !== floor || b.floor !== floor)) continue;

    if (connector) {
      edgeLayer.appendChild(el("line", {
        class: `vlink ${e.kind}`, x1: a.x, y1: a.y, x2: b.x, y2: b.y,
        stroke: TYPE_COLORS[e.kind], "stroke-width": 3, opacity: .8,
      }));
    } else {
      edgeLayer.appendChild(el("line", {
        class: "walk-edge", x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      }));
    }
    const key1 = e.a + "|" + e.b, key2 = e.b + "|" + e.a;
    if (pathSet.has(key1) || pathSet.has(key2)) {
      const attrs = { class: "route-edge", x1: a.x, y1: a.y, x2: b.x, y2: b.y };
      if (connector) {
        attrs["stroke-width"] = 5;
        attrs["stroke-dasharray"] = "8 5";
      }
      routeLayer.appendChild(el("line", attrs));
    }
  }

  // 节点
  const onPath = new Set(state.route ? state.route.path : []);
  for (const n of Object.values(state.nodes)) {
    if (!showAll && n.floor !== floor) continue;
    const closed = n.type === "shop" && !n.open;
    const r = n.type === "corridor" ? 5 : 10;
    const g = el("g");
    const cls = ["node-g"];
    if (closed) cls.push("closed-shop");
    g.setAttribute("class", cls.join(" "));

    const circleAttrs = {
      class: "node-circle", cx: n.x, cy: n.y, r,
      fill: closed ? "#64748b" : TYPE_COLORS[n.type],
    };
    if (state.start === n.id) circleAttrs.class += " start-node";
    if (state.goal === n.id) circleAttrs.class += " goal-node";
    if (onPath.has(n.id)) circleAttrs.class += " route-node";
    if (state.selected === n.id) circleAttrs.stroke = "#ffffff";
    const c = el("circle", circleAttrs);
    g.appendChild(c);

    // 标签: POI / 扶梯 / 电梯显示, 通道不显示
    if (n.type !== "corridor") {
      const ly = n.y + (n.y < 400 ? -16 : 20);
      const t = el("text", {
        class: "node-label" + (n.type === "shop" ? " shop-name" : ""),
        x: n.x, y: ly,
      }, n.name + (closed ? "(停业)" : ""));
      g.appendChild(t);
    }

    c.addEventListener("click", () => onMapNodeClick(n));
    nodeLayer.appendChild(g);
  }
}

function onMapNodeClick(n) {
  state.selected = n.id;
  if (n.type === "corridor" || n.type === "escalator" || n.type === "elevator") {
    showHint(`「${n.name}」是通道设施，不能作为终点；请选择地铁口/店铺/服务台/停车场。`, true);
    renderMap();
    return;
  }
  if (n.type === "shop" && !n.open) {
    showHint(`「${n.name}」当前未营业，不能作为终点或途经点。`, true);
    renderMap();
    return;
  }
  // 连续点击: 依次分配 起点 -> 终点; 都已存在时替换终点, 便于连续浏览
  if (!state.start) { setStart(n.id); }
  else { setGoal(n.id); }
  showHint(`已将「${n.name}」设为${state.goal === n.id ? "终点" : "起点"}。`);
}

/* ---------------- 路径请求与渲染 ---------------- */
async function requestRoute() {
  const preference = document.querySelector('input[name="pref"]:checked').value;
  const summary = $("routeSummary");
  summary.className = "summary";
  summary.textContent = "路径规划中…";
  try {
    const res = await fetch("/api/route", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start: state.start, goal: state.goal, preference }),
    });
    const data = await res.json();
    if (!res.ok) {
      renderRouteError(data.error);
      return;
    }
    state.route = data.route;
    renderRoute(data.route);
    // 自动切到起点所在层, 方便查看
    switchFloorTo(data.route.start.floor);
    renderMap();
  } catch (err) {
    renderRouteError({ code: "NETWORK", message: "网络错误: " + err });
  }
}

function fmtTime(sec) {
  const m = Math.round(sec / 60);
  return m <= 0 ? "约 1 分钟" : `约 ${m} 分钟`;
}

function renderRoute(r) {
  const connText = r.connectors.map(k =>
    `<span class="chip ${k === "escalator" ? "esc" : "ele"}">` +
    (k === "escalator" ? "🪜 扶梯跨层" : "🛗 电梯跨层") + "</span>").join("");
  const floors = r.floors.map(f => f === -1 ? "B1" : "B2").join(" → ");
  $("routeSummary").className = "summary";
  $("routeSummary").innerHTML = `
    <div><b style="color:var(--start)">${r.start.name}</b>
      <span style="color:var(--muted)"> 到 </span>
      <b style="color:var(--goal)">${r.goal.name}</b></div>
    <div class="big">
      <div><b>${r.walk_meters}</b><span>步行距离(米)</span></div>
      <div><b>${fmtTime(r.estimated_seconds)}</b><span>预计用时 · ${PREF_NAME[r.preference]}</span></div>
    </div>
    <div class="chips">
      <span class="chip">楼层 ${floors}</span>${connText}
    </div>`;

  const ol = $("directions");
  ol.innerHTML = "";
  r.segments.forEach(s => {
    const li = document.createElement("li");
    li.className = "kind-" + s.kind;
    li.textContent = s.instruction;
    if (s.kind === "walk") {
      const d = document.createElement("span");
      d.className = "dist";
      d.textContent = `步行约 ${s.distance} 米`;
      li.appendChild(d);
    }
    ol.appendChild(li);
  });
  showHint("路径已在地图上高亮（金色），可切换楼层查看。");
}

function renderRouteError(err) {
  state.route = null;
  renderMap();
  $("routeSummary").className = "summary empty";
  $("routeSummary").innerHTML = `⚠️ ${err.message}`;
  $("directions").innerHTML = "";
  showHint(err.message, true);
}

function resetRoutePanel() {
  state.route = null;
  $("routeSummary").className = "summary empty";
  $("routeSummary").textContent = "请选择起点和终点";
  $("directions").innerHTML = "";
}

init();
