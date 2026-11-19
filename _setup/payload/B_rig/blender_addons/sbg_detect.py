# SecBoneGen 관절 자동 감지 (Blender 애드온)
# Max 에 열린 모델을 가져와 Auto-Rig Pro AI 로 관절을 찾고, 팀 정답 리그 규칙으로
# 노란 지정점(sbg_*)을 계산해서 Max 에 놓는다. Biped 생성은 Max 의 MTOS_RigTools 1.5 [1.5 Biped 자동 생성].
# 필요: max_bridge 애드온(같은 PC), Auto-Rig Pro (Smart AI 파일 포함)
bl_info = {
    "name": "SecBoneGen 관절 자동 감지",
    "author": "ani 팀",
    "version": (1, 3, 0),
    "blender": (4, 0, 0),
    "location": "3D 뷰 > N 패널 > Max Bridge",
    "description": "Max 모델 → ARP 관절 감지 → 지정점(sbg_*)을 Max 에 놓기 (Rig Tools 2. Biped 자동 생성용)",
    "category": "Rigging",
}

import bpy, os, json, time
import numpy as np

K = 0.0254          # Max 단위 → Blender (FBX 가져오기 배율)
S = 1.0 / K

# ---------------------------------------------------------------------------
# 규칙 (정답 리그: Bacha2_t_bip · pc_set_theia_r11 · meira_t_bip · behemoth_t_bip · leviathan_t_bip,
#       eunha 허벅지 수정). 값은 키 h(ARP 발목~목 높이) 비율. 2026-10-28
# ---------------------------------------------------------------------------
RULES = {
    "Bip01 L Thigh": [-0.014034, -0.005397, -0.028939],
    "Bip01 L Calf": [-0.001462, 0.014883, -0.001750],
    "Bip01 L Foot": [0.003877, 0.005111, 0.002631],
    "Bip01 L UpperArm": [-0.000575, -0.010250, -0.005249],
    "Bip01 Neck": [0.0, -0.004516, 0.024696],
    "Bip01 L Forearm": [-0.005171, -0.010560, 0.013202],
    "Bip01 L Hand": [0.006369, -0.002095, -0.007973],
    "head_z": 0.012204, "head_y": -0.013264,
    "spine_start": 0.277869, "spine_y": -0.012483,
    "clav": [-0.070424, -0.001352, 0.011559],
    "toe": [0.005687, -0.083954, -0.106588],
    "thigh": {"dz": -0.033905, "ratio": 0.640143, "yfoot": -0.035143},
    "spinewidth": {"W": 10.8306, "thigh_x": 8.36, "shoulder_x": 11.14},
    "headend_dz": 0.016, "toe_frac": 0.72, "elbow_ratio": 0.482, "hand_limit": 0.18, "handend_ratio": 0.42,
}
LMAP = {"sbg_L_Thigh": ("Bip01 L Thigh", "thigh_loc"), "sbg_L_Calf": ("Bip01 L Calf", "knee_loc"),
        "sbg_L_Foot": ("Bip01 L Foot", "foot_loc"), "sbg_L_UpperArm": ("Bip01 L UpperArm", "shoulder_loc"),
        "sbg_L_Forearm": ("Bip01 L Forearm", "elbow_loc"), "sbg_L_Hand": ("Bip01 L Hand", "hand_loc"),
        "sbg_Neck": ("Bip01 Neck", "neck_loc")}
FINGERS = ("thumb", "index", "middle", "ring", "pinky")
COL = "SBG_detect"


def _bridge():
    import max_bridge
    return max_bridge


def _mesh_points(objs):
    out = []
    for o in objs:
        M = np.array(o.matrix_world)
        co = np.array([v.co for v in o.data.vertices])
        if len(co):
            out.append((np.c_[co, np.ones(len(co))] @ M.T)[:, :3] * S)
    return np.vstack(out)


