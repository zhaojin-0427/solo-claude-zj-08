"""管风琴机械传动放样台 —— 默认数据 / 模型种子。

坐标系约定
----------
* X 轴：沿键盘方向（白键宽 23 mm，键距 24 mm）。
* Y 轴：俯视进深，键盘在前（y 小），风箱在后（y 大）。
* Z 轴：竖直向上（侧视）。

传动链（每键一套）：
  键杠(key lever) → 立木(sticker，竖直) → 滚轴输入角 → 滚轴轴体
  → 滚轴输出角 → 上行木连杆(tracker A) → 转角器输入臂(squareIn)
  → 转角器折角杆 → 输出臂(squareOut) → 阀拉索(tracker B，竖直)
  → 阀板(pallet)。

立木与阀拉索均为竖直杆：俯视面上两端点默认重合对齐，
一旦拖动支点使其错开即产生“侧向偏折”。
"""
import copy
import math

# ---------------------------------------------------------------- 全局参数
GLOBAL_DEFAULTS = {
    "cabinet": {"xMin": -10, "xMax": 202, "yMin": 100, "yMax": 380},
    "keyCount": 8,
    "keySpacing": 24.0,
    "keyWidth": 23.0,
    "keyDepth": 10.0,             # 全按键程（键前端，mm）
    "z": {
        "keyPivot": 720.0,        # 键杠轴高
        "roller": 560.0,         # 滚轴轴高
        "squarePivot": 260.0,    # 转角器轴高
        "valve": 150.0,          # 阀板高度
    },
    "physics": {
        "windPressurePa": 700.0,
        "palletAreaMm2": 3200.0,
        "palletMassN": 0.6,
        "valveSpringN": 2.2,       # 阀板回位弹簧预紧（N）
        "keyReturnSpringN": 0.9,   # 键尾回位簧（N）
        "trackerStiffness": 3.5,   # 连杆轴向刚度（N/mm 伸长 / 100mm 杆长）
        "jointEff": 0.93,          # 每铰点效率
        "effKeyFrontMax": 11.0,    # 触键力上限（N）
        "valveOpenTarget": 5.0,    # 阀板目标开启量（mm）
        "steps": 41,
    },
    "limits": {
        "clearance": 8.0,          # 构件最小净距（mm）
        "slantLimit": 6.0,         # 俯视偏折（水平偏移/杆长）%
        "deadAngleDeg": 8.0,       # 压力角死点带（臂与竖直夹角 < 此值）
        "keyFeelMax": 2.0,         # 相邻键最大手感差（N）
    },
}

# 可选孔位 / 臂长档位（mm）
KEY_HOLES = [28, 32, 36, 40]
HORN_IN_HOLES = [26, 30, 34, 38, 42]
HORN_OUT_HOLES = [30, 34, 38, 42]
SQUARE_IN_HOLES = [40, 46, 52, 58, 64]
SQUARE_OUT_HOLES = [34, 38, 40, 45, 50]
SQUARE_ANGLES = [60.0, 66.0, 72.0]
# 滚轴输入角安装仰角（°，0=水平）。角度过大，剩余行程不足并在 90° 处顶死。
ROLLER_BETA = [0.0, 20.0, 40.0, 60.0, 68.0]
ROLLER_Y_RANGE = [236, 268]
LF_KEY = 40.0                   # 键前端到轴的力臂
KEY_REAR_EXTRA = 6.0            # 立木孔之后的键尾余量
SQ_ARM_PLAN_MM = 22.0           # 转角器输出臂俯视投影


def _square_x(i):
    """第 i 键所服务阀列的 x（= 转角器/阀板 x）。

    种子缺陷：K3↔K4 交换阀列 —— 两根上行木连杆在俯视面交叉擦碰，
    搜索恢复同位（改孔量计入排序）即可消除。
    """
    table = {2: 3 * 24 + 12, 3: 2 * 24 + 12}
    return table.get(i, i * 24 + 12)


