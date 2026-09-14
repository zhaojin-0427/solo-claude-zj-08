"""可行布局搜索。

变量（每键，受“锁定”与固定件约束）：
  keyHole / rollerInHorn / rollerOutHorn / squareInArm / squareOutArm
  / squareAngleDeg / rollerBetaIn：从孔位档位表选值；
  squareXPitch：转角器服务的阀列偏移（以键距为档，0=本位，跨列计入改孔量）。
全局：rollerY（滚轴板未锁定时可前后移动）。

搜索策略：先做每键“邻居枚举”的定向修复，再叠加受限随机采样；
结果按 (违规数, 最大触键力, 键间手感差, 改孔量) 排序。
改孔量 = 各孔位档位跳档数加权和 + 跨列改列 ×键距 + 滚轴位移等。
"""
import copy
import math
import random

from . import physics

HOLE_WEIGHT = 1.0          # 跳一档
BETA_WEIGHT = 0.5
ANGLE_WEIGHT = 0.5
COLUMN_WEIGHT = 3.0        # 跨一列阀位（需重新穿管）
ROLLERY_WEIGHT = 0.05      # 每 2 mm
STICKERX_WEIGHT = 0.1      # 每 1 mm 错位


def _current_catalog(model):
    return model["catalog"]


def _geom_of(model, i):
    return model["keys"][i]["geometry"]


def reconfigure(model, values):
    """根据 values（每键参数 + 全局 rollerY）重算联动几何，返回新 model。

    结构约束：
    * 立木始终竖直：键杠支点 y 随滚轴 y/输入角/立木孔联动；
    * 阀拉索始终竖直：阀板 x 固定（风箱锁定），y 随输出臂投影联动；
    * 改列只移动转角器（squareX），阀板不动 —— 阀拉索斜拉是改列代价
      的一部分；恢复本位即消除交叉。
    """
    m = copy.deepcopy(model)
    cat = m["catalog"]
    sp = m["globals"]["keySpacing"]
    global_y = values.get("rollerY")

    for i, k in enumerate(m["keys"]):
        v = values.get(i) or values.get(str(i)) or {}
        g = k["geometry"]
        for fld in ("keyHole", "rollerInHorn", "rollerOutHorn",
                    "squareInArm", "squareOutArm", "squareAngleDeg",
                    "rollerBetaIn"):
            if fld in v:
                g[fld] = v[fld]
        if "squareXPitch" in v:
            col = i + v["squareXPitch"]
            # 风箱固定：阀板只能落在标准键距阀列上；转角器与阀板同列，
            # 改列即把整套执行件搬到目标阀列（改列量计入成本）。
            g["squareX"] = col * sp + 12
            g["palletX"] = g["squareX"]
        if global_y is not None and not m["fixed"].get("rollerBoard"):
            g["rollerY"] = global_y
        # squareY：输入臂尖与输出角尖俯视对齐，保证 tracker A 竖直
        g["squareY"] = round(
            g["rollerY"] + g["rollerOutHorn"]
            + g["squareInArm"] * math.cos(math.pi / 4), 2)
        # 键杠支点随输入角几何联动，保证立木竖直
        beta = math.radians(g["rollerBetaIn"])
        g["keyPivotY"] = round(
            g["rollerY"] - g["rollerInHorn"] * math.cos(beta) - g["keyHole"], 2)
        # 阀板 y 跟随输出臂俯视投影，阀拉索默认竖直
        alpha = math.radians(g["squareAngleDeg"])
        proj = g["squareOutArm"] * math.cos(abs(math.pi / 4 - alpha))
        g["palletY"] = round(g["squareY"] + proj, 2)
    return m


def _baseline_values(model):
    """当前模型对应的 values。"""
    cat = model["catalog"]
    sp = model["globals"]["keySpacing"]

    def idx(name, val):
        arr = cat[name]
        return min(range(len(arr)), key=lambda t: abs(arr[t] - val))

    vals = {"rollerY": model["keys"][0]["geometry"]["rollerY"]}
    for i, k in enumerate(model["keys"]):
        g = k["geometry"]
        col = round((g["squareX"] - 12) / sp) - i
        vals[i] = {
            "keyHole": idx("keyHole", g["keyHole"]),
            "rollerInHorn": idx("rollerInHorn", g["rollerInHorn"]),
            "rollerOutHorn": idx("rollerOutHorn", g["rollerOutHorn"]),
            "squareInArm": idx("squareInArm", g["squareInArm"]),
            "squareOutArm": idx("squareOutArm", g["squareOutArm"]),
            "squareAngleDeg": idx("squareAngleDeg", g["squareAngleDeg"]),
            "rollerBetaIn": idx("rollerBetaIn", g["rollerBetaIn"]),
            "squareXPitch": int(col),
        }
    return vals


