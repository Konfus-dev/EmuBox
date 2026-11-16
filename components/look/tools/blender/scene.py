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
WANTED = set(ARGS[1:]) or {"wall", "claw", "rowarm"}

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


def tube(name, spine, radii, sides=24, closed=False):
    """A smooth tube along a list of points, its thickness given per point (0 makes a point).
    closed: the spine is a loop, and its last point joins back to its first without a seam."""
    verts, faces = [], []
    n = len(spine)
    for i, (p, r) in enumerate(zip(spine, radii)):
        if closed:
            ahead = spine[(i + 1) % n] - spine[(i - 1) % n]
        else:
            ahead = spine[min(i + 1, n - 1)] - spine[max(i - 1, 0)]
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
    for i in range(n if closed else n - 1):
        j = (i + 1) % n
        for k in range(sides):
            a, b = i * sides + k, i * sides + (k + 1) % sides
            faces.append((a, b, j * sides + (k + 1) % sides, j * sides + k))
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


def fade(path, opacity):
    """Make a rendered picture evenly see-through. The holder is rendered solid and faded as one
    whole, so where its parts overlap (an arm over the ring) they don't show through each other."""
    image = bpy.data.images.load(str(path))
    pixels = list(image.pixels)
    pixels[3::4] = [v * opacity for v in pixels[3::4]]
    image.pixels.foreach_set(pixels)
    image.filepath_raw = str(path)
    image.save()


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
    strength.inputs[1].default_value = 0.9                      # edges glow
    strength.inputs[2].default_value = 0.22                     # faces a little
    l.new(edge.outputs["Facing"], strength.inputs[0])
    l.new(strength.outputs[0], glow.inputs["Strength"])
    add = n.new("ShaderNodeAddShader")
    l.new(body.outputs[0], add.inputs[0])
    l.new(glow.outputs[0], add.inputs[1])
    see = n.new("ShaderNodeBsdfTransparent")
    mix = n.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.2                      # mostly see-through, as the dashboard draws it
    l.new(see.outputs[0], mix.inputs[1])
    l.new(add.outputs[0], mix.inputs[2])
    l.new(mix.outputs[0], out.inputs["Surface"])
    return m


def shell_arm(name, angle, holes=0):
    """One arm of the holder: a curved shell that leaves its clip on the ring, reaches in, and
    curls over the front of the orb lying on its curve, cupping it like a finger. Built as a
    surface of rows across the arm, each row bent round the ball, then given some thickness."""
    rows, cols = 56, 14
    verts, faces = [], []

    def point(u, v):
        """u: from the clip (0) to the tip (1); v: across the arm, -1 to 1."""
        a = math.radians(angle + 70 * u)
        reach = max(0.0, (u - 0.42) / 0.58)                   # 0 until it meets the ball, then curling over it
        r_flat = 1.86 - 0.78 * min(1.0, u / 0.42) ** 0.8 - 0.40 * reach ** 1.2   # tips stop short of the middle (the name)
        z = 0.06 - 0.10 * math.sin(math.pi * min(1.0, u / 0.42)) + 1.05 * reach ** 1.1
        p = Vector((r_flat * math.cos(a), r_flat * math.sin(a), z))
        width = 0.66 * math.sin(math.pi * (0.16 + 0.84 * u)) ** 0.6
        p = p + Vector((-math.sin(a), math.cos(a), 0)) * width * v * 0.5
        bend = 1.07 + 0.25 * (1 - u) ** 3                     # never inside the ball: the arm lies on it
        if p.length < bend:
            p = p.normalized() * bend
        return p

    for i in range(rows + 1):
        for j in range(cols + 1):
            verts.append(point(i / rows, -1 + 2 * j / cols))
    for i in range(rows):
        for j in range(cols):
            a, b = i * (cols + 1) + j, (i + 1) * (cols + 1) + j
            faces.append((a, a + 1, b + 1, b))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    arm = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(arm)
    thick = arm.modifiers.new("thickness", "SOLIDIFY")
    thick.thickness, thick.offset = 0.06, 0
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.modifier_apply(modifier=thick.name)
    for k in range(holes):                                    # the round holes, through the shell
        p = point(0.16 + 0.17 * k, 0)                     # on the part between the ring and the ball
        bpy.ops.mesh.primitive_cylinder_add(radius=0.09, depth=0.5, location=p)
        cutter = bpy.context.active_object
        cutter.rotation_euler = p.normalized().to_track_quat("Z", "Y").to_euler()
        cut = arm.modifiers.new("hole", "BOOLEAN")
        cut.operation, cut.object = "DIFFERENCE", cutter
        cut.solver = "FLOAT"                                  # the exact solver loses whole arms at some angles
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.modifier_apply(modifier=cut.name)
        bpy.data.objects.remove(cutter)
    return arm


