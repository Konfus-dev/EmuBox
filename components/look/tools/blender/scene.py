"""Renders the theme's 3D parts in Blender (see README.md here).

    blender -b -P tools/blender/scene.py -- <art folder> [wall|claw|ring ...]

With no names after the folder, renders all of them.
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGS[0]) if ARGS else HERE.parent.parent / "files" / "theme" / "art"
WANTED = set(ARGS[1:]) or {"wall", "claw"}

# The orb's size in the rings' pictures (art.py's SPHERE_R): radius 1 here is that fraction of the picture.
SPHERE_R = 0.227
GREEN_METAL = (0.07, 0.42, 0.05)


def fresh() -> bpy.types.Scene:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = "Standard"     # colours as chosen, not filmic
    scene.world = bpy.data.worlds.new("world")
    scene.world.use_nodes = True
    return scene


def world_colour(scene, colour, strength=1.0):
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*colour, 1)
    bg.inputs["Strength"].default_value = strength


def material(name, colour, metallic=1.0, roughness=0.3, emission=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*colour, 1)
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = roughness
    if "Coat Weight" in p.inputs:
        p.inputs["Coat Weight"].default_value = 0.4
        p.inputs["Coat Roughness"].default_value = 0.15
    if emission:
        p.inputs["Emission Color"].default_value = (*emission[0], 1)
        p.inputs["Emission Strength"].default_value = emission[1]
    return m


def tube(name, spine, radii, sides=24):
    """A smooth tube along a list of points, its thickness given per point (0 makes a point)."""
    verts, faces = [], []
    for i, (p, r) in enumerate(zip(spine, radii)):
        ahead = spine[min(i + 1, len(spine) - 1)] - spine[max(i - 1, 0)]
        ahead.normalize()
        side = ahead.cross(Vector((0, 0, 1)))
        if side.length < 1e-4:
            side = ahead.cross(Vector((0, 1, 0)))
        side.normalize()
        up = side.cross(ahead)
        # A slightly flattened section: wider across the ball than out from it, like a blade.
        for k in range(sides):
            a = 2 * math.pi * k / sides
            verts.append(p + side * math.cos(a) * r * 1.35 + up * math.sin(a) * r * 0.8)
    for i in range(len(spine) - 1):
        for k in range(sides):
            a, b = i * sides + k, i * sides + (k + 1) % sides
            faces.append((a, b, b + sides, a + sides))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def orb_camera(scene, size=1000):
    """Looking straight at the orb (radius 1 at the middle), framed like the theme's ring pictures."""
    cam = bpy.data.cameras.new("camera")
    cam.type = "ORTHO"
    cam.ortho_scale = 1 / SPHERE_R              # the picture is 1/SPHERE_R sphere radii across
    obj = bpy.data.objects.new("camera", cam)
    obj.location = (0, 0, 20)
    bpy.context.collection.objects.link(obj)
    scene.camera = obj
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"


def lights():
    """A soft key light from the top left and in front, a green fill from below right, a rim behind."""
    for name, kind, where, energy, colour, size in (
            ("key", "AREA", (-6, 7, 9), 2600, (1.0, 1.0, 0.92), 6),
            ("fill", "AREA", (7, -6, 5), 700, (0.45, 1.0, 0.35), 8),
            ("rim", "AREA", (0, 0, -9), 900, (0.6, 1.0, 0.5), 10)):
        data = bpy.data.lights.new(name, kind)
        data.energy, data.color, data.size = energy, colour, size
        obj = bpy.data.objects.new(name, data)
        obj.location = where
        direction = -Vector(where)
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        bpy.context.collection.objects.link(obj)


def even_lights():
    """Light that looks the same after a quarter turn: four soft lights round the front, one behind.
    The claw turns 90 degrees on each move and snaps back after; lit like this, the snap can't be seen."""
    for k in range(4):
        a = math.radians(45 + 90 * k)
        data = bpy.data.lights.new(f"key{k}", "AREA")
        data.energy, data.color, data.size = 900, (0.85, 1.0, 0.8), 5
        obj = bpy.data.objects.new(f"key{k}", data)
        obj.location = (7 * math.cos(a), 7 * math.sin(a), 8)
        obj.rotation_euler = (-Vector(obj.location)).to_track_quat("-Z", "Y").to_euler()
        bpy.context.collection.objects.link(obj)
    data = bpy.data.lights.new("rim", "AREA")
    data.energy, data.color, data.size = 900, (0.6, 1.0, 0.5), 10
    obj = bpy.data.objects.new("rim", data)
    obj.location = (0, 0, -9)
    obj.rotation_euler = (math.pi, 0, 0)
    bpy.context.collection.objects.link(obj)


