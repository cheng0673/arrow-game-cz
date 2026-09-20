# -*- coding: utf-8 -*-
"""
插画风格动态场景模块
====================
按参考插画重绘的童话草地场景，包含：

* 柔和的天空渐变与地平线附近的白色薄雾；
* 随风漂移、上下轻浮的大朵蓬松白云（带柔和底部阴影）；
* 从草地升起、左右轻摆的虹彩泡泡；
* 右侧淡淡的粉彩彩虹；
* 右侧一束随风摇摆的彩色气球；
* 绿色草坡上摇曳的白色雏菊、粉色杯花、黄色小花和郁金香花苞；
* 在空中缓缓飘落旋转的花瓣与嫩叶；
* 底部扇贝形花边与上面的小花；
* 白天的太阳（旋转柔光 + 呼吸光晕）与夜晚的月亮、星星。

天色随 ``day_p``（0~1）在「早晨 → 中午 → 傍晚 → 夜晚 → 破晓」之间平滑变化，
末段渐亮回早晨颜色，绕回时无缝衔接；调用方按 10 秒一个周期传入即可。
对外只暴露 ``DreamScene.draw(surf, t, day_p)``。
"""
import math
import random

import pygame


# 天色色标：(时刻 0~1, 天空顶部颜色, 天空底部颜色)
# 末段「破晓」渐亮回早晨颜色，与 0.00 处相同，昼夜绕回时无缝衔接
_SKY_STOPS = [
    (0.00, (255, 183, 150), (255, 226, 170)),   # 早晨：粉橘朝霞
    (0.30, (102, 184, 234), (205, 239, 249)),   # 中午：明亮天蓝
    (0.55, (255, 138, 88), (128, 92, 196)),     # 傍晚：橙紫晚霞
    (0.70, (24, 28, 82), (66, 56, 126)),        # 入夜：深蓝星空
    (0.88, (24, 28, 82), (66, 56, 126)),        # 深夜：保持星空
    (1.00, (255, 183, 150), (255, 226, 170)),   # 破晓：渐亮回朝霞
]

# 草坡三个色标（远 / 中 / 近），夜晚向这些颜色压暗
_GRASS_DAY = ((198, 237, 134), (156, 217, 102), (110, 195, 94))
_GRASS_NIGHT = ((58, 98, 78), (42, 80, 68), (30, 62, 58))

# 大朵白云的组成：相对中心的偏移与半径
_CLOUD_BLOBS = ((-72, 12, 38), (-34, -18, 50), (20, -26, 56),
                (74, -12, 48), (96, 10, 38), (8, 16, 48),
                (-56, 24, 32))

# 粉彩彩虹的七条弧光色（外 → 内）
_RAINBOW = ((255, 196, 196), (255, 218, 178), (255, 242, 184),
            (200, 238, 186), (184, 232, 232), (192, 214, 246),
            (214, 200, 242))

# 右侧气球：(x比例, y比例, 颜色)
_BALLOONS = [
    (0.898, 0.466, (255, 220, 96)),    # 黄
    (0.946, 0.510, (255, 158, 178)),   # 粉
    (0.866, 0.544, (172, 222, 240)),   # 蓝
    (0.952, 0.572, (192, 162, 226)),   # 紫
]


def _clamp(v, lo=0, hi=255):
    return max(lo, min(hi, v))


def _mix(c1, c2, f):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * f) for i in range(3))


