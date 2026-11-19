bl_info = {
    "name": "Max Bridge (3ds Max 2014)",
    "author": "Claude for 정현",
    "version": (1, 5, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > Max Bridge",
    "description": "Round-trip meshes, skins and animation between 3ds Max 2014 and Blender via MaxBridge.ms",
    "category": "Import-Export",
}

import bpy, os, socket, json, time

HOST = "127.0.0.1"
# Default 9877 = the user's Max (sidebar buttons). Claude Max runs on 9878-9899:
# Claude passes send(code, port=9878) or sets max_bridge.PORT. Env MAXBRIDGE_PORT overrides the default.
# 2.7: a Blender without a window (blender -b) is only used by Claude tests -> default 9878 there, never the user's 9877
PORT = int(os.environ.get("MAXBRIDGE_PORT") or ("9878" if bpy.app.background else "9877"))
DEFAULT_EXCHANGE = r"C:\claude\max_blender\exchange"


# ---------------------------------------------------------------- core API (also used by Claude)
def exchange_dir():
    try:
        d = bpy.context.preferences.addons[__name__].preferences.exchange_dir
    except Exception:
        d = ""
    d = d or DEFAULT_EXCHANGE
    os.makedirs(d, exist_ok=True)
    return d


def send(code, timeout=300, port=None):
    """Send MAXScript text to 3ds Max, return the result string. port=None uses PORT."""
    s = socket.create_connection((HOST, port or PORT), timeout=5)
    s.settimeout(timeout)
    try:
        s.sendall(code.encode("utf-8"))
        s.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            b = s.recv(65536)
            if not b:
                break
            chunks.append(b)
    finally:
        s.close()
    return b"".join(chunks).decode("utf-8-sig", errors="replace")


def ms_path(p):
    return '@"' + p.replace('"', "") + '"'


def ping():
    return send('"pong " + MaxBridge.version', timeout=10)


def max_info():
    return json.loads(send("MaxBridge.info()"))


def _new_objects(before):
    return [o for o in bpy.data.objects if o.name not in before]


def _swap_previous(new, collection_name):
    """Re-import: keep exact Max names on the new objects. Older copies are renamed *_이전 and hidden."""
    import re
    rx = re.compile(r"^(.*)\.\d{3}$")
    oldcol = None
    n = 0
    for o in new:
        m = rx.match(o.name)
        if not m:
            continue
        base = m.group(1)
        prev = bpy.data.objects.get(base)
        if prev is None or prev in new:
            continue
        if oldcol is None:
            oldcol = bpy.data.collections.get(collection_name + "_이전") or bpy.data.collections.new(collection_name + "_이전")
            if oldcol.name not in bpy.context.scene.collection.children:
                bpy.context.scene.collection.children.link(oldcol)
        k = 1
        nm = base + "_이전"
        while bpy.data.objects.get(nm):
            k += 1
            nm = "%s_이전%d" % (base, k)
        prev.name = nm
        for c in list(prev.users_collection):
            c.objects.unlink(prev)
        oldcol.objects.link(prev)
        prev.hide_set(True)
        o.name = base
        if o.data is not None and hasattr(o.data, "name"):
            o.data.name = base
        n += 1
    if oldcol is not None:
        try:
            bpy.context.view_layer.layer_collection.children[oldcol.name].hide_viewport = True
        except Exception:
            pass
    return n


def from_max(selected_only=True, anim=True, collection_name="FromMax", filename="max_to_blender.fbx", clean=True, show_helpers=False):
    path = os.path.join(exchange_dir(), filename)
    if os.path.exists(path):
        os.remove(path)
    res = send("MaxBridge.exportFBX %s selOnly:%s anim:%s" % (ms_path(path), str(selected_only).lower(), str(anim).lower()))
    if res.startswith("ERROR") or not os.path.exists(path):
        raise RuntimeError("Max export failed: " + res)
    # match Blender's timeline to Max (frame range + fps) so animation round-trips 1:1
    try:
        info = max_info()
        sc = bpy.context.scene
        sc.render.fps = int(info["fps"])
        sc.render.fps_base = 1.0
        sc.frame_start = int(info["frame_start"])
        sc.frame_end = int(info["frame_end"])
    except Exception:
        pass
    before = set(bpy.data.objects.keys())
    if bpy.context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
    if bpy.context.mode == "OBJECT":
        bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.import_scene.fbx(
        filepath=path,
        use_custom_normals=True,
        use_image_search=True,
        use_anim=anim,
        anim_offset=0.0,
        ignore_leaf_bones=False,
        force_connect_children=False,
        automatic_bone_orientation=False,
        primary_bone_axis="Y",
        secondary_bone_axis="X",
    )
    new = _new_objects(before)
    col = bpy.data.collections.get(collection_name) or bpy.data.collections.new(collection_name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    replaced = _swap_previous(new, collection_name)
    cleaned = 0
    if clean:
        bpy.context.view_layer.update()
        for o in new:
            if o.type == "ARMATURE":
                try:
                    cv_apply(o.name, hide_helpers=not show_helpers); cleaned += 1
                except Exception as e:
                    print("clean view failed:", o.name, e)
    return "%s | imported %d objects into collection '%s'%s%s" % (res, len(new), col.name, (" | clean view: %d armature" % cleaned) if cleaned else "", (" | 이전 것 %d개는 '%s_이전'에 숨김" % (replaced, collection_name)) if replaced else "")


def to_max(selected_only=True, anim=True, layer_name="FromBlender", filename="blender_to_max.fbx"):
    path = os.path.join(exchange_dir(), filename)
    if os.path.exists(path):
        os.remove(path)
    if selected_only and not bpy.context.selected_objects:
        raise RuntimeError("Nothing selected in Blender")
    bpy.ops.export_scene.fbx(
        filepath=path,
        use_selection=selected_only,
        object_types={"MESH", "ARMATURE", "EMPTY"},
        apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_UNITS",
        axis_forward="Y",
        axis_up="Z",
        use_mesh_modifiers=True,
        mesh_smooth_type="FACE",
        use_tspace=False,
        add_leaf_bones=False,
        primary_bone_axis="Y",
        secondary_bone_axis="X",
        bake_anim=anim,
        bake_anim_use_all_actions=False,
        bake_anim_use_nla_strips=False,
        bake_anim_simplify_factor=0.0,
        bake_anim_force_startend_keying=False,
        path_mode="ABSOLUTE",
        embed_textures=False,
    )
    return send("MaxBridge.importFBX %s layerName:\"%s\"" % (ms_path(path), layer_name))


# ---------------------------------------------------------------- UI
class MAXBRIDGE_Prefs(bpy.types.AddonPreferences):
    bl_idname = __name__
    exchange_dir: bpy.props.StringProperty(name="Exchange folder", subtype="DIR_PATH", default=DEFAULT_EXCHANGE)

    def draw(self, context):
        self.layout.prop(self, "exchange_dir")



# ---------------------------------------------------------------------------
# Clean bone view: Max에서 온 Bip 아마추어를 '보기만' 깔끔하게 (데이터·애니는 그대로)
# ---------------------------------------------------------------------------
from mathutils import Vector


WGT = "WGT_CleanBone"

def cv_widget():
    ob = bpy.data.objects.get(WGT)
    if ob: return ob
    r = 0.08
    verts = [(0,0,0),(0,1,0),( r,0.12,0),(0,0.12, r),(-r,0.12,0),(0,0.12,-r)]
    edges = [(0,2),(0,3),(0,4),(0,5),(1,2),(1,3),(1,4),(1,5),(2,3),(3,4),(4,5),(5,2)]
    me = bpy.data.meshes.new(WGT); me.from_pydata(verts, edges, [])
    ob = bpy.data.objects.new(WGT, me)
    ob.use_fake_user = True
    return ob

def cv_is_nub(n): return "nub" in n.lower() or n.lower() == "root"

import re as _re
_UE_BODY = _re.compile(r"^(pelvis|spine_0\d|neck_0\d|head|clavicle_[lr]|upperarm_[lr]|lowerarm_[lr]|hand_[lr]|"
                       r"(thumb|index|middle|ring|pinky)_(metacarpal|0\d)_[lr]|(index|middle|ring|pinky)_metacarpal_[lr]|"
                       r"thigh_[lr]|calf_[lr]|foot_[lr]|ball_[lr])$")
_CC_BODY = _re.compile(r"^cc_base_(hip|pelvis|waist|spine0\d|necktwist0\d|head|[lr]_(clavicle|upperarm|forearm|hand|thigh|calf|foot|toebase)|"
                       r"[lr]_(thumb|index|mid|ring|pinky)\d)$")
def cv_is_body(n):
    l = n.lower()
    return n.startswith("Bip0") or bool(_UE_BODY.match(l)) or bool(_CC_BODY.match(l))

_FACE = _re.compile(r"^bone_(jaw|chin|lip|eye|brow|cheek|nose|sneer|tongue|teeth|mouth|face)", _re.I)
def cv_is_face(n): return bool(_FACE.match(n))

def cv_side(n):
    l = " " + n.lower().replace(".", "_") + " "
    if " l " in l or l.rstrip().endswith("_l") or "_l_" in l: return "L"
    if " r " in l or l.rstrip().endswith("_r") or "_r_" in l: return "R"
    return ""

def cv_pick_child(b):
    # Nub은 애니 때 엉뚱한 곳에 남는 경우가 있어 목표로 쓰지 않음 → 끝마디는 앞 마디 방향으로 연장
    kids = [c for c in b.children if not cv_is_nub(c.name)]
    if not kids: return None
    if len(kids) == 1: return kids[0]
    lname = b.name.lower()
    ue = {"pelvis":"spine_01", "spine_05":"neck_01", "neck_01":"neck_02", "neck_02":"head",
          "hand_l":"middle_metacarpal_l", "hand_r":"middle_metacarpal_r", "foot_l":"ball_l", "foot_r":"ball_r",
          "cc_base_hip":"cc_base_waist", "cc_base_spine02":"cc_base_necktwist01"}
    if lname == "head" or lname.endswith(" head"): return None   # 머리는 위로 짧게 (얼굴 본 쪽으로 늘이지 않음, Bip01 Head 포함)
    if lname in ue:
        for c in kids:
            if c.name.lower() == ue[lname]: return c
    body_kids = [c for c in kids if cv_is_body(c.name)]
    if cv_is_body(b.name) and body_kids: kids = body_kids
    if len(kids) == 1: return kids[0]
    pref = {"Pelvis":"Spine", "Spine2":"Neck", "Neck":"Head", "Hand":"Finger2", "Foot":"Toe0"}
    for k, v in pref.items():
        if b.name.endswith(k):
            for c in kids:
                if c.name.endswith(v) or (v in c.name and c.name.split()[-1].startswith(v)): return c
    # 부모→나 방향으로 가장 곧게 이어지는 자식
    d = (b.head_local - b.parent.head_local) if b.parent else Vector((0,0,1))
    if d.length < 1e-6: d = Vector((0,0,1))
    d.normalize()
    best = max(kids, key=lambda c: (c.head_local - b.head_local).normalized().dot(d) if (c.head_local - b.head_local).length > 1e-6 else -9)
    return best

def cv_apply(arm_name="Bip01", hide_helpers=True, use_pose=True):
    """use_pose=True: 지금 프레임의 자세 기준으로 모양을 잡음(바인드 자세와 애니 자세가 다른 Biped 대응)."""
    arm = bpy.data.objects[arm_name]; a = arm.data
    P = arm.pose.bones
    H = (lambda b: P[b.name].head.copy()) if use_pose else (lambda b: b.head_local.copy())
    M = (lambda b: P[b.name].matrix.copy()) if use_pose else (lambda b: b.matrix_local.copy())
    wgt = cv_widget()
    deform = set()
    for m in bpy.data.objects:
        if m.type == 'MESH' and any(md.type == 'ARMATURE' and md.object == arm for md in m.modifiers):
            deform |= {vg.name for vg in m.vertex_groups}
    def coll(name):
        return a.collections.get(name) or a.collections.new(name)
    cBody, cDef, cHelp, cNub = coll("Body (Bip)"), coll("Skin Bones"), coll("Helpers"), coll("Nubs")
    cFace = None
    lengths = {}
    for b in a.bones:
        c = cv_pick_child(b)
        if cv_is_face(b.name):
            # 얼굴 본: Max 본 방향으로 짧게. FBX 로 온 본은 Max 방향 = 본 X 축(꼬리는 기본 길이),
            # Max 에서 꼬리를 받아 온 눈 본(눈알·눈꺼풀, 길이 5 미만)은 본 방향(Y) = Max 방향
            R3 = M(b).to_3x3().normalized()
            if "eye" in b.name.lower() and b.length < 5.0:
                tgt = H(b) + R3.col[1] * b.length
            else:
                tgt = H(b) + R3.col[0] * (min(b.length, 6.0) if b.children else 1.0)
        elif c is not None and (H(c) - H(b)).length > 1e-5:
            tgt = H(c)
        else:
            d = (H(b) - H(b.parent)) if b.parent else Vector((0,0,1))
            L = lengths.get(b.parent.name, d.length) * 0.8 if b.parent else 1.0
            if b.name.lower() == "head":        # 머리: 목 방향으로 목 길이 1.5배 (Bip01 Head 는 0.8배 = 얼굴 관통 안 함)
                L = lengths.get(b.parent.name, L) * 1.5 if b.parent else L
            elif not cv_is_body(b.name):   # 보조 본 끝마디는 짧게
                L = min(L, 5.0)
            if "Toe" in b.name:   # 발가락 끝은 바닥과 평행하게
                d = Vector((d.x, d.y, 0)) if Vector((d.x, d.y, 0)).length > 1e-6 else d
                L = min(L, 6.0)
            tgt = H(b) + (d.normalized() if d.length > 1e-6 else Vector((0,0,1))) * max(L, 0.01)
        loc = M(b).inverted() @ tgt          # 본 기준 좌표 (본 머리 = 원점)
        L = loc.length
        lengths[b.name] = L
        pb = arm.pose.bones[b.name]
        pb.custom_shape = wgt
        pb.use_custom_shape_bone_size = False
        if L > 1e-6:
            q = Vector((0,1,0)).rotation_difference(loc.normalized())
            pb.custom_shape_rotation_euler = q.to_euler()
        pb.custom_shape_scale_xyz = (L, L, L)
        pb.custom_shape_translation = (0,0,0)
        # 컬렉션 / 색
        for cc in list(b.collections): cc.unassign(b)
        n = b.name
        if cv_is_nub(n): cNub.assign(b)
        elif cv_is_body(n): cBody.assign(b)
        elif cv_is_face(n):
            cFace = cFace or coll("Face"); cFace.assign(b)   # 얼굴 본은 웨이트 전에도 보이게
        elif n in deform: cDef.assign(b)
        else: cHelp.assign(b)
        sd = cv_side(n)
        b.color.palette = 'THEME04' if sd == "L" else ('THEME01' if sd == "R" else 'THEME09')
    cNub.is_visible = False
    cHelp.is_visible = not hide_helpers
    if cFace: cFace.is_visible = True
    a.display_type = 'OCTAHEDRAL'
    arm.show_in_front = True
    return {"bones": len(a.bones), "body": len(cBody.bones), "skin": len(cDef.bones), "helpers": len(cHelp.bones), "nubs": len(cNub.bones)}

def cv_remove(arm_name="Bip01"):
    arm = bpy.data.objects[arm_name]
    for pb in arm.pose.bones:
        pb.custom_shape = None
        pb.custom_shape_rotation_euler = (0,0,0); pb.custom_shape_scale_xyz = (1,1,1)
        pb.use_custom_shape_bone_size = True
        pb.bone.color.palette = 'DEFAULT'
    for c in list(arm.data.collections):
        if c.name in ("Body (Bip)","Skin Bones","Helpers","Nubs","Face"): arm.data.collections.remove(c)


def cv_targets(context, only_selected=False):
    obs = context.selected_objects if only_selected else context.scene.objects
    return [o for o in obs if o.type == "ARMATURE"]


class MAXBRIDGE_Props(bpy.types.PropertyGroup):
    selected_only: bpy.props.BoolProperty(name="Selected only", default=True)
    anim: bpy.props.BoolProperty(name="Animation", default=True)
    clean_view: bpy.props.BoolProperty(name="Clean bone view", default=True,
        description="가져온 아마추어를 보기 좋게 표시 (본 데이터·애니는 그대로)")
    show_helpers: bpy.props.BoolProperty(name="Show helpers", default=False,
        description="스킨에 안 쓰이는 헬퍼 본도 보이기")
    status: bpy.props.StringProperty(default="")
    last_run: bpy.props.StringProperty(default="")
    accurig_fbx: bpy.props.StringProperty(name="Rigged FBX", subtype="FILE_PATH", default="",
        description="AccuRIG 등 자동 리깅 결과 FBX (원본과 정점 수·순서 같아야 함)")


class MAXBRIDGE_OT_ping(bpy.types.Operator):
    bl_idname = "maxbridge.ping"
    bl_label = "Check Max connection"

    def execute(self, context):
        try:
            context.scene.maxbridge.status = ping()
        except Exception as e:
            context.scene.maxbridge.status = "Max not reachable: %s" % e
            self.report({"WARNING"}, context.scene.maxbridge.status)
            return {"CANCELLED"}
        self.report({"INFO"}, context.scene.maxbridge.status)
        return {"FINISHED"}


class MAXBRIDGE_OT_from_max(bpy.types.Operator):
    bl_idname = "maxbridge.from_max"
    bl_label = "Max -> Blender"

    def execute(self, context):
        p = context.scene.maxbridge
        try:
            p.status = from_max(p.selected_only, p.anim, clean=p.clean_view, show_helpers=p.show_helpers)
        except Exception as e:
            p.status = str(e)
            self.report({"ERROR"}, p.status)
            return {"CANCELLED"}
        self.report({"INFO"}, p.status)
        return {"FINISHED"}


class MAXBRIDGE_OT_to_max(bpy.types.Operator):
    bl_idname = "maxbridge.to_max"
    bl_label = "Blender -> Max"

    def execute(self, context):
        p = context.scene.maxbridge
        try:
            p.status = to_max(p.selected_only, p.anim)
        except Exception as e:
            p.status = str(e)
            self.report({"ERROR"}, p.status)
            return {"CANCELLED"}
        self.report({"INFO"}, p.status)
        return {"FINISHED"}


class MAXBRIDGE_OT_check(bpy.types.Operator):
    bl_idname = "maxbridge.check_rig"
    bl_label = "Check Rig (standard)"
    bl_description = "Run the skeleton standard check on the file open in 3ds Max"

    def execute(self, context):
        p = context.scene.maxbridge
        try:
            r = send("MaxBridge.checkRig()", timeout=600)
        except Exception as e:
            p.status = "Max not reachable: %s" % e
            return {"CANCELLED"}
        lines = r.split("\n")
        errs = [l for l in lines if l.startswith(("ERROR", "WARN"))]
        p.status = lines[0] + (" | " + " | ".join(l.replace("\t", " ") for l in errs[:6]) if errs else "")
        self.report({"INFO"}, lines[0])
        return {"FINISHED"}


class MAXBRIDGE_OT_standardize(bpy.types.Operator):
    bl_idname = "maxbridge.standardize"
    bl_label = "Standardize Character (1 click)"
    bl_description = ("Make a standard copy of the character open in 3ds Max: follower bones for problem skin bones, "
                      "original weights kept, verified in Max and Blender. The original file is never changed")

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event, title="표준화 실행",
                                                     message="원본은 그대로 두고 표준형 사본을 만들어요. 몇 분 걸리고 그동안 블렌더가 멈춘 것처럼 보일 수 있어요.")

    def execute(self, context):
        p = context.scene.maxbridge
        try:
            import importlib, standardize
            importlib.reload(standardize)
        except Exception as e:
            p.status = "standardize module missing: %s" % e
            return {"CANCELLED"}
        run = standardize.standardize()
        d = run.data
        if d.get("ok"):
            worst = max(d["blender_rounds"][-1].values()) if d.get("blender_rounds") else -1
            p.status = "완료 | %s | 검사 전: %s | 검사 후: %s | 블렌더 오차 최대 %.3f인치 | 기록: %s" % (
                os.path.basename(d["standard"]), d.get("check_before", "").replace("RIG CHECK", "").strip(),
                d.get("check_after", "").replace("RIG CHECK", "").strip(), worst, d["run_dir"])
            self.report({"INFO"}, "Standardize done: " + d["standard"])
        else:
            p.status = "실패 | %s | 기록: %s" % (d.get("error"), d.get("run_dir", "-"))
            self.report({"ERROR"}, d.get("error", "failed"))
        context.scene.maxbridge.last_run = d.get("run_dir", "")
        return {"FINISHED"}


class MAXBRIDGE_OT_helpers(bpy.types.Operator):
    bl_idname = "maxbridge.add_helpers"
    bl_label = "Add Standard Helpers (knee/elbow/shoulder)"
    bl_description = ("Build the company-standard volume helpers and thigh/calf bones on the fitted Biped open in 3ds Max, "
                      "scaled to its proportions. Saved as a copy in max_blender\\standardized; the original is not changed")

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event, title="표준 헬퍼 생성",
                                                     message="Max에 열린 캐릭터(Bip 맞춘 상태, 저장된 파일)에 무릎·팔꿈치·어깨 헬퍼와 허벅지·종아리 보조본을 만들고 사본으로 저장해요.")

    def execute(self, context):
        p = context.scene.maxbridge
        try:
            import importlib, helper_template
            importlib.reload(helper_template)
            info = max_info()
            f = info.get("file", "")
            if not f or send("getSaveRequired()").strip() == "true":
                p.status = "먼저 Max 파일을 저장해 주세요"
                return {"CANCELLED"}
            name = os.path.splitext(os.path.basename(f))[0]
            out = os.path.join(r"C:\claude\max_blender\standardized", name + "_helpers.max")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            rep = helper_template.apply(save_as=out)
            chk = send("MaxBridge.checkRig()", timeout=600).split("\n")[0]
            p.status = "완료 | 헬퍼 %d개 + 보조본 %d개 | %s | 저장: %s" % (len(rep["dev"]), len(rep["followers"]), chk.replace("RIG CHECK", "").strip(), out)
        except Exception as e:
            p.status = "실패 | %s" % str(e)[:300]
            self.report({"ERROR"}, p.status)
            return {"CANCELLED"}
        self.report({"INFO"}, p.status)
        return {"FINISHED"}