def holdout_ball():
    """The orb itself, unseen: it hides whatever is behind it, so only what shows round it is kept."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=64, ring_count=32)
    ball = bpy.context.active_object
    ball.is_holdout = True
    return ball


def glow_glass(name, colour=(0.06, 0.50, 0.05)):
    """The dashboard's look for its machinery: green, lit from within, brighter where a surface
    turns away from you (its edges), and a little see-through."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    n.clear()
    out = n.new("ShaderNodeOutputMaterial")
    body = n.new("ShaderNodeBsdfPrincipled")
    body.inputs["Base Color"].default_value = (*colour, 1)
    body.inputs["Metallic"].default_value = 0.6
    body.inputs["Roughness"].default_value = 0.3
    glow = n.new("ShaderNodeEmission")
    glow.inputs["Color"].default_value = (colour[0] * 1.6, colour[1] * 1.5, colour[2] * 1.6, 1)
    edge = n.new("ShaderNodeLayerWeight")
    edge.inputs["Blend"].default_value = 0.45
    strength = n.new("ShaderNodeMath")
    strength.operation = "MULTIPLY_ADD"
    strength.inputs[1].default_value = 1.3                      # edges glow
    strength.inputs[2].default_value = 0.22                     # faces a little
    l.new(edge.outputs["Facing"], strength.inputs[0])
    l.new(strength.outputs[0], glow.inputs["Strength"])
    add = n.new("ShaderNodeAddShader")
    l.new(body.outputs[0], add.inputs[0])
    l.new(glow.outputs[0], add.inputs[1])
    see = n.new("ShaderNodeBsdfTransparent")
    mix = n.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.62                     # partly see-through, as the dashboard draws it
    l.new(see.outputs[0], mix.inputs[1])
    l.new(add.outputs[0], mix.inputs[2])
    l.new(mix.outputs[0], out.inputs["Surface"])
    return m


def arm_path(u):
    """How far out (r) and how far forward (z) an arm is, from its clip on the ring (u=0) to its
    tip over the orb's edge (u=1)."""
    r = 1.86 - 0.95 * (1 - (1 - u) ** 1.7)
    z = 0.10 + 0.20 * math.sin(math.pi * u * 0.9)
    return r, z


def bracket(name, start, sweep, holes=2):
    """One arm of the claw: a flat curved bracket that leaves the ring, sweeps in over the edge of
    the orb and on behind it, lying on the orb's curve like a band, with round holes through it."""
    rows, verts, faces = 48, [], []
    for i in range(rows + 1):
        u = i / rows
        a = math.radians(start + sweep * u)
        r, z = arm_path(u)
        p = Vector((r * math.cos(a), r * math.sin(a), z))
        ahead = (Vector((r * math.cos(a + 0.02), r * math.sin(a + 0.02), z)) - p).normalized()
        flat = ahead.cross(Vector((0, 0, 1))).normalized()    # across the arm, in the ring's plane
        tilt = 0.9 * u                                        # turning in towards the orb as it goes: reads as 3D
        side = (flat * math.cos(tilt) + Vector((0, 0, 1)) * math.sin(tilt)).normalized()
        face = ahead.cross(side).normalized()
        width = (0.50 - 0.14 * u) * min(1.0, 0.55 + u * 4)   # narrow where it leaves the clip
        thick = 0.07
        for sx in (-1, 1):
            for sz in (-1, 1):
                verts.append(p + side * sx * width / 2 + face * sz * thick / 2)
    for i in range(rows):
        a, b = 4 * i, 4 * (i + 1)
        # four corners per section: (-side,-out) (-side,+out) (+side,-out) (+side,+out)
        for c0, c1 in ((0, 1), (1, 3), (3, 2), (2, 0)):
            faces.append((a + c0, a + c1, b + c1, b + c0))
    faces.append((0, 1, 3, 2))
    last = 4 * rows
    faces.append((last, last + 2, last + 3, last + 1))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    arm = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(arm)
    for k in range(holes):                                    # the round holes, punched straight through
        u = (k + 1) / (holes + 1) * 0.8 + 0.08
        a = math.radians(start + sweep * u)
        r, z = arm_path(u)
        p = Vector((r * math.cos(a), r * math.sin(a), z))
        bpy.ops.mesh.primitive_cylinder_add(radius=0.10 - 0.025 * u, depth=0.6, location=p)
        cutter = bpy.context.active_object
        cutter.rotation_euler = Vector((0, 0, 1)).lerp(p.normalized(), 0.9 * u * 0.6).normalized().to_track_quat("Z", "Y").to_euler()
        cut = arm.modifiers.new("hole", "BOOLEAN")
        cut.operation, cut.object = "DIFFERENCE", cutter
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.modifier_apply(modifier=cut.name)
        bpy.data.objects.remove(cutter)
    bevel = arm.modifiers.new("soft edges", "BEVEL")
    bevel.width, bevel.segments = 0.012, 2
    return arm