def _mesh_wrist(V, A, h):
    """손끝에서 어깨 쪽으로 가며 팔 단면이 가장 가는 곳(손목)"""
    sho = np.array(A["shoulder_loc"], float); tip = np.array(A["hand_tip_loc"], float)
    ax = sho - tip; ax /= np.linalg.norm(ax)
    rel = V - tip; t = rel @ ax; perp = np.linalg.norm(rel - np.outer(t, ax), axis=1)
    step = 0.005 * h; best = None
    for i in range(int(0.30 * h / step)):
        t0 = i * step
        sel = (t >= t0) & (t < t0 + step) & (perp < 0.12 * h)
        if sel.sum() < 6:
            continue
        pr = perp[sel]; md = np.median(pr); pr = pr[pr < md * 2.5]
        r = float(np.percentile(pr, 90)); tc = t0 + step / 2
        if 0.03 * h <= tc <= 0.22 * h and (best is None or r < best[0]):
            best = (r, tc)
    if best is None:
        return None
    w = tip + ax * best[1]; w[0] = abs(w[0])
    return w


def _seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(ab @ ab, 1e-9), 0, 1)
    return np.linalg.norm(P - (a + np.outer(t, ab)), axis=1)


def _poly_dist(P, ch, ext=0.3):
    d = np.full(len(P), 1e9)
    pts = list(ch) + [ch[-1] + (ch[-1] - ch[-2]) * ext]
    for i in range(len(pts) - 1):
        d = np.minimum(d, _seg_dist(P, pts[i], pts[i + 1]))
    return d


def refine_fingers(V, F):
    """ARP 손가락 점(5×4, +X 쪽)을 메쉬 손가락 중심선에 맞춤.
    - 정점을 가장 가까운 손가락에 배정 → 길이 방향 단면 중심 = 중심선
    - 첫 마디: 단면 중심들로 직선을 맞춰 손바닥 쪽 뿌리까지 연장 (손바닥에서 뻗는 기울기)
    - 엄지: 세 마디를 한 직선으로 (끝쪽 두 마디 기울기에 첫 마디를 맞춤, 첫 마디 길이 유지)"""
    F = np.array(F, float)
    near = V[(V[:, 0] > 0) & (np.linalg.norm(V - F[2, 1], axis=1) < 20)]
    if len(near) < 50:
        return F, ["손 근처 정점이 부족해 손가락 보정을 건너뜀"]
    D = np.stack([_poly_dist(near, F[i]) for i in range(5)], 1)
    own = D.argmin(1); dmin = D.min(1)
    gap = np.median([np.linalg.norm(F[i, 0] - F[i + 1, 0]) for i in range(1, 4)])
    out = F.copy(); notes = []
    for i in range(5):
        ch = F[i]
        P = near[(own == i) & (dmin < gap * (0.9 if i == 0 else 0.75))]
        Lt = sum(np.linalg.norm(ch[k + 1] - ch[k]) for k in range(3))
        a0 = ch[0]; ax = ch[3] - ch[0]; ax /= np.linalg.norm(ax)
        u = np.cross(ax, [0, 0, 1.0])
        if np.linalg.norm(u) < 1e-3:
            u = np.cross(ax, [0, 1.0, 0])
        u /= np.linalg.norm(u); v = np.cross(ax, u)
        t = (P - a0) @ ax; pu = (P - a0) @ u; pv = (P - a0) @ v
        step = Lt / 14; C = []
        for s in np.arange(0.12 * Lt, 1.3 * Lt, step):
            sel = (t >= s) & (t < s + step)
            if sel.sum() < 8:
                continue
            C.append((s + step / 2, (np.percentile(pu[sel], 5) + np.percentile(pu[sel], 95)) / 2,
                      (np.percentile(pv[sel], 5) + np.percentile(pv[sel], 95)) / 2))
        if len(C) < 4:
            notes.append("손가락 %d: 단면 부족, 감지값 그대로" % (i + 1)); continue
        C = np.array(C); tmax = np.percentile(t, 99.5)

        def cl(s):
            return a0 + ax * s + u * np.interp(s, C[:, 0], C[:, 1]) + v * np.interp(s, C[:, 0], C[:, 2])
        so = [(p - a0) @ ax for p in ch]
        sel = C[:, 0] <= so[1] + 0.08 * Lt
        if sel.sum() < 2:
            sel = np.arange(len(C)) < 3
        A_ = np.c_[C[sel, 0], np.ones(sel.sum())]
        ku = np.linalg.lstsq(A_, C[sel, 1], rcond=None)[0]; kv = np.linalg.lstsq(A_, C[sel, 2], rcond=None)[0]
        n1 = a0 + ax * so[0] + u * (ku[0] * so[0] + ku[1]) + v * (kv[0] * so[0] + kv[1])
        out[i] = [n1, cl(so[1]), cl(so[2]), cl(tmax - 0.03 * Lt)]
    # 엄지 직선
    th = out[0]
    c = th[1:].mean(0); _, _, vt = np.linalg.svd(th[1:] - c); dd = vt[0]
    if dd @ (th[3] - th[1]) < 0:
        dd = -dd
    th[0] = th[1] - dd * np.linalg.norm(th[1] - th[0])
    out[0] = th
    return out, notes


