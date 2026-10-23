"""Import OpenSKP resources as editable Blender mesh objects.

One mesh datablock is shared by placements of the same component/paint variant.
Each placement is a real selectable Mesh, with its own composed world transform.
Collections represent source tags only; there are no hidden source collections.
"""
from __future__ import annotations

import os
import tempfile
import time

import bpy
import mathutils

# glTF Y-up -> Blender Z-up: (x, y, z) -> (x, -z, y). Same convention
# openskp's own scene.py/instanced_scene.py already document for their
# own Y-up output, just expressed as a Blender Matrix instead of a
# per-point axis swap.
_YUP_TO_ZUP = mathutils.Matrix(
    (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, -1.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
)


def _gltf_matrix_to_blender(m):
    """16-element column-major glTF matrix -> mathutils.Matrix (row-major
    constructor, so this transposes while unpacking)."""
    return mathutils.Matrix(
        (
            (m[0], m[4], m[8], m[12]),
            (m[1], m[5], m[9], m[13]),
            (m[2], m[6], m[10], m[14]),
            (m[3], m[7], m[11], m[15]),
        )
    )


def _get_or_build_texture_image(texture_index, textures, image_cache):
    """Returns the Blender Image for textures[texture_index], loading and
    packing it exactly once and caching it for every later material that
    references the same source image (a texture is routinely shared
    across many materials/objects in a real file).

    Blender has no "load an image straight from bytes" API - the bytes
    are written to a real temp file, loaded from there, then Image.pack()
    is called BEFORE the temp file is removed: pack() is what actually
    forces Blender to read the file's bytes into the .blend's own data,
    so the temp file has to still exist at that point (confirmed by
    reading Blender's own docs on Image.pack(), not assumed) - after
    pack() succeeds, the temp file is redundant and safe to delete."""
    if texture_index in image_cache:
        return image_cache[texture_index]
    if textures is None or not (0 <= texture_index < len(textures)):
        return None

    tex = textures[texture_index]
    ext = ".png" if tex.mime_type == "image/png" else ".jpg"
    fd, path = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(tex.data)
        image = bpy.data.images.load(path)
        image.pack()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    # bpy.data.images.load() names the image after the temp file's own
    # basename ("tmp17pryts4.jpg") - rename to the source file's own
    # original filename when openskp recovered one, purely cosmetic
    # (Outliner/Shader Editor readability) but a real improvement over a
    # meaningless temp name.
    source_name = os.path.basename(tex.filename) if tex.filename else ""
    image.name = source_name or f"openskp_texture_{texture_index}"

    image_cache[texture_index] = image
    return image


def _tinted_texture(image, color, image_cache):
    """Bake the glTF color factor so Workbench and shader previews agree."""
    if all(abs(value - 1.0) < 1e-6 for value in color):
        return image
    key = (image.as_pointer(), tuple(color))
    if key not in image_cache:
        import numpy as np
        pixels = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(pixels)
        pixels.reshape((-1, 4))[:, :3] *= np.asarray(color, dtype=np.float32)
        tinted = image.copy()
        tinted.name = image.name + " (paint tint)"
        tinted.pixels.foreach_set(pixels)
        tinted.update()
        tinted.pack()
        image_cache[key] = tinted
    return image_cache[key]


def _get_or_build_material(material_index, gltf_materials, material_cache, textures, image_cache):
    """Returns the Blender Material for gltf_materials[material_index],
    building it exactly once per unique index and caching it for every
    later mesh that references the same one - openskp's own
    get_material_index() (instanced_scene.py) already deduplicates by
    (color, double_sided, texture, transparency) within one file, so the
    index alone is a valid, stable cache key here.

    When the material has a baseColorTexture, a real Image Texture node
    is wired into Base Color (and Alpha, for an image with its own alpha
    channel) - see _get_or_build_texture_image and this module's own
    "Textured materials" docstring section. Otherwise (or if the image
    fails to load) falls back to the resolved solid baseColorFactor,
    same as before textures existed.
    """
    if material_index in material_cache:
        return material_cache[material_index]

    gltf_mat = gltf_materials[material_index] if 0 <= material_index < len(gltf_materials) else {}
    pbr = gltf_mat.get("pbrMetallicRoughness", {})
    r, g, b, a = pbr.get("baseColorFactor", [0.8, 0.8, 0.8, 1.0])
    texture_ref = pbr.get("baseColorTexture")

    mat = bpy.data.materials.new(name=gltf_mat.get("name") or f"OpenSKP Material {material_index + 1}")
    mat.use_nodes = True
    mat.diffuse_color = (r, g, b, a)  # Solid viewport shading / thumbnails
    if a < 1.0:
        mat.surface_render_method = "DITHERED"

    image = None
    if texture_ref is not None:
        image = _get_or_build_texture_image(texture_ref.get("index"), textures, image_cache)
        if image is not None:
            image = _tinted_texture(image, (r, g, b), image_cache)
    from .material_nodes import build_material_nodes
    build_material_nodes(mat, image=image, color=(r, g, b, a),
                         roughness=pbr.get("roughnessFactor", .8),
                         metallic=pbr.get("metallicFactor", 0.0))
    mat.use_backface_culling = True

    material_cache[material_index] = mat
    return mat


def _build_mesh_object(name, resource, gltf_materials, material_cache, textures, image_cache):
    """Builds one Mesh Object (local space, at the origin) from an
    InstancedMeshResource's primitives - already-triangulated, so this is
    a direct from_pydata() with no triangulation of its own to do.

    Each primitive is already grouped by a single resolved material (see
    openskp.instanced_scene.mesh_resource_for's own docstring) - its
    material_index is used both to pick/build the right Blender Material
    and to set each of its triangles' own polygon.material_index, so the
    mesh's material slots and per-face assignment match the source file's
    own per-face paint, not just one flat color for the whole object.
    """
    verts = []
    vert_uvs = []
    tris = []
    tri_material_indices = []
    slot_by_material_index = {}
    mesh_materials = []

    for prim in resource.primitives:
        if prim.material_index not in slot_by_material_index:
            slot_by_material_index[prim.material_index] = len(mesh_materials)
            mesh_materials.append(
                _get_or_build_material(prim.material_index, gltf_materials, material_cache, textures, image_cache)
            )
        slot = slot_by_material_index[prim.material_index]

        base = len(verts)
        pos = prim.positions
        uvs = prim.uvs
        for i in range(0, len(pos), 3):
            verts.append((pos[i], pos[i + 1], pos[i + 2]))
        vertex_count = len(pos) // 3
        if len(uvs) not in (0, vertex_count * 2):
            raise ValueError(f"Invalid UV count for {name}: {len(uvs)} values for {vertex_count} vertices")
        if len(uvs):
            vert_uvs.extend((uvs[i], uvs[i + 1]) for i in range(0, len(uvs), 2))
        else:
            # Untextured primitives still occupy vertices in this shared mesh.
            # Omitting their UVs shifts every subsequent textured primitive.
            vert_uvs.extend([(0.0, 0.0)] * vertex_count)
        idx = prim.indices
        tri_count = len(idx) // 3
        for i in range(tri_count):
            tris.append((base + idx[i * 3], base + idx[i * 3 + 1], base + idx[i * 3 + 2]))
            tri_material_indices.append(slot)
            if gltf_materials[prim.material_index].get("doubleSided"):
                # Workbench culls globally, so represent a shared paint on both
                # sides explicitly as well as the parser's distinct side pairs.
                tris.append((base + idx[i * 3], base + idx[i * 3 + 2], base + idx[i * 3 + 1]))
                tri_material_indices.append(slot)

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], tris)
    for mat in mesh_materials:
        mesh.materials.append(mat)
    for poly, slot in zip(mesh.polygons, tri_material_indices):
        poly.material_index = slot

    # UVs are per-LOOP (face-corner) in Blender, not per-vertex - each
    # loop's own vertex_index looks back up into vert_uvs (built parallel
    # to verts above, in the same per-primitive order) to find its UV.
    if vert_uvs:
        uv_layer = mesh.uv_layers.new(name="UVMap")
        uv_layer.active_render = True
        for loop in mesh.loops:
            uv_layer.data[loop.index].uv = vert_uvs[loop.vertex_index]

    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    return obj


