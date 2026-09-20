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
        # 点击按钮：清脆短音
        self._make("click", _mix(_tone(660, 0.05, "triangle", 0.35),
                                 _tone(990, 0.06, "sine", 0.20)))
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
        bpm = 116
        beat = 60 / bpm
        # 欢快的 C 大调小曲（旋律, 频率/拍数）
        melody = [
            (523, 0.5), (659, 0.5), (784, 0.5), (659, 0.5),
            (587, 0.5), (698, 0.5), (880, 1.0),
            (784, 0.5), (659, 0.5), (587, 0.5), (523, 0.5),
            (587, 0.5), (659, 0.5), (523, 1.0),
        ]
        bass = [262, 196, 220, 196]
        total = sum(d for _, d in melody) * beat + 1.0
        n = int(total * SAMPLE_RATE)
        track = np.zeros(n)
        t_cur = 0.0
        for f, beats_n in melody:
            w = _tone(f, beats_n * beat * 1.1, "triangle", 0.16)
            i = int(t_cur * SAMPLE_RATE)
            track[i:i + len(w)] += w[: max(0, n - i)]
            t_cur += beats_n * beat
        # 低音伴奏，每拍一个
        steps = int(total / beat)
        for i in range(steps):
            f = bass[(i // 2) % len(bass)]
            w = _tone(f, beat * 0.9, "sine", 0.12)
            start = int(i * beat * SAMPLE_RATE)
            track[start:start + len(w)] += w[: max(0, n - start)]
        track = track / max(1, np.abs(track).max()) * 0.5
        self.bgm = pygame.sndarray.make_sound(_stereo(track))

    def play_bgm(self):
        if self.enabled and not self.muted and self.bgm is not None:
            if self._bgm_channel is None:
                self._bgm_channel = self.bgm.play(loops=-1)
                self.bgm.set_volume(0.35)

    def stop_bgm(self):
        if self._bgm_channel is not None:
            self._bgm_channel.stop()
            self._bgm_channel = None

    def play(self, name):
        if self.enabled and not self.muted and name in self.sounds:
            self.sounds[name].play()

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            pygame.mixer.pause()
            self.stop_bgm()
        else:
            pygame.mixer.unpause()
            self.play_bgm()
        return self.muted
