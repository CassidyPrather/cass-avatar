"""Landmarks and cross-sections of the placeholder body, derived from proportions.json.

The tape measurements are barefoot; the character stands in boots, so every
floor-referenced height is raised by the boot heel. Limb lengths and landmark
heights follow the tape, the head is enlarged by `headScale` and the neck
absorbs the difference so the crown stays at the measured height.

Coordinates: metres, Z up, the character faces -Y, its left is +X.
"""

import math

from .meshkit import interp, polyline_length, superellipse

TORSO_COLUMNS = 16
LEG_COLUMNS = 12
ARM_COLUMNS = 10
TORSO_POWER = 2.4


def section_ring(z, a, bf, bb, cy, power=TORSO_POWER, columns=TORSO_COLUMNS):
    """Horizontal ring; column 0 is front centre (-Y) and columns advance toward +X."""
    points = []
    for k in range(columns):
        theta = 2.0 * math.pi * k / columns
        c, s = superellipse(math.cos(theta), math.sin(theta), power)
        points.append((a * s, cy - (bf if c > 0 else bb) * c, z))
    return points


def fit_depth(a, circumference, bias):
    """Half-depth giving a section of half-width `a` the measured circumference.

    `bias` shifts depth to the front (+) or back (-) without changing the fit.
    """
    lo, hi = 0.02, 0.3
    for _ in range(40):
        b = 0.5 * (lo + hi)
        ring = section_ring(0.0, a, b * (1 + bias), b * (1 - bias), 0.0, columns=128)
        if polyline_length(ring) < circumference:
            lo = b
        else:
            hi = b
    return 0.5 * (lo + hi)


