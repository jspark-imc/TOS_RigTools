bl_info = {
    "name": "Biped Test Rig (3ds Max Biped check)",
    "author": "Claude for 정현",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > Biped Test",
    "description": "Adds Biped-like controls (COM, IK hands/feet, poles, FK circles) to an imported 3ds Max Biped skeleton to check skin weights",
    "category": "Rigging",
}

import bpy, bmesh, math
from mathutils import Vector, Matrix, Quaternion

CTRL_PREFIX = "CTRL_"
WGT_COLL = "WGT_BipedTest"
ROM_ACTION = "BipedTest_ROM"


# ------------------------------------------------------------------ helpers
def find_prefix(arm):
    for b in arm.data.bones:
        if b.name.endswith(" Pelvis"):
            return b.name[: -len(" Pelvis")]
    return None


def N(p, side, part):  # Biped bone name, e.g. N("Bip01","L","UpperArm") -> "Bip01 L UpperArm"
    return ("%s %s %s" % (p, side, part)) if side else ("%s %s" % (p, part))


def wdir_to_arm(arm, v):
    m = arm.matrix_world.to_3x3().inverted()
    return (m @ Vector(v)).normalized()


def widget(name, kind):
    coll = bpy.data.collections.get(WGT_COLL)
    if coll is None:
        coll = bpy.data.collections.new(WGT_COLL)
        bpy.context.scene.collection.children.link(coll)
    coll.hide_viewport = True
    coll.hide_render = True
    ob = bpy.data.objects.get(name)
    if ob:
        return ob
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    if kind == "circle":  # ring around the bone axis (bone Y)
        vs = [bm.verts.new((math.cos(a) * 0.5, 0.5, math.sin(a) * 0.5)) for a in [i * 2 * math.pi / 24 for i in range(24)]]
        for i in range(24):
            bm.edges.new((vs[i], vs[(i + 1) % 24]))
    elif kind == "square":  # flat square on the ground plane of the bone
        pts = [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)]
        vs = [bm.verts.new(p) for p in pts]
        for i in range(4):
            bm.edges.new((vs[i], vs[(i + 1) % 4]))
        vs2 = [bm.verts.new((x * 0.8, y, z * 0.8)) for x, y, z in pts]
        for i in range(4):
            bm.edges.new((vs2[i], vs2[(i + 1) % 4]))
    elif kind == "cube":
        bmesh.ops.create_cube(bm, size=1.0)
        bm.faces.ensure_lookup_table()
        for f in list(bm.faces):
            bm.faces.remove(f)
    elif kind == "diamond":
        pts = [(0.5, 0, 0), (-0.5, 0, 0), (0, 0.5, 0), (0, -0.5, 0), (0, 0, 0.5), (0, 0, -0.5)]
        vs = [bm.verts.new(p) for p in pts]
        for a in (0, 1):
            for b in (2, 3, 4, 5):
                bm.edges.new((vs[a], vs[b]))
        for a, b in ((2, 4), (4, 3), (3, 5), (5, 2)):
            bm.edges.new((vs[a], vs[b]))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def signed_angle(u, v, normal):
    a = u.angle(v)
    if u.cross(v).angle(normal) < 1:
        a = -a
    return a


def pole_angle(base, ikb, pole_loc):
    pole_normal = (ikb.tail - base.head).cross(pole_loc - base.head)
    proj = pole_normal.cross(base.tail - base.head)
    return signed_angle(base.x_axis, proj, base.tail - base.head)


def remove_test_rig(arm):
    for pb in arm.pose.bones:
        for c in list(pb.constraints):
            if c.name.startswith("BT_"):
                pb.constraints.remove(c)
        pb.custom_shape = None
    prev = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    p = find_prefix(arm)
    pel = eb.get(N(p, None, "Pelvis"))
    if pel and pel.parent and pel.parent.name.startswith(CTRL_PREFIX):
        pel.parent = None
    for b in [b for b in eb if b.name.startswith(CTRL_PREFIX)]:
        eb.remove(b)
    bpy.ops.object.mode_set(mode="OBJECT")
    for c in list(arm.data.collections):
        if c.name.startswith("BT "):
            arm.data.collections.remove(c)
    bpy.context.view_layer.objects.active = prev


