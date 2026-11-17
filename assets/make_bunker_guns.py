"""
Bunker Breakout - Blender weapon sprite generator
=================================================
Builds low-poly first-person weapons (with gloved arms) and renders each one to a
transparent PNG that the game picks up automatically:

    assets/lo_ar.png  lo_ak.png  lo_smg.png  lo_rifle.png  lo_shotgun.png
    assets/lo_pistol.png  lo_revolver.png  lo_mpist.png  lo_knife.png

It also writes assets/lo_tips.js with each gun's muzzle position, so the game draws
the muzzle flash on the real barrel tip.

Run it (Blender 3.x or 4.x):
    blender -b -P make_bunker_guns.py                  # all weapons
    blender -b -P make_bunker_guns.py -- ar shotgun    # only some of them
or open it in Blender's Scripting tab and press Run Script (Blender freezes until done).

Output goes to an "assets" folder next to this script. Put that folder next to
Bunker_Breakout.html. To send it somewhere else, set OUT_DIR below.
"""
import bpy
import math
import os
import sys
import json
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view

# ----------------------------------------------------------------------------
# Settings you can change
# ----------------------------------------------------------------------------
OUT_DIR = None            # e.g. r"C:\games\bunker\assets"; None = "assets" next to this script
RES = 512                 # sprite size in pixels (the game draws it at 176x176)
SAMPLES = 64              # Cycles samples; raise for cleaner images, lower for speed
GLOVES = True             # True = black tactical gloves, False = bare skin
                          # (a PNG can't follow the in-game skin editor, so gloves avoid a mismatch)
LENS = 38                 # camera lens in mm; lower = more dramatic perspective
VIEW_DIR = Vector((-0.12, -1.0, 0.52)).normalized()   # camera sits behind, above and a bit left
FIT_BOX = (0.10, 0.20, 0.90, 0.95)   # where gun + hands must land: x0, y0, x1, y1 (y from the bottom)

# ----------------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------------
def hexc(h):
    h = h.lstrip('#')
    return tuple((int(h[i:i + 2], 16) / 255.0) ** 2.2 for i in (0, 2, 4))


_mats = {}


def mat(name, hexcol, metal=0.0, rough=0.5):
    if name in _mats:
        return _mats[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*hexc(hexcol), 1.0)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    _mats[name] = m
    return m


STEEL = mat("steel", "#9aa1a9", 0.9, 0.28)
GUNMETAL = mat("gunmetal", "#2c2f34", 0.7, 0.38)
BLACK = mat("black", "#17181b", 0.3, 0.55)
POLY = mat("poly", "#2a2c30", 0.0, 0.65)
WOOD = mat("wood", "#6e4526", 0.0, 0.55)
WOOD_DK = mat("wood_dk", "#43291a", 0.0, 0.50)
BRASS = mat("brass", "#c9a13b", 1.0, 0.30)
BLADE = mat("blade", "#cfd5dd", 1.0, 0.22)
GLOVE = mat("glove", "#1b1c1f" if GLOVES else "#c98f6b", 0.0, 0.85 if GLOVES else 0.6)
SLEEVE = mat("sleeve", "#46523a", 0.0, 0.90)

# ----------------------------------------------------------------------------
# Geometry helpers. Every part is tagged:
#   'gun'   - counts toward camera framing
#   'hand'  - counts toward camera framing
#   'extra' / 'arm' - rendered, but ignored for framing (stocks, forearms run off-frame)
# World axes: +X right, +Y forward (barrel direction), +Z up. The right hand's
# grip center sits at the origin.
# ----------------------------------------------------------------------------
MADE = []


def _reg(o, m, tag):
    o.data.materials.append(m)
    MADE.append((o, tag))
    return o


def _smooth(o, angle=50):
    for p in o.data.polygons:
        p.use_smooth = True
    es = o.modifiers.new("es", 'EDGE_SPLIT')
    es.split_angle = math.radians(angle)


def box(x, y, z, sx, sy, sz, m, rot=(0, 0, 0), tag='gun', bevel=True):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
    o = bpy.context.active_object
    o.data.transform(Matrix.Diagonal((sx, sy, sz, 1.0)))
    o.rotation_euler = [math.radians(a) for a in rot]
    if bevel:
        b = o.modifiers.new("bevel", 'BEVEL')
        b.width = min(0.005, min(sx, sy, sz) * 0.22)
        b.segments = 2
    return _reg(o, m, tag)


