# hair_bones.py (Claude, 2026-10-27)
# 헤어 본 자동 (가닥 찾기): 머리카락 메시(카드)를 덩어리로 나눠 가닥을 찾고, 가닥마다 체인 본 + 웨이트를 만듦.
#   계산은 2_dev\hair_autorig\hair_autorig.py (har_analyze) 를 그대로 옮기고 규칙 하나 추가:
#   같은 쪽(앞·뒤 + 좌·우)에 긴 가닥이 있을 때 마디 1.25배보다 짧은 가닥은 체인 없이 Head 고정 (멜리타 f05 옆 가닥).
#   그쪽에 짧은 가닥만 있으면 체인을 만듦 (지젤 앞머리).
# 구조·이름 (멜리타 f05, tools\parts 밀어내기와 같은 규칙):
#   Bip01 Head -> Bone_hair_root -> Bone_hair_FR1_00 (연결, 웨이트 없음) -> _01 .. _NN -> _end
#   라벨: F/B (앞·뒤) + L/R/C, 번호는 같은 라벨 안에서 x 순서.
# 흐름: '헤어 본 만들기' = 블렌더 본 + 블렌더 헤어 웨이트 + Max 에 본. Max 웨이트는 '3. 스킨 적용 (일괄)' 때.
#   일괄 적용 뒤 Max 헤어 메시에 rt_batch 표시 -> 다음 일괄 때는 Max 헤어 값(작업자가 칠한 값) 그대로.
import json
import os
import re
import math
import time
import heapq
import bpy
import numpy as np
from mathutils import Vector

HAIR_KEY = "msr_ob_hair_bones"   # armature: hair bones made here (parents first); msr_ob_* -> carried over by a re-import
MAX_THICK = 3.0                  # 움직이는 헤어 본 굵기 상한 (Max 단위). 1.61: 5 -> 3 (단발 뒤 갈래가 큰 정육면체로 보이던 것)
ASPECT_MAX = 2.0                 # 1.61: 헤어 본 상자 긴 변 <= 짧은 변 x 이 값 (단발이 넓은 판자로 보이던 것)
SHAPE_KEY = "msr_ob_hair_shape"  # armature: json {bone: {w, h, taper, box}} Max 본 모양 (2026-10-29)
UP_KEY = "msr_ob_hair_up"        # armature: json {bone: bone Z axis (Max world)} - level at the chain start, carried down the chain
HW_KEY = "msr_hair_w"            # scene: json {"obj": hair mesh, "w": {bone: [[vertex, weight], ...]}}
LAYER = "bone_hair"
END_LEN = 2.0                    # Max units (f05 _end)
ROOT_TILT = 25.0                 # Bone_hair_root: max lean from straight up (degrees)
CHAIN_RATIO = 1.25               # chains shorter than this many segments stay on the Head
# 4단계 (2026-11-01, 정현 결정): 가닥은 메시에서 찾되(v2 analyze) 체인 구조는 왼쪽·가운데 기준으로 좌우 대칭.
#   오른쪽 체인 = 왼쪽 체인의 거울, 가운데 체인은 x = Head (정중앙). 오른쪽에만 있는 가닥(멜리타 f_test 의 FR2)은 체인을 안 만들고
#   그 카드는 가장 가까운 체인(없으면 Head)에 웨이트. 옵션은 코드 값만 (UI 변경 없음). 시험용 환경변수 MSR_HAIR_SYM=off|lr.
HAIR_SYM = "lr"                  # "lr": 왼쪽·가운데 가닥만 쓰고 오른쪽은 거울 / "off": 1.9 방식 (찾은 가닥 그대로, 비대칭)
SYM_FRONT = True                 # 앞머리(f*)도 거울. False 면 앞머리는 찾은 대로 두고 옆·뒤(b*)만 거울
SYM_RIGHT_ONLY = "mirror"        # 왼쪽에 짝이 없는 오른쪽 가닥(거울 선이 attach 밖): "mirror" = 남기고 왼쪽에 거울(지젤 앞머리) /
                                 #   "drop" = 체인 없음(카드는 가까운 체인·Head) / "keep" = 찾은 오른쪽 체인 전부 그대로(비대칭)
                                 #   짝이 있는 오른쪽 가닥(멜리타 FR2)은 mirror·drop 모두 체인 없음
SYM_CENTER_X = 2.5               # 체인 마디 평균 x 가 Head 에서 이 안이면 가운데(c) 체인
# 집 확인 (2026-11-01, 정현 요청 "안겹·겉겹은 생성 시 간단한 버전"): 같은 쪽(앞/뒤 + 왼/가운데/오른)에서 나란히 겹치는 가닥
#   (카미엘 BL1·BL2 처럼 안겹·겉겹)을 한 줄기로 합침 → 체인 수·본 수가 줄어듦. 합친 체인은 두 가닥 정점을 다 받고
#   마디 수는 합친 메시 길이로 다시 계산(root·_00·마디·_end 그대로), 거울(_symmetrize)은 그 뒤라 좌우 대칭 유지.
#   False 면 2.0 그대로(겹마다 체인, 물리용). 시험용 환경변수 MSR_HAIR_MERGE=0|1.
HAIR_MERGE_LAYERS = True         # True: 간단판(겹 합침, 기본) / False: 겹마다 체인(2.0 방식)
HAIR_MERGE_DIST = 6.0            # 두 가닥 선의 평균 거리(Max cm)가 이 안이면 '나란히 겹친 가닥'
HAIR_MERGE_OVERLAP = 0.5         # 두 가닥의 높이(z) 범위가 짧은 쪽의 이 비율 이상 겹칠 때만


def _flow():
    import sys
    return sys.modules.get("max_style_rig")


# ---------------------------------------------------------------- analysis (Max units, no bpy)
def _components(nv, polys):
    parent = list(range(nv))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for p in polys:
        r = find(p[0])
        for q in p[1:]:
            rq = find(q)
            if rq != r:
                parent[rq] = r
    groups = {}
    for i in range(nv):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _adjacency(polys):
    adj = {}
    for p in polys:
        n = len(p)
        for i in range(n):
            a, b = p[i], p[(i + 1) % n]
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    return adj


def _geodesic(co, adj, verts, sources):
    dist = {v: math.inf for v in verts}
    h = []
    for s in sources:
        dist[s] = 0.0
        heapq.heappush(h, (0.0, s))
    while h:
        d, u = heapq.heappop(h)
        if d > dist[u]:
            continue
        for w in adj.get(u, ()):
            nd = d + float(np.linalg.norm(co[u] - co[w]))
            if nd < dist.get(w, math.inf):
                dist[w] = nd
                heapq.heappush(h, (nd, w))
    return dist


def _resample(pts, n):
    pts = np.asarray(pts, float)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] < 1e-9:
        return np.repeat(pts[:1], n, axis=0)
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, pts[:, k]) for k in range(3)], axis=1)


def _cut_from_z(line, zstart):
    for i in range(len(line) - 1):
        a, b = line[i], line[i + 1]
        if a[2] >= zstart >= b[2] and a[2] != b[2]:
            t = (a[2] - zstart) / (a[2] - b[2])
            return np.array([a + (b - a) * t] + [q for q in line[i + 1:]])
    if line[0][2] < zstart:
        return np.array(line)
    return None


def _project(line, p):
    best = (math.inf, 0.0)
    acc = 0.0
    for i in range(len(line) - 1):
        a, b = line[i], line[i + 1]
        ab = b - a
        L2 = float(ab @ ab)
        L = math.sqrt(L2)
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, float((p - a) @ ab) / L2))
        d = float(np.linalg.norm(p - (a + ab * t)))
        if d < best[0]:
            best = (d, acc + L * t)
        acc += L
    return best[1], best[0]