class MAXBRIDGE_OT_open_folder(bpy.types.Operator):
    bl_idname = "maxbridge.open_folder"
    bl_label = "Open last report"

    def execute(self, context):
        f = context.scene.maxbridge.last_run or r"C:\claude\max_blender\standardized"
        if os.path.isdir(f):
            os.startfile(f)
        return {"FINISHED"}


class MAXBRIDGE_OT_clean_view(bpy.types.Operator):
    bl_idname = "maxbridge.clean_view"
    bl_label = "Clean Bone View"
    bl_description = "선택한(없으면 전체) 아마추어를 보기 좋게 표시. 지금 프레임 자세 기준. 본 데이터·애니는 그대로"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        p = context.scene.maxbridge
        arms = cv_targets(context, True) or cv_targets(context, False)
        if not arms:
            self.report({"WARNING"}, "아마추어가 없어요"); return {"CANCELLED"}
        if context.mode != "OBJECT" and context.mode != "POSE":
            bpy.ops.object.mode_set(mode="OBJECT")
        context.view_layer.update()
        out = []
        for a in arms:
            r = cv_apply(a.name, hide_helpers=not p.show_helpers)
            out.append("%s: body %d / skin %d / helpers %d / nubs %d" % (a.name, r["body"], r["skin"], r["helpers"], r["nubs"]))
        p.status = " | ".join(out)
        self.report({"INFO"}, p.status)
        return {"FINISHED"}


