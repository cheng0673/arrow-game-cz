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
from datetime import datetime

import pygame

from levels import (all_levels, all_shape_levels, build_difficulty_level,
                     build_shape_level, make_random_level,
                     FRUIT_PATTERNS, ANIMAL_PATTERNS)

# 三个棋盘主题：默认矩形关卡 / 水果异形 / 动物异形
THEME_DEFAULT = "default"
THEME_FRUIT = "fruit"
THEME_ANIMAL = "animal"
THEME_LABELS = {
    THEME_DEFAULT: "默认棋盘",
    THEME_FRUIT: "水果乐园",
    THEME_ANIMAL: "动物世界",
}
from model import CLICK_BLOCKED, CLICK_FLY, Direction, GameSession
from scenery import DreamScene
from sounds import SoundManager

# ============================== 基础配置 ==============================
WIDTH, HEIGHT = 920, 920
FPS = 120
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_PATH = os.path.join(BASE_DIR, "save.json")

# 糖果配色（鲜艳）
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

# 设置页可选箭头配色：index 0 = 经典四色（随方向变色），其余为统一纯色渐变主题
ARROW_COLORS = [
    ("经典四色", None),
    ("草莓粉", ((255, 138, 177), (224, 49, 117))),
    ("苏打蓝", ((96, 190, 255), (35, 132, 224))),
    ("薄荷绿", ((93, 226, 170), (24, 176, 125))),
    ("芒果黄", ((255, 206, 84), (245, 158, 11))),
    ("葡萄紫", ((190, 159, 255), (134, 92, 224))),
    ("蜜桃橙", ((255, 176, 124), (240, 122, 66))),
    ("樱桃红", ((255, 116, 134), (216, 44, 84))),
    ("青柠绿", ((196, 240, 108), (116, 192, 44))),
    ("天空青", ((124, 228, 230), (44, 178, 198))),
    ("薰衣草", ((216, 182, 255), (152, 112, 232))),
]

# 设置页可选箭头表情：classic = 按方向自动搭配；其余为全局统一表情
FACE_OPTIONS = [
    ("classic", "经典"), ("happy", "微笑"), ("joy", "大笑"), ("angry", "生气"),
    ("sad", "委屈"), ("sleepy", "困困"), ("cool", "酷盖"), ("love", "花痴"),
    ("star", "星星眼"), ("dizzy", "晕晕"), ("surprised", "惊讶"),
    ("cheeky", "调皮"), ("shy", "害羞"),
]


# ============================== 工具函数 ==============================
def level_to_data(level):
    """把关卡 dict 转为可 JSON 保存的结构（随机模式每次布局不同，必须整局保存）。"""
    return {
        "name": level.get("name", ""),
        "rows": level["rows"],
        "cols": level["cols"],
        "time_limit": level["time_limit"],
        "mistakes": level["mistakes"],
        "arrows": [[r, c, d.name] for r, c, d in level["arrows"]],
        "random": bool(level.get("random", False)),
        "mask": level.get("mask"),
        "shape_index": level.get("shape_index"),
        "shape_kind": level.get("shape_kind"),
    }


def level_from_data(data):
    """level_to_data 的逆操作，还原出关卡 dict。"""
    level = {
        "name": data.get("name", "随机挑战"),
        "rows": int(data["rows"]),
        "cols": int(data["cols"]),
        "time_limit": float(data["time_limit"]),
        "mistakes": int(data["mistakes"]),
        "arrows": [(int(r), int(c), Direction[str(d)])
                   for r, c, d in data["arrows"]],
        "random": bool(data.get("random", False)),
    }
    if data.get("mask"):
        level["mask"] = data["mask"]  # 每项 [r, c, [R,G,B]]，已是可用结构
    if data.get("shape_index") is not None:
        level["shape_index"] = int(data["shape_index"])
    if data.get("shape_kind"):
        level["shape_kind"] = data["shape_kind"]
    return level


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


