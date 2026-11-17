"""
Bunker Breakout - gun sprite generator for Blender (2.93 - 4.x)

Builds every loadout weapon (AR, AK-47, SMG, RIFLE, SHOTGUN, PISTOL, REVOLVER,
MACHINE PISTOL, KNIFE) in first-person view WITH arms/hands and renders each one
to a transparent PNG that the game picks up automatically.

USAGE (from the folder that contains Bunker_Breakout.html and the assets/ folder):

    blender -b -P make_gun_sprites.py -- assets

  - everything after the "--" is the output folder (default: ./assets)
  - add  --only ak   to render just one weapon (ar ak smg rifle shotgun pistol revolver mpist knife)
  - add  --samples 128   for a cleaner (slower) render

OUTPUT (in the output folder):
    lo_ar.png  lo_ak.png  lo_smg.png  lo_rifle.png  lo_shotgun.png
    lo_pistol.png  lo_revolver.png  lo_mpist.png  lo_knife.png
    lo_tips.js     <- muzzle positions so the game can place muzzle flashes

The game falls back to its built-in pixel guns for any PNG that is missing.
"""
import bpy, sys, os, math, json

# ----------------------------------------------------------------- arguments
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.join(os.getcwd(), 'assets')
ONLY = None
SAMPLES = 64
i = 0
while i < len(argv):
    a = argv[i]
    if a == '--only' and i + 1 < len(argv):
        ONLY = argv[i + 1]; i += 2
    elif a == '--samples' and i + 1 < len(argv):
        SAMPLES = int(argv[i + 1]); i += 2
    else:
        OUT = os.path.abspath(argv[i]); i += 1
os.makedirs(OUT, exist_ok=True)

SIZE = 384            # output image is SIZE x SIZE
PITCH = math.radians(50)   # camera looks this far below the horizon (from behind + above)
SP, CP = math.sin(PITCH), math.cos(PITCH)

# ------------------------------------------------------------------ scene setup
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

MATS = {}
def mat(name, rgb, metal=0.0, rough=0.5):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (rgb[0], rgb[1], rgb[2], 1)
    b.inputs['Metallic'].default_value = metal
    b.inputs['Roughness'].default_value = rough
    MATS[name] = m
    return m

STEEL  = mat('steel',  (0.16, 0.16, 0.17), 0.9, 0.35)
GUNMET = mat('gunmet', (0.28, 0.29, 0.32), 0.8, 0.40)
BLACK  = mat('black',  (0.04, 0.04, 0.045), 0.0, 0.55)
OLIVE  = mat('olive',  (0.12, 0.16, 0.07), 0.0, 0.60)
WOOD   = mat('wood',   (0.30, 0.14, 0.05), 0.0, 0.50)
WOOD2  = mat('wood2',  (0.18, 0.08, 0.03), 0.0, 0.50)
BLADE  = mat('blade',  (0.75, 0.78, 0.82), 1.0, 0.20)
LENS   = mat('lens',   (0.15, 0.45, 0.80), 0.3, 0.10)
BRASS  = mat('brass',  (0.65, 0.45, 0.12), 0.9, 0.35)
SKIN   = mat('skin',   (0.62, 0.38, 0.27), 0.0, 0.65)
SLEEVE = mat('sleeve', (0.11, 0.14, 0.07), 0.0, 0.90)

# ------------------------------------------------------------------ primitives
PARTS = []

def _fin(o, m, bevel):
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(m)
    if bevel:
        bv = o.modifiers.new('bv', 'BEVEL')
        bv.width = bevel
        bv.segments = 2
    PARTS.append(o)
    return o

def B(x, y, z, w, l, h, m, bevel=0.004, rot=(0, 0, 0)):
    """box centred at (x,y,z); w=X width, l=Y length (forward), h=Z height"""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z), rotation=rot)
    o = bpy.context.active_object
    o.scale = (w, l, h)
    return _fin(o, m, bevel)

