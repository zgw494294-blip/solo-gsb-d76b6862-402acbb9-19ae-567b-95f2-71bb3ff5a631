"""步道坡线规划台 —— 规划算法。

规则
----
1. 测点等间距 1 m，共 n 个测点（3 <= n <= 16）。
2. 地面标高 ground[i] 为 0~200 的整数厘米；方案标高 plan[i] 同为 0~200 的
   整数厘米。
3. 首、尾方案标高必须分别等于首、尾地面标高。
4. 相邻方案点高差的绝对值不超过 8 cm。
5. 任意连续 5 段中至少有 1 段水平段（相邻两点方案标高相等的段）。
6. 目标：在所有可行方案中最小化总调整量
       sum_i |plan[i] - ground[i]|；
   总调整量相同则取方案标高序列字典序最小者。

算法
----
带“最近 4 段是否水平”位掩码状态的动态规划。
向后 DP：dp[pos][mask][h] 表示第 pos 点方案标高取 h、其前 4 段
（pos-4..pos-3、…、pos-1..pos）的水平状态打包为 mask（bit 0 为最近一段）
时，pos 点之后（含本点）的最小代价；不存在的更早段以“水平(1)”填充，
使不足 5 段时不会触发水平段约束。整体最优值为 dp[0][0b1111][ground[0]]，
为 INF 即无解。重建时逐点取最小可行标高，天然得到同分下字典序最小的序列。

土方调配核算（:func:`earthwork_accounting`）
-------------------------------------------
可行方案确定后，每段地面与方案标高按端点线性变化积分挖/填体积（米³），
高差变号时在交点拆分；段内挖填先抵消，余量集中于段中点。余量只沿
“起点—各中点”链相邻调配，全线净余/净缺只经起点进出，各边有向净流量
（正值朝终点）由前缀累计唯一确定。详见该函数文档。
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import List

N_MIN = 3
N_MAX = 16
H_MIN = 0
H_MAX = 200
MAX_GRADE = 8          # 相邻方案点允许的最大高差（厘米）
WINDOW = 5             # 任意连续 5 段
RECENT = WINDOW - 1    # 状态中记录最近 4 段
_MASK_RECENT = (1 << RECENT) - 1     # 0b1111
_MASK_WINDOW = (1 << WINDOW) - 1     # 0b11111
INF = 10 ** 18

# 土方调配参数
WIDTH_MIN = 0.5                 # 步道净宽下限（米）
WIDTH_MAX = 10.0                # 步道净宽上限（米）
WIDTH_DECIMALS = 2              # 净宽最多两位小数
CM_PER_M = 100.0                # 标高厘米换算为米
SEGMENT_LENGTH = 1.0            # 测点间距（米），即每段水平长度
START_TO_MIDPOINT = 0.5         # 起点到首段中点的距离（米）
MIDPOINT_SPACING = 1.0          # 相邻段中点间距（米）


class PlanError(ValueError):
    """输入非法或问题无可行解。"""


def _validate(ground: List[int]) -> None:
    if not isinstance(ground, list):
        raise PlanError("地面标高必须是数组。")
    if not (N_MIN <= len(ground) <= N_MAX):
        raise PlanError(
            f"测点数量必须在 {N_MIN}～{N_MAX} 个之间（当前 {len(ground)} 个）。"
        )
    for i, g in enumerate(ground):
        if isinstance(g, bool) or not isinstance(g, int):
            raise PlanError(f"第 {i + 1} 个地面标高必须是整数厘米。")
        if not (H_MIN <= g <= H_MAX):
            raise PlanError(
                f"第 {i + 1} 个地面标高 {g} 超出范围"
                f"（{H_MIN}～{H_MAX} 厘米）。"
            )


def _relaxed_reachable(ground: List[int]) -> bool:
    """只受“相邻高差 <= 8”与首尾固定约束时是否可行（双向区间传播）。"""
    n = len(ground)
    lo = [H_MIN] * n
    hi = [H_MAX] * n
    lo[0] = hi[0] = ground[0]
    lo[n - 1] = hi[n - 1] = ground[n - 1]
    for i in range(1, n - 1):
        lo[i] = max(H_MIN, lo[i - 1] - MAX_GRADE)
        hi[i] = min(H_MAX, hi[i - 1] + MAX_GRADE)
    for i in range(n - 2, 0, -1):
        lo[i] = max(lo[i], lo[i + 1] - MAX_GRADE)
        hi[i] = min(hi[i], hi[i + 1] + MAX_GRADE)
        if lo[i] > hi[i]:
            return False
    return lo[0] <= hi[0] and lo[n - 1] <= hi[n - 1]


def _infeasible_reason(ground: List[int]) -> str:
    n = len(ground)
    if not _relaxed_reachable(ground):
        end_gap = abs(ground[-1] - ground[0])
        limit = MAX_GRADE * (n - 1)
        extra = (
            f"：首尾高差 {end_gap} 厘米，超过 {n - 1} 段最多消化的 {limit} 厘米。"
            if end_gap > limit
            else "。"
        )
        return (
            "无解：在“相邻方案点高差不超过 8 厘米、首尾固定”的条件下，"
            "无法从首点标高连续过渡到尾点标高" + extra
        )
    return (
        "无解：满足相邻高差限制时，无法同时满足“任意连续 5 段中至少有 1 段"
        "水平段”，可尝试增加测点或调整地面标高。"
    )


def _window_mask(mask: int, horizontal: int) -> int:
    """加入新段后，最近 5 段的水平位（bit0 为最近一段）。"""
    return ((mask << 1) | horizontal) & _MASK_WINDOW


def validate_width(width) -> float:
    """校验步道净宽：0.5～10 米、数值类型、最多两位小数。"""
    if isinstance(width, bool) or not isinstance(width, (int, float)):
        raise PlanError("步道净宽必须是数字（米）。")
    w = float(width)
    if not math.isfinite(w):
        raise PlanError("步道净宽必须是有限数值。")
    # 用最短十进制表示判断小数位数，避免二进制浮点的 round 误差
    # （例如 round(2.345, 2) 会得到 2.35）。
    decimals = -Decimal(repr(w)).as_tuple().exponent
    if decimals > WIDTH_DECIMALS:
        raise PlanError(f"步道净宽最多保留 {WIDTH_DECIMALS} 位小数（当前 {w} 米）。")
    if not (WIDTH_MIN <= w <= WIDTH_MAX):
        raise PlanError(
            f"步道净宽必须在 {WIDTH_MIN:g}～{WIDTH_MAX:g} 米之间（当前 {w:g} 米）。"
        )
    return w


def _cut_fill_pair(d0: float, d1: float) -> tuple:
    """单段（厘米为标高差单位、长度 1）两端线性变化时的挖填面积。

    令 d(x) = d0 + (d1-d0)*x，x∈[0,1]：
      d > 0 为挖方（方案高于地面），d < 0 为填方（方案低于地面）。
    同号时整体为挖或填；异号时在交点 x 处拆成两个三角形分别积分。
    返回 (挖方面积, 填方面积)，单位为“厘米·段长比例”。
    """
    if d0 >= 0.0 and d1 >= 0.0:
        return 0.5 * (d0 + d1), 0.0
    if d0 <= 0.0 and d1 <= 0.0:
        return 0.0, 0.5 * (-d0 + -d1)
    # 变号：交点把段拆成两个三角形
    x = d0 / (d0 - d1)
    cut_area = 0.5 * (d0 if d0 > 0.0 else d1) * (x if d0 > 0.0 else 1.0 - x)
    fill_area = 0.5 * (-d0 if d0 < 0.0 else -d1) * (x if d0 < 0.0 else 1.0 - x)
    return cut_area, fill_area


def earthwork_accounting(ground: List[int], plan: List[int], width: float) -> dict:
    """土方调配核算。

    每段地面与方案标高均按线性变化，积分挖方/填方体积（米³）：
    段内高差变号时在交点拆分为两个三角形分别积分；段内挖填先抵消，
    余量挂在该段中点（坐标 i+0.5）。余量只允许在起点（坐标 0）与
    相邻中点之间调配，全线净余/净缺只经起点进出，因此各条边上的
    有向净流量由前缀累计唯一确定。

    返回分段挖填、段后累计净量、各条边有向净流量（正值朝终点）
    及运量距离（Σ|流量|×距离，米³·米）。全程不提前取整。
    """
    width = float(width)
    cm2_to_m3 = SEGMENT_LENGTH / (CM_PER_M ** 2)   # 厘米²×段长 → 米³
    segments = []
    totals_cut = totals_fill = 0.0

    for i in range(len(ground) - 1):
        # 方案标高 − 地面标高（厘米）：正为挖、负为填
        d0 = plan[i] - ground[i]
        d1 = plan[i + 1] - ground[i + 1]
        cut_area, fill_area = _cut_fill_pair(float(d0), float(d1))
        cut = cut_area * width * cm2_to_m3
        fill = fill_area * width * cm2_to_m3
        net = cut - fill                       # 正：本段净余（可调出）
        totals_cut += cut
        totals_fill += fill
        segments.append({
            "index": i + 1,
            "from": i + 1,
            "to": i + 2,
            "cut": cut,
            "fill": fill,
            "net": net + 0.0,                  # 规整 -0.0
        })

    # 段后累计净量：cumulative[i] = 前 i+1 段净量之和
    cumulative = []
    running = 0.0
    for seg in segments:
        running += seg["net"]
        cumulative.append(running + 0.0)

    # 有向净流量（正值朝终点）：
    #   边 0：起点→段1中点（0.5 m），流量 = −全线净量；
    #   边 k（k≥1）：段k中点→段k+1中点（1 m），流量 = −全线净量 + 前 k 段累计。
    # 该式由各中点守恒（流入−流出 + 本段净余 = 0）与“终点不进出”唯一确定。
    flows = []
    total_net = running + 0.0
    for k, seg in enumerate(segments):
        if k == 0:
            edge_flow = -total_net
        else:
            edge_flow = -total_net + cumulative[k - 1]
        distance = START_TO_MIDPOINT if k == 0 else MIDPOINT_SPACING
        flows.append({
            "index": k + 1,
            "from": "起点" if k == 0 else f"段{k}中点",
            "to": f"段{seg['index']}中点",
            "flow": edge_flow + 0.0,
            "distance": distance,
        })

    haul = sum(abs(f["flow"]) * f["distance"] for f in flows)

    return {
        "width": width,
        "unit": "m3",
        "total_cut": totals_cut + 0.0,
        "total_fill": totals_fill + 0.0,
        "total_net": total_net,               # 正：全线净余（经起点运出）
        "segments": segments,
        "cumulative_net": cumulative,
        "flows": flows,
        "haul_distance": haul + 0.0,          # 运量距离（m3·m）
        "haul_unit": "m3·m",
    }


def plan_trail(ground: List[int], width=None) -> dict:
    """计算最优步道坡线方案。

    传入合法 ``width``（步道净宽，米）时，可行结果额外附带 ``earthwork``
    土方调配核算（见 :func:`earthwork_accounting`）。

    可行时返回::

        {
          "feasible": True,
          "ground": [...], "plan": [...],
          "total_adjustment": int,
          "segments": [{"index", "from", "to", "delta", "horizontal"}],
          "horizontal_indices": [...],   # 1-based 段号
          "earthwork": {...} | None,     # 仅在传入 width 时附带
        }

    无解时返回 {"feasible": False, "reason": "..."}；非法输入抛 PlanError。
    """
    _validate(ground)
    validated_width = validate_width(width) if width is not None else None
    n = len(ground)
    g0, glast = ground[0], ground[-1]
    size = H_MAX + 1

    # dp[pos][mask][h]：pos 点取 h、携带到达该点最近 4 段水平掩码时，
    # pos 点之后（含本点标高代价）的最小代价。
    dp = [
        [[INF] * size for _ in range(1 << RECENT)]
        for _ in range(n)
    ]
    for mask in range(1 << RECENT):
        dp[n - 1][mask][glast] = abs(glast - ground[n - 1])

    for pos in range(n - 2, -1, -1):
        layer = dp[pos]
        next_layer = dp[pos + 1]
        seg_index = pos                     # 新放下的是第 seg_index 段（0-based）
        check_window = seg_index >= WINDOW - 1
        cost_h = [abs(h - ground[pos]) for h in range(size)]
        for mask in range(1 << RECENT):
            cell = layer[mask]
            for h in range(H_MIN, H_MAX + 1):
                lo = max(H_MIN, h - MAX_GRADE)
                hi = min(H_MAX, h + MAX_GRADE)
                base = cost_h[h]
                best = INF

                # 水平段：nh == h
                nmask = 1 | ((mask << 1) & _MASK_RECENT)
                if not check_window or _window_mask(mask, 1) != 0:
                    cand = base + next_layer[nmask][h]
                    if cand < best:
                        best = cand

                # 非水平段：nh != h
                nmask = (mask << 1) & _MASK_RECENT
                if not check_window or _window_mask(mask, 0) != 0:
                    nl = next_layer[nmask]
                    for nh in range(lo, h):
                        cand = base + nl[nh]
                        if cand < best:
                            best = cand
                    for nh in range(h + 1, hi + 1):
                        cand = base + nl[nh]
                        if cand < best:
                            best = cand
                cell[h] = best

    total = dp[0][_MASK_RECENT][g0]
    if total >= INF:
        return {"feasible": False, "reason": _infeasible_reason(ground)}

    # 逐点选择最小可行标高，得到同分下字典序最小的方案。
    plan = [0] * n
    plan[0] = g0
    mask = _MASK_RECENT                    # 起点之前的“虚拟段”全部视为水平
    spent = abs(g0 - ground[0])
    for pos in range(0, n - 1):
        h = plan[pos]
        check_window = pos >= WINDOW - 1
        chosen = None
        for nh in range(max(H_MIN, h - MAX_GRADE), min(H_MAX, h + MAX_GRADE) + 1):
            b = 1 if nh == h else 0
            nmask = b | ((mask << 1) & _MASK_RECENT)
            if check_window and _window_mask(mask, b) == 0:
                continue
            if spent + dp[pos + 1][nmask][nh] == total:
                chosen = (nh, nmask)
                break
        assert chosen is not None, "重建最优方案失败"
        plan[pos + 1], mask = chosen
        spent += abs(plan[pos + 1] - ground[pos + 1])

    assert plan[-1] == glast and spent == total

    segments = []
    horizontal_indices = []
    for i in range(n - 1):
        delta = plan[i + 1] - plan[i]
        is_horizontal = delta == 0
        if is_horizontal:
            horizontal_indices.append(i + 1)
        segments.append(
            {"index": i + 1, "from": i + 1, "to": i + 2,
             "delta": delta, "horizontal": is_horizontal}
        )

    result = {
        "feasible": True,
        "ground": list(ground),
        "plan": plan,
        "total_adjustment": total,
        "segments": segments,
        "horizontal_indices": horizontal_indices,
        "earthwork": None,
    }
    if validated_width is not None:
        result["earthwork"] = earthwork_accounting(ground, plan, validated_width)
    return result
