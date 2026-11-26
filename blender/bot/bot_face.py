"""The sprite face: its pictures, its depth order and which shape key shows which sprite.

The screen is SCREEN_W x SCREEN_H pixels. Its upper EYES_H rows are the eyes layer and the rest
the mouth layer. Every sprite is an opaque picture of its whole layer, background included.
Left and right are the avatar's own: the avatar's left eye is on the right of a picture, because
the pictures are drawn as someone facing the avatar sees them.

Plain Python, no bpy: the build, the export check and the README all read these tables.
"""

SCREEN_W, SCREEN_H = 40, 28
EYES_H = 16
MOUTH_H = SCREEN_H - EYES_H
EYE_CENTRES = (12, 28)  # picture columns the two eyes are centred on

# Characters of the pictures -> palette names. Everything but the background glows.
BACKGROUND = "night-0"
LEGEND = {".": BACKGROUND, "X": "cyan", "o": "sky", "#": "ice", "M": "magenta", "P": "pink", "O": "orange", "Y": "banana",
          "W": "white", "B": "blue"}

# --- eyes: one glyph per eye, placed on the eye centres ---------------------------------------

EYE_GLYPHS = {
    "open": ("..XXXX..",
             ".XXXXXX.",
             ".X##XXX.",
             ".X##XXX.",
             ".XXXXXX.",
             ".XXXXXX.",
             ".XXXXXX.",
             ".XXXXXX.",
             "..XXXX.."),
    "line": ("XXXXXXXX",
             "XXXXXXXX"),
    "arc": ("..XXXX..",
            ".XXXXXX.",
            "XXX..XXX",
            "XX....XX"),
    # A brow over a smaller eye; the glyph is the eye on the left of the picture, whose inner end is its right.
    "sad": ("....XXXX",
            "XXXXX...",
            "........",
            "..XXXX..",
            ".XXXXXX.",
            ".XXXXXX.",
            ".XXXXXX.",
            ".XXXXXX.",
            "..XXXX.."),
    "angry": ("OOOO....",
              "...OOOOO",
              "........",
              "..OOOO..",
              ".OOOOOO.",
              ".OOOOOO.",
              ".OOOOOO.",
              ".OOOOOO.",
              "..OOOO.."),
    "wide": ("..XXXX..",
             ".XXXXXX.",
             "XXX..XXX",
             "XX....XX",
             "XX.##.XX",
             "XX.##.XX",
             "XX....XX",
             "XXX..XXX",
             ".XXXXXX.",
             "..XXXX.."),
    "heart": (".MM..MM.",
              "MPPMMMMM",
              "MPMMMMMM",
              "MMMMMMMM",
              ".MMMMMM.",
              "..MMMM..",
              "...MM..."),
    "sleepy": ("oooooooo",
               "XXXXXXXX",
               ".XXXXXX.",
               ".XXXXXX.",
               "..XXXX.."),
    "smug": ("XXXXXXXX",
             "XXXXXXXX",
             "...XXXX.",
             "...XXXX.",
             "....XX.."),
    "cross": ("XX....XX",
              "XXX..XXX",
              ".XXXXXX.",
              "..XXXX..",
              "..XXXX..",
              ".XXXXXX.",
              "XXX..XXX",
              "XX....XX"),
    "spiral": ("YYYYYYY.",
               "Y.....Y.",
               "Y.YYY.Y.",
               "Y.Y.Y.Y.",
               "Y.Y...Y.",
               "Y.YYYYY.",
               "Y.......",
               "YYYYYYYY"),
    "squeeze": ("XX......",
                ".XXX....",
                "...XXX..",
                ".....XXX",
                "...XXX..",
                ".XXX....",
                "XX......"),
    "star": ("...YY...",
             "...YY...",
             "YYYYYYYY",
             ".YYYYYY.",
             "..YYYY..",
             ".YYYYYY.",
             ".YY..YY.",
             "YY....YY"),
    "dot": ("XXXX",
            "XXXX",
            "XXXX",
            "XXXX"),
    "cry": ("XXXXXXXX",
            "XXXXXXXX",
            "..oo....",
            "..oo....",
            "..oo....",
            "..oo....",
            "..o....."),
}