def _expand(model, vals):
    """把档位索引 values 展成实际数值供 reconfigure（键转为字符串以便 JSON）。"""
    cat = model["catalog"]
    out = {}
    if "rollerY" in vals:
        out["rollerY"] = vals["rollerY"]
    for i in range(len(model["keys"])):
        src = vals[i]
        row = dict(src)
        for fld in ("keyHole", "rollerInHorn", "rollerOutHorn",
                    "squareInArm", "squareOutArm", "squareAngleDeg",
                    "rollerBetaIn"):
            row[fld] = cat[fld][src[fld]]
        out[str(i)] = row
    return out


def modification_cost(model, vals):
    """相对当前布局的改孔量（加权）。"""
    base = _baseline_values(model)
    cost = 0.0
    locked = {i for i, k in enumerate(model["keys"]) if k.get("locked")}
    for i in range(len(model["keys"])):
        if i in locked:
            continue
        b, v = base[i], vals[i]
        cost += HOLE_WEIGHT * (abs(v["keyHole"] - b["keyHole"])
                               + abs(v["rollerInHorn"] - b["rollerInHorn"])
                               + abs(v["rollerOutHorn"] - b["rollerOutHorn"])
                               + abs(v["squareInArm"] - b["squareInArm"])
                               + abs(v["squareOutArm"] - b["squareOutArm"]))
        cost += ANGLE_WEIGHT * abs(v["squareAngleDeg"] - b["squareAngleDeg"])
        cost += BETA_WEIGHT * abs(v["rollerBetaIn"] - b["rollerBetaIn"])
        cost += COLUMN_WEIGHT * abs(v["squareXPitch"] - b["squareXPitch"])
    y0 = base.get("rollerY")
    if y0 is not None and "rollerY" in vals and not model["fixed"].get("rollerBoard"):
        cost += ROLLERY_WEIGHT * abs(vals["rollerY"] - y0) / 2.0
    return round(cost, 2)


def score(model, analysis, vals):
    s = analysis["summary"]
    return {
        "violations": s["violationCount"],
        "errors": s["errorCount"],
        "maxForce": s["maxForce"],
        "feel": round(s["feelMaxAdj"], 3),
        "cost": modification_cost(model, vals),
    }


def _evaluate(model, vals_idx):
    expanded = _expand(model, vals_idx)
    m2 = reconfigure(model, expanded)
    a = physics.analyze(m2)
    sc = score(model, a, vals_idx)
    return m2, a, sc


def _viol_keys(a):
    vk = {}
    for v in a["violations"]:
        for i in v["keys"]:
            vk.setdefault(i, []).append(v["code"])
    return vk


# 每类违规的优先修复档位（字段，方向说明在注释）
FIX_FIELDS = [
    ("squareOutArm", +1),    # 加长输出臂 → 行程增加
    ("keyHole", +1),         # 立木孔外移 → 键杠增益
    ("rollerOutHorn", +1),   # 输出角加长 → 下行量
    ("squareInArm", -1),     # 输入臂缩短 → square 增益
    ("rollerInHorn", -1),    # 输入角缩短 → 滚轴角增益
    ("rollerBetaIn", -1),    # 安装角放平 → 远离死点
]


def _neighbors(vals, model, radius=1):
    """产生每键单变量 ±radius 的邻居（跳过锁定键）。"""
    cat = model["catalog"]
    n = len(model["keys"])
    locked = {i for i, k in enumerate(model["keys"]) if k.get("locked")}
    ranges = {
        "keyHole": cat["keyHole"], "rollerInHorn": cat["rollerInHorn"],
        "rollerOutHorn": cat["rollerOutHorn"], "squareInArm": cat["squareInArm"],
        "squareOutArm": cat["squareOutArm"],
        "squareAngleDeg": cat["squareAngleDeg"],
        "rollerBetaIn": cat["rollerBetaIn"],
    }
    for i in range(n):
        if i in locked:
            continue
        for fld, arr in ranges.items():
            for d in (-radius, +radius):
                nv = copy.deepcopy(vals)
                nv[i][fld] = max(0, min(len(arr) - 1, nv[i][fld] + d))
                if nv[i][fld] != vals[i][fld]:
                    yield nv
        # 阀列改列（搜索范围 ±1，避免大改）
        for d in (-1, +1):
            nv = copy.deepcopy(vals)
            t = nv[i]["squareXPitch"] + d
            if -2 <= t <= 2:
                nv[i]["squareXPitch"] = t
                yield nv
    # 全局滚轴板
    if not model["fixed"].get("rollerBoard"):
        for y in cat["rollerY"]:
            if y != vals.get("rollerY"):
                nv = copy.deepcopy(vals)
                nv["rollerY"] = y
                yield nv


