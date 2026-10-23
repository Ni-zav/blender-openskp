"""Blender acceptance for saved page cameras; SDK is a test oracle only."""
import importlib.util, sys, types
from pathlib import Path
import bpy
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('openskp_camera_test',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
pkg=types.ModuleType('camera_reference');pkg.__path__=[str(ROOT.parent/'neos')];sys.modules[pkg.__name__]=pkg
from camera_reference.sketchup_importer.wrapper import Model
from camera_reference.sketchup_importer.blender.scene_builder import build_camera_world_matrix,sketchup_camera_settings
sources=Path(r'C:\Users\awak\Documents\ND\dxfdwgskp_sample')
for name,expected in [('Cam81.skp',19),('bld tower Bentuk I.skp',0),('FINALMASJID & GERBANG CLUSTER (20260928).skp',9)]:
 bpy.ops.wm.read_factory_settings(use_empty=True)
 assert bpy.ops.import_scene.openskp_neos_compare(filepath=str(sources/name),import_scene_cameras=True,import_scene_camera_only=True)=={'FINISHED'}
 assert not bpy.data.meshes and not bpy.data.materials
 cameras=[obj for obj in bpy.context.scene.objects if obj.type=='CAMERA']
 assert len(cameras)==expected,(name,len(cameras),expected)
 with Model(sources/name) as model:
  reference=[s for s in model.scenes if s.use_camera()]
  assert len(reference)==len(cameras)
  for obj,scene in zip(cameras,reference):
   camera=scene.camera();wanted=build_camera_world_matrix(camera.eye(),camera.target(),camera.up(),.0254)
   assert obj['openskp_scene_name']==scene.name()
   assert np.allclose(np.asarray(obj.matrix_world),np.asarray(wanted),atol=1e-5),(name,scene.name())
   settings=sketchup_camera_settings(camera)
   for key in ('type','sensor_fit','lens','ortho_scale','clip_start','clip_end'):
    if key not in settings:continue
    value=getattr(obj.data,key);expected_value=settings[key]
    assert value==expected_value if isinstance(value,str) else abs(value-expected_value)<1e-4,(scene.name(),key,value,expected_value)
 print('CAMERA_SDK_PARITY_PASS',name,len(cameras),flush=True)
# Perspective/orthographic conversion has independent known inputs too.
from openskp_camera_test.scene_cameras import import_cameras
bpy.ops.wm.read_factory_settings(use_empty=True)
# Exercise VFF page conversion without reading a file (Cam81 is handled by legacy scanner above).
module=sys.modules['openskp_camera_test.scene_cameras'];original=module.pages_from_file
module.pages_from_file=lambda *_:[dict(name='Plan',eye=(0,0,100),target=(0,0,0),up=(0,1,0),parallel=True,ortho_height=100)]
assert import_cameras('probe',{},bpy.context,bpy.context.scene.collection)==1
assert abs(bpy.context.scene.camera.data.ortho_scale-100*16/9*.0254)<1e-5
module.pages_from_file=original
addon.unregister()
print('SCENE_CAMERA_ACCEPTANCE_PASS',flush=True)
