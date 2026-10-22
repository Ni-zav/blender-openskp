"""Load private, offline dependencies for the Windows Blender 4.2 legacy ZIP."""
from pathlib import Path
import sys


def ensure_dependencies():
    vendor = Path(__file__).resolve().parent / "vendor"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    import openskp
    import mapbox_earcut
    import shapely
    import defusedxml
    return openskp
