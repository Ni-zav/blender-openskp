# OpenSKP Compare for NEOS

Local legacy build for Blender 4.2 on Windows x64 (Python 3.11).
Based on Ahsan Mehmood's GPL-3.0-or-later blender-openskp.
Dependency licenses are preserved under vendor/*.dist-info and vendor/*.libs.

Install the ZIP through Preferences > Add-ons > Install from Disk and enable
OpenSKP Compare for NEOS. It can be enabled alongside NEOS.

Use File > Import > SketchUp - OpenSKP Compare (.skp).
Show imported textures is enabled by default: Solid viewports switch to flat
texture color. Material Preview and Rendered shading are preserved. Image
nodes are active for Blender Workbench and NEOS Albedo; images remain packed
in the blend file. Turn off the checkbox to preserve Solid viewport settings.
For NEOS, use its existing SKP import control. Use a fresh scene for each
import with the same unit scale, file and viewpoint; do not overlay results.
This build uses OpenSKP with documented legacy parser fixes and keeps its
collection-instancing approach.
It does not convert the imported content into NEOS canonical modelling data.

OpenSKP keeps shared master meshes under <filename> (source geometry).
Visible placements are collection-instance Empties. Enable that source
collection in the Outliner and select its mesh to edit shared geometry.

Import time and counts appear in the system console and in the Scene custom
property openskp_compare_last_import. Unique mesh counts and NEOS projected
object counts represent different structures; compare visible geometry,
placement, scale, hidden tags, materials, textures and editability as well.

Export remains upstream OpenSKP export: select real mesh objects. Placement
Empties are not exported; original hierarchy and texture export are limited.

All changes are local. Nothing has been published to the upstream repository.

## Local validation on Blender 4.2.7

- Actual legacy installation and simultaneous registration with NEOS passed.
- Bld D.skp imported: 63 unique meshes, 257 mesh placements, 71,453 unique
  triangles, 13 loose-edge resources, 23 wire placements and 7 textures.
- All nine files in dxfdwgskp_sample have passing OpenSKP import evidence.
- Legacy parser fixes cover custom line styles, custom-layer bootstrap,
  old Image records without GUIDs, and full image placement matrices.
- These are import checks in background Blender, not visual fidelity approval.