def build_default_model():
    g = copy.deepcopy(GLOBAL_DEFAULTS)
    n = g["keyCount"]
    sp = g["keySpacing"]

    # 档位索引（故意埋入的缺陷见行内注释）
    key_hole_idx = [2, 2, 2, 2, 2, 2, 2, 2]
    horn_in_idx = [3, 3, 3, 3, 3, 3, 3, 3]
    horn_out_idx = [3, 3, 3, 3, 3, 3, 3, 3]
    sq_in_idx = [2, 2, 2, 2, 2, 2, 2, 2]
    sq_out_idx = [1, 1, 1, 1, 0, 1, 1, 1]   # 键5输出臂34最短 → 行程不足
    beta_idx = [0, 4, 0, 0, 0, 0, 0, 0]     # 键2输入角安装 68° → 竖直死点

    keys = []
    for i in range(n):
        xc = i * sp + 12
        kh = KEY_HOLES[key_hole_idx[i]]
        hin = HORN_IN_HOLES[horn_in_idx[i]]
        hout = HORN_OUT_HOLES[horn_out_idx[i]]
        ry = 250.0

        # 滚轴轴体不做横向移位（xIn=xOut=xc）；转位由斜 tracker A 完成。
        # 默认竖直对齐：立木对齐输入角尖；tracker A 对齐输入臂尖；
        # 阀拉索对齐输出臂尖。
        a_in = SQUARE_IN_HOLES[sq_in_idx[i]]
        b_out = SQUARE_OUT_HOLES[sq_out_idx[i]]
        alpha0 = math.radians(SQUARE_ANGLES[0])
        pivot_y = ry - hin * math.cos(math.radians(ROLLER_BETA[beta_idx[i]])) - kh
        square_y = round(ry + hout + a_in * math.cos(math.radians(45.0)), 2)
        pallet_y = round(square_y + b_out * math.cos(
            abs(math.radians(45.0) - alpha0)), 2)
        x_valve = _square_x(i)

        keys.append({
            "id": i,
            "name": f"K{i + 1}",
            "locked": False,
            "geometry": {
                # 键杠（俯视沿 y）
                "x": xc,
                "keyPivotY": round(pivot_y, 2),
                "keyHole": kh,
                # 立木（竖直杆，下端键杠孔，上端输入角尖）
                "stickerX": xc,
                # 滚轴板
                "rollerY": ry,
                "rollerXIn": xc,
                "rollerXOut": xc,
                "rollerInHorn": hin,
                "rollerOutHorn": hout,
                "rollerBetaIn": ROLLER_BETA[beta_idx[i]],
                "rollerBetaOut": 0.0,
                # 转角器（位于阀列）
                "squareX": x_valve,
                "squareY": square_y,
                "squareInArm": SQUARE_IN_HOLES[sq_in_idx[i]],
                "squareOutArm": SQUARE_OUT_HOLES[sq_out_idx[i]],
                "squareAngleDeg": SQUARE_ANGLES[0],
                # 阀板 / 拉索（阀列锁定在标准键距上；y 取输出臂投影端）
                "palletX": x_valve,
                "palletY": pallet_y,
                "valveGap": 1.0,
                # 连接关系（断链时传不动）
                "links": {
                    "sticker_to_hornIn": "hornIn",
                    "hornOut_to_squareIn": "squareIn",
                    "squareOut_to_pallet": "pallet",
                },
            },
        })

    return {
        "name": "窄柜样板工程（8 键）",
        "globals": g,
        "fixed": {"rollerBoard": False, "windchest": True, "keyFrame": True},
        "keys": keys,
        "catalog": {
            "keyHole": KEY_HOLES,
            "rollerInHorn": HORN_IN_HOLES,
            "rollerOutHorn": HORN_OUT_HOLES,
            "squareInArm": SQUARE_IN_HOLES,
            "squareOutArm": SQUARE_OUT_HOLES,
            "squareAngleDeg": SQUARE_ANGLES,
            "rollerBetaIn": ROLLER_BETA,
            "rollerY": list(range(ROLLER_Y_RANGE[0], ROLLER_Y_RANGE[1] + 1, 2)),
            # 转角器可服务的阀列（以键距为档，0=本位，改列计入改孔量）
            "squareXPitch": [-2, -1, 0, 1, 2],
        },
    }
