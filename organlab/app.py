"""Flask 入口：模型编辑、分析、播放、搜索、采纳、持久化、装配图。"""
import copy
import json
import os

from flask import (Flask, Response, abort, jsonify, render_template,
                   request, send_file)

from . import db, drawing, physics, search
from .defaults import build_default_model

app = Flask(__name__)


def out(model, selected=None):
    """写操作统一返回模型与分析，前端据此同步 state.model。"""
    return jsonify({"model": model,
                    "analysis": physics.analyze(model, selected=selected)})


# --------------------------------------------------------------- 会话状态
def _current():
    """取当前活动工程（内存中的工作模型），不存在则以种子初始化并入库。"""
    pid = os.environ.get("ORGANLAB_PID")
    proj = db.load_project(int(pid)) if pid else None
    if proj is None:
        model = build_default_model()
        pid = db.create_project(model["name"], model)
        os.environ["ORGANLAB_PID"] = str(pid)
        proj = db.load_project(pid)
    return proj


@app.before_request
def _ensure_db():
    db.init_db()


# --------------------------------------------------------------- 页面
@app.route("/")
def index():
    return render_template("index.html")


# --------------------------------------------------------------- 模型
@app.route("/api/state")
def api_state():
    proj = _current()
    a = physics.analyze(proj["model"], selected=0)
    return jsonify({"projectId": proj["id"], "name": proj["name"],
                    "model": proj["model"], "analysis": a})


@app.route("/api/analysis")
def api_analysis():
    proj = _current()
    sel = int(request.args.get("key", 0))
    return jsonify(physics.analyze(proj["model"], selected=sel))


@app.route("/api/model", methods=["PUT"])
def api_update_model():
    body = request.get_json(force=True)
    proj = _current()
    model = proj["model"]
    if "globals" in body:
        model["globals"] = body["globals"]
    if "fixed" in body:
        model["fixed"] = body["fixed"]
    if "name" in body:
        model["name"] = body["name"]
    db.save_project(proj["id"], model["name"], model)
    return out(model, int(body.get("selected", 0)))


@app.route("/api/key/<int:i>", methods=["PUT"])
def api_update_key(i):
    proj = _current()
    if not (0 <= i < len(proj["model"]["keys"])):
        abort(404)
    body = request.get_json(force=True)
    key = proj["model"]["keys"][i]
    g = key["geometry"]
    # 锁定键与柜内固定件不允许几何编辑
    if key.get("locked"):
        return jsonify({"error": "该音键已锁定，不能编辑"}), 409
    patch = body.get("geometry", {})
    for k, v in patch.items():
        if k in g and k != "links":
            g[k] = v
    if "locked" in body:
        key["locked"] = bool(body["locked"])
    if "links" in body:
        g.setdefault("links", {}).update(body["links"])
    db.save_project(proj["id"], proj["model"]["name"], proj["model"])
    return out(proj["model"], i)


@app.route("/api/key/<int:i>/lock", methods=["POST"])
def api_lock_key(i):
    proj = _current()
    if not (0 <= i < len(proj["model"]["keys"])):
        abort(404)
    locked = bool(request.get_json(force=True).get("locked", True))
    proj["model"]["keys"][i]["locked"] = locked
    db.save_project(proj["id"], proj["model"]["name"], proj["model"])
    return jsonify({"id": i, "locked": locked})


def _normalize(g, model, keep_pivot=False, keep_square_y=False):
    """改孔/拖拽后重算联动几何：立木、tracker A/B 默认竖直。"""
    import math
    z = model["globals"]["z"]
    beta = math.radians(g["rollerBetaIn"])
    horn_in_y = g["rollerY"] - g["rollerInHorn"] * math.cos(beta)
    if keep_pivot:
        g["keyHole"] = round(max(8.0, horn_in_y - g["keyPivotY"]), 1)
    else:
        g["keyPivotY"] = round(horn_in_y - g["keyHole"], 2)
    if not keep_square_y:
        g["squareY"] = round(g["rollerY"] + g["rollerOutHorn"]
                             + g["squareInArm"] * math.cos(math.pi / 4), 2)
    alpha = math.radians(g["squareAngleDeg"])
    g["palletY"] = round(g["squareY"] + g["squareOutArm"]
                         * math.cos(abs(math.pi / 4 - alpha)), 2)


CATALOG_FIELDS = ("keyHole", "rollerInHorn", "rollerOutHorn", "squareInArm",
                  "squareOutArm", "squareAngleDeg", "rollerBetaIn")


