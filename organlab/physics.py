"""管风琴机械传动物理 / 几何引擎（纯 Python，无第三方依赖）。

输入：defaults.build_default_model() 风格的模型 dict。
输出：各级位移/受力、键程、阀板开启量、触键力、空程，
以及死点、碰撞、交叉连杆、侧向偏折、行程不足等违规。

关键角关系
----------
滚轴：输入角初始仰角 β，轴转 ψ 后
  输入角尖升程 = hin·(sin(β+ψ)-sinβ)，β+ψ→90° 即竖直死点；
  输出角尖降程 = hout·sin(βout+ψ)。
转角器(square)：输入臂初始仰角 θ=45°，输出臂 = θ-α（α=初始夹角），
  折角杆转 φ 后输入臂尖下降 δin、输出臂尖下拉 δout。
弹性：立木/连杆按 K=EA/L 建模，木连杆受压会弹性缩短，
  阀拉索受拉会弹性伸长 —— 两者都吃掉有效行程。
"""
import math

THETA_IN = math.radians(45.0)
LF_KEY = 40.0
SQUARE_R = 9.0          # 转角器圆盘俯视半径
PALLET_W = 23.0
PALLET_D = 24.0
SPRING_RATE = 0.30      # 阀板开启后弹簧刚度 N/mm


# ================================================================ 几何
def plan_points(geom):
    """全部构件俯视关键点 (x, y)。竖直杆默认对齐，拖动错位即偏折。"""
    x = geom["x"]
    kh = geom["keyHole"]
    pivot_y = geom["keyPivotY"]
    front = (x, pivot_y - LF_KEY)
    pivot = (x, pivot_y)
    sticker_foot = (geom["stickerX"], pivot_y + kh)

    ry = geom["rollerY"]
    xi, xo = geom["rollerXIn"], geom["rollerXOut"]
    hin, hout = geom["rollerInHorn"], geom["rollerOutHorn"]
    beta_in = math.radians(geom["rollerBetaIn"])
    beta_out = math.radians(geom["rollerBetaOut"])
    horn_in_tip = (xi, ry - hin * math.cos(beta_in))
    horn_out_tip = (xo, ry + hout * math.cos(beta_out))

    sx, sy = geom["squareX"], geom["squareY"]
    a2 = geom["squareInArm"]
    b2 = geom["squareOutArm"]
    alpha = math.radians(geom["squareAngleDeg"])
    # 臂本身的俯视投影（绘制用）；连杆段端点取臂根(square)，
    # 以保证默认竖直对齐时无伪偏折。
    square_in_plan = (sx, sy - a2 * math.cos(THETA_IN))
    square_out_plan = (sx, sy + b2 * math.cos(abs(THETA_IN - alpha)))
    pallet = (geom["palletX"], geom["palletY"])
    return {
        "keyFront": front, "keyPivot": pivot,
        "keyRear": (x, pivot_y + kh + 6),
        "stickerFoot": sticker_foot,
        "rollerAxisIn": (xi, ry), "rollerAxisOut": (xo, ry),
        "hornInTip": horn_in_tip, "hornOutTip": horn_out_tip,
        "square": (sx, sy),
        "squareInTip": square_in_plan, "squareOutTip": square_out_plan,
        "pallet": pallet,
    }


def vertical_runs(geom, z):
    sticker = z["keyPivot"] - (
        z["roller"] + geom["rollerInHorn"] * math.sin(
            math.radians(geom["rollerBetaIn"])))
    sq_in_tip0 = z["squarePivot"] + geom["squareInArm"] * math.sin(THETA_IN)
    tracker_a = z["roller"] - sq_in_tip0
    out_z0 = z["squarePivot"] + geom["squareOutArm"] * math.sin(
        THETA_IN - math.radians(geom["squareAngleDeg"]))
    tracker_b = out_z0 - z["valve"]
    return {"sticker": max(sticker, 20.0),
            "trackerA": max(tracker_a, 20.0),
            "trackerB": max(tracker_b, 20.0)}


