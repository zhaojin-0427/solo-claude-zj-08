/* 管风琴机械传动放样台 —— 前端（原生 JS + SVG） */
"use strict";

const SVGNS = "http://www.w3.org/2000/svg";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const el = (name, attrs = {}, parent) => {
  const n = document.createElementNS(SVGNS, name);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") n.textContent = v;
    else n.setAttribute(k, v);
  }
  if (parent && parent.appendChild) parent.appendChild(n);
  return n;
};

const state = {
  projectId: null,
  model: null,
  analysis: null,
  selected: 0,
  view: "plan",
  play: { on: false, t: 0, frame: null, timer: null },
  drag: null,
};

/* ------------------------------------------------------------------ 接口 */
async function api(path, method = "GET", body) {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opt.body = JSON.stringify(body);
  const r = await fetch(path, opt);
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.error || ("HTTP " + r.status));
  }
  return r.json();
}
const edit = (key, field, value) =>
  api("/api/edit", "POST", { key, field, value });

/* ------------------------------------------------------------------ 坐标 */
function makeTransform() {
  const cab = state.model.globals.cabinet;
  const W = 980, H = 540, pad = 64;
  const sx = (W - pad * 2) / (cab.xMax - cab.xMin);
  const sy = (H - pad * 2 - 10) / (cab.yMax - cab.yMin);
  const s = Math.min(sx, sy);
  const ox = pad - cab.xMin * s + ((W - pad * 2) - (cab.xMax - cab.xMin) * s) / 2;
  const oy = pad - cab.yMin * s + 14;
  return {
    s,
    X: (x) => ox + x * s,
    Y: (y) => oy + y * s,
    invX: (px) => (px - ox) / s,
    invY: (py) => (py - oy) / s,
  };
}

/* ------------------------------------------------------------------ 主渲染 */
function render() {
  if (!state.analysis) return;
  renderKeyList();
  renderPanels();
  renderStages();
  renderSummary();
  renderViolations();
  renderSnapshots();
  if (state.view === "plan") renderPlan();
  else renderSide();
}

/* ------------------------------------------------------------------ 键列表 */
function renderKeyList() {
  const box = $("#keyList");
  box.innerHTML = "";
  state.analysis.keys.forEach((k) => {
    const m = k.metrics;
    const bad = m.valveOpen < state.model.globals.physics.valveOpenTarget ||
      m.deadAt !== null || m.fFrontMax > state.model.globals.physics.effKeyFrontMax;
    const warn = state.analysis.violations.some(
      (v) => v.severity === "warn" && v.keys.includes(k.id));
    const d = el("div", {
      class: `keychip ${state.selected === k.id ? "sel" : ""} ` +
        `${k.locked ? "locked" : bad ? "bad" : warn ? "warn" : ""}`,
    }, box);
    d.innerHTML = `${k.name}<small>${m.valveOpen.toFixed(1)}mm ` +
      `${m.fFrontMax.toFixed(1)}N</small>` +
      `<span class="vk">${bad ? "✕" : warn ? "!" : "✓"}</span>`;
    d.onclick = () => { state.selected = k.id; render(); };
  });
}

/* ------------------------------------------------------------------ 参数面板 */
const PARAM_DEFS = [
  ["keyHole", "键杠立木孔距轴", "keyHole"],
  ["rollerInHorn", "滚轴输入角长", "rollerInHorn"],
  ["rollerOutHorn", "滚轴输出角长", "rollerOutHorn"],
  ["rollerBetaIn", "输入角安装仰角°", "rollerBetaIn"],
  ["squareInArm", "转角器输入臂", "squareInArm"],
  ["squareOutArm", "转角器输出臂", "squareOutArm"],
  ["squareAngleDeg", "两臂初始夹角°", "squareAngleDeg"],
];

function catalogOptions(field, value) {
  return state.model.catalog[field].map((v) =>
    `<option value="${v}" ${Math.abs(v - value) < 1e-9 ? "selected" : ""}>${v}</option>`
  ).join("");
}