# ------------------------------------------------------------------ build
def build_test_rig(arm):
    p = find_prefix(arm)
    if not p:
        raise RuntimeError("No '<name> Pelvis' bone found - is this a Biped skeleton?")
    if CTRL_PREFIX + "COM" in arm.data.bones:
        remove_test_rig(arm)
    bones = arm.data.bones
    # facing: Max characters look down -Y; character's left is +X then
    lthigh = arm.matrix_world @ bones[N(p, "L", "Thigh")].head_local
    pelv = arm.matrix_world @ bones[N(p, None, "Pelvis")].head_local
    front_w = Vector((0, -1, 0)) if (lthigh - pelv).x > 0 else Vector((0, 1, 0))
    UP = wdir_to_arm(arm, (0, 0, 1))
    FRONT = wdir_to_arm(arm, front_w)

    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones

    def new(name, head, tail, parent=None):
        b = eb.new(CTRL_PREFIX + name)
        b.head, b.tail = head, tail
        b.parent = parent
        b.use_deform = False
        return b

    # limb bones must point at the next Biped joint, or IK flips them (extra child bones such as
    # elbow/knee volume helpers can make Blender aim a limb bone at the wrong child on import)
    for s in ("L", "R"):
        for a, b in (("UpperArm", "Forearm"), ("Forearm", "Hand"), ("Thigh", "Calf"), ("Calf", "Foot")):
            ba, bb = eb.get(N(p, s, a)), eb.get(N(p, s, b))
            if ba and bb and (bb.head - ba.head).length > 1e-6:
                ba.use_connect = False
                ba.tail = bb.head.copy()

    pel = eb[N(p, None, "Pelvis")]
    L_leg = (eb[N(p, "L", "Thigh")].head - eb[N(p, "L", "Foot")].head).length
    com = new("COM", pel.head.copy(), pel.head + UP * L_leg * 0.25)
    pel.parent = com
    pel.use_connect = False
    info = {"pole": {}}
    for s in ("L", "R"):
        up, fo, ha = eb[N(p, s, "UpperArm")], eb[N(p, s, "Forearm")], eb[N(p, s, "Hand")]
        chest = eb[N(p, s, "Clavicle")].parent
        alen = up.length + fo.length
        new("IK_Hand_" + s, ha.head.copy(), ha.head + (ha.tail - ha.head).normalized() * alen * 0.15, chest).roll = ha.roll
        pl = fo.head + (-FRONT) * alen * 0.6
        new("Pole_Elbow_" + s, pl, pl + UP * alen * 0.08, chest)
        info["pole"]["arm" + s] = pole_angle(up, fo, pl)
        th, ca, ft = eb[N(p, s, "Thigh")], eb[N(p, s, "Calf")], eb[N(p, s, "Foot")]
        llen = th.length + ca.length
        new("IK_Foot_" + s, ft.head.copy(), ft.head + (ft.tail - ft.head).normalized() * llen * 0.15).roll = ft.roll
        kl = ca.head + FRONT * llen * 0.6
        new("Pole_Knee_" + s, kl, kl + UP * llen * 0.08)
        info["pole"]["leg" + s] = pole_angle(th, ca, kl)
    bpy.ops.object.mode_set(mode="POSE")

    pbs = arm.pose.bones
    W = {k: widget("WGT_BT_" + k, k) for k in ("circle", "square", "cube", "diamond")}
    BLUE, GREEN, YELLOW, RED = "THEME04", "THEME03", "THEME09", "THEME01"

    def style(name, wgt, color, scale=1.0):
        pb = pbs.get(name)
        if not pb:
            return
        pb.custom_shape = W[wgt]
        pb.custom_shape_scale_xyz = (scale, scale, scale)
        pb.bone.color.palette = color
        pb.color.palette = color

    # IK constraints
    for s in ("L", "R"):
        c = pbs[N(p, s, "Forearm")].constraints.new("IK")
        c.name = "BT_IK"
        c.target, c.subtarget = arm, CTRL_PREFIX + "IK_Hand_" + s
        c.pole_target, c.pole_subtarget = arm, CTRL_PREFIX + "Pole_Elbow_" + s
        c.pole_angle, c.chain_count = info["pole"]["arm" + s], 2
        c = pbs[N(p, s, "Hand")].constraints.new("COPY_ROTATION")
        c.name = "BT_HandRot"
        c.target, c.subtarget = arm, CTRL_PREFIX + "IK_Hand_" + s
        c = pbs[N(p, s, "Calf")].constraints.new("IK")
        c.name = "BT_IK"
        c.target, c.subtarget = arm, CTRL_PREFIX + "IK_Foot_" + s
        c.pole_target, c.pole_subtarget = arm, CTRL_PREFIX + "Pole_Knee_" + s
        c.pole_angle, c.chain_count = info["pole"]["leg" + s], 2
        c = pbs[N(p, s, "Foot")].constraints.new("COPY_ROTATION")
        c.name = "BT_FootRot"
        c.target, c.subtarget = arm, CTRL_PREFIX + "IK_Foot_" + s
        col = BLUE if s == "L" else GREEN
        style(CTRL_PREFIX + "IK_Hand_" + s, "cube", col, 2.5)
        style(CTRL_PREFIX + "IK_Foot_" + s, "cube", col, 2.0)
        style(CTRL_PREFIX + "Pole_Elbow_" + s, "diamond", col, 3.0)
        style(CTRL_PREFIX + "Pole_Knee_" + s, "diamond", col, 3.0)
        style(N(p, s, "Clavicle"), "circle", col, 1.2)
        for f in range(5):
            for seg in ("", "1", "2"):
                style(N(p, s, "Finger%d%s" % (f, seg)), "circle", col, 0.8)
        style(N(p, s, "Toe0"), "circle", col, 1.0)
    style(CTRL_PREFIX + "COM", "square", YELLOW, 1.6)
    for n in ("Pelvis", "Spine", "Spine1", "Spine2", "Spine3", "Neck", "Head"):
        style(N(p, None, n), "circle", YELLOW, 1.5 if n != "Neck" else 1.0)
    extra = []
    for pb in pbs:
        low = pb.name.lower()
        if not pb.name.startswith(p) and not pb.name.startswith(CTRL_PREFIX) and ("skirt" in low or "hair" in low):
            style(pb.name, "circle", RED, 0.9)
            extra.append(pb.name)

    # bone collections
    def bcoll(name, visible):
        c = arm.data.collections.get(name) or arm.data.collections.new(name)
        c.is_visible = visible
        return c
    c_ctrl, c_body, c_extra, c_hide = bcoll("BT Controls", True), bcoll("BT Body", True), bcoll("BT Extra (face/skirt/hair)", True), bcoll("BT Hidden", False)
    for b in arm.data.bones:
        for c in list(b.collections):
            c.unassign(b)
        if b.name.startswith(CTRL_PREFIX):
            c_ctrl.assign(b)
        elif b.name.endswith("Nub") or "Twist" in b.name or b.name.endswith("Footsteps") or b.name.endswith("Prop1"):
            c_hide.assign(b)
        elif b.name.startswith(p):
            (c_ctrl if pbs[b.name].custom_shape else c_body).assign(b)
        else:
            (c_ctrl if pbs[b.name].custom_shape else c_extra).assign(b)
    for c in list(arm.data.collections):
        if not c.name.startswith("BT ") and len(c.bones) == 0:
            arm.data.collections.remove(c)
    arm.data.display_type = "STICK"
    arm.show_in_front = True
    arm["bt_ik"] = 1.0
    for pb in pbs:
        pb.rotation_mode = "QUATERNION"
    bpy.ops.object.mode_set(mode="POSE")
    return "test rig built: COM, IK hands/feet + poles, FK circles, %d skirt/hair controls" % len(extra)


