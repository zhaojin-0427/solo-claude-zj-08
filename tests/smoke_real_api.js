/* 用真实后端 /api/state + /api/play 数据做无头回归。
 * 需先启动服务器（http://127.0.0.1:5000）。
 * 用法：JSDOM_PATH=<jsdom路径> node tests/smoke_real_api.js
 */
const fs = require("fs");
const { JSDOM } = require(process.env.JSDOM_PATH || "jsdom");

const BASE = process.env.BASE || "http://127.0.0.1:5000";
const ROOT = require("path").join(__dirname, "..", "organlab");

async function getJSON(p) {
  const r = await fetch(BASE + p);
  if (!r.ok) throw new Error(p + " -> " + r.status);
  return r.json();
}

(async () => {
  const [st, play0, play1] = await Promise.all([
    getJSON("/api/state"),
    getJSON("/api/play/0?t=0"),
    getJSON("/api/play/0?t=1"),
  ]);
  const html = fs.readFileSync(ROOT + "/templates/index.html", "utf8")
    .replace('<script src="/static/js/app.js"></script>', "");
  const dom = new JSDOM(html, {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.SVGSVGElement.prototype.getScreenCTM = () =>
    ({ inverse: () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }) });
  window.SVGSVGElement.prototype.createSVGPoint = () =>
    ({ x: 0, y: 0, matrixTransform: () => ({ x: 0, y: 0 }) });
  window.fetch = async (url) => {
    const u = String(url);
    let json;
    if (u === "/api/state" || u.startsWith(BASE + "/api/state")) json = st;
    else if (u.includes("/api/play/")) {
      json = u.includes("t=0") ? play0 : play1;
    } else if (u.includes("/api/snapshots")) json = [];
    else json = {};
    return { ok: true, status: 200, json: async () => json, text: async () => "" };
  };
  const errs = [];
  window.addEventListener("error", (e) => errs.push(e.message));
  window.addEventListener("unhandledrejection",
    (e) => errs.push("REJ " + (e.reason && e.reason.message)));
  window.eval(fs.readFileSync(ROOT + "/static/js/app.js", "utf8"));

  await new Promise((r) => setTimeout(r, 300));
  const d = window.document;
  const assert = (cond, msg) => { if (!cond) throw new Error(msg); };

  // 面板由 HTML 命名空间元素组成（空白面板回归）
  assert(d.getElementById("keyList").children.length === st.analysis.keys.length,
    "音键列表为空");
  const sel0 = d.querySelector("#paramForm select");
  assert(sel0 && sel0.namespaceURI === "http://www.w3.org/1999/xhtml",
    "臂长下拉不是 HTML 元素");
  assert(d.querySelectorAll("#linkForm input[type=checkbox]").length === 3,
    "连接关系复选框缺失");
  assert(d.querySelectorAll("#fixedForm input[type=checkbox]").length === 3,
    "固定件复选框缺失");
  assert(d.querySelectorAll("#physForm input").length >= 7, "物理参数输入缺失");
  assert(d.querySelector("#stage > *").namespaceURI ===
    "http://www.w3.org/2000/svg", "SVG 构件不在 SVG 命名空间");

  // 播放到 100%：进度、位移、受力（/api/play 的 stages/nodesZ）
  const slider = d.getElementById("playSlider");
  slider.value = 40;
  slider.dispatchEvent(new window.Event("input", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 200));
  assert(d.getElementById("playVal").textContent === "100%", "进度未到 100%");
  const txt = d.getElementById("stagesTable").textContent;
  assert(!txt.includes("undefined"), "逐级读数出现 undefined");
  assert(txt.includes(play1.stages.keyLift.toFixed(2)), "未显示键杠抬升量");
  assert(!errs.length, "运行时错误: " + errs.join("; "));
  console.log(`REAL-API SMOKE OK  阀开=${play1.v.toFixed(2)}mm ` +
    `触键力=${play1.f.toFixed(2)}N`);
})().catch((e) => { console.error("FAIL:", e.message); process.exit(1); });
