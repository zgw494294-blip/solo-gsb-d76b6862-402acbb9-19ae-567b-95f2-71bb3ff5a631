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
"""

from __future__ import annotations

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


def plan_trail(ground: List[int]) -> dict:
    """计算最优步道坡线方案。

    可行时返回::

        {
          "feasible": True,
          "ground": [...], "plan": [...],
          "total_adjustment": int,
          "segments": [{"index", "from", "to", "delta", "horizontal"}],
          "horizontal_indices": [...],   # 1-based 段号
        }

    无解时返回 {"feasible": False, "reason": "..."}；非法输入抛 PlanError。
    """
    _validate(ground)
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

    return {
        "feasible": True,
        "ground": list(ground),
        "plan": plan,
        "total_adjustment": total,
        "segments": segments,
        "horizontal_indices": horizontal_indices,
    }