def set_ik(arm, on):
    for pb in arm.pose.bones:
        for c in pb.constraints:
            if c.name.startswith("BT_"):
                c.influence = 1.0 if on else 0.0
    arm["bt_ik"] = 1.0 if on else 0.0


def reset_pose(arm):
    for pb in arm.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)


# ------------------------------------------------------------------ range-of-motion test animation
def make_rom(arm):
    p = find_prefix(arm)
    if CTRL_PREFIX + "COM" not in arm.data.bones:
        build_test_rig(arm)
    pbs = arm.pose.bones
    bones = arm.data.bones
    lthigh = arm.matrix_world @ bones[N(p, "L", "Thigh")].head_local
    pelv = arm.matrix_world @ bones[N(p, None, "Pelvis")].head_local
    front_w = Vector((0, -1, 0)) if (lthigh - pelv).x > 0 else Vector((0, 1, 0))
    UP, FRONT = wdir_to_arm(arm, (0, 0, 1)), wdir_to_arm(arm, front_w)
    if arm.animation_data and arm.animation_data.action:
        arm.animation_data.action = None
    reset_pose(arm)
    set_ik(arm, True)
    act = bpy.data.actions.get(ROM_ACTION)
    if act:
        bpy.data.actions.remove(act)
    arm.animation_data_create()
    arm.animation_data.action = bpy.data.actions.new(ROM_ACTION)

    def armlen(s):
        return bones[N(p, s, "UpperArm")].length + bones[N(p, s, "Forearm")].length

    leglen = bones[N(p, "L", "Thigh")].length + bones[N(p, "L", "Calf")].length
    keyed = [CTRL_PREFIX + n for n in ("COM", "IK_Hand_L", "IK_Hand_R", "IK_Foot_L", "IK_Foot_R")]
    keyed += [N(p, None, n) for n in ("Spine", "Spine1", "Spine2", "Neck", "Head") if N(p, None, n) in pbs]
    swing = [pb.name for pb in pbs if not pb.name.startswith(p) and not pb.name.startswith(CTRL_PREFIX) and ("skirt" in pb.name.lower() or "hair" in pb.name.lower())]
    keyed += swing

    def move_to(name, arm_space_pos):
        pb = pbs[name]
        m = pb.matrix.copy()
        m.translation = arm_space_pos
        pb.matrix = m

    def rest_head(name):
        return bones[name].head_local.copy()

    def rot_local(name, axis, deg):
        if name in pbs:
            pbs[name].rotation_quaternion = Quaternion(axis, math.radians(deg))

    SIDE_W = Vector((1, 0, 0)) if front_w.y < 0 else Vector((-1, 0, 0))   # character's left

    def rot_world(name, world_axis, deg):
        """rotate a bone around a WORLD axis (independent of the bone's own roll)"""
        if name not in pbs:
            return
        a_arm = arm.matrix_world.to_3x3().inverted() @ Vector(world_axis)
        a_loc = (bones[name].matrix_local.to_3x3().inverted() @ a_arm).normalized()
        pbs[name].rotation_quaternion = Quaternion(a_loc, math.radians(deg))

    def arms_down():
        for s, side in (("L", 1), ("R", -1)):
            sh = rest_head(N(p, s, "UpperArm"))
            lat = (rest_head(N(p, s, "UpperArm")) - rest_head(N(p, None, "Spine2") if N(p, None, "Spine2") in bones else N(p, None, "Spine"))).normalized()
            move_to(CTRL_PREFIX + "IK_Hand_" + s, sh - UP * armlen(s) * 0.92 + lat * armlen(s) * 0.15)

    def elbows_bent():
        for s in ("L", "R"):
            sh = rest_head(N(p, s, "UpperArm"))
            lat = (sh - rest_head(N(p, None, "Neck"))).normalized()
            move_to(CTRL_PREFIX + "IK_Hand_" + s, sh + FRONT * armlen(s) * 0.55 - UP * armlen(s) * 0.25 - lat * armlen(s) * 0.05)

    def squat():
        pbs[CTRL_PREFIX + "COM"].location = (0, 0, 0)
        m = pbs[CTRL_PREFIX + "COM"].matrix.copy()
        m.translation = m.translation - UP * leglen * 0.28 + FRONT * leglen * 0.05
        pbs[CTRL_PREFIX + "COM"].matrix = m

    def leg_lift(s):
        f = rest_head(N(p, s, "Foot"))
        move_to(CTRL_PREFIX + "IK_Foot_" + s, f + UP * leglen * 0.45 + FRONT * leglen * 0.35)

    def twist():
        for n, d in (("Spine1", 15), ("Spine2", 10), ("Head", 35)):
            rot_world(N(p, None, n), (0, 0, 1), d)

    def bend():  # bow forward
        for n, d in (("Spine", 12), ("Spine1", 12), ("Spine2", 8), ("Head", 15)):
            rot_world(N(p, None, n), SIDE_W, d)

    def swing_all():  # swing only the first bone of each skirt/hair chain, forward
        for n in swing:
            par = bones[n].parent
            if par is None or par.name not in swing:
                rot_world(n, SIDE_W, 30 if "skirt" in n.lower() else 25)

    poses = [(0, None), (15, arms_down), (30, elbows_bent), (45, squat), (60, lambda: leg_lift("L")),
             (75, lambda: leg_lift("R")), (90, twist), (105, bend), (120, swing_all), (135, None)]
    sc = bpy.context.scene
    for frame, fn in poses:
        sc.frame_set(frame)
        reset_pose(arm)
        bpy.context.view_layer.update()
        if fn:
            fn()
        bpy.context.view_layer.update()
        for n in keyed:
            if n in pbs:
                pbs[n].keyframe_insert("location", frame=frame)
                pbs[n].keyframe_insert("rotation_quaternion", frame=frame)
    sc.frame_start, sc.frame_end = 0, 135
    sc.frame_set(0)
    return "ROM animation 0-135: arms down(15) elbows(30) squat(45) leg L(60) leg R(75) twist(90) bend(105) skirt/hair(120)"


