# -*- coding: utf-8 -*-
"""
程序合成音效（无任何外部音频素材）。
用 numpy 生成波形，再交给 pygame.mixer 播放；音频初始化失败时自动静音，不影响游戏。
"""
from __future__ import annotations

import math

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

import pygame

SAMPLE_RATE = 44100


def _stereo(left, right=None):
    if right is None:
        right = left
    arr = np.empty((len(left), 2), dtype=np.int16)
    arr[:, 0] = np.clip(left, -1, 1) * 32767
    arr[:, 1] = np.clip(right, -1, 1) * 32767
    return arr


def _env(n, attack=0.005, release=0.08):
    """简单的起音/释音包络。"""
    a = max(1, int(attack * SAMPLE_RATE))
    r = max(1, int(release * SAMPLE_RATE))
    env = np.ones(n)
    env[:a] = np.linspace(0, 1, a)
    env[-r:] = np.minimum(env[-r:], np.linspace(1, 0, r))
    return env


def _tone(freq, dur, kind="sine", volume=0.4, sweep_to=None):
    n = int(dur * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    if sweep_to is not None:
        phase = 2 * math.pi * (freq * t + 0.5 * (sweep_to - freq) * t * t / dur)
    else:
        phase = 2 * math.pi * freq * t
    if kind == "sine":
        wave = np.sin(phase)
    elif kind == "triangle":
        wave = 2 / math.pi * np.arcsin(np.sin(phase))
    elif kind == "square":
        wave = np.sign(np.sin(phase)) * 0.6
    else:
        wave = np.sin(phase)
    return wave * volume * _env(n, release=dur * 0.5)


def _noise(dur, volume=0.3, lp=0.6):
    n = int(dur * SAMPLE_RATE)
    white = np.random.default_rng(0).uniform(-1, 1, n)
    # 一阶低通，让噪声柔和一点
    out = np.zeros(n)
    last = 0.0
    for i in range(n):  # 数据量小，直接循环
        last = last * lp + white[i] * (1 - lp)
        out[i] = last
    return out * volume * np.geomspace(1, 0.05, n)


def _mix(*tracks):
    n = max(len(t) for t in tracks)
    out = np.zeros(n)
    for t in tracks:
        out[: len(t)] += t
    return out / max(1, np.abs(out).max()) * 0.9


class SoundManager:
    def __init__(self):
        self.enabled = False
        self.muted = False
        self.master = 1.0  # 主音量 0~1，由设置页滑动条控制
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.bgm: pygame.mixer.Sound | None = None
        self._bgm_channel = None
        if np is None:
            return
        try:
            pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, 512)
            pygame.mixer.init()
            self.enabled = True
            self._build_sfx()
            self._build_bgm()
        except pygame.error:
            self.enabled = False

    # ---------- 音效合成 ----------
    def _make(self, name, wave):
        self.sounds[name] = pygame.sndarray.make_sound(_stereo(wave))

    def _build_sfx(self):
        # 点击按钮：清脆"哒"声（高频短促 + 上扬瞬态 + 高八度亮点）
        self._make("click", _mix(_tone(1568, 0.045, "sine", 0.45, sweep_to=2349),
                                 _tone(3136, 0.03, "triangle", 0.14)))
        # 飞出：上扬滑音 + 柔和风声
        fly = _mix(_tone(300, 0.28, "sine", 0.35, sweep_to=920),
                   _noise(0.28, 0.18))
        self._make("fly", fly)
        # 碰撞：低沉闷响 + 噪声
        hit = _mix(_tone(190, 0.32, "sine", 0.55, sweep_to=55),
                   _noise(0.18, 0.4, lp=0.3))
        self._make("collide", hit)
        # 通关：欢快上行琶音 C-E-G-C
        notes = [(523, 0.0), (659, 0.10), (784, 0.20), (1047, 0.30)]
        track = np.zeros(int(0.9 * SAMPLE_RATE))
        for f, start in notes:
            w = _tone(f, 0.45, "triangle", 0.4)
            i = int(start * SAMPLE_RATE)
            track[i:i + len(w)] += w
        self._make("win", track)
        # 失败：下行温柔音阶
        notes = [(523, 0.0), (440, 0.16), (349, 0.32), (262, 0.48)]
        track = np.zeros(int(1.1 * SAMPLE_RATE))
        for f, start in notes:
            w = _tone(f, 0.4, "sine", 0.35)
            i = int(start * SAMPLE_RATE)
            track[i:i + len(w)] += w
        self._make("lose", track)
        # 星星弹出
        self._make("star", _mix(_tone(1175, 0.10, "sine", 0.35),
                                _tone(1568, 0.16, "sine", 0.25)))
        # 提示铃铛
        self._make("hint", _mix(_tone(880, 0.12, "triangle", 0.35),
                                _tone(1320, 0.20, "sine", 0.22)))
        # 倒计时滴答
        self._make("tick", _tone(1250, 0.035, "square", 0.18))
        # 撤销
        self._make("undo", _tone(520, 0.09, "sine", 0.3, sweep_to=760))

    # ---------- 背景音乐 ----------
    def _build_bgm(self):
        """欢快活泼的纯音乐小曲：跳音旋律 + 弹跳低音 + 轻打击乐。"""
        bpm = 138
        beat = 60 / bpm
        e8 = beat / 2
        total = 16 * beat + e8
        n = int(total * SAMPLE_RATE)
        track = np.zeros(n)

        def put(wave, start):
            i = int(start * SAMPLE_RATE)
            j = min(n, i + len(wave))
            if i < n:
                track[i:j] += wave[: j - i]

        # 旋律：C 大调断奏钩子（C-G-Am-F 和声），八分音符跳跃 + 长音收尾
        C5, D5, E5, F5, G5, A5, B5 = 523.25, 587.33, 659.26, 698.46, 783.99, 880.0, 987.77
        C6 = 1046.5
        mel = [
            (C5, 0.0), (E5, 0.5), (G5, 1.0), (E5, 1.5),
            (A5, 2.0, 1.0), (G5, 3.0), (E5, 3.5),
            (B5, 4.0), (G5, 4.5), (D5, 5.0), (G5, 5.5),
            (B5, 6.0, 1.5),
            (A5, 8.0), (C6, 8.5), (E5, 9.0), (A5, 9.5),
            (C6, 10.0, 1.5),
            (F5, 12.0), (A5, 12.5), (F5, 13.0), (D5, 13.5),
            (E5, 14.0), (G5, 14.5), (C6, 15.0, 1.0),
        ]
        for item in mel:
            f, st = item[0], item[1]
            dur = item[2] if len(item) > 2 else 0.5
            put(_tone(f, dur * beat * 0.82, "triangle", 0.17), st * beat)

        # 低音：C-G-Am-F 根音-五音交替弹跳（八分音符）
        roots = [262.0, 196.0, 220.0, 174.6]
        for bi, root in enumerate(roots):
            fifth = root * 1.5
            for k in range(8):
                f = root if k in (0, 3, 4, 7) else fifth
                put(_tone(f, e8 * 0.8, "sine", 0.14), (bi * 4 + k * 0.5) * beat)

        # 轻打击乐：偶数拍小底鼓 + 反拍沙锤，增加活泼律动
        for b in range(0, 16, 2):
            put(_tone(90, 0.10, "sine", 0.22, sweep_to=45), b * beat)
        for b in range(16):
            put(_noise(0.03, 0.06, lp=0.85), b * beat + e8)

        track = track / max(1, np.abs(track).max()) * 0.5
        self.bgm = pygame.sndarray.make_sound(_stereo(track))

    def set_master(self, v):
        """设置主音量（0~1），即时作用于 BGM 与后续音效。"""
        self.master = max(0.0, min(1.0, float(v)))
        if self.bgm is not None:
            self.bgm.set_volume(0.35 * self.master)

    def play_bgm(self):
        if self.enabled and not self.muted and self.bgm is not None:
            if self._bgm_channel is None:
                self._bgm_channel = self.bgm.play(loops=-1)
                self.bgm.set_volume(0.35 * self.master)

    def stop_bgm(self):
        if self._bgm_channel is not None:
            self._bgm_channel.stop()
            self._bgm_channel = None

    def play(self, name):
        if self.enabled and not self.muted and name in self.sounds:
            snd = self.sounds[name]
            snd.set_volume(self.master)
            snd.play()

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            pygame.mixer.pause()
            self.stop_bgm()
        else:
            pygame.mixer.unpause()
            self.play_bgm()
        return self.muted