def C(x, y, z, r, length, m, axis='Y'):
    """cylinder; axis Y (barrels) or Z (mags/pins) or X"""
    rot = {'Y': (math.pi / 2, 0, 0), 'X': (0, math.pi / 2, 0), 'Z': (0, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=r, depth=length, location=(x, y, z), rotation=rot)
    o = bpy.context.active_object
    o.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    PARTS.append(o)
    return o

def TIPCONE(x, y, z, rx, rz, depth, m):
    """flat blade tip pointing +Y"""
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=rx, radius2=0, depth=depth, location=(x, y, z))
    o = bpy.context.active_object
    o.scale = (0.3, 1.0, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    o.rotation_euler = (-math.pi / 2, 0, 0)
    o.data.materials.append(m)
    PARTS.append(o)
    return o

def ARM(a, b, r, m=None):
    """cylinder from point a to point b (sleeve)"""
    m = m or SLEEVE
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    L = math.sqrt(dx * dx + dy * dy + dz * dz)
    theta = math.acos(dz / L)
    psi = math.atan2(dy, dx)
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=r, depth=L,
        location=((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2),
        rotation=(theta, 0, psi + math.pi / 2))
    o = bpy.context.active_object
    o.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    PARTS.append(o)
    return o

def HAND(x, y, z, side=1, tilt=0.0):
    """gripping hand: back of hand + knuckles + thumb. side=+1 right hand, -1 left hand"""
    B(x, y, z, 0.052, 0.062, 0.07, SKIN, 0.012, (tilt, 0, 0))
    for k in range(4):
        B(x - 0.03 + k * 0.02, y + 0.042, z - 0.004, 0.018, 0.034, 0.05, SKIN, 0.007, (tilt, 0, 0))
    B(x - side * 0.038, y + 0.012, z + 0.006, 0.02, 0.05, 0.026, SKIN, 0.008, (0, 0, side * 0.35))

# arms always run to the same point near the bottom of the frame
RIGHT_END = (0.17, -0.58, -0.12)
LEFT_END  = (-0.20, -0.56, -0.12)

def RIGHT_ARM(hx, hy, hz):
    ARM((hx + 0.005, hy - 0.03, hz - 0.01), RIGHT_END, 0.040)

def LEFT_ARM(hx, hy, hz):
    ARM((hx - 0.005, hy - 0.03, hz - 0.01), LEFT_END, 0.040)

# ------------------------------------------------------------------ weapons
# every builder returns the muzzle point (x, y, z)

def build_ar():
    B(0, -0.02, 0.020, 0.040, 0.20, 0.070, BLACK)
    B(0, 0.075, 0.062, 0.040, 0.30, 0.050, BLACK)
    B(0, 0.04, 0.100, 0.020, 0.24, 0.022, GUNMET)          # top rail
    B(0, -0.055, 0.118, 0.018, 0.035, 0.030, BLACK)        # rear sight
    B(0, 0.43, 0.092, 0.010, 0.022, 0.045, BLACK)          # front sight
    C(0, 0.32, 0.058, 0.026, 0.30, GUNMET)                  # handguard
    C(0, 0.50, 0.058, 0.008, 0.12, STEEL)                   # barrel
    C(0, 0.565, 0.058, 0.013, 0.05, BLACK)                  # flash hider
    B(0.0, 0.045, -0.075, 0.034, 0.060, 0.17, OLIVE, 0.004, (0.18, 0, 0))   # mag
    B(0, -0.075, -0.04, 0.036, 0.05, 0.10, BLACK, 0.006, (0.35, 0, 0))      # grip
    C(0, -0.27, 0.048, 0.017, 0.16, BLACK)                  # buffer tube
    B(0, -0.37, 0.03, 0.044, 0.04, 0.11, BLACK, 0.006)      # butt
    HAND(0.0, -0.075, -0.035, 1, 0.3); RIGHT_ARM(0.0, -0.075, -0.035)
    HAND(0.0, 0.25, 0.075, -1, 0.0);   LEFT_ARM(0.0, 0.25, 0.075)
    return (0, 0.59, 0.058)

def build_ak():
    B(0, 0.0, 0.025, 0.040, 0.26, 0.065, STEEL)
    B(0, 0.03, 0.066, 0.036, 0.25, 0.022, STEEL)           # dust cover
    C(0, 0.12, 0.092, 0.009, 0.30, STEEL)                   # gas tube
    B(0, 0.26, 0.04, 0.046, 0.26, 0.060, WOOD)              # handguard
    C(0, 0.52, 0.048, 0.008, 0.20, STEEL)                   # barrel
    B(0, 0.655, 0.048, 0.016, 0.03, 0.022, BLACK)           # muzzle brake
    B(0, 0.58, 0.075, 0.010, 0.02, 0.05, BLACK)             # front sight
    B(0, 0.07, -0.08, 0.034, 0.07, 0.13, BLACK, 0.004, (0.55, 0, 0))        # curved mag (upper)
    B(0, 0.12, -0.15, 0.034, 0.07, 0.10, BLACK, 0.004, (0.9, 0, 0))         # curved mag (lower)
    B(0, -0.07, -0.04, 0.036, 0.05, 0.10, WOOD2, 0.006, (0.35, 0, 0))       # grip
    B(0, -0.28, 0.01, 0.040, 0.30, 0.085, WOOD, 0.008, (-0.12, 0, 0))       # stock
    HAND(0.0, -0.07, -0.035, 1, 0.3); RIGHT_ARM(0.0, -0.07, -0.035)
    HAND(0.0, 0.26, 0.075, -1, 0.0);  LEFT_ARM(0.0, 0.26, 0.075)
    return (0, 0.67, 0.048)

def build_smg():
    B(0, 0.04, 0.045, 0.044, 0.26, 0.075, BLACK)
    B(0, 0.04, 0.090, 0.020, 0.22, 0.016, GUNMET)
    C(0, 0.30, 0.050, 0.020, 0.18, BLACK)                   # suppressor
    B(0, 0.02, -0.085, 0.028, 0.045, 0.17, GUNMET)          # straight mag
    B(0, -0.065, -0.035, 0.034, 0.05, 0.10, BLACK, 0.006, (0.3, 0, 0))
    B(0, -0.21, 0.035, 0.030, 0.20, 0.050, BLACK)           # folded stock
    HAND(0.0, -0.065, -0.03, 1, 0.3); RIGHT_ARM(0.0, -0.065, -0.03)
    HAND(0.0, 0.14, 0.095, -1, 0.0);  LEFT_ARM(0.0, 0.14, 0.095)
    return (0, 0.39, 0.050)

def build_rifle():
    B(0, 0.0, 0.03, 0.040, 0.22, 0.065, STEEL)
    C(0, 0.50, 0.05, 0.010, 0.55, STEEL)                    # long barrel
    C(0, 0.78, 0.05, 0.014, 0.04, BLACK)                    # muzzle
    C(0, 0.17, 0.115, 0.024, 0.26, BLACK)                   # scope tube
    C(0, 0.31, 0.115, 0.030, 0.06, BLACK)                   # scope front bell
    C(0, 0.03, 0.115, 0.030, 0.05, BLACK)                   # scope rear bell
    B(0, 0.17, 0.082, 0.014, 0.035, 0.030, BLACK)           # mounts
    B(0, 0.31, 0.12, 0.010, 0.002, 0.010, LENS)             # lens glint
    B(0, 0.30, 0.03, 0.046, 0.34, 0.058, WOOD)              # forestock
    B(0.04, 0.0, 0.05, 0.010, 0.04, 0.010, BRASS)           # bolt handle
    B(0.056, 0.0, 0.05, 0.026, 0.012, 0.012, BRASS)
    B(0, -0.07, -0.035, 0.034, 0.05, 0.10, WOOD2, 0.006, (0.35, 0, 0))
    B(0, -0.30, 0.0, 0.044, 0.34, 0.10, WOOD, 0.008, (-0.10, 0, 0))
    HAND(0.0, -0.07, -0.03, 1, 0.3); RIGHT_ARM(0.0, -0.07, -0.03)
    HAND(0.0, 0.28, 0.06, -1, 0.0);  LEFT_ARM(0.0, 0.28, 0.06)
    return (0, 0.80, 0.05)

def build_shotgun():
    B(0, 0.0, 0.030, 0.044, 0.24, 0.070, GUNMET)
    C(0, 0.40, 0.058, 0.014, 0.50, STEEL)                   # barrel
    C(0, 0.37, 0.020, 0.016, 0.40, GUNMET)                  # magazine tube
    C(0, 0.655, 0.058, 0.018, 0.02, BLACK)                  # muzzle
    B(0, 0.30, 0.028, 0.052, 0.17, 0.050, WOOD)             # pump
    B(0, 0.67, 0.085, 0.008, 0.015, 0.016, BRASS)           # bead sight
    B(0, -0.075, -0.035, 0.034, 0.05, 0.10, WOOD2, 0.006, (0.3, 0, 0))
    B(0, -0.28, 0.0, 0.046, 0.32, 0.10, WOOD, 0.008, (-0.12, 0, 0))
    HAND(0.0, -0.075, -0.03, 1, 0.3); RIGHT_ARM(0.0, -0.075, -0.03)
    HAND(0.0, 0.30, 0.04, -1, 0.0);   LEFT_ARM(0.0, 0.30, 0.04)
    return (0, 0.665, 0.058)

def build_pistol():
    B(0, 0.04, 0.050, 0.030, 0.19, 0.040, GUNMET)           # slide
    B(0, 0.01, 0.015, 0.028, 0.15, 0.030, BLACK)            # frame
    B(0, -0.03, -0.040, 0.034, 0.05, 0.10, BLACK, 0.006, (0.30, 0, 0))     # grip
    B(0, 0.125, 0.074, 0.008, 0.012, 0.014, BLACK)          # front sight
    B(0, -0.045, 0.074, 0.016, 0.012, 0.014, BLACK)         # rear sight
    HAND(0.0, -0.03, -0.035, 1, 0.3); RIGHT_ARM(0.0, -0.03, -0.035)
    HAND(-0.045, 0.0, -0.030, -1, 0.0); LEFT_ARM(-0.045, 0.0, -0.030)
    return (0, 0.14, 0.05)

def build_revolver():
    B(0, 0.04, 0.050, 0.026, 0.20, 0.040, STEEL)            # frame/barrel shroud
    C(0, 0.14, 0.05, 0.011, 0.20, STEEL)                    # barrel
    C(0, 0.015, 0.045, 0.034, 0.07, GUNMET)                 # cylinder
    B(0, 0.20, 0.068, 0.008, 0.014, 0.014, BLACK)
    B(0, -0.03, -0.040, 0.034, 0.05, 0.10, WOOD, 0.006, (0.30, 0, 0))
    HAND(0.0, -0.03, -0.035, 1, 0.3); RIGHT_ARM(0.0, -0.03, -0.035)
    HAND(-0.045, 0.0, -0.030, -1, 0.0); LEFT_ARM(-0.045, 0.0, -0.030)
    return (0, 0.24, 0.05)

def build_mpist():
    B(0, 0.05, 0.050, 0.032, 0.22, 0.042, BLACK)
    B(0, 0.05, 0.076, 0.012, 0.18, 0.012, GUNMET)
    C(0, 0.19, 0.050, 0.014, 0.10, BLACK)                   # compensator
    B(0, 0.03, -0.075, 0.026, 0.045, 0.14, GUNMET)          # extended mag
    B(0, -0.03, -0.040, 0.034, 0.05, 0.10, BLACK, 0.006, (0.30, 0, 0))
    HAND(0.0, -0.03, -0.035, 1, 0.3); RIGHT_ARM(0.0, -0.03, -0.035)
    HAND(-0.045, 0.0, -0.030, -1, 0.0); LEFT_ARM(-0.045, 0.0, -0.030)
    return (0, 0.24, 0.05)

def build_knife():
    B(0, -0.01, 0.0, 0.026, 0.12, 0.034, BLACK, 0.008)       # handle
    B(0, 0.065, 0.0, 0.020, 0.012, 0.075, STEEL, 0.003)      # guard
    B(0, 0.17, 0.004, 0.008, 0.19, 0.036, BLADE, 0.002)      # blade
    TIPCONE(0, 0.295, 0.004, 0.0185, 0, 0.06, BLADE)
    HAND(0.0, -0.01, 0.0, 1, 0.0); RIGHT_ARM(0.0, -0.01, 0.0)
    return (0, 0.325, 0.004)

WEAPONS = [('ar', build_ar), ('ak', build_ak), ('smg', build_smg), ('rifle', build_rifle),
           ('shotgun', build_shotgun), ('pistol', build_pistol), ('revolver', build_revolver),
           ('mpist', build_mpist), ('knife', build_knife)]
if ONLY:
    WEAPONS = [w for w in WEAPONS if w[0] == ONLY]
    if not WEAPONS:
        raise SystemExit('unknown weapon: ' + ONLY)

# ------------------------------------------------------------------ framing helpers
def to_screen(p):
    """world point -> (sx, sy) in camera-plane units (orthographic camera, right = +X, up = (0, sin, cos))"""
    return p[0], p[1] * SP + p[2] * CP

def part_bounds():
    bpy.context.view_layer.update()
    xs, ys = [], []
    for o in PARTS:
        m = o.matrix_world
        for c in o.bound_box:
            wx = m[0][0] * c[0] + m[0][1] * c[1] + m[0][2] * c[2] + m[0][3]
            wy = m[1][0] * c[0] + m[1][1] * c[1] + m[1][2] * c[2] + m[1][3]
            wz = m[2][0] * c[0] + m[2][1] * c[1] + m[2][2] * c[2] + m[2][3]
            sx, sy = to_screen((wx, wy, wz))
            xs.append(sx); ys.append(sy)
    return min(xs), max(xs), min(ys), max(ys)

def clear_parts():
    for o in PARTS:
        bpy.data.objects.remove(o, do_unlink=True)
    del PARTS[:]

# pass 1: find one camera framing that fits every weapon (same scale for all of them)
ux0 = uy0 = 1e9
ux1 = uy1 = -1e9
for name, fn in WEAPONS:
    fn()
    x0, x1, y0, y1 = part_bounds()
    ux0, ux1, uy0, uy1 = min(ux0, x0), max(ux1, x1), min(uy0, y0), max(uy1, y1)
    clear_parts()
cx, cy = (ux0 + ux1) / 2, (uy0 + uy1) / 2
ORTHO = max(ux1 - ux0, uy1 - uy0) * 1.06
print('[sprites] framing: ortho_scale=%.3f centre=(%.3f, %.3f)' % (ORTHO, cx, cy))

# ------------------------------------------------------------------ camera, lights, render settings
cam_data = bpy.data.cameras.new('cam')
cam_data.type = 'ORTHO'
cam_data.ortho_scale = ORTHO
cam_data.clip_start = 0.1
cam_data.clip_end = 60
cam = bpy.data.objects.new('cam', cam_data)
scene.collection.objects.link(cam)
cam.rotation_euler = (math.radians(90) - PITCH, 0, 0)
cam.location = (cx, cy * SP - 10 * CP, cy * CP + 10 * SP)
scene.camera = cam

def sun(name, energy, rot, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'SUN')
    ld.energy = energy
    ld.color = color
    lo = bpy.data.objects.new(name, ld)
    lo.rotation_euler = rot
    scene.collection.objects.link(lo)

sun('key',  3.2, (math.radians(48), math.radians(8), math.radians(-35)), (1.0, 0.95, 0.88))
sun('fill', 1.0, (math.radians(60), math.radians(-10), math.radians(55)), (0.80, 0.88, 1.0))
sun('rim',  1.6, (math.radians(120), 0, math.radians(160)))

world = bpy.data.worlds.new('w')
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs[0].default_value = (0.50, 0.53, 0.60, 1)
bg.inputs[1].default_value = 0.9
scene.world = world

r = scene.render
r.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = SAMPLES
try:
    scene.cycles.use_denoising = False
except Exception:
    pass
r.resolution_x = SIZE
r.resolution_y = SIZE
r.resolution_percentage = 100
r.film_transparent = True
r.image_settings.file_format = 'PNG'
r.image_settings.color_mode = 'RGBA'
try:
    scene.view_settings.view_transform = 'Standard'
except Exception:
    pass

# thin dark outline so the sprites read well at small size (optional - skipped if unsupported)
try:
    r.use_freestyle = True
    r.line_thickness = 1.2
    vl = bpy.context.view_layer
    vl.use_freestyle = True
    if not vl.freestyle_settings.linesets:
        vl.freestyle_settings.linesets.new('outline')
    ls = vl.freestyle_settings.linesets[0]
    ls.select_silhouette = True
    ls.select_border = True
    ls.select_crease = True
    ls.linestyle.color = (0.02, 0.02, 0.03)
    ls.linestyle.thickness = 1.6
except Exception as e:
    print('[sprites] outline skipped:', e)

# ------------------------------------------------------------------ render pass
tips = {}
for name, fn in WEAPONS:
    tip = fn()
    sx, sy = to_screen(tip)
    tips[name] = {'x': round(0.5 + (sx - cx) / ORTHO, 4), 'y': round(1.0 - (0.5 + (sy - cy) / ORTHO), 4)}
    bpy.context.view_layer.update()
    path = os.path.join(OUT, 'lo_%s.png' % name)
    r.filepath = path
    bpy.ops.render.render(write_still=True)
    print('[sprites] wrote', path, 'muzzle at', tips[name])
    clear_parts()

# merge with tips from earlier runs so --only does not lose the others
tips_path = os.path.join(OUT, 'lo_tips.js')
old = {}
try:
    txt = open(tips_path).read()
    old = json.loads(txt[txt.index('{'):txt.rindex('}') + 1])
except Exception:
    pass
old.update(tips)
with open(tips_path, 'w') as f:
    f.write('window.LO_TIPS=' + json.dumps(old) + ';\n')
print('[sprites] done ->', OUT)