function renderPanels() {
  const i = state.selected;
  const key = state.model.keys[i];
  const g = key.geometry;
  $("#selKeyName").textContent = key.name;
  const lock = $("#chkKeyLock");
  lock.checked = !!key.locked;
  lock.onchange = () => api(`/api/key/${i}/lock`, "POST",
    { locked: lock.checked }).then((r) => {
    state.model.keys[i].locked = r.locked; render();
  });

  const pf = $("#paramForm");
  pf.innerHTML = "";
  PARAM_DEFS.forEach(([field, label, catField]) => {
    const row = el("div", { class: "row" }, pf);
    el("label", { text: label }, row);
    const sel = document.createElement("select");
    sel.innerHTML = catalogOptions(catField, g[field]);
    if (key.locked) sel.disabled = true;
    pf.appendChild(row).appendChild(sel);
    sel.onchange = () => edit(i, field, parseFloat(sel.value))
      .then(applyAnalysis).catch(showErr);
  });
  // 阀列（改列）
  const sp = state.model.globals.keySpacing;
  const pitch = Math.round((g.squareX - 12) / sp) - i;
  const r1 = el("div", { class: "row" }, pf);
  el("label", { text: "服务阀列偏移" }, r1);
  const ps = el("select", {}, r1);
  ps.innerHTML = state.model.catalog.squareXPitch.map((p) =>
    `<option value="${p}" ${p === pitch ? "selected" : ""}>${p === 0 ? "本位" : (p > 0 ? "+" + p : p) + " 列"}</option>`
  ).join("");
  ps.disabled = !!key.locked;
  ps.onchange = () => edit(i, "squareXPitch", parseInt(ps.value))
    .then(applyAnalysis).catch(showErr);
  // 空程（阀间隙）
  const r2 = el("div", { class: "row" }, pf);
  el("label", { text: "阀拉索空程 mm" }, r2);
  const gap = el("input", { type: "number", step: "0.1", min: "0", max: "4",
    value: g.valveGap ?? 1 }, r2);
  if (key.locked) gap.disabled = true;
  gap.onchange = () => edit(i, "valveGap", parseFloat(gap.value))
    .then(applyAnalysis).catch(showErr);

  // 连接关系
  const lf = $("#linkForm");
  lf.innerHTML = "";
  [["sticker_to_hornIn", "立木—输入角", "hornIn"],
   ["hornOut_to_squareIn", "输出角—转角器", "squareIn"],
   ["squareOut_to_pallet", "输出臂—阀板", "pallet"]].forEach(([j, label, target]) => {
    const lab = el("label", {}, lf);
    const cb = el("input", { type: "checkbox" }, lab);
    cb.checked = g.links[j] === target;
    cb.disabled = !!key.locked;
    lab.appendChild(document.createTextNode(" " + label));
    cb.onchange = () => edit(i, "links", { joint: j, target: cb.checked ? target : "" })
      .then(applyAnalysis).catch(showErr);
  });

  // 固定件
  const ff = $("#fixedForm");
  ff.innerHTML = "";
  [["rollerBoard", "滚轴板（锁定后搜索不动）"],
   ["windchest", "风箱/阀板（阀列固定）"],
   ["keyFrame", "键盘框架"]].forEach(([k, label]) => {
    const lab = el("label", {}, ff);
    const cb = el("input", { type: "checkbox" }, lab);
    cb.checked = !!state.model.fixed[k];
    lab.appendChild(document.createTextNode(" " + label));
    cb.onchange = () => api("/api/fixed", "POST", { fixed: { [k]: cb.checked } })
      .then((r) => { state.model.fixed = r; render(); }).catch(showErr);
  });

  // 物理参数
  const phf = $("#physForm");
  phf.innerHTML = "";
  const ph = state.model.globals.physics;
  [["windPressurePa", "风压 Pa", 10],
   ["valveSpringN", "阀回位簧 N", 0.1],
   ["keyReturnSpringN", "键回位簧 N", 0.1],
   ["trackerStiffness", "连杆刚度 N/mm", 0.1],
   ["jointEff", "铰点效率", 0.01],
   ["effKeyFrontMax", "触键力上限 N", 0.5],
   ["valveOpenTarget", "目标阀开 mm", 0.1]].forEach(([k, label, step]) => {
    const row = el("div", { class: "row" }, phf);
    el("label", { text: label }, row);
    const inp = el("input", { type: "number", step, value: ph[k] }, row);
    inp.onchange = () => {
      ph[k] = parseFloat(inp.value);
      api("/api/model", "PUT", { globals: state.model.globals, selected: i })
        .then(applyAnalysis).catch(showErr);
    };
  });

  $("#projectName").value = state.model.name;
}