@app.route("/api/edit", methods=["POST"])
def api_edit():
    """语义化编辑。body: {key:i, field:f, value:v}。
    field 为孔位/臂长档位字段或 keyPivotY/stickerX/squareY/rollerY/squareXPitch。
    rollerY 为滚轴板整体移动（未锁定时）。"""
    body = request.get_json(force=True)
    proj = _current()
    model = proj["model"]
    i = int(body["key"])
    f = body["field"]
    v = body["value"]
    if not (0 <= i < len(model["keys"])):
        abort(404)
    key = model["keys"][i]
    g = key["geometry"]
    if key.get("locked") and f != "links":
        return jsonify({"error": "该音键已锁定"}), 409

    if f in CATALOG_FIELDS:
        g[f] = float(v) if f != "squareAngleDeg" and f != "rollerBetaIn" else float(v)
        _normalize(g, model)
    elif f == "squareXPitch":
        sp = model["globals"]["keySpacing"]
        col = max(0, min(model["globals"]["keyCount"] - 1, i + int(v)))
        g["squareX"] = col * sp + 12
        g["palletX"] = g["squareX"]
    elif f == "keyPivotY":
        g["keyPivotY"] = float(v)
        _normalize(g, model, keep_pivot=True)
    elif f == "stickerX":
        g["stickerX"] = float(v)
    elif f == "squareY":
        g["squareY"] = float(v)
        _normalize(g, model, keep_square_y=True)
    elif f == "rollerY":
        if model["fixed"].get("rollerBoard"):
            return jsonify({"error": "滚轴板已锁定"}), 409
        y = float(v)
        rng = model["catalog"]["rollerY"]
        y = max(rng[0], min(rng[-1], y))
        for k2 in model["keys"]:
            k2["geometry"]["rollerY"] = round(y, 1)
            if not k2.get("locked"):
                _normalize(k2["geometry"], model)
    elif f == "links":
        g.setdefault("links", {})[v["joint"]] = v["target"]
    elif f in ("valveGap",):
        g[f] = max(0.0, float(v))
    else:
        return jsonify({"error": f"未知字段 {f}"}), 400
    db.save_project(proj["id"], model["name"], model)
    return jsonify({"model": model,
                    "analysis": physics.analyze(model, selected=i)})


@app.route("/api/fixed", methods=["POST"])
def api_set_fixed():
    body = request.get_json(force=True)
    proj = _current()
    proj["model"]["fixed"].update(body.get("fixed", {}))
    db.save_project(proj["id"], proj["model"]["name"], proj["model"])
    return jsonify(proj["model"]["fixed"])


@app.route("/api/reset", methods=["POST"])
def api_reset():
    proj = _current()
    fresh = build_default_model()
    db.save_project(proj["id"], fresh["name"], fresh)
    return out(fresh)


# --------------------------------------------------------------- 播放
@app.route("/api/play/<int:i>")
def api_play(i):
    proj = _current()
    model = proj["model"]
    if not (0 <= i < len(model["keys"])):
        abort(404)
    t = max(0.0, min(1.0, float(request.args.get("t", 0))))
    res = physics.solve_key(model["keys"][i]["geometry"],
                            model["globals"],
                            t * model["globals"]["keyDepth"])
    res["nodesZ"] = {k: round(v, 3) for k, v in res["nodesZ"].items()}
    res["stages"] = {k: round(v, 4) for k, v in res["stages"].items()}
    res["phi"] = round(res["phi"], 5)
    res["psi"] = round(res["psi"], 5)
    res["fFront"] = round(res["fFront"], 3)
    res["v"] = round(res["v"], 3)
    res["f"] = res["fFront"]   # 与扫查帧字段对齐，供前端播放使用
    return jsonify(res)


# --------------------------------------------------------------- 搜索
@app.route("/api/search", methods=["POST"])
def api_search():
    body = request.get_json(silent=True) or {}
    budget = int(body.get("budget", 500))
    proj = _current()
    result = search.search(proj["model"], budget=budget)
    run_id = db.save_search_run(proj["id"], result)
    result["runId"] = run_id
    return jsonify(result)


@app.route("/api/adopt", methods=["POST"])
def api_adopt():
    body = request.get_json(force=True)
    proj = _current()
    values = body.get("values")
    if not isinstance(values, dict):
        abort(400)
    model = search.adopt(proj["model"], values)
    db.save_project(proj["id"], model["name"], model)
    return out(model)


# --------------------------------------------------------------- 快照
@app.route("/api/snapshots", methods=["GET", "POST"])
def api_snapshots():
    proj = _current()
    if request.method == "POST":
        label = (request.get_json(force=True).get("label") or "快照")
        sid = db.add_snapshot(proj["id"], label, proj["model"])
        return jsonify({"id": sid, "label": label})
    return jsonify(db.list_snapshots(proj["id"]))


@app.route("/api/snapshots/<int:sid>/restore", methods=["POST"])
def api_restore_snapshot(sid):
    proj = _current()
    snap = db.load_snapshot(sid)
    if not snap or snap["project_id"] != proj["id"]:
        abort(404)
    db.save_project(proj["id"], snap["label"], snap["model"])
    return out(snap["model"])


# --------------------------------------------------------------- 工程
@app.route("/api/projects")
def api_projects():
    return jsonify(db.list_projects())


@app.route("/api/projects", methods=["POST"])
def api_create_project():
    body = request.get_json(force=True)
    model = build_default_model()
    if body.get("name"):
        model["name"] = body["name"]
    pid = db.create_project(model["name"], model)
    os.environ["ORGANLAB_PID"] = str(pid)
    return jsonify({"id": pid})


@app.route("/api/projects/<int:pid>/load", methods=["POST"])
def api_load_project(pid):
    if not db.load_project(pid):
        abort(404)
    os.environ["ORGANLAB_PID"] = str(pid)
    return api_state()


# --------------------------------------------------------------- 装配图
@app.route("/api/drawing/<kind>")
def api_drawing(kind):
    proj = _current()
    model = proj["model"]
    key_idx = int(request.args.get("key", 0))
    a = physics.analyze(model, selected=key_idx)
    if kind == "front":
        svg = drawing.front_view(model, a)
    elif kind == "side":
        svg = drawing.side_view(model, a, key_idx)
    else:
        abort(404)
    db.save_drawing(proj["id"], kind, svg)
    if request.args.get("download"):
        return Response(svg, mimetype="image/svg+xml",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{kind}_assembly.svg"'})
    return Response(svg, mimetype="image/svg+xml")


if __name__ == "__main__":
    db.init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