# ------------------------------------------------------------------ UI
def active_arm(context):
    ob = context.active_object
    if ob and ob.type == "ARMATURE":
        return ob
    if ob and ob.parent and ob.parent.type == "ARMATURE":
        return ob.parent
    for o in context.scene.objects:
        if o.type == "ARMATURE" and find_prefix(o):
            return o
    return None


class BT_OT_build(bpy.types.Operator):
    bl_idname = "biped_test.build"
    bl_label = "Build / Rebuild Test Rig"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm = active_arm(context)
        if not arm:
            self.report({"ERROR"}, "Select the Biped armature")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        self.report({"INFO"}, build_test_rig(arm))
        return {"FINISHED"}


class BT_OT_rom(bpy.types.Operator):
    bl_idname = "biped_test.rom"
    bl_label = "Make Test Motion (ROM)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm = active_arm(context)
        if not arm:
            return {"CANCELLED"}
        self.report({"INFO"}, make_rom(arm))
        return {"FINISHED"}


class BT_OT_reset(bpy.types.Operator):
    bl_idname = "biped_test.reset"
    bl_label = "Reset Pose (remove test motion)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm = active_arm(context)
        if not arm:
            return {"CANCELLED"}
        if arm.animation_data:
            arm.animation_data.action = None
        reset_pose(arm)
        return {"FINISHED"}


