# uv_weights.py (Claude, 2026-11-01)  개발본. numpy 만 사용 (bpy 없이도 돌아감 → 헤드리스 시험·object_bones 에서 import 둘 다 가능)
# 겹친 조각 묶음(파트) 웨이트를 (u, v) 좌표의 매끈한 함수로 다시 계산.
#   u = 부모 축(Z) 둘레 각도 (0 = 앞, + = 왼쪽, ±180 = 뒤)   → 이웃 두 체인을 각도 비례로 섞음
#   v = 체인 시작 줄(윗단)에서 메쉬 위를 따라간 거리(측지 거리). 겹친 조각(겉·안감·띠)은 1.5 안에 맞닿은 점을
#       그래프로 이어 한 표면처럼 재므로 같은 자리면 같은 v → 같은 웨이트 (조각마다 따로 계산하던 틈이 없어짐)
#   s = 마디 좌표: 체인마다 마디 점(J_i)이 표면에서 갖는 v 를 재서 v → s 를 1차식으로 맞춤 → 같은 줄은 같은 s 에서 마디가 넘어감
#   마디 섞기: 마디 경계 ±ALONG_HW(마디 길이 비율) 선형. 윗단: s < TOP_BLEND 에서 몸 웨이트(가장 가까운 몸 정점 값)와 이어짐
# 본 구조·이름은 건드리지 않음 (웨이트만).
import heapq
import math
import numpy as np

ALONG_HW = 0.3      # 마디 경계 섞임 폭 (마디 길이 비율, ±)
TOP_BLEND = 0.5     # 체인 시작(s=0)에서 이 s 까지 몸 웨이트 → 체인 웨이트로 넘어감 (s<=0 은 몸 100%)
LINK_R = 1.5        # Max 단위: 다른 조각 정점이 이 안에 있으면 그래프 연결(겹친 천)
LINK_K = 3          # 조각 사이 연결: 정점마다 가장 가까운 K 개
BODY_R = 3.0        # 윗단 몸 웨이트를 빌릴 몸 정점 탐색 거리
JOINT_R = 6.0       # 마디 점이 표면에서 이보다 멀면 v→s 맞추기에서 뺌
LIMIT = 4           # 정점당 본 수


# ---------------------------------------------------------------- mesh helpers
def islands(nv, F):
    """face (a,b,c) 목록 → 정점마다 조각 번호"""
    par = np.arange(nv)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for f in F:
        a = f[0]
        for b in f[1:]:
            ra, rb = find(a), find(b)
            if ra != rb:
                par[ra] = rb
    lab = np.array([find(i) for i in range(nv)])
    return np.unique(lab, return_inverse=True)[1]


def mesh_edges(F):
    E = set()
    for f in F:
        n = len(f)
        for i in range(n):
            a, b = f[i], f[(i + 1) % n]
            if a != b:
                E.add((min(a, b), max(a, b)))
    return np.array(sorted(E), dtype=np.int64).reshape(-1, 2)


def _near_pairs(P, A, B, r, k):
    """A, B: 정점 번호 배열. A 의 각 정점에서 r 안의 B 정점 중 가까운 k 개 → [(a, b, d)]"""
    out = []
    if len(A) == 0 or len(B) == 0:
        return out
    PB = P[B]
    step = 512
    for i0 in range(0, len(A), step):
        a = A[i0:i0 + step]
        D = np.linalg.norm(P[a][:, None, :] - PB[None, :, :], axis=2)
        for r_i in range(len(a)):
            row = D[r_i]
            idx = np.where(row <= r)[0]
            if len(idx) == 0:
                continue
            idx = idx[np.argsort(row[idx])[:k]]
            for j in idx:
                out.append((int(a[r_i]), int(B[j]), float(row[j])))
    return out


