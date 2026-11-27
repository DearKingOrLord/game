"""
Кубоземье — воксельная песочница на Python (pygame + numpy).

Большой 3D-мир 256x48x256: равнины, горы со снежными вершинами, пустыни
с кактусами, берёзовые рощи, моря и озёра (зимой — лёд), пещеры и руды.
Инвентарь на 36 ячеек, верстак (крафт), инструменты — кирки, топоры и
лопаты четырёх уровней с прочностью. Режимы «Выживание» и «Творчество»
(в творчестве есть вкладка со всеми блоками).

Рендер — векторизованный 3D-рейкастинг (numpy) по полю расстояний:
в пустоте луч перепрыгивает сразу до 15 блоков, поэтому дальность
прорисовки стала в 2 раза больше без потери FPS. Работает и на телефоне
(Pydroid 3).

Телефон:
  левая половина экрана — джойстик (ходьба)
  правая половина — провести пальцем: осмотреться
                    коротко коснуться: поставить блок
                    подержать палец: копать блок
  кнопка со стрелкой — прыжок / плыть вверх (в полёте — вверх),
  рядом — полёт и вниз; кнопка-сетка справа вверху — инвентарь
  хотбар внизу — выбор предмета

Компьютер:
  клик — захватить мышь, Esc — отпустить
  WASD — ходьба, Пробел — прыжок / вверх, Shift — вниз (в полёте)
  F — полёт, ЛКМ (держать) — копать, ПКМ — поставить
  E — инвентарь, 1-9 / колесо — предмет
  [ ] — дальность прорисовки, +/- — качество, F3 — отладка
"""
import math
import os
import sys
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