# Sprite -> (glyph of the eye on the left of the picture, glyph on the right, mirror the right one,
# rows to shift down). The left of the picture is the avatar's RIGHT eye.
EYE_SPRITES = {
    "open": ("open", "open", False, 0),
    "dot": ("dot", "dot", True, 0),
    "sleepy": ("sleepy", "sleepy", True, 2),
    "smug": ("smug", "smug", False, 1),
    "sad": ("sad", "sad", True, 0),
    "angry": ("angry", "angry", True, 0),
    "wide": ("wide", "wide", True, 0),
    "happy": ("arc", "arc", True, 0),
    "hearts": ("heart", "heart", False, 0),
    "stars": ("star", "star", True, 0),
    "dizzy": ("spiral", "spiral", True, 0),
    "crossed": ("cross", "cross", True, 0),
    "cry": ("cry", "cry", True, 0),
    "squeeze": ("squeeze", "squeeze", True, 0),
    "wink-left": ("open", "arc", True, 0),
    "wink-right": ("arc", "open", False, 0),
    "closed": ("line", "line", True, 1),
}

# --- mouths: one glyph, centred -------------------------------------------------------------------

MOUTH_SPRITES = {
    "flat": ("X........X",
             ".XXXXXXXX."),
    "smile": ("X..........X",
              "XX........XX",
              ".XXXXXXXXXX.",
              "..XXXXXXXX.."),
    "smirk": ("..........XX",
              ".........XXX",
              "XXXXXXXXXXX.",
              ".XXXXXXXX..."),
    "frown": ("..XXXXXXXX..",
              ".XXXXXXXXXX.",
              "XX........XX",
              "X..........X"),
    "wavy": ("..XX....XX....",
             ".XXXX..XXXX..X",
             "XX..XXXX..XXXX",
             "X....XX....XX."),
    "cat": ("X....XX....X",
            "X....XX....X",
            "XX..XXXX..XX",
            ".XXXX..XXXX."),
    "triangle": ("...XX...",
                 "..XXXX..",
                 ".XXXXXX.",
                 "XXXXXXXX"),
    "tongue": ("X..........X",
               "XX........XX",
               ".XXXXXXXXXX.",
               "..XXXPPPPX..",
               ".....PPPP...",
               "......PP...."),
    "big-smile": ("XXXXXXXXXXXX",
                  "XXXXXXXXXXXX",
                  ".XXXXXXXXXX.",
                  ".XXXPPPPXXX.",
                  "..XPPPPPPX..",
                  "...XXXXXX..."),
    "pressed": ("XXXXXX",
                "XXXXXX"),
    "narrow": (".XXXXXX.",
               "XX....XX",
               ".XXXXXX."),
    "wide": (".XXXXXXXXXXXX.",
             "X############X",
             "X############X",
             ".XXXXXXXXXXXX."),
    "open-mid": (".XXXXXX.",
                 "XXXXXXXX",
                 "XXXXXXXX",
                 ".XXXXXX."),
    "small-o": (".XX.",
                "X..X",
                "X..X",
                ".XX."),
    "medium-o": (".XXXX.",
                 "XX..XX",
                 "X....X",
                 "X....X",
                 "XX..XX",
                 ".XXXX."),
    "open-big": (".XXXXXXXX.",
                 "XXXXXXXXXX",
                 "XXXXXXXXXX",
                 "XXXXXXXXXX",
                 "XXXPPPPXXX",
                 ".XPPPPPPX.",
                 "..XXXXXX.."),
}
MOUTH_TOP = 2  # rows of background above every mouth glyph

NEUTRAL = {"eyes": "open", "mouth": "flat"}

# Depth order, from nearest the backing plate to nearest the viewer. A sprite further along this
# list covers the ones before it when both are shown: a blink covers an expression, and speech
# covers a smile.
ORDER = {
    "eyes": ["dot", "sleepy", "smug", "sad", "angry", "wide", "happy", "hearts", "stars", "dizzy", "crossed", "cry", "squeeze",
             "wink-left", "wink-right", "closed"],
    "mouth": ["smile", "smirk", "frown", "wavy", "cat", "triangle", "tongue", "big-smile",
              "pressed", "narrow", "wide", "open-mid", "small-o", "medium-o", "open-big"],
}
# Sprites over both layers, in front of every layer sprite, in this order.
OVERLAYS = ["lid-left", "lid-right", "blush", "bluescreen"]

# Depths in metres in front of (+) or behind (-) the screen's backing plate.
NEUTRAL_SHOWN = 0.0020
FIRST_SHOWN = 0.0035
SHOWN_STEP = 0.0006
# The weight at which a sprite driven alone crosses the plate, and at which a neutral sprite goes behind it.
CROSSOVER = 0.35
# Keys that show the same sprite have a quad each, set back from one another by this much at rest,
# so that no two faces of the mesh coincide.
COPY_STEP = 0.0001
# What an empty key moves the hidden anchor triangle by, so that no exporter or importer drops it.
EMPTY_NUDGE = 0.0001