class DreamScene:
    """可插拔的插画风格动态背景，独立于游戏逻辑。"""

    SKY_STEPS = 64

    def __init__(self, width, height):
        self.w = int(width)
        self.h = int(height)
        self.u = min(self.w, self.h) / 920.0   # 等比缩放基准
        rng = random.Random(20260920)
        u = self.u

        # 草坡起始高度
        self.meadow_y = int(self.h * 0.67)

        # 大朵白云：x比例, y比例, 缩放, 漂移速度
        self.clouds = [
            [0.30, 0.215, 1.18, 10.0],
            [0.16, 0.335, 1.28, 8.0],
            [0.27, 0.415, 1.02, 12.0],
            [0.62, 0.435, 0.78, 14.0],
            [0.78, 0.330, 1.16, 9.0],
            [0.87, 0.145, 0.98, 11.0],
        ]

        # 虹彩泡泡：x, 初始y, 半径, 上升速度
        self.bubbles = []
        for _ in range(18):
            self.bubbles.append([
                rng.uniform(10, self.w - 10), rng.uniform(0, self.h),
                rng.uniform(6, 19) * u, rng.uniform(20, 52)])

        # 星星
        self.stars = [
            (rng.uniform(20, self.w - 20), rng.uniform(24, self.h * 0.60),
             rng.uniform(1.5, 3.4), rng.uniform(0, 6.28))
            for _ in range(46)]

        # 草坡上的花
        self.flowers = []
        for _ in range(48):
            y = rng.uniform(self.meadow_y + 24, self.h - 26)
            depth = (y - self.meadow_y) / (self.h - self.meadow_y)
            sc = 0.55 + depth * 0.95 + rng.uniform(-0.08, 0.12)
            roll = rng.random()
            if roll < 0.52:
                kind = "daisy"
            elif roll < 0.72:
                kind = "cosmos"
            elif roll < 0.90:
                kind = "yellow"
            else:
                kind = "tulip"
            self.flowers.append([
                rng.uniform(24, self.w - 24), y, kind, sc,
                rng.uniform(0, 6.28),
                rng.uniform(16, 38) * (0.6 + depth)])

        # 草叶纹理
        self.blades = []
        for _ in range(150):
            self.blades.append((
                rng.uniform(0, self.w),
                rng.uniform(self.meadow_y + 16, self.h - 8),
                rng.uniform(5, 10) * u, rng.uniform(-0.5, 0.5),
                rng.choice([True, False])))

        # 飘落的花瓣 / 嫩叶
        self.petals = []
        for _ in range(15):
            kind = rng.choice(("pink", "pink", "yellow", "leaf"))
            self.petals.append([
                rng.uniform(-20, self.w + 20), rng.uniform(-40, self.h),
                rng.uniform(7, 13) * u, rng.uniform(18, 40),
                rng.uniform(0, 6.28), rng.uniform(0.8, 1.8),
                rng.uniform(-6, 6), rng.uniform(-1.6, 1.6), kind])

        # 童趣小蝴蝶：花丛间飞舞
        bcolors = ((255, 150, 190), (186, 158, 255), (255, 208, 92))
        self.butterflies = []
        for i in range(3):
            self.butterflies.append((
                rng.uniform(self.w * 0.12, self.w * 0.88),
                rng.uniform(self.meadow_y + 40, self.h - 60),
                rng.uniform(0, 6.28), bcolors[i]))

        # 闪烁星光：天空 / 草坡分开存放
        self.sky_sparks = []
        self.grass_sparks = []
        for _ in range(48):
            x = rng.uniform(14, self.w - 14)
            y = rng.uniform(self.h * 0.30, self.h - 40)
            item = (x, y, rng.uniform(2.0, 5.0), rng.uniform(0, 6.28))
            if y < self.meadow_y:
                self.sky_sparks.append(item)
            else:
                self.grass_sparks.append(item)

        # 扇贝花边参数
        self.scallop_y = self.h - int(30 * u)
        self.scallop_r = int(31 * u)
        self.scallop_step = int(58 * u)

        self._sky_cache = {}
        self._rainbow_cache = {}
        self._petal_cache = {}
        self._cloud_cache = {}
        self._meadow_cache = {}
        self._bubble_cache = {}
        self._spark_cache = {}
        self._sun_glow = None
        self.layer = pygame.Surface((self.w, self.h), pygame.SRCALPHA)

    # ---------------- 工具 ----------------
    @staticmethod
    def _smooth01(v):
        v = _clamp(v, 0, 1)
        return v * v * (3 - 2 * v)

    def _night_weight(self, p):
        # 55% 处开始入夜，72% 完全入夜；88%~100% 破晓渐亮，绕回 p=0 时为 0，无缝衔接
        rise = self._smooth01((p - 0.55) / 0.17)
        fall = 1 - self._smooth01((p - 0.88) / 0.12)
        return rise * fall

    def _dim(self, color, night, keep=0.45):
        """夜晚把鲜艳颜色压暗到 keep 左右。"""
        return _mix(color, _mix(color, (40, 46, 80), 0.75), night * keep)

    def _petal_shape(self, length, width, color, ang):
        """按方向旋转的双色花瓣（3 倍超采样，清晰且有立体感）。"""
        key = (int(round(length)), int(round(width)), color,
               int(round(math.degrees(ang) / 22.5)) % 16)
        s = self._petal_cache.get(key)
        if s is None:
            lw = max(int(length * 2) + 6, 6)
            ww = max(int(width * 2) + 6, 6)
            big = pygame.Surface((lw * 3, ww * 3), pygame.SRCALPHA)
            rect = pygame.Rect(9, 9, lw * 3 - 18, ww * 3 - 18)
            # 暗色底 + 亮色受光面，花瓣根深梢浅
            dark = _mix(color, (95, 75, 125), 0.20)
            light = _mix(color, (255, 255, 255), 0.42)
            pygame.draw.ellipse(big, dark, rect)
            hi = rect.inflate(-rect.w // 4, -rect.h // 2)
            hi.topleft = (9 + rect.w // 5, 9 + rect.h // 10)
            pygame.draw.ellipse(big, light, hi)
            pygame.draw.polygon(big, light,
                                [(lw * 3 - 4, ww * 3 // 2),
                                 (lw * 3 - 27, 8), (lw * 3 - 27, ww * 3 - 8)])
            s = pygame.transform.smoothscale(big, (lw, ww))
            s = pygame.transform.rotate(s, -math.degrees(ang))
            if len(self._petal_cache) < 1400:
                self._petal_cache[key] = s
        return s

    def _sky_colors(self, p):
        pp = _clamp(p, 0, 1)
        for i in range(len(_SKY_STOPS) - 1):
            p0, top0, bot0 = _SKY_STOPS[i]
            p1, top1, bot1 = _SKY_STOPS[i + 1]
            if pp <= p1:
                f = (pp - p0) / (p1 - p0)
                return _mix(top0, top1, f), _mix(bot0, bot1, f)
        return _SKY_STOPS[-1][1], _SKY_STOPS[-1][2]

    def _celestial(self, p):
        """太阳/月亮的中心位置与可见度（0~1）。"""
        horizon = self.h * 0.70
        arc = self.h * 0.46
        mid_x = self.w * 0.5
        half_w = self.w * 0.42

        # 太阳：白天 0~2/3 沿弧线移动；夜晚藏于左侧地平线，
        # 破晓 0.94~1.0 在原地渐显，与 p=0 的位置完全一致，绕回无缝
        s = _clamp(p / (2 / 3), 0, 1)
        if p >= 2 / 3:
            sx, sy = mid_x - half_w, horizon
        else:
            sx, sy = (mid_x - half_w + 2 * half_w * s,
                      horizon - math.sin(s * math.pi) * arc)
        sun_vis = max(self._smooth01((0.72 - p) / 0.10),
                      _clamp((p - 0.94) / 0.06, 0, 1))
        sun = (sx, sy, sun_vis)

        m = _clamp((p - 2 / 3) / (1 / 3), 0, 1)
        moon = (mid_x - half_w + 2 * half_w * m,
                horizon - math.sin(m * math.pi) * arc,
                self._smooth01((p - 0.66) / 0.10)
                * (1 - self._smooth01((p - 0.93) / 0.07)))
        return sun, moon

    # ---------------- 天空 ----------------
    def _build_sky(self, step):
        p = step / self.SKY_STEPS
        top, bottom = self._sky_colors(p)
        night = self._night_weight(p)
        sky = pygame.Surface((self.w, self.h))
        for y in range(self.h):
            f = y / max(1, self.h - 1)
            color = _mix(top, bottom, f)
            # 地平线附近的白色薄雾
            d = abs(y - self.h * 0.62) / (self.h * 0.14)
            if d < 1.0:
                color = _mix(color, (255, 255, 255),
                             (1.0 - d) * 0.55 * (1 - night * 0.7))
            pygame.draw.line(sky, color, (0, y), (self.w, y))
        self._sky_cache[step] = sky
        if len(self._sky_cache) > self.SKY_STEPS + 2:
            self._sky_cache.clear()
            self._sky_cache[step] = sky

    def _draw_stars(self, layer, t, night):
        if night <= 0:
            return
        for x, y, r, phase in self.stars:
            tw = 0.45 + 0.55 * abs(math.sin(t * 2.4 + phase))
            a = int(210 * tw * night)
            s = r * 2.1
            pts = []
            for i in range(4):
                ang = -math.pi / 2 + i * math.pi / 2 + phase * 0.2
                pts.append((x + s * 0.5 * math.cos(ang),
                            y + s * 0.5 * math.sin(ang)))
                ang += math.pi / 4
                pts.append((x + s * 0.16 * math.cos(ang),
                            y + s * 0.16 * math.sin(ang)))
            pygame.draw.polygon(layer, (255, 255, 240, a), pts)

    def _draw_sun(self, layer, x, y, vis, t):
        if vis <= 0:
            return
        x, y = int(x), int(y)
        pulse = 0.85 + 0.15 * math.sin(t * 1.8)
        u = self.u
        # 柔和径向光晕（只建一次，整体调透明度）
        if self._sun_glow is None:
            gs = int(210 * u)
            glow = pygame.Surface((gs, gs), pygame.SRCALPHA)
            gc = gs // 2
            for rad, a in ((98, 16), (82, 24), (66, 36), (52, 52)):
                pygame.draw.circle(glow, (255, 234, 150, a),
                                   (gc, gc), int(rad * u))
            self._sun_glow = glow
        self._sun_glow.set_alpha(int(235 * vis * pulse))
        layer.blit(self._sun_glow,
                   self._sun_glow.get_rect(center=(x, y)))
        # 缓缓旋转的锥形光芒
        size = int(220 * u)
        rays = pygame.Surface((size, size), pygame.SRCALPHA)
        rc = size / 2
        for i in range(12):
            mid = i * math.pi / 6 + t * 0.2
            rb, rt = 50 * u, 90 * u
            pts = [
                (rc + (rb) * math.cos(mid - 0.10),
                 rc + (rb) * math.sin(mid - 0.10)),
                (rc + rt * math.cos(mid),
                 rc + rt * math.sin(mid)),
                (rc + rb * math.cos(mid + 0.10),
                 rc + rb * math.sin(mid + 0.10))]
            pygame.draw.polygon(rays, (255, 224, 120, int(120 * vis)), pts)
        layer.blit(rays, rays.get_rect(center=(x, y)))
        # 奶油色太阳本体
        pygame.draw.circle(layer, (255, 246, 206, int(255 * vis)),
                           (x, y), int(44 * u))
        pygame.draw.circle(layer, (255, 253, 232, int(255 * vis)),
                           (x, y), int(28 * u))
        # 童趣笑脸：两道弯弯的眯眯眼 + 微笑弧（不透明插值色，随日落淡出）
        ew = max(2, int(3 * u))
        fc = _mix((255, 246, 206), (255, 190, 96), vis)
        for sx in (-16, 16):
            pygame.draw.arc(layer, fc,
                            pygame.Rect(x + sx - 8, y - 13, 16, 12),
                            math.radians(200), math.radians(340), ew)
        pygame.draw.arc(layer, fc,
                        pygame.Rect(x - 11, y + 1, 22, 13),
                        math.radians(20), math.radians(160), ew)

    def _draw_moon(self, layer, x, y, vis, t):
        if vis <= 0:
            return
        x, y = int(x), int(y)
        u = self.u
        pygame.draw.circle(layer, (235, 240, 255, int(60 * vis)),
                           (x, y), int(52 * u))
        pygame.draw.circle(layer, (246, 248, 255, int(255 * vis)),
                           (x, y), int(34 * u))
        for dx, dy, r in ((-12, -8, 7), (10, 6, 9), (2, 18, 5)):
            pygame.draw.circle(layer, (214, 220, 238, int(200 * vis)),
                               (x + int(dx * u), y + int(dy * u)),
                               int(r * u))

    # ---------------- 彩虹 ----------------
    def _build_rainbow(self, alpha):
        s = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        cx, cy = self.w * 0.93, self.h * 0.92
        r_out = self.w * 0.48
        thick = int(11 * self.u)
        a0, a1 = math.radians(208), math.radians(305)
        steps = 16
        for i, color in enumerate(_RAINBOW):
            ro = r_out - i * thick
            ri = ro - thick
            pts = []
            for j in range(steps + 1):
                a = a0 + (a1 - a0) * j / steps
                pts.append((cx + ro * math.cos(a), cy + ro * math.sin(a)))
            for j in range(steps, -1, -1):
                a = a0 + (a1 - a0) * j / steps
                pts.append((cx + ri * math.cos(a), cy + ri * math.sin(a)))
            pygame.draw.polygon(s, (*color, alpha), pts)
        return s

    def _draw_rainbow(self, layer, night):
        vis = 1.0 - night
        if vis <= 0.02:
            return
        key = int(vis * 20)
        s = self._rainbow_cache.get(key)
        if s is None:
            s = self._build_rainbow(int(135 * vis))
            if len(self._rainbow_cache) <= 22:
                self._rainbow_cache[key] = s
        layer.blit(s, (0, 0))

    # ---------------- 云朵 ----------------
    def _build_cloud(self, sc):
        """2 倍超采样绘制立体云团：暗部 / 主体 / 高光三层，光影分明。"""
        u = self.u
        wpx = int(300 * u * sc)
        hpx = int(150 * u * sc)
        big = pygame.Surface((wpx * 2, hpx * 2), pygame.SRCALPHA)
        k = u * sc * 2
        cx = int(wpx * 0.92)
        cy = int(hpx * 1.44)
        # 底部一条柔和暖灰阴影
        pygame.draw.ellipse(
            big, (214, 223, 242, 150),
            (int(cx - 110 * k), int(cy + 6 * k),
             int(220 * k), int(30 * k)))
        # 暗部：整体向右下偏移的蓝灰色云底
        for dx, dy, r in _CLOUD_BLOBS:
            pygame.draw.circle(
                big, (203, 214, 240, 255),
                (int(cx + (dx + 5) * k), int(cy + (dy + 6) * k)),
                int(r * k))
        # 主体：偏冷的云白
        for dx, dy, r in _CLOUD_BLOBS:
            pygame.draw.circle(
                big, (247, 250, 255, 255),
                (int(cx + dx * k), int(cy + dy * k)),
                int(r * k))
        # 高光：向左上偏移的纯白小云团，形成受光面
        for dx, dy, r in _CLOUD_BLOBS:
            pygame.draw.circle(
                big, (255, 255, 255, 255),
                (int(cx + (dx - 4) * k), int(cy + (dy - 5) * k)),
                int(r * k * 0.82))
        return pygame.transform.smoothscale(big, (wpx, hpx))

    def _cloud_surface(self, sc, nkey):
        key = (int(round(sc / 0.04)), nkey)
        s = self._cloud_cache.get(key)
        if s is None:
            s = self._build_cloud(sc)
            if nkey:
                night = nkey / 10
                tint = _mix((255, 255, 255), (186, 196, 228), night)
                s = s.copy()
                s.fill((tint[0], tint[1], tint[2], 255),
                       special_flags=pygame.BLEND_RGBA_MULT)
            if len(self._cloud_cache) < 220:
                self._cloud_cache[key] = s
        return s

    def _draw_clouds(self, layer, t, night):
        nkey = int(night * 10)
        for fx, fy, sc, spd in self.clouds:
            s = self._cloud_surface(sc, nkey)
            x = (fx * self.w + spd * t) % (self.w + 320) - 160
            y = fy * self.h + math.sin(t * 0.5 + fx * 9) * 8 * self.u
            layer.blit(s, s.get_rect(center=(int(x), int(y))))

    # ---------------- 气球 ----------------
    def _draw_balloons(self, layer, t, night):
        knot = (self.w * 0.918, self.h * 0.685)
        rx, ry = int(29 * self.u), int(36 * self.u)
        for i, (fx, fy, color) in enumerate(_BALLOONS):
            phase = i * 1.7
            cx = fx * self.w + math.sin(t * 1.1 + phase) * 5 * self.u
            cy = fy * self.h + math.sin(t * 1.5 + phase) * 3 * self.u
            body_c = self._dim(color, night, 0.55)
            bottom = (cx, cy + ry - 2)
            # 细绳（带轻微弯曲）
            prev = bottom
            for k in range(1, 7):
                f = k / 6
                px = cx + (knot[0] - cx) * f + math.sin(
                    t + phase + f * 3) * 2 * self.u
                py = cy + (knot[1] - cy) * f
                pygame.draw.line(layer, (150, 150, 170, 200),
                                 (int(prev[0]), int(prev[1])),
                                 (int(px), int(py)), 1)
                prev = (px, py)
            # 气球本体：暗部椭圆垫底 + 主体左上偏移，形成球体明暗
            box = pygame.Rect(int(cx - rx), int(cy - ry), rx * 2, ry * 2)
            dark_c = self._dim(_mix(color, (80, 70, 130), 0.30), night, 0.55)
            pygame.draw.ellipse(layer, dark_c, box)
            mbox = pygame.Rect(int(cx - rx + 2 * self.u),
                               int(cy - ry - 2 * self.u),
                               rx * 2 - 4 * self.u, ry * 2 - 4 * self.u)
            pygame.draw.ellipse(layer, body_c, mbox)
            # 小三角结
            pygame.draw.polygon(layer, dark_c,
                                [(cx - 5, cy + ry - 3),
                                 (cx + 5, cy + ry - 3),
                                 (cx, cy + ry + 5)])
            # 高光：柔光大椭圆 + 一个镜面小亮点
            hl = pygame.Surface((rx, ry), pygame.SRCALPHA)
            pygame.draw.ellipse(hl, (255, 255, 255, 115),
                                (2, 3, int(rx * 0.7), int(ry * 0.8)))
            layer.blit(hl, (int(cx - rx * 0.55), int(cy - ry * 0.55)))
            pygame.draw.circle(layer, (255, 255, 255, 200),
                               (int(cx - rx * 0.34), int(cy - ry * 0.44)),
                               max(1, int(2.6 * self.u)))

    # ---------------- 草坡 ----------------
    def _build_meadow(self, key):
        """草地渐变 + 坡顶圆边（按夜色量化缓存，省去每帧逐行绘制）。"""
        night = key / 40
        top, mid, bot = (
            _mix(_GRASS_NIGHT[i], _GRASS_DAY[i], 1 - night * 0.72)
            for i in range(3))
        mh = self.h - self.meadow_y
        s = pygame.Surface((self.w, mh))
        for y in range(mh):
            f = y / max(1, mh - 1)
            if f < 0.5:
                color = _mix(top, mid, f * 2)
            else:
                color = _mix(mid, bot, (f - 0.5) * 2)
            pygame.draw.line(s, color, (0, y), (self.w, y))
        # 坡顶起伏的草丛圆边
        for x in range(-20, self.w + 30, int(26 * self.u)):
            yy = 2 + int(math.sin(x * 0.7) * 2)
            pygame.draw.circle(s, top, (x, yy), int(15 * self.u))
        if len(self._meadow_cache) > 66:
            self._meadow_cache.clear()
        self._meadow_cache[key] = s

    def _draw_meadow(self, layer, t, night):
        key = int(night * 40)
        s = self._meadow_cache.get(key)
        if s is None:
            self._build_meadow(key)
            s = self._meadow_cache[key]
        layer.blit(s, (0, self.meadow_y))
        # 草叶纹理
        for x, y, length, tilt, light in self.blades:
            c = (170, 228, 120) if light else (86, 165, 82)
            pygame.draw.line(layer, c, (int(x), int(y)),
                             (int(x + tilt * length),
                              int(y - length)),
                             max(1, int(2 * self.u)))
        self._draw_flowers(layer, t, night)

    def _draw_flowers(self, layer, t, night):
        for x, y, kind, sc, phase, head_h in self.flowers:
            sway = math.sin(t * 1.5 + phase)
            hx = x + sway * 4 * self.u * sc
            hy = y - head_h + math.sin(t * 2.2 + phase) * 1.5
            rot = sway * 0.16
            # 茎
            stem_c = self._dim((96, 180, 96), night, 0.5)
            pygame.draw.line(layer, stem_c, (int(x), int(y)),
                             (int(hx), int(hy + 3)),
                             max(1, int(2.6 * sc * self.u)))
            # 一片小叶
            leaf = self._petal_shape(7 * sc * self.u, 3.4 * sc * self.u,
                                     self._dim((130, 205, 120), night, 0.5),
                                     -0.6 + rot)
            layer.blit(leaf, leaf.get_rect(center=(
                int((x + hx) / 2 + 4), int((y + hy) / 2 + 4))))

            hx, hy = int(hx), int(hy)
            if kind == "tulip":
                r = int(7.5 * sc * self.u)
                bc = self._dim((255, 142, 182), night, 0.5)
                pygame.draw.circle(layer, bc, (hx, hy - r), r)
                pygame.draw.circle(layer, bc, (hx - int(r * 0.7), hy - int(r * 1.3)),
                                   int(r * 0.8))
                pygame.draw.circle(layer, bc, (hx + int(r * 0.7), hy - int(r * 1.3)),
                                   int(r * 0.8))
                pygame.draw.polygon(layer, bc, [
                    (hx - int(r * 0.55), hy - int(r * 1.7)),
                    (hx + int(r * 0.55), hy - int(r * 1.7)),
                    (hx, hy - int(r * 2.3))])
                pygame.draw.circle(layer, (255, 220, 232, 160),
                                   (hx - int(r * 0.3), hy - int(r * 1.2)),
                                   max(1, int(r * 0.3)))
                continue

            if kind == "daisy":
                unit, n, petal_c, center = (
                    11 * sc * self.u, 9,
                    self._dim((255, 255, 255), night, 0.35),
                    self._dim((255, 196, 64), night, 0.45))
                pw, pl, dist = 4.2 * sc * self.u, 7.5 * sc * self.u, unit * 0.62
            elif kind == "cosmos":
                unit, n, petal_c, center = (
                    9 * sc * self.u, 5,
                    self._dim((255, 150, 190), night, 0.5),
                    self._dim((255, 222, 110), night, 0.45))
                pw, pl, dist = 6.2 * sc * self.u, 6.6 * sc * self.u, unit * 0.55
            else:
                unit, n, petal_c, center = (
                    8.5 * sc * self.u, 6,
                    self._dim((255, 212, 78), night, 0.5),
                    self._dim((240, 158, 60), night, 0.45))
                pw, pl, dist = 5.6 * sc * self.u, 6.2 * sc * self.u, unit * 0.55
            for i in range(n):
                ang = -math.pi / 2 + i * 2 * math.pi / n + rot
                pcx = hx + math.cos(ang) * dist
                pcy = hy + math.sin(ang) * dist
                ps = self._petal_shape(pl, pw, petal_c, ang)
                layer.blit(ps, ps.get_rect(center=(int(pcx), int(pcy))))
            pygame.draw.circle(layer, center, (hx, hy),
                               max(1, int(unit * 0.38)))

    # ---------------- 童趣小蝴蝶 ----------------
    def _draw_butterflies(self, layer, t, night):
        for x0, y0, phase, color in self.butterflies:
            x = x0 + math.sin(t * 0.33 + phase) * 80 * self.u
            y = y0 + math.sin(t * 0.85 + phase * 2.1) * 40 * self.u
            flap = abs(math.sin(t * 9 + phase))
            c = self._dim(color, night, 0.5)
            wx = 9 * self.u * (0.35 + 0.65 * flap)
            wy = 8 * self.u
            for s in (-1, 1):
                box = pygame.Rect(0, 0, max(2, int(wx)), max(2, int(wy)))
                box.center = (int(x + s * wx * 0.55), int(y))
                pygame.draw.ellipse(layer, (*c, 235), box)
            pygame.draw.line(layer, (90, 70, 110, 235),
                             (int(x), int(y - 5 * self.u)),
                             (int(x), int(y + 4 * self.u)),
                             max(1, int(2 * self.u)))

    # ---------------- 扇贝花边 ----------------
    def _draw_scallops(self, layer, t, night):
        r = self.scallop_r
        c = self._dim((66, 172, 92), night, 0.5)
        pygame.draw.rect(layer, c, (0, self.scallop_y, self.w,
                                    self.h - self.scallop_y))
        for x in range(-r, self.w + r * 2, self.scallop_step):
            pygame.draw.circle(layer, c, (x, self.scallop_y), r)
        # 花边上的小花（黄 / 粉 / 白交替）
        mini_colors = (
            self._dim((255, 214, 90), night, 0.5),
            self._dim((255, 130, 175), night, 0.5),
            self._dim((255, 255, 255), night, 0.35))
        i = 0
        for x in range(self.scallop_step // 2, self.w,
                       self.scallop_step):
            yy = self.scallop_y - int(7 * self.u) + int(
                math.sin(t * 1.8 + x) * 1.5)
            col = mini_colors[i % 3]
            i += 1
            for k in range(5):
                ang = -math.pi / 2 + k * 2 * math.pi / 5
                pygame.draw.circle(layer, col, (int(x + math.cos(ang) * 6),
                                                int(yy + math.sin(ang) * 6)),
                                   max(1, int(3.4 * self.u)))
            pygame.draw.circle(layer,
                               self._dim((255, 230, 120), night, 0.45),
                               (x, yy), max(1, int(3 * self.u)))

    # ---------------- 泡泡 ----------------
    def _bubble_sprite(self, r):
        """泡泡精灵（半透明必须用 blit 合成，draw 会直接替换图层像素）。"""
        key = max(3, int(round(r)))
        s = self._bubble_cache.get(key)
        if s is None:
            size = key * 2 + 4
            s = pygame.Surface((size, size), pygame.SRCALPHA)
            c = size // 2
            rad = math.radians
            # 内部柔光填充
            pygame.draw.circle(s, (208, 234, 255, 26), (c, c), key - 1)
            pygame.draw.circle(s, (255, 255, 255, 95), (c, c), key, 2)
            box = pygame.Rect(2, 2, key * 2, key * 2)
            pygame.draw.arc(s, (255, 170, 210, 160), box,
                            rad(200), rad(255), 2)
            pygame.draw.arc(s, (150, 220, 255, 160), box,
                            rad(25), rad(78), 2)
            pygame.draw.arc(s, (140, 185, 255, 100), box,
                            rad(115), rad(175), 2)
            pygame.draw.circle(s, (255, 255, 255, 185),
                               (int(c - key * 0.36), int(c - key * 0.4)),
                               max(1, int(key * 0.18)))
            pygame.draw.circle(s, (255, 255, 255, 120),
                               (int(c + key * 0.32), int(c + key * 0.28)),
                               max(1, int(key * 0.08)))
            self._bubble_cache[key] = s
        return s

    def _draw_bubbles(self, layer, t):
        for bx, by0, r, spd in self.bubbles:
            y = (by0 - spd * t) % (self.h + 100) - 50
            x = bx + math.sin(t * 1.1 + by0) * 18 * self.u
            s = self._bubble_sprite(r)
            layer.blit(s, s.get_rect(center=(int(x), int(y))))

    # ---------------- 飘落花瓣 ----------------
    def _falling_petal_surface(self, size, kind):
        key = (int(size), kind)
        s = self._petal_cache.get(("fall",) + key)
        if s is not None:
            return s
        base = pygame.Surface((int(size * 2 + 4), int(size * 1.6 + 4)),
                              pygame.SRCALPHA)
        if kind == "leaf":
            color = (154, 208, 116)
        elif kind == "yellow":
            color = (255, 220, 110)
        else:
            color = (255, 158, 192)
        pygame.draw.ellipse(base, color, (2, 2, int(size * 2),
                                          int(size * 1.4)))
        pygame.draw.line(base, _mix(color, (60, 100, 60), 0.35),
                         (3, int(size * 0.8)), (int(size * 2 + 1),
                                                int(size * 0.8)), 1)
        if len(self._petal_cache) < 1400:
            self._petal_cache[("fall",) + key] = base
        return base

    def _draw_petals(self, layer, t, night):
        for (x0, y0, size, fall, phase, sway_spd, drift, rot_spd,
             kind) in self.petals:
            y = (y0 + fall * t) % (self.h + 80) - 40
            x = (x0 + drift * t
                 + math.sin(t * sway_spd + phase) * 26 * self.u)
            x %= (self.w + 60)
            x -= 30
            s = self._falling_petal_surface(size, kind)
            s = pygame.transform.rotate(s, math.degrees(rot_spd * t + phase))
            if night > 0:
                s = s.copy()
                s.fill((30, 36, 70, int(120 * night)),
                       special_flags=pygame.BLEND_RGBA_MULT)
            layer.blit(s, s.get_rect(center=(int(x), int(y))))

    # ---------------- 星光闪烁 ----------------
    def _spark_sprite(self, r):
        """四角星光精灵（blit 合成，避免打穿云层）。"""
        key = max(2, int(round(r * 2)))
        s = self._spark_cache.get(key)
        if s is None:
            size = key * 2 + 4
            s = pygame.Surface((size, size), pygame.SRCALPHA)
            c = size / 2
            pts = []
            for i in range(8):
                ang = -math.pi / 2 + i * math.pi / 4
                rad = key / 2 if i % 2 == 0 else key * 0.11
                pts.append((c + rad * math.cos(ang), c + rad * math.sin(ang)))
            pygame.draw.polygon(s, (255, 255, 255, 220), pts)
            self._spark_cache[key] = s
        return s

    def _draw_sparks(self, layer, t, sparks):
        for x, y, r, phase in sparks:
            tw = 0.3 + 0.7 * abs(math.sin(t * 2.8 + phase))
            s = self._spark_sprite(r * 1.7 * tw)
            layer.blit(s, s.get_rect(center=(int(x), int(y))))

    # ---------------- 对外入口 ----------------
    def draw(self, surf, t, day_p):
        step = int(_clamp(day_p, 0, 1) * self.SKY_STEPS)
        if step not in self._sky_cache:
            self._build_sky(step)
        surf.blit(self._sky_cache[step], (0, 0))

        layer = self.layer
        layer.fill((0, 0, 0, 0))
        p = _clamp(day_p, 0, 1)
        night = self._night_weight(p)
        sun, moon = self._celestial(p)

        self._draw_stars(layer, t, night)
        self._draw_sun(layer, sun[0], sun[1], sun[2], t)
        self._draw_moon(layer, moon[0], moon[1], moon[2], t)
        self._draw_rainbow(layer, night)
        self._draw_clouds(layer, t, night)
        self._draw_sparks(layer, t, self.sky_sparks)
        self._draw_meadow(layer, t, night)
        self._draw_sparks(layer, t, self.grass_sparks)
        self._draw_butterflies(layer, t, night)
        self._draw_balloons(layer, t, night)
        self._draw_petals(layer, t, night)
        self._draw_bubbles(layer, t)
        self._draw_scallops(layer, t, night)

        surf.blit(layer, (0, 0))
        if night > 0:
            veil = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            veil.fill((28, 24, 84, int(66 * night)))
            surf.blit(veil, (0, 0))