def loading(msg):
    screen.fill((22, 26, 34))
    f = pygame.font.SysFont(None, max(18, int(44 * UI)))
    s = f.render(msg, True, (230, 230, 230))
    screen.blit(s, s.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
    pygame.display.flip()
    pygame.event.pump()


loading("Создание мира...")

# --------------------------------------------------------------- БЛОКИ -----
(AIR, GRASS, DIRT, STONE, COBBLE, PLANKS, LOG, LEAVES, SAND, BRICKS, BEDROCK,
 WATER, GRAVEL, SNOW_GRASS, SNOW, SANDSTONE, COAL_ORE, IRON_ORE, GOLD_ORE, DIAMOND_ORE,
 BIRCH_LOG, BIRCH_LEAVES, BIRCH_PLANKS, CACTUS, CLAY, STONE_BRICKS, MOSSY_COBBLE,
 OBSIDIAN, ICE, CRAFT_TABLE, FURNACE, BOOKSHELF, PUMPKIN, IRON_BLOCK, GOLD_BLOCK,
 DIAMOND_BLOCK, WOOL_WHITE, WOOL_RED, WOOL_ORANGE, WOOL_YELLOW, WOOL_GREEN, WOOL_BLUE,
 WOOL_PURPLE, WOOL_BLACK) = range(44)
NUM_BLOCKS = 44
OUTSIDE = 255                       # граница мира (рамка вокруг массива)
BLOCK_NAMES = {
    GRASS: "Трава", DIRT: "Земля", STONE: "Камень", COBBLE: "Булыжник", PLANKS: "Доски",
    LOG: "Бревно", LEAVES: "Листва", SAND: "Песок", BRICKS: "Кирпич",
    BEDROCK: "Коренная порода", WATER: "Вода", GRAVEL: "Гравий",
    SNOW_GRASS: "Заснеженная трава", SNOW: "Снег", SANDSTONE: "Песчаник",
    COAL_ORE: "Угольная руда", IRON_ORE: "Железная руда", GOLD_ORE: "Золотая руда",
    DIAMOND_ORE: "Алмазная руда", BIRCH_LOG: "Берёзовое бревно",
    BIRCH_LEAVES: "Берёзовая листва", BIRCH_PLANKS: "Берёзовые доски", CACTUS: "Кактус",
    CLAY: "Глина", STONE_BRICKS: "Каменные кирпичи", MOSSY_COBBLE: "Замшелый булыжник",
    OBSIDIAN: "Обсидиан", ICE: "Лёд", CRAFT_TABLE: "Верстак", FURNACE: "Печь",
    BOOKSHELF: "Книжная полка", PUMPKIN: "Тыква", IRON_BLOCK: "Железный блок",
    GOLD_BLOCK: "Золотой блок", DIAMOND_BLOCK: "Алмазный блок",
    WOOL_WHITE: "Белая шерсть", WOOL_RED: "Красная шерсть", WOOL_ORANGE: "Оранжевая шерсть",
    WOOL_YELLOW: "Жёлтая шерсть", WOOL_GREEN: "Зелёная шерсть", WOOL_BLUE: "Синяя шерсть",
    WOOL_PURPLE: "Фиолетовая шерсть", WOOL_BLACK: "Чёрная шерсть",
}

# ------------------------------------------------------------ ИНСТРУМЕНТЫ --
TOOL_BASE = 100
TOOL_KINDS = ("pick", "axe", "shovel")
TOOL_KIND_NAMES = (("кирка", 0), ("топор", 1), ("лопата", 0))    # 0 - ж.р., 1 - м.р.
TIER_ADJ = (("Деревянная", "Каменная", "Железная", "Алмазная"),
            ("Деревянный", "Каменный", "Железный", "Алмазный"))
TIER_SPEED = (2.0, 4.0, 6.5, 9.0)
TIER_DUR = (60, 132, 250, 1561)
TIER_COLORS = ((160, 122, 70), (98, 98, 104), (226, 226, 226), (92, 226, 216))


def tool_id(kind, tier):
    return TOOL_BASE + TOOL_KINDS.index(kind) * 4 + tier


def tool_info(item):
    if item is not None and item >= TOOL_BASE:
        return TOOL_KINDS[(item - TOOL_BASE) // 4], (item - TOOL_BASE) % 4
    return None, -1


ITEM_NAMES = dict(BLOCK_NAMES)
ALL_TOOLS = []
for _k, (_kn, _g) in zip(TOOL_KINDS, TOOL_KIND_NAMES):
    for _tier in range(4):
        _id = tool_id(_k, _tier)
        ITEM_NAMES[_id] = TIER_ADJ[_g][_tier] + " " + _kn
        ALL_TOOLS.append(_id)


def max_stack(item):
    return 1 if item >= TOOL_BASE else 64


def new_stack(item, count=None):
    if item >= TOOL_BASE:
        return [item, 1, TIER_DUR[tool_info(item)[1]]]
    return [item, max_stack(item) if count is None else count, 0]


# прочность блоков (секунды рукой) и подходящий инструмент
SOFT = (GRASS, DIRT, SAND, GRAVEL, SNOW_GRASS, SNOW, CLAY)
WOODY = (PLANKS, LOG, BIRCH_LOG, BIRCH_PLANKS, CRAFT_TABLE, BOOKSHELF, PUMPKIN)
ROCKY = (STONE, COBBLE, SANDSTONE, BRICKS, STONE_BRICKS, MOSSY_COBBLE, COAL_ORE, IRON_ORE,
         GOLD_ORE, DIAMOND_ORE, OBSIDIAN, FURNACE, IRON_BLOCK, GOLD_BLOCK, DIAMOND_BLOCK, ICE)
HARD = {GRASS: 0.9, DIRT: 0.75, SAND: 0.75, GRAVEL: 0.9, SNOW_GRASS: 0.9, SNOW: 0.5, CLAY: 0.9,
        LEAVES: 0.3, BIRCH_LEAVES: 0.3, CACTUS: 0.6, PUMPKIN: 1.5, BOOKSHELF: 2.0,
        PLANKS: 2.5, BIRCH_PLANKS: 2.5, LOG: 3.0, BIRCH_LOG: 3.0, CRAFT_TABLE: 3.0,
        STONE: 4.0, COBBLE: 4.5, SANDSTONE: 2.5, BRICKS: 4.5, STONE_BRICKS: 4.5,
        MOSSY_COBBLE: 4.5, COAL_ORE: 5.0, IRON_ORE: 6.0, GOLD_ORE: 6.0, DIAMOND_ORE: 7.0,
        OBSIDIAN: 30.0, ICE: 1.0, FURNACE: 5.0, IRON_BLOCK: 7.0, GOLD_BLOCK: 6.0,
        DIAMOND_BLOCK: 8.0}
TOOL_FOR = {}
TOOL_FOR.update({b: "shovel" for b in SOFT})
TOOL_FOR.update({b: "axe" for b in WOODY})
TOOL_FOR.update({b: "pick" for b in ROCKY})
NEED_TIER = {b: 0 for b in ROCKY if b != ICE}     # без кирки нужного уровня ничего не выпадет
NEED_TIER.update({IRON_ORE: 1, IRON_BLOCK: 1, GOLD_ORE: 2, GOLD_BLOCK: 2,
                  DIAMOND_ORE: 2, DIAMOND_BLOCK: 2, OBSIDIAN: 3})
DROPS = {GRASS: DIRT, SNOW_GRASS: DIRT, STONE: COBBLE}

# рецепты: (результат, количество, ((ингредиент или группа, сколько), ...))
ANY_PLANKS = (PLANKS, BIRCH_PLANKS)
RECIPES = [
    (PLANKS, 4, ((LOG, 1),)),
    (BIRCH_PLANKS, 4, ((BIRCH_LOG, 1),)),
    (CRAFT_TABLE, 1, ((ANY_PLANKS, 4),)),
]
for _k, _n1 in (("pick", 3), ("axe", 3), ("shovel", 1)):
    RECIPES.append((tool_id(_k, 0), 1, ((ANY_PLANKS, _n1 + 2),)))
    for _tier, _mat in ((1, COBBLE), (2, IRON_ORE), (3, DIAMOND_ORE)):
        RECIPES.append((tool_id(_k, _tier), 1, ((_mat, _n1), (ANY_PLANKS, 2))))
RECIPES += [
    (FURNACE, 1, ((COBBLE, 8),)),
    (STONE, 1, ((COBBLE, 1),)),
    (STONE_BRICKS, 4, ((STONE, 4),)),
    (MOSSY_COBBLE, 1, ((COBBLE, 1), (LEAVES, 1))),
    (SANDSTONE, 1, ((SAND, 4),)),
    (BRICKS, 2, ((CLAY, 2),)),
    (BOOKSHELF, 1, ((ANY_PLANKS, 6),)),
    (ICE, 1, ((SNOW, 4),)),
    (IRON_BLOCK, 1, ((IRON_ORE, 4),)),
    (GOLD_BLOCK, 1, ((GOLD_ORE, 4),)),
    (DIAMOND_BLOCK, 1, ((DIAMOND_ORE, 4),)),
]

# --------------------------------------------------------------- ТЕКСТУРЫ --
TEX = 16
rng = np.random.RandomState(2024)
_YY, _XX = np.mgrid[0:TEX, 0:TEX]


def _n(lo, hi):
    return rng.randint(lo, hi + 1, (TEX, TEX, 1)).astype(np.float32)


def _speck(t, p, k):
    m = rng.random_sample((TEX, TEX)) < p
    t[m] *= k
    return t


def noisy(col, a):
    return np.array(col, np.float32) + _n(-a, a)


def t_grass_top():
    t = noisy((92, 152, 58), 16)
    _speck(t, 0.12, 0.82)
    return _speck(t, 0.08, 1.15)


def t_dirt():
    t = noisy((132, 94, 64), 12)
    _speck(t, 0.1, 0.78)
    return _speck(t, 0.06, 1.2)


def t_grass_side(top):
    t = t_dirt()
    for x in range(TEX):
        h = 3 + rng.randint(0, 3) - (1 if rng.random_sample() < 0.2 else 0)
        t[:h, x] = top[:h, x]
    return t


def t_stone():
    t = noisy((126, 126, 128), 12)
    for _ in range(5):                      # тёмные прожилки
        x, y = rng.randint(0, TEX, 2)
        for i in range(rng.randint(2, 5)):
            t[y % TEX, (x + i) % TEX] *= 0.78
    return t


def t_cobble():
    pts = rng.random_sample((11, 2)) * TEX
    yy, xx = _YY.astype(np.float32), _XX.astype(np.float32)
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


def t_planks(base=(168, 128, 78)):
    t = np.zeros((TEX, TEX, 3), np.float32)
    base = np.array(base, np.float32)
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


def t_log_top(c1=(172, 136, 86), c2=(146, 110, 64), bark=(100, 76, 46)):
    r = np.maximum(np.abs(_XX - 7.5), np.abs(_YY - 7.5))
    ring = (r.astype(int) % 2 == 0)
    t = np.where(ring[..., None], np.array(c1, np.float32),
                 np.array(c2, np.float32)).astype(np.float32)
    t[r >= 6.5] = bark
    return t + _n(-6, 6)


def t_leaves(col=(58, 122, 44), dark=(34, 74, 28)):
    t = noisy(col, 22)
    m = rng.random_sample((TEX, TEX)) < 0.22
    t[m] = dark
    return _speck(t, 0.1, 1.2)


def t_sand():
    return _speck(noisy((216, 203, 148), 9), 0.08, 0.9)


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
    return noisy((70, 70, 72), 40)


def t_water():
    t = noisy((46, 92, 200), 6)
    for _ in range(12):
        x, y = rng.randint(0, TEX, 2)
        xs = [(x + i) % TEX for i in range(rng.randint(2, 6))]
        t[y, xs] = t[y, xs] * 0.6 + np.array((140, 180, 245)) * 0.4
    return t


def t_gravel():
    t = noisy((128, 122, 118), 26)
    _speck(t, 0.15, 0.7)
    return _speck(t, 0.1, 1.25)


def t_snow():
    return noisy((236, 240, 247), 5)


def t_sandstone_side():
    t = noisy((216, 200, 142), 5)
    t[0:3] *= 1.05
    t[3] *= 0.84
    t[9] *= 0.9
    t[12:] *= 0.94
    return t


def t_ore(col):
    t = t_stone()
    for _ in range(5):
        x, y = rng.randint(1, TEX - 2, 2)
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            if rng.random_sample() < 0.8:
                t[y + dy, x + dx] = np.array(col) * rng.uniform(0.8, 1.15)
    return t


def t_birch_side():
    t = noisy((214, 212, 200), 8)
    for _ in range(7):
        x, y = rng.randint(0, TEX, 2)
        t[y, [(x + i) % TEX for i in range(rng.randint(2, 6))]] = (44, 42, 38)
    return t


def t_cactus_side():
    t = noisy((70, 138, 52), 8)
    t[:, ::4] *= 0.68
    t[rng.random_sample((TEX, TEX)) < 0.05] = (222, 222, 180)
    return t


def t_cactus_top():
    t = noisy((90, 156, 64), 6)
    r = np.maximum(np.abs(_XX - 7.5), np.abs(_YY - 7.5))
    t[r >= 6.5] *= 0.7
    return t


def t_stone_bricks():
    t = noisy((124, 124, 126), 8)
    t[[0, 8], :] *= 1.12
    t[[7, 15], :] = (82, 82, 84)
    t[0:7, 15] = (82, 82, 84)
    t[8:15, 7] = (82, 82, 84)
    return t


def t_mossy():
    t = t_cobble()
    m = rng.random_sample((TEX, TEX)) < 0.35
    t[m] = t[m] * 0.4 + np.array((70, 122, 50)) * 0.6
    return t


def t_obsidian():
    t = noisy((24, 18, 36), 5)
    t[rng.random_sample((TEX, TEX)) < 0.1] = (66, 46, 100)
    return t


def t_ice():
    t = noisy((150, 190, 242), 5)
    for k in range(3):
        m = (_XX + _YY + k * 5) % 16 == 0
        t[m] = t[m] * 0.5 + 120
    return t


def t_table_top():
    t = t_planks()
    t[[0, 5, 10, 15], :] *= 0.55
    t[:, [0, 5, 10, 15]] *= 0.55
    return t


def t_table_side():
    t = t_planks()
    t[0:2] *= 0.6
    t[4:11, 3] = (70, 50, 30)                  # молоток
    t[4:6, 1:6] = (150, 150, 150)
    t[6, 8:14] = (175, 175, 175)               # пила
    t[7:9, 8:14] = (130, 130, 130)
    t[6:12, 13] = (70, 50, 30)
    return t


def t_furnace_side():
    t = noisy((120, 120, 120), 10)
    t[[0, 15], :] *= 0.75
    t[:, [0, 15]] *= 0.75
    t[2:4, 3:13] *= 0.6
    t[8:14, 4:12] = (34, 30, 28)
    t[11:14, 5:11] = (236, 128, 40)
    t[12, 6:10] = (255, 210, 90)
    return t


def t_bookshelf_side():
    t = t_planks()
    for y0 in (2, 9):
        x = 1
        while x < TEX - 1:
            w = rng.randint(1, 3)
            col = np.array([(150, 40, 40), (40, 70, 150), (50, 120, 60), (170, 140, 60),
                            (110, 60, 130)][rng.randint(0, 5)], np.float32)
            top = y0 + rng.randint(0, 2)
            t[top:y0 + 5, x:min(TEX - 1, x + w)] = col * rng.uniform(0.8, 1.1)
            x += w
        t[y0 + 5] *= 0.6
    return t


def t_pumpkin_side():
    t = noisy((222, 128, 28), 8)
    t[:, ::4] *= 0.78
    return t


def t_pumpkin_top():
    t = noisy((212, 120, 26), 8)
    t[6:10, 6:10] = (110, 82, 40)
    return t


def t_metal(col):
    t = noisy(col, 5)
    t[3:13, 3:13] *= 1.06
    t[0, :] *= 1.2
    t[:, 0] *= 1.2
    t[-1, :] *= 0.7
    t[:, -1] *= 0.7
    t[2, 2:14] *= 0.85
    t[2:14, 2] *= 0.85
    return t


def t_wool(col):
    t = noisy(col, 5)
    t[(_XX + _YY) % 4 == 0] *= 0.9
    t[(_XX - _YY) % 4 == 0] *= 1.05
    return t


TEX_LIST = []
FACE_TEX = np.zeros((256, 3), np.int32)    # [блок] -> (верх, бок, низ)


def tex(t):
    TEX_LIST.append(np.clip(t, 0, 255).astype(np.float32))
    return len(TEX_LIST) - 1


def faces(b, top, side=None, bottom=None):
    FACE_TEX[b] = (top, top if side is None else side, top if bottom is None else bottom)


_gt, _sn = t_grass_top(), t_snow()
TX_DIRT = tex(t_dirt())
TX_SNOW = tex(_sn)
TX_PLANKS = tex(t_planks())
TX_STONE = tex(t_stone())
TX_SAND = tex(t_sand())
faces(GRASS, tex(_gt), tex(t_grass_side(_gt)), TX_DIRT)
faces(SNOW_GRASS, TX_SNOW, tex(t_grass_side(_sn)), TX_DIRT)
faces(SNOW, TX_SNOW)
faces(DIRT, TX_DIRT)
faces(STONE, TX_STONE)
faces(COBBLE, tex(t_cobble()))
faces(PLANKS, TX_PLANKS)
_lt = tex(t_log_top())
faces(LOG, _lt, tex(t_log_side()), _lt)
faces(LEAVES, tex(t_leaves()))
faces(SAND, TX_SAND)
faces(BRICKS, tex(t_bricks()))
faces(BEDROCK, tex(t_bedrock()))
faces(WATER, tex(t_water()))
faces(GRAVEL, tex(t_gravel()))
_sst = tex(noisy((220, 206, 150), 4))
faces(SANDSTONE, _sst, tex(t_sandstone_side()), _sst)
faces(COAL_ORE, tex(t_ore((34, 34, 36))))
faces(IRON_ORE, tex(t_ore((214, 172, 140))))
faces(GOLD_ORE, tex(t_ore((250, 214, 60))))
faces(DIAMOND_ORE, tex(t_ore((96, 236, 226))))
_bt = tex(t_log_top((222, 206, 160), (200, 184, 140), (214, 212, 200)))
faces(BIRCH_LOG, _bt, tex(t_birch_side()), _bt)
faces(BIRCH_LEAVES, tex(t_leaves((104, 156, 62), (66, 108, 40))))
faces(BIRCH_PLANKS, tex(t_planks((206, 186, 132))))
_ct = tex(t_cactus_top())
faces(CACTUS, _ct, tex(t_cactus_side()), _ct)
faces(CLAY, tex(noisy((160, 166, 180), 6)))
faces(STONE_BRICKS, tex(t_stone_bricks()))
faces(MOSSY_COBBLE, tex(t_mossy()))
faces(OBSIDIAN, tex(t_obsidian()))
faces(ICE, tex(t_ice()))
faces(CRAFT_TABLE, tex(t_table_top()), tex(t_table_side()), TX_PLANKS)
_ft = tex(noisy((130, 130, 130), 8))
faces(FURNACE, _ft, tex(t_furnace_side()), _ft)
faces(BOOKSHELF, TX_PLANKS, tex(t_bookshelf_side()), TX_PLANKS)
faces(PUMPKIN, tex(t_pumpkin_top()), tex(t_pumpkin_side()), tex(noisy((200, 116, 26), 8)))
faces(IRON_BLOCK, tex(t_metal((222, 222, 222))))
faces(GOLD_BLOCK, tex(t_metal((246, 206, 64))))
faces(DIAMOND_BLOCK, tex(t_metal((100, 226, 218))))
for _b, _c in ((WOOL_WHITE, (232, 232, 232)), (WOOL_RED, (176, 46, 40)),
               (WOOL_ORANGE, (232, 124, 40)), (WOOL_YELLOW, (238, 206, 60)),
               (WOOL_GREEN, (90, 140, 40)), (WOOL_BLUE, (52, 66, 160)),
               (WOOL_PURPLE, (122, 50, 170)), (WOOL_BLACK, (34, 32, 36))):
    faces(_b, tex(t_wool(_c)))
atlas = np.clip(np.array(TEX_LIST, np.float32), 0, 255)

# трещины на копаемом блоке: 10 стадий
CRACK = np.zeros((10, TEX, TEX), bool)
_crack_px = []
_cr = np.random.RandomState(77)
for _ in range(7):
    x, y = 7.5, 7.5
    a = _cr.uniform(0, 2 * math.pi)
    for _s in range(14):
        a += _cr.uniform(-0.8, 0.8)
        x, y = x + math.cos(a), y + math.sin(a)
        p = (int(y) % TEX, int(x) % TEX)
        if p not in _crack_px:
            _crack_px.append(p)
for _st in range(10):
    for p in _crack_px[:int(len(_crack_px) * (_st + 1) / 10)]:
        CRACK[_st][p] = True

# ------------------------------------------------------------------- МИР ---
SX, SY, SZ = 256, 48, 256          # размер мира (x, высота, z)
SEA = 14
# массив с рамкой в 1 блок: лучи, вылетевшие из мира, упираются в OUTSIDE
world_p = np.zeros((SX + 2, SY + 2, SZ + 2), np.uint8)
world_p[0, :, :] = world_p[-1, :, :] = OUTSIDE
world_p[:, 0, :] = world_p[:, -1, :] = OUTSIDE
world_p[:, :, 0] = world_p[:, :, -1] = OUTSIDE
world = world_p[1:-1, 1:-1, 1:-1]   # вид без рамки: world[x, y, z]
WF = world_p.reshape(-1)            # плоский вид для лучей
STR_X, STR_Y = (SY + 2) * (SZ + 2), SZ + 2

# Поле расстояний: DF[клетка] = расстояние (по Чебышёву) до ближайшего
# непустого блока, но не больше DF_K. Куб радиуса DF-1 вокруг клетки
# гарантированно пуст, и луч может пролететь его за один шаг.
DF_K = 8
DF = np.zeros(world_p.shape, np.uint8)
DFF = DF.reshape(-1)


def compute_df(sub):
    m = sub != 0
    D = (~m).astype(np.uint8)
    for _ in range(DF_K - 1):
        n = m.copy()
        n[1:] |= m[:-1]
        n[:-1] |= m[1:]
        m = n.copy()
        m[:, 1:] |= n[:, :-1]
        m[:, :-1] |= n[:, 1:]
        n = m.copy()
        n[:, :, 1:] |= m[:, :, :-1]
        n[:, :, :-1] |= m[:, :, 1:]
        m = n
        D += ~m
    return D


def update_df(x, y, z):
    """Пересчитать поле расстояний вокруг изменённого блока."""
    c = (x + 1, y + 1, z + 1)
    sh = world_p.shape
    lo = [max(0, c[i] - 2 * DF_K) for i in range(3)]
    hi = [min(sh[i], c[i] + 2 * DF_K + 1) for i in range(3)]
    D = compute_df(world_p[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]])
    il = [max(0, c[i] - DF_K) for i in range(3)]
    ih = [min(sh[i], c[i] + DF_K + 1) for i in range(3)]
    DF[il[0]:ih[0], il[1]:ih[1], il[2]:ih[2]] = D[il[0] - lo[0]:ih[0] - lo[0],
                                                   il[1] - lo[1]:ih[1] - lo[1],
                                                   il[2] - lo[2]:ih[2] - lo[2]]


def _grid(shape, cell, seed):
    r = np.random.RandomState(seed)
    return r.random_sample([s // cell + 2 for s in shape]).astype(np.float32)


def _interp(g, ranges, cell):
    out = g
    for ax, idx in enumerate(ranges):
        p = (np.asarray(idx) + 0.5) / cell
        i0 = np.floor(p).astype(int)
        f = p - i0
        f = (f * f * (3 - 2 * f)).astype(np.float32)
        a = np.take(out, i0, axis=ax)
        b = np.take(out, i0 + 1, axis=ax)
        sh = [1] * out.ndim
        sh[ax] = len(idx)
        f = f.reshape(sh)
        out = a * (1 - f) + b * f
    return out


def _smooth(shape, cell, seed):
    return _interp(_grid(shape, cell, seed), [np.arange(s) for s in shape], cell)


def generate_world(seed=7):
    world[:] = AIR
    cont = np.clip((_smooth((SX, SZ), 56, seed) - 0.5) * 2.4 + 0.5, 0, 1)
    n2 = _smooth((SX, SZ), 22, seed + 1)
    n3 = _smooth((SX, SZ), 9, seed + 2)
    n4 = _smooth((SX, SZ), 3, seed + 3)
    mnt = np.clip((_smooth((SX, SZ), 44, seed + 4) - 0.52) * 4, 0, 1)
    hf = 5 + 17 * cont + 6 * n2 + 3 * n3 + 1.2 * n4 + mnt ** 2 * 18 * (0.4 + n3)
    h = np.clip(hf, 3, SY - 9).astype(int)
    temp = _smooth((SX, SZ), 64, seed + 5)
    forest = _smooth((SX, SZ), 30, seed + 6)
    bottom = _smooth((SX, SZ), 7, seed + 7)

    ys = np.arange(SY)[None, :, None]
    hh = h[:, None, :]
    top_y = h - 1
    desert = (temp > 0.6) & (top_y > SEA + 1) & (top_y < 28)
    beach = top_y <= SEA + 1
    under = top_y < SEA
    snowy = top_y >= 31
    rocky = top_y >= 35
    # колонки по слоям
    world[ys < hh - 4] = STONE
    sub = (ys >= hh - 4) & (ys < hh - 1)
    top = ys == hh - 1
    col_sub = np.full((SX, SZ), DIRT, np.uint8)
    col_top = np.full((SX, SZ), GRASS, np.uint8)
    col_top[snowy] = SNOW_GRASS
    col_top[rocky] = SNOW
    col_sub[rocky] = STONE
    col_top[desert] = SAND
    col_sub[desert] = SANDSTONE
    col_top[beach] = SAND
    col_sub[beach] = SAND
    col_top[under & (bottom > 0.62)] = GRAVEL
    col_top[under & (bottom < 0.3)] = CLAY
    world[:] = np.where(sub, col_sub[:, None, :], world)
    world[:] = np.where(top, col_top[:, None, :], world)
    # вода и лёд
    water = (ys >= hh) & (ys <= SEA)
    world[water] = WATER
    cold = (temp < 0.33)[:, None, :]
    world[water & (ys == SEA) & cold] = ICE

    # пещеры (по слоям, чтобы не тратить много памяти)
    g1, g2 = _grid((SX, SY, SZ), 8, seed + 8), _grid((SX, SY, SZ), 4, seed + 9)
    yr, zr = np.arange(SY), np.arange(SZ)
    for x0 in range(0, SX, 32):
        xr = np.arange(x0, min(SX, x0 + 32))
        cav = _interp(g1, (xr, yr, zr), 8) * 0.7 + _interp(g2, (xr, yr, zr), 4) * 0.3
        sl = world[x0:x0 + len(xr)]
        carve = (cav > 0.66) & (ys > 1) & (ys < hh[x0:x0 + len(xr)] - 3)
        sl[carve] = AIR

    # руды
    r = np.random.RandomState(seed + 10)
    stone = world == STONE
    for ore, p, ymax in ((COAL_ORE, 0.012, 44), (IRON_ORE, 0.007, 30),
                         (GOLD_ORE, 0.0025, 16), (DIAMOND_ORE, 0.0016, 11)):
        m = (r.random_sample(world.shape) < p) & (ys < ymax)
        grow = m.copy()                      # жилы по 2-4 блока
        grow[1:] |= m[:-1] & (r.random_sample((SX - 1, SY, SZ)) < 0.6)
        grow[:, 1:] |= m[:, :-1] & (r.random_sample((SX, SY - 1, SZ)) < 0.4)
        grow[:, :, 1:] |= m[:, :, :-1] & (r.random_sample((SX, SY, SZ - 1)) < 0.6)
        world[grow & stone] = ore
        stone &= ~grow
    world[:, 0, :] = BEDROCK
    world[:, 1, :][r.random_sample((SX, SZ)) < 0.5] = BEDROCK

    # деревья
    for _ in range(int(SX * SZ / 14)):
        x, z = r.randint(3, SX - 3), r.randint(3, SZ - 3)
        y = h[x, z]
        dens = forest[x, z]
        if r.random_sample() > dens * dens * 1.6:
            continue                         # леса гуще, на лугах — редкие деревья
        if world[x, y - 1, z] != GRASS or y + 8 >= SY:
            continue
        th = r.randint(4, 7)
        if (world[x, y:y + th, z] != AIR).any() or \
                (world[x - 2:x + 3, y + th - 2:y + th + 2, z - 2:z + 3] != AIR).any():
            continue
        birch = dens > 0.55 and r.random_sample() < 0.6
        leaf, log = (BIRCH_LEAVES, BIRCH_LOG) if birch else (LEAVES, LOG)
        for dy in range(-2, 2):
            rad = 2 if dy < 0 else 1
            for dx in range(-rad, rad + 1):
                for dz in range(-rad, rad + 1):
                    if abs(dx) == rad and abs(dz) == rad and (dy == 1 or r.random_sample() < 0.5):
                        continue
                    world[x + dx, y + th + dy, z + dz] = leaf
        world[x, y + th + 1, z] = leaf
        world[x, y:y + th, z] = log
    # кактусы
    for _ in range(int(SX * SZ / 30)):
        x, z = r.randint(2, SX - 2), r.randint(2, SZ - 2)
        y = h[x, z]
        if not desert[x, z] or world[x, y - 1, z] != SAND:
            continue
        if (world[x - 1:x + 2, y:y + 3, z - 1:z + 2] != AIR).any():
            continue
        world[x, y:y + r.randint(1, 4), z] = CACTUS
    # тыквы
    for _ in range(int(SX * SZ / 900)):
        x, z = r.randint(1, SX - 1), r.randint(1, SZ - 1)
        y = h[x, z]
        if world[x, y - 1, z] == GRASS and world[x, y, z] == AIR:
            world[x, y, z] = PUMPKIN
    return h


HEIGHTS = generate_world()
loading("Подготовка рендера...")
DF[:] = compute_df(world_p)

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
    update_df(x, y, z)


# ---------------------------------------------------------------- ИГРОК ----
def find_spawn():
    cx, cz = SX // 2, SZ // 2
    for rad in range(0, max(SX, SZ) // 2):
        for x in range(cx - rad, cx + rad + 1):
            for z in (cz - rad, cz + rad) if abs(x - cx) != rad else range(cz - rad, cz + rad + 1):
                if 0 <= x < SX and 0 <= z < SZ:
                    y = HEIGHTS[x, z]
                    if world[x, y - 1, z] == GRASS and y + 3 < SY and (world[x, y:, z] == AIR).all():
                        return x + 0.5, z + 0.5
    return cx + 0.5, cz + 0.5


spawn_x, spawn_z = find_spawn()
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

# ------------------------------------------------------------ ИНВЕНТАРЬ ----
inv = [None] * 36              # 0..8 — хотбар, 9..35 — рюкзак; ячейка: [предмет, кол-во, прочность]
creative = False
selected = 0


def give_start_kit():
    for i, it in enumerate((tool_id("pick", 0), tool_id("axe", 0), tool_id("shovel", 0))):
        inv[i] = new_stack(it)
    inv[3] = new_stack(PLANKS, 16)
    inv[4] = new_stack(CRAFT_TABLE, 1)


give_start_kit()


def add_item(item, count=1, dur=None):
    """Положить предметы в инвентарь. Возвращает, сколько не влезло."""
    ms = max_stack(item)
    if ms > 1:
        for s in inv:
            if s is not None and s[0] == item and s[1] < ms:
                k = min(count, ms - s[1])
                s[1] += k
                count -= k
                if count == 0:
                    return 0
    for i in range(36):
        if inv[i] is None:
            st = new_stack(item, min(count, ms))
            if dur is not None:
                st[2] = dur
            inv[i] = st
            count -= st[1]
            if count == 0:
                return 0
    return count


def count_item(ing):
    group = ing if isinstance(ing, tuple) else (ing,)
    return sum(s[1] for s in inv if s is not None and s[0] in group)


def take_item(ing, n):
    group = ing if isinstance(ing, tuple) else (ing,)
    for i in range(35, -1, -1):
        s = inv[i]
        if n and s is not None and s[0] in group:
            k = min(n, s[1])
            s[1] -= k
            n -= k
            if s[1] == 0:
                inv[i] = None


def can_craft(rec):
    return creative or all(count_item(ing) >= n for ing, n in rec[2])


def held_item():
    s = inv[selected]
    return s[0] if s is not None else None


# --------------------------------------------------- РАЗРЕШЕНИЕ РЕНДЕРА ----
RENDER_DIV = 6 if MOBILE else 5
DIST_STEPS = (16, 24, 32, 40, 48, 64)
dist_idx = 2 if MOBILE else 4
MAX_DIST = float(DIST_STEPS[dist_idx])
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
    global ATLAS_P, SHADE_P, SKY_P, FOG_COL, CRACK_P, SUN_P
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
    CRACK_P = int(pack(np.array((127, 127, 127))))   # маска для деления цвета на 2
    SUN_P = int(pack(np.array((255, 250, 215))))
    SHADE_P = pack(np.repeat(np.linspace(0, 255, 32)[:, None], 3, axis=1))
    # небо: градиент по высоте взгляда (dy от -1 до 1)
    k = np.linspace(-1, 1, 128)[:, None]
    hor = np.array((186, 214, 245), np.float32)
    zen = np.array((96, 150, 235), np.float32)
    sky = hor + (zen - hor) * np.clip(k, 0, 1) ** 0.7
    sky[k[:, 0] < 0] = hor
    SKY_P = pack(sky)
    FOG_COL = tuple(int(c) for c in hor)


ATLAS_P = SHADE_P = SKY_P = None
CRACK_P = SUN_P = 0
FOG_COL = (186, 214, 245)
WATER_FOG = (24, 56, 120)

# яркость граней: [ось][луч идёт в минус]: X, Y (низ/верх), Z
FACE_SHADE = np.array([[0.80, 0.80], [0.5, 1.0], [0.64, 0.64]], np.float32)


def cast_rays(ox, oy, oz, dx, dy, dz, maxd, through_water=False):
    """Трассировка всех лучей сразу по полю расстояний.

    На каждом шаге луч вылетает из пустого куба радиуса DF-1 вокруг своей
    клетки: в открытом пространстве это до 15 блоков за шаг, у стен —
    ровно одна клетка (обычный DDA). Лучи, которые уже во что-то попали,
    выкидываются из массивов. Возвращает t, блок, ось грани, flat-индекс."""
    n = dx.size
    eps = np.float32(1e-6)
    dx = np.where(np.abs(dx) < eps, eps, dx).astype(np.float32)
    dy = np.where(np.abs(dy) < eps, eps, dy).astype(np.float32)
    dz = np.where(np.abs(dz) < eps, eps, dz).astype(np.float32)
    Ox, Oy, Oz = np.float32(ox + 1), np.float32(oy + 1), np.float32(oz + 1)
    gx, gy, gz = dx > 0, dy > 0, dz > 0
    sx = np.where(gx, np.float32(1), np.float32(-1))
    sy = np.where(gy, np.float32(1), np.float32(-1))
    sz = np.where(gz, np.float32(1), np.float32(-1))
    # время (от камеры) до грани куба: (c + r*s + (s<0) - O) / d = (c + r*s + k) * i
    S = [np.arange(n, dtype=np.int32),
         np.full(n, math.floor(ox) + 1, np.float32),
         np.full(n, math.floor(oy) + 1, np.float32),
         np.full(n, math.floor(oz) + 1, np.float32),
         np.zeros(n, np.float32), np.ones(n, np.int8),
         dx, dy, dz, (1 / dx).astype(np.float32), (1 / dy).astype(np.float32),
         (1 / dz).astype(np.float32), sx, sy, sz,
         (~gx).astype(np.float32) - Ox, (~gy).astype(np.float32) - Oy,
         (~gz).astype(np.float32) - Oz, gx, gy, gz]
    out_t = np.full(n, maxd, np.float32)
    out_b = np.zeros(n, np.uint8)
    out_ax = np.ones(n, np.int8)
    out_f = np.zeros(n, np.int32)
    A0, A1, A2 = np.int8(0), np.int8(1), np.int8(2)
    for it in range(int(maxd * 2) + 16):
        ids, cx, cy, cz, t, ax, dx, dy, dz, ix, iy, iz, sx, sy, sz, kx, ky, kz, gx, gy, gz = S
        f = (cx * STR_X + cy * STR_Y + cz).astype(np.int32)
        if through_water:
            b = WF[f]
            solid = (b != 0) & (b != WATER)
            d = np.maximum(DFF[f], 1)
        else:
            d = DFF[f]
            solid = d == 0
        if it == 0:                      # стартовую клетку не проверяем
            solid[:] = False
            d = np.maximum(d, 1)
        done = solid | (t > maxd)
        if done.any():
            di = ids[done]
            fd = f[done]
            out_t[di] = np.minimum(t[done], maxd)
            out_b[di] = np.where(solid[done], WF[fd], 0)
            out_ax[di] = ax[done]
            out_f[di] = fd
            keep = ~done
            if not keep.any():
                break
            S = [v[keep] for v in S]
            ids, cx, cy, cz, t, ax, dx, dy, dz, ix, iy, iz, sx, sy, sz, kx, ky, kz, gx, gy, gz = S
            d = d[keep]
        r = d.astype(np.float32)
        ex = cx + r * sx                 # клетка за гранью куба по каждой оси
        ey = cy + r * sy
        ez = cz + r * sz
        tx = (ex + kx) * ix
        ty = (ey + ky) * iy
        tz = (ez + kz) * iz
        tn = np.minimum(np.minimum(tx, ty), tz)
        m0 = tx == tn
        m1 = (ty == tn) & ~m0
        m2 = ~(m0 | m1)
        t = tn                           # tx..tz уже абсолютные времена
        px = Ox + dx * t
        py = Oy + dy * t
        pz = Oz + dz * t
        S[1] = np.where(m0, ex, np.where(gx, np.floor(px), np.ceil(px) - 1))
        S[2] = np.where(m1, ey, np.where(gy, np.floor(py), np.ceil(py) - 1))
        S[3] = np.where(m2, ez, np.where(gz, np.floor(pz), np.ceil(pz) - 1))
        S[4] = t
        S[5] = np.where(m0, A0, np.where(m1, A1, A2))
    return out_t, out_b, out_ax, out_f


target = None        # ((x, y, z) блока, (x, y, z) соседней пустой клетки)
mine_stage = -1      # стадия трещин на целевом блоке (-1 — нет)
anim_t = 0.0


def render_world():
    fx, fy, fz = math.cos(pitch) * math.cos(yaw), math.sin(pitch), math.cos(pitch) * math.sin(yaw)
    rx, rz = -math.sin(yaw), math.cos(yaw)
    ux, uy, uz = -math.sin(pitch) * math.cos(yaw), math.cos(pitch), -math.sin(pitch) * math.sin(yaw)
    dx = fx + rx * SXF + ux * SYF
    dy = fy + uy * SYF
    dz = fz + rz * SXF + uz * SYF
    inv_ = 1.0 / np.sqrt(dx * dx + dy * dy + dz * dz)
    dx *= inv_
    dy *= inv_
    dz *= inv_
    ox, oy, oz = pos[0], pos[1] + EYE + bob_offset(), pos[2]
    oy = min(oy, SY - 0.01)
    underwater = get_block(int(math.floor(ox)), int(math.floor(oy)), int(math.floor(oz))) == WATER
    maxd = min(MAX_DIST, 14.0) if underwater else MAX_DIST

    t, b, ax, flat = cast_rays(ox, oy, oz, dx, dy, dz, maxd, underwater)
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
        col[sun] = SUN_P
        C[sky] = col
        if underwater:
            F[sky] = 255

    tf = -1
    if target is not None:
        (tx_, ty_, tz_), _ = target
        tf = (tx_ + 1) * STR_X + (ty_ + 1) * STR_Y + (tz_ + 1)

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
        wat = bh == WATER
        if wat.any():                                    # вода "течёт"
            ui[wat] = (ui[wat] + int(anim_t * 3)) % TEX
            vi[wat] = (vi[wat] + int(anim_t * 1.3)) % TEX
        is_y = axh == 1
        kind = np.where(is_y, np.where(hdy < 0, 0, 2), 1)
        ti = FACE_TEX[bh, kind]
        ch = ATLAS_P[ti, vi, ui]
        if mine_stage >= 0 and tf >= 0:                  # трещины
            cm = (fh == tf)
            if cm.any():
                cm &= CRACK[mine_stage][vi, ui]
                ch[cm] = (ch[cm] >> 1) & CRACK_P

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
        f0 = maxd * (0.15 if underwater else FOG_START_K)
        F[hit] = (np.clip((th - f0) / (maxd - f0), 0, 1) * 255).astype(np.uint8)

    # рамка вокруг выбранного блока: контур его области на экране
    if tf >= 0:
        Sm = ((flat == tf) & hit).reshape(RW, RH)
        if Sm.any():
            inner = Sm.copy()
            inner[1:, :] &= Sm[:-1, :]
            inner[:-1, :] &= Sm[1:, :]
            inner[:, 1:] &= Sm[:, :-1]
            inner[:, :-1] &= Sm[:, 1:]
            edge = (Sm & ~inner).reshape(-1)
            C[edge] = 0
            L[edge] = WHITE

    pygame.surfarray.blit_array(small, C.reshape(RW, RH))
    pygame.surfarray.blit_array(light_surf, L.reshape(RW, RH))
    small.blit(light_surf, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    fog_surf.fill((WATER_FOG if underwater else FOG_COL) + (255,))
    fa = pygame.surfarray.pixels_alpha(fog_surf)
    fa[...] = F.reshape(RW, RH)
    del fa
    small.blit(fog_surf, (0, 0))
    if underwater:
        small.fill((150, 185, 255), special_flags=pygame.BLEND_RGB_MULT)
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
        if bl != AIR and bl != WATER:
            return tuple(c), prev


# ---------------------------------------------------------------- ФИЗИКА ---
def collides(x, y, z):
    for bx in range(int(math.floor(x - PW)), int(math.floor(x + PW)) + 1):
        for by in range(int(math.floor(y)), int(math.floor(y + PH - 1e-6)) + 1):
            for bz in range(int(math.floor(z - PW)), int(math.floor(z + PW)) + 1):
                bl = get_block(bx, by, bz)
                if bl != AIR and bl != WATER:
                    return True
    return False


def in_water():
    x, y, z = pos
    return get_block(int(math.floor(x)), int(math.floor(y + 0.5)), int(math.floor(z))) == WATER


def move_player(dx, dz, dy_fly, dt, up):
    """Возвращает True, если упёрлись в стену по горизонтали."""
    global vel_y, on_ground
    blocked = False
    swim = in_water() and not flying
    if swim:
        dx, dz = dx * 0.55, dz * 0.55
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
        if swim:
            vel_y = max(vel_y - 9 * dt, -2.5)
            if up:
                vel_y = min(vel_y + 24 * dt, 3.2)
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


def break_time(b, item):
    """Время добычи блока и выпадет ли он."""
    hard = HARD.get(b, 1.0)
    tk, tier = tool_info(item)
    need = NEED_TIER.get(b, -1)
    ok = need < 0 or (tk == "pick" and tier >= need)
    tm = hard
    if tk is not None and tk == TOOL_FOR.get(b):
        tm /= TIER_SPEED[tier]
    if not ok:
        tm *= 2.5
    return max(0.05, tm), ok


def finish_break(c):
    x, y, z = c
    b = int(world[x, y, z])
    if b in (AIR, WATER, BEDROCK):
        return
    # если рядом вода — она затекает в яму
    nb = (get_block(x + 1, y, z), get_block(x - 1, y, z), get_block(x, y, z + 1),
          get_block(x, y, z - 1), get_block(x, y + 1, z))
    set_block(x, y, z, WATER if WATER in nb else AIR)
    if creative:
        return
    item = held_item()
    _, ok = break_time(b, item)
    if ok:
        add_item(DROPS.get(b, b), 1)
    tk, _ = tool_info(item)
    if tk is not None:
        s = inv[selected]
        s[2] -= 1
        if s[2] <= 0:
            inv[selected] = None
            invalidate_hotbar()


def do_place():
    global hand_swing
    hand_swing = 1.0
    if target is None:
        return
    s = inv[selected]
    if s is None or s[0] >= TOOL_BASE:
        return
    _, c = target
    if not (0 <= c[0] < SX and 0 <= c[1] < SY and 0 <= c[2] < SZ):
        return
    if world[c] not in (AIR, WATER) or (s[0] != WATER and player_hits_cell(c)):
        return
    set_block(c[0], c[1], c[2], s[0])
    if not creative:
        s[1] -= 1
        if s[1] <= 0:
            inv[selected] = None
    invalidate_hotbar()


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
    for org, A, B, tx, shade in ((o, X, Y, top, 1.0), (o + X, Y, Zd, side, 0.62),
                                 (o + Y, X, Zd, side, 0.8)):
        det = A[0] * B[1] - A[1] * B[0]
        ddx, ddy = xx - org[0], yy - org[1]
        s = (ddx * B[1] - ddy * B[0]) / det
        tt = (A[0] * ddy - A[1] * ddx) / det
        m = (s >= 0) & (s < 1) & (tt >= 0) & (tt < 1)
        u = np.clip((s * TEX).astype(int), 0, TEX - 1)
        v = np.clip((tt * TEX).astype(int), 0, TEX - 1)
        out[m, :3] = atlas[tx][v[m], u[m]] * shade
        out[m, 3] = 255
    arr = np.ascontiguousarray(np.clip(out, 0, 255).astype(np.uint8))
    return pygame.image.frombuffer(arr.tobytes(), (S, S), "RGBA").convert_alpha()


def _seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    k = np.clip(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy), 0, 1)
    return np.hypot(px - ax - k * vx, py - ay - k * vy)


def make_tool_sprite(item):
    """Пиксельный 16x16 спрайт инструмента (рисуется формулами)."""
    kind, tier = tool_info(item)
    yy, xx = np.mgrid[0:16, 0:16].astype(np.float32) + 0.5
    head = np.zeros((16, 16), bool)
    if kind == "pick":
        stick = _seg_dist(xx, yy, 2.5, 13.5, 11.0, 5.0) < 0.8
        pts = [(1 - s) ** 2 * np.array((3.0, 3.5)) + 2 * s * (1 - s) * np.array((14.5, 1.5))
               + s ** 2 * np.array((12.5, 13.0)) for s in np.linspace(0, 1, 24)]
        for i in range(len(pts) - 1):
            w = 1.45 - 0.7 * abs(i / (len(pts) - 2) - 0.5) * 2
            head |= _seg_dist(xx, yy, *pts[i], *pts[i + 1]) < w
    elif kind == "axe":
        stick = _seg_dist(xx, yy, 2.5, 13.5, 12.5, 3.5) < 0.8
        ux, uy = 0.7071, -0.7071
        vx, vy = -0.7071, -0.7071
        qx, qy = xx - 11.0, yy - 5.0
        al, ac = qx * ux + qy * uy, qx * vx + qy * vy
        head = (ac > -2.2) & (ac < 6.0) & (np.abs(al) < 1.6 + 0.5 * np.maximum(ac, 0))
    else:
        stick = _seg_dist(xx, yy, 2.5, 13.5, 9.5, 6.5) < 0.8
        ux, uy = 0.7071, -0.7071
        qx, qy = xx - 11.4, yy - 4.6
        al, ac = qx * ux + qy * uy, qx * -uy + qy * ux
        head = ((al / 4.2) ** 2 + (ac / 3.0) ** 2 < 1) | ((np.abs(ac) < 2.9) & (al < 0) & (al > -2.6))
    out = np.zeros((16, 16, 4), np.float32)
    out[stick, :3] = (112, 80, 42)
    out[stick, 3] = 255
    hc = np.array(TIER_COLORS[tier], np.float32)
    out[head, :3] = hc
    out[head, 3] = 255
    edge = head.copy()
    inner = head.copy()
    inner[1:] &= head[:-1]
    inner[:-1] &= head[1:]
    inner[:, 1:] &= head[:, :-1]
    inner[:, :-1] &= head[:, 1:]
    edge &= ~inner
    out[edge, :3] = hc * (0.42 if hc.mean() > 180 else 0.6)
    hl = inner & (xx - yy < 3) & (xx - yy > 0.5)       # блик
    out[hl, :3] = np.minimum(hc * 1.25 + 20, 255)
    arr = np.ascontiguousarray(np.clip(out, 0, 255).astype(np.uint8))
    return pygame.image.frombuffer(arr.tobytes(), (16, 16), "RGBA").convert_alpha()


_TOOL_SPRITES = {}
_ICONS = {}


def get_icon(item, size):
    key = (item, size)
    if key not in _ICONS:
        if item >= TOOL_BASE:
            if item not in _TOOL_SPRITES:
                _TOOL_SPRITES[item] = make_tool_sprite(item)
            _ICONS[key] = pygame.transform.scale(_TOOL_SPRITES[item], (size, size))
        else:
            _ICONS[key] = make_block_icon(item, size)
    return _ICONS[key]


SLOT = int(72 * UI * (1.35 if MOBILE else 1))
ICON_SZ = int(SLOT * 0.72)
HAND_SZ = int(300 * UI)
font = pygame.font.SysFont(None, max(14, int(28 * UI)))
small_font = pygame.font.SysFont(None, max(14, int(26 * UI)))
big_font = pygame.font.SysFont(None, max(18, int(40 * UI)))

hotbar_rect = pygame.Rect(0, 0, SLOT * 9 + 8, SLOT + 8)
hotbar_rect.midbottom = (WIDTH // 2, HEIGHT - max(4, int(8 * UI)))
name_timer = 2.0


def hotbar_slot_at(p):
    if hotbar_rect.collidepoint(p):
        return min(8, int(p[0] - hotbar_rect.x - 4) // SLOT)
    return None


def draw_stack(surf, rect, s, icon_size):
    """Иконка предмета + количество / полоска прочности."""
    if s is None:
        return
    ic = get_icon(s[0], icon_size)
    surf.blit(ic, ic.get_rect(center=rect.center))
    if s[0] >= TOOL_BASE:
        mx = TIER_DUR[tool_info(s[0])[1]]
        if s[2] < mx:
            k = s[2] / mx
            w = int(rect.w * 0.7)
            bar = pygame.Rect(rect.x + (rect.w - w) // 2, rect.bottom - max(4, rect.h // 9), w,
                              max(2, rect.h // 18))
            pygame.draw.rect(surf, (0, 0, 0), bar)
            bar.w = max(1, int(w * k))
            pygame.draw.rect(surf, (int(255 * (1 - k)), int(255 * k), 40), bar)
    elif s[1] > 1:
        txt = small_font.render(str(s[1]), True, (255, 255, 255))
        sh = small_font.render(str(s[1]), True, (0, 0, 0))
        r = txt.get_rect(bottomright=(rect.right - 3, rect.bottom - 1))
        surf.blit(sh, r.move(1, 1))
        surf.blit(txt, r)


_hotbar_cache = {}


def invalidate_hotbar():
    _hotbar_cache.clear()


def draw_hotbar():
    key = (selected, tuple(None if s is None else tuple(s) for s in inv[:9]))
    if key not in _hotbar_cache:
        _hotbar_cache.clear()
        s = pygame.Surface(hotbar_rect.size, pygame.SRCALPHA)
        s.fill((20, 20, 20, 150))
        for i in range(9):
            r = pygame.Rect(4 + i * SLOT, 4, SLOT, SLOT)
            pygame.draw.rect(s, (110, 110, 110, 255), r, 2)
            draw_stack(s, r, inv[i], ICON_SZ)
        r = pygame.Rect(4 + selected * SLOT, 4, SLOT, SLOT)
        pygame.draw.rect(s, (255, 255, 255, 255), r.inflate(2, 2), max(2, int(4 * UI)))
        _hotbar_cache[key] = s
    screen.blit(_hotbar_cache[key], hotbar_rect)
    it = held_item()
    if name_timer > 0 and it is not None:
        txt = big_font.render(ITEM_NAMES[it], True, (255, 255, 255))
        txt.set_alpha(int(255 * min(1.0, name_timer)))
        screen.blit(txt, txt.get_rect(midbottom=(hotbar_rect.centerx, hotbar_rect.y - 6)))


def draw_crosshair():
    cx, cy = WIDTH // 2, HEIGHT // 2
    k = max(6, int(12 * UI))
    for w, col in ((max(3, int(5 * UI)), (0, 0, 0)), (max(1, int(2 * UI)), (255, 255, 255))):
        pygame.draw.line(screen, col, (cx - k, cy), (cx + k, cy), w)
        pygame.draw.line(screen, col, (cx, cy - k), (cx, cy + k), w)


def draw_hand():
    it = held_item()
    if it is None:
        return
    sw = math.sin(hand_swing * math.pi)
    bx = math.cos(walk_phase) * 16 * UI * walk_amount
    by = abs(math.sin(walk_phase)) * 16 * UI * walk_amount
    if it >= TOOL_BASE:
        icon = get_icon(it, int(HAND_SZ * 0.9))
        icon = pygame.transform.rotate(icon, -12 + sw * 35)
        x = WIDTH * (0.64 if MOBILE else 0.68) + bx - sw * 60 * UI
        y = HEIGHT - icon.get_height() * 0.78 + by + sw * 30 * UI
    else:
        icon = get_icon(it, HAND_SZ)
        x = WIDTH * (0.66 if MOBILE else 0.70) + bx - sw * 70 * UI
        y = HEIGHT - icon.get_height() * 0.62 + by + sw * 50 * UI
    screen.blit(icon, (x, y))


# ----------------------------------------------------- ОКНО ИНВЕНТАРЯ -------
IS = int(min(SLOT, (HEIGHT - 30) / 7.3))
IPAD = max(4, int(IS * 0.15))
ITB, IINFO, IBTN = int(IS * 0.7), int(IS * 0.8), int(IS * 0.8)
panel = pygame.Rect(0, 0, 9 * IS + 2 * IPAD,
                    IPAD + ITB + IPAD + 4 * IS + IINFO + IPAD + IS + IPAD + IBTN + IPAD)
panel.center = (WIDTH // 2, HEIGHT // 2)
GRID_Y = panel.y + IPAD + ITB + IPAD
INFO_Y = GRID_Y + 4 * IS
HOT_Y = INFO_Y + IINFO + IPAD
BTN_Y = HOT_Y + IS + IPAD
CATALOG = [b for b in range(1, NUM_BLOCKS)] + ALL_TOOLS
ui_state = {"tab": "inv", "held": None, "info": None, "recipe": 0, "page": 0, "ptr": (0, 0)}


def slot_rect(col, row, y0):
    return pygame.Rect(panel.x + IPAD + col * IS, int(y0 + row * IS), IS, IS)


def inv_tabs():
    tabs = [("inv", "Инвентарь"), ("craft", "Крафт")]
    if creative:
        tabs.append(("all", "Все предметы"))
    w = (panel.w - 2 * IPAD) // len(tabs)
    return [(k, n, pygame.Rect(panel.x + IPAD + i * w, panel.y + IPAD, w - 4, ITB))
            for i, (k, n) in enumerate(tabs)]


def inv_buttons():
    y = BTN_Y
    bw = int(IS * 3.2)
    mode = pygame.Rect(panel.x + IPAD, y, bw, IBTN)
    close = pygame.Rect(panel.right - IPAD - int(IS * 2.2), y, int(IS * 2.2), IBTN)
    tw = font.size("Дальность 64")[0] + 2 * IPAD
    mid = (mode.right + close.x) // 2
    minus = pygame.Rect(mid - tw // 2 - IBTN, y, IBTN, IBTN)
    plus = pygame.Rect(mid + tw // 2, y, IBTN, IBTN)
    return {"mode": mode, "minus": minus, "plus": plus, "close": close}


def info_buttons():
    """Кнопки в строке под сеткой (крафт / листание каталога)."""
    h = IINFO - 6
    y = INFO_Y + 3
    if ui_state["tab"] == "craft":
        return {"craft": pygame.Rect(panel.right - IPAD - int(IS * 2.2), y, int(IS * 2.2), h)}
    if ui_state["tab"] == "all":
        return {"prev": pygame.Rect(panel.right - IPAD - 2 * h - 6, y, h, h),
                "next": pygame.Rect(panel.right - IPAD - h, y, h, h)}
    return {}


def ui_button(surf, rect, text, on=True, active=False):
    pygame.draw.rect(surf, (90, 140, 90) if active else ((95, 95, 105) if on else (60, 60, 64)), rect)
    pygame.draw.rect(surf, (20, 20, 20), rect, 2)
    t = font.render(text, True, (255, 255, 255) if on else (150, 150, 150))
    surf.blit(t, t.get_rect(center=rect.center))


def grid_items():
    """Что лежит в сетке на текущей вкладке: список (rect, kind, index)."""
    tab = ui_state["tab"]
    out = []
    if tab == "inv":
        for i in range(27):
            out.append((slot_rect(i % 9, i // 9 + 0.5, GRID_Y), "inv", 9 + i))
    elif tab == "craft":
        for i in range(len(RECIPES)):
            out.append((slot_rect(i % 9, i // 9, GRID_Y), "rec", i))
    else:
        start = ui_state["page"] * 36
        for i, it in enumerate(CATALOG[start:start + 36]):
            out.append((slot_rect(i % 9, i // 9, GRID_Y), "cat", it))
    for i in range(9):
        out.append((slot_rect(i, 0, HOT_Y), "inv", i))
    return out


def do_craft(i):
    res, cnt, ings = RECIPES[i]
    if not can_craft(RECIPES[i]):
        return
    if not creative:
        for ing, n in ings:
            take_item(ing, n)
    left = add_item(res, cnt)
    if left:
        if ui_state["held"] is None:
            ui_state["held"] = new_stack(res, left)
        # иначе остаток теряется (инвентарь полон)
    invalidate_hotbar()


def inv_click(p):
    """Клик/касание в окне инвентаря. Возвращает False, если окно надо закрыть."""
    global creative, dist_idx, MAX_DIST
    ui_state["ptr"] = p
    if not panel.collidepoint(p):
        return False
    for k, _, r in inv_tabs():
        if r.collidepoint(p):
            ui_state["tab"] = k
            return True
    bt = inv_buttons()
    if bt["close"].collidepoint(p):
        return False
    if bt["mode"].collidepoint(p):
        creative = not creative
        if not creative and ui_state["tab"] == "all":
            ui_state["tab"] = "inv"
        return True
    if bt["minus"].collidepoint(p) or bt["plus"].collidepoint(p):
        dist_idx = max(0, min(len(DIST_STEPS) - 1, dist_idx + (1 if bt["plus"].collidepoint(p) else -1)))
        MAX_DIST = float(DIST_STEPS[dist_idx])
        return True
    ib = info_buttons()
    if "craft" in ib and ib["craft"].collidepoint(p):
        do_craft(ui_state["recipe"])
        return True
    if "prev" in ib and ib["prev"].collidepoint(p):
        ui_state["page"] = max(0, ui_state["page"] - 1)
        return True
    if "next" in ib and ib["next"].collidepoint(p):
        ui_state["page"] = min((len(CATALOG) - 1) // 36, ui_state["page"] + 1)
        return True
    held = ui_state["held"]
    for r, kind, idx in grid_items():
        if not r.collidepoint(p):
            continue
        if kind == "inv":
            s = inv[idx]
            if s is not None:
                ui_state["info"] = s[0]
            if held is None:
                inv[idx], ui_state["held"] = None, s
            elif s is None:
                inv[idx], ui_state["held"] = held, None
            elif s[0] == held[0] and s[1] < max_stack(s[0]):
                k = min(held[1], max_stack(s[0]) - s[1])
                s[1] += k
                held[1] -= k
                if held[1] <= 0:
                    ui_state["held"] = None
            else:
                inv[idx], ui_state["held"] = held, s
            invalidate_hotbar()
        elif kind == "rec":
            if ui_state["recipe"] == idx:
                do_craft(idx)
            ui_state["recipe"] = idx
        elif kind == "cat":
            ui_state["info"] = idx
            # клик по каталогу с предметом в руке — выбросить его
            ui_state["held"] = None if held is not None else new_stack(idx)
        return True
    return True


def close_inventory():
    h = ui_state["held"]
    if h is not None:
        if add_item(h[0], h[1], h[2] if h[0] >= TOOL_BASE else None) == 0:
            pass
        ui_state["held"] = None
    invalidate_hotbar()


def draw_inventory():
    shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 120))
    screen.blit(shade, (0, 0))
    pygame.draw.rect(screen, (198, 198, 198), panel)
    pygame.draw.rect(screen, (30, 30, 30), panel, 3)
    for k, name, r in inv_tabs():
        ui_button(screen, r, name, True, ui_state["tab"] == k)
    isz = int(IS * 0.74)
    tab = ui_state["tab"]
    for r, kind, idx in grid_items():
        pygame.draw.rect(screen, (139, 139, 139), r.inflate(-2, -2))
        pygame.draw.rect(screen, (60, 60, 60), r.inflate(-2, -2), 1)
        if kind == "inv":
            if r.y >= HOT_Y and idx == selected:
                pygame.draw.rect(screen, (255, 255, 255), r.inflate(-2, -2), 3)
            draw_stack(screen, r, inv[idx], isz)
        elif kind == "rec":
            rec = RECIPES[idx]
            ok = can_craft(rec)
            if idx == ui_state["recipe"]:
                pygame.draw.rect(screen, (255, 255, 255), r.inflate(-2, -2), 3)
            draw_stack(screen, r, new_stack(rec[0], rec[1]) if rec[1] > 1 else [rec[0], 1, 1 << 30], isz)
            if not ok:
                dim = pygame.Surface((r.w - 4, r.h - 4), pygame.SRCALPHA)
                dim.fill((60, 60, 60, 150))
                screen.blit(dim, (r.x + 2, r.y + 2))
        else:
            ic = get_icon(idx, isz)
            screen.blit(ic, ic.get_rect(center=r.center))
    # строка информации
    iy = INFO_Y + IINFO // 2
    ix = panel.x + IPAD + 2
    if tab == "craft":
        rec = RECIPES[ui_state["recipe"]]
        t = font.render(ITEM_NAMES[rec[0]] + ":", True, (30, 30, 30))
        screen.blit(t, t.get_rect(midleft=(ix, iy)))
        x = ix + t.get_width() + 6
        isz2 = int(IINFO * 0.8)
        for ing, n in rec[2]:
            it = ing[0] if isinstance(ing, tuple) else ing
            ic = get_icon(it, isz2)
            screen.blit(ic, ic.get_rect(midleft=(x, iy)))
            x += isz2 + 2
            have = count_item(ing)
            col = (20, 110, 20) if (have >= n or creative) else (170, 20, 20)
            t = font.render(f"{min(have, 999)}/{n}", True, col)
            screen.blit(t, t.get_rect(midleft=(x, iy)))
            x += t.get_width() + 8
    elif tab == "all":
        t = font.render(f"Стр. {ui_state['page'] + 1}/{(len(CATALOG) - 1) // 36 + 1}"
                        + (" — " + ITEM_NAMES[ui_state['info']] if ui_state['info'] else ""),
                        True, (30, 30, 30))
        screen.blit(t, t.get_rect(midleft=(ix, iy)))
    else:
        if ui_state["info"] is not None:
            t = font.render(ITEM_NAMES[ui_state["info"]], True, (30, 30, 30))
            screen.blit(t, t.get_rect(midleft=(ix, iy)))
    for k, r in info_buttons().items():
        label = {"craft": "Создать", "prev": "<", "next": ">"}[k]
        on = k != "craft" or can_craft(RECIPES[ui_state["recipe"]])
        ui_button(screen, r, label, on)
    bt = inv_buttons()
    ui_button(screen, bt["mode"], "Творчество" if creative else "Выживание", True, creative)
    ui_button(screen, bt["minus"], "-")
    ui_button(screen, bt["plus"], "+")
    t = font.render(f"Дальность {DIST_STEPS[dist_idx]}", True, (30, 30, 30))
    screen.blit(t, t.get_rect(center=((bt["minus"].right + bt["plus"].x) // 2, bt["minus"].centery)))
    ui_button(screen, bt["close"], "Закрыть")
    h = ui_state["held"]
    if h is not None:
        r = pygame.Rect(0, 0, IS, IS)
        r.center = ui_state["ptr"]
        draw_stack(screen, r, h, isz)


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
        elif self.kind == "inv":   # сетка 3x3
            q = k * 0.62
            for i in range(3):
                for j in range(3):
                    pygame.draw.rect(s, col, (c[0] - k + i * (q + k * 0.07), c[1] - k + j * (q + k * 0.07),
                                              q * 0.9, q * 0.9))
        else:   # полёт: два крыла
            pygame.draw.polygon(s, col, [(c[0], c[1] - k * 0.2), (c[0] - k, c[1] - k * 0.6), (c[0] - k * 0.6, c[1] + k * 0.5)])
            pygame.draw.polygon(s, col, [(c[0], c[1] - k * 0.2), (c[0] + k, c[1] - k * 0.6), (c[0] + k * 0.6, c[1] + k * 0.5)])
        surf.blit(s, (self.c[0] - self.r - 1, self.c[1] - self.r - 1))


BR = int(52 * UI * (1.5 if MOBILE else 1))
btn_jump = Button((WIDTH - BR - int(30 * UI), HEIGHT - BR - int(40 * UI)), BR, "up")
btn_down = Button((btn_jump.c[0] - int(BR * 2.4), btn_jump.c[1]), BR, "down")
btn_fly = Button((btn_jump.c[0], btn_jump.c[1] - int(BR * 2.4)), int(BR * 0.8), "fly")
_ir = int(BR * 0.75)
btn_inv = Button((WIDTH - _ir - int(20 * UI), _ir + int(20 * UI)), _ir, "inv")
JOY_R = int(90 * UI * (1.5 if MOBILE else 1))
JOY_HOME = (int(JOY_R * 1.5), HEIGHT - int(JOY_R * 1.4))

TAP_TIME = 0.28          # короче — "тап" (поставить блок), дольше — копать
MOVE_SLOP = 12 * UI      # смещение пальца, после которого это уже свайп
LOOK_SENS = 0.0065 / UI  # радиан на логический пиксель
CREATIVE_REPEAT = 0.22   # в творчестве блоки ломаются сразу, с таким интервалом


# ------------------------------------------------------------- ОСНОВНОЙ ЦИКЛ
def main():
    global yaw, pitch, vel_y, flying, selected, name_timer, hand_swing
    global walk_phase, walk_amount, target, on_ground, mine_stage, anim_t
    global dist_idx, MAX_DIST

    setup_resolution(RENDER_DIV)
    clock = pygame.time.Clock()
    keys = set()
    mouse_grab = False
    mouse_mining = False
    touch_used = MOBILE
    show_debug = True
    inv_open = False
    bg = None
    joy = None          # [pid, origin, current]
    look = {}           # pid -> dict(start, t0, last, moved)
    mine = {"cell": None, "p": 0.0, "cool": 0.0}
    fps_surf = None
    fps_timer = 0.0
    perf_t, perf_n, auto_res = 0.0, 0, True
    t = 0.0
    help_lines = [] if MOBILE else [
        "Клик - захватить мышь, Esc - отпустить, E - инвентарь",
        "WASD - ходьба, Пробел - прыжок, F - полёт, Shift - вниз",
        "ЛКМ (держать) - копать, ПКМ - поставить, 1-9 / колесо - предмет",
        "[ ] - дальность прорисовки, +/- качество, F3 - скрыть",
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
        selected = int(i) % 9
        name_timer = 2.0

    def set_inventory(on):
        nonlocal inv_open, bg, joy, mouse_mining
        inv_open = on
        bg = None
        joy = None
        look.clear()
        mouse_mining = False
        for b in (btn_jump, btn_fly, btn_down, btn_inv):
            b.pointers.clear()
        keys.clear()
        if on:
            if mouse_grab:
                grab(False)
        else:
            close_inventory()

    def change_dist(k):
        global dist_idx, MAX_DIST
        dist_idx = max(0, min(len(DIST_STEPS) - 1, dist_idx + k))
        MAX_DIST = float(DIST_STEPS[dist_idx])

    running = True
    while running:
        raw_dt = clock.tick(60) / 1000.0
        dt = min(raw_dt, 0.05)
        t += dt
        anim_t = t

        if auto_res and t > 2.0 and not inv_open:
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
                if inv_open:
                    if e.key in (K_e, K_ESCAPE):
                        set_inventory(False)
                    elif K_1 <= e.key <= K_9:
                        select(e.key - K_1)
                    continue
                keys.add(e.key)
                if e.key == K_ESCAPE:
                    if mouse_grab:
                        grab(False)
                    else:
                        running = False
                elif e.key == K_e:
                    set_inventory(True)
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
                elif e.key == K_LEFTBRACKET:
                    change_dist(-1)
                elif e.key == K_RIGHTBRACKET:
                    change_dist(1)
                elif K_1 <= e.key <= K_9:
                    select(e.key - K_1)
            elif e.type == KEYUP:
                keys.discard(e.key)

            elif e.type == MOUSEBUTTONDOWN and not (touch_used or getattr(e, "touch", False)):
                if e.button in (4, 5):
                    continue
                if inv_open:
                    if e.button == 1 and not inv_click(e.pos):
                        set_inventory(False)
                    continue
                if not mouse_grab:
                    slot = hotbar_slot_at(e.pos)
                    if slot is not None:
                        select(slot)
                    else:
                        grab(True)
                elif e.button == 1:
                    mouse_mining = True
                    hand_swing = 1.0
                elif e.button == 3:
                    target = pick_block()
                    do_place()
            elif e.type == MOUSEBUTTONUP and not (touch_used or getattr(e, "touch", False)):
                if e.button == 1:
                    mouse_mining = False
            elif e.type == MOUSEMOTION and not getattr(e, "touch", False):
                if inv_open:
                    ui_state["ptr"] = e.pos
                elif mouse_grab:
                    yaw += e.rel[0] * 0.0025
                    pitch = max(-1.55, min(1.55, pitch - e.rel[1] * 0.0025))
            elif e.type == EV_MOUSEWHEEL:
                select(selected - e.y)

            elif e.type in (EV_FINGERDOWN, EV_FINGERMOTION, EV_FINGERUP):
                touch_used = True
                p = (e.x * WIDTH, e.y * HEIGHT)
                pid = e.finger_id
                if inv_open:
                    if e.type == EV_FINGERDOWN:
                        if not inv_click(p):
                            set_inventory(False)
                    elif e.type == EV_FINGERMOTION:
                        ui_state["ptr"] = p
                    continue
                if e.type == EV_FINGERDOWN:
                    if btn_inv.hit(p):
                        set_inventory(True)
                        continue
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
                        look[pid] = {"start": p, "t0": t, "last": p, "moved": False}
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
                        if not L["moved"] and t - L["t0"] < TAP_TIME + 0.15:
                            target = pick_block()
                            do_place()
                    for b in (btn_jump, btn_fly, btn_down):
                        b.pointers.discard(pid)

        if inv_open:
            if bg is None:
                render_world()
                bg = screen.copy()
            screen.blit(bg, (0, 0))
            draw_inventory()
            pygame.display.flip()
            continue

        # ---- копание: держать ЛКМ или палец без движения ----
        mining = mouse_mining or any(not L["moved"] and t - L["t0"] >= TAP_TIME for L in look.values())
        target = pick_block()
        mine["cool"] = max(0.0, mine["cool"] - dt)
        mine_stage = -1
        if mining and target is not None:
            cell = target[0]
            if cell != mine["cell"]:
                mine["cell"], mine["p"] = cell, 0.0
            hand_swing = max(hand_swing, 0.5 + 0.5 * math.sin(t * 14))
            if creative:
                if mine["cool"] <= 0:
                    finish_break(cell)
                    mine["cool"] = CREATIVE_REPEAT
                    mine["cell"] = None
            else:
                b = int(world[cell])
                if b != BEDROCK:
                    tm, _ = break_time(b, held_item())
                    mine["p"] += dt / tm
                    mine_stage = min(9, int(mine["p"] * 10))
                    if mine["p"] >= 1.0:
                        finish_break(cell)
                        mine["cell"], mine["p"] = None, 0.0
                        mine_stage = -1
                        target = pick_block()
        else:
            mine["cell"], mine["p"] = None, 0.0
            if not mining:
                mine["cool"] = 0.0

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
        swim = in_water()
        if not flying and up and on_ground and not swim:
            vel_y = JUMP_V
            on_ground = False
        blocked = move_player(dxw, dzw, dy_fly, dt, up)
        # автопрыжок на ступеньку в 1 блок (удобно на телефоне), выход из воды на берег
        if blocked and not flying and ln > 0.3:
            if touch_used and on_ground:
                vel_y = JUMP_V
                on_ground = False
            elif swim and up:
                vel_y = 6.0

        moving = ln > 0.1 and (on_ground or flying)
        if moving:
            walk_phase += dt * 9
        walk_amount += ((1.0 if moving and not flying else 0.0) - walk_amount) * min(1, dt * 8)
        hand_swing = max(0.0, hand_swing - dt * 4)
        name_timer = max(0.0, name_timer - dt)

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
            btn_inv.draw(screen)
            if flying:
                btn_down.draw(screen)
            for L in look.values():          # кольцо прогресса копания
                if not L["moved"] and (mine["p"] > 0 or t - L["t0"] < TAP_TIME):
                    k = mine["p"] if mine["p"] > 0 else 0.0
                    if k > 0:
                        rr = int(26 * UI * 1.5)
                        rect = pygame.Rect(0, 0, rr * 2, rr * 2)
                        rect.center = (int(L["start"][0]), int(L["start"][1]))
                        pygame.draw.arc(screen, (255, 255, 255), rect, math.pi / 2,
                                        math.pi / 2 + 2 * math.pi * min(1, k), max(2, int(4 * UI)))

        fps_timer -= dt
        if fps_timer <= 0:
            fps_timer = 0.25
            fps_surf = font.render(
                f"FPS {clock.get_fps():.0f}  рендер {RW}x{RH}  дальность {DIST_STEPS[dist_idx]}  "
                f"XYZ {pos[0]:.1f} {pos[1]:.1f} {pos[2]:.1f}"
                f"{'  полёт' if flying else ''}{'  творчество' if creative else ''}",
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