BLUESCREEN = "bluescreen"

# --- which shape key shows what -----------------------------------------------------------------------

VISEMES = {
    "vrc.v_sil": None, "vrc.v_pp": "pressed", "vrc.v_ff": "narrow", "vrc.v_th": "narrow", "vrc.v_dd": "narrow",
    "vrc.v_kk": "open-mid", "vrc.v_ch": "wide", "vrc.v_ss": "wide", "vrc.v_nn": "narrow", "vrc.v_rr": "small-o",
    "vrc.v_aa": "open-big", "vrc.v_e": "open-mid", "vrc.v_ih": "wide", "vrc.v_oh": "medium-o", "vrc.v_ou": "small-o",
}

# MMD name -> (layer, sprite), or None where the face has nothing to show for it.
MMD = {
    "まばたき": ("eyes", "closed"), "笑い": ("eyes", "happy"), "ウィンク": ("eyes", "wink-left"), "ウィンク右": ("eyes", "wink-right"),
    "ウィンク２": ("eyes", "wink-left"), "ｳｨﾝｸ２右": ("eyes", "wink-right"), "なごみ": ("eyes", "closed"), "はぅ": ("eyes", "squeeze"),
    "びっくり": ("eyes", "wide"), "じと目": ("eyes", "sleepy"), "ｷﾘｯ": ("eyes", "angry"), "はちゅ目": ("eyes", "wide"),
    "はぁと": ("eyes", "hearts"), "星目": ("eyes", "stars"), "瞳小": ("eyes", "dot"), "ハイライト消": None,
    "あ": ("mouth", "open-big"), "い": ("mouth", "wide"), "う": ("mouth", "small-o"), "え": ("mouth", "open-mid"),
    "お": ("mouth", "medium-o"), "あ２": ("mouth", "open-big"), "ん": ("mouth", "pressed"), "▲": ("mouth", "triangle"),
    "∧": ("mouth", "frown"), "□": ("mouth", "open-big"), "ワ": ("mouth", "big-smile"), "ω": ("mouth", "cat"),
    "ω□": ("mouth", "cat"), "にやり": ("mouth", "smirk"), "にっこり": ("mouth", "smile"), "ぺろっ": ("mouth", "tongue"),
    "てへぺろ": ("mouth", "tongue"), "口角上げ": ("mouth", "smile"), "口角下げ": ("mouth", "frown"), "口横広げ": ("mouth", "wide"),
    "真面目": None, "困る": ("eyes", "sad"), "にこり": None, "怒り": ("eyes", "angry"), "上": None, "下": None,
    "照れ": ("overlay", "blush"), "涙": ("eyes", "cry"),
}

TRACKING = {"EyeClosedLeft": ("overlay", "lid-left"), "EyeClosedRight": ("overlay", "lid-right")}


def shown_depth(layer, sprite):
    """How far in front of the backing plate a sprite stands when its key is at 1."""
    if layer == "overlay":
        last = max(len(ORDER["eyes"]), len(ORDER["mouth"]))
        return FIRST_SHOWN + SHOWN_STEP * (last + OVERLAYS.index(sprite)) + (0.0004 if sprite == BLUESCREEN else 0.0)
    if sprite == NEUTRAL[layer]:
        return NEUTRAL_SHOWN
    return FIRST_SHOWN + SHOWN_STEP * ORDER[layer].index(sprite)


def hidden_depth(layer, sprite):
    """How far behind the backing plate the sprite rests, chosen so that it crosses the plate at CROSSOVER."""
    return shown_depth(layer, sprite) * CROSSOVER / (1.0 - CROSSOVER)


# What a key at 1 moves a neutral sprite back by: from NEUTRAL_SHOWN to behind the plate, crossing it at CROSSOVER.
NEUTRAL_TRAVEL = NEUTRAL_SHOWN / CROSSOVER


