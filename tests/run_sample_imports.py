"""Run bounded per-file Blender processes, preserving logs and failure evidence."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--engine', choices=['neos', 'openskp'], required=True)
parser.add_argument('--label', required=True)
parser.add_argument('--samples', type=Path, default=Path(r'C:\Users\awak\Documents\ND\dxfdwgskp_sample'))
parser.add_argument('--files', nargs='*')
parser.add_argument('--timeout', type=int, default=1200)
args = parser.parse_args()
output = ROOT / 'sample-validation' / args.label / args.engine
output.mkdir(parents=True, exist_ok=True)
files = sorted((path for path in args.samples.iterdir() if path.suffix.lower() == '.skp'), key=lambda p: p.stat().st_size)
if args.files:
    files = [path for path in files if path.name in args.files]
blender = r'C:\Program Files\Blender Foundation\Blender 4.2\blender.exe'
rows = []
for path in files:
    result_path = output / (path.name + '.json')
    if result_path.exists():
        raise SystemExit('Evidence already exists: ' + str(result_path))
    print('START', args.engine, path.name, flush=True)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='skp_sample_profile_') as profile:
        env = dict(os.environ)
        for kind in ('CONFIG', 'SCRIPTS', 'EXTENSIONS'):
            env['BLENDER_USER_' + kind] = str(Path(profile) / kind.lower())
        command = [blender, '-b', '--factory-startup', '--python-exit-code', '1', '--python',
                   str(ROOT / 'tests/sample_import_child.py'), '--', '--engine', args.engine,
                   '--input', str(path), '--result', str(result_path)]
        with (output / (path.name + '.log')).open('w', encoding='utf-8') as log:
            try:
                completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                           env=env, timeout=args.timeout)
                code = completed.returncode
            except subprocess.TimeoutExpired:
                code = 'timeout'
    if result_path.exists():
        row = json.loads(result_path.read_text(encoding='utf-8'))
    else:
        row = dict(engine=args.engine, file=path.name, status='failed', exit_code=code,
                   elapsed_seconds=round(time.perf_counter()-started, 3))
        result_path.write_text(json.dumps(row, indent=2) + '\n', encoding='utf-8')
    rows.append(row)
    print('DONE', args.engine, path.name, row['status'], row['elapsed_seconds'], row.get('error', ''), flush=True)
    (output / 'summary.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