def dijkstra(nloc, adj, src, src_d=None):
    """adj: list of [(j, w)] per local vertex. src: local vertex ids (거리 0 또는 src_d)"""
    dist = np.full(nloc, np.inf)
    h = []
    for k, s in enumerate(src):
        d0 = 0.0 if src_d is None else float(src_d[k])
        if d0 < dist[s]:
            dist[s] = d0
            heapq.heappush(h, (d0, int(s)))
    while h:
        d, i = heapq.heappop(h)
        if d > dist[i]:
            continue
        for j, w in adj[i]:
            nd = d + w
            if nd < dist[j]:
                dist[j] = nd
                heapq.heappush(h, (nd, j))
    return dist


def geodesic(nloc, adj, faces, Ploc, src, src_d=None):
    """측지 거리: Dijkstra + 삼각형 안을 가로지르는 갱신 (엣지만 따라가면 지그재그로 5~15% 길어져 줄마다 v 가 달라짐).
    faces: 파트 안 삼각형 (local 번호). 두 꼭짓점이 확정되면 그 둘의 거리로 삼각형 평면 위 가상 광원을 놓고 셋째 꼭짓점까지 직선 거리"""
    dist = np.full(nloc, np.inf)
    done = np.zeros(nloc, dtype=bool)
    vf = [[] for _ in range(nloc)]
    for fi, f in enumerate(faces):
        for a in f:
            vf[a].append(fi)
    h = []
    for k_, s in enumerate(src):
        d0 = 0.0 if src_d is None else float(src_d[k_])
        if d0 < dist[s]:
            dist[s] = d0
            heapq.heappush(h, (d0, int(s)))

    def tri(i, j, k):
        di, dj = dist[i], dist[j]
        pi, pj, pk = Ploc[i], Ploc[j], Ploc[k]
        e = pj - pi
        L = np.linalg.norm(e)
        if L < 1e-9:
            return np.inf
        ex = e / L
        q = pk - pi
        kx = float(q @ ex)
        ky_v = q - kx * ex
        ky = float(np.linalg.norm(ky_v))
        if ky < 1e-9:
            return np.inf
        sx = (di * di - dj * dj + L * L) / (2 * L)
        sy2 = di * di - sx * sx
        if sy2 < 0:
            return np.inf
        sy = -math.sqrt(sy2)
        # S→k 선이 엣지 ij 안을 지나야 함
        t = -sy / (ky - sy)
        x0 = sx + t * (kx - sx)
        if x0 < 0 or x0 > L:
            return np.inf
        return math.hypot(kx - sx, ky - sy)
    while h:
        d, i = heapq.heappop(h)
        if d > dist[i] or done[i]:
            continue
        done[i] = True
        for j, w in adj[i]:
            nd = d + w
            if nd < dist[j]:
                dist[j] = nd
                heapq.heappush(h, (nd, j))
        for fi in vf[i]:
            f = faces[fi]
            o = [a for a in f if a != i]
            if len(o) != 2:
                continue
            j, k = o
            for a, b in ((j, k), (k, j)):
                if done[a] and not done[b]:
                    nd = tri(i, a, b)
                    if nd < dist[b]:
                        dist[b] = nd
                        heapq.heappush(h, (nd, b))
    return dist


def angle_deg(P, cx, cy):
    """둘레 각도: 0 = 앞(-Y), + = 왼쪽(+X), ±180 = 뒤"""
    return np.degrees(np.arctan2(P[:, 0] - cx, -(P[:, 1] - cy)))


def _wrap(a):
    return (a + 180.0) % 360.0 - 180.0