def claw(scene):
    """The orb's holder, after the classic dashboard's: a thick flat ring with four loop clips, and
    four shell arms reaching in from it and curling over the front of the orb. Everything a
    quarter turn apart (the theme turns it 90 degrees per move) and lit only by its own glow, so
    each quarter turn looks the same."""
    orb_camera(scene)
    world_colour(scene, (0.0, 0.0, 0.0), 0.0)
    even_lights()
    holdout_ball()
    look = glow_glass("claw")
    look.node_tree.nodes["Mix Shader"].inputs["Fac"].default_value = 1.0   # solid: see fade() below
    ring_line = [Vector((1.86 * math.cos(2 * math.pi * i / 128), 1.86 * math.sin(2 * math.pi * i / 128), 0.1)) for i in range(128)]
    band = tube("ring", ring_line, [0.085] * 128, sides=16, closed=True)
    band.data.materials.append(look)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.17, minor_radius=0.035,
                                         location=(1.86 * math.cos(a), 1.86 * math.sin(a), 0.1))
        clip = bpy.context.active_object
        clip.rotation_euler = Vector((-math.sin(a), math.cos(a), 0)).to_track_quat("Z", "Y").to_euler()   # loops round the band
        clip.data.materials.append(look)
        arm = shell_arm(f"arm{k}", 45 + 90 * k)
        arm.data.materials.append(look)
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and not obj.is_holdout:
            for poly in obj.data.polygons:
                poly.use_smooth = True
    scene.cycles.samples = 96
    scene.render.filepath = str(OUT / "rings_a.png")
    bpy.ops.render.render(write_still=True)
    fade(OUT / "rings_a.png", 0.35)


def row_arm(scene, width=300, height=160):
    """The little arm joining each menu row's pod to its bar, seen from the side: a tapered metal
    strut leaving the pod's top right, bending down in a step, and reaching into the bar's corner.
    art.py lays this picture into the rows (render it first). Units: 100 = the picture's height."""
    cam = bpy.data.cameras.new("camera")
    cam.type = "ORTHO"
    cam.ortho_scale = width / height * 100
    obj = bpy.data.objects.new("camera", cam)
    obj.location = (width / height * 50, 50, 50)
    bpy.context.collection.objects.link(obj)
    scene.camera = obj
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    world_colour(scene, (0.0, 0.0, 0.0), 0.0)
    even_lights()
    look = glow_glass("strut", colour=(0.08, 0.55, 0.06))
    look.node_tree.nodes["Mix Shader"].inputs["Fac"].default_value = 1.0
    w = width / height * 100
    # Out to the right, a smooth step down, on into the bar: points in the picture's units.
    knots = [(6, 74), (w * 0.40, 74), (w * 0.68, 32), (w - 4, 32)]
    spine = []
    for i in range(len(knots) - 1):
        (x0, y0), (x1, y1) = knots[i], knots[i + 1]
        steps = 24 if i == 1 else 10
        for k in range(steps):
            t = k / steps
            ease = 3 * t * t - 2 * t * t * t if i == 1 else t   # the step down eases in and out
            spine.append(Vector((x0 + (x1 - x0) * t, y0 + (y1 - y0) * ease, 0)))
    spine.append(Vector((*knots[-1], 0)))
    n = len(spine)
    radii = [7.0 + 4.0 * math.sin(math.pi * i / (n - 1)) for i in range(n)]   # thicker in the middle, like a strut
    strut = tube("strut", spine, radii, sides=20)
    strut.data.materials.append(look)
    for end in (spine[0], spine[-1]):                        # a collar at each end where it joins
        bpy.ops.mesh.primitive_cylinder_add(radius=10.0, depth=8.0, location=end)
        collar = bpy.context.active_object
        collar.rotation_euler = (0, math.pi / 2, 0)
        collar.data.materials.append(look)
    scene.cycles.samples = 64
    scene.render.filepath = str(OUT / "row_arm.png")
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
    falloff.inputs["From Min"].default_value = 0.965   # black only behind the orb (it covers about 18° of view)
    falloff.inputs["From Max"].default_value = 0.75
    falloff.inputs["To Min"].default_value = 0.0
    falloff.inputs["To Max"].default_value = 1.0
    deep = nodes.new("ShaderNodeMath"); deep.operation = "POWER"               # how quickly it fades towards the middle
    links.new(falloff.outputs["Result"], deep.inputs[0])
    deep.inputs[1].default_value = 1.0
    level = nodes.new("ShaderNodeMath"); level.operation = "MULTIPLY"
    links.new(lines.outputs["Result"], level.inputs[0])
    links.new(deep.outputs["Value"], level.inputs[1])
    ground = nodes.new("ShaderNodeMath"); ground.operation = "MULTIPLY_ADD"     # a faint green between the lines
    links.new(deep.outputs["Value"], ground.inputs[0])
    ground.inputs[1].default_value = 0.03
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
if "rowarm" in WANTED:
    row_arm(fresh())
if "wall" in WANTED:
    wall(fresh(), "bg_system.jpg", 0.45, centre=(25, -2))   # the far end behind the orb (at 0.27 across)
    wall(fresh(), "bg_list.jpg", 0.3)
