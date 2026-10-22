"""Build an offline Windows/CPython 3.11 legacy ZIP without pip installation."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "openskp-neos-compare-0.2.6-blender42-win64-legacy.zip"
WHEELS = [
    "openskp-1.3.0-py3-none-any.whl",
    "mapbox_earcut-2.1.0-cp311-cp311-win_amd64.whl",
    "shapely-2.1.2-cp311-cp311-win_amd64.whl",
    "defusedxml-0.7.1-py2.py3-none-any.whl",
]


def main():
    if OUTPUT.exists():
        raise SystemExit("Output already exists; preserve previous local build")
    prefix = "openskp_neos_compare/"
    vendor = ROOT / "vendor"
    for name in WHEELS:
        with zipfile.ZipFile(ROOT / "wheels" / name) as wheel:
            wheel.extractall(vendor)
    provenance = {
        "upstream": "https://github.com/iamahsanmehmood/blender-openskp",
        "upstream_commit": subprocess.check_output(["git", "rev-parse", "refs/remotes/origin/main"], cwd=ROOT, text=True).strip(),
        "target": "Blender 4.2 Windows x64, CPython 3.11",
        "version": "0.2.6-local-compare",
        "dependencies": [{"file": name, "sha256": hashlib.sha256((ROOT / "wheels" / name).read_bytes()).hexdigest()}
                         for name in WHEELS],
        "changes": ["Legacy packaging with offline dependencies", "Distinct comparison menu and operator identities",
                    "Blender 4.2 transparency API", "Import time and counts recorded in Scene custom property"],
        "parser": "Original upstream OpenSKP 1.3.0; no NEOS SDK or semantic graph substitution",
    }
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ["__init__.py", "import_skp.py", "export_skp.py", "runtime.py", "LICENSE", "COMPARE.md"]:
            archive.write(ROOT / name, prefix + name)
        archive.writestr(prefix + "build-info.json", json.dumps(provenance, indent=2) + "\n")
        for path in sorted(vendor.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                archive.write(path, prefix + "vendor/" + path.relative_to(vendor).as_posix())
    metadata = dict(file=OUTPUT.name, size_bytes=OUTPUT.stat().st_size,
                    sha256=hashlib.sha256(OUTPUT.read_bytes()).hexdigest(), **provenance)
    OUTPUT.with_suffix(".zip.build.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: metadata[key] for key in ["file", "size_bytes", "sha256"]}, indent=2))


if __name__ == "__main__":
    main()