class MAXBRIDGE_OT_clean_view_reset(bpy.types.Operator):
    bl_idname = "maxbridge.clean_view_reset"
    bl_label = "Reset Bone View"
    bl_description = "Clean Bone View를 지우고 원래 본 표시로"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arms = cv_targets(context, True) or cv_targets(context, False)
        for a in arms:
            cv_remove(a.name)
        context.scene.maxbridge.status = "reset view: %d armature" % len(arms)
        return {"FINISHED"}


class MAXBRIDGE_OT_accurig_prep(bpy.types.Operator):
    bl_idname = "maxbridge.accurig_prep"
    bl_label = "AccuRIG 정리 → Max용 FBX"
    bl_description = ("Max에 열린 원본 모델 기준으로 리깅 FBX를 정리: 원래 모델링 자세 복원, 정점당 4본, "
                      "셰이프키·ik 본 삭제, 1단위=1인치. 결과는 <이름>_origpose.fbx")

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event, title="AccuRIG 정리",
            message="Max에 원본 모델(스킨 전 메쉬)이 열려 있어야 해요. 20~40초 걸리고 그동안 블렌더가 멈춘 것처럼 보여요.")

    def execute(self, context):
        p = context.scene.maxbridge
        path = bpy.path.abspath(p.accurig_fbx)
        if not path or not os.path.isfile(path):
            p.status = "리깅 FBX 파일을 먼저 고르세요"
            self.report({"WARNING"}, p.status)
            return {"CANCELLED"}
        try:
            import importlib, accurig_prep
            importlib.reload(accurig_prep)
        except Exception as e:
            p.status = "accurig_prep 모듈 없음: %s" % e
            return {"CANCELLED"}
        r = accurig_prep.run(path)
        if r.get("ok"):
            p.status = "완료 | %s | 자세 복원 오차 최대 %.3f인치 | 원본과 차이 %.5f인치 | 본 %d개 | 다음: Max BipFit '리깅 FBX → 원본 메쉬'" % (
                os.path.basename(r["out"]), r["solve_max"], r["rest_err"], r["bones"])
            self.report({"INFO"}, "AccuRIG 정리 완료: " + r["out"])
            return {"FINISHED"}
        p.status = "실패 | %s" % r.get("error")
        self.report({"ERROR"}, p.status)
        return {"CANCELLED"}


