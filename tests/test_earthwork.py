"""土方调配核算测试：手算体积、交点拆分、流量守恒、宽度线性。"""

from __future__ import annotations

import itertools

import pytest

from app.planner import (
    PlanError,
    earthwork_accounting,
    plan_trail,
    validate_width,
)

CM2 = 100.0 ** 2  # 1 m³ = 10000 cm²×1m 段长


def test_validate_width():
    assert validate_width(1) == 1.0
    assert validate_width(2.5) == 2.5
    assert validate_width(0.5) == 0.5
    assert validate_width(10.0) == 10.0
    for bad in (0, 0.49, 10.01, -0.5, 2.345, "2", True, False, None, float("nan")):
        with pytest.raises(PlanError):
            validate_width(bad)


def test_trapezoid_cut_only():
    # 段两端 d0=2cm, d1=4cm，宽 1m：挖方面积 = (2+4)/2 = 3 cm²
    ew = earthwork_accounting([0, 0], [2, 4], 1.0)
    seg = ew["segments"][0]
    assert seg["cut"] == pytest.approx(3.0 / CM2)
    assert seg["fill"] == 0.0
    assert seg["net"] == pytest.approx(3.0 / CM2)
    assert ew["total_net"] == pytest.approx(3.0 / CM2)


def test_trapezoid_fill_only():
    # 面积 3 cm² × 宽 2m = 6 cm²·m → 0.0006 m³
    ew = earthwork_accounting([0, 0], [-2, -4], 2.0)
    seg = ew["segments"][0]
    assert seg["cut"] == 0.0
    assert seg["fill"] == pytest.approx(6.0 / CM2)
    assert seg["net"] == pytest.approx(-6.0 / CM2)


def test_horizontal_full_rectangle():
    # 方案整体比地面高 10cm：每段为矩形 10 cm²
    ew = earthwork_accounting([50, 50, 50], [60, 60, 60], 1.0)
    assert ew["total_cut"] == pytest.approx(20.0 / CM2)
    assert ew["total_fill"] == 0.0
    assert ew["total_net"] == pytest.approx(20.0 / CM2)
    assert ew["cumulative_net"] == [pytest.approx(10.0 / CM2),
                                    pytest.approx(20.0 / CM2)]


def test_crossing_midpoint_split():
    # d0=10cm, d1=-10cm：交点在段中点，两三角形面积各 2.5 cm²
    ew = earthwork_accounting([0, 0], [10, -10], 2.0)
    seg = ew["segments"][0]
    assert seg["cut"] == pytest.approx(2.5 * 2.0 / CM2)
    assert seg["fill"] == pytest.approx(2.5 * 2.0 / CM2)
    assert seg["net"] == 0.0


def test_crossing_offcenter_split():
    # d0=3cm, d1=-6cm：交点 x=3/9=1/3
    # 挖三角 0.5*3*(1/3)=0.5 cm²；填三角 0.5*6*(2/3)=2 cm²
    ew = earthwork_accounting([0, 0], [3, -6], 1.0)
    seg = ew["segments"][0]
    assert seg["cut"] == pytest.approx(0.5 / CM2)
    assert seg["fill"] == pytest.approx(2.0 / CM2)
    assert seg["net"] == pytest.approx(-1.5 / CM2)


def test_zero_difference_segments():
    ew = earthwork_accounting([100, 100, 100], [100, 100, 100], 3.0)
    assert ew["total_cut"] == 0.0
    assert ew["total_fill"] == 0.0
    assert ew["total_net"] == 0.0
    assert ew["haul_distance"] == 0.0
    assert all(f["flow"] == 0.0 for f in ew["flows"])