def cyl(x, y, z, r, length, m, axis='Y', seg=24, tag='gun'):
    rot = {'X': (0, 90, 0), 'Y': (-90, 0, 0), 'Z': (0, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=seg, radius=r, depth=length, location=(x, y, z),
        rotation=[math.radians(a) for a in rot])
    o = bpy.context.active_object
    _smooth(o)
    return _reg(o, m, tag)


def sphere(x, y, z, r, m, tag='gun'):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=20, ring_count=12, location=(x, y, z))
    o = bpy.context.active_object
    _smooth(o, 80)
    return _reg(o, m, tag)


def limb(p1, p2, r, m, tag='arm', seg=16):
    a, b = Vector(p1), Vector(p2)
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=seg, radius=r, depth=d.length, location=(a + b) / 2)
    o = bpy.context.active_object
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    _smooth(o)
    return _reg(o, m, tag)


def prism(poly, z0, z1, m, tag='gun'):
    """Extrude a counter-clockwise XY polygon between z0 and z1."""
    n = len(poly)
    verts = [(x, y, z0) for x, y in poly] + [(x, y, z1) for x, y in poly]
    faces = [list(range(n))[::-1], list(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])
    me = bpy.data.meshes.new("prism")
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new("prism", me)
    bpy.context.scene.collection.objects.link(o)
    return _reg(o, m, tag)


# ----------------------------------------------------------------------------
# Hands and arms
# ----------------------------------------------------------------------------
def forearm_r(gx=0.0, gy=0.0, gz=0.0):
    limb((gx + 0.02, gy - 0.085, gz + 0.03), (gx + 0.055, gy - 0.20, gz - 0.045), 0.040, GLOVE)
    limb((gx + 0.055, gy - 0.20, gz - 0.045), (gx + 0.19, gy - 0.65, gz - 0.38), 0.054, SLEEVE)


def right_hand(rake=-18):
    """Right hand wrapped around a pistol grip centered on the origin."""
    box(0.010, -0.040, 0.012, 0.086, 0.065, 0.100, GLOVE, (rake, 0, 0), 'hand')      # palm
    for i in range(4):                                                                # fingers
        box(-0.004, 0.028, 0.040 - i * 0.026, 0.084, 0.030, 0.023, GLOVE, (rake, 0, 0), 'hand')
    box(-0.040, 0.030, 0.072, 0.024, 0.085, 0.024, GLOVE, (0, 0, -4), 'hand')        # thumb
    forearm_r()


def support_hand(y, zc, r):
    """Left hand cupped under a handguard centered at (0, y, zc) with half-thickness r."""
    box(-0.004, y, zc - r - 0.016, 2 * r + 0.034, 0.085, 0.040, GLOVE, (0, 0, 0), 'hand')   # palm
    box(r + 0.012, y + 0.004, zc - 0.004, 0.022, 0.074, 2 * r + 0.012, GLOVE, (0, 0, 0), 'hand')  # fingers
    box(-(r + 0.014), y + 0.022, zc + r * 0.55, 0.022, 0.070, 0.026, GLOVE, (0, 0, 4), 'hand')    # thumb
    box(-(r + 0.020), y - 0.018, zc - r * 0.6, 0.030, 0.090, 0.060, GLOVE, (0, 0, 0), 'hand')     # back of hand
    zb = zc - r - 0.04
    limb((-0.03, y - 0.05, zb), (-0.11, y - 0.30, zb - 0.14), 0.040, GLOVE)
    limb((-0.11, y - 0.30, zb - 0.14), (-0.24, y - 0.78, zb - 0.48), 0.054, SLEEVE)


def cup_hand():
    """Left hand cupping the right one on a pistol-style grip."""
    box(-0.052, -0.004, -0.010, 0.040, 0.080, 0.100, GLOVE, (-18, 0, 0), 'hand')
    box(-0.062, 0.050, 0.035, 0.024, 0.075, 0.024, GLOVE, (0, 0, 6), 'hand')
    limb((-0.06, -0.05, -0.02), (-0.11, -0.25, -0.12), 0.040, GLOVE)
    limb((-0.11, -0.25, -0.12), (-0.26, -0.70, -0.42), 0.054, SLEEVE)


