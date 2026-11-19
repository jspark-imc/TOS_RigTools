"""accurig_prep.py — AccuRIG(또는 다른 자동 리깅) FBX를 Max 원본 모델 자세로 되돌려 Max용 FBX로 정리

흐름 (Max Bridge 패널 "AccuRIG 정리" 버튼):
  1. Max에 열린 원본 메쉬(스킨 전 좌표)를 읽음 — 이름(대소문자 무시)과 정점 수로 짝 맞춤
  2. 리깅된 FBX를 임시 씬에 가져옴
  3. "원본 메쉬 x 웨이트 x 본별 강체 변환 = FBX 메쉬"를 최소제곱으로 풀어 본별 변환을 구함
     (UE5 프리셋처럼 메쉬 자체를 다른 자세로 바꿔 저장한 경우를 되돌림. 이미 원래 자세면 변환은 거의 단위행렬)
  4. 뼈대를 원래 자세로 옮기고 메쉬 좌표를 원본으로 교체
  5. 정점당 4본 제한·정규화, 셰이프키 삭제, ik_* 본 삭제
  6. 1단위 = 1인치로 바꿔 FBX 내보내기 (Max에서 루트 스케일 1.0)

정점 순서가 원본과 같아야 함(같지 않으면 중단하고 알려줌).
"""
import bpy, os, time, json
import numpy as np
from mathutils import Matrix

INCH = 0.0254


def _send(code):
    import max_bridge
    return max_bridge.send(code)


def read_max_meshes(tmp_dir):
    """Max 씬의 편집 가능한 메쉬(본·Biped 제외) 이름, 정점 수, 스킨 전 월드 좌표(인치)"""
    os.makedirs(tmp_dir, exist_ok=True)
    r = _send('''(
        local s = ""
        for o in objects where (classOf o.baseObject == Editable_Poly or classOf o.baseObject == Editable_mesh) and not (matchPattern o.name pattern:"ACC_*") do (
            local n = if classOf o.baseObject == Editable_Poly then (polyop.getNumVerts o.baseObject) else (getNumVerts o.baseObject.mesh)
            s += o.name + "|" + (n as string) + ";")
        s
    )''').strip()
    items = [x.split("|") for x in r.strip(";").split(";") if "|" in x]
    out = {}
    for name, n in items:
        f = os.path.join(tmp_dir, "orig_%s.txt" % name).replace("\\", "/")
        _send('''(
            local o = getNodeByName "%s"
            local f = createFile "%s"
            local tm = o.objectTransform
            if classOf o.baseObject == Editable_Poly then (
                for v = 1 to (polyop.getNumVerts o.baseObject) do (local p = (polyop.getVert o.baseObject v) * tm; format "%% %% %%\\n" p.x p.y p.z to:f))
            else (
                local m = o.baseObject.mesh
                for v = 1 to m.numverts do (local p = (getVert m v) * tm; format "%% %% %%\\n" p.x p.y p.z to:f))
            close f
            "ok"
        )''' % (name, f))
        out[name] = np.loadtxt(f).reshape(-1, 3)
    return out


def _base_coords(m):
    me = m.data
    a = np.empty(len(me.vertices) * 3)
    (me.shape_keys.key_blocks[0].data if me.shape_keys else me.vertices).foreach_get("co", a)
    return a.reshape(-1, 3)


def _weights(m, bi, NB):
    n = len(m.data.vertices)
    W = np.zeros((n, NB))
    gi = {g.index: bi.get(g.name) for g in m.vertex_groups}
    for v in m.data.vertices:
        for g in v.groups:
            j = gi.get(g.group)
            if j is not None and g.weight > 1e-5:
                W[v.index, j] += g.weight
    s = W.sum(1, keepdims=True); s[s == 0] = 1
    return W / s


