"""Placeholder garments: sweater, shorts, boots, hat.

Each garment reaches past the border loops of the skin zones its tile hides
(uv-tiles.json `hides`), because Unity discards those zones while it is worn.
Garments reuse the body's trunk and limb topology so the shared weight field
bends them exactly like the skin underneath.
"""

import math

from .body import armhole_loop, build_branch, build_leg, build_trunk, even_leg_angles, leg_top_loop
from .face import HEAD
from .layout import section_ring


def build_sweater(mb, L):
    nz, az, hz = L.neck_base_z, L.arm_z, L.hip_z
    # (z, half-width, front depth, back depth, centre y), collar to hem.
    table = [
        (nz + 0.016, 0.070, 0.066, 0.066, 0.012),
        (nz + 0.002, 0.078, 0.072, 0.072, 0.012),
        (nz - 0.008, 0.130, 0.088, 0.088, 0.010),
        (az + 0.060, 0.188, 0.100, 0.100, 0.008),
        (az + 0.020, 0.192, 0.108, 0.108, 0.008),
        (az - 0.020, 0.192, 0.114, 0.114, 0.008),
        (az - 0.060, 0.188, 0.120, 0.118, 0.008),
        (hz + 0.40, 0.184, 0.126, 0.124, 0.008),
        (hz + 0.30, 0.180, 0.127, 0.126, 0.008),
        (hz + 0.20, 0.178, 0.127, 0.127, 0.008),
        (hz + 0.10, 0.180, 0.128, 0.130, 0.008),
        (hz + 0.02, 0.183, 0.128, 0.138, 0.008),
        (hz - 0.005, 0.182, 0.127, 0.137, 0.008),
        (hz - 0.040, 0.176, 0.122, 0.132, 0.008),
    ]
    holes = (3, 6)
    last = len(table) - 2

    def swatch(r, k):
        return "sweater-shade" if r in (0, last) else "sweater"

    grid = build_trunk(mb, [section_ring(*row) for row in table], holes, swatch)
    # Ribbing folds inward at the collar and the hem so the openings do not show through.
    collar = mb.ring(section_ring(nz + 0.004, 0.061, 0.058, 0.058, 0.012))
    mb.loft([grid[0], collar], "sweater-shade", inward=True)
    hem = mb.ring(section_ring(hz - 0.022, 0.168, 0.114, 0.124, 0.008))
    mb.loft([grid[-1], hem], "sweater-shade", inward=True)

    sx, ex, wx = L.shoulder_x, L.elbow_x, L.wrist_x
    # (x, front-back radius, vertical radius); the cuff ends past the wrist loop, over the hand.
    sleeve = [
        (sx + 0.030, 0.062, 0.060),
        (sx + 0.100, 0.058, 0.058),
        (sx + 0.190, 0.056, 0.056),
        (ex - 0.040, 0.054, 0.054),
        (ex, 0.053, 0.053),
        (ex + 0.040, 0.054, 0.054),
        (ex + 0.120, 0.053, 0.053),
        (wx - 0.075, 0.052, 0.052),
        (wx - 0.025, 0.047, 0.047),
        (wx - 0.005, 0.039, 0.039),
        (wx + 0.028, 0.037, 0.037),
    ]
    cuff = len(sleeve) - 1
    for side in (1, -1):
        mb.set_side(side)
        rings = [armhole_loop(grid, holes, side)]
        for x, _, _ in sleeve:
            sag = 0.008 * math.sin(math.pi * min(1.0, (x - sx) / (wx - sx)))
            rings.append(mb.ring(L.arm_ring(x, table=sleeve, sag=sag)))
        mb.loft(rings, lambda span, k: "sweater-shade" if span == cuff else "sweater")
        inner = mb.ring(L.arm_ring(wx + 0.018, table=[(wx + 0.018, 0.033, 0.033)]))
        mb.loft([rings[-1], inner], "sweater-shade", inward=True)
    mb.set_side(1)


def build_shorts(mb, L):
    hz = L.hip_z
    ease = 0.008
    zs = [L.waist_z + 0.012, L.waist_z - 0.020, hz + 0.08, hz + 0.02]
    grid = build_trunk(mb, [L.torso_ring(z, ease) for z in zs], None, lambda r, k: "denim-shade" if r == 0 else "denim")
    ring, crotch = build_branch(mb, L, grid[-1], "denim", inflate=ease, drop=0.010)
    # The hem ends below the mid-thigh loop, so the hips zone is covered to its border.
    leg_zs = [hz - 0.125, L.mid_thigh_z + 0.018, L.mid_thigh_z + 0.013, L.mid_thigh_z - 0.012]
    flare = {leg_zs[0]: ease + 0.001, leg_zs[1]: 0.012, leg_zs[2]: 0.013, leg_zs[3]: 0.016}
    bands = ["denim", "denim", "denim-stitch", "denim-shade"]
    for side in (1, -1):
        mb.set_side(side)
        rings = build_leg(mb, L, leg_top_loop(ring, crotch, side), leg_zs, side,
                          lambda span, k: bands[span], inflate=lambda z: flare[z])
        inner = mb.ring(L.leg_ring(L.mid_thigh_z, even_leg_angles(), 0.004))
        mb.loft([rings[-1], inner], "denim-shade", inward=True)
    mb.set_side(1)