def test_net_deficit_flows_in_from_start():
    # 段1 自平衡；段2 净缺 0.002 m³（d0=d1=-10cm，宽 2m）
    ew = earthwork_accounting([100, 110, 120], [110, 100, 110], 2.0)
    assert ew["total_net"] == pytest.approx(-0.002)
    # 两条边都有 +0.002 朝终点运送（起点→段1中点 0.5m；段1→段2 中点 1m）
    assert ew["flows"][0]["flow"] == pytest.approx(0.002)
    assert ew["flows"][0]["distance"] == 0.5
    assert ew["flows"][1]["flow"] == pytest.approx(0.002)
    assert ew["flows"][1]["distance"] == 1.0
    assert ew["haul_distance"] == pytest.approx(0.002 * 0.5 + 0.002 * 1.0)


def test_net_surplus_flows_out_to_start():
    # 全线高 10cm、宽 2m、2 段：每段净余 0.002，共 0.004 经起点运出
    ew = earthwork_accounting([0, 0, 0], [10, 10, 10], 2.0)
    assert ew["total_net"] == pytest.approx(0.004)
    assert ew["flows"][0]["flow"] == pytest.approx(-0.004)
    assert ew["flows"][1]["flow"] == pytest.approx(-0.002)
    assert ew["haul_distance"] == pytest.approx(0.004 * 0.5 + 0.002 * 1.0)


def test_rebalance_between_midpoints():
    # 段1 净余、段2 净缺且总量平衡：起点边为 0，仅中点间调配
    # 段1：d0=0,d1=5 → 挖三角 2.5 cm²；
    # 段2：d0=5,d1=-10，交点 x=1/3：挖 0.5*5/3≈0.8333，
    #      填 0.5*10*2/3≈3.3333，净 −2.5 cm²，全线平衡。
    ew = earthwork_accounting([0, 0, 0], [0, 5, -10], 1.0)
    # 段1：0.5*(0+5)=2.5 挖；段2：d0=5,d1=-10，挖三角 0.5*5*(1/3)... x=5/15=1/3
    # 挖=0.5*5/3≈0.8333，填=0.5*10*2/3≈3.3333，净=-2.5；全线平衡
    assert ew["total_net"] == pytest.approx(0.0, abs=1e-12)
    assert ew["flows"][0]["flow"] == pytest.approx(0.0, abs=1e-12)  # 起点不进出
    assert ew["flows"][1]["flow"] == pytest.approx(2.5 / CM2)  # 余量朝终点
    assert ew["haul_distance"] == pytest.approx(2.5 / CM2 * 1.0)


@pytest.mark.parametrize("width", [1.0, 2.5, 3.75, 10.0])
def test_volume_linear_in_width(width):
    base = earthwork_accounting([100, 107, 114, 119, 124, 130],
                                [100, 108, 114, 121, 125, 130], 1.0)
    ew = earthwork_accounting([100, 107, 114, 119, 124, 130],
                              [100, 108, 114, 121, 125, 130], width)
    scale = width
    assert ew["total_cut"] == pytest.approx(base["total_cut"] * scale)
    assert ew["total_fill"] == pytest.approx(base["total_fill"] * scale)
    assert ew["total_net"] == pytest.approx(base["total_net"] * scale)
    assert ew["haul_distance"] == pytest.approx(base["haul_distance"] * scale)
    for a, b in zip(ew["segments"], base["segments"]):
        assert a["cut"] == pytest.approx(b["cut"] * scale)
        assert a["fill"] == pytest.approx(b["fill"] * scale)
    for a, b in zip(ew["flows"], base["flows"]):
        assert a["flow"] == pytest.approx(b["flow"] * scale)