# ----------------------------------------------------------------------------
# Weapons. Each builder returns the muzzle position (x, y, z).
# ----------------------------------------------------------------------------
def build_ar():
    box(0, 0.040, 0.082, 0.040, 0.200, 0.055, GUNMETAL)               # lower receiver
    box(0, 0.090, 0.130, 0.042, 0.300, 0.050, GUNMETAL)               # upper receiver
    box(0, -0.070, 0.148, 0.026, 0.050, 0.026, BLACK)                 # charging handle
    box(0, 0.060, 0.170, 0.022, 0.260, 0.016, BLACK)                  # top rail
    box(0, -0.020, 0.188, 0.018, 0.030, 0.030, BLACK)                 # rear sight
    cyl(0, 0.430, 0.125, 0.032, 0.380, POLY)                          # handguard
    cyl(0, 0.745, 0.125, 0.0105, 0.250, STEEL)                        # barrel
    box(0, 0.665, 0.158, 0.012, 0.016, 0.052, BLACK)                  # front sight
    cyl(0, 0.650, 0.125, 0.017, 0.040, GUNMETAL)                      # gas block
    cyl(0, 0.885, 0.125, 0.016, 0.060, BLACK)                         # flash hider
    box(0, 0.105, -0.020, 0.030, 0.050, 0.160, BLACK, (8, 0, 0))      # magazine
    box(0, -0.012, -0.005, 0.036, 0.045, 0.115, POLY, (-18, 0, 0))    # pistol grip
    cyl(0, -0.180, 0.110, 0.022, 0.240, GUNMETAL, tag='extra')        # buffer tube
    box(0, -0.310, 0.090, 0.040, 0.100, 0.090, POLY, (6, 0, 0), 'extra')  # stock
    right_hand(-18)
    support_hand(0.40, 0.125, 0.032)
    return (0, 0.915, 0.125)


def build_ak():
    box(0, 0.060, 0.082, 0.040, 0.300, 0.050, GUNMETAL)               # receiver
    box(0, 0.070, 0.118, 0.040, 0.300, 0.028, BLACK)                  # dust cover
    cyl(0, 0.540, 0.113, 0.0105, 0.640, STEEL)                        # barrel
    cyl(0, 0.470, 0.158, 0.013, 0.310, GUNMETAL)                      # gas tube
    box(0, 0.420, 0.100, 0.050, 0.260, 0.054, WOOD)                   # lower handguard
    box(0, 0.500, 0.142, 0.040, 0.180, 0.026, WOOD_DK)                # upper handguard
    box(0, 0.780, 0.145, 0.012, 0.030, 0.050, BLACK)                  # front sight
    cyl(0, 0.845, 0.113, 0.015, 0.060, BLACK)                         # muzzle brake
    box(0, 0.115, 0.000, 0.030, 0.050, 0.110, BLACK, (12, 0, 0))      # curved mag, upper
    box(0, 0.155, -0.080, 0.030, 0.050, 0.100, BLACK, (30, 0, 0))     # curved mag, lower
    box(0, -0.014, -0.008, 0.036, 0.046, 0.120, WOOD_DK, (-22, 0, 0)) # pistol grip
    box(0, -0.230, 0.070, 0.040, 0.300, 0.075, WOOD, (9, 0, 0), 'extra')  # stock
    right_hand(-22)
    support_hand(0.40, 0.100, 0.027)
    return (0, 0.875, 0.113)


def build_smg():
    box(0, 0.070, 0.088, 0.042, 0.300, 0.062, POLY)                   # receiver
    box(0, 0.060, 0.128, 0.020, 0.220, 0.014, BLACK)                  # top rail
    box(0, -0.030, 0.142, 0.014, 0.024, 0.024, BLACK)                 # rear sight
    box(0, 0.295, 0.090, 0.052, 0.130, 0.052, POLY)                   # handguard
    cyl(0, 0.440, 0.092, 0.021, 0.200, BLACK)                         # suppressor
    box(0, 0.130, -0.030, 0.028, 0.050, 0.170, BLACK, (6, 0, 0))      # long magazine
    box(0, -0.010, -0.010, 0.034, 0.046, 0.112, POLY, (-18, 0, 0))    # grip
    box(-0.018, -0.170, 0.095, 0.009, 0.200, 0.009, STEEL, tag='extra')   # stock rail L
    box(0.018, -0.170, 0.095, 0.009, 0.200, 0.009, STEEL, tag='extra')    # stock rail R
    box(0, -0.272, 0.090, 0.040, 0.012, 0.075, POLY, tag='extra')     # butt plate
    right_hand(-18)
    support_hand(0.295, 0.090, 0.026)
    return (0, 0.54, 0.092)


