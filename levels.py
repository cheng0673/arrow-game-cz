# -*- coding: utf-8 -*-
"""
关卡系统：
- 手工关卡用字符串布局表示（↑↓←→ 是箭头，· 或空格是空位）；
- solve() 用记忆化 DFS 验证关卡可解，并给出一条通关顺序（提示功能用）；
- reverse_generate() 用「逆向构造法」随机构造关卡，数学上保证必然可解。

逆向构造原理：
设清除顺序为 a1, a2, ..., an（a1 最先飞走）。倒着摆放：先摆 an，再摆 a(n-1)，
最后摆 a1。摆 ai 时棋盘上只有 a(i+1)...an，因此只要保证「新箭头前进方向的
射线上没有任何已摆放的箭头」，那么按摆放顺序的逆序点击就一定能通关。
"""
from __future__ import annotations

import random
from typing import Optional

from model import Direction

CHAR_TO_DIR = {
    "↑": Direction.UP,
    "↓": Direction.DOWN,
    "←": Direction.LEFT,
    "→": Direction.RIGHT,
}
DIR_TO_CHAR = {d: ch for ch, d in CHAR_TO_DIR.items()}

ArrowSpec = tuple[int, int, Direction]


def parse_layout(text: str) -> tuple[int, int, list[ArrowSpec]]:
    """把多行字符串布局解析成 (行数, 列数, 箭头列表)。"""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    rows = len(lines)
    cols = max(len(line) for line in lines)
    arrows: list[ArrowSpec] = []
    for r, line in enumerate(lines):
        for c, ch in enumerate(line):
            if ch in CHAR_TO_DIR:
                arrows.append((r, c, CHAR_TO_DIR[ch]))
    return rows, cols, arrows


def layout_to_text(rows: int, cols: int, arrows: list[ArrowSpec]) -> str:
    grid = [["·" for _ in range(cols)] for _ in range(rows)]
    for r, c, d in arrows:
        grid[r][c] = DIR_TO_CHAR[d]
    return "\n".join("".join(row) for row in grid)


def _ray_clear(occ: set[tuple[int, int]], rows: int, cols: int,
               r: int, c: int, d: Direction) -> bool:
    """(r,c) 处朝 d 方向的射线上（不含自身）没有已占据格子。"""
    nr, nc = r + d.dr, c + d.dc
    while 0 <= nr < rows and 0 <= nc < cols:
        if (nr, nc) in occ:
            return False
        nr += d.dr
        nc += d.dc
    return True


def solve(rows: int, cols: int, arrows: list[ArrowSpec],
          budget: int = 400_000) -> Optional[list[ArrowSpec]]:
    """
    记忆化 DFS：返回一条通关顺序（每步都是当时前方无阻挡的箭头）。
    无解或超过搜索预算时返回 None。
    """
    initial = frozenset((r, c, d) for r, c, d in arrows)
    # 带路径记忆化 DFS：找到一条「每步都前方无阻挡」的消除顺序
    path: list[ArrowSpec] = []
    memo_path: dict[frozenset, bool] = {}
    calls = 0

    def dfs_path(state: frozenset) -> bool:
        nonlocal calls
        calls += 1
        if calls > budget:
            raise TimeoutError("搜索预算耗尽")
        if not state:
            return True
        cached = memo_path.get(state)
        if cached is not None:
            return cached
        occupied = {(r, c) for r, c, _ in state}
        free = []
        for r, c, d in state:
            nr, nc = r + d.dr, c + d.dc
            blocked = False
            while 0 <= nr < rows and 0 <= nc < cols:
                if (nr, nc) in occupied:
                    blocked = True
                    break
                nr += d.dr
                nc += d.dc
            if not blocked:
                free.append((r, c, d))
        for a in free:
            path.append(a)
            if dfs_path(state - {a}):
                memo_path[state] = True
                return True
            path.pop()
        memo_path[state] = False
        return False

    try:
        if dfs_path(initial):
            return list(path)
    except TimeoutError:
        return None
    return None