def build_boots(mb, L):
    angles = even_leg_angles()
    mc, az = L.mid_calf_z, L.ankle_z
    ease = 0.009
    for side in (1, -1):
        mb.set_side(side)
        # Western scallop: the shaft top dips at the front and back and peaks at the sides,
        # staying above the mid-calf loop all the way round.
        def scallop(drop, grow):
            return [(p[0], p[1], mc + 0.025 + 0.035 * abs(math.sin(a)) ** 1.5 - drop)
                    for a, p in zip(angles, L.leg_ring(mc + 0.025, angles, grow))]

        rings = [mb.ring(scallop(0.0, 0.020)), mb.ring(scallop(0.012, 0.018)), mb.ring(scallop(0.018, 0.017))]
        for z, grow in ((mc - 0.005, 0.014), (az + 0.115, 0.011), (az + 0.045, ease), (az, ease)):
            rings.append(mb.ring(L.leg_ring(z, angles, grow)))
        first_foot = len(rings)
        foot, tip = L.foot_rings(angles, inflate=ease, toe_point=0.012)
        for i, points in enumerate(foot):
            if i >= 2:
                # Flatten the underside of the forefoot onto the floor (columns 7 and 8 are the bottom).
                points = [(p[0], p[1], 0.0 if j in (7, 8) else p[2]) for j, p in enumerate(points)]
            rings.append(mb.ring(points))
        toe_cap = len(rings) - 2

        def swatch(span, k, first_foot=first_foot, toe_cap=toe_cap):
            if span > first_foot and k in (6, 7, 8):
                return "boot-sole"
            if span in (0, toe_cap):
                return "boot-shade"
            return "boot-stitch" if span == 1 else "boot"

        mb.loft(rings, swatch)
        mb.cap(rings[-1], (tip[0], tip[1], 0.016), "boot-shade")
        lining = mb.ring(L.leg_ring(mc + 0.012, angles, 0.008))
        mb.loft([rings[0], lining], "boot-shade", inward=True)

        # Low block heel; the boot's own heel curve rests on it.
        x0, x1, y0, y1, h = L.hip_x - 0.030, L.hip_x + 0.030, L.heel_y + 0.012, -0.004, L.lift + 0.004
        low = mb.ring([(x0, y1 + 0.006, 0.0), (x1, y1 + 0.006, 0.0), (x1, y0 - 0.004, 0.0), (x0, y0 - 0.004, 0.0)])
        high = mb.ring([(x0, y1, h), (x1, y1, h), (x1, y0, h), (x0, y0, h)])
        mb.loft([low, high], "boot-sole")
        mb.orient_toward([mb.face(low, "boot-sole")], (0.0, 0.0, -1.0))
    mb.set_side(1)


def build_hat(mb, L):
    s = L.head_h / 0.27
    z0 = L.chin_z + 0.235 * s
    cy = 0.006
    columns = 24
    tilt = math.radians(-4.0)

    def place(a, b, dz, k):
        """Point on an ellipse of the hat, tipped back about the brim line so the fringe shows."""
        theta = 2.0 * math.pi * k / columns
        y, z = -b * math.cos(theta), dz
        return (a * math.sin(theta), cy + y * math.cos(tilt) - z * math.sin(tilt), z0 + y * math.sin(tilt) + z * math.cos(tilt))

    def ring(a, b, dz):
        return mb.ring([place(a, b, dz(k) if callable(dz) else dz, k) for k in range(columns)], HEAD)

    # Crown: band, tapering wall, pinched top.
    crown = [ring(0.090, 0.102, 0.0), ring(0.089, 0.101, 0.024), ring(0.086, 0.098, 0.065), ring(0.078, 0.092, 0.105), ring(0.050, 0.064, 0.097)]
    mb.loft(crown, lambda span, k: "hat-band" if span == 0 else "hat")
    mb.cap(crown[-1], place(0.0, 0.0, 0.085, 0), "hat-shade", weights=HEAD)

    # Brim: rolled up at the sides, dipping front and back; the ears pass through it beside the crown.
    def curl(rho):
        def dz(k):
            theta = 2.0 * math.pi * k / columns
            return rho ** 1.6 * (0.065 * math.sin(theta) ** 2 - 0.012 * math.cos(theta) ** 2)
        return dz

    spread = [0.0, 0.35, 0.70, 1.0]
    top = [crown[0]] + [ring(0.090 + 0.155 * rho, 0.102 + 0.113 * rho, curl(rho)) for rho in spread[1:]]
    mb.orient_toward(mb.loft(top, "hat"), (0.0, 0.0, 1.0))
    thickness = 0.004
    under = [ring(0.090 + 0.155 * rho, 0.102 + 0.113 * rho, lambda k, rho=rho: curl(rho)(k) - thickness) for rho in spread]
    mb.orient_toward(mb.loft(under, "hat-shade"), (0.0, 0.0, -1.0))
    mb.loft([top[-1], under[-1]], "hat-shade")
