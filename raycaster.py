"""
Raycasting Minecraft-like — оптимизированная версия на numpy.

Что изменилось по сравнению с исходником:
  * Весь рендер векторизован через numpy: DDA сразу для всех столбцов,
    текстурирование стен/пола/неба — одна выборка из массивов, без
    subsurface/transform.scale на каждый луч.
  * Картинка считается в низком внутреннем разрешении и растягивается
    одним вызовом pygame.transform.scale (пиксельный стиль, как в Minecraft).
    Клавиши +/- меняют качество прямо в игре.
  * Свет: карта освещения с тенями от факелов (пересчитывается только
    при изменении карты), мерцание, мягкое затенение углов (AO), туман,
    смена дня и ночи (N), небо с облаками/солнцем/звёздами.
  * Текстурированный пол, факелы-спрайты с ореолом и z-буфером.
  * Можно ломать и ставить блоки, хотбар с 3D-иконками, рамка
    выделения блока, покачивание камеры, обзор мышью (M).
  * Исправлено: мультитач (палец, отпущенный с одной кнопки, больше не
    отпускает все остальные), двойная обработка touch->mouse, коллизия с
    радиусом игрока (нельзя "влипнуть" в стену), дверь нельзя закрыть на себе.

Управление:
  WASD / стрелки вверх-вниз — ходьба, стрелки влево-вправо — поворот
  M — захват мыши (обзор мышью), ЛКМ — сломать, ПКМ — поставить блок
  1-5 / колесо — выбор блока, E — открыть/закрыть дверь
  N — день/ночь, +/- — качество рендера, H — скрыть touch-кнопки, F3 — отладка
"""
import math
import os
import sys
import traceback

# ---------------------------------------------------- ПОКАЗ ОШИБОК --------
# Если игра падает (например, на телефоне), текст ошибки показывается на
# экране и сохраняется в raycaster_error.txt рядом со скриптом.
try:
    _ERR_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raycaster_error.txt")
except Exception:
    _ERR_FILE = "raycaster_error.txt"


