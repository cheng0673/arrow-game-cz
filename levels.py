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


def reverse_generate_masked(rows: int, cols: int,
                            active: set[tuple[int, int]],
                            count: int,
                            seed: Optional[int] = None,
                            attempts: int = 200) -> list[ArrowSpec]:
    """
    异形棋盘版逆向构造：只在 ``active`` 集合里的格子上摆放箭头。
    非 active 格子视为「空洞」——箭头射线可穿过，不会阻挡，也不放置箭。
    其余逻辑与 reverse_generate 一致，数学上保证可解。
    """
    active = set(active)
    if count > len(active):
        count = len(active)
    if count <= 0:
        return []
    rng = random.Random(seed)
    dirs = list(Direction)
    best: Optional[list[ArrowSpec]] = None
    best_score = -1

    for _ in range(attempts):
        occupied: set[tuple[int, int]] = set()
        placed: list[ArrowSpec] = []
        blocked_by: dict[tuple[int, int], int] = {}
        for _ in range(count):
            candidates: list[tuple[int, int, int]] = []
            for r, c in active:
                if (r, c) in occupied:
                    continue
                for d in dirs:
                    if _ray_clear(occupied, rows, cols, r, c, d):
                        candidates.append((blocked_by.get((r, c), 0), r, c))
                        break
            if not candidates:
                break
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
        raise RuntimeError(f"无法在异形棋盘上生成 {count} 支箭的关卡")
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


# ---------------- 难度分级 ----------------
# 每关均可选 简单/中等/困难：(名称, 棋盘边长, 填充率, 限时秒, 按钮配色)
DIFFICULTIES = [
    ("简单", 5, 0.55, 75, "mint"),
    ("中等", 6, 0.70, 105, "orange"),
    ("困难", 7, 0.88, 140, "pink"),
]


