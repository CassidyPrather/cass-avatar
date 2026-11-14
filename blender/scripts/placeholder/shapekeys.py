"""Procedural shape keys for the placeholder face.

Every name in Spec/blendshapes.json gets a delta array over the Body mesh.
Eye and brow keys re-pose the decals through `EyeState`; mouth keys move the
lip stations and let the surrounding skin, the mouth sock, the lower teeth and
the tongue follow with falloff. "Left"/"Right" are the character's (+X / -X).
All deltas stay on head and neck vertices.
"""

import math

import numpy as np

from . import face as F
from .face import BASIS_EYE, CORNER, EYE_W, basis_bot, basis_top
from .meshkit import lerp, smoothstep

SIDES = (("Left", 1), ("Right", -1))
JAW_OPEN_ANGLE = 0.17
STATIONS = 2 * CORNER + 1
T = np.array([c / CORNER for c in range(-CORNER, CORNER + 1)])
MID = 1.0 - np.abs(T) ** 2.5
COR = np.abs(T) ** 3


def _side_mask(side):
    left = np.array([smoothstep((t + 0.25) / 0.5) for t in T])
    return {1: left, -1: 1.0 - left, 0: np.ones(STATIONS)}[side]


class KeyBuilder:
    def __init__(self, face, basis):
        self.face = face
        self.P = np.array(basis, dtype=np.float64)
        self.n = len(basis)
        f = face
        s = f.scale
        self.hinge_y, self.hinge_z = 0.039 * s, f.chin_z + 0.075 * s
        self.upper = [f.lip_upper[c] for c in range(-CORNER, CORNER + 1)]
        self.lower = [f.lip_lower[c] for c in range(-CORNER, CORNER + 1)]
        self.x0 = self.P[self.upper, 0]
        self.gap = self.P[self.upper, 2] - self.P[self.lower, 2]

        # How much each vertex rides the jaw.
        self.jaw = np.zeros(self.n)
        for i, v in enumerate(self.lower):
            self.jaw[v] = 1.0 - 0.5 * abs(T[i]) ** 3
        for (r, c), v in f.grid.items():
            k = abs(c)
            if k > F.LAST_FRONT or r < F.ROW_MOUTH:
                continue
            u = F.FRONT_U[k]
            if r == F.ROW_MOUTH:
                self.jaw[v] = 0.5 * smoothstep((0.8 - u) / 0.5)
            else:
                self.jaw[v] = smoothstep((1.0 - u) / 0.5)
        self.jaw[f.bottom_pole] = 1.0
        for v, part, _, _ in f.sock:
            self.jaw[v] = {"upper": 0.0, "corner": 0.5, "lower": 1.0}[part]
        for v in f.teeth_lower:
            self.jaw[v] = 1.0
        for v, *_ in f.tongue:
            self.jaw[v] = 1.0

        # Skin that follows a lip station: (vertex, 'upper'|'lower', station index, factor).
        self.followers = []
        column_fall = {5: 0.60, 6: 0.33, 7: 0.14, 8: 0.04}
        row_fall = {F.ROW_NOSE: ("upper", 0.15), F.ROW_ABOVE_LIP: ("upper", 0.50), F.ROW_MOUTH: ("upper", 1.0),
                    F.ROW_BELOW_LIP: ("lower", 0.55), F.ROW_CHIN: ("lower", 0.20), F.ROW_CHIN_TIP: ("lower", 0.05)}
        for (r, c), v in f.grid.items():
            if r not in row_fall or abs(c) > 8 or (r == F.ROW_MOUTH and abs(c) == CORNER):
                continue
            part, factor = row_fall[r]
            station = max(-CORNER, min(CORNER, c)) + CORNER
            self.followers.append((v, part, station, factor * column_fall.get(abs(c), 1.0)))
        for v, part, c, depth in f.sock:
            self.followers.append((v, "lower" if part == "lower" else "upper", c + CORNER, {1: 0.8, 2: 0.4, 3: 0.2}[depth]))

        self.skin = sorted(set(f.grid.values()) | set(self.upper) | set(self.lower))

    def zeros(self):
        return np.zeros((self.n, 3))

    # -- eyes and brows ------------------------------------------------------
    def eyes(self, left=None, right=None):
        states = {1: left or BASIS_EYE, -1: right or BASIS_EYE}
        delta = self.zeros()
        for v, position in self.face.pose_decals(states).items():
            delta[v] = np.array(position) - self.P[v]
        return delta

    def eye(self, side, state):
        return self.eyes(left=state) if side > 0 else self.eyes(right=state)

    def both_eyes(self, state):
        return self.eyes(state, state)

    # -- mouth ---------------------------------------------------------------
    def lips(self, upper=(0, 0, 0), lower=(0, 0, 0), corner=(0, 0, 0), narrow=0.0, close=0.0, side=0):
        """Lip station offsets. `corner` is (outward, y, z); `narrow` pulls x toward the centre;
        `close` raises the lower lip by that fraction of the rest gap."""
        m = _side_mask(side)
        d_upper = np.outer(m * MID, upper)
        d_lower = np.outer(m * MID, lower)
        corner_move = np.outer(m * COR, (0.0, corner[1], corner[2]))
        corner_move[:, 0] = m * COR * np.sign(T) * corner[0] - narrow * m * self.x0
        d_lower[:, 2] += close * m * self.gap
        return d_upper + corner_move, d_lower + corner_move

    def curve(self, upper_z, lower_z, corner=(0, 0, 0)):
        """Lip offsets from explicit vertical profiles of t in [-1, 1]; corners move by `corner`."""
        d_upper, d_lower = self.lips(corner=corner)
        inner = np.abs(T) < 1.0
        d_upper[inner, 2] += np.array([upper_z(t) for t in T])[inner]
        d_lower[inner, 2] += np.array([lower_z(t) for t in T])[inner]
        return d_upper, d_lower

    def jaw_motion(self, amount, shift=(0.0, 0.0, 0.0)):
        angle = JAW_OPEN_ANGLE * amount
        y, z = self.P[:, 1] - self.hinge_y, self.P[:, 2] - self.hinge_z
        delta = self.zeros()
        delta[:, 1] = y * (math.cos(angle) - 1.0) - z * math.sin(angle)
        delta[:, 2] = y * math.sin(angle) + z * (math.cos(angle) - 1.0)
        delta += np.array(shift)
        return delta * self.jaw[:, None]

    def mouth(self, *lip_poses, jaw=0.0, shift=(0.0, 0.0, 0.0), teeth_drop=0.0):
        """Combines lip poses and jaw motion into a full delta; skin and the sock follow the lips."""
        d_upper = sum((p[0] for p in lip_poses), np.zeros((STATIONS, 3)))
        d_lower = sum((p[1] for p in lip_poses), np.zeros((STATIONS, 3)))
        delta = self.jaw_motion(jaw, shift)
        for i in range(STATIONS):
            delta[self.upper[i]] += d_upper[i]
            if 0 < i < STATIONS - 1:
                delta[self.lower[i]] += d_lower[i]
        for v, part, station, factor in self.followers:
            delta[v] += factor * (d_upper if part == "upper" else d_lower)[station]
        # Anime mouths show a band of upper teeth as soon as they open.
        for v in self.face.teeth_upper:
            delta[v, 2] -= teeth_drop
        return delta

    def radial(self, side, x, height, radius, move):
        """Moves head skin near (side*x, chin + height) with a smooth falloff.
        `move` is a vector, or a float meaning metres along the outward normal."""
        centre = np.array([side * x * self.face.scale, self.face.chin_z + height * self.face.scale])
        delta = self.zeros()
        for v in self.skin:
            p = self.P[v]
            w = smoothstep(1.0 - math.hypot(p[0] - centre[0], p[2] - centre[1]) / radius)
            if w <= 0.0:
                continue
            if isinstance(move, (int, float)):
                normal = np.array([p[0], p[1] - 0.004, 0.0])
                delta[v] = w * move * normal / np.linalg.norm(normal)
            else:
                delta[v] = w * np.array(move)
        return delta

    def tongue(self, out=0.0, up=0.0, left=0.0, roll=0.0, bend=0.0, curl=0.0, squish=0.0, flat=0.0, twist=0.0):
        delta = self.zeros()
        for v, f, lx, lz in self.face.tongue:
            fc = min(f, 1.0)
            tip = max(0.0, (fc - 0.5) / 0.5)
            angle = 0.7 * twist * fc
            dx = left * 0.007 * fc * fc - roll * 0.3 * lx - squish * 0.3 * lx + flat * 0.35 * lx
            dx += lx * (math.cos(angle) - 1.0) - lz * math.sin(angle)
            dy = -0.026 * out * f ** 1.2 + 0.002 * bend * tip + 0.005 * curl * tip * tip
            dz = out * (0.0035 * min(1.0, fc / 0.4) - 0.0035 * tip) + up * 0.006 * fc * fc
            dz += roll * 0.004 * (lx / 0.0105) ** 2 * (0.3 + 0.7 * fc) - 0.008 * bend * tip * tip + 0.008 * curl * tip * tip
            dz += 0.6 * lz * squish - 0.45 * lz * flat + lx * math.sin(angle) + lz * (math.cos(angle) - 1.0)
            delta[v] = (dx, dy, dz)
        return delta

    def neck(self, columns, move):
        """Moves the lower neck rings (never the collar loop, which borders the torso zone)."""
        delta = self.zeros()
        for ring, ring_weight in zip(self.face.neck[:3], (0.6, 1.0, 0.7)):
            for column, weight in columns.items():
                v = ring[column]
                p = self.P[v]
                if isinstance(move, (int, float)):
                    normal = np.array([p[0], p[1] - 0.011, 0.0])
                    delta[v] = ring_weight * weight * move * normal / np.linalg.norm(normal)
                else:
                    delta[v] = ring_weight * weight * np.array(move)
        return delta