def show_error(text):
    print(text)
    try:
        with open(_ERR_FILE, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass
    try:
        import pygame as pg
        pg.init()
        scr = pg.display.get_surface() or pg.display.set_mode((0, 0))
        w, h = scr.get_size()
        fnt = pg.font.SysFont(None, max(22, h // 32))
        lines = ["ОШИБКА (коснитесь экрана, чтобы выйти):", ""]
        for line in text.splitlines():
            while len(line) > 70:
                lines.append(line[:70])
                line = "  " + line[70:]
            lines.append(line)
        scr.fill((25, 0, 0))
        y = 10
        for line in lines[-(h // fnt.get_linesize()):]:
            scr.blit(fnt.render(line, True, (255, 220, 220)), (10, y))
            y += fnt.get_linesize()
        pg.display.flip()
        while True:
            e = pg.event.wait()
            if e.type in (pg.QUIT, pg.KEYDOWN, pg.MOUSEBUTTONDOWN):
                break
        pg.quit()
    except Exception:
        pass


def _excepthook(tp, val, tb):
    show_error("".join(traceback.format_exception(tp, val, tb)))


sys.excepthook = _excepthook

try:
    import numpy as np
except ImportError:
    show_error("Не установлен numpy.\n\nPydroid 3: меню -> Pip -> numpy -> Install\n"
               "ПК: pip install numpy")
    sys.exit(1)

# телефон: просим альбомную ориентацию (до pygame.init)
IS_ANDROID = hasattr(sys, "getandroidapilevel") or "ANDROID_ROOT" in os.environ
if IS_ANDROID:
    os.environ.setdefault("SDL_IOS_ORIENTATIONS", "LandscapeLeft LandscapeRight")

import pygame
from pygame.locals import *

pygame.init()

# события, которых нет в старых версиях pygame
EV_MOUSEWHEEL = getattr(pygame, "MOUSEWHEEL", -101)
EV_FINGERDOWN = getattr(pygame, "FINGERDOWN", -102)
EV_FINGERUP = getattr(pygame, "FINGERUP", -103)
EV_FINGERMOTION = getattr(pygame, "FINGERMOTION", -104)

# ---------------------------------------------------------------- ЭКРАН ----
if IS_ANDROID:
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
else:
    WIDTH, HEIGHT = 2060, 1040
    _info = pygame.display.Info()
    if _info.current_w > 0 and _info.current_h > 0:
        WIDTH = min(WIDTH, _info.current_w)
        HEIGHT = min(HEIGHT, _info.current_h)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
WIDTH, HEIGHT = screen.get_size()
UI = max(0.6, min(WIDTH, HEIGHT) / 1040)        # масштаб интерфейса
pygame.display.set_caption("Raycasting Minecraft-like (numpy)")

# ---------------------------------------------------------------- КАРТА ----
# 0 - пусто, 1 - камень, 2 - кирпич, 3 - доски, 4 - дверь, 5 - булыжник
grid = np.array([
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,0,0,0,0,0,0,0,0,2,0,0,0,0,0,1],
    [1,0,3,3,0,0,0,0,0,2,0,0,0,3,0,1],
    [1,0,0,0,0,0,0,0,0,2,0,0,0,3,0,1],
    [1,0,0,0,0,0,0,0,0,2,0,0,0,3,0,1],
    [1,0,0,0,4,4,4,0,0,2,0,0,0,3,0,1],
    [1,0,0,0,4,0,4,0,0,2,0,0,0,3,0,1],
    [1,0,0,0,4,4,4,0,0,2,0,0,0,3,0,1],
    [1,0,0,0,2,0,2,0,0,2,0,0,0,3,0,1],
    [1,0,0,0,2,0,2,0,0,2,0,0,0,3,0,1],
    [1,0,0,0,2,0,2,0,0,2,0,0,0,3,0,1],
    [1,0,0,0,2,0,2,0,0,2,0,0,0,3,0,1],
    [1,0,0,0,2,0,2,0,0,2,0,0,0,3,0,1],
    [1,0,0,0,2,0,2,0,0,2,0,0,0,3,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
], dtype=np.int32)
MAP_H, MAP_W = grid.shape

# двери, которые можно открывать (E)
doors = {(x, y) for y in range(MAP_H) for x in range(MAP_W) if grid[y, x] == 4}

# пол: 6 - трава, 7 - доски пола (внутри "домиков")
floor_map = np.full((MAP_H, MAP_W), 6, dtype=np.int32)
floor_map[6, 5] = 7
floor_map[8:14, 5] = 7
floor_map[1:15, 10:13] = 7

# факелы (стоят на полу, светят и отбрасывают тени)
TORCHES = [(5.5, 6.5), (5.5, 12.5), (11.5, 2.5), (11.5, 12.5), (2.5, 4.5), (14.5, 1.5)]

# --------------------------------------------------------------- ИГРОК ----
px, py = 3.5, 3.5
p_angle = 0.0
pitch = 0.0              # вертикальный обзор (в долях высоты экрана)
MOVE_SPEED = 3.0
ROT_SPEED = 2.6
MOUSE_SENS = 0.0025
PLAYER_R = 0.2
REACH = 4.0

FOV = math.radians(66)
PLANE = math.tan(FOV / 2)
MAX_STEPS = MAP_W + MAP_H + 4

# --------------------------------------------------------------- ТЕКСТУРЫ --
TEX = 16
rng = np.random.RandomState(1337)   # есть во всех версиях numpy


def _noise(lo, hi):
    return rng.randint(lo, hi + 1, (TEX, TEX, 1)).astype(np.float32)


def tex_stone():
    t = np.array([125, 125, 128], np.float32) + _noise(-16, 16)
    spots = rng.random_sample((TEX, TEX)) < 0.08
    t[spots] *= 0.75
    return t


def tex_cobble():
    pts = rng.random_sample((11, 2)) * TEX
    yy, xx = np.mgrid[0:TEX, 0:TEX].astype(np.float32)
    # расстояния с учётом тайлинга
    d = np.full((len(pts), TEX, TEX), 1e9, np.float32)
    for i, (cx, cy) in enumerate(pts):
        for ox in (-TEX, 0, TEX):
            for oy in (-TEX, 0, TEX):
                d[i] = np.minimum(d[i], (xx - cx - ox) ** 2 + (yy - cy - oy) ** 2)
    order = np.sort(d, axis=0)
    edge = (np.sqrt(order[1]) - np.sqrt(order[0])) < 1.3
    shade = rng.uniform(0.85, 1.15, len(pts))[np.argmin(d, axis=0)]
    t = np.array([120, 120, 120], np.float32) * shade[..., None] + _noise(-10, 10)
    t[edge] = (70, 70, 72)
    return t


def tex_bricks():
    t = np.zeros((TEX, TEX, 3), np.float32)
    t[:] = (160, 155, 150)                      # раствор
    for row in range(4):
        off = 4 if row % 2 else 0
        for col in range(-1, 3):
            x0 = col * 8 + off
            shade = rng.uniform(0.85, 1.1)
            for y in range(row * 4, row * 4 + 3):
                for x in range(x0, x0 + 7):
                    if 0 <= x < TEX:
                        t[y, x] = np.array((150, 72, 55)) * shade
    t += _noise(-8, 8)
    return t


def tex_planks(vertical=False):
    t = np.zeros((TEX, TEX, 3), np.float32)
    base = np.array((165, 125, 75), np.float32)
    for p in range(4):
        sh = rng.uniform(0.88, 1.08)
        t[p * 4:(p + 1) * 4] = base * sh
        t[p * 4 + 3] = base * 0.6
        seam = rng.randint(0, TEX)
        t[p * 4:p * 4 + 3, seam] = base * 0.7
    t += _noise(-7, 7)
    grain = rng.random_sample((TEX, TEX)) < 0.12
    t[grain] *= 0.88
    if vertical:
        t = t.transpose(1, 0, 2).copy()
    return t


def tex_door():
    t = tex_planks(vertical=True) * 0.8
    t[0, :] = t[-1, :] = t[:, 0] = t[:, -1] = (70, 48, 25)
    t[7:9, 1:15] = (85, 58, 30)
    # окошки
    t[2:6, 3:7] = (150, 190, 210)
    t[2:6, 9:13] = (150, 190, 210)
    t[2, 3:7] = t[2, 9:13] = (200, 230, 240)
    # ручка
    t[10:12, 12] = (200, 200, 190)
    return t


def tex_grass():
    t = np.array([88, 150, 52], np.float32) + _noise(-14, 14)
    light = rng.random_sample((TEX, TEX)) < 0.1
    dark = rng.random_sample((TEX, TEX)) < 0.1
    t[light] *= 1.18
    t[dark] *= 0.8
    return t


def make_torch_frames():
    frames = []
    for f in range(3):
        s = np.zeros((TEX, TEX, 4), np.float32)
        s[7:16, 7:9, :3] = (110, 80, 42)
        s[7:16, 7, :3] = (90, 64, 32)
        s[7:16, 7:9, 3] = 1
        flame = [(6, 7), (6, 8), (5, 7), (5, 8), (4, 7 + (f % 2)), (3, 8 - (f == 2))]
        for i, (y, x) in enumerate(flame):
            col = (255, 250, 200) if i >= 4 else ((255, 210, 80) if i >= 2 else (255, 140, 40))
            s[y, x, :3] = col
            s[y, x, 3] = 1
        frames.append(s)
    return frames


# атлас: индекс = код тайла
atlas = np.zeros((8, TEX, TEX, 3), np.float32)
atlas[1] = tex_stone()
atlas[2] = tex_bricks()
atlas[3] = tex_planks()
atlas[4] = tex_door()
atlas[5] = tex_cobble()
atlas[6] = tex_grass()
atlas[7] = tex_planks()
np.clip(atlas, 0, 255, out=atlas)
TORCH_FRAMES = make_torch_frames()

BLOCK_NAMES = {1: "Камень", 2: "Кирпич", 3: "Доски", 4: "Дверь", 5: "Булыжник"}
HOTBAR = [1, 2, 3, 4, 5]
selected_slot = 2

# ------------------------------------------------------------------ НЕБО ---
SKY_W, SKY_H = 1024, 256


def build_sky(night):
    rows = np.linspace(0, 1, SKY_H, dtype=np.float32)[None, :, None]   # 0 - зенит, 1 - горизонт
    if not night:
        top, hor = np.array((70, 130, 230), np.float32), np.array((185, 215, 245), np.float32)
    else:
        top, hor = np.array((4, 6, 20), np.float32), np.array((22, 28, 58), np.float32)
    sky = top + (hor - top) * rows ** 1.5
    sky = np.repeat(sky, SKY_W, axis=0)
    r = np.random.RandomState(7 if night else 3)
    if not night:
        # блочные облака как в Minecraft
        cells = r.random_sample((SKY_W // 16, 12)) > 0.62
        cells = np.repeat(np.repeat(cells, 16, 0), 8, 1)
        band = slice(SKY_H - 150, SKY_H - 54)
        sky[:, band][cells] = sky[:, band][cells] * 0.25 + np.array((250, 250, 255)) * 0.75
        sky[300:340, 90:130] = (255, 250, 210)     # солнце
        sky[296:344, 86:134] = sky[296:344, 86:134] * 0.5 + np.array((255, 245, 200)) * 0.5
        sky[304:336, 94:126] = (255, 255, 235)
    else:
        stars = r.random_sample((SKY_W, SKY_H)) < 0.004
        stars[:, SKY_H - 25:] = False
        b = r.uniform(140, 255, (SKY_W, SKY_H))
        sky[stars] = b[stars][:, None]
        sky[700:724, 70:94] = (220, 225, 235)      # луна
        sky[706:712, 76:82] = (180, 185, 200)
    return np.clip(sky, 0, 255).astype(np.float32)


SKY_DAY = build_sky(False)
SKY_NIGHT = build_sky(True)
sky_cur = SKY_DAY.copy()
sky_cur_night = 0.0

FOG_DAY = np.array((185, 215, 245), np.float32)
FOG_NIGHT = np.array((14, 18, 36), np.float32)
AMB_DAY = np.array((1.0, 1.0, 0.97), np.float32)
AMB_NIGHT = np.array((0.11, 0.13, 0.25), np.float32)
TORCH_COLOR = np.array((1.35, 0.9, 0.5), np.float32)

night = 0.0            # 0 - день, 1 - ночь (плавно)
night_target = 0.0

# ----------------------------------------------------- КАРТА ОСВЕЩЕНИЯ -----
LM = 8                         # точек карты света на один блок
LMW, LMH = MAP_W * LM, MAP_H * LM
LIGHT_R = 5.5
AO_MAP = np.ones((LMH, LMW), np.float32)
LIGHT_BASES = np.zeros((0, LMH, LMW), np.float32)


def _box3(a):
    p = np.pad(a, 1, mode="edge")
    return (p[:-2, :-2] + p[:-2, 1:-1] + p[:-2, 2:] +
            p[1:-1, :-2] + p[1:-1, 1:-1] + p[1:-1, 2:] +
            p[2:, :-2] + p[2:, 1:-1] + p[2:, 2:]) / 9.0


def _blur_masked(v, m):
    return _box3(v * m) / np.maximum(_box3(m), 1e-6) * (m > 0)


def compute_static_light():
    """Тени факелов + AO. Вызывается только когда карта меняется."""
    global AO_MAP, LIGHT_BASES
    solid = grid != 0
    jj, ii = np.mgrid[0:LMH, 0:LMW]
    wx = ((ii + 0.5) / LM).astype(np.float32)
    wy = ((jj + 0.5) / LM).astype(np.float32)
    cx, cy = ii // LM, jj // LM

    # AO: расстояние до ближайшего твёрдого блока среди соседей
    dmin = np.full((LMH, LMW), 9.0, np.float32)
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            nx = np.clip(cx + ox, 0, MAP_W - 1)
            ny = np.clip(cy + oy, 0, MAP_H - 1)
            ddx = np.maximum(np.maximum(nx - wx, wx - (nx + 1)), 0)
            ddy = np.maximum(np.maximum(ny - wy, wy - (ny + 1)), 0)
            d = np.hypot(ddx, ddy)
            dmin = np.where(solid[ny, nx], np.minimum(dmin, d), dmin)
    a = np.clip(dmin / 0.75, 0, 1)
    AO_MAP = (0.55 + 0.45 * a * a * (3 - 2 * a)).astype(np.float32)

    empty = (~solid[cy, cx]).astype(np.float32)
    steps = 40
    bases = []
    for tx, ty in TORCHES:
        dx, dy = wx - tx, wy - ty
        fall = np.clip(1 - np.hypot(dx, dy) / LIGHT_R, 0, 1) ** 2
        vis = np.ones_like(fall, dtype=bool)
        for k in range(1, steps):
            t = k / steps
            sx = np.clip((tx + dx * t).astype(np.int32), 0, MAP_W - 1)
            sy = np.clip((ty + dy * t).astype(np.int32), 0, MAP_H - 1)
            vis &= ~solid[sy, sx]
        b = fall * vis
        b = _blur_masked(_blur_masked(b, empty), empty)
        bases.append(b.astype(np.float32))
    LIGHT_BASES = np.array(bases, np.float32).reshape(len(bases), LMH, LMW)


# ----------------------------------------------------- РАЗРЕШЕНИЕ РЕНДЕРА --
RENDER_DIV = max(4, round(WIDTH / 400)) if IS_ANDROID else 4
RW = RH = 0
PROJ = 0.0
CAM_X = None
small = None


def setup_resolution(div):
    global RENDER_DIV, RW, RH, PROJ, CAM_X, small, ROW_IDX
    RENDER_DIV = max(2, min(8, div))
    RW, RH = WIDTH // RENDER_DIV, HEIGHT // RENDER_DIV
    PROJ = (RW / 2) / PLANE
    CAM_X = (2 * (np.arange(RW, dtype=np.float32) + 0.5) / RW - 1).astype(np.float32)
    ROW_IDX = np.arange(RH, dtype=np.float32)
    small = pygame.Surface((RW, RH)).convert()


# ------------------------------------------------------------ РЕНДЕР -------
# результат центрального луча (для ломания/постановки блоков)
target = None          # (hit_cell, prev_cell, dist)


def render_world(t):
    global sky_cur, sky_cur_night, target
    dir_x, dir_y = math.cos(p_angle), math.sin(p_angle)
    pl_x, pl_y = -dir_y * PLANE, dir_x * PLANE
    rdx = (dir_x + pl_x * CAM_X).astype(np.float32)
    rdy = (dir_y + pl_y * CAM_X).astype(np.float32)

    horizon = int(RH / 2 + pitch * RH)
    cam_z = 0.5 + math.sin(bob_phase) * 0.018 * bob_amount

    # ---- DDA для всех столбцов сразу ----
    mx = np.full(RW, int(px), np.int32)
    my = np.full(RW, int(py), np.int32)
    with np.errstate(divide="ignore"):
        ddx = np.where(rdx == 0, 1e30, np.abs(1.0 / rdx)).astype(np.float32)
        ddy = np.where(rdy == 0, 1e30, np.abs(1.0 / rdy)).astype(np.float32)
    stx = np.where(rdx < 0, -1, 1).astype(np.int32)
    sty = np.where(rdy < 0, -1, 1).astype(np.int32)
    sdx = np.where(rdx < 0, (px - mx) * ddx, (mx + 1.0 - px) * ddx).astype(np.float32)
    sdy = np.where(rdy < 0, (py - my) * ddy, (my + 1.0 - py) * ddy).astype(np.float32)
    hit = np.zeros(RW, bool)
    side = np.zeros(RW, bool)          # False - грань X, True - грань Y
    tile = np.zeros(RW, np.int32)
    for _ in range(MAX_STEPS):
        act = ~hit
        if not act.any():
            break
        go_x = act & (sdx < sdy)
        go_y = act & ~go_x
        sdx += ddx * go_x
        mx += stx * go_x
        sdy += ddy * go_y
        my += sty * go_y
        side = np.where(go_x, False, np.where(go_y, True, side))
        np.clip(mx, 0, MAP_W - 1, out=mx)
        np.clip(my, 0, MAP_H - 1, out=my)
        cell = grid[my, mx]
        new = act & (cell != 0)
        tile = np.where(new, cell, tile)
        hit |= new

    perp = np.maximum(np.where(side, sdy - ddy, sdx - ddx), 1e-4).astype(np.float32)
    hx = px + rdx * perp
    hy = py + rdy * perp
    wall_x = np.where(side, hx, hy)
    wall_x -= np.floor(wall_x)
    tex_x = np.clip((wall_x * TEX).astype(np.int32), 0, TEX - 1)
    flip = (~side & (rdx > 0)) | (side & (rdy < 0))
    tex_x = np.where(flip, TEX - 1 - tex_x, tex_x)

    # цель под прицелом
    c = RW // 2
    if perp[c] < REACH:
        hit_cell = (int(mx[c]), int(my[c]))
        prev = (hit_cell[0], hit_cell[1] - int(sty[c])) if side[c] else (hit_cell[0] - int(stx[c]), hit_cell[1])
        target = (hit_cell, prev, float(perp[c]))
    else:
        target = None

    # ---- освещение на этот кадр ----
    amb = AMB_DAY + (AMB_NIGHT - AMB_DAY) * night
    fog_col = FOG_DAY + (FOG_NIGHT - FOG_DAY) * night
    fog_start, fog_end = 6.0 - 3.0 * night, 18.0 - 8.0 * night
    flick = np.array([0.88 + 0.08 * math.sin(t * 11 + i * 1.7) + 0.04 * math.sin(t * 27 + i * 3.1)
                      for i in range(len(TORCHES))], np.float32)
    torch_map = np.tensordot(flick, LIGHT_BASES, axes=1) * (0.45 + 0.75 * night)
    floor_light = AO_MAP[..., None] * amb + torch_map[..., None] * TORCH_COLOR

    frame = np.empty((RW, RH, 3), np.float32)

    # ---- небо ----
    sky_rows = min(max(horizon + 1, 0), RH)
    if abs(night - sky_cur_night) > 0.004:
        sky_cur = SKY_DAY + (SKY_NIGHT - SKY_DAY) * night
        sky_cur_night = night
    if sky_rows > 0:
        ang = np.arctan2(rdy, rdx)
        col = ((ang / (2 * math.pi) * SKY_W).astype(np.int32) + int(t * 3)) % SKY_W
        elev = np.arctan((horizon - ROW_IDX[:sky_rows] + 0.5) / PROJ)
        row = np.clip(((1 - elev / (math.pi / 2)) * (SKY_H - 1)).astype(np.int32), 0, SKY_H - 1)
        frame[:, :sky_rows] = sky_cur[col[:, None], row[None, :]]

    # ---- пол ----
    if sky_rows < RH:
        ys = ROW_IDX[sky_rows:]
        rowd = (cam_z * PROJ / (ys - horizon)).astype(np.float32)          # (n,)
        fx = px + rdx[:, None] * rowd[None, :]
        fy = py + rdy[:, None] * rowd[None, :]
        cxi = np.clip(fx.astype(np.int32), 0, MAP_W - 1)
        cyi = np.clip(fy.astype(np.int32), 0, MAP_H - 1)
        txi = (fx * TEX).astype(np.int32) & (TEX - 1)
        tyi = (fy * TEX).astype(np.int32) & (TEX - 1)
        fcol = atlas[floor_map[cyi, cxi], tyi, txi]
        li = np.clip((fx * LM).astype(np.int32), 0, LMW - 1)
        lj = np.clip((fy * LM).astype(np.int32), 0, LMH - 1)
        fcol *= floor_light[lj, li]
        fog = np.clip((rowd - fog_start) / (fog_end - fog_start), 0, 1)[None, :, None]
        frame[:, sky_rows:] = fcol + (fog_col - fcol) * fog

    # ---- стены ----
    line_h = PROJ / perp
    top = horizon - line_h * (1 - cam_z)
    bottom = top + line_h
    y0 = int(max(0, np.floor(top.min())))
    y1 = int(min(RH, np.ceil(bottom.max())))
    if y1 > y0:
        v = (ROW_IDX[None, y0:y1] - top[:, None]) / line_h[:, None]        # (RW, n)
        mask = (v >= 0) & (v < 1)
        tyw = np.clip((v * TEX).astype(np.int32), 0, TEX - 1)
        wcol = atlas[tile[:, None], tyw, tex_x[:, None]]

        # свет в точке попадания (чуть отступив от грани)
        lx = np.where(side, hx, hx - stx * 0.02)
        ly = np.where(side, hy - sty * 0.02, hy)
        li = np.clip((lx * LM).astype(np.int32), 0, LMW - 1)
        lj = np.clip((ly * LM).astype(np.int32), 0, LMH - 1)
        face = np.where(side, 0.78, 1.0).astype(np.float32)[:, None]
        wl = amb[None, :] * face + torch_map[lj, li][:, None] * TORCH_COLOR[None, :]
        # затемнение у пола (контактная тень)
        s = np.clip((v - 0.72) / 0.28, 0, 1)
        ao = 1 - 0.42 * s * s * (3 - 2 * s)
        wcol *= wl[:, None, :] * ao[..., None]

        # рамка выделения блока под прицелом
        if target is not None:
            (tcx, tcy), _, _ = target
            sel = (mx == tcx) & (my == tcy)
            if sel.any():
                edge = (tex_x == 0) | (tex_x == TEX - 1)
                outline = sel[:, None] & (edge[:, None] | (tyw == 0) | (tyw == TEX - 1))
                wcol[sel] *= 1.12
                wcol[outline] *= 0.15

        fog = np.clip((perp - fog_start) / (fog_end - fog_start), 0, 1)[:, None, None]
        wcol += (fog_col - wcol) * fog
        sub = frame[:, y0:y1]
        np.copyto(sub, wcol, where=mask[..., None])

    # ---- спрайты (факелы) ----
    inv = 1.0 / (pl_x * dir_y - dir_x * pl_y)
    order = sorted(range(len(TORCHES)),
                   key=lambda i: -((TORCHES[i][0] - px) ** 2 + (TORCHES[i][1] - py) ** 2))
    spr = TORCH_FRAMES[int(t * 8) % len(TORCH_FRAMES)]
    for i in order:
        tx, ty = TORCHES[i]
        sx, sy = tx - px, ty - py
        trx = inv * (dir_y * sx - dir_x * sy)
        depth = inv * (-pl_y * sx + pl_x * sy)
        if depth < 0.15:
            continue
        scr_x = (RW / 2) * (1 + trx / depth)
        size = PROJ * 0.55 / depth
        bot = horizon + PROJ * cam_z / depth
        top_s = bot - size
        left = scr_x - size / 2
        fog = min(1.0, max(0.0, (depth - fog_start) / (fog_end - fog_start)))

        # ореол (аддитивно)
        glow = 0.25 + 0.75 * night
        gr = size * 1.6
        gcx, gcy = scr_x, top_s + size * 0.3
        gx0, gx1 = max(0, int(gcx - gr)), min(RW, int(gcx + gr) + 1)
        gy0, gy1 = max(0, int(gcy - gr)), min(RH, int(gcy + gr) + 1)
        if gx1 > gx0 and gy1 > gy0:
            gxs = (np.arange(gx0, gx1, dtype=np.float32) - gcx) / gr
            gys = (np.arange(gy0, gy1, dtype=np.float32) - gcy) / gr
            g = np.clip(1 - np.sqrt(gxs[:, None] ** 2 + gys[None, :] ** 2), 0, 1) ** 2
            g *= (perp[gx0:gx1, None] > depth - 0.3) * (glow * flick[i] * 70 * (1 - fog))
            frame[gx0:gx1, gy0:gy1] += g[..., None] * TORCH_COLOR

        x0, x1 = max(0, int(left)), min(RW, int(left + size) + 1)
        y0s, y1s = max(0, int(top_s)), min(RH, int(bot) + 1)
        if x0 >= x1 or y0s >= y1s:
            continue
        u = np.clip(((np.arange(x0, x1) - left) / size * TEX).astype(np.int32), 0, TEX - 1)
        vv = np.clip(((np.arange(y0s, y1s) - top_s) / size * TEX).astype(np.int32), 0, TEX - 1)
        smp = spr[vv[None, :], u[:, None]]                                 # (nx, ny, 4)
        vis = (smp[..., 3] > 0) & (perp[x0:x1, None] > depth)
        col = smp[..., :3] + (fog_col - smp[..., :3]) * fog
        region = frame[x0:x1, y0s:y1s]
        region[vis] = col[vis]

    np.clip(frame, 0, 255, out=frame)
    pygame.surfarray.blit_array(small, frame.astype(np.uint8))
    pygame.transform.scale(small, (WIDTH, HEIGHT), screen)


# -------------------------------------------------------- ИКОНКИ БЛОКОВ ----
def make_block_icon(tile_id, size):
    """Изометрический кубик из текстуры (для хотбара и руки)."""
    S = size
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) + 0.5
    a = S / 2
    c30 = math.cos(math.radians(30))
    X = np.array((a * c30, a * 0.5))
    Y = np.array((-a * c30, a * 0.5))
    Zd = np.array((0.0, a))
    o_top = np.array((S / 2, 0.0))
    out = np.zeros((S, S, 4), np.float32)
    tex = atlas[tile_id]
    faces = [(o_top, X, Y, 1.0), (o_top + X, Y, Zd, 0.62), (o_top + Y, X, Zd, 0.8)]
    for o, A, B, shade in faces:
        det = A[0] * B[1] - A[1] * B[0]
        dx, dy = xx - o[0], yy - o[1]
        s = (dx * B[1] - dy * B[0]) / det
        tt = (A[0] * dy - A[1] * dx) / det
        m = (s >= 0) & (s < 1) & (tt >= 0) & (tt < 1)
        u = np.clip((s * TEX).astype(int), 0, TEX - 1)
        v = np.clip((tt * TEX).astype(int), 0, TEX - 1)
        out[m, :3] = tex[v[m], u[m]] * shade
        out[m, 3] = 255
    arr = np.ascontiguousarray(np.clip(out, 0, 255).astype(np.uint8))
    return pygame.image.frombuffer(arr.tobytes(), (S, S), "RGBA").convert_alpha()


ICON_SMALL = {b: make_block_icon(b, int(48 * UI)) for b in HOTBAR}
ICON_HAND = {b: make_block_icon(b, int(220 * UI)) for b in HOTBAR}

# ---------------------------------------------------------- TOUCH-КНОПКИ ---
def rrect(surf, color, rect, width=0, radius=0):
    try:
        pygame.draw.rect(surf, color, rect, width, border_radius=radius)
    except TypeError:                     # старый pygame без border_radius
        pygame.draw.rect(surf, color, rect, width)


class TouchButton:
    def __init__(self, rect, label):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.pointers = set()           # id пальцев/мыши, держащих кнопку
        self.surf_up = self._make(False)
        self.surf_down = self._make(True)

    def _make(self, down):
        s = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        rrect(s, (255, 255, 255, 150 if down else 70), s.get_rect(), 0, 14)
        rrect(s, (255, 255, 255, 200), s.get_rect(), 2, 14)
        txt = btn_font.render(self.label, True, (20, 20, 20) if down else (255, 255, 255))
        s.blit(txt, txt.get_rect(center=s.get_rect().center))
        return s

    @property
    def active(self):
        return bool(self.pointers)

    def press(self, pid, pos):
        if self.rect.collidepoint(pos):
            self.pointers.add(pid)
            return True
        return False

    def move(self, pid, pos):
        if self.rect.collidepoint(pos):
            self.pointers.add(pid)       # можно "въехать" пальцем на кнопку
        else:
            self.pointers.discard(pid)

    def release(self, pid):
        self.pointers.discard(pid)

    def draw(self, surface):
        surface.blit(self.surf_down if self.active else self.surf_up, self.rect)


btn_font = pygame.font.SysFont(None, int(40 * UI))
font = pygame.font.SysFont(None, max(18, int(26 * UI)))
big_font = pygame.font.SysFont(None, int(34 * UI))

BS, PAD = int(80 * UI * (1.4 if IS_ANDROID else 1)), int(20 * UI)
mcx, mcy = PAD + BS + 8, HEIGHT - BS - PAD
rcx, rcy = WIDTH - PAD - 2 * BS - 8, HEIGHT - BS - PAD
buttons = {
    "F": TouchButton((mcx, mcy - BS - 8, BS, BS), "W"),
    "B": TouchButton((mcx, mcy, BS, BS), "S"),
    "L": TouchButton((mcx - BS - 8, mcy, BS, BS), "A"),
    "R": TouchButton((mcx + BS + 8, mcy, BS, BS), "D"),
    "<": TouchButton((rcx - BS - 8, rcy, BS, BS), "<"),
    ">": TouchButton((rcx + BS + 8, rcy, BS, BS), ">"),
    "E": TouchButton((rcx, rcy - BS - 8, BS, BS), "E"),
    "X": TouchButton((rcx - BS - 8, rcy - BS - 8, BS, BS), "X"),
    "P": TouchButton((rcx + BS + 8, rcy - BS - 8, BS, BS), "+"),
}
show_buttons = True

SLOT = int(64 * UI)
hotbar_rect = pygame.Rect(0, 0, SLOT * len(HOTBAR) + 8, SLOT + 8)
hotbar_rect.midbottom = (WIDTH // 2, HEIGHT - 14)


def hotbar_slot_at(pos):
    if hotbar_rect.collidepoint(pos):
        return min(len(HOTBAR) - 1, (pos[0] - hotbar_rect.x - 4) // SLOT)
    return None


# -------------------------------------------------------------- МИНИКАРТА --
MM_SCALE = max(5, int(10 * UI))
minimap = None


def build_minimap():
    global minimap
    minimap = pygame.Surface((MAP_W * MM_SCALE, MAP_H * MM_SCALE), pygame.SRCALPHA)
    minimap.fill((0, 0, 0, 120))
    for y in range(MAP_H):
        for x in range(MAP_W):
            tid = grid[y, x] if grid[y, x] else floor_map[y, x]
            col = atlas[tid].mean(axis=(0, 1)).astype(int)
            if grid[y, x] == 0:
                col = col * 0.55
            r = (x * MM_SCALE, y * MM_SCALE, MM_SCALE, MM_SCALE)
            pygame.draw.rect(minimap, (*[int(c) for c in col], 230), r)
    for tx, ty in TORCHES:
        pygame.draw.circle(minimap, (255, 200, 80), (int(tx * MM_SCALE), int(ty * MM_SCALE)), 3)


def draw_minimap():
    ox, oy = WIDTH - minimap.get_width() - 12, 12
    screen.blit(minimap, (ox, oy))
    cx, cy = ox + px * MM_SCALE, oy + py * MM_SCALE
    for a in (p_angle - FOV / 2, p_angle + FOV / 2):
        pygame.draw.line(screen, (255, 255, 255), (cx, cy),
                         (cx + math.cos(a) * 30, cy + math.sin(a) * 30), 1)
    pygame.draw.circle(screen, (255, 60, 60), (int(cx), int(cy)), 4)


# ---------------------------------------------------------------- ЛОГИКА ---
def solid_at(x, y):
    ix, iy = int(math.floor(x)), int(math.floor(y))
    if ix < 0 or iy < 0 or ix >= MAP_W or iy >= MAP_H:
        return True
    return grid[iy, ix] != 0


def free_at(x, y):
    r = PLAYER_R
    return not (solid_at(x - r, y - r) or solid_at(x + r, y - r) or
                solid_at(x - r, y + r) or solid_at(x + r, y + r))


def cell_hits_player(cx, cy):
    nx = min(max(px, cx), cx + 1)
    ny = min(max(py, cy), cy + 1)
    return (nx - px) ** 2 + (ny - py) ** 2 < (PLAYER_R + 0.02) ** 2


def map_changed():
    compute_static_light()
    build_minimap()


def break_block():
    global hand_swing
    hand_swing = 1.0
    if target is None:
        return
    (cx, cy), _, _ = target
    if 0 < cx < MAP_W - 1 and 0 < cy < MAP_H - 1:
        grid[cy, cx] = 0
        doors.discard((cx, cy))
        map_changed()


def place_block():
    global hand_swing
    hand_swing = 1.0
    if target is None:
        return
    _, (cx, cy), _ = target
    if not (0 <= cx < MAP_W and 0 <= cy < MAP_H) or grid[cy, cx] != 0:
        return
    if cell_hits_player(cx, cy):
        return
    if any(int(tx) == cx and int(ty) == cy for tx, ty in TORCHES):
        return
    b = HOTBAR[selected_slot]
    grid[cy, cx] = b
    if b == 4:
        doors.add((cx, cy))
    map_changed()


def toggle_door():
    # закрытая дверь под прицелом -> открыть
    if target is not None and target[0] in doors and grid[target[0][1], target[0][0]] == 4:
        cx, cy = target[0]
        grid[cy, cx] = 0
        map_changed()
        return
    # иначе ищем открытую дверь по направлению взгляда -> закрыть
    ca, sa = math.cos(p_angle), math.sin(p_angle)
    d = 0.4
    while d < 2.5:
        cx, cy = int(px + ca * d), int(py + sa * d)
        if (cx, cy) in doors and grid[cy, cx] == 0:
            if not cell_hits_player(cx, cy):
                grid[cy, cx] = 4
                map_changed()
            return
        if solid_at(px + ca * d, py + sa * d):
            return
        d += 0.2


# --------------------------------------------------------------- HUD -------
def draw_crosshair():
    cx, cy = WIDTH // 2, HEIGHT // 2
    for w, col in ((5, (0, 0, 0)), (2, (255, 255, 255))):
        pygame.draw.line(screen, col, (cx - 12, cy), (cx + 12, cy), w)
        pygame.draw.line(screen, col, (cx, cy - 12), (cx, cy + 12), w)


def draw_hotbar():
    s = pygame.Surface(hotbar_rect.size, pygame.SRCALPHA)
    s.fill((0, 0, 0, 130))
    screen.blit(s, hotbar_rect)
    for i, b in enumerate(HOTBAR):
        r = pygame.Rect(hotbar_rect.x + 4 + i * SLOT, hotbar_rect.y + 4, SLOT, SLOT)
        pygame.draw.rect(screen, (140, 140, 140), r, 2)
        screen.blit(ICON_SMALL[b], ICON_SMALL[b].get_rect(center=r.center))
        if i == selected_slot:
            pygame.draw.rect(screen, (255, 255, 255), r.inflate(6, 6), 4)
    name = big_font.render(BLOCK_NAMES[HOTBAR[selected_slot]], True, (255, 255, 255))
    screen.blit(name, name.get_rect(midbottom=(hotbar_rect.centerx, hotbar_rect.y - 8)))


def draw_hand():
    icon = ICON_HAND[HOTBAR[selected_slot]]
    bx = math.cos(bob_phase * 0.5) * 14 * bob_amount
    by = abs(math.sin(bob_phase * 0.5)) * 14 * bob_amount
    sw = math.sin(hand_swing * math.pi)
    x = WIDTH - icon.get_width() - 230 * UI + bx - sw * 60 * UI
    y = HEIGHT - icon.get_height() * 0.72 + by + sw * 40
    # тень от освещения: ночью рука темнее
    k = 1.0 - 0.6 * night
    if k < 0.999:
        icon = icon.copy()
        icon.fill((int(255 * k),) * 3 + (255,), special_flags=pygame.BLEND_RGBA_MULT)
    screen.blit(icon, (x, y))


HELP = [
    "WASD - ходьба   стрелки - поворот   M - обзор мышью",
    "ЛКМ / X - сломать   ПКМ / + - поставить   1-5, колесо - блок",
    "E - дверь   N - день/ночь   +/- качество   H - кнопки   F3 - отладка",
]
help_surfs = [font.render(line, True, (255, 255, 255)) for line in HELP]


# ------------------------------------------------------------ ОСНОВНОЙ ЦИКЛ -
bob_phase = 0.0
bob_amount = 0.0
hand_swing = 0.0


def main():
    global px, py, p_angle, pitch, night, night_target, selected_slot
    global bob_phase, bob_amount, hand_swing, show_buttons

    setup_resolution(RENDER_DIV)
    map_changed()

    clock = pygame.time.Clock()
    keys_held = set()
    mouse_look = False
    show_debug = True
    fps_surf = None
    fps_timer = 0.0
    t = 0.0
    prev_use = False
    touch_used = False        # после первого касания игнорируем "мышь" из касаний
    perf_t, perf_n, auto_res = 0.0, 0, True

    def set_mouse_look(on):
        nonlocal mouse_look
        mouse_look = on
        pygame.event.set_grab(on)
        pygame.mouse.set_visible(not on)
        pygame.mouse.get_rel()

    running = True
    while running:
        raw_dt = clock.tick(120) / 1000.0
        dt = min(raw_dt, 0.05)
        t += dt

        # авто-качество: если долго < 25 FPS, уменьшаем разрешение рендера
        if auto_res and t > 1.5:
            perf_t += raw_dt
            perf_n += 1
            if perf_t > 2.0:
                if perf_t / perf_n > 1 / 25 and RENDER_DIV < 8:
                    setup_resolution(RENDER_DIV + 1)
                perf_t, perf_n = 0.0, 0

        for event in pygame.event.get():
            if event.type == QUIT:
                running = False

            elif event.type == KEYDOWN:
                keys_held.add(event.key)
                if event.key == K_ESCAPE:
                    if mouse_look:
                        set_mouse_look(False)
                    else:
                        running = False
                elif event.key == K_m:
                    set_mouse_look(not mouse_look)
                elif event.key == K_n:
                    night_target = 1.0 - night_target
                elif event.key in (K_EQUALS, K_PLUS, K_KP_PLUS):
                    auto_res = False
                    setup_resolution(RENDER_DIV - 1)
                elif event.key in (K_MINUS, K_KP_MINUS):
                    auto_res = False
                    setup_resolution(RENDER_DIV + 1)
                elif event.key == K_h:
                    show_buttons = not show_buttons
                elif event.key == K_F3:
                    show_debug = not show_debug
                elif event.key == K_q:
                    break_block()
                elif event.key == K_f:
                    place_block()
                elif K_1 <= event.key <= K_9 and event.key - K_1 < len(HOTBAR):
                    selected_slot = event.key - K_1
            elif event.type == KEYUP:
                keys_held.discard(event.key)

            # мышь (события, эмулированные из касаний, пропускаем)
            elif event.type == MOUSEBUTTONDOWN and not (touch_used or getattr(event, "touch", False)):
                if event.button in (4, 5):
                    continue
                if mouse_look:
                    if event.button == 1:
                        break_block()
                    elif event.button == 3:
                        place_block()
                    continue
                slot = hotbar_slot_at(event.pos)
                if slot is not None:
                    selected_slot = slot
                elif not (show_buttons and any(b.press("mouse", event.pos) for b in buttons.values())):
                    if event.button == 1:
                        break_block()
                    elif event.button == 3:
                        place_block()
            elif event.type == MOUSEBUTTONUP and not (touch_used or getattr(event, "touch", False)):
                for b in buttons.values():
                    b.release("mouse")
            elif event.type == MOUSEMOTION and not (touch_used or getattr(event, "touch", False)):
                if mouse_look:
                    p_angle += event.rel[0] * MOUSE_SENS
                    pitch = max(-0.45, min(0.45, pitch - event.rel[1] * MOUSE_SENS * 0.8))
                elif event.buttons[0]:
                    for b in buttons.values():
                        if "mouse" in b.pointers:
                            b.move("mouse", event.pos)
            elif event.type == EV_MOUSEWHEEL:
                selected_slot = (selected_slot - event.y) % len(HOTBAR)

            # мультитач
            elif event.type in (EV_FINGERDOWN, EV_FINGERMOTION, EV_FINGERUP):
                pos = (int(event.x * WIDTH), int(event.y * HEIGHT))
                pid = ("finger", event.finger_id)
                touch_used = True
                if event.type == EV_FINGERDOWN:
                    slot = hotbar_slot_at(pos)
                    if slot is not None:
                        selected_slot = slot
                    for b in buttons.values():
                        b.press(pid, pos)
                elif event.type == EV_FINGERMOTION:
                    for b in buttons.values():
                        b.move(pid, pos)
                else:
                    for b in buttons.values():
                        b.release(pid)

        def held(*ks):
            return any(k in keys_held for k in ks)

        fwd = held(K_w, K_UP) or buttons["F"].active
        back = held(K_s, K_DOWN) or buttons["B"].active
        left = held(K_a) or buttons["L"].active
        right = held(K_d) or buttons["R"].active
        rot_l = held(K_LEFT) or buttons["<"].active
        rot_r = held(K_RIGHT) or buttons[">"].active
        use = held(K_e) or buttons["E"].active

        # кнопки X / + на сенсоре — по нажатию
        for key, fn in (("X", break_block), ("P", place_block)):
            b = buttons[key]
            was = getattr(b, "_was", False)
            if b.active and not was:
                fn()
            b._was = b.active

        if rot_l:
            p_angle -= ROT_SPEED * dt
        if rot_r:
            p_angle += ROT_SPEED * dt
        p_angle %= 2 * math.pi

        ca, sa = math.cos(p_angle), math.sin(p_angle)
        mvx = mvy = 0.0
        if fwd:
            mvx += ca; mvy += sa
        if back:
            mvx -= ca; mvy -= sa
        if left:
            mvx += sa; mvy -= ca
        if right:
            mvx -= sa; mvy += ca
        ln = math.hypot(mvx, mvy)
        moving = ln > 0
        if moving:
            k = MOVE_SPEED * dt / ln            # диагональ не быстрее прямой
            nx, ny = px + mvx * k, py + mvy * k
            if free_at(nx, py):
                px = nx
            if free_at(px, ny):
                py = ny
            bob_phase += dt * 11
        bob_amount += ((1.0 if moving else 0.0) - bob_amount) * min(1, dt * 8)
        hand_swing = max(0.0, hand_swing - dt * 4)
        night += (night_target - night) * min(1, dt * 1.5)

        if use and not prev_use:
            toggle_door()
        prev_use = use

        render_world(t)

        draw_crosshair()
        draw_hand()
        draw_hotbar()
        draw_minimap()

        fps_timer -= dt
        if fps_timer <= 0:
            fps_timer = 0.25
            info = (f"FPS {clock.get_fps():.0f}   рендер {RW}x{RH}   "
                    f"x={px:.2f} y={py:.2f} угол={math.degrees(p_angle):.0f}")
            fps_surf = font.render(info, True, (255, 255, 255))
        if show_debug and fps_surf:
            screen.blit(fps_surf, (12, 10))
            for i, s in enumerate(help_surfs):
                screen.blit(s, (12, 38 + i * 24))

        if show_buttons:
            for b in buttons.values():
                b.draw(screen)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        show_error(traceback.format_exc())
