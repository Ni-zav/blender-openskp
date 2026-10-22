"""Install the actual ZIP and verify textured SKP import outside/inside NEOS."""
import importlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import addon_utils
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'texture-validation'
OUTPUT.mkdir(exist_ok=True)
bpy.ops.preferences.addon_install(filepath=str(ROOT / 'openskp-neos-compare-0.2.8-blender42-win64-legacy.zip'))
addon_utils.modules_refresh()
assert addon_utils.enable('openskp_neos_compare', default_set=False) is not None
importer = importlib.import_module('openskp_neos_compare.import_skp')

# Mixed untextured/textured primitives must keep UV indices aligned.
plain = SimpleNamespace(material_index=0, positions=[0,0,0, 1,0,0, 0,1,0], uvs=[], indices=[0,1,2])
textured = SimpleNamespace(material_index=0, positions=[0,0,1, 1,0,1, 0,1,1], uvs=[.2,.3, .7,.3, .2,.9], indices=[0,1,2])
probe = importer._build_mesh_object('UV alignment', SimpleNamespace(primitives=[plain, textured]), [{}], {}, [], {})
uvs = [tuple(item.uv) for item in probe.data.uv_layers.active.data]
assert len(uvs) == 6 and all(abs(value) < 1e-6 for uv in uvs[:3] for value in uv)
assert abs(uvs[3][0]-.2) < 1e-6 and abs(uvs[5][1]-.9) < 1e-6


def render_preview(label):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    shading = scene.display.shading
    shading.light, shading.color_type = 'FLAT', 'TEXTURE'
    shading.show_shadows = False
    shading.show_cavity = False
    points = []
    for instance in bpy.context.evaluated_depsgraph_get().object_instances:
        if instance.object.type == 'MESH':
            points.extend(instance.matrix_world @ Vector(corner) for corner in instance.object.bound_box)
    assert points
    lower = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    upper = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    center, extent = (lower+upper)/2, max(upper-lower)
    camera = bpy.data.objects.new(label+' camera', bpy.data.cameras.new(label+' camera'))
    scene.collection.objects.link(camera)
    camera.location = center + Vector((1., -2., 1.)) * extent
    camera.rotation_euler = (center-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type, camera.data.ortho_scale = 'ORTHO', extent * 1.4
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = 960, 640
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(OUTPUT / (label+'.png'))
    bpy.ops.render.render(write_still=True)


def check_import(label):
    before = set(bpy.data.materials)
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.shading.type = 'SOLID'
            area.spaces.active.shading.color_type = 'SINGLE'
    source = r'C:\Users\awak\Documents\ND\dxfdwgskp_sample\Bld D.skp'
    assert bpy.ops.import_scene.openskp_neos_compare(filepath=source) == {'FINISHED'}
    count = 0
    for material in set(bpy.data.materials)-before:
        nodes = material.node_tree.nodes
        images = [node for node in nodes if node.type == 'TEX_IMAGE']
        if not images:
            continue
        node = images[0]
        assert nodes.active == node and node.image.packed_file
        assert all(size > 0 for size in node.image.size)
        assert node.inputs['Vector'].is_linked
        assert node.inputs['Vector'].links[0].from_node.uv_map == 'UVMap'
        count += 1
    assert count > 0
    views = [area.spaces.active for area in bpy.context.screen.areas if area.type == 'VIEW_3D']
    assert views and all(space.shading.color_type == 'TEXTURE' for space in views)
    print('TEXTURE_PREVIEW_OK', label, count, flush=True)
    render_preview(label)
    return count


bpy.context.window.scene = bpy.data.scenes.new('Blender texture preview')
outside = check_import('outside-neos')
neos_root = ROOT.parent / 'neos'
spec = importlib.util.spec_from_file_location('neos_texture_host', neos_root / '__init__.py', submodule_search_locations=[str(neos_root)])
neos = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = neos
spec.loader.exec_module(neos)
neos._register_core_modules()
try:
    bpy.context.window.scene = bpy.data.scenes.new('NEOS texture preview')
    assert bpy.ops.sketch_mode.activate() == {'FINISHED'}
    assert bpy.context.scene.sketch_mode_props.is_sketch_mode
    inside = check_import('inside-neos')
    assert bpy.ops.sketchmode.set_texture(material_preview=False) == {'FINISHED'}
    assert bpy.ops.sketch_mode.deactivate() == {'FINISHED'}
finally:
    neos._unregister_core_modules()

(OUTPUT / 'result.json').write_text(json.dumps(dict(blender=bpy.app.version_string, outside_textured_materials=outside,
    inside_textured_materials=inside, mixed_primitive_uvs='passed', previews='Workbench texture renders'), indent=2)+'\n')
print('OPENSKP_TEXTURE_PREVIEW_PASS')
