# body_template.py  (Claude, 2026-10-24)
# 기본 바디 웨이트 템플릿: 작업자(User)가 다듬은 바디 웨이트(보조본 포함)를 Bip 뼈대 기준으로 저장해 두고,
# 새 캐릭터는 정점을 뼈대 비율로 기준 캐릭터 공간에 옮겨 가장 가까운 기준 정점들의 웨이트를 받는다.
# (기준 캐릭터 자신에게 쓰면 그대로 같은 값)
import json, os, re
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TPL_PATH = os.path.join(HERE, "body_template_melitta.json")
SKIP = ("skirt", "cape", "hair")
# 10/31: 팔을 내린 캐릭터는 손이 엉덩이 옆 옷자락 바로 옆에 있어서, 옷자락 정점이 손·아래팔 본 기준으로 옮겨지고
# 멜리타 손·팔 정점의 웨이트(forearm twist1·finger 100%)를 받아 팔을 들면 날개처럼 솟았음.
# 떨어진 조각(섬) 중 '가장 가까운 Bip 본이 팔인 정점'이 이 비율보다 적으면 몸통 옷 조각: 팔 본은 매칭·웨이트에서 뺌
ARM_SEG_RE = re.compile(r"(clavicle|upperarm|uparm|forearm|foretwist|hand|finger)", re.I)
ARM_W_RE = re.compile(r"(clavicle|upperarm|uparm|forearm|foretwist|hand|finger|elbow)", re.I)
TORSO_ISLAND_ARM = 0.2
# 11/01: 다리·골반이 가장 가까운 정점이 팔보다 많은 섬도 몸통 옷 (지젤 치마 섬 1200정점: 손 옆이라 팔 31% 로 0.2 를 넘었음)
LEG_SEG_RE = re.compile(r"(pelvis|thigh|calf|foot|toe)", re.I)
UPARM_SEG_RE = re.compile(r"(clavicle|upperarm|uparm)", re.I)


def _segments(arm):
    mw = arm.matrix_world
    out = []
    for b in arm.data.bones:
        n = b.name
        if not n.startswith("Bip01 ") or "Nub" in n or "Footsteps" in n or n == "Bip01":
            continue
        h = np.array(tuple(mw @ b.head_local)); t = np.array(tuple(mw @ b.tail_local))
        R = np.array((mw.to_3x3() @ b.matrix_local.to_3x3()).normalized())   # columns = bone axes (world)
        L = float(np.linalg.norm(t - h))
        if L < 1e-6:
            continue
        out.append((n, h, t, R, L))
    return out


def _seg_dist(P, h, t):
    d = t - h; L2 = d @ d
    s = np.clip(((P - h) @ d) / L2, 0, 1)
    return np.linalg.norm(P - (h + s[:, None] * d), axis=1)


def _mesh_arrays(obj):
    me = obj.data
    mw = obj.matrix_world; nm = mw.to_3x3().inverted().transposed()
    P = np.array([tuple(mw @ v.co) for v in me.vertices])
    N = np.array([tuple((nm @ v.normal).normalized()) for v in me.vertices])
    return P, N


def build(arm, obj, user_w, path=TPL_PATH, note="", keep=None):
    """user_w: list of dict(bone->weight) per vertex of obj; keep: bool array (vertices to store)"""
    P, N = _mesh_arrays(obj)
    segs = _segments(arm)
    bones = sorted({k for w in user_w for k in w if not any(s in k.lower() for s in SKIP)})
    bi = {b: i for i, b in enumerate(bones)}
    rows_i, rows_w, keepi = [], [], []
    for v, w in enumerate(user_w):
        if keep is not None and not keep[v]:
            continue
        ww = {k: x for k, x in w.items() if k in bi}
        if not ww or sum(ww.values()) < 0.5:          # skirt / cape vertices -> not body samples
            continue
        it = sorted(ww.items(), key=lambda kv: -kv[1])[:4]
        s = sum(x for _, x in it)
        rows_i.append([bi[k] for k, _ in it] + [-1] * (4 - len(it)))
        rows_w.append([x / s for _, x in it] + [0.0] * (4 - len(it)))
        keepi.append(v)
    data = dict(version=1, note=note, bones=bones,
                segs=[dict(name=n, h=h.tolist(), t=t.tolist(), R=R.tolist(), L=L) for n, h, t, R, L in segs],
                P=np.round(P[keepi], 6).tolist(), N=np.round(N[keepi], 4).tolist(),
                wi=rows_i, ww=np.round(rows_w, 5).tolist())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    return len(keepi), len(bones)