def test_flow_and_cumulative_consistency():
    ground = [100, 107, 114, 119, 124, 130]
    plan = [100, 108, 114, 121, 125, 130]
    ew = earthwork_accounting(ground, plan, 2.0)

    # 段后累计 = 分段净量前缀和
    running = 0.0
    for seg, cum in zip(ew["segments"], ew["cumulative_net"]):
        running += seg["net"]
        assert cum == pytest.approx(running)
    assert ew["total_net"] == pytest.approx(running)
    assert ew["total_cut"] - ew["total_fill"] == pytest.approx(ew["total_net"])

    flows = ew["flows"]
    # 起点边 = −全线净量；中点边 = −全线净量 + 前 k 段累计
    assert flows[0]["flow"] == pytest.approx(-ew["total_net"])
    for k in range(1, len(flows)):
        assert flows[k]["flow"] == pytest.approx(
            -ew["total_net"] + ew["cumulative_net"][k - 1]
        )

    # 各中点守恒：边 i 流入 − 边 i+1 流出 + 本段净余 = 0
    for i, seg in enumerate(ew["segments"]):
        fin = flows[i]["flow"]
        fout = flows[i + 1]["flow"] if i + 1 < len(flows) else 0.0
        assert fin - fout + seg["net"] == pytest.approx(0.0)

    # 运量距离 = Σ|流量|×距离
    assert ew["haul_distance"] == pytest.approx(
        sum(abs(f["flow"]) * f["distance"] for f in flows)
    )
    # 最后一个中点之后（终点）无进出
    assert abs(flows[-1]["flow"]) == pytest.approx(abs(ew["segments"][-1]["net"]))


@pytest.mark.parametrize(
    "ground,plan",
    [
        ([0, 0, 0, 0], [0, 3, -2, 0]),
        ([5, 9, 3, 8], [6, 6, 6, 8]),
        (list(range(0, 12, 2)), [0, 2, 2, 4, 6, 6]),
    ],
)
def test_piecewise_integration_matches_numerical(ground, plan):
    # 用极细数值积分对拍分段挖填体积（宽 1.23m）
    width = 1.23
    ew = earthwork_accounting(ground, plan, width)
    n = 1_000_000
    cut_num = fill_num = 0.0
    for i in range(len(ground) - 1):
        d0 = plan[i] - ground[i]
        d1 = plan[i + 1] - ground[i + 1]
        sc = sf = 0.0
        for j in range(n):
            x = (j + 0.5) / n
            d = d0 + (d1 - d0) * x
            if d > 0:
                sc += d / n
            else:
                sf += -d / n
        cut_num += sc * width / 10000.0
        fill_num += sf * width / 10000.0
    assert ew["total_cut"] == pytest.approx(cut_num, rel=1e-5)
    assert ew["total_fill"] == pytest.approx(fill_num, rel=1e-5)


def test_plan_trail_attaches_earthwork():
    r = plan_trail([100, 107, 114, 119, 124, 130], 2.5)
    assert r["feasible"]
    ew = r["earthwork"]
    assert ew["width"] == 2.5
    assert ew["unit"] == "m3"
    assert ew["haul_unit"] == "m3·m"
    assert len(ew["segments"]) == len(r["segments"])


def test_plan_trail_without_width_has_null_earthwork():
    r = plan_trail([100, 107, 114, 119, 124, 130])
    assert r["feasible"]
    assert r["earthwork"] is None


def test_plan_trail_invalid_width_raises():
    with pytest.raises(PlanError):
        plan_trail([100, 107, 114], 0.1)
    with pytest.raises(PlanError):
        plan_trail([100, 107, 114], 2.999)


def test_plan_trail_infeasible_has_no_earthwork():
    r = plan_trail([0, 8, 16, 24, 32, 40], 2.0)
    assert not r["feasible"]
    assert "earthwork" not in r


def test_no_premature_rounding():
    # 非整齐数值（宽 1.01m）下，分段体积之和应与总量严格一致（未中途取整）
    r = plan_trail([3, 7, 11, 9, 5, 3, 0], 1.01)
    ew = r["earthwork"]
    assert sum(s["cut"] for s in ew["segments"]) == ew["total_cut"]
    assert sum(s["fill"] for s in ew["segments"]) == ew["total_fill"]
    assert sum(s["net"] for s in ew["segments"]) == ew["total_net"]