def build_rifle():
    box(0, 0.040, 0.100, 0.034, 0.230, 0.050, GUNMETAL)               # receiver
    cyl(0, 0.560, 0.107, 0.0115, 0.820, STEEL)                        # long barrel
    box(0, 0.330, 0.084, 0.042, 0.360, 0.048, WOOD)                   # fore-end
    box(0, -0.130, 0.060, 0.044, 0.320, 0.075, WOOD, (10, 0, 0), 'extra')  # stock
    box(0, -0.012, -0.005, 0.036, 0.050, 0.112, WOOD, (-20, 0, 0))    # grip
    box(0.032, 0.012, 0.108, 0.040, 0.012, 0.012, STEEL)              # bolt handle
    sphere(0.056, 0.012, 0.108, 0.013, BLACK)                         # bolt knob
    cyl(0, 0.050, 0.188, 0.019, 0.280, BLACK)                         # scope tube
    cyl(0, 0.205, 0.188, 0.027, 0.060, BLACK)                         # scope objective
    cyl(0, -0.105, 0.188, 0.025, 0.050, BLACK)                        # scope eyepiece
    box(0, 0.010, 0.147, 0.020, 0.030, 0.045, GUNMETAL)               # mount rear
    box(0, 0.120, 0.147, 0.020, 0.030, 0.045, GUNMETAL)               # mount front
    box(0, 0.070, 0.040, 0.030, 0.070, 0.050, POLY)                   # magazine
    cyl(0, 0.965, 0.107, 0.0145, 0.020, GUNMETAL)                     # muzzle crown
    right_hand(-20)
    support_hand(0.40, 0.084, 0.026)
    return (0, 0.975, 0.107)


def build_shotgun():
    box(0, 0.050, 0.098, 0.042, 0.270, 0.058, GUNMETAL)               # receiver
    cyl(0, 0.525, 0.112, 0.0165, 0.750, STEEL)                        # barrel
    cyl(0, 0.520, 0.076, 0.0135, 0.700, GUNMETAL)                     # magazine tube
    box(0, 0.420, 0.078, 0.052, 0.200, 0.050, WOOD)                   # pump
    box(0, 0.905, 0.134, 0.008, 0.012, 0.012, BRASS)                  # bead sight
    box(0, -0.140, 0.062, 0.044, 0.320, 0.076, WOOD, (10, 0, 0), 'extra')  # stock
    box(0, -0.012, -0.005, 0.036, 0.050, 0.112, WOOD, (-20, 0, 0))    # grip
    right_hand(-20)
    support_hand(0.42, 0.078, 0.028)
    return (0, 0.90, 0.112)


def build_pistol():
    box(0, 0.075, 0.095, 0.030, 0.200, 0.036, GUNMETAL)               # slide
    box(0, 0.070, 0.066, 0.030, 0.190, 0.022, POLY)                   # frame
    box(0, -0.006, -0.018, 0.032, 0.052, 0.120, POLY, (-16, 0, 0))    # grip
    box(0, 0.060, 0.040, 0.010, 0.080, 0.012, POLY)                   # trigger guard
    box(0, 0.002, 0.118, 0.012, 0.014, 0.012, BLACK)                  # rear sight
    box(0, 0.165, 0.118, 0.007, 0.012, 0.012, BLACK)                  # front sight
    cyl(0, 0.180, 0.095, 0.0085, 0.020, STEEL)                        # barrel tip
    right_hand(-16)
    cup_hand()
    return (0, 0.19, 0.095)


