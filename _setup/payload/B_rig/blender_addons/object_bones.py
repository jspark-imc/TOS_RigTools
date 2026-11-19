# object_bones.py (Claude, 2026-10-25)  · 1.7 (10-30): 멜리타 자동 = 위치로 짝짓기(preset_map), 미리보기 = 만든 본
# · 1.8 (11-01): 치마 종류 파트 웨이트를 (u 둘레 각도, v 높이) 로 다시 계산(uv_weights.py, uv_refine), 겹친 옷 조각은 치마 본으로(msr_ob_bundle)
# ④ 오브젝트 본: 바디 복사 -> 떨어진 조각으로 분리 -> 뷰포트에서 조각 클릭(Shift 여러 개) -> 그 자리에 본 미리보기
#   -> 체인 수·마디 수 바꾸면 바로 갱신 -> '파트 확정' -> '생성' 으로 Max 에 본만 (bone_body, Renderable 끔, Box)
#   -> 웨이트는 '3. Max에 스킨 적용' 때 바디에 얹어서 같이 보냄.
# 원본 바디는 스킨 적용 때 파트 정점 웨이트만 바뀜. 복사본은 컬렉션 MSR_ObjBones, '복사본 정리'로 지움.
# 구조·이름 (멜리타 파츠 본과 같게, 전부 소문자): 체인 2개 이상이면 bone_obj01_root + 체인마다 _00(연결, 웨이트 없음)
#   bone_obj01_fl1_00, _01 .. _NN, _end  (방향 fl/l/bl/bc/br/r/fr/fc 자동). 체인 1개면 root·_00 없이 _01..+_end
# 종류 (2026-10-29): 파트마다 치마/망토/기타 — 자동 판별(골반·목 위치와 모양) 또는 직접 선택.
#   치마 = bone_skirt_..(Max 레이어 bone_skirt), 망토 = bone_cape_..(bone_cape), 기타 = bone_objNN_..(bone_etc)
# 부모: 먼저 만든 다른 파트 본(가까우면) > 하체 천은 Pelvis > 웨이트가 가장 큰 본. 바꾸려면 Max 에서 직접 링크
import collections
import json
import os
import re
import bpy, bmesh
import numpy as np
from mathutils import Vector

COL = "MSR_ObjBones"
PREFIX = "OBP_"
ARM_KEY = "msr_ob_bones"      # armature: names of the bones made here (parents first)
SHAPE_KEY = "msr_ob_shape"    # armature: json {bone: {up (Max world), w, h, taper}} = f05 bone roll/size for the Melitta preset (Max push)
CENTER_KEY = "msr_ob_centers" # armature: json [[centre chain bones], [left], [right]] (Max: centre turns 50:50 with its neighbours)
AUTO_PARENT_KEY = "msr_ob_auto_parents"   # armature: json {bone: parent} as made here (a different Max parent = set by hand)
ORIG_KEY = "msr_ob_orig"      # scene: json {vertex: {bone: weight}} body weights before the object bones took the vertex
PARTS_KEY = "msr_ob_parts"    # scene: json list of parts
PART_BONES_KEY = "msr_ob_part_bones"   # armature: json {bone prefix (bone_skirt_ ...): [bone names]} = which part made which bones
W_KEY = "msr_ob_weights"      # scene: json {bone: [[vertex, weight], ...]} applied on send
LAYER = "bone_body"
U = 0.0254          # Blender world units per Max unit
ROOT_LEN = 5.0      # Max units (Melitta skirt root)
END_LEN = 2.0       # Max units (Melitta _end)
ATTACH = 10.0       # Max units: a one-chain part starting this close to another part's bone hangs on it


# ---------------------------------------------------------------- data
def _islands(me):
    nv = len(me.vertices)
    ev = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    par = np.arange(nv)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for a, b in ev:
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb
    root = np.array([find(i) for i in range(nv)])
    return np.unique(root, return_inverse=True)[1]


def _world_co(obj):
    me = obj.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    M = np.array(obj.matrix_world)
    return co @ M[:3, :3].T + M[:3, 3]


def _vids(o):
    out = np.empty(len(o.data.vertices), dtype=np.int64)
    o.data.attributes["ob_vid"].data.foreach_get("value", out)
    return out


def pieces():
    col = bpy.data.collections.get(COL)
    return [o for o in col.objects if o.type == "MESH"] if col else []


def get_parts(scene):
    try:
        return json.loads(scene.get(PARTS_KEY, "[]"))
    except Exception:
        return []


def set_parts(scene, parts):
    scene[PARTS_KEY] = json.dumps(parts)


def part_of(scene, name):
    for p in get_parts(scene):
        if name in p["pieces"]:
            return p
    return None


def selected_pieces(ctx):
    pcs = set(pieces())
    return [o for o in ctx.selected_objects if o in pcs]


# ---------------------------------------------------------------- split
def split(ctx, body, min_verts=50):
    clear(ctx, body)
    me = body.data
    comp = _islands(me)
    P = _world_co(body)
    size = np.bincount(comp)
    big = np.where(size >= min_verts)[0]
    if len(big) == 0:
        big = np.array([int(np.argmax(size))])
    from mathutils.kdtree import KDTree
    bigv = np.where(np.isin(comp, big))[0]
    kd = KDTree(len(bigv))
    for i, v in enumerate(bigv):
        kd.insert(P[v].tolist(), i)
    kd.balance()
    grp = comp.copy()
    for s in np.where(size < min_verts)[0]:
        idx = np.where(comp == s)[0]
        grp[idx] = comp[bigv[kd.find(P[idx].mean(0).tolist())[1]]]
    col = bpy.data.collections.new(COL)
    ctx.scene.collection.children.link(col)
    n = 0
    for g in np.unique(grp):
        keep = set(np.where(grp == g)[0].tolist())
        bm = bmesh.new()
        bm.from_mesh(me)
        lay = bm.verts.layers.int.new("ob_vid")
        for v in bm.verts:
            v[lay] = v.index
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in keep], context="VERTS")
        n += 1
        m2 = bpy.data.meshes.new("%s%03d" % (PREFIX, n))
        bm.to_mesh(m2)
        bm.free()
        o = bpy.data.objects.new(m2.name, m2)
        o.matrix_world = body.matrix_world
        for s in body.material_slots:
            o.data.materials.append(s.material)
        col.objects.link(o)
    # only the pieces are clickable while picking
    locked = [o.name for o in ctx.scene.objects if o.name not in col.objects and not o.hide_select]
    for nm in locked:
        ctx.scene.objects[nm].hide_select = True
    ctx.scene["msr_ob_locked"] = locked
    body.hide_set(True)
    return n, len(size)


def clear(ctx, body):
    col = bpy.data.collections.get(COL)
    if col:
        for o in list(col.objects):
            me = o.data
            bpy.data.objects.remove(o)
            if me and me.users == 0:
                bpy.data.meshes.remove(me)
        bpy.data.collections.remove(col)
    for nm in ctx.scene.get("msr_ob_locked", []):
        o = ctx.scene.objects.get(nm)
        if o:
            o.hide_select = False
    ctx.scene["msr_ob_locked"] = []
    ctx.scene[PELVIS_KEY] = "[]"      # 2.5: 조각을 지우면 골반 고리 띠 기록도 (다시 나눈 같은 OBP_ 이름이 다른 조각을 가리키지 않게)
    if body:
        body.hide_set(False)
    _CACHE.clear()


# ---------------------------------------------------------------- chains
def _kmeans(X, k, it=20):
    if k <= 1 or len(X) <= k:
        return np.zeros(len(X), dtype=int)
    ang = np.arctan2(X[:, 1], X[:, 0])
    C = []
    for a0 in np.linspace(-np.pi, np.pi, k, endpoint=False):
        m = (ang >= a0) & (ang < a0 + 2 * np.pi / k)
        C.append(X[m].mean(0) if m.any() else X[len(C) % len(X)])
    C = np.array(C)
    for _ in range(it):
        lab = np.argmin(((X[:, None] - C[None]) ** 2).sum(2), 1)
        C = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
    return lab


_OLD_PART_RE = re.compile(r"(?i)^bone_(skirt|cape|obj\d*|hair)_")


def _parent_bone(arm, body, vids, skip):
    """the body bone with the most weight on the part vertices.
    11/01: 예전 파츠 본(셋에 남은 bone_skirt_BL2_02 같은 체인 본)은 후보에서 뺌 → 몸 본(골반 등)이 부모
    (카미엘: 예전 왼쪽 뒤 치마 본이 뽑혀 부채꼴 중심이 한쪽으로 치우치고, 새로 만들 때 지워져 뿌리 부모가 없어짐)"""
    bones = arm.data.bones
    old = lambda n: bool(_OLD_PART_RE.match(n) or _CH_RE.match(n))

    def body_of(n):                       # 예전 파츠 본만 받는 정점: 그 본의 위쪽 첫 몸 본
        b = bones[n].parent
        while b is not None and (old(b.name) or b.name in skip or not b.use_deform):
            b = b.parent
        return b.name if b is not None else None
    names = {g.index: g.name for g in body.vertex_groups}
    acc, acc_old = {}, {}
    for vi in vids:
        for e in body.data.vertices[int(vi)].groups:
            n = names.get(e.group)
            if n and n in bones and n not in skip and bones[n].use_deform:
                d = acc_old if old(n) else acc
                d[n] = d.get(n, 0.0) + e.weight
    if not acc:
        for n, w in acc_old.items():
            p = body_of(n)
            if p:
                acc[p] = acc.get(p, 0.0) + w
    return max(acc, key=acc.get) if acc else None


OB_MAX_W, OB_MAX_H = 5.0, 5.0   # 웨이트 받는 마디 본 굵기: 메쉬를 따르되 width·height 최대 5 (사용자 10/30)
BEND_MAX = 20.0      # 체인이 일직선에서 이보다 많이 휘면 여기까지만 (사용자 규칙 10/30: 더 휘게는 작업자에게 물어봄)
_LAST_BENT = []      # 마지막 생성에서 휨을 줄인 체인 [(이름, 원래 각도)]


def _bend_angle(J):
    """마디들이 첫 마디→끝을 잇는 직선에서 가장 많이 벗어난 각도 (도)"""
    d = J[-1] - J[0]
    L = np.linalg.norm(d)
    if L < 1e-9:
        return 0.0
    u = d / L
    worst = 0.0
    for i in range(len(J) - 1):
        s = J[i + 1] - J[i]
        n = np.linalg.norm(s)
        if n > 1e-9:
            worst = max(worst, float(np.degrees(np.arccos(np.clip(np.dot(s / n, u), -1.0, 1.0)))))
    return worst


def _limit_bend(J, lim=BEND_MAX):
    """휜 정도가 lim 도를 넘으면 직선 쪽으로 당겨서 lim 도에 맞춤. returns (J, 원래 각도)"""
    a0 = _bend_angle(J)
    if a0 <= lim:
        return J, a0
    a, b = J[0], J[-1]
    u = (b - a) / max(np.linalg.norm(b - a), 1e-9)
    S = a + np.outer((J - a) @ u, u)
    lo, hi = 0.0, 1.0
    for _ in range(20):
        mid = (lo + hi) / 2
        if _bend_angle(S + mid * (J - S)) <= lim:
            lo = mid
        else:
            hi = mid
    return S + lo * (J - S), a0