def shape_keys(spec_visemes, spec_mmd):
    """Every shape key of the face in export order: (name, group, layer, sprite or None).

    `layer` is None for a key that shows nothing. A key of a layer shows its sprite and hides that
    layer's neutral sprite; an overlay key only shows its sprite."""
    keys = []
    for name in spec_visemes:
        sprite = VISEMES[name]
        keys.append((name, "viseme", "mouth" if sprite else None, sprite))
    for name in ("EyeClosedLeft", "EyeClosedRight"):
        keys.append((name, "tracking") + TRACKING[name])
    for name in spec_mmd:
        target = MMD[name]
        keys.append((name, "mmd") + (target if target else (None, None)))
    for layer in ("eyes", "mouth"):
        keys.append((f"{layer}.{NEUTRAL[layer]}", "sprite", None, None))
        for sprite in ORDER[layer]:
            keys.append((f"{layer}.{sprite}", "sprite", layer, sprite))
    keys.append(("face.blush", "sprite", "overlay", "blush"))
    keys.append(("face.bluescreen", "sprite", "overlay", BLUESCREEN))
    return keys


# --- pictures -----------------------------------------------------------------------------------------


def _blank(w, h):
    return [["."] * w for _ in range(h)]


def _stamp(rows, x, y, glyph, mirror=False):
    for j, line in enumerate(glyph):
        line = line[::-1] if mirror else line
        for i, ch in enumerate(line):
            if ch != "." and 0 <= y + j < len(rows) and 0 <= x + i < len(rows[0]):
                rows[y + j][x + i] = ch


def _eye_x(glyph, right):
    w = len(glyph[0])
    left_x = EYE_CENTRES[0] - w // 2
    return SCREEN_W - left_x - w if right else left_x


def eyes_picture(sprite, half=None):
    """Rows of characters, SCREEN_W x EYES_H. `half` keeps only the 'left' or 'right' half of the picture."""
    left, right, mirror, down = EYE_SPRITES[sprite]
    rows = _blank(SCREEN_W, EYES_H)
    for name, is_right in ((left, False), (right, True)):
        glyph = EYE_GLYPHS[name]
        top = (EYES_H - len(glyph)) // 2 + down
        # A glyph is drawn for the left of the picture; on the right it is mirrored when the sprite says so.
        _stamp(rows, _eye_x(glyph, is_right), top, glyph, is_right and mirror)
    rows = ["".join(row) for row in rows]
    if half == "left":
        rows = [row[:SCREEN_W // 2] for row in rows]
    elif half == "right":
        rows = [row[SCREEN_W // 2:] for row in rows]
    return rows


def mouth_picture(sprite):
    glyph = MOUTH_SPRITES[sprite]
    rows = _blank(SCREEN_W, MOUTH_H)
    _stamp(rows, (SCREEN_W - len(glyph[0])) // 2, MOUTH_TOP, glyph)
    return ["".join(row) for row in rows]


# Where the two blush marks sit: columns (left mark; the right one mirrors it) and screen rows.
BLUSH_COLUMNS, BLUSH_ROWS = (3, 9), (14, 19)
BLUSH_ART = ("......",
             ".P.P.P",
             "P.P.P.",
             ".P.P.P",
             "......")


def bluescreen_picture():
    rows = [["B"] * SCREEN_W for _ in range(SCREEN_H)]
    face = ("WW...WW.",
            "WW..WW..",
            "....WW..",
            "....WW..",
            "....WW..",
            "....WW..",
            "WW..WW..",
            "WW...WW.")
    _stamp(rows, 4, 3, face)
    # Lines of blocky "text": runs of lit pixels with gaps for the spaces.
    for y, runs in ((14, ((4, 9), (14, 6), (21, 11))), (17, ((4, 5), (10, 12), (23, 4), (28, 6))), (20, ((4, 14), (19, 7)))):
        for x, length in runs:
            for i in range(length):
                rows[y][x + i] = "#"
                if y != 20:
                    rows[y + 1][x + i] = "#"
    # A block of checks, like the corner of a code to scan.
    for j in range(6):
        for i in range(6):
            if (i // 2 + j // 2) % 2 == 0:
                rows[3 + j][29 + i] = "W"
    for i in range(10):
        rows[24][4 + i] = "o"
        rows[25][4 + i] = "o" if i < 6 else "B"
    return ["".join(row) for row in rows]


def sprite_picture(layer, sprite):
    """(rows of characters) for any sprite, by layer."""
    if layer == "eyes":
        return eyes_picture(sprite)
    if layer == "mouth":
        return mouth_picture(sprite)
    if sprite == "lid-left":
        return eyes_picture("closed", half="right")
    if sprite == "lid-right":
        return eyes_picture("closed", half="left")
    if sprite == "blush":
        return list(BLUSH_ART)
    if sprite == BLUESCREEN:
        return bluescreen_picture()
    raise KeyError(sprite)