/* ------------------------------------------------------------------ 俯视 SVG */
function renderPlan() {
  const svg = $("#stage");
  svg.innerHTML = "";
  svg.setAttribute("viewBox", "0 0 980 560");
  const T = makeTransform();
  const cab = state.model.globals.cabinet;
  const viol = state.analysis.violations;
  const z = state.model.globals.z;

  // 柜体
  el("rect", {
    x: T.X(cab.xMin), y: T.Y(cab.yMin),
    width: (cab.xMax - cab.xMin) * T.s, height: (cab.yMax - cab.yMin) * T.s,
    rx: 6, class: "cabinet",
  }, svg);
  el("text", { x: T.X(cab.xMin) + 6, y: T.Y(cab.yMin) + 14, class: "lbl",
    text: "柜体边界" }, svg);

  // 键盘床板 / 滚轴板 / 风箱
  const ry = state.model.keys[0].geometry.rollerY;
  band(T, cab.xMin, cab.xMax, cab.yMin, ry - 34, ry - 10, "keybed", "键盘框架", svg);
  if (!state.model.fixed.rollerBoard)
    band(T, cab.xMin, cab.xMax, ry - 10, ry + 12, "rollerboard", "滚轴板（可前后移）", svg);
  const palY = state.model.keys[state.selected].geometry.palletY;
  band(T, cab.xMin, cab.xMax, palY - 18, cab.yMax - 6, "windchest",
       "风箱（阀板在其上）", svg);

  // 交叉擦碰高亮
  viol.filter((v) => v.code === "CROSS").forEach((v) => {
    const [x, y] = v.at;
    el("circle", { cx: T.X(x), cy: T.Y(y), r: 11, class: "crossmark" }, svg);
    el("text", { x: T.X(x) + 12, y: T.Y(y) - 8, class: "lbl bad",
      text: "交叉擦碰" }, svg);
  });

  // 每键构件
  state.analysis.keys.forEach((k) => {
    const i = k.id;
    const g = state.model.keys[k.id].geometry;
    const p = k.points;
    const locked = state.model.keys[k.id].locked;
    const sel = state.selected === k.id;
    const badLink = (...names) => names.some((nm) =>
      viol.some((v) => v.keys.includes(k.id) &&
        (v.part === nm || (v.part || "").includes(nm))));

    const P = (n) => [T.X(p[n][0]), T.Y(p[n][1])];
    const line = (a, b, cls, width) => {
      const [x1, y1] = P(a), [x2, y2] = P(b);
      const ln = el("line", { x1, y1, x2, y2, class: cls,
        "stroke-width": width || null }, svg);
      return ln;
    };

    // 键杠
    const [fx, fy] = P("keyFront"), [px, py] = P("keyPivot");
    const [rx2, ry2] = P("keyRear");
    const lever = el("line", { x1: fx, y1: fy, x2: rx2, y2: ry2,
      class: "keylever" + (sel ? "" : "") }, svg);
    lever.setAttribute("opacity", sel ? 1 : 0.55);
    // 立木
    const stCls = "part sticker " + (badLink("立木") ? "v-warn" : "");
    if (g.links.sticker_to_hornIn === "hornIn")
      line("stickerFoot", "hornInTip", stCls, 3);
    // 滚轴轴体（xIn→xOut 沿 x，在 rollerY）
    const [axi, ay] = P("rollerAxisIn"), [axo] = P("rollerAxisOut");
    el("line", { x1: axi, y1: ay, x2: axo, y2: ay, class: "roller-axle",
      opacity: sel ? 1 : 0.5 }, svg);
    // 角
    if (g.links.sticker_to_hornIn === "hornIn")
      line("rollerAxisIn", "hornInTip", "part horn", null);
    if (g.links.hornOut_to_squareIn === "squareIn")
      line("rollerAxisOut", "hornOutTip", "part horn", null);
    // tracker A
    if (g.links.hornOut_to_squareIn === "squareIn")
      line("hornOutTip", "squareInTip",
           "part tracker " + (badLink("上行连杆") ? "v-warn" : ""), 3);
    // 阀拉索
    if (g.links.squareOut_to_pallet === "pallet")
      line("squareOutTip", "pallet",
           "part tracker-b " + (badLink("阀拉索") ? "v-warn" : ""), null);

    // 转角器圆盘 + 臂投影
    const [sx, sy] = P("square");
    el("circle", { cx: sx, cy: sy, r: 10, class: "square-disc",
      opacity: sel ? 1 : 0.55 }, svg);
    const [siX, siY] = P("squareInTip"), [soX, soY] = P("squareOutTip");
    el("line", { x1: sx, y1: sy, x2: siX, y2: siY, class: "square-arm",
      opacity: sel ? 1 : 0.5 }, svg);
    el("line", { x1: sx, y1: sy, x2: soX, y2: soY, class: "square-arm",
      opacity: sel ? 1 : 0.5 }, svg);

    // 阀板矩形
    const [plX, plY] = P("pallet");
    const w = state.model.globals.keyWidth * T.s * 0.8;
    const d = 14;
    el("rect", { x: plX - w / 2, y: plY - d / 2, width: w, height: d, rx: 2,
      class: "pallet", opacity: sel ? 1 : 0.6 }, svg);

    // 标签
    if (sel) {
      el("text", { x: fx - 4, y: fy + 3, "text-anchor": "end",
        class: "lbl", text: state.model.keys[k.id].name + " 键前端" }, svg);
      el("text", { x: sx + 13, y: sy - 8, class: "lbl", text: "转角器" }, svg);
      el("text", { x: plX + 12, y: plY + 3, class: "lbl", text: "阀板" }, svg);
    }

    // ---- 可拖支点（仅选中键）
    if (sel && !locked) {
      addHandle(svg, T, p.keyPivot, "keyPivot", i, "拖动：改变键杠支点（孔距联动）");
      addHandle(svg, T, p.stickerFoot, "sticker", i, "拖动：立木下端侧向位置");
      addHandle(svg, T, p.rollerAxisIn, "roller", i,
        state.model.fixed.rollerBoard ? "滚轴板已锁定" : "拖动：滚轴板前后位置（整板联动）");
      addHandle(svg, T, p.square, "square", i, "拖动：转角器位置");
      addHandle(svg, T, p.pallet, "pallet", i, "风箱固定件，不可拖动", true);
      // 臂上可选孔（键杠 + 输入/输出角）
      addHoleDots(svg, T, g, p, i);
      // 连接节点（点击断/连）
      addJointToggle(svg, T, p.hornInTip, i, "sticker_to_hornIn",
        g.links.sticker_to_hornIn === "hornIn");
      addJointToggle(svg, T, p.squareInTip, i, "hornOut_to_squareIn",
        g.links.hornOut_to_squareIn === "squareIn");
      addJointToggle(svg, T, p.squareOutTip, i, "squareOut_to_pallet",
        g.links.squareOut_to_pallet === "pallet");
    } else if (sel) {
      // 锁定状态仅显示支点灰色
      [["keyPivot", "keyPivot"], ["rollerAxisIn", "roller"],
       ["square", "square"], ["pallet", "pallet"]].forEach(([n]) => {
        const [hx, hy] = P(n);
        el("circle", { cx: hx, cy: hy, r: 5, class: "handle locked" }, svg);
      });
    }
  });

  // 播放动画覆盖
  if (state.play.t > 0 && state.play.frame) drawPlayMotion(svg, T);
}

