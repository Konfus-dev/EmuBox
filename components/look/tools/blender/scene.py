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
WANTED = set(ARGS[1:]) or {"wall", "claw", "ring"}

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


def claw(scene):
    """Four metal fingers that come round from behind the orb, hug its edge, and curl out at the tips."""
    orb_camera(scene)
    world_colour(scene, (0.01, 0.05, 0.01), 0.6)
    even_lights()
    holdout_ball()
    metal = material("claw", GREEN_METAL, metallic=1.0, roughness=0.32, emission=((0.05, 0.3, 0.03), 0.4))
    # (where round the orb the finger starts, how far round it wraps, how far the tip flicks out, how thick)
    # Four identical fingers, a quarter turn apart: the theme turns the claw 90 degrees per move.
    for start, sweep, flick, thick in ((-150 + 90 * k, 92, 0.85, 0.16) for k in range(4)):
        spine, radii, steps = [], [], 80
        for i in range(steps + 1):
            u = i / steps
            a = math.radians(start + sweep * u)
            r = 0.97 + 0.06 * math.sin(math.pi * u) + flick * u ** 3          # tight round the edge, then away
            z = -0.75 * (1 - u) ** 2 + 0.35 * math.sin(math.pi * min(1.0, u * 1.2))   # from behind, over the rim
            spine.append(Vector((r * math.cos(a), r * math.sin(a), z)))
            radii.append(thick * math.sin(math.pi * min(1.0, 0.15 + u)) ** 0.6 * (1 - u ** 3))
        finger = tube("finger", spine, radii)
        finger.data.materials.append(metal)
    scene.cycles.samples = 96
    scene.render.filepath = str(OUT / "rings_a.png")
    bpy.ops.render.render(write_still=True)


def ring(scene, notches=12, radius=1.52, thick=0.035):
    """A flat metal ring round the orb, broken into evenly spaced pieces so that its turn shows."""
    orb_camera(scene)
    world_colour(scene, (0.01, 0.05, 0.01), 0.6)
    lights()
    metal = material("ring", GREEN_METAL, metallic=1.0, roughness=0.25, emission=((0.05, 0.3, 0.03), 0.3))
    gap = math.radians(3.5)
    for k in range(notches):
        a0, a1 = 2 * math.pi * k / notches + gap / 2, 2 * math.pi * (k + 1) / notches - gap / 2
        spine = [Vector((radius * math.cos(a0 + (a1 - a0) * i / 30), radius * math.sin(a0 + (a1 - a0) * i / 30), 0)) for i in range(31)]
        piece = tube("ring", spine, [thick] * 31, sides=16)
        piece.data.materials.append(metal)
    scene.cycles.samples = 64
    scene.render.filepath = str(OUT / "rings_b.png")
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
if "ring" in WANTED:
    ring(fresh())
if "wall" in WANTED:
    wall(fresh(), "bg_system.jpg", 1.0, centre=(25, -2))   # the far end behind the orb (at 0.27 across)
    wall(fresh(), "bg_list.jpg", 0.6)
