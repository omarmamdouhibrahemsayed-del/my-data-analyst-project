#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=====================================================================
  KNOCKOUT LEGENDS  -  لعبة ملاكمة / مصارعة بمنظور خلفي (Pygame)
=====================================================================
تشغيل:   pip install pygame-ce      (أو pygame)
         python knockout_legends.py

الملف الواحد لا يحتاج أي صور أو أصوات خارجية:
  * كل الرسومات تُرسم برمجياً (أشكال هندسية).
  * كل الأصوات تُولَّد برمجياً عبر pygame.mixer.

التحكم أثناء القتال:
  A / D  أو  السهمين يمين/يسار  : التحرك جانبياً (للمراوغة والمحاذاة)
  J  أو  Z  أو  كليك يسار       : لكمة سريعة (Jab)
  K  أو  X  أو  كليك يمين       : لكمة قوية (Hook)
  S  أو  السهم السفلي أو Space  : الدفاع (Block)
  عجلة الماوس / Q , E / - , +   : تقريب وإبعاد الكاميرا (Zoom)
  ESC                            : إيقاف مؤقت

هيكل الملف:
  1) الثوابت والأدوات المساعدة
  2) توليد الأصوات
  3) الشخصيات (Roster) + المتجر
  4) الخلفيات الـ 21 + الحلبة + الجمهور
  5) نظام الكاميرا (Camera)  - منظور + Zoom + اهتزاز
  6) رسم المقاتلين (من الخلف / من الأمام)
  7) المقاتل (Fighter) + الذكاء الاصطناعي
  8) القتال (Fight) - الجيم بلاي + المؤثرات + الواجهة HUD
  9) اللعبة (Game) - القوائم، المتجر، المستويات، النتائج