function band(T, x0, x1, y0, y1, cls, label, svg) {
  el("rect", {
    x: T.X(x0) + 4, y: T.Y(y1), width: (x1 - x0 - 8) * T.s,
    height: (y1 - y0) * T.s, rx: 3, class: cls,
  }, svg);
  el("text", { x: T.X(x0) + 10, y: T.Y(y1) + 13, class: "lbl", text: label }, svg);
}

function addHandle(svg, T, pt, kind, keyIdx, tip, fixed) {
  const h = el("circle", {
    cx: T.X(pt[0]), cy: T.Y(pt[1]), r: 6,
    class: "handle" + (fixed ? " locked" : "") + (kind === "keyPivot" ? " sel" : ""),
  }, svg);
  h.appendChild(el("title", { text: tip }));
  if (fixed) return;
  h.addEventListener("pointerdown", (e) => startDrag(e, kind, keyIdx));
}

function addHoleDots(svg, T, g, p, keyIdx) {
  // 键杠上的孔位（轴→键尾方向，沿 y）：catalog keyHole
  const [px, py] = [T.X(p.keyPivot[0]), T.Y(p.keyPivot[1])];
  const dirY = 1;
  state.model.catalog.keyHole.forEach((d) => {
    const cx = px, cy = py + d * T.s * dirY;
    const dot = el("circle", { cx, cy, r: 3.6,
      class: "hole" + (Math.abs(d - g.keyHole) < 1e-9 ? " sel" : "") }, svg);
    dot.onclick = (e) => { e.stopPropagation(); edit(keyIdx, "keyHole", d)
      .then(applyAnalysis).catch(showErr); };
  });
  // 输入角孔（沿角，从轴向 -y 投影长 = horn*cosβ）
  const beta = g.rollerBetaIn * Math.PI / 180;
  state.model.catalog.rollerInHorn.forEach((L) => {
    const cx = T.X(p.rollerAxisIn[0]);
    const cy = T.Y(g.rollerY - L * Math.cos(beta));
    const dot = el("circle", { cx, cy, r: 3.2,
      class: "hole" + (Math.abs(L - g.rollerInHorn) < 1e-9 ? " sel" : "") }, svg);
    dot.onclick = (e) => { e.stopPropagation(); edit(keyIdx, "rollerInHorn", L)
      .then(applyAnalysis).catch(showErr); };
  });
  // 输出角孔
  state.model.catalog.rollerOutHorn.forEach((L) => {
    const cx = T.X(p.rollerAxisOut[0]);
    const cy = T.Y(g.rollerY + L);
    const dot = el("circle", { cx, cy, r: 3.2,
      class: "hole" + (Math.abs(L - g.rollerOutHorn) < 1e-9 ? " sel" : "") }, svg);
    dot.onclick = (e) => { e.stopPropagation(); edit(keyIdx, "rollerOutHorn", L)
      .then(applyAnalysis).catch(showErr); };
  });
}

function addJointToggle(svg, T, pt, keyIdx, joint, connected) {
  const j = el("circle", { cx: T.X(pt[0]), cy: T.Y(pt[1]), r: 4.6,
    class: "joint" + (connected ? "" : " off") }, svg);
  j.appendChild(el("title", { text: connected ? "点击：断开连接" : "点击：重新连接" }));
  j.onclick = (e) => {
    e.stopPropagation();
    const g = state.model.keys[keyIdx].geometry;
    const targetMap = { sticker_to_hornIn: "hornIn",
      hornOut_to_squareIn: "squareIn", squareOut_to_pallet: "pallet" };
    edit(keyIdx, "links", { joint,
      target: connected ? "" : targetMap[joint] })
      .then(applyAnalysis).catch(showErr);
  };
}

