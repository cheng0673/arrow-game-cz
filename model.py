# -*- coding: utf-8 -*-
"""
一箭又一箭 —— 核心逻辑层（不依赖 pygame，可直接用 unittest 测试）

规则：
1. 棋盘上有上、下、左、右四种方向的箭头；
2. 点击一个箭头：若它前进方向（同行 / 同列）到棋盘边界之间没有其它
   还活着的箭头，它就飞出棋盘被消除；否则碰撞失败，失误次数 -1；
3. 清空全部箭头即通关；失误次数用完（或倒计时归零）即失败。
"""
from __future__ import annotations

import itertools
from enum import Enum
from typing import Iterable, Optional


class Direction(Enum):
    """四个方向，值为 (行位移 dr, 列位移 dc)。"""

    UP = (-1, 0)
    DOWN = (1, 0)
    LEFT = (0, -1)
    RIGHT = (0, 1)

    @property
    def dr(self) -> int:
        return self.value[0]

    @property
    def dc(self) -> int:
        return self.value[1]

    @property
    def angle(self) -> float:
        """绘制时朝右的箭头素材需要旋转的角度（顺时针角度）。"""
        return {
            Direction.RIGHT: 0.0,
            Direction.DOWN: 90.0,
            Direction.LEFT: 180.0,
            Direction.UP: 270.0,
        }[self]


class Arrow:
    """棋盘上的一支箭。"""

    _id_counter = itertools.count(1)

    def __init__(self, row: int, col: int, direction: Direction):
        self.id = next(Arrow._id_counter)
        self.row = row
        self.col = col
        self.direction = direction

    def __repr__(self) -> str:
        symbol = {
            Direction.UP: "↑",
            Direction.DOWN: "↓",
            Direction.LEFT: "←",
            Direction.RIGHT: "→",
        }[self.direction]
        return f"Arrow({self.row},{self.col},{symbol})"


class Board:
    """rows × cols 的二维棋盘，每格放一支 Arrow 或 None。"""

    def __init__(self, rows: int, cols: int, arrows: Iterable[Arrow]):
        self.rows = rows
        self.cols = cols
        self.grid: list[list[Optional[Arrow]]] = [
            [None for _ in range(cols)] for _ in range(rows)
        ]
        self.arrows: list[Arrow] = []
        for arrow in arrows:
            if not self.inside(arrow.row, arrow.col):
                raise ValueError(f"箭头越界: {arrow!r}")
            if self.grid[arrow.row][arrow.col] is not None:
                raise ValueError(f"格子被重复占用: ({arrow.row},{arrow.col})")
            self.grid[arrow.row][arrow.col] = arrow
            self.arrows.append(arrow)

    def inside(self, row: int, col: int) -> bool:
        return 0 <= row < self.rows and 0 <= col < self.cols

    def iter_path(self, arrow: Arrow) -> Iterable[tuple[int, int]]:
        """沿箭头方向，逐个产出箭头前方直到边界之间的格子坐标。"""
        r, c = arrow.row + arrow.direction.dr, arrow.col + arrow.direction.dc
        while self.inside(r, c):
            yield r, c
            r += arrow.direction.dr
            c += arrow.direction.dc

    def path_clear(self, arrow: Arrow) -> bool:
        """前方（同一直线）没有任何活着的箭头时返回 True。"""
        for r, c in self.iter_path(arrow):
            if self.grid[r][c] is not None:
                return False
        return True

    def blocker(self, arrow: Arrow) -> Optional[Arrow]:
        """返回挡住箭头的第一支箭（没有则 None）。"""
        for r, c in self.iter_path(arrow):
            other = self.grid[r][c]
            if other is not None:
                return other
        return None

    def free_arrows(self) -> list[Arrow]:
        """当前可以直接飞出棋盘的所有箭头。"""
        return [a for a in self.arrows if self.grid[a.row][a.col] is a and self.path_clear(a)]

    def remove(self, arrow: Arrow) -> None:
        self.grid[arrow.row][arrow.col] = None
        self.arrows.remove(arrow)

    def alive_count(self) -> int:
        return len(self.arrows)

    def snapshot(self) -> tuple[tuple[tuple[int, int, Direction], ...], int, int, int, float, int]:
        """保存局面（箭头位置方向 + 全部计分状态），用于撤销。"""
        spec = tuple(sorted((a.row, a.col, a.direction) for a in self.arrows))
        return spec

    def restore(self, spec: Iterable[tuple[int, int, Direction]]) -> None:
        self.grid = [[None for _ in range(self.cols)] for _ in range(self.rows)]
        self.arrows = []
        for r, c, d in spec:
            arrow = Arrow(r, c, d)
            self.grid[r][c] = arrow
            self.arrows.append(arrow)


# 点击结果
CLICK_FLY = "fly"          # 成功飞出
CLICK_BLOCKED = "blocked"  # 被挡住
CLICK_EMPTY = "empty"      # 点到空格
CLICK_IGNORED = "ignored"  # 游戏未在进行 / 动画锁等

