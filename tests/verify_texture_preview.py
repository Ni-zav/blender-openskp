"""Install the actual ZIP and verify textured SKP import outside/inside NEOS."""
import argparse
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
parser = argparse.ArgumentParser()
parser.add_argument('--input', type=Path, default=Path(r'C:\Users\awak\Documents\ND\dxfdwgskp_sample\Bld D.skp'))
parser.add_argument('--output', type=Path, default=ROOT / 'texture-validation')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
OUTPUT = args.output.resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)
bpy.ops.preferences.addon_install(filepath=str(ROOT / 'openskp-neos-compare-0.2.11-blender42-win64-legacy.zip'))
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


# Equal average colors must not collapse distinct front/back textures, and
# unpainted faces must inherit the complete instance texture, not just color.
from openskp._face_groups import FaceGroupContext, build_local_face_groups
paint = lambda index: dict(color=dict(r=100, g=100, b=100, a=255), texture=dict(index=index, x_scale=2, y_scale=2))
paints = {'front': paint(1), 'back': paint(2)}
face = dict(loops=[[(0,1), (1,1), (2,1)]], normal=(0,0,1), material_id=1, back_material_id=2)
builder = SimpleNamespace(vertices={0:(0,0,0), 1:(1,0,0), 2:(0,1,0)}, edges={0:(0,1), 1:(1,2), 2:(2,0)}, faces={0:face})
context = FaceGroupContext({1:'front', 2:'back'}, paints, {}, lambda tex: tex['index'] if tex else None, (255,255,255), 'regression')
groups = build_local_face_groups(builder, context)
assert len(groups) == 2 and {key[2] for key in groups} == {1, 2}
face['material_id'] = face['back_material_id'] = None
context.inherited_material = paints['front']
groups = build_local_face_groups(builder, context)
assert len(groups) == 1 and next(iter(groups))[2] == 1


def render_preview(label):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    shading = scene.display.shading
    shading.light, shading.color_type = 'FLAT', 'TEXTURE'
    shading.show_backface_culling = True
    shading.show_shadows = False
    shading.show_cavity = False
    points = []
    for instance in bpy.context.evaluated_depsgraph_get().object_instances:
        if instance.object.type == 'MESH':
            points.extend(instance.matrix_world @ Vector(corner) for corner in instance.object.bound_box)
    if not points:
        stats = json.loads(scene['openskp_compare_last_import'])
        assert stats['unique_meshes'] == 0 and stats['unique_curve_meshes'] == 0
        print('NO_GEOMETRY_PREVIEW', label, args.input.name, flush=True)
        return
    lower = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    upper = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    center, extent = (lower+upper)/2, max(upper-lower)
    camera = bpy.data.objects.new(label+' camera', bpy.data.cameras.new(label+' camera'))
    scene.collection.objects.link(camera)
    smallest_axis = min(range(3), key=lambda axis: upper[axis] - lower[axis])
    direction = ((2., 0., .45), (0., -2., .45), (0., -1., 2.))[smallest_axis] if (upper[smallest_axis] - lower[smallest_axis]) < extent * .01 else (0., -2., .45)
    camera.location = center + Vector(direction) * extent
    camera.rotation_euler = (center-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type, camera.data.ortho_scale = 'ORTHO', extent * 1.4
    camera.data.clip_start = max(extent / 100000, 0.0001)
    camera.data.clip_end = max(extent * 20, 1000)
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
    source = str(args.input)
    assert bpy.ops.import_scene.openskp_neos_compare(filepath=source) == {'FINISHED'}
    stats = json.loads(bpy.context.scene['openskp_compare_last_import'])
    count = 0
    for material in set(bpy.data.materials)-before:
        nodes = material.node_tree.nodes
        images = [node for node in nodes if node.type == 'TEX_IMAGE']
        if not images:
            continue
        node = images[0]
        assert nodes.active.type in {'TEX_IMAGE','BSDF_PRINCIPLED'} and node.image.packed_file
        assert all(size > 0 for size in node.image.size)
        assert node.inputs['Vector'].is_linked
        assert node.inputs['Vector'].links[0].from_node.type == 'MAPPING'
        assert node.inputs['Vector'].links[0].from_node.inputs['Vector'].links[0].from_node.type in {'TEX_COORD','UVMAP'}
        count += 1
    if args.input.name == 'Bld D.skp':
        assert stats['textures_loaded'] >= 9 and count >= 17
    assert count > 0 or stats['textures_loaded'] == 0
    views = [area.spaces.active for area in bpy.context.screen.areas if area.type == 'VIEW_3D']
    assert views and all(space.shading.color_type == 'TEXTURE' for space in views)
    print('TEXTURE_PREVIEW_OK', label, count, flush=True)
    render_preview(label)
    return count


bpy.context.window.scene = bpy.data.scenes.new('Blender texture preview')
outside = check_import('outside-neos')
# Keep the 190 MB sample from occupying memory twice across the two modes.
fresh = bpy.data.scenes.new('Texture validation transition')
bpy.context.window.scene = fresh
for scene in list(bpy.data.scenes):
    if scene != fresh:
        bpy.data.scenes.remove(scene)
bpy.data.orphans_purge(do_recursive=True)
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

(OUTPUT / 'result.json').write_text(json.dumps(dict(file=args.input.name, blender=bpy.app.version_string, outside_textured_materials=outside,
    inside_textured_materials=inside, mixed_primitive_uvs='passed', previews='Workbench renders when mesh geometry exists'), indent=2)+'\n')
print('OPENSKP_TEXTURE_PREVIEW_PASS')
