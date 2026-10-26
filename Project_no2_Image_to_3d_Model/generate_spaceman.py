#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
#  generate_spaceman.py
#
#  Procedural retro sci-fi "spaceman" (LL3M-style generator) — production build.
#
#  Builds a stylized cartoon astronaut entirely out of Blender primitives:
#
#    * Cyan metallic space helmet with an open face ring, translucent glass
#      visor, top antenna with a red beacon and side communication pods.
#    * Green big-brained alien head inside the visor (neck included): large
#      glossy black almond eyes, brow ridges and a frowning mouth.
#    * Padded orange spacesuit torso with chest control console (screen,
#      dials, buttons), corrugated breathing hoses, life-support backpack,
#      cyan harness straps and a cyan utility belt with buckle.
#    * Segmented orange arms with cyan shoulder pads, cuffs and chunky
#      mittens (with thumbs), orange legs with cyan knee pads and heavy
#      cyan space boots with soles and toe caps.
#
#  Pipeline guarantees:
#    * All colors are converted from sRGB hex to scene-linear before being
#      plugged into Principled BSDF inputs, so renders match the reference
#      swatches (Base Color expects linear values, not sRGB bytes).
#    * Bevel/solidify modifiers are baked AND smooth/sharp shading is
#      re-derived on the final topology before any exporter runs — all four
#      exported formats contain identical, correctly shaded geometry.
#    * Exports are pinned to an explicit selection (stock "selection only"
#      defaults differ per format and Blender version, which would silently
#      produce empty or contaminated files) and every artifact is
#      size-verified so a silent failure cannot slip through.
#    * A best-effort Workbench preview render (exports/preview.png) is
#      produced as a visual QA artifact; it never blocks the exports.
#
#  Compatibility : Blender 4.0+  (4.1 auto-smooth removal handled internally)
#  Usage         : blender --background --python generate_spaceman.py
#                  (or open in Blender's Text Editor and press "Run Script")
#  Success marker: "SPACEMAN_BUILD_OK" is printed to stdout on full success.
# =============================================================================

import bpy
import bmesh
import math
from mathutils import Vector
from pathlib import Path

# -----------------------------------------------------------------------------
# 0.  BOOTSTRAP  (make __file__ available when run from the Text Editor)
# -----------------------------------------------------------------------------
_f = globals().get("__file__")
if not _f or not str(_f).endswith(".py"):
    __file__ = bpy.data.filepath or str(Path.cwd() / "generate_spaceman.py")

# -----------------------------------------------------------------------------
# 1.  CONFIGURATION
#     (character is Z-up, stands on the XY plane, faces -Y; the +X side of
#     every paired part is mirrored onto -X)
# -----------------------------------------------------------------------------
HELMET_CENTER = Vector((0.0, 0.0, 2.42))      # helmet sphere centre
HELMET_RADIUS = 0.65                          # outer helmet radius (m)
VISOR_RADIUS  = 0.62                          # glass visor radius (m)
ALIEN_CENTER  = Vector((0.0, 0.01, 2.36))     # alien head centre
TORSO_CENTER  = Vector((0.0, 0.0, 1.375))     # suit torso centre
TORSO_DIMS    = (0.70, 0.50, 0.85)            # torso width / depth / height
SHOULDER_POS  = Vector((0.42, 0.00, 1.66))    # +X shoulder joint
ELBOW_POS     = Vector((0.485, 0.01, 1.38))   # +X elbow joint
WRIST_POS     = Vector((0.555, 0.02, 1.12))   # +X wrist joint
LEG_X         = 0.23                          # leg offset from centre line (sturdy stance)
SMOOTH_ANGLE  = 35.0                          # smooth-shading threshold (deg)

# -----------------------------------------------------------------------------
# 2.  GENERIC HELPERS
# -----------------------------------------------------------------------------
def clear_scene():
    """Remove every object and purge all orphan datablocks (recursive)."""
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    if bpy.context.selected_objects:
        bpy.ops.object.delete(use_global=False)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True,
                           do_recursive=True)


def _active():
    return bpy.context.view_layer.objects.active


def apply_scale(obj):
    """Bake object scale so bevel widths stay uniform in world space."""
    for o in list(bpy.context.selected_objects):
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def add_bevel(obj, width, segments=3, angle_deg=40.0):
    mod = obj.modifiers.new(name="Bevel", type='BEVEL')
    mod.width = width
    mod.segments = segments
    mod.limit_method = 'ANGLE'
    mod.angle_limit = math.radians(angle_deg)
    return mod