def measure_foot(V, ankle, h, toe_frac):
    """발목(+X 쪽) 아래 메쉬로 뒤꿈치·발가락 시작·발끝·너비. 앞 = -Y"""
    a = np.array(ankle, float)
    sel = (V[:, 0] > 0) & (np.abs(V[:, 0] - a[0]) < 0.10 * h) & (V[:, 2] < a[2] * 0.8) & (np.abs(V[:, 1] - a[1]) < 0.25 * h)
    P = V[sel]
    if len(P) < 30:
        return None
    heel = np.percentile(P[:, 1], 99.5); tip = np.percentile(P[:, 1], 0.5)
    Lt = heel - tip
    root = heel - Lt * toe_frac
    band = P[np.abs(P[:, 1] - root) < 0.04 * Lt]
    if len(band) < 6:
        band = P
    x0, x1 = np.percentile(band[:, 0], 2), np.percentile(band[:, 0], 98)
    cx = (x0 + x1) / 2; w = x1 - x0
    tb = P[(P[:, 1] < root) & (P[:, 1] > tip)]
    th = float(np.percentile(tb[:, 2], 98)) if len(tb) >= 6 else 0.2 * Lt
    return dict(heel=[cx, heel, 0.0], toe=[cx, root, 0.0], toe_end=[cx, tip, 0.0], width=[cx + w / 2, root, 0.0],
                toe_top=[cx, (root + tip) / 2, th], Lt=Lt, w=w)