/* ------------------------------------------------------------------ 拖拽 */
function startDrag(e, kind, keyIdx) {
  e.preventDefault();
  e.target.setPointerCapture(e.pointerId);
  state.drag = { kind, key: keyIdx, moved: false, last: 0 };
  const move = async (ev) => {
    const svg = $("#stage");
    const pt = svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const loc = pt.matrixTransform(ctm.inverse());
    const T = makeTransform();
    const x = T.invX(loc.x), y = T.invY(loc.y);
    const now = performance.now();
    if (now - state.drag.last < 40) return;
    state.drag.last = now;
    state.drag.moved = true;
    let field, value;
    if (kind === "keyPivot") { field = "keyPivotY"; value = y; }
    else if (kind === "sticker") { field = "stickerX"; value = x; }
    else if (kind === "roller") { field = "rollerY"; value = y; }
    else if (kind === "square") { field = "squareY"; value = y; }
    try {
      const a = await edit(keyIdx, field, Math.round(value * 10) / 10);
      applyAnalysis(a);
    } catch (err) { /* 锁定等错误静默 */ }
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    state.drag = null;
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

/* ------------------------------------------------------------------ 播放动画 */
function drawPlayMotion(svg, T) {
  const fr = state.play.frame;
  const k = state.analysis.keys[state.selected];
  const p = k.points;
  const z0 = state.analysis.z;
  // 俯视主要是平面位置不动，用颜色+高亮显示力流；画位移箭头
  const flow = [
    ["keyFront", "keyPivot"], ["keyPivot", "hornInTip"],
    ["rollerAxisIn", "hornOutTip"], ["hornOutTip", "squareInTip"],
    ["square", "squareOutTip"], ["squareOutTip", "pallet"],
  ];
  const force = fr.f || 0;
  const intensity = Math.min(1, force / 12);
  flow.forEach((pair, idx) => {
    const a = p[pair[0]], b = p[pair[1]];
    if (!a || !b) return;
    el("line", {
      x1: T.X(a[0]), y1: T.Y(a[1]), x2: T.X(b[0]), y2: T.Y(b[1]),
      stroke: `rgba(220,60,30,${0.25 + 0.55 * intensity})`,
      "stroke-width": 2 + idx * 0.3, "stroke-dasharray": "4 4",
      "stroke-linecap": "round", fill: "none",
    }, svg);
  });
  // 阀板开启标识
  const [plX, plY] = p.pallet;
  el("text", { x: T.X(plX), y: T.Y(plY) - 20, "text-anchor": "middle",
    class: "lbl " + (fr.v >= 5 ? "ok" : "bad"),
    fill: fr.v >= 5 ? "#2f7d4f" : "#c0392b",
    text: `阀开 ${fr.v.toFixed(2)} mm　力 ${fr.f.toFixed(2)} N` }, svg);
}

function setPlayFrame(t) {
  state.play.t = t;
  const i = state.selected;
  api(`/api/play/${i}?t=${t.toFixed(3)}`).then((fr) => {
    state.play.frame = fr;
    if (state.view === "plan") renderPlan();
    else renderSide();
    renderStages(fr);
    $("#playSlider").value = Math.round(t * 40);
    $("#playVal").textContent = Math.round(t * 100) + "%";
  });
}

/* ------------------------------------------------------------------ 侧视图 */
function renderSide() {
  const svg = $("#stage");
  svg.innerHTML = "";
  svg.setAttribute("viewBox", "0 0 980 620");
  const i = state.selected;
  const g = state.model.keys[i].geometry;
  const k = state.analysis.keys[i];
  const p = k.points;
  const z = state.model.globals.z;

  // 侧视坐标：水平=y（进深），竖直=z
  const yMin = 140, yMax = 380, zMin = 80, zMax = 780;
  const ml = 80, mt = 40;
  const sx = (980 - ml * 2) / (yMax - yMin);
  const sy = 520 / (zMax - zMin);
  const Y = (mm) => ml + (mm - yMin) * sx;
  const Z = (mm) => mt + (zMax - mm) * sy;

  // 柜体
  el("rect", { x: Y(yMin), y: Z(zMax - 30), width: (yMax - yMin) * sx,
    height: (zMax - 30 - zMin) * sy + 8, rx: 4, class: "cabinet" }, svg);

  // 播放时 z 偏移
  const fr = state.play.frame;
  const dz = fr ? fr.z : null;
  // 播放帧中的滚轴转角 ψ 与转角器转角 φ（弧度）
  const psi = fr && fr.s ? fr.s.rollerAngleDeg * Math.PI / 180 : 0;
  const phi = fr && fr.s ? fr.s.squareAngleDeg * Math.PI / 180 : 0;

  // 关键点 z（静止或播放帧）
  const zpInTip0 = z.roller + g.rollerInHorn *
    Math.sin(g.rollerBetaIn * Math.PI / 180);
  const zpOutTip0 = z.roller - g.rollerOutHorn *
    Math.sin(g.rollerBetaOut * Math.PI / 180);
  const sqIn0 = z.squarePivot + g.squareInArm * Math.sin(Math.PI / 4);
  const sqOut0 = z.squarePivot + g.squareOutArm *
    Math.sin(Math.PI / 4 - g.squareAngleDeg * Math.PI / 180);

  const zKeyFront = dz ? dz.keyFront : z.keyPivot;
  const zFoot = dz ? dz.stickerFoot : z.keyPivot;
  const zHin = dz ? dz.hornInTip : zpInTip0;
  const zHout = dz ? dz.hornOutTip : zpOutTip0;
  const zSqIn = dz ? dz.squareInTip : sqIn0;
  const zSqOut = dz ? dz.squareOutTip : sqOut0;
  const zPal = dz ? dz.pallet : z.valve;

  // 侧投影：滚轴角随 ψ 转动（角尖 y,z 都变）；转角器臂随 φ 转动
  const bIn = g.rollerBetaIn * Math.PI / 180;
  const bOut = g.rollerBetaOut * Math.PI / 180;
  const aIn0 = Math.PI / 4;
  const aOut0 = Math.PI / 4 - g.squareAngleDeg * Math.PI / 180;
  const yHin = g.rollerY - g.rollerInHorn * Math.cos(bIn + psi);
  const yHout = g.rollerY + g.rollerOutHorn * Math.cos(bOut + psi);
  const ySqIn = p.square[1] - g.squareInArm * Math.cos(aIn0 - phi);
  const ySqOut = p.square[1] + g.squareOutArm * Math.cos(aOut0 - phi);

  const seg = (y1, z1, y2, z2, cls, w) => el("line", {
    x1: Y(y1), y1: Z(z1), x2: Y(y2), y2: Z(z2), class: cls,
    "stroke-width": w || null }, svg);

  // 键杠
  seg(p.keyFront[1], zKeyFront, p.keyPivot[1], z.keyPivot, "keylever", 5);
  seg(p.keyPivot[1], z.keyPivot, p.stickerFoot[1], zFoot, "keylever", 5);
  el("circle", { cx: Y(p.keyPivot[1]), cy: Z(z.keyPivot), r: 5, fill: "#333" }, svg);
  // 立木
  if (g.links.sticker_to_hornIn === "hornIn")
    seg(p.stickerFoot[1], zFoot, yHin, zHin, "part sticker", 3.4);
  // 滚轴
  el("circle", { cx: Y(g.rollerY), cy: Z(z.roller), r: 6,
    fill: "#4a5d78", stroke: "#27384d", "stroke-width": 1.3 }, svg);
  if (g.links.sticker_to_hornIn === "hornIn")
    seg(g.rollerY, z.roller, yHin, zHin, "part horn");
  if (g.links.hornOut_to_squareIn === "squareIn")
    seg(g.rollerY, z.roller, yHout, zHout, "part horn");
  // tracker A（竖杆：转动中输出角尖 y 与输入臂尖 y 同步变化）
  if (g.links.hornOut_to_squareIn === "squareIn")
    seg(yHout, zHout, ySqIn, zSqIn, "part tracker", 3);
  // 转角器
  el("circle", { cx: Y(p.square[1]), cy: Z(z.squarePivot), r: 6,
    fill: "#7a4b9a" }, svg);
  seg(ySqIn, zSqIn, p.square[1], z.squarePivot, "square-arm", 2.8);
  seg(p.square[1], z.squarePivot, ySqOut, zSqOut, "square-arm", 2.8);
  // 阀拉索 + 阀板 + 簧
  if (g.links.squareOut_to_pallet === "pallet")
    seg(ySqOut, zSqOut, ySqOut, zPal, "part tracker-b", 2);
  el("rect", { x: Y(ySqOut) - 16, y: Z(zPal) - 5, width: 32, height: 10,
    rx: 2, class: "pallet" }, svg);
  el("path", { d: `M${Y(ySqOut) + 18},${Z(zPal)} q4,-7 8,0 t8,0 t8,0`,
    fill: "none", stroke: "#b07b2b", "stroke-width": 1.3 }, svg);

  // 层参考线 + 标签
  [["键杠轴", z.keyPivot, "#9a6a2f"], ["滚轴轴", z.roller, "#4a5d78"],
   ["转角器轴", z.squarePivot, "#7a4b9a"], ["阀板", z.valve, "#2f7d4f"]]
  .forEach(([lab, zz, c]) => {
    el("line", { x1: 40, y1: Z(zz), x2: 960, y2: Z(zz),
      stroke: c, "stroke-width": 0.6, "stroke-dasharray": "3 5", opacity: .55 }, svg);
    el("text", { x: 44, y: Z(zz) - 4, fill: c, class: "lbl", text:
      `${lab} ${zz.toFixed(0)}` }, svg);
  });
  el("text", { x: 940, y: 24, "text-anchor": "end", class: "lbl",
    text: `侧视图 · ${state.model.keys[i].name}（进深 y →，竖直 z ↑）` }, svg);

  // 位移标尺（右侧）
  if (fr) {
    const stages = fr.s || {};
    el("text", { x: 40, y: 30, class: "lbl", fill: "#c0392b",
      text: `t=${Math.round(state.play.t * 100)}%　` +
        `键前端↓${(state.play.t * state.model.globals.keyDepth).toFixed(2)}mm　` +
        `滚轴转 ${(stages.rollerAngleDeg || 0).toFixed(1)}°　` +
        `转角器转 ${(stages.squareAngleDeg || 0).toFixed(1)}°　` +
        `阀开 ${fr.v.toFixed(2)}mm　触键力 ${fr.f.toFixed(2)}N` }, svg);
  }
}

/* ------------------------------------------------------------------ 读数 */
function renderStages(fr) {
  const i = state.selected;
  const k = state.analysis.keys[i];
  const s = fr ? fr.s : k.stages;
  const ph = state.model.globals.physics;
  const rows = [
    ["① 键杠后端抬升", s.keyLift, "mm"],
    ["② 滚轴转角", s.rollerAngleDeg, "°"],
    ["② 输出角尖下行", s.rollerDrop, "mm"],
    ["③ 转角器转角", s.squareAngleDeg, "°"],
    ["④ 阀板开启量", s.valveOpen, "mm",
      s.valveOpen >= ph.valveOpenTarget ? "ok" : "ng"],
    ["阀拉索弹性伸长", s.elastB, "mm"],
    ["上行连杆弹性缩短", s.elastA, "mm"],
    ["阀板端阻力", s.fValve, "N"],
    ["上行连杆受力", s.fTrackerA, "N"],
    ["立木受力", s.fSticker, "N"],
    ["键前端触键力", s.fFront, "N",
      s.fFront > ph.effKeyFrontMax ? "ng" : "ok"],
    ["滚轴压力角", s.gammaRoller, "°",
      s.gammaRoller < state.model.globals.limits.deadAngleDeg ? "ng" : ""],
    ["转角器压力角(出)", s.gammaSqOut, "°",
      s.gammaSqOut < state.model.globals.limits.deadAngleDeg ? "ng" : ""],
    ["空程（阀开始开）", k.metrics.lostMotion, "mm"],
  ];
  $("#stagesTable").innerHTML = rows.map(([a, v, u, cls]) =>
    `<tr><td>${a}</td><td class="${cls || ""}">${(+v).toFixed(2)} ${u}</td></tr>`
  ).join("");
}

function renderSummary() {
  const s = state.analysis.summary;
  const ph = state.model.globals.physics;
  const feelLim = state.model.globals.limits.keyFeelMax;
  const box = $("#summaryBox");
  const item = (label, v, cls) =>
    `<div class="stat"><span>${label}</span><b class="${cls || ""}">${v}</b></div>`;
  box.innerHTML =
    item("违规总数", s.violationCount, s.violationCount ? "ng" : "ok") +
    item("严重错误", s.errorCount, s.errorCount ? "ng" : "ok") +
    item("最大触键力", s.maxForce.toFixed(2) + " N",
      s.maxForce > ph.effKeyFrontMax ? "ng" : "ok") +
    item("最大键间手感差", s.feelMaxAdj.toFixed(2) + " N",
      s.feelMaxAdj > feelLim ? "ng" : "ok") +
    item("最小阀板开启", s.minValveOpen.toFixed(2) + " mm",
      s.minValveOpen < ph.valveOpenTarget ? "ng" : "ok");
}

function renderViolations() {
  const box = $("#violBox");
  const vs = state.analysis.violations;
  if (!vs.length) {
    box.innerHTML = '<div class="viol ok">✓ 无违规，布局可行</div>';
    return;
  }
  box.innerHTML = vs.map((v, idx) =>
    `<div class="viol ${v.severity === "error" ? "error" : ""}" data-i="${idx}">
      <div class="code">${v.code} · ${v.part || ""}</div>${v.msg}</div>`
  ).join("");
  $$(".viol[data-i]", box).forEach((d) => {
    d.onclick = () => {
      const v = vs[+d.dataset.i];
      if (v.keys && v.keys.length) { state.selected = v.keys[0]; render(); }
    };
  });
}

/* ------------------------------------------------------------------ 搜索 */
async function runSearch() {
  const budget = parseInt($("#searchBudget").value) || 500;
  const out = $("#searchResults");
  out.innerHTML = '<div class="searching">搜索中…（邻居枚举 + 贪心修复 + 随机采样）</div>';
  const r = await api("/api/search", "POST", { budget });
  state.lastSearch = r;
  const head = `<div class="cand head"><div class="r1">
      <span>#</span><span>违规</span><span>最大力</span><span>手感差</span>
      <span>改孔量</span><span></span></div></div>`;
  out.innerHTML = head + r.results.slice(0, 15).map((c) => {
    const s = c.score;
    const zero = s.violations === 0;
    return `<div class="cand" data-rank="${c.rank}">
      <div class="r1">
        <span class="rank">#${c.rank}</span>
        <span class="${s.violations ? "ng" : "ok"}">${s.violations}${s.errors ? ` (${s.errors}严重)` : ""}</span>
        <span>${s.maxForce.toFixed(2)}N</span>
        <span class="${s.feel > 2 ? "ng" : ""}">${s.feel.toFixed(2)}</span>
        <span>${s.cost.toFixed(1)}</span>
        <button class="btn primary ${zero ? "" : ""}">采纳</button>
      </div>
      <div class="badges">
        <span class="badge ${zero ? "zero" : ""}">${zero ? "可行布局" : "仍有违规"}</span>
        <span class="badge">最小阀开 ${c.summary.minValveOpen.toFixed(2)}mm</span>
      </div>
      <div class="r2">${c.violationsPreview.map((m) => "· " + m).join("<br>") || "全部检查通过"}</div>
    </div>`;
  }).join("");
  $$(".cand[data-rank] button", out).forEach((b) => {
    b.onclick = async () => {
      const rank = +b.closest(".cand").dataset.rank;
      const cand = r.results.find((x) => x.rank === rank);
      const a = await api("/api/adopt", "POST", { values: cand.values });
      applyAnalysis(a);
      flash("已采纳 #" + rank + "，几何与计算参数已保留");
    };
  });
}

/* ------------------------------------------------------------------ 快照 / 图 */
async function renderSnapshots() {
  const snaps = await api("/api/snapshots").catch(() => []);
  $("#snapList").innerHTML = snaps.length ? snaps.map((s) =>
    `<div class="snap"><span>#${s.id} ${s.label}</span>
      <button class="btn" data-id="${s.id}">恢复</button></div>`).join("")
    : '<div class="tip">暂无快照</div>';
  $$("#snapList button").forEach((b) => {
    b.onclick = async () => {
      const a = await api(`/api/snapshots/${b.dataset.id}/restore`, "POST");
      applyAnalysis(a);
    };
  });
}

async function openDrawing(kind) {
  const key = state.selected;
  const url = `/api/drawing/${kind}?key=${key}`;
  const txt = await (await fetch(url)).text();
  $("#drawTitle").textContent = (kind === "front" ? "正视" : "侧视") + "装配图（带编号尺寸）";
  $("#drawBody").innerHTML = txt;
  $("#btnDrawDownload").onclick = () => {
    const a = document.createElement("a");
    a.href = url + "&download=1"; a.download = kind + "_assembly.svg"; a.click();
  };
  $("#drawModal").classList.remove("hidden");
}

/* ------------------------------------------------------------------ 杂项 */
function applyAnalysis(resp) {
  // 写接口返回 {model, analysis}；个别接口直接返回 analysis
  if (resp.analysis) { state.analysis = resp.analysis; }
  if (resp.model) { state.model = resp.model; }
  if (!resp.analysis && resp.summary) { state.analysis = resp; }
  render();
}
function showErr(e) {
  flash("⚠ " + e.message, true);
}
let flashTimer;
function flash(msg, bad) {
  const h = $("#hint");
  h.textContent = msg;
  h.style.color = bad ? "#c0392b" : "#0b5cab";
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    h.textContent = "拖动方块支点移动构件；点击臂上小圆孔切换孔位；点击连杆端点连接/断开。";
    h.style.color = "";
  }, 3500);
}

