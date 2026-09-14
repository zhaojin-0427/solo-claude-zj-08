"""带编号尺寸的正视 / 侧视装配图（纯字符串拼 SVG）。

正视（front elevation）：X-Z 平面，看键盘横向布置与各阀列高度；
侧视（side elevation）：Y-Z 平面（取选中键的传动链），
逐级画键杠、立木、滚轴角、连杆、转角器、阀板。
所有尺寸带 D1、D2 …… 编号，图下附编号尺寸表与计算参数表。
"""
import html
import math

from . import physics

FONT = "font-family:'Noto Sans CJK SC','Microsoft YaHei',sans-serif"


def _esc(s):
    return html.escape(str(s), quote=True)


def _dim(x1, y1, x2, y2, num, color="#0b5cab"):
    """带编号的尺寸标注（箭头线 + 编号气泡）。"""
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    return f"""
    <g stroke="{color}" stroke-width="0.9" fill="none">
      <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" marker-start="url(#arr)"
            marker-end="url(#arr)"/>
    </g>
    <g transform="translate({mx},{my})">
      <circle r="7.8" fill="white" stroke="{color}" stroke-width="1"/>
      <text y="3.2" text-anchor="middle" font-size="8.5" fill="{color}"
            style="{FONT}">D{num}</text>
    </g>"""