# ---------------------------------------------------------------- main
def uv_part_weights(P, F, part_vids, chains, body_w=None, parent_bone=None, lab=None,
                    along_hw=ALONG_HW, top_blend=TOP_BLEND, link_r=LINK_R, link_k=LINK_K,
                    body_r=BODY_R, limit=LIMIT, geo_tri=True, s_mode="common", v_mode="height",
                    top_mode="nearest", ref_mixed_top=0.09, top_chain=0.0, log=None):
    """top_mode 'nearest' = 바로 옆 몸 정점 웨이트를 s<=0 에서 (1-top_chain)×100%, top_blend 까지 매끈하게 체인으로 (기본, 11-01 정현 확정)
             'ref' = 1.72 ref_weights 윗단 규칙(부모 몸 본 하나, 참고값 bip_mixed_top: 치마 0.09). 비교용(이음새 차이 0.90 로 나빠 안 씀)
    top_chain: 윗단에도 체인을 이만큼 남김 (작업자식 0.5). 0 = 첫 마디 위는 몸 100%
    v_mode 'height' = 윗단에서 내려온 높이(z) (기본, 11-01 정현: 눈에 보이는 가로줄이 고르게),
           'geodesic' = 메쉬 위를 따라간 길이 (비스듬한 뒤쪽은 같은 높이라도 마디가 늦게 넘어감. 접힌 천·트인 앞섶용)
    s_mode 'common' = 모든 체인의 v→s 식을 평균한 한 식 (같은 v 면 어느 각도든 같은 마디 → 줄이 고름. 마디 점 높이가 체인마다
    1~2 다른 만큼 경계가 실제 마디와 조금 어긋남), 'local' = 이웃 두 체인의 식만 (경계 = 실제 마디, 줄은 체인마다 들쭉)"""
    """P (nv,3) Max 단위 세계 좌표, F face 목록(정점 번호), part_vids: 파트(겹친 조각 묶음) 정점 번호,
    chains: [(names [bone_01..bone_n], J (n+1,3) 마디 점: bone_01 머리 … 마지막 본 꼬리)],
    body_w: {vid: {bone: w}} 지금 웨이트 (윗단 몸 웨이트를 빌릴 때, 파트 밖 정점만 씀), parent_bone: 몸 정점이 없을 때 쓸 몸 본.
    returns (W {vid: {bone: w}}, info dict)"""
    say = log if log else (lambda *a: None)
    P = np.asarray(P, float)
    part = np.asarray(sorted(set(int(v) for v in part_vids)), dtype=np.int64)
    nv = len(P)
    if lab is None:
        lab = islands(nv, F)
    loc = {int(v): i for i, v in enumerate(part)}
    nloc = len(part)
    inpart = np.zeros(nv, dtype=bool)
    inpart[part] = True
    # 1) 그래프: 파트 안 메쉬 엣지 + 조각 사이 접촉 연결
    E = mesh_edges(F)
    E = E[inpart[E[:, 0]] & inpart[E[:, 1]]]
    adj = [[] for _ in range(nloc)]
    for a, b in E:
        d = float(np.linalg.norm(P[a] - P[b]))
        ia, ib = loc[int(a)], loc[int(b)]
        adj[ia].append((ib, d))
        adj[ib].append((ia, d))
    isl = sorted(set(lab[part].tolist()))
    nlink = {}
    for k in isl:
        A = part[lab[part] == k]
        B = part[lab[part] != k]
        prs = _near_pairs(P, A, B, link_r, link_k)
        nlink[k] = len(prs)
        for a, b, d in prs:
            ia, ib = loc[a], loc[b]
            adj[ia].append((ib, max(d, 1e-3)))
            adj[ib].append((ia, max(d, 1e-3)))
    # 2) 중심축·각도
    J0 = np.array([np.asarray(J, float)[0] for _, J in chains])
    hub = J0.mean(0)
    cx, cy = float(hub[0]), float(hub[1])
    u = angle_deg(P[part], cx, cy)
    uc = []
    for names, J in chains:
        J = np.asarray(J, float)
        m = J[1:].mean(0)
        uc.append(float(math.degrees(math.atan2(m[0] - cx, -(m[1] - cy)))))
    order = np.argsort(uc)
    uc_s = np.array(uc)[order]
    # 3) v: 윗단(체인 시작 줄)에서 측지 거리
    zJ0 = float(J0[:, 2].mean())
    z = P[part, 2]
    ztop = min(zJ0, float(z.max()))
    src = np.where(z >= ztop - 1.0)[0]
    if len(src) == 0:
        src = np.array([int(np.argmax(z))])
    # 윗단 띠(1 단위) 안에서는 맨 위 높이에서 내려온 만큼을 시작 거리로 (띠 안이 전부 0 이면 줄이 1 만큼 들쭉)
    src_d = np.maximum(0.0, ztop - z[src])
    if v_mode == "height":
        v = np.maximum(0.0, ztop - z)          # 높이 기준: 윗단에서 아래로 내려온 높이 → 같은 높이 줄 = 같은 마디
    elif geo_tri:
        floc = [tuple(loc[int(a)] for a in f) for f in F if len(f) == 3 and all(inpart[a] for a in f)]
        v = geodesic(nloc, adj, floc, P[part], src, src_d)
    else:
        v = dijkstra(nloc, adj, src, src_d)
    unreach = ~np.isfinite(v)
    if unreach.any():
        ok = np.where(~unreach)[0]
        for i in np.where(unreach)[0]:
            d = np.linalg.norm(P[part[ok]] - P[part[i]], axis=1)
            j = int(np.argmin(d))
            v[i] = v[ok[j]] + d[j]
    # 4) 체인마다 마디 점의 v → s 1차식 (v = a + b*L, L = 마디까지 체인 길이)
    fits = []
    for ci, (names, J) in enumerate(chains):
        J = np.asarray(J, float)
        L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(J, axis=0), axis=1))])
        vj, Lj = [], []
        for i in range(len(J)):
            d = np.linalg.norm(P[part] - J[i], axis=1)
            j = int(np.argmin(d))
            if d[j] <= JOINT_R:
                vj.append(v[j]); Lj.append(L[i])
        if len(vj) >= 2:
            b, a = np.polyfit(Lj, vj, 1)
            b = max(b, 0.2)
        else:
            a, b = 0.0, 1.0
        fits.append((a, b, L, len(vj)))
        say("  chain %s: u %.0f°, joints on surface %d/%d, v = %.2f + %.3f*L" % (names[0], uc[ci], len(vj), len(J), a, b))

    def s_of(ci, vv):
        a, b, L, _ = fits[ci]
        Lv = (vv - a) / b
        n = len(L) - 1
        # 마디 사이 선형, 바깥은 끝 마디 길이로 외삽
        s = np.interp(Lv, L, np.arange(n + 1))
        lo, hi = Lv < L[0], Lv > L[-1]
        s = np.where(lo, (Lv - L[0]) / max(L[1] - L[0], 1e-6), s)
        s = np.where(hi, n + (Lv - L[-1]) / max(L[-1] - L[-2], 1e-6), s)
        return s
    # 5) 정점마다 이웃 두 체인 + 각도 비례 섞기, s 는 두 체인 값을 같은 비율로 섞음
    nch = len(chains)
    W = {}
    s_all = np.zeros(nloc)
    mix_u = np.zeros((nloc, 2))
    pair = np.zeros((nloc, 2), dtype=int)
    for i in range(nloc):
        ui = u[i]
        if nch == 1:
            ca, cb, t = order[0], order[0], 0.0
        else:
            k = int(np.searchsorted(uc_s, ui))      # uc_s[k-1] <= ui < uc_s[k]
            ia, ib = (k - 1) % nch, k % nch
            ua, ub = uc_s[ia], uc_s[ib]
            span = _wrap(ub - ua) % 360.0 or 360.0
            t = (_wrap(ui - ua) % 360.0) / span
            t = float(np.clip(t, 0.0, 1.0))
            ca, cb = order[ia], order[ib]
        if s_mode == "local":
            sa, sb = float(s_of(ca, np.array([v[i]]))[0]), float(s_of(cb, np.array([v[i]]))[0])
            s = (1 - t) * sa + t * sb
        else:
            s = float(np.mean([s_of(c, np.array([v[i]]))[0] for c in range(nch)]))
        s_all[i] = s
        mix_u[i] = (1 - t, t)
        pair[i] = (ca, cb)
    # 6) 몸 웨이트 (윗단): 파트 밖, 오브젝트 본 없는 가장 가까운 정점
    body_src = None
    if body_w:
        cand = [vi for vi in range(nv) if not inpart[vi] and vi in body_w and body_w[vi]
                and not any(_is_part_bone(n) for n in body_w[vi])]
        cand = np.array(cand, dtype=np.int64)
        if len(cand):
            body_src = cand
    nbody = 0
    nfall = 0
    # 윗단 몸 섞기 'ref' (11-01 정현: 1.72 ref_weights 규칙 그대로): pos = s/마디수, 윗 1/4 정점 pos 의 bip_mixed_top 분위수/0.95
    # (최소 bip_mixed_top*0.25) 까지 부모 몸 본 하나를 pos=0 에서 100% → zb 에서 0 으로 선형
    zb = 0.0
    if top_mode == "ref":
        nb0 = max(len(chains[0][0]), 1)
        pos_all = s_all / nb0
        topq = pos_all[pos_all < 0.25]
        zb = float(np.quantile(topq, min(ref_mixed_top, 0.95)) / 0.95) if (parent_bone and len(topq) and ref_mixed_top > 0) else 0.0
        if parent_bone and ref_mixed_top > 0:
            zb = max(zb, ref_mixed_top * 0.25)
        say("  top 'ref': parent %s, zb = %.4f of chain (= %.2f segs)" % (parent_bone, zb, zb * nb0))
    for i in range(nloc):
        vi = int(part[i])
        s = s_all[i]
        w = {}
        for side in (0, 1):
            cw = mix_u[i, side]
            if cw <= 1e-6:
                continue
            names = chains[pair[i, side]][0]
            for k, x in _along(s, len(names), along_hw).items():
                w[names[k]] = w.get(names[k], 0.0) + cw * x
        if top_mode == "ref":
            if zb > 0 and parent_bone:
                pos = s / max(len(chains[pair[i, 0]][0]), 1)
                if pos < zb:
                    wb = float(np.clip((zb - pos) / zb, 0.0, 1.0))
                    w = {n: x * (1 - wb) for n, x in w.items()}
                    w[parent_bone] = w.get(parent_bone, 0.0) + wb
                    nfall += 1
        elif s < top_blend:
            a = (1.0 if s <= 0 else 1.0 - _smooth(s / top_blend)) * (1.0 - top_chain)
            bw = None
            if body_src is not None:
                d = np.linalg.norm(P[body_src] - P[vi], axis=1)
                j = int(np.argmin(d))
                if d[j] <= body_r:
                    bw = body_w[int(body_src[j])]
                    nbody += 1
            if bw is None and parent_bone:
                bw = {parent_bone: 1.0}
                nfall += 1
            if bw:
                tot = sum(bw.values()) or 1.0
                w = {n: x * (1 - a) for n, x in w.items()}
                for n, x in bw.items():
                    w[n] = w.get(n, 0.0) + a * x / tot
        it = sorted(w.items(), key=lambda kv: -kv[1])[:limit]
        tot = sum(x for _, x in it) or 1.0
        W[vi] = {n: x / tot for n, x in it if x / tot > 1e-4}
    info = dict(hub=hub.tolist(), chain_u=uc, islands=isl, links=nlink, unreach=int(unreach.sum()),
                v_max=float(v.max()), s_min=float(s_all.min()), s_max=float(s_all.max()),
                n_body_blend=nbody, n_parent_fallback=nfall, fits=[(a, b, n) for a, b, _, n in fits],
                u=u, v=v, s=s_all, part=part)
    say("  part verts %d, islands %s, links %s, unreachable %d, v max %.1f, s %.2f~%.2f, top body %d (parent fallback %d)" % (
        nloc, isl, nlink, info["unreach"], info["v_max"], info["s_min"], info["s_max"], nbody, nfall))
    return W, info