def analyze_v1(co, polys, head, seg_len=8.0, link=9.0, start_up=4.0, wide_width=10.0, col_width=9.0, front_y=2.0,
            blend=0.3, head_ramp=0.3, attach=8.0, max_seg=10, min_seg=2, bins=12, top_ratio=0.03,
            short_ratio=0.75, chain_ratio=CHAIN_RATIO, limit=4, log=None):
    """hair cards -> dict(chains=[dict(name, joints)], bones=["Head", "FR1_01", ..], weights=[[(bone idx, w)] per vertex])"""
    log = log or (lambda *a: None)
    co = np.asarray(co, float)
    nv = len(co)
    head = np.asarray(head, float)
    zstart = head[2] + start_up
    adj = _adjacency(polys)
    comps = [c for c in _components(nv, polys) if len(c) > 3]
    # 1) double-sided cards: keep one, copy its weights to the twin at the end
    uniq, keys, twins = [], [], []
    for c in comps:
        cen = co[c].mean(axis=0)
        dup = None
        for ki, (cc, ce) in enumerate(keys):
            if cc == len(c) and np.linalg.norm(ce - cen) < 0.05:
                dup = ki
                break
        if dup is not None:
            twins.append((c, uniq[dup]))
            continue
        keys.append((len(c), cen))
        uniq.append(c)
    log("카드 %d -> 겹침 제거 %d" % (len(comps), len(uniq)))
    # 2) centre line of each card by surface distance from its top (wide cards split in columns)
    pcards = []
    for ci, c in enumerate(uniq):
        z = co[c, 2]
        ext = z.max() - z.min()
        top = [v for v in c if co[v, 2] >= z.max() - max(ext * top_ratio, 0.05)]
        dist = _geodesic(co, adj, c, top)
        dd = np.array([dist[v] for v in c])
        dd[~np.isfinite(dd)] = 0
        dmax = dd.max()
        xs = co[c, 0]
        width = xs.max() - xs.min()
        ncol = max(2, int(round(width / col_width))) if width > wide_width else 1
        edges = np.linspace(xs.min(), xs.max(), ncol + 1)
        for k in range(ncol):
            if ncol == 1:
                sel = np.arange(len(c))
            else:
                last = k == ncol - 1
                sel = np.where((xs >= edges[k]) & ((xs <= edges[k + 1]) if last else (xs < edges[k + 1])))[0]
            if len(sel) < 3:
                continue
            cs = [c[i] for i in sel]
            ds = dd[sel]
            b = np.minimum((ds / max(dmax, 1e-9) * bins).astype(int), bins - 1)
            line = [co[cs][b == bi].mean(axis=0) for bi in range(bins) if (b == bi).any()]
            if len(line) < 2:
                continue
            line = np.array(line)
            pcards.append(dict(verts=cs, line=line, tip=line[-1], card=ci, split=(ncol > 1)))

    # 3) front / back, left / right, then cluster the card tips
    def label(pc):
        cen = co[pc['verts']].mean(axis=0)
        fb = 'F' if cen[1] < head[1] + front_y else 'B'
        dx = pc['tip'][0] - head[0]
        side = 'C' if (pc['split'] and abs(dx) < 2.0) else ('R' if dx < 0 else 'L')
        return fb + side
    groups, shorts = {}, []
    for i, pc in enumerate(pcards):
        cut = _cut_from_z(pc['line'], zstart)
        ln = 0.0 if cut is None or len(cut) < 2 else float(np.linalg.norm(np.diff(cut, axis=0), axis=1).sum())
        if ln < seg_len * short_ratio:
            shorts.append(i)
            continue
        groups.setdefault(label(pc), []).append(i)
    chains = []
    for lab in sorted(groups):
        clusters = [[i] for i in groups[lab]]
        while True:
            best, bp = math.inf, None
            for a in range(len(clusters)):
                for b in range(a + 1, len(clusters)):
                    d = np.mean([np.linalg.norm(pcards[i]['tip'] - pcards[j]['tip']) for i in clusters[a] for j in clusters[b]])
                    if d < best:
                        best, bp = d, (a, b)
            if bp is None or best > link:
                break
            a, b = bp
            clusters[a] += clusters[b]
            del clusters[b]
        clusters.sort(key=lambda cl: np.mean([pcards[i]['tip'][0] for i in cl]))
        cand = []
        for cl in clusters:
            mean = np.mean([_resample(pcards[i]['line'], 24) for i in cl], axis=0)
            cut = _cut_from_z(mean, zstart)
            length = 0.0 if cut is None or len(cut) < 2 else float(np.linalg.norm(np.diff(cut, axis=0), axis=1).sum())
            cand.append((cl, cut, length))
        # a short strand next to a long one on the same side stays on the Head (Melitta f05 side strands);
        # when the side has only short strands they still get a chain (Gisele bangs)
        has_long = any(ln >= seg_len * chain_ratio for _, _, ln in cand)
        n = 0
        for cl, cut, length in cand:
            members = [v for i in cl for v in pcards[i]['verts']]
            if length < seg_len * short_ratio or (has_long and length < seg_len * chain_ratio):
                log("%s 짧은 가닥 (길이 %.1f) -> Head" % (lab, length))
                continue
            n += 1
            nseg = max(min_seg, min(max_seg, int(length / seg_len + 0.5)))
            chains.append(dict(name="%s%d" % (lab, n), joints=_resample(cut, nseg + 1), members=members, length=length))
            log("체인 %s%d: 카드 %d장, 길이 %.1f, 마디 %d" % (lab, n, len(cl), length, nseg))
    # 3.5) short cards hang on the nearest chain when close (chain shape unchanged)
    nat = 0
    for i in shorts:
        vs = pcards[i]['verts']
        sample = vs[::max(1, len(vs) // 40)]
        best, bc = math.inf, None
        for c in chains:
            d = float(np.mean([_project(c['joints'], co[v])[1] for v in sample]))
            if d < best:
                best, bc = d, c
        if bc is not None and best <= attach:
            bc['members'] = bc['members'] + list(vs)
            nat += 1
    log("짧은 카드 %d장 중 %d장 체인에 붙임" % (len(shorts), nat))
    # 4) weights along each chain (blend at the joints, soft start from the Head)
    bones = ["Head"]
    wt = [[(0, 1.0)] for _ in range(nv)]
    for ch in chains:
        j = ch['joints']
        nseg = len(j) - 1
        segl = float(np.linalg.norm(np.diff(j, axis=0), axis=1).sum()) / nseg
        base = len(bones)
        bones += ["%s_%02d" % (ch['name'], k) for k in range(1, nseg + 1)]
        half = blend / 2.0
        for v in ch['members']:
            s, _ = _project(j, co[v])
            if s <= 1e-6:
                continue
            u = s / segl
            k = min(int(u), nseg - 1)
            f = u - k
            w = {k: 1.0}
            if f < half and k > 0:
                t = 0.5 + f / (2 * half) * 0.5
                w = {k: t, k - 1: 1 - t}
            elif f > 1 - half and k < nseg - 1:
                t = 0.5 + (1 - f) / (2 * half) * 0.5
                w = {k: t, k + 1: 1 - t}
            if head_ramp > 0 and u < head_ramp:
                hw = 1.0 - u / head_ramp
                w = {i: x * (1 - hw) for i, x in w.items()}
                w[-1] = hw
            items = sorted([((0 if i == -1 else base + i), x) for i, x in w.items() if x > 1e-4], key=lambda t: -t[1])[:limit]
            tot = sum(x for _, x in items)
            wt[v] = [(i, x / tot) for i, x in items]
    for dupv, kept in twins:
        kc = co[kept]
        for v in dupv:
            wt[v] = list(wt[kept[int(np.argmin(((kc - co[v]) ** 2).sum(axis=1)))]])
    return dict(chains=chains, bones=bones, weights=wt)


# ---------------------------------------------------------------- Blender
def hair_obj(context, store=True):
    """hair mesh among the imported objects (name has 'hair'); the panel can pick another one.
    store=False for the panel draw (no property writes while drawing)"""
    wm = context.window_manager
    o = bpy.data.objects.get(wm.msr_hair)
    if o is not None and o.type == "MESH":
        return o
    f = _flow()
    col = bpy.data.collections.get(f.FLOW_COL) if f else None
    pool = list(col.objects) if col else list(context.view_layer.objects)
    arm, body, face, tooth = f.flow_objects(context)
    c = [o for o in pool if o.type == "MESH" and "hair" in o.name.lower() and o not in (body, face, tooth)]
    o = max(c, key=lambda o: len(o.data.vertices)) if c else None
    if store:
        wm.msr_hair = o.name if o else ""
    return o


_CACHE = {}     # 2.2: 미리보기 때 같은 메시 분석을 다시 안 하게 {key: (res, co, head, log lines)}


def _analysis(context, arm, hair, seg_len=8.0, start_up=4.0, fresh=False):
    """hair mesh (Max units) -> (analyze result, co, head, Head bone name, log lines). 같은 메시면 저장해 둔 결과"""
    f = _flow()
    mb = f._max_bridge()
    if mb is None:
        raise RuntimeError("Max 연결이 필요해요 (Max 좌표로 계산)")
    pre = f.bip_prefix(arm) or "Bip01"
    hn = pre + " Head"
    if hn not in arm.data.bones:
        raise RuntimeError("%s 가 없어요" % hn)
    unit, off = f._max_xform(arm, mb)
    mw = hair.matrix_world
    co = np.array([tuple((mw @ v.co) * unit + off) for v in hair.data.vertices])
    head = np.array(tuple((arm.matrix_world @ arm.data.bones[hn].head_local) * unit + off))
    key = (hair.name, hair.data.as_pointer(), len(co), round(float(co.sum()), 3), tuple(np.round(head, 3)), seg_len, start_up)
    if not fresh and _CACHE.get("key") == key:
        res, lines = _CACHE["val"]
        return res, co, head, hn, list(lines)
    polys = [list(p.vertices) for p in hair.data.polygons]
    lines = []
    # 10/30: 완성 파일 참고값 (secondary_weight_ref.json): 위아래 마디 섞임 폭, 뿌리 쪽 Head 섞임 길이 (체인 길이 비율)
    kw = {}
    try:
        import object_bones as _ob
        R = _ob.load_ref().get("hair", {})
        kw = dict(blend=min(max(R.get("along_blend", 0.3), 0.1), 0.9), head_frac=R.get("bip_mixed_top", 0.54) * 0.25)
    except Exception as e:
        print("[hair_bones] 참고값 없음:", e)
    res = analyze(co, polys, head, seg_len=seg_len, start_up=start_up, log=lambda s: lines.append(s), **kw)
    if not res["chains"]:
        raise RuntimeError("가닥을 못 찾았어요 (머리 메시: %s)" % hair.name)
    _CACHE.clear()
    _CACHE.update(key=key, val=(res, list(lines)))
    return res, co, head, hn, lines


def generate(context, arm, hair, seg_len=8.0, start_up=4.0, branch="BASIC", density="NORMAL", fresh=True):
    """hair bones in the Blender armature + weights (scene HW_KEY). returns (made, old, analysis log)
    2.2: branch / density = 패널 선택 (기본·보통 = 2.1 과 같음)"""
    res, co, head, hn, lines = _analysis(context, arm, hair, seg_len, start_up, fresh=fresh)
    res = variant(res, co, head, branch, density, log=lambda s: lines.append(s))
    f = _flow()
    unit, off = f._max_xform(arm, f._max_bridge())
    old = list(arm.get(HAIR_KEY, []))
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    hs = arm.hide_select
    arm.hide_select = False
    for ob in list(context.view_layer.objects.selected):
        ob.select_set(False)
    arm.hide_set(False)
    arm.select_set(True)
    context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    # old hair bones (made here, or the hair rig the file already had: Bone_hair_*) go, in Max too
    old = sorted(set(old) | {b.name for b in eb if b.name.lower().startswith("bone_hair_")})
    for n in old:
        b = eb.get(n)
        if b:
            eb.remove(b)
    inv = arm.matrix_world.inverted()
    made = []
    ups = {}

    def level(d):
        z = np.cross([0.0, 0.0, 1.0], d)
        return z / np.linalg.norm(z) if np.linalg.norm(z) > 1e-3 else np.array([1.0, 0.0, 0.0])

    def carry(z, d):
        # previous bone's Z axis turned onto this bone (no flip when a long strand bends back / down)
        z = z - (z @ d) * d
        return z / np.linalg.norm(z) if np.linalg.norm(z) > 1e-3 else level(d)

    def nrm(v):
        v = np.asarray(v, float)
        return v / max(np.linalg.norm(v), 1e-9)

    def bl(p):
        return inv @ ((Vector(tuple(p)) - off) / unit)

    def new_bone(name, h, t, parent, deform):
        b = eb.new(name)
        b.head, b.tail = bl(h), bl(t)
        b.parent, b.use_connect, b.use_deform = parent, False, deform
        made.append(name)
        return b
    # root: from the Head up towards the chain starts (HAR_Root.ms), kept on the centre line (no side tilt)
    # and at most ROOT_TILT degrees back/forward from straight up (Melitta f05 ~20; many back strands would lay it down)
    c = np.mean([ch["joints"][0] for ch in res["chains"]], axis=0)
    dv = c - head
    L = float(np.linalg.norm(dv))
    dv = np.array([0.0, dv[1], dv[2]])
    if np.linalg.norm(dv) < 1e-6 or dv[2] <= 0:
        dv = np.array([0.0, 0.0, 1.0])
    ang = min(math.degrees(math.atan2(abs(dv[1]), dv[2])), ROOT_TILT)
    dv = np.array([0.0, math.copysign(math.sin(math.radians(ang)), dv[1]), math.cos(math.radians(ang))])
    shape = {}
    root = new_bone("bone_hair_root", head, head + dv * max(L * 0.6, 2.0), eb.get(hn), False)
    ups[root.name] = level(dv)
    shape[root.name] = dict(w=1.0, h=1.0, taper=90.0, box=False)
    ren = {}
    for ch in res["chains"]:
        J = ch["joints"]
        base = "bone_hair_%s_" % ch["name"].upper()     # 방향 글자만 대문자 (10/30): bone_hair_BL1_01
        prev = new_bone(base + "00", head, J[0], root, False)        # link bone, no weight (push: no rotate)
        d = nrm(J[0] - head)
        z = ups[prev.name] = level(d)
        for i in range(len(J) - 1):
            prev = new_bone(base + "%02d" % (i + 1), J[i], J[i + 1], prev, True)
            ren["%s_%02d" % (ch["name"], i + 1)] = prev.name
            d = nrm(J[i + 1] - J[i])
            z = ups[prev.name] = carry(z, d)
        prev = new_bone(base + "end", J[-1], J[-1] + d * END_LEN, prev, False)
        ups[prev.name] = carry(z, d)
        # 본 굵기: 키 안 들어가는 본(root·_00·_end) = 1 (박스 끔), 움직이는 본 = 그 마디 메쉬 단면 크기 (박스 켬)
        for nm in (base + "00", base + "end"):
            shape[nm] = dict(w=1.0, h=1.0, taper=90.0, box=False)
        mem = np.array(ch.get("core", ch.get("members", [])), int)
        Pm = co[mem] if len(mem) else np.zeros((0, 3))
        for i in range(len(J) - 1):
            nm = base + "%02d" % (i + 1)
            a, b = J[i], J[i + 1]
            ab = b - a
            L2 = max(float(ab @ ab), 1e-9)
            t = ((Pm - a) @ ab) / L2 if len(Pm) else np.zeros(0)
            Z = np.asarray(ups[nm], float)
            dn = ab / math.sqrt(L2)
            Y = np.cross(Z, dn)
            Y = Y / max(np.linalg.norm(Y), 1e-9)

            def ext(sel):
                if sel.sum() < 4:
                    return None
                Q = Pm[sel] - a
                Q = Q - np.outer(Q @ dn, dn)
                perp = np.linalg.norm(Q, axis=1)
                sel2 = perp <= max(np.median(perp) * 2.5, 1.0)          # 멀리 떨어진 카드는 빼고 그 마디 덩어리만
                Q = Q[sel2]
                if len(Q) < 4:
                    return None
                qy, qz = Q @ Y, Q @ Z
                return (float(np.percentile(qy, 90) - np.percentile(qy, 10)), float(np.percentile(qz, 90) - np.percentile(qz, 10)))
            whole = ext((t >= 0) & (t <= 1)) if len(t) else None
            if whole is None:
                shape[nm] = dict(w=2.0, h=2.0, taper=50.0, box=True)
                continue
            st = ext((t >= 0) & (t <= 0.35)) or whole
            en = ext((t >= 0.65) & (t <= 1)) or whole
            w = min(max(st[0], 0.8), MAX_THICK)       # 너무 굵으면 MAX_THICK 을 넘지 않게 (10/29 5, 1.61 에서 3)
            h = min(max(st[1], 0.8), MAX_THICK)
            k = max(en[0], 0.5) / w * 0.5 + max(en[1], 0.5) / h * 0.5
            tp = float(np.clip((1.0 - k) * 100.0, 0.0, 80.0))
            w, h = min(w, h * ASPECT_MAX), min(h, w * ASPECT_MAX)      # 1.61: 납작함 제한 (테이퍼는 제한 전 크기로)
            shape[nm] = dict(w=round(w, 2), h=round(h, 2), taper=tp, box=True)
    # 1.61: 좌우 거울 체인(fr*·br*)은 굵기도 왼쪽(fl*·bl*) 마디 그대로 - 오른쪽만 정점을 안 추려 더 굵게 나오던 것
    if res.get("sym", HAIR_SYM) != "off":
        for ch in res["chains"]:
            n = ch["name"]
            if len(n) < 2 or n[1] != "r":
                continue
            rb, lb = "bone_hair_%s_" % n.upper(), "bone_hair_%s_" % (n[0] + "l" + n[2:]).upper()
            for nm in [x for x in shape if x.startswith(rb)]:
                if lb + nm[len(rb):] in shape:
                    shape[nm] = dict(shape[lb + nm[len(rb):]])
    _align_rolls(arm, eb, ups)
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.hide_select = hs
    arm[HAIR_KEY] = made
    arm[UP_KEY] = json.dumps({n: [float(x) for x in v] for n, v in ups.items()})
    arm[SHAPE_KEY] = json.dumps(shape)
    show_boxes(arm, made, unit)
    W = {}
    for vi, row in enumerate(res["weights"]):
        for i, w in row:
            n = hn if i == 0 else ren[res["bones"][i]]
            W.setdefault(n, []).append([vi, float(w)])
    context.scene[HW_KEY] = json.dumps({"obj": hair.name, "w": W})
    apply_weights(context, arm, hair)
    return made, old, lines


def apply_weights(context, arm, hair):
    """stored hair weights -> the hair mesh vertex groups (whole skin of the hair mesh) + Armature modifier"""
    try:
        d = json.loads(context.scene.get(HW_KEY, "{}") or "{}")
    except Exception:
        d = {}
    W = d.get("w") or {}
    if not W or len(hair.data.vertices) <= max(v for lst in W.values() for v, _ in lst):
        return 0
    for g in list(hair.vertex_groups):
        hair.vertex_groups.remove(g)
    for n, lst in W.items():
        g = hair.vertex_groups.new(name=n)
        for vi, w in lst:
            g.add([vi], w, "REPLACE")
    mods = [m for m in hair.modifiers if m.type == "ARMATURE"]
    if mods:
        mods[0].object = arm
    else:
        hair.modifiers.new("Armature", "ARMATURE").object = arm
    return len(hair.data.vertices)


def push_bones(context, arm, made, old, hair):
    """Max: old hair bones out, new ones in (bone_hair layer), hair mesh loses its batch mark (new weights go on next apply)"""
    f = _flow()
    mb = f._max_bridge()
    allb = sorted(set(old) | set(made))
    # a bone another mesh still skins to (costume hair etc.) stays; the hair mesh's own Skin is replaced on the next apply
    r = mb.send('(local keep = ""; local d = #(); for n in #(%s) do (local o = getNodeByName n exact:true; if o != undefined do ('
                'local used = false; for r in refs.dependents o where classOf r == Skin do (for nd in refs.dependentNodes r where nd.name != "%s" do used = true); '
                'if used and findItem #(%s) n == 0 then keep += n + "|" + (if o.parent == undefined then "" else o.parent.name) + "|" + ((if classOf o == BoneGeometry then o.length else 0) as string) + ";" else append d o)); delete d; keep)'
                % (",".join('"%s"' % n for n in allb), hair.name, ",".join('"%s"' % n for n in made)), timeout=60).strip().strip('"')
    kept = [it.split("|") for it in r.split(";") if "|" in it]
    k = f.push_bones_to_max(arm, made, mb, recreate=True)
    _relink(mb, kept)      # 2.2: 남긴 본의 부모가 새로 만들어졌으면 다시 링크 (고아 본 방지)
    mb.send('(local o = getNodeByName "%s" exact:true; if o != undefined do deleteUserProp o "rt_batch"; "OK")' % hair.name, timeout=30)
    return k, len(kept)


def rebuild_weights(context, arm, hair):
    """10/30: 헤어 웨이트가 Blender 에 없을 때 (다른 파일 작업으로 정리됨 / Blender 새로 켬) Max 에 있는 헤어 본 이름으로 다시 계산.
    본을 만들 때와 같은 분석을 다시 돌려 정점 → 체인·마디를 정하고, Max 에 없는 마디는 Head 로. returns 정점 수 (0 = 못 함)"""
    hb = [b.name for b in arm.data.bones if re.match(r"bone_hair_[A-Za-z]+\d+_\d\d$", b.name, re.I) and not b.name.endswith("_00")]
    if not hb:
        return 0
    f = _flow()
    mb = f._max_bridge()
    pre = f.bip_prefix(arm) or "Bip01"
    hn = pre + " Head"
    if hn not in arm.data.bones:
        return 0
    unit, off = f._max_xform(arm, mb)
    mw = hair.matrix_world
    co = np.array([tuple((mw @ v.co) * unit + off) for v in hair.data.vertices])
    polys = [list(p.vertices) for p in hair.data.polygons]
    head = np.array(tuple((arm.matrix_world @ arm.data.bones[hn].head_local) * unit + off))
    kw = {}
    try:
        import object_bones as _ob
        R = _ob.load_ref().get("hair", {})
        kw = dict(blend=min(max(R.get("along_blend", 0.3), 0.1), 0.9), head_frac=R.get("bip_mixed_top", 0.54) * 0.25)
    except Exception:
        pass
    res = analyze(co, polys, head, **kw)
    have = {n.lower(): n for n in hb}
    W = {}
    hit = 0
    for vi, row in enumerate(res["weights"]):
        for i, w in row:
            n = hn
            if i != 0:
                ch, _, k = res["bones"][i].rpartition("_")
                n = have.get(("bone_hair_%s_%s" % (ch.upper(), k)).lower(), hn)
                hit += n != hn
            W.setdefault(n, []).append([vi, float(w)])
    if not hit:
        return 0
    context.scene[HW_KEY] = json.dumps({"obj": hair.name, "w": W})
    arm[HAIR_KEY] = sorted({b.name for b in arm.data.bones if b.name.lower().startswith("bone_hair_")})
    return len(res["weights"])


def batch_send(context, arm, mb, limit=4):
    """'3. 스킨 적용 (일괄)': hair weights made here -> Max hair Skin (once; after that the Max values stay). returns status text"""
    hair = hair_obj(context)
    if hair is None:
        return ""
    if get_state(arm).get("pending"):
        # 2.2: 미리보기(갈래·마디·코스튬)를 Max 에 아직 안 보냄 -> 블렌더 본과 Max 본이 달라 헤어는 건너뜀
        return " | 헤어: 미리보기를 아직 [반영] 안 해서 건너뜀 (헤어 패널에서 [반영] 또는 [되돌리기] 뒤 다시 스킨 적용)"
    try:
        d = json.loads(context.scene.get(HW_KEY, "{}") or "{}")
    except Exception:
        d = {}
    f = _flow()
    marked = mb.send('(local o = getNodeByName "%s" exact:true; (o != undefined and getUserProp o "rt_batch" != undefined) as string)'
                     % hair.name, timeout=30).strip().strip('"').lower() == "true"
    if marked:
        # 10/30: 표시는 있는데 Max 헤어 스킨에 헤어 본이 하나도 없으면 (웨이트가 안 들어간 채 표시만 됨) 다시 보냄
        nh = mb.send('(local o = getNodeByName "%s" exact:true; local n = 0; if o != undefined do (for m in o.modifiers where classOf m == Skin do '
                     '(for r in (refs.dependsOn m) where isValidNode r and matchPattern r.name pattern:"bone_hair_*" do n += 1)); n as string)'
                     % hair.name, timeout=30).strip().strip('"')
        if not (nh.isdigit() and int(nh) == 0):
            return " | 헤어: Max 값 그대로"
    rebuilt = 0
    if not arm.get(HAIR_KEY) or d.get("obj") != hair.name or not d.get("w"):
        try:
            rebuilt = rebuild_weights(context, arm, hair)
        except Exception as e:
            print("[hair_bones] 웨이트 다시 계산 실패:", e)
        if not rebuilt:
            return "" if not arm.get(HAIR_KEY) else " | 헤어: 웨이트 기록이 없어 못 보냄 (헤어 본 다시 만들기)"
    if not apply_weights(context, arm, hair):
        return " | 헤어: 정점 수가 달라 못 보냄 (헤어 본 다시 만들기)"
    f.limit_normalize(hair, limit)
    k = f.push_bones_to_max(arm, list(arm[HAIR_KEY]), mb)
    f.send_weights_to_max(hair, hair.name, mb, limit)
    mb.send('(local o = getNodeByName "%s" exact:true; if o != undefined do setUserProp o "rt_batch" "1"; "OK")' % hair.name, timeout=30)
    return " | 헤어 %s OK (본 %d%s%s)" % (hair.name, len(arm[HAIR_KEY]), ", Max에 없던 본 %d" % k if k else "",
                                       ", Max 헤어 본으로 웨이트 다시 계산" if rebuilt else "")


# ---------------------------------------------------------------- 2.2: 미리보기 상태 · 본 모양 · 되돌리기 기록
STATE_KEY = "msr_ob_hair_state"   # armature: json {mode "gen"|"ext", branch, density, pending, made, moved, mesh, undo}
UNDO_AD = 30593                   # Max appData 번호: 되돌리기 기록 때 있던 헤어 본 표시 (기록 뒤 새로 만든 본과 구별)
BOX_PREFIX = "MSR_hairbox_"       # 블렌더 본 모양 (Max 박스 본처럼): 테이퍼 5% 단위 상자 메시
HAIR_COL = "Hair (bone_hair)"     # 블렌더 본 컬렉션: 헤어 본 전부 보이게


def get_state(arm):
    try:
        return json.loads(arm.get(STATE_KEY, "{}") or "{}") if arm is not None else {}
    except Exception:
        return {}


def set_state(arm, **kw):
    st = get_state(arm)
    st.update(kw)
    arm[STATE_KEY] = json.dumps(st)
    return st


def _enter_edit(context, arm):
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    hs = arm.hide_select
    arm.hide_select = False
    for ob in list(context.view_layer.objects.selected):
        ob.select_set(False)
    arm.hide_set(False)
    arm.select_set(True)
    context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    return hs


def _leave_edit(arm, hs):
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.hide_select = hs


def _align_rolls(arm, eb, ups):
    """블렌더 본 Z 축 = Max 본 Z 축 (ups = Max world 방향) -> 상자 모양의 가로·세로가 Max 와 같은 방향"""
    m = arm.matrix_world.inverted().to_3x3()
    for n, z in ups.items():
        b = eb.get(n)
        if b is None or b.length < 1e-9:
            continue
        v = m @ Vector(tuple(float(x) for x in z))
        if v.length > 1e-9:
            b.align_roll(v)


def _box_obj(taper):
    """Max 박스 본 모양 (길이 1, 굵기 1, 끝 = 1 - taper%) - 본 custom shape 용, 장면에는 안 넣음"""
    t = int(round(min(max(float(taper), 0.0), 95.0) / 5.0) * 5)
    name = "%s%02d" % (BOX_PREFIX, t)
    o = bpy.data.objects.get(name)
    if o is not None and o.type == "MESH":
        return o
    s = 1.0 - t / 100.0
    v = [(-.5, 0, -.5), (.5, 0, -.5), (.5, 0, .5), (-.5, 0, .5),
         (-.5 * s, 1, -.5 * s), (.5 * s, 1, -.5 * s), (.5 * s, 1, .5 * s), (-.5 * s, 1, .5 * s)]
    fc = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(v, [], fc)
    me.update()
    o = bpy.data.objects.new(name, me)
    o.use_fake_user = True
    return o


def show_boxes(arm, names=None, unit=None):
    """헤어 본을 Max 박스 본 굵기·테이퍼로 표시 (SHAPE_KEY: Max 단위 w·h·taper)"""
    try:
        shape = json.loads(arm.get(SHAPE_KEY, "{}") or "{}")
    except Exception:
        shape = {}
    if unit is None:
        unit = float(list(arm["msr_mx"])[0]) if arm.get("msr_mx") else 1.0
    mw = arm.matrix_world
    n_ok = 0
    for n in (shape if names is None else names):
        pb = arm.pose.bones.get(n)
        sh = shape.get(n)
        if pb is None or not sh:
            continue
        b = arm.data.bones[n]
        L = (mw @ b.tail_local - mw @ b.head_local).length
        if L < 1e-9:
            continue
        pb.custom_shape = _box_obj(sh.get("taper", 0.0))
        pb.use_custom_shape_bone_size = True
        pb.custom_shape_scale_xyz = (sh["w"] / unit / L, 1.0, sh["h"] / unit / L)
        pb.custom_shape_rotation_euler = (0.0, 0.0, 0.0)      # Clean bone view(max_bridge.cv_apply)가 돌려 놓은 것 되돌림
        pb.custom_shape_translation = (0.0, 0.0, 0.0)
        # Clean bone view 는 웨이트 없는 본(root·_00·_end)을 숨은 Helpers 에 넣음 -> 헤어 본은 Max 처럼 전부 보이게
        if hasattr(arm.data, "collections"):
            col = arm.data.collections.get(HAIR_COL) or arm.data.collections.new(HAIR_COL)
            col.is_visible = True
            for c in list(b.collections):
                if c is not col:
                    c.unassign(b)
            col.assign(b)
        n_ok += 1
    return n_ok


def import_boxes(arm, mb):
    """① 가져오기 뒤: 모양 기록이 없는 헤어 본(파일에 있던 본)은 Max 굵기·테이퍼를 읽어 기록하고 상자로 표시"""
    try:
        shape = json.loads(arm.get(SHAPE_KEY, "{}") or "{}")
    except Exception:
        shape = {}
    hb = [b.name for b in arm.data.bones if b.name.lower().startswith("bone_hair_")]
    need = [n for n in hb if n not in shape]
    if need:
        for n, (sh, z) in _max_bone_info(mb, need).items():
            shape[n] = sh
        arm[SHAPE_KEY] = json.dumps(shape)
    return show_boxes(arm, hb)


def hair_view(context, arm):
    """Clean bone view 다시 (다른 본과 같은 모양) + 헤어 본은 Max 박스 모양"""
    try:
        import object_bones as _ob
        _ob._clean_view(context, arm)
    except Exception as e:
        print("hair clean view:", e)
    show_boxes(arm, [b.name for b in arm.data.bones if b.name.lower().startswith("bone_hair_")])


def _undo_paths(mb):
    """되돌리기 기록 파일 (Max 파일 이름 + 포트 기준): %LOCALAPPDATA%\\GE_RigJobs\\hair_undo\\"""
    base = os.path.splitext(mb.send("maxFileName", timeout=30).strip().strip('"'))[0] or "untitled"
    base = re.sub(r'[\\/:*?"<>|]', "_", base)
    d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "GE_RigJobs", "hair_undo")
    os.makedirs(d, exist_ok=True)
    k = os.path.join(d, "%s__p%s" % (base, getattr(mb, "PORT", "") or ""))
    return dict(bl=k + "_bl_undo.json", ap=k + "_bl_applied.json", mx=k + "_max.max", mt=k + "_max.txt", mw=k + "_max_w.txt")


def _mesh_vg(o):
    names = {g.index: g.name for g in o.vertex_groups}
    vg = {g.name: [] for g in o.vertex_groups}
    for v in o.data.vertices:
        for g in v.groups:
            if g.group in names:
                vg[names[g.group]].append([v.index, g.weight])
    return dict(order=[g.name for g in o.vertex_groups], w=vg)


def _bl_capture(context, arm, meshes):
    """블렌더 헤어 본(머리·위치·roll·부모) + 기록 값 + 메시 웨이트 -> dict"""
    hs = _enter_edit(context, arm)
    bones = [dict(n=b.name, h=list(b.head), t=list(b.tail), r=b.roll, p=b.parent.name if b.parent else "", d=b.use_deform, c=b.use_connect)
             for b in arm.data.edit_bones if b.name.lower().startswith("bone_hair_")]
    _leave_edit(arm, hs)
    props = {}
    for k in (HAIR_KEY, UP_KEY, SHAPE_KEY, STATE_KEY):
        v = arm.get(k)
        props[k] = None if v is None else (v if isinstance(v, str) else list(v))
    vgs = {o.name: _mesh_vg(o) for o in meshes if o is not None}
    return dict(bones=bones, props=props, hw=context.scene.get(HW_KEY, ""), vgs=vgs)


def _bl_restore(context, arm, rec):
    hs = _enter_edit(context, arm)
    eb = arm.data.edit_bones
    for b in [b for b in eb if b.name.lower().startswith("bone_hair_")]:
        eb.remove(b)
    names = {d["n"] for d in rec["bones"]}
    todo, order, done = list(rec["bones"]), [], set()
    while todo:
        nxt = [d for d in todo if d["p"] not in names or d["p"] in done]
        if not nxt:
            nxt = todo[:1]
        for d in nxt:
            order.append(d)
            done.add(d["n"])
            todo.remove(d)
    for d in order:
        b = eb.new(d["n"])
        b.head, b.tail, b.roll = Vector(d["h"]), Vector(d["t"]), d["r"]
        b.use_deform = d["d"]
    for d in order:
        b = eb.get(d["n"])
        b.parent = eb.get(d["p"]) if d["p"] else None
        b.use_connect = d["c"]
    _leave_edit(arm, hs)
    for k, v in rec["props"].items():
        if v is None:
            if k in arm:
                del arm[k]
        else:
            arm[k] = v
    context.scene[HW_KEY] = rec.get("hw", "")
    for mn, vg in rec.get("vgs", {}).items():
        o = bpy.data.objects.get(mn)
        if o is None or o.type != "MESH":
            continue
        for g in list(o.vertex_groups):
            o.vertex_groups.remove(g)
        for gn in vg["order"]:
            g = o.vertex_groups.new(name=gn)
            for vi, w in vg["w"].get(gn, []):
                g.add([vi], w, "REPLACE")
    hb = set(arm.get(HAIR_KEY, []))
    for pb in arm.pose.bones:
        if pb.name.lower().startswith("bone_hair_") and pb.name not in hb:
            pb.custom_shape = None
    show_boxes(arm, list(hb))


def _max_snapshot(mb, P, mesh_name):
    """Max 헤어 본 전부 (saveNodes .max + 이름·부모·변환 목록) + 헤어 메시 스킨 웨이트 (applyWeights 형식)"""
    for p in (P["mx"], P["mt"], P["mw"]):
        if os.path.exists(p):
            os.remove(p)
    sid = "%d" % int(time.time() * 1000)
    code = '''(
 local hs = for o in objects where matchPattern o.name pattern:"bone_hair_*" collect o
 for o in hs do setAppData o @AD@ "@ID@"
 local h = getNodeByName "@H@" exact:true
 local sk = undefined
 if h != undefined do (for m in h.modifiers where classOf m == Skin and sk == undefined do sk = m)
 local f = createFile @MT@
 format "ID|@ID@\\n" to:f
 format "MESH|@H@\\n" to:f
 format "SKIN|%\\n" (sk != undefined) to:f
 format "BATCH|%\\n" (if h == undefined then undefined else (getUserProp h "rt_batch")) to:f
 for o in hs do (local t = o.transform; format "N|%|%|%|%|%|%|%\\n" o.name (if o.parent == undefined then "" else o.parent.name) t.row1 t.row2 t.row3 t.row4 (if classOf o == BoneGeometry then o.length else 0) to:f)
 close f
 if hs.count > 0 do saveNodes hs @MX@ quiet:true
 if sk != undefined do (
  max modify mode
  select h
  modPanel.setCurrentObject sk
  local nb = skinOps.GetNumberBones sk
  local nv = skinOps.GetNumberVertices sk
  local g = createFile @MW@
  format "#BONES" to:g
  for b = 1 to nb do format "\\t%" (skinOps.GetBoneName sk b 1) to:g
  format "\\n" to:g
  for v = 1 to nv do (
   local s = ""
   for j = 1 to (skinOps.GetVertexWeightCount sk v) do (
    local w = skinOps.GetVertexWeight sk v j
    if w > 0.0 do s += (((skinOps.GetVertexWeightBoneID sk v j) - 1) as string) + ":" + (w as string) + " "
   )
   format "%\\n" (trimRight s) to:g
  )
  close g
  clearSelection()
  max create mode
 )
 "OK " + (hs.count as string)
)'''
    code = (code.replace("@AD@", str(UNDO_AD)).replace("@ID@", sid).replace("@H@", mesh_name.replace('"', ""))
            .replace("@MT@", mb.ms_path(P["mt"])).replace("@MX@", mb.ms_path(P["mx"])).replace("@MW@", mb.ms_path(P["mw"])))
    r = mb.send(code, timeout=300).strip().strip('"')
    if not r.startswith("OK"):
        raise RuntimeError("Max 되돌리기 기록 실패: " + r[:200])
    return int(r.split()[1])


def _max_restore(mb, P):
    """_max_snapshot 기록대로: 기록 뒤 생긴 헤어 본 지우기 -> 없어진 본은 .max 에서 병합 -> 부모·변환 -> 헤어 스킨"""
    rec = dict(N=[])
    with open(P["mt"], encoding="utf-8-sig") as fh:
        for line in fh:
            p = line.rstrip("\r\n").split("|")
            if p[0] == "N":
                rec["N"].append(p[1:])
            elif len(p) > 1:
                rec[p[0]] = p[1]
    names = [n[0] for n in rec["N"]]
    L = ["(", ' local id = "%s"' % rec["ID"],
         ' local del = for o in objects where matchPattern o.name pattern:"bone_hair_*" and (getAppData o %d) != id collect o' % UNDO_AD,
         ' for o in del where isValidNode o do try (delete o) catch ()',
         ' local want = #(%s)' % ",".join('"%s"' % n for n in names),
         ' local miss = for n in want where (getNodeByName n exact:true) == undefined collect n']
    if names and os.path.exists(P["mx"]):
        L.append(' if miss.count > 0 do mergeMaxFile %s miss #noRedraw #skipDups #neverReparent #useSceneMtlDups quiet:true' % mb.ms_path(P["mx"]))
    for n, par, r1, r2, r3, r4, ln in rec["N"]:
        L.append(' (local o = getNodeByName "%s" exact:true; if o != undefined do (local p = %s; if o.parent != p do o.parent = p; '
                 'local tm = matrix3 %s %s %s %s; if (distance o.transform.row4 tm.row4) > 0.001 or (distance o.transform.row1 tm.row1) > 0.0001 '
                 'or (distance o.transform.row3 tm.row3) > 0.0001 do o.transform = tm; '
                 'if classOf o == BoneGeometry and (abs (o.length - %s)) > 0.001 do o.length = %s))'
                 % (n, ('getNodeByName "%s" exact:true' % par) if par else "undefined", r1, r2, r3, r4, ln, ln))
    L += [' for o in objects where matchPattern o.name pattern:"bone_hair_*" do deleteAppData o %d' % UNDO_AD,
          ' local back = for n in want where (getNodeByName n exact:true) == undefined collect n',
          ' "OK " + (back.count as string)', ")"]
    r = mb.send("\n".join(L), timeout=300).strip().strip('"')
    if not r.startswith("OK"):
        raise RuntimeError("Max 헤어 본 되돌리기 실패: " + r[:200])
    lost = int(r.split()[1])
    mesh = rec.get("MESH", "")
    if rec.get("SKIN", "false").lower() == "true" and os.path.exists(P["mw"]):
        r2 = mb.send('MaxBridge.applyWeights "%s" %s limit:4' % (mesh, mb.ms_path(P["mw"])), timeout=600)
        if not r2.startswith("OK"):
            raise RuntimeError("Max 헤어 스킨 되돌리기 실패: " + r2[:200])
    else:
        mb.send('(local o = getNodeByName "%s" exact:true; if o != undefined do (for i = o.modifiers.count to 1 by -1 where classOf o.modifiers[i] == Skin do deleteModifier o i); "OK")' % mesh, timeout=60)
    b = rec.get("BATCH", "undefined")
    # Max 2014 에는 deleteUserProp 가 없음 -> 사용자 속성 글에서 rt_batch 줄만 뺌
    unmark = ('local s = ""; for l in (filterString (getUserPropBuffer o) "\\r\\n") where not (matchPattern l pattern:"rt_batch*") do s += l + "\\r\\n"; '
              'setUserPropBuffer o s')
    mb.send('(local o = getNodeByName "%s" exact:true; if o != undefined do (%s); "OK")'
            % (mesh, unmark if b == "undefined" else 'setUserProp o "rt_batch" "%s"' % b), timeout=30)
    return len(names), lost


def _save_applied(context, arm, meshes, mb, P=None):
    P = P or _undo_paths(mb)
    with open(P["ap"], "w", encoding="utf-8") as fh:
        json.dump(_bl_capture(context, arm, meshes), fh)


def _before_preview(context, arm, hair, mb):
    """미리보기 첫 변경 전: 지금 블렌더 상태(= Max 에 반영된 상태)를 기록. 이미 미리보기 중이면 처음 보는 메시 웨이트만 더함"""
    P = _undo_paths(mb)
    st = get_state(arm)
    if not st.get("pending") or not os.path.exists(P["ap"]):
        _save_applied(context, arm, [hair], mb, P)
        return
    with open(P["ap"], encoding="utf-8") as fh:
        rec = json.load(fh)
    if hair.name not in rec.get("vgs", {}):
        rec.setdefault("vgs", {})[hair.name] = _mesh_vg(hair)
        with open(P["ap"], "w", encoding="utf-8") as fh:
            json.dump(rec, fh)


def _undo_owner(mesh):
    return [mesh.name, len(mesh.data.vertices)] if mesh is not None and mesh.type == "MESH" else []


def _take_undo(context, arm, mesh, mb):
    """[만들기]·[반영] 직전: 블렌더 = 마지막 반영 상태 (미리보기 중이면 그 기록), Max = 지금 헤어 본·헤어 스킨"""
    P = _undo_paths(mb)
    if get_state(arm).get("pending") and os.path.exists(P["ap"]):
        with open(P["ap"], encoding="utf-8") as fh:
            rec = json.load(fh)
        if mesh is not None and mesh.name not in rec.get("vgs", {}):
            rec.setdefault("vgs", {})[mesh.name] = _mesh_vg(mesh)
    else:
        rec = _bl_capture(context, arm, [mesh])
    # 2.5: 이 기록의 주인(헤어 메시 이름·정점 수). 기록 파일은 Max 파일 이름으로만 나뉘어 다른 캐릭터에서 쓰이지 않게
    rec["owner"] = _undo_owner(mesh)
    set_state(arm, undo_owner=rec["owner"])
    with open(P["bl"], "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    _max_snapshot(mb, P, mesh.name if mesh is not None else "")
    return P


def push_bones_all(context, arm, made, hair):
    """[반영] (갈래·마디): Max 의 헤어 본(bone_hair_*) 전부 지우고 새 본 생성. 다른 메시가 스킨에 쓰는 본은 남김 (새 본과 같은 이름이면 새 본으로)"""
    f = _flow()
    mb = f._max_bridge()
    r = mb.send('(local keep = ""; local d = #(); for o in objects where matchPattern o.name pattern:"bone_hair_*" do ('
                'local used = false; for r in refs.dependents o where classOf r == Skin do (for nd in refs.dependentNodes r where nd.name != "%s" do used = true); '
                'if used and findItem #(%s) o.name == 0 then keep += o.name + "|" + (if o.parent == undefined then "" else o.parent.name) + "|" + ((if classOf o == BoneGeometry then o.length else 0) as string) + ";" else append d o); '
                'for o in d where isValidNode o do try (delete o) catch (); keep)'
                % (hair.name, ",".join('"%s"' % n for n in made)), timeout=60).strip().strip('"')
    kept = [it.split("|") for it in r.split(";") if "|" in it]
    k = f.push_bones_to_max(arm, made, mb, recreate=True)
    # 남긴 본(코스튬 메시가 쓰는 붙인 마디 등)의 부모가 지워졌다 새로 만들어졌으면 같은 이름 새 본에 다시 링크 (고아 본 방지)
    _relink(mb, kept)
    return k, len(kept)


def _relink(mb, kept):
    """kept = [[이름, 부모, 길이]]: 부모가 지워져 world 에 걸린 본을 같은 이름 새 부모에 다시 링크, 자식(_end)이 지워져 바뀐 길이도 되돌림"""
    if not kept:
        return
    mb.send('(for it in #(%s) do (local o = getNodeByName it[1] exact:true; local p = getNodeByName it[2] exact:true; '
            'if o != undefined and p != undefined and o.parent == undefined do o.parent = p; '
            'if o != undefined and classOf o == BoneGeometry and it[3] > 0 and abs (o.length - it[3]) > 0.001 do o.length = it[3]); "OK")'
            % ",".join('#("%s","%s",%s)' % (n, p, ln) for n, p, ln in kept), timeout=60)


def _max_bone_info(mb, names):
    """Max 본 굵기·테이퍼·박스·Z 축 -> {이름: (shape dict, z)}"""
    out = {}
    for i in range(0, len(names), 60):
        part = names[i:i + 60]
        r = mb.send('(local r = ""; for n in #(%s) do (local o = getNodeByName n exact:true; if o != undefined and classOf o == BoneGeometry do '
                    '(local z = o.transform.row3; r += n + "|" + (o.width as string) + "|" + (o.height as string) + "|" + (o.taper as string) + "|" + '
                    '(o.boxMode as string) + "|" + (z.x as string) + "," + (z.y as string) + "," + (z.z as string) + ";")); r)'
                    % ",".join('"%s"' % n for n in part), timeout=60).strip().strip('"')
        for it in r.split(";"):
            p = it.split("|")
            if len(p) == 6:
                out[p[0]] = (dict(w=float(p[1]), h=float(p[2]), taper=float(p[3]), box=p[4].lower() == "true"),
                             [float(x) for x in p[5].split(",")])
    return out


def existing_chains(arm, xf):
    """지금 리그의 헤어 체인: 끝 본에서 위로, 헤어 본이 한 줄인 동안.
    returns [dict(segs=[웨이트 본 이름], link, end, joints (Max), prefix, next, width, root)]"""
    bones = arm.data.bones
    hs = {b.name for b in bones if b.name.lower().startswith("bone_hair_")}

    def kids(b):
        return [c for c in b.children if c.name in hs]
    out = []
    for b in bones:
        if b.name not in hs or kids(b):
            continue
        path = [b]
        p = b.parent
        while p is not None and p.name in hs and len(kids(p)) == 1 and not p.name.lower().endswith("_root"):
            path.append(p)
            p = p.parent
        path.reverse()
        link = path[0] if re.search(r"_00$", path[0].name) else None
        end = path[-1] if path[-1].name.lower().endswith("end") and len(path) > 1 else None
        segs = [x for x in path if x is not link and x is not end]
        if not segs:
            continue
        J = [xf(x.head_local) for x in segs] + [xf(end.head_local) if end else xf(segs[-1].tail_local)]
        m = re.match(r"^(.*?)(\d+)$", segs[-1].name)
        prefix, nxt, width = (m.group(1), int(m.group(2)) + 1, len(m.group(2))) if m else (segs[-1].name + "_", 1, 2)
        out.append(dict(segs=[x.name for x in segs], link=link.name if link else None, end=end.name if end else None,
                        joints=np.array(J), prefix=prefix, next=nxt, width=width, root=p.name if p is not None else None))
    return out


def extend(context, arm, hair, seg_len=8.0, start_up=4.0):
    """코스튬 머리 -> 지금 헤어 체인 끝에 마디를 붙여 (블렌더 미리보기). 기존 본은 이름·위치·축 그대로 (_end 만 새 끝으로).
    returns (붙인 본, 옮긴 _end, log lines)"""
    f = _flow()
    mb = f._max_bridge()
    res, co, head, hn, lines = _analysis(context, arm, hair, seg_len, start_up)
    unit, off = f._max_xform(arm, mb)
    amw = arm.matrix_world

    def xf(v):
        return np.array(tuple((amw @ v) * unit + off))
    old = existing_chains(arm, xf)
    if not old:
        raise RuntimeError("지금 헤어 본이 없어요 (먼저 '헤어 본 만들기', 또는 헤어 본 있는 셋을 ① 가져오기)")
    use = plan_extend(res, co, head, old, log=lambda s: lines.append(s))
    ups = json.loads(arm.get(UP_KEY, "{}") or "{}")
    shape = json.loads(arm.get(SHAPE_KEY, "{}") or "{}")
    known = [n for ch in old for n in [ch["link"]] + ch["segs"] + [ch["end"]] if n]
    known += sorted({ch["root"] for ch in old if ch["root"] and ch["root"].lower().startswith("bone_hair_")})
    info = _max_bone_info(mb, [n for n in known if n not in shape or n not in ups])
    for n, (sh, z) in info.items():
        shape.setdefault(n, sh)
        ups.setdefault(n, z)
    hs = _enter_edit(context, arm)
    eb = arm.data.edit_bones
    inv = amw.inverted()
    made, moved = [], []

    def bl(p):
        return inv @ ((Vector(tuple(p)) - off) / unit)
    segname = {}
    for j, u in sorted(use.items()):
        ch = old[j]
        for k, n in enumerate(ch["segs"]):
            segname[(j, k)] = n
        if not u["add"]:
            continue
        last = ch["segs"][-1]
        prev = eb.get(last)
        J = [ch["joints"][-1]] + list(u["add"])
        d = _nrm(J[1] - J[0])
        z = _carry(ups[last], d) if last in ups else _level(d)
        for i in range(len(J) - 1):
            n = "%s%0*d" % (ch["prefix"], ch["width"], ch["next"] + i)
            if eb.get(n):
                _leave_edit(arm, hs)
                raise RuntimeError("이름이 겹쳐요: %s" % n)
            b = eb.new(n)
            b.head, b.tail = bl(J[i]), bl(J[i + 1])
            b.parent, b.use_connect, b.use_deform = prev, False, True
            prev = b
            made.append(n)
            segname[(j, len(ch["segs"]) + i)] = n
            d = _nrm(J[i + 1] - J[i])
            z = _carry(z, d)
            ups[n] = [float(x) for x in z]
            if last in shape:
                shape[n] = dict(shape[last])
        if ch["end"]:
            e = eb.get(ch["end"])
            ln = max((amw @ e.tail - amw @ e.head).length * unit, 0.5)
            e.parent, e.use_connect = prev, False
            e.head, e.tail = bl(J[-1]), bl(J[-1] + d * ln)
            ups[ch["end"]] = [float(x) for x in _carry(z, d)]
            moved.append(ch["end"])
    _align_rolls(arm, eb, {n: ups[n] for n in known + made if n in ups})
    _leave_edit(arm, hs)
    arm[HAIR_KEY] = list(dict.fromkeys(list(arm.get(HAIR_KEY, [])) + known + made))
    arm[UP_KEY] = json.dumps(ups)
    arm[SHAPE_KEY] = json.dumps(shape)
    show_boxes(arm, known + made, unit)
    # 웨이트: 코스튬 정점은 Head, 따라가는 체인이 있으면 그 체인 (기존 마디 + 붙인 마디) 따라
    names, idx = [hn], {}

    def bi(n):
        if n not in idx:
            idx[n] = len(names)
            names.append(n)
        return idx[n]
    wt = [[(0, 1.0)] for _ in range(len(co))]
    for j, u in sorted(use.items()):
        J = np.vstack([old[j]["joints"]] + ([np.array(u["add"])] if u["add"] else []))
        segb = [bi(segname[(j, k)]) for k in range(len(J) - 1)]
        _line_weights(co, J, u["members"], segb, wt, own=u["own"])
    _twin_copy(co, wt, res["twins"])
    W = {}
    for vi, row in enumerate(wt):
        for i, w in row:
            W.setdefault(names[i], []).append([vi, float(w)])
    context.scene[HW_KEY] = json.dumps({"obj": hair.name, "w": W})
    apply_weights(context, arm, hair)
    return made, moved, lines


def push_extend(context, arm, made, moved, hair):
    """[반영] (코스튬): 붙인 본 생성 + 옮긴 _end 다시 걸기 (같은 노드)"""
    f = _flow()
    mb = f._max_bridge()
    k = f.push_bones_to_max(arm, made, mb, recreate=True) if made else 0
    if moved:
        unit, off = f._max_xform(arm, mb)
        mw = arm.matrix_world
        ups = json.loads(arm.get(UP_KEY, "{}") or "{}")
        cmd = ["("]
        for n in moved:
            b = arm.data.bones[n]
            h = np.array(tuple((mw @ b.head_local) * unit + off))
            t = np.array(tuple((mw @ b.tail_local) * unit + off))
            x = _nrm(t - h)
            z = _carry(ups.get(n, _level(x)), x)
            y = np.cross(z, x)
            cmd.append(' (local o = getNodeByName "%s" exact:true; local p = getNodeByName "%s" exact:true; if o != undefined and p != undefined do ('
                       'o.parent = p; o.transform = matrix3 [%f,%f,%f] [%f,%f,%f] [%f,%f,%f] [%f,%f,%f]; try (o.length = %f) catch ()))'
                       % ((n, b.parent.name) + tuple(x) + tuple(y) + tuple(z) + tuple(h) + (float(np.linalg.norm(t - h)),)))
        cmd += [' redrawViews()', ' "OK")']
        r = mb.send("\n".join(cmd), timeout=60)
        if not r.strip().strip('"').startswith("OK"):
            raise RuntimeError("Max _end 옮기기 실패: " + r)
    return k


def preview(context, arm, hair, mode, branch="BASIC", density="NORMAL"):
    """선택 -> 블렌더 본·웨이트만 바꿈 (Max 는 [반영] 때). returns 상태 글"""
    f = _flow()
    mb = f._max_bridge()
    if mb is None:
        raise RuntimeError("Max 연결이 필요해요 (Max 좌표로 계산)")
    wm = context.window_manager
    st = get_state(arm)
    if mode == "ext" and st.get("pending") and st.get("mode") != "ext":
        raise RuntimeError("갈래·마디 미리보기를 먼저 [반영]하거나 [되돌리기] 한 뒤 코스튬 맞추기")
    _before_preview(context, arm, hair, mb)
    if mode == "ext":
        made, moved, lines = extend(context, arm, hair, wm.msr_hair_seg, wm.msr_hair_up)
        if st.get("pending") and st.get("mode") == "ext":
            made = list(dict.fromkeys(st.get("made", []) + made))
            moved = list(dict.fromkeys(st.get("moved", []) + moved))
        set_state(arm, mode="ext", pending=True, made=made, moved=moved, mesh=hair.name)
        msg = "코스튬 미리보기: 붙인 본 %d개 · 끝 본 %d개 옮김" % (len(made), len(moved))
    else:
        made, old, lines = generate(context, arm, hair, wm.msr_hair_seg, wm.msr_hair_up, branch, density, fresh=False)
        set_state(arm, mode="gen", branch=branch, density=density, pending=True, made=made, moved=[], mesh=hair.name)
        chains = sorted({n.rsplit("_", 1)[0] for n in made if n.endswith("_00")})
        msg = "미리보기: 헤어 본 %d개 · 체인 %d개 (%s)" % (len(made), len(chains), ", ".join(c.replace("bone_hair_", "") for c in chains))
    hair_view(context, arm)
    wm.msr_hair_last = " / ".join(lines[-4:])
    return msg + " | Max는 아직 그대로 ([반영]을 누르면 Max에)"


def apply_preview(context, arm, limit=4):
    """[반영]: 미리보기 본 -> Max (옛 헤어 본 지우고 새 본 / 코스튬은 붙인 본) + 헤어 웨이트 바로 Max 스킨에"""
    f = _flow()
    mb = f._max_bridge()
    st = get_state(arm)
    if not st.get("pending"):
        return "이미 반영됨 (바뀐 것 없음)"
    mesh = bpy.data.objects.get(st.get("mesh") or "") or hair_obj(context)
    P = _take_undo(context, arm, mesh, mb)
    if st.get("mode") == "ext":
        k = push_extend(context, arm, st.get("made", []), st.get("moved", []), mesh)
        msg = "반영: Max에 붙인 본 %d개 · 끝 본 %d개 옮김" % (k, len(st.get("moved", [])))
    else:
        k, kept = push_bones_all(context, arm, list(arm.get(HAIR_KEY, [])), mesh)
        msg = "반영: Max 헤어 본 %d개" % k + (" · 다른 메시가 쓰는 옛 헤어 본 %d개는 남김" % kept if kept else "")
    if apply_weights(context, arm, mesh):
        f.limit_normalize(mesh, limit)
        f.send_weights_to_max(mesh, mesh.name, mb, limit)
        mb.send('(local o = getNodeByName "%s" exact:true; if o != undefined do setUserProp o "rt_batch" "1"; "OK")' % mesh.name, timeout=30)
        msg += " | 헤어 웨이트도 Max 스킨에 넣음 (다음 스킨 적용 때는 Max 값 그대로)"
    else:
        msg += " | 헤어 웨이트는 다음 '스킨 적용' 때"
    set_state(arm, pending=False, undo=True)
    _save_applied(context, arm, [mesh], mb, P)
    return msg


def undo_last(context, arm):
    """[되돌리기]: 직전 [만들기]·[반영] 전 헤어 본 상태로 Max·블렌더 모두"""
    f = _flow()
    mb = f._max_bridge()
    P = _undo_paths(mb)
    if not (os.path.exists(P["bl"]) and os.path.exists(P["mt"])):
        set_state(arm, undo=False)
        raise RuntimeError("되돌릴 기록이 없어요 (이 Max 파일에서 [만들기]·[반영] 한 뒤에만)")
    with open(P["bl"], encoding="utf-8") as fh:
        rec = json.load(fh)
    if rec.get("owner") != _undo_owner(hair_obj(context, store=False)):
        set_state(arm, undo=False)
        raise RuntimeError("이 되돌리기 기록은 다른 헤어 메시(%s) 것이라 되돌리지 않았어요" % ((rec.get("owner") or ["?"])[0]))
    n, lost = _max_restore(mb, P)
    _bl_restore(context, arm, rec)
    st = set_state(arm, pending=False, undo=False)
    wm = context.window_manager
    wm.msr_hair_branch, wm.msr_hair_density = st.get("branch", "BASIC"), st.get("density", "NORMAL")
    with open(P["ap"], "w", encoding="utf-8") as fh:
        json.dump(_bl_capture(context, arm, [bpy.data.objects.get(m) for m in rec.get("vgs", {})]), fh)
    for k in ("bl", "mx", "mt", "mw"):
        if os.path.exists(P[k]):
            os.remove(P[k])
    hair_view(context, arm)
    return "되돌림: Max 헤어 본 %d개 (반영 전 상태)%s · 블렌더 본·웨이트도" % (n, " · 못 찾은 본 %d개" % lost if lost else "")


class MSR_OT_hair_generate(bpy.types.Operator):
    """머리카락 메시에서 가닥을 찾아 체인 본을 만들고 Max에 보냄 (본만. 웨이트는 '3. 스킨 적용 (일괄)' 때)"""
    bl_idname = "msr.hair_generate"
    bl_label = "헤어 본 만들기"
    bl_options = {"REGISTER", "UNDO"}
    branch: bpy.props.StringProperty(default="BASIC")      # 1.62: Max 갈래 버튼 [기본]/[간단] -> "BASIC"/"SIMPLE"

    def execute(self, context):
        f = _flow()
        wm = context.window_manager
        arm = f.flow_objects(context)[0]
        hair = hair_obj(context)
        if arm is None or hair is None:
            wm.msr_status = "Bip·머리카락 메시가 없어요 (Max에서 머리카락도 선택하고 ① 가져오기)"
            self.report({"WARNING"}, wm.msr_status)
            return {"CANCELLED"}
        mb = f._max_bridge()
        P = None
        try:
            P = _take_undo(context, arm, hair, mb) if mb is not None else None     # 2.2: [되돌리기] 용
        except Exception as e:
            print("[hair_bones] 되돌리기 기록 실패:", e)
        try:
            br = self.branch if self.branch in ("BASIC", "SIMPLE") else "BASIC"
            made, old, lines = generate(context, arm, hair, wm.msr_hair_seg, wm.msr_hair_up, branch=br)
        except RuntimeError as e:
            if context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            wm.msr_status = "헤어 본 실패 | %s" % e
            self.report({"WARNING"}, wm.msr_status)
            return {"CANCELLED"}
        hair_view(context, arm)
        chains = sorted({n.rsplit("_", 1)[0] for n in made if n.endswith("_00")})
        msg = "헤어 본 %d개 · 체인 %d개 (%s)" % (len(made), len(chains), ", ".join(c.replace("bone_hair_", "") for c in chains))
        try:
            k, kept = push_bones(context, arm, made, old, hair)
            msg += " | Max에 본 %d개" % k + (" | 다른 메시가 쓰는 옛 헤어 본 %d개는 남김" % kept if kept else "")
        except Exception as e:
            msg += " | Max 실패: %s" % str(e)[:150]
        wm.msr_hair_branch, wm.msr_hair_density = br, "NORMAL"
        set_state(arm, mode="gen", branch=br, density="NORMAL", pending=False, made=made, moved=[], mesh=hair.name, undo=P is not None)
        if P is not None:
            try:
                _save_applied(context, arm, [hair], mb, P)
            except Exception as e:
                print("[hair_bones] 반영 기록 실패:", e)
        wm.msr_hair_last = " / ".join(lines[-4:])
        wm.msr_status = msg + " | 블렌더 헤어에 웨이트 넣음 · Max 웨이트는 '3. 스킨 적용' 때"
        self.report({"INFO"}, wm.msr_status)
        return {"FINISHED"}


def _run(self, context, fn):
    f = _flow()
    wm = context.window_manager
    arm = f.flow_objects(context)[0]
    if arm is None:
        wm.msr_status = "Bip이 없어요 (① 가져오기)"
        self.report({"WARNING"}, wm.msr_status)
        return {"CANCELLED"}
    try:
        wm.msr_status = fn(arm)
    except Exception as e:
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        wm.msr_status = "헤어 실패 | %s" % str(e)[:200]
        self.report({"WARNING"}, wm.msr_status)
        return {"CANCELLED"}
    self.report({"INFO"}, wm.msr_status)
    return {"FINISHED"}


class MSR_OT_hair_pick(bpy.types.Operator):
    """헤어 본 갈래·마디 고르기: 블렌더에서 바로 미리 보임 (Max는 [반영] 때)"""
    bl_idname = "msr.hair_pick"
    bl_label = "헤어 갈래·마디"
    bl_options = {"REGISTER"}
    kind: bpy.props.StringProperty(default="branch")
    value: bpy.props.StringProperty(default="BASIC")

    def execute(self, context):
        wm = context.window_manager
        hair = hair_obj(context)
        if hair is None:
            self.report({"WARNING"}, "머리카락 메시가 없어요")
            return {"CANCELLED"}
        if self.kind == "branch":
            wm.msr_hair_branch = self.value
        else:
            wm.msr_hair_density = self.value
        return _run(self, context, lambda arm: preview(context, arm, hair, "gen", wm.msr_hair_branch, wm.msr_hair_density))


class MSR_OT_hair_costume(bpy.types.Operator):
    """코스튬 머리: 새 본 없이 지금 헤어 체인 끝에 마디를 붙여 긴 머리 끝까지 (블렌더 미리보기, Max는 [반영] 때).
머리카락 칸에서 코스튬 머리 메시를 고른 뒤 눌러요"""
    bl_idname = "msr.hair_costume"
    bl_label = "기존 본 늘려 맞추기"
    bl_options = {"REGISTER"}

    def execute(self, context):
        hair = hair_obj(context)
        if hair is None:
            self.report({"WARNING"}, "머리카락 메시가 없어요")
            return {"CANCELLED"}
        return _run(self, context, lambda arm: preview(context, arm, hair, "ext"))


class MSR_OT_hair_apply(bpy.types.Operator):
    """미리보기를 Max에 반영: 옛 헤어 본을 지우고 새 본 생성 (다른 메시가 쓰는 헤어 본은 남김) + 헤어 웨이트도 Max 스킨에"""
    bl_idname = "msr.hair_apply"
    bl_label = "반영"
    bl_options = {"REGISTER"}

    def execute(self, context):
        return _run(self, context, lambda arm: apply_preview(context, arm, context.window_manager.msr_limit))


class MSR_OT_hair_undo(bpy.types.Operator):
    """직전 [반영](또는 [헤어 본 만들기]) 전 헤어 본 상태로 Max·블렌더 모두 되돌림"""
    bl_idname = "msr.hair_undo"
    bl_label = "되돌리기"
    bl_options = {"REGISTER"}

    def execute(self, context):
        return _run(self, context, lambda arm: undo_last(context, arm))


def draw(lay, context):
    wm = context.window_manager
    found = hair_obj(context, store=False)
    lay.prop_search(wm, "msr_hair", bpy.data, "objects", text="머리카락")
    if found is not None and not wm.msr_hair:
        lay.label(text="자동: %s" % found.name, icon="CHECKMARK")
    r = lay.row()
    r.scale_y = 1.3
    r.enabled = found is not None
    r.operator("msr.hair_generate", text="헤어 본 만들기 (블렌더 웨이트 + Max 본)", icon="BONE_DATA")
    f = _flow()
    arm = f.flow_objects(context)[0] if f else None
    st = get_state(arm)
    if arm is not None and arm.get(HAIR_KEY):
        box = lay.box()
        col = box.column(align=True)
        gen = st.get("mode", "gen") == "gen"
        col.label(text="갈래")
        row = col.row(align=True)
        for v, t in (("BASIC", "기본 (메시대로)"), ("SIMPLE", "간단 (뒤 3갈래)")):
            op = row.operator("msr.hair_pick", text=t, depress=gen and wm.msr_hair_branch == v)
            op.kind, op.value = "branch", v
        col.label(text="마디")
        row = col.row(align=True)
        for v, t in (("DENSE", "촘촘하게"), ("NORMAL", "기본"), ("SPARSE", "성기게")):
            op = row.operator("msr.hair_pick", text=t, depress=gen and wm.msr_hair_density == v)
            op.kind, op.value = "density", v
        col.label(text="코스튬 머리 (머리카락 칸에서 고르기)")
        col.operator("msr.hair_costume", text="기존 본 늘려 맞추기", icon="CON_SPLINEIK", depress=not gen and bool(st.get("pending")))
        if st.get("pending"):
            w = box.row()
            w.alert = True
            w.label(text="미리보기 중 · Max는 아직 그대로", icon="ERROR")
        row = box.row(align=True)
        row.scale_y = 1.3
        a = row.row(align=True)
        a.enabled = bool(st.get("pending"))
        a.operator("msr.hair_apply", text="반영 (Max에)", icon="EXPORT")
        u = row.row(align=True)
        u.enabled = bool(st.get("undo")) and st.get("undo_owner") == _undo_owner(found)
        u.operator("msr.hair_undo", text="되돌리기", icon="LOOP_BACK")
    # 2.2 (정현 11-01): '고급'(마디 길이·시작)·가닥 찾기 기록·안내 문구는 화면에서 뺌 (값·기록은 그대로 씀).
    #   설명은 1_project\작업자_안내_헤어패널.md


classes = (MSR_OT_hair_generate, MSR_OT_hair_pick, MSR_OT_hair_costume, MSR_OT_hair_apply, MSR_OT_hair_undo)
_WM_PROPS = ("msr_hair", "msr_hair_seg", "msr_hair_up", "msr_hair_last", "msr_hair_branch", "msr_hair_density", "msr_hair_adv")


def register():
    for c in classes:
        bpy.utils.register_class(c)
    WM = bpy.types.WindowManager
    WM.msr_hair = bpy.props.StringProperty(name="머리카락", default="")
    WM.msr_hair_seg = bpy.props.FloatProperty(default=8.0, min=1.0, max=50.0, description="본 한 마디 길이 (Max 단위, 멜리타 8)")
    WM.msr_hair_up = bpy.props.FloatProperty(default=4.0, min=-20.0, max=40.0, description="체인이 시작하는 높이 (Bip Head 위, Max 단위, 멜리타 4)")
    WM.msr_hair_last = bpy.props.StringProperty(default="")
    WM.msr_hair_branch = bpy.props.StringProperty(default="BASIC")
    WM.msr_hair_density = bpy.props.StringProperty(default="NORMAL")
    WM.msr_hair_adv = bpy.props.BoolProperty(default=False, description="마디 길이·시작 높이")


def unregister():
    for p in _WM_PROPS:
        try:
            delattr(bpy.types.WindowManager, p)
        except Exception:
            pass
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


# ================================================================ v2 (2026-10-29): 갈래별 체인 + 메쉬 가운데를 지나는 본
#   기준: eunha_t_bip (사람이 만든 헤어 본) — 앞머리·뒷머리 가운데·리본·양갈래(포니테일)를 갈래마다 따로.
#   1) 카드(떨어진 조각)마다 위→아래 중심선. 넓은 카드는 '아래쪽' 너비로 기둥을 나눔 (위는 모이고 아래가 갈라지는 머리)
#   2) 앞/뒤 + 왼/가운데/오른 라벨, 같은 라벨 안에서 모양이 비슷한 카드끼리 묶음
#   3) 정수리 덮개(앞→뒤로 넘어가는 층)·옆으로 누운 카드·두개골 안쪽 카드는 갈래에서 뺌
#   4) 거의 같은 길을 가는 갈래는 하나로 (긴 쪽에 합침)
#   5) 체인마다 자기 가닥 꼭대기에서 시작 (예전: 모든 체인이 Head+4 높이에서 시작)
#   6) 본은 손가락처럼 메쉬 단면의 가운데를 지나게 (묶인 카드 정점을 체인 방향으로 잘라 단면 중심)
def _v2_cards(co, adj, uniq, bins=12, top_ratio=0.03, wide_width=10.0, col_width=8.0):
    pcards = []
    for ci, c in enumerate(uniq):
        P = co[c]
        z = P[:, 2]
        ext = z.max() - z.min()
        top = [v for v in c if co[v, 2] >= z.max() - max(ext * top_ratio, 0.05)]
        dist = _geodesic(co, adj, c, top)
        dd = np.array([dist[v] for v in c])
        dd[~np.isfinite(dd)] = 0
        dmax = dd.max()
        xs = P[:, 0]
        width = xs.max() - xs.min()
        low = z < z.min() + 0.5 * ext
        xl = xs[low] if low.sum() > 3 else xs
        wl = xl.max() - xl.min()
        ncol = max(2, int(round(wl / col_width))) if (width > wide_width and wl > col_width * 1.5) else 1
        colof = np.zeros(len(c), int)
        if ncol > 1:
            edges = np.linspace(xl.min(), xl.max(), ncol + 1)
            colof[:] = -1
            for k in range(ncol):
                last = k == ncol - 1
                m = low & (xs >= edges[k]) & ((xs <= edges[k + 1]) if last else (xs < edges[k + 1]))
                colof[m] = k
            for i in np.where(colof < 0)[0]:
                colof[i] = int(np.clip(np.searchsorted(edges, xs[i]) - 1, 0, ncol - 1))
        for k in range(ncol):
            sel = np.where(colof == k)[0]
            if len(sel) < 3:
                continue
            cs = [c[i] for i in sel]
            ds = dd[sel]
            b = np.minimum((ds / max(dmax, 1e-9) * bins).astype(int), bins - 1)
            line = np.array([co[cs][b == bi].mean(axis=0) for bi in range(bins) if (b == bi).any()])
            if len(line) < 2:
                continue
            L = float(np.linalg.norm(np.diff(line, axis=0), axis=1).sum())
            pcards.append(dict(verts=cs, line=line, tip=line[-1], card=ci, length=L))
    return pcards


def _v2_proj_mean(a, b):
    A = _resample(a, 12)
    return float(np.mean([_project(b, p)[1] for p in A]))


def _v2_centerline(co, verts, joints, radius=6.0):
    """묶인 카드 정점을 체인 방향으로 잘라 단면 중심을 이음 (손가락 맞추기와 같은 방식)"""
    J = _resample(joints, 24)
    total = float(np.linalg.norm(np.diff(J, axis=0), axis=1).sum())
    if total < 1e-6:
        return joints
    ss, keep = [], []
    for v in verts:
        s, d = _project(J, co[v])
        if d <= radius:
            ss.append(s)
            keep.append(v)
    if len(keep) < 10:
        return joints
    ss = np.array(ss)
    P = co[keep]
    nb = 16
    edges = np.linspace(0.0, total, nb + 1)
    pts = []
    for i in range(nb):
        m = (ss >= edges[i]) & (ss <= edges[i + 1])
        if m.sum() >= 3:
            pts.append(P[m].mean(axis=0))
    if len(pts) < 3:
        return joints
    pts = np.array(pts)
    sm = pts.copy()
    sm[1:-1] = (pts[:-2] + 2 * pts[1:-1] + pts[2:]) / 4.0          # 살짝 부드럽게
    return sm


def _v2_trim_top(line, steep=0.7):
    """앞쪽부터, 내려가는 비율(-dz/길이)이 steep 이상인 구간이 시작되는 곳까지 잘라냄"""
    P = _resample(line, 24)
    d = np.diff(P, axis=0)
    n = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    slope = -d[:, 2] / n
    for i in range(len(slope)):
        if slope[i] >= steep and (i + 1 >= len(slope) or slope[i + 1] >= steep * 0.8):
            return P[i:] if len(P) - i >= 4 else P
    return P


def _v2_nseg(L, max_seg):
    return 3 if L < 16.0 else max(4, min(max_seg, int(L / 9.0 + 0.5)))


def _even_joints(J, iters=4):
    """4단계: 마디(관절 사이 직선) 길이를 고르게. _resample 은 곡선 길이 기준이라 굽은 곳의 마디가 짧아짐 →
    관절 꺾은선을 다시 같은 간격으로 몇 번 나눠 직선 길이를 맞춤 (굽은 곳에서 선이 조금 안쪽으로 듦)"""
    J = np.asarray(J, float)
    n = len(J)
    for _ in range(iters):
        J = _resample(J, n)
    return J


def _merge_layers(keep, log, dist=None, overlap=None):
    """집 확인 (11/01): 같은 라벨(앞뒤+좌우)에서 선이 나란히 가까운 가닥(안겹·겉겹)을 한 줄기로.
    긴 쪽을 남기고 선은 두 선의 정점 수 가중 평균(두 겹 사이), 정점·카드는 합침. 마디 수는 뒤에서 합친 선 길이로 다시 계산."""
    dist = HAIR_MERGE_DIST if dist is None else dist
    overlap = HAIR_MERGE_OVERLAP if overlap is None else overlap

    def zrange(c):
        z = c['line'][:, 2]
        return float(z.min()), float(z.max())
    merged = True
    while merged:
        merged = False
        for a_ in range(len(keep)):
            for b_ in range(a_ + 1, len(keep)):
                ca, cb = keep[a_], keep[b_]
                if ca['lab'] != cb['lab']:
                    continue
                d = 0.5 * (_v2_proj_mean(ca['line'], cb['line']) + _v2_proj_mean(cb['line'], ca['line']))
                if d > dist:
                    continue
                (a0, a1), (b0, b1) = zrange(ca), zrange(cb)
                ov = min(a1, b1) - max(a0, b0)
                if ov < overlap * max(min(a1 - a0, b1 - b0), 1e-6):
                    continue
                k, r = (ca, cb) if ca['length'] >= cb['length'] else (cb, ca)
                wk, wr = max(len(k['members']), 1), max(len(r['members']), 1)
                k['line'] = (_resample(k['line'], 24) * wk + _resample(r['line'], 24) * wr) / float(wk + wr)
                k['length'] = float(np.linalg.norm(np.diff(k['line'], axis=0), axis=1).sum())
                k['members'] = k['members'] + r['members']
                k['cards'] = k['cards'] + r['cards']
                k['ncards'] += r['ncards']
                k['merged'] = k.get('merged', 1) + r.get('merged', 1)
                log("%s 겹친 가닥 합침 (선 거리 %.1f, 높이 겹침 %.0f%%) -> 한 줄기" % (k['lab'], d, ov / max(min(a1 - a0, b1 - b0), 1e-6) * 100))
                keep = [x for x in keep if x is not r]
                merged = True
                break
            if merged:
                break
    return keep


def _symmetrize(chains, pcards, co, head, log, attach=8.0, link=6.0, center_x=None, front=None, right_only=None):
    """4단계: 찾은 체인 → 왼쪽·가운데 기준 좌우 대칭 구조.
    가운데(c, 마디 평균 x 가 Head 에서 center_x 안) 체인은 x = Head 로 (서로 겹치는 가운데 체인은 하나로),
    왼쪽(l) 체인은 그대로 + 거울 사본(r), 오른쪽(r) 체인은 right_only 에 따라 빼거나 그대로.
    뺀 체인의 카드는 가장 가까운 최종 체인(attach 안)에, 없으면 Head. 거울 오차 = 거울 체인 ↔ 가장 가까운 원래 오른쪽 체인 선 거리"""
    center_x = SYM_CENTER_X if center_x is None else center_x
    front = SYM_FRONT if front is None else front
    right_only = (os.environ.get("MSR_HAIR_RIGHT") or SYM_RIGHT_ONLY) if right_only is None else right_only
    hx = float(head[0])

    def mirror(J):
        M = np.array(J, float).copy()
        M[:, 0] = 2.0 * hx - M[:, 0]
        return M

    def ldist(a, b):
        return 0.5 * (_v2_proj_mean(a, b) + _v2_proj_mean(b, a))
    final, dropped, pool, rights = [], [], [], []
    for ch in chains:
        mx = float(np.mean(ch['joints'][:, 0])) - hx
        side = 'c' if abs(mx) < center_x else ('l' if mx > 0 else 'r')
        fb = ch['lab'][0]
        ch = dict(ch, lab=fb + side, src=None)
        if fb == 'f' and not front:
            final.append(ch)
            continue
        if side == 'r':
            rights.append(ch)
            continue
        if side == 'c':
            J = np.array(ch['joints'], float).copy()
            J[:, 0] = hx
            ch['joints'] = J
            if 'line' in ch:
                ln = np.array(ch['line'], float).copy()
                ln[:, 0] = hx
                ch['line'] = ln
            same = [k for k in final if k['lab'] == ch['lab'] and ldist(k['joints'], J) < link]
            if same:
                k = same[0]
                if ch['length'] > k['length']:
                    k['joints'] = J
                    k['length'] = ch['length']
                    if 'line' in ch:
                        k['line'] = ch['line']
                k['members'] = k['members'] + ch['members']
                k['core'] = k['core'] + ch['core']
                k['cards'] = k['cards'] + ch['cards']
                k['ncards'] += ch['ncards']
                log("가운데 체인 겹침 -> 하나로 (%s)" % ch['name'])
                continue
            final.append(ch)
        else:
            final.append(ch)
            final.append(dict(name="", joints=mirror(ch['joints']), line=mirror(ch.get('line', ch['joints'])), members=[], core=[], cards=[], ncards=0,
                              length=ch['length'], lab=fb + 'r', src=ch))
    # 오른쪽 가닥: "drop" = 전부 뺌 / "keep" = 그대로 / "mirror" = 왼쪽에 짝(거울 선이 attach 안)이 없는 가닥만 남기고 왼쪽에 거울
    for ch in rights:
        fb = ch['lab'][0]
        if right_only == "keep":
            final.append(ch)
            continue
        if right_only == "mirror":
            pair = min([ldist(ch['joints'], k['joints']) for k in final if k['lab'] == fb + 'r'] or [math.inf])
            if pair > attach:
                final.append(ch)
                final.append(dict(name="", joints=mirror(ch['joints']), line=mirror(ch.get('line', ch['joints'])), members=[], core=[], cards=[], ncards=0,
                                  length=ch['length'], lab=fb + 'l', src=ch))
                log("왼쪽에 짝 없는 오른쪽 가닥 %s -> 남기고 왼쪽에 거울" % ch['name'])
                continue
        dropped.append(ch)
        pool += ch['cards']
    # 뺀 체인의 카드 -> 가장 가까운 최종 체인
    tohead = 0
    for i in pool:
        pc = pcards[i]
        best, bc = math.inf, None
        for k in final:
            d = _v2_proj_mean(pc['line'], k['joints'])
            if d < best:
                best, bc = d, k
        if bc is not None and best <= attach:
            bc['members'] = bc['members'] + list(pc['verts'])
            bc['cards'].append(i)
            bc['ncards'] += 1
            if bc['src'] is not None:
                bc['core'] = bc['core'] + list(pc['verts'])
        else:
            tohead += 1
    # 거울 체인에 카드가 원본의 절반도 안 오면(그쪽 카드가 거르기에서 빠졌을 때) 어느 체인에도 안 든 카드를 attach 안에서 줍는다
    used = {i for k in final for i in k['cards']} | set(pool)
    free = [i for i in range(len(pcards)) if i not in used]
    for k in final:
        if k['src'] is None or k['ncards'] * 2 >= max(k['src']['ncards'], 1):
            continue
        got = 0
        for i in free:
            if i in used:
                continue
            pc = pcards[i]
            if _v2_proj_mean(pc['line'], k['joints']) <= attach:
                k['members'] = k['members'] + list(pc['verts'])
                k['core'] = k['core'] + list(pc['verts'])
                k['cards'].append(i)
                k['ncards'] += 1
                used.add(i)
                got += 1
        if got:
            log("거울 체인(%s 거울)에 남은 카드 %d장 붙임" % (k['src']['name'], got))
    # 이름: 가운데 c1.., 왼쪽은 x 순서 l1.., 거울은 같은 번호 r1..
    out = []
    for fb in ('f', 'b'):
        cs = [k for k in final if k['lab'] == fb + 'c' and k['src'] is None]
        cs.sort(key=lambda k: float(np.mean(k['joints'][:, 1])))
        for n, k in enumerate(cs, 1):
            k['name'] = "%s%d" % (k['lab'], n)
            out.append(k)
        pairs = []
        for k in final:
            if k['lab'] != fb + 'l':
                continue
            if k['src'] is None:
                pairs.append((k, next((q for q in final if q['src'] is k), None)))
            else:
                pairs.append((k, k['src']))
        pairs.sort(key=lambda p: float(np.mean(p[0]['joints'][:, 0])))
        for n, (l, r) in enumerate(pairs, 1):
            l['name'] = "%sl%d" % (fb, n)
            out.append(l)
            if r is not None:
                r['name'] = "%sr%d" % (fb, n)
                out.append(r)
        paired = {id(r) for _, r in pairs if r is not None}
        rs = [k for k in final if k['lab'] == fb + 'r' and id(k) not in paired]
        rs.sort(key=lambda k: -float(np.mean(k['joints'][:, 0])))
        for n, k in enumerate(rs, len(pairs) + 1):
            k['name'] = "%s%d" % (k['lab'], n)
            out.append(k)
    for k in out:
        if k['src'] is not None:
            err = min([ldist(k['joints'], d['joints']) for d in dropped if d['lab'][0] == k['lab'][0]] or [math.nan])
            log("거울 체인 %s <- %s: 카드 %d장, 원래 그쪽 가닥과 선 거리 %.1f" % (k['name'], k['src']['name'], k['ncards'], err))
    if dropped:
        log("오른쪽 가닥 %d개(%s) 체인 없음 -> 카드 %d장 가까운 체인, %d장 Head" % (len(dropped), ", ".join(d['name'] for d in dropped), len(pool) - tohead, tohead))
    return out


def analyze(co, polys, head, seg_len=8.0, front_y=2.0, center_x=2.5, min_len=12.0, link=6.0, absorb=4.0,
            drop_ratio=0.5, skull_r=5.0, attach=8.0, centre_r=4.0, bundle_start=4.0, bundle_end=6.0, steep=0.7, max_seg=10, blend=0.3, head_ramp=0.3, limit=4, log=None, head_frac=None,
            sym=None, **_old):
    """hair cards -> dict(chains=[dict(name, joints)], bones=["Head", "fr1_01", ..], weights=[[(bone idx, w)] per vertex])"""
    log = log or (lambda *a: None)
    co = np.asarray(co, float)
    nv = len(co)
    head = np.asarray(head, float)
    adj = _adjacency(polys)
    comps = [c for c in _components(nv, polys) if len(c) > 3]
    uniq, keys, twins = [], [], []
    for c in comps:
        cen = co[c].mean(axis=0)
        dup = None
        for ki, (cc, ce) in enumerate(keys):
            if cc == len(c) and np.linalg.norm(ce - cen) < 0.05:
                dup = ki
                break
        if dup is not None:
            twins.append((c, uniq[dup]))
            continue
        keys.append((len(c), cen))
        uniq.append(c)
    log("카드 %d -> 겹침 제거 %d" % (len(comps), len(uniq)))
    pcards = _v2_cards(co, adj, uniq)

    def label(pc):
        cen = co[pc['verts']].mean(axis=0)
        fb = 'f' if cen[1] < head[1] + front_y else 'b'
        dx = (pc['tip'][0] + cen[0]) / 2 - head[0]
        side = 'c' if abs(dx) < center_x else ('r' if dx < 0 else 'l')
        return fb + side
    groups, shorts = {}, []
    for i, pc in enumerate(pcards):
        if pc['length'] < min_len:
            shorts.append(i)
            continue
        groups.setdefault(label(pc), []).append(i)
    cand = []
    for lab in sorted(groups):
        clusters = [[i] for i in groups[lab]]

        def cd(a, b):
            return np.mean([np.linalg.norm(_resample(pcards[i]['line'], 8) - _resample(pcards[j]['line'], 8), axis=1).mean()
                            for i in a for j in b])
        while True:
            best, bp = math.inf, None
            for a in range(len(clusters)):
                for b in range(a + 1, len(clusters)):
                    d = cd(clusters[a], clusters[b])
                    if d < best:
                        best, bp = d, (a, b)
            if bp is None or best > link:
                break
            a, b = bp
            clusters[a] += clusters[b]
            del clusters[b]
        for cl in clusters:
            mx = max(pcards[i]['length'] for i in cl)
            use = [i for i in cl if pcards[i]['length'] >= 0.7 * mx]
            mean = np.mean([_resample(pcards[i]['line'], 24) for i in use], axis=0)
            L = float(np.linalg.norm(np.diff(mean, axis=0), axis=1).sum())
            cand.append(dict(lab=lab, line=mean, length=L, members=[v for i in cl for v in pcards[i]['verts']], ncards=len(cl), cards=list(cl)))
    # 거르기: 정수리 덮개(앞→뒤로 넘어감)는 머리 뒤부터만, 옆으로 누운 카드·두개골 안쪽 카드는 뺌
    ok = []
    for c in cand:
        j = c['line']
        if j[0][1] < head[1] and j[-1][1] > head[1] + 4:
            line = _resample(j, 40)
            k = int(np.argmax(line[:, 1] > head[1] + 2))
            line = line[k:]
            L = float(np.linalg.norm(np.diff(line, axis=0), axis=1).sum())
            if L < min_len:
                log("%s 덮개 층 -> 뺌" % c['lab'])
                continue
            c = dict(c, line=line, length=L)
            j = line
        if j[0][2] - j[-1][2] < drop_ratio * c['length']:
            log("%s 옆으로 누운 카드 (길이 %.1f) -> Head" % (c['lab'], c['length']))
            continue
        tip = j[-1]
        if np.hypot(tip[0] - head[0], tip[1] - head[1]) < skull_r and tip[2] > head[2] - 3:
            log("%s 두개골 안쪽 카드 -> Head" % c['lab'])
            continue
        ok.append(c)
    # 거의 같은 길이면 긴 갈래에 합침 (선은 평균)
    ok.sort(key=lambda c: -c['length'])
    keep = []
    for c in ok:
        hit = [k for k in keep if _v2_proj_mean(c['line'], k['line']) < absorb]
        if hit:
            k = hit[0]
            k['members'] = k['members'] + c['members']
            k['cards'] = k['cards'] + c['cards']
            if abs(k['length'] - c['length']) < 0.3 * k['length']:
                k['line'] = (_resample(k['line'], 24) + _resample(c['line'], 24)) / 2.0
            continue
        keep.append(c)
    # 큰 덩어리(포니테일·묶은 머리): 시작과 끝이 서로 가까운 갈래들은 한 체인으로 (가운데에 가장 가까운 것을 남김)
    merged = True
    while merged:
        merged = False
        for a_ in range(len(keep)):
            for b_ in range(a_ + 1, len(keep)):
                ca, cb = keep[a_], keep[b_]
                ds = float(np.linalg.norm(ca['line'][0] - cb['line'][0]))
                de = float(np.linalg.norm(ca['line'][-1] - cb['line'][-1]))
                if ds < bundle_start and de < bundle_end:
                    k, r = (ca, cb) if abs(float(np.mean(ca['line'][:, 0])) - head[0]) <= abs(float(np.mean(cb['line'][:, 0])) - head[0]) else (cb, ca)
                    k['members'] = k['members'] + r['members']
                    k['cards'] = k['cards'] + r['cards']
                    k['ncards'] += r['ncards']
                    if k['lab'][1] != 'c' and abs(float(np.mean(k['line'][:, 0])) - head[0]) < center_x * 1.5:
                        k['lab'] = k['lab'][0] + 'c'
                    log("%s 덩어리에 %s 합침 (시작 %.1f, 끝 %.1f 거리)" % (k['lab'], r['lab'], ds, de))
                    keep = [x for x in keep if x is not r]
                    merged = True
                    break
            if merged:
                break
    mg = os.environ.get("MSR_HAIR_MERGE")
    if (HAIR_MERGE_LAYERS if mg is None else mg not in ("0", "off", "")) and len(keep) > 1:
        keep = _merge_layers(keep, log)
    for c in keep:
        c['core'] = list(c['members'])          # 단면 중심은 갈래 자기 카드로만 (붙인 짧은 카드 제외)
    # 짧은 카드는 가까운 갈래에 붙임 (갈래 모양은 그대로)
    nat = 0
    for i in shorts:
        vs = pcards[i]['verts']
        sample = vs[::max(1, len(vs) // 40)]
        best, bc = math.inf, None
        for c in keep:
            d = float(np.mean([_project(c['line'], co[v])[1] for v in sample]))
            if d < best:
                best, bc = d, c
        if bc is not None and best <= attach:
            bc['members'] = bc['members'] + list(vs)
            bc['cards'].append(i)
            nat += 1
    log("짧은 카드 %d장 중 %d장 갈래에 붙임" % (len(shorts), nat))
    # 이름 (라벨 안에서 x 순서) + 메쉬 가운데를 지나는 선
    chains = []
    count = {}
    for c in sorted(keep, key=lambda c: (c['lab'], float(np.mean(c['line'][:, 0])))):
        count[c['lab']] = count.get(c['lab'], 0) + 1
        mid = _v2_centerline(co, c['core'], c['line'], radius=centre_r * (2.0 if (c['ncards'] > 6 or c.get('merged', 1) > 1) else 1.0))
        # 정수리·이마처럼 머리에 붙어 누운 부분은 빼고, 아래로 흘러내리기 시작하는 곳부터 체인 (머리 모양 유지 부분은 Head 가 맡음)
        mid = _v2_trim_top(mid, steep)
        L = float(np.linalg.norm(np.diff(mid, axis=0), axis=1).sum())
        nseg = _v2_nseg(L, max_seg)
        name = "%s%d" % (c['lab'], count[c['lab']])
        chains.append(dict(name=name, joints=_even_joints(_resample(mid, nseg + 1)), line=mid, members=c['members'], core=c['core'], length=L,
                           lab=c['lab'], cards=list(c['cards']), ncards=c['ncards']))
        log("체인 %s: 카드 %d장, 길이 %.1f, 마디 %d" % (name, c['ncards'], L, nseg))
    sym = (sym or os.environ.get("MSR_HAIR_SYM") or HAIR_SYM).lower()
    if sym != "off" and chains:
        chains = _symmetrize(chains, pcards, co, head, log, attach=attach, link=link)
    # 웨이트: 체인을 따라 (마디 사이 부드럽게, 시작은 Head 에서 서서히)
    wp = dict(blend=blend, head_ramp=head_ramp, head_frac=head_frac, limit=limit)
    bones, wt = _chain_weights(co, chains, nv, **wp)
    _twin_copy(co, wt, twins)
    return dict(chains=chains, bones=bones, weights=wt, twins=twins, wp=wp, sym=sym)


def _seg_w(s, segl, nseg, blend, ramp):
    """체인 위 거리 s -> {마디 번호: 웨이트} (-1 = Head). 마디 사이 blend 폭으로 섞고, 시작 ramp 마디 안은 Head 에서 서서히"""
    half = blend / 2.0
    u = s / segl
    k = min(int(u), nseg - 1)
    f = u - k
    w = {k: 1.0}
    if f < half and k > 0:
        t = 0.5 + f / (2 * half) * 0.5
        w = {k: t, k - 1: 1 - t}
    elif f > 1 - half and k < nseg - 1:
        t = 0.5 + (1 - f) / (2 * half) * 0.5
        w = {k: t, k + 1: 1 - t}
    if ramp > 0 and u < ramp:
        hw = 1.0 - u / ramp
        w = {i: x * (1 - hw) for i, x in w.items()}
        w[-1] = hw
    return w


def _chain_weights(co, chains, nv, blend=0.3, head_ramp=0.3, head_frac=None, limit=4, near=2, cut=0.1):
    """chains -> (bones ["Head", "fr1_01", ..], weights [[(bone idx, w)] per vertex]).
    체인마다 자기 정점을 체인 따라. blend=True 인 체인들(간단판 뒤 3갈래)은 그 정점들을 가까운 두 체인 사이에서 섞음 (예전 auto3)"""
    bones = ["Head"]
    wt = [[(0, 1.0)] for _ in range(nv)]
    info = []
    for ch in chains:
        j = ch['joints']
        nseg = len(j) - 1
        segl = float(np.linalg.norm(np.diff(j, axis=0), axis=1).sum()) / nseg
        base = len(bones)
        bones += ["%s_%02d" % (ch['name'], k) for k in range(1, nseg + 1)]
        ramp = head_frac * nseg if head_frac else head_ramp      # Head 섞임: 체인 길이 비율 → 마디 단위
        info.append((j, nseg, segl, base, ramp))
        if ch.get('blend'):
            continue
        for v in ch['members']:
            s, _ = _project(j, co[v])
            if s <= 1e-6:
                continue
            w = _seg_w(s, segl, nseg, blend, ramp)
            items = sorted([((0 if i == -1 else base + i), x) for i, x in w.items() if x > 1e-4], key=lambda t: -t[1])[:limit]
            tot = sum(x for _, x in items)
            wt[v] = [(i, x / tot) for i, x in items]
    grp = [c for c, ch in enumerate(chains) if ch.get('blend')]
    for v in sorted({v for c in grp for v in chains[c]['members']}):
        p = co[v]
        sc = sorted((((1.0 / (_project(info[c][0], p)[1] + 0.5)) ** 4, c) for c in grp), key=lambda t: -t[0])[:near]
        tot = sum(s for s, _ in sc)
        sh = [(s / tot, c) for s, c in sc if s / tot >= cut]
        tot = sum(s for s, _ in sh)
        acc = {}
        for s_, c in sh:
            j, nseg, segl, base, ramp = info[c]
            s, _ = _project(j, p)
            w = _seg_w(s, segl, nseg, blend, ramp) if s > 1e-6 else {-1: 1.0}
            for i, x in w.items():
                b = 0 if i == -1 else base + i
                acc[b] = acc.get(b, 0.0) + s_ / tot * x
        items = sorted([(b, x) for b, x in acc.items() if x > 1e-4], key=lambda t: -t[1])[:limit]
        tot = sum(x for _, x in items)
        wt[v] = [(i, x / tot) for i, x in items]
    return bones, wt


def _twin_copy(co, wt, twins):
    """겹쳐 놓인 같은 카드(두 장): 가까운 정점 값 그대로"""
    for dupv, kept in twins:
        kc = co[kept]
        for v in dupv:
            wt[v] = list(wt[kept[int(np.argmin(((kc - co[v]) ** 2).sum(axis=1)))]])


# ================================================================ 2.2 (2026-11-01): 헤어 패널 선택 (갈래·마디·코스튬) — 블렌더 미리보기 → [반영] → [되돌리기]
#   갈래 '간단' = 뒷머리를 BL1·BC1·BR1 3갈래로 (예전 2_dev\rigtools_parts\hair_bones.py auto3/back3: 뒤 가닥 시작 x 로
#   가운데(|x| < BACK_C)·왼·오른 묶고, 높이 조각마다 두께 가운데를 따라 관절). 앞머리는 '기본' 그대로. 좌우 거울(HAIR_SYM) 유지.
#   마디 = 체인마다 마디 수 +1 / 그대로 / -1 (최소 2). 코스튬 = 새 체인 없이 지금 체인 끝에 마디를 이어 붙임 (예전 extend/plan_costume).
BACK_C = 3.0          # 간단판: 뒤 가닥 시작 x 가 Head 에서 이 안이면 가운데(BC1) 묶음 (예전 auto3 값)
SIMPLE_BINS = 12      # 간단판: 묶음 정점을 높이로 나누는 조각 수
SIMPLE_START = 4.0    # 간단판: 가운데 가닥이 없어 정점으로 BC1 을 만들 때, Head 위 이 높이부터 (예전 auto3 start_up). 묶음은 체인 시작 높이부터
DENSITY = {"DENSE": 1, "NORMAL": 0, "SPARSE": -1}
EXT_MIN = 0.5         # 코스튬: 가닥이 체인 끝을 마디 길이 x 이만큼 넘을 때만 마디를 붙임 (예전 값)


def _arclen(line):
    return float(np.linalg.norm(np.diff(line, axis=0), axis=1).sum()) if len(line) > 1 else 0.0


def _simple_back(chains, co, head, log, sym=True, centre=BACK_C, bins=SIMPLE_BINS, start_up=SIMPLE_START, max_seg=10):
    """뒤 체인(b*) -> 시작 x 로 가운데·왼·오른 묶음 -> 묶음마다 체인 1개 (bc1·bl1·br1). sym 이면 오른쪽 = 왼쪽 거울, 가운데 x = Head.
    앞 체인(f*)은 그대로. 새 체인은 blend=True (그 정점들을 가까운 두 체인 사이에서 섞어 웨이트)"""
    hx = float(head[0])
    front = [c for c in chains if c['lab'][0] == 'f']
    back = [c for c in chains if c['lab'][0] == 'b']
    if not back:
        log("간단: 뒤 가닥 없음 -> 기본과 같음")
        return chains
    grp = {'c': [], 'l': [], 'r': []}
    for c in back:
        x = float(c['joints'][0][0]) - hx
        grp['c' if abs(x) < centre else ('l' if x > 0 else 'r')].append(c)
    zs = float(head[2]) + start_up

    def members(chs):
        return sorted({v for c in chs for v in c['members']})

    def line_of(chs, mem):
        # 조각은 묶음 체인이 시작하는 높이부터 (2.0 가닥은 흘러내리기 시작하는 곳에서 시작 · 지젤 BC1 은 Head+4 보다 위에서 끝남)
        z0 = float(np.mean([c['joints'][0][2] for c in chs])) if chs else zs
        P = co[mem] if len(mem) else np.zeros((0, 3))
        P = P[P[:, 2] <= z0]
        if len(P) < 3:
            return None
        e = np.linspace(z0, P[:, 2].min(), bins + 1)
        pts = [np.mean([c['joints'][0] for c in chs], axis=0)] if chs else []
        for i in range(bins):
            s = P[(P[:, 2] <= e[i]) & (P[:, 2] >= e[i + 1])]
            if len(s):
                pts.append([(s[:, 0].min() + s[:, 0].max()) / 2, (s[:, 1].min() + s[:, 1].max()) / 2, s[:, 2].mean()])
        if len(pts) < 2:
            return None
        pts.append([pts[-1][0], pts[-1][1], P[:, 2].min()])
        return np.array(pts, float)

    def mirror(L):
        M = np.array(L, float).copy()
        M[:, 0] = 2.0 * hx - M[:, 0]
        return M
    mem = {k: members(v) for k, v in grp.items()}
    if not mem['c']:
        # 가운데에서 시작하는 가닥이 없으면 뒤 정점 중 가운데(|x| < centre) 것으로
        allb = members(back)
        mem['c'] = [v for v in allb if abs(co[v][0] - hx) < centre]
        if len(mem['c']) < 30:
            mem['c'] = []
    lines = {k: line_of(grp[k], mem[k]) for k in ('c', 'l', 'r')}
    if lines['c'] is not None:
        lines['c'][:, 0] = hx
    if sym:
        if lines['l'] is not None:
            lines['r'] = mirror(lines['l'])
        elif lines['r'] is not None:
            lines['l'] = mirror(lines['r'])
    out = list(front)
    for k in ('c', 'l', 'r'):
        L = lines[k]
        if L is None:
            log("간단: 뒤 %s 묶음 없음" % {'c': "가운데", 'l': "왼쪽", 'r': "오른쪽"}[k])
            continue
        length = _arclen(L)
        nseg = _v2_nseg(length, max_seg)
        name = "b%s1" % k
        out.append(dict(name=name, joints=_even_joints(_resample(L, nseg + 1)), line=L, members=mem[k], core=mem[k], length=length,
                        lab="b" + k, cards=[], ncards=0, blend=True, src=None))
        log("간단: %s <- 뒤 가닥 %s, 길이 %.1f, 마디 %d" % (name, ", ".join(c['name'] for c in grp[k]) or "가운데 정점", length, nseg))
    return out


def _redensity(chains, d):
    """마디 수 +d (최소 2), 체인 선(line) 위에서 다시 고르게"""
    out = []
    for ch in chains:
        n = max(2, len(ch['joints']) - 1 + d)
        line = ch.get('line', ch['joints'])
        out.append(dict(ch, joints=_even_joints(_resample(line, n + 1))))
    return out


def variant(res, co, head, branch="BASIC", density="NORMAL", log=None):
    """analyze 결과 -> 선택(갈래·마디)을 적용한 체인 + 웨이트. BASIC·NORMAL = analyze 결과 그대로"""
    log = log or (lambda *a: None)
    chains = list(res['chains'])
    if branch == "SIMPLE":
        chains = _simple_back(chains, co, head, log, sym=res.get('sym', "lr") != "off")
    d = DENSITY.get(density, 0)
    if d:
        chains = _redensity(chains, d)
    if branch == "BASIC" and not d:
        return dict(res)
    bones, wt = _chain_weights(co, chains, len(co), **res['wp'])
    _twin_copy(co, wt, res['twins'])
    return dict(res, chains=chains, bones=bones, weights=wt)


# ---------------------------------------------------------------- 코스튬: 지금 체인에 마디 이어 붙이기 (예전 extend / plan_costume, 새 체인 없음)
def _sub(line, s0, s1):
    """polyline 의 곡선 길이 s0..s1 부분"""
    line = np.asarray(line, float)
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))])

    def at(t):
        return np.array([np.interp(t, s, line[:, k]) for k in range(3)])
    mid = [line[i] for i in range(len(line)) if s0 < s[i] < s1]
    return np.array([at(s0)] + mid + [at(s1)])