def solve_bone_transforms(P, Q, Wt, iters=6, log=print):
    """P(리깅 FBX 메쉬), Q(원본) 인치 좌표, Wt 웨이트 -> 본별 강체 변환 T (Q -> P)"""
    used = np.where(Wt.sum(0) > 1e-6)[0]
    Qh = np.hstack([Q, np.ones((len(Q), 1))])
    X = (Wt[:, used][:, :, None] * Qh[:, None, :]).reshape(len(Q), -1)
    XtX = X.T @ X
    lam = 1e-6 * np.trace(XtX) / XtX.shape[0]
    sol = np.linalg.solve(XtX + lam * np.eye(XtX.shape[0]), X.T @ P)
    R = np.zeros((len(used), 3, 3)); t = np.zeros((len(used), 3))
    for k, j in enumerate(used):
        A = sol[k * 4:(k + 1) * 4, :].T; M = A[:, :3]; tt = A[:, 3]
        w = Wt[:, j]; c = (w[:, None] * Q).sum(0) / w.sum()
        U, S, Vt = np.linalg.svd(M); Rk = U @ Vt
        if np.linalg.det(Rk) < 0:
            U[:, -1] *= -1; Rk = U @ Vt
        R[k] = Rk; t[k] = M @ c + tt - Rk @ c
    Wu = Wt[:, used]

    def recon():
        return np.einsum('nb,bij,nj->ni', Wu, R, Q) + Wu @ t
    for it in range(iters):
        Pr = recon()
        for k in range(len(used)):
            w = Wu[:, k]; idx = np.where(w > 1e-4)[0]
            if len(idx) < 3:
                continue
            wk = w[idx]
            others = Pr[idx] - wk[:, None] * (Q[idx] @ R[k].T + t[k])
            target = (P[idx] - others) / wk[:, None]
            ww = wk ** 2
            cq = (ww[:, None] * Q[idx]).sum(0) / ww.sum(); cp = (ww[:, None] * target).sum(0) / ww.sum()
            H = ((Q[idx] - cq) * ww[:, None]).T @ (target - cp)
            U, S, Vt = np.linalg.svd(H)
            D = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))])
            Rn = Vt.T @ D @ U.T; tn = cp - Rn @ cq
            Pr[idx] += wk[:, None] * ((Q[idx] @ Rn.T + tn) - (Q[idx] @ R[k].T + t[k]))
            R[k] = Rn; t[k] = tn
    e = np.linalg.norm(recon() - P, axis=1)
    T = {}
    for k, j in enumerate(used):
        M = np.eye(4); M[:3, :3] = R[k]; M[:3, 3] = t[k]
        T[j] = M
    return T, float(e.max()), float(e.mean())


