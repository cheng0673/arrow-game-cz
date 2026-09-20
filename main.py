# -*- coding: utf-8 -*-
"""
一箭又 Arrow（一箭又一箭）—— Python + Pygame 实现

玩法：
  点击棋盘上的箭头，若它前进方向到边界之间没有其它箭头，就飞出消除；
  否则碰撞提示并失去一次失误机会。清空全部箭头通关，失误用完 / 超时失败。

运行：python main.py
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

import pygame

from levels import all_levels, make_random_level
from model import CLICK_BLOCKED, CLICK_FLY, Direction, GameSession
from sounds import SoundManager

# ============================== 基础配置 ==============================
WIDTH, HEIGHT = 920, 920
FPS = 60
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_PATH = os.path.join(BASE_DIR, "save.json")

# 糖果配色（鲜艳）
BG_TOP = (122, 219, 255)
BG_BOTTOM = (255, 183, 230)
INK = (58, 46, 92)
WHITE = (255, 255, 255)

DIR_STYLE = {
    Direction.UP: ((255, 138, 177), (224, 49, 117)),     # 草莓粉
    Direction.DOWN: ((96, 190, 255), (35, 132, 224)),    # 苏打蓝
    Direction.LEFT: ((93, 226, 170), (24, 176, 125)),    # 薄荷绿
    Direction.RIGHT: ((255, 206, 84), (245, 158, 11)),   # 芒果黄
}
DIR_RED = ((255, 130, 130), (214, 40, 40))

# 四个方向对应四种表情：上=喜，下=怒，左=哀，右=乐
DIRECTION_FACE = {
    Direction.UP: "happy",
    Direction.DOWN: "angry",
    Direction.LEFT: "sad",
    Direction.RIGHT: "joy",
}

BUTTON_STYLE = {
    "pink": ((255, 143, 183), (232, 62, 130)),
    "mint": ((102, 232, 178), (22, 178, 128)),
    "blue": ((110, 190, 255), (44, 132, 226)),
    "purple": ((190, 159, 255), (134, 92, 224)),
    "orange": ((255, 190, 92), (242, 146, 20)),
    "gray": ((226, 228, 242), (184, 188, 210)),
}


# ============================== 工具函数 ==============================
def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ease_out_back(t):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_out(t):
    return 1 - (1 - t) ** 3


_font_cache: dict = {}


def get_font(size, bold=True):
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]
    font = None
    for name in ("msyhbd.ttc", "msyh.ttc", "simhei.ttf", "Deng.ttf"):
        path = os.path.join("C:/Windows/Fonts", name)
        if os.path.exists(path):
            try:
                font = pygame.font.Font(path, size)
                break
            except Exception:
                pass
    if font is None:
        font = pygame.font.SysFont("microsoftyahei,simhei", size, bold=bold)
    _font_cache[key] = font
    return font


_surf_cache: dict = {}


def jelly_surface(w, h, top, bottom, radius=24, shadow=6, gloss=True, outline=None):
    """生成立体果冻质感的圆角矩形（带投影、渐变、高光、描边）。"""
    key = ("jelly", w, h, top, bottom, radius, shadow, gloss, outline)
    if key in _surf_cache:
        return _surf_cache[key]
    w, h = int(w), int(h)
    surf = pygame.Surface((w + shadow, h + shadow * 2), pygame.SRCALPHA)
    # 竖向渐变
    grad = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        pygame.draw.line(grad, lerp(top, bottom, y / max(1, h - 1)), (0, y), (w, y))
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
    grad.blit(mask, (0, 0), None, pygame.BLEND_RGBA_MULT)
    # 投影
    if shadow:
        sh = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(sh, (50, 35, 80, 70), (0, 0, w, h), border_radius=radius)
        surf.blit(sh, (0, shadow))
    surf.blit(grad, (0, 0))
    # 顶部高光
    if gloss:
        band = pygame.Surface((w, h), pygame.SRCALPHA)
        gh = max(8, int(h * 0.38))
        pygame.draw.rect(band, (255, 255, 255, 78),
                         (4, 3, w - 8, gh), border_radius=max(4, radius - 4))
        band.blit(mask, (0, 0), None, pygame.BLEND_RGBA_MULT)
        surf.blit(band, (0, 0))
    # 描边
    if outline:
        pygame.draw.rect(surf, outline, (0, 0, w, h), 3, border_radius=radius)
    _surf_cache[key] = surf
    return surf


_arrow_cache: dict = {}


def arrow_surface(size, top, bottom, face="happy"):
    """画一支朝右的胖嘟嘟立体箭头，旋转即可表示其它方向。
    face: happy=喜(微笑) / joy=乐(大笑) / angry=怒 / sad=哀"""
    key = ("arrow", int(size), top, bottom, face)
    if key in _arrow_cache:
        return _arrow_cache[key]
    s = int(size)
    surf = pygame.Surface((s + 10, s + 10), pygame.SRCALPHA)
    cx = (s + 10) / 2
    cy = (s + 10) / 2
    # 单位坐标点（胖箭头）
    pts = [(0.10, 0.34), (0.46, 0.34), (0.46, 0.20), (0.90, 0.50),
           (0.46, 0.80), (0.46, 0.66), (0.10, 0.66)]
    poly = [(5 + x * s, 5 + y * s) for x, y in pts]

    def shape_on(target, color, scale=1.0, offset=(0, 0)):
        pp = [(cx + (px - cx) * scale + offset[0],
               cy + (py - cy) * scale + offset[1]) for px, py in poly]
        pygame.draw.polygon(target, color, pp)

    # 投影
    sh = pygame.Surface((s + 10, s + 10), pygame.SRCALPHA)
    shape_on(sh, (50, 35, 80, 80), 1.0, (3, 5))
    surf.blit(sh, (0, 0))
    # 深色描边底层（略微放大）
    shape_on(surf, lerp(bottom, (0, 0, 0), 0.35), 1.07)
    # 渐变主体：用多边形做遮罩
    body = pygame.Surface((s + 10, s + 10), pygame.SRCALPHA)
    grad = pygame.Surface((s + 10, s + 10), pygame.SRCALPHA)
    for y in range(s + 10):
        pygame.draw.line(grad, lerp(top, bottom, y / (s + 9)), (0, y), (s + 10, y))
    mask = pygame.Surface((s + 10, s + 10), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), poly)
    grad.blit(mask, (0, 0), None, pygame.BLEND_RGBA_MULT)
    body = grad
    surf.blit(body, (0, 0))
    # 高光（沿箭头背部）
    hl = pygame.Surface((s + 10, s + 10), pygame.SRCALPHA)
    hl_pts = [(0.18, 0.38), (0.44, 0.38), (0.44, 0.30),
              (0.70, 0.46), (0.44, 0.46), (0.18, 0.46)]
    hl_poly = [(5 + x * s, 5 + y * s) for x, y in hl_pts]
    pygame.draw.polygon(hl, (255, 255, 255, 90), hl_poly)
    hl.blit(mask, (0, 0), None, pygame.BLEND_RGBA_MULT)
    surf.blit(hl, (0, 0))
    # 可爱大表情（画在箭头宽宽的身体上，跟箭头一起旋转）
    # face: happy=喜(微笑) / joy=乐(眯眼大笑) / angry=怒(皱眉) / sad=哀(含泪)
    ink = (74, 47, 91)
    eye_r = max(3, int(s * 0.078))
    ey = 5 + int(0.455 * s)
    for ex in (0.195, 0.365):
        ex_px = 5 + int(ex * s)
        if face == "joy":
            # 眯眯笑眼 ^ ^
            r = pygame.Rect(int(ex_px - eye_r * 1.2), int(ey - eye_r),
                            int(eye_r * 2.4), int(eye_r * 2.1))
            pygame.draw.arc(surf, ink, r, math.radians(200), math.radians(340),
                            max(2, s // 22))
        else:
            pygame.draw.circle(surf, ink, (ex_px, ey), eye_r)
            pygame.draw.circle(surf, WHITE,
                               (int(ex_px - eye_r * 0.3), int(ey - eye_r * 0.3)),
                               max(1, int(eye_r * 0.4)))
    mx = 5 + int(0.28 * s)   # 嘴巴中心
    my = 5 + int(0.57 * s)
    R = max(3, int(0.085 * s))
    mw = max(2, s // 20)
    if face == "happy":
        pygame.draw.arc(surf, ink,
                        pygame.Rect(mx - R, my - int(R * 0.85), 2 * R, int(R * 1.7)),
                        math.radians(30), math.radians(150), mw)
    elif face == "joy":
        # 张嘴大笑（下半圆）+ 小舌头
        pts = [(mx + int(R * math.cos(math.radians(a))),
                my + int(R * math.sin(math.radians(a))))
               for a in range(0, 181, 10)]
        pygame.draw.polygon(surf, ink, pts)
        pygame.draw.circle(surf, (240, 110, 130),
                           (mx, my + int(R * 0.5)), max(2, int(R * 0.45)))
    elif face == "angry":
        # 憋嘴 + 皱眉
        pygame.draw.line(surf, ink, (mx - int(R * 0.7), my),
                         (mx + int(R * 0.7), my), mw)
        pygame.draw.line(surf, ink, (5 + int(0.125 * s), 5 + int(0.35 * s)),
                         (5 + int(0.25 * s), 5 + int(0.40 * s)), mw)
        pygame.draw.line(surf, ink, (5 + int(0.435 * s), 5 + int(0.35 * s)),
                         (5 + int(0.31 * s), 5 + int(0.40 * s)), mw)
    elif face == "sad":
        # 撇嘴 + 眼泪
        pygame.draw.arc(surf, ink,
                        pygame.Rect(mx - R, my - int(R * 0.7), 2 * R, int(R * 1.4)),
                        math.radians(200), math.radians(340), mw)
        pygame.draw.circle(surf, (130, 190, 255),
                           (5 + int(0.42 * s), 5 + int(0.545 * s)),
                           max(2, int(0.035 * s)))
    # 腮红
    if face in ("happy", "joy", "angry"):
        cheek = (255, 150, 165, 130) if face != "angry" else (255, 120, 110, 145)
        for cx in (0.165, 0.40):
            pygame.draw.circle(surf, cheek,
                               (5 + int(cx * s), 5 + int(0.555 * s)),
                               max(2, int(0.055 * s)))
    _arrow_cache[key] = surf
    return surf


def rotated_arrow(size, direction, red=False, face="happy"):
    top, bottom = DIR_RED if red else DIR_STYLE[direction]
    surf = arrow_surface(size, top, bottom, face)
    if direction.angle:
        surf = pygame.transform.rotate(surf, -direction.angle)
    return surf


def star_surface(size, color=((255, 224, 102), (245, 170, 20)), gray=False):
    key = ("star", int(size), gray)
    if key not in _surf_cache:
        s = int(size)
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        if gray:
            top, bottom = (225, 228, 238), (196, 200, 216)
        else:
            top, bottom = color
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rad = s * 0.46 if i % 2 == 0 else s * 0.21
            pts.append((s / 2 + rad * math.cos(ang), s / 2 + rad * math.sin(ang)))
        sh = pygame.Surface((s, s), pygame.SRCALPHA)
        pygame.draw.polygon(sh, (50, 35, 80, 70),
                            [(p[0] + 2, p[1] + 4) for p in pts])
        surf.blit(sh, (0, 0))
        grad = pygame.Surface((s, s), pygame.SRCALPHA)
        for y in range(s):
            pygame.draw.line(grad, lerp(top, bottom, y / max(1, s - 1)), (0, y), (s, y))
        mask = pygame.Surface((s, s), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255), pts)
        grad.blit(mask, (0, 0), None, pygame.BLEND_RGBA_MULT)
        surf.blit(grad, (0, 0))
        pygame.draw.polygon(surf, lerp(bottom, (0, 0, 0), 0.25), pts, 2)
        pygame.draw.circle(surf, (255, 255, 255, 110), (int(s * 0.38), int(s * 0.34)),
                           max(2, int(s * 0.08)))
        _surf_cache[key] = surf
    return _surf_cache[key]


def heart_surface(size, filled=True):
    key = ("heart", int(size), filled)
    if key not in _surf_cache:
        s = int(size)
        surf = pygame.Surface((s, s + 4), pygame.SRCALPHA)
        if filled:
            top, bottom = (255, 120, 150), (220, 44, 90)
        else:
            top, bottom = (214, 216, 228), (184, 188, 204)
        r = s * 0.26
        c1 = (s * 0.36, s * 0.34)
        c2 = (s * 0.64, s * 0.34)
        pygame.draw.circle(surf, bottom, (int(c1[0] + 1), int(c1[1] + 3)), int(r))
        pygame.draw.circle(surf, bottom, (int(c2[0] + 1), int(c2[1] + 3)), int(r))
        pygame.draw.polygon(surf, bottom, [
            (s * 0.12 + 1, s * 0.42 + 3), (s * 0.88 + 1, s * 0.42 + 3),
            (s * 0.5 + 1, s * 0.92 + 3)])
        for c in (c1, c2):
            pygame.draw.circle(surf, top, (int(c[0]), int(c[1])), int(r))
        pygame.draw.polygon(surf, top, [
            (s * 0.12, s * 0.42), (s * 0.5, s * 0.62), (s * 0.88, s * 0.42),
            (s * 0.5, s * 0.88)])
        if filled:
            pygame.draw.circle(surf, (255, 255, 255, 120),
                               (int(s * 0.34), int(s * 0.26)), max(2, int(s * 0.07)))
        _surf_cache[key] = surf
    return _surf_cache[key]


# ---------- 吉祥物（程序手绘线稿风） ----------
def _ear_surface(tilt):
    """一只长耳朵，tilt 控制旋转角度。"""
    ear = pygame.Surface((34, 64), pygame.SRCALPHA)
    ink = (64, 58, 74)
    pygame.draw.ellipse(ear, ink, (2, 2, 30, 60))
    pygame.draw.ellipse(ear, (255, 255, 255), (7, 7, 20, 50))
    pygame.draw.ellipse(ear, (255, 214, 224), (11, 12, 12, 38))
    if tilt:
        ear = pygame.transform.rotate(ear, tilt)
    return ear


def bunny_praise_surface():
    """通关用：举着两块「棒」牌子的小兔子。"""
    if "bunny" in _surf_cache:
        return _surf_cache["bunny"]
    W, H = 262, 152
    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    ink = (64, 58, 74)
    cx = W // 2
    sign_y = 92

    # 手臂（先画，会被身体和牌子盖住接头）
    for sx, arm_end in ((40, 76), (222, 186)):
        pygame.draw.line(surf, ink, (arm_end, 88), (sx + (35 if sx < cx else -35), 84), 13)
        pygame.draw.circle(surf, ink, (arm_end, 88), 7)

    # 两只长耳朵
    surf.blit(_ear_surface(11), (cx - 32, 8))
    surf.blit(_ear_surface(-11), (cx - 2, 8))

    # 头 / 身体
    head = pygame.Rect(0, 0, 96, 82)
    head.center = (cx, 86)
    pygame.draw.ellipse(surf, ink, head)
    pygame.draw.ellipse(surf, (255, 255, 255), head.inflate(-11, -11))

    # 眼睛（竖向小椭圆）
    for ex in (cx - 13, cx + 13):
        pygame.draw.ellipse(surf, ink, (ex - 5, 78, 10, 15))
        pygame.draw.circle(surf, WHITE, (ex - 1, 82), 2)
    # 小鼻子 + 嘴巴
    pygame.draw.polygon(surf, ink, [(cx, 95), (cx - 5, 99), (cx + 5, 99)])
    pygame.draw.line(surf, ink, (cx, 99), (cx, 103), 3)
    pygame.draw.arc(surf, ink, (cx - 9, 99, 9, 9), 0, math.pi / 1.6, 3)
    pygame.draw.arc(surf, ink, (cx, 99, 9, 9), math.pi / 2.6, math.pi, 3)

    # 两块「棒」牌子
    for sx in (40, 222):
        rect = pygame.Rect(0, 0, 70, 88)
        rect.center = (sx, sign_y)
        pygame.draw.rect(surf, ink, rect, border_radius=22)
        pygame.draw.rect(surf, (255, 255, 255), rect.inflate(-11, -11),
                         border_radius=17)
        bang = get_font(38).render("棒", True, ink)
        surf.blit(bang, bang.get_rect(center=(sx, sign_y + 1)))

    _surf_cache["bunny"] = surf
    return surf


def cheer_cat_surface(size=166):
    """失败页用：举高手臂、元气满满为你加油的小猫咪贴纸。"""
    key = ("cheer_cat", size)
    if key in _surf_cache:
        return _surf_cache[key]
    B = 190  # 基础画布
    surf = pygame.Surface((B, B), pygame.SRCALPHA)
    ink = (58, 54, 66)

    # 白色贴纸边 + 粉色底
    pygame.draw.rect(surf, WHITE, (0, 0, B, B), border_radius=34)
    pygame.draw.rect(surf, (255, 233, 240), (8, 8, B - 16, B - 16), border_radius=27)

    # 漫画感短斜线
    for (x1, y1), (x2, y2) in (
        ((22, 66), (44, 58)), ((16, 116), (40, 110)), ((28, 152), (47, 141)),
        ((168, 22), (182, 40)), ((172, 150), (184, 134))):
        pygame.draw.line(surf, ink, (x1, y1), (x2, y2), 4)

    # 举高的手臂（深色粗线打底，白线在内）
    pts = [(76, 102), (58, 76), (48, 42)]
    for i in range(len(pts) - 1):
        pygame.draw.line(surf, ink, pts[i], pts[i + 1], 23)
    for p in pts:
        pygame.draw.circle(surf, ink, p, 12)
    for i in range(len(pts) - 1):
        pygame.draw.line(surf, WHITE, pts[i], pts[i + 1], 14)
    for p in pts:
        pygame.draw.circle(surf, WHITE, p, 7)

    # 两只耳朵
    for tri in ([(70, 78), (81, 38), (107, 65)], [(150, 78), (139, 38), (113, 65)]):
        pygame.draw.polygon(surf, WHITE, tri)
        pygame.draw.polygon(surf, ink, tri, 4)
        inner = [(tri[0][0] * 0.35 + tri[2][0] * 0.65,
                  tri[0][1] * 0.35 + tri[2][1] * 0.65),
                 (tri[1][0], tri[1][1] + 12),
                 (tri[2][0] * 0.35 + tri[0][0] * 0.65,
                  tri[2][1] * 0.35 + tri[0][1] * 0.65)]
        pygame.draw.polygon(surf, (255, 200, 214), inner)

    # 身体（在头后面）
    body = pygame.Rect(0, 0, 66, 42)
    body.center = (110, 152)
    pygame.draw.ellipse(surf, ink, body)
    pygame.draw.ellipse(surf, WHITE, body.inflate(-9, -9))

    # 头
    head = pygame.Rect(0, 0, 98, 82)
    head.center = (110, 104)
    pygame.draw.ellipse(surf, ink, head)
    pygame.draw.ellipse(surf, WHITE, head.inflate(-9, -9))

    # 腮红
    for cx in (90, 130):
        pygame.draw.ellipse(surf, (255, 178, 198), (cx - 12, 108, 24, 16))
    # 笑眯眯的眼睛（><）
    pygame.draw.line(surf, ink, (95, 99), (104, 106), 4)
    pygame.draw.line(surf, ink, (125, 99), (116, 106), 4)
    # 小嘴巴（倒 Y）
    pygame.draw.line(surf, ink, (110, 113), (105, 119), 3)
    pygame.draw.line(surf, ink, (110, 113), (115, 119), 3)

    # 右侧小尾巴 / 爪子
    pygame.draw.circle(surf, ink, (152, 150), 13)
    pygame.draw.circle(surf, WHITE, (152, 150), 8)
    pygame.draw.line(surf, ink, (149, 147), (155, 153), 3)

    # 黄色四角星光
    sx, sy = 152, 40
    spts = []
    for i in range(8):
        ang = -math.pi / 2 + i * math.pi / 4
        rad = 21 if i % 2 == 0 else 9
        spts.append((sx + rad * math.cos(ang), sy + rad * math.sin(ang)))
    pygame.draw.polygon(surf, ink, spts, 3)
    pygame.draw.polygon(surf, (255, 238, 92), spts)
    # 侧边感叹小点
    pygame.draw.circle(surf, ink, (170, 102), 3)
    pygame.draw.circle(surf, ink, (175, 118), 2)
    pygame.draw.line(surf, ink, (168, 128), (176, 128), 3)

    if size != B:
        surf = pygame.transform.smoothscale(surf, (size, size))
    _surf_cache[key] = surf
    return surf


# ============================== UI 组件 ==============================
class Button:
    def __init__(self, rect, text, style="pink", size=26, icon=None, enabled=True):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.style = style
        self.font = get_font(size)
        self.icon = icon
        self.enabled = enabled
        self.hover = False
        self.press_t = 0.0

    def handle_event(self, event, sounds):
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                sounds.play("click")
                return True
        return False

    def draw(self, surf, dt):
        top, bottom = BUTTON_STYLE[self.style]
        if not self.enabled:
            top, bottom = (214, 216, 226), (184, 188, 204)
        scale = 1.0
        if self.hover and self.enabled:
            self.press_t = min(1, self.press_t + dt * 10)
            scale = round((1.0 + 0.05 * ease_out(self.press_t)) * 50) / 50
        else:
            self.press_t = max(0, self.press_t - dt * 10)
        w = int(self.rect.w * scale)
        h = int(self.rect.h * scale)
        x = self.rect.centerx - w // 2
        y = self.rect.centery - h // 2 + (3 if self.hover else 0)
        body = jelly_surface(w, h, top, bottom, radius=h // 2, shadow=7,
                             outline=lerp(bottom, (0, 0, 0), 0.25))
        surf.blit(body, (x, y - 6))
        cx, cy = self.rect.centerx, self.rect.centery + (3 if self.hover else 0)
        if self.icon:
            icon_surf = self._make_icon(self.icon, int(h * 0.46))
            total = icon_surf.get_width() + (self.font.size(self.text)[0] + 10 if self.text else 0)
            start = cx - total // 2
            surf.blit(icon_surf, (start, cy - icon_surf.get_height() // 2))
            tx = start + icon_surf.get_width() + 10
        else:
            tx = None
        if self.text:
            txt = self.font.render(self.text, True, WHITE)
            if tx is None:
                tx = cx - txt.get_width() // 2
            surf.blit(txt, (tx, cy - txt.get_height() // 2))

    @staticmethod
    def _make_icon(kind, s):
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        w = max(3, s // 8)
        if kind == "play":
            pygame.draw.polygon(surf, WHITE, [(s * 0.28, s * 0.2), (s * 0.28, s * 0.8),
                                              (s * 0.82, s * 0.5)])
        elif kind == "back":
            pygame.draw.polygon(surf, WHITE, [(s * 0.72, s * 0.2), (s * 0.18, s * 0.5),
                                              (s * 0.72, s * 0.8)])
        elif kind == "pause":
            pygame.draw.rect(surf, WHITE, (s * 0.26, s * 0.2, s * 0.16, s * 0.6),
                             border_radius=3)
            pygame.draw.rect(surf, WHITE, (s * 0.58, s * 0.2, s * 0.16, s * 0.6),
                             border_radius=3)
        elif kind == "home":
            pygame.draw.polygon(surf, WHITE, [(s * 0.5, s * 0.14), (s * 0.88, s * 0.46),
                                              (s * 0.74, s * 0.46), (s * 0.74, s * 0.84),
                                              (s * 0.26, s * 0.84), (s * 0.26, s * 0.46),
                                              (s * 0.12, s * 0.46)])
        elif kind == "bulb":
            pygame.draw.circle(surf, WHITE, (s // 2, int(s * 0.42)), int(s * 0.28), w)
            pygame.draw.line(surf, WHITE, (s * 0.38, s * 0.72), (s * 0.62, s * 0.72), w)
            pygame.draw.line(surf, WHITE, (s * 0.42, s * 0.82), (s * 0.58, s * 0.82), w)
        elif kind == "undo":
            pygame.draw.arc(surf, WHITE, (s * 0.14, s * 0.2, s * 0.6, s * 0.6),
                            math.radians(-60), math.radians(200), w)
            pygame.draw.polygon(surf, WHITE, [(s * 0.12, s * 0.5), (s * 0.34, s * 0.34),
                                              (s * 0.30, s * 0.58)])
        elif kind == "dice":
            pygame.draw.rect(surf, WHITE, (s * 0.18, s * 0.18, s * 0.64, s * 0.64),
                             w, border_radius=4)
            for px, py in ((0.34, 0.34), (0.66, 0.34), (0.5, 0.5),
                           (0.34, 0.66), (0.66, 0.66)):
                pygame.draw.circle(surf, WHITE, (int(s * px), int(s * py)), max(2, s // 14))
        return surf


# ============================== 动态背景 ==============================
class Background:
    def __init__(self):
        self.grad = pygame.Surface((WIDTH, HEIGHT))
        for y in range(HEIGHT):
            t = y / HEIGHT
            pygame.draw.line(self.grad, lerp(BG_TOP, BG_BOTTOM, t), (0, y), (WIDTH, y))
        rng = random.Random(7)
        self.blobs = []
        for _ in range(6):
            self.blobs.append([
                rng.uniform(0, WIDTH), rng.uniform(0, HEIGHT),
                rng.uniform(90, 200), rng.uniform(0, 6.28),
                rng.choice([(255, 255, 255), (180, 240, 255), (255, 220, 245)])
            ])
        self.stars = [(rng.uniform(20, WIDTH - 20), rng.uniform(20, HEIGHT - 20),
                       rng.uniform(2, 4), rng.uniform(0, 6.28)) for _ in range(36)]
        # 上升气泡：x, 初始y, 半径, 上升速度
        self.bubbles = [(rng.uniform(0, WIDTH), rng.uniform(0, HEIGHT),
                         rng.uniform(9, 24), rng.uniform(20, 60)) for _ in range(14)]
        # 漂移云朵：x, y, 缩放, 速度
        self.clouds = [(rng.uniform(0, WIDTH), rng.uniform(60, HEIGHT - 260),
                        rng.uniform(0.7, 1.5), rng.uniform(10, 24)) for _ in range(5)]
        self.layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

    def _cloud(self, x, y, sc):
        for dx, dy, r in ((0, 0, 44), (40, -14, 32), (78, 2, 38),
                          (-38, 8, 30), (38, 14, 30)):
            pygame.draw.circle(self.layer, (255, 255, 255, 55),
                               (int(x + dx * sc), int(y + dy * sc)), int(r * sc))

    def draw(self, surf, t):
        self.layer.fill((0, 0, 0, 0))
        # 云朵缓缓向右漂移
        for cx, cy, sc, spd in self.clouds:
            x = (cx + spd * t) % (WIDTH + 380) - 190
            y = cy + math.sin(t * 0.4 + cx) * 10
            self._cloud(x, y, sc)
        for x, y, r, phase, color in self.blobs:
            bx = x + math.sin(t * 0.35 + phase) * 36
            by = y + math.cos(t * 0.28 + phase) * 24
            pygame.draw.circle(self.layer, (*color, 38), (int(bx), int(by)), int(r))
        for x, y, r, phase in self.stars:
            tw = 0.4 + 0.6 * abs(math.sin(t * 2.2 + phase))
            pygame.draw.circle(self.layer, (255, 255, 255, int(120 * tw)),
                               (int(x), int(y)), int(r))
        # 从底部不断升起、左右轻摆的气泡
        for bx, by0, r, spd in self.bubbles:
            y = (by0 - spd * t) % (HEIGHT + 120) - 60
            x = bx + math.sin(t * 0.9 + by0) * 16
            pygame.draw.circle(self.layer, (255, 255, 255, 26),
                               (int(x), int(y)), int(r))
            pygame.draw.circle(self.layer, (255, 255, 255, 80),
                               (int(x), int(y)), int(r), 2)
            pygame.draw.circle(self.layer, (255, 255, 255, 110),
                               (int(x - r * 0.35), int(y - r * 0.35)),
                               max(1, int(r * 0.18)))
        surf.blit(self.grad, (0, 0))
        surf.blit(self.layer, (0, 0))


# ============================== 粒子 / 浮字 ==============================
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color",
                 "gravity", "spin", "rot", "shape")

    def __init__(self, x, y, vx, vy, life, size, color, gravity=380, shape="star"):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.size, self.color, self.gravity = size, color, gravity
        self.spin = random.uniform(-6, 6)
        self.rot = random.uniform(0, 6.28)
        self.shape = shape

    def update(self, dt):
        self.vy += self.gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rot += self.spin * dt
        self.life -= dt

    def draw(self, surf):
        k = max(0, self.life / self.max_life)
        if self.shape == "circle":
            pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)),
                               max(1, int(self.size * k)))
            return
        s = int(self.size * (0.6 + 0.4 * k))
        if s < 4:
            return
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5 + self.rot
            rad = s * 0.5 if i % 2 == 0 else s * 0.22
            pts.append((self.x + rad * math.cos(ang), self.y + rad * math.sin(ang)))
        tmp = pygame.Surface((s * 2 + 2, s * 2 + 2), pygame.SRCALPHA)
        local = [(p[0] - self.x + s + 1, p[1] - self.y + s + 1) for p in pts]
        pygame.draw.polygon(tmp, (*self.color, int(230 * k)), local)
        surf.blit(tmp, (int(self.x - s - 1), int(self.y - s - 1)))


class FloatingText:
    def __init__(self, text, x, y, color, size=24, life=1.0):
        self.image = get_font(size).render(text, True, color)
        shadow = get_font(size).render(text, True, (255, 255, 255))
        self.x, self.y = x, y
        self.life = self.max_life = life
        self.image = image_with_outline(self.image, shadow)

    def update(self, dt):
        self.y -= 46 * dt
        self.life -= dt

    def draw(self, surf):
        k = max(0, self.life / self.max_life)
        self.image.set_alpha(int(255 * k))
        surf.blit(self.image, (self.x - self.image.get_width() // 2, int(self.y)))


def image_with_outline(img, white_img=None):
    w, h = img.get_size()
    out = pygame.Surface((w + 6, h + 6), pygame.SRCALPHA)
    if white_img:
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
            out.blit(white_img, (dx + 3, dy + 3))
    out.blit(img, (3, 3))
    return out


# ============================== 游戏进行场景 ==============================
class PlayState:
    FLY_TIME = 0.38
    HIT_TIME = 0.45

    def __init__(self, app, level, level_index=-1, seq=0):
        self.app = app
        self.level = level
        self.level_index = level_index  # -1 表示随机模式
        self.seq = seq
        self.session = GameSession(
            level["rows"], level["cols"], level["arrows"],
            time_limit=level["time_limit"], max_mistakes=level["mistakes"])
        rows, cols = level["rows"], level["cols"]
        board_w_max = WIDTH - 48
        board_h_max = HEIGHT - 250
        self.cell = int(min(board_w_max / cols, board_h_max / rows))
        bw, bh = self.cell * cols, self.cell * rows
        self.ox = (WIDTH - bw) // 2
        self.oy = 232 + (board_h_max - bh) // 2
        self.t = 0.0
        self.shake = 0.0
        self.flying = []       # dict(arrow, surf, x,y, trail, dist)
        self.hits = {}         # arrow_id -> 剩余时间
        self.particles = []
        self.texts = []
        self.rings = []        # 消除后的扩散圈
        self.hint_id = None
        self.hint_t = 0.0
        self.last_tick_sec = None
        self.result_delay = 0.0
        self.saved = False
        self.stars_shown = 0
        self.confetti_t = 0.0
        self.ended_sound = False
        self.paused = False

        btn_y = 168
        self.btn_hint = Button((24, btn_y, 128, 48), f"提示 {self.session.hints_left}",
                               "orange", 22, "bulb")
        self.btn_undo = Button((164, btn_y, 108, 48), "撤销", "blue", 22, "undo")
        self.btn_pause = Button((WIDTH - 248, btn_y, 100, 48), "暂停", "purple", 22, "pause")
        self.btn_home = Button((WIDTH - 136, btn_y, 112, 48), "主菜单", "gray", 20, "home")
        # 暂停面板里的静音小按钮
        self.btn_mute_p = pygame.Rect(0, 0, 56, 56)
        # 结算 / 暂停按钮
        self.btn_resume = Button((0, 0, 240, 64), "继续游戏", "mint", 26, "play")
        self.btn_restart_p = Button((0, 0, 240, 64), "重新开始", "blue", 26)
        self.btn_menu_p = Button((0, 0, 240, 64), "返回菜单", "gray", 24)
        self.btn_next = Button((0, 0, 220, 62), "下一关", "pink", 26)
        self.btn_replay = Button((0, 0, 200, 62), "再来一次", "mint", 24)
        self.btn_menu_r = Button((0, 0, 200, 62), "返回菜单", "gray", 24)

    # ---------- 工具 ----------
    def cell_rect(self, r, c, scale=1.0):
        size = int(self.cell * 0.90 * scale)
        cx = self.ox + c * self.cell + self.cell // 2
        cy = self.oy + r * self.cell + self.cell // 2
        return pygame.Rect(cx - size // 2, cy - size // 2, size, size)

    def cell_at(self, pos):
        x, y = pos
        c = (x - self.ox) // self.cell
        r = (y - self.oy) // self.cell
        if 0 <= r < self.level["rows"] and 0 <= c < self.level["cols"]:
            if self.cell_rect(r, c).collidepoint(pos):
                return r, c
        return None

    def busy(self):
        return bool(self.flying) or bool(self.hits)

    # ---------- 事件 ----------
    def handle_event(self, event):
        s = self.app.sounds
        hud_buttons = (self.btn_hint, self.btn_undo, self.btn_pause, self.btn_home)
        if self.paused:
            overlay = (self.btn_resume, self.btn_restart_p, self.btn_menu_p)
        elif self.session.state != "playing":
            overlay = [self.btn_replay, self.btn_menu_r]
            if self.session.state == "won":
                overlay = [self.btn_next] + overlay
        else:
            overlay = ()

        if event.type == pygame.MOUSEMOTION:
            for b in hud_buttons + tuple(overlay):
                b.hover = b.enabled and b.rect.collidepoint(event.pos)
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.session.state == "playing":
                self.paused = not self.paused
            return

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        if self.paused:
            if self.btn_mute_p.collidepoint(event.pos):
                muted = s.toggle_mute()
                self.app.save["muted"] = muted
                self.app._write_save()
            elif self.btn_resume.rect.collidepoint(event.pos):
                s.play("click")
                self.paused = False
            elif self.btn_restart_p.rect.collidepoint(event.pos):
                s.play("click")
                self.app.restart_play(self.level, self.level_index, self.seq)
            elif self.btn_menu_p.rect.collidepoint(event.pos):
                s.play("click")
                self.app.go_menu()
            return

        if self.session.state != "playing":
            self._handle_result_click(event.pos)
            return

        if self.btn_hint.rect.collidepoint(event.pos):
            if not self.busy():
                self._do_hint()
            return
        if self.btn_undo.rect.collidepoint(event.pos):
            if not self.busy() and self.session.can_undo():
                self.session.undo()
                s.play("undo")
                self.hint_id = None
            return
        if self.btn_pause.rect.collidepoint(event.pos):
            s.play("click")
            self.paused = True
            return
        if self.btn_home.rect.collidepoint(event.pos):
            s.play("click")
            self.app.go_menu()
            return
        if self.busy():
            return
        cell = self.cell_at(event.pos)
        if cell:
            self._do_click(*cell)

    def _do_hint(self):
        if self.session.hints_left <= 0 or self.busy():
            return
        arrow = self.session.use_hint()
        if arrow is not None:
            self.hint_id = arrow.id
            self.hint_t = 3.0
            self.app.sounds.play("hint")
            self.btn_hint.text = f"提示 {self.session.hints_left}"

    def _do_click(self, r, c):
        s = self.app.sounds
        result, arrow, blocker = self.session.click(r, c)
        if result == CLICK_FLY:
            s.play("fly")
            self._start_fly(arrow)
            self.rings.append((r, c, 0.0))
            self._burst(self.cell_rect(r, c).center,
                        DIR_STYLE[arrow.direction][0], 16)
            gain = 100 + (self.session.combo - 1) * 50
            cr = self.cell_rect(r, c)
            self.texts.append(FloatingText(f"+{gain}", cr.centerx, cr.centery - 10,
                                           (255, 120, 170), 26))
            if self.session.combo >= 2:
                self.texts.append(FloatingText(f"连击 x{self.session.combo}!",
                                               cr.centerx, cr.centery - 42,
                                               (134, 92, 224), 24, 0.9))
            if self.hint_id == arrow.id:
                self.hint_id = None
        elif result == CLICK_BLOCKED:
            s.play("collide")
            self.hits[arrow.id] = self.HIT_TIME
            self.shake = 10
            cr = self.cell_rect(r, c)
            self.texts.append(FloatingText("砰！被挡住啦", cr.centerx, cr.top - 8,
                                           (220, 60, 70), 24))
            self._burst(event_pos=cr.center, color=(255, 120, 120), n=10,
                        gravity=200, shape="circle")
            self.hint_id = None

    def _start_fly(self, arrow):
        size = int(self.cell * 0.80)
        surf = rotated_arrow(size, arrow.direction,
                             face=DIRECTION_FACE[arrow.direction])
        cr = self.cell_rect(arrow.row, arrow.col)
        x, y = cr.center
        if arrow.direction == Direction.RIGHT:
            dist = (self.ox + self.cell * self.level["cols"]) - x + self.cell * 1.6
        elif arrow.direction == Direction.LEFT:
            dist = x - self.ox + self.cell * 1.6
        elif arrow.direction == Direction.DOWN:
            dist = (self.oy + self.cell * self.level["rows"]) - y + self.cell * 1.6
        else:
            dist = y - self.oy + self.cell * 1.6
        self.flying.append({"surf": surf, "x": float(x), "y": float(y),
                            "p": 0.0, "dist": dist, "dir": arrow.direction,
                            "trail": []})

    def _burst(self, event_pos, color, n, gravity=420, shape="star"):
        x, y = event_pos
        for _ in range(n):
            ang = random.uniform(0, 6.283)
            spd = random.uniform(80, 320)
            col = random.choice([color, (255, 214, 84), (255, 255, 255),
                                 (134, 92, 224), (96, 190, 255)])
            self.particles.append(Particle(
                x, y, math.cos(ang) * spd, math.sin(ang) * spd - 60,
                random.uniform(0.5, 0.95), random.uniform(6, 12), col,
                gravity=gravity, shape=shape))

    # ---------- 更新 ----------
    def update(self, dt):
        s = self.app.sounds
        if self.paused:
            return
        self.t += dt
        self.session.update(dt)
        self.shake = max(0, self.shake - dt * 40)

        # 飞出动画
        for f in self.flying:
            f["p"] += dt / self.FLY_TIME
            ease = min(1, f["p"]) ** 2.4  # 加速
            d = f["dir"]
            f["x"] += d.dc * (f["dist"] / self.FLY_TIME * dt) * (0.5 + 2.2 * ease)
            f["y"] += d.dr * (f["dist"] / self.FLY_TIME * dt) * (0.5 + 2.2 * ease)
            f["trail"].append((f["x"], f["y"], 1.0))
            f["trail"] = [(x, y, a - dt * 4) for x, y, a in f["trail"] if a > 0][-7:]
        self.flying = [f for f in self.flying if f["p"] < 1]

        for aid in list(self.hits):
            self.hits[aid] -= dt
            if self.hits[aid] <= 0:
                del self.hits[aid]
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]
        for tx in self.texts:
            tx.update(dt)
        self.texts = [x for x in self.texts if x.life > 0]
        self.rings = [(r, c, p + dt / 0.45) for r, c, p in self.rings if p < 1]

        if self.hint_id is not None:
            self.hint_t -= dt
            if self.hint_t <= 0:
                self.hint_id = None

        # 倒计时滴答
        sec = math.ceil(self.session.time_left)
        if (self.session.state == "playing" and self.session.time_left <= 10
                and sec != self.last_tick_sec and sec > 0):
            s.play("tick")
        self.last_tick_sec = sec

        # 胜负
        if self.session.state != "playing":
            self.result_delay += dt
            if not self.ended_sound and self.result_delay > 0.4:
                s.play("win" if self.session.state == "won" else "lose")
                self.ended_sound = True
            if self.session.state == "won":
                target = self.session.stars()
                interval = 0.35
                if self.result_delay > 0.8 + interval * self.stars_shown and self.stars_shown < target:
                    self.stars_shown += 1
                    s.play("star")
                self.confetti_t += dt
                if self.confetti_t > 0.05 and self.stars_shown <= target:
                    self.confetti_t = 0
                    self._rain_one()
                if self.result_delay > 0.8 and self.level_index >= 0 and not self.saved:
                    self.saved = True
                    self.app.save_result(self.level_index, self.session.stars(),
                                         self.session.score)

    def _rain_one(self):
        x = random.uniform(40, WIDTH - 40)
        col = random.choice([(255, 120, 160), (96, 190, 255), (255, 206, 84),
                             (93, 226, 170), (180, 140, 255)])
        self.particles.append(Particle(
            x, -10, random.uniform(-30, 30), random.uniform(40, 120),
            random.uniform(1.6, 2.6), random.uniform(7, 12), col,
            gravity=120, shape=random.choice(["star", "circle"])))

    # ---------- 绘制 ----------
    def draw(self, surf, dt, mouse):
        self._draw_hud(surf, dt)
        ox, oy = self.ox, self.oy
        if self.shake:
            ox += int(random.uniform(-self.shake, self.shake))
            oy += int(random.uniform(-self.shake, self.shake))
        saved = (self.ox, self.oy)
        self.ox, self.oy = ox, oy
        self._draw_board(surf, dt, mouse)
        self.ox, self.oy = saved

        for p in self.particles:
            p.draw(surf)
        for tx in self.texts:
            tx.draw(surf)

        if self.session.state == "playing" and self.session.time_left <= 10 and not self.paused:
            pulse = int(30 + 40 * abs(math.sin(self.t * 6)))
            vign = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.rect(vign, (230, 40, 60, pulse), (0, 0, WIDTH, 70))
            pygame.draw.rect(vign, (230, 40, 60, pulse), (0, HEIGHT - 70, WIDTH, 70))
            pygame.draw.rect(vign, (230, 40, 60, pulse), (0, 0, 30, HEIGHT))
            pygame.draw.rect(vign, (230, 40, 60, pulse), (WIDTH - 30, 0, 30, HEIGHT))
            surf.blit(vign, (0, 0))

        if self.paused:
            self._draw_pause(surf, dt)
        elif self.session.state != "playing" and self.result_delay > 0.6:
            self._draw_result(surf, dt)

    def _draw_hud(self, surf, dt):
        # 顶部信息面板
        panel = jelly_surface(WIDTH - 48, 132, (255, 255, 255), (238, 244, 255),
                              radius=28, shadow=6, gloss=True)
        surf.blit(panel, (24, 18))
        title = get_font(28).render(self.level["name"], True, INK)
        surf.blit(title, (48, 30))
        remain = get_font(20).render(f"剩余箭头：{self.session.board.alive_count()}",
                                     True, (120, 110, 150))
        surf.blit(remain, (48, 74))
        total = self.session.board.alive_count() + self.session.cleared
        prog = self.session.cleared / max(1, total)
        bar = pygame.Rect(48, 110, 220, 14)
        pygame.draw.rect(surf, (226, 230, 244), bar, border_radius=7)
        if prog:
            fill = bar.copy()
            fill.width = max(14, int(bar.w * prog))
            pygame.draw.rect(surf, (93, 226, 170), fill, border_radius=7)

        # 爱心（失误次数）
        for i in range(self.session.max_mistakes):
            hs = heart_surface(40, filled=i < self.session.mistakes_left)
            surf.blit(hs, (WIDTH // 2 - 70 + i * 48, 56))

        # 分数（右上角，静音按钮在游戏中隐藏，不会重叠）
        score_txt = get_font(28).render(f"得分 {self.session.score}", True, (240, 120, 40))
        surf.blit(score_txt, score_txt.get_rect(top=56, right=WIDTH - 48))

        # 时间条（放在顶部面板内部，避开左右两侧按钮）
        tbar = pygame.Rect(300, 112, 432, 15)
        pygame.draw.rect(surf, (226, 230, 244), tbar, border_radius=7)
        frac = max(0, self.session.time_left / self.session.time_limit)
        if frac > 0.5:
            tcol = (93, 226, 170)
        elif frac > 0.25:
            tcol = (255, 196, 70)
        else:
            tcol = (235, 87, 109)
        if frac > 0:
            pygame.draw.rect(surf, tcol,
                             (tbar.x, tbar.y, max(15, int(tbar.w * frac)), tbar.h),
                             border_radius=7)
        sec = get_font(17).render(f"{math.ceil(self.session.time_left)} 秒", True, INK)
        surf.blit(sec, (tbar.right + 10, tbar.y - 3))

        for b in (self.btn_hint, self.btn_undo, self.btn_pause, self.btn_home):
            b.draw(surf, dt)

    def _draw_board(self, surf, dt, mouse):
        rows, cols = self.level["rows"], self.level["cols"]
        hover_cell = None
        if self.session.state == "playing" and not self.busy():
            hover_cell = self.cell_at(mouse) or (-1, -1)
        # 棋盘底板
        bw = self.cell * cols + 26
        bh = self.cell * rows + 26
        board_bg = jelly_surface(bw, bh, (255, 255, 255), (225, 235, 252),
                                 radius=30, shadow=10, gloss=True)
        surf.blit(board_bg, (self.ox - 13, self.oy - 13))

        pop_t = self.t
        for r in range(rows):
            for c in range(cols):
                delay = 0.025 * (r + c)
                k = min(1, max(0, (pop_t - delay) / 0.3))
                scale = round(ease_out_back(k) * 25) / 25  # 量化，避免缓存爆炸
                rect = self.cell_rect(r, c, scale=scale)
                tint = ((245, 249, 255) if (r + c) % 2 == 0 else (232, 240, 252))
                tile = jelly_surface(rect.w, rect.h, (255, 255, 255), tint,
                                     radius=max(10, rect.w // 6), shadow=4,
                                     gloss=True, outline=(214, 226, 248))
                surf.blit(tile, (rect.x, rect.y - 3))

        # 消除扩散圈
        for r, c, p in self.rings:
            rect = self.cell_rect(r, c)
            rad = int(rect.w * 0.5 * (1 + p * 0.9))
            ring = pygame.Surface((rad * 2 + 4, rad * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(ring, (255, 180, 210, max(0, int(180 * (1 - p)))),
                               (rad + 2, rad + 2), rad, 5)
            surf.blit(ring, (rect.centerx - rad - 2, rect.centery - rad - 2))

        # 箭头
        arrow_size = int(self.cell * 0.80)
        for arrow in self.session.board.arrows:
            rect = self.cell_rect(arrow.row, arrow.col)
            bob = math.sin(self.t * 3 + arrow.id) * 3
            scale = 1.0
            if hover_cell == (arrow.row, arrow.col):
                scale = 1.10
            scale = round(scale * 25) / 25
            hinted = self.hint_id == arrow.id
            if hinted:
                bob += math.sin(self.t * 9) * 4 - 3
                glow = int(90 + 70 * abs(math.sin(self.t * 6)))
                gs = pygame.Surface((rect.w + 26, rect.h + 26), pygame.SRCALPHA)
                pygame.draw.rect(gs, (255, 210, 80, glow),
                                 (0, 0, gs.get_width(), gs.get_height()),
                                 border_radius=24, width=6)
                surf.blit(gs, (rect.centerx - gs.get_width() // 2,
                               rect.centery - gs.get_height() // 2))
            img = rotated_arrow(int(arrow_size * scale), arrow.direction,
                                face=DIRECTION_FACE[arrow.direction])
            hitting = arrow.id in self.hits
            if hitting:
                ht = self.hits[arrow.id] / self.HIT_TIME
                dx = math.sin((1 - ht) * 50) * 7 * ht
                rect = rect.move(int(dx), 0)
            rect_img = img.get_rect(center=(rect.centerx, rect.centery + int(bob)))
            surf.blit(img, rect_img)
            if hitting:
                ht = self.hits[arrow.id] / self.HIT_TIME
                red = rotated_arrow(int(arrow_size * scale), arrow.direction, red=True,
                                    face=DIRECTION_FACE[arrow.direction])
                red.set_alpha(int(220 * ht))
                surf.blit(red, rect_img)

        # 飞出的箭头（加速 + 残影）
        for f in self.flying:
            for tx, ty, a in f["trail"][:-1]:
                ghost = f["surf"].copy()
                ghost.set_alpha(int(70 * a))
                gr = ghost.get_rect(center=(int(tx), int(ty)))
                surf.blit(ghost, gr)
            rr = f["surf"].get_rect(center=(int(f["x"]), int(f["y"])))
            surf.blit(f["surf"], rr)

    # ---------- 暂停 / 结算 ----------
    def _dim(self, surf, alpha=150):
        d = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        d.fill((70, 50, 110, alpha))
        surf.blit(d, (0, 0))

    def _draw_pause(self, surf, dt):
        self._dim(surf)
        panel = jelly_surface(440, 460, (255, 255, 255), (236, 242, 255),
                              radius=32, shadow=12)
        pr = panel.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        surf.blit(panel, pr)
        title = get_font(40).render("游戏暂停", True, INK)
        surf.blit(title, title.get_rect(center=(WIDTH // 2, pr.top + 80)))
        btns = [self.btn_resume, self.btn_restart_p, self.btn_menu_p]
        labels_y = [pr.top + 170, pr.top + 260, pr.top + 350]
        for b, y in zip(btns, labels_y):
            b.rect.center = (WIDTH // 2, y)
            b.draw(surf, dt)
        # 面板右上角静音开关
        self.btn_mute_p.center = (pr.right - 44, pr.top + 44)
        mbody = jelly_surface(56, 56, BUTTON_STYLE["purple"][0],
                              BUTTON_STYLE["purple"][1], radius=28, shadow=5)
        surf.blit(mbody, (self.btn_mute_p.x, self.btn_mute_p.y - 4))
        draw_speaker_icon(surf, self.btn_mute_p.center, self.app.sounds.muted, 28)

    def _draw_result(self, surf, dt):
        self._dim(surf, 120)
        won = self.session.state == "won"
        pw, ph = 500, 600 if won else 540
        panel = jelly_surface(pw, ph, (255, 255, 255),
                              (255, 240, 250) if won else (238, 242, 252),
                              radius=34, shadow=14)
        pr = panel.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        surf.blit(panel, pr)
        if won:
            # 举「棒」小兔子，弹入出场
            pop_k = min(1, max(0, (self.result_delay - 0.05) / 0.5))
            bunny = bunny_praise_surface()
            if 0 < pop_k < 1:
                sc = ease_out_back(pop_k)
                bunny = pygame.transform.rotozoom(bunny, 0, sc)
            if pop_k > 0:
                by = pr.top + 102 + math.sin(self.t * 2.2) * 3
                surf.blit(bunny, bunny.get_rect(center=(WIDTH // 2, int(by))))

            title = get_font(42).render("通关啦！你真棒！", True, (232, 62, 130))
            surf.blit(title, title.get_rect(center=(WIDTH // 2, pr.top + 192)))
            # 星星依次弹出
            for i in range(3):
                size = 84
                x = WIDTH // 2 + (i - 1) * 100
                y = pr.top + 282
                if i < self.stars_shown:
                    pop = min(1, (self.result_delay - 0.8 - i * 0.35) / 0.3)
                    size = int(84 * ease_out_back(pop))
                    star = star_surface(size)
                    surf.blit(star, star.get_rect(center=(x, y)))
                else:
                    star = star_surface(70, gray=True)
                    surf.blit(star, star.get_rect(center=(x, y)))
            score = get_font(28).render(f"得分：{self.session.score}", True, INK)
            surf.blit(score, score.get_rect(center=(WIDTH // 2, pr.top + 374)))
            combo = get_font(20).render(
                f"最高连击 x{self.session.best_combo}   剩余时间 {math.ceil(self.session.time_left)} 秒",
                True, (130, 120, 160))
            surf.blit(combo, combo.get_rect(center=(WIDTH // 2, pr.top + 414)))
            btns = [self.btn_next, self.btn_replay, self.btn_menu_r]
            has_next = (self.level_index >= 0 and self.level_index + 1 < len(self.app.levels)) \
                or self.level_index < 0
            self.btn_next.enabled = has_next
        else:
            # 加油小猫咪贴纸（轻轻上下浮动）
            cat = cheer_cat_surface(160)
            cy = pr.top + 120 + int(math.sin(self.t * 2.4) * 4)
            surf.blit(cat, cat.get_rect(center=(WIDTH // 2, cy)))
            reason = "失误用完啦" if self.session.lose_reason == "mistake" else "时间到啦"
            title = get_font(36).render(f"挑战失败（{reason}）", True, (90, 90, 130))
            surf.blit(title, title.get_rect(center=(WIDTH // 2, pr.top + 226)))
            # 鼓励的话
            encouragements = [
                ("别灰心呀，失败是成功之母～", (160, 120, 175)),
                ("小猫咪为你加油，", (150, 130, 170)),
                ("冷静观察、再来一次一定行！", (150, 130, 170)),
            ]
            y = pr.top + 274
            for text, color in encouragements:
                tip = get_font(20).render(text, True, color)
                surf.blit(tip, tip.get_rect(center=(WIDTH // 2, y)))
                y += 31
            btns = [self.btn_replay, self.btn_menu_r]
        if won:
            # 三个按钮缩窄，保证不超出 500 宽面板
            for b in btns:
                b.rect.width = 152
            gap = 162
        else:
            gap = 230
        start_x = WIDTH // 2 - (len(btns) - 1) * gap // 2
        for i, b in enumerate(btns):
            b.rect.center = (start_x + i * gap, pr.bottom - 64 if won else pr.bottom - 70)
            b.draw(surf, dt)

    def _handle_result_click(self, pos):
        s = self.app.sounds
        if self.session.state == "won":
            if self.btn_next.enabled and self.btn_next.rect.collidepoint(pos):
                s.play("click")
                if self.level_index < 0:
                    self.app.start_random(self.seq + 1)
                else:
                    self.app.start_level(self.level_index + 1)
                return
            if self.btn_replay.rect.collidepoint(pos):
                s.play("click")
                self.app.restart_play(self.level, self.level_index, self.seq)
                return
        else:
            if self.btn_replay.rect.collidepoint(pos):
                s.play("click")
                self.app.restart_play(self.level, self.level_index, self.seq)
                return
        if self.btn_menu_r.rect.collidepoint(pos):
            s.play("click")
            self.app.go_menu()


def draw_speaker_icon(surf, center, muted, size=30):
    icon = pygame.Surface((size, size), pygame.SRCALPHA)
    k = size / 30
    pygame.draw.polygon(icon, WHITE, [(4 * k, 10 * k), (12 * k, 10 * k), (20 * k, 3 * k),
                                      (20 * k, 27 * k), (12 * k, 20 * k),
                                      (4 * k, 20 * k)])
    if muted:
        pygame.draw.line(icon, (255, 90, 110), (22 * k, 8 * k), (29 * k, 26 * k), max(2, int(3 * k)))
        pygame.draw.line(icon, (255, 90, 110), (29 * k, 8 * k), (22 * k, 26 * k), max(2, int(3 * k)))
    else:
        pygame.draw.arc(icon, WHITE, (19 * k, 9 * k, 10 * k, 12 * k), -1.2, 1.2, max(2, int(2 * k)))
    surf.blit(icon, (center[0] - size // 2, center[1] - size // 2))


# ============================== 主应用 ==============================
class App:
    def __init__(self):
        # 必须在 init 前预配置混音器参数，供 SoundManager 合成 44.1kHz 音效
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        pygame.display.set_caption("一箭又一箭 · 糖果解谜")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.sounds = SoundManager()
        self.bg = Background()
        self.levels = all_levels()
        self.save = self._load_save()
        if self.save.get("muted"):
            self.sounds.muted = True
        self.scene = "menu"
        self.play: PlayState | None = None
        self.t = 0.0
        self.mouse = (0, 0)
        self._build_menu_ui()
        self._build_help_ui()
        self._build_select_ui()
        self.btn_mute = Button((WIDTH - 92, 24, 68, 48), "", "purple", 20)

    # ---------- 存档 ----------
    def _load_save(self):
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"unlocked": 1, "stars": {}, "best": {}, "muted": False}

    def _write_save(self):
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.save, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save_result(self, index, stars, score):
        key = str(index)
        if stars > self.save["stars"].get(key, 0):
            self.save["stars"][key] = stars
        if score > self.save["best"].get(key, 0):
            self.save["best"][key] = score
        self.save["unlocked"] = max(self.save["unlocked"],
                                    min(index + 2, len(self.levels)))
        self._write_save()

    # ---------- 场景跳转 ----------
    def start_level(self, index):
        if index >= len(self.levels):
            self.go_select()
            return
        self.play = PlayState(self, self.levels[index], level_index=index)
        self.scene = "play"

    def start_random(self, seq=0):
        level = make_random_level(seq)
        self.play = PlayState(self, level, level_index=-1, seq=seq)
        self.scene = "play"

    def restart_play(self, level, index, seq):
        if index < 0:
            self.start_random(seq)
        else:
            self.start_level(index)

    def go_menu(self):
        self.scene = "menu"
        self.play = None

    def go_select(self):
        self._build_select_ui()
        self.scene = "select"
        self.play = None

    # ---------- 各界面 UI ----------
    def _build_menu_ui(self):
        self.btn_start = Button((WIDTH // 2 - 150, 430, 300, 72), "开始游戏",
                                "pink", 30, "play")
        self.btn_help = Button((WIDTH // 2 - 150, 522, 300, 66), "玩法说明",
                               "mint", 26)
        self.btn_quit = Button((WIDTH // 2 - 150, 608, 300, 66), "退出游戏",
                               "purple", 26)

    def _build_help_ui(self):
        self.btn_help_back = Button((WIDTH // 2 - 120, 800, 240, 62), "返回",
                                    "gray", 24)

    def _build_select_ui(self):
        self.cards = []
        self.btn_select_back = Button((36, 30, 110, 52), "返回", "gray", 22, "back")
        self.btn_select_random = Button((WIDTH - 268, 30, 168, 52), "随机挑战",
                                        "orange", 22, "dice")

    # ---------- 主循环 ----------
    def run(self):
        self.sounds.play_bgm()
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.t += dt
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)
                if event.type == pygame.MOUSEMOTION:
                    self.mouse = event.pos
                if event.type == pygame.MOUSEBUTTONDOWN and self.btn_mute.rect.collidepoint(
                        event.pos) and event.button == 1:
                    muted = self.sounds.toggle_mute()
                    self.save["muted"] = muted
                    self._write_save()
                    continue
                self.route_event(event)
            self.update(dt)
            self.draw(dt)

    def route_event(self, event):
        if self.scene == "menu":
            if self.btn_start.handle_event(event, self.sounds):
                self.go_select()
            elif self.btn_help.handle_event(event, self.sounds):
                self.scene = "help"
            elif self.btn_quit.handle_event(event, self.sounds):
                pygame.quit()
                sys.exit(0)
        elif self.scene == "help":
            if self.btn_help_back.handle_event(event, self.sounds):
                self.scene = "menu"
        elif self.scene == "select":
            self._select_event(event)
        elif self.scene == "play":
            self.play.handle_event(event)

    def update(self, dt):
        if self.scene == "play" and self.play is not None:
            self.play.update(dt)

    # ---------- 选关 ----------
    def _card_rect(self, i):
        cols = 3
        cw, ch = 252, 178
        gap_x, gap_y = 28, 26
        x0 = (WIDTH - (cw * cols + gap_x * (cols - 1))) // 2
        y0 = 180
        r, c = divmod(i, cols)
        return pygame.Rect(x0 + c * (cw + gap_x), y0 + r * (ch + gap_y), cw, ch)

    def _select_event(self, event):
        s = self.sounds
        self.btn_select_back.handle_event(event, s)
        self.btn_select_random.handle_event(event, s)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.btn_select_back.rect.collidepoint(event.pos):
                self.scene = "menu"
                return
            if self.btn_select_random.rect.collidepoint(event.pos):
                self.start_random(0)
                return
            for i, level in enumerate(self.levels):
                rect = self._card_rect(i)
                if rect.collidepoint(event.pos):
                    unlocked = i + 1 <= self.save.get("unlocked", 1)
                    if unlocked:
                        s.play("click")
                        self.start_level(i)
                    else:
                        s.play("collide")

    # ---------- 绘制分发 ----------
    def draw(self, dt):
        self.bg.draw(self.screen, self.t)
        if self.scene == "menu":
            self._draw_menu(dt)
        elif self.scene == "help":
            self._draw_help(dt)
        elif self.scene == "select":
            self._draw_select(dt)
        elif self.scene == "play":
            self.play.draw(self.screen, dt, self.mouse)
        self._draw_mute()
        pygame.display.flip()

    def _draw_mute(self):
        # 游戏进行中静音开关放在暂停面板里，避免与分数重叠
        if self.scene == "play":
            return
        body = jelly_surface(68, 48, BUTTON_STYLE["purple"][0], BUTTON_STYLE["purple"][1],
                             radius=24, shadow=5)
        self.screen.blit(body, (self.btn_mute.rect.x, self.btn_mute.rect.y - 4))
        draw_speaker_icon(self.screen, self.btn_mute.rect.center, self.sounds.muted, 30)

    # ---------- 主菜单 ----------
    def _draw_menu(self, dt):
        # 装饰：四只表情各异的漂浮大箭头（喜 / 怒 / 哀 / 乐）
        faces = ["happy", "angry", "sad", "joy"]
        for i, d in enumerate(Direction):
            size = 100
            img = rotated_arrow(size, d, face=faces[i])
            phase = self.t * 0.9 + i * 1.7
            x = 150 + i * 206 + math.sin(phase) * 16
            y = 150 + math.cos(phase * 0.8) * 20
            tilt = math.sin(self.t * 1.3 + i * 1.1) * 7
            if abs(tilt) > 0.4:
                img = pygame.transform.rotate(img, tilt)
            img.set_alpha(235)
            self.screen.blit(img, img.get_rect(center=(int(x), int(y))))

        # 标题
        title = get_font(72).render("一箭又一箭", True, WHITE)
        outline = get_font(72).render("一箭又一箭", True, (134, 92, 224))
        x = WIDTH // 2 - title.get_width() // 2
        y = 226
        for dx, dy in ((-3, 3), (3, 3), (0, 4)):
            self.screen.blit(outline, (x + dx, y + dy))
        self.screen.blit(title, (x, y))
        sub = get_font(24).render("糖果色箭头解谜 · 点一点，让箭飞出棋盘", True, INK)
        self.screen.blit(sub, sub.get_rect(center=(WIDTH // 2, 336)))

        self.btn_start.draw(self.screen, dt)
        self.btn_help.draw(self.screen, dt)
        self.btn_quit.draw(self.screen, dt)

    # ---------- 玩法说明 ----------
    def _draw_help(self, dt):
        panel = jelly_surface(760, 680, (255, 255, 255), (240, 246, 255),
                              radius=32, shadow=12)
        pr = panel.get_rect(center=(WIDTH // 2, 420))
        self.screen.blit(panel, pr)
        title = get_font(40).render("怎么玩？", True, (134, 92, 224))
        self.screen.blit(title, (pr.x + 40, pr.y + 30))

        rows = [
            (Direction.RIGHT, "点击一支箭头，如果它前进方向（同行或同列）到"),
            (None, "棋盘边界之间没有其它箭头，它就会飞出棋盘消失。"),
            (Direction.UP, "如果前方被挡住，箭头会晃一晃、闪红光，同时失去"),
            (None, "一次爱心机会，每关只有 3 次机会哦！"),
            (Direction.LEFT, "清空棋盘上所有箭头就通关，连续成功会触发连击加分，"),
            (None, "一次不碰撞可拿 3 星，剩余时间也会计入得分。"),
        ]
        y = pr.y + 110
        for d, text in rows:
            if d is not None:
                img = rotated_arrow(46, d)
                self.screen.blit(img, (pr.x + 40, y - 8))
            t = get_font(22).render(text, True, INK)
            self.screen.blit(t, (pr.x + 110, y))
            y += 44

        tips = [
            ("小提示", (232, 62, 130),
             ["被挡住时，先想办法消除挡住它的那支箭；",
              "卡关可以用「提示」，每关 3 次，撤销可以反悔；",
              "注意顶部倒计时，最后 10 秒屏幕会变红报警！"]),
        ]
        for head, color, lines in tips:
            hd = get_font(24).render("★ " + head, True, color)
            self.screen.blit(hd, (pr.x + 40, y + 6))
            y += 44
            for line in lines:
                t = get_font(20).render("• " + line, True, (110, 100, 140))
                self.screen.blit(t, (pr.x + 56, y))
                y += 36
        self.btn_help_back.rect.center = (WIDTH // 2, pr.bottom - 46)
        self.btn_help_back.draw(self.screen, dt)

    # ---------- 选关界面 ----------
    def _draw_select(self, dt):
        title = get_font(46).render("选择关卡", True, WHITE)
        ot = get_font(46).render("选择关卡", True, (134, 92, 224))
        x = WIDTH // 2 - title.get_width() // 2
        self.screen.blit(ot, (x + 3, 103))
        self.screen.blit(title, (x, 100))
        self.btn_select_back.draw(self.screen, dt)
        self.btn_select_random.draw(self.screen, dt)

        for i, level in enumerate(self.levels):
            rect = self._card_rect(i)
            unlocked = i + 1 <= self.save.get("unlocked", 1)
            hover = unlocked and rect.collidepoint(self.mouse)
            offset = 6 if hover else 0
            style = ["pink", "mint", "blue", "orange", "purple", "pink"][i]
            top, bottom = BUTTON_STYLE[style]
            if not unlocked:
                top, bottom = (214, 216, 226), (184, 188, 204)
            card = jelly_surface(rect.w, rect.h, top, bottom, radius=26, shadow=8,
                                 gloss=True)
            self.screen.blit(card, (rect.x, rect.y + 4 + offset))
            num = get_font(40).render(f"第 {i + 1} 关", True, WHITE)
            self.screen.blit(num, num.get_rect(center=(rect.centerx, rect.y + 50 + offset)))
            name = get_font(22).render(level["name"], True, WHITE)
            self.screen.blit(name, name.get_rect(center=(rect.centerx, rect.y + 96 + offset)))
            if unlocked:
                stars = self.save["stars"].get(str(i), 0)
                for k in range(3):
                    s = star_surface(30, gray=k >= stars)
                    self.screen.blit(s, s.get_rect(
                        center=(rect.centerx + (k - 1) * 38, rect.y + 140 + offset)))
                best = self.save["best"].get(str(i))
                if best:
                    bt = get_font(15).render(f"最佳 {best}", True, WHITE)
                    self.screen.blit(bt, bt.get_rect(center=(rect.centerx,
                                                             rect.bottom - 12 + offset)))
            else:
                lock = pygame.Surface((44, 44), pygame.SRCALPHA)
                pygame.draw.arc(lock, WHITE, (9, 0, 26, 22), math.pi, 3 * math.pi, 6)
                pygame.draw.rect(lock, WHITE, (4, 19, 36, 22), border_radius=7)
                pygame.draw.circle(lock, (150, 155, 178), (22, 28), 3.5)
                self.screen.blit(lock, lock.get_rect(center=(rect.centerx, rect.y + 142 + offset)))


def main():
    App().run()


if __name__ == "__main__":
    main()