SCORE_BASE = 100           # 每支箭基础分
COMBO_BONUS = 50           # 连击额外加成


class GameSession:
    """一局游戏：棋盘 + 失误 / 计时 / 计分 / 提示 / 撤销。"""

    def __init__(
        self,
        rows: int,
        cols: int,
        arrows: Iterable[tuple[int, int, Direction]],
        time_limit: float = 90.0,
        max_mistakes: int = 3,
        max_hints: int = 3,
    ):
        self.rows = rows
        self.cols = cols
        self.board = Board(rows, cols, [Arrow(r, c, d) for r, c, d in arrows])
        self.time_limit = float(time_limit)
        self.time_left = float(time_limit)
        self.max_mistakes = max_mistakes
        self.mistakes_left = max_mistakes
        self.max_hints = max_hints
        self.hints_left = max_hints
        self.score = 0
        self.combo = 0
        self.best_combo = 0
        self.cleared = 0
        self.state = "playing"  # playing / won / lost
        self.lose_reason = None  # "mistake" / "timeout"
        self._history: list[tuple] = []

    # ---------- 局面快照 / 撤销 ----------
    def _snapshot(self) -> tuple:
        spec = tuple(sorted((a.row, a.col, a.direction) for a in self.board.arrows))
        return (
            spec,
            self.mistakes_left,
            self.score,
            self.combo,
            self.best_combo,
            self.cleared,
            self.time_left,
            self.hints_left,
        )

    def can_undo(self) -> bool:
        return self.state == "playing" and bool(self._history)

    def undo(self) -> bool:
        """撤销上一次点击（成功或失误都可撤销，时间不回退）。"""
        if not self._history:
            return False
        spec, mistakes, score, combo, best, cleared, _time_left, hints = self._history.pop()
        self.board.restore(spec)
        self.mistakes_left = mistakes
        self.score = score
        self.combo = combo
        self.best_combo = best
        self.cleared = cleared
        # 撤销恢复局面与计分，但不退还已经流逝的时间
        self.hints_left = hints
        return True

    # ---------- 计时 ----------
    def update(self, dt: float) -> None:
        if self.state != "playing":
            return
        self.time_left -= dt
        if self.time_left <= 0:
            self.time_left = 0
            self._lose("timeout")

    # ---------- 核心点击 ----------
    def click(self, row: int, col: int) -> tuple[str, Optional[Arrow], Optional[Arrow]]:
        """
        返回 (结果, 被点击的箭头, 阻挡它的箭头)。
        成功飞出 -> (CLICK_FLY, arrow, None)
        被挡住   -> (CLICK_BLOCKED, arrow, blocker)
        点空格   -> (CLICK_EMPTY, None, None)
        """
        if self.state != "playing" or not self.board.inside(row, col):
            return CLICK_IGNORED, None, None
        arrow = self.board.grid[row][col]
        if arrow is None:
            return CLICK_EMPTY, None, None

        self._history.append(self._snapshot())
        blocker = self.board.blocker(arrow)
        if blocker is not None:
            self.mistakes_left -= 1
            self.combo = 0
            if self.mistakes_left <= 0:
                self._lose("mistake")
            return CLICK_BLOCKED, arrow, blocker

        # 前方畅通：飞出、计分
        self.board.remove(arrow)
        self.cleared += 1
        self.combo += 1
        self.best_combo = max(self.best_combo, self.combo)
        self.score += SCORE_BASE + (self.combo - 1) * COMBO_BONUS
        if self.board.alive_count() == 0:
            self._win()
        return CLICK_FLY, arrow, None

    def _win(self) -> None:
        self.state = "won"
        # 时间奖励：每秒剩余时间 +5 分
        self.score += int(self.time_left) * 5

    def _lose(self, reason: str) -> None:
        self.state = "lost"
        self.lose_reason = reason

    # ---------- 星级 ----------
    def stars(self) -> int:
        """通关星级：满失误（一次没撞）3 星，最多失误 1 次 2 星，其余 1 星。"""
        if self.state != "won":
            return 0
        if self.mistakes_left == self.max_mistakes:
            return 3
        if self.mistakes_left >= self.max_mistakes - 1:
            return 2
        return 1

    # ---------- 提示 ----------
    def use_hint(self) -> Optional[Arrow]:
        """消耗一次提示，返回当前应该点击的箭头（DFS 求出可行解的第一步）。"""
        if self.state != "playing" or self.hints_left <= 0:
            return None
        from levels import solve

        seq = solve(self.rows, self.cols,
                    [(a.row, a.col, a.direction) for a in self.board.arrows])
        if not seq:
            return None
        r, c, _ = seq[0]
        arrow = self.board.grid[r][c]
        if arrow is not None:
            self.hints_left -= 1
        return arrow