class MAXBRIDGE_PT_panel(bpy.types.Panel):
    bl_label = "Max Bridge (3ds Max 2014)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Max Bridge"

    def draw(self, context):
        p = context.scene.maxbridge
        col = self.layout.column(align=True)
        col.operator("maxbridge.ping", icon="LINKED")
        col.separator()
        col.prop(p, "selected_only")
        col.prop(p, "anim")
        col.separator()
        col.prop(p, "clean_view")
        col.operator("maxbridge.from_max", icon="IMPORT")
        col.operator("maxbridge.to_max", icon="EXPORT")
        col.separator()
        col.label(text="Bone view")
        row = col.row(align=True)
        row.operator("maxbridge.clean_view", icon="BONE_DATA")
        row.operator("maxbridge.clean_view_reset", text="", icon="LOOP_BACK")
        col.prop(p, "show_helpers")
        col.separator()
        col.label(text="Skeleton standard")
        col.operator("maxbridge.check_rig", icon="CHECKMARK")
        col.operator("maxbridge.standardize", icon="MODIFIER")
        col.operator("maxbridge.add_helpers", icon="BONE_DATA")
        col.operator("maxbridge.open_folder", icon="FILE_FOLDER")
        col.separator()
        col.label(text="Auto rig (AccuRIG) → Max")
        col.prop(p, "accurig_fbx", text="")
        col.operator("maxbridge.accurig_prep", icon="ARMATURE_DATA")
        if p.status:
            box = self.layout.box()
            for line in p.status.split(" | "):
                box.label(text=line[:90])


classes = (
    MAXBRIDGE_OT_clean_view,
    MAXBRIDGE_OT_clean_view_reset,MAXBRIDGE_Prefs, MAXBRIDGE_Props, MAXBRIDGE_OT_ping, MAXBRIDGE_OT_from_max, MAXBRIDGE_OT_to_max,
           MAXBRIDGE_OT_check, MAXBRIDGE_OT_standardize, MAXBRIDGE_OT_helpers, MAXBRIDGE_OT_open_folder, MAXBRIDGE_OT_accurig_prep, MAXBRIDGE_PT_panel)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.maxbridge = bpy.props.PointerProperty(type=MAXBRIDGE_Props)


def unregister():
    del bpy.types.Scene.maxbridge
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