# ================================================================ 小几何
def _seg_intersection(p1, p2, p3, p4):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-12:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / den
    if 0.0 < t < 1.0 and 0.0 < u < 1.0:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def _collinear_overlap_midpoint(p1, p2, p3, p4):
    """两共线段有实质重叠时，返回重叠区中点，否则 None。"""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    if abs(cross(p1, p2, p3)) > 1e-6 or abs(cross(p1, p2, p4)) > 1e-6:
        return None
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return None
    t3 = ((p3[0] - p1[0]) * dx + (p3[1] - p1[1]) * dy) / L2
    t4 = ((p4[0] - p1[0]) * dx + (p4[1] - p1[1]) * dy) / L2
    lo, hi = max(0.0, min(t3, t4)), min(1.0, max(t3, t4))
    if lo < hi - 1e-9:
        t = (lo + hi) / 2
        return (p1[0] + t * dx, p1[1] + t * dy)
    return None


def _pt_seg_dist(p, a, b):
    px, py = p
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - a[0], py - a[1])
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def _seg_seg_dist(p1, p2, p3, p4):
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2 = cross(p3, p4, p1), cross(p3, p4, p2)
    d3, d4 = cross(p1, p2, p3), cross(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    if _collinear_overlap_midpoint(p1, p2, p3, p4) is not None:
        return 0.0
    return min(_pt_seg_dist(p3, p1, p2), _pt_seg_dist(p4, p1, p2),
               _pt_seg_dist(p1, p3, p4), _pt_seg_dist(p2, p3, p4))


# ================================================================ 单键
def _valve_response(u, KB, f0, ks):
    """拉索端有效位移 u → (阀开 v, 阀阻力 fv)。先消预紧再开启。"""
    pre = f0 / KB
    if u <= 0:
        return 0.0, 0.0
    if u <= pre:
        return 0.0, u * KB
    v = (u - pre) / (1.0 + ks / KB)
    return v, f0 + ks * v


def solve_key(geom, gl, press):
    ph = gl["physics"]
    z = gl["z"]
    kh = geom["keyHole"]
    hin, hout = geom["rollerInHorn"], geom["rollerOutHorn"]
    a2, b2 = geom["squareInArm"], geom["squareOutArm"]
    beta = math.radians(geom["rollerBetaIn"])
    beta_out = math.radians(geom["rollerBetaOut"])
    alpha = math.radians(geom["squareAngleDeg"])
    th_out0 = THETA_IN - alpha
    eta = ph["jointEff"]
    runs = vertical_runs(geom, z)
    EA = ph["trackerStiffness"] / 100.0
    KA = max(EA * runs["trackerA"], 0.5)
    KB = max(EA * runs["trackerB"], 0.5)
    f0 = (ph["windPressurePa"] * ph["palletAreaMm2"] * 1e-6
          + ph["valveSpringN"] + ph["palletMassN"])
    ks = SPRING_RATE
    gap = geom.get("valveGap", 1.0)

    links = geom.get("links", {})
    linked_s = links.get("sticker_to_hornIn") == "hornIn"
    linked_a = links.get("hornOut_to_squareIn") == "squareIn"
    linked_b = links.get("squareOut_to_pallet") == "pallet"

    # ---- 键杠
    s_lift = press * kh / LF_KEY
    if not linked_s:
        s_lift = 0.0
    # ---- 滚轴转角（含竖直死点顶死）
    sin_target = math.sin(beta) + s_lift / hin
    psi_max = math.pi / 2 - beta - 0.005
    dead = False
    if math.sin(beta + psi_max) <= sin_target:
        psi = psi_max
        dead = True
    else:
        psi = math.asin(max(-1, min(1, sin_target))) - beta
        psi = max(psi, 0.0)
    ang_in = beta + psi
    ang_out = beta_out + psi
    d_out = hout * math.sin(ang_out)
    if not linked_a:
        d_out = 0.0

    # ---- 转角器（φ 二分，含弹性相容）
    def delta_in(phi):
        return a2 * (math.sin(THETA_IN) - math.sin(THETA_IN - phi))

    def delta_out(phi):
        return b2 * (math.sin(th_out0) - math.sin(th_out0 - phi))

    def valve_and_force(phi):
        u = delta_out(phi) - gap
        v, fv = _valve_response(u, KB, f0, ks)
        if not linked_b:
            v, fv = 0.0, 0.0
        ma = max(a2 * math.cos(THETA_IN - phi), 1e-6)
        mb = max(b2 * math.cos(th_out0 - phi), 1e-6)
        fa = fv * mb / ma / (eta ** 2)
        return v, fv, fa

    def residual(phi):
        _, _, fa = valve_and_force(phi)
        return d_out - delta_in(phi) - fa / KA

    hi = math.pi / 2 - 0.02
    if residual(0) < 0:
        phi = 0.0
    elif residual(hi) > 0:
        phi = hi
        dead = dead or True
    else:
        lo = 0.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if residual(mid) >= 0:
                lo = mid
            else:
                hi = mid
        phi = (lo + hi) / 2

    v, fv, fa = valve_and_force(phi)

    # ---- 反推到键前端（压力角传力，死点处力放大并封顶标注）
    F_CAP = 40.0
    cin = max(hin * math.cos(ang_in), 0.05)
    cout = max(hout * math.cos(ang_out), 1e-6)
    f_sticker = fa * cout / cin / eta if linked_s else 0.0
    f_front = ((f_sticker + ph["keyReturnSpringN"]) * kh / LF_KEY) / eta
    force_capped = f_front > F_CAP
    if force_capped:
        f_front = F_CAP

    gamma_roller = 90.0 - math.degrees(ang_in)
    gamma_sq_out = abs(90.0 - abs(math.degrees(th_out0 - phi)))
    gamma_sq_in = abs(90.0 - abs(math.degrees(THETA_IN - phi)))

    zp = z["squarePivot"]
    nodes_z = {
        "keyFront": z["keyPivot"] - press,
        "keyPivot": z["keyPivot"],
        "keyRear": z["keyPivot"] + s_lift,
        "stickerFoot": z["keyPivot"] + (s_lift if linked_s else 0),
        "rollerAxisIn": z["roller"], "rollerAxisOut": z["roller"],
        "hornInTip": z["roller"] + hin * math.sin(ang_in),
        "hornOutTip": z["roller"] - hout * math.sin(ang_out),
        "square": z["squarePivot"],
        "squareInTip": zp + a2 * math.sin(THETA_IN - phi),
        "squareOutTip": zp + b2 * math.sin(th_out0 - phi),
        "pallet": z["valve"] - v,
    }
    stages = {
        "keyLift": s_lift,
        "rollerAngleDeg": math.degrees(psi),
        "rollerDrop": hout * math.sin(ang_out) if linked_a else 0,
        "squareAngleDeg": math.degrees(phi),
        "valveOpen": v,
        "fValve": fv, "fTrackerA": fa, "fSticker": f_sticker,
        "fFront": f_front,
        "gammaRoller": gamma_roller,
        "gammaSqIn": gamma_sq_in, "gammaSqOut": gamma_sq_out,
        "elastA": fa / KA, "elastB": fv / KB,
    }
    return {"phi": phi, "psi": psi, "v": v, "fFront": f_front,
            "dead": dead, "stages": stages, "nodesZ": nodes_z}


def sweep_key(geom, gl, steps=None):
    steps = steps or gl["physics"]["steps"]
    depth = gl["keyDepth"]
    return [solve_key(geom, gl, k / (steps - 1) * depth)
            for k in range(steps)]


def key_metrics(geom, gl):
    depth = gl["keyDepth"]
    frames = sweep_key(geom, gl)
    full = frames[-1]
    open_press = depth
    prev_v = 0.0
    for i, fr in enumerate(frames):
        if fr["v"] > 0.05:
            if i == 0:
                open_press = 0.0
            else:
                t0, t1 = (i - 1) / (len(frames) - 1), i / (len(frames) - 1)
                frac = (0.05 - prev_v) / max(fr["v"] - prev_v, 1e-9)
                open_press = depth * (t0 + frac * (t1 - t0))
            break
        prev_v = fr["v"]
    f_max = max(fr["fFront"] for fr in frames)
    dead_at = next((i / (len(frames) - 1) * depth
                    for i, fr in enumerate(frames) if fr["dead"]), None)
    return {"valveOpen": full["v"], "fFrontFull": full["fFront"],
            "fFrontMax": f_max, "lostMotion": open_press,
            "keyDepth": depth, "stages": full["stages"],
            "frames": frames, "deadAt": dead_at}


# ================================================================ 违规
def _slant(pa, pb, z_run):
    return 100.0 * math.hypot(pa[0] - pb[0], pa[1] - pb[1]) / max(z_run, 1.0)


def check_violations(model, metrics=None):
    gl = model["globals"]
    lim = gl["limits"]
    z = gl["z"]
    keys = model["keys"]
    pts = [plan_points(k["geometry"]) for k in keys]
    n = len(keys)
    viol = []

    # ---- 单键
    for i, k in enumerate(keys):
        g = k["geometry"]
        p = pts[i]
        runs = vertical_runs(g, z)
        m = metrics[i] if metrics else key_metrics(g, gl)
        st = m["stages"]
        for nm, pa, pb, L in (
                ("立木", p["stickerFoot"], p["hornInTip"], runs["sticker"]),
                ("上行连杆", p["hornOutTip"], p["squareInTip"], runs["trackerA"]),
                ("阀拉索", p["squareOutTip"], p["pallet"], runs["trackerB"])):
            val = _slant(pa, pb, L)
            if val > lim["slantLimit"]:
                viol.append({
                    "code": "SLANT", "keys": [i], "part": nm,
                    "value": round(val, 1), "limit": lim["slantLimit"],
                    "msg": f"键{i+1} {nm}侧向偏折 {val:.1f}% > {lim['slantLimit']:.0f}%",
                    "severity": "warn"})
        if m["valveOpen"] + 1e-6 < gl["physics"]["valveOpenTarget"]:
            viol.append({
                "code": "TRAVEL", "keys": [i], "part": "阀板",
                "value": round(m["valveOpen"], 2),
                "limit": gl["physics"]["valveOpenTarget"],
                "msg": f"键{i+1} 阀板开启 {m['valveOpen']:.2f}mm 不足 "
                       f"{gl['physics']['valveOpenTarget']:.0f}mm",
                "severity": "error"})
        if m["fFrontMax"] > gl["physics"]["effKeyFrontMax"] + 1e-9:
            viol.append({
                "code": "FORCE", "keys": [i], "part": "键前端",
                "value": round(m["fFrontMax"], 2),
                "limit": gl["physics"]["effKeyFrontMax"],
                "msg": f"键{i+1} 最大触键力 {m['fFrontMax']:.2f}N 超限 "
                       f"{gl['physics']['effKeyFrontMax']:.0f}N",
                "severity": "error"})
        if m["deadAt"] is not None:
            viol.append({
                "code": "DEADPOINT", "keys": [i],
                "part": "滚轴/转角器", "value": round(m["deadAt"], 2),
                "limit": lim["deadAngleDeg"],
                "msg": f"键{i+1} 在行程 {m['deadAt']:.1f}mm 处进入死点（压力角 "
                       f"{st['gammaRoller']:.1f}°）", "severity": "error"})
        cab = gl["cabinet"]
        for nm_, q in p.items():
            if not (cab["xMin"] - 1e-6 <= q[0] <= cab["xMax"] + 1e-6
                    and cab["yMin"] - 1e-6 <= q[1] <= cab["yMax"] + 1e-6):
                viol.append({
                    "code": "BOUNDS", "keys": [i], "part": nm_,
                    "value": [round(q[0], 1), round(q[1], 1)],
                    "msg": f"键{i+1} {nm_} 越出柜体", "severity": "error"})

    # ---- 交叉连杆（标出擦碰点，含共线对穿）
    for i in range(n):
        a1, a2 = pts[i]["hornOutTip"], pts[i]["squareInTip"]
        for j in range(i + 1, n):
            b1, b2 = pts[j]["hornOutTip"], pts[j]["squareInTip"]
            inter = _seg_intersection(a1, a2, b1, b2)
            if inter is None:
                q = _collinear_overlap_midpoint(a1, a2, b1, b2)
                inter = q if q is not None else None
            if inter:
                viol.append({
                    "code": "CROSS", "keys": [i, j], "part": "上行连杆",
                    "at": [round(inter[0], 1), round(inter[1], 1)],
                    "msg": f"键{i+1} 与键{j+1} 上行连杆交叉擦碰 @ "
                           f"({inter[0]:.0f},{inter[1]:.0f})",
                    "severity": "error"})

    # ---- 实体净距
    solids = []
    for i, (k, p) in enumerate(zip(keys, pts)):
        g = k["geometry"]
        solids += [
            (i, "立木", "seg", (p["stickerFoot"], p["hornInTip"])),
            (i, "滚轴", "seg", (p["rollerAxisIn"], p["rollerAxisOut"])),
            (i, "输入角", "seg", (p["rollerAxisIn"], p["hornInTip"])),
            (i, "输出角", "seg", (p["rollerAxisOut"], p["hornOutTip"])),
            (i, "上行连杆", "seg", (p["hornOutTip"], p["squareInTip"])),
            (i, "阀拉索", "seg", (p["squareOutTip"], p["pallet"])),
            (i, "转角器", "circle", (p["square"], SQUARE_R)),
            (i, "阀板", "rect", (g["palletX"], g["palletY"],
                                 PALLET_W, PALLET_D)),
        ]
    joined = {
        frozenset(("立木", "输入角")), frozenset(("输入角", "滚轴")),
        frozenset(("滚轴", "输出角")), frozenset(("输出角", "上行连杆")),
        frozenset(("上行连杆", "转角器")), frozenset(("转角器", "阀拉索")),
        frozenset(("阀拉索", "阀板")),
    }

    def pair_dist(s1, s2):
        t1, d1, t2, d2 = s1, s2
        if t1 == "seg" and t2 == "seg":
            return _seg_seg_dist(d1[0], d1[1], d2[0], d2[1])
        if t1 == "circle" and t2 == "circle":
            return math.hypot(d1[0][0] - d2[0][0],
                              d1[0][1] - d2[0][1]) - d1[1] - d2[1]
        if t1 == "rect" and t2 == "rect":
            dx = abs(d1[0] - d2[0]) - (d1[2] + d2[2]) / 2
            dy = abs(d1[1] - d2[1]) - (d1[3] + d2[3]) / 2
            return min(dx, dy) if dx < 0 and dy < 0 else max(dx, dy)

        def circle_seg(c, r, a, b):
            return _pt_seg_dist(c, a, b) - r

        def circle_rect(c, r, rc):
            rx, ry, rw, rd = rc
            qx = max(rx - rw / 2, min(c[0], rx + rw / 2))
            qy = max(ry - rd / 2, min(c[1], ry + rd / 2))
            return math.hypot(c[0] - qx, c[1] - qy) - r

        def rect_seg(rc, a, b):
            rx, ry, rw, rd = rc
            cs = [(rx - rw / 2, ry - rd / 2), (rx + rw / 2, ry - rd / 2),
                  (rx + rw / 2, ry + rd / 2), (rx - rw / 2, ry + rd / 2)]
            d = min(_seg_seg_dist(a, b, cs[k], cs[(k + 1) % 4])
                    for k in range(4))
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            return 0.0 if rx - rw / 2 <= mx <= rx + rw / 2 and \
                ry - rd / 2 <= my <= ry + rd / 2 else d

        if t1 == "circle" and t2 == "seg":
            return circle_seg(d1[0], d1[1], d2[0], d2[1])
        if t1 == "seg" and t2 == "circle":
            return circle_seg(d2[0], d2[1], d1[0], d1[1])
        if t1 == "circle" and t2 == "rect":
            return circle_rect(d1[0], d1[1], d2)
        if t1 == "rect" and t2 == "circle":
            return circle_rect(d2[0], d2[1], d1)
        if t1 == "rect" and t2 == "seg":
            return rect_seg(d1, d2[0], d2[1])
        return rect_seg(d2, d1[0], d1[1])

    clearance = lim["clearance"]
    seen = set()
    for u in range(len(solids)):
        for w in range(u + 1, len(solids)):
            i, ni, ti, di = solids[u]
            j, nj, tj, dj = solids[w]
            if i == j or frozenset((ni, nj)) in joined:
                continue
            try:
                d = pair_dist((ti, di), (tj, dj))
            except Exception:
                continue
            if d < clearance and (i, ni, j, nj) not in seen:
                seen.add((i, ni, j, nj))
                viol.append({
                    "code": "COLLIDE", "keys": [i, j],
                    "part": f"{ni}~{nj}", "value": round(max(d, 0), 1),
                    "limit": clearance,
                    "msg": f"键{i+1}{ni} 与键{j+1}{nj} 净距 "
                           f"{max(d, 0):.1f}mm < {clearance:.0f}mm",
                    "severity": "error" if d < 0 else "warn"})
    return viol


# ================================================================ 整机分析
def analyze(model, selected=None):
    gl = model["globals"]
    if selected is None:
        selected = 0
    per_key, points = [], []
    for k in model["keys"]:
        m = key_metrics(k["geometry"], gl)
        per_key.append(m)
        points.append(plan_points(k["geometry"]))
    viols = check_violations(model, per_key)
    forces = [m["fFrontMax"] for m in per_key]
    feel_adj = [round(abs(forces[i + 1] - forces[i]), 3)
                for i in range(len(forces) - 1)]
    summary = {
        "violationCount": len(viols),
        "errorCount": sum(1 for v in viols if v["severity"] == "error"),
        "maxForce": round(max(forces), 3),
        "feelMaxAdj": max(feel_adj) if feel_adj else 0,
        "feelSpread": round(max(forces) - min(forces), 3),
        "minValveOpen": round(min(m["valveOpen"] for m in per_key), 3),
    }

    frames_out = []
    for i, m in enumerate(per_key):
        row = []
        for fr in m["frames"]:
            item = {"z": fr["nodesZ"], "f": round(fr["fFront"], 3),
                    "v": round(fr["v"], 3)}
            if i == selected:
                item["s"] = {k: round(v, 4)
                             for k, v in fr["stages"].items()}
            row.append(item)
        frames_out.append(row)

    key_out = []
    for i, (k, m) in enumerate(zip(model["keys"], per_key)):
        key_out.append({
            "id": i, "name": k["name"], "locked": k["locked"],
            "metrics": {
                "valveOpen": round(m["valveOpen"], 3),
                "fFrontFull": round(m["fFrontFull"], 3),
                "fFrontMax": round(m["fFrontMax"], 3),
                "lostMotion": round(m["lostMotion"], 3),
                "keyDepth": m["keyDepth"],
                "deadAt": (round(m["deadAt"], 2)
                           if m["deadAt"] is not None else None)},
            "stages": {kk: round(vv, 4)
                       for kk, vv in m["stages"].items()},
            "points": {kk: [round(x, 2), round(y, 2)]
                       for kk, (x, y) in points[i].items()}})
    return {"summary": summary, "violations": viols, "keys": key_out,
            "frames": frames_out, "selected": selected,
            "feelAdj": feel_adj, "z": gl["z"]}
