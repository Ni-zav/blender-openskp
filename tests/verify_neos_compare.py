"""Install the actual legacy ZIP and import user SKP samples beside NEOS."""
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import tempfile

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
archive = ROOT / 'openskp-neos-compare-0.2.6-blender42-win64-legacy.zip'
samples = Path(r'C:\Users\awak\Documents\ND\dxfdwgskp_sample')
bpy.ops.preferences.addon_install(filepath=str(archive), overwrite=False)
addon_utils.modules_refresh()
addon = addon_utils.enable('openskp_neos_compare', default_set=False)
assert addon is not None, 'Legacy add-on did not enable'
assert 'openskp_neos_compare/vendor' in importlib.import_module('openskp').__file__.replace('\\', '/')

neos_root = ROOT.parent / 'neos'
spec = importlib.util.spec_from_file_location('neos_compare_host', neos_root / '__init__.py',
                                            submodule_search_locations=[str(neos_root)])
neos = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = neos
spec.loader.exec_module(neos)
neos._register_core_modules()
results = []
try:
    assert bpy.types.Operator.bl_rna_get_subclass_py('NEOS_OT_import_skp') is not None
    for name in ['Bld D.skp', 'minmalist house.skp']:
        scene = bpy.data.scenes.new('OpenSKP comparison: ' + name)
        bpy.context.window.scene = scene
        started = time.perf_counter()
        try:
            result = bpy.ops.import_scene.openskp_neos_compare(filepath=str(samples / name))
            assert result == {'FINISHED'}, result
            report = json.loads(scene['openskp_compare_last_import'])
            assert report['placements'] > 0 and report['triangles'] > 0, report
            assert 'neos_semantic_model_v2' not in scene
            results.append(dict(file=name, status='passed', **report))
        except Exception as error:
            results.append(dict(file=name, status='failed', error=str(error), seconds=time.perf_counter()-started))
        print('COMPARE_RESULT ' + json.dumps(results[-1]), flush=True)
    # Verify the shipped export operator on a normal Blender mesh. Collection
    # instance export remains an upstream limitation, documented in COMPARE.md.
    scene = bpy.data.scenes.new('OpenSKP export check')
    bpy.context.window.scene = scene
    bpy.ops.mesh.primitive_cube_add(size=2, location=(1, 2, 3))
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / 'cube.skp'
        assert bpy.ops.export_scene.openskp_neos_compare(filepath=str(output)) == {'FINISHED'}
        assert output.is_file() and output.stat().st_size > 0
        parsed = importlib.import_module('openskp').SkpFile.open(output).build_instanced_scene()
        assert len(parsed.mesh_resources) > 0
        print('OPEN_SKP_EXPORT_ROUNDTRIP_OK', flush=True)
finally:
    neos._unregister_core_modules()
    addon_utils.disable('openskp_neos_compare', default_set=False)

(ROOT / 'comparison-validation.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
assert results[0]['status'] == 'passed', results
assert results[1]['status'] == 'failed' and 'CCustomLineStyle' in results[1]['error'], results
print('OPEN_SKP_NEOS_COEXISTENCE_OK')