def search(model, budget=900, seed=20260914):
    """返回排序后的候选方案列表。"""
    rng = random.Random(seed)
    cat = model["catalog"]
    n = len(model["keys"])
    locked = {i for i, k in enumerate(model["keys"]) if k.get("locked")}
    results = []
    seen = set()

    def push(vals):
        sig = json_sig(vals)
        if sig in seen:
            return None
        seen.add(sig)
        try:
            m2, a, sc = _evaluate(model, vals)
        except Exception:
            return None
        results.append({"score": sc, "values": copy.deepcopy(vals),
                        "expanded": _expand(model, vals),
                        "summary": a["summary"],
                        "violations": a["violations"]})
        return sc

    def json_sig(vals):
        return (tuple((v["keyHole"], v["rollerInHorn"], v["rollerOutHorn"],
                       v["squareInArm"], v["squareOutArm"],
                       v["squareAngleDeg"], v["rollerBetaIn"],
                       v["squareXPitch"]) for v in
                      (vals[i] for i in range(n))), vals.get("rollerY"))

    # 0) 现状
    base = _baseline_values(model)
    push(base)

    # 1) 定向局部爬山：按违规涉及的键优先改
    cur = copy.deepcopy(base)
    cur_sc = results[0]["score"]
    for _sweep in range(6):
        _, a0, _ = _evaluate(model, cur)
        vk = _viol_keys(a0)
        best, best_sc = None, cur_sc
        cat_arr = {
            "keyHole": cat["keyHole"], "rollerInHorn": cat["rollerInHorn"],
            "rollerOutHorn": cat["rollerOutHorn"],
            "squareInArm": cat["squareInArm"],
            "squareOutArm": cat["squareOutArm"],
            "squareAngleDeg": cat["squareAngleDeg"],
            "rollerBetaIn": cat["rollerBetaIn"],
        }
        candidates = []
        for i, codes in vk.items():
            if i in locked:
                continue
            fields = list(FIX_FIELDS)
            if "DEADPOINT" in codes or "FORCE" in codes:
                fields = [("rollerBetaIn", -1)] + fields
            for fld, d in fields:
                nv = copy.deepcopy(cur)
                if fld == "squareXPitch":
                    nv[i][fld] = max(-2, min(2, nv[i][fld] + d))
                else:
                    arr = cat_arr[fld]
                    nv[i][fld] = max(0, min(len(arr) - 1,
                                            nv[i][fld] + d))
                if nv[i] != cur[i] or fld == "squareXPitch":
                    candidates.append(nv)
        # 交叉擦碰：收集 CROSS 键对，成对地回本位（解除交换的关键）
        cross_keys = set()
        for v in a0["violations"]:
            if v["code"] == "CROSS":
                cross_keys.update(v["keys"])
        if len(cross_keys) >= 2:
            cks = sorted(cross_keys)
            for a in range(len(cks)):
                for b in range(a + 1, len(cks)):
                    i, j = cks[a], cks[b]
                    if i in locked or j in locked:
                        continue
                    nv = copy.deepcopy(cur)
                    nv[i]["squareXPitch"] = 0
                    nv[j]["squareXPitch"] = 0
                    candidates.append(nv)
            for i in cks:
                if i in locked:
                    continue
                for t in (-1, 1):
                    nv = copy.deepcopy(cur)
                    nv[i]["squareXPitch"] = t
                    candidates.append(nv)
        # 评估全部候选
        improved = False
        for nv in candidates:
            sig = json_sig(nv)
            if sig in seen:
                sc = next((r["score"] for r in results
                           if json_sig(r["values"]) == sig), None)
            else:
                sc = push(nv)
            if sc and _better(sc, best_sc):
                best, best_sc, improved = nv, sc, True
        if not improved:
            break
        cur, cur_sc = best, best_sc
        if cur_sc["errors"] == 0 and cur_sc["violations"] == 0:
            break

    # 1b) 确定性贪心修复：从现状出发，逐违规键应用修复，
    #     每步在所有候选中选违规最少者（保证稳定找到可行解）。
    def greedy_repair(start):
        gv = copy.deepcopy(start)
        for _ in range(12):
            _, a0, sc0 = _evaluate(model, gv)
            if sc0["violations"] == 0:
                break
            vk0 = _viol_keys(a0)
            cands = []
            cross_keys = set()
            for v in a0["violations"]:
                if v["code"] == "CROSS":
                    cross_keys.update(v["keys"])
            cks = sorted(cross_keys)
            for a in range(len(cks)):
                for b in range(a + 1, len(cks)):
                    if cks[a] in locked or cks[b] in locked:
                        continue
                    nv = copy.deepcopy(gv)
                    nv[cks[a]]["squareXPitch"] = 0
                    nv[cks[b]]["squareXPitch"] = 0
                    cands.append(nv)
            for i, codes in vk0.items():
                if i in locked:
                    continue
                moves = []
                if "DEADPOINT" in codes or "FORCE" in codes:
                    # 安装角过大是死点根源：直接放平到 0°（再考虑相邻档）
                    moves += [("rollerBetaIn", 0), ("rollerBetaIn", -1)]
                if "TRAVEL" in codes:
                    moves += [("squareOutArm", +1), ("keyHole", +1),
                              ("rollerOutHorn", +1), ("squareInArm", -1)]
                if "SLANT" in codes:
                    moves += [("rollerOutHorn", -1), ("squareOutArm", -1),
                              ("squareXPitch", 0)]
                for fld, d in moves:
                    nv = copy.deepcopy(gv)
                    if fld == "squareXPitch":
                        nv[i][fld] = d
                    elif d == 0:
                        nv[i][fld] = 0      # 绝对跳档（如安装角放平）
                    else:
                        size = len(cat[fld])
                        nv[i][fld] = max(0, min(size - 1, nv[i][fld] + d))
                    if nv[i] != gv[i]:
                        cands.append(nv)
            if not cands:
                break
            best_c, best_csc = None, sc0
            for nv in cands:
                sig = json_sig(nv)
                if sig in seen:
                    sc = next((r["score"] for r in results
                               if json_sig(r["values"]) == sig), None)
                else:
                    sc = push(nv)
                if sc and _better(sc, best_csc):
                    best_c, best_csc = nv, sc
            if best_c is None:
                break
            gv = best_c
        push(gv)

    greedy_repair(base)

    # 2) 受限随机采样
    fields_idx = {
        "keyHole": len(cat["keyHole"]),
        "rollerInHorn": len(cat["rollerInHorn"]),
        "rollerOutHorn": len(cat["rollerOutHorn"]),
        "squareInArm": len(cat["squareInArm"]),
        "squareOutArm": len(cat["squareOutArm"]),
        "squareAngleDeg": len(cat["squareAngleDeg"]),
        "rollerBetaIn": len(cat["rollerBetaIn"]),
    }
    attempts = 0
    while attempts < budget and len(seen) < budget:
        attempts += 1
        nv = copy.deepcopy(base)
        # 70% 采样只改 1~2 个键（贴近现状的小改方案）
        if rng.random() < 0.7:
            targets = rng.sample(range(n), rng.choice((1, 2)))
        else:
            targets = range(n)
        for i in targets:
            if i in locked:
                continue
            for fld, size in fields_idx.items():
                if rng.random() < 0.5:
                    nv[i][fld] = rng.randrange(size)
            if rng.random() < 0.12:
                nv[i]["squareXPitch"] = rng.choice((-1, 0, 0, 1))
        if not model["fixed"].get("rollerBoard") and rng.random() < 0.25:
            nv["rollerY"] = rng.choice(cat["rollerY"])
        push(nv)

    # 3) 排序：违规数(错>警)、最大力、手感差、改孔量
    def sort_key(r):
        s = r["score"]
        # 题目规定的排序：违规数 → 最大触键力 → 键间手感差 → 改孔量
        # （违规数相同的，error 多者略靠后作为次序内细分）
        return (s["violations"], s["errors"], s["maxForce"],
                s["feel"], s["cost"])

    results.sort(key=sort_key)
    out = []
    for rank, r in enumerate(results[:30], 1):
        out.append({
            "rank": rank,
            "score": r["score"],
            "values": r["expanded"],
            "summary": r["summary"],
            "violationCount": r["score"]["violations"],
            "violationsPreview": [v["msg"] for v in r["violations"][:6]],
        })
    return {"count": len(results), "results": out}


def _better(a, b):
    return (a["violations"], a["errors"], a["maxForce"], a["feel"], a["cost"]) < \
           (b["violations"], b["errors"], b["maxForce"], b["feel"], b["cost"])


def adopt(model, expanded_values):
    """采纳候选：把实际数值写回模型几何。"""
    return reconfigure(model, expanded_values)