def claw(scene):
    """The orb's holder, after the classic dashboard's: a thick flat ring with four loop clips, and
    four bracket arms reaching in from it over the orb's edge and round behind it. Everything a
    quarter turn apart (the theme turns it 90 degrees per move) and lit only by its own glow, so
    each quarter turn looks the same."""
    orb_camera(scene)
    world_colour(scene, (0.0, 0.0, 0.0), 0.0)
    even_lights()
    holdout_ball()
    look = glow_glass("claw")
    ring_line = [Vector((1.86 * math.cos(2 * math.pi * i / 128), 1.86 * math.sin(2 * math.pi * i / 128), 0.1)) for i in range(129)]
    band = tube("ring", ring_line, [0.085] * 129, sides=16)
    band.data.materials.append(look)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.17, minor_radius=0.035,
                                         location=(1.86 * math.cos(a), 1.86 * math.sin(a), 0.1))
        clip = bpy.context.active_object
        clip.rotation_euler = Vector((-math.sin(a), math.cos(a), 0)).to_track_quat("Z", "Y").to_euler()   # loops round the band
        clip.data.materials.append(look)
        arm = bracket(f"arm{k}", 45 + 90 * k, 70)
        arm.data.materials.append(look)
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and not obj.is_holdout:
            for poly in obj.data.polygons:
                poly.use_smooth = True
    scene.cycles.samples = 96
    scene.render.filepath = str(OUT / "rings_a.png")
    bpy.ops.render.render(write_still=True)


def wall(scene, name, brightness, centre=(0.0, 0.0)):
    """The tunnel of cells: the inside of a globe covered in the cell tile, glowing green, dark
    straight ahead and brighter towards the sides, seen from near its middle towards a pole."""
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.quality = 92
    world_colour(scene, (0, 0, 0), 0)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=500, segments=128, ring_count=64)
    globe = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    m = bpy.data.materials.new("cells")
    m.use_nodes = True
    nodes, links = m.node_tree.nodes, m.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(HERE / "cell_tile.png"))
    tex.image.colorspace_settings.name = "Non-Color"   # its values as they are: the lines are the bright green
    tex.interpolation = "Cubic"
    coords = nodes.new("ShaderNodeTexCoord")
    scale = nodes.new("ShaderNodeMapping")
    scale.inputs["Scale"].default_value = (50, 25, 1)              # as in the Unity scene
    links.new(coords.outputs["UV"], scale.inputs["Vector"])
    links.new(scale.outputs["Vector"], tex.inputs["Vector"])
    # The tile's lines, apart from its dark green ground: brightest green value is the line.
    lines = nodes.new("ShaderNodeMapRange")
    sep = nodes.new("ShaderNodeSeparateColor")
    links.new(tex.outputs["Color"], sep.inputs["Color"])
    links.new(sep.outputs["Green"], lines.inputs["Value"])
    lines.inputs["From Min"].default_value = 0.22
    lines.inputs["From Max"].default_value = 0.36
    # Darker straight ahead (near the pole the camera faces), brighter out to the sides.
    obj_coords = nodes.new("ShaderNodeTexCoord")
    axis = nodes.new("ShaderNodeVectorMath"); axis.operation = "NORMALIZE"
    links.new(obj_coords.outputs["Object"], axis.inputs[0])
    sepz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(axis.outputs["Vector"], sepz.inputs["Vector"])
    falloff = nodes.new("ShaderNodeMapRange")
    links.new(sepz.outputs["Z"], falloff.inputs["Value"])
    falloff.inputs["From Min"].default_value = 0.98
    falloff.inputs["From Max"].default_value = 0.55
    falloff.inputs["To Min"].default_value = 0.05
    falloff.inputs["To Max"].default_value = 1.0
    level = nodes.new("ShaderNodeMath"); level.operation = "MULTIPLY"
    links.new(lines.outputs["Result"], level.inputs[0])
    links.new(falloff.outputs["Result"], level.inputs[1])
    ground = nodes.new("ShaderNodeMath"); ground.operation = "MULTIPLY_ADD"     # a faint green between the lines
    links.new(falloff.outputs["Result"], ground.inputs[0])
    ground.inputs[1].default_value = 0.06
    links.new(level.outputs["Value"], ground.inputs[2])
    links.new(ground.outputs["Value"], emit.inputs["Strength"])
    emit.inputs["Color"].default_value = (0.25 * brightness, 1.0 * brightness, 0.12 * brightness, 1)
    links.new(emit.outputs["Emission"], out.inputs["Surface"])
    globe.data.materials.append(m)
    # The pole is straight ahead along +Z; the camera sits near the middle looking at it.
    cam = bpy.data.cameras.new("camera")
    cam.angle = math.radians(60)
    cam.sensor_fit = "VERTICAL"
    cam.clip_end = 2000
    obj = bpy.data.objects.new("camera", cam)
    obj.location = (0, 0, -4.67)
    obj.rotation_euler = (math.radians(180) + math.radians(centre[1]), math.radians(centre[0]), 0)
    bpy.context.collection.objects.link(obj)
    scene.camera = obj
    scene.cycles.samples = 24
    scene.render.filepath = str(OUT / name)
    bpy.ops.render.render(write_still=True)


if "claw" in WANTED:
    claw(fresh())
if "wall" in WANTED:
    wall(fresh(), "bg_system.jpg", 1.0, centre=(25, -2))   # the far end behind the orb (at 0.27 across)
    wall(fresh(), "bg_list.jpg", 0.6)
