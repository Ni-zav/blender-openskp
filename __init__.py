"""OpenSKP Import/Export - native SketchUp (.skp) support for Blender.

Registers File > Import > SketchUp (.skp) and File > Export > SketchUp
(.skp). See import_skp.py / export_skp.py for the actual implementation -
this file only wires them into Blender's operator/menu system.
"""
import bpy
import json
import time
from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

bl_info = {
    "name": "OpenSKP Compare for NEOS",
    "author": "Ahsan Mehmood; local NEOS compatibility build",
    "version": (0, 2, 13),
    "blender": (4, 2, 0),
    "location": "File > Import/Export > SketchUp - OpenSKP Compare",
    "description": "Independent OpenSKP parser for comparison with NEOS SKP",
    "category": "Import-Export",
}

from . import runtime


class IMPORT_OT_openskp_neos_compare(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.openskp_neos_compare"
    bl_label = "Import SketchUp - OpenSKP Compare"
    bl_description = "Import a native SketchUp .skp file"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".skp"
    filter_glob: StringProperty(default="*.skp", options={"HIDDEN"})
    show_textures: BoolProperty(name="Show imported textures", default=True,
        description="Show source textures in Solid viewports, including NEOS Albedo")

    import_scene_cameras: BoolProperty(name="Import Scenes As Cameras", default=False,
        description="Create Blender cameras from saved SketchUp scenes/pages")
    import_scene_camera_only: BoolProperty(name="Import Scene Cameras Only", default=False,
        description="Import saved scene cameras without building geometry or materials")

    def draw(self, context):
        self.layout.prop(self, "show_textures")
        self.layout.prop(self, "import_scene_cameras")
        column = self.layout.column()
        column.active = self.import_scene_cameras
        column.prop(self, "import_scene_camera_only")

    def execute(self, context):
        started = time.perf_counter()
        try:
            runtime.ensure_dependencies()
            from . import import_skp
            stats = import_skp.import_skp(self.filepath, context,
                import_scene_cameras=self.import_scene_cameras,
                import_scene_camera_only=self.import_scene_camera_only)
            if self.show_textures and not (self.import_scene_cameras and self.import_scene_camera_only):
                import_skp.show_imported_textures(context)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
            self.report({"ERROR"}, f"OpenSKP import failed: {exc}")
            return {"CANCELLED"}

        stats.update(elapsed_seconds=round(time.perf_counter() - started, 3),
                     source_file=self.filepath, engine="OpenSKP 1.3.0 + local legacy parser fixes")
        context.scene["openskp_compare_last_import"] = json.dumps(stats)
        print("[OpenSKP Compare] " + json.dumps(stats), flush=True)
        self.report(
            {"INFO"},
            f"Imported {stats['unique_meshes']} unique meshes "
            f"({stats['placements']} placed), "
            f"{stats['unique_curve_meshes']} loose-edge groups "
            f"({stats['curve_placements']} placed), {stats.get('scene_cameras', 0)} scene cameras",
        )
        return {"FINISHED"}


class EXPORT_OT_openskp_neos_compare(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.openskp_neos_compare"
    bl_label = "Export SketchUp - OpenSKP Compare"
    bl_description = "Export selected objects to a native SketchUp .skp file"
    bl_options = {"REGISTER"}

    filename_ext = ".skp"
    filter_glob: StringProperty(default="*.skp", options={"HIDDEN"})

    def execute(self, context):
        try:
            runtime.ensure_dependencies()
            from . import export_skp
            stats = export_skp.export_skp(self.filepath, context)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, f"OpenSKP export failed: {exc}")
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"Exported {stats['faces_written']} faces "
            f"({stats['objects_skipped']} objects skipped)",
        )
        return {"FINISHED"}


def _menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_openskp_neos_compare.bl_idname, text="SketchUp - OpenSKP Compare (.skp)")


def _menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_openskp_neos_compare.bl_idname, text="SketchUp - OpenSKP Compare (.skp)")


_classes = (IMPORT_OT_openskp_neos_compare, EXPORT_OT_openskp_neos_compare)


def register():
    runtime.ensure_dependencies()
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(_menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(_menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(_menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(_menu_func_export)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
