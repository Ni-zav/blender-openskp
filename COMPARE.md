ï»¿# OpenSKP Compare for NEOS

Local legacy build for Blender 4.2 on Windows x64 (Python 3.11).
Based on Ahsan Mehmood's GPL-3.0-or-later blender-openskp.
Dependency licenses are preserved under vendor/*.dist-info and vendor/*.libs.

Install the ZIP through Preferences > Add-ons > Install from Disk and enable
OpenSKP Compare for NEOS. Use File > Import > SketchUp - OpenSKP Compare (.skp),
including while NEOS mode is active. The NEOS SKP import control uses its own
separate SDK engine for comparison.

## Editable geometry in 0.2.10

Every visible placement is a real Mesh object. Select it and press Tab to edit.
There are no collection-instance Empties or hidden source-geometry collections.
A single-tag file uses one import collection; multiple tags get child collections
with their original visibility. Bld D.skp uses one collection and 280 Mesh objects
(257 face placements plus 23 loose-edge placements).

Repeated components share mesh data, preserving SketchUp-style shared editing.
Use Object > Relations > Make Single User > Object & Data to edit one copy alone.
Object transforms stay independent. Source component/paint variants keep their
own mesh and per-face material slots.

## Editable materials

Textured paints have UV Texture Coordinate > Mapping > Image Texture > OpenSKP
Material Adjustment > Principled BSDF > Material Output. The adjustment group
exposes Tint, Hue, Saturation, Brightness, Roughness, Metallic and Alpha.
An optional grayscale-to-Bump branch starts with Strength 0: SketchUp has not
provided an actual PBR height/normal map. Texture alpha multiplies source opacity.
Materials retain recovered source names; packed paint images remain active for
Solid texture view. The shader is self-contained and needs no NEOS asset pack.

Use Material Preview or Rendered view to see shader/Mapping adjustments; Solid
TEXTURE displays the active image and does not evaluate the complete shader tree.
Show imported textures (on by default) sets Solid viewports to flat TEXTURE with
two-sided visibility. Material Preview and Rendered viewport choices are preserved.
World placements and editable Mesh objects remain; see 0.2.11 paint changes below.
This is not a claim of pixel-identical rendering or reconstruction of SketchUp
renderer-specific PBR materials. No NEOS custom shader groups are copied.

## Comparison and scope

Import counts/timing appear in the console and Scene.openskp_compare_last_import.
Use fresh scenes and identical units, source files and camera positions.
The importer uses OpenSKP 1.3.0 plus documented independent legacy parser fixes.
It does not adopt geometry into NEOS canonical modeling records.

Focused 0.2.10 acceptance uses Bld D.skp in Blender 4.2.7 outside/inside NEOS mode:
real Edit Mode, component sharing, source material names, shader controls, neutral
bump defaults, alpha links and the previous world bounds/triangle count.
Shader brightness is exercised through a small Cycles render.
Older all-sample evidence belongs to earlier builds; it does not validate 0.2.10
on every SKP. No raw validation reports or screenshots ship in the ZIP.

Export consumes selected real mesh objects, so imported geometry can now be
selected directly for export. The existing export still has limitations in
material/texture fidelity and hierarchy reconstruction.

All changes are local. Nothing is published to upstream or deployed.

## Material fidelity in 0.2.11

Paint colorization now uses SketchUp HLS Shift/Tint rather than multiplying
average RGB into the texture. The legacy texture mode is decoded, uncolorized
images remain unchanged, solid paint is converted from sRGB for Blender shader
inputs, and image deduplication hashes all bytes.

Reference: https://github.com/SketchUp/sketchup-colorize-algorithm
The numerical implementation is independent; the SketchUp SDK is used only as
an optional test reference, never as an OpenSKP runtime dependency.

Coincident front/back paint triangles become one editable surface with a
Backfacing shader switch and distinct UVMap / UVMap_Back layers. SketchUp's front
paint remains the primary material preview. Triangle winding follows the source
normal; source/back duplicate polygons and their orphan vertices are removed.
Solid shows the front image; use Material Preview/Rendered for differing back
paint. Solid backface culling is disabled to show these two-sided surfaces.

Focused acceptance compares all 12 textured Bld D paints against fresh SDK
texture exports, verifies Edit Mode and unchanged world bounds, checks two-sided
UVs, exercises shader brightness, and imports outside/inside NEOS mode. This
improves the sampled file; it does not promise pixel-identical results under
other lighting/color management or validate all sample files.

## Saved scene cameras in 0.2.12

Import Scenes As Cameras creates named Blender camera objects from captured
SketchUp page views, selects the first imported camera as the scene camera,
and preserves perspective/orthographic projection. Import Scene Cameras Only
skips geometry/material construction when the first option is enabled.
Both options default to off, matching NEOS. Parsing is still required in
camera-only mode; its timing is not a geometry import measurement.

Camera decoding is independent of NEOS/SketchUp SDK at runtime. Modern pages
use the OpenSKP page records; classic pages use locally validated MFC camera
records. This imports views, not SketchUp styles, animation, tag-visibility
transitions or Scene tabs as separate Blender scenes. Aspect/FOV conversion
uses the default vertical FOV / 16:9 when the parser has no aspect metadata;
2-point perspective shifts and arbitrary legacy camera back-references are not
guaranteed. SDK comparison is a development test oracle, not a runtime fallback.
Camera-only acceptance checks 19 classic Cam81 views, zero tower views and nine
modern FINALMASJID views against SDK names, matrices and camera settings.