_C = {}


def _load(path):
    m = os.path.getmtime(path)
    if path in _C and _C[path][0] == m:
        return _C[path][1]
    d = json.load(open(path, encoding="utf-8"))
    from mathutils.kdtree import KDTree
    P = np.array(d["P"]); kd = KDTree(len(P))
    for i, p in enumerate(P):
        kd.insert(p.tolist(), i)
    kd.balance()
    ref = dict(bones=d["bones"], P=P, N=np.array(d["N"]), wi=np.array(d["wi"]), ww=np.array(d["ww"]), kd=kd,
               segs={s["name"]: (np.array(s["h"]), np.array(s["t"]), np.array(s["R"]), s["L"]) for s in d["segs"]})
    _C[path] = (m, ref)
    return ref


def _islands(me):
    """vertex -> island label (edge connected)"""
    nv = len(me.vertices)
    ed = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", ed)
    par = np.arange(nv)

    def root(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for a, b in ed.reshape(-1, 2):
        ra, rb = root(a), root(b)
        if ra != rb:
            par[rb] = ra
    return np.unique([root(i) for i in range(nv)], return_inverse=True)[1]


def apply(arm, obj, path=TPL_PATH, limit=4, k=8, nseg=3, mask=None):
    """replace obj vertex-group weights with template weights. mask: bool array of vertices to change (None = all)"""
    if not os.path.exists(path):
        return "바디 템플릿 없음"
    ref = _load(path)
    P, N = _mesh_arrays(obj)
    segs = [s for s in _segments(arm) if s[0] in ref["segs"]]
    if len(segs) < 10:
        return "바디 템플릿: 맞는 Bip 본이 부족함"
    D = np.stack([_seg_dist(P, h, t) for _, h, t, _, _ in segs], 1)       # (V, S)
    # 몸통 옷 조각(팔 가까운 정점이 적은 섬): 팔 선분으로 옮기지 않음
    armcol = np.array([bool(ARM_SEG_RE.search(s[0])) for s in segs])
    torso_v = np.zeros(len(P), bool)
    if armcol.any() and (~armcol).any() and len(P):
        lab = _islands(obj.data)
        near = np.argmin(D, 1)
        share = np.bincount(lab, weights=armcol[near].astype(float)) / np.bincount(lab)
        legcol = np.array([bool(LEG_SEG_RE.search(s[0])) for s in segs])
        upcol = np.array([bool(UPARM_SEG_RE.search(s[0])) for s in segs])
        leg = np.bincount(lab, weights=legcol[near].astype(float)) / np.bincount(lab)
        up = np.bincount(lab, weights=upcol[near].astype(float)) / np.bincount(lab)
        # 위팔·쇄골에 걸친 섬(팔이 붙은 몸 메쉬)은 빼고: 손 옆에 늘어진 옷자락만
        torso_v = (share[lab] < TORSO_ISLAND_ARM) | ((leg[lab] > share[lab]) & (up[lab] < 0.01))
        D[np.ix_(torso_v, armcol)] = np.inf
    armrow = np.array([any(b >= 0 and x > 0.02 and ARM_W_RE.search(ref["bones"][b]) for b, x in zip(bi, bw))
                       for bi, bw in zip(ref["wi"], ref["ww"])])
    # 11/01: 몸통 옷 조각은 '팔·손 아닌 템플릿 정점' 만으로 찾음. 예전엔 가까운 32개가 모두 팔이면 팔 값으로 되돌아가서
    # (or hits / or acc) 지젤 치마가 팔 올릴 때 손을 따라감
    body_kd, body_ids = None, None
    if torso_v.any() and (~armrow).any():
        from mathutils.kdtree import KDTree
        body_ids = np.where(~armrow)[0]
        body_kd = KDTree(len(body_ids))
        for j, i in enumerate(body_ids):
            body_kd.insert(ref["P"][i].tolist(), j)
        body_kd.balance()
    order = np.argsort(D, 1)[:, :nseg]
    Pm = np.zeros_like(P); Nm = np.zeros_like(N)
    for v in range(len(P)):
        ds = D[v, order[v]]
        w = 1.0 / (ds + 1e-4) ** 4; w /= w.sum()
        for j, sidx in enumerate(order[v]):
            n, h, t, R, L = segs[sidx]
            h2, t2, R2, L2 = ref["segs"][n]
            q = R.T @ (P[v] - h) / L
            Pm[v] += w[j] * (h2 + R2 @ (q * L2))
            Nm[v] += w[j] * (R2 @ (R.T @ N[v]))
    Nm /= np.linalg.norm(Nm, axis=1, keepdims=True) + 1e-9
    bones = ref["bones"]
    vg = {g.name: g for g in obj.vertex_groups}
    for b in bones:
        if b not in vg and b in arm.data.bones:
            vg[b] = obj.vertex_groups.new(name=b)
    me = obj.data
    nchg = 0; miss = set()
    same = len(ref["P"]) == len(P)      # the template's own mesh: vertex v -> stored vertex v when it maps onto it
    for v in range(len(P)):
        if mask is not None and not mask[v]:
            continue
        if same and (np.linalg.norm(Pm[v] - ref["P"][v]) < 1e-4 or np.linalg.norm(P[v] - ref["P"][v]) < 1e-4):
            hits = [(None, v, 0.0)]          # exact own value (overlapping seam vertices are not averaged)
        else:
            hits = ref["kd"].find_n(Pm[v].tolist(), k)
            if torso_v[v] and body_kd is not None:
                # 몸통 옷 조각: 멜리타의 팔·손 정점은 건너뛰고 몸 쪽 정점에서 받기
                hits = [(co, int(body_ids[j]), d) for co, j, d in body_kd.find_n(Pm[v].tolist(), k)]
        good = [h for h in hits if ref["N"][h[1]] @ Nm[v] > 0.2] or hits
        good = good[:4]
        acc = {}
        wsum = 0.0
        for co, i, dist in good:
            iw = 1.0 / (dist ** 2 + 1e-10)
            wsum += iw
            for bidx, x in zip(ref["wi"][i], ref["ww"][i]):
                if bidx >= 0 and x > 0:
                    acc[bones[bidx]] = acc.get(bones[bidx], 0.0) + iw * x
        acc = {b: x / wsum for b, x in acc.items() if b in vg}
        if torso_v[v] and hits[0][0] is not None:
            acc = {b: x for b, x in acc.items() if not ARM_W_RE.search(b)} or acc
        miss |= {b for b in acc if b not in vg}
        it = sorted(acc.items(), key=lambda kv: -kv[1])[:limit]
        s = sum(x for _, x in it)
        if s <= 0:
            continue
        for g in list(me.vertices[v].groups):
            obj.vertex_groups[g.group].remove([v])
        for b, x in it:
            vg[b].add([v], x / s, "REPLACE")
        nchg += 1
    return "바디 템플릿: 정점 %d" % nchg


def has_bones(names, path=TPL_PATH):
    """True when the template carries any of these bones (e.g. breast bones from the worker's hand weights)"""
    try:
        return bool(set(names) & set(_load(path)["bones"]))
    except Exception:
        return False
