# Local OpenSKP legacy parser overlay

legacy.py is based on iamahsanmehmood/openskp commit 525093b (MIT).
LICENSE-OpenSKP preserves that project's license. The Blender integration
remains GPL-3.0-or-later. The build applies this tracked overlay after
extracting the original pinned wheel, and records its SHA-256 in build-info.

The newer upstream reader fixes the custom-layer anchor in Cam81.skp.
Local changes read schema-2 custom line styles referenced by SketchUp 2019
layers, preserve schema-1 Image record boundaries (no GUID), and append the
homogeneous scale component to legacy Image placement matrices. These fix
minmalist house.skp, AutoSave_AutoSave_Untitled_1.skp and Lukisan.skp.

Unknown custom line-style layouts remain explicit parse errors. No binary
class scanning, dropped geometry, SDK fallback or NEOS graph substitution is
used to make an import appear successful.