def compute_points(A, V):
    """ARP 마커(Max 좌표) → 지정점. 반환: pts, fingers(5×4 또는 None), toe, flags, notes"""
    R = RULES
    h = A["neck_loc"][2] - A["foot_loc"][2]
    P = {}
    for k, (bn, mk) in LMAP.items():
        a = np.array(A[mk], float)
        a[0] = abs(a[0]) if k.startswith("sbg_L_") else 0.0
        P[k] = a + np.array(R[bn]) * h
        if not k.startswith("sbg_L_"):
            P[k][0] = 0.0
    # 허벅지: (ARP 기준 + 키 비율 기준) 평균, 앞뒤는 발 기준
    th = P["sbg_L_Thigh"]; T = R["thigh"]
    th[2] = ((A["thigh_loc"][2] + T["dz"] * h) + (A["foot_loc"][2] + T["ratio"] * h)) / 2
    th[1] = A["foot_loc"][1] + T["yfoot"] * h
    head = np.array([0.0, A["neck_loc"][1] + R["head_y"] * h, A["chin_loc"][2] + R["head_z"] * h])
    P["sbg_Head"] = head; P["sbg_NeckEnd"] = head.copy()
    P["sbg_HeadEnd"] = np.array([0.0, head[1], A["head_tip_loc"][2] + R["headend_dz"] * h])
    nk = P["sbg_Neck"]
    sz = th[2] + R["spine_start"] * (nk[2] - th[2]); sy = A["root_loc"][1] + R["spine_y"] * h
    P["sbg_Spine"] = np.array([0.0, sy, sz])
    W = R["spinewidth"]
    w = (abs(A["thigh_loc"][0]) * W["W"] / W["thigh_x"] + abs(A["shoulder_loc"][0]) * W["W"] / W["shoulder_x"]) / 2
    P["sbg_SpineWidth"] = np.array([w, sy, sz])
    P["sbg_L_Clavicle"] = P["sbg_L_UpperArm"] + np.array(R["clav"]) * h
    toe = P["sbg_L_Foot"] + np.array(R["toe"]) * h; toe[2] = max(toe[2], 0.0)
    try:
        fm = measure_foot(V, P["sbg_L_Foot"], h, R["toe_frac"])
    except Exception as e:
        print("[SecBoneGen] 발 측정 실패:", e); fm = None
    if fm:
        P["sbg_L_Heel"] = np.array(fm["heel"]); P["sbg_L_ToeEnd"] = np.array(fm["toe_end"])
        P["sbg_L_FootWidth"] = np.array(fm["width"]); P["sbg_L_ToeTop"] = np.array(fm["toe_top"]); toe = np.array(fm["toe"])
    fing = None
    if all(("%s%d_loc" % (n, i)) in A for n in FINGERS for i in range(1, 5)):
        fing = [[[abs(A["%s%d_loc" % (n, i)][0])] + list(A["%s%d_loc" % (n, i)][1:]) for i in range(1, 5)] for n in FINGERS]
        try:
            ff, fn = refine_fingers(V, fing)
            fing = ff.tolist()
        except Exception as e:
            print("[SecBoneGen] 손가락 보정 실패:", e)
        m1 = np.array(fing[2][0], float); m2 = np.array(fing[2][1], float)
        P["sbg_L_HandEnd"] = m1 + (m2 - m1) * R["handend_ratio"]
    else:
        hd = np.array(A["hand_loc"], float); tp = np.array(A["hand_tip_loc"], float); hd[0] = abs(hd[0]); tp[0] = abs(tp[0])
        P["sbg_L_HandEnd"] = hd + (tp - hd) * 0.5
    flags, notes = [], []
    ratio = np.linalg.norm(np.array(A["hand_tip_loc"]) - np.array(A["hand_loc"])) / h
    if ratio > R["hand_limit"]:
        wr = _mesh_wrist(V, A, h)
        if wr is not None:
            up = P["sbg_L_UpperArm"]; tp = np.array(A["hand_tip_loc"], float); tp[0] = abs(tp[0])
            P["sbg_L_Hand"] = wr
            P["sbg_L_Forearm"] = up + (wr - up) * R["elbow_ratio"]
            P["sbg_L_HandEnd"] = wr + (tp - wr) * 0.6
        fing = None
        flags = ["sbg_L_Hand", "sbg_L_Forearm", "sbg_L_HandEnd"]
        notes.append("손목→손끝이 키의 %.0f%% (보통 12~14%%): 소매 등에 가려 손목 감지가 틀린 것으로 보고 메쉬에서 손목을 다시 찾았어요. 손가락은 맞추지 않아요." % (ratio * 100))
    if fing is None and not flags:
        notes.append("손가락 감지가 안 됐어요 (주먹·붙은 손가락 등). 손가락은 Biped 기본 모양이 돼요.")
    return {k: [float(x) for x in v] for k, v in P.items()}, fing, [float(x) for x in toe], flags, notes, h