# ---------------------------------------------------------------- 正视图
def front_view(model, analysis):
    gl = model["globals"]
    z = gl["z"]
    keys = model["keys"]
    n = len(keys)
    sp = gl["keySpacing"]
    ml, mr, margin_top = 96, 96, 88
    sx = 2.6                       # x 比例
    zmin, zmax = 80, 780
    sh = 560.0
    sy = sh / (zmax - zmin)

    def X(xmm):
        return ml + xmm * sx

    def Z(zmm):
        return margin_top + (zmax - zmm) * sy

    width = ml + mr + (n * sp) * sx + 20
    height = margin_top + sh + 250
    p = [physics.plan_points(k["geometry"]) for k in keys]
    dims = []
    body = []

    cab_x0, cab_x1 = X(-10), X(n * sp + 4)
    # 柜体轮廓
    body.append(f'<rect x="{cab_x0}" y="{margin_top - 10}" '
                f'width="{cab_x1 - cab_x0}" height="{sh + 20}" '
                f'rx="4" fill="#f7f3ea" stroke="#8a7a55" stroke-width="1.4" '
                f'stroke-dasharray="6 4"/>')
    body.append(f'<text x="{cab_x0 + 6}" y="{margin_top + 2}" font-size="11" '
                f'fill="#8a7a55" style="{FONT}">柜体（俯视进深方向压缩）</text>')

    # 水平层线：键杠 / 滚轴 / 转角器 / 阀板
    for label, zz, col in (("键杠轴", z["keyPivot"], "#9a6a2f"),
                           ("滚轴轴", z["roller"], "#5b6f8a"),
                           ("转角器轴", z["squarePivot"], "#7a4b9a"),
                           ("阀板", z["valve"], "#2f7d4f")):
        y = Z(zz)
        body.append(f'<line x1="{cab_x0 + 6}" y1="{y}" x2="{cab_x1 - 6}" '
                    f'y2="{y}" stroke="{col}" stroke-width="0.6" stroke-dasharray="3 4" '
                    f'opacity="0.6"/>')
        body.append(f'<text x="{cab_x0 + 10}" y="{y - 3}" font-size="9" '
                    f'fill="{col}" style="{FONT}">{label} {zz:.0f}</text>')

    dims = []
    for i, k in enumerate(keys):
        g = k["geometry"]
        xc = g["x"]
        xv = g["palletX"]
        x = X(xc)
        m = analysis["keys"][i]["metrics"]
        # 键前端（小方块）
        body.append(f'<rect x="{x - 8}" y="{Z(z["keyPivot"]) - 3}" width="16" '
                    f'height="7" rx="1.5" fill="#d9c9a3" stroke="#7d6838"/>')
        body.append(f'<text x="{x}" y="{Z(z["keyPivot"]) - 8}" text-anchor="middle" '
                    f'font-size="9" fill="#5a4d2c" style="{FONT}">{k["name"]}</text>')
        # 立木
        body.append(f'<line x1="{x}" y1="{Z(z["keyPivot"])}" x2="{x}" '
                    f'y2="{Z(z["roller"])}" stroke="#8a5a2b" stroke-width="2.4"/>')
        # 滚轴（小三角）到 trackerA 上端（square 输入臂尖 z）
        zp_sq_in = z["squarePivot"] + g["squareInArm"] * math.sin(math.pi / 4)
        body.append(f'<polyline points="{x},{Z(z["roller"])} {x},{Z(z["roller"]) - 4} '
                    f'{X(xv)},{Z(zp_sq_in) + 2}" stroke="#4a5d78" stroke-width="1.8" '
                    f'fill="none"/>')
        # 转角器：轴 + 输入/输出臂（正视近似画在同 x）
        z_out_tip = z["squarePivot"] + g["squareOutArm"] * math.sin(
            math.pi / 4 - math.radians(g["squareAngleDeg"]))
        body.append(f'<circle cx="{X(xv)}" cy="{Z(z["squarePivot"])}" r="3.4" '
                    f'fill="#7a4b9a"/>')
        body.append(f'<line x1="{X(xv)}" y1="{Z(z["squarePivot"])}" x2="{X(xv)}" '
                    f'y2="{Z(zp_sq_in)}" stroke="#7a4b9a" stroke-width="1.6"/>')
        body.append(f'<line x1="{X(xv)}" y1="{Z(z["squarePivot"])}" x2="{X(xv)}" '
                    f'y2="{Z(z_out_tip)}" stroke="#7a4b9a" stroke-width="1.6"/>')
        # 阀拉索 + 阀板
        body.append(f'<line x1="{X(xv)}" y1="{Z(z_out_tip)}" x2="{X(xv)}" '
                    f'y2="{Z(z["valve"])}" stroke="#555" stroke-width="1.2"/>')
        body.append(f'<rect x="{X(xv) - 8}" y="{Z(z["valve"]) - 3}" width="16" '
                    f'height="8" rx="1.5" fill="#bcd6c5" stroke="#2f7d4f"/>')
        # 开启量文字
        col = "#2f7d4f" if m["valveOpen"] >= gl["physics"]["valveOpenTarget"] else "#c0392b"
        body.append(f'<text x="{X(xv) - 11}" y="{Z(z["valve"]) + 6}" font-size="8.5" '
                    f'fill="{col}" text-anchor="end" style="{FONT}">{m["valveOpen"]:.1f}mm</text>')

        # D1 键距（每个键距同编号，工程图惯例）—— 置于柜体上方
        if i < n - 1:
            dims.append(_dim(X(xc), margin_top - 22, X(xc + sp),
                             margin_top - 22, 1))

    # D2 键宽（第一只键上，置于 D1 上方）
    x0 = X(keys[0]["geometry"]["x"])
    kw = gl["keyWidth"]
    dims.append(_dim(x0 - kw / 2 * sx, margin_top - 40,
                     x0 + kw / 2 * sx, margin_top - 40, 2))
    # D3 总高 / D4-D6 分层高度（柜体左侧两列，延伸线伸入柜内 4mm）
    xtotal = cab_x0 - 52
    xlayer = cab_x0 - 26
    dims.append(_dim(xtotal, Z(z["keyPivot"]), xtotal,
                     Z(z["valve"]), 3))
    dims.append(_dim(xlayer, Z(z["keyPivot"]), xlayer,
                     Z(z["roller"]), 4))
    dims.append(_dim(xlayer, Z(z["roller"]), xlayer,
                     Z(z["squarePivot"]), 5))
    dims.append(_dim(xlayer, Z(z["squarePivot"]), xlayer,
                     Z(z["valve"]), 6))

    dim_table, _ = _dimension_table(dim_rows_front(model), 6, start_offset=0)
    param_table = _param_table(model, analysis)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"
     font-size="10" style="{FONT}">
  <defs><marker id="arr" markerWidth="8" markerHeight="8" refX="4" refY="4"
     orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#0b5cab"/></marker></defs>
  <rect width="100%" height="100%" fill="#fffdf6"/>
  <text x="16" y="22" font-size="15" font-weight="bold" fill="#333"
        style="{FONT}">正视装配图 — {_esc(model['name'])}</text>
  {''.join(body)}
  {''.join(str(d) for d in dims)}
  <g transform="translate(30,{margin_top + sh + 24})">{dim_table}
  </g>
  <g transform="translate(340,{margin_top + sh + 24})">{param_table}</g>