def _eye_keys(kb, keys):
    def blink_line(ex):
        return -0.010 + 0.0045 * (ex / EYE_W) ** 2

    def joy_line(ex):
        return 0.0025 - 0.0075 * (ex / EYE_W) ** 2

    closed = BASIS_EYE.but(top=blink_line, bot=blink_line, lash=0.6)
    joy = BASIS_EYE.but(top=joy_line, bot=joy_line, lash=0.7)
    calm = BASIS_EYE.but(top=lambda ex: -0.004, bot=lambda ex: -0.004, lash=0.55)

    # "> <": both lash lines straighten into a chevron pointing at the nose.
    apex, high, low = (-0.011, 0.0), (0.014, 0.0115), (0.014, -0.0115)

    def stroke(end, half=0.0017):
        dx, dz = end[0] - apex[0], end[1] - apex[1]
        length = math.hypot(dx, dz)
        nx, nz = -dz / length * half, dx / length * half
        if nz < 0:
            nx, nz = -nx, -nz

        def at(s):
            x, z = lerp(apex[0], end[0], s), lerp(apex[1], end[1], s)
            return (x - nx, z - nz), (x + nx, z + nz)
        return at

    def chevron_line(ex):
        q = min(1.0, max(0.0, (ex - apex[0]) / (high[0] - apex[0])))
        return lerp(apex[1], high[1], q)

    squeezed = BASIS_EYE.but(top=chevron_line, bot=chevron_line, upper_stroke=stroke(high), lower_stroke=stroke(low))

    def round_top(ex):
        return math.sqrt(max(0.0, 0.0145 ** 2 - ex * ex))

    wide = BASIS_EYE.but(top=lambda ex: basis_top(ex) + 0.003, bot=lambda ex: basis_bot(ex) - 0.0012)
    squint = BASIS_EYE.but(top=lambda ex: basis_top(ex) - 0.0015, bot=lambda ex: min(basis_bot(ex) + 0.0045, basis_top(ex) - 0.0015))

    for name, side in SIDES:
        keys[f"EyeLookUp{name}"] = kb.eye(side, BASIS_EYE.but(look=(0.0, 0.003)))
        keys[f"EyeLookDown{name}"] = kb.eye(side, BASIS_EYE.but(look=(0.0, -0.003)))
        keys[f"EyeLookIn{name}"] = kb.eye(side, BASIS_EYE.but(look=(-0.0035, 0.0)))
        keys[f"EyeLookOut{name}"] = kb.eye(side, BASIS_EYE.but(look=(0.0035, 0.0)))
        keys[f"EyeClosed{name}"] = kb.eye(side, closed)
        keys[f"EyeDilation{name}"] = kb.eye(side, BASIS_EYE.but(pupil=1.35))
        keys[f"EyeConstrict{name}"] = kb.eye(side, BASIS_EYE.but(pupil=0.6))
        keys[f"EyeSquint{name}"] = kb.eye(side, squint)
        keys[f"EyeWide{name}"] = kb.eye(side, wide)
        keys[f"BrowPinch{name}"] = kb.eye(side, BASIS_EYE.but(brow=lambda s: (-0.004 * (1 - s), -0.002 * (1 - s))))
        keys[f"BrowLowerer{name}"] = kb.eye(side, BASIS_EYE.but(brow=lambda s: (0.0, -0.005 * (1 - 0.3 * s))))
        keys[f"BrowInnerUp{name}"] = kb.eye(side, BASIS_EYE.but(brow=lambda s: (0.0, 0.006 * (1 - s) ** 1.5)))
        keys[f"BrowOuterUp{name}"] = kb.eye(side, BASIS_EYE.but(brow=lambda s: (0.0, 0.006 * s ** 1.5)))

    keys["まばたき"] = kb.both_eyes(closed)
    keys["笑い"] = kb.both_eyes(joy)
    keys["ウィンク"] = kb.eye(1, joy)
    keys["ウィンク右"] = kb.eye(-1, joy)
    keys["ウィンク２"] = kb.eye(1, closed)
    keys["ｳｨﾝｸ２右"] = kb.eye(-1, closed)
    keys["なごみ"] = kb.both_eyes(calm)
    keys["はぅ"] = kb.both_eyes(squeezed)
    keys["びっくり"] = kb.both_eyes(wide.but(iris=0.8, scribble=1.15))
    keys["じと目"] = kb.both_eyes(BASIS_EYE.but(top=lambda ex: min(basis_top(ex), 0.005 + F.EYE_TILT * ex)))
    keys["ｷﾘｯ"] = kb.both_eyes(BASIS_EYE.but(
        top=lambda ex: 0.85 * basis_top(ex) + 0.10 * ex - 0.001, bot=lambda ex: 0.9 * basis_bot(ex) + 0.05 * ex))
    keys["はちゅ目"] = kb.both_eyes(BASIS_EYE.but(top=round_top, bot=lambda ex: -round_top(ex), iris=0.0, hilite=0.0, lash=0.35))
    keys["はぁと"] = kb.both_eyes(BASIS_EYE.but(heart=1.0, pupil=0.0))
    keys["星目"] = kb.both_eyes(BASIS_EYE.but(star=1.0, pupil=0.0))
    keys["瞳小"] = kb.both_eyes(BASIS_EYE.but(iris=0.6))
    keys["ハイライト消"] = kb.both_eyes(BASIS_EYE.but(hilite=0.0))

    keys["真面目"] = kb.both_eyes(BASIS_EYE.but(brow=lambda s: (0.0, -0.004 * (1 - s) + 0.001 * s)))
    keys["困る"] = kb.both_eyes(BASIS_EYE.but(brow=lambda s: (0.0, 0.007 * (1 - s) ** 1.2 - 0.004 * s)))
    keys["にこり"] = kb.both_eyes(BASIS_EYE.but(brow=lambda s: (0.0, 0.003 + 0.003 * math.sin(math.pi * s))))
    keys["怒り"] = kb.both_eyes(BASIS_EYE.but(brow=lambda s: (-0.003 * (1 - s), -0.008 * (1 - s) ** 1.2 + 0.004 * s)))
    keys["上"] = kb.both_eyes(BASIS_EYE.but(brow=lambda s: (0.0, 0.007)))
    keys["下"] = kb.both_eyes(BASIS_EYE.but(brow=lambda s: (0.0, -0.006)))
    keys["照れ"] = kb.both_eyes(BASIS_EYE.but(blush=1.0))
    keys["涙"] = kb.both_eyes(BASIS_EYE.but(tear=1.0))