def blit_pixel_preview(surf, cells, centerx, top_y, max_w, max_h):
    """
    在指定区域内居中绘制像素画图案（cells: [[r, c, [R,G,B]], ...]）。
    按图案实际包围盒计算，保证形状居中。
    """
    rs = [e[0] for e in cells]
    cs = [e[1] for e in cells]
    minr, maxr, minc, maxc = min(rs), max(rs), min(cs), max(cs)
    nr, nc = maxr - minr + 1, maxc - minc + 1
    cell = max(4, min(max_w // nc, max_h // nr))
    px = centerx - cell * nc // 2 - minc * cell
    py = top_y - minr * cell
    for r, c, color in cells:
        rct = pygame.Rect(px + c * cell, py + r * cell, cell - 1, cell - 1)
        top = tuple(min(255, ch + 20) for ch in color)
        bottom = tuple(max(0, ch - 20) for ch in color)
        mini = jelly_surface(rct.w, rct.h, top, bottom,
                             radius=max(2, cell // 5), shadow=0, gloss=False,
                             outline=lerp(color, (70, 50, 90), 0.55))
        surf.blit(mini, rct)


_arrow_cache: dict = {}


def star_points(cx, cy, r):
    """五角星顶点（尖朝上）。"""
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    return pts


def draw_star(surf, cx, cy, r, top=(255, 214, 84), bottom=(245, 158, 11)):
    """立体小星星：暗色描边 + 亮色主体 + 白色高光。"""
    pts = star_points(cx, cy, r)
    pts_out = [(cx + (px - cx) * 1.18, cy + (py - cy) * 1.18) for px, py in pts]
    pygame.draw.polygon(surf, lerp(bottom, (0, 0, 0), 0.3), pts_out)
    pygame.draw.polygon(surf, top, pts)
    pygame.draw.circle(surf, (255, 255, 255),
                       (int(cx - r * 0.28), int(cy - r * 0.3)),
                       max(1, int(r * 0.18)))


def arrow_surface(size, top, bottom, face="happy", blink=0, mood="normal"):
    """画一支朝右的胖嘟嘟立体箭头，旋转即可表示其它方向。

    face: happy=微笑 / joy=大笑 / angry=生气 / sad=委屈 / sleepy=困困 /
          cool=酷盖(墨镜) / love=花痴(爱心眼) / star=星星眼 / dizzy=晕晕 /
          surprised=惊讶 / cheeky=调皮(吐舌眨眼) / shy=害羞
    blink: 0~1，眼睛闭合程度（用于眨眼动画，内部量化为 5 档缓存）
    mood: normal=平常 / cry=哭泣（走错时使用，挤眼、大哭、掉眼泪）
    """
    blink_step = int(round(min(1, max(0, blink)) * 4))
    key = ("arrow", int(size), top, bottom, face, blink_step, mood)
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
    open_k = 1 - blink_step / 4
    for ex in (0.195, 0.365):
        ex_px = 5 + int(ex * s)
        if mood == "cry":
            # 哭泣挤眼："><" 形尖角相对，委屈又生动
            rr = max(3, int(eye_r * 1.2))
            lw = max(2, s // 18)
            tip = rr // 2
            if ex < 0.28:   # 左眼 ">"：尖角朝内
                pygame.draw.line(surf, ink, (ex_px - rr, ey - rr), (ex_px + tip, ey), lw)
                pygame.draw.line(surf, ink, (ex_px - rr, ey + rr), (ex_px + tip, ey), lw)
            else:           # 右眼 "<"：尖角朝内
                pygame.draw.line(surf, ink, (ex_px + rr, ey - rr), (ex_px - tip, ey), lw)
                pygame.draw.line(surf, ink, (ex_px + rr, ey + rr), (ex_px - tip, ey), lw)
        elif face == "joy":
            # 眯眯笑眼 ^ ^
            r = pygame.Rect(int(ex_px - eye_r * 1.2), int(ey - eye_r),
                            int(eye_r * 2.4), int(eye_r * 2.1))
            pygame.draw.arc(surf, ink, r, math.radians(200), math.radians(340),
                            max(2, s // 22))
        elif face == "sleepy":
            # 困困：闭成下弯的弧（呼呼大睡）
            rr = int(eye_r * 1.25)
            pygame.draw.arc(surf, ink,
                            pygame.Rect(ex_px - rr, ey - rr // 2, 2 * rr, rr + rr // 2),
                            math.radians(205), math.radians(335), max(2, s // 20))
        elif face == "love":
            # 花痴：立体爱心眼 + 高光
            hr = int(eye_r * 1.2)
            hc = (250, 90, 130)
            ytop = ey - hr // 3
            pygame.draw.circle(surf, hc, (ex_px - hr // 2, ytop), hr // 2 + 1)
            pygame.draw.circle(surf, hc, (ex_px + hr // 2, ytop), hr // 2 + 1)
            pygame.draw.polygon(surf, hc, [(ex_px - hr, ytop - hr // 4),
                                           (ex_px + hr, ytop - hr // 4),
                                           (ex_px, ey + hr)])
            pygame.draw.circle(surf, (255, 255, 255),
                               (ex_px - hr // 2 + max(1, hr // 6), ytop - max(1, hr // 6)),
                               max(1, hr // 5))
        elif face == "star":
            # 星星眼
            draw_star(surf, ex_px, ey, int(eye_r * 1.55))
        elif face == "dizzy":
            # 晕晕：X 形眼
            rr = int(eye_r * 0.95)
            lw = max(2, s // 20)
            pygame.draw.line(surf, ink, (ex_px - rr, ey - rr), (ex_px + rr, ey + rr), lw)
            pygame.draw.line(surf, ink, (ex_px - rr, ey + rr), (ex_px + rr, ey - rr), lw)
        elif face == "surprised":
            # 惊讶：圆睁大眼 + 大高光
            eh = int(eye_r * 1.25)
            pygame.draw.ellipse(surf, ink, (ex_px - eye_r, ey - eh, 2 * eye_r, 2 * eh))
            pygame.draw.circle(surf, WHITE,
                               (ex_px - eye_r // 3, ey - eh // 2),
                               max(1, int(eye_r * 0.45)))
        elif face == "cheeky":
            # 调皮：左眼正常、右眼眨眼
            if ex < 0.28:
                eh = max(1, int(eye_r * (0.16 + 0.84 * open_k)))
                pygame.draw.ellipse(surf, ink,
                                    (ex_px - eye_r, ey - eh, 2 * eye_r, 2 * eh))
                pygame.draw.circle(surf, WHITE,
                                   (int(ex_px - eye_r * 0.3), int(ey - eye_r * 0.3)),
                                   max(1, int(eye_r * 0.4)))
            else:
                rr = int(eye_r * 1.2)
                pygame.draw.arc(surf, ink,
                                pygame.Rect(ex_px - rr, ey - rr, 2 * rr, 2 * rr),
                                math.radians(200), math.radians(340),
                                max(2, s // 20))
        elif face == "shy":
            # 害羞：弯弯的笑眼（配合大腮红）
            rr = int(eye_r * 1.15)
            pygame.draw.arc(surf, ink,
                            pygame.Rect(ex_px - rr, ey - rr, 2 * rr, 2 * rr),
                            math.radians(200), math.radians(340), max(2, s // 20))
        elif face == "cool":
            pass  # 墨镜在眼睛循环之后整体绘制
        else:
            # 普通眼睛随眨眼压扁
            eh = max(1, int(eye_r * (0.16 + 0.84 * open_k)))
            pygame.draw.ellipse(surf, ink,
                                (ex_px - eye_r, ey - eh, 2 * eye_r, 2 * eh))
            if open_k > 0.55:
                pygame.draw.circle(surf, WHITE,
                                   (int(ex_px - eye_r * 0.3),
                                    int(ey - eye_r * 0.3)),
                                   max(1, int(eye_r * 0.4)))
    mx = 5 + int(0.28 * s)   # 嘴巴中心
    my = 5 + int(0.57 * s)
    R = max(3, int(0.085 * s))
    mw = max(2, s // 20)
    if face == "cool" and mood == "normal":
        # 酷盖墨镜：两片深色镜面 + 镜桥镜腿 + 高光斜杠
        gy = ey - int(eye_r * 1.05)
        gh = int(eye_r * 2.2)
        gw = int(eye_r * 2.6)
        lx, rx2 = 5 + int(0.195 * s), 5 + int(0.365 * s)
        pygame.draw.rect(surf, (40, 36, 60), (lx - gw // 2, gy, gw, gh),
                         border_radius=max(4, s // 14))
        pygame.draw.rect(surf, (40, 36, 60), (rx2 - gw // 2, gy, gw, gh),
                         border_radius=max(4, s // 14))
        pygame.draw.line(surf, (40, 36, 60), (lx + gw // 2 - 2, gy + gh // 3),
                         (rx2 - gw // 2 + 2, gy + gh // 3), max(2, s // 22))
        pygame.draw.line(surf, (40, 36, 60), (lx - gw // 2, gy + gh // 3),
                         (lx - gw // 2 - int(eye_r * 0.7), gy + gh // 4), max(2, s // 22))
        pygame.draw.line(surf, (40, 36, 60), (rx2 + gw // 2, gy + gh // 3),
                         (rx2 + gw // 2 + int(eye_r * 0.7), gy + gh // 4), max(2, s // 22))
        pygame.draw.line(surf, (235, 240, 255), (lx - gw // 3, gy + gh - 5),
                         (lx - gw // 6, gy + 5), max(2, s // 26))
        pygame.draw.line(surf, (235, 240, 255), (rx2 - gw // 3, gy + gh - 5),
                         (rx2 - gw // 6, gy + 5), max(2, s // 26))
    if mood == "cry":
        # 哭泣：张嘴哇哇大哭（深色小椭圆 + 粉舌头）+ 带高光的大泪珠
        mw2 = max(3, int(R * 1.05))
        pygame.draw.ellipse(surf, ink,
                            (mx - mw2, my - int(R * 0.5), mw2 * 2, int(R * 1.15)))
        pygame.draw.ellipse(surf, (238, 110, 130),
                            (mx - int(mw2 * 0.5), my + int(R * 0.15),
                             mw2, int(R * 0.5)))
        for i, ex in enumerate((0.155, 0.405)):
            tx = 5 + int(ex * s)
            ty = 5 + int(0.585 * s) + i * max(1, s // 70)
            tr = max(2, int(eye_r * 0.55))
            drop = (135, 200, 255)
            # 泪珠：上尖下圆 + 白色高光，两滴高低错开像正在流
            pygame.draw.polygon(surf, drop,
                                [(tx - tr, ty), (tx + tr, ty),
                                 (tx, ty - int(tr * 1.3))])
            pygame.draw.circle(surf, drop, (tx, ty + int(tr * 0.35)), tr)
            pygame.draw.circle(surf, (255, 255, 255),
                               (tx - int(tr * 0.3), ty + int(tr * 0.3)),
                               max(1, int(tr * 0.3)))
    elif face == "happy":
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
    elif face == "sleepy":
        # 睡着的小圆嘴 + 鼻尖小泡泡
        pygame.draw.ellipse(surf, ink, (mx - R // 2, my - 2, R, R))
        pygame.draw.circle(surf, (205, 228, 255), (mx + R, my - int(R * 0.9)),
                           max(2, R // 2))
    elif face == "cool":
        # 得意斜嘴
        pygame.draw.line(surf, ink, (mx - R, my + R // 3), (mx + R, my - R // 4), mw)
    elif face == "love":
        # 小开心嘴
        pygame.draw.arc(surf, ink,
                        pygame.Rect(mx - R, my - int(R * 0.8), 2 * R, int(R * 1.5)),
                        math.radians(25), math.radians(155), mw)
    elif face == "star":
        # 张嘴欢呼（小下半圆）
        pts = [(mx + int(R * 0.8 * math.cos(math.radians(a))),
                my + int(R * 0.75 * math.sin(math.radians(a))))
               for a in range(0, 181, 12)]
        pygame.draw.polygon(surf, ink, pts)
    elif face == "dizzy":
        # 波浪嘴（晕乎乎）
        pts = [(mx - int(R * 1.3), my), (mx - int(R * 0.65), my - R // 2),
               (mx, my), (mx + int(R * 0.65), my + R // 2), (mx + int(R * 1.3), my)]
        pygame.draw.lines(surf, ink, False, pts, mw)
    elif face == "surprised":
        # O 形嘴 + 小舌头
        pygame.draw.ellipse(surf, ink, (mx - R, my - int(R * 0.7), 2 * R, int(R * 1.5)))
        pygame.draw.ellipse(surf, (255, 170, 180), (mx - R // 2, my, R, int(R * 0.7)))
    elif face == "cheeky":
        # 吐舌头
        pygame.draw.line(surf, ink, (mx - R, my), (mx + R, my - 2), mw)
        pygame.draw.ellipse(surf, (240, 110, 130),
                            (mx - int(R * 0.6), my + 1, int(R * 1.2), int(R * 1.1)))
    elif face == "shy":
        # w 形猫嘴
        pygame.draw.arc(surf, ink, (mx - R, my - int(R * 0.4), R, R), 0, math.pi, mw)
        pygame.draw.arc(surf, ink, (mx, my - int(R * 0.4), R, R), 0, math.pi, mw)
    # 腮红（哭泣时不画留给泪珠；墨镜脸不画；害羞腮红加大且下移避 开眼睛）
    if mood != "cry" and face != "cool":
        cheek = (255, 150, 165, 130) if face != "angry" else (255, 120, 110, 145)
        is_shy = face == "shy"
        cr = max(2, int(0.072 * s) if is_shy else int(0.055 * s))
        cy = 5 + int((0.605 if is_shy else 0.555) * s)
        for cx in (0.165, 0.40):
            pygame.draw.circle(surf, cheek, (5 + int(cx * s), cy), cr)
    _arrow_cache[key] = surf
    return surf


def rotated_arrow(size, direction, red=False, face="happy",
                  blink=0, mood="normal", colors=None):
    top, bottom = DIR_RED if red else (colors if colors else DIR_STYLE[direction])
    surf = arrow_surface(size, top, bottom, face, blink=blink, mood=mood)
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


def thumbs_cat_surface(size=200):
    """失败页用：大脸大眼的高清立体猫咪头贴纸。"""
    key = ("cat_head_v3", size)
    if key in _surf_cache:
        return _surf_cache[key]
    B = 220
    surf = pygame.Surface((B, B), pygame.SRCALPHA)
    ink = (56, 50, 72)
    fur_shade = (232, 216, 226)
    pink = (255, 172, 198)
    gold = (255, 222, 102)

    def mini_heart(cx, cy, r, color):
        pygame.draw.circle(surf, color, (cx - r, cy), r)
        pygame.draw.circle(surf, color, (cx + r, cy), r)
        pygame.draw.polygon(surf, color,
                            [(cx - 2 * r, cy + 1), (cx + 2 * r, cy + 1),
                             (cx, cy + 2 * r + 2)])

    def sparkle(cx, cy, r, color):
        pts = []
        for i in range(8):
            ang = -math.pi / 2 + i * math.pi / 4
            rad = r if i % 2 == 0 else r * 0.4
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        pygame.draw.polygon(surf, color, pts)

    # ---- 贴纸底 ----
    pygame.draw.rect(surf, WHITE, (0, 0, B, B), border_radius=40)
    pygame.draw.rect(surf, (250, 237, 247), (10, 10, B - 20, B - 20),
                     border_radius=32)

    # 背景小点缀（纯装饰，无肢体动作）
    mini_heart(34, 44, 8, (255, 183, 205))
    sparkle(192, 40, 12, gold)
    pygame.draw.circle(surf, (190, 220, 255), (30, 168), 6)
    pygame.draw.circle(surf, (255, 205, 225), (198, 172), 5)
    sparkle(26, 108, 7, (255, 240, 246))
    mini_heart(196, 132, 5, (255, 183, 205))
    sparkle(38, 190, 6, gold)

    # ---- 两只耳朵（在头后面）----
    for tri in ([(42, 96), (58, 22), (120, 52)],
                [(178, 96), (162, 22), (100, 52)]):
        pygame.draw.polygon(surf, WHITE, tri)
        pygame.draw.polygon(surf, ink, tri, 4)
        cx = sum(p[0] for p in tri) / 3
        cy = sum(p[1] for p in tri) / 3
        inner = pygame.Surface((20, 18), pygame.SRCALPHA)
        pygame.draw.polygon(inner, (255, 194, 212),
                            [(2, 16), (10, 1), (18, 16)])
        surf.blit(pygame.transform.smoothscale(inner, (30, 27)),
                  (int(cx - 15), int(cy - 8)))
        # 耳尖一小撮绒毛
        tip = tri[1]
        pygame.draw.line(surf, ink, (tip[0] - 5, tip[1] + 10),
                         (tip[0] + 3, tip[1] + 2), 2)

    # ---- 大圆头（带立体明暗）----
    pygame.draw.circle(surf, ink, (110, 116), 82)
    pygame.draw.circle(surf, WHITE, (110, 116), 74)
    # 右下内侧一弯柔和暗部 + 左上柔和高光，让脸更立体
    pygame.draw.arc(surf, (238, 226, 238),
                    pygame.Rect(110 - 68, 116 - 68, 136, 136),
                    math.radians(-40), math.radians(80), 9)
    hi = pygame.Surface((B, B), pygame.SRCALPHA)
    pygame.draw.ellipse(hi, (255, 255, 255, 60), (46, 44, 84, 52))
    surf.blit(hi, (0, 0))
    # 额头三道小虎斑
    for dx in (-15, 0, 15):
        pygame.draw.line(surf, fur_shade, (110 + dx, 56),
                         (110 + dx, 70), 5)

    # 大眼睛（椭圆黑瞳 + 大小双高光 + 睫毛）
    for ex, side in ((88, -1), (132, 1)):
        pygame.draw.ellipse(surf, ink, (ex - 14, 92, 28, 38))
        pygame.draw.circle(surf, WHITE, (ex - 5, 102), 6)
        pygame.draw.circle(surf, WHITE, (ex + 6, 116), 3)
        pygame.draw.line(surf, ink, (ex + side * 10, 92),
                         (ex + side * 20, 85), 2)
        pygame.draw.line(surf, ink, (ex + side * 2, 88),
                         (ex + side * 8, 80), 2)
    # 腮红（带高光）
    for cx in (64, 156):
        pygame.draw.ellipse(surf, pink, (cx - 14, 130, 28, 18))
        pygame.draw.ellipse(surf, (255, 205, 218), (cx - 8, 133, 9, 6))
    # 小三角鼻
    pygame.draw.polygon(surf, (255, 150, 175),
                        [(104, 126), (116, 126), (110, 134)])
    # W 形小嘴
    pygame.draw.line(surf, ink, (102, 141), (110, 147), 3)
    pygame.draw.line(surf, ink, (110, 147), (118, 141), 3)
    # 胡须
    for side in (-1, 1):
        for dy in (-6, 1, 8):
            pygame.draw.line(surf, ink,
                             (110 + side * 58, 122 + dy),
                             (110 + side * 88, 116 + dy), 2)

    # 头顶星光点缀
    sparkle(110, 26, 9, gold)
    pygame.draw.circle(surf, gold, (150, 34), 3)

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

    def __init__(self, app, level, level_index=-1, seq=0, checkpoint=None,
                 diff=0, timed=None):
        self.app = app
        self.level = level
        self.level_index = level_index  # -1 表示随机模式
        self.seq = seq
        self.diff = diff      # 0=简单 1=中等 2=困难（随机模式无意义）
        self.timed = timed    # 限时挑战秒数（None 表示非限时）
        self.session = GameSession(
            level["rows"], level["cols"], level["arrows"],
            time_limit=level["time_limit"], max_mistakes=level["mistakes"])
        rows, cols = level["rows"], level["cols"]
        # 像素画棋盘：mask 每项 [r, c, 颜色]；普通矩形棋盘 mask=None
        if level.get("mask"):
            self.tile_colors = {(int(m[0]), int(m[1])): tuple(m[2])
                                for m in level["mask"]}
            self.mask = set(self.tile_colors)
        else:
            self.tile_colors = None
            self.mask = None
        self.shape_kind = level.get("shape_kind")    # "fruit" / "animal" / None
        board_w_max = WIDTH - 48
        board_h_max = HEIGHT - 250
        if self.mask is not None:
            # 按形状实际包围盒确定格子尺寸与偏移，保证异形棋盘在屏幕上居中
            mr = [r for r, _ in self.mask]
            mc = [c for _, c in self.mask]
            minr, maxr, minc, maxc = min(mr), max(mr), min(mc), max(mc)
            shape_rows = maxr - minr + 1
            shape_cols = maxc - minc + 1
            self.cell = int(min(board_w_max / shape_cols,
                                board_h_max / shape_rows))
            self.ox = (WIDTH - self.cell * shape_cols) // 2 - minc * self.cell
            self.oy = (232 + (board_h_max - self.cell * shape_rows) // 2
                       - minr * self.cell)
        else:
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
        # 进入关卡时若有中途存档，先挂起游戏并弹出询问
        self.ask_restore = None
        if checkpoint is not None:
            try:
                GameSession.from_checkpoint(level, checkpoint["data"])
                self.ask_restore = checkpoint
            except Exception:
                # 存档损坏：直接丢弃，按新局开始
                self.app.clear_checkpoint(self.cp_key())

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
        self.btn_set_p = Button((0, 0, 240, 64), "游戏设置", "purple", 24)
        self.btn_menu_p = Button((0, 0, 240, 64), "返回菜单", "gray", 24)
        self.btn_next = Button((0, 0, 220, 62), "下一关", "pink", 26)
        self.btn_replay = Button((0, 0, 200, 62), "再来一次", "mint", 24)
        self.btn_menu_r = Button((0, 0, 200, 62), "返回菜单", "gray", 24)
        # 「是否回到上次进度」询问弹窗按钮
        self.btn_restore_yes = Button((0, 0, 228, 64), "是，继续进度",
                                      "mint", 24, "play")
        self.btn_restore_no = Button((0, 0, 228, 64), "否，重新开始",
                                     "gray", 24)

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

    # ---------- 关卡进度保存 / 恢复 ----------
    def cp_key(self):
        return self.app.checkpoint_key(self.level_index, self.seq, self.diff,
                                       theme=self.shape_kind)

    def has_mid_progress(self):
        """局面确实离开过初始状态时才有保存价值。"""
        s = self.session
        return (s.state == "playing"
                and (s.cleared > 0 or s.mistakes_left < s.max_mistakes
                     or s.hints_left < s.max_hints))

    def save_and_menu(self):
        """中途退出：自动保存当前进度后返回主菜单。"""
        if self.has_mid_progress():
            self.app.save_checkpoint(self.cp_key(), self.level, self.session)
        self.app.go_menu()

    def _accept_restore(self):
        """选择“是”：用存档局面替换当前新局。"""
        try:
            self.session = GameSession.from_checkpoint(
                self.level, self.ask_restore["data"])
        except Exception:
            self.app.clear_checkpoint(self.cp_key())
            self.ask_restore = None
            return
        self.ask_restore = None
        self.btn_hint.text = f"提示 {self.session.hints_left}"

    def _decline_restore(self):
        """选择“否”：废弃存档。固定关卡保持新局；随机模式另开一把全新随机。"""
        is_random = self.level_index < 0
        self.app.clear_checkpoint(self.cp_key())
        self.ask_restore = None
        if is_random:
            self.app.start_random(0)

    # ---------- 事件 ----------
    def handle_event(self, event):
        s = self.app.sounds

        # 恢复进度询问挂起时，只响应询问弹窗，其余操作全部冻结
        if self.ask_restore is not None:
            ask_buttons = (self.btn_restore_yes, self.btn_restore_no)
            if event.type == pygame.MOUSEMOTION:
                for b in ask_buttons:
                    b.hover = b.enabled and b.rect.collidepoint(event.pos)
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.btn_restore_yes.rect.collidepoint(event.pos):
                    s.play("click")
                    self._accept_restore()
                elif self.btn_restore_no.rect.collidepoint(event.pos):
                    s.play("click")
                    self._decline_restore()
            return

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
                self.app.restart_play(self.level, self.level_index, self.seq,
                                      self.diff, self.timed)
            elif self.btn_set_p.rect.collidepoint(event.pos):
                s.play("click")
                self.app.scene = "settings"  # 游戏保持挂起，返回后仍是暂停态
            elif self.btn_menu_p.rect.collidepoint(event.pos):
                s.play("click")
                self.save_and_menu()
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
            self.save_and_menu()
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
            self.texts.append(FloatingText("啊欧，不对哦！", cr.centerx, cr.top - 8,
                                           (255, 110, 160), 26))
            self._burst(event_pos=cr.center, color=(255, 150, 190), n=10,
                        gravity=200, shape="circle")
            self.hint_id = None

    def _start_fly(self, arrow):
        size = int(self.cell * 0.80)
        surf = rotated_arrow(size, arrow.direction,
                             face=self.app.arrow_face(arrow.direction),
                             colors=self.app.arrow_colors(arrow.direction))
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
        if self.paused or self.ask_restore is not None:
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
            # 关卡已结束，中途进度存档不再有意义（仅当存在时写盘一次）
            self.app.clear_checkpoint(self.cp_key())
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
                    key = self.app.checkpoint_key(self.level_index, self.seq,
                                                  self.diff, theme=self.shape_kind)
                    self.app.save_result(key, self.level_index,
                                         self.session.stars(), self.session.score)

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

        if self.ask_restore is not None:
            self._draw_restore_ask(surf, dt)
        elif self.paused:
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
        # 棋盘底板（异形棋盘只在形状轮廓内画格子，不画整块大白底）
        if self.mask is None:
            bw = self.cell * cols + 26
            bh = self.cell * rows + 26
            board_bg = jelly_surface(bw, bh, (255, 255, 255), (225, 235, 252),
                                     radius=30, shadow=10, gloss=True)
            surf.blit(board_bg, (self.ox - 13, self.oy - 13))

        pop_t = self.t
        if self.tile_colors is not None:
            # 像素画棋盘：逐格按图案颜色渲染
            for (r, c), color in self.tile_colors.items():
                delay = 0.025 * (r + c)
                k = min(1, max(0, (pop_t - delay) / 0.3))
                scale = round(ease_out_back(k) * 25) / 25
                rect = self.cell_rect(r, c, scale=scale)
                top = tuple(min(255, ch + 26) for ch in color)
                bottom = tuple(max(0, ch - 26) for ch in color)
                tile = jelly_surface(rect.w, rect.h, top, bottom,
                                     radius=max(8, rect.w // 7), shadow=3,
                                     gloss=True,
                                     outline=lerp(color, (70, 50, 90), 0.5))
                surf.blit(tile, (rect.x, rect.y - 2))
        else:
            for r in range(rows):
                for c in range(cols):
                    delay = 0.025 * (r + c)
                    k = min(1, max(0, (pop_t - delay) / 0.3))
                    scale = round(ease_out_back(k) * 25) / 25
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

            hitting = arrow.id in self.hits
            if hitting:
                # 走错：变成哭泣表情并左右发抖
                mood, blink = "cry", 1.0
                ht = self.hits[arrow.id] / self.HIT_TIME
                dx = math.sin((1 - ht) * 50) * 7 * ht
                rect = rect.move(int(dx), 0)
            else:
                # 每支箭按自己的节奏眨眼（周期 3.2~6.8 秒，闭合 0.16 秒）
                mood = "normal"
                period = 3.2 + (arrow.id % 5) * 0.9
                ph = (self.t + arrow.id * 1.27) % period
                close_t = ph - (period - 0.16)
                blink = (math.sin(close_t / 0.16 * math.pi)
                         if close_t > 0 else 0.0)

            img = rotated_arrow(int(arrow_size * scale), arrow.direction,
                                face=self.app.arrow_face(arrow.direction),
                                blink=blink, mood=mood,
                                colors=self.app.arrow_colors(arrow.direction))
            rect_img = img.get_rect(center=(rect.centerx, rect.centery + int(bob)))
            surf.blit(img, rect_img)

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

    def _draw_restore_ask(self, surf, dt):
        """“是否选择回到上次进度”询问弹窗。"""
        self._dim(surf)
        panel = jelly_surface(560, 340, (255, 255, 255), (236, 242, 255),
                              radius=32, shadow=12)
        pr = panel.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        surf.blit(panel, pr)

        title = get_font(30).render("是否选择回到上次进度？", True, INK)
        surf.blit(title, title.get_rect(center=(WIDTH // 2, pr.top + 78)))
        tip1 = get_font(20).render("检测到本关存在中途退出时自动保存的局面",
                                   True, (120, 112, 150))
        surf.blit(tip1, tip1.get_rect(center=(WIDTH // 2, pr.top + 132)))
        tip2 = get_font(20).render("“是”将回到上次进度，“否”则重新开始",
                                   True, (120, 112, 150))
        surf.blit(tip2, tip2.get_rect(center=(WIDTH // 2, pr.top + 168)))

        self.btn_restore_yes.rect.center = (WIDTH // 2 - 132, pr.top + 256)
        self.btn_restore_no.rect.center = (WIDTH // 2 + 132, pr.top + 256)
        self.btn_restore_yes.draw(surf, dt)
        self.btn_restore_no.draw(surf, dt)

    def _draw_pause(self, surf, dt):
        self._dim(surf)
        panel = jelly_surface(440, 560, (255, 255, 255), (236, 242, 255),
                              radius=32, shadow=12)
        pr = panel.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        surf.blit(panel, pr)
        title = get_font(40).render("游戏暂停", True, INK)
        surf.blit(title, title.get_rect(center=(WIDTH // 2, pr.top + 74)))
        btns = [self.btn_resume, self.btn_restart_p, self.btn_set_p, self.btn_menu_p]
        labels_y = [pr.top + 138, pr.top + 214, pr.top + 290, pr.top + 366]
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
            if self.shape_kind is not None:
                total = 6  # 水果 / 动物主题各 6 关
                has_next = self.level_index + 1 < total
            else:
                has_next = (self.level_index >= 0 and self.level_index + 1 < len(self.app.levels)) \
                    or self.level_index < 0
            self.btn_next.enabled = has_next
        else:
            # 竖大拇指的可爱小猫咪（轻轻上下浮动）
            cat = thumbs_cat_surface(180)
            cy = pr.top + 126 + int(math.sin(self.t * 2.4) * 4)
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
                    self.app.start_random(self.seq + 1, self.timed)
                elif self.shape_kind is not None:
                    self.app.start_shape_level(self.shape_kind,
                                              self.level_index + 1, self.diff)
                else:
                    self.app.start_level(self.level_index + 1, self.diff)
                return
            if self.btn_replay.rect.collidepoint(pos):
                s.play("click")
                self.app.restart_play(self.level, self.level_index, self.seq,
                                      self.diff, self.timed)
                return
        else:
            if self.btn_replay.rect.collidepoint(pos):
                s.play("click")
                self.app.restart_play(self.level, self.level_index, self.seq,
                                      self.diff, self.timed)
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
        pygame.display.set_caption("重生之我是箭神")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.sounds = SoundManager()
        self.bg = DreamScene(WIDTH, HEIGHT)
        self.levels = all_levels()
        self._theme_meta = {}   # 懒加载：fruit/animal 形状元数据
        self.save = self._load_save()
        self.sounds.set_master(float(self.save.get("volume", 1.0)))
        if self.save.get("muted"):
            self.sounds.muted = True
        self.play: PlayState | None = None
        self.t = 0.0
        self.mouse = (0, 0)
        self.timed_mode = None   # 当前限时挑战秒数（随机模式用）
        self._level_cache = {}   # (主题, 关卡序号, 难度) -> 关卡数据
        self._shape_cache_path = os.path.join(os.path.dirname(__file__),
                                               "_shape_cache.json")
        self._shape_disk_cache = self._load_shape_cache()
        self.cur_theme = THEME_DEFAULT
        self._build_menu_ui()
        self._build_help_ui()
        self._build_theme_ui()
        self._build_select_ui()
        self._build_pick_ui()
        self._build_settings_ui()
        self._build_boot_ui()
        self.btn_mute = Button((WIDTH - 76, 30, 52, 52), "", "purple", 20)
        # 有历史进度时启动先询问「继续 / 从头开始」，否则直接进主菜单
        self.scene = "boot" if self._has_progress() else "menu"

    @staticmethod
    def _shape_cache_version():
        """用图案内容 hash 作版本号——图案一改，旧缓存自动失效。"""
        import hashlib
        blob = repr(FRUIT_PATTERNS) + repr(ANIMAL_PATTERNS)
        return hashlib.md5(blob.encode()).hexdigest()[:12]

    def _load_shape_cache(self):
        """从磁盘加载异形关卡缓存，避免每次启动重新生成。"""
        try:
            with open(self._shape_cache_path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("version") != self._shape_cache_version():
                return {}
            return data.get("levels", {})
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_shape_cache(self):
        """把异形关卡缓存写入磁盘（带版本号）。"""
        try:
            data = {"version": self._shape_cache_version(),
                    "levels": self._shape_disk_cache}
            with open(self._shape_cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except OSError:
            pass

    def theme_meta(self, theme):
        """获取水果/动物主题的形状元数据（懒加载缓存）。"""
        if theme not in self._theme_meta:
            self._theme_meta[theme] = all_shape_levels(theme)
        return self._theme_meta[theme]

    def _has_progress(self):
        """存档中是否存在值得询问的历史进度。"""
        return bool(self.save.get("stars")) or self.save.get("unlocked", 1) > 1 \
            or self.save.get("fruit_unlocked", 1) > 1 \
            or self.save.get("animal_unlocked", 1) > 1 \
            or bool(self.save.get("checkpoints"))

    def reset_progress(self):
        """初始化从头开始：清空全部成绩与中途存档（保留音量等偏好设置）。"""
        prefs = {k: self.save.get(k) for k in ("volume", "muted",
                                               "arrow_colors", "faces")}
        self.save = self._default_save()
        for k, v in prefs.items():
            if v is not None:
                self.save[k] = v
        self._write_save()
        self._level_cache = {}

    # ---------- 个性化设置读取 ----------
    # 方向 -> 存档键名
    DIR_KEY = {
        Direction.UP: "up",
        Direction.DOWN: "down",
        Direction.LEFT: "left",
        Direction.RIGHT: "right",
    }

    def arrow_colors(self, direction):
        """指定方向的箭头配色（None = 经典四色，随方向变色）。"""
        i = self.save.get("arrow_colors", {}).get(self.DIR_KEY[direction], 0)
        return ARROW_COLORS[i][1]

    def arrow_face(self, direction):
        """指定方向的箭头表情（classic = 按方向自动搭配）。"""
        f = self.save.get("faces", {}).get(self.DIR_KEY[direction], "classic")
        return DIRECTION_FACE[direction] if f == "classic" else f

    # ---------- 存档 ----------
    def _default_save(self):
        return {"unlocked": 1, "fruit_unlocked": 1, "animal_unlocked": 1,
                "stars": {}, "best": {}, "muted": False,
                "checkpoints": {}, "volume": 1.0,
                "arrow_colors": {"up": 0, "down": 0, "left": 0, "right": 0},
                "faces": {"up": "classic", "down": "classic",
                          "left": "classic", "right": "classic"}}

    def _load_save(self):
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return self._default_save()
        data.setdefault("unlocked", 1)
        data.setdefault("fruit_unlocked", 1)
        data.setdefault("animal_unlocked", 1)
        data.pop("shape_unlocked", None)  # 旧版异形解锁键已废弃
        data.setdefault("stars", {})
        data.setdefault("best", {})
        data.setdefault("muted", False)
        data.setdefault("checkpoints", {})
        data.setdefault("volume", 1.0)
        # 旧版全局配色/表情迁移为四个方向各一份；缺失的方向补默认值
        old_c = data.pop("arrow_color", 0)
        old_f = data.pop("face", "classic")
        colors = data.setdefault("arrow_colors", {})
        faces = data.setdefault("faces", {})
        for k in ("up", "down", "left", "right"):
            colors[k] = colors.get(k, old_c)
            faces[k] = faces.get(k, old_f)
        # 旧版进度按无难度键名保存：星级/最佳迁移到「中等」难度键；旧中途存档布局
        # 与新难度棋盘不匹配，直接丢弃
        for k in [k for k in data["stars"] if k.isdigit()]:
            nk = f"{k}:1"
            data["stars"][nk] = max(data["stars"].pop(k), data["stars"].get(nk, 0))
        for k in [k for k in data["best"] if k.isdigit()]:
            nk = f"{k}:1"
            data["best"][nk] = max(data["best"].pop(k), data["best"].get(nk, 0))
        for k in [k for k in data["checkpoints"] if k.isdigit()]:
            del data["checkpoints"][k]
        # 水果/动物像素画历经改版，旧中途存档的棋盘布局与新版不匹配，
        # 统一丢弃（星级/解锁不受影响）
        for k in [k for k in data["checkpoints"] if k.startswith(("f_", "a_"))]:
            del data["checkpoints"][k]
        return data

    def _write_save(self):
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.save, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save_result(self, key, index, stars, score):
        """
        key 形如 '2:1'（默认第3关·中等）、'f_2:1'（水果第3个·中等）、
        'a_2:1'（动物第3个·中等）。三个主题的星级/解锁各自独立。
        """
        if stars > self.save["stars"].get(key, 0):
            self.save["stars"][key] = stars
        if score > self.save["best"].get(key, 0):
            self.save["best"][key] = score
        nxt = min(index + 2, 6)
        if key.startswith("f_"):
            self.save["fruit_unlocked"] = max(self.save.get("fruit_unlocked", 1), nxt)
        elif key.startswith("a_"):
            self.save["animal_unlocked"] = max(self.save.get("animal_unlocked", 1), nxt)
        else:
            self.save["unlocked"] = max(self.save["unlocked"],
                                        min(index + 2, len(self.levels)))
        self._write_save()

    # ---------- 关卡进度存档 ----------
    def checkpoint_key(self, level_index, seq=0, diff=0, theme=None):
        """默认关卡 '序号:难度'，水果 'f_序号:难度'，动物 'a_序号:难度'；随机按时限。"""
        if level_index < 0:
            return "random" if self.timed_mode is None else f"random:{self.timed_mode}"
        prefix = {"fruit": "f_", "animal": "a_"}.get(theme, "")
        return f"{prefix}{level_index}:{diff}"

    def get_checkpoint(self, key):
        return self.save.get("checkpoints", {}).get(key)

    def save_checkpoint(self, key, level, session):
        checkpoints = self.save.setdefault("checkpoints", {})
        checkpoints[key] = {
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "level": level_to_data(level),
            "data": session.to_checkpoint(),
        }
        self._write_save()

    def clear_checkpoint(self, key):
        checkpoints = self.save.get("checkpoints", {})
        if key in checkpoints:
            del checkpoints[key]
            self._write_save()

    # ---------- 场景跳转 ----------
    def _get_difficulty_level(self, index, diff):
        key = (index, diff)
        if key not in self._level_cache:
            self._level_cache[key] = build_difficulty_level(index, diff)
        return self._level_cache[key]

    def start_level(self, index, diff=0):
        if index >= len(self.levels):
            self.go_theme()
            return
        self.timed_mode = None
        level = self._get_difficulty_level(index, diff)
        checkpoint = self.get_checkpoint(f"{index}:{diff}")
        self.play = PlayState(self, level, level_index=index, diff=diff,
                              checkpoint=checkpoint)
        self.scene = "play"

    def start_shape_level(self, theme, index, diff=0):
        if index >= 6:
            self.go_theme()
            return
        self.timed_mode = None
        key = (theme, index, diff)
        cache_key = f"{theme}_{index}_{diff}"
        if key not in self._level_cache:
            # 先查磁盘缓存，避免重新生成
            if cache_key in self._shape_disk_cache:
                self._level_cache[key] = level_from_data(
                    self._shape_disk_cache[cache_key])
            else:
                level = build_shape_level(theme, index, diff)
                self._level_cache[key] = level
                self._shape_disk_cache[cache_key] = level_to_data(level)
                self._save_shape_cache()
        level = self._level_cache[key]
        prefix = {"fruit": "f_", "animal": "a_"}[theme]
        checkpoint = self.get_checkpoint(f"{prefix}{index}:{diff}")
        self.play = PlayState(self, level, level_index=index, diff=diff,
                              checkpoint=checkpoint)
        self.scene = "play"

    def start_random(self, seq=0, timed=None):
        self.timed_mode = timed
        key = "random" if timed is None else f"random:{timed}"
        checkpoint = self.get_checkpoint(key)
        if checkpoint is not None:
            try:
                level = level_from_data(checkpoint["level"])
                self.play = PlayState(self, level, level_index=-1, seq=seq,
                                      timed=timed, checkpoint=checkpoint)
                self.scene = "play"
                return
            except Exception:
                # 保存的关卡布局损坏：丢弃后按全新随机处理
                self.clear_checkpoint(key)
        level = make_random_level(seq)
        if timed:
            level["time_limit"] = float(timed)
            level["name"] = f"限时挑战·{timed}秒"
        self.play = PlayState(self, level, level_index=-1, seq=seq, timed=timed)
        self.scene = "play"

    def restart_play(self, level, index, seq, diff=0, timed=None):
        # 主动选择"重新开始"：旧进度立即作废，避免再次弹询问
        kind = level.get("shape_kind")
        self.clear_checkpoint(self.checkpoint_key(index, seq, diff, theme=kind))
        if index < 0:
            self.start_random(seq, timed)
        elif kind is not None:
            self.start_shape_level(kind, index, diff)
        else:
            self.start_level(index, diff)

    def go_menu(self):
        self.scene = "menu"
        self.play = None

    def go_theme(self):
        """开始游戏 → 棋盘主题选择页。"""
        self.pick_level = None
        self.pick_timed = False
        self.cur_theme = THEME_DEFAULT
        self.scene = "theme"
        self.play = None

    def open_theme(self, theme):
        """打开某主题下的 6 个关卡列表。"""
        self._build_select_ui()
        self.cur_theme = theme
        self.pick_level = None
        self.pick_timed = False
        self.scene = "select"
        self.play = None

    # ---------- 各界面 UI ----------
    def _build_menu_ui(self):
        self.btn_start = Button((WIDTH // 2 - 150, 430, 300, 72), "开始游戏",
                                "pink", 30, "play")
        self.btn_help = Button((WIDTH // 2 - 150, 522, 300, 66), "玩法说明",
                               "mint", 26)
        self.btn_settings = Button((WIDTH // 2 - 150, 608, 300, 66), "游戏设置",
                                   "blue", 26)
        self.btn_quit = Button((WIDTH // 2 - 150, 694, 300, 66), "退出游戏",
                               "purple", 26)

    def _build_help_ui(self):
        self.btn_help_back = Button((WIDTH // 2 - 120, 800, 240, 62), "返回",
                                    "gray", 24)

    def _build_select_ui(self):
        # 每个主题关卡列表页：返回主题页 + 随机 / 限时快捷入口
        self.btn_select_back = Button((36, 30, 110, 52), "返回", "gray", 22, "back")
        self.btn_select_random = Button((WIDTH - 436, 30, 168, 52), "随机挑战",
                                        "orange", 22, "dice")
        self.btn_select_timed = Button((WIDTH - 252, 30, 168, 52), "限时挑战",
                                       "pink", 22)

    def _build_theme_ui(self):
        # 主题选择页：返回主菜单
        self.btn_theme_back = Button((36, 30, 110, 52), "返回", "gray", 22, "back")
        self.theme_rects = [
            pygame.Rect(70, 300, 250, 320),
            pygame.Rect(335, 300, 250, 320),
            pygame.Rect(600, 300, 250, 320),
        ]

    def _build_boot_ui(self):
        # 启动选择：继续进度 / 从头开始
        self.btn_boot_continue = Button((WIDTH // 2 - 280, 560, 260, 68),
                                        "继续游戏进度", "mint", 24)
        self.btn_boot_reset = Button((WIDTH // 2 + 20, 560, 260, 68),
                                     "从头开始", "pink", 24)

    def _build_pick_ui(self):
        # 难度选择弹窗（点击关卡卡片后弹出）
        n_easy = round(25 * 0.55)
        n_mid = round(36 * 0.70)
        n_hard = round(49 * 0.88)
        self.diff_btns = [
            Button((0, 0, 300, 62), f"简单  5×5 · {n_easy} 支箭头", "mint", 22),
            Button((0, 0, 300, 62), f"中等  6×6 · {n_mid} 支箭头", "orange", 22),
            Button((0, 0, 300, 62), f"困难  7×7 · {n_hard} 支箭头", "pink", 22),
        ]
        self.btn_pick_cancel = Button((0, 0, 150, 46), "取消", "gray", 20)
        # 限时挑战弹窗
        self.timed_btns = [
            Button((0, 0, 300, 58), "15 秒 · 手速挑战", "pink", 22),
            Button((0, 0, 300, 58), "20 秒 · 飞快消除", "orange", 22),
            Button((0, 0, 300, 58), "30 秒 · 从容一些", "blue", 22),
            Button((0, 0, 300, 58), "不限时 · 放松模式", "mint", 20),
        ]
        self.btn_timed_cancel = Button((0, 0, 150, 46), "取消", "gray", 20)
        self.pick_level = None   # None / 关卡序号（难度弹窗）
        self.pick_timed = False  # 限时选择弹窗

    def _build_settings_ui(self):
        self.btn_settings_back = Button((WIDTH // 2 - 110, 758, 220, 56), "返回",
                                        "gray", 24, "back")
        self.slider_rect = pygame.Rect(296, 216, 430, 16)
        self.drag_volume = False
        self.set_dir = Direction.RIGHT  # 当前正在设置的方向
        # 方向选择行（点击后下方的颜色/表情只作用于该方向）
        self.dir_rects = []
        dw, dgap = 100, 16
        dx0 = (WIDTH - (dw * 4 + dgap * 3)) // 2
        for i, d in enumerate(Direction):
            self.dir_rects.append(
                pygame.Rect(dx0 + i * (dw + dgap), 258, dw, 76))
        self.color_rects = []
        cw, gap = 50, 12
        x0 = (WIDTH - (cw * len(ARROW_COLORS) + gap * (len(ARROW_COLORS) - 1))) // 2
        for i in range(len(ARROW_COLORS)):
            self.color_rects.append(pygame.Rect(x0 + i * (cw + gap), 390, cw, cw))
        self.face_rects = []
        fw, fgap = 92, 12
        fx0 = (WIDTH - (fw * 6 + fgap * 5)) // 2
        for i in range(len(FACE_OPTIONS)):
            r, c = divmod(i, 6)
            self.face_rects.append(
                pygame.Rect(fx0 + c * (fw + fgap), 490 + r * (fw + fgap), fw, fw))

    def _set_volume_from_mouse(self, x):
        v = (x - self.slider_rect.x) / self.slider_rect.w
        self.save["volume"] = round(min(1.0, max(0.0, v)), 2)
        self.sounds.set_master(self.save["volume"])

    def _settings_event(self, event):
        s = self.sounds
        if self.btn_settings_back.handle_event(event, s):
            # 从暂停面板进来时回到对局（保持暂停），否则回主菜单
            self.scene = "play" if self.play is not None else "menu"
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hit = self.slider_rect.inflate(16, 30)
            if hit.collidepoint(event.pos):
                self.drag_volume = True
                self._set_volume_from_mouse(event.pos[0])
                return
            for i, rect in enumerate(self.dir_rects):
                if rect.collidepoint(event.pos):
                    self.set_dir = list(Direction)[i]
                    s.play("click")
                    return
            for i, rect in enumerate(self.color_rects):
                if rect.collidepoint(event.pos):
                    self.save["arrow_colors"][self.DIR_KEY[self.set_dir]] = i
                    self._write_save()
                    s.play("click")
                    return
            for i, rect in enumerate(self.face_rects):
                if rect.collidepoint(event.pos):
                    self.save["faces"][self.DIR_KEY[self.set_dir]] = FACE_OPTIONS[i][0]
                    self._write_save()
                    s.play("star")
                    return
        elif event.type == pygame.MOUSEMOTION and self.drag_volume:
            self._set_volume_from_mouse(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.drag_volume:
                self.drag_volume = False
                s.play("click")
                self._write_save()

    def _draw_settings(self, dt):
        panel = jelly_surface(840, 760, (255, 255, 255), (238, 244, 255),
                              radius=34, shadow=14)
        pr = panel.get_rect(center=(WIDTH // 2, 465))
        self.screen.blit(panel, pr)
        title = get_font(42).render("游戏设置", True, (134, 92, 224))
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, pr.top + 52)))

        # ---- 音量滑动条 ----
        lab = get_font(24).render("音量", True, INK)
        self.screen.blit(lab, (pr.x + 80, 182))
        track = self.slider_rect
        pygame.draw.rect(self.screen, (226, 230, 244), track, border_radius=8)
        frac = float(self.save.get("volume", 1.0))
        if frac > 0:
            fill = track.copy()
            fill.width = max(14, int(track.w * frac))
            pygame.draw.rect(self.screen, (134, 92, 224), fill, border_radius=8)
        kx, ky = track.x + int(track.w * frac), track.centery
        kr = 16 if self.drag_volume else 14
        pygame.draw.circle(self.screen, WHITE, (kx, ky), kr)
        pygame.draw.circle(self.screen, (134, 92, 224), (kx, ky), kr,
                           max(3, kr // 4))
        pct = get_font(22).render(f"{int(round(frac * 100))}%", True, (120, 110, 150))
        self.screen.blit(pct, (track.right + 24, ky - pct.get_height() // 2))

        # ---- 方向选择（颜色/表情作用于所选方向） ----
        lab = get_font(24).render("箭头方向", True, INK)
        self.screen.blit(lab, (pr.x + 80, 230))
        dir_names = {Direction.UP: "上", Direction.DOWN: "下",
                     Direction.LEFT: "左", Direction.RIGHT: "右"}
        for i, d in enumerate(Direction):
            rect = self.dir_rects[i]
            cell = jelly_surface(rect.w, rect.h, (255, 255, 255), (240, 246, 255),
                                 radius=18, shadow=4, outline=(214, 226, 248))
            self.screen.blit(cell, rect)
            img = rotated_arrow(44, d, face=self.arrow_face(d),
                                colors=self.arrow_colors(d))
            self.screen.blit(img, img.get_rect(center=(rect.centerx, rect.y + 28)))
            txt = get_font(15, bold=(self.set_dir == d)).render(dir_names[d], True, INK)
            self.screen.blit(txt, txt.get_rect(center=(rect.centerx, rect.bottom - 14)))
            if self.set_dir == d:
                pygame.draw.rect(self.screen, (134, 92, 224),
                                 rect.inflate(8, 8), width=4, border_radius=22)

        # ---- 箭头颜色 ----
        lab = get_font(24).render("箭头颜色", True, INK)
        self.screen.blit(lab, (pr.x + 80, 362))
        sel_color = self.save["arrow_colors"][self.DIR_KEY[self.set_dir]]
        for i, (name, pair) in enumerate(ARROW_COLORS):
            rect = self.color_rects[i]
            if pair is None:  # 经典四色：2×2 小色块
                base = jelly_surface(rect.w, rect.h, (255, 255, 255), (238, 240, 250),
                                     radius=16, shadow=4, outline=(214, 226, 248))
                self.screen.blit(base, rect)
                for j, (ct, cb) in enumerate(DIR_STYLE.values()):
                    sub = pygame.Rect(rect.x + 5 + (j % 2) * (rect.w // 2 - 3),
                                      rect.y + 5 + (j // 2) * (rect.h // 2 - 3),
                                      rect.w // 2 - 6, rect.h // 2 - 6)
                    mini = jelly_surface(sub.w, sub.h, ct, cb, radius=8, shadow=0)
                    self.screen.blit(mini, sub)
            else:
                top, bottom = pair
                body = jelly_surface(rect.w, rect.h, top, bottom, radius=16, shadow=4)
                self.screen.blit(body, rect)
            if sel_color == i:
                pygame.draw.rect(self.screen, (134, 92, 224),
                                 rect.inflate(10, 10), width=4, border_radius=20)

        # ---- 箭头表情 ----
        lab = get_font(24).render("箭头表情", True, INK)
        self.screen.blit(lab, (pr.x + 80, 462))
        sel_face = self.save["faces"][self.DIR_KEY[self.set_dir]]
        for i, (key, name) in enumerate(FACE_OPTIONS):
            rect = self.face_rects[i]
            cell = jelly_surface(rect.w, rect.h, (255, 255, 255), (240, 246, 255),
                                 radius=18, shadow=4, outline=(214, 226, 248))
            self.screen.blit(cell, rect)
            img = rotated_arrow(52, Direction.RIGHT,
                                face=DIRECTION_FACE[self.set_dir] if key == "classic" else key,
                                colors=self.arrow_colors(self.set_dir))
            self.screen.blit(img, img.get_rect(center=(rect.centerx, rect.y + 32)))
            txt = get_font(15, bold=(sel_face == key)).render(name, True, INK)
            self.screen.blit(txt, txt.get_rect(center=(rect.centerx, rect.bottom - 15)))
            if sel_face == key:
                pygame.draw.rect(self.screen, (134, 92, 224),
                                 rect.inflate(8, 8), width=4, border_radius=22)
        self.btn_settings_back.draw(self.screen, dt)

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
        if self.scene == "boot":
            if self.btn_boot_continue.handle_event(event, self.sounds):
                self.scene = "menu"
            elif self.btn_boot_reset.handle_event(event, self.sounds):
                self.reset_progress()
                self.sounds.set_master(float(self.save.get("volume", 1.0)))
                self.scene = "menu"
        elif self.scene == "menu":
            if self.btn_start.handle_event(event, self.sounds):
                self.go_theme()
            elif self.btn_help.handle_event(event, self.sounds):
                self.scene = "help"
            elif self.btn_settings.handle_event(event, self.sounds):
                self.scene = "settings"
            elif self.btn_quit.handle_event(event, self.sounds):
                pygame.quit()
                sys.exit(0)
        elif self.scene == "theme":
            self._theme_event(event)
        elif self.scene == "help":
            if self.btn_help_back.handle_event(event, self.sounds):
                self.scene = "menu"
        elif self.scene == "settings":
            self._settings_event(event)
        elif self.scene == "select":
            self._select_event(event)
        elif self.scene == "play":
            self.play.handle_event(event)

    def update(self, dt):
        if self.scene == "play" and self.play is not None:
            self.play.update(dt)

    # ---------- 棋盘主题选择 ----------
    def _theme_event(self, event):
        s = self.sounds
        if self.btn_theme_back.handle_event(event, s):
            self.scene = "menu"
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.btn_theme_back.rect.collidepoint(event.pos):
                self.scene = "menu"
                return
            for theme, rect in zip((THEME_DEFAULT, THEME_FRUIT, THEME_ANIMAL),
                                   self.theme_rects):
                if rect.collidepoint(event.pos):
                    s.play("click")
                    self.open_theme(theme)
                    return

    def _draw_theme(self, dt):
        title = get_font(44).render("选择棋盘主题", True, WHITE)
        ot = get_font(44).render("选择棋盘主题", True, (134, 92, 224))
        x = WIDTH // 2 - title.get_width() // 2
        self.screen.blit(ot, (x + 3, 103))
        self.screen.blit(title, (x, 100))
        sub = get_font(19).render("三种风格棋盘，每个主题 6 个关卡",
                                  True, (24, 22, 34))
        self.screen.blit(sub, sub.get_rect(center=(WIDTH // 2, 172)))
        self.btn_theme_back.draw(self.screen, dt)

        themes = (THEME_DEFAULT, THEME_FRUIT, THEME_ANIMAL)
        for theme, rect in zip(themes, self.theme_rects):
            hover = rect.collidepoint(self.mouse)
            card = jelly_surface(rect.w, rect.h, (255, 255, 255),
                                 (228, 236, 250), radius=30,
                                 shadow=10 if not hover else 14, gloss=True,
                                 outline=(210, 224, 246))
            self.screen.blit(card, (rect.x, rect.y - (4 if hover else 0)))
            self._draw_theme_preview(theme, rect)
            name = get_font(28).render(THEME_LABELS[theme], True, INK)
            self.screen.blit(name, name.get_rect(center=(rect.centerx, rect.bottom - 66)))
            desc_text = {THEME_DEFAULT: "经典矩形棋盘",
                         THEME_FRUIT: "水果形状异形棋盘",
                         THEME_ANIMAL: "动物形状异形棋盘"}[theme]
            desc = get_font(17).render(desc_text, True, (88, 80, 112))
            self.screen.blit(desc, desc.get_rect(center=(rect.centerx, rect.bottom - 34)))

    def _draw_theme_preview(self, theme, rect):
        """主题卡片上半部的形状缩略预览。"""
        if theme == THEME_DEFAULT:
            # 4×4 小网格
            n = 4
            cell = 22
            pw = cell * n
            px = rect.centerx - pw // 2
            py = rect.y + 44
            for r in range(n):
                for c in range(n):
                    rct = pygame.Rect(px + c * cell, py + r * cell, cell - 3, cell - 3)
                    mini = jelly_surface(rct.w, rct.h, (236, 244, 255),
                                         (200, 222, 252), radius=6, shadow=0)
                    self.screen.blit(mini, rct)
            return
        metas = self.theme_meta(theme)
        meta = metas[0]  # 水果取苹果、动物取小猫作为代表
        blit_pixel_preview(self.screen, meta["cells"], rect.centerx,
                           rect.y + 30, 190, 190)

    # ---------- 启动选择 ----------
    def _draw_boot(self, dt):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((52, 38, 92, 140))
        self.screen.blit(overlay, (0, 0))
        panel = jelly_surface(700, 400, (255, 255, 255), (235, 241, 255),
                              radius=34, shadow=14)
        pr = panel.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 40))
        self.screen.blit(panel, pr)
        title = get_font(34).render("欢迎回来，小箭神！", True, INK)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, pr.top + 72)))
        tip = get_font(21).render("检测到上次的游戏进度，要继续吗？", True, (126, 112, 164))
        self.screen.blit(tip, tip.get_rect(center=(WIDTH // 2, pr.top + 128)))
        note = get_font(17).render("选择「从头开始」将清空全部星级与解锁记录（音量等设置保留）",
                                   True, (160, 148, 188))
        self.screen.blit(note, note.get_rect(center=(WIDTH // 2, pr.top + 200)))
        self.btn_boot_continue.rect.center = (WIDTH // 2 - 150, pr.top + 290)
        self.btn_boot_reset.rect.center = (WIDTH // 2 + 150, pr.top + 290)
        self.btn_boot_continue.draw(self.screen, dt)
        self.btn_boot_reset.draw(self.screen, dt)

    # ---------- 选关 ----------
    def _card_rect(self, i):
        cols = 3
        cw, ch = 252, 178
        gap_x, gap_y = 28, 26
        x0 = (WIDTH - (cw * cols + gap_x * (cols - 1))) // 2
        y0 = 194
        r, c = divmod(i, cols)
        return pygame.Rect(x0 + c * (cw + gap_x), y0 + r * (ch + gap_y), cw, ch)

    def _select_event(self, event):
        s = self.sounds
        # 弹窗打开时只响应弹窗内部
        if self.pick_level is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, b in enumerate(self.diff_btns):
                    if b.rect.collidepoint(event.pos):
                        idx = self.pick_level
                        theme = self.cur_theme
                        self.pick_level = None
                        if theme == THEME_DEFAULT:
                            self.start_level(idx, i)
                        else:
                            self.start_shape_level(theme, idx, i)
                        return
                if self.btn_pick_cancel.rect.collidepoint(event.pos):
                    s.play("click")
                    self.pick_level = None
            return
        if self.pick_timed:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, b in enumerate(self.timed_btns):
                    if b.rect.collidepoint(event.pos):
                        self.pick_timed = False
                        self.start_random(0, timed=(15, 20, 30, None)[i])
                        return
                if self.btn_timed_cancel.rect.collidepoint(event.pos):
                    s.play("click")
                    self.pick_timed = False
            return

        self.btn_select_back.handle_event(event, s)
        self.btn_select_random.handle_event(event, s)
        self.btn_select_timed.handle_event(event, s)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.btn_select_back.rect.collidepoint(event.pos):
                self.scene = "theme"
                return
            if self.btn_select_random.rect.collidepoint(event.pos):
                self.start_random(0)
                return
            if self.btn_select_timed.rect.collidepoint(event.pos):
                self.pick_timed = True
                return
            total = 6
            for i in range(total):
                rect = self._card_rect(i)
                if rect.collidepoint(event.pos):
                    unlocked = self._is_unlocked(self.cur_theme, i)
                    if unlocked:
                        s.play("click")
                        self.pick_level = i
                    else:
                        s.play("collide")

    def _is_unlocked(self, theme, i):
        if theme == THEME_DEFAULT:
            return i + 1 <= self.save.get("unlocked", 1)
        # 水果/动物主题全解锁，用户自由选择
        return True

    # ---------- 绘制分发 ----------
    def _day_progress(self):
        """天色 10 秒完成一次早晨到夜晚的更替，到夜晚后重新循环。"""
        return (self.t % 10.0) / 10.0

    def draw(self, dt):
        self.bg.draw(self.screen, self.t, self._day_progress())
        if self.scene == "menu":
            self._draw_menu(dt)
        elif self.scene == "boot":
            self._draw_boot(dt)
        elif self.scene == "theme":
            self._draw_theme(dt)
        elif self.scene == "help":
            self._draw_help(dt)
        elif self.scene == "settings":
            self._draw_settings(dt)
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
        # 装饰：四只表情各异的漂浮大箭头（实时预览各自方向的配色与表情设置）
        for i, d in enumerate(Direction):
            size = 100
            img = rotated_arrow(size, d, face=self.arrow_face(d),
                                colors=self.arrow_colors(d))
            phase = self.t * 0.9 + i * 1.7
            x = 150 + i * 206 + math.sin(phase) * 16
            y = 150 + math.cos(phase * 0.8) * 20
            tilt = math.sin(self.t * 1.3 + i * 1.1) * 7
            if abs(tilt) > 0.4:
                img = pygame.transform.rotate(img, tilt)
            img.set_alpha(235)
            self.screen.blit(img, img.get_rect(center=(int(x), int(y))))

        # 标题
        title = get_font(72).render("重生之我是箭神", True, WHITE)
        outline = get_font(72).render("重生之我是箭神", True, (134, 92, 224))
        x = WIDTH // 2 - title.get_width() // 2
        y = 226
        for dx, dy in ((-3, 3), (3, 3), (0, 4)):
            self.screen.blit(outline, (x + dx, y + dy))
        self.screen.blit(title, (x, y))
        sub = get_font(24).render("糖果色箭头解谜 · 点一点，让箭飞出棋盘", True, INK)
        self.screen.blit(sub, sub.get_rect(center=(WIDTH // 2, 336)))

        self.btn_start.draw(self.screen, dt)
        self.btn_help.draw(self.screen, dt)
        self.btn_settings.draw(self.screen, dt)
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
        theme = self.cur_theme
        is_shape = theme != THEME_DEFAULT
        title_text = THEME_LABELS[theme]
        title = get_font(46).render(title_text, True, WHITE)
        ot = get_font(46).render(title_text, True, (134, 92, 224))
        x = WIDTH // 2 - title.get_width() // 2
        self.screen.blit(ot, (x + 3, 103))
        self.screen.blit(title, (x, 100))
        sub = get_font(19).render("点击关卡卡片，选择 简单 / 中等 / 困难 难度开始",
                                  True, (24, 22, 34))
        self.screen.blit(sub, sub.get_rect(center=(WIDTH // 2, 172)))
        self.btn_select_back.draw(self.screen, dt)
        self.btn_select_random.draw(self.screen, dt)
        self.btn_select_timed.draw(self.screen, dt)

        metas = self.theme_meta(theme) if is_shape else None
        card_styles = (["blue", "pink", "mint", "orange", "purple", "blue"]
                       if not is_shape else
                       ["pink", "mint", "orange", "grape", "red", "yellow"])
        # 回退到已注册的按钮配色，避免 KeyError
        for i_s, st in enumerate(card_styles):
            if st not in BUTTON_STYLE:
                card_styles[i_s] = ["pink", "mint", "blue", "orange", "purple"][i_s % 5]

        for i in range(6):
            rect = self._card_rect(i)
            unlocked = self._is_unlocked(theme, i)
            hover = unlocked and self.pick_level is None and not self.pick_timed \
                and rect.collidepoint(self.mouse)
            offset = 6 if hover else 0
            top, bottom = BUTTON_STYLE[card_styles[i]]
            if not unlocked:
                top, bottom = (214, 216, 226), (184, 188, 204)
            card = jelly_surface(rect.w, rect.h, top, bottom, radius=26, shadow=8,
                                 gloss=True)
            self.screen.blit(card, (rect.x, rect.y + 4 + offset))

            if is_shape:
                meta = metas[i]
                self._draw_card_shape(meta, rect, offset)
                level_name = meta["name"]
                name = get_font(26).render(level_name, True, (40, 30, 56))
                self.screen.blit(name, name.get_rect(
                    center=(rect.centerx, rect.y + 130 + offset)))
                star_key_prefix = "f_" if theme == THEME_FRUIT else "a_"
            else:
                num = get_font(40).render(f"第 {i + 1} 关", True, WHITE)
                self.screen.blit(num, num.get_rect(
                    center=(rect.centerx, rect.y + 44 + offset)))
                name = get_font(22).render(self.levels[i]["name"], True, WHITE)
                self.screen.blit(name, name.get_rect(
                    center=(rect.centerx, rect.y + 90 + offset)))
                star_key_prefix = ""

            if unlocked:
                sk = f"{star_key_prefix}{i}"
                stars = max(self.save["stars"].get(f"{sk}:{d}", 0) for d in range(3))
                star_y = rect.bottom - 30 if is_shape else rect.y + 140
                for k in range(3):
                    s = star_surface(28 if is_shape else 30, gray=k >= stars)
                    self.screen.blit(s, s.get_rect(
                        center=(rect.centerx + (k - 1) * (34 if is_shape else 38),
                                star_y + offset)))
                if not is_shape:
                    best = max((self.save["best"].get(f"{i}:{d}", 0) for d in range(3)),
                               default=0)
                    if best:
                        bt = get_font(15).render(f"最佳 {best}", True, WHITE)
                        self.screen.blit(bt, bt.get_rect(
                            center=(rect.centerx, rect.bottom - 12 + offset)))
            else:
                lock = pygame.Surface((40, 40), pygame.SRCALPHA)
                pygame.draw.arc(lock, WHITE, (8, 0, 24, 20), math.pi, 3 * math.pi, 5)
                pygame.draw.rect(lock, WHITE, (4, 18, 32, 20), border_radius=6)
                pygame.draw.circle(lock, (150, 155, 178), (20, 26), 3)
                lock_y = rect.bottom - 28 if is_shape else rect.y + 142
                self.screen.blit(lock, lock.get_rect(
                    center=(rect.centerx, lock_y + offset)))

        if self.pick_level is not None:
            self._draw_diff_pick(dt)
        elif self.pick_timed:
            self._draw_timed_pick(dt)

    def _draw_card_shape(self, meta, rect, offset):
        """关卡卡片上的像素画缩略预览。"""
        blit_pixel_preview(self.screen, meta["cells"], rect.centerx,
                           rect.y + 14 + offset, 150, 110)

    def _draw_diff_pick(self, dt):
        d = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        d.fill((70, 50, 110, 150))
        self.screen.blit(d, (0, 0))
        panel = jelly_surface(560, 430, (255, 255, 255), (236, 242, 255),
                              radius=32, shadow=12)
        pr = panel.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        self.screen.blit(panel, pr)
        is_shape = self.cur_theme != THEME_DEFAULT
        if is_shape:
            metas = self.theme_meta(self.cur_theme)
            name = metas[self.pick_level]["name"]
            title = get_font(32).render(f"{name} · 选择难度", True, INK)
            tip = get_font(19).render("同一种形状，箭头越多越烧脑", True, (130, 120, 160))
        else:
            name = self.levels[self.pick_level]["name"]
            title = get_font(32).render(f"第 {self.pick_level + 1} 关 · 选择难度", True, INK)
            tip = get_font(19).render(f"「{name}」三种棋盘规格，箭头越多越烧脑", True, (130, 120, 160))
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, pr.top + 62)))
        self.screen.blit(tip, tip.get_rect(center=(WIDTH // 2, pr.top + 112)))
        # 形状关卡难度按钮文案：同形状，箭头数随难度递增
        if is_shape:
            metas = self.theme_meta(self.cur_theme)
            n_active = metas[self.pick_level]["playable"]
            for i, (label, ratio, _tl) in enumerate(
                    [("简单", 0.50, 75), ("中等", 0.70, 105), ("困难", 0.88, 140)]):
                self.diff_btns[i].text = f"{label}  · {round(n_active * ratio)} 支箭头"
        else:
            # 默认主题按钮文案恢复为棋盘规格文案
            n_easy = round(25 * 0.55)
            n_mid = round(36 * 0.70)
            n_hard = round(49 * 0.88)
            texts = [f"简单  5×5 · {n_easy} 支箭头",
                     f"中等  6×6 · {n_mid} 支箭头",
                     f"困难  7×7 · {n_hard} 支箭头"]
            for i, t in enumerate(texts):
                self.diff_btns[i].text = t
        for i, b in enumerate(self.diff_btns):
            b.rect.center = (WIDTH // 2, pr.top + 170 + i * 76)
            b.draw(self.screen, dt)
        self.btn_pick_cancel.rect.center = (WIDTH // 2, pr.bottom - 52)
        self.btn_pick_cancel.draw(self.screen, dt)

    def _draw_timed_pick(self, dt):
        d = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        d.fill((70, 50, 110, 150))
        self.screen.blit(d, (0, 0))
        panel = jelly_surface(560, 540, (255, 255, 255), (255, 240, 250),
                              radius=32, shadow=12)
        pr = panel.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        self.screen.blit(panel, pr)
        title = get_font(32).render("限时挑战", True, (232, 62, 130))
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, pr.top + 60)))
        tip = get_font(19).render("在倒计时归零前清空全部箭头！", True, (130, 120, 160))
        self.screen.blit(tip, tip.get_rect(center=(WIDTH // 2, pr.top + 110)))
        for i, b in enumerate(self.timed_btns):
            b.rect.center = (WIDTH // 2, pr.top + 158 + i * 72)
            b.draw(self.screen, dt)
        self.btn_timed_cancel.rect.center = (WIDTH // 2, pr.bottom - 52)
        self.btn_timed_cancel.draw(self.screen, dt)


def main():
    App().run()


if __name__ == "__main__":
    main()
