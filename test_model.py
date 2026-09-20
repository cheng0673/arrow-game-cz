# -*- coding: utf-8 -*-
"""
核心逻辑单元测试：python test_model.py
覆盖：方向与路径检测、成功消除、碰撞与失误、连击计分、
      超时失败、撤销、提示、全部内置关卡可解性、随机生成可解性。
"""
import time
import unittest

from levels import all_levels, make_random_level, parse_layout, reverse_generate, solve
from model import (CLICK_BLOCKED, CLICK_FLY, Board, Direction, GameSession,
                   Arrow)


def session_from_layout(text, time_limit=90, mistakes=3):
    rows, cols, arrows = parse_layout(text)
    return GameSession(rows, cols, arrows, time_limit=time_limit,
                       max_mistakes=mistakes)


def autoplay(session, seq=None):
    """按求解顺序自动通关（seq 为外部给定时用它，否则实时求解）。"""
    clicks = 0
    while session.state == "playing":
        if seq is None:
            sol = solve(session.rows, session.cols,
                        [(a.row, a.col, a.direction) for a in session.board.arrows])
            if not sol:
                return False, clicks
            r, c, _ = sol[0]
        else:
            r, c, _ = seq[clicks]
        result, _, _ = session.click(r, c)
        clicks += 1
        if result == CLICK_BLOCKED:
            return False, clicks
    return session.state == "won", clicks


class TestBoard(unittest.TestCase):
    def test_path_clear(self):
        # (0,0) 朝右一路畅通
        a = Arrow(0, 0, Direction.RIGHT)
        b = Arrow(2, 2, Direction.UP)
        board = Board(4, 4, [a, b])
        self.assertTrue(board.path_clear(a))
        # b 上方 (1,2)、(0,2) 都空，畅通
        self.assertTrue(board.path_clear(b))

    def test_blocked(self):
        a = Arrow(0, 0, Direction.RIGHT)
        b = Arrow(0, 3, Direction.LEFT)
        board = Board(4, 4, [a, b])
        self.assertFalse(board.path_clear(a))
        self.assertFalse(board.path_clear(b))
        self.assertIs(board.blocker(a), b)
        self.assertIs(board.blocker(b), a)

    def test_vertical_and_diagonal_not_count(self):
        # 斜向的箭头不算阻挡
        a = Arrow(0, 0, Direction.DOWN)
        b = Arrow(2, 2, Direction.UP)
        board = Board(4, 4, [a, b])
        self.assertTrue(board.path_clear(a))
        self.assertTrue(board.path_clear(b))

    def test_remove(self):
        a = Arrow(0, 0, Direction.RIGHT)
        board = Board(3, 3, [a])
        board.remove(a)
        self.assertEqual(board.alive_count(), 0)
        self.assertIsNone(board.grid[0][0])


class TestSession(unittest.TestCase):
    LAYOUT = (
        "→···\n"
        "→·↑·\n"
        "·↓··\n"
        "··←·"
    )

    def test_fly_click(self):
        s = session_from_layout(self.LAYOUT)
        result, arrow, _ = s.click(0, 0)
        self.assertEqual(result, CLICK_FLY)
        self.assertIsNone(s.board.grid[0][0])
        self.assertEqual(s.cleared, 1)
        self.assertEqual(s.score, 100)  # 通关前只有基础分，时间奖励结算时才加
        self.assertEqual(s.combo, 1)

    def test_blocked_click_costs_mistake(self):
        s = session_from_layout(self.LAYOUT)
        # (1,0) 朝右，被 (1,2) 挡住
        result, arrow, blocker = s.click(1, 0)
        self.assertEqual(result, CLICK_BLOCKED)
        self.assertIsNotNone(blocker)
        self.assertEqual(s.mistakes_left, 2)
        self.assertEqual(s.combo, 0)
        self.assertEqual(s.board.alive_count(), 5)

    def test_empty_click(self):
        s = session_from_layout(self.LAYOUT)
        result, _, _ = s.click(3, 3)
        self.assertEqual(result, "empty")

    def test_three_mistakes_lose(self):
        s = session_from_layout(self.LAYOUT)
        for _ in range(3):
            s.click(1, 0)  # 一直撞
        self.assertEqual(s.state, "lost")
        self.assertEqual(s.lose_reason, "mistake")

    def test_timeout_lose(self):
        s = session_from_layout(self.LAYOUT, time_limit=1)
        s.update(1.5)
        self.assertEqual(s.state, "lost")
        self.assertEqual(s.lose_reason, "timeout")

    def test_combo_score(self):
        s = session_from_layout(self.LAYOUT)
        s.click(0, 0)  # 第 1 支：100
        s.click(2, 1)  # 第 2 支：100 + 50 连击加成
        s.click(3, 2)  # 第 3 支：100 + 100 连击加成
        self.assertEqual(s.best_combo, 3)
        self.assertEqual(s.score, 100 + 150 + 200)

    def test_combo_resets_on_block(self):
        s = session_from_layout(self.LAYOUT)
        s.click(0, 0)
        s.click(1, 0)  # 撞
        self.assertEqual(s.combo, 0)

    def test_undo_fly(self):
        s = session_from_layout(self.LAYOUT)
        s.click(0, 0)
        self.assertIsNone(s.board.grid[0][0])
        self.assertTrue(s.undo())
        self.assertIsNotNone(s.board.grid[0][0])
        self.assertEqual(s.cleared, 0)
        self.assertEqual(s.score, 0)

    def test_undo_refunds_mistake(self):
        s = session_from_layout(self.LAYOUT)
        s.click(1, 0)
        self.assertEqual(s.mistakes_left, 2)
        s.undo()
        self.assertEqual(s.mistakes_left, 3)

    def test_win_and_stars(self):
        s = session_from_layout(self.LAYOUT)
        ok, _ = autoplay(s)
        self.assertTrue(ok)
        self.assertEqual(s.state, "won")
        self.assertEqual(s.stars(), 3)  # 自动通关无碰撞 → 3 星

    def test_hint_points_to_free_arrow(self):
        s = session_from_layout(self.LAYOUT)
        arrow = s.use_hint()
        self.assertIsNotNone(arrow)
        self.assertTrue(s.board.path_clear(arrow))
        self.assertEqual(s.hints_left, 2)


class TestLevels(unittest.TestCase):
    def test_all_builtin_levels_solvable(self):
        for level in all_levels():
            with self.subTest(level=level["name"]):
                sol = solve(level["rows"], level["cols"], level["arrows"])
                self.assertIsNotNone(sol, f"{level['name']} 无解")
                s = GameSession(level["rows"], level["cols"], level["arrows"],
                                time_limit=999, max_mistakes=3)
                ok, _ = autoplay(s, seq=sol)
                self.assertTrue(ok)
                self.assertEqual(s.board.alive_count(), 0)

    def test_random_levels_solvable(self):
        for i in range(6):
            level = make_random_level(i)
            sol = solve(level["rows"], level["cols"], level["arrows"])
            self.assertIsNotNone(sol)
            s = GameSession(level["rows"], level["cols"], level["arrows"],
                            time_limit=999)
            ok, _ = autoplay(s, seq=sol)
            self.assertTrue(ok)

    def test_reverse_generate_performance(self):
        # 7x7、22 支箭必须在短时间内生成完成
        t0 = time.time()
        arrows = reverse_generate(7, 7, 22, seed=412)
        self.assertEqual(len(arrows), 22)
        self.assertLess(time.time() - t0, 3.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