def run(fbx_path, out_path=None, keep_scene=False, report_dir=None):
    t0 = time.time()
    rep = {"fbx": fbx_path, "ok": False, "log": []}

    def log(s):
        rep["log"].append(s); print("[accurig_prep]", s)
    out_path = out_path or os.path.splitext(fbx_path)[0] + "_origpose.fbx"
    rep["out"] = out_path
    report_dir = report_dir or os.path.join(os.path.dirname(out_path), "accurig_prep_tmp")
    win = bpy.context.window
    orig_scene = win.scene
    name = "_accurig_prep"
    if name in bpy.data.scenes:
        sc = bpy.data.scenes[name]
        for o in list(sc.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.scenes.remove(sc)
    tmp = bpy.data.scenes.new(name)
    try:
        # 1) Max 원본
        maxm = read_max_meshes(report_dir)
        if not maxm:
            raise RuntimeError("Max 씬에 원본 메쉬가 없음 (원본 모델 파일을 Max에 열어 주세요)")
        log("Max 원본 메쉬: " + ", ".join("%s(%d)" % (k, len(v)) for k, v in maxm.items()))
        # 2) FBX 가져오기
        win.scene = tmp
        bpy.ops.import_scene.fbx(filepath=fbx_path, automatic_bone_orientation=False, ignore_leaf_bones=False, anim_offset=0)
        arms = [o for o in tmp.objects if o.type == 'ARMATURE']
        if len(arms) != 1:
            raise RuntimeError("아마추어가 %d개 (1개여야 함)" % len(arms))
        arm = arms[0]
        if arm.animation_data:
            arm.animation_data.action = None
        for pb in arm.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        arm.data.pose_position = 'REST'
        meshes = [o for o in tmp.objects if o.type == 'MESH']
        # 짝 맞추기: 이름(대소문자·.001 무시) + 정점 수
        lower = {k.lower(): k for k in maxm}
        pairs = []
        for m in meshes:
            key = m.name.split(".")[0].lower()
            mx = lower.get(key)
            if mx is None:
                cands = [k for k, v in maxm.items() if len(v) == len(m.data.vertices)]
                mx = cands[0] if len(cands) == 1 else None
            if mx is None or len(maxm[mx]) != len(m.data.vertices):
                raise RuntimeError("메쉬 '%s'(%d정점)와 맞는 Max 원본을 못 찾음" % (m.name, len(m.data.vertices)))
            pairs.append((m, mx))
        log("짝: " + ", ".join("%s=%s" % (m.name, mx) for m, mx in pairs))
        # 3) 풀기
        bones = [b.name for b in arm.data.bones]; bi = {n: i for i, n in enumerate(bones)}; NB = len(bones)
        Ps, Qs, Ws = [], [], []
        for m, mx in pairs:
            Wm = np.array(m.matrix_world)
            a = _base_coords(m)
            P = (a @ Wm[:3, :3].T + Wm[:3, 3]) / INCH
            Q = maxm[mx]
            # 정점 순서 검사: 엣지 길이 비율
            ed = np.empty(len(m.data.edges) * 2, int); m.data.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
            lp = np.linalg.norm(P[ed[:, 0]] - P[ed[:, 1]], axis=1); lq = np.linalg.norm(Q[ed[:, 0]] - Q[ed[:, 1]], axis=1)
            ok = lp > 1e-4
            same = float(np.mean(np.abs(lq[ok] / lp[ok] - 1) < 0.05))
            if same < 0.85:
                raise RuntimeError("'%s' 정점 순서가 원본과 다름 (엣지 일치 %.0f%%)" % (m.name, same * 100))
            Ps.append(P); Qs.append(Q); Ws.append(_weights(m, bi, NB))
        P = np.vstack(Ps); Q = np.vstack(Qs); Wt = np.vstack(Ws)
        before = float(np.linalg.norm(P - Q, axis=1).max())
        Tw, emax, emean = solve_bone_transforms(P, Q, Wt)
        log("자세 차이(풀기 전) 최대 %.2f인치 -> 재현 오차 최대 %.3f / 평균 %.4f인치" % (before, emax, emean))
        if emax > 0.5:
            log("경고: 재현 오차가 큼 — 결과를 꼭 확인하세요")
        # 웨이트 없는 본: 머리가 같은(1인치 이내) 웨이트 있는 자손 -> 없으면 부모(이미 정한 값)
        C = np.diag([1 / INCH] * 3 + [1]) @ np.array(arm.matrix_world); Ci = np.linalg.inv(C)
        heads = {b.name: (C @ np.append(np.array(b.head_local), 1))[:3] for b in arm.data.bones}
        Tn = {bones[j]: T for j, T in Tw.items()}
        order = []

        def walk(b):
            order.append(b)
            for c in b.children:
                walk(c)
        for r in [b for b in arm.data.bones if b.parent is None]:
            walk(r)
        Tall = {}
        for b in order:
            if b.name in Tn:
                Tall[b.name] = Tn[b.name]; continue
            best = None; bd = 1.0
            stack = list(b.children)
            while stack:
                c = stack.pop()
                if c.name in Tn:
                    d = np.linalg.norm(heads[c.name] - heads[b.name])
                    if d < bd:
                        bd = d; best = c.name
                stack.extend(c.children)
            Tall[b.name] = Tn[best] if best else (Tall[b.parent.name] if b.parent else np.eye(4))
        # 4) 원래 자세 뼈대(인치 월드)
        bd_ = {}
        for b in arm.data.bones:
            M = C @ np.linalg.inv(C) @ np.linalg.inv(Tall[b.name]) @ C @ np.array(b.matrix_local)
            R = M[:3, :3]; R = R / np.linalg.norm(R, axis=0)
            head = (np.linalg.inv(Tall[b.name]) @ np.append(heads[b.name], 1))[:3]
            tail = (np.linalg.inv(Tall[b.name]) @ C @ np.append(np.array(b.tail_local), 1))[:3]
            bd_[b.name] = (R, head, float(np.linalg.norm(tail - head)))
        for m, mx in pairs:
            m.parent = None; m.matrix_world = Matrix.Identity(4)
            if m.data.shape_keys:
                m.shape_key_clear()
        arm.matrix_world = Matrix.Identity(4)
        vl = tmp.view_layers[0]
        for o in tmp.objects:
            o.select_set(False, view_layer=vl)
        arm.select_set(True, view_layer=vl); vl.objects.active = arm
        with bpy.context.temp_override(window=win, scene=tmp, view_layer=vl, active_object=arm, object=arm, selected_objects=[arm]):
            bpy.ops.object.mode_set(mode='EDIT')
            eb = arm.data.edit_bones
            ik = [e for e in eb if e.name.lower().startswith("ik_")]
            for e in ik:
                eb.remove(e)
            for e in eb:
                e.use_connect = False
            for e in eb:
                R, head, L = bd_[e.name]
                M = np.eye(4); M[:3, :3] = R; M[:3, 3] = head
                e.matrix = Matrix(M.tolist()); e.length = max(L, 0.05)
            bpy.ops.object.mode_set(mode='OBJECT')
        log("ik 본 %d개 삭제, 본 %d개" % (len(ik), len(arm.data.bones)))
        # 5) 메쉬 = 원본 좌표, 4본 제한
        for m, mx in pairs:
            m.data.vertices.foreach_set("co", maxm[mx].ravel()); m.data.update()
            m.parent = arm; m.matrix_parent_inverse = Matrix.Identity(4)
            for md in m.modifiers:
                if md.type == 'ARMATURE':
                    md.object = arm
            names = [g.name for g in m.vertex_groups]
            rows = []; mxb = 0
            for v in m.data.vertices:
                ws = sorted(((g.weight, g.group) for g in v.groups if g.weight > 1e-4), reverse=True)
                mxb = max(mxb, len(ws))
                ws = ws[:4]; s = sum(w for w, _ in ws)
                rows.append([(gi, w / s) for w, gi in ws] if s > 0 else [])
            m.vertex_groups.clear()
            for nm in names:
                m.vertex_groups.new(name=nm)
            for vi, row in enumerate(rows):
                for gi, w in row:
                    m.vertex_groups[gi].add([vi], w, 'REPLACE')
            m.name = mx
            m.data.name = mx
            log("%s: 정점당 본 %d -> 4" % (mx, mxb))
        tmp.unit_settings.system = 'METRIC'; tmp.unit_settings.scale_length = INCH
        # 검증: 레스트 = 원본
        dg = bpy.context.evaluated_depsgraph_get(); dg.update()
        worst = 0.0
        for m, mx in pairs:
            e = m.evaluated_get(dg); me = e.to_mesh()
            a = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", a); e.to_mesh_clear()
            worst = max(worst, float(np.linalg.norm(a.reshape(-1, 3) - maxm[mx], axis=1).max()))
        log("레스트 자세 vs 원본 최대 %.5f인치" % worst)
        # 6) 내보내기
        sel = [arm] + [m for m, _ in pairs]
        for o in tmp.objects:
            o.select_set(False, view_layer=vl)
        for o in sel:
            o.select_set(True, view_layer=vl)
        with bpy.context.temp_override(window=win, scene=tmp, view_layer=vl, active_object=arm, selected_objects=sel):
            bpy.ops.export_scene.fbx(filepath=out_path, use_selection=True, object_types={'ARMATURE', 'MESH'},
                                     use_mesh_modifiers=False, mesh_smooth_type='FACE', add_leaf_bones=False, bake_anim=False,
                                     axis_forward='Y', axis_up='Z', apply_scale_options='FBX_SCALE_UNITS',
                                     use_armature_deform_only=False, path_mode='STRIP', embed_textures=False)
        log("내보냄: %s (%.1f초)" % (out_path, time.time() - t0))
        rep.update(ok=True, solve_max=emax, rest_err=worst, bones=len(arm.data.bones))
    except Exception as ex:
        import traceback
        rep["error"] = str(ex); rep["trace"] = traceback.format_exc()
        log("실패: %s" % ex)
    finally:
        win.scene = orig_scene
        if not keep_scene and name in bpy.data.scenes:
            sc = bpy.data.scenes[name]
            for o in list(sc.objects):
                bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.scenes.remove(sc)
            for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.actions):
                for d in [x for x in coll if x.users == 0]:
                    coll.remove(d)
    try:
        with open(os.path.splitext(out_path)[0] + "_report.json", "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in rep.items() if k != "trace"}, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return rep