</svg>"""
    return svg


def dim_rows_front(model):
    gl = model["globals"]
    z = gl["z"]
    rows = [
        ("键距（中到中）", f"{gl['keySpacing']:.0f} mm"),
        ("键宽", f"{gl['keyWidth']:.0f} mm"),
        ("键轴—阀板总高", f"{z['keyPivot'] - z['valve']:.0f} mm"),
        ("键轴—滚轴", f"{z['keyPivot'] - z['roller']:.0f} mm"),
        ("滚轴—转角器轴", f"{z['roller'] - z['squarePivot']:.0f} mm"),
        ("转角器轴—阀板", f"{z['squarePivot'] - z['valve']:.0f} mm"),
    ]
    return rows


# ---------------------------------------------------------------- 侧视图
def side_view(model, analysis, key_idx=0):
    gl = model["globals"]
    z = gl["z"]
    g = model["keys"][key_idx]["geometry"]
    p = physics.plan_points(g)
    runs = physics.vertical_runs(g, z)
    ymin, ymax = 140, 380
    zmin, zmax = 80, 780
    ml, mt = 70, 40
    sx = 3.4
    sy = 620.0 / (zmax - zmin)

    def Y(mm):
        return ml + (mm - ymin) * sx

    def Z(mm):
        return mt + (zmax - mm) * sy

    width = ml * 2 + (ymax - ymin) * sx
    height = mt + 560 + 250
    body = []
    dnum = 1

    # 柜体
    body.append(f'<rect x="{Y(ymin)}" y="{Z(zmax - 30)}" width="{(ymax-ymin)*sx}" '
                f'height="{(zmax - 30 - (zmin + 20)) * sy + 10}" rx="4" '
                f'fill="#f7f3ea" stroke="#8a7a55" stroke-width="1.2" '
                f'stroke-dasharray="6 4"/>')

    # ---- 侧投影坐标（y 进深，z 高）。俯视 plan y 与侧投影共用进深轴，
    # 但滚轴角在侧视中按安装仰角绘制：tip_y=rollerY∓Lcosβ，tip_z 按 β。
    kf_y = p["keyFront"][1]
    piv_y = p["keyPivot"][1]
    foot_y = p["stickerFoot"][1]
    r_y = g["rollerY"]
    beta_in = math.radians(g["rollerBetaIn"])
    beta_out = math.radians(g["rollerBetaOut"])
    hin_y = r_y - g["rollerInHorn"] * math.cos(beta_in)
    hin_z = z["roller"] + g["rollerInHorn"] * math.sin(beta_in)
    hout_y = r_y + g["rollerOutHorn"] * math.cos(beta_out)
    hout_z = z["roller"] - g["rollerOutHorn"] * math.sin(beta_out)
    sq_piv_y, sq_piv_z = p["square"][1], z["squarePivot"]
    # tracker A 上端（输入臂尖）进深与输出角尖一致（连杆竖直）
    sq_in_y = hout_y
    sq_out_y = p["squareOutTip"][1]
    sq_in_z = z["squarePivot"] + g["squareInArm"] * math.sin(math.pi / 4)
    sq_out_z = z["squarePivot"] + g["squareOutArm"] * math.sin(
        math.pi / 4 - math.radians(g["squareAngleDeg"]))
    pal_y, pal_z = p["pallet"][1], z["valve"]

    def line(a_y, a_z, b_y, b_z, **kw):
        attrs = " ".join(f'{k}="{v}"' for k, v in kw.items())
        body.append(f'<line x1="{Y(a_y)}" y1="{Z(a_z)}" x2="{Y(b_y)}" '
                    f'y2="{Z(b_z)}" {attrs}/>')

    # 键杠：前端 → 轴 → 立木孔（键尾）
    line(kf_y, z["keyPivot"], piv_y, z["keyPivot"],
         stroke="#7d6838", **{"stroke-width": 4})
    line(piv_y, z["keyPivot"], foot_y, z["keyPivot"],
         stroke="#7d6838", **{"stroke-width": 4})
    body.append(f'<circle cx="{Y(piv_y)}" cy="{Z(z["keyPivot"])}" r="4" '
                f'fill="#333"/>')
    body.append(f'<text x="{Y(kf_y) - 4}" y="{Z(z["keyPivot"]) + 18}" '
                f'font-size="9" fill="#7d6838" text-anchor="end" '
                f'style="{FONT}">键前端</text>')

    # 立木（竖直，下端键杠孔，上端=输入角尖侧投影）
    line(foot_y, z["keyPivot"], hin_y, hin_z,
         stroke="#8a5a2b", **{"stroke-width": 3})
    # 滚轴轴体 + 两角（按安装仰角）
    body.append(f'<circle cx="{Y(r_y)}" cy="{Z(z["roller"])}" r="5" '
                f'fill="#4a5d78" stroke="#27384d" stroke-width="1.2"/>')
    line(r_y, z["roller"], hin_y, hin_z,
         stroke="#4a5d78", **{"stroke-width": 2.2})
    line(r_y, z["roller"], hout_y, hout_z,
         stroke="#4a5d78", **{"stroke-width": 2.2})
    # tracker A（竖直：输出角尖 → 输入臂尖，默认同 y）
    line(hout_y, hout_z, sq_in_y, sq_in_z,
         stroke="#355e3b", **{"stroke-width": 2.6})
    # 转角器折角杆
    body.append(f'<circle cx="{Y(sq_piv_y)}" cy="{Z(sq_piv_z)}" r="5" '
                f'fill="#7a4b9a" stroke="#4d2e63" stroke-width="1.2"/>')
    line(sq_in_y, sq_in_z, sq_piv_y, sq_piv_z,
         stroke="#7a4b9a", **{"stroke-width": 2.4})
    line(sq_piv_y, sq_piv_z, sq_out_y, sq_out_z,
         stroke="#7a4b9a", **{"stroke-width": 2.4})
    # 阀拉索 + 阀板 + 弹簧
    line(sq_out_y, sq_out_z, pal_y, pal_z,
         stroke="#444", **{"stroke-width": 1.8})
    body.append(f'<rect x="{Y(pal_y) - 12}" y="{Z(pal_z) - 4}" '
                f'width="24" height="9" rx="1.5" fill="#bcd6c5" '
                f'stroke="#2f7d4f" stroke-width="1.4"/>')
    body.append(f'<path d="M{Y(pal_y) + 14},{Z(pal_z)} q3,-6 6,0 t6,0 t6,0" '
                f'fill="none" stroke="#b07b2b" stroke-width="1.2"/>')

    # 标注文字
    labels = [
        ((foot_y + hin_y) / 2, (z["keyPivot"] + hin_z) / 2, "立木", "#8a5a2b"),
        (r_y + 6, z["roller"] - 24, "滚轴/角", "#4a5d78"),
        (hout_y + 4, (hout_z + sq_in_z) / 2, "上行木连杆", "#355e3b"),
        (sq_piv_y + 8, sq_piv_z + 22, "转角器", "#7a4b9a"),
        ((sq_out_y + pal_y) / 2, (sq_out_z + pal_z) / 2, "阀拉索", "#444"),
    ]
    for yy, zz, t, c in labels:
        body.append(f'<text x="{Y(yy)}" y="{Z(zz)}" font-size="9.5" fill="{c}" '
                    f'text-anchor="middle" style="{FONT};font-weight:bold">{t}</text>')

    dims = []
    rows = []

    def add_dim(name, value, x1, y1, x2, y2, color="#0b5cab", offx=0, offy=0):
        n = len(rows) + 1
        dims.append(_dim(x1 + offx, y1 + offy, x2 + offx, y2 + offy, n, color))
        rows.append((name, value))

    # D1-D4 水平进深尺寸（图上方）
    add_dim("键前端—键轴", f"{physics.LF_KEY:.0f} mm",
            Y(kf_y), Z(zmax - 24), Y(piv_y), Z(zmax - 24))
    add_dim("键轴—立木孔", f"{g['keyHole']:.0f} mm",
            Y(piv_y), Z(zmax - 24), Y(foot_y), Z(zmax - 24))
    add_dim("滚轴—输入臂尖（进深）",
            f"{abs(sq_in_y - r_y):.1f} mm",
            Y(r_y), Z(zmax - 24), Y(sq_in_y), Z(zmax - 24))
    add_dim("转角器轴—输出臂尖（进深）",
            f"{abs(pal_y - sq_piv_y):.1f} mm",
            Y(sq_piv_y), Z(zmax - 24), Y(pal_y), Z(zmax - 24))
    # D5-D7 连杆实长（平行引线，细灰蓝色，避免压住构件）
    add_dim("立木长", f"{runs['sticker']:.0f} mm",
            Y(foot_y) + 18, Z(z["keyPivot"]), Y(hin_y) + 18, Z(hin_z),
            color="#7a5c8c")
    add_dim("上行连杆长", f"{runs['trackerA']:.0f} mm",
            Y(hout_y) + 18, Z(hout_z), Y(sq_in_y) + 18, Z(sq_in_z),
            color="#7a5c8c")
    add_dim("阀拉索长", f"{runs['trackerB']:.0f} mm",
            Y(sq_out_y) + 20, Z(sq_out_z), Y(pal_y) + 20, Z(pal_z),
            color="#7a5c8c")
    # D8-D11 臂长（沿臂粉紫色引线）
    add_dim("滚轴输入角长", f"{g['rollerInHorn']:.0f} mm",
            Y(r_y), Z(z["roller"]), Y(hin_y), Z(hin_z),
            color="#a14b7d", offx=-15, offy=-4)
    add_dim("滚轴输出角长", f"{g['rollerOutHorn']:.0f} mm",
            Y(r_y), Z(z["roller"]), Y(hout_y), Z(hout_z),
            color="#a14b7d", offx=15, offy=4)
    add_dim("转角器输入臂", f"{g['squareInArm']:.0f} mm",
            Y(sq_in_y), Z(sq_in_z), Y(sq_piv_y), Z(sq_piv_z),
            color="#a14b7d", offx=-16, offy=6)
    add_dim("转角器输出臂", f"{g['squareOutArm']:.0f} mm",
            Y(sq_piv_y), Z(sq_piv_z), Y(sq_out_y), Z(sq_out_z),
            color="#a14b7d", offx=16, offy=6)

    dim_table, _ = _dimension_table(rows, len(rows) + 1, start_offset=0)
    param_table = _param_table(model, analysis, key_idx)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"
     font-size="10" style="{FONT}">
  <defs><marker id="arr" markerWidth="8" markerHeight="8" refX="4" refY="4"
     orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#0b5cab"/></marker></defs>
  <rect width="100%" height="100%" fill="#fffdf6"/>
  <text x="16" y="22" font-size="15" font-weight="bold" fill="#333"
        style="{FONT}">侧视装配图 — {_esc(model['keys'][key_idx]['name'])}
        （{_esc(model['name'])}）</text>
  {''.join(body)}
  {''.join(str(d) for d in dims)}
  <g transform="translate(30,{mt + 560 + 26})">{dim_table}</g>
  <g transform="translate(330,{mt + 560 + 26})">{param_table}</g>
</svg>"""
    return svg