def _get_or_build_layer_collection(layer_name, layer_collection_cache, root_collection):
    """Returns the Collection that placements on `layer_name` (SketchUp's
    own term is "tag") get linked into, building it exactly once per
    distinct layer and linking it directly under root_collection -
    separate from sources_collection, since a layer is a property of a
    PLACEMENT (InstancedNode.layer), not of a definition: the same
    definition can appear on different layers in different places, so
    grouping by layer only makes sense at the placement level."""
    name = layer_name or "Layer0"
    if name in layer_collection_cache:
        return layer_collection_cache[name]
    coll = bpy.data.collections.new(name)
    root_collection.children.link(coll)
    layer_collection_cache[name] = coll
    return coll


def _get_mesh_object(resource_id, resources, cache, materials, material_cache,
                     textures, image_cache, stats, *, name):
    if resource_id not in cache:
        resource = resources[resource_id]
        obj = _build_mesh_object(name, resource, materials, material_cache, textures, image_cache)
        cache[resource_id] = obj.data
        stats["unique_meshes"] += 1
        stats["triangles"] += sum(len(prim.indices) // 3 for prim in resource.primitives)
        return obj
    return bpy.data.objects.new(name, cache[resource_id])


def _build_curve_object(name, resource):
    """Builds one edges-only Mesh Object (local space, at the origin) from
    an InstancedCurveResource's runs - no faces, so Blender renders these
    as plain construction lines, matching what the source file actually
    stores for loose edges (a light-gauge-steel/structural-framing member
    drawn as a line, not a solid).

    Renders each run's own chords (LocalCurve.points_m) rather than
    reconstructing a true circular arc from LocalCurve.arc when present -
    a well-tessellated arc's chords are visually indistinguishable at any
    reasonable zoom, and a genuine smooth-curve (bpy.data.curves) import
    for the analytic-arc case is future scope, not required for loose
    edges to stop being silently invisible.
    """
    verts = []
    edges = []
    for curve in resource.curves:
        base = len(verts)
        pts = curve.points_m
        verts.extend(pts)
        for i in range(len(pts) - 1):
            edges.append((base + i, base + i + 1))
        if curve.closed and len(pts) > 2:
            edges.append((base + len(pts) - 1, base))

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, edges, [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    return obj


def _place_node(node, parent_matrix, resources, mesh_cache, curve_resources,
                curve_cache, layers, root, materials, material_cache,
                textures, image_cache, stats):
    world = parent_matrix @ _gltf_matrix_to_blender(node.matrix)
    target = _get_or_build_layer_collection(node.layer, layers, root)
    for resource_id, is_curve in ((node.mesh_resource_id, False), (node.curve_resource_id, True)):
        if resource_id is None:
            continue
        name = node.name or resource_id
        if is_curve:
            name += " (lines)"
            if resource_id not in curve_cache:
                resource = curve_resources[resource_id]
                obj = _build_curve_object(name, resource)
                curve_cache[resource_id] = obj.data
                stats["unique_curve_meshes"] += 1
                stats["curve_runs"] += len(resource.curves)
            else:
                obj = bpy.data.objects.new(name, curve_cache[resource_id])
            stats["curve_placements"] += 1
        else:
            obj = _get_mesh_object(resource_id, resources, mesh_cache, materials,
                                   material_cache, textures, image_cache, stats, name=name)
            stats["placements"] += 1
        obj.matrix_world = _YUP_TO_ZUP @ world
        obj["openskp_resource"] = resource_id
        obj["openskp_layer"] = node.layer or "Layer0"
        target.objects.link(obj)
    for child in node.children:
        _place_node(child, world, resources, mesh_cache, curve_resources, curve_cache,
                    layers, root, materials, material_cache, textures, image_cache, stats)


def _placed_layers(node):
    layers = {node.layer or "Layer0"}
    for child in node.children:
        layers.update(_placed_layers(child))
    return layers


def import_skp(filepath, context=None):
    """Imports a .skp file into the current (or given) Blender context's
    scene, returning a stats dict."""
    import openskp

    context = context or bpy.context

    print(f"openskp: parsing {os.path.basename(filepath)}...")
    t0 = time.time()
    skp = openskp.SkpFile.open(filepath)
    scene = skp.build_instanced_scene()
    print(f"openskp: parsed in {time.time() - t0:.1f}s, building objects...")

    resources_by_id = {r.id: r for r in scene.mesh_resources}
    collection_cache = {}
    curve_resources_by_id = {r.id: r for r in getattr(scene, "curve_resources", None) or []}
    curve_collection_cache = {}
    layer_collection_cache = {}
    layer_hidden = getattr(scene, "layer_hidden", None) or {}
    gltf_materials = getattr(scene, "gltf_materials", None) or []
    material_cache = {}
    textures = getattr(scene, "textures", None) or []
    image_cache = {}
    stats = {
        "unique_meshes": 0,
        "placements": 0,
        "triangles": 0,
        "unique_curve_meshes": 0,
        "curve_placements": 0,
        "curve_runs": 0,
    }

    root_name = os.path.splitext(os.path.basename(filepath))[0]
    root_collection = bpy.data.collections.new(root_name)
    context.scene.collection.children.link(root_collection)

    # A single tag needs only the import collection. Multiple tags get
    # one child collection each so their visibility remains independent.
    source_layers = _placed_layers(scene.scene_hierarchy)
    if len(source_layers) == 1:
        layer_collection_cache[next(iter(source_layers))] = root_collection

    t0 = time.time()
    _place_node(scene.scene_hierarchy, mathutils.Matrix.Identity(4),
                resources_by_id, collection_cache, curve_resources_by_id,
                curve_collection_cache, layer_collection_cache, root_collection,
                gltf_materials, material_cache, textures, image_cache, stats)
    stats["textures_loaded"] = sum(isinstance(key, int) for key in image_cache)
    stats["texture_tint_variants"] = sum(isinstance(key, tuple) for key in image_cache)
    print(
        f"openskp: {stats['unique_meshes']} unique meshes "
        f"({stats['triangles']} triangles), {stats['placements']} instances placed; "
        f"{stats['unique_curve_meshes']} unique loose-edge groups "
        f"({stats['curve_runs']} runs), {stats['curve_placements']} placed; "
        f"{len(layer_collection_cache)} layers, {stats['textures_loaded']} textures "
        f"in {time.time() - t0:.1f}s"
    )

    # A layer hidden in the source file (SketchUp's own Tags panel
    # visibility) hides its whole Collection here too - Collection-level
    # hide_viewport/hide_render (the same "eye"/camera icons a user can
    # toggle in the Outliner), not the exclude-from-View-Layer mechanism
    # sources_collection uses below: a hidden layer is still meant to be a
    # normal, working part of the scene (just not shown right now), unlike
    # sources_collection's deliberately-excluded master geometry.
    stats["unique_layers"] = len(layer_collection_cache)
    stats["hidden_layers"] = 0
    for name, coll in layer_collection_cache.items():
        if layer_hidden.get(name, False):
            coll.hide_viewport = True
            coll.hide_render = True
            stats["hidden_layers"] += 1

    context.view_layer.update()
    meshes = [obj for obj in root_collection.all_objects if obj.type == 'MESH' and len(obj.data.polygons)]
    if meshes:
        # Make the geometry and its first textured material available immediately
        # to Edit Mode, Material Properties and the Shader Editor.
        active = max(meshes, key=lambda obj: len(obj.data.polygons))
        for obj in context.selected_objects:
            obj.select_set(False)
        active.select_set(True)
        context.view_layer.objects.active = active
        for index, material in enumerate(active.data.materials):
            if material and material.use_nodes and any(node.type == 'TEX_IMAGE' for node in material.node_tree.nodes):
                active.active_material_index = index
                break
    stats["mesh_objects"] = len(root_collection.all_objects)
    stats["collections"] = 1 + len(root_collection.children)
    return stats


def show_imported_textures(context):
    """Enable the active-image albedo view in Solid viewports after import.

    Blender's actual Material Preview and Rendered modes already evaluate the
    imported shader, so preserve those choices. No NEOS hooks or timers needed.
    """
    windows = getattr(getattr(context, 'window_manager', None), 'windows', ())
    screens = {window.screen for window in windows if window.screen is not None}
    if getattr(context, 'screen', None) is not None:
        screens.add(context.screen)
    for screen in screens:
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            shading = area.spaces.active.shading
            if shading.type == 'SOLID':
                shading.color_type = 'TEXTURE'
                shading.light = 'FLAT'
                shading.show_backface_culling = True
            area.tag_redraw()