def points_maxscript(pts, fing, toe, flags, h):
    sz = max(h * 0.025, 1.0)
    L = ['(',
         'local lay = LayerManager.getLayerFromName "sbg_debug"',
         'if lay == undefined do lay = LayerManager.newLayerFromName "sbg_debug"',
         'delete (for o in objects where matchPattern o.name pattern:"sbg_*" collect o)',
         'fn mk nm p sz c = ( local o = point pos:p size:sz cross:true box:false centermarker:false axistripod:false wirecolor:c name:nm; lay.addNode o; o )']
    for k, v in pts.items():
        c = "red" if k in flags else "yellow"
        s = sz * (1.8 if k in flags else 1.0)
        L.append('mk "%s" [%f,%f,%f] %f %s' % (k, v[0], v[1], v[2], s, c))
    if fing:
        for i, ch in enumerate(fing, 1):
            for j, p in enumerate(ch, 1):
                L.append('mk "sbg_F%d_%d" [%f,%f,%f] %f (color 255 140 0)' % (i, j, p[0], p[1], p[2], sz * 0.25))
    L.append('mk "sbg_L_Toe" [%f,%f,%f] %f yellow' % (toe[0], toe[1], toe[2], sz * 0.6))
    L.append('redrawViews()')
    L.append('((for o in objects where matchPattern o.name pattern:"sbg_*" collect o).count) as string')
    L.append(')')
    return "\n".join(L)


# ---------------------------------------------------------------------------
def _view3d_ctx():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return dict(window=win, area=area, region=region)


def _cleanup(col_name=COL, restore=None):
    col = bpy.data.collections.get(col_name)
    if col:
        for o in list(col.objects):
            me = o.data if o.type == 'MESH' else None
            bpy.data.objects.remove(o)
            if me and me.users == 0:
                bpy.data.meshes.remove(me)
        bpy.data.collections.remove(col)
    if restore:
        for n in restore:
            o = bpy.data.objects.get(n)
            if o:
                try:
                    o.hide_set(False)
                except Exception:
                    pass


def _set_status(s):
    bpy.context.scene["sbg_detect_status"] = s
    print("[SecBoneGen]", s)
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def _has_arp():
    return hasattr(bpy.ops, "arp") and hasattr(bpy.ops.arp, "guess_markers") and hasattr(bpy.ops.id, "get_selected_objects")


def _detect_fbx(path):
    """FBX 를 가져와 ARP 로 감지. 성공하면 (A, V), 실패하면 오류 문자열."""
    sc = bpy.context.scene
    ctx = _view3d_ctx()
    hidden_by_me = []
    with bpy.context.temp_override(**ctx):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        _cleanup()
        for o in bpy.data.objects:
            try:
                if not o.hide_get():
                    o.hide_set(True); hidden_by_me.append(o.name)
            except Exception:
                pass
        before = set(bpy.data.objects.keys())
        bpy.ops.import_scene.fbx(filepath=path)
        new = [o for o in bpy.data.objects if o.name not in before]
        col = bpy.data.collections.new(COL); sc.collection.children.link(col)
        meshes = []
        for o in new:
            for c in o.users_collection:
                c.objects.unlink(o)
            col.objects.link(o)
            if o.type == 'MESH':
                meshes.append(o)
        if not meshes:
            _cleanup(restore=hidden_by_me)
            return "가져온 메쉬가 없어요."
        V = _mesh_points(meshes)
        bpy.ops.object.select_all(action='DESELECT')
        for o in meshes:
            o.hide_set(False); o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        try:
            bpy.ops.id.get_selected_objects()
            bpy.ops.arp.guess_markers()
        except Exception as e:
            try:
                bpy.ops.id.cancel_and_delete_markers()
            except Exception:
                pass
            _cleanup(restore=hidden_by_me)
            return "ARP 몸 감지 실패: %s" % e
        try:
            bpy.ops.arp.guess_fingers()
        except Exception as e:
            print("[SecBoneGen] 손가락 감지 실패:", e)
        A = {o.name: [v * S for v in o.matrix_world.translation] for o in bpy.data.objects
             if o.name.endswith('_loc') and not o.name.endswith('_sym')}
        try:
            bpy.ops.id.cancel_and_delete_markers()
        except Exception:
            pass
        _cleanup(restore=hidden_by_me)
    need = ("neck_loc", "foot_loc", "thigh_loc", "knee_loc", "shoulder_loc", "elbow_loc", "hand_loc", "hand_tip_loc", "chin_loc", "head_tip_loc", "root_loc")
    miss = [k for k in need if k not in A]
    if miss:
        return "ARP 가 몸 관절을 다 찾지 못했어요: " + ", ".join(miss)
    return A, V