def _mean_line(lines, step=1.0):
    """가닥들을 시작점 0 에 맞춰 곡선 길이로 평균 (긴 가닥 혼자 끝을 맡음)"""
    L = max(_arclen(l) for l in lines)
    t = np.arange(0.0, L + 1e-6, step)
    acc, cnt = np.zeros((len(t), 3)), np.zeros(len(t))
    for l in lines:
        l = np.asarray(l, float)
        s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(l, axis=0), axis=1))])
        ok = t <= s[-1] + 1e-6
        acc[ok] += np.stack([np.interp(t[ok], s, l[:, k]) for k in range(3)], axis=1) - l[0]
        cnt[ok] += 1
    return acc / np.maximum(cnt, 1)[:, None]


def _line_weights(co, J, members, segbones, wt, blend=0.3, head_ramp=0.3, limit=4, own=None):
    """마디 길이가 제각각인 체인(기존 본 + 붙인 본) 따라 웨이트. segbones: 마디마다 본 번호 (0 = Head).
    own: {정점: 그 정점 가닥 선} - 체인 위 위치를 자기 가닥에서 잼 (체인 옆 가닥)"""
    J = np.asarray(J, float)
    L = np.linalg.norm(np.diff(J, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(L)])
    nseg = len(L)
    for v in members:
        s, _ = _project(own[v] if own and v in own else J, co[v])
        if s <= 1e-6:
            continue
        k = min(int(np.searchsorted(cum, s, side="right")) - 1, nseg - 1)
        u = k + (s - cum[k]) / max(L[k], 1e-9)
        w = _seg_w(u, 1.0, nseg, blend, head_ramp)
        acc = {}
        for i, x in w.items():
            if x > 1e-4:
                b = 0 if i == -1 else segbones[i]
                acc[b] = acc.get(b, 0.0) + x
        items = sorted(acc.items(), key=lambda t: -t[1])[:limit]
        tot = sum(x for _, x in items)
        wt[v] = [(i, x / tot) for i, x in items]