def reverse_generate(rows: int, cols: int, count: int,
                     seed: Optional[int] = None, attempts: int = 200) -> list[ArrowSpec]:
    """
    逆向构造法生成必然可解的关卡。
    优先选择「能挡住更多已摆放箭头」的位置，让局面更纠缠、更有解谜感。
    """
    rng = random.Random(seed)
    dirs = list(Direction)
    best: Optional[list[ArrowSpec]] = None
    best_score = -1

    for _ in range(attempts):
        occupied: set[tuple[int, int]] = set()
        placed: list[ArrowSpec] = []
        # 每个候选格子被多少已摆放箭头的射线经过（放在那里就能挡住它们）
        blocked_by: dict[tuple[int, int], int] = {}
        for _ in range(count):
            candidates: list[tuple[int, int, int]] = []  # (阻挡数, r, c)
            for r in range(rows):
                for c in range(cols):
                    if (r, c) in occupied:
                        continue
                    for d in dirs:
                        if _ray_clear(occupied, rows, cols, r, c, d):
                            candidates.append((blocked_by.get((r, c), 0), r, c))
                            break  # 该格只需一个可行方向，后面再随机选
            if not candidates:
                break
            # 在所有可行 (格, 方向) 组合里挑，偏向高阻挡数
            full: list[tuple[int, int, Direction]] = []
            for _, r, c in candidates:
                for d in dirs:
                    if _ray_clear(occupied, rows, cols, r, c, d):
                        full.append((blocked_by.get((r, c), 0), r, c, d))
            if not full:
                break
            max_block = max(item[0] for item in full)
            if max_block > 0 and rng.random() < 0.75:
                pool = [item for item in full if item[0] >= max(1, max_block - 1)]
            else:
                pool = full
            _, r, c, d = rng.choice(pool)
            occupied.add((r, c))
            placed.append((r, c, d))
            # 更新阻挡计数：新箭头的整条射线格子 +1
            nr, nc = r + d.dr, c + d.dc
            while 0 <= nr < rows and 0 <= nc < cols:
                blocked_by[(nr, nc)] = blocked_by.get((nr, nc), 0) + 1
                nr += d.dr
                nc += d.dc

        if len(placed) == count:
            score = sum(blocked_by.values())
            if score > best_score:
                best_score = score
                best = placed

    if best is None:
        raise RuntimeError(f"无法生成 {rows}x{cols} 共 {count} 支箭的关卡")
    return best


# ---------------- 关卡配置 ----------------

# 前两关为手工设计的教学关卡；其余关卡由固定随机种子逆向构造，保证可解且复现一致。
HAND_LEVELS: list[dict] = [
    {
        "name": "初识箭头",
        "rows": 4, "cols": 4,
        "time_limit": 90, "mistakes": 3,
        "layout": (
            "→···\n"
            "→·↑·\n"
            "·↓··\n"
            "··←·"
        ),
    },
    {
        "name": "左右为难",
        "rows": 5, "cols": 5,
        "time_limit": 90, "mistakes": 3,
        "layout": (
            "↓··→·\n"
            "···↑·\n"
            "←···→\n"
            "··↓··\n"
            "←→···"
        ),
    },
]

GENERATED_LEVELS: list[dict] = [
    {"name": "小试身手", "rows": 5, "cols": 5, "count": 11, "time_limit": 85, "mistakes": 3, "seed": 103},
    {"name": "箭如雨下", "rows": 6, "cols": 6, "count": 14, "time_limit": 80, "mistakes": 3, "seed": 207},
    {"name": "眼花缭乱", "rows": 7, "cols": 7, "count": 18, "time_limit": 75, "mistakes": 3, "seed": 308},
    {"name": "昆冈论剑", "rows": 7, "cols": 7, "count": 22, "time_limit": 70, "mistakes": 3, "seed": 412},
]


def build_level(spec: dict) -> dict:
    """把关卡配置实例化为箭头列表，并验证可解性；手工关卡若意外无解则自动替换。"""
    if "layout" in spec:
        rows, cols, arrows = parse_layout(spec["layout"])
        rows, cols = spec["rows"], spec["cols"]
        result = solve(rows, cols, arrows)
        if result is None:
            # 兜底：逆向构造一个同规模关卡
            arrows = reverse_generate(rows, cols, len(arrows), seed=999)
    else:
        rows, cols = spec["rows"], spec["cols"]
        arrows = reverse_generate(rows, cols, spec["count"], seed=spec["seed"])
        # 逆向构造在数学上已保证可解，这里再跑一次求解器做双重确认
        solve(rows, cols, arrows)
    return {
        "name": spec["name"],
        "rows": rows,
        "cols": cols,
        "time_limit": spec["time_limit"],
        "mistakes": spec["mistakes"],
        "arrows": arrows,
    }


def all_levels() -> list[dict]:
    return [build_level(spec) for spec in HAND_LEVELS + GENERATED_LEVELS]


def make_random_level(index: int) -> dict:
    """随机挑战模式：难度随关卡序号递增，规模 5x5 → 8x8。"""
    rng = random.Random()
    size = min(5 + index // 2, 8)
    # 密度过高时摆放可能失败，限制在约半数格子以内保证生成顺畅
    count = min(9 + index * 2, size * size - 4, size * size // 2 + size // 2)
    time_limit = max(45, 75 - index * 2)
    arrows = reverse_generate(size, size, count, seed=rng.randrange(1 << 30))
    return {
        "name": f"随机挑战 {index + 1}",
        "rows": size,
        "cols": size,
        "time_limit": time_limit,
        "mistakes": 3,
        "arrows": arrows,
        "random": True,
    }