def _tracking_mouth_keys(kb, keys):
    lips, mouth = kb.lips, kb.mouth
    jaw_open = mouth(lips(narrow=0.06), jaw=1.0, teeth_drop=0.0015)
    keys["JawOpen"] = jaw_open
    keys["JawRight"] = mouth(jaw=0.0, shift=(-0.005, 0.0, 0.0))
    keys["JawLeft"] = mouth(jaw=0.0, shift=(0.005, 0.0, 0.0))
    keys["JawForward"] = mouth(jaw=0.0, shift=(0.0, -0.004, 0.0))
    keys["JawBackward"] = mouth(jaw=0.0, shift=(0.0, 0.003, 0.0))
    keys["JawClench"] = mouth(lips(close=1.0), shift=(0.0, 0.0, 0.0008)) + kb.radial(1, 0.050, 0.040, 0.030, 0.0025) + kb.radial(-1, 0.050, 0.040, 0.030, 0.0025)
    keys["JawMandibleRaise"] = mouth(lips(lower=(0.0, -0.0015, 0.0012), close=1.0), shift=(0.0, 0.0, 0.003))

    # ARKit-style convention: this key is the difference between "jaw open" and
    # "jaw open with the lips sealed", so it undoes JawOpen on the lips only.
    seal = np.zeros(kb.n)
    for v in kb.lower:
        seal[v] = 1.0
    for (r, c), v in kb.face.grid.items():
        seal[v] = {F.ROW_MOUTH: 1.0, F.ROW_BELOW_LIP: 0.5}.get(r, 0.0)
    for v, part, _, depth in kb.face.sock:
        seal[v] = {1: 0.8, 2: 0.3, 3: 0.0}[depth] if part != "upper" else 0.0
    keys["MouthClosed"] = -kb.jaw_motion(1.0) * seal[:, None] + mouth(lips(close=1.0))

    keys["MouthRaiserUpper"] = mouth(lips(upper=(0.0, -0.003, 0.002)))
    keys["MouthRaiserLower"] = mouth(lips(lower=(0.0, -0.002, 0.0035))) + kb.radial(1, 0.0, 0.020, 0.030, (0.0, 0.0, 0.002))
    for name, side in SIDES:
        keys[f"LipSuckUpper{name}"] = mouth(lips(upper=(0.0, 0.003, -0.0012), side=side))
        keys[f"LipSuckLower{name}"] = mouth(lips(lower=(0.0, 0.003, 0.002), side=side))
        keys[f"LipSuckCorner{name}"] = mouth(lips(corner=(-0.0025, 0.003, 0.0), side=side))
        keys[f"LipFunnelUpper{name}"] = mouth(lips(upper=(0.0, -0.005, 0.003), side=side))
        keys[f"LipFunnelLower{name}"] = mouth(lips(lower=(0.0, -0.005, -0.003), side=side))
        keys[f"LipPuckerUpper{name}"] = mouth(lips(upper=(0.0, -0.005, 0.0005), corner=(0.0, -0.002, 0.0), narrow=0.2, side=side))
        keys[f"LipPuckerLower{name}"] = mouth(lips(lower=(0.0, -0.005, -0.0005), corner=(0.0, -0.002, 0.0), narrow=0.2, side=side))
        keys[f"MouthUpperUp{name}"] = mouth(lips(upper=(0.0, -0.001, 0.004), side=side))
        keys[f"MouthUpperDeepen{name}"] = mouth(lips(upper=(0.0, 0.0015, 0.0015), side=side)) + kb.radial(side, 0.020, 0.056, 0.016, (0.0, 0.002, 0.0))
        keys[f"MouthLowerDown{name}"] = mouth(lips(lower=(0.0, -0.001, -0.004), side=side))
        # These four slide a whole lip sideways, so `side` is the direction rather than a half.
        keys[f"MouthUpper{name}"] = mouth(lips(upper=(0.004 * side, 0.0, 0.0)))
        keys[f"MouthLower{name}"] = mouth(lips(lower=(0.004 * side, 0.0, 0.0)))
        keys[f"MouthCornerPull{name}"] = mouth(lips(corner=(0.006, 0.002, 0.005), side=side)) + kb.radial(side, 0.045, 0.062, 0.03, (0.0, 0.0, 0.0015))
        keys[f"MouthCornerSlant{name}"] = mouth(lips(corner=(0.0, 0.0, 0.005), side=side))
        keys[f"MouthFrown{name}"] = mouth(lips(corner=(0.001, 0.0, -0.005), side=side))
        keys[f"MouthStretch{name}"] = mouth(lips(corner=(0.006, 0.002, -0.0015), side=side))
        keys[f"MouthDimple{name}"] = mouth(lips(corner=(0.002, 0.0035, 0.0), side=side))
        keys[f"MouthPress{name}"] = mouth(lips(upper=(0.0, 0.0, -0.0005), corner=(0.0015, 0.0, 0.0), close=1.0, side=side))
        keys[f"MouthTightener{name}"] = mouth(lips(upper=(0.0, 0.001, 0.0), lower=(0.0, 0.001, 0.0), narrow=0.18, close=0.5, side=side))

        keys[f"NoseSneer{name}"] = kb.radial(side, 0.012, 0.064, 0.016, (0.0, 0.0, 0.003)) + mouth(lips(upper=(0.0, 0.0, 0.0012), side=side))
        nostril = kb.zeros()
        nostril[kb.face.grid[(F.ROW_NOSE, side)]] = (0.002 * side, -0.0008, 0.0)
        keys[f"NasalDilation{name}"] = nostril
        keys[f"NasalConstrict{name}"] = -0.75 * nostril
        keys[f"CheekSquint{name}"] = kb.radial(side, 0.045, 0.078, 0.030, (0.0, 0.0, 0.003)) + kb.eye(side, BASIS_EYE.but(bot=lambda ex: basis_bot(ex) + 0.002))
        # Centred low on the cheek so the bulge never rises in front of the eye decals.
        keys[f"CheekPuff{name}"] = kb.radial(side, 0.052, 0.046, 0.030, 0.008)
        keys[f"CheekSuck{name}"] = kb.radial(side, 0.052, 0.046, 0.030, -0.004)

        left = float(side)
        keys[f"Tongue{name}"] = kb.tongue(left=left)
        keys[f"TongueTwist{name}"] = kb.tongue(twist=left)
        flex = {2: 0.5, 3: 1.0, 4: 1.0, 5: 1.0, 6: 0.5} if side > 0 else {10: 0.5, 11: 1.0, 12: 1.0, 13: 1.0, 14: 0.5}
        keys[f"NeckFlex{name}"] = kb.neck(flex, 0.003)

    keys["TongueOut"] = kb.tongue(out=1.0)
    keys["TongueUp"] = kb.tongue(up=1.0)
    keys["TongueDown"] = kb.tongue(up=-1.0)
    keys["TongueRoll"] = kb.tongue(roll=1.0)
    keys["TongueBendDown"] = kb.tongue(bend=1.0)
    keys["TongueCurlUp"] = kb.tongue(curl=1.0)
    keys["TongueSquish"] = kb.tongue(squish=1.0)
    keys["TongueFlat"] = kb.tongue(flat=1.0)

    palate = kb.zeros()
    for v, part, _, depth in kb.face.sock:
        if part == "upper" and depth >= 2:
            palate[v, 2] = -0.002 * (depth - 1)
    keys["SoftPalateClose"] = palate
    keys["ThroatSwallow"] = kb.neck({0: 1.0, 1: 0.6, 15: 0.6, 2: 0.2, 14: 0.2}, (0.0, -0.002, 0.004))