class Layout:
    def __init__(self, prop):
        lift = prop["bootHeelHeight"]
        self.lift = lift
        self.crown_z = prop["height"] + lift
        self.neck_base_z = prop["neckBaseHeight"] + lift
        self.neck_radius = prop["neckCircumference"] / (2.0 * math.pi)
        # A head is about 13% of stature before the stylised enlargement.
        self.head_h = 0.13 * prop["height"] * prop["headScale"]
        self.chin_z = self.crown_z - self.head_h

        self.shoulder_x = 0.5 * prop["shoulderWidth"]
        self.wrist_x = self.shoulder_x + prop["shoulderToWrist"]
        self.elbow_x = self.shoulder_x + 0.52 * prop["shoulderToWrist"]
        self.arm_z = self.neck_base_z - 0.065
        # The armholes sit on the trunk's side columns, which are centred slightly behind the origin.
        self.arm_y = 0.008
        self.hand_len = 0.104
        self.knuckle_x = self.wrist_x + 0.096

        self.hip_z = prop["hipHeight"] + lift
        self.hip_x = 0.085
        self.ankle_z = 0.075 + lift
        self.knee_z = self.ankle_z + 0.49 * (self.hip_z - self.ankle_z)
        self.foot_len = prop["footLength"]
        self.heel_y = 0.040
        self.toe_y = self.heel_y - self.foot_len
        self.toe_joint_y = self.toe_y + 0.07

        # Zone borders (uv-tiles.json): each is one closed edge loop of the body.
        self.waist_z = self.hip_z + 0.14
        self.mid_thigh_z = self.hip_z - 0.17
        self.mid_calf_z = 0.5 * (self.knee_z + self.ankle_z)
        self.crotch_z = self.hip_z - 0.095

        self.armhole_rows = [self.arm_z + 0.040, self.arm_z + 0.013, self.arm_z - 0.015, self.arm_z - 0.043]
        span = self.neck_base_z - self.hip_z
        hz, nz = self.hip_z, self.neck_base_z
        collar = self.neck_radius + 0.006
        # (z, half-width, front depth, back depth, centre y), top to bottom.
        self.torso_table = [
            (nz, collar + 0.002, collar - 0.002, collar - 0.002, 0.012),
            (nz - 0.012, 0.110, 0.066, 0.066, 0.010),
            (self.armhole_rows[0], 0.160, 0.078, 0.078, 0.008),
            (self.armhole_rows[1], 0.163, 0.084, 0.084, 0.008),
            (self.armhole_rows[2], 0.163, 0.088, 0.088, 0.008),
            (self.armhole_rows[3], 0.160, 0.092, 0.090, 0.008),
            (self.arm_z - 0.070, 0.150, 0.100, 0.092, 0.007),
            self._measured(hz + 0.724 * span, 0.145, prop["bustCircumference"], 0.12, 0.006),
            self._measured(hz + 0.638 * span, 0.138, prop["underbustCircumference"], 0.04, 0.005),
            self._measured(hz + 0.517 * span, 0.136, 0.5 * (prop["underbustCircumference"] + prop["waistCircumference"]), 0.0, 0.004),
            self._measured(hz + 0.379 * span, 0.137, prop["waistCircumference"], 0.0, 0.003),
            self._measured(self.waist_z, 0.148, 0.6 * prop["waistCircumference"] + 0.4 * prop["hipCircumference"], -0.03, 0.004),
            self._measured(hz + 0.08, 0.158, 0.25 * prop["waistCircumference"] + 0.75 * prop["hipCircumference"], -0.07, 0.006),
            self._measured(hz + 0.02, 0.166, prop["hipCircumference"], -0.10, 0.008),
            self._measured(hz - 0.035, 0.166, prop["hipCircumference"] - 0.005, -0.10, 0.008),
        ]
        self.torso_rows = [row[0] for row in self.torso_table[:-1]]

        kz, az = self.knee_z, self.ankle_z
        # (z, centre x, centre y, radius x, radius y), top to bottom.
        self.leg_table = [
            (hz - 0.125, 0.088, 0.004, 0.080, 0.088),
            (self.mid_thigh_z, 0.088, 0.003, 0.073, 0.079),
            (hz - 0.24, 0.087, 0.002, 0.066, 0.070),
            (hz - 0.32, 0.086, 0.000, 0.058, 0.061),
            (kz + 0.04, self.hip_x, -0.001, 0.052, 0.054),
            (kz, self.hip_x, -0.002, 0.049, 0.051),
            (kz - 0.04, self.hip_x, 0.002, 0.047, 0.050),
            (kz - 0.095, self.hip_x, 0.008, 0.049, 0.054),
            (kz - 0.155, self.hip_x, 0.007, 0.044, 0.048),
            (self.mid_calf_z, self.hip_x, 0.006, 0.040, 0.043),
            (az + 0.115, self.hip_x, 0.003, 0.033, 0.035),
            (az + 0.045, self.hip_x, 0.001, 0.029, 0.031),
            (az, self.hip_x, 0.000, 0.029, 0.033),
        ]
        self.leg_rows = [row[0] for row in self.leg_table]

        sx, ex, wx = self.shoulder_x, self.elbow_x, self.wrist_x
        # (x, front-back radius, vertical radius), shoulder to knuckles.
        self.arm_table = [
            (sx + 0.0175, 0.046, 0.046),
            (sx + 0.07, 0.042, 0.042),
            (sx + 0.47 * (ex - sx), 0.039, 0.039),
            (sx + 0.72 * (ex - sx), 0.037, 0.037),
            (ex - 0.04, 0.036, 0.036),
            (ex, 0.035, 0.035),
            (ex + 0.04, 0.036, 0.036),
            (ex + 0.40 * (wx - ex), 0.035, 0.035),
            (ex + 0.68 * (wx - ex), 0.030, 0.029),
            (wx - 0.033, 0.027, 0.023),
            (wx, 0.026, 0.019),
        ]
        self.arm_rows = [row[0] for row in self.arm_table]
        self.hand_table = [
            (wx + 0.0225, 0.032, 0.016),
            (wx + 0.0525, 0.041, 0.015),
            (wx + 0.0825, 0.043, 0.013),
            (wx + 0.0985, 0.041, 0.011),
        ]
        # (name, base y offset, radius, length); the thumb is placed separately.
        self.fingers = [
            ("Index", -0.030, 0.0085, 0.072),
            ("Middle", -0.010, 0.0090, 0.080),
            ("Ring", 0.010, 0.0085, 0.074),
            ("Little", 0.029, 0.0075, 0.058),
        ]
        self.thumb_base = (wx + 0.034, self.arm_y - 0.030, self.arm_z - 0.004)
        self.thumb_dir = (0.60, -0.79, -0.12)
        self.thumb = ("Thumb", 0.0100, 0.062)
        # Fractions of a finger's length where its second and third bones start.
        self.finger_joints = (0.45, 0.75)

        head_scale = self.head_h / 0.27
        # The ears root on the upper sides of the skull, under the hair, so they
        # clear the hat's crown and come up through its brim.
        self.ear_root = (0.082, 0.010, self.chin_z + 0.205 * head_scale)
        self.ear_dir = (0.32, 0.04, 0.947)
        self.ear_len = 0.25
        self.eye_x = 0.041 * head_scale
        self.eye_z = self.chin_z + 0.098 * head_scale

    @staticmethod
    def _measured(z, a, circumference, bias, cy):
        b = fit_depth(a, circumference, bias)
        return (z, a, b * (1 + bias), b * (1 - bias), cy)

    # -- trunk -------------------------------------------------------------
    def torso_ring(self, z, inflate=0.0):
        a, bf, bb, cy = interp(self.torso_table, z)
        return section_ring(z, a + inflate, bf + inflate, bb + inflate, cy)

    def branch_ring(self, inflate=0.0, drop=0.0):
        """The saddle-shaped loop where the trunk splits into the legs, plus the crotch line.

        Returns (16 ring points, 3 crotch points back-to-front). Each leg's top
        loop is its half of the ring closed through the shared crotch points.
        """
        z_side = self.torso_table[-1][0]
        _, a, bf, bb, cy = self.torso_table[-1]
        ring = []
        for k in range(TORSO_COLUMNS):
            theta = 2.0 * math.pi * k / TORSO_COLUMNS
            c, s = superellipse(math.cos(theta), math.sin(theta), TORSO_POWER)
            side = abs(math.sin(theta)) ** 1.5
            z = self.crotch_z + 0.020 + (z_side - self.crotch_z - 0.020) * side - drop * (1 - side)
            tuck = 1.0 - 0.30 * (1.0 - side)
            depth = (bf if c > 0 else bb) + inflate
            ring.append(((a + inflate) * s, cy - depth * tuck * c, z))
        cz = self.crotch_z - drop
        crotch = [(0.0, 0.052 + 0.5 * inflate, cz + 0.006), (0.0, 0.004, cz), (0.0, -0.045 - 0.5 * inflate, cz + 0.006)]
        return ring, crotch

    # -- legs (authored for the left side) -----------------------------------
    def leg_centre(self, z):
        cx, cy, _, _ = interp(self.leg_table, z)
        return (cx, cy)

    def leg_ring(self, z, angles, inflate=0.0):
        cx, cy, rx, ry = interp(self.leg_table, z)
        return [(cx + (rx + inflate) * math.sin(a), cy - (ry + inflate) * math.cos(a), z) for a in angles]

    def foot_rings(self, angles, inflate=0.0, toe_point=0.0):
        """Rings sweeping from below the ankle round the heel to the toes, then the toe tip.

        (bend angle, centre y, centre z, half-width, half-height): the ring
        plane tilts from horizontal at the ankle to vertical along the foot.
        `toe_point` narrows and lengthens the toe (boots).
        """
        x = self.hip_x
        f = self.foot_len
        # The heel rests `lift` above the floor (boot heel), the ball and toes a sole's thickness above it.
        sweep = [
            (25.0, 0.004, self.ankle_z - 0.027, 0.030, 0.040),
            (55.0, -0.012, self.ankle_z - 0.040, 0.033, 0.042),
            (90.0, self.heel_y - 0.36 * f, self.lift + 0.024, 0.038, 0.026),
            (90.0, self.heel_y - 0.54 * f, self.lift + 0.009, 0.043, 0.019),
            (90.0, self.toe_joint_y, self.lift - 0.004, 0.044 - 0.25 * toe_point, 0.014),
            (90.0, self.toe_y + 0.03 - 0.3 * toe_point, self.lift - 0.007, 0.040 - 0.6 * toe_point, 0.011),
        ]
        rings = []
        for bend, cy, cz, rx, rv in sweep:
            b = math.radians(bend)
            v = (-math.cos(b), math.sin(b))
            rings.append([
                (x + (rx + inflate) * math.sin(a), cy + (rv + inflate) * math.cos(a) * v[0], cz + (rv + inflate) * math.cos(a) * v[1])
                for a in angles
            ])
        tip = (x, self.toe_y - toe_point - inflate, self.lift - 0.008)
        return rings, tip

    # -- arms (authored for the left side) ------------------------------------
    def arm_ring(self, x, inflate=0.0, table=None, power=2.0, sag=0.0):
        """Ring around the arm axis; vertex 0 is on top and the ring advances toward the front."""
        ry, rz = interp(table or self.arm_table, x)
        points = []
        for j in range(ARM_COLUMNS):
            phi = 2.0 * math.pi * j / ARM_COLUMNS
            c, s = superellipse(math.cos(phi), math.sin(phi), power)
            points.append((x, self.arm_y - (ry + inflate) * s, self.arm_z - sag + (rz + inflate) * c))
        return points