class BT_OT_ik(bpy.types.Operator):
    bl_idname = "biped_test.ik"
    bl_label = "IK / FK"
    on: bpy.props.BoolProperty()

    def execute(self, context):
        arm = active_arm(context)
        if arm:
            set_ik(arm, self.on)
        return {"FINISHED"}


class BT_PT_panel(bpy.types.Panel):
    bl_label = "Biped Test Rig"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Biped Test"

    def draw(self, context):
        lay = self.layout
        arm = active_arm(context)
        col = lay.column(align=True)
        col.operator("biped_test.build", icon="ARMATURE_DATA")
        if arm and (CTRL_PREFIX + "COM") in arm.data.bones:
            row = col.row(align=True)
            row.operator("biped_test.ik", text="IK (Biped)", depress=arm.get("bt_ik", 1.0) > 0.5).on = True
            row.operator("biped_test.ik", text="FK", depress=arm.get("bt_ik", 1.0) < 0.5).on = False
            col.separator()
            col.operator("biped_test.rom", icon="PLAY")
            col.operator("biped_test.reset", icon="LOOP_BACK")
            box = lay.box()
            box.label(text="Yellow square: COM (move whole body)")
            box.label(text="Cubes: IK hands / feet, diamonds: elbow / knee")
            box.label(text="Circles: rotate (spine, head, fingers, skirt, hair)")
            for c in arm.data.collections:
                if c.name.startswith("BT "):
                    box.prop(c, "is_visible", text=c.name[3:])


classes = (BT_OT_build, BT_OT_rom, BT_OT_reset, BT_OT_ik, BT_PT_panel)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
