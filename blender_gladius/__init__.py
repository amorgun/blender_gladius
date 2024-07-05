bl_info = {
    'name': 'Gladius - Relics of War .MSH meshes and .XML unit files',
    'description': 'Import models from Warhammer 40,000: Gladius - Relics of War',
    'author': 'amorgun',
    'license': 'GPL',
    'version': (1, 1),
    'blender': (4, 1, 0),
    'doc_url': 'https://github.com/amorgun/blender_gladius',
    'tracker_url': 'https://github.com/amorgun/blender_gladius/issues',
    'support': 'COMMUNITY',
    'category': 'Import-Export',
}

import pathlib
import platform

import bpy
from bpy_extras.io_utils import ImportHelper

from . import importer


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

    def draw(self, context):
        self.layout.prop(self, 'mod_folder')


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

    def execute(self, context):
        if self.new_project:
            bpy.ops.wm.read_homefile(app_template='')
            for mesh in bpy.data.meshes:
                bpy.data.meshes.remove(mesh)
        preferences = context.preferences
        addon_prefs = preferences.addons[__package__].preferences
        loader = importer.UnitLoader(pathlib.Path(addon_prefs.mod_folder), context=context)
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

    def execute(self, context):
        if self.new_project:
            bpy.ops.wm.read_homefile(app_template='')
            for mesh in bpy.data.meshes:
                bpy.data.meshes.remove(mesh)
        preferences = context.preferences
        addon_prefs = preferences.addons[__package__].preferences
        loader = importer.UnitLoader(pathlib.Path(addon_prefs.mod_folder), context=context)
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
    self.layout.operator(ImportUnit.bl_idname, text='Gladius Unit (.xml)')


def import_msh_menu_func(self, context):
    self.layout.operator(ImportMsh.bl_idname, text='Gladius Mesh (.msh)')


def register():
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