"""
Кубоземье — воксельная песочница на Python (pygame + numpy).

Настоящий 3D-мир из кубиков: холмы, деревья, пещеры. Можно ходить,
прыгать, летать, ломать и ставить блоки в любом направлении.
Рендер — векторизованный 3D-рейкастинг (numpy), работает и на телефоне
(Pydroid 3).

Телефон:
  левая половина экрана — джойстик (ходьба)
  правая половина — провести пальцем: осмотреться
                    коротко коснуться: сломать блок
                    подержать палец: поставить блок
  кнопка со стрелкой — прыжок (в полёте — вверх), рядом — полёт и вниз
  хотбар внизу — выбор блока

Компьютер:
  клик — захватить мышь, Esc — отпустить
  WASD — ходьба, Пробел — прыжок / вверх, Shift — вниз (в полёте)
  F — полёт, ЛКМ — сломать, ПКМ — поставить, 1-9 / колесо — блок
  +/- — качество, F3 — отладка
"""
import math
import os
import sys
import time
import traceback

# ---------------------------------------------------- ПОКАЗ ОШИБОК --------
try:
    _ERR_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voxel_error.txt")
except Exception:
    _ERR_FILE = "voxel_error.txt"


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
        fnt = pg.font.SysFont(None, max(16, h // 28))
        lines = ["ОШИБКА (коснитесь экрана, чтобы выйти):", ""]
        for line in text.splitlines():
            while len(line) > 70:
                lines.append(line[:70])
                line = "  " + line[70:]
            lines.append(line)
        scr.fill((25, 0, 0))
        y = 6
        for line in lines[-(h // fnt.get_linesize()):]:
            scr.blit(fnt.render(line, True, (255, 220, 220)), (6, y))
            y += fnt.get_linesize()
        pg.display.flip()
        while True:
            e = pg.event.wait()
            if e.type in (pg.QUIT, pg.KEYDOWN, pg.MOUSEBUTTONDOWN):
                break
        pg.quit()
    except Exception:
        pass


sys.excepthook = lambda tp, val, tb: show_error("".join(traceback.format_exception(tp, val, tb)))

try:
    import numpy as np
except ImportError:
    show_error("Не установлен numpy.\n\nPydroid 3: меню -> Pip -> numpy -> Install\nПК: pip install numpy")
    sys.exit(1)

IS_ANDROID = hasattr(sys, "getandroidapilevel") or "ANDROID_ROOT" in os.environ
if IS_ANDROID:
    os.environ.setdefault("SDL_IOS_ORIENTATIONS", "LandscapeLeft LandscapeRight")

import pygame
from pygame.locals import *

pygame.init()

EV_MOUSEWHEEL = getattr(pygame, "MOUSEWHEEL", -101)
EV_FINGERDOWN = getattr(pygame, "FINGERDOWN", -102)
EV_FINGERUP = getattr(pygame, "FINGERUP", -103)
EV_FINGERMOTION = getattr(pygame, "FINGERMOTION", -104)

# ---------------------------------------------------------------- ЭКРАН ----
MOBILE = IS_ANDROID or os.environ.get("VOXEL_MOBILE") == "1"
screen = None
if MOBILE:
    _info = pygame.display.Info()
    _pw, _ph = max(_info.current_w, 1), max(_info.current_h, 1)
    if _ph > _pw:
        _pw, _ph = _ph, _pw
    _lh = 432
    _lw = max(640, int(_lh * _pw / _ph))
    try:
        screen = pygame.display.set_mode((_lw, _lh), pygame.SCALED | pygame.FULLSCREEN)
    except Exception:
        screen = None
    if screen is None:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
else:
    _w, _h = 1600, 900
    _info = pygame.display.Info()
    if _info.current_w > 0 and _info.current_h > 0:
        _w, _h = min(_w, _info.current_w), min(_h, _info.current_h - 60)
    screen = pygame.display.set_mode((_w, _h))
WIDTH, HEIGHT = screen.get_size()
UI = max(0.4, HEIGHT / 900)
pygame.display.set_caption("Кубоземье")

# --------------------------------------------------------------- БЛОКИ -----
AIR, GRASS, DIRT, STONE, COBBLE, PLANKS, LOG, LEAVES, SAND, BRICKS, BEDROCK = range(11)
OUTSIDE = 255                       # граница мира (рамка вокруг массива)
BLOCK_NAMES = {GRASS: "Трава", DIRT: "Земля", STONE: "Камень", COBBLE: "Булыжник",
               PLANKS: "Доски", LOG: "Бревно", LEAVES: "Листва", SAND: "Песок",
               BRICKS: "Кирпич", BEDROCK: "Коренная порода"}
HOTBAR = [GRASS, DIRT, STONE, COBBLE, PLANKS, LOG, LEAVES, SAND, BRICKS]

# --------------------------------------------------------------- ТЕКСТУРЫ --
TEX = 16
rng = np.random.RandomState(2024)


def _n(lo, hi):
    return rng.randint(lo, hi + 1, (TEX, TEX, 1)).astype(np.float32)


def _speck(t, p, k):
    m = rng.random_sample((TEX, TEX)) < p
    t[m] *= k
    return t


def t_grass_top():
    t = np.array((92, 152, 58), np.float32) + _n(-16, 16)
    _speck(t, 0.12, 0.82)
    return _speck(t, 0.08, 1.15)


def t_dirt():
    t = np.array((132, 94, 64), np.float32) + _n(-12, 12)
    _speck(t, 0.1, 0.78)
    return _speck(t, 0.06, 1.2)


def t_grass_side():
    t = t_dirt()
    top = t_grass_top()
    for x in range(TEX):
        h = 3 + rng.randint(0, 3) - (1 if rng.random_sample() < 0.2 else 0)
        t[:h, x] = top[:h, x]
    return t


def t_stone():
    t = np.array((126, 126, 128), np.float32) + _n(-12, 12)
    for _ in range(5):                      # тёмные прожилки
        x, y = rng.randint(0, TEX, 2)
        for i in range(rng.randint(2, 5)):
            t[(y) % TEX, (x + i) % TEX] *= 0.78
    return t


def t_cobble():
    pts = rng.random_sample((11, 2)) * TEX
    yy, xx = np.mgrid[0:TEX, 0:TEX].astype(np.float32)
    d = np.full((len(pts), TEX, TEX), 1e9, np.float32)
    for i, (cx, cy) in enumerate(pts):
        for ox in (-TEX, 0, TEX):
            for oy in (-TEX, 0, TEX):
                d[i] = np.minimum(d[i], (xx - cx - ox) ** 2 + (yy - cy - oy) ** 2)
    srt = np.sort(d, axis=0)
    edge = (np.sqrt(srt[1]) - np.sqrt(srt[0])) < 1.3
    shade = rng.uniform(0.82, 1.15, len(pts))[np.argmin(d, axis=0)]
    t = np.array((122, 122, 122), np.float32) * shade[..., None] + _n(-8, 8)
    t[edge] = (68, 68, 70)
    return t


def t_planks():
    t = np.zeros((TEX, TEX, 3), np.float32)
    base = np.array((168, 128, 78), np.float32)
    for p in range(4):
        t[p * 4:(p + 1) * 4] = base * rng.uniform(0.88, 1.08)
        t[p * 4 + 3] = base * 0.6
        t[p * 4:p * 4 + 3, rng.randint(0, TEX)] = base * 0.7
    t += _n(-6, 6)
    return _speck(t, 0.1, 0.88)


def t_log_side():
    t = np.zeros((TEX, TEX, 3), np.float32)
    for x in range(TEX):
        t[:, x] = np.array((104, 78, 48)) * rng.uniform(0.75, 1.12)
    t += _n(-8, 8)
    for _ in range(6):
        x, y = rng.randint(0, TEX, 2)
        t[y:y + rng.randint(2, 5), x] *= 0.7
    return t


def t_log_top():
    yy, xx = np.mgrid[0:TEX, 0:TEX].astype(np.float32)
    r = np.maximum(np.abs(xx - 7.5), np.abs(yy - 7.5))
    ring = (r.astype(int) % 2 == 0)
    t = np.where(ring[..., None], np.array((172, 136, 86), np.float32),
                 np.array((146, 110, 64), np.float32)).astype(np.float32)
    t[r >= 6.5] = (100, 76, 46)
    return t + _n(-6, 6)


def t_leaves():
    t = np.array((58, 122, 44), np.float32) + _n(-22, 22)
    m = rng.random_sample((TEX, TEX)) < 0.22
    t[m] = (34, 74, 28)
    return _speck(t, 0.1, 1.2)


def t_sand():
    t = np.array((216, 203, 148), np.float32) + _n(-9, 9)
    return _speck(t, 0.08, 0.9)


def t_bricks():
    t = np.zeros((TEX, TEX, 3), np.float32)
    t[:] = (162, 156, 150)
    for row in range(4):
        off = 4 if row % 2 else 0
        for col in range(-1, 3):
            x0 = col * 8 + off
            c = np.array((150, 72, 55)) * rng.uniform(0.85, 1.1)
            for x in range(max(0, x0), min(TEX, x0 + 7)):
                t[row * 4:row * 4 + 3, x] = c
    return t + _n(-7, 7)


def t_bedrock():
    t = np.array((70, 70, 72), np.float32) + _n(-40, 40)
    return t


TEX_LIST = [t_grass_top(), t_grass_side(), t_dirt(), t_stone(), t_cobble(), t_planks(),
            t_log_side(), t_log_top(), t_leaves(), t_sand(), t_bricks(), t_bedrock()]
(TX_GRASS_TOP, TX_GRASS_SIDE, TX_DIRT, TX_STONE, TX_COBBLE, TX_PLANKS,
 TX_LOG_SIDE, TX_LOG_TOP, TX_LEAVES, TX_SAND, TX_BRICKS, TX_BEDROCK) = range(12)
atlas = np.clip(np.array(TEX_LIST, np.float32), 0, 255)

# текстура грани: [блок, вид грани] вид: 0 - верх, 1 - бок, 2 - низ
FACE_TEX = np.zeros((256, 3), np.int32)
for _b, (_t, _s, _d) in {
    GRASS: (TX_GRASS_TOP, TX_GRASS_SIDE, TX_DIRT), DIRT: (TX_DIRT,) * 3, STONE: (TX_STONE,) * 3,
    COBBLE: (TX_COBBLE,) * 3, PLANKS: (TX_PLANKS,) * 3, LOG: (TX_LOG_TOP, TX_LOG_SIDE, TX_LOG_TOP),
    LEAVES: (TX_LEAVES,) * 3, SAND: (TX_SAND,) * 3, BRICKS: (TX_BRICKS,) * 3,
    BEDROCK: (TX_BEDROCK,) * 3,
}.items():
    FACE_TEX[_b] = (_t, _s, _d)

# ------------------------------------------------------------------- МИР ---
SX, SY, SZ = 64, 32, 64            # размер мира (x, высота, z)
# массив с рамкой в 1 блок: лучи, вылетевшие из мира, упираются в OUTSIDE
world_p = np.zeros((SX + 2, SY + 2, SZ + 2), np.uint8)
world_p[0, :, :] = world_p[-1, :, :] = OUTSIDE
world_p[:, 0, :] = world_p[:, -1, :] = OUTSIDE
world_p[:, :, 0] = world_p[:, :, -1] = OUTSIDE
world = world_p[1:-1, 1:-1, 1:-1]   # вид без рамки: world[x, y, z]
WF = world_p.reshape(-1)            # плоский вид для лучей
STR_X, STR_Y = (SY + 2) * (SZ + 2), SZ + 2
SEA = 9


def _smooth(shape, cell, seed):
    r = np.random.RandomState(seed)
    gs = [s // cell + 2 for s in shape]
    g = r.random_sample(gs).astype(np.float32)
    out = g
    for ax, s in enumerate(shape):
        p = (np.arange(s) + 0.5) / cell
        i0 = np.floor(p).astype(int)
        f = p - i0
        f = f * f * (3 - 2 * f)
        a = np.take(out, i0, axis=ax)
        b = np.take(out, i0 + 1, axis=ax)
        sh = [1] * len(shape)
        sh[ax] = s
        f = f.reshape(sh)
        out = a * (1 - f) + b * f
    return out


def generate_world(seed=7):
    world[:] = AIR
    h = (5 + 13 * _smooth((SX, SZ), 16, seed) + 5 * _smooth((SX, SZ), 7, seed + 1)
         + 1.5 * _smooth((SX, SZ), 3, seed + 2)).astype(int)
    h = np.clip(h, 3, SY - 8)
    ys = np.arange(SY)[None, :, None]
    hh = h[:, None, :]
    world[(ys < hh - 3)] = STONE
    dirt = (ys >= hh - 3) & (ys < hh - 1)
    world[dirt] = DIRT
    top = ys == hh - 1
    world[top & (hh - 1 <= SEA)] = SAND
    world[top & (hh - 1 > SEA)] = GRASS
    world[dirt & (hh - 1 <= SEA)] = SAND
    # пещеры
    cav = _smooth((SX, SY, SZ), 6, seed + 3) * 0.7 + _smooth((SX, SY, SZ), 3, seed + 4) * 0.3
    carve = (cav > 0.66) & (ys > 1) & (ys < hh - 2)
    world[carve] = AIR
    world[:, 0, :] = BEDROCK
    # деревья
    r = np.random.RandomState(seed + 5)
    for _ in range(70):
        x, z = r.randint(3, SX - 3), r.randint(3, SZ - 3)
        y = h[x, z]
        if world[x, y - 1, z] != GRASS or y + 7 >= SY:
            continue
        if (world[x - 2:x + 3, y:y + 6, z - 2:z + 3] != AIR).any():
            continue
        th = r.randint(4, 6)
        for dy in range(-2, 2):
            rad = 2 if dy < 0 else 1
            for dx in range(-rad, rad + 1):
                for dz in range(-rad, rad + 1):
                    if abs(dx) == rad and abs(dz) == rad and (dy == 1 or r.random_sample() < 0.5):
                        continue
                    world[x + dx, y + th + dy, z + dz] = LEAVES
        world[x, y + th + 1, z] = LEAVES
        world[x, y:y + th, z] = LOG
    return h


generate_world()
# высота "неба" над колонкой: всё, что ниже — в тени (пещеры, под деревьями)
SKYTOP = np.zeros((SX + 2, SZ + 2), np.int32)


def update_skytop(x0=0, x1=SX, z0=0, z1=SZ):
    sub = world[x0:x1, :, z0:z1] != AIR
    any_ = sub.any(axis=1)
    top = SY - np.argmax(sub[:, ::-1, :], axis=1)
    SKYTOP[x0 + 1:x1 + 1, z0 + 1:z1 + 1] = np.where(any_, top, 0)


update_skytop()


def get_block(x, y, z):
    if 0 <= x < SX and 0 <= y < SY and 0 <= z < SZ:
        return int(world[x, y, z])
    return OUTSIDE if y < SY else AIR


def set_block(x, y, z, b):
    world[x, y, z] = b
    update_skytop(x, x + 1, z, z + 1)


# ---------------------------------------------------------------- ИГРОК ----
spawn_x, spawn_z = SX // 2 + 0.5, SZ // 2 + 0.5
pos = [spawn_x, float(SKYTOP[int(spawn_x) + 1, int(spawn_z) + 1]) + 0.01, spawn_z]
vel_y = 0.0
yaw, pitch = 0.6, -0.15
on_ground = False
flying = False
EYE = 1.62
PW, PH = 0.3, 1.8
WALK, FLY_SPEED = 4.3, 9.0
GRAVITY, JUMP_V = 26.0, 8.4
REACH = 5.0
FOV = math.radians(75)

# --------------------------------------------------- РАЗРЕШЕНИЕ РЕНДЕРА ----
RENDER_DIV = 6 if MOBILE else 5
MAX_DIST = 18.0 if MOBILE else 24.0
FOG_START_K = 0.55
RW = RH = 0
small = light_surf = fog_surf = None
SH = (16, 8, 0)
WHITE = 0
SXF = SYF = None


def pack(rgb):
    a = np.clip(rgb, 0, 255).astype(np.uint32)
    return (a[..., 0] << SH[0]) | (a[..., 1] << SH[1]) | (a[..., 2] << SH[2])


SUN = np.array((0.45, 0.62, 0.64), np.float32)
SUN /= np.linalg.norm(SUN)


def setup_resolution(div):
    global RENDER_DIV, RW, RH, small, light_surf, fog_surf, SH, WHITE, SXF, SYF
    global ATLAS_P, SHADE_P, SKY_P, FOG_COL
    RENDER_DIV = max(3, min(12, div))
    RW, RH = max(32, WIDTH // RENDER_DIV), max(18, HEIGHT // RENDER_DIV)
    small = pygame.Surface((RW, RH)).convert()
    if small.get_bitsize() != 32:
        small = pygame.Surface((RW, RH), 0, 32)
    light_surf = small.copy()
    fog_surf = pygame.Surface((RW, RH), pygame.SRCALPHA, 32)
    SH = tuple(small.get_shifts()[:3])
    WHITE = int(pack(np.array((255, 255, 255))))
    tanh = math.tan(FOV / 2)
    sx = ((2 * (np.arange(RW) + 0.5) / RW - 1) * tanh).astype(np.float32)
    sy = ((1 - 2 * (np.arange(RH) + 0.5) / RH) * tanh * RH / RW).astype(np.float32)
    SXF = np.repeat(sx, RH)
    SYF = np.tile(sy, RW)
    ATLAS_P = pack(atlas)
    SHADE_P = pack(np.repeat(np.linspace(0, 255, 32)[:, None], 3, axis=1))
    # небо: градиент по высоте взгляда (dy от -1 до 1)
    k = np.linspace(-1, 1, 128)[:, None]
    hor = np.array((186, 214, 245), np.float32)
    zen = np.array((96, 150, 235), np.float32)
    sky = hor + (zen - hor) * np.clip(k, 0, 1) ** 0.7
    sky[k[:, 0] < 0] = hor * 0.95
    SKY_P = pack(sky)
    FOG_COL = tuple(int(c) for c in hor)


ATLAS_P = SHADE_P = SKY_P = None
FOG_COL = (186, 214, 245)

# яркость граней: [ось][луч идёт в минус]: X, Y (низ/верх), Z
FACE_SHADE = np.array([[0.80, 0.80], [0.5, 1.0], [0.64, 0.64]], np.float32)


def cast_rays(ox, oy, oz, dx, dy, dz, maxd):
    """3D DDA сразу для всех лучей. Возвращает t, блок, ось, flat-индекс клетки.
    Лучи, которые уже во что-то попали, выкидываются из массивов (их всё
    меньше с каждым шагом), поэтому дальние шаги почти бесплатны."""
    n = dx.size
    cx, cy, cz = int(math.floor(ox)), int(math.floor(oy)), int(math.floor(oz))
    with np.errstate(divide="ignore"):
        ex = np.minimum(np.abs(1.0 / dx), 1e30).astype(np.float32)
        ey = np.minimum(np.abs(1.0 / dy), 1e30).astype(np.float32)
        ez = np.minimum(np.abs(1.0 / dz), 1e30).astype(np.float32)
    nx, ny, nz = dx < 0, dy < 0, dz < 0
    fx, fy, fz = ox - cx, oy - cy, oz - cz
    tx = np.where(nx, fx, 1 - fx).astype(np.float32) * ex
    ty = np.where(ny, fy, 1 - fy).astype(np.float32) * ey
    tz = np.where(nz, fz, 1 - fz).astype(np.float32) * ez
    sx = np.where(nx, -STR_X, STR_X).astype(np.int32)
    sy = np.where(ny, -STR_Y, STR_Y).astype(np.int32)
    sz = np.where(nz, -1, 1).astype(np.int32)
    flat = np.full(n, (cx + 1) * STR_X + (cy + 1) * STR_Y + (cz + 1), np.int32)
    ids = np.arange(n, dtype=np.int32)
    out_t = np.full(n, maxd, np.float32)
    out_b = np.zeros(n, np.uint8)
    out_ax = np.zeros(n, np.int8)
    out_f = np.zeros(n, np.int32)
    for _ in range(int(maxd * 1.8) + 3):
        m0 = (tx <= ty) & (tx <= tz)
        m1 = (ty < tx) & (ty <= tz)
        t = np.minimum(np.minimum(tx, ty), tz)
        m2 = ~(m0 | m1)
        np.add(tx, ex, out=tx, where=m0)
        np.add(ty, ey, out=ty, where=m1)
        np.add(tz, ez, out=tz, where=m2)
        flat += np.where(m0, sx, np.where(m1, sy, sz))
        b = WF[flat]
        done = (b != 0) | (t > maxd)
        if done.any():
            d_ids = ids[done]
            out_t[d_ids] = t[done]
            out_b[d_ids] = b[done]
            out_ax[d_ids] = np.where(m0[done], 0, np.where(m1[done], 1, 2))
            out_f[d_ids] = flat[done]
            keep = ~done
            if not keep.any():
                break
            ids, flat = ids[keep], flat[keep]
            tx, ty, tz = tx[keep], ty[keep], tz[keep]
            ex, ey, ez = ex[keep], ey[keep], ez[keep]
            sx, sy, sz = sx[keep], sy[keep], sz[keep]
    return out_t, out_b, out_ax, out_f


target = None        # ((x, y, z) блока, (x, y, z) соседней пустой клетки)


def render_world():
    fx, fy, fz = math.cos(pitch) * math.cos(yaw), math.sin(pitch), math.cos(pitch) * math.sin(yaw)
    rx, rz = -math.sin(yaw), math.cos(yaw)
    ux, uy, uz = -math.sin(pitch) * math.cos(yaw), math.cos(pitch), -math.sin(pitch) * math.sin(yaw)
    dx = fx + rx * SXF + ux * SYF
    dy = fy + uy * SYF
    dz = fz + rz * SXF + uz * SYF
    inv = 1.0 / np.sqrt(dx * dx + dy * dy + dz * dz)
    dx *= inv
    dy *= inv
    dz *= inv
    ox, oy, oz = pos[0], pos[1] + EYE + bob_offset(), pos[2]
    oy = min(oy, SY - 0.01)

    t, b, ax, flat = cast_rays(ox, oy, oz, dx, dy, dz, MAX_DIST)
    hit = (b != 0) & (b != OUTSIDE)

    C = np.empty(t.size, np.uint32)
    L = np.full(t.size, WHITE, np.uint32)
    F = np.zeros(t.size, np.uint8)

    # небо
    sky = ~hit
    if sky.any():
        sdy = dy[sky]
        col = SKY_P[np.clip(((sdy + 1) * 63.5).astype(np.int32), 0, 127)]
        sun = (dx[sky] * SUN[0] + sdy * SUN[1] + dz[sky] * SUN[2]) > 0.9965
        col[sun] = pack(np.array((255, 250, 215)))
        C[sky] = col

    if hit.any():
        th, bh, axh, fh = t[hit], b[hit], ax[hit], flat[hit]
        hdx, hdy, hdz = dx[hit], dy[hit], dz[hit]
        px_ = ox + hdx * th
        py_ = oy + hdy * th
        pz_ = oz + hdz * th
        # текстурные координаты на грани
        fxr = px_ - np.floor(px_)
        fyr = py_ - np.floor(py_)
        fzr = pz_ - np.floor(pz_)
        u = np.where(axh == 0, fzr, fxr)
        v = np.where(axh == 1, fzr, 1 - fyr)
        ui = np.minimum((u * TEX).astype(np.int32), TEX - 1)
        vi = np.minimum((v * TEX).astype(np.int32), TEX - 1)
        is_y = axh == 1
        kind = np.where(is_y, np.where(hdy < 0, 0, 2), 1)
        ti = FACE_TEX[bh, kind]
        ch = ATLAS_P[ti, vi, ui]

        # освещение: грань + тень (клетка перед гранью ниже "неба" колонки)
        neg = np.where(axh == 0, hdx < 0, np.where(is_y, hdy < 0, hdz < 0))
        stepf = np.choose(axh, (STR_X, STR_Y, 1)) * np.where(neg, -1, 1)
        af = fh - stepf                                  # пустая клетка перед гранью
        acx = af // STR_X
        acy = (af // STR_Y) % (SY + 2)
        acz = af % (SZ + 2)
        lit = (acy - 1) >= SKYTOP[acx, acz]
        shade = FACE_SHADE[axh, neg.astype(np.int8)] * np.where(lit, 1.0, 0.55)
        L[hit] = SHADE_P[(shade * 31).astype(np.int32)]

        C[hit] = ch
        f0 = MAX_DIST * FOG_START_K
        F[hit] = (np.clip((th - f0) / (MAX_DIST - f0), 0, 1) * 255).astype(np.uint8)

    # рамка вокруг выбранного блока: контур его области на экране
    if target is not None:
        (tx, ty, tz), _ = target
        tf = (tx + 1) * STR_X + (ty + 1) * STR_Y + (tz + 1)
        S = ((flat == tf) & hit).reshape(RW, RH)
        if S.any():
            inner = S.copy()
            inner[1:, :] &= S[:-1, :]
            inner[:-1, :] &= S[1:, :]
            inner[:, 1:] &= S[:, :-1]
            inner[:, :-1] &= S[:, 1:]
            edge = (S & ~inner).reshape(-1)
            C[edge] = 0
            L[edge] = WHITE

    pygame.surfarray.blit_array(small, C.reshape(RW, RH))
    pygame.surfarray.blit_array(light_surf, L.reshape(RW, RH))
    small.blit(light_surf, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    fog_surf.fill(FOG_COL + (255,))
    fa = pygame.surfarray.pixels_alpha(fog_surf)
    fa[...] = F.reshape(RW, RH)
    del fa
    small.blit(fog_surf, (0, 0))
    try:
        pygame.transform.scale(small, (WIDTH, HEIGHT), screen)
    except (ValueError, pygame.error):
        screen.blit(pygame.transform.scale(small, (WIDTH, HEIGHT)), (0, 0))


# --------------------------------------------------------- ПРИЦЕЛ (1 луч) --
def pick_block():
    """Блок под прицелом и пустая клетка перед ним (для постановки)."""
    ox, oy, oz = pos[0], pos[1] + EYE, pos[2]
    d = (math.cos(pitch) * math.cos(yaw), math.sin(pitch), math.cos(pitch) * math.sin(yaw))
    c = [int(math.floor(ox)), int(math.floor(oy)), int(math.floor(oz))]
    o = (ox, oy, oz)
    step, tmax, tdel = [0] * 3, [0.0] * 3, [0.0] * 3
    for i in range(3):
        if abs(d[i]) < 1e-9:
            step[i], tmax[i], tdel[i] = 0, 1e30, 1e30
        else:
            step[i] = 1 if d[i] > 0 else -1
            tdel[i] = abs(1 / d[i])
            tmax[i] = ((c[i] + 1 - o[i]) if d[i] > 0 else (o[i] - c[i])) * tdel[i]
    prev = tuple(c)
    while True:
        i = 0 if tmax[0] < tmax[1] and tmax[0] < tmax[2] else (1 if tmax[1] < tmax[2] else 2)
        if tmax[i] > REACH:
            return None
        prev = tuple(c)
        c[i] += step[i]
        tmax[i] += tdel[i]
        bl = get_block(*c)
        if bl == OUTSIDE:
            return None
        if bl != AIR:
            return tuple(c), prev


# ---------------------------------------------------------------- ФИЗИКА ---
def collides(x, y, z):
    for bx in range(int(math.floor(x - PW)), int(math.floor(x + PW)) + 1):
        for by in range(int(math.floor(y)), int(math.floor(y + PH - 1e-6)) + 1):
            for bz in range(int(math.floor(z - PW)), int(math.floor(z + PW)) + 1):
                bl = get_block(bx, by, bz)
                if bl != AIR:
                    return True
    return False


def move_player(dx, dz, dy_fly, dt):
    """Возвращает True, если упёрлись в стену по горизонтали."""
    global vel_y, on_ground
    blocked = False
    x, y, z = pos
    for _ in range(2):                  # маленькими шагами, чтобы не проскочить
        sx, sz = dx / 2, dz / 2
        if sx and not collides(x + sx, y, z):
            x += sx
        elif sx:
            blocked = True
        if sz and not collides(x, y, z + sz):
            z += sz
        elif sz:
            blocked = True
    if flying:
        vel_y = 0.0
        ny = y + dy_fly
        if not collides(x, ny, z):
            y = ny
        on_ground = False
    else:
        vel_y = max(vel_y - GRAVITY * dt, -40)
        ny = y + vel_y * dt
        if collides(x, ny, z):
            if vel_y < 0:
                y = math.floor(ny) + 1.0
                on_ground = True
                if collides(x, y, z):       # на всякий случай
                    y = pos[1]
            vel_y = 0.0
        else:
            y = ny
            on_ground = False
    if y < -5:                           # выпали из мира — на точку появления
        x, z = spawn_x, spawn_z
        y = float(SKYTOP[int(x) + 1, int(z) + 1]) + 0.01
    pos[:] = [x, min(y, SY - PH - 0.05), z]
    return blocked


def player_hits_cell(c):
    x, y, z = pos
    return (c[0] + 1 > x - PW and c[0] < x + PW and c[1] + 1 > y and c[1] < y + PH
            and c[2] + 1 > z - PW and c[2] < z + PW)


hand_swing = 0.0
walk_phase = 0.0
walk_amount = 0.0


def bob_offset():
    return math.sin(walk_phase * 2) * 0.04 * walk_amount


def do_break():
    global hand_swing
    hand_swing = 1.0
    if target is None:
        return
    (x, y, z), _ = target
    if world[x, y, z] != BEDROCK:
        set_block(x, y, z, AIR)


def do_place():
    global hand_swing
    hand_swing = 1.0
    if target is None:
        return
    _, c = target
    if not (0 <= c[0] < SX and 0 <= c[1] < SY and 0 <= c[2] < SZ):
        return
    if world[c] != AIR or player_hits_cell(c):
        return
    set_block(c[0], c[1], c[2], HOTBAR[selected])


# -------------------------------------------------------------- ИКОНКИ -----
def make_block_icon(block, size):
    S = size
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) + 0.5
    a = S / 2
    c30 = math.cos(math.radians(30))
    X = np.array((a * c30, a * 0.5))
    Y = np.array((-a * c30, a * 0.5))
    Zd = np.array((0.0, a))
    o = np.array((S / 2, 0.0))
    out = np.zeros((S, S, 4), np.float32)
    top, side, _ = FACE_TEX[block]
    for org, A, B, tex, shade in ((o, X, Y, top, 1.0), (o + X, Y, Zd, side, 0.62),
                                  (o + Y, X, Zd, side, 0.8)):
        det = A[0] * B[1] - A[1] * B[0]
        ddx, ddy = xx - org[0], yy - org[1]
        s = (ddx * B[1] - ddy * B[0]) / det
        tt = (A[0] * ddy - A[1] * ddx) / det
        m = (s >= 0) & (s < 1) & (tt >= 0) & (tt < 1)
        u = np.clip((s * TEX).astype(int), 0, TEX - 1)
        v = np.clip((tt * TEX).astype(int), 0, TEX - 1)
        out[m, :3] = atlas[tex][v[m], u[m]] * shade
        out[m, 3] = 255
    arr = np.ascontiguousarray(np.clip(out, 0, 255).astype(np.uint8))
    return pygame.image.frombuffer(arr.tobytes(), (S, S), "RGBA").convert_alpha()


SLOT = int(72 * UI * (1.35 if MOBILE else 1))
ICON_SMALL = {b: make_block_icon(b, int(SLOT * 0.72)) for b in HOTBAR}
ICON_HAND = {b: make_block_icon(b, int(300 * UI)) for b in HOTBAR}
font = pygame.font.SysFont(None, max(14, int(28 * UI)))
big_font = pygame.font.SysFont(None, max(18, int(40 * UI)))

hotbar_rect = pygame.Rect(0, 0, SLOT * len(HOTBAR) + 8, SLOT + 8)
hotbar_rect.midbottom = (WIDTH // 2, HEIGHT - max(4, int(8 * UI)))
selected = 0
name_timer = 2.0


def hotbar_slot_at(p):
    if hotbar_rect.collidepoint(p):
        return min(len(HOTBAR) - 1, (p[0] - hotbar_rect.x - 4) // SLOT)
    return None


_hotbar_cache = {}


def draw_hotbar():
    if selected not in _hotbar_cache:
        s = pygame.Surface(hotbar_rect.size, pygame.SRCALPHA)
        s.fill((20, 20, 20, 150))
        for i, bl in enumerate(HOTBAR):
            r = pygame.Rect(4 + i * SLOT, 4, SLOT, SLOT)
            pygame.draw.rect(s, (110, 110, 110, 255), r, 2)
            s.blit(ICON_SMALL[bl], ICON_SMALL[bl].get_rect(center=r.center))
        r = pygame.Rect(4 + selected * SLOT, 4, SLOT, SLOT)
        pygame.draw.rect(s, (255, 255, 255, 255), r.inflate(2, 2), max(2, int(4 * UI)))
        _hotbar_cache[selected] = s
    screen.blit(_hotbar_cache[selected], hotbar_rect)
    if name_timer > 0:
        txt = big_font.render(BLOCK_NAMES[HOTBAR[selected]], True, (255, 255, 255))
        txt.set_alpha(int(255 * min(1.0, name_timer)))
        screen.blit(txt, txt.get_rect(midbottom=(hotbar_rect.centerx, hotbar_rect.y - 6)))


def draw_crosshair():
    cx, cy = WIDTH // 2, HEIGHT // 2
    k = max(6, int(12 * UI))
    for w, col in ((max(3, int(5 * UI)), (0, 0, 0)), (max(1, int(2 * UI)), (255, 255, 255))):
        pygame.draw.line(screen, col, (cx - k, cy), (cx + k, cy), w)
        pygame.draw.line(screen, col, (cx, cy - k), (cx, cy + k), w)


def draw_hand():
    icon = ICON_HAND[HOTBAR[selected]]
    sw = math.sin(hand_swing * math.pi)
    bx = math.cos(walk_phase) * 16 * UI * walk_amount
    by = abs(math.sin(walk_phase)) * 16 * UI * walk_amount
    x = WIDTH * (0.66 if MOBILE else 0.70) + bx - sw * 70 * UI
    y = HEIGHT - icon.get_height() * 0.62 + by + sw * 50 * UI
    screen.blit(icon, (x, y))


# --------------------------------------------------- СЕНСОРНОЕ УПРАВЛЕНИЕ --
class Button:
    def __init__(self, center, radius, kind):
        self.c = center
        self.r = radius
        self.kind = kind
        self.pointers = set()

    @property
    def active(self):
        return bool(self.pointers)

    def hit(self, p):
        return (p[0] - self.c[0]) ** 2 + (p[1] - self.c[1]) ** 2 <= (self.r * 1.15) ** 2

    def draw(self, surf, on=False):
        s = pygame.Surface((self.r * 2 + 2, self.r * 2 + 2), pygame.SRCALPHA)
        c = (self.r + 1, self.r + 1)
        pygame.draw.circle(s, (255, 255, 255, 140 if (self.active or on) else 60), c, self.r)
        pygame.draw.circle(s, (255, 255, 255, 200), c, self.r, 2)
        k = self.r * 0.45
        col = (30, 30, 30) if (self.active or on) else (255, 255, 255)
        if self.kind == "up":
            pygame.draw.polygon(s, col, [(c[0], c[1] - k), (c[0] - k, c[1] + k * 0.6), (c[0] + k, c[1] + k * 0.6)])
        elif self.kind == "down":
            pygame.draw.polygon(s, col, [(c[0], c[1] + k), (c[0] - k, c[1] - k * 0.6), (c[0] + k, c[1] - k * 0.6)])
        else:   # полёт: два крыла
            pygame.draw.polygon(s, col, [(c[0], c[1] - k * 0.2), (c[0] - k, c[1] - k * 0.6), (c[0] - k * 0.6, c[1] + k * 0.5)])
            pygame.draw.polygon(s, col, [(c[0], c[1] - k * 0.2), (c[0] + k, c[1] - k * 0.6), (c[0] + k * 0.6, c[1] + k * 0.5)])
        surf.blit(s, (self.c[0] - self.r - 1, self.c[1] - self.r - 1))


BR = int(52 * UI * (1.5 if MOBILE else 1))
btn_jump = Button((WIDTH - BR - int(30 * UI), HEIGHT - BR - int(40 * UI)), BR, "up")
btn_down = Button((btn_jump.c[0] - int(BR * 2.4), btn_jump.c[1]), BR, "down")
btn_fly = Button((btn_jump.c[0], btn_jump.c[1] - int(BR * 2.4)), int(BR * 0.8), "fly")
JOY_R = int(90 * UI * (1.5 if MOBILE else 1))
JOY_HOME = (int(JOY_R * 1.5), HEIGHT - int(JOY_R * 1.4))

TAP_TIME = 0.28          # короче — "тап" (сломать)
HOLD_TIME = 0.45         # дольше без движения — поставить блок
MOVE_SLOP = 12 * UI      # смещение пальца, после которого это уже свайп
LOOK_SENS = 0.0065 / UI  # радиан на логический пиксель


# ------------------------------------------------------------- ОСНОВНОЙ ЦИКЛ
def main():
    global yaw, pitch, vel_y, flying, selected, name_timer, hand_swing
    global walk_phase, walk_amount, target, on_ground

    setup_resolution(RENDER_DIV)
    clock = pygame.time.Clock()
    keys = set()
    mouse_grab = False
    touch_used = MOBILE
    show_debug = True
    joy = None          # [pid, origin, current]
    look = {}           # pid -> dict(start, t0, last, moved, placed)
    fps_surf = None
    fps_timer = 0.0
    perf_t, perf_n, auto_res = 0.0, 0, True
    t = 0.0
    help_lines = [] if MOBILE else [
        "Клик - захватить мышь, Esc - отпустить",
        "WASD - ходьба, Пробел - прыжок, F - полёт, Shift - вниз",
        "ЛКМ - сломать, ПКМ - поставить, 1-9 / колесо - блок, +/- качество",
    ]
    help_surfs = [font.render(s, True, (255, 255, 255)) for s in help_lines]

    def grab(on):
        nonlocal mouse_grab
        mouse_grab = on
        pygame.event.set_grab(on)
        pygame.mouse.set_visible(not on)
        pygame.mouse.get_rel()

    def select(i):
        global selected, name_timer
        selected = i % len(HOTBAR)
        name_timer = 2.0

    running = True
    while running:
        raw_dt = clock.tick(60) / 1000.0
        dt = min(raw_dt, 0.05)
        t += dt

        if auto_res and t > 2.0:
            perf_t += raw_dt
            perf_n += 1
            if perf_t > 2.0:
                avg = perf_t / perf_n
                if avg > 1 / 22 and RENDER_DIV < 12:
                    setup_resolution(RENDER_DIV + 1)
                elif avg < 1 / 45 and RENDER_DIV > (4 if MOBILE else 3):
                    setup_resolution(RENDER_DIV - 1)
                perf_t, perf_n = 0.0, 0

        for e in pygame.event.get():
            if e.type == QUIT:
                running = False
            elif e.type == KEYDOWN:
                keys.add(e.key)
                if e.key == K_ESCAPE:
                    if mouse_grab:
                        grab(False)
                    else:
                        running = False
                elif e.key == K_f:
                    flying = not flying
                    vel_y = 0.0
                elif e.key == K_F3:
                    show_debug = not show_debug
                elif e.key in (K_EQUALS, K_PLUS, K_KP_PLUS):
                    auto_res = False
                    setup_resolution(RENDER_DIV - 1)
                elif e.key in (K_MINUS, K_KP_MINUS):
                    auto_res = False
                    setup_resolution(RENDER_DIV + 1)
                elif K_1 <= e.key <= K_9:
                    select(e.key - K_1)
            elif e.type == KEYUP:
                keys.discard(e.key)

            elif e.type == MOUSEBUTTONDOWN and not (touch_used or getattr(e, "touch", False)):
                if e.button in (4, 5):
                    continue
                if not mouse_grab:
                    slot = hotbar_slot_at(e.pos)
                    if slot is not None:
                        select(slot)
                    else:
                        grab(True)
                elif e.button == 1:
                    do_break()
                elif e.button == 3:
                    do_place()
            elif e.type == MOUSEMOTION and mouse_grab and not getattr(e, "touch", False):
                yaw += e.rel[0] * 0.0025
                pitch = max(-1.55, min(1.55, pitch - e.rel[1] * 0.0025))
            elif e.type == EV_MOUSEWHEEL:
                select(selected - e.y)

            elif e.type in (EV_FINGERDOWN, EV_FINGERMOTION, EV_FINGERUP):
                touch_used = True
                p = (e.x * WIDTH, e.y * HEIGHT)
                pid = e.finger_id
                if e.type == EV_FINGERDOWN:
                    slot = hotbar_slot_at(p)
                    if slot is not None:
                        select(slot)
                        continue
                    handled = False
                    for b in (btn_jump, btn_fly, btn_down):
                        if (b is not btn_down or flying) and b.hit(p):
                            b.pointers.add(pid)
                            if b is btn_fly:
                                flying = not flying
                                vel_y = 0.0
                            handled = True
                            break
                    if handled:
                        continue
                    if p[0] < WIDTH * 0.42 and joy is None:
                        joy = [pid, p, p]
                    else:
                        look[pid] = {"start": p, "t0": t, "last": p, "moved": False, "placed": False}
                elif e.type == EV_FINGERMOTION:
                    if joy is not None and joy[0] == pid:
                        joy[2] = p
                    elif pid in look:
                        L = look[pid]
                        ddx, ddy = p[0] - L["last"][0], p[1] - L["last"][1]
                        L["last"] = p
                        if not L["moved"] and math.hypot(p[0] - L["start"][0], p[1] - L["start"][1]) > MOVE_SLOP:
                            L["moved"] = True
                        if L["moved"]:
                            yaw += ddx * LOOK_SENS
                            pitch = max(-1.55, min(1.55, pitch - ddy * LOOK_SENS))
                else:
                    if joy is not None and joy[0] == pid:
                        joy = None
                    if pid in look:
                        L = look.pop(pid)
                        if not L["moved"] and not L["placed"] and t - L["t0"] < TAP_TIME + 0.15:
                            target = pick_block()
                            do_break()
                    for b in (btn_jump, btn_fly, btn_down):
                        b.pointers.discard(pid)

        # долгое нажатие -> поставить блок
        for L in look.values():
            if not L["moved"] and not L["placed"] and t - L["t0"] >= HOLD_TIME:
                L["placed"] = True
                target = pick_block()
                do_place()

        # ---- движение ----
        mf = ms = 0.0
        if K_w in keys or K_UP in keys:
            mf += 1
        if K_s in keys or K_DOWN in keys:
            mf -= 1
        if K_a in keys or K_LEFT in keys:
            ms -= 1
        if K_d in keys or K_RIGHT in keys:
            ms += 1
        if joy is not None:
            jx = (joy[2][0] - joy[1][0]) / JOY_R
            jy = (joy[2][1] - joy[1][1]) / JOY_R
            ln = math.hypot(jx, jy)
            if ln > 1:
                jx, jy = jx / ln, jy / ln
            if ln > 0.12:
                mf -= jy
                ms += jx
        ln = math.hypot(mf, ms)
        if ln > 1:
            mf, ms = mf / ln, ms / ln
        speed = (FLY_SPEED if flying else WALK) * dt
        cy_, sy_ = math.cos(yaw), math.sin(yaw)
        dxw = (cy_ * mf - sy_ * ms) * speed
        dzw = (sy_ * mf + cy_ * ms) * speed
        up = K_SPACE in keys or btn_jump.active
        down = K_LSHIFT in keys or K_RSHIFT in keys or btn_down.active
        dy_fly = ((1 if up else 0) - (1 if down else 0)) * FLY_SPEED * dt
        if not flying and up and on_ground:
            vel_y = JUMP_V
            on_ground = False
        blocked = move_player(dxw, dzw, dy_fly, dt)
        # автопрыжок на ступеньку в 1 блок (удобно на телефоне)
        if touch_used and blocked and on_ground and not flying and ln > 0.3:
            vel_y = JUMP_V
            on_ground = False

        moving = ln > 0.1 and (on_ground or flying)
        if moving:
            walk_phase += dt * 9
        walk_amount += ((1.0 if moving and not flying else 0.0) - walk_amount) * min(1, dt * 8)
        hand_swing = max(0.0, hand_swing - dt * 4)
        name_timer = max(0.0, name_timer - dt)

        target = pick_block()
        render_world()

        # ---- интерфейс ----
        draw_crosshair()
        draw_hand()
        draw_hotbar()
        if touch_used:
            jc = joy[1] if joy else JOY_HOME
            s = pygame.Surface((JOY_R * 2 + 2, JOY_R * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (255, 255, 255, 50), (JOY_R + 1, JOY_R + 1), JOY_R)
            pygame.draw.circle(s, (255, 255, 255, 140), (JOY_R + 1, JOY_R + 1), JOY_R, 2)
            screen.blit(s, (jc[0] - JOY_R - 1, jc[1] - JOY_R - 1))
            kn = jc
            if joy:
                ddx, ddy = joy[2][0] - jc[0], joy[2][1] - jc[1]
                ln2 = math.hypot(ddx, ddy)
                if ln2 > JOY_R:
                    ddx, ddy = ddx / ln2 * JOY_R, ddy / ln2 * JOY_R
                kn = (jc[0] + ddx, jc[1] + ddy)
            pygame.draw.circle(screen, (235, 235, 235), (int(kn[0]), int(kn[1])), int(JOY_R * 0.42))
            btn_jump.draw(screen)
            btn_fly.draw(screen, on=flying)
            if flying:
                btn_down.draw(screen)
            for L in look.values():          # кольцо прогресса долгого нажатия
                if not L["moved"] and not L["placed"]:
                    k = (t - L["t0"]) / HOLD_TIME
                    if k > 0.25:
                        rr = int(26 * UI * 1.5)
                        rect = pygame.Rect(0, 0, rr * 2, rr * 2)
                        rect.center = (int(L["start"][0]), int(L["start"][1]))
                        pygame.draw.arc(screen, (255, 255, 255), rect, math.pi / 2,
                                        math.pi / 2 + 2 * math.pi * min(1, k), max(2, int(4 * UI)))

        fps_timer -= dt
        if fps_timer <= 0:
            fps_timer = 0.25
            fps_surf = font.render(
                f"FPS {clock.get_fps():.0f}  рендер {RW}x{RH}  "
                f"XYZ {pos[0]:.1f} {pos[1]:.1f} {pos[2]:.1f}{'  полёт' if flying else ''}",
                True, (255, 255, 255))
        if show_debug and fps_surf:
            screen.blit(fps_surf, (6, 4))
            for i, s in enumerate(help_surfs):
                screen.blit(s, (6, 6 + (i + 1) * font.get_linesize()))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        show_error(traceback.format_exc())
