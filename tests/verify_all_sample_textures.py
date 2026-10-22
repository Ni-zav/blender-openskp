"""Run ZIP texture checks for every sample in isolated Blender processes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--samples', type=Path, required=True)
parser.add_argument('--exclude', action='append', default=[], help='Sample filename to skip (repeatable)')
parser.add_argument('--output', type=Path, default=ROOT / 'texture-validation' / 'all-samples')
parser.add_argument('--blender', default=r'C:\Program Files\Blender Foundation\Blender 4.2\blender.exe')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
results = []
for source in sorted(args.samples.iterdir(), key=lambda path: path.stat().st_size):
    if source.suffix.lower() != '.skp' or source.name.lower() in {name.lower() for name in args.exclude}:
        continue
    target = args.output / source.stem
    target.mkdir(exist_ok=True)
    # Never let a previous successful result mask a failed rerun.
    (target / 'result.json').unlink(missing_ok=True)
    environment = os.environ.copy()
    profile = Path(tempfile.mkdtemp(prefix='openskp-all-textures-'))
    for key, folder in [('BLENDER_USER_CONFIG', 'config'), ('BLENDER_USER_SCRIPTS', 'scripts'), ('BLENDER_USER_EXTENSIONS', 'extensions')]:
        environment[key] = str(profile / folder)
    print('START', source.name, flush=True)
    started = time.monotonic()
    with (target / 'blender.log').open('w', encoding='utf-8') as log:
        run = subprocess.run([args.blender, '-b', '--factory-startup', '--python-exit-code', '1', '--python',
            str(ROOT / 'tests' / 'verify_texture_preview.py'), '--', '--input', str(source), '--output', str(target)],
            env=environment, stdout=log, stderr=subprocess.STDOUT)
    result = dict(file=source.name, exit_code=run.returncode, seconds=round(time.monotonic() - started, 1))
    if (target / 'result.json').exists():
        result.update(json.loads((target / 'result.json').read_text()))
    results.append(result)
    (args.output / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    print('RESULT', json.dumps(result), flush=True)
raise SystemExit(0 if results and all(item['exit_code'] == 0 for item in results) else 1)