def build_revolver():
    box(0, 0.035, 0.078, 0.030, 0.150, 0.052, STEEL)                  # frame
    cyl(0, 0.075, 0.086, 0.032, 0.075, STEEL)                         # cylinder
    cyl(0, 0.240, 0.100, 0.0125, 0.300, STEEL)                        # barrel
    box(0, 0.250, 0.080, 0.022, 0.280, 0.018, STEEL)                  # under lug
    box(0, 0.378, 0.120, 0.008, 0.014, 0.014, BLACK)                  # front sight
    box(0, -0.030, 0.112, 0.014, 0.030, 0.034, STEEL, (-20, 0, 0))    # hammer
    box(0, -0.008, -0.018, 0.034, 0.056, 0.118, WOOD, (-18, 0, 0))    # grip
    box(0, 0.035, 0.040, 0.010, 0.090, 0.012, STEEL)                  # trigger guard
    right_hand(-18)
    cup_hand()
    return (0, 0.392, 0.100)


def build_mpist():
    box(0, 0.075, 0.092, 0.038, 0.230, 0.052, POLY)                   # body
    box(0, 0.070, 0.123, 0.026, 0.200, 0.012, BLACK)                  # top plate
    cyl(0, 0.235, 0.092, 0.019, 0.170, BLACK)                         # suppressor
    box(0, -0.006, -0.018, 0.034, 0.052, 0.120, POLY, (-16, 0, 0))    # grip
    box(0, -0.040, -0.135, 0.027, 0.040, 0.130, BLACK, (-16, 0, 0), 'extra')  # extended mag
    box(0, 0.060, 0.045, 0.010, 0.080, 0.012, POLY)                   # trigger guard
    box(-0.018, -0.125, 0.098, 0.008, 0.150, 0.008, STEEL, tag='extra')   # wire stock L
    box(0.018, -0.125, 0.098, 0.008, 0.150, 0.008, STEEL, tag='extra')    # wire stock R
    box(0, -0.205, 0.095, 0.036, 0.010, 0.050, POLY, tag='extra')     # butt
    right_hand(-16)
    cup_hand()
    return (0, 0.32, 0.092)


def build_knife():
    cyl(0, 0.020, 0.0, 0.0185, 0.170, BLACK)                          # handle
    box(0, 0.108, 0.0, 0.074, 0.014, 0.026, GUNMETAL)                 # cross guard
    box(0, -0.070, 0.0, 0.044, 0.014, 0.044, GUNMETAL)                # pommel
    prism([(-0.022, 0.115), (0.022, 0.115), (0.022, 0.285), (0.004, 0.380), (-0.022, 0.285)],
          -0.004, 0.004, BLADE)                                       # blade, flat side up
    box(0, 0.200, 0.0045, 0.007, 0.140, 0.0015, GUNMETAL, bevel=False)    # fuller
    box(0.0, 0.005, 0.014, 0.082, 0.085, 0.060, GLOVE, (0, 0, 0), 'hand')  # fist
    box(0.0, 0.045, 0.052, 0.022, 0.075, 0.020, GLOVE, (0, 0, 0), 'hand')  # thumb
    forearm_r()
    return (0, 0.38, 0.0)


# name -> (builder, minimum forward reach used for framing; 0 = use the real gun)
GUNS = {
    'ar':       (build_ar, 0.0),
    'ak':       (build_ak, 0.0),
    'smg':      (build_smg, 0.62),
    'rifle':    (build_rifle, 0.0),
    'shotgun':  (build_shotgun, 0.0),
    'pistol':   (build_pistol, 0.50),
    'revolver': (build_revolver, 0.52),
    'mpist':    (build_mpist, 0.52),
    'knife':    (build_knife, 0.50),
}

# ----------------------------------------------------------------------------
# Scene, lights, camera
# ----------------------------------------------------------------------------
def setup_render(sc):
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoise = True
    sc.cycles.max_bounces = 4
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    try:
        sc.view_settings.view_transform = 'Standard'
    except TypeError:
        pass


def add_sun(sc, name, rot, energy, color=(1.0, 1.0, 1.0)):
    ld = bpy.data.lights.new(name, 'SUN')
    ld.energy = energy
    ld.color = color
    ld.angle = math.radians(8)
    o = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(o)
    o.rotation_euler = [math.radians(a) for a in rot]


