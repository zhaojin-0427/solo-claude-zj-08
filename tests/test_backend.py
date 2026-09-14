"""后端回归测试：python -m tests.test_backend（或直接运行）。"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from organlab import physics, search  # noqa: E402
from organlab.defaults import build_default_model  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("  " + detail if detail else ""))
    if not cond:
        fails.append(name)


def main():
    m = build_default_model()
    a = physics.analyze(m, selected=1)

    # 种子缺陷齐全
    codes = {}
    for v in a["violations"]:
        codes[v["code"]] = codes.get(v["code"], 0) + 1
    check("种子：存在死点", any(v["code"] == "DEADPOINT" for v in a["violations"]))
    check("种子：存在交叉连杆", codes.get("CROSS", 0) >= 1, str(codes))
    check("种子：存在侧向偏折", codes.get("SLANT", 0) >= 2)
    check("种子：存在行程不足键", any(
        k["metrics"]["valveOpen"] < m["globals"]["physics"]["valveOpenTarget"]
        for k in a["keys"]))
    check("正常键阀开达标",
          a["keys"][0]["metrics"]["valveOpen"] >= 5.0)
    check("正常键力 5~11N",
          5 < a["keys"][0]["metrics"]["fFrontMax"] <= 11)
    check("空程 > 0", a["keys"][0]["metrics"]["lostMotion"] > 2.0)

    # 力单调 & 满程最大
    fr = a["keys"][0]
    fs = [f["f"] for f in a["frames"][0]]
    vs = [f["v"] for f in a["frames"][0]]
    check("触键力单调不减", all(fs[i + 1] >= fs[i] - 1e-9 for i in range(len(fs) - 1)))
    check("阀开单调不减", all(vs[i + 1] >= vs[i] - 1e-9 for i in range(len(vs) - 1)))

    # 播放：t=0 无位移
    r0 = physics.solve_key(m["keys"][0]["geometry"], m["globals"], 0)
    check("t=0 阀开为0", abs(r0["v"]) < 1e-9)

    # 物理参数敏感性
    m1 = build_default_model()
    m1["globals"]["physics"]["windPressurePa"] = 1200
    f_hi = physics.analyze(m1)["keys"][0]["metrics"]["fFrontMax"]
    f_lo = a["keys"][0]["metrics"]["fFrontMax"]
    check("风压↑则力↑", f_hi > f_hi * 0.9 and f_hi > f_lo, f"{f_lo:.2f}->{f_hi:.2f}")

    m2 = build_default_model()
    m2["globals"]["physics"]["trackerStiffness"] = 0.8
    v_soft = physics.analyze(m2)["keys"][0]["metrics"]["valveOpen"]
    check("杆软则阀开小", v_soft < 4.0, f"{v_soft:.2f}")

    # 断链 → 无输出
    m3 = build_default_model()
    m3["keys"][0]["geometry"]["links"]["squareOut_to_pallet"] = ""
    check("断阀拉索阀开为0",
          physics.analyze(m3)["keys"][0]["metrics"]["valveOpen"] == 0)

    # 搜索：第一名零违规；锁定键不被改
    res = search.search(build_default_model(), budget=400)
    top = res["results"][0]
    check("搜索存在零违规方案", top["score"]["violations"] == 0,
          json.dumps(top["score"], ensure_ascii=False))
    check("排序违规数非降", all(
        res["results"][i]["score"]["violations"]
        <= res["results"][i + 1]["score"]["violations"]
        for i in range(len(res["results"]) - 1)))

    ml = build_default_model()
    ml["keys"][2]["locked"] = True
    res2 = search.search(ml, budget=300)
    locked_fields = ("keyHole", "rollerInHorn", "rollerOutHorn",
                     "squareInArm", "squareOutArm", "squareAngleDeg",
                     "rollerBetaIn")
    # 采纳后 K3 几何应与基线一致（锁定）
    adopted = search.adopt(ml, res2["results"][0]["values"])
    g0 = ml["keys"][2]["geometry"]
    g1 = adopted["keys"][2]["geometry"]
    check("锁定键几何不被改",
          all(g0[f] == g1[f] for f in locked_fields)
          and g0["squareX"] == g1["squareX"])

    # 排序按题目顺序（违规数优先于改孔量）
    s_bad = {"violations": 1, "errors": 0, "maxForce": 9, "feel": 1, "cost": 1}
    s_good = {"violations": 0, "errors": 0, "maxForce": 10, "feel": 3, "cost": 99}
    check("排序：违规数优先", search._better(s_good, s_bad))

    print()
    if fails:
        print(f"{len(fails)} 项失败：{fails}")
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