def plan_part(arm, body, objs, chains, segs, axis, single=False, parent=None, center=False, straight=False, force_root=False, lr=False):
    """-> dict(parent, chains=[(vids, joints, s)], centers={chain index: (left, right)})  (world coordinates)
    center: a part that goes all the way round (skirt) also gets chains at the front and back centre
    force_root (3단계): 체인 1개여도 root·_00 을 둠 (모든 체인 root·_00·_end)
    lr (3단계): 체인 2개를 좌우(x 중간값)로 가름 (앞치마·목도리 앞자락, shape_rules.split_lr)"""
    P = np.concatenate([_world_co(o) for o in objs])
    vids = np.concatenate([_vids(o) for o in objs])
    par = parent if (parent and parent in arm.data.bones) else _parent_bone(arm, body, vids, set(arm.get(ARM_KEY, [])))
    if par is None:
        return None
    pb = arm.data.bones[par]
    ph, pt = np.array(arm.matrix_world @ pb.head_local), np.array(arm.matrix_world @ pb.tail_local)
    d = ph + np.clip(((P - ph) @ (pt - ph)) / max(np.dot(pt - ph, pt - ph), 1e-12), 0, 1)[:, None] * (pt - ph)
    root_pt = P[np.argmin(np.linalg.norm(P - d, axis=1))]
    if single:
        chains, segs = 1, 1
    c = P.mean(0)
    if axis == "DOWN":
        ax = np.array([0.0, 0.0, -1.0])
    else:
        ax = np.linalg.eigh(np.cov((P - c).T))[1][:, -1]
        # 11/01: 체인은 부모 본에 가까운 끝에서 시작. 예전엔 '가장 가까운 정점 → 무게중심' 방향이라, 부모(골반)가 긴 조각의
        # 가운데 높이에 있으면 (카미엘 앞자락) 무게중심 쪽에 따라 아래에서 위로 거꾸로 만들어짐
        t_ = (P - c) @ ax
        lo, hi = t_ <= np.percentile(t_, 10), t_ >= np.percentile(t_, 90)

        def seg_d(q):
            return float(np.linalg.norm(q - (ph + np.clip(np.dot(q - ph, pt - ph) / max(np.dot(pt - ph, pt - ph), 1e-12), 0, 1) * (pt - ph))))
        if seg_d(P[hi].mean(0)) < seg_d(P[lo].mean(0)):
            ax = -ax
    ref = np.array([0.0, -1.0, 0.0]) if abs(ax[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = ref - ax * np.dot(ref, ax)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(ax, e1)
    Q = P - c
    if lr and chains == 2:
        mid = None
        cj = []
        lab = _rules().split_lr(P)
    elif axis == "DOWN" and chains > 1:
        # hanging cloth: equal angle sectors around the vertical line through the parent bone (0 = front, + = left)
        th = np.degrees(np.arctan2(P[:, 0] - ph[0], -(P[:, 1] - ph[1]))) % 360.0
        srt = np.sort(th)
        gaps = np.diff(np.concatenate([srt, [srt[0] + 360.0]]))
        g = int(np.argmax(gaps))
        ring = gaps[g] < 60.0
        if ring and center and chains % 2 == 0:
            # +2 chains, sectors turned half a sector so that one chain sits at the front centre and one at the back
            chains += 2
            a0, span = -180.0 / chains, 360.0
        elif ring:                     # all the way round (skirt): sectors start at the front
            a0, span = 0.0, 360.0
        else:                          # open (cape): split the covered range
            a0, span = srt[(g + 1) % len(srt)], 360.0 - gaps[g]
        lab = np.minimum((((th - a0) % 360.0) / max(span, 1e-6) * chains).astype(int), chains - 1)
        mid = [np.radians(a0 + span * (j + 0.5) / chains) for j in range(chains)]
        sector = np.radians(span / chains)     # 2.7: 체인 하나가 맡은 부채꼴 각 (마디 본 굵기)
        cj = [j for j in range(chains) if ring and center and abs(((np.degrees(mid[j]) + 90.0) % 180.0) - 90.0) < 1e-6]
    else:
        mid = None
        cj = []
        lab = _kmeans(np.stack([Q @ e1, Q @ e2], 1), chains)
    if mid is None:
        sector = None
    out, js, bends = [], [], []
    ax_all = ax
    for j in range(chains):
        m = lab == j
        if not m.any():
            continue
        ax = ax_all
        if lr and axis != "DOWN" and m.sum() > 3:
            # 3단계 좌우 갈래(앞자락): 갈래마다 자기 긴 방향 (전체 PCA 는 좌우로 벌어진 두 갈래를 가로축으로 잡음). 부모 본에 가까운 끝에서 시작
            axj = np.linalg.eigh(np.cov((P[m] - P[m].mean(0)).T))[1][:, -1]
            tj = (P[m] - P[m].mean(0)) @ axj
            lo_, hi_ = tj <= np.percentile(tj, 10), tj >= np.percentile(tj, 90)
            if seg_d(P[m][hi_].mean(0)) < seg_d(P[m][lo_].mean(0)):
                axj = -axj
            ax = axj
        t = (P[m] - c) @ ax
        t0, L = t.min(), max(t.max() - t.min(), 1e-6)
        s = (t - t0) / L * segs
        J = []
        for i in range(segs + 1):
            sel = np.abs(s - i) <= 0.5
            if not sel.any():
                sel = np.abs(s - i) <= np.abs(s - i).min() + 1e-9
            q = P[m][sel].mean(0)
            q = q + ax * ((t0 + L * i / segs) - np.dot(q - c, ax))
            if mid is not None:
                # put the joint on the sector's centre angle (even fan like the Melitta skirt / cape)
                rr = np.median(np.hypot(P[m][sel][:, 0] - ph[0], P[m][sel][:, 1] - ph[1]))
                q = np.array([ph[0] + rr * np.sin(mid[j]), ph[1] - rr * np.cos(mid[j]), q[2]])
            J.append(q)
        J = np.array(J)
        bent = 0.0
        if not straight and len(J) > 2:
            J, bent = _limit_bend(J)
        bends.append(bent)
        if straight and len(J) > 2:
            # 곧은 체인 (Rig Tools [Max 수정] 의 치마 아닌 파트): 마디를 위→아래 직선 위에 고르게
            a, b = J[0], J[-1]
            J = np.array([a + (b - a) * (i / (len(J) - 1)) for i in range(len(J))])
        out.append((vids[m], J, s))
        js.append(j)
    # direction for the bone name: the sector's centre angle when there is one (fc1 really is the front centre)
    dirs = [np.array([np.sin(mid[j]), -np.cos(mid[j]), 0.0]) if mid is not None else None for j in js]
    # centre chains follow their two neighbours (chain index in out -> (left, right) index in out)
    pos = {j: k for k, j in enumerate(js)}
    centers = {pos[j]: (pos[(j - 1) % chains], pos[(j + 1) % chains]) for j in cj
               if j in pos and (j - 1) % chains in pos and (j + 1) % chains in pos}
    hub = None
    if len(out) > 1:
        # Melitta: root bone below a hub at the mean top of the chains, _00 links hub -> chain top
        tops = np.array([J[0] for _, J, _ in out])
        hub = np.array([tops[:, 0].mean(), tops[:, 1].mean(), tops[:, 2].mean()])
    elif len(out) == 1 and force_root:
        hub = out[0][1][0] - ax * (2.0 * U)      # 체인 시작 2cm 위에 허브 → root + _00
    return dict(parent=par, chains=out, hub=hub, root_pt=root_pt, center=ph, nv=len(P), zc=float(c[2]), centers=centers, dirs=dirs, bends=bends,
                sector=sector)


def _rules():
    """3단계 모양 규칙 모듈 (이 파일 옆 shape_rules.py)"""
    import shape_rules
    return shape_rules


def _area_max(o, unit):
    """조각 메쉬 면적 (Max 단위²)"""
    me = o.data
    me.calc_loop_triangles()
    P = _world_co(o) * unit
    n = len(me.loop_triangles)
    if n == 0:
        return 0.0
    idx = np.empty(n * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", idx)
    idx = idx.reshape(-1, 3)
    a, b, c = P[idx[:, 0]], P[idx[:, 1]], P[idx[:, 2]]
    return float(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum())


CORD_MAX = 0.5        # 면적 / (긴 쪽 × 둘째 쪽) 이 이 미만이면 가는 줄 (치마·망토를 따라가는 후보)
STRAP_MAX = 0.7       # 매달린 물건 묶음 안에서 이 미만이면 끈 → 몸 웨이트 (11/01 정현: 가방 몸통만 체인, 끈부터 체인은 변형 hang=1)


def _follow_nearest(W, chain_data, objs, Pw):
    """W 에 붙은 조각(objs) 정점을 더함: 파트 정점 중 가장 가까운 것의 웨이트를 그대로 복사 (ps_build 6번째 방식)"""
    from mathutils.kdtree import KDTree
    src = np.concatenate([v for v, _, _, _ in chain_data]).astype(np.int64)
    if len(src) == 0 or not objs:
        return 0
    kd = KDTree(len(src))
    for j, i in enumerate(src):
        kd.insert(Pw[int(i)].tolist(), j)
    kd.balance()
    byv = {}
    for n, lst in W.items():
        for v, w in lst:
            byv.setdefault(int(v), {})[n] = float(w)
    cnt = 0
    for o in objs:
        for vi in _vids(o):
            _, j, _ = kd.find(Pw[int(vi)].tolist())
            for n, w in byv.get(int(src[j]), {}).items():
                W.setdefault(n, []).append([int(vi), w])
            cnt += 1
    return cnt


def plan_ring(arm, body, objs, centre, parent):
    """3단계 '목 둘레' 구조 (shape_rules.plan_ring): 목 둘레 4칸, 칸마다 본 하나. plan_part 와 같은 dict"""
    P = np.concatenate([_world_co(o) for o in objs])
    vids = np.concatenate([_vids(o) for o in objs])
    return _rules().plan_ring(P, vids, centre, parent)


_PART_BONES = {}


def _made_lines(arm, part):
    """preview segments of a Melitta preset part from the bones already made
    (the part's bones in the preset, e.g. skirt also has Bone_miniskirt_*; any case)"""
    if not part:
        return []
    if not _PART_BONES:
        try:
            for pp in json.load(open(PRESET, encoding="utf-8"))["parts"]:
                _PART_BONES[pp["name"]] = {b[0].lower() for b in pp.get("bones", [])}
        except Exception:
            pass
    names = _PART_BONES.get(part) or set()
    pre = "bone_%s_" % part.lower()
    made = set(arm.get(ARM_KEY, []))
    M = arm.matrix_world
    out = []
    for b in arm.data.bones:
        n = b.name.lower()
        if b.name in made and (n in names or n.startswith(pre)):
            out += [tuple(M @ b.head_local), tuple(M @ b.tail_local)]
    return out


def _lines(pl):
    """preview segments of a plan: hub links + chains"""
    out = []
    if pl["hub"] is not None:
        for _, J, _ in pl["chains"]:
            out += [pl["hub"], J[0]]
    for _, J, _ in pl["chains"]:
        out += [p for i in range(len(J) - 1) for p in (J[i], J[i + 1])]
    return out


def _dir(v):
    """Melitta-style direction label from a horizontal offset (x = left, -y = front): fl, l, bl, bc, br, r, fr, fc"""
    th = np.degrees(np.arctan2(v[0], -v[1]))
    fb = "f" if abs(th) < 75 else ("b" if abs(th) > 105 else "")
    s = "l" if 15 < th < 165 else ("r" if -165 < th < -15 else "c")
    return (fb + s) if fb else s


# ---------------------------------------------------------------- preview (temporary, drawn only)
_CACHE = {}


def _flow():
    import sys
    return sys.modules.get("max_style_rig")


def _preview(ctx):
    """lines to draw: current selection (yellow) + confirmed parts (green)"""
    f = _flow()
    if f is None or not pieces():
        return [], []
    arm, body, face, tooth = f.flow_objects(ctx)
    if arm is None or body is None:
        return [], []
    wm = ctx.window_manager
    sel = sorted(o.name for o in selected_pieces(ctx))
    key = (tuple(sel), wm.msr_ob_chains, wm.msr_ob_segs, wm.msr_ob_axis, wm.msr_ob_single, wm.msr_ob_center, ctx.scene.get(PARTS_KEY, ""),
           tuple(arm.get(ARM_KEY, [])))
    if _CACHE.get("key") == key:
        return _CACHE["cur"], _CACHE["done"]
    cur, done = [], []
    if sel:
        pl = plan_part(arm, body, [bpy.data.objects[n] for n in sel], wm.msr_ob_chains, wm.msr_ob_segs, wm.msr_ob_axis, wm.msr_ob_single, center=wm.msr_ob_center)
        if pl:
            cur += _lines(pl)
    for p in get_parts(ctx.scene):
        objs = [bpy.data.objects[n] for n in p["pieces"] if n in bpy.data.objects]
        if not objs or set(p["pieces"]) & set(sel):
            continue
        if p.get("preset"):
            # (1.7, from 10-29) Melitta auto: bones come from the f05 layout, not from the pieces -> draw the bones made
            # (a plan from the pieces looked nothing like them). Not made yet = nothing drawn.
            done += _made_lines(arm, p.get("name", ""))
            continue
        pl = plan_part(arm, body, objs, p["chains"], p["segs"], p["axis"], p["single"], p.get("parent"), p.get("center", True),
                       p.get("straight", False))
        if pl:
            if p.get("no_root"):
                pl["hub"] = None
            done += _lines(pl)
    _CACHE.update(key=key, cur=cur, done=done)
    return cur, done


_HANDLE = None


def _draw():
    import gpu
    from gpu_extras.batch import batch_for_shader
    ctx = bpy.context
    try:
        if ctx.window_manager.msr_p4 != "OB":
            return
        cur, done = _preview(ctx)
    except Exception as e:
        print("ob preview:", e)
        return
    if not cur and not done:
        return
    sh = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.depth_test_set("NONE")
    gpu.state.line_width_set(4.0)
    gpu.state.point_size_set(9.0)
    for pts, col in ((done, (0.2, 1.0, 0.3, 1.0)), (cur, (1.0, 0.85, 0.1, 1.0))):
        if pts:
            P = [tuple(p) for p in pts]
            sh.uniform_float("color", col)
            batch_for_shader(sh, "LINES", {"pos": P}).draw(sh)
            batch_for_shader(sh, "POINTS", {"pos": P}).draw(sh)
    gpu.state.line_width_set(1.0)
    gpu.state.point_size_set(1.0)


def _settings_changed(self, ctx):
    """number changed: update the part being edited (if the selection is a confirmed part)"""
    sel = sorted(o.name for o in selected_pieces(ctx))
    parts = get_parts(ctx.scene)
    for p in parts:
        if sorted(p["pieces"]) == sel and sel:
            p.update(chains=self.msr_ob_chains, segs=self.msr_ob_segs, axis=self.msr_ob_axis, single=self.msr_ob_single,
                     center=self.msr_ob_center)
            set_parts(ctx.scene, parts)
    for a in ctx.screen.areas if ctx.screen else []:
        if a.type == "VIEW_3D":
            a.tag_redraw()


@bpy.app.handlers.persistent
def _on_depsgraph(scene, depsgraph):
    # selection changed -> show the clicked part's own numbers
    ctx = bpy.context
    try:
        sel = sorted(o.name for o in selected_pieces(ctx))
    except Exception:
        return
    if _CACHE.get("sel") == sel:
        return
    _CACHE["sel"] = sel
    p = None
    for q in get_parts(scene):
        if sorted(q["pieces"]) == sel and sel:
            p = q
    if p:
        wm = ctx.window_manager
        for k, a in (("chains", "msr_ob_chains"), ("segs", "msr_ob_segs"), ("axis", "msr_ob_axis"), ("single", "msr_ob_single"), ("center", "msr_ob_center")):
            if getattr(wm, a) != p[k]:
                setattr(wm, a, p[k])


# ---------------------------------------------------------------- confirm / generate / weights
def confirm(ctx):
    wm = ctx.window_manager
    sel = sorted(o.name for o in selected_pieces(ctx))
    if not sel:
        return None
    parts = [p for p in get_parts(ctx.scene) if not set(p["pieces"]) & set(sel)]
    f = _flow()
    arm, body, face, tooth = f.flow_objects(ctx)
    pl = plan_part(arm, body, [bpy.data.objects[n] for n in sel], 1, 1, "AUTO", True)
    x = np.concatenate([_world_co(bpy.data.objects[n]) for n in sel])[:, 0].mean()
    used = {p["id"] for p in parts}
    pid = next(i for i in range(1, 999) if i not in used)
    kind = wm.msr_ob_kind
    kind = guess_kind(arm, [bpy.data.objects[n] for n in sel]) if kind == "AUTO" else ("" if kind == "OTHER" else kind.lower())
    name = None
    if kind:
        taken = {str(q.get("name") or "").lower() for q in parts}
        name = kind if kind not in taken else next(kind + str(i) for i in range(2, 99) if kind + str(i) not in taken)
    parts.append(dict(id=pid, pieces=sel, chains=wm.msr_ob_chains, segs=wm.msr_ob_segs, axis=wm.msr_ob_axis,
                      single=wm.msr_ob_single, center=wm.msr_ob_center, parent=pl["parent"] if pl else None, x=float(x),
                      kind=kind, name=name))
    set_parts(ctx.scene, parts)
    return pid


KIND_LABEL = {"skirt": "치마", "cape": "망토", "": "기타"}
LAST_MINI = []      # 2.7: 미니 치마 조건으로 치마가 된 조각 이름 (recommend_parts 마다 비움, 결과 메시지에 표시)


def _bip_pos(arm, pre, n):
    b = arm.data.bones.get(pre + " " + n)
    return (arm.matrix_world @ b.head_local) if b else None


def guess_kind(arm, objs, loose=False, diag=None):
    """파트 종류 자동 판별 -> "skirt" / "cape" / "" (기타)
    망토: 위쪽이 가슴(Spine2) 높이 이상, 몸 뒤쪽(+Y)에 있고 아래로 늘어짐
    치마: 위쪽이 골반~허리 높이, 골반 둘레를 거의 한 바퀴 감쌈
    loose: 사람이 Max 에서 고른 면(이미 파트로 정해짐) — 다리 조각을 걸러 내는 '가운데 천' 조건은 안 봄
    diag: 목록이면 판정 수치 한 줄을 붙임 (MSR_OB_DEBUG 표)"""
    try:
        P = np.concatenate([_world_co(o) for o in objs])
        pre = _flow().bip_prefix(arm) or "Bip01"
        pel, sp2, nk = _bip_pos(arm, pre, "Pelvis"), _bip_pos(arm, pre, "Spine2"), _bip_pos(arm, pre, "Neck")
        if pel is None or nk is None or len(P) < 10:
            if diag is not None:
                diag.append("bip 없음 pel %s nk %s" % (pel, nk))
            return ""
        if sp2 is None:
            sp2 = (pel + nk) * 0.5
        H = max(nk.z - pel.z, 1e-6)
        top, bot = np.percentile(P[:, 2], 97), np.percentile(P[:, 2], 3)
        x0, x1 = np.percentile(P[:, 0], 2), np.percentile(P[:, 0], 98)
        across = x0 < pel.x - 0.1 * H and x1 > pel.x + 0.1 * H      # 몸 가운데를 가로지름 (팔·다리 조각 제외)
        ang = np.arctan2(P[:, 1] - pel.y, P[:, 0] - pel.x)
        cover = len(np.unique(np.floor((ang + np.pi) / (2 * np.pi) * 12).astype(int) % 12)) / 12.0
        back = float(np.mean(P[:, 1] > nk.y))
        if diag is not None:
            diag.append("top %.0f bot %.0f (pel %.0f sp2 %.0f nk %.0f) x %.0f~%.0f across %s cover %.2f back %.2f" % (
                top / U, bot / U, pel.z / U, sp2.z / U, nk.z / U, x0 / U, x1 / U, across, cover, back))
        if not across:
            return ""
        # 망토: 위가 가슴 높이 이상, 몸 뒤쪽에 몰려 있고, 아래로 길게 늘어짐
        # (11/01 3단계: 밑단이 골반 관절 위에서 끝나는 짧은 망토도 — 길이가 가슴~골반 길이보다 길면. ClothBones v0.7 규칙)
        if top > sp2.z - 0.15 * H and back > 0.7 and (bot < pel.z or (top - bot) > (sp2.z - pel.z)):
            return "cape"
        # 치마: 위가 골반~허리, 골반 둘레를 감싸고, 사타구니보다 한참 아래까지 내려오며 아래가 더 넓음
        # 다리 조각 제외: 치마는 무릎~허벅지 높이에서도 앞·뒤 가운데에 천이 있음 (다리는 가운데가 비어 있음)
        mid = (P[:, 2] > bot + 0.15 * (top - bot)) & (P[:, 2] < bot + 0.5 * (top - bot))
        centre = float(np.mean(np.abs(P[mid, 0] - pel.x) < 0.08 * H)) if mid.sum() > 10 else 0.0
        # 2.7 미니 치마(세레나): 밑단이 골반 아래 0.25~0.35H 로 짧아도, 골반 둘레를 빈틈없이(12칸 모두) 감싸면 같은 조건으로 봄
        #   (기존 조건은 그대로. 멜리타·카미엘·카르멘·실베스티아·위젤 셋에서 판정이 바뀌는 조각 0개 확인)
        mini = cover >= 0.95 and pel.z - 0.35 * H <= bot < pel.z - 0.25 * H
        if pel.z - 0.5 * H < top < sp2.z + 0.1 * H and cover >= 0.65 and (bot < pel.z - 0.35 * H or mini) and (loose or centre > 0.04):
            def rad(z0, z1):
                m = (P[:, 2] >= z0) & (P[:, 2] <= z1)
                return float(np.median(np.hypot(P[m, 0] - pel.x, P[m, 1] - pel.y))) if m.sum() > 5 else 0.0
            span = top - bot
            if rad(bot, bot + 0.25 * span) > 1.05 * rad(top - 0.25 * span, top):
                if mini:
                    LAST_MINI.extend(o.name for o in objs)
                return "skirt"
    except Exception as e:
        print("[object_bones] 종류 판별 실패:", e)
    return ""


def _part_label(q):
    k = q.get("kind")
    if k is None:   # 예전 파트·멜리타 프리셋: 이름으로
        n = (q.get("name") or "").lower()
        k = "skirt" if "skirt" in n else "cape" if "cape" in n else ""
    return "%s(%s)" % (q.get("name") or "%02d" % q["id"], KIND_LABEL.get(k, "기타"))


def unconfirm(ctx):
    sel = {o.name for o in selected_pieces(ctx)}
    parts = get_parts(ctx.scene)
    keep = [p for p in parts if not set(p["pieces"]) & sel]
    set_parts(ctx.scene, keep)
    return len(parts) - len(keep)


PRESET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parts_preset_melitta.json")
PRESET_SHARE = 0.5      # a piece belongs to a preset part when at least this share of its vertices are that part's


PRESET_TOL = 0.05       # Max units: a body vertex is the preset vertex when this close (after centring)
PRESET_MISS = 0.1       # share of preset vertices allowed without a body vertex there (more = not the Melitta body)
PRESET_PART_OK = 0.98   # a preset part is used only when this share of its vertices are in place (else: moved -> 직접 고치기)
_PMAP = {}              # (body, vertex count, coordinate sum) -> preset vertex -> body vertex


def preset_map(body, data=None, path=PRESET):
    """preset vertex number -> this body's vertex number, matched by position (preset "co" = Melitta body in Max world).
    (1.7, from 10-29) The vertex order can change in Max (detach/attach, export) while the mesh is the same: a melitta_body
    kept 0..10572 and the rest was reordered -> parts and weights landed on the wrong vertices (skirt weights on the cuffs).
    -1 = no body vertex at that place (moved in Max). None = not the Melitta body (vertex count differs or too many moved;
    the old '>=' test also took bigger bodies such as Gisele_body 27367 for Melitta)."""
    if data is None:
        if not os.path.exists(path):
            return None
        data = json.load(open(path, encoding="utf-8"))
    n = len(body.data.vertices)
    need = data.get("nv") or max(max(pp["vids"]) for pp in data["parts"]) + 1
    if n != need:
        return None
    co = data.get("co")
    if not co:
        return np.arange(n)                    # preset without positions: vertex numbers as they are
    P = _world_co(body) / U
    key = (body.name, n, round(float(P.sum()), 2))
    if key in _PMAP:
        return _PMAP[key]
    R = np.asarray(co, dtype=float).reshape(-1, 3)
    R = R + (np.median(P, axis=0) - np.median(R, axis=0))
    same = np.linalg.norm(P - R, axis=1) < PRESET_TOL
    m = np.full(n, -1, dtype=np.int64)
    if same.all():
        m = np.arange(n)
    else:
        from mathutils.kdtree import KDTree
        kd = KDTree(n)
        for i, p in enumerate(P):
            kd.insert(p, i)
        kd.balance()
        used = np.zeros(n, dtype=bool)
        idx = np.nonzero(same)[0]
        m[idx] = idx
        used[idx] = True
        for i in np.nonzero(~same)[0]:
            near = sorted(kd.find_range(R[i], PRESET_TOL), key=lambda h: h[2])
            j = next((h[1] for h in near if not used[h[1]]), near[0][1] if near else -1)
            m[i] = j
            if j >= 0:
                used[j] = True
        if (m < 0).mean() > PRESET_MISS:
            m = None
    _PMAP[key] = m
    return m


def preset_body_lock(body, path=PRESET):
    """11/01: preset weights {BODY_TOKEN: 1} = 정답 멜리타 01 에서 몸 본만 받는 정점 (스카프·후드 옆 가슴·허리).
    파츠 넓히기가 여기에 파츠 웨이트를 주지 않게 → 이 바디의 정점 번호 set (멜리타 바디가 아니면 빈 set)"""
    try:
        data = json.load(open(path, encoding="utf-8"))
        ids = [int(v) for v, d in data.get("weights", {}).items() if set(d) == {BODY_TOKEN}]
        if not ids:
            return set()
        vm = preset_map(body, data)
    except Exception as e:
        print("[object_bones] 몸 고정 정점 읽기 실패:", e)
        return set()
    if vm is None:
        return set()
    return {int(vm[i]) for i in ids if vm[i] >= 0}


# 집 확인 (2026-11-01): 멜리타 바디를 f05 프리셋(본 위치 저장값)으로 만들지, 다른 캐릭터처럼 모양 규칙만으로 만들지.
#   True = 프리셋(2.0 까지의 기본), False = 규칙만(치마 8×6·망토·후드·물건이 작업자 본 1~3cm 안에 자동, 3단계 결과와 같음).
#   시험용 환경변수 MSR_PRESET=0|1 이 이 값보다 우선. (MSR_NO_PRESET=1 은 3단계 시험용, 같은 뜻)
MELITTA_PRESET = True

# 집 확인 (2026-11-01): 골반 둘레를 두르는 낮은 고리 띠(카미엘 obj06 엉덩이 고리). 체인을 만들지 않고 뒤 띠처럼 치마·코트 본으로 묶음.
#   판정: 골반 둘레 24칸 중 LOW_RING_COVER 이상 덮고, 높이 LOW_RING_H 미만, 골반 높이 띠(골반 -10 ~ +25cm) 안, 몸 본에서 LOW_RING_DIST 넘게
#   떠 있음(몸에 붙은 벨트 071/073 은 7.6cm 로 제외, 고리는 13.5). 치마·코트가 없으면 Pelvis.
#   LOW_RING_TO = "skirt": 치마·코트 묶음(기본, uv 웨이트) / "pelvis": Bip Pelvis 100% (정현이 '2' 라고 하면 이 값으로)
LOW_RING_COVER = 0.6
LOW_RING_H = 15.0
LOW_RING_DIST = 10.0
LOW_RING_TO = "skirt"
PELVIS_KEY = "msr_ob_pelvis"   # scene: json [조각 이름] → generate 가 그 정점을 Pelvis 100% 로 (LOW_RING_TO="pelvis" 또는 치마 없음)


def is_low_ring(d, pel):
    """recommend_parts 조각 수치 d 가 '골반 둘레 낮은 고리 띠' 인지"""
    if pel is None:
        return False
    hz = d["zmax"] - d["zmin"]
    return (d["cover"] >= LOW_RING_COVER and hz < LOW_RING_H and d["dist"] >= LOW_RING_DIST
            and d["zmin"] >= pel[2] - 10.0 and d["zmax"] <= pel[2] + 25.0 and d["top"] == "torso")


def is_preset_body(body, path=PRESET):
    """the Melitta preset only works on the Melitta body: same vertex count and the same shape (by position, any vertex order)
    환경변수 MSR_NO_PRESET=1 이면 멜리타도 규칙 경로로 (3단계 시험용). MELITTA_PRESET=False 면 항상 규칙 경로"""
    if os.environ.get("MSR_NO_PRESET"):
        return False
    ev = os.environ.get("MSR_PRESET")
    use = MELITTA_PRESET if ev is None else ev not in ("0", "off", "")
    if not use:
        return False
    return preset_map(body, path=path) is not None


def load_preset(ctx, body, path=PRESET):
    """Melitta parts preset -> confirmed parts (pieces picked from the preset's body vertices).
    Only for the Melitta body (is_preset_body; matched by position). returns (found [(name, pieces)], missing [name])"""
    data = json.load(open(path, encoding="utf-8"))
    vm = preset_map(body, data)
    if not pieces():
        split(ctx, body, ctx.window_manager.msr_ob_min)
    owner = {}
    for pp in data["parts"]:
        for v in pp["vids"]:
            if vm[v] >= 0:
                owner[int(vm[v])] = pp["name"]
    mine = {pp["name"]: [] for pp in data["parts"]}
    for o in pieces():
        vids = _vids(o)
        cnt = {}
        for v in vids.tolist():
            n = owner.get(v)
            if n:
                cnt[n] = cnt.get(n, 0) + 1
        if cnt:
            n, c = max(cnt.items(), key=lambda kv: kv[1])
            if c >= PRESET_SHARE * len(vids):
                mine[n].append(o.name)
    parts, found, missing = [], [], []
    for i, pp in enumerate(data["parts"], 1):
        if (vm[np.asarray(pp["vids"])] >= 0).mean() < PRESET_PART_OK:
            missing.append(pp["name"] + "(모양 바뀜)")    # vertices moved in Max: the f05 layout and weights do not fit
            continue
        if not mine[pp["name"]]:
            missing.append(pp["name"])
            continue
        parts.append(dict(id=i, name=pp["name"], pieces=sorted(mine[pp["name"]]), chains=pp["chains"], segs=pp["segs"],
                          axis=pp["axis"], single=pp["single"], center=False,
                          no_root=pp.get("no_root", False), end=pp.get("end", True), labels=pp.get("labels"),
                          label_map=pp.get("label_map", {}), parent_fix=pp.get("parent"), preset=True))
        found.append((pp["name"], len(mine[pp["name"]])))
    set_parts(ctx.scene, parts)
    _CACHE.clear()
    return found, missing


def _preset_layout(ctx, arm, parts, body):
    """preset parts -> ({part: f05 bones}, {body vertex: {bone: weight}}, {Bip anchor: Max transform rows}, unit, off).
    The anchors' transforms come from Max (the f05 layout is stored in the anchor's Max frame).
    Weights are stored by preset vertex number -> moved to this body's vertex numbers (preset_map)."""
    names = {p["name"] for p in parts if p.get("preset")}
    if not names or not os.path.exists(PRESET):
        return {}, {}, {}, 1.0, Vector()
    data = json.load(open(PRESET, encoding="utf-8"))
    bones = {pp["name"]: pp["bones"] for pp in data["parts"] if pp["name"] in names and pp.get("bones")}
    if not bones:
        return {}, {}, {}, 1.0, Vector()
    own = {b[0] for lst in bones.values() for b in lst}
    vm = preset_map(body, data)
    if vm is None:
        raise RuntimeError("멜리타 프리셋과 바디 정점 위치가 안 맞아요 (다른 바디) → 1. 파츠 나누기 다시")
    W = {str(int(vm[int(v)])): d for v, d in data.get("weights", {}).items() if set(d) & own and vm[int(v)] >= 0}
    f = _flow()
    mb = f._max_bridge()
    if mb is None:
        raise RuntimeError("멜리타 자동 본은 Max 연결이 필요해요 (Bip 위치를 Max에서 읽음)")
    anchors = sorted({b[2] for lst in bones.values() for b in lst})
    r = mb.send('(local r = ""; for n in #(%s) do (local o = getNodeByName n exact:true; if o != undefined do '
                '(local m = o.transform; r += n + "|"; for v in #(m.row1, m.row2, m.row3, m.row4) do r += (v.x as string) + "," + '
                '(v.y as string) + "," + (v.z as string) + ","; r += ";")); r)' % ",".join('"%s"' % a for a in anchors),
                timeout=30).strip().strip('"')
    tm = {}
    for item in r.split(";"):
        n, _, v = item.partition("|")
        if n and v:
            x = [float(s) for s in v.strip(",").split(",")]
            tm[n] = [x[0:3], x[3:6], x[6:9], x[9:12]]
    miss = [a for a in anchors if a not in tm]
    if miss:
        raise RuntimeError("Max에 없는 Bip 본: %s" % ", ".join(miss))
    unit, off = f._max_xform(arm, mb)
    return bones, W, tm, unit, off


def part_prefix(p):
    """bone name prefix of a part: bone_skirt_ / bone_cape2_ / bone_obj03_"""
    return ("bone_%s_" % p["name"].lower()) if p.get("name") else ("bone_obj%02d_" % p["id"])


# ---------------------------------------------------------------- 세컨더리 웨이트 참고값 (10/30)
# C:\claude\test\rig_test 완성 파일(기본 의상 18개)에서 뽑은 세컨더리 본 웨이트 모양 (secondary_weight_ref.json, 이 파일 옆).
# 참고값: 위아래 마디 섞임 폭 / 옆 체인 섞임 비율 / 체인 위쪽에서 몸(부모 Bip) 섞임 길이. 파일이 없으면 아래 기본값.
REF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secondary_weight_ref.json")
REF_DEFAULT = {"skirt": dict(along_blend=0.23, side_blend=0.31, bip_mixed_top=0.09),
               "cape": dict(along_blend=0.23, side_blend=0.27, bip_mixed_top=0.06),
               "hair": dict(along_blend=0.47, side_blend=0.15, bip_mixed_top=0.54),
               "etc": dict(along_blend=0.18, side_blend=0.11, bip_mixed_top=0.23)}
_REF = {}


def load_ref():
    m = os.path.getmtime(REF_PATH) if os.path.exists(REF_PATH) else 0
    if _REF.get("m") == m and "k" in _REF:
        return _REF["k"]
    out = {k: dict(v) for k, v in REF_DEFAULT.items()}
    try:
        for k, v in json.load(open(REF_PATH, encoding="utf-8")).get("kinds", {}).items():
            if k in out:
                out[k].update({x: float(v[x]) for x in ("along_blend", "side_blend", "bip_mixed_top") if x in v})
    except Exception as e:
        print("[object_bones] 웨이트 참고값 못 읽음:", e)
    _REF.update(m=m, k=out)
    return out


def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _poly_proj(P, J):
    """points -> (distance to the polyline J, position along it in segment units: joint i = i)"""
    J = np.asarray(J, float)
    best_d = np.full(len(P), 1e18)
    best_s = np.zeros(len(P))
    for i in range(len(J) - 1):
        a, d = J[i], J[i + 1] - J[i]
        L2 = max(float(d @ d), 1e-12)
        f = np.clip((P - a) @ d / L2, 0, 1)
        e = np.linalg.norm(P - (a + f[:, None] * d), axis=1)
        m = e < best_d
        best_d[m] = e[m]
        best_s[m] = i + f[m]
    return best_d, best_s


def _along(s, nb, hw):
    """chain weights at s (joints at integers, bone k spans [k, k+1]): one bone in the middle,
    straight blend within hw of a joint (50:50 on the joint)"""
    x = min(max(float(s), 0.0), float(nb) - 1e-6)
    k = min(int(x), nb - 1)
    f = x - k
    if f < hw and k > 0:
        o = 0.5 * (1 - f / hw)
        return {k: 1 - o, k - 1: o}
    if f > 1 - hw and k < nb - 1:
        o = 0.5 * (1 - (1 - f) / hw)
        return {k: 1 - o, k + 1: o}
    return {k: 1.0}


def ref_weights(W, CD, kind, bip, Pw, limit=4):
    """one part's chain weights shaped like the finished files.
    CD = [(vids, s, names, J)] per chain (s: joint i = i), bip = parent body bone for the top blend (None = none).
    참고값은 '정점 몇 %가 섞였나' 이라서, 이 파트 정점 분포에서 그 비율이 나오게 폭을 정함 (메쉬 밀도가 고르지 않아도 맞게)"""
    R = load_ref().get(kind if kind in ("skirt", "cape") else "etc")
    side = R["side_blend"] if len(CD) > 1 else 0.0
    # 위아래 마디 섞임 폭: 가운데 마디 경계까지 거리의 분위수
    dj = []
    for vids, s, names, J in CD:
        nb = len(names)
        if nb > 1:
            x = np.clip(s, 0, nb)
            d = np.abs(x - np.clip(np.round(x), 1, nb - 1))
            dj.append(d)
    hw = 0.15
    if dj:
        dj = np.concatenate(dj)
        hw = float(np.clip(np.quantile(dj, min(R["along_blend"], 0.95)) / 0.9, 0.05, 0.5))
    # 몸(부모 Bip) 섞임: 체인 위쪽 1/4 정점 중 참고 비율만큼, 맨 위 1 → 아래로 0
    pos_all = np.concatenate([np.asarray(s, float) / max(len(n), 1) for _, s, n, _ in CD])
    top = pos_all[pos_all < 0.25]
    zb = float(np.quantile(top, min(R["bip_mixed_top"], 0.95)) / 0.95) if (bip and len(top) and R["bip_mixed_top"] > 0) else 0.0
    if bip and R["bip_mixed_top"] > 0:
        zb = max(zb, R["bip_mixed_top"] * 0.25)     # 체인 시작 위(허리 밴드 등) 정점이 몰려 있어도 최소 이만큼은 섞음
    zb0 = 0.0                                        # 체인 시작점(과 그 위) = 몸 본 100%
    proj = []
    for ci, (vids, s, names, J) in enumerate(CD):
        P = Pw[np.asarray(vids, dtype=np.int64)]
        dn, sn, cn = np.full(len(P), 1e18), np.zeros(len(P)), np.full(len(P), -1)
        if side > 0:
            for cj, (_, _, _, J2) in enumerate(CD):
                if cj == ci:
                    continue
                d2, s2 = _poly_proj(P, J2)
                m = d2 < dn
                dn[m], sn[m], cn[m] = d2[m], s2[m], cj
        d1, _ = _poly_proj(P, J)
        proj.append((d1, dn, sn, cn))
    thr = 0.5
    if side > 0:
        T = np.concatenate([d1 / np.maximum(d1 + dn, 1e-12) for d1, dn, _, _ in proj])
        if len(T):
            q = float(np.quantile(T, 1 - min(side, 0.95)))
            thr = float(np.clip((q - 0.1) / 0.8, 0.0, 0.45))     # 옆 체인 몫이 0.1 넘는 정점이 참고 비율만큼
    nmix = 0
    for ci, (vids, s, names, J) in enumerate(CD):
        d1, dn, sn, cn = proj[ci]
        nb = len(names)
        for j, vi in enumerate(vids):
            w = {names[k]: x for k, x in _along(s[j], nb, hw).items()}
            if side > 0 and cn[j] >= 0:
                t = d1[j] / max(d1[j] + dn[j], 1e-12)
                if t > thr:
                    wn = 0.5 * min((t - thr) / max(0.5 - thr, 1e-6), 1.0)
                    on = CD[cn[j]][2]
                    w = {n: x * (1 - wn) for n, x in w.items()}
                    for k, x in _along(sn[j], len(on), hw).items():
                        w[on[k]] = w.get(on[k], 0.0) + wn * x
                    nmix += 1
            if zb > zb0:
                pos = float(s[j]) / max(nb, 1)
                if pos < zb:
                    wb = float(np.clip((zb - pos) / (zb - zb0), 0.0, 1.0))
                    w = {n: x * (1 - wb) for n, x in w.items()}
                    w[bip] = w.get(bip, 0.0) + wb
            it = sorted(w.items(), key=lambda kv: -kv[1])[:limit]
            tot = sum(x for _, x in it) or 1.0
            for n, x in it:
                if x / tot > 1e-4:
                    W.setdefault(n, []).append([int(vi), float(x / tot)])
    return nmix


def generate(ctx, arm, body, only=None):
    """confirmed parts -> bones in the Blender armature + weights kept for the skin send. returns (made, removed, verts)
    only: None = all parts again (old bones all go). A set of part prefixes = only those parts are made again;
    the other parts' bones and weights stay (Rig Tools [Max 수정]: one part at a time, the fixed ones are kept)"""
    parts = get_parts(ctx.scene)
    _LAST_BENT.clear()
    old = list(arm.get(ARM_KEY, []))
    try:
        pmap = json.loads(arm.get(PART_BONES_KEY, "{}") or "{}")
    except Exception:
        pmap = {}
    if only is None:
        removed, keep, pmap = old, [], {}
    else:
        cur = {part_prefix(p) for p in parts}
        drop = {k for k in pmap if k not in cur or k in only}
        rm = {n for k in drop for n in pmap[k]} | {n for n in old if any(n.startswith(k) for k in only)}
        removed = [n for n in old if n in rm]
        keep = [n for n in old if n not in rm]
        pmap = {k: v for k, v in pmap.items() if k not in drop}
    plans = []
    pre_bones, pre_w, pre_tm, unit, off = _preset_layout(ctx, arm, parts, body) if only is None else ({}, {}, {}, 1.0, Vector((0, 0, 0)))
    for p in parts:
        if only is not None and part_prefix(p) not in only:
            continue
        if p.get("name") in pre_bones:
            continue                       # Melitta preset part: f05 layout (below), no chain plan
        objs = [bpy.data.objects[n] for n in p["pieces"] if n in bpy.data.objects]
        if not objs:
            continue
        if p.get("struct") == "ring":
            pre_ = _flow().bip_prefix(arm) or "Bip01"
            nk_ = _bip_pos(arm, pre_, "Neck")
            pl = plan_ring(arm, body, objs, np.array(tuple(nk_)) if nk_ is not None else np.concatenate([_world_co(o) for o in objs]).mean(0),
                           p.get("parent") or _fallback_parent(arm, "cape", np.concatenate([_world_co(o) for o in objs])))
            p["labels"] = pl["labels"]
        else:
            pl = plan_part(arm, body, objs, p["chains"], p["segs"], p["axis"], p["single"], p.get("parent"), p.get("center", True),
                           p.get("straight", False), force_root=bool(p.get("force_root")), lr=bool(p.get("lr")))
        if pl:
            p["parent"] = pl["parent"]
            plans.append((p, pl))
    set_parts(ctx.scene, parts)
    # big parts first (small ones can hang on them); parts fixed onto another part's bone after that part
    plans.sort(key=lambda t: (str(t[0].get("parent_fix", "")).startswith("part:"), -t[1]["nv"]))
    if ctx.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    hs = arm.hide_select
    arm.hide_select = False
    for ob in list(ctx.view_layer.objects.selected):
        ob.select_set(False)
    arm.hide_set(False)
    arm.select_set(True)
    ctx.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    for n in removed:
        b = eb.get(n)
        if b:
            eb.remove(b)
    # 다시 만드는 파트 이름으로 시작하는 본은 기록에 없어도 모두 지움 (남아 있으면 새 본이 bone_..001 처럼 이름이 바뀜)
    redo = tuple(part_prefix(p) for p, pl in plans)
    if redo:
        for b in [b for b in eb if b.name.lower().startswith(redo)]:
            if b.name not in removed:
                removed.append(b.name)
            eb.remove(b)
    if pre_bones:
        # 2.7: 멜리타 프리셋 본도 같은 이름(대소문자·.001 무시)이 이미 있으면 지움. Max 에서 가져온 지난번 본이 남아 있으면
        #   새 본이 Bone_skirt_L1_01.001 처럼 생기고 웨이트·Max 보내기는 옛 본으로 가던 것 (블렌더를 새로 켠 뒤 다시 만들 때)
        pn = {b[0].lower() for lst in pre_bones.values() for b in lst}
        for b in [b for b in eb if re.sub(r"\.\d{3}$", "", b.name).lower() in pn]:
            if b.name not in removed:
                removed.append(b.name)
            eb.remove(b)
    inv = arm.matrix_world.inverted()
    made, W, segs_done, centers, shape = [], {}, [], [], {}
    # 마디 본 굵기를 메쉬에서 재려고 Max 단위로 (Max 연결이 없으면 Blender 단위 그대로)
    try:
        u_m, o_m = _flow()._max_xform(arm, _flow()._max_bridge())
        o_m = np.array(tuple(o_m))
    except Exception:
        u_m, o_m = 1.0, np.zeros(3)
    Pw_bl = _world_co(body)
    Pbody = Pw_bl * u_m + o_m
    pre = _flow().bip_prefix(arm) or "Bip01"
    sp1 = arm.data.bones.get(pre + " Spine1")
    sp1z = (arm.matrix_world @ sp1.head_local).z if sp1 else None

    def new_bone(name, h, t, parent, deform):
        b = eb.new(name)
        b.head, b.tail = inv @ Vector(h), inv @ Vector(t)
        b.parent, b.use_connect, b.use_deform = parent, False, deform
        made.append(name)
        return b
    for p, pl in plans:
        top = pl["hub"] if pl["hub"] is not None else pl["root_pt"]
        # one-chain parts hang on the nearest bone of a part made before (Melitta: bag, vial -> skirt bones)
        # 3단계: root 를 두는 1갈래 파트(force_root)도 같음 — 그 root 의 부모가 가까운 파트 본 (약병 → 치마 본)
        par, bd = None, ATTACH * U
        for n, h, t in (segs_done if (pl["hub"] is None or (p.get("force_root") and p.get("struct") in ("hang", "line"))) else []):
            d = t - h
            q = h + np.clip(np.dot(pl["root_pt"] - h, d) / max(np.dot(d, d), 1e-12), 0, 1) * d
            dist = np.linalg.norm(pl["root_pt"] - q)
            if dist < bd:
                par, bd = n, dist
        fix = p.get("parent_fix")                 # preset: a fixed parent ('Bip01 Spine2' or 'part:skirt:l1:01')
        if fix:
            if fix.startswith("part:"):
                _, pn, pl_lab, pn_i = fix.split(":")
                fix = "bone_%s_%s_%s" % (pn.lower(), pl_lab, pn_i)
            if eb.get(fix):
                par = fix
        if not par:
            par = pl["parent"]
            low = par.lower()
            if sp1z is not None and top[2] < sp1z and ("pelvis" in low or "spine" in low or "thigh" in low):
                par = pre + " Pelvis"     # lower body cloth hangs on the Pelvis (Melitta skirt)
        p["parent_used"] = par
        pid = part_prefix(p)
        m0 = len(made)
        parent = eb.get(par)
        hub = pl["hub"] if not p.get("no_root") else None
        if hub is not None:
            parent = new_bone(pid + "root", hub - np.array([0, 0, ROOT_LEN * U]), hub, parent, False)
        chain_names = []
        chain_data = []
        # 11/01: 같은 방향 글자의 번호는 앞(0°)에서 가까운 순서 → 좌우 거울 체인이 같은 번호 (BL1 ↔ BR1).
        # 예전엔 둘레를 한 방향으로 돌며 셌기 때문에 왼쪽은 앞→뒤, 오른쪽은 뒤→앞 순서가 되어 번호가 엇갈림
        ref = (pl["hub"] if pl["hub"] is not None else pl["center"])
        dvs = pl.get("dirs", [None] * len(pl["chains"]))
        vs = [dvs[ci] if dvs[ci] is not None else J.mean(0) - ref for ci, (_, J, _) in enumerate(pl["chains"])]
        labs = [p.get("label_map", {}).get(_dir(v), _dir(v)) for v in vs]
        num = {}
        for lab in set(labs):
            idx = sorted([ci for ci, l in enumerate(labs) if l == lab], key=lambda ci: abs(np.degrees(np.arctan2(vs[ci][0], -vs[ci][1]))))
            for k, ci in enumerate(idx, 1):
                num[ci] = k
        for ci, (vids, J, s) in enumerate(pl["chains"]):
            if p.get("labels") and ci < len(p["labels"]):
                base = pid + p["labels"][ci] + "_"
            else:
                lab = labs[ci]
                # 방향 글자만 대문자 (사용자 규칙 10/30): bone_skirt_FL1_01
                base = pid + "%s%d_" % (lab if p.get("preset") else lab.upper(), num[ci])
                if pl.get("bends") and ci < len(pl["bends"]) and pl["bends"][ci] > BEND_MAX:
                    _LAST_BENT.append((base.rstrip("_"), pl["bends"][ci]))
            prev = parent
            if hub is not None:
                prev = new_bone(base + "00", hub, J[0], parent, False)   # link bone, no weight
            names = []
            for i in range(len(J) - 1):
                prev = new_bone(base + "%02d" % (i + 1), J[i], J[i + 1], prev, True)
                names.append(prev.name)
                segs_done.append((prev.name, J[i], J[i + 1]))
            if p.get("end", True):
                d = (J[-1] - J[-2]) / max(np.linalg.norm(J[-1] - J[-2]), 1e-9)
                new_bone(base + "end", J[-1], J[-1] + d * END_LEN * U, prev, False)
            chain_names.append(names)
            # 마디 본 모양: 천에 납작하게 붙게 — 둘레 방향 폭 = width(최대 5), 천 두께 방향 = height(최대 2). 그 마디가 맡은 정점 폭을 재서 상한까지만
            try:
                Jm = np.asarray(J) * u_m + o_m
                refm = np.asarray(ref) * u_m + o_m
                rad = Jm.mean(0) - refm
                rad[2] = 0.0
                rad = rad / np.linalg.norm(rad) if np.linalg.norm(rad) > 1e-6 else np.array([0.0, -1.0, 0.0])
                Pm = Pbody[np.asarray(vids, dtype=np.int64)]
                for i, nm_ in enumerate(names):
                    a, b = Jm[i], Jm[i + 1]
                    dn = (b - a) / max(np.linalg.norm(b - a), 1e-9)
                    Z = rad - dn * float(rad @ dn)
                    if np.linalg.norm(Z) < 1e-6:
                        Z = np.array([0.0, 0.0, 1.0]) - dn * dn[2]
                    Z = Z / np.linalg.norm(Z)
                    Y = np.cross(Z, dn)
                    sel = (s >= i) & (s <= i + 1)
                    if sel.sum() >= 4:
                        Q = Pm[sel] - a
                        Q = Q - np.outer(Q @ dn, dn)
                        w_ = float(np.percentile(Q @ Y, 90) - np.percentile(Q @ Y, 10))
                        h_ = float(np.percentile(Q @ Z, 90) - np.percentile(Q @ Z, 10))
                    else:
                        w_, h_ = OB_MAX_W, OB_MAX_H
                    if pl.get("sector"):
                        # 2.7: 부채꼴로 나눈 체인(치마·망토)은 둘레 폭을 정점 퍼짐 대신 부채꼴 호 길이로 → 같은 높이는 같은 굵기
                        # (예전: 앞 트임 등으로 그 마디 정점이 적으면 가운데 체인 아래쪽이 0.8 로 아주 얇았음)
                        mm = 0.5 * (a + b) - refm
                        w_ = 2.0 * float(np.hypot(mm[0], mm[1])) * float(np.sin(0.5 * pl["sector"])) * 0.8
                    # Max 본 width 는 본의 Z 축 방향으로 그려짐 → Z 를 둘레 방향(Y)으로 둬서 넓은 쪽(5)이 천에 붙고 얇은 쪽(2)이 두께 방향 (10/30)
                    # 10/30: 메쉬를 따르되 width·height 모두 최대 5 (사용자 결정)
                    shape[nm_] = {"up": [float(x) for x in Y], "w": round(min(max(w_, 0.8), OB_MAX_W), 2),
                                  "h": round(min(max(h_, 0.8), OB_MAX_H), 2), "taper": 90.0}
            except Exception as e:
                print("[object_bones] 마디 본 굵기 계산 실패:", e)
            # weights: 완성 파일 참고값 모양으로 (파트의 체인을 다 만든 뒤 한 번에, 옆 체인과 섞어야 해서)
            chain_data.append((np.asarray(vids, dtype=np.int64), np.asarray(s, float), names, np.asarray(J, float)))
        if pl.get("sector"):
            # 2.7: 두께 쪽(h)도 같은 마디 번호끼리 중앙값으로 맞춤 (체인마다 제각각이던 것)
            for i in range(max((len(n_) for n_ in chain_names), default=0)):
                row = [shape[n_[i]] for n_ in chain_names if i < len(n_) and n_[i] in shape]
                if row:
                    hm = round(float(np.median([e["h"] for e in row])), 2)
                    for e in row:
                        e["h"] = hm
        if chain_data:
            pb = arm.data.bones.get(par) if par else None
            bipb = par if (pb is not None and pb.use_deform and par not in made) else None
            try:
                ref_weights(W, chain_data, p.get("kind") or "", bipb, Pw_bl)
            except Exception as e:
                print("[object_bones] 참고값 웨이트 실패, 선형으로:", e)
                for vids, s, names, J in chain_data:
                    for vi, ss in zip(vids, s):
                        for k, x in _along(ss, len(names), 0.5).items():
                            W.setdefault(names[k], []).append([int(vi), float(x)])
            # 3단계: 치마가 아닌 파트(망토)에 붙은 조각(bundle)은 가장 가까운 파트 정점 웨이트를 그대로 (ps_build '가까운 웨이트 따라가기').
            # 치마 파트의 bundle 은 아래 uv_refine 이 (u,v) 로 함께 계산
            if p.get("bundle") and not _is_skirt_prefix(pid, p.get("kind") or ""):
                try:
                    _follow_nearest(W, chain_data, [bpy.data.objects[n] for n in p["bundle"] if n in bpy.data.objects], Pw_bl)
                except Exception as e:
                    print("[object_bones] 붙은 조각 따라가기 실패:", e)
        for ci, (li, ri) in pl.get("centers", {}).items():
            centers.append([chain_names[ci], chain_names[li], chain_names[ri]])
        pmap[pid] = made[m0:]
    # Melitta preset parts: f05 bones in their Bip anchor's frame (Max) -> this skeleton, f05 weights of the part vertices
    if pre_bones:
        lower = ctx.window_manager.msr_ob_lower
        own = {b[0] for lst in pre_bones.values() for b in lst}

        def nm(n):
            return n.lower() if lower and n in own else n

        def to_bl(a, l):
            r = pre_tm[a]
            pm = [l[0] * r[0][k] + l[1] * r[1][k] + l[2] * r[2][k] + r[3][k] for k in range(3)]
            return (Vector(pm) - off) / unit
        todo = [b for p in parts if p.get("name") in pre_bones for b in pre_bones[p["name"]]]
        for p in parts:
            if p.get("name") in pre_bones:
                p["parent_used"] = pre_bones[p["name"]][0][1]
        while todo:
            rest = [b for b in todo if not (b[1] == b[2] or eb.get(nm(b[1])))]
            if len(rest) == len(todo):
                break                          # parent missing (should not happen)
            for n, par, a, h, t, deform in [b for b in todo if b not in rest]:
                new_bone(nm(n), to_bl(a, h), to_bl(a, t), eb.get(nm(par)), deform)
            todo = rest
        for vi, d in pre_w.items():
            for n, w in d.items():
                W.setdefault(nm(n), []).append([int(vi), w])
        # f05 roll / size: bone Z axis in the anchor's frame -> Max world (the push builds the bone with it)
        try:
            sh = json.load(open(PRESET, encoding="utf-8")).get("shape", {})
        except Exception:
            sh = {}
        for lst in pre_bones.values():
            for n, par, a, h, t, deform in lst:
                e = sh.get(n)
                if e and nm(n) in made:
                    r, z = pre_tm[a], e["z"]
                    shape[nm(n)] = {"up": [z[0] * r[0][k] + z[1] * r[1][k] + z[2] * r[2][k] for k in range(3)],
                                    "w": e["w"], "h": e["h"], "taper": e["taper"]}
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.hide_select = hs
    # 11/01: 치마 파트(프리셋 포함)는 (u,v) 로 다시 계산
    # 한 파트만 다시 만들 때는 다른 파트의 uv 정점 표시를 남김 (치마 뒤 다른 파트를 다시 만들면 치마가 경계 섞기에 다시 뭉개지던 것)
    prev_uv = set(uv_verts(ctx.scene)) if only is not None else set()
    try:
        extra = {}
        for p in parts:
            for n in p.get("bundle") or []:
                o = bpy.data.objects.get(n)
                if o is not None and o.data and "ob_vid" in o.data.attributes:
                    extra.setdefault(part_prefix(p), []).extend(int(v) for v in _vids(o))
        uv_refine(W, arm, body, [part_prefix(p) for p in parts if (only is None or part_prefix(p) in only)
                                 and _is_skirt_prefix(part_prefix(p), p.get("kind") or p.get("name") or "")], scene=ctx.scene, extra=extra)
    except Exception as e:
        print("[object_bones] uv 다듬기 실패 (ref 값 그대로):", e)
    if prev_uv:
        redo_v = {int(v) for lst in W.values() for v, _ in lst}
        ctx.scene[UV_KEY] = json.dumps(sorted((prev_uv - redo_v) | set(uv_verts(ctx.scene))))
    # 집 확인 (11/01): 골반 둘레 낮은 고리 띠를 Pelvis 100% 로 (recommend_parts PELVIS_KEY). 전체 다시 만들 때만
    try:
        pv_names = json.loads(ctx.scene.get(PELVIS_KEY, "[]") or "[]") if only is None else []
        pvn = pre + " Pelvis"
        # 2.5: 없는 조각 이름은 건너뜀 (예전엔 KeyError 로 고리 띠 처리 전체가 빠짐)
        pv = {int(v) for n in pv_names if n in bpy.data.objects for v in _vids(bpy.data.objects[n])} if pvn in arm.data.bones else set()
        if pv:
            W = {n: [e for e in lst if int(e[0]) not in pv] for n, lst in W.items()}
            W = {n: lst for n, lst in W.items() if lst}
            W.setdefault(pvn, []).extend([int(v), 1.0] for v in sorted(pv))
            print("[object_bones] 골반 고리 띠 %d조각 정점 %d → %s 100%%" % (len(pv_names), len(pv), pvn))
    except Exception as e:
        print("[object_bones] 골반 고리 띠 Pelvis 웨이트 실패:", e)
    nv = len({v for lst in W.values() for v, _ in lst})
    auto_par = {n: (arm.data.bones[n].parent.name if arm.data.bones[n].parent else "") for n in made}
    if only is not None:
        # keep the other parts: their weights (minus the vertices the new part took), parents, shapes
        try:
            prevW = json.loads(ctx.scene.get(W_KEY, "{}") or "{}")
        except Exception:
            prevW = {}
        taken = {v for lst in W.values() for v, _ in lst}
        rmset = set(removed)
        for n, lst in prevW.items():
            if n in rmset or n in W:
                continue
            lst = [e for e in lst if e[0] not in taken]
            if lst:
                W[n] = lst
        try:
            ap = json.loads(arm.get(AUTO_PARENT_KEY, "{}") or "{}")
        except Exception:
            ap = {}
        ap = {k: v for k, v in ap.items() if k not in rmset}
        ap.update(auto_par)
        auto_par = ap
        try:
            sh0 = json.loads(arm.get(SHAPE_KEY, "{}") or "{}")
        except Exception:
            sh0 = {}
        sh0 = {k: v for k, v in sh0.items() if k not in rmset}
        sh0.update(shape)
        shape = sh0
    arm[ARM_KEY] = [n for n in keep if n not in removed and n in arm.data.bones] + made
    arm[PART_BONES_KEY] = json.dumps(pmap)
    arm[CENTER_KEY] = json.dumps(centers)
    arm[SHAPE_KEY] = json.dumps(shape)
    arm[AUTO_PARENT_KEY] = json.dumps(auto_par)
    ctx.scene[W_KEY] = json.dumps(W)
    for n in removed:
        g = body.vertex_groups.get(n)
        if g and n not in made:
            body.vertex_groups.remove(g)
    return made, removed, nv


# ---------------------------------------------------------------- (u,v) 웨이트 다듬기 (11/01, uv_weights.py 이 파일 옆)
# 치마 종류 파트(긴 코트 포함)는 ref_weights·프리셋 값 대신 겹친 조각 묶음을 한 표면으로 보고 (u 둘레 각도, v 높이) 로 다시 계산.
# 겹친 겉·안감·띠가 같은 자리면 같은 웨이트, 같은 높이 줄은 같은 마디, 윗단은 옆 몸 정점 값으로 이어짐. 치마 외 파트는 그대로.
UV_ON = True
UV_V_MODE = "height"       # "geodesic" = 메쉬 위 길이 기준 (접힌 천·트인 앞섶용)
UV_TOP_CHAIN = 0.0         # 윗단에 체인을 남기는 비율 (작업자식 0.5). 0 = 첫 마디 위는 몸 100%
UV_INNER = True            # 코트가 감싸는 안쪽 별도 조각(속치마)도 묶음에 (카미엘)
UV_KEY = "msr_uv_verts"    # scene: json [정점] uv 로 계산한 정점 → 스킨 적용의 경계 그라데이션(smooth_boundaries)이 건너뜀 (이미 매끈, 겹끼리 같게 유지)


def _is_skirt_prefix(pre, kind=""):
    return "skirt" in (kind or "").lower() or "skirt" in (pre or "").lower()


def uv_verts(scene):
    try:
        return [int(v) for v in json.loads(scene.get(UV_KEY, "[]") or "[]")]
    except Exception:
        return []


def uv_refine(W, arm, body, prefixes, scene=None, extra=None, log=None):
    """W {bone: [[v, w]]} 의 치마 파트(prefixes 중 skirt) 정점 웨이트를 uv_weights 로 바꿔 넣음 (W 를 고침). returns {prefix: 정점 수}
    extra: {prefix: [정점]} 추천 단계에서 '겹친 조각' 으로 묶은 정점 (그 조각 전체를 묶음에 넣음)"""
    say = log or (lambda *a: print("[object_bones uv]", *a))
    if scene is not None:
        scene[UV_KEY] = "[]"
    if not UV_ON or not prefixes:
        return {}
    try:
        import uv_weights as UVW
    except Exception as e:
        say("uv_weights 없음:", e)
        return {}
    me = body.data
    nv = len(me.vertices)
    P = _world_co(body) / U                                  # Max 단위 (거리 기준이 Max 단위)
    F = [tuple(p.vertices) for p in me.polygons]
    lab = UVW.islands(nv, F)
    mw = arm.matrix_world
    bones = arm.data.bones
    # 지금 몸 웨이트 (윗단 옆 몸 정점 값을 빌림)
    names = {g.index: g.name for g in body.vertex_groups}
    deform = {g.index for g in body.vertex_groups if g.name in bones and bones[g.name].use_deform}
    body_w = {}
    for v in me.vertices:
        d = {names[e.group]: e.weight for e in v.groups if e.group in deform and e.weight > 0}
        if d:
            body_w[v.index] = d
    # W → 정점별
    Wd = {}
    for n, lst in W.items():
        for v, w in lst:
            Wd.setdefault(int(v), {})[n] = Wd.get(int(v), {}).get(n, 0.0) + float(w)
    done = {}
    for pre in prefixes:
        pl = pre.lower()
        ch = {}
        for n in W:
            m = _CH_RE.match(n)
            if m and m.group("pre").lower() == pl and m.group("i") != "00" and n in bones and bones[n].use_deform:
                ch.setdefault(m.group("ch"), []).append((int(m.group("i")), n))
        if len(ch) < 2:
            continue
        chains = []
        for c, lst in sorted(ch.items()):
            lst = [n for _, n in sorted(lst, key=lambda t: t[0])]
            # 마디 점 = 각 본의 머리 (꼬리는 본 길이가 짧으면 다음 머리와 다름: 프리셋 f05 본) + 끝 = _end 머리(없으면 마지막 꼬리)
            J = [np.array(tuple(mw @ bones[n].head_local)) / U for n in lst]
            endb = bones.get(lst[-1].rsplit("_", 1)[0] + "_end")
            J.append(np.array(tuple(mw @ (endb.head_local if endb else bones[lst[-1]].tail_local))) / U)
            chains.append((lst, np.array(J)))
        cn = {n for lst, _ in chains for n in lst}
        # 윗단에서 섞을 몸 본: 첫 마디의 부모를 따라 올라가 처음 만나는 몸 본
        parent = None
        b = bones[chains[0][0][0]].parent
        while b is not None:
            if b.use_deform and not b.name.lower().startswith(pl) and not _CH_RE.match(b.name):
                parent = b.name
                break
            b = b.parent
        ex = (extra or {}).get(pre) or (extra or {}).get(pl) or []
        isl, main, inner = UVW.part_bundle(P, lab, Wd, cn, chains, inner=UV_INNER, log=say,
                                           extra_isl=sorted({int(lab[int(v)]) for v in ex if 0 <= int(v) < nv}))
        if not isl:
            continue
        part_vids = np.where(np.isin(lab, isl))[0]
        say("%s: J0 %s .. Jend %s | part z %.1f~%.1f, xy centre %s" % (pre, np.round(chains[0][1][0], 1).tolist(), np.round(chains[0][1][-1], 1).tolist(),
            P[part_vids, 2].min(), P[part_vids, 2].max(), np.round(P[part_vids, :2].mean(0), 1).tolist()))
        Wn, info = UVW.uv_part_weights(P, F, part_vids, chains, body_w=body_w, parent_bone=parent, lab=lab,
                                      v_mode=UV_V_MODE, top_mode="nearest", top_chain=UV_TOP_CHAIN, log=say)
        pv = set(int(v) for v in part_vids)
        for n in list(W):
            W[n] = [e for e in W[n] if int(e[0]) not in pv]
            if not W[n]:
                del W[n]
        for v, d in Wn.items():
            Wd[v] = dict(d)
            for n, w in d.items():
                W.setdefault(n, []).append([int(v), float(w)])
        done[pre] = len(Wn)
        say("%s: 묶음 조각 %d (주 %d, 안쪽 %s) 정점 %d 다시 계산" % (pre, len(isl), main, inner, len(Wn)))
        if scene is not None:
            scene[UV_KEY] = json.dumps(sorted(set(uv_verts(scene)) | set(int(v) for v in Wn)))
    return done


def recover_weights(scene, arm, body):
    """new Blender session (nothing kept from ④): take the object bone weights that ① brought from the Max skin,
    so ③ can put them back after the body weights. Object bones = Melitta preset names or bone_objNN_*.
    returns the number of vertices kept (0 = nothing to do)"""
    if json.loads(scene.get(W_KEY, "{}") or "{}") or arm.get(ARM_KEY):
        return 0
    own = set()
    if os.path.exists(PRESET):
        own = {b[0] for pp in json.load(open(PRESET, encoding="utf-8"))["parts"] for b in pp.get("bones", [])}
    own |= {n.lower() for n in own}
    obn = [b for b in arm.data.bones if b.name in own or re.match(r"bone_obj\d+_", b.name, re.I)]
    if not obn:
        return 0
    names = {g.index: g.name for g in body.vertex_groups}
    deform = {g.index for g in body.vertex_groups if g.name in arm.data.bones and arm.data.bones[g.name].use_deform}
    obg = {g.index for g in body.vertex_groups if g.name in {b.name for b in obn}}
    W = {}
    nv = 0
    for v in body.data.vertices:
        if any(e.group in obg and e.weight > 0 for e in v.groups):
            nv += 1
            for e in v.groups:
                if e.group in deform and e.weight > 0:
                    W.setdefault(names[e.group], []).append([v.index, float(e.weight)])
    if not nv:
        return 0
    obn.sort(key=lambda b: len(b.parent_recursive))
    arm[ARM_KEY] = [b.name for b in obn]
    scene[W_KEY] = json.dumps(W)
    scene[ORIG_KEY] = "{}"
    return nv



# ---------------------------------------------------------------- 고른 면 → 자연스럽게 넓히기 (10/30)
# 파트 면은 '본을 만들려고 잡은 면' 이지 웨이트 경계가 아님 (사용자 10/30). 웨이트는 이렇게 넓힘:
#  - 조각(떨어진 메쉬 덩어리)의 SPREAD_ISLAND 이상이 파트면 → 그 조각 전체 (나머지 정점은 가장 가까운 파트 정점 값)
#  - 파트에 붙은 작은 조각(밑단 레이스·리본 등, SPREAD_SMALL 미만, SPREAD_ATTACH 안에 붙음) → 붙은 자리 값으로 통째로
#  - 일부만 잡힌 큰 조각 → 경계에서 SPREAD_BAND 까지 몸 웨이트와 서서히 섞음
SPREAD_ISLAND = 0.3
SPREAD_SMALL = 300
SPREAD_ATTACH = 2.5     # Max 단위
SPREAD_BAND = 4.0       # Max 단위
SPREAD_LAYER = 2.5      # Max 단위: 이 안에 파트 정점이 있으면 '겹친 천'
SPREAD_LAYER_SHARE = 0.6  # 조각 정점 중 이만큼이 파트에 겹쳐야 같은 파트로 봄
BODY_TOKEN = "__body__"
_ARM_TOP = re.compile(r"(upperarm|uparm|forearm|foretwist|hand|finger|elbow|clavicle|armpit)", re.I)
_UPPER_TOP = re.compile(r"(spine|bast|breast|neck|clavicle|head)", re.I)
_LEG_TOP = re.compile(r"(thigh|calf|foot|toe|knee|leg_)", re.I)


def spread_weights(W, body):
    """W {bone: [[v, w]]} -> (W2 with extra vertices, number added). BODY_TOKEN = 그 정점 원래 몸 웨이트 몫"""
    from mathutils.kdtree import KDTree
    me = body.data
    nv = len(me.vertices)
    V = {}
    for n, lst in W.items():
        for v, w in lst:
            if 0 <= v < nv:
                V.setdefault(int(v), {})[n] = V.get(int(v), {}).get(n, 0.0) + float(w)
    if not V:
        return W, 0
    lab = _islands(me)
    sizes = np.bincount(lab)
    P = _world_co(body)
    # 넓힐 정점의 지금 몸 웨이트에서 가장 큰 본: 팔(어떤 파트든)·다리(치마 아닌 파트)를 따르는 정점은 넓히지 않음
    # (소매·다리 메쉬가 장식 파트에 끌려가 팔·다리를 안 따라가는 것 방지, 10/30)
    gname = {g.index: g.name for g in body.vertex_groups}
    top = [""] * nv
    for v in me.vertices:
        best = max(((gname[e.group], e.weight) for e in v.groups), key=lambda t: t[1], default=("", 0.0))
        top[v.index] = best[0]

    def ok(i, src_w):
        tb = top[i]
        if _ARM_TOP.search(tb):
            return False
        skirt = any("skirt" in n.lower() for n in src_w)
        if not skirt and _LEG_TOP.search(tb):
            return False
        return True
    cov = np.zeros(nv, dtype=bool)
    cov[list(V)] = True
    ncov = np.bincount(lab, weights=cov.astype(float), minlength=len(sizes))
    add = {}

    def pre_of(w):
        b = max(w, key=w.get) if w else ""
        m = _CH_RE.match(b)
        return m.group("pre").lower() if m else b.lower()
    ptop = {}                                       # 파트(본 이름 앞부분)별 고른 면 맨 위 높이
    for i, w in V.items():
        k_ = pre_of(w)
        ptop[k_] = max(ptop.get(k_, -1e18), float(P[i, 2]))

    def kd_of(idx):
        kd = KDTree(len(idx))
        for j, i in enumerate(idx):
            kd.insert(P[i].tolist(), j)
        kd.balance()
        return kd
    # 1) 대부분 잡힌 조각: 조각 전체
    for k in np.where((ncov > 0) & (ncov < sizes) & (ncov >= SPREAD_ISLAND * sizes))[0]:
        vs = np.where(lab == k)[0]
        cv = [i for i in vs if cov[i]]
        kd = kd_of(cv)
        ztop = float(P[cv, 2].max()) + 0.5 * U        # 고른 면보다 위(허리 밴드 쪽)로는 넓히지 않음
        for i in vs:
            if not cov[i] and P[i, 2] <= ztop:
                _, j, _ = kd.find(P[i].tolist())
                if ok(i, V[cv[j]]):
                    add[int(i)] = dict(V[cv[j]])
    # 2) 파트에 매달린 작은 조각 (두 번: 장식 위 장식). 몸(파트 아닌 정점)에 더 가까이 붙은 조각은 그대로 몸을 따름
    for _ in range(2):
        idx = sorted(set(V) | set(add))
        src = {**V, **add}
        kd = kd_of(idx)
        rest = [i for i in range(nv) if i not in src and sizes[lab[i]] >= SPREAD_SMALL]   # 큰 몸 조각만 (장식끼리 붙은 건 상관없음)
        kdr = kd_of(rest) if rest else None
        lim = SPREAD_ATTACH * U
        for k in np.where((sizes < SPREAD_SMALL))[0]:
            vs = np.where(lab == k)[0]
            if any(int(i) in src for i in vs):
                continue
            best = None
            for i in vs:
                _, j, d = kd.find(P[i].tolist())
                if j is not None and d <= lim and (best is None or d < best[0]):
                    best = (d, idx[j])
            if not best:
                continue
            # 이 조각이 큰 몸 조각(파트 아님)에 붙은 거리: 파트보다 확실히 몸에 붙어 있으면 몸을 따름
            dr = min(kdr.find(P[i].tolist())[2] for i in vs) if kdr else 1e9
            if dr * 1.5 < best[0]:
                continue
            if not all(ok(i, src[best[1]]) for i in vs):
                continue
            # 매달린 조각만: 조각 가운데가 붙은 자리보다 위면 (벨트·허리 장식) 몸을 따름
            if float(P[vs, 2].mean()) > ptop.get(pre_of(src[best[1]]), 1e18) + 0.5 * U:
                continue
            # 붙은 자리가 체인 맨 위(몸 본과 반쯤 섞인 곳)면 벨트·허리 장식 → 몸을 따름
            sw = src[best[1]]
            if sum(x for n, x in sw.items() if _CH_RE.match(n)) < 0.25 * (sum(sw.values()) or 1.0):
                continue
            for i in vs:
                add[int(i)] = dict(src[best[1]])
    # 3) 일부만 잡힌 큰 조각: 경계 띠에서 몸과 섞음
    band = SPREAD_BAND * U
    for k in np.where((ncov > 0) & (ncov < SPREAD_ISLAND * sizes))[0]:
        vs = np.where(lab == k)[0]
        cv = [i for i in vs if cov[i]]
        kd = kd_of(cv)
        ztop = float(P[cv, 2].max()) + 0.5 * U
        for i in vs:
            if cov[i] or int(i) in add or P[i, 2] > ztop:
                continue
            _, j, d = kd.find(P[i].tolist())
            if d < band and ok(i, V[cv[j]]):
                a = 1.0 - d / band
                a = a * a * (3 - 2 * a)
                w = {n: x * a for n, x in V[cv[j]].items()}
                w[BODY_TOKEN] = 1.0 - a
                add[int(i)] = w
    # 4) 10/31: 파트 면에 안 들었지만 파트 조각에 바로 겹친 큰 조각 (2중 치마의 속·겉 겹: 떨어진 조각이라 면 선택에서 빠짐)
    #    → 가까운 파트 정점(고른 면만) 값을 그대로. 고른 면 맨 위보다 위는 몸 그대로. 맨 마지막이라 1)~3) 결과는 안 바뀜
    cv_all = sorted(V)
    kd_all = kd_of(cv_all)
    lay = SPREAD_LAYER * U
    for k in np.where((ncov == 0) & (sizes >= SPREAD_SMALL))[0]:
        vs = np.where(lab == k)[0]
        if any(int(i) in add for i in vs):
            continue
        hit = [kd_all.find(P[i].tolist()) for i in vs]
        if np.mean([h[2] is not None and h[2] < lay for h in hit]) < SPREAD_LAYER_SHARE:
            continue
        for i, h in zip(vs, hit):
            src_w = V[cv_all[h[1]]]
            if P[i, 2] <= ptop.get(pre_of(src_w), 1e18) + 0.5 * U and ok(i, src_w):
                add[int(i)] = dict(src_w)
    if not add:
        return W, 0
    W2 = {n: list(lst) for n, lst in W.items()}
    for i, w in add.items():
        for n, x in w.items():
            if x > 1e-4:
                W2.setdefault(n, []).append([i, float(x)])
    return W2, len(add)


_PART_BONE = re.compile(r"^bone_(skirt\d*|cape\d*|obj\d+)_", re.I)


def drop_dead(W, gone, body):
    """2.3 수정안 A (정현 11-01): 기록 W 에서 지금 없는 본(gone) 을 뺄 때, 그 본 몫이 있던 정점은 남은 값(Pelvis 0.05 등)을
    100% 로 맞추지 않고 정점 전체를 기록에서 뺌 -> 몸 웨이트로 다시 계산. 같은 떨어진 조각(메시 덩어리)에서 몸 본만 기록된
    정점(체인 시작의 부모 본 몫)도 같이 뺌 (위젤 손목 장식: 일부 정점만 Pelvis 100% 로 남아 팔을 들면 늘어나던 것).
    returns (새 W, 뺀 정점 수)"""
    gone = set(gone)
    dead = {int(v) for n in gone for v, w in W.get(n, []) if w > 0}
    if dead and body is not None:
        me = body.data
        par = np.arange(len(me.vertices))

        def find(a):
            while par[a] != a:
                par[a] = par[par[a]]
                a = par[a]
            return a
        ev = np.empty(len(me.edges) * 2, dtype=np.int64)
        me.edges.foreach_get("vertices", ev)
        for a, b in ev.reshape(-1, 2):
            ra, rb = find(a), find(b)
            if ra != rb:
                par[ra] = rb
        isl = {find(v) for v in dead if v < len(par)}
        haspart = {int(v) for n, lst in W.items() if n not in gone and _PART_BONE.match(n) for v, w in lst if w > 0}
        rec = {int(v) for lst in W.values() for v, _ in lst}
        dead |= {v for v in rec if v not in haspart and v < len(par) and find(v) in isl}
    W = {n: [e for e in lst if int(e[0]) not in dead] for n, lst in W.items() if n not in gone}
    return {n: lst for n, lst in W.items() if lst}, len(dead)


def apply_weights(scene, arm, body):
    """object bone weights replace the body weights of those vertices (on '생성', ③ and the skin send).
    The body weights they replace are kept (scene ORIG_KEY) so a vertex that leaves a part gets them back.
    10/30: 고른 면 밖으로 자연스럽게 넓힘 (spread_weights). BODY_TOKEN 몫은 원래 몸 웨이트로"""
    try:
        W = json.loads(scene.get(W_KEY, "{}"))
    except Exception:
        W = {}
    # 10/31: Max 본 목록에서 지운 파트는 본이 없는데 이 기록에 남아 있으면, 그 정점의 몸 웨이트를 지우고 없는 본만 넣어
    # 웨이트가 빈 채로 Max 에 감 (띠가 반은 손, 반은 골반에 남아 늘어남) → 지금 없는 본은 버리고 그 정점은 몸 웨이트 그대로
    live = {b.name for b in arm.data.bones if b.use_deform}
    # 2.3 (수정안 A): 없는 본 몫이 있던 정점은 남은 값으로 100% 맞추지 않고 정점 전체를 몸 웨이트로 (drop_dead)
    W, _nd = drop_dead(W, [n for n in W if n not in live and n != BODY_TOKEN], body)
    W = {n: lst for n, lst in W.items() if n in live}
    try:
        orig = {int(k): v for k, v in json.loads(scene.get(ORIG_KEY, "{}")).items()}
    except Exception:
        orig = {}
    try:
        W, _nsp = spread_weights(W, body)
    except Exception as e:
        print("[object_bones] 넓히기 실패:", e)
        _nsp = 0
    lock = preset_body_lock(body)
    if lock:
        W = {n: [e for e in lst if int(e[0]) not in lock] for n, lst in W.items()}
        W = {n: lst for n, lst in W.items() if lst}
    deform = {g.index for g in body.vertex_groups if g.name in arm.data.bones and arm.data.bones[g.name].use_deform}
    names = {g.index: g.name for g in body.vertex_groups}
    obn = set(arm.get(ARM_KEY, []))
    verts = {v for lst in W.values() for v, _ in lst}
    for vi in [v for v in orig if v not in verts]:          # no longer in a part: body weights back
        v = body.data.vertices[vi]
        for gi in [g.group for g in v.groups if g.group in deform]:
            body.vertex_groups[gi].remove([vi])
        for n, w in orig.pop(vi).items():
            (body.vertex_groups.get(n) or body.vertex_groups.new(name=n)).add([vi], w, "REPLACE")
    for vi in verts:
        if vi not in orig:
            orig[vi] = {names[g.group]: g.weight for g in body.data.vertices[vi].groups
                        if g.group in deform and g.weight > 0 and names[g.group] not in obn}
    scene[ORIG_KEY] = json.dumps(orig)
    if not W:
        return 0
    deform = {g.index for g in body.vertex_groups if g.name in arm.data.bones and arm.data.bones[g.name].use_deform}
    for vi in verts:
        v = body.data.vertices[vi]
        for gi in [g.group for g in v.groups if g.group in deform]:
            body.vertex_groups[gi].remove([vi])
    for n, lst in W.items():
        if n == BODY_TOKEN:
            for vi, a in lst:
                ow = orig.get(vi) or {}
                s = sum(ow.values()) or 1.0
                for bn, x in ow.items():
                    g = body.vertex_groups.get(bn) or body.vertex_groups.new(name=bn)
                    g.add([vi], a * x / s, "ADD")
            continue
        g = body.vertex_groups.get(n) or body.vertex_groups.new(name=n)
        for vi, w in lst:
            g.add([vi], w, "ADD")
    return len(verts)


# ---------------------------------------------------------------- 스킨 적용 때 웨이트 다시 만들기 (10/30)
# ② 로 만든 웨이트(scene W_KEY)는 Blender 에만 있어서, 그 사이 Blender 가 다른 파일 작업으로 정리되면 사라짐 →
# 스킨 적용 때 Max 에 있는 실제 본(손으로 다듬은 위치 그대로)과 Max 에 남은 파트 면 기록(7760·7761)으로 다시 계산.
_CH_RE = re.compile(r"^(?P<pre>.+_)(?P<ch>[A-Za-z]+\d+)_(?P<i>\d\d)$")


def weights_from_bones(scene, arm, body, marks, prefixes, limit=4):
    """marks: [(kind, [blender vertex ids])] per part, prefixes: [bone prefix] per part (same order).
    returns number of vertices given object bone weights (scene W_KEY is replaced)"""
    mw = arm.matrix_world
    Pw = _world_co(body)
    bones = arm.data.bones
    W = {}
    own = []
    nv = 0
    for (kind, vids), pre in zip(marks, prefixes):
        if not vids or not pre or pre == "none":
            continue
        chains = {}
        for b in bones:
            m = _CH_RE.match(b.name)
            if m and m.group("pre").lower() == pre.lower() and m.group("i") != "00" and b.use_deform:
                chains.setdefault(m.group("ch"), []).append((int(m.group("i")), b))
        if not chains:
            continue
        CH = []
        for ch, lst in sorted(chains.items()):
            lst = [b for _, b in sorted(lst, key=lambda t: t[0])]
            J = [np.array(tuple(mw @ lst[0].head_local))] + [np.array(tuple(mw @ b.tail_local)) for b in lst]
            CH.append(([b.name for b in lst], np.array(J), lst[0]))
        vids = np.array([v for v in vids if 0 <= v < len(Pw)], dtype=np.int64)
        if not len(vids):
            continue
        P = Pw[vids]
        D, S = [], []
        for names, J, _ in CH:
            d, s = _poly_proj(P, J)
            D.append(d); S.append(s)
        D = np.array(D); S = np.array(S)
        pick = np.argmin(D, axis=0)
        CD = []
        for ci, (names, J, b0) in enumerate(CH):
            m = pick == ci
            if m.any():
                CD.append((vids[m], S[ci][m], names, J))
            own += names
        # 체인 위쪽에서 섞일 몸 본: 첫 마디의 부모를 따라 올라가 처음 만나는 몸(이 파트가 아닌 변형) 본
        bip = None
        p = CH[0][2].parent
        while p is not None:
            if p.use_deform and not p.name.lower().startswith(pre.lower()):
                bip = None if _CH_RE.match(p.name) else p.name      # 다른 파트 본에 매달린 파트는 섞지 않음
                break
            p = p.parent
        k = "skirt" if "skirt" in (kind or pre).lower() else ("cape" if "cape" in (kind or pre).lower() else "etc")
        ref_weights(W, CD, k, bip, Pw, limit)
        nv += len(vids)
    if W:
        try:
            uv_refine(W, arm, body, [pre for (kind, vids), pre in zip(marks, prefixes) if pre and pre != "none" and _is_skirt_prefix(pre, kind)], scene=scene)
        except Exception as e:
            print("[object_bones] uv 다듬기 실패 (ref 값 그대로):", e)
        scene[W_KEY] = json.dumps(W)
        scene[ORIG_KEY] = "{}"
        arm[ARM_KEY] = list(dict.fromkeys(own))
    return nv

# ---------------------------------------------------------------- operators / UI

# ---------------------------------------------------------------- ③ 치마·망토 자동 (Max Rig Tools 버튼, 2026-10-29)
AUTO_SET = {"skirt": dict(chains=6, segs=6, axis="DOWN", center=True),
            "cape": dict(chains=3, segs=4, axis="DOWN", center=False)}


def auto_parts(ctx):
    """조각 나누기 → 조각마다 종류 판별 → 치마 조각끼리, 망토 조각끼리 묶어 파트 확정 (치마 6×6, 망토 3×4).
    이미 확정한 같은 종류 파트가 있으면 그대로 둠 (Blender 에서 고친 것 유지). returns 파트 설명 목록"""
    f = _flow()
    arm, body, face, tooth = f.flow_objects(ctx)
    if arm is None or body is None:
        raise RuntimeError("Bip·바디가 없어요")
    if ctx.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    wm = ctx.window_manager
    if not pieces():
        split(ctx, body, wm.msr_ob_min)
    pcs = pieces()
    if len(pcs) < 2:
        return []
    groups = {"skirt": [], "cape": []}
    pcs = [o for o in pcs if not o.name.startswith(MARK_PREFIX)]   # Max 지정 파트 조각은 제외
    if len(pcs) < 2:
        split(ctx, body, wm.msr_ob_min)
        pcs = pieces()
    for o in pcs:
        if len(o.data.vertices) < 30:
            continue
        k = guess_kind(arm, [o])
        if k in groups:
            groups[k].append(o)
    have = {q.get("kind") for q in get_parts(ctx.scene)}
    keys = ("msr_ob_chains", "msr_ob_segs", "msr_ob_axis", "msr_ob_single", "msr_ob_center", "msr_ob_kind")
    for k, objs in groups.items():
        if not objs or k in have:
            continue
        for o in list(ctx.view_layer.objects.selected):
            o.select_set(False)
        for o in objs:
            o.select_set(True)
        ctx.view_layer.objects.active = objs[0]
        old = [getattr(wm, a) for a in keys]
        st = AUTO_SET[k]
        try:
            wm.msr_ob_chains, wm.msr_ob_segs, wm.msr_ob_axis = st["chains"], st["segs"], st["axis"]
            wm.msr_ob_single, wm.msr_ob_center, wm.msr_ob_kind = False, st["center"], k.upper()
            pid = confirm(ctx)
            if pid is not None:
                parts = get_parts(ctx.scene)
                has_w = any(g.name in arm.data.bones for g in body.vertex_groups)
                for q in parts:
                    if q["id"] == pid:
                        q.update(chains=st["chains"], segs=st["segs"], axis=st["axis"], single=False, center=st["center"],
                                 kind=k, name=q.get("name") or k)
                        if not has_w:      # 새 캐릭터(웨이트 없음): 위치로 부모
                            q["parent"] = _fallback_parent(arm, k, np.concatenate([_world_co(x) for x in objs]))
                set_parts(ctx.scene, parts)
        finally:
            # 창 설정을 되돌리기 전에 선택을 풀어야 함 (설정이 바뀌면 선택된 파트에 덮어씀)
            for o in list(ctx.view_layer.objects.selected):
                o.select_set(False)
            for a, v in zip(keys, old):
                setattr(wm, a, v)
    for o in list(ctx.view_layer.objects.selected):
        o.select_set(False)
    _CACHE.clear()
    return ["%s 조각 %d개" % (_part_label(q), len(q["pieces"])) for q in get_parts(ctx.scene)]




# ---------------------------------------------------------------- ② 바디 전체에서 세컨더리 본이 필요한 조각 추천 (10/30)
_LIMB_RE = (("armL", r"L (Clavicle|UpperArm|Forearm|Hand|Finger)|LUpArm|LForeTwist"),
            ("armR", r"R (Clavicle|UpperArm|Forearm|Hand|Finger)|RUpArm|RForeTwist"),
            ("legL", r"L (Thigh|Calf|Foot|Toe)"), ("legR", r"R (Thigh|Calf|Foot|Toe)"), ("head", r"Head|Neck"))
REC_SMALL = 6.0       # 이보다 작은 조각(단추·장식 판)은 본 없이 (Max 단위 cm)
REC_TOUCH = 1.0       # 이보다 가까이 붙은 조각끼리는 한 파트
# 파츠 본 생성 범위 (11/01 정현: 물리 엔진이 아니면 작업자가 손으로 움직일 파츠에만 본). Max 기본 흐름 = PARTS_LEVEL
#   1 = 치마·망토(긴 코트·자켓 밑단 포함)·치마 위로 긴 앞판만 체인, 나머지 몸 웨이트
#   2 = 1 + 후드·큰 매달린 물건(LEVEL_HANG_MIN↑)·긴 끈·띠(LEVEL_STRAND_MIN↑) 를 1갈래 1~2마디
#   3 = 모두 (예전 방식). 소매(팔·다리를 감싸는 조각)는 어느 단계든 본 없음
PARTS_LEVEL = 2
LEVEL_HANG_MIN = 15.0     # 2단계: 매달린 물건은 높이·폭 중 큰 쪽이 이 이상(가방·약병 홀더)만. 작은 장식·배지는 몸
LEVEL_STRAND_MIN = 30.0   # 2단계: 끈·띠는 이 높이 이상만
LEVEL_SEG2_H = 20.0       # 2단계 간단 체인: 이 높이 미만이면 1마디, 이상이면 2마디
LEVEL_KEY = "msr_ob_level"   # scene: 마지막 자동 파츠 본 범위 (블렌더 패널 버튼 표시)
_LEVEL_NEXT = 0              # 블렌더 패널 범위 버튼이 이번 한 번만 쓸 범위 (0 = PARTS_LEVEL). 시험: 환경변수 MSR_PARTS_LEVEL
SLEEVE_ARM_D = 12.0      # 소매 조각 정점이 팔 본에서 이 거리 안이면 팔을 덮는 쪽 (나머지 = 등 뒤로 늘어진 천)
SKIRT_INNER_D = 12.0      # 2.5: 치마 높이 안의 조각이 가까운 본에서 이만큼(다리 쪽이 절반 넘으면 15cm) 떠 있으면 치마 안쪽 층(안감·속치마)으로 묶음
                          #      카미엘 바지(다리 쪽 55%, 10.6cm)는 다리 웨이트 그대로
SKIRT_BELOW_K = 0.3       # 2.8: 조각 맨 아래가 치마 밑단보다 (치마 높이 × 이 값) 넘게 내려가면 치마 묶음에서 뺌 (다리 옷)
                          #      시험 기록: 묶인 정상 조각은 최대 0.23 (세레나 뒤 리본), 세레나 다리 옷 OBP_002 는 1.20
SLEEVE_BACK_H = 20.0     # 등 뒤 쪽이 이 높이 이상 늘어져야 망토로 가름


def _level_keep(level, st):
    """recommend_parts 의 조각 묶음 구조(st) 를 이 단계에서 본으로 만들지: False = 몸 웨이트, "full" = 그대로, "simple" = 1갈래 1~2마디"""
    s = st["struct"]
    if s == "apron":                 # 짧은 앞치마는 앞에서 이미 빠짐 → 치마 위로 길게 늘어진 앞판 = 큰 부피
        return "full"
    if level <= 1:
        return False
    if s == "hood":
        return "simple"
    if s == "hang" and max(st["hz"], st["wdt"]) >= LEVEL_HANG_MIN:
        return "simple"
    if s == "strand" and st["hz"] >= LEVEL_STRAND_MIN:
        return "simple"
    return False


# ---------------------------------------------------------------- 3단계 (11/01): 치마·망토 밖 조각의 구조 종류 → shape_rules.py
#  ring 목 둘레 / hood 덮개·후드 / hang 매달린 물건 / strand 가닥·띠·사슬 / apron 앞치마 / flat 그 밖. 판정·체인 수·마디 수·변형은 shape_rules.
#  치마·망토 판정(guess_kind)·겹친 조각 묶음은 1.72/1.8 그대로. 모든 체인 root·_00·_end (force_root).
#  판정 근거 표: 환경변수 MSR_OB_DEBUG=<파일> 이면 조각마다 수치·결정을 그 파일에 씀.


def _split_piece(ctx, o, mask, suffixes):
    """조각 o 를 정점 마스크로 두 조각으로 가름 (True → suffixes[0], False → suffixes[1]). ob_vid 유지. 원래 조각은 지움.
    returns [새 조각 이름] (정점 4개 미만인 쪽은 안 만듦)"""
    col = bpy.data.collections.get(COL)
    me = o.data
    out = []
    for keep_mask, suf in ((mask, suffixes[0]), (~mask, suffixes[1])):
        keep = set(np.where(keep_mask)[0].tolist())
        if len(keep) < 4:
            continue
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in keep], context="VERTS")
        m2 = bpy.data.meshes.new("%s_%s" % (o.name, suf))
        bm.to_mesh(m2)
        bm.free()
        for s in o.material_slots:
            m2.materials.append(s.material)
        n = bpy.data.objects.new(m2.name, m2)
        n.matrix_world = o.matrix_world
        col.objects.link(n)
        out.append(n.name)
    bpy.data.objects.remove(o)
    if me.users == 0:
        bpy.data.meshes.remove(me)
    return out


def _z_overlap(a, b):
    """두 조각의 높이 범위가 작은 쪽 기준으로 얼마나 겹치는지 (0~1)"""
    lo, hi = max(a["zmin"], b["zmin"]), min(a["zmax"], b["zmax"])
    small = max(min(a["zmax"] - a["zmin"], b["zmax"] - b["zmin"]), 1e-6)
    return max(0.0, hi - lo) / small


def _body_parent(arm, P):
    """늘어진 장식의 부모: 파트 위쪽에서 가장 가까운 몸통 본 (Pelvis·Spine·Neck·Head·Clavicle). 팔·다리 본에는 안 붙임"""
    pre = _flow().bip_prefix(arm) or "Bip01"
    top = P[P[:, 2] >= np.percentile(P[:, 2], 90)].mean(0)
    best, bd = None, 1e18
    mw = arm.matrix_world
    for b in arm.data.bones:
        n = b.name
        if not n.startswith(pre + " ") or not re.search(r"Pelvis|Spine|Neck|Head|Clavicle", n) or "Nub" in n:
            continue
        h, tl = np.array(mw @ b.head_local), np.array(mw @ b.tail_local)
        d = tl - h
        q = h + np.clip(np.dot(top - h, d) / max(np.dot(d, d), 1e-12), 0, 1) * d
        dist = np.linalg.norm(top - q)
        if dist < bd:
            best, bd = n, dist
    return best or (pre + " Pelvis")


def _limb_of(n):
    for k, pat in _LIMB_RE:
        if re.search(pat, n):
            return k
    return "torso"


def recommend_parts(ctx, level=None, _keep_pieces=False):
    """바디를 조각으로 나눈 뒤, 조각마다 본이 필요한지 판단해서 파트를 정함 (본 생성은 generate). level: 생성 범위 1/2/3 (None = PARTS_LEVEL)
    - 치마·망토: 모양으로 판별 (guess_kind). 치마에 붙어 한 바퀴 도는 단 조각은 치마에 합침
    - 본 없음: 몸을 한 바퀴 감싸는 조각(상의·목깃·벨트·다리), 팔·다리 본에 바짝 붙은 조각(손·소매·신발), 6cm 미만 조각(단추)
    - 나머지(리본·가방·장식·끈): 붙어 있는 조각끼리 묶어 아래로 곧은 체인 (폭에 따라 1~4갈래, 길이에 따라 마디 2~6)
    returns (설명 목록, 뺀 조각 설명 목록)"""
    from mathutils.kdtree import KDTree
    level = int(level or _LEVEL_NEXT or os.environ.get("MSR_PARTS_LEVEL") or PARTS_LEVEL)
    ctx.scene[LEVEL_KEY] = level
    del LAST_MINI[:]
    f = _flow()
    arm, body, face, tooth = f.flow_objects(ctx)
    if arm is None or body is None:
        raise RuntimeError("Bip·바디가 없어요")
    if ctx.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    if not _keep_pieces:
        split(ctx, body, ctx.window_manager.msr_ob_min)
    pcs = [o for o in pieces() if len(o.data.vertices) >= 4]
    if not pcs:
        return [], []
    try:
        unit, off = f._max_xform(arm, f._max_bridge())
        off = np.array(tuple(off))
    except Exception:
        unit, off = 1.0, np.zeros(3)
    mw = arm.matrix_world
    pre = f.bip_prefix(arm) or "Bip01"
    segs_ = [(b.name, np.array(mw @ b.head_local) * unit + off, np.array(mw @ b.tail_local) * unit + off)
             for b in arm.data.bones if b.name.startswith(pre + " ") and "Nub" not in b.name and "Footsteps" not in b.name]
    bn = [s[0] for s in segs_]
    H = np.array([s[1] for s in segs_])
    T = np.array([s[2] for s in segs_])
    pel = H[bn.index(pre + " Pelvis")] if pre + " Pelvis" in bn else H.mean(0)
    D = T - H
    L2 = np.maximum((D * D).sum(1), 1e-9)

    def near_bone(Q):
        tt = np.clip(((Q[:, None, :] - H[None]) * D[None]).sum(2) / L2[None], 0, 1)
        d = np.linalg.norm(Q[:, None, :] - (H[None] + tt[..., None] * D[None]), axis=2)
        i = d.argmin(1)
        return i, d[np.arange(len(Q)), i]

    P = {o.name: _world_co(o) * unit + off for o in pcs}
    allv = np.concatenate([P[o.name] for o in pcs])
    owner = np.concatenate([[k] * len(P[o.name]) for k, o in enumerate(pcs)])
    kd = KDTree(len(allv))
    for i, p in enumerate(allv):
        kd.insert(p.tolist(), i)
    kd.balance()
    info = {}
    touch = {o.name: set() for o in pcs}
    for k, o in enumerate(pcs):
        Q = P[o.name]
        S = Q[::max(1, len(Q) // 300)]
        # 다른 조각과 붙어 있는지 (가까운 다른 조각)
        for q in S:
            for co, j, dist in kd.find_n(q.tolist(), 8):
                if owner[j] != k and dist < REC_TOUCH:
                    touch[o.name].add(pcs[owner[j]].name)
        bi, bd = near_bone(S)
        ch = collections.Counter(_limb_of(bn[i]) for i in bi)
        top, cnt = ch.most_common(1)[0]
        legs = (ch.get("legL", 0) + ch.get("legR", 0)) / len(S)
        c = Q.mean(0)
        ext = sorted([float(np.ptp(Q @ v)) for v in np.linalg.eigh(np.cov((Q - c).T))[1].T], reverse=True)
        ang = np.arctan2(Q[:, 1] - pel[1], Q[:, 0] - pel[0])
        cover = len(np.unique(np.floor((ang + np.pi) / (2 * np.pi) * 24).astype(int) % 24)) / 24.0
        # 3단계: 가장 많이 가까운 본의 축 둘레를 얼마나 감싸는지 (소매·장갑·부츠 = 1에 가깝고, 옆에 매달린 약병·어깨 뒤 망토 = 작음)
        # 그 본에서 10cm 안의 정점만 봄 (멀리 넓게 퍼진 망토가 팔 둘레를 '감싼' 것으로 나오지 않게)
        ib = collections.Counter(int(i) for i in bi).most_common(1)[0][0]
        ax_ = D[ib] / np.sqrt(L2[ib])
        e1_ = np.cross(ax_, [0.0, 0.0, 1.0] if abs(ax_[2]) < 0.9 else [1.0, 0.0, 0.0])
        e1_ /= max(np.linalg.norm(e1_), 1e-9)
        e2_ = np.cross(ax_, e1_)
        nearm = (bi == ib) & (bd < 10.0)
        R_ = S[nearm] - H[ib]
        la = np.arctan2(R_ @ e2_, R_ @ e1_)
        limb_cover = (len(np.unique(np.floor((la + np.pi) / (2 * np.pi) * 12).astype(int) % 12)) / 12.0) if len(R_) >= 4 else 0.0
        kdiag = []
        kind = guess_kind(arm, [o], diag=kdiag) if len(Q) >= 30 else ""
        # 소매 (11/01 정현: 팔·다리를 감싸는 조각은 어느 단계든 본 없이 몸 웨이트): 가장 많이 가까운 본이 위팔·아래팔이고
        # 그 축 둘레를 반 넘게 감싸고, 정점 40% 이상이 팔 쪽. 어깨 쪽이 몸통에 더 가까워도 (실베스티아 소매 55%, 카르멘 숄 소매)
        sleeve = bool(re.search(r"UpperArm|Forearm|ForeTwist|UpArm", bn[ib])) and limb_cover >= 0.5 \
            and (ch.get("armL", 0) + ch.get("armR", 0)) >= 0.4 * len(S) and float(np.median(bd)) < 10.0
        if sleeve:
            kind = ""
        elif o.name.endswith("_back") and len(Q) >= 30 and float(np.ptp(Q[:, 2])) >= SLEEVE_BACK_H:
            kind = "cape"                    # 소매에서 가른 등 뒤 늘어진 천 = 망토 (카르멘 숄)
        # 3단계: 가는 줄인지 — 면적이 바운딩 면(긴 쪽 × 둘째 쪽)의 절반 미만이면 줄·끈 (가방·약병·후드 같은 덩어리는 1 넘음)
        cordness = _area_max(o, unit) / max(ext[0] * ext[1], 1e-6)
        arms = (ch.get("armL", 0) + ch.get("armR", 0)) / len(S)
        info[o.name] = dict(o=o, Q=Q, top=top, share=cnt / len(S), legs=legs, dist=float(np.median(bd)), ext=ext, limb_cover=limb_cover,
                            cover=cover, kind=kind, kdiag=(kdiag[0] if kdiag else ""), zmin=float(Q[:, 2].min()), zmax=float(Q[:, 2].max()),
                            cord=cordness, vids=_vids(o), arms=arms, ib=bn[ib], sleeve=sleeve)
    if not _keep_pieces:
        # 11/01 정현 (카르멘 숄): 소매 조각에 등 뒤로 늘어진 천이 붙어 있으면 정점 단위로 가름 → 팔을 덮는 쪽은 팔 웨이트,
        # 등 뒤 쪽(팔 본에서 SLEEVE_ARM_D 넘게 떨어지거나 몸통 본이 더 가까움)은 망토. 몸통을 두르는 옷(상의·칼라)은 안 가름
        did = 0
        for n, d in list(info.items()):
            if not d["sleeve"]:
                continue
            bi_, bd_ = near_bone(d["Q"])
            on_arm = np.array([_limb_of(bn[i]) in ("armL", "armR") for i in bi_]) & (bd_ < SLEEVE_ARM_D)
            B = d["Q"][~on_arm]
            if len(B) < max(40, 0.15 * len(d["Q"])) or float(np.ptp(B[:, 2])) < SLEEVE_BACK_H or B[:, 1].mean() < pel[1] + 2.0:
                continue
            if not (B[:, 0].min() < pel[0] - 3.0 and B[:, 0].max() > pel[0] + 3.0):
                continue                     # 등 가운데를 가로지르는 천만 (팔 뒤에 늘어진 소매 자락은 소매 그대로: 실베스티아)
            bang = np.arctan2(B[:, 1] - pel[1], B[:, 0] - pel[0])
            if len(np.unique(np.floor((bang + np.pi) / (2 * np.pi) * 24).astype(int) % 24)) / 24.0 >= 0.6:
                continue
            _split_piece(ctx, d["o"], ~on_arm, ("back", "sleeve"))
            did += 1
        if did:
            return recommend_parts(ctx, level, _keep_pieces=True)
    # 치마·망토
    groups = {"skirt": [n for n, d in info.items() if d["kind"] == "skirt"], "cape": [n for n, d in info.items() if d["kind"] == "cape"]}
    if groups["skirt"]:
        z0 = min(info[n]["zmin"] for n in groups["skirt"])
        z1 = max(info[n]["zmax"] for n in groups["skirt"])
        zmid = z0 + 0.5 * (z1 - z0)
        for n, d in info.items():
            # 치마 아래쪽 절반에서 한 바퀴 도는 단(밑단 겹 등)만 치마에 합침. 허리 벨트처럼 위쪽은 안 합침
            if n not in groups["skirt"] and d["cover"] >= 0.9 and z0 - 5 <= d["zmin"] and d["zmax"] <= zmid and touch[n] & set(groups["skirt"]):
                groups["skirt"].append(n)
    used = set(groups["skirt"]) | set(groups["cape"])
    skipped, cand = [], []
    nk_ = H[bn.index(pre + " Neck")] if (pre + " Neck") in bn else None
    sp2_ = H[bn.index(pre + " Spine2")] if (pre + " Spine2") in bn else None
    SR = _rules()

    def on_limb(d):
        """팔·다리(·머리)에 붙은 조각: 그 본에 가장 가깝고(75%↑) 감싸거나(축 둘레 50%↑), 바짝 붙은 작은 조각(8cm 안, 25cm 미만).
        머리·목에 가까운 것은 목 위에 있을 때만(모자). 목도리·망토는 목·팔에 가까워도 감싸지 않으면 후보로 (3단계)"""
        if d.get("sleeve"):
            return True
        if d["top"] == "torso" or d["share"] < 0.75:
            return False
        if d["top"] == "head":
            return nk_ is None or d["zmin"] > nk_[2] - 2.0
        return d["limb_cover"] >= 0.5 or (d["dist"] < 8.0 and d["ext"][0] < 25.0)

    def wraps_legs(d):
        """다리를 감싸는 조각(바지·부츠): 다리 본에 가깝고(60%↑) 감싸거나 큰 것. 다리 옆에 매달린 작은 물건(약병)은 아님"""
        return d["legs"] >= 0.6 and (d["limb_cover"] >= 0.5 or d["ext"][0] >= SR.HANG_SIZE)
    # 11/01 정현: 코트·치마에 겹치거나 붙은 옷 조각(뒤 띠·겹치마 바깥 겹·프릴)은 따로 본을 만들지 않고 치마 본으로 웨이트(uv 묶음).
    # 끄면(msr_ob_bundle) 1.72 처럼 별도 파트. 팔·다리에 붙은 조각, 몸을 감싸는 조각은 그대로 몸.
    bundle = []
    pelvis_fix = []
    # 집 확인 (11/01): 골반 둘레 낮은 고리 띠 → 치마·코트 묶음(LOW_RING_TO="skirt", 치마가 있을 때) 아니면 Pelvis 100%
    for n, d in info.items():
        if n in used or not is_low_ring(d, pel):
            continue
        if LOW_RING_TO == "skirt" and groups["skirt"] and getattr(ctx.window_manager, "msr_ob_bundle", True):
            bundle.append(n)
            skipped.append((n, "골반 둘레 낮은 고리 띠 (치마·코트 본으로, 둘레 %.0f%% 높이 %.0fcm)" % (100 * d["cover"], d["zmax"] - d["zmin"])))
        else:
            pelvis_fix.append(n)
            skipped.append((n, "골반 둘레 낮은 고리 띠 (Pelvis 100%%, 둘레 %.0f%% 높이 %.0fcm)" % (100 * d["cover"], d["zmax"] - d["zmin"])))
        used.add(n)
    ctx.scene[PELVIS_KEY] = json.dumps(pelvis_fix)
    if groups["skirt"] and getattr(ctx.window_manager, "msr_ob_bundle", True):
        SK = np.concatenate([info[n]["Q"] for n in groups["skirt"]])
        skc = SK.mean(0)
        su = np.degrees(np.arctan2(SK[:, 0] - skc[0], -(SK[:, 1] - skc[1])))
        sr = np.linalg.norm(SK[:, :2] - skc[:2], axis=1)
        z0 = min(info[n]["zmin"] for n in groups["skirt"])
        z1 = max(info[n]["zmax"] for n in groups["skirt"])
        body_piece = max(info, key=lambda n: len(info[n]["Q"]))
        for n, d in info.items():
            # 3단계: 다리 가까이 있어도 다리를 감싸지 않는 조각(치마 뒤 금색 줄)은 겹침 검사로 (바지는 '안쪽 깊이' 로 빠짐)
            if n in used or (d["legs"] >= 0.6 and d["limb_cover"] >= 0.5) or on_limb(d):
                continue
            # 몸 본체(가장 큰 조각)·치마 윗단보다 한참 위로 올라가는 조각은 겹친 치마 천이 아님 (카르멘: 꼭 붙는 롱스커트라 다리~목 몸이 묶이던 것)
            if n == body_piece or d["zmax"] > z1 + 0.2 * (z1 - z0):
                continue
            if d["zmax"] < z0 - 2 or d["zmin"] > z1 + 2:
                continue
            # 2.8 (세레나): 치마 밑단보다 한참 아래(치마 높이의 SKIRT_BELOW_K 배 넘게)로 내려가는 조각은 겹친 치마 천이 아님
            # (허리~무릎 다리 옷이 Biped 에 따라 다리 비율 0.6 아래로 떨어져 치마 본에 묶이던 것) → 아래 판정으로 (바디 웨이트)
            if d["zmin"] < z0 - SKIRT_BELOW_K * (z1 - z0):
                continue
            if d["zmin"] > z1 - 0.15 * (z1 - z0):
                continue                     # 치마 맨 위 15% 안에만 있는 조각 = 허리 벨트·장식 → 그대로(몸 또는 자기 본)
            Q = d["Q"][::max(1, len(d["Q"]) // 200)]
            qu = np.degrees(np.arctan2(Q[:, 0] - skc[0], -(Q[:, 1] - skc[1])))
            qr = np.linalg.norm(Q[:, :2] - skc[:2], axis=1)
            h = deep = near = 0
            for i in range(len(Q)):
                du = np.abs((su - qu[i] + 180) % 360 - 180)
                m = (du < 10) & (np.abs(SK[:, 2] - Q[i, 2]) < 2.0)
                if m.any():
                    dr = qr[i] - sr[m].min()
                    if abs(dr) < 2.5:
                        h += 1
                    elif dr < -2.5:
                        deep += 1            # 치마 표면보다 안쪽으로 깊이 들어감 (다리·바지)
                    elif dr < 6.0:
                        near += 1            # 표면 바깥으로 조금 떠 있음 (치마에 매단 줄·끈)
            hug, deep, near = h / max(len(Q), 1), deep / max(len(Q), 1), near / max(len(Q), 1)
            d["hug"] = (hug, deep)
            touching = bool(touch[n] & set(groups["skirt"]))
            if deep < 0.3 and (hug >= 0.5 or (touching and hug >= 0.3)):
                bundle.append(n)
                used.add(n)
                skipped.append((n, "치마·코트에 겹친 조각 (치마 본으로, 겹침 %.0f%%)" % (100 * hug)))
            elif (d["dist"] >= 15.0 or (d["dist"] >= SKIRT_INNER_D and d["legs"] < 0.5)) and d["zmax"] - d["zmin"] >= 20.0 and d["zmax"] <= z1 + 5.0 and (hug + deep >= 0.3 or d["cover"] >= 0.9):
                # 2.5 (실베스티아 안감·속치마): 치마 안쪽으로 들어가 있어도(안쪽 30%↑) 몸 본에서 떠 있는 천은 다리 옷이 아니라 치마 안쪽 층.
                # 다리 옷(바지·스타킹)은 가까운 본에서 가까움 (실베스티아 다리 조각 3~8cm, 카미엘 바지 10.6cm)
                bundle.append(n)
                used.add(n)
                skipped.append((n, "치마 안쪽 층 (치마 본으로, 겹침 %.0f%% · 안쪽 %.0f%% · 몸에서 %.0fcm)" % (100 * hug, 100 * deep, d["dist"])))
            elif deep < 0.3 and touching and hug + near >= 0.5 and d["ext"][0] < 30.0 and d["cord"] < CORD_MAX:
                # 3단계: 치마에 붙어 바깥으로 늘어진 가는 조각(금색 줄) → 치마 웨이트 따라감 (ps_build '가까운 웨이트 따라가기')
                bundle.append(n)
                used.add(n)
                skipped.append((n, "치마에 붙어 늘어진 줄·끈 (치마 본으로, 겹침 %.0f%% + 가까움 %.0f%%)" % (100 * hug, 100 * near)))
    # 3단계: 망토에 붙은 가는 조각(펜던트 줄)은 기본으로 망토 웨이트를 따라감 (변형 line=1 이면 자기 체인, 부모 = 가까운 망토 본)
    cape_bundle = []
    cape_set = set(groups["cape"])
    if cape_set and SR.variant("line") == 0:
        CP = np.concatenate([info[n]["Q"] for n in groups["cape"]])
        from mathutils.kdtree import KDTree as _KD
        kc = _KD(len(CP))
        for i, p in enumerate(CP):
            kc.insert(p.tolist(), i)
        kc.balance()
        for n, d in info.items():
            if n in used or not (touch[n] & cape_set) or d["ext"][0] >= 30.0 or d["cord"] >= CORD_MAX or wraps_legs(d) or on_limb(d):
                continue
            Q = d["Q"][::max(1, len(d["Q"]) // 200)]
            nearc = float(np.mean([kc.find(q.tolist())[2] < 6.0 for q in Q]))
            if nearc >= 0.6:
                cape_bundle.append(n)
                used.add(n)
                skipped.append((n, "망토에 붙은 줄·장식 (망토 웨이트 따라감, 가까움 %.0f%%)" % (100 * nearc)))
    # 시험용: 환경변수 MSR_OB_FORCE="OBP_021:ring,OBP_022:ring" 이면 그 조각을 빼지 않고 그 구조로 (판정 규칙이 아니라 코드 경로 시험)
    force = {}
    for kv in os.environ.get("MSR_OB_FORCE", "").split(","):
        k, _, v = kv.partition(":")
        if k.strip() and v.strip():
            force[k.strip()] = v.strip()
    wrap = set()
    for n, d in info.items():
        if n in used:
            continue
        if n in force:
            cand.append(n)
        elif d["ext"][0] < REC_SMALL:
            skipped.append((n, "작은 조각 (%.0fcm)" % d["ext"][0]))
        elif d.get("sleeve"):
            skipped.append((n, "소매 (팔 웨이트로, 팔 둘레 %.0f%%)" % (100 * d["limb_cover"])))
            wrap.add(n)
        elif d["cover"] >= 0.9 or wraps_legs(d):
            skipped.append((n, "몸을 감싸는 조각 (바디 웨이트로)"))
            wrap.add(n)
        elif d["cover"] >= 0.6 and d["top"] in ("torso", "head") and d["dist"] < 6.0 and (nk_ is None or d["zmax"] <= nk_[2] + 6.0):
            # 3단계: 몸통에 바짝 붙어 반 바퀴 넘게 두르는 옷(앞판 셔츠·조끼) → 몸 (망토·후드는 팔·목에서 떨어져 있어 안 걸림)
            # 목보다 6cm 넘게 올라가는 조각(머리에서 늘어진 덮개·베일)은 여기서 안 뺌
            skipped.append((n, "몸통에 붙은 옷 (바디 웨이트로, 둘레 %.0f%%)" % (100 * d["cover"])))
            wrap.add(n)
        elif on_limb(d):
            skipped.append((n, "팔·다리·머리에 붙은 조각 (바디 웨이트로)"))
            wrap.add(n)
        elif SR.is_flat_band(d["Q"], d["dist"]):
            skipped.append((n, "몸에 붙은 납작한 띠·판 (바디 웨이트로, 높이 %.0fcm)" % (d["zmax"] - d["zmin"])))
        else:
            cand.append(n)
    # 3단계: 팔·다리 옷(부츠·소매)에만 붙어 있는 작은 장식(버클·끈)은 그 옷을 따라 몸에 — 서로 붙은 작은 장식 묶음째로 봄
    smallL = {n for n in cand if info[n]["top"] != "torso" and info[n]["share"] >= 0.75 and info[n]["ext"][0] < SR.HANG_SIZE and touch[n]}
    seen_s = set()
    for n in sorted(smallL):
        if n in seen_s:
            continue
        g, st = [], [n]
        while st:
            x = st.pop()
            if x in seen_s:
                continue
            seen_s.add(x)
            g.append(x)
            st += [y for y in touch[x] if y in smallL and y not in seen_s]
        outside = {y for x in g for y in touch[x]} - set(g)
        gh = max(info[x]["zmax"] for x in g) - min(info[x]["zmin"] for x in g)
        # 납작한 것(높이 10 미만: 버클·부츠 윗단 장식)만. 어깨에서 늘어진 술·끈(높이 11↑)은 본
        if outside and outside <= wrap and gh < 10.0:
            for x in g:
                cand.remove(x)
                skipped.append((x, "팔·다리 옷에 붙은 작은 장식 (바디 웨이트로)"))
    # 붙어 있는 후보끼리 한 파트
    # 3단계: 혼자서 목 둘레·후드로 판정되는 조각은 같은 종류끼리만 묶음 (목도리에 닿은 후드·펜던트가 목도리 고리에 섞이지 않게)
    solo = {n: (force.get(n) or SR.classify(info[n]["Q"], pel, sp2_, nk_)["struct"]) for n in cand}

    def can_join(x, y):
        if solo[x] in ("ring", "hood") or solo[y] in ("ring", "hood"):
            return solo[x] == solo[y]
        return True
    grp, seen = [], set()
    for n in cand:
        if n in seen:
            continue
        stack, g = [n], []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            g.append(x)
            # 붙어 있고 높이도 겹치는 조각끼리만 (어깨 장식과 등 리본처럼 끝만 닿는 것은 따로)
            stack += [y for y in touch[x] if y in cand and y not in seen and _z_overlap(info[x], info[y]) >= 0.5 and can_join(x, y)]
        grp.append(g)
    parts, out = [], []
    pid = 0
    for k in ("skirt", "cape"):
        if groups[k]:
            pid += 1
            objs = [info[n]["o"] for n in groups[k]]
            st = AUTO_SET[k]
            Pw = np.concatenate([_world_co(o) for o in objs])
            parts.append(dict(id=pid, pieces=list(groups[k]), chains=st["chains"], segs=st["segs"], axis="DOWN", single=False,
                              center=st["center"], parent=_fallback_parent(arm, k, Pw), x=float(Pw[:, 0].mean()), kind=k, name=k,
                              bundle=(list(bundle) if k == "skirt" else list(cape_bundle))))
            nb = len(bundle) if k == "skirt" else len(cape_bundle)
            out.append("%s: 조각 %d개%s" % (KIND_LABEL[k], len(groups[k]), (" (+붙은 조각 %d개 %s 본으로)" % (nb, KIND_LABEL[k])) if nb else ""))
    # 매달린 물건(작은 조각)끼리 3cm 안에 있으면 한 묶음 (약병 + 홀더 끈처럼 안 닿아도 한 물건)
    bbox = {n: (d["Q"].min(0), d["Q"].max(0)) for n, d in info.items()}
    small = lambda g: SR.classify(np.concatenate([info[n]["Q"] for n in g]), pel, sp2_, nk_)["struct"] == "hang"
    grp = SR.near_groups(grp, bbox, small)
    dbg = []
    for g in sorted(grp, key=lambda g: -sum(len(info[n]["Q"]) for n in g)):
        Q = np.concatenate([info[n]["Q"] for n in g])
        st = SR.classify(Q, pel, sp2_, nk_)
        fs = {force[n] for n in g if n in force}
        if fs:
            st = SR.forced(st, fs.pop(), Q)
        var = SR.variant(st["struct"])
        if st["struct"] == "apron" and var == 0:
            # 변형 0(몸 웨이트)은 짧은 앞치마만: 밑단이 치마 길이의 절반보다 위(치마가 없으면 높이 30 미만). 치마 위로 길게 늘어진 앞판은 체인
            if groups["skirt"]:
                sz0 = min(info[x]["zmin"] for x in groups["skirt"])
                sz1 = max(info[x]["zmax"] for x in groups["skirt"])
                short = (float(Q[:, 2].min()) - sz0) >= 0.5 * (sz1 - sz0)
            else:
                short = st["hz"] < 30.0
            if short:
                skipped.append((g[0], "짧은 앞치마 (몸 웨이트로; 변형 apron=1 이면 좌우 2갈래 체인)"))
                dbg.append((g, st, var, "skip"))
                continue
            st = dict(st, why=st["why"] + " · 치마 위로 길게 늘어져 체인")
        pieces_ = list(g)
        if st["struct"] == "hang" and var == 0 and len(g) > 1:
            # 11/01 정현: 매달린 물건은 몸통만 체인, 끈(가는 조각)은 몸(어깨) 웨이트. 변형 hang=1 이면 끈부터 체인
            straps = [n for n in g if info[n]["cord"] < STRAP_MAX]
            body_ = [n for n in g if n not in straps]
            if straps and body_:
                for n in straps:
                    skipped.append((n, "매달린 물건의 끈 (몸 웨이트로; 변형 hang=1 이면 끈부터 체인)"))
                pieces_ = body_
                Q = np.concatenate([info[n]["Q"] for n in body_])
                st = dict(SR.classify(Q, pel, sp2_, nk_), struct="hang", why=st["why"] + " · 끈 %d개 뺌" % len(straps))
                st["chains"], st["segs"] = 1, SR.segs_for(st["hz"], "hang")
        if level < 3:
            keep = _level_keep(level, st)
            if not keep:
                for n in g:
                    skipped.append((n, "단계 %d: 본 없이 몸 웨이트 (%s)" % (level, SR.STRUCT_LABEL.get(st["struct"], st["struct"]))))
                dbg.append((g, st, var, "skip level %d" % level))
                continue
            if keep == "simple":
                st = dict(st, chains=1, segs=(1 if st["hz"] < LEVEL_SEG2_H else 2), why=st["why"] + " · 단계 %d 간단 체인" % level)
        flaps = []
        if st["struct"] == "ring" and var == 1 and nk_ is not None:
            # 변형 1: 목 앞 아래로 내려온 앞자락을 정점 단위로 갈라 좌우 2갈래 체인 (아래→위, 부모 = 아래 끝에 가까운 척추)
            pieces_ = []
            for n in g:
                o = info[n]["o"]
                m = SR.flap_mask(info[n]["Q"], nk_)
                if m.sum() >= 20 and (~m).sum() >= 20:
                    new = _split_piece(ctx, o, m, ("flap", "ring"))
                    flaps += [x for x in new if x.endswith("_flap")]
                    pieces_ += [x for x in new if x.endswith("_ring")]
                else:
                    pieces_.append(n)
        pid += 1
        objs = [bpy.data.objects[n] for n in pieces_]
        Pw = np.concatenate([_world_co(o) for o in objs])
        par = (pre + " Spine2") if (st["parent"] == "Spine2" and (pre + " Spine2") in bn) else _body_parent(arm, Pw)
        parts.append(dict(id=pid, pieces=pieces_, chains=st["chains"], segs=st["segs"], axis="DOWN", single=False, center=False, straight=True,
                          parent=par, x=float(Pw[:, 0].mean()), kind="", name=None, struct=st["struct"], force_root=True,
                          lr=(st["struct"] == "apron")))
        out.append("기타 %02d [%s]: 조각 %d개 · 높이 %.0fcm 폭 %.0fcm → %s" % (pid, SR.STRUCT_LABEL.get(st["struct"], st["struct"]), len(g), st["hz"], st["wdt"],
                   ("목 둘레 고리 %d칸" % SR.RING_N if st["struct"] == "ring" else "%d갈래 × %d마디" % (st["chains"], st["segs"]))))
        dbg.append((g, st, var, "part %02d" % pid))
        if flaps:
            fo = [bpy.data.objects[n] for n in flaps]
            Pf = np.concatenate([_world_co(o) for o in fo])
            Qf = Pf * unit + off
            hz = float(Qf[:, 2].max() - Qf[:, 2].min())
            # 부모: 앞자락 아래 끝에 가장 가까운 척추 (ps_build; 작업자 10-24 요청 '뿌리를 벨트 쪽 아래 끝에')
            bot = Pf[Pf[:, 2] <= np.percentile(Pf[:, 2], 10)].mean(0)
            cand_ = [b for b in arm.data.bones if re.match(re.escape(pre) + r" Spine\d?$", b.name)]
            fpar = min(cand_, key=lambda b: np.linalg.norm(np.array(mw @ b.head_local) - bot)).name if cand_ else par
            pid += 1
            parts.append(dict(id=pid, pieces=flaps, chains=2, segs=SR.segs_for(hz, "flap"), axis="AUTO", single=False, center=False, straight=True,
                              parent=fpar, x=float(Pf[:, 0].mean()), kind="", name=None, struct="flap", force_root=True, lr=True))
            out.append("기타 %02d [앞자락]: 목도리 앞자락 정점 %d · 높이 %.0fcm → 좌우 2갈래 × %d마디 (아래→위, 부모 %s)" % (pid, len(Pf), hz, SR.segs_for(hz, "flap"), fpar))
    set_parts(ctx.scene, parts)
    for o in list(ctx.view_layer.objects.selected):
        o.select_set(False)
    _CACHE.clear()
    dpath = os.environ.get("MSR_OB_DEBUG")
    if dpath:
        try:
            with open(dpath, "w", encoding="utf-8") as fh:
                fh.write("# 조각 | 정점 | z 범위 | x 범위 | y 범위 | 긴 쪽 크기 | 줄 정도(면적/바운딩면) | 골반 둘레 덮음 | 가까운 본 부위(비율, 거리, 축 둘레 덮음) | 다리 | 닿은 조각 | 종류 | 결정 | 치마·망토 판정 수치\n")
            with open(dpath + ".vids.txt", "w", encoding="utf-8") as fv:     # 조각별 Max 정점 번호 (Blender + 1) → Max 에서 선택해 보기
                for n, d in info.items():
                    fv.write("%s|%s\n" % (n, ",".join(str(int(v) + 1) for v in d["vids"])))
            with open(dpath, "a", encoding="utf-8") as fh:
                dec = {}
                for n, why in skipped:
                    dec[n] = "skip: " + why
                for k in ("skirt", "cape"):
                    for n in groups[k]:
                        dec[n] = KIND_LABEL[k]
                for g, st, var, r in dbg:
                    for n in g:
                        dec[n] = "%s [%s %s] %d×%d var%d" % (r, st["struct"], st["why"], st["chains"], st["segs"], var)
                for n, d in sorted(info.items(), key=lambda t: -len(t[1]["Q"])):
                    Q_ = d["Q"]
                    fh.write("%s | %d | %.1f~%.1f | %.1f~%.1f | %.1f~%.1f | %.1f | %.2f | %.2f | %s(%.2f, %.1f, %.2f) | %.2f | %s | %s | %s | %s\n" % (
                        n, len(Q_), d["zmin"], d["zmax"], Q_[:, 0].min(), Q_[:, 0].max(), Q_[:, 1].min(), Q_[:, 1].max(), d["ext"][0], d["cord"], d["cover"],
                        d["top"], d["share"], d["dist"], d["limb_cover"], d["legs"], ",".join(sorted(touch[n])), d["kind"], dec.get(n, "?"),
                        d["kdiag"] + (" | 치마 겹침 %.2f 안쪽 %.2f" % d["hug"] if d.get("hug") else "") + " | ib %s arms %.2f" % (d["ib"], d["arms"])))
        except Exception as e:
            print("[object_bones] 판정 표 쓰기 실패:", e)
    return out, skipped


# ---------------------------------------------------------------- ③ 파트: Max 에서 지정한 영역으로 (Rig Tools 4_2, 2026-10-29)
MARK_PREFIX = "OBM_"
MARK_KIND = {"skirt": "skirt", "cape": "cape", "etc": ""}
MARK_DEFAULT = {"skirt": (6, 6), "cape": (3, 4), "": (1, 3)}   # 종류 "auto" 지정(Rig Tools [Max 수정])일 때 체인×마디


def _all_round(P, c):
    """한 바퀴 다 도는 치마인지 (골반 축에서 봤을 때 36칸 중 33칸 이상 덮음) → 앞·뒤 가운데 체인을 더함.
    반원 치마·앞치마처럼 일부만 덮으면 체인 수 그대로"""
    th = np.arctan2(P[:, 1] - c[1], P[:, 0] - c[0])
    return len(np.unique(np.floor((th + np.pi) / (2 * np.pi) * 36).astype(int) % 36)) >= 33


def _fallback_parent(arm, kind, P):
    """웨이트 없을 때 부모: 치마 = Pelvis, 망토 = Spine2(없으면 위 척추), 기타 = 파트 위쪽에서 가장 가까운 Bip 본"""
    pre = _flow().bip_prefix(arm) or "Bip01"
    names = arm.data.bones.keys()
    if kind == "skirt" and pre + " Pelvis" in names:
        return pre + " Pelvis"
    if kind == "cape":
        for n in ("Spine2", "Spine1", "Spine", "Neck"):
            if pre + " " + n in names:
                return pre + " " + n
    top = P[P[:, 2] >= np.percentile(P[:, 2], 90)].mean(0)
    best, bd = None, 1e18
    mw = arm.matrix_world
    for b in arm.data.bones:
        if not b.name.startswith(pre + " ") or "Nub" in b.name or "Footsteps" in b.name:
            continue
        h, t = np.array(mw @ b.head_local), np.array(mw @ b.tail_local)
        d = t - h
        q = h + np.clip(np.dot(top - h, d) / max(np.dot(d, d), 1e-12), 0, 1) * d
        dist = np.linalg.norm(top - q)
        if dist < bd:
            best, bd = b.name, dist
    return best


def marked_parts(ctx, plist):
    """plist: [(종류 skirt/cape/etc, 체인, 마디, Max 노드 이름, Max 좌표 N×3), ...]
    지정한 정점만으로 파트를 만들어 확정 (이전 파트는 모두 바꿈). 치마·망토는 아래로, 기타는 긴 방향으로.
    반원 치마·앞치마처럼 따로 지정한 조각은 각각 다른 파트(bone_skirt_, bone_skirt2_ ...). returns 설명 목록"""
    from mathutils.kdtree import KDTree
    f = _flow()
    arm, body, face, tooth = f.flow_objects(ctx)
    if arm is None or body is None:
        raise RuntimeError("Bip·바디가 없어요")
    if ctx.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    unit, off = f._max_xform(arm, f._max_bridge())
    Pm = _world_co(body) * unit + np.array(tuple(off))
    kd = KDTree(len(Pm))
    for i, p in enumerate(Pm):
        kd.insert(p.tolist(), i)
    kd.balance()
    pb = arm.data.bones.get((f.bip_prefix(arm) or "Bip01") + " Pelvis")
    pel = np.array(arm.matrix_world @ pb.head_local) if pb else _world_co(body).mean(0)
    # 바디에 아직 스킨 웨이트가 없으면(새 캐릭터) 웨이트로 부모를 못 찾음 → 위치로 정함
    has_w = any(g.name in arm.data.bones for g in body.vertex_groups)
    clear(ctx, body)                                   # 예전 조각·파트 정리
    col = bpy.data.collections.new(COL)
    ctx.scene.collection.children.link(col)
    parts, out, taken = [], [], set()
    for n, (kind, ch, sg, node, P) in enumerate(plist, 1):
        if kind == "none":                      # 지운 파트 자리: 번호만 차지 (다른 파트 이름이 안 바뀌게)
            continue
        vids = set()
        miss = 0
        for p in P:
            co, i, d = kd.find(p.tolist())
            if d is not None and d < 0.5:
                # 양면 천(같은 자리에 정점 2개): 한 자리의 정점을 모두 (카르멘 치마: 하나만 잡아 반쪽 면이 몸 웨이트로 끌려가던 것)
                vids.update(j for _, j, _ in kd.find_range(p.tolist(), d + 1e-3))
            else:
                miss += 1
        k = MARK_KIND.get(kind, "")
        lab = KIND_LABEL.get(k, "기타") if kind != "auto" else "자동"
        if len(vids) < 4 or miss > 0.5 * len(P):
            raise RuntimeError("%d번 %s 파트(%s)를 바디 메쉬(%s)에서 찾지 못했어요. 파트는 바디 메쉬 안에서 지정해 주세요."
                               % (n, lab, node, body.name))
        bm = bmesh.new()
        bm.from_mesh(body.data)
        lay = bm.verts.layers.int.new("ob_vid")
        for v in bm.verts:
            v[lay] = v.index
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in vids], context="VERTS")
        m2 = bpy.data.meshes.new("%s%02d" % (MARK_PREFIX, n))
        bm.to_mesh(m2)
        bm.free()
        o = bpy.data.objects.new(m2.name, m2)
        o.matrix_world = body.matrix_world
        col.objects.link(o)
        o.hide_set(True)
        around = 0
        if kind == "auto":                      # 종류는 모양으로 판별. 체인·마디: Max 에서 정한 값, 0 이면 종류 기본값
            k = guess_kind(arm, [o], loose=True)
            dch, dsg = MARK_DEFAULT.get(k, (1, 3))
            around = int(ch)                    # Max 값 = 둘레 전체 체인 수 (치마는 앞·뒤 가운데 체인 포함)
            ch = around if around > 0 else dch
            sg = int(sg) if int(sg) > 0 else dsg
            lab = KIND_LABEL.get(k, "기타")
        name = None
        if k:
            name = k if k not in taken else next(k + str(i) for i in range(2, 99) if k + str(i) not in taken)
            taken.add(name)
        cen = (k == "skirt" and _all_round(_world_co(o), pel))
        if cen and around > 0:
            # 한 바퀴 도는 치마: 앞·뒤 가운데 체인 2개가 더해지므로 둘레 N 개 = 체인 N-2 + 가운데 2 (N 이 짝수일 때)
            if around % 2 == 0 and around >= 4:
                ch = around - 2
            else:
                cen = False
        parts.append(dict(id=n, pieces=[o.name], chains=int(ch), segs=int(sg), axis="DOWN" if (k or kind == "auto") else "AUTO",
                          straight=(kind == "auto" and k != "skirt"),
                          single=False, center=cen,
                          parent=None if has_w else _fallback_parent(arm, k, _world_co(o)), x=float(_world_co(o)[:, 0].mean()),
                          kind=k, name=name))
        out.append("%d. %s %s 정점 %d · %d×%d" % (n, lab, name or "", len(vids), ch, sg))
    set_parts(ctx.scene, parts)
    _CACHE.clear()
    return out


class MSR_OT_ob_split(bpy.types.Operator):
    """바디를 복사해서 떨어진 조각별로 나눔 (원본 바디는 숨김만).
멜리타 바디면 멜리타 파츠(치마·망토·후드·어깨사슬·목도리·가방·약병)를 자동으로 정하고 본까지 생성"""
    bl_idname = "msr.ob_split"
    bl_label = "1. 파츠 나누기"
    bl_options = {"REGISTER", "UNDO"}
    auto: bpy.props.BoolProperty(default=True, description="멜리타 바디면 파츠 자동 + 본 생성")

    def execute(self, context):
        arm, body, face, tooth = _flow().flow_objects(context)
        if body is None:
            self.report({"WARNING"}, "바디가 없어요")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        wm = context.window_manager
        n, raw = split(context, body, wm.msr_ob_min)
        if not (self.auto and is_preset_body(body)):
            try:
                same_nv = self.auto and json.load(open(PRESET, encoding="utf-8")).get("nv") == len(body.data.vertices)
            except Exception:
                same_nv = False
            wm.msr_status = "조각 %d개 (원래 %d개) | 조각 클릭(Shift 여러 개) → 본 미리보기 → 파트 확정" % (n, raw) + \
                (" | 정점 수는 멜리타와 같지만 모양이 달라 멜리타 자동 안 씀" if same_nv else "")
            return {"FINISHED"}
        found, missing = load_preset(context, body)
        msg = "멜리타 파츠 %d개 자동" % len(found) + (" | 못 찾음: %s" % ", ".join(missing) if missing else "")
        if found and arm is not None:
            r = bpy.ops.msr.ob_generate()
            msg += " | " + wm.msr_status
            if "FINISHED" not in r:
                wm.msr_status = msg          # 2.7: 본 생성·Max 보내기 실패를 실패로 (예전엔 FINISHED)
                return {"CANCELLED"}
        wm.msr_status = msg
        return {"FINISHED"}


class MSR_OT_ob_confirm(bpy.types.Operator):
    """선택한 조각을 지금 숫자로 파트 확정 (초록 미리보기)"""
    bl_idname = "msr.ob_confirm"
    bl_label = "파트 확정"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        pid = confirm(context)
        if pid is None:
            self.report({"WARNING"}, "조각을 먼저 클릭하세요")
            return {"CANCELLED"}
        _CACHE.clear()
        context.window_manager.msr_status = "파트 %02d 확정 | 다른 조각을 클릭하거나 '생성'" % pid
        return {"FINISHED"}


class MSR_OT_ob_unconfirm(bpy.types.Operator):
    """선택한 조각이 들어 있는 파트를 풀기"""
    bl_idname = "msr.ob_unconfirm"
    bl_label = "파트 풀기"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        n = unconfirm(context)
        _CACHE.clear()
        context.window_manager.msr_status = "파트 %d개 풀었어요" % n
        return {"FINISHED"}


def _fixed_part_count():
    """Max 에서 [Max 수정] → [선택한 면으로 본 만들기] 로 고른 파트 수 (고른 면 기록 7760 의 종류 'auto' 줄). Max 연결 없으면 0"""
    try:
        mb = _flow()._max_bridge()
        s = mb.send('(local n = 0; for o in rts_mkNodes() do for p in (rts_mkRead o) where p[1] == "auto" do n += 1; n as string)', timeout=30)
        return int(str(s).strip().strip('"') or 0)
    except Exception:
        return 0


class MSR_OT_ob_level(bpy.types.Operator):
    """파츠 본 범위를 골라 바로 다시 만들기 (Max 의 파츠 본·고른 면 기록을 지우고 자동으로 새로). 되돌리려면 이전 단계를 다시 누르세요"""
    bl_idname = "msr.ob_level"
    bl_label = "파츠 본 범위"
    bl_options = {"REGISTER"}
    level: bpy.props.IntProperty(default=2, min=1, max=3)

    def invoke(self, context, event):
        # 정현 11-01: Max 에서 '선택한 면으로' 고친 파트가 있을 때만 확인 창 (없으면 바로)
        n = _fixed_part_count()
        if n:
            msg = "Max 에서 선택한 면으로 고친 파트 %d개가 지워지고 범위 %d 로 자동으로 새로 만들어요. 계속할까요?" % (n, self.level)
            try:
                return context.window_manager.invoke_confirm(self, event, title="파츠 본 범위 %d" % self.level, message=msg,
                                                             confirm_text="다시 만들기", icon="WARNING")
            except TypeError:
                return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        global _LEVEL_NEXT
        wm = context.window_manager
        try:
            import ge_jobs
            mb = _flow()._max_bridge()
            if mb is None:
                raise RuntimeError("Max 연결이 없어요")
            # Max [② 세컨더리 본 만들기] 와 같게: 고른 면 기록을 지우고 자동으로 (Max 패널 rts_partAutoStart)
            mb.send("(for x in rts_mkNodes() do ( deleteAppData x 7761; deleteAppData x 7760 ); \"ok\")", timeout=60)
            _LEVEL_NEXT = self.level
            msg = ge_jobs.step_parts(mb, {"magica": 1})
        except Exception as e:
            wm.msr_status = "파츠 본 다시 만들기 실패 | %s" % str(e)[:300]
            self.report({"WARNING"}, wm.msr_status)
            return {"CANCELLED"}
        finally:
            _LEVEL_NEXT = 0
        wm.msr_status = "범위 %d 로 다시 만들었어요 | %s" % (self.level, msg[:400])
        self.report({"INFO"}, wm.msr_status)
        return {"FINISHED"}


def _clean_view(ctx, arm):
    """armature already in max_bridge Clean bone view -> redo it so the object bones get the same look"""
    if not any(pb.custom_shape and pb.custom_shape.name == "WGT_CleanBone" for pb in arm.pose.bones):
        return
    try:
        import max_bridge
        mbp = getattr(ctx.scene, "maxbridge", None)
        max_bridge.cv_apply(arm.name, hide_helpers=not (mbp and mbp.show_helpers))
    except Exception as e:
        print("object_bones: clean view skipped:", e)
    try:
        import hair_bones
        hair_bones.show_boxes(arm)          # 2.2: 헤어 본은 Max 박스 모양 그대로 (보기만)
    except Exception as e:
        print("object_bones: hair boxes skipped:", e)


class MSR_OT_ob_generate(bpy.types.Operator):
    """확정한 파트의 본을 만들어 Max에 보냄 (본만. 웨이트는 '3. Max에 스킨 적용' 때)"""
    bl_idname = "msr.ob_generate"
    bl_label = "4. 생성 (Max에 본)"
    bl_options = {"REGISTER", "UNDO"}
    only: bpy.props.StringProperty(default="", description="json 목록: 이 파트(본 이름 앞부분)만 다시 만들고 다른 파트 본은 그대로")
    nocenter: bpy.props.BoolProperty(default=False, description="매지카용: 앞·뒤 가운데 체인에 좌우 50:50 구속을 걸지 않음 (매지카 옆 연결이 대신함)")

    def execute(self, context):
        f = _flow()
        arm, body, face, tooth = f.flow_objects(context)
        if arm is None or body is None:
            self.report({"WARNING"}, "Bip·바디가 없어요")
            return {"CANCELLED"}
        if not get_parts(context.scene):
            self.report({"WARNING"}, "확정한 파트가 없어요")
            return {"CANCELLED"}
        wm = context.window_manager
        prev_auto = json.loads(arm.get(AUTO_PARENT_KEY, "{}"))
        try:
            only = set(json.loads(self.only)) if self.only else None
            made, old, nv = generate(context, arm, body, only=only)
        except RuntimeError as e:
            if context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            wm.msr_status = "생성 실패 | %s" % e
            self.report({"WARNING"}, wm.msr_status)
            return {"CANCELLED"}
        apply_weights(context.scene, arm, body)          # weights on the Blender body now (⑤ pose test shows them)
        _clean_view(context, arm)                        # new bones drawn like the other bones (Clean bone view)
        msg = "본 %d개(root·_00·_end 포함) · 정점 %d개" % (len(made), nv)
        if _LAST_BENT:
            msg += (" | 많이 휜 체인 %d개를 %d°까지만 휘게 했어요: %s — 이대로 둘지, 더 휘게 할지는 Max 에서 직접 조정해 주세요"
                    % (len(_LAST_BENT), BEND_MAX, ", ".join("%s(원래 %.1f°)" % (n, a) for n, a in _LAST_BENT)))
        mb = f._max_bridge()
        if mb is not None:
            try:
                keep = {}
                if wm.msr_ob_keep_parent and prev_auto:
                    # parents changed by hand in Max (differ from what was made last time) stay
                    r = mb.send('(local r = ""; for n in #(%s) do (local o = getNodeByName n exact:true; '
                                'if o != undefined and o.parent != undefined do r += n + "|" + o.parent.name + ";"); r)'
                                % ",".join('"%s"' % n for n in made if n in prev_auto), timeout=30).strip().strip('"')
                    for item in r.split(";"):
                        n, _, p = item.partition("|")
                        if n and p and p != prev_auto.get(n):
                            keep[n] = p
                # remove the previous object bones in one go (centre-chain constraints point at each other)
                allb = sorted(set(old) | set(made))
                mb.send('(local d = for n in #(%s) collect (getNodeByName n exact:true); d = for o in d where o != undefined collect o; '
                        'for o in d do try (o.rotation.controller = Euler_XYZ(); o.position.controller = Position_XYZ()) catch (); '
                        'for o in d where isValidNode o do try (delete o) catch (); "OK")'
                        % ",".join('"%s"' % n for n in allb), timeout=60)
                k = f.push_bones_to_max(arm, made, mb, recreate=True)
                msg += " | Max에 본 %d개" % k
                if keep:
                    mb.send('(for e in #(%s) do (local o = getNodeByName e[1] exact:true; local p = getNodeByName e[2] exact:true; '
                            'if o != undefined and p != undefined do o.parent = p); "OK")'
                            % ",".join('#("%s","%s")' % kv for kv in keep.items()), timeout=30)
                    msg += " | Max에서 바꾼 부모 %d개 유지" % len(keep)
                cs = json.loads(arm.get(CENTER_KEY, "[]"))
                if cs and self.nocenter:
                    msg += " | 매지카용: 가운데 체인 구속 안 함"
                elif cs:
                    # centre chains turn half way between their left and right neighbours (like bone_waist)
                    trip = [(c, l, r) for C, L, R in cs for c, l, r in zip(C, L, R)]
                    mb.send('(for e in #(%s) do (local c = getNodeByName e[1] exact:true; local a = getNodeByName e[2] exact:true; '
                            'local b = getNodeByName e[3] exact:true; if c != undefined and a != undefined and b != undefined do '
                            # 순서 중요 (Max 2014): 본에 먼저 넣고 → 처음 방향 유지 켜고 → 대상 추가. 거꾸로 하면 월드 X 로 누움
                            '(local oc = Orientation_Constraint(); c.rotation.controller = oc; oc.relative = true; '
                            'oc.appendTarget a 50; oc.appendTarget b 50)); "OK")' % ",".join('#("%s","%s","%s")' % t for t in trip), timeout=30)
                    msg += " | 가운데 체인 %d개(좌우 50:50)" % len(cs)
            except Exception as e:
                # 2.7: Max 에 본을 못 보냈으면 실패로 (예전엔 상태 글에만 남기고 성공 처리 → Max 리그툴이 OK 로 보임)
                wm.msr_status = "생성 실패 | 블렌더에는 본을 만들었지만 Max 에 보내지 못했어요: %s" % str(e)[:200]
                self.report({"WARNING"}, wm.msr_status)
                return {"CANCELLED"}
            # 집 확인 (2026-11-01): ④ 웨이트를 이 Max 파일 기록으로 바로 저장. 블렌더를 새로 켠 뒤(또는 다른 파일 작업 뒤) 스킨 적용해도
            #   같은 값으로 시작하게. 멜리타 프리셋은 Max 면 기록(7760)이 없어 다시 계산을 못 해 오브젝트 본 웨이트가 0 이 되던 것 막음
            try:
                if hasattr(f, "_ob_save"):
                    f._ob_save(context.scene, mb, body)
            except Exception as e:
                print("[object_bones] ④ 웨이트 기록 실패:", e)
        else:
            msg += " | Max 연결 없음 (블렌더에만 만듦)"
        wm.msr_status = msg + " | 블렌더 바디에도 웨이트 넣음(⑤로 확인) · Max 웨이트는 '3. Max에 스킨 적용' 때"
        return {"FINISHED"}


# Max: test swing keys on the object bones (like the Biped test motion) so weights can be checked while rigging
TEST_MS = r"""
fn rtTestKeys names cnt amp step = (
  local nodes = for n in names collect getNodeByName n exact:true
  local ok = for i = 1 to nodes.count where nodes[i] != undefined and isKindOf nodes[i].rotation.controller Euler_XYZ collect i
  local bipT = 0f
  for o in objects where isKindOf o Biped_Object do (local c = o.controller; try (for k in c.keys do if k.time > bipT do bipT = k.time) catch ())
  local s = if bipT > 0f then bipT + step else 0f
  local poses = #(#([1,0,0], -1), #([1,0,0], 1), #([0,1,0], 1), #([0,1,0], -1))
  for i in ok where nodes[i].rotation.controller.keys.count > 0 do (local r0 = at time 0f nodes[i].rotation; deleteKeys nodes[i].rotation.controller #allKeys; nodes[i].rotation = r0)
  local rest = for i in ok collect nodes[i].rotation
  local depth = for i in ok collect (local d = 0; local p = nodes[i].parent; while p != undefined do (d += 1; p = p.parent); d)
  local order = for j = 1 to ok.count collect j
  fn cmpD a b dep: = dep[a] - dep[b]
  qsort order cmpD dep:depth
  with animate on (
    for pi = 0 to poses.count do (
      for j = 1 to ok.count do at time (s + step * 2 * pi) nodes[ok[j]].rotation = rest[j]
      if pi > 0 do (
        local tp = s + step * (2 * pi - 1)
        for j = 1 to ok.count do at time tp nodes[ok[j]].rotation = rest[j]
        for j in order do at time tp (in coordsys world about pivot rotate nodes[ok[j]] (angleaxis (poses[pi][2] * amp / cnt[ok[j]]) poses[pi][1]))
      )
    )
  )
  local e = s + step * 2 * poses.count
  if animationRange.end < e do animationRange = interval animationRange.start e
  redrawViews()
  ((ok.count as string) + "|" + (((s as integer) / ticksPerFrame) as string) + "|" + (((e as integer) / ticksPerFrame) as string))
)
fn rtTestKeysClear names = (
  local n = 0
  for nm in names do (local o = getNodeByName nm exact:true
    if o != undefined and isKindOf o.rotation.controller Euler_XYZ and o.rotation.controller.keys.count > 0 do
      (local r0 = at time 0f o.rotation; deleteKeys o.rotation.controller #allKeys; o.rotation = r0; n += 1))
  redrawViews()
  n as string
)
"""


def _test_bones(arm):
    """object / hair bones that swing: no root / _00 (connection, no turn) / _end. returns (names, bones per chain)"""
    names = [n for n in list(arm.get(ARM_KEY, [])) + list(arm.get("msr_ob_hair_bones", []))
             if not re.search(r"(_root|_00|_end)$", n, re.I)]
    chain = {}
    for n in names:
        k = re.sub(r"_\d+$", "", n)
        chain[k] = chain.get(k, 0) + 1
    return names, [chain[re.sub(r"_\d+$", "", n)] for n in names]


class MSR_OT_ob_testkeys(bpy.types.Operator):
    """Max 의 오브젝트 본에 확인용 흔들기 키 (바이패드 테스트 동작 뒤에 앞·뒤·좌·우, 3프레임 간격). 리깅할 때 웨이트 확인용"""
    bl_idname = "msr.ob_testkeys"
    bl_label = "움직임 확인 키"
    bl_options = {"REGISTER"}
    clear: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        f = _flow()
        arm, body, face, tooth = f.flow_objects(context)
        wm = context.window_manager
        mb = f._max_bridge()
        if arm is None or mb is None:
            self.report({"WARNING"}, "Bip 또는 Max 연결이 없어요")
            return {"CANCELLED"}
        names, cnt = _test_bones(arm)
        if not names:
            self.report({"WARNING"}, "오브젝트 본이 없어요 (먼저 생성)")
            return {"CANCELLED"}
        try:
            mb.send(TEST_MS, timeout=30)
            lst = ",".join('"%s"' % n for n in names)
            if self.clear:
                r = mb.send("rtTestKeysClear #(%s)" % lst, timeout=60).strip().strip('"')
                wm.msr_status = "확인 키 지움: 본 %s개 (처음 자세로)" % r
            else:
                r = mb.send("rtTestKeys #(%s) #(%s) %d.0 3f" % (lst, ",".join(str(c) for c in cnt), wm.msr_ob_test_amp),
                            timeout=120).strip().strip('"').split("|")
                wm.msr_status = "확인 키: 본 %s개, %s~%s프레임 (앞·뒤·좌·우, 체인 끝 %d도)" % (r[0], r[1], r[2], wm.msr_ob_test_amp)
        except Exception as e:
            wm.msr_status = "Max 실패: %s" % str(e)[:150]
            self.report({"WARNING"}, wm.msr_status)
            return {"CANCELLED"}
        self.report({"INFO"}, wm.msr_status)
        return {"FINISHED"}


class MSR_OT_ob_clear(bpy.types.Operator):
    """나눈 복사본을 지우고 바디를 다시 보이게 (확정·생성한 본과 웨이트 정보는 그대로)"""
    bl_idname = "msr.ob_clear"
    bl_label = "복사본 정리"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm, body, face, tooth = _flow().flow_objects(context)
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        clear(context, body)
        return {"FINISHED"}


def draw(lay, context):
    wm = context.window_manager
    pcs = pieces()
    sel = selected_pieces(context) if pcs else []
    parts = get_parts(context.scene)
    p = part_of(context.scene, sel[0].name) if sel else None
    # A. Melitta: one click = pieces + parts + bones
    b = lay.box()
    b.label(text="멜리타 바디면 파츠·본 자동 (다른 캐릭터는 아래 '직접 고치기')", icon="INFO")
    r = b.row()
    r.scale_y = 1.3
    r.operator("msr.ob_split", text="1. 파츠 나누기 (멜리타 자동)", icon="MOD_EXPLODE").auto = True
    if parts:
        b.label(text="파츠 %d개: %s" % (len(parts), ", ".join(_part_label(q) for q in parts)))
    # 11/01: 파츠 본 범위 1/2/3 — 누르면 그 범위로 바로 다시 만들기 (Max 기본 = 2)
    b = lay.box()
    b.label(text="파츠 본 범위 (누르면 바로 다시 만들기)")
    cur = int(context.scene.get(LEVEL_KEY, 0) or 0)
    row = b.row(align=True)
    row.scale_y = 1.3
    for v, t in ((1, "1 큰 옷만"), (2, "2 기본"), (3, "3 전부")):
        row.operator("msr.ob_level", text=t, depress=(cur == v)).level = v
    # generate
    b = lay.box()
    b.enabled = bool(parts)
    r = b.row()
    r.scale_y = 1.3
    r.alert = bool(parts)
    r.operator("msr.ob_generate", text="생성 (블렌더 웨이트 + Max 본)", icon="BONE_DATA")
    b.prop(wm, "msr_ob_keep_parent", text="다시 생성할 때 Max에서 바꾼 부모 링크 유지")
    b.prop(wm, "msr_ob_lower", text="멜리타 자동 본 이름 소문자로 (끄면 f05 이름 그대로)")
    b.prop(wm, "msr_ob_bundle", text="겹친 옷 조각은 코트/치마 본으로 (끄면 따로 본)")
    b.label(text="다음: (Max에서 본 손보기 → ① 다시 가져오기) → '3. 스킨 적용 (일괄)'")
    # test swing keys in Max (weights check while rigging)
    b = lay.box()
    a = context.scene.objects.get(wm.msr_arm)
    b.enabled = bool(a and (a.get(ARM_KEY) or a.get("msr_ob_hair_bones")))
    r = b.row(align=True)
    r.operator("msr.ob_testkeys", text="Max에 움직임 확인 키", icon="ANIM").clear = False
    r.operator("msr.ob_testkeys", text="키 지우기", icon="X").clear = True
    b.prop(wm, "msr_ob_test_amp", text="흔드는 각도 (체인 끝, 도)")
    # B. manual (fix or add parts by clicking)
    r = lay.row()
    r.prop(wm, "msr_ob_manual", text="직접 고치기 (조각 클릭으로 파트 추가·수정)",
           icon="TRIA_DOWN" if wm.msr_ob_manual else "TRIA_RIGHT", emboss=False)
    if wm.msr_ob_manual:
        m = lay.box()
        r = m.row()
        r.operator("msr.ob_split", text="1. 파츠 나누기" + ("  (다시 나누기)" if pcs else ""), icon="MOD_EXPLODE").auto = False
        r = m.row()
        r.prop(wm, "msr_ob_adv", text="고급 설정", icon="TRIA_DOWN" if wm.msr_ob_adv else "TRIA_RIGHT", emboss=False)
        if wm.msr_ob_adv:
            m.prop(wm, "msr_ob_min", text="작은 조각 합치기 (정점 이 수 미만)")
        if pcs:
            c = m.column()
            c.active = not sel
            c.label(text=("2. 선택 조각 %d개" % len(sel) + (" · 파트 %s" % _part_label(p) if p else ""))
                    if sel else "2. 조각을 클릭하세요 (Shift = 여러 개)", icon="RESTRICT_SELECT_OFF")
            c = m.column()
            c.enabled = bool(sel)
            c.label(text="3. 체인·마디 조정 → 파트 확정 (노랑 = 미리보기)")
            r = c.row(align=True)
            r.prop(wm, "msr_ob_single", text="본 1개", toggle=True)
            s = r.row(align=True)
            s.enabled = not wm.msr_ob_single
            s.prop(wm, "msr_ob_chains", text="체인")
            s.prop(wm, "msr_ob_segs", text="마디")
            c.row(align=True).prop(wm, "msr_ob_axis", expand=True)
            r = c.row(align=True)
            r.enabled = wm.msr_ob_axis == "DOWN" and wm.msr_ob_chains > 1 and not wm.msr_ob_single
            r.prop(wm, "msr_ob_center", text="앞·뒤 가운데 체인 (치마처럼 한 바퀴 도는 파트)")
            r = c.row(align=True)
            r.label(text="종류")
            r.prop(wm, "msr_ob_kind", expand=True)
            r = c.row(align=True)
            r.operator("msr.ob_confirm", icon="CHECKMARK")
            r.operator("msr.ob_unconfirm", icon="X")
            if p and p.get("parent_used"):
                c.label(text="부모: %s (바꾸려면 Max에서 링크)" % p["parent_used"], icon="CON_CHILDOF")
    lay.operator("msr.ob_clear", text="끝나면: 복사본 정리", icon="TRASH")

classes = (MSR_OT_ob_split, MSR_OT_ob_confirm, MSR_OT_ob_unconfirm, MSR_OT_ob_generate, MSR_OT_ob_testkeys, MSR_OT_ob_clear, MSR_OT_ob_level)
_WM_PROPS = ("msr_ob_min", "msr_ob_chains", "msr_ob_segs", "msr_ob_axis", "msr_ob_single", "msr_ob_center", "msr_ob_keep_parent", "msr_ob_lower", "msr_ob_adv", "msr_ob_manual", "msr_ob_test_amp", "msr_ob_kind", "msr_ob_bundle")


def register():
    global _HANDLE
    for c in classes:
        bpy.utils.register_class(c)
    WM = bpy.types.WindowManager
    WM.msr_ob_min = bpy.props.IntProperty(default=50, min=1, max=5000, description="이보다 정점이 적은 조각은 가까운 조각에 붙임")
    WM.msr_ob_chains = bpy.props.IntProperty(name="체인 수", default=1, min=1, max=16, update=_settings_changed)
    WM.msr_ob_segs = bpy.props.IntProperty(name="마디 수", default=3, min=1, max=12, update=_settings_changed)
    WM.msr_ob_axis = bpy.props.EnumProperty(items=[("AUTO", "길이 방향", "파트의 가장 긴 방향"), ("DOWN", "아래로", "위에서 아래 (치마·망토)")],
                                            default="AUTO", update=_settings_changed)
    WM.msr_ob_single = bpy.props.BoolProperty(default=False, update=_settings_changed, description="파트 전체를 본 하나에")
    WM.msr_ob_center = bpy.props.BoolProperty(default=True, update=_settings_changed,
                                              description="한 바퀴 도는 파트(치마)에 앞·뒤 가운데 체인을 더함. Max 에서 좌우 체인을 50:50 으로 따라 돎")
    WM.msr_ob_keep_parent = bpy.props.BoolProperty(default=True, description="Max 에서 손으로 링크를 바꾼 본은 다시 생성해도 그 부모를 그대로 둠")
    WM.msr_ob_lower = bpy.props.BoolProperty(default=False, description="멜리타 자동 본 이름: 켜면 소문자(bone_skirt_fl1_01), 끄면 f05 그대로(Bone_skirt_FL1_01)")
    WM.msr_ob_adv = bpy.props.BoolProperty(default=False, description="고급 설정 보기")
    WM.msr_ob_bundle = bpy.props.BoolProperty(default=True, description="치마·코트에 겹치거나 붙은 옷 조각(뒤 띠·겹치마 바깥 겹·프릴)은 따로 본을 만들지 않고 치마 본으로 웨이트 (끄면 1.72 처럼 별도 파트·자기 본)")
    WM.msr_ob_test_amp = bpy.props.IntProperty(default=40, min=5, max=120, description="확인 키에서 체인 끝까지 합친 회전 각도")
    WM.msr_ob_kind = bpy.props.EnumProperty(items=[("AUTO", "자동", "골반·목 위치와 모양으로 치마/망토/기타 자동 판별"),
                                                   ("SKIRT", "치마", "bone_skirt_.. (Max 레이어 bone_skirt)"),
                                                   ("CAPE", "망토", "bone_cape_.. (Max 레이어 bone_cape)"),
                                                   ("OTHER", "기타", "bone_objNN_.. (Max 레이어 bone_etc)")], default="AUTO")
    WM.msr_ob_manual = bpy.props.BoolProperty(default=False, description="조각을 직접 클릭해서 파트를 추가하거나 고치기")
    if _HANDLE is None:
        _HANDLE = bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_VIEW")
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister():
    global _HANDLE
    if _HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_HANDLE, "WINDOW")
        _HANDLE = None
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    for p in _WM_PROPS:
        try:
            delattr(bpy.types.WindowManager, p)
        except Exception:
            pass
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
