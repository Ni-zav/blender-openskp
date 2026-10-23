"""Focused Bld D acceptance: editable meshes, tags, materials, geometry and NEOS."""
import importlib, importlib.util, json, sys, tempfile
from pathlib import Path
import addon_utils, bpy, bmesh
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'C:\Users\awak\Documents\ND\dxfdwgskp_sample\Bld D.skp')
ZIP = ROOT / 'openskp-neos-compare-0.2.10-blender42-win64-legacy.zip'
bpy.ops.preferences.addon_install(filepath=str(ZIP))
addon_utils.modules_refresh()
addon = addon_utils.enable('openskp_neos_compare', default_set=False)
assert addon and addon.bl_info['version'] == (0, 2, 10)


def check(label):
    result = bpy.ops.import_scene.openskp_neos_compare(filepath=str(SOURCE))
    assert result == {'FINISHED'}
    stats = json.loads(bpy.context.scene['openskp_compare_last_import'])
    root = next(coll for coll in bpy.context.scene.collection.children if coll.name.startswith('Bld D'))
    objects = list(root.all_objects)
    assert len(objects) == 280 and all(obj.type == 'MESH' for obj in objects)
    assert all(obj.instance_type == 'NONE' and obj.instance_collection is None for obj in objects)
    assert not root.children and stats['collections'] == 1
    active = bpy.context.view_layer.objects.active
    assert active in objects and len(active.data.polygons) and active.active_material
    bpy.ops.object.mode_set(mode='EDIT')
    mesh = bmesh.from_edit_mesh(active.data)
    mesh.verts.ensure_lookup_table()
    old = mesh.verts[0].co.copy()
    mesh.verts[0].co.x += .001
    bmesh.update_edit_mesh(active.data)
    assert abs(mesh.verts[0].co.x-old.x-.001) < 1e-5
    mesh.verts[0].co = old
    bmesh.update_edit_mesh(active.data)
    bpy.ops.object.mode_set(mode='OBJECT')
    assert any(obj.data.users > 1 for obj in objects)
    mats = {slot.material for obj in objects for slot in obj.material_slots if slot.material}
    textured = 0
    for mat in mats:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = next(node for node in nodes if node.type == 'BSDF_PRINCIPLED')
        control = bsdf.inputs['Base Color'].links[0].from_node
        assert control.type == 'GROUP' and control.node_tree.get('openskp_adjustment_version') == 1
        assert all(name in control.inputs for name in ('Tint','Hue','Saturation','Brightness','Roughness','Metallic','Alpha','Normal'))
        assert all(control.inputs[name].default_value == value for name,value in [('Hue',.5),('Saturation',1.),('Brightness',1.)])
        images = [node for node in nodes if node.type == 'TEX_IMAGE']
        if not images: continue
        textured += 1
        image = images[0]
        assert nodes.active == image and image.image.packed_file
        mapping = image.inputs['Vector'].links[0].from_node
        assert mapping.type == 'MAPPING' and mapping.inputs['Vector'].links[0].from_node.type == 'TEX_COORD'
        assert control.inputs['Base Color'].links[0].from_node == image
        bump = next(node for node in nodes if node.type == 'BUMP')
        assert bump.inputs['Strength'].default_value == 0
        alpha = control.inputs['Alpha'].links[0].from_node
        assert alpha.type == 'MATH' and alpha.operation == 'MULTIPLY'
    assert textured >= 17 and any(mat.name == '*' or mat.name.startswith('*.') for mat in mats)
    # World-space placement must match the previous instanced import, including
    # mirrored / nested components, face duplication, loose edges and UV data.
    lo = np.array([np.inf]*3); hi = -lo
    count = 0
    for obj in objects:
        v = np.empty(len(obj.data.vertices)*3)
        obj.data.vertices.foreach_get('co',v)
        v = v.reshape(-1,3)
        if len(v):
            world = np.c_[v,np.ones(len(v))] @ np.asarray(obj.matrix_world).T
            lo = np.minimum(lo,world[:,:3].min(0)); hi = np.maximum(hi,world[:,:3].max(0))
        obj.data.calc_loop_triangles(); count += len(obj.data.loop_triangles)
        if len(obj.data.polygons):
            assert obj.data.uv_layers.active.name == 'UVMap'
    assert count == 94818, count
    assert np.allclose(lo,[458.1573395986254,315.2744643491311,-.9000014141222044],atol=.0001)
    assert np.allclose(hi,[493.4919232742368,357.9350903484739,6.3000006475693135],atol=.0001)
    print('EDITABLE_IMPORT_PASS',label,json.dumps(stats),flush=True)

bpy.context.window.scene = bpy.data.scenes.new('Editable OpenSKP outside NEOS')
check('outside-neos')
# Compile and exercise actual material controls in a small Cycles albedo render.
# Use a copy of an imported paint, leaving the imported materials untouched.
original = bpy.context.view_layer.objects.active.active_material
material = original.copy()
nt = material.node_tree
control = next(node for node in nt.nodes if node.type == 'GROUP')
output = next(node for node in nt.nodes if node.type == 'OUTPUT_MATERIAL')
emission = nt.nodes.new('ShaderNodeEmission')
nt.links.new(control.outputs['Base Color'],emission.inputs['Color'])
nt.links.new(emission.outputs[0],output.inputs['Surface'])
scene = bpy.data.scenes.new('Shader control check'); bpy.context.window.scene = scene
bpy.ops.mesh.primitive_plane_add(size=2)
bpy.context.object.data.materials.append(material)
cam = bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera'));scene.collection.objects.link(cam)
cam.location=(0,0,3);cam.data.type='ORTHO';cam.data.ortho_scale=2;scene.camera=cam
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1;scene.cycles.use_denoising=False
scene.render.resolution_x=32;scene.render.resolution_y=32;scene.render.resolution_percentage=100
with tempfile.TemporaryDirectory(prefix='openskp-shader-check-') as temp:
    means=[]
    for value in (1.,.25):
        control.inputs['Brightness'].default_value=value
        scene.render.filepath=str(Path(temp)/'probe.png')
        bpy.ops.render.render(write_still=True)
        image=bpy.data.images.load(scene.render.filepath,check_existing=False)
        pixels=np.array(image.pixels[:]).reshape(-1,4)
        means.append(pixels[:,:3].mean());bpy.data.images.remove(image)
    assert means[0]>0 and means[1]<means[0]*.8, means
print('SHADER_CONTROL_RENDER_PASS',flush=True)

neos_root = ROOT.parent / 'neos'
spec=importlib.util.spec_from_file_location('editable_neos_host',neos_root/'__init__.py',submodule_search_locations=[str(neos_root)])
neos=importlib.util.module_from_spec(spec);sys.modules[spec.name]=neos;spec.loader.exec_module(neos)
neos._register_core_modules()
try:
    bpy.context.window.scene=bpy.data.scenes.new('Editable OpenSKP inside NEOS')
    assert bpy.ops.sketch_mode.activate()=={'FINISHED'}
    check('inside-neos')
    assert bpy.ops.sketchmode.set_texture(material_preview=False)=={'FINISHED'}
    assert bpy.ops.sketch_mode.deactivate()=={'FINISHED'}
finally:
    neos._unregister_core_modules()
print('OPENSKP_EDITABLE_ACCEPTANCE_PASS',flush=True)