def _write_log(logd, model, A, pts, fing, toe, flags, notes):
    try:
        os.makedirs(logd, exist_ok=True)
        json.dump({"model": model, "markers": A, "points": pts, "fingers": fing, "toe": toe, "flags": flags, "notes": notes},
                  open(os.path.join(logd, "%s_%s.json" % (os.path.splitext(model)[0] or "scene", time.strftime("%Y%m%d_%H%M%S"))), "w", encoding="utf-8"),
                  ensure_ascii=False)
    except Exception:
        pass


def _summary(t0, n, fing, flags, notes):
    msg = "완료 (%.0f초): 지정점 %s개를 Max 에 놓았어요. 손가락 %s." % (time.time() - t0, n, "있음" if fing else "없음")
    if flags:
        msg += "\n※ 빨간 점 확인 필요: " + ", ".join(flags)
    for n_ in notes:
        msg += "\n- " + n_
    return msg


def run_detect():
    """Blender 버튼: 브리지로 연결된 Max 에서 모델을 가져와 감지하고 지정점을 놓는다."""
    if not _has_arp():
        return "Auto-Rig Pro(Smart)가 없어서 감지할 수 없어요. Auto-Rig Pro 를 설치·켜고 다시 해 주세요. (담당자에게 문의)"
    try:
        mb = _bridge()
    except Exception:
        return "Max Bridge 애드온이 없어요. 설치기(1_INSTALL.bat)를 먼저 실행하세요."
    t0 = time.time()
    path = os.path.join(mb.exchange_dir(), "sbg_detect.fbx")
    if os.path.exists(path):
        os.remove(path)
    r = mb.send(r'''(
local ms = for o in objects where (superclassof o == GeometryClass and classof o != Biped_Object and classof o != BoneGeometry and not o.isHidden and not (matchPattern o.name pattern:"sbg_*")) collect o
if ms.count == 0 then "ERROR: 보이는 메쉬가 없어요" else (
  local old = selection as array
  select ms
  local r = MaxBridge.exportFBX %s selOnly:true anim:false
  if old.count > 0 then select old else clearSelection()
  (r as string) + " | " + maxFileName
)
)''' % mb.ms_path(path))
    if r.startswith("ERROR") or not os.path.exists(path):
        return "Max 에서 모델을 가져오지 못했어요: " + r
    model = r.split("|")[-1].strip()
    res = _detect_fbx(path)
    if isinstance(res, str):
        return res
    A, V = res
    pts, fing, toe, flags, notes, h = compute_points(A, V)
    r2 = mb.send(points_maxscript(pts, fing, toe, flags, h))
    _write_log(os.path.join(mb.exchange_dir(), "sbg_detect_log"), model, A, pts, fing, toe, flags, notes)
    return _summary(t0, r2.strip(), fing, flags, notes) + "\n다음: Max 의 MTOS_RigTools [2. Biped 자동 생성 → Biped 생성]"