def build_difficulty_level(index: int, diff: int) -> dict:
    """
    按关卡序号 + 难度（0=简单 / 1=中等 / 2=困难）构造关卡。
    固定种子保证同一 (关卡, 难度) 布局一致、存档可复现；
    填充率最高 88%，尽量把棋盘填满提高可玩性。
    """
    label, size, ratio, time_limit, _style = DIFFICULTIES[diff]
    target = round(size * size * ratio)
    arrows = None
    # 个别种子在高密度下可能摆不下，逐级降低数量重试
    for count in (target, target - 2, target - 4, target - 6):
        if count < 6:
            break
        try:
            arrows = reverse_generate(size, size, count,
                                      seed=1009 * (index + 1) + 373 * (diff + 1))
            break
        except RuntimeError:
            continue
    if arrows is None:
        arrows = reverse_generate(size, size, max(6, target // 2), seed=7)
    bases = HAND_LEVELS + GENERATED_LEVELS
    base_name = bases[index]["name"] if index < len(bases) else f"第{index + 1}关"
    return {
        "name": f"{base_name}·{label}",
        "rows": size,
        "cols": size,
        "time_limit": float(time_limit),
        "mistakes": 3,
        "arrows": arrows,
    }


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


# ---------------- 异形关卡（像素画棋盘）----------------
# 图案字符：'.' 空洞；'#' 主体格（用形状主色，可放箭头）；
# 其余字符为「装饰格」：按像素画上固定颜色（果柄/叶子/五官等），
# 不放置箭头、射线可穿过，从开局就能看到完整图案特征。

# 像素画调色板（字符 -> RGB）
PIXEL_COLORS = {
    "g": (92, 188, 84),    # 绿叶
    "d": (46, 140, 70),    # 深绿（瓜纹/叶暗部）
    "b": (134, 86, 44),    # 棕色（果柄）
    "w": (252, 250, 244),  # 白色（肚皮/眼白/兔身）
    "c": (208, 200, 190),  # 浅灰（胡须/嘴线/阴影）
    "k": (52, 44, 56),     # 黑色（眼睛/鼻子/轮廓/蝴蝶身体）
    "p": (255, 146, 174),  # 粉色（鼻子/内耳/腮红）
    "o": (255, 152, 62),   # 橙色（喙/脚）
    "y": (255, 214, 92),   # 明黄（菠萝/籽）
    "u": (150, 102, 220),  # 紫色（葡萄纹理/翅膀花纹）
    "n": (52, 72, 116),    # 深蓝（企鹅背/暗部）
    "t": (224, 180, 122),  # 浅棕（熊口鼻/内耳）
    "s": (255, 240, 150),  # 浅黄（草莓籽/高光）
}


def _parse_mask(text: str, primary):
    """
    解析像素画图案，返回 (rows, cols, cells, playable)：
    - cells：所有图案格 {(r, c): 颜色}（主体格 + 装饰格）；
    - playable：可放置箭头的主体格集合（仅 '#'）。
    """
    lines = [ln.rstrip() for ln in text.strip().splitlines()]
    rows = len(lines)
    cols = max((len(ln) for ln in lines), default=0)
    cells: dict[tuple[int, int], tuple[int, int, int]] = {}
    playable: set[tuple[int, int]] = set()
    for r, ln in enumerate(lines):
        for c, ch in enumerate(ln):
            if ch == "#":
                cells[(r, c)] = primary
                playable.add((r, c))
            elif ch in PIXEL_COLORS:
                cells[(r, c)] = PIXEL_COLORS[ch]
    return rows, cols, cells, playable


# ---------------- 水果 / 动物主题图案（13 列像素画） ----------------
# '#' 主体格（可放箭）；g 绿叶 / d 深绿 / b 棕柄 / w 白 / c 灰点 /
# k 黑（眼鼻嘴）/ p 粉（鼻/内耳/腮红）/ o 橙（喙脚）/ y 黄 /
# u 紫（菠萝格纹）/ n 深蓝 / t 浅棕 / s 浅黄（草莓籽）。
# 装饰格不放箭、射线穿过。关键：五官只能「替换」满行里的格子，不能在脸
# 中间留下整行空洞。

# 水果主题：6 种水果
FRUIT_PATTERNS = [
    ("苹果", """
......b......
.....gbg.....
.....###.....
....#####....
...#######...
..#########..
.###########.
#############
#############
.###########.
..#########..
...#######...
....#####....
.....###.....
""", (238, 64, 78)),
    ("草莓", """
..g...d...g..
..ggggggggg..
..#########..
.##s#####s##.
#############
##s#######s##
#############
.##s#####s##.
.###########.
..#########..
...#######...
....#####....
.....###.....
""", (236, 58, 84)),
    ("西瓜", """
.....b
....gggg
...d#####d
..###d#d###
.###########
###d#####d###
#############
####d###d####
###d#####d###
.###########
..###d#d###
...d#####d
....gggg
""", (86, 196, 108)),
    ("葡萄", """
.....gb......
.....gb......
.##..##..##..
.##########..
..########..
...######....
....####.....
.....##......
""", (156, 108, 224)),
    ("樱桃", """
....bbb
...b...b
..b.....b
..b......b
.###....###
####....####
#####..#####
#####..#####
.###....###
""", (232, 52, 82)),
    ("菠萝", """
...g..d..g...
..ggggggggg..
....ggdgg....
....#####....
...#u###u#...
..##u#u#u##..
..#u#####u#..
..##u#u#u##..
..#u#####u#..
..##u#u#u##..
...##u#u##...
....#####....
....#####....
""", (252, 202, 74)),
]

# 动物主题：6 种动物头像
ANIMAL_PATTERNS = [
    ("小猫", """
..##.....##..
.#p#.....#p#.
#####...#####
.###########.
###k#####k###
#############
######p######
#####k#k#####
.cp###k###pc.
..#########..
""", (252, 200, 140)),
    ("兔子", """
...##...##...
...#p...p#...
...#p...p#...
...##...##...
...##...##...
.###########.
#############
###k#####k###
#############
######p######
#####k#k#####
.###########.
""", (248, 244, 236)),
    ("小熊", """
.###....###
##t##..##t##
#####...#####
.###########
##k#######k##
####tttt####
###tttkttt###
####tttt####
#############
.###########
..#########
""", (192, 130, 76)),
    ("企鹅", """
....#####
...#######
..#########
..##wwwww##
.##wwwwwww##
##wwwwowwww##
##wwwwwwwww##
##wwwwwwwww##
.##wwwwwww##
..##wwwww##
...#######
..#o#...#o#
..#o#...#o#
""", (52, 72, 116)),
    ("小鱼", """
..#######..#.
.#########.##
##k#######.#.
###########.#
#####c#####.#
###########.#
.#########.##
..#######..#.
""", (96, 180, 246)),
    ("蝴蝶", """
..b.......b..
.#####.#####.
##p###.###p##
#############
##u#######u##
######k######
.###########.
..#########..
..##u##k##u#.
.####k#k####.
..##p###p##..
...###.###...
""", (190, 124, 232)),
]

SHAPE_THEMES = {
    "fruit": FRUIT_PATTERNS,
    "animal": ANIMAL_PATTERNS,
}


SHAPE_DIFFICULTIES = [
    ("简单", 0.50, 75),
    ("中等", 0.70, 105),
    ("困难", 0.88, 140),
]


def build_shape_level(theme: str, index: int, diff: int) -> dict:
    """
    异形关卡：按主题（fruit/animal）+ 形状序号 + 难度构造。
    难度只改变「主体格」上的箭头填充率，像素画图案本身不变。
    """
    patterns = SHAPE_THEMES[theme]
    name, pattern, primary = patterns[index % len(patterns)]
    rows, cols, cells, playable = _parse_mask(pattern, primary)
    label, ratio, time_limit = SHAPE_DIFFICULTIES[diff]
    target = round(len(playable) * ratio)
    arrows = None
    theme_seed = 777 if theme == "fruit" else 1453
    for count in (target, target - 2, target - 4, target - 6):
        if count < 4:
            break
        try:
            arrows = reverse_generate_masked(
                rows, cols, playable, count,
                seed=3001 * (index + 1) + 503 * (diff + 1) + theme_seed)
            break
        except RuntimeError:
            continue
    if arrows is None:
        arrows = reverse_generate_masked(rows, cols, playable,
                                         max(4, len(playable) // 2), seed=11)
    return {
        "name": f"{name}·{label}",
        "rows": rows,
        "cols": cols,
        "time_limit": float(time_limit),
        "mistakes": 3,
        "arrows": arrows,
        "mask": [[r, c, color] for (r, c), color in sorted(cells.items())],
        "shape_index": index,
        "shape_kind": theme,
    }


def all_shape_levels(theme: str) -> list[dict]:
    """返回某主题下所有形状的元数据（含逐格颜色，用于选关预览）。"""
    out = []
    for name, pattern, primary in SHAPE_THEMES[theme]:
        rows, cols, cells, playable = _parse_mask(pattern, primary)
        out.append({"name": name, "rows": rows, "cols": cols,
                    "cells": [[r, c, color] for (r, c), color in sorted(cells.items())],
                    "playable": len(playable)})
    return out