def shade_smart(obj, angle_deg=SMOOTH_ANGLE):
    """Smooth-shade faces while marking edges sharp above `angle_deg`.

    Implemented with raw sharp-edge flags so it works in every Blender
    version (use_auto_smooth was removed in 4.1; on 4.0 those flags are
    inert without the legacy auto-smooth setting, so it is enabled there).
    """
    me = obj.data
    threshold = math.radians(angle_deg)
    bm = bmesh.new()
    bm.from_mesh(me)
    for face in bm.faces:
        face.smooth = True
    for edge in bm.edges:
        if len(edge.link_faces) == 2:
            try:
                edge.smooth = edge.calc_face_angle() < threshold
            except ValueError:
                edge.smooth = True
        else:
            edge.smooth = True
    bm.to_mesh(me)
    bm.free()
    if bpy.app.version < (4, 1):
        me.use_auto_smooth = True          # 4.0: sharp edges need auto-smooth
        me.auto_smooth_angle = threshold
    me.update()


def delete_faces(obj, predicate):
    """Delete mesh faces (local space) matching `predicate(face)`.

    The 'FACES' delete context keeps orphaned wire geometry, so any edges
    left without faces (and verts left without edges) are swept afterwards.
    """
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    doomed = [f for f in bm.faces if predicate(f)]
    if doomed:
        bmesh.ops.delete(bm, geom=doomed, context='FACES')
        loose_edges = [e for e in bm.edges if not e.link_faces]
        if loose_edges:
            bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')
        loose_verts = [v for v in bm.verts if not v.link_edges]
        if loose_verts:
            bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')
    bm.to_mesh(me)
    bm.free()
    me.update()


def finish(obj, name, mat, smooth=True):
    """Name an object, assign a material and apply smart smooth shading."""
    obj.name = name
    if mat is not None:
        obj.data.materials.append(mat)
    if smooth:
        shade_smart(obj)
    return obj


def add_sphere(name, radius, location, mat, segments=48, rings=32,
               scale=None, rotation=None):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=radius, segments=segments, ring_count=rings,
        location=location, rotation=rotation or (0.0, 0.0, 0.0))
    obj = _active()
    if scale:
        obj.scale = scale
        apply_scale(obj)
    return finish(obj, name, mat)


def add_cube(name, location, dims, mat, rotation=None,
             bevel=0.0, bevel_segments=3):
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=location, rotation=rotation or (0.0, 0.0, 0.0))
    obj = _active()
    obj.scale = dims
    apply_scale(obj)
    if bevel and bevel > 0.0:
        add_bevel(obj, bevel, bevel_segments)
    return finish(obj, name, mat)


def add_cylinder(name, radius, depth, location, mat, rotation=None,
                 vertices=32, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius, depth=depth, vertices=vertices, location=location,
        rotation=rotation or (0.0, 0.0, 0.0))
    obj = _active()
    if bevel and bevel > 0.0:
        add_bevel(obj, bevel, 2)
    return finish(obj, name, mat)


def add_torus(name, major_radius, minor_radius, location, mat,
              rotation=None, major_segments=48, minor_segments=16):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius, minor_radius=minor_radius,
        major_segments=major_segments, minor_segments=minor_segments,
        location=location, rotation=rotation or (0.0, 0.0, 0.0))
    return finish(_active(), name, mat)


def tube_between(name, p1, p2, radius, mat, vertices=24):
    """Cylinder spanning two points (used for limbs and hose cores)."""
    p1, p2 = Vector(p1), Vector(p2)
    direction = p2 - p1
    if direction.length < 1e-6:
        raise ValueError(f"tube_between '{name}': degenerate segment")
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius, depth=direction.length, vertices=vertices,
        location=(p1 + p2) / 2.0)
    obj = _active()
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = direction.to_track_quat('Z', 'Y')
    return finish(obj, name, mat)


def join_objects(objs, name):
    """Join a list of objects into the first one and rename it."""
    objs = [o for o in objs if o is not None]
    if not objs:
        return None
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    objs[0].name = name
    return objs[0]