# ---------------------------------------------------------------------------
# Max 가 직접 부르는 감지 (Rig Tools [Biped 생성] → 지정점이 없으면 Blender 를 새로 띄워 실행)
#   blender.exe --python-expr "import sbg_detect; sbg_detect.start_job(r'<폴더>\job.json')"
#   job.json: {"fbx": ..., "model": ...}
#   결과: 같은 폴더 points.ms (Max 가 fileIn), status.txt (진행/오류), 끝나면 Blender 종료
# ---------------------------------------------------------------------------
def _job_status(d, s):
    try:
        open(os.path.join(d, "status.txt"), "w", encoding="utf-8").write(s)
    except Exception:
        pass
    print("[SecBoneGen]", s)


def run_job(job_path):
    d = os.path.dirname(job_path)
    t0 = time.time()
    try:
        job = json.load(open(job_path, encoding="utf-8"))
        if not _has_arp():
            raise RuntimeError("Auto-Rig Pro(Smart)가 없어서 감지할 수 없어요. (담당자에게 문의)")
        _job_status(d, "감지 중 (ARP)...")
        res = _detect_fbx(job["fbx"])
        if isinstance(res, str):
            raise RuntimeError(res)
        A, V = res
        pts, fing, toe, flags, notes, h = compute_points(A, V)
        ms = points_maxscript(pts, fing, toe, flags, h)
        open(os.path.join(d, "points_tmp.ms"), "w", encoding="utf-8-sig").write(ms)
        os.replace(os.path.join(d, "points_tmp.ms"), os.path.join(d, "points.ms"))
        _write_log(os.path.join(os.path.dirname(d), "sbg_detect_log"), job.get("model", "scene"), A, pts, fing, toe, flags, notes)
        _job_status(d, "OK\n" + _summary(t0, len(pts) + sum(len(c) for c in (fing or [])) + 1, fing, flags, notes))
    except Exception as e:
        import traceback; traceback.print_exc()
        _job_status(d, "ERROR\n%s" % e)


def start_job(job_path, quit=True):
    """Blender 시작 직후 부름: 화면이 뜬 뒤 감지하고 끝나면 Blender 를 닫는다."""
    def job():
        run_job(job_path)
        if quit:
            try:
                bpy.ops.wm.quit_blender()
            except Exception:
                os._exit(0)
        return None
    bpy.app.timers.register(job, first_interval=2.0)


class SBG_OT_detect(bpy.types.Operator):
    bl_idname = "sbg.detect_joints"
    bl_label = "관절 자동 감지 → Max 지정점"
    bl_description = "Max 에 열린 모델(보이는 메쉬)을 가져와 ARP AI 로 관절을 찾고, 노란 지정점(sbg_*)을 Max 에 놓습니다. 약 5~10분, 그동안 Blender 가 멈춘 것처럼 보여요"

    def execute(self, context):
        _set_status("감지 중... 약 5~10분 걸려요 (Blender 가 멈춘 것처럼 보여도 정상)")

        def job():
            try:
                msg = run_detect()
            except Exception as e:
                import traceback; traceback.print_exc()
                msg = "오류: %s" % e
            _set_status(msg)

            def draw(self, ctx):
                for line in msg.split("\n"):
                    self.layout.label(text=line)
            try:
                bpy.context.window_manager.popup_menu(draw, title="SecBoneGen 관절 자동 감지", icon='INFO')
            except Exception:
                pass
            return None
        bpy.app.timers.register(job, first_interval=0.3)
        return {'FINISHED'}


class SBG_PT_panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Max Bridge"
    bl_label = "SecBoneGen 관절 자동 감지"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        col = self.layout.column()
        col.label(text="1) Max 에 모델을 열고 (Biped 없이)")
        col.label(text="2) 아래 버튼 → 노란 지정점이 Max 에 생김")
        col.label(text="3) Max Rig Tools [2. Biped 생성]")
        col.operator("sbg.detect_joints", icon='ARMATURE_DATA')
        st = context.scene.get("sbg_detect_status", "")
        if st:
            box = col.box()
            for line in str(st).split("\n")[:8]:
                box.label(text=line)


classes = (SBG_OT_detect, SBG_PT_panel)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