# ---------------------------------------------------------------- 表格
def _dimension_table(rows, dnum, start_offset=0):
    """rows: [(名称, 值)]。返回 (svg, 下一编号)。"""
    line_h = 16
    out = [f'<rect x="0" y="-14" width="280" height="{len(rows)*line_h + 22}" '
           f'rx="4" fill="#f3f6fa" stroke="#9fb3c8"/>',
           f'<text x="8" y="0" font-size="11" font-weight="bold" fill="#234" '
           f'style="{FONT}">编号尺寸表</text>']
    for i, (name, val) in enumerate(rows):
        y = 18 + i * line_h
        out.append(
            f'<text x="8" y="{y}" font-size="9.5" fill="#0b5cab" '
            f'style="{FONT}">D{start_offset + i + 1}</text>'
            f'<text x="42" y="{y}" font-size="9.5" fill="#333" '            f'style="{FONT}">{_esc(name)}</text>'
            f'<text x="270" y="{y}" font-size="9.5" fill="#333" '
            f'text-anchor="end" style="{FONT}">{_esc(val)}</text>')
    return "".join(out), start_offset + len(rows)


def _param_table(model, analysis, key_idx=None):
    ph = model["globals"]["physics"]
    rows = [
        ("风压", f"{ph['windPressurePa']:.0f} Pa"),
        ("阀板面积", f"{ph['palletAreaMm2']:.0f} mm²"),
        ("阀回位簧预紧", f"{ph['valveSpringN']:.1f} N"),
        ("键回位簧", f"{ph['keyReturnSpringN']:.1f} N"),
        ("连杆刚度", f"{ph['trackerStiffness']:.1f} N/mm/100mm"),
        ("铰点效率", f"{ph['jointEff']:.2f}"),
        ("键程", f"{physics.key_metrics(model['keys'][key_idx or 0]['geometry'], model['globals'])['keyDepth']:.1f} mm"),
    ]
    if key_idx is not None:
        m = analysis["keys"][key_idx]["metrics"]
        rows += [
            ("阀板开启量", f"{m['valveOpen']:.2f} mm"),
            ("最大触键力", f"{m['fFrontMax']:.2f} N"),
            ("空程", f"{m['lostMotion']:.2f} mm"),
        ]
    else:
        rows += [
            ("最小阀开", f"{analysis['summary']['minValveOpen']:.2f} mm"),
            ("最大触键力", f"{analysis['summary']['maxForce']:.2f} N"),
            ("最大手感差", f"{analysis['summary']['feelMaxAdj']:.2f} N"),
        ]
    line_h = 16
    out = [f'<rect x="0" y="-14" width="280" height="{len(rows)*line_h + 22}" '
           f'rx="4" fill="#f6f3fa" stroke="#b3a5c8"/>',
           f'<text x="8" y="0" font-size="11" font-weight="bold" fill="#432" '
           f'style="{FONT}">计算参数 / 结果</text>']
    for i, (name, val) in enumerate(rows):
        y = 18 + i * line_h
        out.append(
            f'<text x="8" y="{y}" font-size="9.5" fill="#333" '
            f'style="{FONT}">{_esc(name)}</text>'
            f'<text x="270" y="{y}" font-size="9.5" fill="#333" '
            f'text-anchor="end" style="{FONT}">{_esc(val)}</text>')
    return "".join(out)