=====================================================================
"""
import sys
import math
import random
import array

import pygame

# ---------------------------------------------------------------------
# 1) الثوابت والأدوات المساعدة
# ---------------------------------------------------------------------
W, H, FPS = 1280, 720, 60
NUM_LEVELS = 21          # عدد المراحل / الخلفيات
WIN_REWARD = 1000        # مكافأة الفوز (جنيه)
ROUND_TIME = 90          # مدة الجولة بالثواني
HORIZON = 430            # خط الأفق في الخلفية
PIVOT = (W / 2, 470)     # مركز التقريب (Zoom)
CURRENCY = "EGP"

GOLD = (255, 205, 60)
WHITE = (245, 245, 245)


def clamp(v, a, b):
    return max(a, min(b, v))


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def shade(c, f):
    return tuple(clamp(int(v * f), 0, 255) for v in c)


_font_cache = {}


def get_font(size, bold=True):
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = pygame.font.SysFont("arial,dejavusans,helvetica", size, bold=bold)
    return _font_cache[key]


def text(surf, s, size, color, pos, anchor="center", shadow=True, bold=True):
    """رسم نص مع ظل. anchor مثل: center, midleft, topleft, topright, midtop ..."""
    f = get_font(size, bold)
    img = f.render(str(s), True, color)
    r = img.get_rect(**{anchor: pos})
    if shadow:
        sh = f.render(str(s), True, (0, 0, 0))
        surf.blit(sh, r.move(2, 2))
    surf.blit(img, r)
    return r


def money_str(v):
    return f"{v:,} {CURRENCY}"


def draw_star(surf, cx, cy, r, col, pts=8):
    poly = []
    for i in range(pts * 2):
        a = math.pi * i / pts
        rr = r if i % 2 == 0 else r * 0.45
        poly.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    pygame.draw.polygon(surf, col, poly)


# ---------------------------------------------------------------------
# 2) توليد الأصوات برمجياً (بدون ملفات)
# ---------------------------------------------------------------------
SR = 22050


class NullSound:
    def play(self, *a, **k):
        pass

    def set_volume(self, v):
        pass


class SoundBank(dict):
    def __missing__(self, key):
        return NullSound()


def synth(dur, fn, vol=0.8):
    """يحوّل دالة موجة fn(t) إلى كائن Sound (ستيريو 16-bit)."""
    n = int(SR * dur)
    buf = array.array("h")
    for i in range(n):
        v = int(clamp(fn(i / SR), -1, 1) * 32767 * vol)
        buf.append(v)
        buf.append(v)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def build_sounds():
    bank = SoundBank()
    try:
        # pygame.init() يفتح المكسر بإعدادات افتراضية؛ نعيد فتحه بإعداداتنا (22050Hz ستيريو)
        pygame.mixer.quit()
        try:
            pygame.mixer.init(SR, -16, 2, 512, allowedchanges=0)
        except TypeError:
            pygame.mixer.init(SR, -16, 2, 512)
        if not pygame.mixer.get_init():
            return bank
        rnd = random.Random(1)
        tp = 2 * math.pi

        def noise():
            return rnd.uniform(-1, 1)

        # لكمة خفيفة / قوية (ضربة + ضجيج قصير)
        bank["hit_light"] = synth(0.18, lambda t: math.sin(tp * (170 - 250 * t) * t) * math.exp(-t * 28) * 0.9
                                  + noise() * math.exp(-t * 70) * 0.6)
        bank["hit_heavy"] = synth(0.32, lambda t: math.sin(tp * (110 - 150 * t) * t) * math.exp(-t * 13)
                                  + noise() * math.exp(-t * 45) * 0.8)
        # صوت الدفاع
        bank["block"] = synth(0.12, lambda t: math.sin(tp * 420 * t) * math.exp(-t * 40) * 0.7
                              + noise() * math.exp(-t * 90) * 0.5)
        # صوت هواء اللكمة (Whoosh)
        lp = [0.0]

        def whoosh(t):
            lp[0] += 0.25 * (noise() - lp[0])
            return lp[0] * (math.sin(math.pi * t / 0.15) ** 2) * 1.2
        bank["whoosh"] = synth(0.15, whoosh, 0.5)
        # جرس الحلبة
        bank["bell"] = synth(1.4, lambda t: (math.sin(tp * 880 * t) + 0.6 * math.sin(tp * 1760.5 * t)
                                             + 0.3 * math.sin(tp * 2640 * t)) * math.exp(-t * 2.6) * 0.5)
        # سقوط الخصم
        bank["ko"] = synth(0.9, lambda t: math.sin(tp * (70 - 30 * t) * t) * math.exp(-t * 4)
                           + noise() * math.exp(-t * 10) * 0.4)

        # فوز / خسارة / نقرة واجهة / تصفيق الجمهور
        def arp(freqs, step):
            def f(t):
                i = min(int(t / step), len(freqs) - 1)
                loc = t - i * step
                return math.sin(tp * freqs[i] * t) * math.exp(-loc * 6) * 0.6
            return f
        bank["win"] = synth(0.9, arp([523, 659, 784, 1047], 0.2))
        bank["lose"] = synth(1.0, arp([392, 330, 262, 196], 0.25))
        bank["click"] = synth(0.05, lambda t: math.sin(tp * 900 * t) * math.exp(-t * 80))
        lp2 = [0.0]

        def cheer(t):
            lp2[0] += 0.35 * (noise() - lp2[0])
            return lp2[0] * math.sin(math.pi * t / 1.2) * 1.4
        bank["cheer"] = synth(1.2, cheer, 0.5)
    except Exception as exc:  # لا يوجد جهاز صوت
        print("Audio disabled:", exc)
        return SoundBank()
    return bank


SOUNDS = SoundBank()

# ---------------------------------------------------------------------
# 3) الشخصيات (المتجر) - كل القيم من 1 إلى 10
# ---------------------------------------------------------------------
ROSTER = [
    dict(name="Muhammad Ali", tag="The Greatest", price=0, power=7, speed=10, health=7,
         skin=(120, 78, 52), hair=(25, 20, 20), trunks=(245, 245, 245), trim=(212, 175, 55), gloves=(200, 30, 30)),
    dict(name="Mike Tyson", tag="Iron Mike", price=2500, power=10, speed=8, health=6,
         skin=(92, 58, 40), hair=(70, 44, 30), trunks=(20, 20, 24), trim=(230, 230, 230), gloves=(40, 40, 48)),
    dict(name="Iron Titan", tag="The Wall", price=1500, power=8, speed=5, health=9,
         skin=(200, 150, 120), hair=(60, 40, 20), trunks=(30, 60, 160), trim=(255, 255, 255), gloves=(30, 90, 200)),
    dict(name="Viking Bjorn", tag="Berserker", price=2000, power=9, speed=4, health=10,
         skin=(235, 190, 160), hair=(200, 140, 40), trunks=(90, 50, 20), trim=(200, 200, 200), gloves=(120, 75, 30)),
    dict(name="Samurai Kane", tag="Silent Blade", price=2200, power=6, speed=10, health=6,
         skin=(225, 180, 140), hair=(15, 15, 15), trunks=(150, 20, 40), trim=(255, 215, 0), gloves=(150, 20, 40)),
    dict(name="El Toro", tag="The Bull", price=3000, power=9, speed=7, health=8,
         skin=(170, 115, 80), hair=(30, 20, 15), trunks=(20, 120, 60), trim=(255, 255, 255), gloves=(20, 140, 70)),
    dict(name="Pharaoh Ramy", tag="Nile King", price=3500, power=8, speed=8, health=8,
         skin=(150, 100, 65), hair=(10, 10, 10), trunks=(230, 190, 40), trim=(30, 90, 200), gloves=(230, 190, 40)),
    dict(name="Cyber Max", tag="Machine", price=5000, power=10, speed=9, health=10,
         skin=(150, 170, 190), hair=(0, 220, 255), trunks=(40, 40, 60), trim=(0, 255, 200), gloves=(110, 0, 200)),
]

# ---------------------------------------------------------------------
# 4) الخلفيات الـ 21: (الاسم، النمط، سماء-أعلى، سماء-أسفل، أرضية، حبال، لون مميز)
# ---------------------------------------------------------------------
BACKGROUNDS = [
    ("Local Gym",         "arena",  (30, 30, 45),   (80, 70, 90),   (70, 50, 40),   (220, 40, 40),  (255, 220, 120)),
    ("Downtown Club",     "city",   (20, 25, 60),   (120, 90, 140), (50, 45, 60),   (60, 140, 255), (255, 180, 80)),
    ("Desert Pyramids",   "desert", (90, 150, 230), (250, 220, 160), (190, 150, 90), (230, 170, 40), (255, 240, 150)),
    ("Snow Peak",         "snow",   (110, 150, 210), (220, 235, 250), (150, 170, 190), (60, 110, 220), (255, 255, 255)),
    ("Sunny Beach",       "beach",  (60, 160, 240), (250, 230, 190), (210, 180, 120), (240, 90, 60),  (255, 240, 120)),
    ("Neon Night",        "neon",   (15, 0, 40),    (110, 20, 120), (40, 15, 70),   (255, 60, 200),  (0, 240, 255)),
    ("Deep Space",        "space",  (3, 3, 20),     (30, 10, 70),   (25, 25, 50),   (120, 200, 255), (255, 140, 60)),
    ("Jungle Temple",     "jungle", (60, 120, 70),  (170, 210, 120), (70, 90, 50),  (150, 100, 40),  (240, 220, 90)),
    ("Golden Stadium",    "arena",  (40, 30, 10),   (140, 110, 40), (100, 80, 40),  (230, 190, 40),  (255, 230, 140)),
    ("Skyscraper Roof",   "city",   (30, 60, 120),  (200, 160, 150), (60, 60, 75),  (250, 250, 250), (255, 200, 100)),
    ("Sahara Sunset",     "desert", (120, 40, 70),  (255, 160, 70), (170, 110, 70), (255, 120, 40),  (255, 200, 80)),
    ("Frozen Arena",      "snow",   (40, 70, 130),  (160, 200, 235), (120, 150, 185), (130, 220, 255), (220, 245, 255)),
    ("Tropical Island",   "beach",  (30, 130, 200), (255, 200, 150), (180, 150, 100), (30, 180, 120), (255, 210, 90)),
    ("Cyber Grid",        "neon",   (0, 10, 40),    (0, 70, 120),   (10, 25, 55),   (0, 255, 160),   (255, 0, 140)),
    ("Mars Colony",       "space",  (40, 10, 10),   (130, 40, 20),  (90, 40, 30),   (255, 120, 60),  (230, 90, 50)),
    ("Ancient Ruins",     "jungle", (40, 80, 60),   (150, 180, 110), (80, 80, 60),  (200, 200, 120), (180, 240, 120)),
    ("Royal Arena",       "arena",  (30, 10, 50),   (100, 40, 110), (80, 30, 70),   (240, 200, 60),  (255, 130, 230)),
    ("Midnight City",     "city",   (5, 5, 25),     (40, 30, 80),   (30, 30, 45),   (255, 60, 120),  (120, 220, 255)),
    ("Blood Moon Desert", "desert", (30, 0, 20),    (130, 30, 40),  (110, 60, 50),  (220, 40, 40),   (255, 90, 70)),
    ("Aurora Arctic",     "snow",   (5, 20, 50),    (40, 110, 120), (80, 110, 140), (80, 255, 190),  (120, 255, 200)),
    ("Final Championship", "arena", (10, 10, 20),   (90, 60, 20),   (60, 45, 25),   (255, 215, 0),   (255, 245, 180)),
]
assert len(BACKGROUNDS) == NUM_LEVELS

_bg_cache = {}
_crowd_cache = {}


def build_background(i):
    """بناء الطبقة الثابتة للخلفية مرة واحدة (سماء + ديكور)."""
    name, style, top, bot, floor, rope, acc = BACKGROUNDS[i]
    s = pygame.Surface((W, H))
    rnd = random.Random(i * 131 + 7)
    for y in range(HORIZON):
        pygame.draw.line(s, mix(top, bot, y / HORIZON), (0, y), (W, y))
    for y in range(HORIZON, H):
        pygame.draw.line(s, mix(floor, shade(floor, 0.4), (y - HORIZON) / (H - HORIZON)), (0, y), (W, y))
    ov = pygame.Surface((W, H), pygame.SRCALPHA)

    if style == "city":
        x = 0
        while x < W:
            bw, bh = rnd.randint(50, 110), rnd.randint(90, 300)
            pygame.draw.rect(s, shade(mix(top, bot, 0.5), rnd.uniform(0.35, 0.6)), (x, HORIZON - bh, bw, bh))
            for wy in range(HORIZON - bh + 10, HORIZON - 60, 22):
                for wx in range(x + 8, x + bw - 10, 18):
                    if rnd.random() < 0.45:
                        pygame.draw.rect(s, mix((255, 220, 120), acc, 0.3), (wx, wy, 8, 11))
            x += bw + rnd.randint(0, 8)
    elif style == "desert":
        pygame.draw.circle(s, acc, (rnd.randint(200, 1000), 140), 70)
        for _ in range(3):
            bx, w = rnd.randint(100, W - 100), rnd.randint(90, 170)
            by = HORIZON - 40
            col = mix(floor, bot, 0.3)
            pygame.draw.polygon(s, col, [(bx - w, by), (bx, by - w * 0.9), (bx + w, by)])
            pygame.draw.polygon(s, shade(col, 0.7), [(bx, by - w * 0.9), (bx + w, by), (bx, by)])
        for _ in range(7):
            pygame.draw.ellipse(s, shade(floor, 1.15), (rnd.randint(-100, W), HORIZON - 70, rnd.randint(300, 600), 120))
    elif style == "snow":
        for _ in range(8):
            bx, w = rnd.randint(0, W), rnd.randint(140, 260)
            hgt = rnd.randint(140, 280)
            pygame.draw.polygon(s, mix(top, (90, 110, 150), 0.5), [(bx - w, HORIZON - 30), (bx, HORIZON - 30 - hgt), (bx + w, HORIZON - 30)])
            pygame.draw.polygon(s, (240, 248, 255), [(bx - w * 0.28, HORIZON - 30 - hgt * 0.72), (bx, HORIZON - 30 - hgt),
                                                      (bx + w * 0.28, HORIZON - 30 - hgt * 0.72)])
        for _ in range(50):
            pygame.draw.circle(s, (255, 255, 255), (rnd.randint(0, W), rnd.randint(0, HORIZON - 80)), rnd.randint(1, 3))
    elif style == "beach":
        pygame.draw.circle(s, acc, (rnd.randint(250, 1000), 160), 65)
        for y in range(HORIZON - 100, HORIZON):
            pygame.draw.line(s, mix((30, 140, 210), (10, 70, 140), (y - HORIZON + 100) / 100), (0, y), (W, y))
        for _ in range(40):
            wx, wy = rnd.randint(0, W), rnd.randint(HORIZON - 95, HORIZON - 10)
            pygame.draw.line(s, (220, 240, 255), (wx, wy), (wx + rnd.randint(20, 50), wy), 2)
    elif style == "neon":
        pygame.draw.circle(s, acc, (W // 2, HORIZON - 40), 130)
        for k in range(7):
            pygame.draw.rect(s, mix(top, bot, 0.8), (W // 2 - 140, HORIZON - 120 + k * 19, 280, 3 + k * 2))
        for k in range(-14, 15):
            pygame.draw.line(s, shade(acc, 0.5), (W // 2 + k * 40, HORIZON), (W // 2 + k * 220, H), 1)
        for k in range(1, 9):
            yy = HORIZON + (k / 8) ** 2 * (H - HORIZON)
            pygame.draw.line(s, shade(acc, 0.5), (0, int(yy)), (W, int(yy)), 1)
    elif style == "space":
        for _ in range(220):
            c = rnd.randint(120, 255)
            pygame.draw.circle(s, (c, c, c), (rnd.randint(0, W), rnd.randint(0, HORIZON)), rnd.choice((1, 1, 2)))
        for _ in range(5):
            pygame.draw.circle(ov, (*acc, 22), (rnd.randint(0, W), rnd.randint(40, 300)), rnd.randint(80, 200))
        px, py = rnd.randint(150, 1100), rnd.randint(90, 200)
        pygame.draw.circle(s, acc, (px, py), 85)
        pygame.draw.ellipse(s, mix(acc, (255, 255, 255), 0.5), (px - 150, py - 18, 300, 36), 4)
    elif style == "jungle":
        for _ in range(16):
            tx = rnd.randint(0, W)
            pygame.draw.rect(s, (70, 45, 25), (tx, HORIZON - rnd.randint(150, 330), rnd.randint(18, 34), 330))
        for _ in range(60):
            pygame.draw.circle(s, mix((20, 90, 40), (60, 160, 70), rnd.random()),
                               (rnd.randint(0, W), rnd.randint(30, 260)), rnd.randint(30, 70))
        for _ in range(10):
            vx = rnd.randint(0, W)
            pygame.draw.line(s, (30, 110, 50), (vx, 0), (vx + rnd.randint(-20, 20), rnd.randint(120, 260)), 4)
    else:  # arena: كشافات + لافتات
        for _ in range(6):
            x0 = rnd.randint(60, W - 60)
            pygame.draw.polygon(ov, (*acc, 38), [(x0, 0), (x0 - rnd.randint(70, 130), HORIZON), (x0 + rnd.randint(70, 130), HORIZON)])
        for k in range(6):
            bx = 100 + k * 220
            pygame.draw.rect(s, shade(rope, 0.7), (bx, 40, 110, 150))
            pygame.draw.rect(s, acc, (bx + 10, 55, 90, 12))
            pygame.draw.circle(s, acc, (bx + 55, 120), 28, 4)
    s.blit(ov, (0, 0))
    return s.convert()


def get_background(i):
    if i not in _bg_cache:
        _bg_cache[i] = build_background(i)
    return _bg_cache[i]


def get_crowd(i):
    """الجمهور: ثلاثة صفوف خلف الحلبة."""
    if i not in _crowd_cache:
        rnd = random.Random(i * 17 + 3)
        base = BACKGROUNDS[i][4]
        lst = []
        for row, (yy, r) in enumerate(((HORIZON - 44, 9), (HORIZON - 24, 10), (HORIZON - 3, 12))):
            x = rnd.randint(0, 20)
            while x < W + 30:
                col = mix(shade(base, 0.5), (rnd.randint(40, 200), rnd.randint(40, 200), rnd.randint(40, 200)), 0.35)
                lst.append((x, yy, r, shade(col, 0.55 + row * 0.2), rnd.random() * 6))
                x += rnd.randint(22, 32)
        _crowd_cache[i] = lst
    return _crowd_cache[i]


# ---------------------------------------------------------------------
# 5) نظام الكاميرا: منظور خلفي + Zoom + اهتزاز عند الضربات
#    إحداثيات العالم: x من -1 (يسار) إلى 1 (يمين)، d من 0 (قريب) إلى 1 (بعيد)
# ---------------------------------------------------------------------
class Camera:
    ZOOM_MIN, ZOOM_MAX = 0.75, 1.5

    def __init__(self):
        self.zoom = 1.0
        self.target = 1.0
        self.shake = 0.0
        self.sx = self.sy = 0.0
        self.cx = 0.0

    def zoom_by(self, delta):
        self.target = clamp(self.target + delta, self.ZOOM_MIN, self.ZOOM_MAX)

    def update(self, dt, focus_x):
        self.zoom += (self.target - self.zoom) * min(1, dt * 8)
        self.shake = max(0.0, self.shake - dt * 2.5)
        a = self.shake * 16
        self.sx, self.sy = random.uniform(-a, a), random.uniform(-a, a)
        self.cx += (focus_x * 70 - self.cx) * min(1, dt * 3)

    def proj(self, x, d):
        """تحويل نقطة عالم إلى شاشة. يعيد (px, py, scale)."""
        y = lerp(700, 440, d)
        sc = lerp(1.0, 0.6, d)
        hw = lerp(600, 340, d)
        sx = W / 2 + x * hw - self.cx
        z = self.zoom
        return (PIVOT[0] + (sx - PIVOT[0]) * z + self.sx,
                PIVOT[1] + (y - PIVOT[1]) * z + self.sy,
                sc * z)


def draw_ring(surf, cam, bg_i):
    """رسم الحلبة: القماش، الدائرة، الحبال، الأعمدة (بمنظور)."""
    name, style, top, bot, floor, rope, acc = BACKGROUNDS[bg_i]

    def P(x, d):
        return cam.proj(x, d)[:2]

    pygame.draw.polygon(surf, shade(acc, 0.35), [P(-1.4, -0.4), P(1.4, -0.4), P(1.4, 1.35), P(-1.4, 1.35)])
    canvas = mix((222, 214, 198), acc, 0.12)
    corners = [(-1.15, -0.25), (1.15, -0.25), (1.15, 1.2), (-1.15, 1.2)]
    pygame.draw.polygon(surf, canvas, [P(*c) for c in corners])
    # دائرة الشعار
    ring_pts = [P(0.62 * math.cos(a), 0.48 + 0.42 * math.sin(a)) for a in [k * math.pi / 20 for k in range(40)]]
    pygame.draw.polygon(surf, mix(canvas, acc, 0.25), ring_pts)
    pygame.draw.polygon(surf, mix(canvas, rope, 0.7), ring_pts, 4)
    pygame.draw.polygon(surf, WHITE, [P(*c) for c in corners], 4)

    base = [cam.proj(x, d) for (x, d) in corners]   # NL, NR, FR, FL

    def top_of(pt, h):
        return (pt[0], pt[1] - h * pt[2])
    # الحبال الثلاثة: الخلفي ثم الجانبيان
    for h in (55, 105, 155):
        for a, b in ((3, 2), (0, 3), (1, 2)):
            pa, pb = top_of(base[a], h), top_of(base[b], h)
            w = max(2, int(6 * (base[a][2] + base[b][2]) / 2))
            pygame.draw.line(surf, rope, pa, pb, w)
            pygame.draw.line(surf, shade(rope, 1.4), (pa[0], pa[1] - w // 3), (pb[0], pb[1] - w // 3), max(1, w // 3))
    # الأعمدة
    for p in base:
        t = top_of(p, 175)
        pygame.draw.line(surf, (190, 190, 200), (p[0], p[1]), t, max(3, int(11 * p[2])))
        pygame.draw.circle(surf, rope, (int(t[0]), int(t[1])), max(4, int(9 * p[2])))
        pygame.draw.rect(surf, rope, (p[0] - 8 * p[2], p[1] - 150 * p[2], 16 * p[2], 105 * p[2]), 0)


def draw_backdrop(surf, cam, bg_i, t):
    """الخلفية الثابتة + الجمهور المتحرك + الحلبة."""
    surf.blit(get_background(bg_i), (0, 0))
    for (x, y, r, col, ph) in get_crowd(bg_i):
        yy = y + math.sin(t * 3 + ph) * 3
        xx = x - cam.cx * 0.15
        pygame.draw.ellipse(surf, col, (xx - r * 1.3, yy + r * 0.6, r * 2.6, r * 2.2))
        pygame.draw.circle(surf, shade(col, 1.3), (int(xx), int(yy)), r)
    draw_ring(surf, cam, bg_i)


# ---------------------------------------------------------------------
# 6) رسم المقاتل (أشكال هندسية). back=True => منظور خلفي (اللاعب)
# ---------------------------------------------------------------------
def draw_fighter(surf, ox, oy, s, ch, back, pose):
    ko = pose.get("ko", 0)
    if ko > 0:  # السقوط: ارسم على سطح مؤقت ثم أدِر
        tw, th = int(380 * s), int(430 * s)
        tmp = pygame.Surface((tw, th), pygame.SRCALPHA)
        p2 = dict(pose)
        p2["ko"] = 0
        draw_fighter(tmp, tw / 2, th - 10 * s, s, ch, back, p2)
        ang = 88 * min(1, ko) * pose.get("dir", 1)
        rot = pygame.transform.rotozoom(tmp, ang, 1)
        rad = math.radians(ang)
        vy = th / 2 - 10 * s
        surf.blit(rot, rot.get_rect(center=(ox - vy * math.sin(rad), oy - vy * math.cos(rad))))
        return

    t = pose.get("t", 0)
    hurt = pose.get("hurt", 0)
    e = pose.get("ext", 0)
    hand = pose.get("hand", 1)
    kind = pose.get("kind", "jab")
    block = pose.get("block", False)
    skin = ch["skin"]
    if pose.get("flash", 0) > 0:
        skin = mix(skin, (255, 255, 255), min(0.7, pose["flash"] * 3))
    dark, light = shade(skin, 0.75), shade(skin, 1.15)
    trunk, trim, glove, hair = ch["trunks"], ch["trim"], ch["gloves"], ch["hair"]
    bob = math.sin(t * 7) * 3
    sway = math.sin(t * 3.5) * 4

    def P(x, y):
        k = clamp(-y / 300, 0, 1)
        return (ox + (x + sway * k) * s, oy + (y + bob * k) * s)

    def circ(c, pt, r, w=0):
        pygame.draw.circle(surf, c, (int(pt[0]), int(pt[1])), max(1, int(r * s)), w)

    # --- الساقان والحذاء ---
    for sg in (-1, 1):
        pygame.draw.line(surf, skin, P(sg * 24, -150), P(sg * 32, -14), max(2, int(34 * s)))
        foot = P(sg * 32 - 20, -17)
        pygame.draw.ellipse(surf, trim, (foot[0], foot[1], max(2, 40 * s), max(2, 17 * s)))
    # --- السروال ---
    pygame.draw.polygon(surf, trunk, [P(-48, -195), P(48, -195), P(58, -112), P(5, -122), P(-5, -122), P(-58, -112)])
    pygame.draw.polygon(surf, trim, [P(-48, -195), P(48, -195), P(49, -184), P(-49, -184)])
    pygame.draw.line(surf, trim, P(-56, -116), P(-5, -125), max(2, int(5 * s)))
    pygame.draw.line(surf, trim, P(56, -116), P(5, -125), max(2, int(5 * s)))
    # --- الجذع ---
    pygame.draw.polygon(surf, skin, [P(-50, -195), P(50, -195), P(66, -278), P(-66, -278)])
    pygame.draw.polygon(surf, dark, [P(-50, -195), P(-38, -195), P(-50, -278), P(-66, -278)])
    pygame.draw.polygon(surf, dark, [P(50, -195), P(38, -195), P(50, -278), P(66, -278)])
    lw = max(1, int(3 * s))
    if back:
        pygame.draw.line(surf, dark, P(0, -280), P(0, -198), lw)
        for sg in (-1, 1):
            pygame.draw.line(surf, dark, P(sg * 34, -266), P(sg * 12, -228), lw)
            pygame.draw.line(surf, dark, P(sg * 12, -228), P(sg * 4, -214), lw)
    else:
        pygame.draw.line(surf, dark, P(0, -270), P(0, -198), lw)
        for yy in (-216, -233, -250):
            pygame.draw.line(surf, dark, P(-15, yy), P(15, yy), lw)
        for sg in (-1, 1):
            pygame.draw.line(surf, dark, P(sg * 8, -262), P(sg * 42, -258), lw)
    # --- الرقبة ---
    pygame.draw.rect(surf, dark, (P(-14, -298)[0], P(-14, -298)[1], 28 * s, 24 * s))

    def arm(sg):
        shoulder = (sg * 62, -264)
        gr = 26
        if block:
            g = (sg * 20, -322) if back else (sg * 17, -306)
        else:
            g = (sg * 44, -292)
        if (not block) and e > 0 and sg == hand:
            if back:   # اللكمة تذهب بعيداً (للأعلى وتصغر)
                if kind == "hook":
                    g = (lerp(sg * 44, -sg * 10, e) + sg * 80 * math.sin(math.pi * e), lerp(-292, -368, e))
                else:
                    g = (lerp(sg * 44, sg * 6, e), lerp(-292, -382, e))
                gr = 26 * (1 - 0.3 * e)
            else:      # اللكمة تأتي نحو الكاميرا (تكبر)
                if kind == "hook":
                    g = (lerp(sg * 44, -sg * 8, e) + sg * 90 * math.sin(math.pi * e), lerp(-292, -262, e))
                else:
                    g = (lerp(sg * 44, sg * 4, e), lerp(-292, -262, e))
                gr = 26 * (1 + 0.9 * e)
        slack = 1 - e * 0.7 if (e > 0 and sg == hand) else 1
        elbow = ((shoulder[0] + g[0]) / 2 + sg * 28 * slack, (shoulder[1] + g[1]) / 2 + 30 * slack)
        aw = max(2, int(24 * s * (gr / 26) ** 0.5))
        pygame.draw.line(surf, skin, P(*shoulder), P(*elbow), aw)
        pygame.draw.line(surf, skin, P(*elbow), P(*g), aw)
        circ(skin, P(*elbow), 11 * (gr / 26) ** 0.5)
        gp = P(*g)
        circ(trim, gp, gr + 4)
        circ(glove, gp, gr)
        circ(shade(glove, 1.5), (gp[0] - gr * 0.3 * s, gp[1] - gr * 0.3 * s), gr * 0.35)
        circ(shade(glove, 0.7), (gp[0] + sg * gr * 0.55 * s, gp[1] + gr * 0.25 * s), gr * 0.3)

    def head():
        hx = math.sin(t * 40) * 7 * hurt
        hy = -312 + hurt * 6
        c = P(hx, hy)
        circ(skin, P(hx - 31, hy + 2), 7)
        circ(skin, P(hx + 31, hy + 2), 7)
        if back:
            circ(hair, c, 31)
            pygame.draw.ellipse(surf, dark, (P(hx - 20, hy + 20)[0], P(hx - 20, hy + 20)[1], 40 * s, 14 * s))
        else:
            circ(skin, c, 31)
            circ(hair, P(hx, hy - 8), 31)
            f = P(hx - 27, hy - 18)
            pygame.draw.ellipse(surf, skin, (f[0], f[1], 54 * s, 56 * s))
            pygame.draw.line(surf, trim, P(hx - 29, hy - 14), P(hx + 29, hy - 14), max(2, int(6 * s)))
            for sg in (-1, 1):
                ex, ey = P(hx + sg * 12, hy - 2)
                if hurt > 0.4:
                    pygame.draw.line(surf, (30, 20, 20), (ex - 6 * s, ey), (ex + 6 * s, ey), max(1, int(3 * s)))
                else:
                    pygame.draw.ellipse(surf, WHITE, (ex - 7 * s, ey - 4 * s, 14 * s, 9 * s))
                    circ((20, 20, 20), (ex, ey), 3.5)
                bx0, by0 = P(hx + sg * 5, hy - 12)
                bx1, by1 = P(hx + sg * 20, hy - 8)
                pygame.draw.line(surf, hair if hair != skin else dark, (bx0, by0), (bx1, by1), max(2, int(4 * s)))
            pygame.draw.line(surf, dark, P(hx, hy - 2), P(hx - 2, hy + 8), max(1, int(3 * s)))
            if hurt > 0.2:
                m = P(hx - 9, hy + 12)
                pygame.draw.ellipse(surf, (60, 10, 10), (m[0], m[1], 18 * s, 10 * s))
                pygame.draw.ellipse(surf, WHITE, (m[0] + 2 * s, m[1], 14 * s, 4 * s))
            else:
                pygame.draw.line(surf, (90, 30, 30), P(hx - 9, hy + 14), P(hx + 9, hy + 14), max(2, int(4 * s)))

    if back:
        if not block:
            arm(-1)
            arm(1)
        head()
        if block:
            arm(-1)
            arm(1)
    else:
        head()
        arm(-1)
        arm(1)


# ---------------------------------------------------------------------
# 7) المقاتل
# ---------------------------------------------------------------------
PUNCH = {"jab": (0.32, 0.13), "hook": (0.56, 0.25)}   # (المدة الكلية، لحظة التأثير)


class Fighter:
    def __init__(self, ch, is_player, max_hp, dmg_mult=1.0, move_speed=1.7):
        self.ch = ch
        self.is_player = is_player
        self.x = 0.0
        self.d = 0.05 if is_player else 0.7
        self.max_hp = max_hp
        self.hp = max_hp
        self.ghost = max_hp               # شريط الضرر المتأخر
        self.pf = 0.6 + 0.08 * ch["power"]
        self.dmg_mult = dmg_mult
        self.move_speed = move_speed
        self.state = "idle"               # idle | punch | block | hurt | ko
        self.t = 0.0
        self.dur = 0.0
        self.hit_t = 0.0
        self.kind = "jab"
        self.hand = 1
        self.hit_done = False
        self.cool = 0.0
        self.after = 0.05                 # راحة بعد اللكمة
        self.anim = random.random() * 5
        self.flash = 0.0
        self.dir = 1 if is_player else -1

    @property
    def ext(self):
        if self.state != "punch":
            return 0.0
        if self.t < self.hit_t:
            return self.t / max(1e-3, self.hit_t)
        return max(0.0, 1 - (self.t - self.hit_t) / max(1e-3, self.dur - self.hit_t))

    def pose(self):
        return dict(t=self.anim, ext=self.ext, hand=self.hand, kind=self.kind, block=self.state == "block",
                    hurt=(1 - self.t / max(1e-3, self.dur)) if self.state == "hurt" else 0,
                    flash=self.flash, ko=min(1, self.t / 0.9) if self.state == "ko" else 0, dir=self.dir)

    def punch(self, kind, hand, slow=1.0):
        if self.state != "idle" or self.cool > 0:
            return False
        dur, hit = PUNCH[kind]
        spd = 0.75 + 0.05 * self.ch["speed"]
        self.kind, self.hand = kind, hand
        self.state, self.t = "punch", 0.0
        self.dur, self.hit_t = dur * slow / spd, hit * slow / spd
        self.hit_done = False
        SOUNDS["whoosh"].play()
        return True

    def take(self, dmg, kind):
        self.hp -= dmg
        self.flash = 0.18
        if self.hp <= 0:
            self.hp = 0
            self.state, self.t = "ko", 0.0
        else:
            self.state, self.t = "hurt", 0.0
            self.dur = 0.22 if kind == "jab" else 0.38

    def chip(self, dmg):  # ضرر مخفف أثناء الدفاع
        self.hp -= dmg
        self.flash = 0.08
        if self.hp <= 0:
            self.hp = 0
            self.state, self.t = "ko", 0.0

    def update(self, dt, fight, foe):
        self.anim += dt
        self.flash = max(0.0, self.flash - dt)
        self.cool = max(0.0, self.cool - dt)
        self.ghost = max(self.hp, self.ghost - self.max_hp * 0.2 * dt) if self.ghost > self.hp else self.hp
        if self.state in ("punch", "hurt", "ko"):
            self.t += dt
        if self.state == "punch":
            if not self.hit_done and self.t >= self.hit_t:
                self.hit_done = True
                fight.resolve_hit(self, foe)
            if self.state == "punch" and self.t >= self.dur:
                self.state = "idle"
                self.cool = self.after
        elif self.state == "hurt" and self.t >= self.dur:
            self.state = "idle"


# ---------------------------------------------------------------------
# 8) القتال (الجيم بلاي)
# ---------------------------------------------------------------------
class Fight:
    def __init__(self, game, level):
        self.game = game
        self.level = level
        self.bg = level - 1
        self.cam = Camera()
        pc = ROSTER[game.selected]
        oi = level % len(ROSTER)
        if oi == game.selected:
            oi = (oi + 1) % len(ROSTER)
        oc = ROSTER[oi]
        lv = level / NUM_LEVELS
        self.player = Fighter(pc, True, 100 * (0.7 + 0.06 * pc["health"]), 1.0, 1.7 + 0.08 * pc["speed"])
        self.opp = Fighter(oc, False, (60 + level * 4) * (0.85 + 0.03 * oc["health"]),
                           0.55 + 0.04 * level, lerp(0.6, 1.5, lv))
        self.opp.after = lerp(0.5, 0.15, lv)
        self.ai = dict(think=1.5, target=0.0, block=0.0, combo=0)
        self.phase = "intro"             # intro | fight | end
        self.phase_t = 0.0
        self.t = 0.0
        self.timer = float(ROUND_TIME)
        self.fx = []
        self.hitstop = 0.0
        self.red = 0.0
        self.paused = False
        self.winner = None
        self.banner = ("ROUND 1", 2.4, GOLD)
        SOUNDS["bell"].play()

    # ---------- الإدخال ----------
    def handle_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.paused = not self.paused
            elif self.paused and e.key == pygame.K_m:
                self.game.set_state("menu")
            elif self.phase == "fight" and not self.paused:
                if e.key in (pygame.K_j, pygame.K_z):
                    self.player.punch("jab", -1)
                elif e.key in (pygame.K_k, pygame.K_x):
                    self.player.punch("hook", 1)
        elif e.type == pygame.MOUSEBUTTONDOWN and self.phase == "fight" and not self.paused:
            if e.button == 1:
                self.player.punch("jab", -1)
            elif e.button == 3:
                self.player.punch("hook", 1)
        elif e.type == pygame.MOUSEWHEEL:
            self.cam.zoom_by(0.08 * e.y)

    # ---------- حركة / ذكاء اصطناعي ----------
    def move_fighter(self, f, direction, dt):
        if f.state in ("idle", "punch", "block"):
            k = 0.4 if f.state == "punch" else 0.6 if f.state == "block" else 1.0
            f.x = clamp(f.x + direction * f.move_speed * k * dt, -0.9, 0.9)

    def update_ai(self, dt):
        o, p = self.opp, self.player
        lv = self.level / NUM_LEVELS
        ai = self.ai
        ai["think"] -= dt
        slow = lerp(2.0, 1.1, lv)         # كلما قلّ الرقم أصبحت لكمات الخصم أسرع (أصعب)
        if ai["block"] > 0:
            ai["block"] -= dt
            if o.state == "idle":
                o.state = "block"
            if ai["block"] <= 0 and o.state == "block":
                o.state = "idle"
        if o.state == "idle" and ai["combo"] > 0 and o.cool <= 0:
            ai["combo"] -= 1
            o.punch("hook", random.choice((-1, 1)), slow)
        if ai["think"] <= 0:
            ai["think"] = lerp(1.1, 0.35, lv) * random.uniform(0.7, 1.3)
            aligned = abs(o.x - p.x) < 0.35
            if p.state == "punch" and random.random() < lerp(0.2, 0.65, lv):
                if random.random() < 0.6:
                    ai["block"] = random.uniform(0.35, 0.7)
                else:
                    ai["target"] = clamp(o.x + random.choice((-1, 1)) * 0.7, -0.9, 0.9)
            elif o.state in ("idle", "block") and aligned and random.random() < lerp(0.5, 0.9, lv):
                if o.state == "block":
                    o.state = "idle"
                    ai["block"] = 0
                kind = "hook" if random.random() < 0.4 else "jab"
                o.punch(kind, random.choice((-1, 1)), slow)
                if kind == "jab" and random.random() < lv * 0.7:
                    ai["combo"] = 1
            else:
                ai["target"] = clamp(p.x + random.uniform(-0.35, 0.35), -0.9, 0.9)
        diff = ai["target"] - o.x
        if abs(diff) > 0.03:
            self.move_fighter(o, math.copysign(1, diff), dt)

    # ---------- حساب الضربة ----------
    def resolve_hit(self, att, dfn):
        if dfn.state == "ko" or self.phase == "end":
            return
        reach = 0.5 if att.kind == "jab" else 0.62
        if abs(att.x - dfn.x) > reach:       # أخطأ الهدف
            if att.is_player:
                sx, sy, sc = self.cam.proj(dfn.x, dfn.d)
                self.fx.append(dict(k="text", x=sx, y=sy - 330 * sc, life=0.5, txt="MISS", c=(200, 200, 200), size=28))
            return
        heavy = att.kind == "hook"
        dmg = (14 if heavy else 6) * att.pf * att.dmg_mult
        sx, sy, sc = self.cam.proj(dfn.x, dfn.d)
        hx = sx + random.uniform(-15, 15)
        hy = sy - (300 if heavy else 270) * sc
        if dfn.state == "block":
            dfn.chip(dmg * (0.3 if heavy else 0.2))
            SOUNDS["block"].play()
            self.add_fx(hx, hy, heavy, True)
            self.cam.shake = max(self.cam.shake, 0.12)
        else:
            if dfn.state == "punch" and not dfn.hit_done:
                dmg *= 1.3                      # ضربة مضادة
            dfn.take(dmg, att.kind)
            SOUNDS["hit_heavy" if heavy else "hit_light"].play()
            self.add_fx(hx, hy, heavy, False)
            self.cam.shake = max(self.cam.shake, 0.45 if heavy else 0.22)
            self.hitstop = 0.07 if heavy else 0.035
            if dfn.is_player:
                self.red = 0.3

    def add_fx(self, x, y, heavy, blocked):
        col = (150, 200, 255) if blocked else ((255, 120, 30) if heavy else (255, 230, 90))
        for _ in range(8 if not heavy else 15):
            a = random.uniform(0, math.tau)
            v = random.uniform(150, 420)
            self.fx.append(dict(k="spark", x=x, y=y, vx=math.cos(a) * v, vy=math.sin(a) * v - 80,
                                life=0.4, max=0.4, c=col))
        self.fx.append(dict(k="burst", x=x, y=y, life=0.25, max=0.25, r=(70 if heavy else 45), c=col))
        word = "BLOCK" if blocked else random.choice(("WHAM!", "POW!", "BAM!", "SMACK!") if heavy else ("POW!", "BAP!", "THUD!"))
        self.fx.append(dict(k="text", x=x, y=y - 40, life=0.7, txt=word, c=col, size=52 if heavy else 40))

    # ---------- التحديث ----------
    def update(self, dt):
        if self.paused:
            return
        self.t += dt
        self.cam.update(dt, self.player.x * 0.6)
        self.red = max(0.0, self.red - dt)
        k = pygame.key.get_pressed()
        if k[pygame.K_e] or k[pygame.K_EQUALS] or k[pygame.K_PLUS] or k[pygame.K_KP_PLUS]:
            self.cam.zoom_by(dt * 0.8)
        if k[pygame.K_q] or k[pygame.K_MINUS] or k[pygame.K_KP_MINUS]:
            self.cam.zoom_by(-dt * 0.8)
        # المؤثرات
        for f in self.fx:
            f["life"] -= dt
            if f["k"] == "spark":
                f["x"] += f["vx"] * dt
                f["y"] += f["vy"] * dt
                f["vy"] += 700 * dt
            elif f["k"] == "text":
                f["y"] -= 40 * dt
        self.fx = [f for f in self.fx if f["life"] > 0]
        if self.hitstop > 0:
            self.hitstop -= dt
            return
        p, o = self.player, self.opp
        if self.banner[1] > 0:
            self.banner = (self.banner[0], self.banner[1] - dt, self.banner[2])
        self.phase_t += dt

        if self.phase == "intro":
            p.anim += dt
            o.anim += dt
            if self.phase_t > 2.4:
                self.phase, self.phase_t = "fight", 0.0
                self.banner = ("FIGHT!", 1.0, (255, 80, 60))
        elif self.phase == "fight":
            self.timer -= dt
            move = (1 if (k[pygame.K_d] or k[pygame.K_RIGHT]) else 0) - (1 if (k[pygame.K_a] or k[pygame.K_LEFT]) else 0)
            if move:
                self.move_fighter(p, move, dt)
            want_block = k[pygame.K_s] or k[pygame.K_DOWN] or k[pygame.K_SPACE]
            if want_block and p.state == "idle":
                p.state = "block"
            elif not want_block and p.state == "block":
                p.state = "idle"
            self.update_ai(dt)
            p.update(dt, self, o)
            o.update(dt, self, p)
            if p.hp <= 0 or o.hp <= 0:
                self.end_fight(o.hp <= 0, "K.O.!")
            elif self.timer <= 0:
                self.end_fight(p.hp / p.max_hp >= o.hp / o.max_hp, "TIME!")
        else:  # end
            p.update(dt, self, o)
            o.update(dt, self, p)
            if self.phase_t > 3.0:
                self.game.finish_fight(self.winner)

    def end_fight(self, player_won, msg):
        self.phase, self.phase_t = "end", 0.0
        self.winner = player_won
        self.banner = (msg, 3.0, (255, 60, 60) if player_won else (200, 200, 200))
        loser = self.opp if player_won else self.player
        if loser.state != "ko":
            loser.hp = max(loser.hp, 1)
        SOUNDS["ko"].play()
        SOUNDS["cheer" if player_won else "lose"].play()
        self.cam.shake = 0.6

    # ---------- الرسم ----------
    def fighter_screen(self, f):
        e = f.ext if not f.is_player else 0
        return self.cam.proj(f.x, f.d - 0.1 * e)

    def draw_one(self, surf, f, back):
        sx, sy, sc = self.fighter_screen(f)
        near = abs(self.player.x - self.opp.x) < 0.5
        sh_col = (255, 230, 80) if (f.is_player and near) else (0, 0, 0)
        shadow = pygame.Surface((int(160 * sc) + 2, int(34 * sc) + 2), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (*sh_col, 90), shadow.get_rect())
        surf.blit(shadow, shadow.get_rect(center=(sx, sy)))
        draw_fighter(surf, sx, sy, sc, f.ch, back, f.pose())

    def draw(self, surf):
        draw_backdrop(surf, self.cam, self.bg, self.t)
        self.draw_one(surf, self.opp, False)      # الخصم من الأمام
        self.draw_one(surf, self.player, True)    # اللاعب من الخلف
        for f in self.fx:
            if f["k"] == "spark":
                pygame.draw.line(surf, f["c"], (f["x"], f["y"]), (f["x"] - f["vx"] * 0.03, f["y"] - f["vy"] * 0.03), 3)
            elif f["k"] == "burst":
                prog = 1 - f["life"] / f["max"]
                draw_star(surf, f["x"], f["y"], f["r"] * (0.6 + prog), f["c"])
                draw_star(surf, f["x"], f["y"], f["r"] * (0.3 + prog * 0.5), WHITE)
            else:
                text(surf, f["txt"], f.get("size", 40), f["c"], (f["x"], f["y"]))
        if self.red > 0:
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((255, 0, 0, int(110 * self.red / 0.3)))
            surf.blit(ov, (0, 0))
        self.draw_hud(surf)
        if self.paused:
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 150))
            surf.blit(ov, (0, 0))
            text(surf, "PAUSED", 80, GOLD, (W / 2, 300))
            text(surf, "ESC - resume      M - main menu", 30, WHITE, (W / 2, 380))

    def bar(self, surf, x, y, w, h, f, right):
        pct, gh = f.hp / f.max_hp, f.ghost / f.max_hp
        pygame.draw.rect(surf, (25, 25, 30), (x - 3, y - 3, w + 6, h + 6), border_radius=8)
        pygame.draw.rect(surf, (60, 60, 70), (x, y, w, h), border_radius=6)
        col = mix((230, 40, 40), (60, 220, 70), clamp(pct * 1.6 - 0.2, 0, 1))
        for val, c in ((gh, (255, 210, 60)), (pct, col)):
            bw = int(w * clamp(val, 0, 1))
            if bw > 0:
                pygame.draw.rect(surf, c, (x + w - bw if right else x, y, bw, h), border_radius=6)

    def draw_hud(self, surf):
        p, o = self.player, self.opp
        self.bar(surf, 40, 62, 470, 28, p, False)
        self.bar(surf, W - 40 - 470, 62, 470, 28, o, True)
        text(surf, p.ch["name"], 28, WHITE, (40, 34), "midleft")
        text(surf, o.ch["name"], 28, WHITE, (W - 40, 34), "midright")
        text(surf, f"{int(math.ceil(max(0, self.timer)))}", 54, GOLD, (W / 2, 52))
        text(surf, f"LEVEL {self.level}/{NUM_LEVELS}  -  {BACKGROUNDS[self.bg][0]}", 22, WHITE, (W / 2, 96))
        text(surf, money_str(self.game.money), 26, (120, 255, 140), (40, H - 28), "midleft")
        text(surf, "A/D move | J/K or L/R-click punch | S block | Wheel / Q,E zoom | ESC pause",
             18, (230, 230, 230), (W - 30, H - 28), "midright", bold=False)
        text_z = f"ZOOM x{self.cam.zoom:.2f}"
        text(surf, text_z, 18, (230, 230, 230), (W - 30, H - 52), "midright", bold=False)
        if self.banner[1] > 0:
            size = 130 if self.phase == "end" else int(100 + 20 * math.sin(self.t * 6))
            text(surf, self.banner[0], size, self.banner[2], (W / 2, 250))


# ---------------------------------------------------------------------
# 9) واجهات المستخدم + إدارة اللعبة
# ---------------------------------------------------------------------
class Button:
    def __init__(self, rect, label, cb, size=32, color=(190, 40, 40)):
        self.rect = pygame.Rect(rect)
        self.label, self.cb, self.size, self.color = label, cb, size, color

    def draw(self, surf, mouse):
        hov = self.rect.collidepoint(mouse)
        col = shade(self.color, 1.25) if hov else self.color
        pygame.draw.rect(surf, (0, 0, 0), self.rect.move(3, 4), border_radius=12)
        pygame.draw.rect(surf, col, self.rect, border_radius=12)
        pygame.draw.rect(surf, GOLD if hov else (230, 230, 230), self.rect, 3, border_radius=12)
        text(surf, self.label, self.size, WHITE, self.rect.center)


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("KNOCKOUT LEGENDS")
        self.clock = pygame.time.Clock()
        global SOUNDS
        SOUNDS = build_sounds()
        self.running = True
        # --- بيانات اللاعب (في الذاكرة) ---
        self.money = 0
        self.owned = {0}
        self.selected = 0
        self.progress = 1            # أعلى مستوى مفتوح
        self.level = 1
        self.next_level = 1
        self.result = None
        self.fight = None
        self.state = "menu"
        self.menu_t = 0.0
        self.toast = ("", 0.0)
        self.cam = Camera()
        self.buttons = []
        self.set_state("menu")

    # ---------- إدارة الحالات ----------
    def set_state(self, st):
        self.state = st
        b = []
        cx = W // 2
        if st == "menu":
            b = [Button((cx - 160, 290, 320, 58), "PLAY", lambda: self.start_fight(self.progress), 34),
                 Button((cx - 160, 360, 320, 58), "LEVELS", lambda: self.set_state("levels"), 34, (40, 90, 190)),
                 Button((cx - 160, 430, 320, 58), "SHOP", lambda: self.set_state("shop"), 34, (200, 140, 20)),
                 Button((cx - 160, 500, 320, 58), "QUIT", self.quit, 34, (80, 80, 90))]
        elif st in ("levels", "shop"):
            b = [Button((30, 22, 150, 46), "< BACK", lambda: self.set_state("menu"), 26, (80, 80, 90))]
        elif st == "result":
            win = self.result["win"]
            b = [Button((cx - 480, 580, 220, 56), "NEXT" if win else "RETRY", lambda: self.start_fight(self.next_level), 30),
                 Button((cx - 240, 580, 220, 56), "LEVELS", lambda: self.set_state("levels"), 30, (40, 90, 190)),
                 Button((cx + 20, 580, 220, 56), "SHOP", lambda: self.set_state("shop"), 30, (200, 140, 20)),
                 Button((cx + 260, 580, 220, 56), "MENU", lambda: self.set_state("menu"), 30, (80, 80, 90))]
        self.buttons = b

    def quit(self):
        self.running = False

    def start_fight(self, level):
        level = int(clamp(level, 1, NUM_LEVELS))
        self.level = level
        self.fight = Fight(self, level)
        self.state = "fight"
        self.buttons = []

    def finish_fight(self, win):
        lvl = self.fight.level
        if win:
            self.money += WIN_REWARD
            self.progress = min(NUM_LEVELS, max(self.progress, lvl + 1))
            self.next_level = min(NUM_LEVELS, lvl + 1)   # تقدم تلقائي للمستوى التالي
        else:
            self.next_level = lvl                         # إعادة نفس المستوى والخلفية
        self.result = dict(win=win, level=lvl, timer=7.0, champion=win and lvl == NUM_LEVELS)
        SOUNDS["win" if win else "lose"].play()
        self.set_state("result")

    def say(self, msg):
        self.toast = (msg, 2.0)

    # ---------- تخطيط الشاشات ----------
    def shop_rects(self):
        return [pygame.Rect(30 + (i % 4) * 310, 125 + (i // 4) * 278, 290, 262) for i in range(len(ROSTER))]

    def level_rects(self):
        return [pygame.Rect(67 + (i % 7) * 166, 170 + (i // 7) * 142, 150, 128) for i in range(NUM_LEVELS)]

    # ---------- الأحداث ----------
    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False
            return
        if self.state == "fight":
            self.fight.handle_event(e)
            return
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE and self.state in ("levels", "shop", "result"):
                self.set_state("menu")
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.state == "result":
                    self.start_fight(self.next_level)
                elif self.state == "menu":
                    self.start_fight(self.progress)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for b in self.buttons:
                if b.rect.collidepoint(e.pos):
                    SOUNDS["click"].play()
                    b.cb()
                    return
            if self.state == "levels":
                for i, r in enumerate(self.level_rects()):
                    if r.collidepoint(e.pos):
                        if i + 1 <= self.progress:
                            SOUNDS["click"].play()
                            self.start_fight(i + 1)
                        else:
                            self.say("Level locked - win the previous level first!")
                        return
            elif self.state == "shop":
                for i, r in enumerate(self.shop_rects()):
                    if r.collidepoint(e.pos):
                        self.shop_click(i)
                        return

    def shop_click(self, i):
        ch = ROSTER[i]
        if i in self.owned:
            self.selected = i
            SOUNDS["click"].play()
            self.say(f"{ch['name']} selected")
        elif self.money >= ch["price"]:
            self.money -= ch["price"]
            self.owned.add(i)
            self.selected = i
            SOUNDS["win"].play()
            self.say(f"Purchased {ch['name']}!")
        else:
            SOUNDS["block"].play()
            self.say(f"Not enough money! Need {money_str(ch['price'] - self.money)} more")

    # ---------- التحديث ----------
    def update(self, dt):
        self.menu_t += dt
        self.toast = (self.toast[0], max(0, self.toast[1] - dt))
        if self.state == "fight":
            self.fight.update(dt)
        elif self.state == "result":
            self.result["timer"] -= dt
            if self.result["timer"] <= 0:       # بدء المستوى التالي تلقائياً
                self.start_fight(self.next_level)
        self.cam.update(dt, 0)

    # ---------- الرسم ----------
    def draw(self):
        s = self.screen
        mouse = pygame.mouse.get_pos()
        if self.state == "fight":
            self.fight.draw(s)
            return
        if self.state == "menu":
            self.draw_scene_bg(s, self.progress - 1)
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 120))
            s.blit(ov, (0, 0))
            text(s, "KNOCKOUT LEGENDS", 88, GOLD, (W / 2, 120))
            text(s, "Boxing & Wrestling Arena", 30, WHITE, (W / 2, 190))
            text(s, f"Money: {money_str(self.money)}    Level: {self.progress}/{NUM_LEVELS}    "
                    f"Fighter: {ROSTER[self.selected]['name']}", 24, (120, 255, 140), (W / 2, 250))
            text(s, "A/D move | J/K or Left/Right click = punch | S block | Mouse wheel or Q/E = zoom",
                 20, WHITE, (W / 2, H - 30), bold=False)
        elif self.state == "levels":
            self.draw_levels(s, mouse)
        elif self.state == "shop":
            self.draw_shop(s, mouse)
        elif self.state == "result":
            self.draw_result(s)
        for b in self.buttons:
            b.draw(s, mouse)
        if self.toast[1] > 0:
            r = text(s, self.toast[0], 28, WHITE, (W / 2, H - 70), shadow=False)
            pygame.draw.rect(s, (20, 20, 30), r.inflate(40, 20), border_radius=10)
            pygame.draw.rect(s, GOLD, r.inflate(40, 20), 2, border_radius=10)
            text(s, self.toast[0], 28, WHITE, (W / 2, H - 70))

    def draw_scene_bg(self, s, bg_i):
        """مشهد حلبة بشخصيتين للقوائم."""
        draw_backdrop(s, self.cam, bg_i, self.menu_t)
        a = Fighter(ROSTER[self.selected], True, 100)
        b = Fighter(ROSTER[(self.progress) % len(ROSTER) if (self.progress) % len(ROSTER) != self.selected else 2], False, 100)
        a.anim = b.anim = self.menu_t
        a.x, b.x = -0.35, 0.35
        for f, back in ((b, False), (a, True)):
            sx, sy, sc = self.cam.proj(f.x, f.d)
            draw_fighter(s, sx, sy, sc, f.ch, back, f.pose())

    def draw_levels(self, s, mouse):
        s.fill((14, 14, 24))
        text(s, "SELECT LEVEL", 56, GOLD, (W / 2, 70))
        text(s, "Win a fight: +1000 EGP and auto-advance to the next level. Lose: replay the same level.",
             22, WHITE, (W / 2, 125), bold=False)
        for i, r in enumerate(self.level_rects()):
            name, style, top, bot, floor, rope, acc = BACKGROUNDS[i]
            unlocked = i + 1 <= self.progress
            pygame.draw.rect(s, top, r, border_radius=12)
            pygame.draw.rect(s, bot, (r.x, r.y + r.h // 2, r.w, r.h // 2), border_bottom_left_radius=12, border_bottom_right_radius=12)
            pygame.draw.rect(s, floor, (r.x, r.y + r.h - 34, r.w, 34), border_bottom_left_radius=12, border_bottom_right_radius=12)
            text(s, str(i + 1), 52, WHITE, (r.centerx, r.y + 44))
            text(s, name, 17, WHITE, (r.centerx, r.y + r.h - 16))
            if not unlocked:
                ov = pygame.Surface(r.size, pygame.SRCALPHA)
                pygame.draw.rect(ov, (0, 0, 0, 175), ov.get_rect(), border_radius=12)
                s.blit(ov, r)
                pygame.draw.rect(s, (200, 200, 210), (r.centerx - 14, r.centery - 4, 28, 22), border_radius=4)
                pygame.draw.arc(s, (200, 200, 210), (r.centerx - 10, r.centery - 22, 20, 28), 0, math.pi, 4)
            elif i + 1 < self.progress:
                text(s, "CLEARED", 16, (120, 255, 140), (r.centerx, r.y + 88))
            border = GOLD if r.collidepoint(mouse) and unlocked else ((255, 255, 255) if i + 1 == self.progress else (90, 90, 100))
            width = 4 if i + 1 == self.progress else 2
            pygame.draw.rect(s, border, r, width, border_radius=12)
        text(s, f"Money: {money_str(self.money)}", 26, (120, 255, 140), (W - 40, 45), "midright")

    def draw_shop(self, s, mouse):
        s.fill((16, 14, 26))
        text(s, "SHOP", 56, GOLD, (W / 2, 55))
        text(s, f"Money: {money_str(self.money)}", 28, (120, 255, 140), (W - 40, 45), "midright")
        for i, r in enumerate(self.shop_rects()):
            ch = ROSTER[i]
            owned, sel = i in self.owned, i == self.selected
            pygame.draw.rect(s, (34, 32, 50) if not r.collidepoint(mouse) else (46, 42, 70), r, border_radius=14)
            pygame.draw.rect(s, GOLD if sel else (90, 90, 110), r, 4 if sel else 2, border_radius=14)
            text(s, ch["name"], 26, WHITE, (r.centerx, r.y + 24))
            text(s, ch["tag"], 16, (180, 180, 200), (r.centerx, r.y + 46), bold=False)
            s.set_clip(r.inflate(-6, -6))
            draw_fighter(s, r.x + 72, r.y + 205, 0.42, ch, False,
                         dict(t=self.menu_t + i, ext=0, hand=1, kind="jab", block=False, hurt=0, flash=0, ko=0))
            s.set_clip(None)
            for k, (lab, key) in enumerate((("POWER", "power"), ("SPEED", "speed"), ("HEALTH", "health"))):
                yy = r.y + 85 + k * 34
                text(s, lab, 16, WHITE, (r.x + 150, yy), "midleft", bold=False)
                pygame.draw.rect(s, (60, 60, 75), (r.x + 150, yy + 10, 120, 10), border_radius=5)
                pygame.draw.rect(s, [(230, 70, 60), (80, 190, 255), (90, 220, 100)][k],
                                 (r.x + 150, yy + 10, 12 * ch[key], 10), border_radius=5)
            if sel:
                lab, col = "SELECTED", (40, 150, 70)
            elif owned:
                lab, col = "SELECT", (40, 90, 190)
            else:
                lab = f"BUY  {ch['price']:,} {CURRENCY}"
                col = (200, 140, 20) if self.money >= ch["price"] else (110, 60, 60)
            br = pygame.Rect(r.x + 20, r.bottom - 48, r.w - 40, 36)
            pygame.draw.rect(s, col, br, border_radius=8)
            text(s, lab, 22, WHITE, br.center)

    def draw_result(self, s):
        res = self.result
        self.draw_scene_bg(s, res["level"] - 1)
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        s.blit(ov, (0, 0))
        if res["win"]:
            text(s, "CHAMPION!" if res["champion"] else "VICTORY!", 110, GOLD, (W / 2, 160))
            text(s, f"+ {money_str(WIN_REWARD)}", 56, (120, 255, 140), (W / 2, 275))
            nxt = "You beat the final level! Replaying level 21..." if res["champion"] else \
                f"Next: Level {self.next_level} - {BACKGROUNDS[self.next_level - 1][0]}"
        else:
            text(s, "DEFEATED", 110, (230, 70, 70), (W / 2, 160))
            text(s, "Try again - same level, same arena", 40, WHITE, (W / 2, 275))
            nxt = f"Retry: Level {self.next_level} - {BACKGROUNDS[self.next_level - 1][0]}"
        text(s, f"Total money: {money_str(self.money)}", 32, WHITE, (W / 2, 360))
        text(s, nxt, 30, (200, 220, 255), (W / 2, 430))
        text(s, f"Auto-starting in {int(math.ceil(max(0, res['timer'])))}s  (Enter = now, ESC = menu)",
             26, WHITE, (W / 2, 500), bold=False)

    # ---------- الحلقة الرئيسية ----------
    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            for e in pygame.event.get():
                self.handle_event(e)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()


def main():
    Game().run()


if __name__ == "__main__":
    main()