def chain_label(prefix, J, head):
    """기존 체인의 앞뒤 + 좌우: 이름(bone_hair_FR1_..), 없으면 시작 위치"""
    m = re.match(r"^bone_hair_([FB][LRC])", prefix, re.I)
    if m:
        return m.group(1).upper()
    e = J[0]
    return ("F" if e[1] < head[1] + 2.0 else "B") + ("C" if abs(e[0] - head[0]) < 2.0 else ("R" if e[0] < head[0] else "L"))


def plan_extend(res, co, head, old, log=None):
    """코스튬 머리 가닥(res = analyze) -> 지금 체인(old = existing_chains)에 배정 (같은 앞/뒤, 반대 방향 아님, 시작이 가장 가까운 것).
    가닥이 체인보다 길면 그 체인 끝에 마디(체인 평균 마디 길이)를 붙임. 새 체인은 안 만듦 (같은 앞/뒤 체인이 없으면 아무 체인, 없으면 Head).
    returns {old idx: dict(add=[joints], members, strands, lines, own)}"""
    log = log or (lambda *a: None)
    use = {}
    for st in sorted(res['chains'], key=lambda c: -c['length']):
        line = st.get('line', st['joints'])
        a = line[0]
        da = _nrm(_sub(line, 0.0, min(8.0, _arclen(line)))[-1] - a)
        best, bd = None, math.inf
        for same in (True, False):
            for j, ch in enumerate(old):
                E = ch['joints']
                if same and chain_label(ch['prefix'], E, head)[0] != st['name'][0].upper():
                    continue
                if float(_nrm(E[1] - E[0]) @ da) < -0.3:      # 반대로 가는 체인
                    continue
                d = float(np.linalg.norm(E[0] - a))
                if d < bd:
                    best, bd = j, d
            if best is not None:
                break
        if best is None:
            log("가닥 %s: 맞는 체인 없음 -> Head" % st['name'])
            continue
        u = use.setdefault(best, dict(add=[], members=[], strands=[], lines=[], own={}))
        u['members'] += list(st['members'])
        u['own'].update({v: line for v in st['members']})
        u['strands'].append(st['name'])
        u['lines'].append(line)
    for j, u in use.items():
        E = old[j]['joints']
        Lc = _arclen(E)
        seg = Lc / max(len(E) - 1, 1)
        M = _mean_line(u['lines'])
        Lm = _arclen(M)
        if Lm - Lc >= seg * EXT_MIN:
            k = max(1, min(10, int((Lm - Lc) / seg + 0.5)))
            part = _sub(M, min(Lc, Lm), Lm)
            part = part - part[0] + E[-1]
            u['add'] = list(_resample(part, k + 1)[1:])
        log("기존 %s: 가닥 %s%s" % (old[j]['prefix'].rstrip("_").replace("bone_hair_", "").replace("Bone_hair_", ""), ", ".join(u['strands']),
                                 " -> 마디 %d개 붙임" % len(u['add']) if u['add'] else " (길이 충분, 그대로)"))
    return use


def _nrm(v):
    v = np.asarray(v, float)
    return v / max(np.linalg.norm(v), 1e-9)


def _level(d):
    z = np.cross([0.0, 0.0, 1.0], d)
    return z / np.linalg.norm(z) if np.linalg.norm(z) > 1e-3 else np.array([1.0, 0.0, 0.0])


def _carry(z, d):
    # 앞 본 Z 축을 이 본 방향에 맞게 돌림 (긴 가닥이 꺾여도 뒤집히지 않게)
    z = np.asarray(z, float) - (np.asarray(z, float) @ d) * d
    return z / np.linalg.norm(z) if np.linalg.norm(z) > 1e-3 else _level(d)
