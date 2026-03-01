import dataclasses
import pathlib
import math
import struct
import xml.etree.ElementTree as ET

import bpy
import mathutils


class StopParsing(Exception): ...


def read_str(stream) -> str:
    res = []
    while (c := stream.read(1)) != b'\x00':
        res.append(c)
    return str(b''.join(res), 'utf8')


def read_struct(fmt: str, stream) -> tuple:
    size = struct.calcsize(fmt)
    return struct.unpack(fmt, stream.read(size))


def read_one(fmt: str, stream):
    p = read_struct(fmt, stream)
    assert len(p) == 1
    return p[0]


@dataclasses.dataclass
class VertexData:
    position: list[float] = dataclasses.field(default_factory=lambda: [0] * 3)
    normal: list[float] = dataclasses.field(default_factory=lambda: [0] * 3)
    bone_weights: list[float] = dataclasses.field(default_factory=lambda: [0] * 4)
    bone_ids: list[int] = dataclasses.field(default_factory=lambda: [0] * 4)


class UnitLoader:
    def __init__(
        self,
        data_root: pathlib.Path,
        scale: float,
        enable_vertex_automerge: bool,
        vertex_position_merge_threshold: float = 0.001,
        vertex_normal_merge_threshold: float = 1.99,
        vertex_weight_merge_threshold: float = 0.01,
        context=None,
    ):
        self.data_root = data_root
        self.scale = scale
        self.enable_vertex_automerge = enable_vertex_automerge
        self.vertex_position_merge_threshold = vertex_position_merge_threshold
        self.vertex_normal_merge_threshold = vertex_normal_merge_threshold
        self.vertex_weight_merge_threshold = vertex_weight_merge_threshold

        self.bpy_context = context
        if self.bpy_context is None:
            self.bpy_context = bpy.context
        self._reset()

    def _reset(self):
        self.armature = bpy.data.armatures.new('Armature')
        self.armature_obj = bpy.data.objects.new('Armature', self.armature)
        self.armature_obj.show_in_front = True
        self.armature_obj.scale = self.scale, self.scale, self.scale
        bpy.data.collections['Collection'].objects.link(self.armature_obj)
        self.messages = []

    def read_xml(self, filepath: str, expected_tag: str = None) -> ET.Element:
        tree = ET.parse(filepath)
        root = tree.getroot()
        if expected_tag is not None and root.tag != expected_tag:
            self.messages.append(('ERROR', f'File {filepath} contains a wrong kind of data: expected {expected_tag}, got {root.tag}'))
            raise StopParsing
        return root

    def load_material(self, filepath: pathlib.Path):
        xml_root = self.read_xml(filepath.with_suffix('.xml'), 'material')
        mat = bpy.data.materials.new(name=filepath.stem)
        mat.blend_method = 'CLIP'
        mat.show_transparent_back = False
        mat.use_nodes = True
        links = mat.node_tree.links
        node_final = mat.node_tree.nodes[0]
        textures = {}
        for tex in xml_root.find('textures').iterfind('texture'):
            if tex.get('name') == 'ShadowMapColor':
                continue
            texture_path = self.data_root / 'Video/Textures' / f'{tex.get("name")}.dds'
            image = bpy.data.images.load(str(texture_path))
            image.pack()
            if texture_path.stem.endswith('Diffuse'):
                key = 'diffuse'
            elif texture_path.stem.endswith('Normal'):
                key = 'normal'
            elif texture_path.stem.endswith('SIC'):
                key = 'sic'
            textures[key] = image

        node_diffuse = mat.node_tree.nodes.new('ShaderNodeTexImage')
        node_diffuse.image = textures['diffuse']
        node_diffuse.label = 'diffuse'
        links.new(node_diffuse.outputs[1], node_final.inputs['Alpha'])
        node_diffuse.location = -500, 400 - 320 * 0

        node_normal_img = mat.node_tree.nodes.new('ShaderNodeTexImage')
        node_normal_img.image = textures['normal']
        node_normal_img.label = 'normal'
        node_normal_img.location = -500, 400 - 320 * 1

        node_normal = mat.node_tree.nodes.new('ShaderNodeNormalMap')
        node_normal.location = -200, 400 - 320 * 1
        links.new(node_normal_img.outputs[0], node_normal.inputs['Color'])
        links.new(node_normal.outputs[0], node_final.inputs['Normal'])

        node_sic = mat.node_tree.nodes.new('ShaderNodeTexImage')
        node_sic.image = textures['sic']
        node_sic.label = 'sic'
        node_sic.location = -700, 400 - 320 * 2

        node_split = mat.node_tree.nodes.new('ShaderNodeSeparateColor')
        links.new(node_sic.outputs[0], node_split.inputs['Color'])
        links.new(node_split.outputs[0], node_final.inputs['Metallic'])
        links.new(node_split.outputs[1], node_final.inputs['Emission Strength'])
        node_split.location = -400, 400 - 320 * 2

        node_mix = mat.node_tree.nodes.new('ShaderNodeMixRGB')
        links.new(node_split.outputs[2], node_mix.inputs['Fac'])
        links.new(node_diffuse.outputs[0], node_mix.inputs['Color1'])
        node_mix.inputs['Color2'].default_value = (0.60, 0.07, 0.08, 0.0)
        links.new(node_mix.outputs[0], node_final.inputs['Base Color'])
        links.new(node_mix.outputs[0], node_final.inputs['Emission Color'])
        node_mix.location = -200, 400 - 320 * 2

        return mat

    def load_mesh(self, filename: str, *args, **kwargs):
        full_path = self.data_root / 'Video/Meshes' / filename
        return self.load_msh_file(full_path.with_suffix('.msh'), *args, **kwargs)

    def load_msh_file(self, filepath: pathlib.Path, material=None, parent_bone=None, apply_scale: bool = False):
        delta = mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'Z')  # Fix bone rotation
        if parent_bone is None:
            global_matrix = mathutils.Matrix.Identity(4)
        else:
            global_matrix = parent_bone.matrix_local @ delta.inverted().to_4x4()
        with filepath.open('rb') as f:
            magic = read_str(f)
            assert magic == 'MSH1.0', magic
            self.bpy_context.view_layer.objects.active = self.armature_obj
            bpy.ops.object.mode_set(mode='EDIT', toggle=True)
            num_bones = read_one('<B', f)
            bone_names = []
            created_bones = {}
            for _ in range(num_bones):
                bone_name = read_str(f)
                bone_matrix = read_struct('<16f', f)
                bone_names.append(bone_name)
                if parent_bone and parent_bone.name == bone_name:
                    new_bone = parent_bone
                else:
                    new_bone = self.armature.edit_bones.new(bone_name)
                    new_bone.head = (0, 0, 0)
                    new_bone.tail = (10, 0, 0)
                    new_bone.matrix = global_matrix @ mathutils.Matrix([bone_matrix[i*4:i*4+4] for i in range(4)]).transposed() @ delta.to_4x4()
                    if parent_bone:
                        new_bone.parent = self.armature.edit_bones[parent_bone.name]
                created_bones[bone_name] = new_bone.name
            bpy.ops.object.mode_set(mode='EDIT', toggle=True)
            unk_type1 = read_one('<B', f)
            unk_data1 = read_struct('<9f', f)
            unk_type2 = read_one('<B', f)
            unk_data2 = read_struct('<12f', f)
            has_bbox = unk_type2 == 2
            if has_bbox:
                bbox_name = read_str(f)
                bbox_pos = read_struct('<3f', f)
                unk_data2_2 = read_one('<f', f)  # usually 1.0
                bbox_rot = read_struct('<4f', f)
                bbox_scale = read_struct('<3f', f)
            unk_type3 = read_one('<B', f)
            unk_data3 = read_struct('<6f', f)
            layout_size = read_one('<B', f)
            vertex_layout = {read_str(f): read_one('<B', f) for _ in range(layout_size)}
            data_size = read_one('<L', f)
            vertex_info_size = sum(vertex_layout.values())
            vertex_cnt = data_size // vertex_info_size
            assert vertex_cnt % 3 == 0, f'{data_size=} {vertex_info_size=}'
            poly_cnt = vertex_cnt // 3

            face_list = []
            face_uv_list = []

            vertex_list: list[VertexData] = []
            for poly_idx in range(poly_cnt):
                face_vertices = []
                for idx in range(3):
                    vertex_data = {k: read_struct(f'<{v}f', f) for k, v in vertex_layout.items()}
                    vertex_item = VertexData(
                        position=(global_matrix @ mathutils.Vector(vertex_data['vertexPosition'])).freeze(),
                        normal=(global_matrix @ mathutils.Vector(vertex_data.get('vertexNormal', (0, 0, 0)))).freeze(),
                    )
                    for bone_idx, bone_weight in sorted(zip(vertex_data.get('vertexBoneIndices', []), vertex_data.get('vertexBoneWeights', []))):
                        if bone_weight == 0:
                            continue
                        vertex_item.bone_ids.append(bone_idx)
                        vertex_item.bone_weights.append(bone_weight)
                    face_vertices.append(len(vertex_list))
                    vertex_list.append(vertex_item)
                    u, v = vertex_data.get('vertexTextureCoordinate', (0, 0))
                    face_uv_list.append((u, 1 - v))
                face_list.append(face_vertices)

            if self.enable_vertex_automerge:
                vertex_kd = mathutils.kdtree.KDTree(vertex_cnt)
                for idx, v in enumerate(vertex_list):
                    vertex_kd.insert(v.position, idx)
                vertex_kd.balance()
                vertex_group_by_postition = {}
                seen_data = {}
                idx2merged = []
                merged_vert_ids = []
                for orig_vertex_idx, v in enumerate(vertex_list):
                    for (co, index, dist) in vertex_kd.find_range(v.position, self.vertex_position_merge_threshold):
                        if index == orig_vertex_idx:
                            continue
                        if index in vertex_group_by_postition:
                            vertex_group_key = vertex_group_by_postition[index]
                            break
                    else:
                        vertex_group_key = vertex_group_by_postition[orig_vertex_idx] = orig_vertex_idx
                    seen_vertex_data = seen_data.setdefault(vertex_group_key, [])
                    vertex_normal = v.normal
                    bone_ids = tuple(v.bone_ids)
                    bone_weights = mathutils.Vector(v.bone_weights).to_4d()
                    vertex_idx = None
                    for idx, other_normal, other_bone_ids, other_bone_weights in seen_vertex_data:
                        if (
                            (other_normal - vertex_normal).length < self.vertex_normal_merge_threshold
                            and bone_ids == other_bone_ids
                            and (bone_weights - other_bone_weights).length < self.vertex_weight_merge_threshold
                        ):
                            vertex_idx = idx
                            break
                    if vertex_idx is None:
                        vertex_idx = len(merged_vert_ids)
                        seen_vertex_data.append((vertex_idx, vertex_normal, bone_ids, bone_weights))
                        merged_vert_ids.append(orig_vertex_idx)
                    idx2merged.append(vertex_idx)
                old_face_list = face_list
                face_list = []
                uv_array =  face_uv_list
                face_uv_list = []
                seen_faces = set()
                vertex_normals = []
                for face in old_face_list:
                    new_face = [idx2merged[i] for i in face]
                    if not (new_face[0] != new_face[1] != new_face[2] != new_face[0]):
                        continue
                    f_key = tuple(sorted(new_face))
                    if f_key in seen_faces:
                        continue
                    seen_faces.add(f_key)
                    face_list.append(new_face)
                    face_uv_list.extend(uv_array[i] for i in face)
                    vertex_normals.extend(vertex_list[i].normal for i in face)
                vertex_list = [vertex_list[i] for i in merged_vert_ids]
                del uv_array
            else:
                vertex_normals = [vertex_list[v].normal for p in face_list for v in p]

            new_mesh = bpy.data.meshes.new(filepath.stem)
            new_mesh.from_pydata([v.position for v in vertex_list], [], face_list, shade_flat=False)
            new_mesh.normals_split_custom_set(vertex_normals)

            uv_layer = new_mesh.uv_layers.new()
            uv_layer.data.foreach_set('uv', [i for p in face_uv_list for i in p])

            if material is not None:
                new_mesh.materials.append(material)
                new_mesh.polygons.foreach_set('material_index', [len(new_mesh.materials) - 1] * len(new_mesh.polygons))

            obj = bpy.data.objects.new(filepath.stem, new_mesh)
            obj.parent = self.armature_obj

            vertex_groups = {}
            for vertex_idx, v in enumerate(vertex_list):
                for bone_idx, bone_weight in zip(v.bone_ids, v.bone_weights):
                    bone_name = bone_names[int(bone_idx)]
                    vertex_groups.setdefault(bone_name, []).append((vertex_idx, bone_weight))

            for bone_name in created_bones:
                vertex_group = obj.vertex_groups.new(name=bone_name)
                weight_info = vertex_groups.get(bone_name)
                if weight_info is None:
                    continue
                for vertex_idx, bone_weight in weight_info:
                    vertex_group.add([vertex_idx], bone_weight, 'REPLACE')
            
            armature_mod = obj.modifiers.new('Skeleton', 'ARMATURE')
            armature_mod.object = self.armature_obj
            bpy.data.collections['Collection'].objects.link(obj)
            if has_bbox:
                bbox = bpy.data.objects.new(bbox_name, None)
                bbox.empty_display_type = 'CUBE'
                bbox.matrix_local = global_matrix @ mathutils.Matrix.LocRotScale(
                    mathutils.Vector(bbox_pos),
                    mathutils.Quaternion([bbox_rot[3], *bbox_rot[:3]]),
                    mathutils.Vector(bbox_scale),
                )
                bbox.parent = obj
                bpy.data.collections['Collection'].objects.link(bbox)

    def load_animations(self, name: str, filename: str, count: int | str = None, suffix: str = ''):
        if count is None or int(count) == 1:
            self.load_anm_file(f'{name}{suffix}', self.data_root / 'Video/Animations' / f'{filename}{suffix}.anm')
        else:
            for idx in range(int(count)):
                self.load_anm_file(f'{name}{suffix}{idx}', self.data_root / 'Video/Animations' / f'{filename}{idx}{suffix}.anm')

    def load_anm_file(self, name: str, filepath: pathlib.Path):
        if not filepath.exists():
            self.messages.append(('WARNING', f'Cannot find a file {filepath}'))
            return
        with filepath.open('rb') as f:
            magic = read_str(f)
            assert magic == 'ANM1.0', magic
            animation = bpy.data.actions.new(name=name)
            animation.use_fake_user = True
            if self.armature_obj.animation_data is None:
                self.armature_obj.animation_data_create()
            self.armature_obj.animation_data.action = animation
            num_bones, num_frames, framerate = read_struct('<BLL', f)
            animation.frame_range = 0, num_frames - 1
            for _ in range(num_bones):
                bone_name = read_str(f)
                try:
                    bone = self.armature_obj.pose.bones[bone_name]
                    orig_pos, orig_rot, orig_scale = bone.bone.matrix_local.decompose()
                except KeyError:  # Something weird with Chaplain and TacticalMarines
                    # matching_bones = [b for b in self.armature_obj.pose.bones if b.name.startswith(bone_name)]
                    # if len(matching_bones) == 1:
                    #     bone = matching_bones[0]
                    #     # self.messages.append(('DEBUG', f'Animation {filepath} contains an unknown bone {bone_name}. Interpreted as {bone.name}'))
                    # # if bone_idx < len(self.bones) and self.bones[bone_idx].startswith(bone_name):
                    # #     bone = self.armature_obj.pose.bones[bone_name]
                    # else:
                    #     self.messages.append(('WARNING', f'Animation {filepath} contains an unknown bone {bone_name}. Cannot guess the correct name'))
                    #     bone = None
                    bone = None
                    self.messages.append(('WARNING', f'Animation {filepath} contains an unknown bone {bone_name}.'))
                for frame in range(num_frames):
                    pos = mathutils.Vector(read_struct('<3f', f))
                    rot = read_struct('<4f', f)
                    scale = mathutils.Vector(read_struct('<3f', f))
                    if bone is None:
                        continue
                    rot = mathutils.Quaternion([rot[3], *rot[:3]])
                    bone.matrix = mathutils.Matrix.LocRotScale(pos + orig_pos, rot @ orig_rot, scale * orig_scale)
                    self.armature_obj.keyframe_insert(data_path=f'pose.bones["{bone.name}"].location', frame=frame, group=bone_name)
                    self.armature_obj.keyframe_insert(data_path=f'pose.bones["{bone.name}"].rotation_quaternion', frame=frame, group=bone_name)
                    self.armature_obj.keyframe_insert(data_path=f'pose.bones["{bone.name}"].scale', frame=frame, group=bone_name)

    def load_unit(self, filepath: pathlib.Path):
        root = self.read_xml(filepath, 'unit')
        loaded_animations = {}
        animation_suffixes = []
        for unit in root.find('model'):
            material = self.load_material(self.data_root / 'Video/Materials' / unit.get('material'))
            unit_name = unit.get('mesh')
            self.load_mesh(unit_name, material)
            idle_animation_path = unit.get('idleAnimation')
            if idle_animation_path:
                self.load_animations('idle', idle_animation_path, unit.get('idleAnimationCount'))
                loaded_animations[idle_animation_path] = 'idle', unit.get('idleAnimationCount')
        for weapons in root.iterfind('weapons'):
            for weapon in weapons.iterfind('weapon'):
                for model in weapon.iterfind('model'):
                    for weapon_type in model:
                        material_path = weapon_type.get('material')
                        mesh_path = weapon_type.get('mesh')
                        if mesh_path is None:
                            continue
                        parent_bone_name = weapon_type.get('bone')
                        if parent_bone_name:
                            parent_bone = self.armature.bones[parent_bone_name]
                        else:
                            parent_bone = None
                        if mesh_path and material_path:
                            material = self.load_material(self.data_root / 'Video/Materials' / material_path)
                            self.load_mesh(mesh_path, material, parent_bone=parent_bone)
                            animation_suffix = weapon_type.get('animationSuffix')
                            if animation_suffix:
                                animation_suffixes.append(animation_suffix)
        for actions_root in root.iterfind('actions'):
            for action in actions_root:
                for model in action.iterfind('model'):
                    extra_actions = []
                    for action_inner in model.iterfind('action'):
                        for key, animation_path in action_inner.attrib.items():
                            if not key.lower().endswith('animation'):
                                continue
                            if animation_path in loaded_animations:
                                continue
                            suffix = key[:-len('animation')]
                            animation_name, animation_count = f'{action.tag}{suffix[:1].upper()}{suffix[1:]}', action_inner.get(f'{key}Count')
                            self.load_animations(animation_name, animation_path, animation_count)
                            loaded_animations[animation_path] = animation_name, animation_count
                            for suffix in ('Move', 'Levitate'):
                                if animation_path.lower().endswith(suffix.lower()):
                                    extra_actions.append((f'{animation_name}Begin', f'{animation_path}Begin', 1))
                                    extra_actions.append((f'{animation_name}End', f'{animation_path}End', 1))
                                    break
                    for anim_name, anim_path, animation_count in extra_actions:
                        if not (self.data_root / 'Video/Animations' / f'{anim_path}.anm').exists():
                            continue
                        self.load_animations(anim_name, anim_path, animation_count)
                        loaded_animations[anim_path] = anim_name, animation_count

        for suffix in animation_suffixes:
            for path, (name, cnt) in loaded_animations.items():
                self.load_animations(name, path, cnt, suffix=suffix)
        bpy.ops.object.mode_set(mode='EDIT', toggle=True)
        for bone in self.armature_obj.pose.bones:
            bone.matrix_basis = mathutils.Matrix()
        bpy.ops.object.mode_set(mode='EDIT', toggle=True)
        self.armature_obj.hide_set(True)

def import_unit(data_root: pathlib.Path, target_path: pathlib.Path):
    print('------------------------')
    for action in bpy.data.actions:
        bpy.data.actions.remove(action)

    for material in bpy.data.materials:
        material.user_clear()
        bpy.data.materials.remove(material)
    
    for image in bpy.data.images:
        bpy.data.images.remove(image)

    for mesh in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)

    loader = UnitLoader(data_root)
    try:
        loader.load_unit(target_path)
    finally:
        for _, msg in loader.messages:
            print(msg)