INNER_LEN, INNER_HUG, INNER_D = 0.6, 0.6, 2.5


def part_bundle(P, lab, Wd, chain_names, chains, share=0.5, min_isl=5, inner=True, log=None, extra_isl=None):
    """파트 묶음 조각 고르기. Wd = {v: {bone: w}} 지금 웨이트, chain_names = 이 파트 체인 본 이름(set).
    1) 정점 share 이상이 체인 웨이트 > 0.3 인 조각 (겉·안감·띠·장식)
    2) (inner) 코트가 감싸는 안쪽 별도 조각: 바디 조각(가장 큰 조각) 아님 + z 길이 ≥ 체인 길이 INNER_LEN + 정점 INNER_HUG 이상이
       같은 각도·높이의 주 조각 표면에서 반지름 차 INNER_D 안 (11-01 정현: 카미엘 속치마도 코트를 따르게. 다리·바지는 안쪽으로 멀어 빠짐)
    returns (조각 목록, 주 조각, 안쪽 조각 목록)"""
    say = log if log else (lambda *a: None)
    sizes = np.bincount(lab)
    nv = len(lab)
    tot = np.array([sum(x for n, x in Wd.get(v, {}).items() if n in chain_names) for v in range(nv)])
    isl = [k for k in range(len(sizes)) if sizes[k] >= min_isl and np.mean(tot[lab == k] > 0.3) >= share]
    if not isl:
        return [], None, []
    main = max(isl, key=lambda k: sizes[k])
    for k in (extra_isl or []):            # 추천 단계에서 '겹친 조각' 으로 정한 조각 전체
        if int(k) not in isl:
            isl.append(int(k))
    inn = []
    if inner:
        hub = np.mean([np.asarray(J, float)[0] for _, J in chains], axis=0)
        zlo = min(np.asarray(J, float)[-1][2] for _, J in chains)
        zhi = max(np.asarray(J, float)[0][2] for _, J in chains)
        cv = np.where(lab == main)[0]
        u_c = angle_deg(P[cv], hub[0], hub[1]); r_c = np.linalg.norm(P[cv, :2] - hub[:2], axis=1); z_c = P[cv, 2]
        body_isl = int(np.argmax(sizes))
        for k in range(len(sizes)):
            if sizes[k] < 30 or k in isl or k == body_isl:
                continue
            vs = np.where(lab == k)[0]
            z = P[vs, 2]
            if (z.max() - z.min()) < INNER_LEN * (zhi - zlo):
                continue
            if any(_is_part_bone(n) for v in vs for n in Wd.get(int(v), {})):
                continue
            u = angle_deg(P[vs], hub[0], hub[1]); r = np.linalg.norm(P[vs, :2] - hub[:2], axis=1)
            h = 0
            for i in range(len(vs)):
                du = np.abs((u_c - u[i] + 180) % 360 - 180)
                m = (du < 10) & (np.abs(z_c - z[i]) < 2.0)
                if m.any() and abs(r[i] - r_c[m].min()) < INNER_D:
                    h += 1
            if h / len(vs) >= INNER_HUG:
                inn.append(int(k))
                say("  inner island %d: %d v, z %.0f~%.0f, hug %.0f%%" % (k, len(vs), z.min(), z.max(), 100.0 * h / len(vs)))
    return isl + inn, main, inn


def _is_part_bone(n):
    low = n.lower()
    return low.startswith("bone_") and not low.startswith("bone_l ") and not low.startswith("bone_r ") \
        and "_" in low[5:] and any(c.isdigit() for c in low)


def _smooth(x):
    x = min(max(float(x), 0.0), 1.0)
    return x * x * (3 - 2 * x)


def _along(s, nb, hw):
    """마디 k 는 [k, k+1]. 경계(정수) ±hw 에서 선형 섞기, 경계에서 50:50. s<0 → 첫 마디, s>nb → 마지막 마디"""
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