def _viseme_and_mmd_mouth_keys(kb, keys):
    lips, mouth, curve, tongue = kb.lips, kb.mouth, kb.curve, kb.tongue
    drop = 0.0015
    keys["vrc.v_sil"] = mouth(lips(corner=(0.0, 0.0, -0.0008), close=0.7))
    keys["vrc.v_pp"] = mouth(lips(upper=(0.0, 0.0015, 0.0), lower=(0.0, 0.0015, 0.0), narrow=0.08, close=1.0))
    keys["vrc.v_ff"] = mouth(lips(upper=(0.0, 0.0, 0.002), lower=(0.0, 0.003, 0.003)), jaw=0.05, teeth_drop=drop)
    keys["vrc.v_th"] = mouth(lips(upper=(0.0, 0.0, 0.001)), jaw=0.18, teeth_drop=drop) + tongue(out=0.4, up=0.3)
    keys["vrc.v_dd"] = mouth(lips(upper=(0.0, 0.0, 0.0015)), jaw=0.15, teeth_drop=drop) + tongue(up=1.0)
    keys["vrc.v_kk"] = mouth(lips(corner=(0.002, 0.0, 0.0)), jaw=0.25, teeth_drop=drop)
    keys["vrc.v_ch"] = mouth(lips(upper=(0.0, -0.003, 0.002), lower=(0.0, -0.003, -0.002), narrow=0.2), jaw=0.12, teeth_drop=drop)
    keys["vrc.v_ss"] = mouth(lips(upper=(0.0, 0.0, 0.0015), lower=(0.0, 0.0, -0.002), corner=(0.004, 0.001, 0.0)), jaw=0.06, teeth_drop=drop)
    keys["vrc.v_nn"] = mouth(lips(lower=(0.0, 0.0, -0.001)), jaw=0.08) + tongue(up=0.6)
    keys["vrc.v_rr"] = mouth(lips(upper=(0.0, -0.003, 0.0), lower=(0.0, -0.003, 0.0), narrow=0.25), jaw=0.15)
    keys["vrc.v_aa"] = mouth(lips(upper=(0.0, 0.0, 0.001)), jaw=0.75, teeth_drop=drop)
    keys["vrc.v_e"] = mouth(lips(upper=(0.0, 0.0, 0.0015), corner=(0.004, 0.001, 0.0)), jaw=0.4, teeth_drop=drop)
    keys["vrc.v_ih"] = mouth(lips(upper=(0.0, 0.0, 0.002), corner=(0.005, 0.001, 0.001)), jaw=0.22, teeth_drop=drop)
    keys["vrc.v_oh"] = mouth(lips(upper=(0.0, -0.004, 0.001), lower=(0.0, -0.004, 0.0), narrow=0.30), jaw=0.5)
    keys["vrc.v_ou"] = mouth(lips(upper=(0.0, -0.006, 0.0005), lower=(0.0, -0.006, 0.0), narrow=0.50), jaw=0.2)

    keys["あ"] = mouth(lips(upper=(0.0, 0.0, 0.002)), jaw=0.6, teeth_drop=drop)
    keys["い"] = mouth(lips(upper=(0.0, 0.0, 0.002), lower=(0.0, 0.0, -0.002), corner=(0.005, 0.001, 0.0)), jaw=0.12, teeth_drop=drop)
    keys["う"] = mouth(lips(upper=(0.0, -0.005, 0.0), lower=(0.0, -0.005, 0.0), narrow=0.45), jaw=0.15)
    keys["え"] = mouth(lips(lower=(0.0, 0.0, -0.001), corner=(0.003, 0.001, 0.0)), jaw=0.35, teeth_drop=drop)
    keys["お"] = mouth(lips(upper=(0.0, -0.004, 0.0015), lower=(0.0, -0.004, 0.0), narrow=0.35), jaw=0.5)
    keys["あ２"] = mouth(lips(upper=(0.0, 0.0, 0.004), corner=(0.004, 0.001, 0.0)), jaw=0.85, teeth_drop=drop)
    keys["ん"] = mouth(lips(corner=(0.0, 0.0, -0.001), narrow=0.12, close=1.0))
    keys["▲"] = mouth(curve(lambda t: 0.010 * (1 - abs(t)), lambda t: -0.0035, corner=(0.003, 0.0, -0.003)))
    keys["∧"] = mouth(curve(lambda t: 0.005 * (1 - abs(t)) - 0.001, lambda t: 0.005 * (1 - abs(t)) - 0.001, corner=(0.0, 0.0, -0.004)))
    keys["□"] = mouth(curve(lambda t: 0.006, lambda t: -0.008, corner=(0.001, 0.0, 0.0)), teeth_drop=drop)
    keys["ワ"] = mouth(curve(lambda t: 0.001, lambda t: -0.011 * (1 - t * t), corner=(0.004, 0.001, 0.004)), jaw=0.25, teeth_drop=drop)

    def cat(t):
        return 0.004 * math.cos(2.0 * math.pi * t) * (1 - abs(t)) + 0.003 * abs(t) ** 3 - 0.0005

    keys["ω"] = mouth(curve(cat, cat, corner=(0.001, 0.0, 0.003)))
    keys["ω□"] = mouth(curve(cat, lambda t: cat(t) - 0.009 * (1 - t * t), corner=(0.001, 0.0, 0.003)), jaw=0.2)
    keys["にやり"] = mouth(lips(corner=(0.005, 0.001, 0.006), close=0.6, side=1), lips(corner=(0.002, 0.0, 0.002), side=-1))
    keys["にっこり"] = mouth(lips(upper=(0.0, 0.0, -0.001), lower=(0.0, 0.0, -0.001), corner=(0.004, 0.001, 0.005)))
    keys["ぺろっ"] = mouth(lips(lower=(0.0, 0.0, -0.001)), jaw=0.15) + tongue(out=0.8)
    keys["てへぺろ"] = mouth(lips(corner=(0.004, 0.001, 0.004), side=1), lips(lower=(0.0, 0.0, -0.001)), jaw=0.15) + tongue(out=0.8, left=1.0)
    keys["口角上げ"] = mouth(lips(corner=(0.0, 0.0, 0.004)))
    keys["口角下げ"] = mouth(lips(corner=(0.0, 0.0, -0.004)))
    keys["口横広げ"] = mouth(lips(corner=(0.006, 0.001, 0.0)))


def build_shape_keys(face, basis, names):
    """Returns {name: (n, 3) delta array} in the order of `names` (the spec's order)."""
    kb = KeyBuilder(face, basis)
    keys = {}
    _eye_keys(kb, keys)
    _tracking_mouth_keys(kb, keys)
    _viseme_and_mmd_mouth_keys(kb, keys)
    if set(keys) != set(names):
        raise RuntimeError(f"shape keys out of step with blendshapes.json: missing {sorted(set(names) - set(keys))}, "
                           f"extra {sorted(set(keys) - set(names))}")
    for name, delta in keys.items():
        if np.abs(delta).max() < 1e-4:
            raise RuntimeError(f"shape key {name!r} moves nothing")
    return {name: keys[name] for name in names}
