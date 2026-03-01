import json
import pathlib
import platform

import bpy
from bpy_extras.io_utils import ImportHelper

from . import importer


class LastCallArgsGroup(bpy.types.PropertyGroup):
    import_xml: bpy.props.StringProperty()
    import_msh: bpy.props.StringProperty()


class AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    mod_folder: bpy.props.StringProperty(
        name="Data folder",
        description='Directory containing your data. Used for locating textures and other linked data',
        subtype='DIR_PATH',
        default=str((pathlib.Path(
            'C:\Program Files (x86)' if platform.system() == 'Windows' else '~/.local/share'
        ) / 'Steam/steamapps/common/Warhammer 40000 Gladius - Relics of War/Data').expanduser()),
    )

    last_args: bpy.props.PointerProperty(type=LastCallArgsGroup)

    def draw(self, context):
        self.layout.prop(self, 'mod_folder')


def get_preferences(context) -> AddonPreferences:
    return context.preferences.addons[__package__].preferences


def save_args(storage, op, op_id: str, *arg_names):
    defaults = {
        k: getattr(v, 'default', None)
        for k, v in bpy.ops._op_get_rna_type(op.bl_idname).properties.items()
    }
    args = {i: getattr(op, i) for i in arg_names}
    args = {k: v for k, v in args.items() if v != defaults.get(k)}
    setattr(storage, op_id, json.dumps(args))


def remember_last_args(operator, context, args_location: str):
    last_args = {}
    addon_prefs = get_preferences(context)
    last_args_global = getattr(addon_prefs.last_args, args_location)
    if last_args_global:
        last_args.update(json.loads(last_args_global))
    last_args_file = getattr(context.scene.dow_last_args, args_location, None)
    if last_args_file:
        last_args.update(json.loads(last_args_file))
    for k, v in last_args.items():
        try:
            setattr(operator, k, v)
        except Exception:
            pass
    return operator



class ImportUnit(bpy.types.Operator, ImportHelper):
    """Import Warhammer 40,000: Gladius - Relics of War unit .xml file"""
    bl_idname = 'import_model.gladius_unit_xml'
    bl_label = 'Import .xml file'
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = '.xml'

    filter_glob: bpy.props.StringProperty(
        default='*.xml',
        options={'HIDDEN'},
        maxlen=255,
    )

    new_project: bpy.props.BoolProperty(
        name='New project',
        description='Create a new project for the imported unit',
        default=True,
    )

    scale: bpy.props.FloatProperty(
        name="Scale",
        description="Multiply imported mesh/rig size by this value (e.g. 0.4 to fit Gladius+ hex scale)",
        default=1.0, min=0, soft_min=0.01, soft_max=2.0, step=0.05,
    )

    enable_vertex_automerge: bpy.props.BoolProperty(
        name='Enable Vertex Automerge',
        description='Automatically merge close vertices',
        default=True,
    )

    vertex_position_merge_threshold: bpy.props.FloatProperty(
        name='Vertex merging position threshold',
        description='Maximum distance between merged vertices',
        default=0.001, min=0, soft_max=1, precision=3,
    )

    def execute(self, context):
        if self.new_project:
            bpy.ops.wm.read_homefile(app_template='')
            for mesh in bpy.data.meshes:
                bpy.data.meshes.remove(mesh)
        addon_prefs = get_preferences(context)
        save_args(addon_prefs.last_args, self, 'import_xml',
                  'filepath', 'new_project', 'scale',
                  'enable_vertex_automerge', 'vertex_position_merge_threshold',
        )
        loader = importer.UnitLoader(
            pathlib.Path(addon_prefs.mod_folder),
            self.scale,
            self.enable_vertex_automerge,
            self.vertex_position_merge_threshold,
            context=context,
        )
        window = context.window_manager.windows[0]
        with context.temp_override(window=window):
            try:
                loader.load_unit(self.filepath)
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        space = area.spaces.active
                        if space.type == 'VIEW_3D':
                            space.shading.type = 'MATERIAL'
            finally:
                for message_lvl, message in loader.messages:
                    self.report({message_lvl}, message)
        return {'FINISHED'}


class ImportMsh(bpy.types.Operator, ImportHelper):
    """Import Warhammer 40,000: Gladius - Relics of War mesh .msh file"""
    bl_idname = 'import_model.gladius_mesh_msh'
    bl_label = 'Import .msh file'
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = '.msh'

    filter_glob: bpy.props.StringProperty(
        default='*.msh',
        options={'HIDDEN'},
        maxlen=255,
    )

    new_project: bpy.props.BoolProperty(
        name='New project',
        description='Create a new project for the imported mesh',
        default=True,
    )

    scale: bpy.props.FloatProperty(
        name="Scale",
        description="Multiply imported mesh/rig size by this value (e.g. 0.4 to fit Gladius+ hex scale)",
        default=1.0, min=0, soft_min=0.01, soft_max=2.0, step=0.05,
    )

    enable_vertex_automerge: bpy.props.BoolProperty(
        name='Enable Vertex Automerge',
        description='Automatically merge close vertices',
        default=True,
    )

    vertex_position_merge_threshold: bpy.props.FloatProperty(
        name='Vertex merging position threshold',
        description='Maximum distance between merged vertices',
        default=0.001, min=0, soft_max=1, precision=3,
    )

    def execute(self, context):
        if self.new_project:
            bpy.ops.wm.read_homefile(app_template='')
            for mesh in bpy.data.meshes:
                bpy.data.meshes.remove(mesh)
        addon_prefs = get_preferences(context)
        save_args(addon_prefs.last_args, self, 'import_msh',
                  'filepath', 'new_project', 'scale',
                  'enable_vertex_automerge', 'vertex_position_merge_threshold',
        )
        loader = importer.UnitLoader(
            pathlib.Path(addon_prefs.mod_folder),
            self.scale,
            self.enable_vertex_automerge,
            self.vertex_position_merge_threshold,
            context=context,
        )
        window = context.window_manager.windows[0]
        with context.temp_override(window=window):
            try:
                loader.load_msh_file(pathlib.Path(self.filepath))
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        space = area.spaces.active
                        if space.type == 'VIEW_3D':
                            space.shading.type = 'MATERIAL'
            finally:
                for message_lvl, message in loader.messages:
                    self.report({message_lvl}, message)
        return {'FINISHED'}


def import_unit_menu_func(self, context):
    op = self.layout.operator(ImportUnit.bl_idname, text='Gladius Unit (.xml)')
    remember_last_args(op, context, 'import_xml')

def import_msh_menu_func(self, context):
    op = self.layout.operator(ImportMsh.bl_idname, text='Gladius Mesh (.msh)')
    remember_last_args(op, context, 'import_msh')


def register():
    bpy.utils.register_class(LastCallArgsGroup)
    bpy.utils.register_class(AddonPreferences)
    bpy.utils.register_class(ImportUnit)
    bpy.utils.register_class(ImportMsh)
    bpy.types.TOPBAR_MT_file_import.append(import_unit_menu_func)
    bpy.types.TOPBAR_MT_file_import.append(import_msh_menu_func)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(import_msh_menu_func)
    bpy.types.TOPBAR_MT_file_import.remove(import_unit_menu_func)
    bpy.utils.unregister_class(ImportMsh)
    bpy.utils.unregister_class(ImportUnit)
    bpy.utils.unregister_class(AddonPreferences)
    bpy.utils.unregister_class(LastCallArgsGroup)
