/* 无头 DOM 冒烟：加载 index.html + app.js，mock fetch，验证渲染与交互。 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require(process.env.JSDOM_PATH || "jsdom");

const ROOT = "/workspace/organlab";
const html = fs.readFileSync(path.join(ROOT, "templates/index.html"), "utf8")
  .replace('<script src="/static/js/app.js"></script>', "");
const js = fs.readFileSync(path.join(ROOT, "static/js/app.js"), "utf8");

// ---- 构造与后端 /api/state 同形的假数据 ----
function fakeState() {
  const N = 8, sp = 24;
  const keys = [];
  const points = {};
  const names = ["keyFront","keyPivot","keyRear","stickerFoot","rollerAxisIn",
    "rollerAxisOut","hornInTip","hornOutTip","square","squareInTip",
    "squareOutTip","pallet"];
  for (let i = 0; i < N; i++) {
    const xc = i * sp + 12;
    const xv = (i === 2 ? 3 * sp + 12 : i === 3 ? 2 * sp + 12 : xc);
    const p = {
      keyFront: [xc, 174], keyPivot: [xc, 214], keyRear: [xc, 256],
      stickerFoot: [xc, 250], rollerAxisIn: [xc, 250], rollerAxisOut: [xc, 250],
      hornInTip: [xc, 212], hornOutTip: [xc, 288], square: [xv, 324.7],
      squareInTip: [xv, 288], squareOutTip: [xv, 335], pallet: [xv, 363.3],
    };
    const bad = i === 1 || i === 4;
    keys.push({
      id: i, name: "K" + (i + 1), locked: false,
      metrics: { valveOpen: i === 4 ? 4.49 : 5.55, fFrontFull: 8, fFrontMax:
        i === 1 ? 40 : 7.5 + (i % 2) * 0.5, lostMotion: 3.1, keyDepth: 10,
        deadAt: i === 1 ? 3.2 : null },
      stages: { keyLift: 9, rollerAngleDeg: 10, rollerDrop: 7,
        squareAngleDeg: 12, valveOpen: 5.5, fValve: 6, fTrackerA: 5,
        fSticker: 6, fFront: 8, gammaRoller: i === 1 ? 0.3 : 76,
        gammaSqIn: 33, gammaSqOut: 63, elastA: .2, elastB: .3 },
      points: p,
    });
    points[i] = p;
  }
  const frames = keys.map((k, i) => Array.from({ length: 41 }, (_, t) => ({
    z: Object.fromEntries(names.map((n) => [n, 400])),
    f: 8 * t / 40, v: 5.5 * t / 40,
    ...(i === 2 ? { s: { keyLift: 1, rollerAngleDeg: 2, rollerDrop: 1,
      squareAngleDeg: 3, valveOpen: 1, fValve: 2, fTrackerA: 2, fSticker: 2,
      fFront: 3, gammaRoller: 70, gammaSqIn: 40, gammaSqOut: 60,
      elastA: .1, elastB: .1 } } : {}),
  })));
  return {
    projectId: 1,
    model: {
      name: "测试工程",
      globals: {
        cabinet: { xMin: -10, xMax: 202, yMin: 100, yMax: 380 },
        keyCount: 8, keySpacing: 24, keyWidth: 23, keyDepth: 10,
        z: { keyPivot: 720, roller: 560, squarePivot: 260, valve: 150 },
        physics: { windPressurePa: 700, palletAreaMm2: 3200, palletMassN: .6,
          valveSpringN: 2.2, keyReturnSpringN: .9, trackerStiffness: 3.5,
          jointEff: .93, effKeyFrontMax: 11, valveOpenTarget: 5, steps: 41 },
        limits: { clearance: 8, slantLimit: 6, deadAngleDeg: 8, keyFeelMax: 2 },
      },
      fixed: { rollerBoard: false, windchest: true, keyFrame: true },
      keys: keys.map((k, i) => ({
        id: i, name: k.name, locked: false,
        geometry: {
          x: i * 24 + 12, keyPivotY: 214, keyHole: 36, stickerX: i * 24 + 12,
          rollerY: 250, rollerXIn: i * 24 + 12, rollerXOut: i * 24 + 12,
          rollerInHorn: 38, rollerOutHorn: 38, rollerBetaIn: i === 1 ? 68 : 0,
          rollerBetaOut: 0, squareX: k.points.square[0], squareY: 324.7,
          squareInArm: 52, squareOutArm: i === 4 ? 34 : 40,
          squareAngleDeg: 60, palletX: k.points.square[0], palletY: 363.3,
          valveGap: 1,
          links: { sticker_to_hornIn: "hornIn",
            hornOut_to_squareIn: "squareIn", squareOut_to_pallet: "pallet" },
        },
      })),
      catalog: {
        keyHole: [28, 32, 36, 40], rollerInHorn: [26, 30, 34, 38, 42],
        rollerOutHorn: [30, 34, 38, 42], squareInArm: [40, 46, 52, 58, 64],
        squareOutArm: [34, 38, 40, 45, 50], squareAngleDeg: [60, 66, 72],
        rollerBetaIn: [0, 20, 40, 60, 68],
        rollerY: [236, 238, 240, 242, 244, 246, 248, 250, 252, 254, 256, 258,
          260, 262, 264, 266, 268],
        squareXPitch: [-2, -1, 0, 1, 2],
      },
    },
    analysis: {
      summary: { violationCount: 5, errorCount: 3, maxForce: 40,
        feelMaxAdj: 32, feelSpread: 33, minValveOpen: 4.49 },
      violations: [
        { code: "DEADPOINT", keys: [1], part: "滚轴/转角器", severity: "error",
          msg: "键2 死点" },
        { code: "FORCE", keys: [1], part: "键前端", severity: "error",
          msg: "键2 力超限" },
        { code: "CROSS", keys: [2, 3], part: "上行连杆", severity: "error",
          at: [72, 292], msg: "键3/4 交叉" },
        { code: "SLANT", keys: [2], part: "上行连杆", severity: "warn",
          msg: "键3 偏折" },
        { code: "TRAVEL", keys: [4], part: "阀板", severity: "error",
          msg: "键5 行程不足" },
      ],
      keys, frames, selected: 0, feelAdj: [1, 1, 0, .5, .5, 0, 0],
      z: { keyPivot: 720, roller: 560, squarePivot: 260, valve: 150 },
    },
  };
}

const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true,
  url: "http://127.0.0.1:5000/" });
const { window } = dom;
window.SVGElement = window.SVGElement || function () {};
// getScreenCTM polyfill（jsdom 不做布局）
window.SVGSVGElement.prototype.getScreenCTM = function () {
  return { inverse: () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }) };
};
window.SVGPoint = undefined;

let state = fakeState();
let adopted = false;
window.fetch = async (url, opt) => {
  const u = String(url);
  let body = opt && opt.body ? JSON.parse(opt.body) : null;
  let json;
  if (u === "/api/state") json = state;
  else if (u.startsWith("/api/play/")) json = { dead: false, fFront: 8, f: 8, v: 5,
    z: Object.fromEntries(["keyFront","keyPivot","keyRear","stickerFoot",
      "rollerAxisIn","rollerAxisOut","hornInTip","hornOutTip","square",
      "squareInTip","squareOutTip","pallet"].map((n) => [n, 400])),
    s: state.analysis.keys[2].stages };
  else if (u === "/api/edit") {
    if (state.model.keys[body.key].locked)
      return { ok: false, status: 409, json: async () => ({ error: "锁定" }) };
    state.model.keys[body.key].geometry[body.field] = body.value;
    json = { model: state.model, analysis: state.analysis };
  } else if (u === "/api/search") {
    json = { count: 10, results: [{ rank: 1,
      score: { violations: 0, errors: 0, maxForce: 8, feel: .5, cost: 9 },
      values: { "0": { keyHole: 36 } }, summary: { minValveOpen: 5.2 },
      violationsPreview: [] }] };
  } else if (u === "/api/adopt") { adopted = true;
    state.analysis.summary.violationCount = 0;
    json = { model: state.model, analysis: state.analysis };
  } else if (u.startsWith("/api/key/") && u.includes("/lock")) {
    const i = +u.split("/api/key/")[1].split("/")[0];
    state.model.keys[i].locked = body.locked;
    json = { id: i, locked: body.locked };
  } else if (u === "/api/snapshots") {
    json = opt && opt.method === "POST" ? { id: 1, label: body.label } : [];
  } else if (u.startsWith("/api/drawing/")) {
    return { ok: true, status: 200, text: async () => "<svg></svg>" };
  } else if (u === "/api/reset" || u === "/api/model" || u === "/api/fixed") {
    json = { model: state.model, analysis: state.analysis };
  } else { json = {}; }
  return { ok: true, status: 200, json: async () => json, text: async () => "" };
};

// createSVGPoint polyfill
window.SVGSVGElement.prototype.createSVGPoint = function () {
  return { x: 0, y: 0, matrixTransform() { return { x: 0, y: 0 }; } };
};

const errors = [];
window.addEventListener("error", (e) => errors.push(e.message));

window.eval(js);

setTimeout(async () => {
  const doc = window.document;
  const $ = (s) => doc.querySelector(s);
  try {
    const stage = $("#stage");
    const nChildren = stage.children.length;
    console.log("plan svg children:", nChildren);
    if (nChildren < 30) throw new Error("SVG 未渲染足够构件");
    if (!/K\d/.test($("#keyList").textContent)) throw new Error("键列表未渲染");
    if (!$("#violBox").textContent.includes("死点")) throw new Error("违规未列出");
    if (!$("#stagesTable").textContent.includes("阀板开启量"))
      throw new Error("逐级读数未渲染");

    // 切换到 K2（死点键）
    doc.querySelectorAll(".keychip")[1].dispatchEvent(new window.Event("click",{bubbles:true}));
    await new Promise((r) => setTimeout(r, 20));

    // 切到侧视
    doc.querySelector(".tab[data-view=\"side\"]").dispatchEvent(new window.Event("click",{bubbles:true}));
    await new Promise((r) => setTimeout(r, 20));
    if ($("#stage").children.length < 10) throw new Error("侧视图未渲染");

    // 播放一帧（拖动 slider 触发 setPlayFrame）
    $("#playSlider").value = 20;
    $("#playSlider").dispatchEvent(new window.Event("input", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 60));

    // 搜索 + 采纳
    $("#btnSearch").dispatchEvent(new window.Event("click",{bubbles:true}));
    await new Promise((r) => setTimeout(r, 60));
    const adoptBtn = $(".cand[data-rank] button");
    if (!adoptBtn) throw new Error("搜索结果未渲染");
    adoptBtn.dispatchEvent(new window.Event("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 60));
    if (!adopted) throw new Error("采纳未调用");

    // 锁定后编辑被拒（检查 lock checkbox 存在）
    if (!$("#chkKeyLock")) throw new Error("锁定控件缺失");

    // 图纸 modal
    $("#btnDrawFront").dispatchEvent(new window.Event("click",{bubbles:true}));
    await new Promise((r) => setTimeout(r, 40));
    if ($("#drawModal").classList.contains("hidden"))
      throw new Error("装配图弹窗未打开");

    if (errors.length) throw new Error("运行时错误: " + errors.join("; "));
    console.log("HEADLESS SMOKE OK");
  } catch (e) {
    console.error("SMOKE FAIL:", e.message);
    process.exit(1);
  }
}, 300);
