"""rig_weights.py - Blender side of the Max Biped weight pipeline (used by Claude and the Max Bridge panel).

1. apply_max_segments(arm, segments.txt, unit)  : rebuild every influence bone from 3ds Max's real geometry
   (fixes leaf/helper bones that FBX imports with random length/direction, and zero-length bones)
2. autoweight(mesh, arm, allowed_bones)          : heat weights limited to the bones the mesh may use,
   with fallbacks: voxel proxy (hair cards, open pieces) -> nearest weighted vertex
3. export_weights(mesh, path)                     : '#BONES' header + 'index:weight' per vertex (for MaxBridge.applyWeights)
"""
import bpy, math
from mathutils import Vector
from mathutils.kdtree import KDTree

UNIT_TO_M = {"in": 0.0254, "cm": 0.01, "mm": 0.001, "m": 1.0, "ft": 0.3048}


def _set_mode(obj, mode):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if obj.mode != mode:
        bpy.ops.object.mode_set(mode=mode)


def read_segments(path):
    out = {}
    for line in open(path, encoding="utf-8-sig").read().split("\n"):
        if not line.strip():
            continue
        r = line.split("\t")
        out[r[0]] = dict(cls=r[1], kind=r[2], a=Vector(map(float, r[3].split())), b=Vector(map(float, r[4].split())),
                         parent=r[5], det=float(r[6]))
    return out


def apply_max_segments(arm, seg_path, unit="in", min_len_ratio=0.15):
    segs = read_segments(seg_path)
    s = UNIT_TO_M[unit]
    inv = arm.matrix_world.inverted()
    _set_mode(arm, "EDIT")
    eb = arm.data.edit_bones
    for b in eb:
        b.use_connect = False
    log = {"set": 0, "point_fixed": 0, "created": 0, "zero_fixed": 0}
    for name, g in segs.items():
        b = eb.get(name)
        if b is None:
            b = eb.new(name)
            par = eb.get(g["parent"])
            b.parent = par
            log["created"] += 1
        head = inv @ (g["a"] * s)
        tail = inv @ (g["b"] * s)
        if (tail - head).length < 1e-4:  # point helper: short bone along parent direction
            par = b.parent
            d = (par.tail - par.head).normalized() if par and par.length > 1e-6 else Vector((0, 0, 1))
            L = (par.length if par else 1.0) * min_len_ratio
            tail = head + d * max(L, 1e-3)
            log["point_fixed"] += 1
        b.head, b.tail = head, tail
        log["set"] += 1
    # any remaining zero/near-zero bone (not an influence) gets a sane length too
    for b in eb:
        if b.length < 1e-4:
            par = b.parent
            d = (par.tail - par.head).normalized() if par and par.length > 1e-6 else Vector((0, 0, 1))
            b.tail = b.head + d * ((par.length if par else 1.0) * min_len_ratio)
            log["zero_fixed"] += 1
    bpy.ops.object.mode_set(mode="OBJECT")
    return log


def _unweighted(me):
    return [v.index for v in me.data.vertices if not any(g.weight > 0 for g in v.groups)]


def _finish(me, limit=4):
    _set_mode(me, "OBJECT")
    bpy.ops.object.vertex_group_clean(group_select_mode="ALL", limit=0.001)
    bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=limit)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)


def _heat(obj, arm):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO", keep_transform=True)


def _proxy_fill(me, arm, targets, div=80):
    px = me.copy()
    px.data = me.data.copy()
    px.name = me.name + "_PROXY"
    bpy.context.scene.collection.objects.link(px)
    px.vertex_groups.clear()
    px.parent = None
    px.matrix_world = me.matrix_world.copy()
    for m in list(px.modifiers):
        px.modifiers.remove(m)
    r = px.modifiers.new("remesh", "REMESH")
    r.mode = "VOXEL"
    r.voxel_size = max(me.dimensions) / div / max(px.scale)
    _set_mode(px, "OBJECT")
    bpy.ops.object.modifier_apply(modifier="remesh")
    _heat(px, arm)
    mask = me.vertex_groups.new(name="_fill")
    mask.add(targets, 1.0, "REPLACE")
    for g in px.vertex_groups:
        if g.name not in me.vertex_groups:
            me.vertex_groups.new(name=g.name)
    dt = me.modifiers.new("wt", "DATA_TRANSFER")
    dt.object = px
    dt.use_vert_data = True
    dt.data_types_verts = {"VGROUP_WEIGHTS"}
    dt.vert_mapping = "POLYINTERP_NEAREST"
    dt.layers_vgroup_select_src = "ALL"
    dt.layers_vgroup_select_dst = "NAME"
    dt.vertex_group = "_fill"
    dt.mix_mode = "REPLACE"
    _set_mode(me, "OBJECT")
    bpy.ops.object.modifier_move_to_index(modifier="wt", index=0)
    bpy.ops.object.modifier_apply(modifier="wt")
    me.vertex_groups.remove(me.vertex_groups["_fill"])
    bpy.data.objects.remove(px)


def _nearest_fill(me):
    vs = me.data.vertices
    w = [v for v in vs if any(g.weight > 0 for g in v.groups)]
    u = [v for v in vs if not any(g.weight > 0 for g in v.groups)]
    if not w or not u:
        return
    kd = KDTree(len(w))
    for i, v in enumerate(w):
        kd.insert(v.co, i)
    kd.balance()
    for v in u:
        _, i, _ = kd.find(v.co)
        for g in w[i].groups:
            if g.weight > 0:
                me.vertex_groups[g.group].add([v.index], g.weight, "REPLACE")


def autoweight(me, arm, allowed, limit=4):
    allowed = set(allowed)
    keep = {b.name: b.use_deform for b in arm.data.bones}
    for b in arm.data.bones:
        b.use_deform = b.name in allowed
    try:
        me.vertex_groups.clear()
        for m in list(me.modifiers):
            if m.type == "ARMATURE":
                me.modifiers.remove(m)
        me.parent = None
        _heat(me, arm)
        steps = ["heat: %d unweighted" % len(_unweighted(me))]
        for div in (60, 45, 35):  # coarser proxies until heat weighting finds a solution
            t = _unweighted(me)
            if not t:
                break
            _proxy_fill(me, arm, t, div=div)
            steps.append("proxy/%d: %d unweighted" % (div, len(_unweighted(me))))
        if _unweighted(me):
            _nearest_fill(me)
            steps.append("nearest: %d unweighted" % len(_unweighted(me)))
        _finish(me, limit)
    finally:
        for b in arm.data.bones:
            b.use_deform = keep.get(b.name, True)
    return " | ".join(steps)


def export_weights(me, path):
    used = sorted({g.group for v in me.data.vertices for g in v.groups if g.weight > 0})
    names = [me.vertex_groups[i].name for i in used]
    remap = {gi: k for k, gi in enumerate(used)}
    with open(path, "w", encoding="utf-8") as f:
        f.write("#BONES\t" + "\t".join(names) + "\n")
        for v in me.data.vertices:
            f.write(" ".join("%d:%.5f" % (remap[g.group], g.weight) for g in v.groups if g.weight > 0) + "\n")
    return len(names)