def setup_world_and_lights(sc):
    w = bpy.data.worlds.new("GunWorld")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.45, 0.48, 0.55, 1.0)
    bg.inputs[1].default_value = 0.8
    sc.world = w
    add_sun(sc, "Key", (50, 0, -30), 3.5)                          # upper left, behind the camera
    add_sun(sc, "Fill", (60, 0, 40), 0.9)                          # soft fill from the right
    add_sun(sc, "Rim", (-50, 0, -25), 2.0, (0.85, 0.92, 1.0))      # edge light from the front


def make_camera(sc):
    cd = bpy.data.cameras.new("GunCam")
    cd.lens = LENS
    cd.clip_start = 0.05
    cd.clip_end = 50
    cam = bpy.data.objects.new("GunCam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam


def aim(cam, loc, tgt):
    cam.location = loc
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()


def project(cam, pts):
    bpy.context.view_layer.update()
    sc = bpy.context.scene
    return [world_to_camera_view(sc, cam, p) for p in pts]


def key_points(frame_len):
    bpy.context.view_layer.update()
    pts = []
    for o, tag in MADE:
        if tag in ('gun', 'hand'):
            mw = o.matrix_world
            pts += [mw @ Vector(c) for c in o.bound_box]
    if frame_len:
        pts.append(Vector((0.0, frame_len, 0.10)))
    return pts


def fit_camera(cam, pts):
    """Move the camera back/forward and re-center it until pts fill FIT_BOX."""
    half = math.tan(cam.data.angle / 2.0)
    tgt = sum(pts, Vector((0.0, 0.0, 0.0))) / len(pts)
    dist = 2.0
    bx0, by0, bx1, by1 = FIT_BOX
    cx_t, cy_t = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
    for _ in range(40):
        aim(cam, tgt + VIEW_DIR * dist, tgt)
        nd = project(cam, pts)
        xs = [v.x for v in nd]
        ys = [v.y for v in nd]
        r = max((max(xs) - min(xs)) / (bx1 - bx0), (max(ys) - min(ys)) / (by1 - by0))
        q = cam.matrix_world.to_quaternion()
        right, up = q @ Vector((1, 0, 0)), q @ Vector((0, 1, 0))
        frame_h = 2.0 * dist * half
        cx = (max(xs) + min(xs)) / 2.0
        cy = (max(ys) + min(ys)) / 2.0
        tgt = tgt + right * (cx - cx_t) * frame_h * 0.7 + up * (cy - cy_t) * frame_h * 0.7
        dist *= 1.0 + (r - 1.0) * 0.7
    aim(cam, tgt + VIEW_DIR * dist, tgt)


def clear_gun():
    for o, _ in MADE:
        bpy.data.objects.remove(o, do_unlink=True)
    MADE.clear()
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)


def _here():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        pass
    if bpy.data.filepath:
        return os.path.dirname(bpy.data.filepath)
    return os.path.expanduser("~")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    sc = bpy.context.scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    setup_render(sc)
    setup_world_and_lights(sc)
    cam = make_camera(sc)

    out = OUT_DIR or os.path.join(_here(), "assets")
    os.makedirs(out, exist_ok=True)

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    names = [n for n in GUNS if not argv or n in argv]

    tips = {}
    for name in names:
        build, frame_len = GUNS[name]
        muzzle = build()
        pts = key_points(frame_len)
        fit_camera(cam, pts)
        sc.render.filepath = os.path.join(out, "lo_%s.png" % name)
        bpy.ops.render.render(write_still=True)
        if name != "knife":
            v = world_to_camera_view(sc, cam, Vector(muzzle))
            tips[name] = {"x": round(v.x, 3), "y": round(1.0 - v.y, 3)}
        clear_gun()
        print("[bunker guns] rendered", name)

    # muzzle positions for the game (merge with an existing file if only some guns were rendered)
    tips_path = os.path.join(out, "lo_tips.js")
    old = {}
    if os.path.exists(tips_path):
        try:
            with open(tips_path) as f:
                txt = f.read()
            old = json.loads(txt[txt.index('{'):txt.rindex('}') + 1])
        except Exception:
            old = {}
    old.update(tips)
    with open(tips_path, "w") as f:
        f.write("window.LO_TIPS = " + json.dumps(old) + ";\n")
    print("[bunker guns] done ->", out)


main()