def find_layer_collection(parent_layer, collection):
    for layer in parent_layer.children:
        if layer.collection == collection:
            return layer
        nested = find_layer_collection(layer, collection)
        if nested is not None:
            return nested
    return None

# -----------------------------------------------------------------------------
# 3.  COLOR + MATERIALS  (Principled BSDF, version-tolerant socket names)
# -----------------------------------------------------------------------------
def _srgb_to_linear(c):
    """sRGB -> scene-linear channel conversion."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_rgba(hex_str, alpha=1.0):
    """'#E85D26' -> linear RGBA tuple for Principled 'Base Color'.

    Principled inputs are scene-linear; feeding them raw sRGB byte values
    washes every material out (worst on dark colors such as the console
    slate), so the conversion happens here, once, at the source.
    """
    h = hex_str.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (_srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b), alpha)


def _set_input(bsdf, names, value):
    """Set the first input socket that exists (4.x renamed several)."""
    for name in names:
        sock = bsdf.inputs.get(name)
        if sock is not None:
            sock.default_value = value
            return


def make_material(name, color, roughness=0.5, metallic=0.0, alpha=1.0,
                  transmission=0.0, subsurface=0.0, subsurface_radius=None,
                  emission=None, emission_strength=0.0):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes
                if n.type == 'BSDF_PRINCIPLED')

    _set_input(bsdf, ("Base Color",), color)
    _set_input(bsdf, ("Roughness",), roughness)
    _set_input(bsdf, ("Metallic",), metallic)
    _set_input(bsdf, ("Alpha",), alpha)
    _set_input(bsdf, ("Transmission Weight", "Transmission"), transmission)
    _set_input(bsdf, ("Subsurface Weight", "Subsurface"), subsurface)
    if subsurface_radius is not None:
        # green-dominant radius: the default is red-biased and would bleed
        # red through the alien skin in Cycles
        _set_input(bsdf, ("Subsurface Radius",), subsurface_radius)
    if emission is not None:
        _set_input(bsdf, ("Emission Color", "Emission"), emission)
        _set_input(bsdf, ("Emission Strength",), emission_strength)

    if alpha < 1.0:
        for attr, value in (("blend_method", "BLEND"),
                            ("shadow_method", "NONE")):
            try:
                setattr(mat, attr, value)
            except (AttributeError, TypeError):
                pass                      # property removed in newer EEVEE
    try:
        mat.diffuse_color = color         # viewport solid-mode color (linear)
    except (AttributeError, TypeError):
        pass
    return mat


def build_materials():
    """PBR palette (hex values converted to scene-linear)."""
    m = {}
    m["orange"]    = make_material("Suit_Orange",    hex_rgba("#E85D26"),
                                   roughness=0.55)
    m["cyan"]      = make_material("Cyan_Trim",      hex_rgba("#38A3C2"),
                                   roughness=0.30, metallic=0.35)
    m["cyan_dark"] = make_material("Cyan_Dark",      hex_rgba("#2A7A94"),
                                   roughness=0.40, metallic=0.30)
    m["green"]     = make_material("Alien_Skin",     hex_rgba("#7CB534"),
                                   roughness=0.45, subsurface=0.15,
                                   subsurface_radius=(0.012, 0.048, 0.016))
    m["black"]     = make_material("Eye_Glossy",     hex_rgba("#0D0D0D"),
                                   roughness=0.08)
    m["visor"]     = make_material("Visor_Glass",    hex_rgba("#88C8D8"),
                                   roughness=0.10, alpha=0.35,
                                   transmission=0.85)
    m["slate"]     = make_material("Console_Slate",  hex_rgba("#243342"),
                                   roughness=0.45, metallic=0.20)
    m["red"]       = make_material("Accent_Red",     hex_rgba("#E03B24"),
                                   roughness=0.40)
    m["yellow"]    = make_material("Accent_Yellow",  hex_rgba("#F5C518"),
                                   roughness=0.40)
    m["screen"]    = make_material("Console_Screen", hex_rgba("#9EE8F5"),
                                   roughness=0.20,
                                   emission=hex_rgba("#4DB3CC"),
                                   emission_strength=1.5)
    m["white"]     = make_material("White_Highlight", hex_rgba("#FFFFFF"),
                                   roughness=0.05, emission=hex_rgba("#FFFFFF"), emission_strength=2.0)
    return m

# -----------------------------------------------------------------------------
# 4.  HEAD & HELMET
# -----------------------------------------------------------------------------
def build_helmet(m):
    """Cyan helmet shell (open face), glass visor dome, collar, antenna, pods.

    The visor dome is deliberately seated ~2 cm proud of the shell rim and
    interpenetrates the collar torus — it reads as a glazed visor clamped
    into the collar ring, matching the reference artwork.
    """
    # --- shell with a circular front opening (bmesh cut, no booleans) ------
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=HELMET_RADIUS, segments=48, ring_count=32,
        location=HELMET_CENTER)
    helmet = finish(_active(), "Helmet_Shell", m["cyan"])
    delete_faces(helmet, lambda f: f.normal.y < -0.45)     # open the -Y face
    sol = helmet.modifiers.new(name="Solidify", type='SOLIDIFY')
    sol.thickness = 0.035
    sol.offset = -1.0                                      # shell grows inward

    # --- translucent glass visor dome (front cap of a slightly smaller,
    #     slightly forward-shifted sphere) ------------------------------------
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=VISOR_RADIUS, segments=48, ring_count=32,
        location=HELMET_CENTER + Vector((0.0, -0.05, 0.0)))
    visor = finish(_active(), "Helmet_Visor", m["visor"])
    delete_faces(visor, lambda f: f.normal.y > 0.35)       # keep front dome
    sol = visor.modifiers.new(name="Solidify", type='SOLIDIFY')
    sol.thickness = 0.012
    sol.offset = -1.0

    # --- chunky collar ring sealing shell rim and visor ---------------------
    add_torus("Helmet_Collar", 0.585, 0.055,
              HELMET_CENTER + Vector((0.0, -0.29, 0.0)), m["cyan"],
              rotation=(math.pi / 2, 0, 0))

    # --- antenna with red beacon ---------------------------------------------
    add_cylinder("Antenna_Base", 0.06, 0.05, (0.0, 0.0, 3.06), m["cyan"])
    add_cylinder("Antenna_Stalk", 0.02, 0.36, (0.0, 0.0, 3.25), m["slate"])
    add_sphere("Antenna_Beacon", 0.075, (0.0, 0.0, 3.46), m["red"],
               segments=32, rings=16)

    # --- ear pods (communication ports) --------------------------------------
    for s in (-1, 1):
        tag = "L" if s < 0 else "R"
        add_cylinder(f"EarPod_{tag}", 0.135, 0.10, (s * 0.66, 0.0, 2.42),
                     m["cyan"], rotation=(0, math.pi / 2, 0), bevel=0.012)
        add_cylinder(f"EarPod_Cap_{tag}", 0.085, 0.06, (s * 0.725, 0.0, 2.42),
                     m["slate"], rotation=(0, math.pi / 2, 0))
        add_cylinder(f"EarPod_Dot_{tag}", 0.03, 0.03, (s * 0.757, 0.0, 2.42),
                     m["red"], rotation=(0, math.pi / 2, 0), vertices=16)

# -----------------------------------------------------------------------------
# 5.  ALIEN HEAD (inside the visor)
# -----------------------------------------------------------------------------
def build_alien(m):
    """Green alien: neck, elongated skull, big glossy eyes, brows, frown."""
    # neck bridges torso top and skull (seals the helmet's bottom opening
    # and removes the floating-head gap visible through the visor)
    add_cylinder("Alien_Neck", 0.13, 0.34, (0.0, 0.01, 1.92), m["green"])
    add_sphere("Alien_Head", 0.40, ALIEN_CENTER, m["green"],
               scale=(0.95, 0.85, 1.15))                   # elongated skull

    for s in (-1, 1):
        tag = "L" if s < 0 else "R"
        # large almond eye: flattened, yawed + droopy tilted ellipsoid
        eye = add_sphere(f"Alien_Eye_{tag}", 1.0,
                         (s * 0.155, -0.315, 2.38), m["black"],
                         segments=32, rings=24, scale=(0.115, 0.055, 0.15))
        eye.rotation_euler = (0.0, s * math.radians(12), s * math.radians(25))
        # subtle brow ridge
        brow = add_cube(f"Alien_Brow_{tag}", (s * 0.14, -0.29, 2.58),
                        (0.17, 0.10, 0.045), m["green"], bevel=0.012)
        brow.rotation_euler = (0.0, s * math.radians(10), s * math.radians(15))
        # Cartoon eye specular catchlights
        add_sphere(f"Alien_Eye_Highlight_{tag}", 0.028, (s * 0.13, -0.365, 2.43), m["white"], segments=16, rings=12)
        add_sphere(f"Alien_Eye_Highlight_Small_{tag}", 0.015, (s * 0.17, -0.355, 2.37), m["white"], segments=12, rings=8)

    # frowning mouth: upper arc of a small torus, turned to face forward.
    # NOTE (local-space predicate): the torus is rotated +90 deg about X, so
    # its LOCAL +Y axis maps to WORLD +Z — keeping faces whose local centre
    # y >= 0.03 keeps the upper "frown" arc of the ring.
    mouth = add_torus("Alien_Mouth", 0.085, 0.014, (0.0, -0.315, 2.185),
                      m["black"], rotation=(math.pi / 2, 0, 0),
                      major_segments=32, minor_segments=12)
    delete_faces(mouth, lambda f: f.calc_center_median().y < 0.03)  # keep "∩"

# -----------------------------------------------------------------------------
# 6.  TORSO & LIFE SUPPORT
# -----------------------------------------------------------------------------
def build_torso(m):
    """Padded orange suit body, belt, chest console, backpack, straps."""
    add_cube("Suit_Torso", TORSO_CENTER, TORSO_DIMS, m["orange"],
             bevel=0.07, bevel_segments=5)

    # utility belt + buckle (raised to the true waist line)
    add_cube("Utility_Belt", (0.0, 0.0, 1.18), (0.76, 0.545, 0.115),
             m["cyan"], bevel=0.03, bevel_segments=4)
    add_cube("Belt_Buckle", (0.0, -0.29, 1.18), (0.17, 0.05, 0.14),
             m["slate"], bevel=0.015)
    add_cube("Belt_Buckle_Plate", (0.0, -0.315, 1.18), (0.11, 0.02, 0.09),
             m["cyan"])

    # chest control pack: console, screen, dials, buttons
    add_cube("Chest_Console", (0.0, -0.28, 1.52), (0.36, 0.10, 0.28),
             m["slate"], bevel=0.02)
    add_cube("Console_Screen", (-0.06, -0.335, 1.565), (0.19, 0.025, 0.13),
             m["screen"], bevel=0.008)
    add_cylinder("Console_Dial_A", 0.04, 0.04, (0.115, -0.335, 1.585),
                 m["yellow"], rotation=(math.pi / 2, 0, 0), vertices=24)
    add_cylinder("Console_Dial_B", 0.04, 0.04, (0.115, -0.335, 1.50),
                 m["red"], rotation=(math.pi / 2, 0, 0), vertices=24)
    for i, (x, key) in enumerate(((-0.115, "red"), (-0.06, "yellow"),
                                  (-0.005, "cyan"))):
        add_cylinder(f"Console_Button_{i + 1}", 0.022, 0.035,
                     (x, -0.335, 1.435), m[key],
                     rotation=(math.pi / 2, 0, 0), vertices=16)

    # life-support backpack + vents + valves
    add_cube("Backpack", (0.0, 0.30, 1.45), (0.46, 0.20, 0.58), m["orange"],
             bevel=0.04, bevel_segments=4)
    for i, z in enumerate((1.29, 1.41, 1.53)):
        add_cube(f"Backpack_Vent_{i + 1}", (0.0, 0.405, z),
                 (0.30, 0.03, 0.04), m["slate"])
    for s in (-1, 1):
        tag = "L" if s < 0 else "R"
        add_cylinder(f"Backpack_Valve_{tag}", 0.045, 0.12,
                     (s * 0.16, 0.30, 1.79), m["cyan"], vertices=20)

    # cyan harness straps over the shoulders — thin enough to slip under the
    # helmet rim, outer ends tuck beneath the shoulder pads
    for s in (-1, 1):
        tag = "L" if s < 0 else "R"
        add_cube(f"Harness_Strap_{tag}", (s * 0.24, 0.0, 1.80),
                 (0.09, 0.54, 0.02), m["cyan"], bevel=0.008)

# -----------------------------------------------------------------------------
# 7.  ARMS, GLOVES, LEGS & BOOTS
# -----------------------------------------------------------------------------
def build_arms(m):
    """Segmented orange sleeves, cyan shoulder pads, cuffs and mittens."""
    for s in (-1, 1):
        tag = "L" if s < 0 else "R"
        shoulder = Vector((s * SHOULDER_POS.x, SHOULDER_POS.y, SHOULDER_POS.z))
        elbow    = Vector((s * ELBOW_POS.x,    ELBOW_POS.y,    ELBOW_POS.z))
        wrist    = Vector((s * WRIST_POS.x,    WRIST_POS.y,    WRIST_POS.z))

        add_sphere(f"Shoulder_Pad_{tag}", 0.17, (s * 0.40, 0.0, 1.80),
                   m["cyan"], segments=32, rings=24, scale=(1.0, 0.95, 0.75))
        add_sphere(f"Arm_Shoulder_{tag}", 0.115, shoulder, m["orange"],
                   segments=24, rings=16)
        tube_between(f"Arm_Upper_{tag}", shoulder, elbow, 0.115, m["orange"])
        add_sphere(f"Arm_Elbow_{tag}", 0.115, elbow, m["orange"],
                   segments=24, rings=16)
        tube_between(f"Arm_Forearm_{tag}", elbow, wrist, 0.10, m["orange"])

        arm_dir = (wrist - elbow).normalized()
        tube_between(f"Glove_Cuff_{tag}", wrist - arm_dir * 0.02,
                     wrist + arm_dir * 0.06, 0.105, m["cyan"])
        glove_c = wrist + arm_dir * 0.14
        add_sphere(f"Glove_{tag}", 0.15, glove_c, m["cyan"],
                   segments=32, rings=24, scale=(0.95, 0.90, 1.05))
        # thumb on the INNER face of the mitten, yawed so it splays
        # forward-outward (a straight forward-pointing thumb reads wrong)
        thumb = add_sphere(f"Glove_Thumb_{tag}", 0.055,
                           glove_c + Vector((-s * 0.11, -0.04, 0.03)),
                           m["cyan"], segments=20, rings=12,
                           scale=(0.8, 1.5, 0.9))
        thumb.rotation_euler = (0.0, 0.0, s * math.radians(35))
        # Orange glove pad on back of mitten
        add_cube(f"Glove_Pad_{tag}", glove_c + Vector((s * 0.05, -0.10, 0.02)), (0.08, 0.035, 0.09), m["orange"], bevel=0.01)


def build_legs(m):
    """Orange legs, cyan knee pads and heavy cyan boots."""
    for s in (-1, 1):
        tag = "L" if s < 0 else "R"
        x = s * LEG_X
        tube_between(f"Leg_{tag}", (x, 0.0, 1.00), (x, 0.0, 0.30),
                     0.145, m["orange"], vertices=32)
        add_sphere(f"Knee_Pad_{tag}", 0.135, (x, -0.125, 0.62),
                   m["cyan"], segments=32, rings=24, scale=(1.0, 0.55, 1.15))
        add_cube(f"Boot_Sole_{tag}", (x, -0.04, 0.045),
                 (0.30, 0.44, 0.09), m["cyan_dark"], bevel=0.02)
        add_cube(f"Boot_Body_{tag}", (x, -0.03, 0.20),
                 (0.27, 0.38, 0.22), m["cyan"], bevel=0.05, bevel_segments=4)
        # toe cap kept over the sole footprint (no floating toe)
        add_sphere(f"Boot_Toe_Cap_{tag}", 0.14, (x, -0.13, 0.16),
                   m["cyan"], segments=32, rings=16, scale=(1.0, 0.85, 0.7))
        add_cylinder(f"Boot_Cuff_{tag}", 0.16, 0.09, (x, 0.0, 0.325),
                     m["cyan"], vertices=32)

# -----------------------------------------------------------------------------
# 8.  BREATHING HOSES (corrugated pipes, chest console -> backpack)
# -----------------------------------------------------------------------------
def build_hoses(m):
    """Corrugated breathing hoses: chest console -> around the sides ->
    backpack.

    Each run is a solid core tube dressed with torus corrugation rings —
    the core guarantees a closed, see-through-free hose (rings alone would
    leave gaps between the tori).  The route dips below the belt line
    (z = 1.06 < belt bottom 1.12) and stays forward of the forearm, so it
    clears the belt, the forearm and the torso side everywhere.
    """
    for s in (-1, 1):
        tag = "L" if s < 0 else "R"
        waypoints = [
            Vector((s * 0.17, -0.31, 1.44)),   # chest console (embedded)
            Vector((s * 0.36, -0.32, 1.26)),   # curved elbow at the waist
            Vector((s * 0.40, -0.32, 1.06)),   # descend in front of the belt
            Vector((s * 0.40,  0.32, 1.06)),   # along the side, under the belt
            Vector((s * 0.20,  0.34, 1.22)),   # up into the backpack
        ]
        parts = []
        # rounded joint spheres at the interior corners
        for j, wp in enumerate(waypoints[1:-1], start=1):
            parts.append(add_sphere(f"Hose_Joint_{tag}_{j}", 0.042, wp,
                                    m["slate"], segments=20, rings=12))
        # solid core + corrugation rings along every segment
        for i in range(len(waypoints) - 1):
            a, b = waypoints[i], waypoints[i + 1]
            seg = b - a
            direction = seg.normalized()
            parts.append(tube_between(f"Hose_Core_{tag}_{i}", a, b,
                                      0.038, m["slate"], vertices=16))
            # ring spacing <= tube diameter: corrugations visibly overlap
            n = max(2, math.ceil(seg.length / 0.05))
            for k in range(n):
                loc = a + seg * ((k + 0.5) / n)
                bpy.ops.mesh.primitive_torus_add(
                    major_radius=0.040, minor_radius=0.012,
                    major_segments=18, minor_segments=8, location=loc)
                ring = _active()
                ring.rotation_mode = 'QUATERNION'
                ring.rotation_quaternion = direction.to_track_quat('Z', 'Y')
                finish(ring, f"Hose_Ring_{tag}_{i}_{k:02d}", m["slate"])
                parts.append(ring)
        join_objects(parts, f"Breathing_Hose_{tag}")

# -----------------------------------------------------------------------------
# 9.  SCENE ASSEMBLY / MODIFIER BAKING / VALIDATION / MULTI-FORMAT EXPORT
# -----------------------------------------------------------------------------
def build_spaceman():
    mats = build_materials()

    coll = bpy.data.collections.get("Spaceman")
    if coll is None:
        coll = bpy.data.collections.new("Spaceman")
    if "Spaceman" not in [c.name for c in
                          bpy.context.scene.collection.children]:
        bpy.context.scene.collection.children.link(coll)
    layer = find_layer_collection(
        bpy.context.view_layer.layer_collection, coll)
    if layer is not None:
        bpy.context.view_layer.active_layer_collection = layer

    build_helmet(mats)
    build_alien(mats)
    build_torso(mats)
    build_arms(mats)
    build_legs(mats)
    build_hoses(mats)
    return coll


def apply_all_modifiers(objects):
    """Bake bevel/solidify so all four exporters emit identical geometry,
    then re-derive smooth/sharp shading on the FINAL topology (shading was
    computed on pre-modifier geometry at creation time)."""
    for obj in objects:
        if obj.type != 'MESH' or not obj.modifiers:
            continue
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        for mod in list(obj.modifiers):
            try:
                bpy.ops.object.modifier_apply(modifier=mod.name)
            except Exception as exc:
                print(f"    ! could not apply '{mod.name}' "
                      f"on '{obj.name}': {exc}")
        shade_smart(obj)


def validate(objects):
    """LL3M-style self-check: mesh presence, floor contact, overall size."""
    meshes = [o for o in objects if o.type == 'MESH']
    if not meshes:
        raise RuntimeError("generator produced no mesh objects")
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    zmin, zmax = min(p.z for p in pts), max(p.z for p in pts)
    if zmin < -1e-4:
        print(f"    ! model sinks below the floor (zmin={zmin:.3f})")
    print(f"    bbox: {zmax - zmin:.2f} m tall (z {zmin:.2f}..{zmax:.2f}), "
          f"{len(meshes)} mesh objects")


def export_all(objects):
    """Export the finished model to GLB / OBJ / STL / FBX.

    Selection is set explicitly and every exporter is pinned to it — stock
    defaults differ per format and version (the new STL exporter defaults
    to selection-only, glTF/FBX default to the whole scene), which would
    silently produce empty or contaminated files.  Each artifact is
    size-checked so a silent failure cannot pass unnoticed.

    NOTE: FBX has no transmission parameter — the visor exports there as
    alpha-blended transparency (by design, not a bug).
    """
    from pathlib import Path
    exports_dir = Path(__file__).resolve().parent / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    if not objects:
        raise RuntimeError("nothing to export")

    print(f"Exporting spaceman to: {exports_dir}")

    # Export EXACTLY the generated model, regardless of exporter defaults.
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]

    jobs = (
        ("spaceman.glb", lambda p: bpy.ops.export_scene.gltf(
            filepath=str(p), export_format='GLB',
            use_selection=True, export_apply=True)),      # belt-and-braces
        ("spaceman.obj", lambda p: bpy.ops.wm.obj_export(
            filepath=str(p), export_selected_objects=True)),
        ("spaceman.stl", lambda p: bpy.ops.wm.stl_export(
            filepath=str(p), export_selected_objects=True)),
        ("spaceman.fbx", lambda p: bpy.ops.export_scene.fbx(
            filepath=str(p), use_selection=True)),
    )
    failures = []
    for i, (fname, exporter) in enumerate(jobs, 1):
        path = exports_dir / fname
        try:
            exporter(path)
            size = path.stat().st_size if path.exists() else 0
            if size < 1024:   # an empty binary STL is ~84 bytes
                raise RuntimeError(f"output suspiciously small ({size} B)")
            print(f"    [{i}/4] {fname}  ({size / 1024:.1f} KiB)")
        except Exception as exc:
            failures.append((fname, str(exc)))
            print(f"    [{i}/4] {fname}  FAILED: {exc}")
    if failures:
        raise RuntimeError(f"export failures: {failures}")
    return exports_dir


def render_preview(exports_dir):
    """Best-effort QA artifact: a Workbench preview render of the model.

    Strictly optional — headless environments without a GPU/EGL context
    cannot do real-time renders, so any failure here is logged and swallowed
    (the four exports above are the critical deliverables).
    """
    try:
        scene = bpy.context.scene
        cam_data = bpy.data.cameras.new("PreviewCamera")
        cam = bpy.data.objects.new("PreviewCamera", cam_data)
        scene.collection.objects.link(cam)
        target = Vector((0.0, 0.0, 1.75))
        origin = Vector((3.4, -5.2, 2.3))
        cam.location = origin
        cam.rotation_mode = 'QUATERNION'
        cam.rotation_quaternion = (target - origin).to_track_quat('-Z', 'Y')
        scene.camera = cam

        sun_data = bpy.data.lights.new("PreviewSun", type='SUN')
        sun_data.energy = 3.0
        sun = bpy.data.objects.new("PreviewSun", sun_data)
        scene.collection.objects.link(sun)
        sun.rotation_euler = (math.radians(45), 0.0, math.radians(-35))

        fill_data = bpy.data.lights.new("PreviewFill", type='POINT')
        fill_data.energy = 50.0
        fill = bpy.data.objects.new("PreviewFill", fill_data)
        scene.collection.objects.link(fill)
        fill.location = Vector((0.0, -1.8, 2.4))

        scene.render.engine = 'CYCLES'
        scene.cycles.samples = 24
        scene.cycles.adaptive_threshold = 0.05
        scene.render.resolution_x = 800
        scene.render.resolution_y = 800
        scene.render.image_settings.file_format = 'PNG'
        scene.render.filepath = str(exports_dir / "preview.png")
        bpy.ops.render.render(write_still=True)
        print("    [+] preview.png  (QA render)")
    except Exception as exc:
        print(f"    ! preview render skipped: {exc}")


def main():
    print("=== LL3M generator: retro spaceman ===")
    if bpy.app.version < (4, 0):
        raise RuntimeError(
            f"Blender >= 4.0 required (wm.stl_export / wm.obj_export), "
            f"found {bpy.app.version_string}")
    clear_scene()
    coll = build_spaceman()
    objects = list(coll.objects)
    apply_all_modifiers(objects)
    validate(objects)
    exports_dir = export_all(objects)
    render_preview(exports_dir)
    faces = sum(len(o.data.polygons) for o in objects if o.type == 'MESH')
    print(f"=== SPACEMAN_BUILD_OK - {len(objects)} objects, "
          f"{faces:,} faces ===")


if __name__ == "__main__":
    main()