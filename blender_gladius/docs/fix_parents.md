# How to fix parents in the imported model

If you tried to pose a model imported from Gladius you noticed that rotating a bone doesn't affect its children.  
It happens because there is no information about the parent bones in the Gladius model format.  
Here I'll describe a way to restore this information.
1. Import a Gladius model
2. Open the Scripting tab and run the following script:
```py
import bpy
orig_arm = bpy.data.objects['Armature']
bpy.context.view_layer.objects.active = orig_arm
bone_collection = orig_arm.data.collections.new('Orig')
bpy.ops.object.mode_set(mode='EDIT', toggle=True)
orig_names = []
for b in list(orig_arm.data.bones):
    orig_name = b.name
    orig_bone = orig_arm.data.edit_bones[orig_name]
    bone_collection.assign(orig_bone)
    orig_names.append(orig_name)
    nb = orig_arm.data.edit_bones.new(orig_name + '_fix')
    nb.length = b.length
    nb.matrix = orig_bone.matrix
bpy.ops.object.mode_set(mode='EDIT', toggle=True)
bone_collection.is_visible = False
for name in orig_names:
    bone = orig_arm.pose.bones[name + '_fix']
    constraint = bone.constraints.new("COPY_TRANSFORMS")
    constraint.target = orig_arm
    constraint.subtarget = name
for obj in bpy.data.objects:
    if obj.type != 'MESH':
        continue
    for g in obj.vertex_groups:
        g.name = g.name + '_fix'
```
3. Manually set the correct parents for each bone
    1. Unhide the Armature and select it
    2. Go to Edit mode
    3. For each bone
        1. Click to select this bone
        2. Shift+Click to select the parent for this bone
        3. Press Ctrl+P and select `Keep Offset`
4. Make sure the Armature is still selected. Go back to the Scripting and run the following script:
```py
import bpy
armature = bpy.context.object
actions = list(bpy.data.actions)
latest = len(actions) - 1
for idx, a in enumerate(actions):
    orig_name = a.name
    armature.animation_data.action = a
    bpy.ops.nla.bake(frame_start=1, frame_end=int(a.frame_end), only_selected=False, visual_keying=True, clear_constraints=idx == latest, bake_types={'POSE'}, channel_types={'LOCATION', 'ROTATION', 'SCALE', 'BBONE'})

    action = bpy.data.actions['Action']
    a.name = f'{a.name}_orig'
    action.name = orig_name
    action.use_fake_user = True
    bpy.data.actions.remove(a, do_unlink=True)
```

All done. Now you have a correctly configured Armature and animations are baked to work with it.