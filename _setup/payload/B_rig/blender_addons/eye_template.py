# eye_template.py  (Claude, 2026-10-24)
# 눈꺼풀 웨이트 템플릿: 작업자(User)가 다듬은 눈 웨이트를 눈 크기 기준 좌표로 저장해 두고,
# 새 캐릭터 자동 웨이트에서 같은 좌표의 값을 찾아 넣는다.
# 좌표: t = 안쪽 눈꼬리 0 ~ 바깥 눈꼬리 1, s = 눈꺼풀 가장자리(눈 구멍 경계)까지 거리 / 안구 반지름 (위 +, 아래 -),
#       dy = 안구 중심에서 앞쪽 거리 / 안구 반지름
import json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TPL_PATH = os.path.join(HERE, "eye_template_melitta.json")
PARTS = ("up_in", "up", "up_out", "dn_in", "dn", "dn_out")
FW = np.array([1.2, 1.0, 0.5])          # feature scale (t, s, dy)
SIDES = (("L", 1), ("R", -1))


def feats(fc, mesh, L, eyeinfo, side, sg, small=False, eyecols_w=None):
    P = mesh.P
    ce = L.g["Bone_eyeball_%s" % side]
    er = getattr(L, "eye_r", {}).get(side)
    if not er:
        return None
    cap, rim = fc.eye_cap(mesh, ce, er)
    U, D, cxe = eyeinfo[side]
    ri = np.where(rim & (np.abs(P[:, 0] - cxe) < 1.2 * er))[0]
    if len(ri) < 4:
        return None
    u = sg * (P[:, 0] - ce[0]) / er
    a, b = ri[np.argmin(u[ri])], ri[np.argmax(u[ri])]
    ua, ub = u[a], u[b]
    t = (u - ua) / max(ub - ua, 1e-9)
    zl = P[a, 2] + (P[b, 2] - P[a, 2]) * np.clip(t, 0, 1)
    dy = (ce[1] - P[:, 1]) / er
    rel = np.linalg.norm(P - ce, axis=1) / er
    sidem = (sg * (P[:, 0] - ce[0]) > -1.5 * er) & (sg * P[:, 0] > 0)
    if small:   # lashes / small cards near this eye (eyeball pieces excluded by caller)
        region = (~mesh.ismain) & (rel < 2.6) & sidem
        if eyecols_w is not None:
            region &= ~eyecols_w
    else:
        region = mesh.ismain & (rel < 2.6) & (dy > -0.3) & sidem
    idx = np.where(region)[0]
    R = P[ri]
    d = np.sqrt(((P[idx, None, :] - R[None, :, :]) ** 2).sum(-1)).min(1) / er
    s = d * np.where(P[idx, 2] > zl[idx], 1.0, -1.0)
    F = np.stack([t[idx], s, dy[idx]], 1) * FW
    return idx, F, ce, er


def _ballmask(mesh, user_or_W, is_user):
    m = np.zeros(mesh.N, bool)
    for el in mesh.elements():
        if mesh.ismain[el[0]]:
            continue
        if is_user:
            s = sum(user_or_W[v].get("Bone_eyeball_L", 0) + user_or_W[v].get("Bone_eyeball_R", 0) for v in el)
        else:
            s = user_or_W(el)
        if s > 0.5 * len(el):
            m[el] = True
    return m


def build(fc, mesh, L, eyeinfo, user_w, path=TPL_PATH, sides=("L", "R"), note=""):
    """user_w: list of dict(bone -> weight) per vertex (작업자 최종 웨이트)"""
    ball = _ballmask(mesh, user_w, True)
    data = dict(version=2, note=note, fw=FW.tolist())
    for key, small in (("main", False), ("small", True)):
        Fs, Ws = [], []
        for side, sg in SIDES:
            if side not in sides:
                continue
            r = feats(fc, mesh, L, eyeinfo, side, sg, small, ball)
            if r is None:
                continue
            idx, F, ce, er = r
            for k, i in enumerate(idx):
                w = user_w[i]
                Fs.append(F[k].tolist())
                Ws.append([w.get("Bone_eye_%s_%s" % (side, p), 0.0) for p in PARTS])
        data[key] = dict(feat=Fs, lid=Ws)
    Fs = data["main"]["feat"] + data["small"]["feat"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return len(data["main"]["feat"]), len(data["small"]["feat"])


_CACHE = {}


def _load(path):
    m = os.path.getmtime(path)
    c = _CACHE.get(path)
    if c and c[0] == m:
        return c[1]
    d = json.load(open(path, encoding="utf-8"))
    from mathutils.kdtree import KDTree
    out = {}
    for key in ("main", "small"):
        F = np.array(d[key]["feat"]); Wl = np.array(d[key]["lid"])
        if not len(F):
            continue
        kd = KDTree(len(F))
        for i, f in enumerate(F):
            kd.insert(f.tolist(), i)
        kd.balance()
        out[key] = (kd, Wl)
    _CACHE[path] = (m, out)
    return out


def apply(fc, mesh, L, eyeinfo, W, names, path=TPL_PATH, k=6, near=0.12, far=0.35):
    """W: (N, K) weights in compute_weights layout. Returns new W and a log string."""
    if not os.path.exists(path):
        return W, "눈 템플릿 없음"
    T = _load(path)
    bi = {n: i for i, n in enumerate(names)}
    W = W.copy()
    log = []
    head = bi.get("Bip01 Head")
    eyecols = [bi[n] for n in ("Bone_eyeball_L", "Bone_eyeball_R") if n in bi]
    ball = _ballmask(mesh, (lambda el: W[el][:, eyecols].sum()) if eyecols else (lambda el: 0), False)
    for side, sg in SIDES:
        cols = [bi.get("Bone_eye_%s_%s" % (side, p)) for p in PARTS]
        if None in cols:
            log.append("%s: 눈꺼풀 본 없음" % side); continue
        other = [c for c in range(W.shape[1]) if c not in cols]
        for key, small in (("main", False), ("small", True)):
            if key not in T:
                continue
            kd, Wl = T[key]
            r = feats(fc, mesh, L, eyeinfo, side, sg, small, ball)
            if r is None:
                log.append("%s: 눈 구멍 경계 못 찾음" % side); break
            idx, F, ce, er = r
            nchg = 0
            for kk, i in enumerate(idx):
                hits = kd.find_n(F[kk].tolist(), k)
                if not hits:
                    continue
                dmin = hits[0][2]
                al = 1.0 if dmin <= near else max(0.0, 1.0 - (dmin - near) / (far - near))
                if al <= 0:
                    continue
                ws = np.array([1.0 / (h[2] ** 2 + 1e-6) for h in hits])
                tpl = (Wl[[h[1] for h in hits]] * ws[:, None]).sum(0) / ws.sum()
                new = np.clip(al * tpl + (1 - al) * W[i, cols], 0, 1)
                if new.sum() > 1:
                    new /= new.sum()
                rest = W[i, other]; rs = rest.sum()
                W[i, cols] = new
                remain = 1.0 - new.sum()
                if rs > 1e-9:
                    W[i, other] = rest / rs * remain
                elif head is not None:
                    W[i, head] += remain
                nchg += 1
            log.append("%s %s %d" % (side, "피부" if key == "main" else "작은조각", nchg))
    return W, " | ".join(log)
