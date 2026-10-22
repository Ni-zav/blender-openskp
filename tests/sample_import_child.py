"""Import one real sample in a fresh Blender process; emit structured evidence."""
import argparse
import importlib
import json
from pathlib import Path
import sys
import time
import traceback
import types

import bpy

parser = argparse.ArgumentParser()
parser.add_argument('--engine', choices=['neos', 'openskp'], required=True)
parser.add_argument('--input', type=Path, required=True)
parser.add_argument('--result', type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
root = Path(__file__).resolve().parents[1]
package_root = root if args.engine == 'openskp' else root.parent / 'neos'
package = types.ModuleType('sample_import')
package.__path__ = [str(package_root)]
sys.modules[package.__name__] = package
started = time.perf_counter()
result = dict(engine=args.engine, file=args.input.name, input_bytes=args.input.stat().st_size)
try:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if args.engine == 'openskp':
        runtime = importlib.import_module('sample_import.runtime')
        runtime.ensure_dependencies()
        importer = importlib.import_module('sample_import.import_skp')
        result['stats'] = importer.import_skp(str(args.input), bpy.context)
    else:
        importer = importlib.import_module('sample_import.sketchup_importer.blender')
        migration = importlib.import_module('sample_import.semantic.migrations.projection')
        original_plan = migration.projection_plan
        def diagnose_plan(*positional, **keywords):
            try:
                return original_plan(*positional, **keywords)
            except Exception as error:
                tb = error.__traceback__
                while tb:
                    values = tb.tb_frame.f_locals
                    if tb.tb_frame.f_code.co_name == 'projection_plan' and 'expected' in values:
                        result['projection_failure'] = {key: values.get(key) for key in ('obj', 'record', 'expected', 'parent')}
                    tb = tb.tb_next
                bpy.ops.wm.save_as_mainfile(filepath=str(args.result.with_suffix('.blend')), check_existing=False)
                raise
        migration.projection_plan = diagnose_plan
        def progress(percent, message=None):
            print('PROGRESS', percent, message, flush=True)
        objects = importer.import_skp(args.input, options={'prepare_mesh': False}, progress_callback=progress)
        projection = importlib.import_module('sample_import.semantic.blender_projection')
        model = projection.read_model(bpy.context.scene)
        projection.validate_projection(bpy.context.scene, model)
        result['stats'] = dict(imported_objects=len(objects), canonical_entities=len(model['entities']))
    meshes = [mesh for mesh in bpy.data.meshes if mesh.users]
    result.update(status='passed', objects=len(bpy.context.scene.objects), meshes=len(meshes),
                  polygons=sum(len(mesh.polygons) for mesh in meshes),
                  edges=sum(len(mesh.edges) for mesh in meshes),
                  materials=len(bpy.data.materials), images=len(bpy.data.images))
except Exception as error:
    result.update(status='failed', error=str(error), traceback=traceback.format_exc())
    traceback.print_exc()
result['elapsed_seconds'] = round(time.perf_counter() - started, 3)
args.result.parent.mkdir(parents=True, exist_ok=True)
args.result.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print('SAMPLE_RESULT ' + json.dumps(result), flush=True)