/* ------------------------------------------------------------------ 初始化 */
async function boot() {
  const st = await api("/api/state");
  state.projectId = st.projectId;
  state.model = st.model;
  state.analysis = st.analysis;
  render();

  // 播放
  $("#btnPlay").onclick = () => {
    if (state.play.on) {
      stopPlay();
    } else {
      state.play.on = true;
      $("#btnPlay").textContent = "■ 停止";
      let dir = 1;
      state.play.timer = setInterval(() => {
        let t = state.play.t + dir * 0.025;
        if (t >= 1) { t = 1; dir = -1; }
        if (t <= 0) { t = 0; stopPlay(); return; }
        setPlayFrame(t);
      }, 60);
    }
  };
  function stopPlay() {
    state.play.on = false;
    clearInterval(state.play.timer);
    $("#btnPlay").textContent = "▶ 按键播放";
    state.play.t = 0;
    state.play.frame = null;
    $("#playSlider").value = 0;
    $("#playVal").textContent = "0%";
    render();
  }
  $("#playSlider").oninput = (e) => {
    if (state.play.on) stopPlay();
    setPlayFrame(e.target.value / 40);
  };

  $$(".tab").forEach((t) => t.onclick = () => {
    $$(".tab").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    state.view = t.dataset.view;
    state.play.t = 0; state.play.frame = null;
    render();
  });

  $("#btnSearch").onclick = () => runSearch().catch(showErr);
  $("#btnReset").onclick = async () => {
    if (!confirm("恢复到样板工程？当前编辑将丢失。")) return;
    applyAnalysis(await api("/api/reset", "POST"));
  };
  $("#btnSnapshot").onclick = async () => {
    const label = prompt("快照名称", "方案 " + new Date().toLocaleTimeString());
    if (!label) return;
    await api("/api/snapshots", "POST", { label });
    renderSnapshots();
  };
  $("#btnDrawFront").onclick = () => openDrawing("front").catch(showErr);
  $("#btnDrawSide").onclick = () => openDrawing("side").catch(showErr);
  $("#btnDrawClose").onclick = () => $("#drawModal").classList.add("hidden");
  $("#projectName").onchange = async (e) => {
    state.model.name = e.target.value;
    await api("/api/model", "PUT", { name: e.target.value });
  };
}

boot().catch((e) => {
  document.body.insertAdjacentHTML("afterbegin",
    `<div style="padding:20px;color:#c0392b">启动失败：${e.message}</div>`);
  console.error(e);
});
