bl_info = {
    "name": "Max Style Rig (Max 유저용 리깅·웨이팅)",
    "author": "Claude for 애니팀",
    "version": (1, 8, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > Max 리깅",
    "description": "3ds Max 사용자용: Max식 단축키, Skin Weight Tool식 웨이트 보정, Max Skin으로 웨이트 보내기",
    "category": "Rigging",
}

import bpy
import bmesh
import json
import os
import re
from mathutils import Vector, kdtree

TAB = "Max 리깅"


# ============================================================ facerig core (numpy only, embedded)
import types as _types
_FC_SRC = r'''# -*- coding: utf-8 -*-
"""
facerig_core.py  -  numpy-only facial auto-rig core (no scipy)
Coordinates: 3ds Max world (Z up, face looks toward -Y).
Input : mesh verts P (N,3), tris T (M,3), guide bone positions (dict name->xyz)
Output: detailed bone layout + skin weights (N, nbones)
"""
import numpy as np
import heapq
from collections import defaultdict

SIDES = (('L', 1), ('R', -1))


# ---------------------------------------------------------------- mesh utils
class Mesh:
    def __init__(self, P, T):
        self.P = np.asarray(P, float)
        self.T = np.asarray(T, int)
        N = len(self.P)
        self.N = N
        e = np.vstack([self.T[:, [0, 1]], self.T[:, [1, 2]], self.T[:, [2, 0]]])
        e.sort(1)
        ue, cnt = np.unique(e, axis=0, return_counts=True)
        self.E = ue
        self.boundary = np.zeros(N, bool)
        self.boundary[ue[cnt == 1].ravel()] = True
        nb = [[] for _ in range(N)]
        for a, b in ue:
            nb[a].append(b); nb[b].append(a)
        self.nb = nb
        # elements (union-find)
        par = np.arange(N)

        def f(x):
            while par[x] != x:
                par[x] = par[par[x]]; x = par[x]
            return x
        for a, b in ue:
            ra, rb = f(a), f(b)
            if ra != rb: par[rb] = ra
        self.root = np.array([f(i) for i in range(N)])
        vals, cnts = np.unique(self.root, return_counts=True)
        self.main_root = vals[np.argmax(cnts)]
        self.ismain = self.root == self.main_root

    def elements(self):
        out = defaultdict(list)
        for i, r in enumerate(self.root): out[r].append(i)
        return [np.array(v) for v in out.values()]

    def nearest(self, c, mask=None):
        d = np.linalg.norm(self.P - c, axis=1)
        if mask is not None: d[~mask] = 1e18
        return int(np.argmin(d))

    def bfs(self, start, ok):
        R = np.zeros(self.N, bool)
        if not ok[start]: return R
        st = [start]
        while st:
            i = st.pop()
            if R[i] or not ok[i]: continue
            R[i] = True
            st.extend(self.nb[i])
        return R

    def harmonic(self, seed1, seed0, iters=4000, tol=1e-7):
        """Laplace solve with Dirichlet seeds on main element, conjugate gradient (numpy only)."""
        P, E = self.P, self.E
        l = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1)
        w = 1.0 / (l + 1e-3 * max(l.mean(), 1e-12))
        N = self.N
        deg = np.zeros(N); np.add.at(deg, E[:, 0], w); np.add.at(deg, E[:, 1], w)
        fixed = seed1 | seed0 | (~self.ismain)
        val = np.zeros(N); val[seed1] = 1.0
        free = ~fixed

        def Lmul(x):  # full Laplacian times x
            y = deg * x
            np.add.at(y, E[:, 0], -w * x[E[:, 1]])
            np.add.at(y, E[:, 1], -w * x[E[:, 0]])
            return y
        # A x_free = -L_free,fixed * val_fixed
        xf = np.where(fixed, val, 0.0)
        b = -Lmul(xf)
        b[fixed] = 0
        x = np.full(N, 0.5); x[fixed] = 0
        # warm start: nearest-seed guess
        r = b - (Lmul(x) * free)
        r[fixed] = 0
        p = r.copy(); rs = r @ r
        b2 = max(b @ b, 1e-30)
        for _ in range(iters):
            Ap = Lmul(p); Ap[fixed] = 0
            a = rs / max(p @ Ap, 1e-30)
            x += a * p; r -= a * Ap
            rn = r @ r
            if rn / b2 < tol * tol: break
            p = r + (rn / rs) * p; rs = rn
        out = val.copy(); out[free] = x[free]
        return np.clip(out, 0, 1)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def gauss(P, c, rx, ry, rz):
    d = P - np.asarray(c)
    return np.exp(-((d[:, 0] / rx) ** 2 + (d[:, 1] / ry) ** 2 + (d[:, 2] / rz) ** 2))


def hat_partition(x, xs):
    """piecewise-linear partition of unity over sorted knot list xs; returns (len(x), len(xs))."""
    xs = np.asarray(xs, float)
    o = np.argsort(xs); k = xs[o]
    W = np.zeros((len(x), len(k)))
    xc = np.clip(x, k[0], k[-1])
    j = np.clip(np.searchsorted(k, xc) - 1, 0, len(k) - 2)
    t = (xc - k[j]) / np.maximum(k[j + 1] - k[j], 1e-9)
    W[np.arange(len(x)), j] = 1 - t
    W[np.arange(len(x)), j + 1] += t
    out = np.zeros_like(W); out[:, o] = W
    return out


# ---------------------------------------------------------------- landmarks
class Landmarks:
    """Everything derived from the guide bones (legacy 22-bone layout or user-placed guides)."""

    def __init__(self, g):
        self.g = {k: np.asarray(v, float) for k, v in g.items()}
        G = self.g
        self.cw = abs(G['Bone_lip_L'][0] - G['Bone_lip_R'][0]) / 2          # mouth half width
        self.s = self.cw / 1.82                                             # mouth scale (1 = Melitta)
        self.se = abs(G['Bone_eyeball_L'][0] - G['Bone_eyeball_R'][0]) / 2 / 2.55
        self.lipup = G['Bone_lip_up']; self.lipdn = G['Bone_lip_dn']
        self.jaw = G['Bone_jaw']; self.head = G['Bip01 Head']


# ---------------------------------------------------------------- bone layout
def snap_inset(mesh, c, inset, mask=None, rad=0.25, sc=1.0):
    rad = rad * sc
    """move point c to (front-most surface vertex near c in x/z) + inset along +y."""
    P = mesh.P
    m = mesh.ismain.copy() if mask is None else mask.copy()
    d = np.hypot(P[:, 0] - c[0], P[:, 2] - c[2])
    cand = m & (d < rad)
    if not cand.any():
        cand = m & (d < rad * 3)
    i = np.where(cand)[0][np.argmin(P[cand, 1])]
    return np.array([c[0], P[i, 1] + inset, c[2]])


def surf_inset(mesh, c, sc=1.0):
    P = mesh.P
    d = np.hypot(P[:, 0] - c[0], P[:, 2] - c[2])
    m = mesh.ismain & (d < 0.3 * sc)
    if not m.any(): return 0.25 * sc
    return c[1] - P[m, 1].min()


def build_layout(mesh, L):
    """returns ordered dict name -> dict(head, tail, parent, kind)"""
    G, s, se, cw = L.g, L.s, L.se, L.cw
    B = {}

    def add(n, head, tail=None, parent='Bip01 Head', kind='pt'):
        head = np.asarray(head, float)
        if tail is None: tail = head + np.array([0, -0.3 * s, 0])
        B[n] = dict(head=head, tail=np.asarray(tail, float), parent=parent, kind=kind)

    # jaw (keep guide pivot, tip toward chin)
    chin_c = np.array([0, 0, L.lipdn[2] - 1.6 * s])
    chin = snap_inset(mesh, chin_c, 0.3 * s, sc=s)
    add('Bone_jaw', L.jaw, chin, 'Bip01 Head', 'jaw')
    add('Bone_chin', chin, None, 'Bone_jaw')
    # ---- lips
    for side, sg in SIDES:
        cor = G[f'Bone_lip_{side}']
        up_in = G[f'Bone_lip_{side}_up']; dn_in = G[f'Bone_lip_{side}_dn']
        add(f'Bone_lip_{side}', cor)
        add(f'Bone_lip_{side}_up', up_in)
        t = (0.80 * cw - abs(up_in[0])) / (cw - abs(up_in[0]))
        add(f'Bone_lip_{side}_up_out', up_in + (cor - up_in) * t)
        add(f'Bone_lip_{side}_dn', dn_in, None, 'Bone_jaw')
        add(f'Bone_lip_{side}_dn_out', dn_in + (cor - dn_in) * t, None, 'Bone_jaw')
    add('Bone_lip_up', L.lipup)
    add('Bone_lip_dn', L.lipdn, None, 'Bone_jaw')
    # ---- nose / sneer / cheeks
    for side, sg in SIDES:
        add(f'Bone_nose_{side}', snap_inset(mesh, [sg * 0.42 * cw, 0, L.lipup[2] + 1.45 * s], 0.2 * s, sc=s))
        add(f'Bone_sneer_{side}', snap_inset(mesh, [sg * 0.58 * cw, 0, L.lipup[2] + 2.6 * s], 0.25 * s, sc=s))
        ck = G[f'Bone_cheek_{side}']
        add(f'Bone_cheek_{side}', ck)
        ins = surf_inset(mesh, ck, s)
        add(f'Bone_cheek_{side}_dn', snap_inset(mesh, [ck[0] * 1.12, 0, ck[2] - 1.5 * s], ins, rad=0.4, sc=s))
    # ---- brows
    for side, sg in SIDES:
        bi, bo = G[f'Bone_brow_{side}_in'], G[f'Bone_brow_{side}_out']
        mid = (bi + bo) / 2
        ins = (surf_inset(mesh, bi, s) + surf_inset(mesh, bo, s)) / 2
        mid = snap_inset(mesh, [mid[0], 0, mid[2] + 0.15 * se], ins, sc=s)
        add(f'Bone_brow_{side}_in', bi); add(f'Bone_brow_{side}_mid', mid); add(f'Bone_brow_{side}_out', bo)
    # ---- eyes (lids pivot at eyeball centre, tail at lid edge)
    eyeinfo = {}
    for side, sg in SIDES:
        ce = G[f'Bone_eyeball_{side}']
        er0 = getattr(L, 'eye_r', {}).get(side)
        # eyeball bone length follows the eyeball size (Melitta original: 2.116 / eyeball radius 1.80 = 1.176)
        eb_len = 1.176 * er0 if er0 else 0.6 * se
        add(f'Bone_eyeball_{side}', ce, ce + np.array([0, -eb_len, 0]), kind='eye')
        U, D, cxe = eyelid_regions(mesh, L, side, sg)
        eyeinfo[side] = (U, D, cxe)
        er = getattr(L, 'eye_r', {}).get(side)
        w = 0.75 * er if er else se
        for part, R, pick in (('up', U, np.argmin), ('dn', D, np.argmax)):
            for suf, off in (('_in', -0.55), ('', 0.0), ('_out', 0.55)):
                tx = cxe + sg * off * w
                m = R & (np.abs(mesh.P[:, 0] - tx) < 0.18 * w)
                if not m.any(): m = R & (np.abs(mesh.P[:, 0] - tx) < 0.4 * w)
                idx = np.where(m)[0]
                tip = mesh.P[idx[pick(mesh.P[idx, 2])]]
                add(f'Bone_eye_{side}_{part}{suf}', ce, tip, kind='lid')
    # ---- tongue placeholder (filled by teeth analysis if available)
    return B, eyeinfo


def eye_cap(mesh, ce, er):
    """faces that close the eye hole sit inside the eyeball sphere in front.
    returns (cap verts: all faces inside, rim verts: lid edge where skin meets the cap / open hole edge)"""
    P, T = mesh.P, mesh.T
    C = P[T].mean(1) - ce
    inside = (np.linalg.norm(C, axis=1) < 1.02 * er) & (-C[:, 1] > 0.2 * er)
    cnt = np.zeros(mesh.N); cin = np.zeros(mesh.N)
    np.add.at(cnt, T.ravel(), 1); np.add.at(cin, T[inside].ravel(), 1)
    cap = mesh.ismain & (cnt > 0) & (cin == cnt)
    rim = mesh.ismain & (cin > 0) & (cin < cnt)
    if not rim.any():   # open eye hole: its boundary edge is the rim
        rim = mesh.boundary & mesh.ismain & (np.linalg.norm(P - ce, axis=1) < 1.4 * er) & (P[:, 1] < ce[1])
    return cap, rim


def eyelid_regions(mesh, L, side, sg):
    G, se = L.g, L.se
    ce = G[f'Bone_eyeball_{side}']
    P = mesh.P
    er = getattr(L, 'eye_r', {}).get(side)
    if er:  # measured eyeball (ce = true centre): region sized by the eyeball radius
        cxe = ce[0] + sg * 0.1 * er
        hw = 1.0 * er
        ok = mesh.ismain & (np.abs(P[:, 0] - cxe) < hw) & (P[:, 1] < ce[1] - 0.5 * er) & \
            (P[:, 2] > ce[2] - 1.1 * er) & (P[:, 2] < ce[2] + 1.3 * er)
        cap, rim = eye_cap(mesh, ce, er)
        ok &= ~cap                     # faces filling the eye hole would join the upper and lower lid
        gu = G.get(f'Bone_eye_{side}_up', ce + [0, -0.95 * er, 0.3 * er])
        gd = G.get(f'Bone_eye_{side}_dn', ce + [0, -0.95 * er, -0.3 * er])
        # upper / lower lid split by the line through the two eye corners (lids meet there)
        zl = np.full(len(P), ce[2])
        ri = np.where(rim & (np.abs(P[:, 0] - cxe) < 1.2 * er))[0]
        if len(ri) >= 4:
            a, b = ri[np.argmin(P[ri, 0])], ri[np.argmax(P[ri, 0])]
            t = np.clip((P[:, 0] - P[a, 0]) / max(P[b, 0] - P[a, 0], 1e-9), 0, 1)
            zl = P[a, 2] + (P[b, 2] - P[a, 2]) * t
        oku, okd = ok & (P[:, 2] > zl), ok & (P[:, 2] <= zl)
        U = mesh.bfs(mesh.nearest(gu, oku), oku)
        D = mesh.bfs(mesh.nearest(gd, okd), okd)
        return U, D, cxe
    else:
        cxe = ce[0] + sg * 0.25 * se
        hw = 0.85 * se
        ok = mesh.ismain & (np.abs(P[:, 0] - cxe) < hw) & (P[:, 1] < ce[1] - 0.54 * se) & \
            (P[:, 2] > ce[2] - 1.2 * se) & (P[:, 2] < ce[2] + 1.5 * se)
        gu = G.get(f'Bone_eye_{side}_up', ce + [0, -1.35 * se, 0.6 * se])
        gd = G.get(f'Bone_eye_{side}_dn', ce + [0, -0.75 * se, -0.52 * se])
    U = mesh.bfs(mesh.nearest(gu, ok), ok)
    D = mesh.bfs(mesh.nearest(gd, ok), ok)
    if (U & D).any():  # connected through corners -> shrink
        ok2 = ok & (np.abs(P[:, 0] - cxe) < 0.82 * hw)
        U = mesh.bfs(mesh.nearest(gu, ok2), ok2); D = mesh.bfs(mesh.nearest(gd, ok2), ok2)
    return U, D, cxe


# ---------------------------------------------------------------- weights
def mouth_regions(mesh, L):
    P = mesh.P; s, cw = L.s, L.cw
    x, y, z = P.T
    zl = (L.lipup[2] + L.lipdn[2]) / 2
    yfront = P[mesh.nearest(L.lipup, mesh.ismain), 1]
    ok = mesh.ismain & (np.abs(x) < 0.88 * cw) & (z > L.lipdn[2] - 1.15 * s) & (z < L.lipup[2] + 1.1 * s) & \
        (y < yfront + 2.3 * s)
    UPF = mesh.bfs(mesh.nearest(L.lipup, ok), ok)
    LOWF = mesh.bfs(mesh.nearest(L.lipdn, ok), ok)
    if (UPF & LOWF).any():
        raise RuntimeError('upper/lower lip not separated: is the mouth slit open in the mesh?')
    okb = mesh.ismain & (y > yfront + 0.88 * s) & (np.abs(x) < 0.96 * cw) & (z > zl - 1.3 * s) & (z < zl + 1.3 * s)
    start = mesh.nearest(np.array([0, yfront + 1.43 * s, zl]), okb)
    BAG = mesh.bfs(start, okb)
    return UPF, LOWF, BAG, zl, yfront


def jaw_field(mesh, L, UPF, LOWF, BAG, zl, yfront):
    P = mesh.P; s, cw = L.s, L.cw
    x, y, z = P.T; ax = np.abs(x)
    m = mesh.ismain
    jy = L.jaw[1]
    s1 = m & (((z < L.lipdn[2] - 1.45 * s) & (y < jy - 0.9 * s) & (ax < 1.65 * cw)))
    s0 = m & ((z > L.lipup[2] + 1.8 * s) | (y > jy + 2.1 * s) | ((z > L.lipup[2] + 0.7 * s) & (ax > 2.5 * cw)))
    neck = mesh.boundary & m & (z < L.lipup[2] + 1.0 * s) & (y > 0 + jy - 2.43 * s)
    s1 |= neck & (y < jy + 0.77 * s)
    s0 |= neck & (y > jy + 2.57 * s)
    s1 |= LOWF | (BAG & (z < zl - 0.5 * s))
    s0 = (s0 | UPF | (BAG & (z > zl + 0.2 * s))) & ~s1
    jaw = mesh.harmonic(s1, s0)
    # round mouth corners
    cL, cR = L.g['Bone_lip_L'], L.g['Bone_lip_R']
    dc = np.minimum(np.linalg.norm(P - cL, axis=1), np.linalg.norm(P - cR, axis=1))
    cf = np.exp(-(dc / (0.85 * s)) ** 2)
    J = np.clip(0.5 + (jaw - 0.5) * (1 - 0.75 * cf), 0, 1)
    # soften the crease around the corners: a few neighbour-average passes inside the corner zone
    zone = (dc < 1.3 * s) & mesh.ismain
    E = mesh.E
    for _ in range(8):
        acc = np.zeros(mesh.N); cnt = np.zeros(mesh.N)
        np.add.at(acc, E[:, 0], J[E[:, 1]]); np.add.at(acc, E[:, 1], J[E[:, 0]])
        np.add.at(cnt, E[:, 0], 1); np.add.at(cnt, E[:, 1], 1)
        avg = acc / np.maximum(cnt, 1)
        t = 0.5 * np.exp(-(dc / (1.0 * s)) ** 2)
        J = np.where(zone, J * (1 - t) + avg * t, J)
    return np.clip(J, 0, 1)


def compute_weights(mesh, L, B, eyeinfo):
    P = mesh.P; N = mesh.N; s, se, cw = L.s, L.se, L.cw
    x, y, z = P.T; ax = np.abs(x)
    names = list(B.keys())
    if 'Bip01 Head' not in names: names = ['Bip01 Head'] + names
    bi = {n: i for i, n in enumerate(names)}
    pos = {n: B[n]['head'] for n in B}
    UPF, LOWF, BAG, zl, yfront = mouth_regions(mesh, L)
    J = jaw_field(mesh, L, UPF, LOWF, BAG, zl, yfront)
    H = 1 - J
    HG, JG = {}, {}
    lidmask = np.zeros(N)
    # ---- eyelids (rotation pivot = eyeball centre)
    for side, sg in SIDES:
        U, D, cxe = eyeinfo[side]
        Dn = D
        ce = L.g[f'Bone_eyeball_{side}']
        er = getattr(L, 'eye_r', {}).get(side)
        if er:  # measured eyeball: distances in eyeball radii from the true centre (independent of eye size)
            de = np.linalg.norm((P - ce) * [0.85, 1, 1], axis=1) / er
            reg = mesh.ismain & (de < 1.9)
            lidu = (1 - smoothstep(1.2, 1.75, de)) * mesh.ismain
            lidd = (1 - smoothstep(1.1, 1.5, de)) * mesh.ismain
        else:
            de = np.linalg.norm((P - ce) * [0.85, 1, 1], axis=1) / se
            reg = mesh.ismain & (de < 2.4)
            lidu = (1 - smoothstep(1.15, 1.8, de)) * mesh.ismain
            lidd = (1 - smoothstep(0.95, 1.45, de)) * mesh.ismain
        s1 = U | (mesh.ismain & ~reg & (z > ce[2]))
        s0 = D | (mesh.ismain & ~reg & (z <= ce[2]))
        u = mesh.harmonic(s1 & ~s0, s0)
        lidmask = np.maximum(lidmask, np.maximum(lidu * u, lidd * (1 - u)))
        for part, amt in (('up', lidu * u * 1.0), ('dn', lidd * (1 - u) * 0.85)):
            ns = [f'Bone_eye_{side}_{part}_in', f'Bone_eye_{side}_{part}', f'Bone_eye_{side}_{part}_out']
            xs = [B[n]['tail'][0] for n in ns]
            hp = hat_partition(x, xs)
            for k, n in enumerate(ns): HG[n] = amt * hp[:, k]
    nolid = 1 - lidmask
    # ---- brows
    for side, sg in SIDES:
        ns = [f'Bone_brow_{side}_in', f'Bone_brow_{side}_mid', f'Bone_brow_{side}_out']
        ps = np.array([pos[n] for n in ns])
        xs = ps[:, 0]
        hp = hat_partition(x, xs)
        zb = hp @ ps[:, 2]
        xin, xout = min(abs(xs[0]), abs(xs[2])), max(abs(xs[0]), abs(xs[2]))
        xfall = (1 - smoothstep(xout, xout + 1.1 * se, ax)) * (1 - smoothstep(xin, xin - 1.0 * se, ax) * (ax < xin)) \
            * (np.sign(x) == sg)
        dzb = z - zb
        band = np.exp(-(np.maximum(dzb, 0) / (1.25 * se)) ** 2) * np.exp(-(np.minimum(dzb, 0) / (0.7 * se)) ** 2) \
            * (y < L.g[f'Bone_eyeball_{side}'][1]) * mesh.ismain
        amt = band * xfall * 1.0 * nolid
        for k, n in enumerate(ns): HG[n] = amt * hp[:, k]
    # ---- cheeks / nose / sneer
    for side, sg in SIDES:
        HG[f'Bone_cheek_{side}'] = gauss(P, pos[f'Bone_cheek_{side}'], 1.2 * s, 1.8 * s, 1.0 * s) * 0.75 * nolid
        HG[f'Bone_cheek_{side}_dn'] = gauss(P, pos[f'Bone_cheek_{side}_dn'], 1.1 * s, 1.8 * s, 1.0 * s) * 0.7 * nolid
        HG[f'Bone_nose_{side}'] = gauss(P, pos[f'Bone_nose_{side}'], 0.45 * s, 0.9 * s, 0.45 * s) * 0.8
        HG[f'Bone_sneer_{side}'] = gauss(P, pos[f'Bone_sneer_{side}'], 0.5 * s, 0.9 * s, 0.6 * s) * 0.7 * nolid
    # ---- lips (partition of unity in x, band around lip line)
    up_ns = ['Bone_lip_R', 'Bone_lip_R_up_out', 'Bone_lip_R_up', 'Bone_lip_up', 'Bone_lip_L_up', 'Bone_lip_L_up_out', 'Bone_lip_L']
    dn_ns = ['Bone_lip_R_dn_out', 'Bone_lip_R_dn', 'Bone_lip_dn', 'Bone_lip_L_dn', 'Bone_lip_L_dn_out']
    lipfront = y < yfront + 2.6 * s
    for ns, side_amt, sign in ((up_ns, H, +1), (dn_ns, J, -1)):
        ps = np.array([pos[n] for n in ns])
        hp = hat_partition(x, ps[:, 0])
        zline = hp @ ps[:, 2]
        dz = (z - zline) * sign
        band = np.exp(-(np.maximum(dz, 0) / (0.55 * s)) ** 2) * np.exp(-(np.minimum(dz, 0) / (0.35 * s)) ** 2)
        xf = 1 - smoothstep(cw, cw + 0.7 * s, ax)
        amt = band * xf * lipfront * mesh.ismain * 0.9
        tgt = HG if sign > 0 else JG
        for k, n in enumerate(ns):
            tgt[n] = tgt.get(n, 0) + amt * hp[:, k]
    # corners spill into cheek a little (head side)
    for side, sg in SIDES:
        HG[f'Bone_lip_{side}'] = np.maximum(HG[f'Bone_lip_{side}'],
                                           gauss(P, pos[f'Bone_lip_{side}'], 0.55 * s, 1.2 * s, 0.6 * s) * 0.9)
    JG['Bone_chin'] = gauss(P, pos['Bone_chin'], 0.9 * s, 1.5 * s, 0.7 * s) * 0.7 * (1 - sum(JG.values()))
    # ---- allocate
    W = np.zeros((N, len(names)))

    def alloc(Gd, total):
        S = sum(Gd.values()); sc = np.where(S > 1, 1 / np.maximum(S, 1e-9), 1)
        used = np.zeros(N)
        for n, g in Gd.items():
            w = g * sc * total; W[:, bi[n]] += w; used += w
        return total - used
    W[:, bi['Bip01 Head']] += alloc(HG, H)
    W[:, bi['Bone_jaw']] += alloc(JG, J)
    # ---- non-main elements (eyeballs, lashes)
    lash = []
    for el in mesh.elements():
        if mesh.ismain[el[0]]: continue
        c = P[el].mean(0); side = 'L' if c[0] > 0 else 'R'
        ce = L.g[f'Bone_eyeball_{side}']
        W[el] = 0
        er_ = getattr(L, 'eye_r', {}).get(side)
        rr = np.linalg.norm(P[el] - ce, axis=1) / er_ if er_ else None
        # eyeball pieces (split cap / iris) sit on the eyeball sphere; lashes stick out past it
        on_ball = rr is not None and len(el) >= 12 and rr.max() < 1.1 and abs(rr.mean() - 1) < 0.08
        if (len(el) > 100 and np.linalg.norm(c - ce) < 1.0 * se) or on_ball:
            W[el, bi[f'Bone_eyeball_{side}']] = 1
        else:
            lash.append(el)
    # lashes / small cards: copy the weights of the nearest lid skin so they stay attached
    if lash:
        mi = np.where(mesh.ismain)[0]
        for el in lash:
            for i in el:
                d = np.einsum('ij,ij->i', P[mi] - P[i], P[mi] - P[i])
                W[i] = W[mi[np.argmin(d)]]
    return finalize(W), names, dict(J=J, UPF=UPF, LOWF=LOWF, BAG=BAG)


def finalize(W, maxinf=4, thr=0.01):
    W = W.copy()
    W[W < thr] = 0
    o = np.argsort(-W, axis=1)
    rows = np.arange(len(W))[:, None]
    W[rows, o[:, maxinf:]] = 0
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    return W


# ---------------------------------------------------------------- teeth / tongue
def teeth_tongue(Pt, Tt, L, B):
    """classify teeth-object elements: upper teeth->Head, lower teeth->jaw, tongue->tongue chain.
    adds tongue bones to B. returns weights (n, names) dict-of-arrays"""
    m = Mesh(Pt, Tt)
    els = m.elements()
    zl = (L.lipup[2] + L.lipdn[2]) / 2
    info = []
    for el in els:
        c = Pt[el].mean(0); info.append((el, c))
    # tongue = element whose centroid is furthest back (largest y) among those near mouth line
    cand = sorted(info, key=lambda t: -t[1][1])
    tongue = None
    if len(info) >= 3:
        tongue = cand[0][0]
    res = {}
    if tongue is not None:
        tp = Pt[tongue]
        yb, yf = tp[:, 1].max(), tp[:, 1].min()
        zc = np.median(tp[:, 2])
        j = [np.array([0, yb - (yb - yf) * f, zc]) for f in (0.15, 0.5, 0.8)]
        tip = np.array([0, yf, zc])
        B['Bone_tongue_1'] = dict(head=j[0], tail=j[1], parent='Bone_jaw', kind='chain')
        B['Bone_tongue_2'] = dict(head=j[1], tail=j[2], parent='Bone_tongue_1', kind='chain')
        B['Bone_tongue_3'] = dict(head=j[2], tail=tip, parent='Bone_tongue_2', kind='chain')
        hp = hat_partition(-tp[:, 1], [-j[0][1], -j[1][1], -j[2][1]])
        for k in range(3):
            res.setdefault(f'Bone_tongue_{k+1}', np.zeros(len(Pt)))[tongue] = hp[:, k]
    for el, c in info:
        if tongue is not None and el is tongue: continue
        n = 'Bip01 Head' if c[2] > zl + 0.3 * L.s else 'Bone_jaw'
        res.setdefault(n, np.zeros(len(Pt)))[el] = 1
    return res
'''
fc = _types.ModuleType("msr_facerig_core")
exec(compile(_FC_SRC, "msr_facerig_core", "exec"), fc.__dict__)


# ============================================================ helpers
def mesh_obj(context):
    o = context.active_object
    return o if o and o.type == "MESH" else None


def armature_of(obj):
    for m in obj.modifiers:
        if m.type == "ARMATURE" and m.object:
            return m.object
    if obj.parent and obj.parent.type == "ARMATURE":
        return obj.parent
    return None


def deform_group_indices(obj):
    """Vertex-group indices that belong to deform bones (all groups if no armature)."""
    arm = armature_of(obj)
    if not arm:
        return {g.index for g in obj.vertex_groups}
    names = {b.name for b in arm.data.bones if b.use_deform}
    return {g.index for g in obj.vertex_groups if g.name in names}


def vweights(v, deform):
    return {g.group: g.weight for g in v.groups if g.group in deform and g.weight > 0.0}


def write_weights(obj, vi, new, deform):
    """Replace deform weights of vertex vi with dict {group_index: weight}."""
    v = obj.data.vertices[vi]
    for gi in [g.group for g in v.groups if g.group in deform and g.group not in new]:
        obj.vertex_groups[gi].remove([vi])
    for gi, w in new.items():
        obj.vertex_groups[gi].add([vi], max(0.0, min(1.0, w)), "REPLACE")


def normalize(d):
    s = sum(d.values())
    if s <= 1e-9:
        return d
    return {k: w / s for k, w in d.items()}


def flip_name(n):
    def sw(m):
        return {"L": "R", "R": "L", "l": "r", "r": "l"}[m.group(0)]
    return re.sub(r"(?<![A-Za-z0-9])[LRlr](?![A-Za-z0-9])", sw, n)


class DataMode:
    """Edit Mode keeps vertex data in a bmesh; switch to Object Mode while we touch weights."""
    def __init__(self, context):
        self.context = context
        self.was_edit = context.mode == "EDIT_MESH"
        self.active_vi = None

    def __enter__(self):
        obj = self.context.active_object
        if self.was_edit:
            bm = bmesh.from_edit_mesh(obj.data)
            act = bm.select_history.active
            if isinstance(act, bmesh.types.BMVert):
                self.active_vi = act.index
            bpy.ops.object.mode_set(mode="OBJECT")
        return self

    def __exit__(self, *a):
        obj = self.context.active_object
        obj.data.update()
        if self.was_edit:
            bpy.ops.object.mode_set(mode="EDIT")
        return False


def selected_indices(obj):
    return [v.index for v in obj.data.vertices if v.select]


def ref_vertex(obj, dm):
    if dm.active_vi is not None and obj.data.vertices[dm.active_vi].select:
        return dm.active_vi
    sel = selected_indices(obj)
    return sel[0] if sel else None


def tag_redraw(context):
    for a in context.screen.areas:
        if a.type in ("VIEW_3D", "PROPERTIES"):
            a.tag_redraw()


class WeightOpBase:
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        o = mesh_obj(context)
        return o is not None and context.mode in ("EDIT_MESH", "PAINT_WEIGHT", "OBJECT")


# ============================================================ weight tool operators
class MSR_OT_set_weight(WeightOpBase, bpy.types.Operator):
    """선택한 정점의 현재 본 웨이트를 지정 (나머지 본은 합이 1이 되도록 자동 조정)"""
    bl_idname = "msr.set_weight"
    bl_label = "웨이트 지정"
    value: bpy.props.FloatProperty(default=1.0, min=0.0, max=1.0)
    delta: bpy.props.FloatProperty(default=0.0)
    scale: bpy.props.FloatProperty(default=0.0)

    def execute(self, context):
        obj = mesh_obj(context)
        g = obj.vertex_groups.active
        if g is None:
            self.report({"WARNING"}, "본(정점 그룹)을 먼저 고르세요")
            return {"CANCELLED"}
        with DataMode(context):
            deform = deform_group_indices(obj) | {g.index}
            sel = selected_indices(obj)
            if not sel:
                self.report({"WARNING"}, "정점을 먼저 선택하세요")
                return {"CANCELLED"}
            stuck = 0
            for vi in sel:
                d = vweights(obj.data.vertices[vi], deform)
                cur = d.get(g.index, 0.0)
                if self.delta:
                    w = cur + self.delta
                elif self.scale:
                    w = cur * self.scale
                else:
                    w = self.value
                w = max(0.0, min(1.0, w))
                others = {k: x for k, x in d.items() if k != g.index}
                s = sum(others.values())
                if s <= 1e-9:
                    if w < 1.0:
                        stuck += 1
                    new = {g.index: 1.0}
                else:
                    new = {k: x * (1.0 - w) / s for k, x in others.items()}
                    if w > 0.0:
                        new[g.index] = w
                write_weights(obj, vi, new, deform)
        if stuck:
            self.report({"INFO"}, "정점 %d개는 다른 본 영향이 없어 1.0으로 유지됐어요" % stuck)
        tag_redraw(context)
        return {"FINISHED"}


class MSR_OT_blend(WeightOpBase, bpy.types.Operator):
    """Max Weight Tool의 Blend: 선택 정점 웨이트를 이웃 정점과 섞어서 부드럽게"""
    bl_idname = "msr.blend"
    bl_label = "Blend"

    def execute(self, context):
        obj = mesh_obj(context)
        with DataMode(context):
            me = obj.data
            deform = deform_group_indices(obj)
            sel = set(selected_indices(obj))
            if not sel:
                self.report({"WARNING"}, "정점을 먼저 선택하세요")
                return {"CANCELLED"}
            nb = {i: [] for i in sel}
            for e in me.edges:
                a, b = e.vertices
                if a in nb:
                    nb[a].append(b)
                if b in nb:
                    nb[b].append(a)
            snap = {}
            for vi in sel | {n for l in nb.values() for n in l}:
                snap[vi] = vweights(me.vertices[vi], deform)
            for vi in sel:
                acc = {}
                ring = [vi] + nb[vi]
                for j in ring:
                    for k, w in snap[j].items():
                        acc[k] = acc.get(k, 0.0) + w
                new = normalize({k: w / len(ring) for k, w in acc.items() if w / len(ring) > 1e-4})
                if new:
                    write_weights(obj, vi, new, deform)
        tag_redraw(context)
        return {"FINISHED"}


class MSR_OT_copy(WeightOpBase, bpy.types.Operator):
    """기준 정점(마지막 선택 또는 첫 선택)의 웨이트 복사"""
    bl_idname = "msr.copy"
    bl_label = "Copy"

    def execute(self, context):
        obj = mesh_obj(context)
        with DataMode(context) as dm:
            vi = ref_vertex(obj, dm)
            if vi is None:
                self.report({"WARNING"}, "정점을 먼저 선택하세요")
                return {"CANCELLED"}
            deform = deform_group_indices(obj)
            d = vweights(obj.data.vertices[vi], deform)
            context.window_manager.msr_clip = json.dumps({obj.vertex_groups[k].name: w for k, w in d.items()})
        self.report({"INFO"}, "웨이트 복사: 본 %d개" % len(d))
        return {"FINISHED"}


class MSR_OT_paste(WeightOpBase, bpy.types.Operator):
    """복사한 웨이트를 선택한 모든 정점에 붙여넣기"""
    bl_idname = "msr.paste"
    bl_label = "Paste"

    def execute(self, context):
        obj = mesh_obj(context)
        clip = context.window_manager.msr_clip
        if not clip:
            self.report({"WARNING"}, "먼저 Copy 하세요")
            return {"CANCELLED"}
        data = json.loads(clip)
        with DataMode(context):
            new = {}
            for n, w in data.items():
                g = obj.vertex_groups.get(n) or obj.vertex_groups.new(name=n)
                new[g.index] = w
            deform = deform_group_indices(obj) | set(new)
            sel = selected_indices(obj)
            for vi in sel:
                write_weights(obj, vi, new, deform)
        self.report({"INFO"}, "정점 %d개에 붙여넣기" % len(sel))
        tag_redraw(context)
        return {"FINISHED"}


class MSR_OT_mirror(WeightOpBase, bpy.types.Operator):
    """선택한 정점의 웨이트를 X축 반대편 정점에 복사 (L/R 본 이름 자동 교체)"""
    bl_idname = "msr.mirror"
    bl_label = "Mirror (선택 → 반대편)"

    def execute(self, context):
        obj = mesh_obj(context)
        with DataMode(context):
            me = obj.data
            deform = deform_group_indices(obj)
            sel = selected_indices(obj)
            if not sel:
                self.report({"WARNING"}, "원본 쪽 정점을 선택하세요")
                return {"CANCELLED"}
            kd = kdtree.KDTree(len(me.vertices))
            for v in me.vertices:
                kd.insert(v.co, v.index)
            kd.balance()
            dims = obj.dimensions
            scale = max(obj.scale) or 1.0
            tol = max(dims) / scale * 0.002
            name_to_idx = {g.name: g.index for g in obj.vertex_groups}
            done = miss = center = 0
            for vi in sel:
                co = me.vertices[vi].co
                if abs(co.x) <= tol:
                    center += 1
                    continue
                co2, mi, dist = kd.find(Vector((-co.x, co.y, co.z)))
                if dist > tol or mi in sel and mi == vi:
                    miss += 1
                    continue
                d = vweights(me.vertices[vi], deform)
                new = {}
                for k, w in d.items():
                    fn = flip_name(obj.vertex_groups[k].name)
                    if fn not in name_to_idx:
                        g = obj.vertex_groups.new(name=fn)
                        name_to_idx[fn] = g.index
                        deform.add(g.index)
                    new[name_to_idx[fn]] = new.get(name_to_idx[fn], 0.0) + w
                write_weights(obj, mi, new, deform | set(new))
                done += 1
        self.report({"INFO"}, "미러 %d개 / 대칭점 못 찾음 %d개 / 중앙선 %d개(그대로)" % (done, miss, center))
        tag_redraw(context)
        return {"FINISHED"}


class MSR_OT_clean(WeightOpBase, bpy.types.Operator):
    """작은 웨이트 제거 + 정점당 본 개수 제한 + 합계 1로 정규화 (선택 없으면 전체)"""
    bl_idname = "msr.clean"
    bl_label = "정리 (최대 본 수·정규화)"
    threshold: bpy.props.FloatProperty(name="최소 웨이트", default=0.01, min=0.0, max=0.5)
    limit: bpy.props.IntProperty(name="정점당 최대 본", default=4, min=1, max=8)

    def execute(self, context):
        obj = mesh_obj(context)
        with DataMode(context):
            deform = deform_group_indices(obj)
            idx = selected_indices(obj) or range(len(obj.data.vertices))
            changed = 0
            for vi in idx:
                d = vweights(obj.data.vertices[vi], deform)
                if not d:
                    continue
                items = sorted(d.items(), key=lambda kv: -kv[1])[: self.limit]
                items = [kv for kv in items if kv[1] >= self.threshold] or items[:1]
                new = normalize(dict(items))
                if set(new) != set(d) or any(abs(new[k] - d[k]) > 1e-5 for k in new):
                    write_weights(obj, vi, new, deform)
                    changed += 1
        self.report({"INFO"}, "정리한 정점 %d개" % changed)
        tag_redraw(context)
        return {"FINISHED"}


class MSR_OT_select_bone_verts(WeightOpBase, bpy.types.Operator):
    """현재 본의 영향을 받는 정점 모두 선택"""
    bl_idname = "msr.select_bone_verts"
    bl_label = "이 본의 정점 선택"

    def execute(self, context):
        obj = mesh_obj(context)
        g = obj.vertex_groups.active
        if g is None:
            return {"CANCELLED"}
        with DataMode(context):
            n = 0
            for v in obj.data.vertices:
                w = next((x.weight for x in v.groups if x.group == g.index), 0.0)
                v.select = w > 0.001
                n += v.select
        self.report({"INFO"}, "%s: 정점 %d개" % (g.name, n))
        tag_redraw(context)
        return {"FINISHED"}


class MSR_OT_grow(WeightOpBase, bpy.types.Operator):
    """선택 확장/축소 (Max의 Grow/Shrink)"""
    bl_idname = "msr.grow"
    bl_label = "Grow"
    shrink: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        obj = mesh_obj(context)
        with DataMode(context):
            me = obj.data
            sel = {v.index for v in me.vertices if v.select}
            if self.shrink:
                border = set()
                for e in me.edges:
                    a, b = e.vertices
                    if (a in sel) != (b in sel):
                        border.add(a if a in sel else b)
                for i in border:
                    me.vertices[i].select = False
            else:
                for e in me.edges:
                    a, b = e.vertices
                    if a in sel or b in sel:
                        me.vertices[a].select = True
                        me.vertices[b].select = True
        tag_redraw(context)
        return {"FINISHED"}


class MSR_OT_ring_loop(bpy.types.Operator):
    """Ring / Loop 선택 (편집 모드)"""
    bl_idname = "msr.ring_loop"
    bl_label = "Loop"
    bl_options = {"REGISTER", "UNDO"}
    ring: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def execute(self, context):
        ts = context.tool_settings
        prev = tuple(ts.mesh_select_mode)
        ts.mesh_select_mode = (False, True, False)
        if "select_edge_loop_multi" in dir(bpy.ops.mesh):  # Blender 5.x
            (bpy.ops.mesh.select_edge_ring_multi if self.ring else bpy.ops.mesh.select_edge_loop_multi)()
        else:
            bpy.ops.mesh.loop_multi_select(ring=self.ring)
        ts.mesh_select_mode = prev
        return {"FINISHED"}


class MSR_OT_set_active_group(bpy.types.Operator):
    """이 본을 현재 본으로"""
    bl_idname = "msr.set_active_group"
    bl_label = "본 선택"
    name: bpy.props.StringProperty()

    def execute(self, context):
        obj = mesh_obj(context)
        g = obj.vertex_groups.get(self.name) if obj else None
        if g:
            obj.vertex_groups.active_index = g.index
            arm = armature_of(obj)
            if arm and self.name in arm.data.bones:
                arm.data.bones.active = arm.data.bones[self.name]
        return {"FINISHED"}


class MSR_OT_check(WeightOpBase, bpy.types.Operator):
    """웨이트 검사: 미할당 정점 / 본 수 초과 / 합계 오류"""
    bl_idname = "msr.check"
    bl_label = "웨이트 검사"
    limit: bpy.props.IntProperty(default=4)
    select_bad: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        obj = mesh_obj(context)
        with DataMode(context):
            deform = deform_group_indices(obj)
            zero = over = badsum = 0
            for v in obj.data.vertices:
                d = vweights(v, deform)
                s = sum(d.values())
                bad = False
                if not d:
                    zero += 1; bad = True
                elif len(d) > self.limit:
                    over += 1; bad = True
                elif abs(s - 1.0) > 0.01:
                    badsum += 1; bad = True
                if self.select_bad:
                    v.select = bad
        msg = "미할당 %d / %d본 초과 %d / 합계≠1 %d" % (zero, self.limit, over, badsum)
        context.window_manager.msr_status = msg + ("  (문제 정점 선택됨)" if (zero + over + badsum) and self.select_bad else "")
        self.report({"INFO"}, msg)
        tag_redraw(context)
        return {"FINISHED"}


# ============================================================ modes
def _select_only(context, objs, active):
    for o in context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    context.view_layer.objects.active = active


class MSR_OT_weight_mode(bpy.types.Operator):
    """Max의 Skin 편집처럼: 웨이트 페인트 + 정점 선택 마스크 + 자동 정규화. Ctrl+클릭으로 본 선택"""
    bl_idname = "msr.weight_mode"
    bl_label = "웨이트 편집 시작 (Skin)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = mesh_obj(context)
        if obj is None:
            sel = [o for o in context.selected_objects if o.type == "MESH"]
            obj = sel[0] if sel else None
        if obj is None:
            self.report({"WARNING"}, "웨이팅할 메쉬를 선택하세요")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        arm = armature_of(obj)
        _select_only(context, [o for o in (arm, obj) if o], obj)
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        obj.data.use_paint_mask_vertex = True
        ts = context.tool_settings
        ts.use_auto_normalize = True
        if arm:
            arm.show_in_front = True
        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
        except Exception:
            pass
        return {"FINISHED"}


class MSR_OT_figure_mode(bpy.types.Operator):
    """Max Biped의 Figure Mode처럼: 뼈대 편집(대칭 X) + 앞에 보이기. 다시 누르면 종료"""
    bl_idname = "msr.figure_mode"
    bl_label = "피규어 모드 (골격 맞추기)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if context.mode == "EDIT_ARMATURE":
            bpy.ops.object.mode_set(mode="OBJECT")
            return {"FINISHED"}
        o = context.active_object
        arm = o if o and o.type == "ARMATURE" else (armature_of(o) if o and o.type == "MESH" else None)
        if arm is None:
            arms = [x for x in context.view_layer.objects if x.type == "ARMATURE"]
            arm = arms[0] if arms else None
        if arm is None:
            self.report({"WARNING"}, "아마추어(Bip)가 없어요")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        _select_only(context, [arm], arm)
        arm.show_in_front = True
        arm.data.use_mirror_x = True
        bpy.ops.object.mode_set(mode="EDIT")
        return {"FINISHED"}


# ============================================================ Rigify start
def _ensure_rigify():
    import addon_utils
    if "rigify_generate" not in dir(bpy.ops.pose):
        try:
            addon_utils.enable("rigify", default_set=True, persistent=True)
        except Exception as e:
            print("rigify enable:", e)
    return "rigify_generate" in dir(bpy.ops.pose)


def _is_metarig(o):
    return o and o.type == "ARMATURE" and o.pose and any(getattr(pb, "rigify_type", "") for pb in o.pose.bones)


def _find_metarig(context):
    o = context.active_object
    if _is_metarig(o):
        return o
    for x in context.view_layer.objects:
        if _is_metarig(x):
            return x
    return None


class MSR_OT_rigify_metarig(bpy.types.Operator):
    """선택한 바디 메쉬 키에 맞춰 Rigify 사람 메타리그를 만들고 피규어 모드로 들어감"""
    bl_idname = "msr.rigify_metarig"
    bl_label = "Rigify 메타리그로 시작"
    bl_options = {"REGISTER", "UNDO"}
    no_face: bpy.props.BoolProperty(name="얼굴 본 제외", default=False,
                                    description="게임용: Rigify 얼굴 리그(눈·입 등) 없이 몸·손가락만")

    def execute(self, context):
        if not _ensure_rigify():
            self.report({"ERROR"}, "Rigify 애드온을 켤 수 없어요")
            return {"CANCELLED"}
        # character = selected meshes (body + face + hair ...), or every visible mesh if nothing is selected
        meshes = [o for o in context.selected_objects if o.type == "MESH"]
        if not meshes:
            meshes = [o for o in context.visible_objects if o.type == "MESH"]
        body = max(meshes, key=lambda o: len(o.data.vertices)) if meshes else None
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.object.armature_human_metarig_add()
        meta = context.active_object
        if body:
            context.window_manager.msr_body = body.name
            bb = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
            lo = Vector((min(p.x for p in bb), min(p.y for p in bb), min(p.z for p in bb)))
            hi = Vector((max(p.x for p in bb), max(p.y for p in bb), max(p.z for p in bb)))
            bones = meta.data.bones
            rig_h = max(max(b.head_local.z, b.tail_local.z) for b in bones) - min(min(b.head_local.z, b.tail_local.z) for b in bones)
            s = (hi.z - lo.z) / rig_h if rig_h > 0 else 1.0
            meta.scale = (s, s, s)
            meta.location = ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        meta.show_in_front = True
        meta.data.use_mirror_x = True
        bpy.ops.object.mode_set(mode="EDIT")
        if self.no_face:
            eb = meta.data.edit_bones
            face = eb.get("face")
            if face:
                for b in [face] + list(face.children_recursive):
                    eb.remove(b)
        self.report({"INFO"}, "메타리그 관절을 메쉬에 맞춘 뒤 'Rigify 리그 생성'을 누르세요")
        return {"FINISHED"}


class MSR_OT_rigify_generate(bpy.types.Operator):
    """메타리그로 Rigify 리그를 만들고 바디 메쉬에 자동 웨이트(DEF 본)"""
    bl_idname = "msr.rigify_generate"
    bl_label = "Rigify 리그 생성 + 자동 웨이트"
    bl_options = {"REGISTER", "UNDO"}
    auto_weight: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        if not _ensure_rigify():
            return {"CANCELLED"}
        meta = _find_metarig(context)
        if meta is None:
            self.report({"WARNING"}, "메타리그가 없어요. 먼저 'Rigify 메타리그로 시작'")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        _select_only(context, [meta], meta)
        try:
            bpy.ops.pose.rigify_generate()
        except Exception as e:
            self.report({"ERROR"}, "리그 생성 실패: %s" % str(e)[:200])
            return {"CANCELLED"}
        rig = meta.data.rigify_target_rig if hasattr(meta.data, "rigify_target_rig") else None
        rig = rig or context.active_object
        meta.hide_set(True)
        body = bpy.data.objects.get(context.window_manager.msr_body)
        msg = "리그: %s" % rig.name
        if body and self.auto_weight:
            for m in [m for m in body.modifiers if m.type == "ARMATURE"]:
                body.modifiers.remove(m)
            body.parent = None
            _select_only(context, [body, rig], rig)
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
            n = len([g for g in body.vertex_groups if g.name.startswith("DEF-")])
            msg += " | %s 자동 웨이트 (DEF 본 %d개)" % (body.name, n)
            _select_only(context, [body], body)
        context.window_manager.msr_status = msg
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class MSR_OT_zoom(bpy.types.Operator):
    """Max의 Z: 선택한 것에 맞춰 줌, 선택이 없으면 전체"""
    bl_idname = "msr.zoom"
    bl_label = "Zoom Extents"

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D"

    def execute(self, context):
        o = context.active_object
        nothing = False
        if context.mode == "PAINT_WEIGHT" and o and o.type == "MESH":
            nothing = not any(v.select for v in o.data.vertices)
        elif context.mode == "OBJECT":
            nothing = not context.selected_objects
        if nothing:
            bpy.ops.view3d.view_all(center=False)
        else:
            r = bpy.ops.view3d.view_selected()
            if r != {"FINISHED"}:
                bpy.ops.view3d.view_all(center=False)
        return {"FINISHED"}


class MSR_OT_max_view(bpy.types.Operator):
    """Max 뷰 단축키: T 위 / B 아래 / F 앞 / L 왼쪽 / P 퍼스펙티브 / U 직교 / C 카메라"""
    bl_idname = "msr.max_view"
    bl_label = "Max View"
    view: bpy.props.EnumProperty(items=[(k, k, "") for k in
                                        ("TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT", "PERSP", "USER", "CAMERA")])

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D"

    def execute(self, context):
        rv3d = context.region_data
        if self.view == "CAMERA":
            if context.scene.camera:
                bpy.ops.view3d.view_camera()
            return {"FINISHED"}
        if rv3d is None or getattr(rv3d, "lock_rotation", False):
            return {"CANCELLED"}
        if self.view in ("PERSP", "USER"):
            if rv3d.view_perspective == "CAMERA":
                bpy.ops.view3d.view_camera()
            rv3d.view_perspective = "PERSP" if self.view == "PERSP" else "ORTHO"
        else:
            bpy.ops.view3d.view_axis(type=self.view)
        return {"FINISHED"}


class MSR_OT_quad_view(bpy.types.Operator):
    """Max처럼 4분할 뷰 켜기/끄기"""
    bl_idname = "msr.quad_view"
    bl_label = "4분할 뷰"

    def execute(self, context):
        bpy.ops.screen.region_quadview()
        return {"FINISHED"}


# ============================================================ Max skin export
def _max_bridge():
    import importlib
    try:
        return importlib.import_module("max_bridge")
    except Exception:
        return None


class MSR_OT_send_weights(bpy.types.Operator):
    """현재 메쉬 웨이트를 3ds Max의 같은 이름 메쉬 Skin에 적용 (Max Bip 본 이름 기준, 정점은 위치로 대조)"""
    bl_idname = "msr.send_weights"
    bl_label = "Max Skin에 웨이트 적용"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self, event, title="Max로 웨이트 보내기",
            message="Max의 '%s' 메쉬 Skin을 이 웨이트로 교체해요 (Max에서 Ctrl+Z 가능)." % (context.window_manager.msr_target or (mesh_obj(context).name if mesh_obj(context) else "")))

    def execute(self, context):
        wm = context.window_manager
        obj = mesh_obj(context)
        if obj is None:
            self.report({"WARNING"}, "메쉬를 선택하세요")
            return {"CANCELLED"}
        mb = _max_bridge()
        if mb is None:
            wm.msr_status = "Max Bridge 애드온이 필요해요"
            return {"CANCELLED"}
        target = wm.msr_target or obj.name
        try:
            r = send_weights_to_max(obj, target, mb, wm.msr_limit)
        except Exception as e:
            wm.msr_status = "실패 | %s" % str(e)[:300]
            self.report({"ERROR"}, wm.msr_status)
            return {"CANCELLED"}
        wm.msr_status = r
        self.report({"INFO"}, r)
        return {"FINISHED"}


def send_weights_to_max(obj, target, mb, limit=4):
    ex = mb.exchange_dir()
    # 11/01: Max 포트별 파일 (작업자 9877 과 Claude 9878~ 가 동시에 스킨 적용하면 같은 파일을 지우다 WinError 32)
    tag = str(getattr(mb, "PORT", "") or "")
    vpath = os.path.join(ex, "msr_max_verts%s.txt" % (("_" + tag) if tag else ""))
    wpath = os.path.join(ex, "msr_weights%s.txt" % (("_" + tag) if tag else ""))
    for p in (vpath, wpath):
        if os.path.exists(p):
            os.remove(p)
    # 1) Max vertex positions (world) of the target mesh, in Skin vertex order
    code = (
        '(local o = getNodeByName "@T@"\n'
        ' if o == undefined then "ERROR: Max에 \'@T@\' 메쉬가 없어요" else (\n'
        '  local sks = for md in o.modifiers where classOf md == Skin and md.enabled collect md\n'
        '  for md in sks do md.enabled = false\n'   # bind shape, not the current animated pose
        '  local m = snapshotAsMesh o\n'
        '  for md in sks do md.enabled = true\n'
        '  local f = createFile @P@\n'
        '  for i = 1 to m.numverts do (local p = getVert m i; format "% % %\\n" p.x p.y p.z to:f)\n'
        '  close f\n'
        '  local n = m.numverts\n'
        '  delete m\n'
        '  "OK " + (n as string)))'
    ).replace("@T@", target.replace('"', "")).replace("@P@", mb.ms_path(vpath))
    res = mb.send(code, timeout=120)
    if not res.startswith("OK"):
        raise RuntimeError(res)
    maxv = []
    with open(vpath, encoding="utf-8-sig") as f:
        for line in f:
            p = line.split()
            if len(p) == 3:
                maxv.append(Vector((float(p[0]), float(p[1]), float(p[2]))))
    # 2) Blender vertex positions (world, evaluated rest shape = base mesh)
    me = obj.data
    mw = obj.matrix_world
    bv = [mw @ v.co for v in me.vertices]

    def norm(pts):
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        c = (lo + hi) / 2
        s = (hi - lo).length or 1.0
        return [(p - c) / s for p in pts]

    nm, nb = norm(maxv), norm(bv)
    mapping = None
    how = ""
    if len(nm) == len(nb):
        err = max((a - b).length for a, b in zip(nm, nb))
        if err < 0.002:
            mapping = list(range(len(nb)))
            how = "정점 순서 일치"
    if mapping is None:
        kd = kdtree.KDTree(len(nb))
        for i, p in enumerate(nb):
            kd.insert(p, i)
        kd.balance()
        mapping, worst = [], 0.0
        for p in nm:
            _, i, d = kd.find(p)
            mapping.append(i)
            worst = max(worst, d)
        if worst > 0.01:
            raise RuntimeError("Max와 블렌더 메쉬 모양이 달라요 (최대 오차 %.1f%%). 같은 메쉬인지 확인하세요" % (worst * 100))
        how = "위치로 대조(최대 오차 %.2f%%)" % (worst * 100)
    # 3) weights in Max vertex order
    deform = deform_group_indices(obj)
    arm = armature_of(obj)
    # Bone_breast_L/R weights go to Max's breast jiggle bones bone_bast_l/r (when Max has them)
    ren = {a: b for a, b in BREAST_BAST.items() if a in obj.vertex_groups}
    if ren:
        # Max names by their real case (Ivelar rig: Bone_bast_L, Melitta: bone_bast_l); the Skin needs the exact name
        r = mb.send('(local r = ""; for n in #(%s) do (local o = getNodeByName n exact:true; r += (if o != undefined then o.name else "") + "|"); r)'
                    % ",".join('"%s"' % b for b in ren.values()), timeout=30).strip().strip('"').split("|")
        ren = {a: r[i] for i, a in enumerate(ren) if i < len(r) and r[i]}
    used, rows = {}, []
    for bi in mapping:
        d = vweights(me.vertices[bi], deform)
        items = sorted(d.items(), key=lambda kv: -kv[1])[:limit]
        acc = {}
        for k, w in normalize(dict(items)).items():
            n = obj.vertex_groups[k].name
            n = ren.get(n, n)
            acc[n] = acc.get(n, 0.0) + w
        row = []
        for n, w in acc.items():
            if n not in used:
                used[n] = len(used)
            row.append("%d:%.6f" % (used[n], w))
        rows.append(" ".join(row))
    empty = sum(1 for r in rows if not r)
    names = sorted(used, key=lambda n: used[n])
    with open(wpath, "w", encoding="utf-8") as f:
        f.write("#BONES\t" + "\t".join(names) + "\n")
        f.write("\n".join(rows) + "\n")
    res = mb.send("MaxBridge.applyWeights \"%s\" %s limit:%d" % (target, mb.ms_path(wpath), limit), timeout=600)   # MaxBridge 1.4.4 이상 필요
    if not res.startswith("OK"):
        raise RuntimeError(res)
    # 10/30: 보낸 값 기록 → [리깅 완료] 때 '자동 값 → 사람이 고친 값' 비교용
    try:
        import rig_template as _rt
        _rt.keep_sent(mb.send("maxFileName", timeout=30).strip().strip('"'), target, wpath)
    except Exception as e:
        print("keep sent:", e)
    return "완료 | Max '%s' | %s | 본 %d개 | 미할당 정점 %d | %s" % (target, how, len(names), empty, res)


class MSR_OT_from_max(bpy.types.Operator):
    """Max에서 선택한 메쉬 + Bip을 블렌더로 가져오기 (Max Bridge)"""
    bl_idname = "msr.from_max"
    bl_label = "Max에서 가져오기"

    def execute(self, context):
        try:
            r = bpy.ops.maxbridge.from_max()
            context.window_manager.msr_status = "Max에서 가져오기 완료 (이전 것은 'FromMax_이전'에 숨김)" if "FINISHED" in r else "가져오기 취소됨"
            return r
        except Exception as e:
            context.window_manager.msr_status = "실패 | %s" % e
            return {"CANCELLED"}


# ============================================================ game face bones (Bone_part_side_updown)
# (name, parent, u, v, inset_k, tail)   u: -1..1 of half face width (+ = character left),
# v: 0..1 of face height from chin, inset_k: depth behind surface as fraction of face width
FACE_TPL = [
    ("Bone_eyeball_L", "HEAD", 0.35, 0.455, 0.070),
    ("Bone_eye_L_up", "HEAD", 0.35, 0.490, 0.020),
    ("Bone_eye_L_dn", "HEAD", 0.35, 0.425, 0.020),
    ("Bone_brow_L_in", "HEAD", 0.17, 0.545, 0.020),
    ("Bone_brow_L_out", "HEAD", 0.55, 0.550, 0.020),
    ("Bone_cheek_L", "HEAD", 0.33, 0.330, 0.030),
    ("Bone_lip_L", "HEAD", 0.25, "M", 0.020),
    ("Bone_lip_L_up", "HEAD", 0.13, "MU", 0.015),
    ("Bone_lip_L_dn", "Bone_jaw", 0.13, "MD", 0.015),
    ("Bone_lip_up", "HEAD", 0.0, "MU", 0.015),
    ("Bone_lip_dn", "Bone_jaw", 0.0, "MD", 0.015),
]
# radius of influence (fraction of face width) by name part
FACE_RADIUS = {"eyeball": 0.075, "eye": 0.10, "brow": 0.14, "cheek": 0.20, "lip": 0.075, "tongue": 0.07}


def _mirror_tpl():
    out = []
    for e in FACE_TPL:
        out.append(e)
        if "_L" in e[0]:
            out.append((e[0].replace("_L", "_R"), e[1], -e[2]) + e[3:])
    return out


def _face_frame(face, tooth):
    from mathutils.bvhtree import BVHTree
    pts = [face.matrix_world @ v.co for v in face.data.vertices]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    fr = {"lo": lo, "hi": hi, "cx": (lo.x + hi.x) / 2, "hw": (hi.x - lo.x) / 2, "H": hi.z - lo.z,
          "W": hi.x - lo.x, "D": hi.y - lo.y}
    bm = bmesh.new()
    bm.from_mesh(face.data)
    bm.transform(face.matrix_world)
    fr["bvh"] = BVHTree.FromBMesh(bm)
    bm.free()
    fr["mouth_v"] = 0.205
    fr["tooth"] = None
    if tooth:
        tp = [tooth.matrix_world @ v.co for v in tooth.data.vertices]
        tz0, tz1 = min(p.z for p in tp), max(p.z for p in tp)
        fr["mouth_v"] = ((tz0 + tz1) / 2 - lo.z) / fr["H"]
        fr["tooth"] = (tz0, tz1, min(p.y for p in tp), max(p.y for p in tp))
    return fr


def _surface(fr, x, z):
    """front surface point (smallest y = front, Max/Blender -Y forward) at x,z"""
    hit = fr["bvh"].ray_cast(Vector((x, fr["lo"].y - 1.0, z)), Vector((0, 1, 0)))
    if hit[0] is not None:
        return hit[0].y
    return fr["lo"].y + 0.15 * fr["D"]


def face_bone_points(face, tooth=None):
    fr = _face_frame(face, tooth)
    mv = fr["mouth_v"]
    vmap = {"M": mv, "MU": mv + 0.022, "MD": mv - 0.022}
    pts = {}
    for name, parent, u, v, k in _mirror_tpl():
        v = vmap.get(v, v)
        x = fr["cx"] + u * fr["hw"]
        z = fr["lo"].z + v * fr["H"]
        y = _surface(fr, x, z) + k * fr["W"]
        pts[name] = (Vector((x, y, z)), parent)
    # jaw: pivot behind the mouth at ~ear level, tail at the chin
    jz = fr["lo"].z + 0.30 * fr["H"]
    chin_z = fr["lo"].z + 0.06 * fr["H"]
    jaw = Vector((fr["cx"], fr["lo"].y + 0.45 * fr["D"], jz))
    chin = Vector((fr["cx"], _surface(fr, fr["cx"], chin_z) + 0.04 * fr["W"], chin_z))
    pts["Bone_jaw"] = (jaw, "HEAD", chin)
    # tongue: two bones inside the mouth, parented to jaw
    mz = fr["lo"].z + (mv - 0.01) * fr["H"]
    lip_y = _surface(fr, fr["cx"], fr["lo"].z + mv * fr["H"])
    pts["Bone_tongue_01"] = (Vector((fr["cx"], lip_y + 0.14 * fr["W"], mz)), "Bone_jaw")
    pts["Bone_tongue_02"] = (Vector((fr["cx"], lip_y + 0.06 * fr["W"], mz)), "Bone_tongue_01")
    return pts, fr


def build_face_bones(arm, head_name, face, tooth=None):
    """Create the game face bones in arm (edit mode inside). Returns (names, frame)."""
    pts, fr = face_bone_points(face, tooth)
    L = 0.035 * fr["W"]
    inv = arm.matrix_world.inverted()
    ctx = bpy.context
    prev_active = ctx.view_layer.objects.active
    if ctx.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    _select_only(ctx, [arm], arm)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    order = ["Bone_jaw"] + [n for n in pts if n != "Bone_jaw"]
    order.remove("Bone_tongue_02")
    order.append("Bone_tongue_02")
    for n in order:
        rec = pts[n]
        head = rec[0]
        tail = rec[2] if len(rec) > 2 else None
        if n == "Bone_tongue_01":
            tail = pts["Bone_tongue_02"][0]
        if tail is None:
            tail = head + Vector((0, -L, 0))
        b = eb.get(n) or eb.new(n)
        b.head = inv @ head
        b.tail = inv @ tail
        b.roll = 0.0
        par = rec[1]
        b.parent = eb.get(head_name if par == "HEAD" else par)
        b.use_connect = False
        b.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")
    if prev_active:
        ctx.view_layer.objects.active = prev_active
    return [n for n in order], fr


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def face_auto_weights(arm, head_name, face, tooth=None, limit=4):
    """Local falloff weights: each face bone owns a small region, the rest stays on the head bone."""
    pts, fr = face_bone_points(face, tooth)
    W = fr["W"]
    mw = arm.matrix_world
    bones = {n: mw @ arm.data.bones[n].head_local for n in pts if n in arm.data.bones}
    mouth_z = fr["lo"].z + fr["mouth_v"] * fr["H"]
    jaw_y = bones["Bone_jaw"].y
    eye_z = {s: bones["Bone_eyeball_%s" % s].z for s in "LR"}

    def rad(n):
        for key in ("eyeball", "tongue", "cheek", "brow", "lip", "eye"):
            if "_%s" % key in n:
                return FACE_RADIUS[key] * W
        return 0.1 * W

    def weights_for(p):
        w = {}
        # jaw region (v2): soft round falloff so the open mouth is oval, not a box
        H, hw = fr["H"], fr["hw"]
        dx = abs(p.x - fr["cx"])
        below = mouth_z + 0.015 * H - p.z                     # >0 under the mouth line
        V = _smooth(below / (0.11 * H))                        # lip line -> chin
        Vdeep = _smooth((below - 0.10 * H) / (0.12 * H))       # jaw line / under the chin
        Lat = 1.0 - _smooth((dx - 0.15 * hw) / (0.55 * hw))    # mouth centre -> outer cheek
        jw = V * (Lat + (1.0 - Lat) * Vdeep)
        # mouth corners / lower cheeks: partial jaw so the corners stretch diagonally
        cz = abs(p.z - mouth_z) / (0.08 * H)
        cxd = abs(dx - 0.27 * hw) / (0.22 * hw)
        corner = 0.35 * (1.0 - _smooth((cz * cz + cxd * cxd) ** 0.5))
        jw = max(jw, corner)
        jw *= _smooth((jaw_y - p.y) / (0.15 * fr["D"]))        # nothing behind the jaw pivot (ears, neck back)
        jw *= 1.0 - _smooth((dx - 0.85 * hw) / (0.15 * hw))
        for n, h in bones.items():
            if n in ("Bone_jaw", "Bone_tongue_01", "Bone_tongue_02"):
                continue
            d = (p - h).length / rad(n)
            if d >= 1.0:
                continue
            f = 1.0 - _smooth(d)
            if "_eye_" in n:  # upper lid takes points above the eye centre, lower lid below
                s = n.split("_")[2]
                above = p.z >= eye_z[s]
                if (n.endswith("_up") and not above) or (n.endswith("_dn") and above):
                    continue
            if "_lip" in n:
                if n.endswith("_up") and p.z < mouth_z - 0.003 * fr["H"]:
                    continue
                if n.endswith("_dn") and p.z > mouth_z + 0.003 * fr["H"]:
                    continue
            w[n] = f
        if jw > 0.001:
            w["Bone_jaw"] = jw * (1.0 - min(1.0, sum(v for k, v in w.items() if k.endswith("_dn") and "_lip" in k)))
        s = sum(w.values())
        if s > 1.0:
            w = {k: v / s for k, v in w.items()}
            s = 1.0
        if s < 0.999:
            w[head_name] = 1.0 - s
        items = sorted(w.items(), key=lambda kv: -kv[1])[:limit]
        t = sum(v for _, v in items)
        return {k: v / t for k, v in items if v / t > 0.005}

    def apply(obj, fn):
        for m in [m for m in obj.modifiers if m.type == "ARMATURE"]:
            obj.modifiers.remove(m)
        mod = obj.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
        groups = {}
        for v in obj.data.vertices:
            p = obj.matrix_world @ v.co
            for n, x in fn(p).items():
                g = groups.get(n) or obj.vertex_groups.get(n) or obj.vertex_groups.new(name=n)
                groups[n] = g
                g.add([v.index], x, "REPLACE")
        return len(groups)

    n_face = apply(face, weights_for)
    n_tooth = 0
    if tooth:
        tz0, tz1 = fr["tooth"][0], fr["tooth"][1]
        mid = (tz0 + tz1) / 2
        # v3 (from the artist's fix on Melitta): split by connected piece, not by height.
        # lower pieces (lower teeth, tongue, mouth floor) -> jaw 1.0, their top 40% -> jaw 0.9 / head 0.1,
        # upper pieces (upper teeth, palate) -> head 1.0
        bm = bmesh.new()
        bm.from_mesh(tooth.data)
        bm.verts.ensure_lookup_table()
        isl, seen = {}, set()
        for v in bm.verts:
            if v.index in seen:
                continue
            stack, comp = [v], []
            seen.add(v.index)
            while stack:
                x = stack.pop()
                comp.append(x.index)
                for e in x.link_edges:
                    o2 = e.other_vert(x)
                    if o2.index not in seen:
                        seen.add(o2.index)
                        stack.append(o2)
            zs = [(tooth.matrix_world @ bm.verts[i].co).z for i in comp]
            info = (sum(zs) / len(zs), min(zs), max(zs))
            for i in comp:
                isl[i] = info
        bm.free()

        def tooth_w_v3(p, vi):
            cz, lo_z, hi_z = isl[vi]
            if cz >= mid:
                return {head_name: 1.0}
            top = lo_z + 0.6 * (hi_z - lo_z)
            return {"Bone_jaw": 1.0} if p.z <= top else {"Bone_jaw": 0.9, head_name: 0.1}

        for m in [m for m in tooth.modifiers if m.type == "ARMATURE"]:
            tooth.modifiers.remove(m)
        tooth.modifiers.new("Armature", "ARMATURE").object = arm
        for v in tooth.data.vertices:
            for n, x in tooth_w_v3(tooth.matrix_world @ v.co, v.index).items():
                g = tooth.vertex_groups.get(n) or tooth.vertex_groups.new(name=n)
                g.add([v.index], x, "REPLACE")
        n_tooth = len(tooth.vertex_groups)
    return n_face, n_tooth


def _find_head_bone(arm):
    for b in arm.data.bones:
        if b.name.endswith(" Head") and "Nub" not in b.name:
            return b.name
    for b in arm.data.bones:
        if b.name.lower().endswith("head"):
            return b.name
    return None


class MSR_OT_face_bones(bpy.types.Operator):
    """얼굴 메쉬를 선택하고 실행: 게임용 얼굴 본 45개(Bone_부위_L/R_up/dn)를 Bip 머리 아래 만들고 자동 웨이트"""
    bl_idname = "msr.face_bones"
    bl_label = "게임용 얼굴 본 + 자동 웨이트"
    bl_options = {"REGISTER", "UNDO"}
    weights: bpy.props.BoolProperty(name="자동 웨이트", default=True)

    def execute(self, context):
        face = mesh_obj(context) or next((o for o in context.selected_objects if o.type == "MESH"), None)
        if face is None:
            self.report({"WARNING"}, "얼굴 메쉬를 선택하세요")
            return {"CANCELLED"}
        arms = [o for o in context.view_layer.objects if o.type == "ARMATURE" and _find_head_bone(o)]
        arm = armature_of(face) if armature_of(face) in arms else (arms[0] if arms else None)
        if arm is None:
            self.report({"WARNING"}, "머리 본(… Head)이 있는 아마추어(Bip)가 없어요")
            return {"CANCELLED"}
        head = _find_head_bone(arm)
        tooth = next((o for o in context.view_layer.objects if o.type == "MESH" and
                      any(k in o.name.lower() for k in ("tooth", "teeth"))), None)
        names, fr = build_face_bones(arm, head, face, tooth)
        msg = "얼굴 본 %d개 생성 (머리: %s)" % (len(names), head)
        if self.weights:
            nf, nt = face_auto_weights(arm, head, face, tooth)
            msg += " | 웨이트: %s 본 %d개%s" % (face.name, nf, (" · %s" % tooth.name) if tooth else "")
        _select_only(context, [face], face)
        context.window_manager.msr_status = msg
        self.report({"INFO"}, msg)
        return {"FINISHED"}


# ============================================================ B: auto weights straight on the Max Biped
def bip_prefix(arm):
    for b in arm.data.bones:
        if b.name.endswith(" Pelvis"):
            return b.name[:-len(" Pelvis")]
    return None


def _wpos(arm, n):
    b = arm.data.bones.get(n)
    return (arm.matrix_world @ b.head_local) if b else None


def _bone_ci(arm, n):
    """the armature's bone name for n, ignoring upper/lower case (n itself when there is none)"""
    if n in arm.data.bones:
        return n
    lo = n.lower()
    for b in arm.data.bones:
        if b.name.lower() == lo:
            return b.name
    return n


def bip_segments(arm, use_twist=True, extra=("Bone_breast_L", "Bone_breast_R"), twist_ci=True):
    """Deform bones for body auto weights with correct head->tail segments (FBX bone tails are not usable).
    Twist chains 'Bone {S} UpperArm Twist'+'Twist1' replace the Biped limb when present."""
    P = bip_prefix(arm)
    if P is None:
        raise RuntimeError("Bip(… Pelvis) 본을 찾지 못했어요")
    seg = {}

    def has(n):
        return n in arm.data.bones

    def put(n, tail_name=None, tail_pos=None):
        if not has(n):
            return
        tail_name = _bone_ci(arm, tail_name) if tail_name else tail_name
        h = _wpos(arm, n)
        t = tail_pos if tail_pos is not None else (_wpos(arm, tail_name) if tail_name and has(tail_name) else None)
        if t is None or (t - h).length < 1e-6:
            b = arm.data.bones[n]
            par = b.parent
            d = (h - _wpos(arm, par.name)) if par else Vector((0, 0, 1))
            t = h + d.normalized() * max(0.3 * d.length, 1e-3)
        seg[n] = (h, t)

    S = lambda s, x: "%s %s %s" % (P, s, x)
    # spine
    thighs = [_wpos(arm, S(s, "Thigh")) for s in "LR" if has(S(s, "Thigh"))]
    put(P + " Pelvis", tail_pos=(sum(thighs, Vector()) / len(thighs)) if thighs else None)
    chain = [P + " Spine"] + [P + " Spine%d" % i for i in range(1, 5) if has(P + " Spine%d" % i)] + [P + " Neck"]
    chain = [c for c in chain if has(c)]
    for a, b in zip(chain, chain[1:] + [P + " Head"]):
        put(a, b)
    put(P + " Head", P + " HeadNub")
    for s in "LR":
        put(S(s, "Clavicle"), S(s, "UpperArm"))
        limbs = (("UpperArm", "Forearm", "Bone %s UpperArm Twist" % s),
                 ("Forearm", "Hand", "Bone %s ForeArm Twist" % s),
                 ("Thigh", "Calf", "Bone %s Thigh Twist" % s),
                 ("Calf", "Foot", "Bone %s Calf Twist" % s))
        for limb, nxt, tw in limbs:
            if twist_ci:
                tw = _bone_ci(arm, tw)  # rig twist bones are lower case now ('bone l upperarm twist')
            if use_twist and has(tw) and has(tw + "1"):
                put(tw, tw + "1")
                put(tw + "1", S(s, nxt))
            else:
                put(S(s, limb), S(s, nxt))
        mid = S(s, "Finger2") if has(S(s, "Finger2")) else S(s, "Finger1")
        put(S(s, "Hand"), mid)
        for f in range(5):
            names = [S(s, "Finger%d" % f)] + [S(s, "Finger%d%d" % (f, k)) for k in (1, 2, 3)]
            names = [n for n in names if has(n)]
            for a, b in zip(names, names[1:] + [S(s, "Finger%dNub" % f)]):
                put(a, b)
        put(S(s, "Foot"), S(s, "Toe0"))
        put(S(s, "Toe0"), S(s, "Toe0Nub"))
    for n in extra:
        if has(n):
            b = arm.data.bones[n]
            seg[n] = (arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local)
    return seg


# per-bone distance factors fitted to the team's hand-made Melitta skin (75% same dominant bone vs 61% plain)
# >1 = bone reaches less far, <1 = reaches further.  S = either side.
BIP_STYLE = {
    "Bip01 Head": 0.7, "Bip01 Neck": 1.5, "Bip01 Pelvis": 1.5, "Bip01 Spine": 0.7, "Bip01 Spine2": 0.7,
    "Bip01 S Clavicle": 1.5, "Bip01 S Hand": 0.85, "Bip01 S Foot": 1.2, "Bip01 S Toe0": 1.2,
    "Bip01 S Finger0": 2.0, "Bip01 S Finger01": 2.0, "Bip01 S Finger02": 2.0, "Bip01 S Finger1": 2.0,
    "Bip01 S Finger2": 1.2, "Bip01 S Finger3": 1.2,
    "Bone S UpperArm Twist": 1.35, "Bone S UpperArm Twist1": 1.35,
    "Bone S ForeArm Twist": 1.13, "Bone S ForeArm Twist1": 1.13,
    "Bone S Thigh Twist": 0.85, "Bone S Thigh Twist1": 0.85,
    "Bone S Calf Twist": 1.1, "Bone S Calf Twist1": 1.1,
}


_STYLE_LC = {k.lower(): v for k, v in BIP_STYLE.items()}


def _style_key(n, prefix):
    k = re.sub(r"(?<![A-Za-z0-9])[LR](?![A-Za-z0-9])", "S", n)
    return k.replace(prefix + " ", "Bip01 ", 1) if prefix and k.startswith(prefix + " ") else k


def _style_factor(n, prefix):
    """BIP_STYLE value for n; also matches the lower-case rig twist names ('bone l upperarm twist')"""
    k = _style_key(n, prefix)
    if k in BIP_STYLE:
        return BIP_STYLE[k]
    k2 = re.sub(r"(?<![a-z0-9])[lr](?![a-z0-9])", "s", k.lower())
    return _STYLE_LC.get(k2, 1.0)



def _smoothstep_np(x):
    import numpy as np
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _bip_masks(arm, names, Pts, H, D, L2):
    """Anatomy limits on top of the distance weights (vertex x bone multipliers):
    - Head fades in from just below the Neck joint (shoulders / trapezius stay on Spine2)
    - first upper-arm segment does not reach in past the shoulder joint (top of shoulder / back of neck)"""
    import numpy as np
    pre = bip_prefix(arm)
    M = np.ones((len(Pts), len(names)))
    nk, hd = _wpos(arm, pre + " Neck"), _wpos(arm, pre + " Head")
    if nk is not None and hd is not None and hd.z > nk.z:
        # team skin: Head starts a little below the Neck joint, ~half at mid-neck, dominant above
        z0 = nk.z - 0.6 * (hd.z - nk.z)
        span = 1.1 * (hd.z - nk.z)
        k = names.index(pre + " Head") if (pre + " Head") in names else -1
        if k >= 0:
            M[:, k] = _smoothstep_np((Pts[:, 2] - z0) / max(span, 1e-6))
    for s in "LR":
        for first in (_bone_ci(arm, "Bone %s UpperArm Twist" % s), "%s %s UpperArm" % (pre, s)):
            if first in names:
                k = names.index(first)
                tr = ((Pts - H[k]) * D[k]).sum(1) / L2[k]
                M[:, k] = _smoothstep_np((tr + 0.15) / 0.15)
                break
    return M


def bip_auto_weights(arm, body, use_twist=True, limit=4, clear_old=True, power=4.0, smooth_iter=0, style=True, masks=True,
                     twist_ci=True):
    """Distance-to-bone-segment weights + mesh smoothing.
    (Blender bone heat fails on open, multi-layer game meshes, so it is not used.)"""
    import numpy as np
    seg = bip_segments(arm, use_twist=use_twist, twist_ci=twist_ci)
    ctx = bpy.context
    if ctx.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    names = list(seg)
    H = np.array([seg[n][0] for n in names])
    T = np.array([seg[n][1] for n in names])
    me = body.data
    nv = len(me.vertices)
    co = np.empty(nv * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(nv, 3)
    M = np.array(body.matrix_world)
    P = co @ M[:3, :3].T + M[:3, 3]
    # distance point -> segment, N x B
    D = T - H
    L2 = np.maximum((D * D).sum(1), 1e-12)
    t = np.clip(((P[:, None, :] - H[None]) * D[None]).sum(2) / L2[None], 0.0, 1.0)
    Q = H[None] + t[..., None] * D[None]
    dist = np.sqrt(((P[:, None, :] - Q) ** 2).sum(2)) + 1e-6
    raw = dist.copy()
    if style:
        pre = bip_prefix(arm)
        fac = np.array([_style_factor(n, pre) for n in names])
        dist = dist * fac[None]
    # scale-free: relative to each vertex's nearest bone distance
    dmin = dist.min(1, keepdims=True)
    W = (dmin / dist) ** power
    if masks:
        W = W * _bip_masks(arm, names, P, H, D, L2)
        z = np.where(W.sum(1) <= 1e-9)[0]
        W[z, np.argmin(dist[z], axis=1)] = 1.0
    # breast bones only near the chest
    for k, n in enumerate(names):
        if n.startswith("Bone_breast"):
            r = BREAST_REACH * np.sqrt(L2[k])
            W[:, k] *= np.clip(1.0 - (raw[:, k] / r) ** 2, 0.0, 1.0)
    W /= W.sum(1, keepdims=True)
    # smoothing over mesh edges (keeps separate pieces separate)
    ne = len(me.edges)
    ev = np.empty(ne * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(ne, 2)
    deg = np.bincount(ev.ravel(), minlength=nv).astype(float)
    for _ in range(smooth_iter):
        acc = np.zeros_like(W)
        np.add.at(acc, ev[:, 0], W[ev[:, 1]])
        np.add.at(acc, ev[:, 1], W[ev[:, 0]])
        nb = np.where(deg[:, None] > 0, acc / np.maximum(deg[:, None], 1), W)
        W = 0.5 * W + 0.5 * nb
    # top-N, prune, normalise
    order = np.argsort(-W, axis=1)[:, :limit]
    # write
    bone_names = {b.name for b in arm.data.bones}
    if clear_old:
        for g in [g for g in body.vertex_groups if g.name in bone_names]:
            body.vertex_groups.remove(g)
    for mo in [mo for mo in body.modifiers if mo.type == "ARMATURE"]:
        body.modifiers.remove(mo)
    groups = [body.vertex_groups.get(n) or body.vertex_groups.new(name=n) for n in names]
    for vi in range(nv):
        idx = order[vi]
        w = W[vi, idx]
        keep = w >= 0.01
        if not keep.any():
            keep[0] = True
        w = w[keep] / w[keep].sum()
        for k, x in zip(idx[keep], w):
            groups[k].add([vi], float(x), "REPLACE")
    mod = body.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return len(seg), 0


# Bone_breast_L/R = Max breast jiggle bones bone_bast_l/r (start -> _nub). Weights are sent to bone_bast in Max.
BREAST_BAST = {"Bone_breast_L": "bone_bast_l", "Bone_breast_R": "bone_bast_r"}
BREAST_REACH = 1.9   # breast weight radius = bone length x this (was 1.6)


def _bast_pairs(arm):
    """{Bone_breast_X: (start, end)} from the imported bone_bast_x / bone_bast_x_nub, or None if missing."""
    out = {}
    low = {x.name.lower(): x.name for x in arm.data.bones}      # Ivelar rig: Bone_bast_L / Bone_bast_L_Nub
    for n, b in BREAST_BAST.items():
        b0, b1 = low.get(b), low.get(b + "_nub")
        if b0 is None or b1 is None:
            return None
        out[n] = (_wpos(arm, b0), _wpos(arm, b1))
    return out


BREAST_SKIP_ASYM = False  # loose pieces with no mirror copy (one-side decorations) keep the template weights


def _asym_pieces(body, tol=0.01):
    """Vertex indices of loose mesh pieces whose mirror (x -> -x) has no matching vertices (mean distance > tol)."""
    me = body.data
    mw = body.matrix_world
    P = [mw @ v.co for v in me.vertices]
    kd = kdtree.KDTree(len(P))
    for i, p in enumerate(P):
        kd.insert(p, i)
    kd.balance()
    nb = [[] for _ in P]
    for e in me.edges:
        a, b = e.vertices
        nb[a].append(b)
        nb[b].append(a)
    seen, out = set(), set()
    for s in range(len(P)):
        if s in seen:
            continue
        st, idx = [s], []
        seen.add(s)
        while st:
            i = st.pop()
            idx.append(i)
            for j in nb[i]:
                if j not in seen:
                    seen.add(j)
                    st.append(j)
        d = sum(kd.find(Vector((-P[i].x, P[i].y, P[i].z)))[2] for i in idx) / len(idx)
        if d > tol:
            out.update(idx)
    return out


def _breast_capture(body):
    """{vertex: {group_index: weight}} of the Bone_breast groups (kept across the body template)."""
    gi = {body.vertex_groups[n].index for n in BREAST_BAST if n in body.vertex_groups}
    skip = _asym_pieces(body) if BREAST_SKIP_ASYM else set()
    out = {}
    for v in body.data.vertices:
        if v.index in skip:
            continue
        d = {g.group: g.weight for g in v.groups if g.group in gi and g.weight > 0.0}
        if d:
            out[v.index] = d
    return out


def _breast_restore(body, cap, limit=4):
    """Put captured breast weights back on top: other weights scaled by (1 - breast)."""
    deform = deform_group_indices(body)
    for vi, br in cap.items():
        s = min(sum(br.values()), 1.0)
        new = {k: w * (1.0 - s) for k, w in vweights(body.data.vertices[vi], deform).items() if k not in br}
        new.update(br)
        items = sorted(new.items(), key=lambda kv: -kv[1])[:limit]
        write_weights(body, vi, normalize(dict(items)), deform)
    return len(cap)


def breast_points(arm, body):
    """Rigify-like breast bones: root inside the chest, tip at the most forward point of each breast.
    When the Max breast jiggle bones (bone_bast_l/r) were imported, use their start/end instead."""
    got = _bast_pairs(arm)
    if got:
        return got
    P = bip_prefix(arm)
    sp2 = _wpos(arm, P + " Spine2") or _wpos(arm, P + " Spine1")
    ua = {s: _wpos(arm, "%s %s UpperArm" % (P, s)) for s in "LR"}
    fa = {s: _wpos(arm, "%s %s Forearm" % (P, s)) for s in "LR"}
    if sp2 is None or ua["L"] is None:
        raise RuntimeError("Spine2 / UpperArm 본이 없어요")
    mw = body.matrix_world
    pts = [mw @ v.co for v in body.data.vertices]
    out = {}
    for s in "LR":
        sx = ua[s].x - sp2.x
        ual = (fa[s] - ua[s]).length
        z1, z0 = ua[s].z - 0.10 * ual, ua[s].z - 0.75 * ual
        xa, xb = sorted((sp2.x + 0.15 * sx, sp2.x + 0.75 * sx))
        band = [p for p in pts if xa <= p.x <= xb and z0 <= p.z <= z1]
        if not band:
            raise RuntimeError("가슴 영역 정점을 찾지 못했어요")
        apex = min(band, key=lambda p: p.y)          # -Y = front
        back_y = sp2.y
        root = Vector((sp2.x + 0.85 * (apex.x - sp2.x), apex.y + 0.55 * (back_y - apex.y), apex.z + 0.02 * ual))
        out["Bone_breast_%s" % s] = (root, apex)
    return out


def add_breast_bones(arm, body, to_max=True):
    P = bip_prefix(arm)
    pts = breast_points(arm, body)
    ctx = bpy.context
    if ctx.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    _select_only(ctx, [arm], arm)
    bpy.ops.object.mode_set(mode="EDIT")
    inv = arm.matrix_world.inverted()
    eb = arm.data.edit_bones
    for n, (h, t) in pts.items():
        b = eb.get(n) or eb.new(n)
        b.head, b.tail = inv @ h, inv @ t
        b.parent = eb.get(P + " Spine2") or eb.get(P + " Spine1")
        b.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")
    msg = "가슴 본 2개 (블렌더)"
    if to_max:
        mb = _max_bridge()
        if mb is None:
            return msg + " | Max Bridge 없음"
        # Blender world -> Max: measured from two Biped joints that exist in both
        a_n, b_n = P + " Spine2", P + " Head"
        try:
            ma = mb.send('(getNodeByName "%s").transform.pos as string' % a_n, timeout=15)
            mbp = mb.send('(getNodeByName "%s").transform.pos as string' % b_n, timeout=15)
            va = Vector([float(x) for x in ma.strip()[1:-1].split(",")])
            vb = Vector([float(x) for x in mbp.strip()[1:-1].split(",")])
        except Exception as e:
            return msg + " | Max 위치 읽기 실패: %s" % e
        ba, bb = _wpos(arm, a_n), _wpos(arm, b_n)
        unit = (vb - va).length / max((bb - ba).length, 1e-9)
        off = va - ba * unit
        lines = ["(", " local made = 0",
                 ' local lay = LayerManager.getLayerFromName "Body_Bones"',
                 ' if lay == undefined do lay = LayerManager.newLayerFromName "Body_Bones"']
        par = P + " Spine2"
        for n, (h, t) in pts.items():
            h2, t2 = h * unit + off, t * unit + off
            lines.append(' (local o = getNodeByName "%s" exact:true; if o != undefined do try (delete o) catch ())' % n)   # Max 2014: 구속 대상이던 본은 지워지면서 예외를 낼 때가 있음(지워지긴 함)
            lines.append(' (local b = BoneSys.createBone [%f,%f,%f] [%f,%f,%f] [0,0,1]; b.name = "%s"; b.width = 1.5; b.height = 1.5; '
                         'b.wirecolor = %s; b.parent = getNodeByName "%s" exact:true; lay.addNode b; made += 1)'
                         % (h2.x, h2.y, h2.z, t2.x, t2.y, t2.z, n, "(color 40 160 255)" if n.endswith("_L") else "(color 255 90 60)", par))
        lines.append(' "OK " + (made as string))')
        lines.append(")")
        try:
            msg += " | Max: " + mb.send("\n".join(lines), timeout=60)
        except Exception as e:
            msg += " | Max 실패: %s" % e
    return msg


class MSR_OT_breast_bones(bpy.types.Operator):
    """Rigify식 가슴 본(Bone_breast_L/R)을 Bip Spine2 아래 만들기 (블렌더 + Max에 동시에)"""
    bl_idname = "msr.breast_bones"
    bl_label = "가슴 본 추가 (Rigify식)"
    bl_options = {"REGISTER", "UNDO"}
    to_max: bpy.props.BoolProperty(name="Max에도 만들기", default=True)

    def execute(self, context):
        body = mesh_obj(context) or next((o for o in context.selected_objects if o.type == "MESH"), None)
        arm = armature_of(body) if body else None
        arm = arm or next((o for o in context.view_layer.objects if o.type == "ARMATURE" and bip_prefix(o)), None)
        if body is None or arm is None:
            self.report({"WARNING"}, "바디 메쉬를 선택하세요 (Bip 아마추어 필요)")
            return {"CANCELLED"}
        try:
            msg = add_breast_bones(arm, body, to_max=self.to_max)
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        _select_only(context, [body], body)
        context.window_manager.msr_status = msg
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class MSR_OT_bip_auto_weights(bpy.types.Operator):
    """Max에서 가져온 Bip 골격에 바로 자동 웨이트 (본 방향 보정, 트위스트 사용, 헬퍼·Nub 제외, 정점당 4본)"""
    bl_idname = "msr.bip_auto_weights"
    bl_label = "Bip 자동 웨이트 (바디)"
    bl_options = {"REGISTER", "UNDO"}
    use_twist: bpy.props.BoolProperty(name="트위스트 본 사용", default=True,
                                      description="Bone L UpperArm Twist/Twist1 등이 있으면 팔다리 본 대신 사용")
    limit: bpy.props.IntProperty(name="정점당 최대 본", default=4, min=1, max=8)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="Bip 자동 웨이트: 기존 바디 웨이트를 지우고 새로 넣어요")

    def execute(self, context):
        body = mesh_obj(context) or next((o for o in context.selected_objects if o.type == "MESH"), None)
        arm = armature_of(body) if body else None
        arm = arm or next((o for o in context.view_layer.objects if o.type == "ARMATURE" and bip_prefix(o)), None)
        if body is None or arm is None:
            self.report({"WARNING"}, "바디 메쉬를 선택하세요 (Bip 아마추어 필요)")
            return {"CANCELLED"}
        try:
            n, filled = bip_auto_weights(arm, body, use_twist=self.use_twist, limit=self.limit)
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        _select_only(context, [body], body)
        msg = "자동 웨이트: 본 %d개 | 열 확산 실패 보충 %d정점 | 다음: 웨이트 검사 → Max Skin에 적용" % (n, filled)
        context.window_manager.msr_status = msg
        self.report({"INFO"}, msg)
        return {"FINISHED"}


# ============================================================ simple flow: Max Bip -> Blender bones + weights -> Max Skin
FLOW_COL = "FromMax"
WEIGHT_BRUSHES = "brushes/essentials_brushes-mesh_weight.blend/Brush/"


def _obj(name, kind=None):
    o = bpy.data.objects.get(name) if name else None
    if o is not None and kind and o.type != kind:
        return None
    return o


def flow_objects(context):
    wm = context.window_manager
    return (_obj(wm.msr_arm, "ARMATURE"), _obj(wm.msr_body, "MESH"),
            _obj(wm.msr_face, "MESH"), _obj(wm.msr_tooth, "MESH"))


def flow_detect(context):
    """Guess Bip armature / body / face / tooth among the imported objects."""
    wm = context.window_manager
    col = bpy.data.collections.get(FLOW_COL)
    pool = list(col.objects) if col and len(col.objects) else list(context.view_layer.objects)
    arms = [o for o in pool if o.type == "ARMATURE" and bip_prefix(o)]
    meshes = [o for o in pool if o.type == "MESH" and not o.name.lower().startswith(("box", "point"))]
    face = next((o for o in meshes if "face" in o.name.lower()), None)
    tooth = next((o for o in meshes if any(k in o.name.lower() for k in ("tooth", "teeth"))), None)
    rest = [o for o in meshes if o not in (face, tooth)]
    body = next((o for o in rest if "body" in o.name.lower()), None) or \
        (max(rest, key=lambda o: len(o.data.vertices)) if rest else None)
    wm.msr_arm = arms[0].name if arms else ""
    wm.msr_body = body.name if body else ""
    wm.msr_face = face.name if face else ""
    wm.msr_tooth = tooth.name if tooth else ""


def limit_normalize(obj, limit=4, threshold=0.01):
    deform = deform_group_indices(obj)
    n = 0
    for v in obj.data.vertices:
        d = vweights(v, deform)
        if not d:
            continue
        items = sorted(d.items(), key=lambda kv: -kv[1])[:limit]
        items = [kv for kv in items if kv[1] >= threshold] or items[:1]
        new = normalize(dict(items))
        if set(new) != set(d) or any(abs(new[k] - d[k]) > 1e-5 for k in new):
            write_weights(obj, v.index, new, deform)
            n += 1
    return n


def weight_stats(obj, limit=4):
    deform = deform_group_indices(obj)
    zero = over = 0
    for v in obj.data.vertices:
        d = vweights(v, deform)
        if not d:
            zero += 1
        elif len(d) > limit:
            over += 1
    return zero, over


# ---------------------------------------------------------------- bones -> Max
def _max_xform(arm, mb, live=False):
    """Blender world -> Max world, measured on two Biped joints that exist in both (stored at import)."""
    if not live and arm.get("msr_mx"):
        u, x, y, z = list(arm["msr_mx"])
        return u, Vector((x, y, z))
    P = bip_prefix(arm)
    a_n, b_n = P + " Spine2", P + " Head"

    def mp(n):
        r = mb.send('(getNodeByName "%s" exact:true).transform.pos as string' % n, timeout=15)
        return Vector([float(x) for x in r.strip().strip('"')[1:-1].split(",")])
    va, vb = mp(a_n), mp(b_n)
    ba, bb = _wpos(arm, a_n), _wpos(arm, b_n)
    unit = (vb - va).length / max((bb - ba).length, 1e-9)
    return unit, va - ba * unit


def max_missing(mb, names):
    if not names:
        return []
    q = '(local r = ""; for n in #(%s) where (getNodeByName n exact:true) == undefined do r += n + "|"; r)' % \
        ",".join('"%s"' % n for n in names)
    r = mb.send(q, timeout=30).strip().strip('"')
    return [n for n in r.split("|") if n]


def _bone_color(n):
    if n.endswith("_L") or "_L_" in n:
        return "(color 40 160 255)"
    if n.endswith("_R") or "_R_" in n:
        return "(color 255 90 60)"
    return "(color 120 220 90)"


FACE_LAYER = "bone_head"   # Max layer for face bones (RigTools layer set; was "Face_Bones")


def push_bones_to_max(arm, names, mb, recreate=False):
    """Create Blender-made bones (face / breast) in Max with BoneSys, same names and parents."""
    bones = arm.data.bones
    names = [n for n in names if n in bones]
    todo = list(names) if recreate else max_missing(mb, names)
    if not todo:
        return 0
    todo.sort(key=lambda n: len(bones[n].parent_recursive))
    unit, off = _max_xform(arm, mb)
    mw = arm.matrix_world
    lines = ["(", " local made = 0"]
    hairb = set(arm.get("msr_ob_hair_bones", []))
    hairup = json.loads(arm.get("msr_ob_hair_up", "{}") or "{}")
    obn = set(arm.get("msr_ob_bones", [])) | hairb      # object / hair bones: Renderable off + Box
    obshape = json.loads(arm.get("msr_ob_shape", "{}") or "{}")
    hairshape = json.loads(arm.get("msr_ob_hair_shape", "{}") or "{}")

    def ob_extra(n, h, t):
        # ④ object bones: Renderable off + Box (RigTools rule), up vector not along the bone
        if n not in obn:
            return "", "[0,0,1]"
        up = "[0,-1,0]" if abs((t - h).normalized().z) > 0.9 else "[0,0,1]"
        if n in hairb:
            # hair bones like Melitta f05: Z axis level at the chain start, carried down the chain (hair_bones.UP_KEY)
            z = Vector(hairup[n]) if n in hairup else Vector((0, 0, 1)).cross((t - h).normalized())
            if z.length > 1e-3:
                up = "[%f,%f,%f]" % tuple(z.normalized())
        hs_ = hairshape.get(n)
        if hs_:   # 헤어: root·_00·_end 는 굵기 1·박스 끔, 움직이는 본은 메쉬 단면 크기·박스 켬
            return ("b.renderable = false; b.boxMode = %s; b.width = %f; b.height = %f; b.taper = %f; "
                    % ("true" if hs_["box"] else "false", hs_["w"], hs_["h"], hs_["taper"])), up
        ex = "b.renderable = false; b.boxMode = true; "
        sh = obshape.get(n)
        if not sh and re.search(r"(_root|_00|_end)$", n, re.I):
            # 치마·망토·기타도 헤어처럼 (10/30): root·_00(연결)·_end 는 굵기 1×1, Display as Box 끔
            return "b.renderable = false; b.boxMode = false; b.width = 1.0; b.height = 1.0; ", up
        if sh:   # Melitta preset: f05 roll and size
            up = "[%f,%f,%f]" % tuple(sh["up"])
            ex += "b.width = %f; b.height = %f; b.taper = %f; " % (sh["w"], sh["h"], sh["taper"])
        return ex, up

    def layer_of(n):
        # 세컨더리 본 구분 (2026-10-29): 헤어 bone_hair / 망토 bone_cape / 치마 bone_skirt / 그 밖의 오브젝트 본 bone_body
        if (n in hairb or n in obn) and n.lower().endswith("_end"):
            return "nub"                    # 끝 본(_end)은 nub 레이어 (사용자 요청 10/29)
        if n in hairb:
            return "bone_hair"
        if n in obn:
            low = n.lower()
            return "bone_body"              # 치마·망토·기타 본은 모두 bone_body (10/30). 헤어는 bone_hair
        return "Body_Bones" if "breast" in n else FACE_LAYER
    for lay in sorted({layer_of(n) for n in todo}):
        lines.append(' if LayerManager.getLayerFromName "%s" == undefined do LayerManager.newLayerFromName "%s"' % (lay, lay))
    for n in todo:
        b = bones[n]
        h = (mw @ b.head_local) * unit + off
        t = (mw @ b.tail_local) * unit + off
        w = max((t - h).length * 0.25, 0.3)
        lay = layer_of(n)
        par = b.parent.name if b.parent else ""
        ex, up = ob_extra(n, h, t)
        lines.append(' (local o = getNodeByName "%s" exact:true; if o != undefined do try (delete o) catch ())' % n)   # Max 2014: 구속 대상이던 본은 지워지면서 예외를 낼 때가 있음(지워지긴 함)
        lines.append(
            ' (local b = BoneSys.createBone [%f,%f,%f] [%f,%f,%f] %s; b.name = "%s"; b.width = %f; b.height = %f; '
            'b.wirecolor = %s; local pp = getNodeByName "%s" exact:true; if pp != undefined do b.parent = pp; '
            '%s%s(LayerManager.getLayerFromName "%s").addNode b; made += 1)'
            % (h.x, h.y, h.z, t.x, t.y, t.z, up, n, w, w, _bone_color(n), par,
               "b.taper = 0; " if lay == FACE_LAYER else "", ex, lay))   # face bones: box shape like the Melitta original
    lines.append(' redrawViews()')   # Max viewport shows the new bones right away
    lines.append(' "OK " + (made as string)')
    lines.append(")")
    r = mb.send("\n".join(lines), timeout=60)
    if not r.strip().strip('"').startswith("OK"):
        raise RuntimeError("Max 본 생성 실패: " + r)
    return len(todo)


def _flow_face_bone_names():
    return [e[0] for e in _mirror_tpl()] + ["Bone_jaw", "Bone_tongue_01", "Bone_tongue_02"]



# ============================================================ face rig v2: 45 bones (facerig_core)
# Overrides build_face_bones / face_auto_weights / _flow_face_bone_names defined above.
# Old 23-bone versions stay available as *_v23 (used automatically for old rigs).
_build_face_bones_v23 = build_face_bones
_face_auto_weights_v23 = face_auto_weights

FACE45_HEAD = "Bip01 Head"          # name used inside facerig_core for the head bone
FACE45_TONGUE = ["Bone_tongue_01", "Bone_tongue_02", "Bone_tongue_03"]
FACE45_MARK = "Bone_eye_L_up_in"    # present only in the 45-bone layout


def _face45_names():
    out = ["Bone_jaw", "Bone_chin", "Bone_lip_up", "Bone_lip_dn"]
    for s in ("L", "R"):
        out += ["Bone_lip_%s" % s, "Bone_lip_%s_up" % s, "Bone_lip_%s_up_out" % s, "Bone_lip_%s_dn" % s,
                "Bone_lip_%s_dn_out" % s, "Bone_nose_%s" % s, "Bone_sneer_%s" % s, "Bone_cheek_%s" % s,
                "Bone_cheek_%s_dn" % s, "Bone_brow_%s_in" % s, "Bone_brow_%s_mid" % s, "Bone_brow_%s_out" % s,
                "Bone_eyeball_%s" % s]
        for p in ("up", "dn"):
            out += ["Bone_eye_%s_%s_in" % (s, p), "Bone_eye_%s_%s" % (s, p), "Bone_eye_%s_%s_out" % (s, p)]
    return out + FACE45_TONGUE


def _flow_face_bone_names():
    return _face45_names()


def _np_mesh_world(obj):
    import numpy as np
    me = obj.data
    me.calc_loop_triangles()
    mw = obj.matrix_world
    P = np.array([tuple(mw @ v.co) for v in me.vertices], float)
    T = np.array([tuple(t.vertices) for t in me.loop_triangles], int)
    return P, T



LID_SNAP = True   # eyelid bone tips -> skin surface along the bone (eye sizes differ between characters)
_LID_BVH = {}


def _is_lid(n):
    return n.startswith("Bone_eye_") and n.endswith(("_up", "_dn", "_up_in", "_up_out", "_dn_in", "_dn_out"))


def _lid_tail(arm, face, n):
    """world tail of an eyelid bone; with LID_SNAP the tip is moved along the bone onto the face skin
    (the skin hit nearest to the original tip). Pivot / direction stay as placed."""
    from mathutils.bvhtree import BVHTree
    mw = arm.matrix_world
    b = arm.data.bones[n]
    h, t = mw @ b.head_local, mw @ b.tail_local
    if not LID_SNAP or face is None or (t - h).length < 1e-9:
        return t
    key = (face.name, len(face.data.vertices), tuple(round(x, 6) for x in face.matrix_world.translation))
    bvh = _LID_BVH.get(key)
    if bvh is None:
        fw = face.matrix_world
        bvh = BVHTree.FromPolygons([fw @ v.co for v in face.data.vertices], [tuple(p.vertices) for p in face.data.polygons])
        _LID_BVH.clear()
        _LID_BVH[key] = bvh
    d = (t - h).normalized()
    L = (t - h).length
    hits, o, far = [], h + d * 1e-5, L * 3.0
    for _ in range(12):
        loc, nrm, idx, dist = bvh.ray_cast(o, d, far)
        if loc is None:
            break
        hits.append(loc)
        o = loc + d * 1e-5
    if not hits:
        return t
    best = min(hits, key=lambda p: (p - t).length)
    return best

def _face45_guides(arm, head_name, face, tooth):
    """guide points (world) for facerig_core: existing bones first (artist-tuned), template for the rest."""
    import numpy as np
    mw = arm.matrix_world
    bones = arm.data.bones
    tpl, fr = face_bone_points(face, tooth)
    g = {FACE45_HEAD: np.array(tuple(mw @ bones[head_name].head_local))}
    need = ["Bone_jaw", "Bone_lip_L", "Bone_lip_R", "Bone_lip_up", "Bone_lip_dn", "Bone_lip_L_up", "Bone_lip_R_up",
            "Bone_lip_L_dn", "Bone_lip_R_dn", "Bone_cheek_L", "Bone_cheek_R", "Bone_brow_L_in", "Bone_brow_L_out",
            "Bone_brow_R_in", "Bone_brow_R_out", "Bone_eyeball_L", "Bone_eyeball_R",
            "Bone_eye_L_up", "Bone_eye_L_dn", "Bone_eye_R_up", "Bone_eye_R_dn"]
    has45 = FACE45_MARK in bones
    src = {}
    for n in need:
        if n in bones:
            b = bones[n]
            # 45 layout: lid bones pivot at the eyeball, the lid edge is the tail
            if has45 and n.startswith("Bone_eye_") and n.endswith(("_up", "_dn")):
                g[n] = np.array(tuple(_lid_tail(arm, face, n)))
            else:
                g[n] = np.array(tuple(mw @ b.head_local))
            src[n] = "bone"
        elif n in tpl:
            g[n] = np.array(tuple(tpl[n][0])); src[n] = "template"
    _eye_fix_guides(g, src, face)
    return g, src, fr


_EYE_FIT = {}          # last eyeball fit: side -> (centre, radius); used by _eye_scale
_EYE_OBJ = []          # separate eyeball meshes the last fit used (rigid skin to Bone_eyeball_L/R at send)


def _eye_objects(face):
    """separate eyeball meshes imported with the face (name has 'eye', e.g. Gisele_eye); lashes / brows fail the sphere fit"""
    col = bpy.data.collections.get(FLOW_COL)
    pool = list(col.objects) if col else list(bpy.context.view_layer.objects)
    return [o for o in pool if o.type == "MESH" and o is not face and "eye" in o.name.lower()
            and not any(k in o.name.lower() for k in ("brow", "lash"))]
EYE_WARN = []          # messages for the status line (flipped lid bones, moved pivots)


def _sphere_fit(Q):
    """least-squares sphere through points -> (centre, radius, rms error / radius) or None"""
    import numpy as np
    if len(Q) < 12:
        return None
    m = Q.mean(0)
    q = Q - m
    A = np.c_[2 * q, np.ones(len(q))]
    sol = np.linalg.lstsq(A, (q * q).sum(1), rcond=None)[0]
    r2 = sol[3] + sol[:3] @ sol[:3]
    if r2 <= 0:
        return None
    R = float(np.sqrt(r2))
    err = float(np.sqrt(np.mean((np.linalg.norm(q - sol[:3], axis=1) - R) ** 2))) / R
    return sol[:3] + m, R, err


def _eye_fix_guides(g, src, face):
    """eye guides that survive modelling changes:
    - eyeball pivot = centre of the eyeball element in the face mesh (not the old bone position)
    - eyelid guides: an 'up' tail below the eyeball (or 'dn' above) means the bones are flipped -> swap / drop"""
    import numpy as np
    _EYE_FIT.clear()
    del _EYE_OBJ[:]
    del EYE_WARN[:]
    P, T = _np_mesh_world(face)
    mesh = fc.Mesh(P, T)
    ed = abs(g["Bone_eyeball_L"][0] - g["Bone_eyeball_R"][0]) if "Bone_eyeball_L" in g and "Bone_eyeball_R" in g else None
    if not ed:
        return
    # eyeball pieces: small elements inside the face mesh (Melitta) or the elements of a separate eye mesh (Gisele_eye)
    cands = [(P[el], None) for el in mesh.elements() if not mesh.ismain[el[0]] and len(el) >= 12]
    for eo in _eye_objects(face):
        Pe, Te = _np_mesh_world(eo)
        cands += [(Pe[el], eo) for el in fc.Mesh(Pe, Te).elements() if len(el) >= 12]
    for side in ("L", "R"):
        k = "Bone_eyeball_%s" % side
        c0 = g[k]
        best = None
        for Q, eo in cands:
            if best and len(Q) <= best[3]:
                continue
            if np.linalg.norm(Q.mean(0) - c0) > 0.35 * ed:
                continue
            sf = _sphere_fit(Q)
            if sf is None or sf[2] > 0.1 or not (0.08 * ed < sf[1] < 0.5 * ed) or np.linalg.norm(sf[0] - c0) > 0.3 * ed:
                continue
            best = (sf[0], sf[1], sf[2], len(Q), eo)
        if best is not None:
            if best[4] is not None and best[4] not in _EYE_OBJ:
                _EYE_OBJ.append(best[4])
            mv = np.linalg.norm(best[0] - c0)
            g[k] = np.array(best[0]); src[k] = "eyeball mesh"
            _EYE_FIT[side] = (best[0], best[1])
            if mv > 0.05 * best[1]:
                EYE_WARN.append("%s 눈알 회전 중심을 눈알 메쉬 중심으로 %.1fmm 옮겨 계산" % (side, mv * 1000))
        ce = g[k]
        ku, kd = "Bone_eye_%s_up" % side, "Bone_eye_%s_dn" % side
        if ku in g and kd in g:
            # open upper lid edge sits about at eyeball-centre height: compare the two tips, not the centre
            bad_u = bad_d = g[ku][2] < g[kd][2]
        else:
            bad_u = ku in g and g[ku][2] < ce[2]
            bad_d = kd in g and g[kd][2] > ce[2]
        if bad_u and bad_d:
            g[ku], g[kd] = g[kd], g[ku]
            EYE_WARN.append("%s 눈꺼풀 본 위·아래가 뒤집혀 있어요 (웨이트는 바로잡아 계산) → Max '눈 본만 다시 맞추기' 후 다시 가져오기" % side)
        elif bad_u or bad_d:
            for kk, bad in ((ku, bad_u), (kd, bad_d)):
                if bad:
                    del g[kk]; src.pop(kk, None)
            EYE_WARN.append("%s 눈꺼풀 본 방향이 이상해서 기본 위치로 계산 → Max '눈 본만 다시 맞추기' 권장" % side)


def _eye_scale(L):
    """lid weights measured in eyeball radii when the eyeball was found in the mesh (eye sizes differ)."""
    L.eye_r = {side: r for side, (_, r) in _EYE_FIT.items()}
    return L


def build_face_bones(arm, head_name, face, tooth=None):
    """45 game face bones under the Bip head. Existing face bones are used as guides (keeps artist placement)."""
    import numpy as np
    g, src, fr = _face45_guides(arm, head_name, face, tooth)
    P, T = _np_mesh_world(face)
    mesh = fc.Mesh(P, T)
    L = _eye_scale(fc.Landmarks(g))
    B, _ = fc.build_layout(mesh, L)
    if tooth is not None:
        Pt, Tt = _np_mesh_world(tooth)
        try:
            fc.teeth_tongue(Pt, Tt, L, B)
        except Exception as e:
            print("tongue layout:", e)
    ren = {"Bone_tongue_1": "Bone_tongue_01", "Bone_tongue_2": "Bone_tongue_02", "Bone_tongue_3": "Bone_tongue_03"}
    B = {ren.get(n, n): dict(b, parent=ren.get(b["parent"], b["parent"])) for n, b in B.items()}
    inv = arm.matrix_world.inverted()
    ctx = bpy.context
    prev_active = ctx.view_layer.objects.active
    if ctx.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    _select_only(ctx, [arm], arm)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    for n, b in B.items():
        e = eb.get(n) or eb.new(n)
        e.head = inv @ Vector(tuple(b["head"]))
        e.tail = inv @ Vector(tuple(b["tail"]))
        if (e.tail - e.head).length < 1e-6:
            e.tail = e.head + Vector((0, -0.01, 0))
        e.roll = 0.0
        e.use_connect = False
        e.use_deform = True
    for n, b in B.items():
        par = head_name if b["parent"] == FACE45_HEAD else b["parent"]
        eb[n].parent = eb.get(par)
    bpy.ops.object.mode_set(mode="OBJECT")
    arm["msr_face_rig"] = "45"
    if prev_active:
        ctx.view_layer.objects.active = prev_active
    return list(B.keys()), fr


def _tooth_weights_v3(arm, head_name, tooth):
    """teeth: artist fix v3 (upper pieces -> head, lower pieces -> jaw) + tongue piece -> tongue chain."""
    import numpy as np
    bm = bmesh.new(); bm.from_mesh(tooth.data); bm.verts.ensure_lookup_table()
    mw = tooth.matrix_world
    isl, comps, seen = {}, [], set()
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, comp = [v], []
        seen.add(v.index)
        while stack:
            x = stack.pop(); comp.append(x.index)
            for e in x.link_edges:
                o2 = e.other_vert(x)
                if o2.index not in seen:
                    seen.add(o2.index); stack.append(o2)
        comps.append(comp)
    pts = {i: mw @ bm.verts[i].co for c in comps for i in c}
    bm.free()
    zall = [p.z for p in pts.values()]
    mid = (min(zall) + max(zall)) / 2
    infos = []
    for c in comps:
        zs = [pts[i].z for i in c]; ys = [pts[i].y for i in c]
        infos.append((c, sum(zs) / len(zs), min(zs), max(zs), sum(ys) / len(ys)))
    lower = [t for t in infos if t[1] < mid]
    tongue = None
    chain = [n for n in FACE45_TONGUE if n in arm.data.bones]
    if len(infos) >= 3 and lower and len(chain) == 3:
        tongue = max(lower, key=lambda t: t[4])[0]          # furthest back lower piece
    for m in [m for m in tooth.modifiers if m.type == "ARMATURE"]:
        tooth.modifiers.remove(m)
    tooth.modifiers.new("Armature", "ARMATURE").object = arm
    for vg in list(tooth.vertex_groups):
        tooth.vertex_groups.remove(vg)
    def put(n, i, w):
        gg = tooth.vertex_groups.get(n) or tooth.vertex_groups.new(name=n)
        gg.add([i], w, "REPLACE")
    amw = arm.matrix_world
    if tongue is not None:
        ky = [(amw @ arm.data.bones[n].head_local).y for n in chain]
        hp = fc.hat_partition(np.array([-pts[i].y for i in tongue]), [-y for y in ky])
        for r, i in enumerate(tongue):
            for k, n in enumerate(chain):
                if hp[r, k] > 0.005:
                    put(n, i, float(hp[r, k]))
    for c, cz, lo_z, hi_z, cy in infos:
        if c is tongue:
            continue
        top = lo_z + 0.6 * (hi_z - lo_z)
        for i in c:
            if cz >= mid:
                put(head_name, i, 1.0)
            elif pts[i].z <= top:
                put("Bone_jaw", i, 1.0)
            else:
                put("Bone_jaw", i, 0.9); put(head_name, i, 0.1)
    return len(tooth.vertex_groups)


def face_auto_weights(arm, head_name, face, tooth=None, limit=4):
    """45-bone rig: topology-aware weights (lip split, jaw field, rotating lids). Old rigs: v23 weights."""
    import numpy as np
    bones = arm.data.bones
    if FACE45_MARK not in bones:
        return _face_auto_weights_v23(arm, head_name, face, tooth, limit)
    mw = arm.matrix_world
    B = {}
    for n in _face45_names():
        if n in FACE45_TONGUE or n not in bones:
            continue
        b = bones[n]
        par = b.parent.name if b.parent else head_name
        tl = _lid_tail(arm, face, n) if _is_lid(n) else (mw @ b.tail_local)
        B[n] = dict(head=np.array(tuple(mw @ b.head_local)), tail=np.array(tuple(tl)),
                    parent=FACE45_HEAD if par == head_name else par, kind="pt")
    g, src, fr = _face45_guides(arm, head_name, face, tooth)
    P, T = _np_mesh_world(face)
    mesh = fc.Mesh(P, T)
    L = _eye_scale(fc.Landmarks(g))
    _, eyeinfo = fc.build_layout(mesh, L)
    W, names, dbg = fc.compute_weights(mesh, L, B, eyeinfo)
    # eye template (Melitta User eye weights, tools\eyeclose\eye_template.py)
    try:
        import sys as _sys
        # eye_template.py + eye_template_melitta.json: next to this add-on (deploy) or the work folder (dev)
        for _p in (os.path.dirname(os.path.abspath(__file__)), r"C:\claude\max_blender\tools\eyeclose"):
            if os.path.exists(os.path.join(_p, "eye_template.py")):
                if _p not in _sys.path:
                    _sys.path.insert(0, _p)
                break
        import eye_template as _et
        W, _log = _et.apply(fc, mesh, L, eyeinfo, W, names)
        EYE_WARN.append("눈 템플릿: " + _log)
    except Exception as _e:
        EYE_WARN.append("눈 템플릿 실패: %s" % _e)
    W = fc.finalize(W, maxinf=limit)
    for m in [m for m in face.modifiers if m.type == "ARMATURE"]:
        face.modifiers.remove(m)
    face.modifiers.new("Armature", "ARMATURE").object = arm
    for vg in list(face.vertex_groups):
        face.vertex_groups.remove(vg)
    used = 0
    for k, n in enumerate(names):
        idx = np.nonzero(W[:, k])[0]
        if not len(idx):
            continue
        vg = face.vertex_groups.new(name=head_name if n == FACE45_HEAD else n)
        for i in idx.tolist():
            vg.add([i], float(W[i, k]), "REPLACE")
        used += 1
    n_tooth = _tooth_weights_max45(arm, head_name, tooth, g) if tooth else 0
    return used, n_tooth


def _tooth_weights_max45(arm, head_name, tooth, g):
    """teeth: same rule as the Melitta 45-bone Max result (upper pieces -> head, lower -> jaw, tongue piece -> tongue chain)."""
    import numpy as np
    Pt, Tt = _np_mesh_world(tooth)
    L = fc.Landmarks(g)
    B = {}
    TW = fc.teeth_tongue(Pt, Tt, L, B)
    ren = {"Bone_tongue_1": "Bone_tongue_01", "Bone_tongue_2": "Bone_tongue_02", "Bone_tongue_3": "Bone_tongue_03",
           FACE45_HEAD: head_name}
    for m in [m for m in tooth.modifiers if m.type == "ARMATURE"]:
        tooth.modifiers.remove(m)
    tooth.modifiers.new("Armature", "ARMATURE").object = arm
    for vg in list(tooth.vertex_groups):
        tooth.vertex_groups.remove(vg)
    for n, w in TW.items():
        n = ren.get(n, n)
        if n not in arm.data.bones:
            continue
        idx = np.nonzero(w > 0.0005)[0]
        if not len(idx):
            continue
        vg = tooth.vertex_groups.new(name=n)
        for i in idx.tolist():
            vg.add([i], float(round(w[i], 4)), "REPLACE")
    return len(tooth.vertex_groups)


# ---------------------------------------------------------------- skeleton fitting in Blender -> Max Biped (BipFit)
TWIST_SETS = [("Bone %s UpperArm Twist", "UpperArm", "Forearm"), ("Bone %s UpperArm Twist1", "UpperArm", "Forearm"),
              ("Bone %s ForeArm Twist", "Forearm", "Hand"), ("Bone %s ForeArm Twist1", "Forearm", "Hand"),
              ("Bone %s Thigh Twist", "Thigh", "Calf"), ("Bone %s Thigh Twist1", "Thigh", "Calf"),
              ("Bone %s Calf Twist", "Calf", "Foot"), ("Bone %s Calf Twist1", "Calf", "Foot")]
CHAIN_PRIORITY = ("Spine", "Neck", "Head", "UpperArm", "Forearm", "Hand", "Finger2", "Finger1", "Calf", "Foot", "Toe0")


def store_max_xform(arm, mb):
    """Remember Blender->Max mapping right after import (before any joint is moved)."""
    unit, off = _max_xform(arm, mb, live=True)
    arm["msr_mx"] = [unit, off.x, off.y, off.z]


def _is_bip(arm, n):
    P = bip_prefix(arm)
    return P is not None and n.startswith(P + " ")


def bip_chain(arm):
    """primary child of every Biped bone (to draw/drag it as a joint chain)."""
    P = bip_prefix(arm)
    out = {}
    for b in arm.data.bones:
        if not _is_bip(arm, b.name) or b.name in (P, P + " Pelvis"):
            continue
        kids = [c for c in b.children if _is_bip(arm, c.name)]
        if not kids:
            continue
        pick = None
        if len(kids) == 1:
            pick = kids[0]
        else:
            for key in CHAIN_PRIORITY:
                pick = next((c for c in kids if c.name.endswith(" " + key) or c.name.endswith(key)), None)
                if pick:
                    break
        if pick is None:
            pick = next((c for c in kids if c.name.startswith(b.name)), kids[0])
        out[b.name] = pick.name
    return out



def _leaf_tail(arm, name, heads, tipf=0.85):
    """Estimated end point (world) for a Biped end link that has no Nub: finger tips, toe, head."""
    B = arm.data.bones
    b = B[name]
    h = heads[name]
    p = b.parent
    if p is None or p.name not in heads:
        return h + Vector((0, 0, 0.05))
    d = h - heads[p.name]
    if name.endswith(" Head"):
        return h + Vector((0, 0, 1)) * max(d.length * 2.2, 0.05)
    if name.endswith("Toe0"):
        flat = Vector((d.x, d.y, 0))
        if flat.length < 1e-6:
            flat = Vector((0, -1, 0))
        return h + flat.normalized() * max(d.length * 0.5, 0.02)
    if d.length < 1e-9:
        return h + Vector((0, 0, 0.01))
    return h + d * tipf


def _leaf_names(arm):
    chain = bip_chain(arm)
    P = bip_prefix(arm)
    return [b.name for b in arm.data.bones if _is_bip(arm, b.name) and "Nub" not in b.name
            and b.name not in chain and b.name not in (P, P + " Pelvis")
            and (b.name.endswith((" Head", "Toe0")) or "Finger" in b.name)]


def fit_enter(context, arm):
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    mw = arm.matrix_world
    arm["msr_fit0"] = json.dumps({b.name: list(mw @ b.head_local) for b in arm.data.bones})
    arm.data.pose_position = "REST"
    arm.show_in_front = True
    arm.data.display_type = "OCTAHEDRAL"
    _select_only(context, [arm], arm)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    chain = bip_chain(arm)
    inv = arm.matrix_world.inverted()
    heads = {e.name: mw @ e.head for e in eb}
    leaves = set(_leaf_names(arm))
    order = sorted(eb, key=lambda e: len(e.parent_recursive))
    for e in order:
        c = chain.get(e.name)
        if c and c in eb:
            e.tail = eb[c].head.copy()
            eb[c].use_connect = True
        elif e.name in leaves:
            e.tail = inv @ _leaf_tail(arm, e.name, heads)
        elif _is_bip(arm, e.name) and e.parent is not None and "Nub" in e.name:
            d = (e.head - e.parent.head)
            e.tail = e.head + (d.normalized() * max(d.length * 0.35, 0.005) if d.length > 1e-6 else Vector((0, 0, 0.01)))
    P = bip_prefix(arm)
    for s in "LR":
        for t, _, _ in TWIST_SETS:
            e = eb.get(_bone_ci(arm, t % s))
            if e:
                e.hide = True
    try:
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    except Exception:
        pass


def fit_exit(context, arm):
    """Leave edit mode; slide twist bones along their (moved) limb in Blender too."""
    if context.mode == "EDIT_ARMATURE":
        bpy.ops.object.mode_set(mode="OBJECT")
    raw = arm.get("msr_fit0")
    if not raw:
        return
    old = {k: Vector(v) for k, v in json.loads(raw).items()}
    P = bip_prefix(arm)
    inv = arm.matrix_world.inverted()
    mw = arm.matrix_world
    now = {b.name: mw @ b.head_local for b in arm.data.bones}
    moves = {}
    for s in "LR":
        for t, a, b in TWIST_SETS:
            tn, an, bn = _bone_ci(arm, t % s), "%s %s %s" % (P, s, a), "%s %s %s" % (P, s, b)
            if tn in old and an in old and bn in old and an in now and bn in now:
                ab = old[bn] - old[an]
                if ab.length < 1e-9:
                    continue
                f = (old[tn] - old[an]).dot(ab) / ab.dot(ab)
                moves[tn] = now[an] + (now[bn] - now[an]) * f
    if moves:
        _select_only(context, [arm], arm)
        bpy.ops.object.mode_set(mode="EDIT")
        eb = arm.data.edit_bones
        for tn, p in moves.items():
            e = eb.get(tn)
            if e:
                e.hide = False
                d = e.tail - e.head
                e.head = inv @ p
                e.tail = e.head + d
        bpy.ops.object.mode_set(mode="OBJECT")
    for b in arm.data.bones:
        b.hide = False


def fit_mirror(arm, src="L"):
    """Copy one side's joints to the other side (mirror on X around the pelvis)."""
    eb = arm.data.edit_bones
    P = bip_prefix(arm)
    mw = arm.matrix_world
    inv = mw.inverted()
    cx = (mw @ eb[P + " Pelvis"].head).x if (P + " Pelvis") in eb else 0.0
    mir = lambda v: inv @ Vector((2 * cx - (mw @ v).x, (mw @ v).y, (mw @ v).z))
    done = 0
    for e in sorted(eb, key=lambda x: len(x.parent_recursive)):
        other = flip_name(e.name)
        if other == e.name or other not in eb:
            continue
        side = re.search(r"(?<![A-Za-z0-9])([LR])(?![A-Za-z0-9])", e.name)
        if not side or side.group(1) != src:
            continue
        o = eb[other]
        h, t = e.head.copy(), e.tail.copy()
        o.head = mir(h)
        o.tail = mir(t)
        done += 1
    return done


def _fit_points(arm):
    """(Biped part, head, tail) in Blender world for every link BipFit uses."""
    P = bip_prefix(arm)
    mw = arm.matrix_world
    B = arm.data.bones
    chain = bip_chain(arm)
    leaves = set(_leaf_names(arm))
    heads = {x.name: mw @ x.head_local for x in B}
    out = []
    for b in B:
        if not _is_bip(arm, b.name) or "Nub" in b.name or b.name in (P, P + " Pelvis"):
            continue
        h = mw @ b.head_local
        c = chain.get(b.name)
        if c and c in B:
            t = mw @ B[c].head_local
        elif b.name in leaves:
            # after fitting in Blender the end point is the (draggable) tail, otherwise estimate it
            t = (mw @ b.tail_local) if arm.get("msr_fit0") else _leaf_tail(arm, b.name, heads)
        else:
            continue
        out.append((b.name[len(P) + 1:], h, t))
    return out


def _ms_v(v):
    return "[%f,%f,%f]" % (v.x, v.y, v.z)


def fit_apply_to_max(arm, mb, extra_bones=()):
    """Fit the Max Biped to the Blender joints with BipFit (figure mode), keep twist bones on their limbs,
    move face/breast bones, and rebind every Skin so meshes keep their shape."""
    P = bip_prefix(arm)
    unit, off = _max_xform(arm, mb)
    X = lambda v: v * unit + off
    mw = arm.matrix_world
    L = ["(", ' if BipFit == undefined do throw "BipFit.ms가 Max에 없어요 (scripts\\\\startup)"',
         ' local bp = getNodeByName "%s" exact:true' % P,
         ' if bp == undefined do throw "Max에 %s가 없어요"' % P,
         " local selSave = selection as array",
         " local ctl = bp.controller",
         " local wasFig = ctl.figureMode",
         " local sks = #()",
         " for o in objects do for m in o.modifiers where classOf m == Skin do append sks m",
         " local fits = #()",
         " try (",
         " for m in sks do try (m.always_deform = false) catch()",
         " local tw = #(%s)" % ",".join(
             '#("%s","%s %s %s","%s %s %s")' % (t % s, P, s, a, P, s, b) for s in "LR" for t, a, b in TWIST_SETS),
         " local twf = for e in tw collect (local t = getNodeByName e[1] exact:true; local a = getNodeByName e[2] exact:true; "
         "local b = getNodeByName e[3] exact:true; if t == undefined or a == undefined or b == undefined then undefined else "
         "(local ab = b.transform.pos - a.transform.pos; (dot (t.transform.pos - a.transform.pos) ab) / (dot ab ab)))",
         " ctl.figureMode = true"]
    for part, h, t in _fit_points(arm):
        hm, tm = X(h), X(t)
        d = (tm - hm)
        up = "[0,1,0]" if d.length > 1e-9 and abs(d.normalized().z) > 0.9 else "[0,0,1]"
        L.append(' (local n = BoneSys.createBone %s %s %s; n.name = "FIT %s"; append fits n)' % (_ms_v(hm), _ms_v(tm), up, part))
    toe = [(h, t) for part, h, t in _fit_points(arm) if part == "L Toe0"]
    if toe:
        L.append(" BipFit.prevToe = %f" % ((toe[0][1] - toe[0][0]).length * unit))
    L += [' local lg = BipFit.fit bp 2 prefix:"FIT"',
          " for n in fits do delete n",
          " for i = 1 to tw.count where twf[i] != undefined do try (local t = getNodeByName tw[i][1] exact:true; "
          "local a = getNodeByName tw[i][2] exact:true; local b = getNodeByName tw[i][3] exact:true; "
          "t.pos = a.transform.pos + (b.transform.pos - a.transform.pos) * twf[i]) catch()"]
    B = arm.data.bones
    for n in sorted([n for n in extra_bones if n in B], key=lambda n: len(B[n].parent_recursive)):
        # position only: keep the Max bone's own rotation/length (FBX tails are not meaningful)
        L.append(' (local b = getNodeByName "%s" exact:true; if b != undefined do try (b.pos = %s) catch())'
                 % (n, _ms_v(X(mw @ B[n].head_local))))
    # stay in figure mode: the fitted base pose lives there (animation keys would show the old pose)
    L += [" for m in sks do try (m.always_deform = true) catch()",
          " ctl.figureMode = true",
          " clearSelection(); for o in selSave where isValidNode o do selectMore o",
          ' "OK " + (if lg == undefined then "" else lg)',
          " ) catch (",
          "  local err = getCurrentException()",
          "  for n in fits where isValidNode n do delete n",
          "  for m in sks do try (m.always_deform = true) catch()",
          "  try (ctl.figureMode = wasFig) catch()",
          '  "ERROR " + err)',
          ")"]
    r = mb.send("\n".join(L), timeout=180)
    if not r.strip().strip('"').startswith("OK"):
        raise RuntimeError(r[:300])
    return r.strip().strip('"')[3:].strip()


class MSR_OT_flow_fit(bpy.types.Operator):
    """골격 맞추기: 관절(본 끝 구)을 클릭하고 W로 끌어서 모델에 맞춰요. 다시 누르면 종료"""
    bl_idname = "msr.flow_fit"
    bl_label = "골격 맞추기"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        wm = context.window_manager
        arm = flow_objects(context)[0]
        if arm is None:
            self.report({"WARNING"}, "Bip이 없어요. 먼저 'Max에서 가져오기'")
            return {"CANCELLED"}
        if context.mode == "EDIT_ARMATURE" and context.active_object is arm:
            fit_exit(context, arm)
            wm.msr_status = "골격 맞추기 끝 | 다음: 'Max Biped에 적용'"
            return {"FINISHED"}
        fit_enter(context, arm)
        wm.msr_status = "골격 맞추기 | 관절(구) 클릭 → W로 끌기 | 한쪽 맞춘 뒤 L→R 복사"
        return {"FINISHED"}


class MSR_OT_flow_fit_mirror(bpy.types.Operator):
    """한쪽에서 맞춘 관절을 반대쪽에 대칭 복사"""
    bl_idname = "msr.flow_fit_mirror"
    bl_label = "좌우 복사"
    bl_options = {"REGISTER", "UNDO"}
    src: bpy.props.StringProperty(default="L")

    def execute(self, context):
        arm = flow_objects(context)[0]
        if arm is None or context.mode != "EDIT_ARMATURE":
            self.report({"WARNING"}, "골격 맞추기 중에 쓰세요")
            return {"CANCELLED"}
        n = fit_mirror(arm, self.src)
        context.window_manager.msr_status = "%s → %s 복사: 본 %d개" % (self.src, "R" if self.src == "L" else "L", n)
        return {"FINISHED"}


class MSR_OT_flow_fit_apply(bpy.types.Operator):
    """맞춘 관절 위치로 Max Biped를 맞추고(피규어 모드, BipFit) 다시 가져와요. 스킨은 모양 유지한 채 다시 바인드"""
    bl_idname = "msr.flow_fit_apply"
    bl_label = "Max Biped에 적용"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self, event, title="Max Biped 관절을 이 위치로 맞춰요",
            message="Max Biped는 피규어 모드로 남아요 (Ctrl+Z 가능). 적용 후 다시 가져와요.")

    def execute(self, context):
        wm = context.window_manager
        arm = flow_objects(context)[0]
        mb = _max_bridge()
        if arm is None or mb is None:
            self.report({"WARNING"}, "Bip 또는 Max Bridge가 없어요")
            return {"CANCELLED"}
        if context.mode == "EDIT_ARMATURE":
            fit_exit(context, arm)
        elif context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        extra = [n for n in _flow_face_bone_names() + ["Bone_breast_L", "Bone_breast_R"] if n in arm.data.bones]
        try:
            lg = fit_apply_to_max(arm, mb, extra)
        except Exception as e:
            wm.msr_status = "Max 적용 실패 | %s" % str(e)[:250]
            self.report({"ERROR"}, wm.msr_status)
            return {"CANCELLED"}
        r = bpy.ops.msr.flow_import()
        warn = [l for l in lg.replace("\\n", "\n").splitlines() if l.strip()]
        tail = (" | " + " | ".join(warn[:3])) if warn else ""
        if "FINISHED" in r:
            wm.msr_status = "Max Biped 맞춤 완료 → 다시 가져옴%s | 다음: 자동 웨이트" % tail
        else:
            wm.msr_status = "Max Biped 맞춤 완료 (다시 가져오기는 실패: ① 가져오기를 눌러 주세요)%s" % tail
        return {"FINISHED"}



def pull_bones_from_max(arm, mb, names):
    """Bones that exist in Max but not in the Blender armature: create them at Max's position (same parent)."""
    names = [n for n in names if n not in arm.data.bones]
    if not names:
        return 0
    q = ('(local r = ""; for n in #(%s) do (local o = getNodeByName n exact:true; if o != undefined do '
         '(local h = o.transform.pos; local t = h + o.transform.row1 * (try (o.length) catch (2.0)); '
         'r += n + "|" + (if o.parent != undefined then o.parent.name else "") + "|" + (h.x as string) + "," + (h.y as string) + "," + (h.z as string) '
         '+ "|" + (t.x as string) + "," + (t.y as string) + "," + (t.z as string) + ";")); r)') % ",".join('"%s"' % n for n in names)
    r = mb.send(q, timeout=30).strip().strip('"')
    unit, off = _max_xform(arm, mb)
    recs = []
    for item in r.split(";"):
        p = item.split("|")
        if len(p) == 4:
            h = (Vector([float(x) for x in p[2].split(",")]) - off) / unit
            t = (Vector([float(x) for x in p[3].split(",")]) - off) / unit
            recs.append((p[0], p[1], h, t))
    if not recs:
        return 0
    ctx = bpy.context
    if ctx.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    prev = ctx.view_layer.objects.active
    _select_only(ctx, [arm], arm)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    inv = arm.matrix_world.inverted()
    for n, par, h, t in recs:
        b = eb.get(n) or eb.new(n)
        b.head, b.tail = inv @ h, inv @ t
        if (b.tail - b.head).length < 1e-6:
            b.tail = b.head + Vector((0, 0, 0.01))
        b.use_deform = True
    for n, par, h, t in recs:
        if par and par in eb:
            eb[n].parent = eb[par]
    bpy.ops.object.mode_set(mode="OBJECT")
    if prev:
        ctx.view_layer.objects.active = prev
    return len(recs)




def fix_leaf_bones_from_max(arm, mb):
    """FBX gives end bones (face, breast, nub-less bones) a default length. Set their tails from the Max bone
    (pos + X axis * length) when the direction already matches, so only the length changes (rest rotation and
    animation stay the same)."""
    bones = arm.data.bones
    leaves = [b.name for b in bones if not b.children and "Nub" not in b.name and not b.name.startswith("Bip0")]
    if not leaves:
        return 0
    q = ('(local r = ""; for n in #(%s) do (local o = getNodeByName n exact:true; '
         'if o != undefined and classOf o == BoneGeometry do (local h = o.transform.pos; local t = h + o.transform.row1 * o.length; '
         'r += n + "|" + (t.x as string) + "," + (t.y as string) + "," + (t.z as string) + ";")); r)') % ",".join('"%s"' % n for n in leaves)
    r = mb.send(q, timeout=30).strip().strip('"')
    unit, off = _max_xform(arm, mb)
    want = {}
    for item in r.split(";"):
        p = item.split("|")
        if len(p) == 2:
            want[p[0]] = (Vector([float(x) for x in p[1].split(",")]) - off) / unit
    if not want:
        return 0
    ctx = bpy.context
    if ctx.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    prev = ctx.view_layer.objects.active
    _select_only(ctx, [arm], arm)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    inv = arm.matrix_world.inverted()
    n = 0
    for name, tw in want.items():
        e = eb.get(name)
        if e is None:
            continue
        cur = e.tail - e.head
        new = inv @ tw - e.head
        if cur.length < 1e-9 or new.length < 1e-9:
            continue
        if cur.normalized().dot(new.normalized()) > 0.9995:       # same direction (< ~1.8 deg): length only
            e.tail = e.head + cur.normalized() * new.length
            n += 1
        elif _is_lid(name) or name.startswith("Bone_eyeball_"):
            # eye bones: the Max direction is data (lid weights use the tail) -> take the Max tail as is
            e.tail = e.head + new
            n += 1
    bpy.ops.object.mode_set(mode="OBJECT")
    if prev:
        ctx.view_layer.objects.active = prev
    return n

# ---------------------------------------------------------------- operators
class MSR_OT_flow_import(bpy.types.Operator):
    """Max에서 선택한 바디·얼굴·이·Bip을 가져오고 자동으로 찾아 둡니다"""
    bl_idname = "msr.flow_import"
    bl_label = "Max에서 가져오기"

    def execute(self, context):
        wm = context.window_manager
        mb = _max_bridge()
        if mb is None:
            wm.msr_status = "Max Bridge 애드온이 꺼져 있어요"
            return {"CANCELLED"}
        try:
            n = mb.send("selection.count as string", timeout=10).strip().strip('"')
        except Exception as e:
            wm.msr_status = "Max 연결 실패 | Max가 켜져 있는지 확인하세요 | %s" % str(e)[:120]
            self.report({"ERROR"}, "Max 연결 실패")
            return {"CANCELLED"}
        if n == "0":
            # nothing selected in Max: re-select what was imported last time (meshes/helpers + whole Bip hierarchy)
            col = bpy.data.collections.get(FLOW_COL)
            names = [o.name for o in col.objects] if col else []
            got = "0"
            if names:
                q = ('(clearSelection(); for n in #(%s) do (local o = getNodeByName n exact:true; if o != undefined do '
                     '(selectMore o; if classOf o == Biped_Object or n == o.name do (for c in (execute ("$\'" + o.name + "\'...*")) do selectMore c))); '
                     'selection.count as string)') % ",".join('"%s"' % x.replace('"', "") for x in names)
                try:
                    got = mb.send(q, timeout=30).strip().strip('"')
                except Exception as e:
                    print("reselect:", e)
            if got in ("0", ""):
                wm.msr_status = "Max에서 바디·얼굴·이·Bip을 먼저 선택하세요"
                self.report({"WARNING"}, wm.msr_status)
                return {"CANCELLED"}
        try:
            # always take the whole Biped hierarchy (face / breast / twist bones live under it)
            mb.send('(local roots = #(); for o in selection where classOf o == Biped_Object do appendIfUnique roots o.controller.rootNode; '
                    'for r in roots do for c in (execute ("$\'" + r.name + "\'...*")) do selectMore c; selection.count as string)', timeout=30)
        except Exception as e:
            print("hierarchy select:", e)
        try:
            # separate eyeball mesh (Gisele_eye): visible geometry named *eye* near the selected face
            mb.send('(local fs = for o in selection where matchPattern o.name pattern:"*face*" and superClassOf o == GeometryClass collect o; '
                    'for f in fs do for o in geometry where matchPattern o.name pattern:"*eye*" and not o.isHiddenInVpt '
                    'and not (isKindOf o Biped_Object) and classOf o != BoneGeometry and not o.isSelected '
                    'and distance o.center f.center < length (f.max - f.min) do selectMore o; selection.count as string)', timeout=30)
        except Exception as e:
            print("eye select:", e)
        try:
            # hair mesh (melitta_hair): when none is selected, the visible *hair* geometry nearest the selected face
            mb.send('(local fs = for o in selection where matchPattern o.name pattern:"*face*" and superClassOf o == GeometryClass collect o; '
                    'if fs.count > 0 and (for o in selection where matchPattern o.name pattern:"*hair*" and superClassOf o == GeometryClass '
                    'and classOf o != BoneGeometry and not (isKindOf o Biped_Object) collect o).count == 0 do ('
                    'local best = undefined; local bd = 1e9; for f in fs do for o in geometry where matchPattern o.name pattern:"*hair*" '
                    'and not o.isHiddenInVpt and not (isKindOf o Biped_Object) and classOf o != BoneGeometry do ('
                    'local d = distance o.center f.center; if d < bd and d < 2 * length (f.max - f.min) do (best = o; bd = d)); '
                    'if best != undefined do selectMore best); selection.count as string)', timeout=30)
        except Exception as e:
            print("hair select:", e)
        try:
            r = bpy.ops.maxbridge.from_max()
        except Exception as e:
            wm.msr_status = "가져오기 실패 | %s" % str(e)[:200]
            self.report({"ERROR"}, wm.msr_status)
            return {"CANCELLED"}
        if "FINISHED" not in r:
            wm.msr_status = "가져오기 취소됨"
            return {"CANCELLED"}
        flow_detect(context)
        arm, body, face, tooth = flow_objects(context)
        ncarry = _carry_ob_props(arm)
        if arm:
            arm.show_in_front = True
            try:
                store_max_xform(arm, mb)
            except Exception as e:
                print("max xform:", e)
            nfix = 0
            try:
                nfix = fix_leaf_bones_from_max(arm, mb)
                if nfix and hasattr(mb, "cv_apply"):
                    # bone shapes were drawn at import with the FBX default length: redraw with the real lengths
                    hide = True
                    try:
                        hide = not context.scene.maxbridge.show_helpers
                    except Exception:
                        pass
                    mb.cv_apply(arm.name, hide_helpers=hide)
            except Exception as e:
                print("leaf bones:", e)
            if _hb is not None:
                try:
                    _hb.import_boxes(arm, mb)       # 2.2: 헤어 본은 Max 박스 굵기 모양으로
                except Exception as e:
                    print("hair boxes:", e)
        else:
            nfix = 0
        wm.msr_status = "가져오기 완료 | Bip: %s | 바디: %s | 얼굴: %s | 이: %s" % tuple(
            o.name if o else "없음" for o in (arm, body, face, tooth)) + (" | 끝 본 길이 %d개 Max에 맞춤" % nfix if nfix else "") + (
            " | 파츠·헤어 본 정보 이어받음 (본 %d개)" % ncarry if ncarry else "")
        return {"FINISHED"}


def _carry_ob_props(arm):
    """a re-import from Max makes a new armature: carry the ④ object bone info (msr_ob_*) over from the previous one
    (renamed *_이전 by the import). Returns the number of object bones carried (0 = nothing to do)"""
    if arm is None or arm.get("msr_ob_bones") or arm.get("msr_ob_hair_bones"):
        return 0

    def age(o):
        t = o.name[len(arm.name) + len("_이전"):]
        return int(t) if t.isdigit() else 1
    olds = [o for o in bpy.data.objects if o is not arm and o.type == "ARMATURE" and o.name.startswith(arm.name + "_이전")
            and (o.get("msr_ob_bones") or o.get("msr_ob_hair_bones"))]
    if not olds:
        return 0
    old = max(olds, key=age)              # the import names the newest previous copy with the highest number
    for k in list(old.keys()):
        if k.startswith("msr_ob_"):
            v = old[k]
            arm[k] = list(v) if hasattr(v, "to_list") or isinstance(v, (list, tuple)) else v
    n = 0
    for k in ("msr_ob_bones", "msr_ob_hair_bones"):     # ④ object bones, hair bones
        if k in arm:
            arm[k] = [b for b in arm[k] if b in arm.data.bones]
            n += len(arm[k])
    return n


def _result_popup(context, title, lines, icon="INFO"):
    """result box in the middle of the screen (stays until the mouse leaves it); skipped when running without UI"""
    if bpy.app.background or context.window is None:
        return

    def draw(menu, ctx):
        for s in lines:
            menu.layout.label(text=s)
    context.window_manager.popup_menu(draw, title=title, icon=icon)


class MSR_OT_flow_bones(bpy.types.Operator):
    """얼굴 본 45개 + 가슴 본 2개를 블렌더와 Max에 만들기 (예전 23개 구조는 자동으로 45개로 업그레이드, 위치는 유지)"""
    bl_idname = "msr.flow_bones"
    bl_label = "얼굴·가슴 본 추가"
    bl_options = {"REGISTER", "UNDO"}
    face: bpy.props.BoolProperty(name="얼굴 본", default=True)
    breast: bpy.props.BoolProperty(name="가슴 본", default=True)
    rebuild: bpy.props.BoolProperty(name="이미 있어도 새로 만들기", default=False,
                                    description="끄면 Max에서 가져온 본(직접 맞춘 위치)을 그대로 씁니다")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="얼굴·가슴 본 추가 (블렌더 + Max)")

    def execute(self, context):
        wm = context.window_manager
        arm, body, face, tooth = flow_objects(context)
        if arm is None:
            self.report({"WARNING"}, "Bip이 없어요. 먼저 'Max에서 가져오기'")
            return {"CANCELLED"}
        msgs, made = [], []
        bones = arm.data.bones
        try:
            if self.face and face:
                if self.rebuild or FACE45_MARK not in bones:
                    names, _ = build_face_bones(arm, _find_head_bone(arm), face, tooth)
                    made += names
                    msgs.append("얼굴 본 %d개 만듦 (Max bone_head 레이어)" % len(names))
                else:
                    msgs.append("얼굴 본 이미 있음 (그대로 사용, Max bone_head 레이어)")
            if self.breast and body:
                if self.rebuild or "Bone_breast_L" not in bones:
                    add_breast_bones(arm, body, to_max=False)
                    made += ["Bone_breast_L", "Bone_breast_R"]
                if _bast_pairs(arm):
                    msgs.append("가슴 본: 장면에 bone_bast_l·r 이 있어 새로 안 만듦 → Max bone_helper 레이어의 bone_bast_l·r 사용, 웨이트는 '3. Max에 스킨 적용' 때 들어감")
                else:
                    msgs.append("가슴 본: bone_bast 없음 → 메시 기준 Bone_breast_L/R (Max에도 만듦, Body_Bones 레이어)")
        except Exception as e:
            wm.msr_status = "본 만들기 실패 | %s" % str(e)[:200]
            self.report({"ERROR"}, wm.msr_status)
            wm.msr_bones_last = "실패: %s" % str(e)[:120]
            _result_popup(context, "② 얼굴·가슴 본: 실패", msgs + ["실패: %s" % str(e)[:200]], "ERROR")
            return {"CANCELLED"}
        mb = _max_bridge()
        want = [n for n in _flow_face_bone_names() + ["Bone_breast_L", "Bone_breast_R"] if n in arm.data.bones]
        if _bast_pairs(arm):
            # Max already has the breast bones (bone_bast_l/r): no Bone_breast in Max, weights are mapped on send
            made = [n for n in made if n not in BREAST_BAST]
            want = [n for n in want if n not in BREAST_BAST]
        if mb is not None:
            try:
                k = push_bones_to_max(arm, made, mb, recreate=True) if made else 0
                k += push_bones_to_max(arm, [n for n in want if n not in made], mb)
                msgs.append("Max에 본 %d개 만듦" % k if k else "Max 본 이미 있음")
            except Exception as e:
                msgs.append("Max 본 생성 실패: %s" % str(e)[:150])
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        wm.msr_status = " | ".join(msgs) + " | 다음: 자동 웨이트"
        self.report({"INFO"}, wm.msr_status)
        wm.msr_bones_last = " | ".join(msgs)
        _result_popup(context, "② 얼굴·가슴 본 결과", msgs + ["다음: ③ 자동 웨이트"])
        return {"FINISHED"}




_LOWARM_RE = re.compile(r"(forearm|foretwist|hand|finger|elbow)", re.I)
_ARM_RE = re.compile(r"(upperarm|uparm|forearm|foretwist|hand|finger|elbow)", re.I)   # 조각 판단: 팔 전체
_HIP_RE = re.compile(r"(pelvis|spine$|waist|thigh|calf|hip|leg_)", re.I)
FIX_ISLAND = 300      # 이보다 작은 조각은 붙은 곳 웨이트로 통째로 (장식이 팔에 끌려가지 않게)
FIX_ISLAND_LEG = 100  # 이보다 작은 장식 조각이 다리(허벅지)와 몸통(Spine·허리)을 같이 따르면 찢어짐 → 통째로 (10/30)
_LEG_RE = re.compile(r"(thigh|calf|knee|leg_)", re.I)
_TORSO_RE = re.compile(r"(spine|waist|bast|breast)", re.I)


def _fix_arm_hip_mix(arm, body, skip=()):
    """10/30: 팔을 내린(A 포즈) 캐릭터에서 엉덩이 옆 장식·치마 정점이 템플릿에서 아래팔(forearm·hand·elbow) 웨이트를 받아
    팔을 들면 찢어지는 것 막기.
    - 아래팔 + 허리·다리 웨이트가 같이 있는 작은 조각(FIX_ISLAND 미만): 다른 조각과 가장 가까이 붙은 정점의 웨이트를 조각 전체에
    - 그 밖의 정점 중 아래팔 + 허리·다리가 섞인 정점: 아래팔 웨이트만 빼고 다시 합 1
    skip = 치마·망토 파트 정점 (그쪽 웨이트는 따로). returns (고친 조각 수, 고친 정점 수)"""
    from mathutils.kdtree import KDTree
    import numpy as np
    me = body.data
    nv = len(me.vertices)
    names = {g.index: g.name for g in body.vertex_groups}
    deform = {g.index for g in body.vertex_groups if g.name in arm.data.bones and arm.data.bones[g.name].use_deform}
    W = [{names[e.group]: e.weight for e in v.groups if e.group in deform and e.weight > 1e-4} for v in me.vertices]
    low = [any(_LOWARM_RE.search(n) and x > 0.02 for n, x in w.items()) for w in W]
    anyarm = [any(_ARM_RE.search(n) and x > 0.02 for n, x in w.items()) for w in W]
    hip = [any(_HIP_RE.search(n) and x > 0.02 for n, x in w.items()) for w in W]
    leg = [any(_LEG_RE.search(n) and x > 0.04 for n, x in w.items()) for w in W]
    torso = [any(_TORSO_RE.search(n) and x > 0.1 for n, x in w.items()) for w in W]
    skip = set(skip)
    try:
        import object_bones as _o
        lab = np.asarray(_o._islands(me))
    except Exception:
        lab = np.zeros(nv, dtype=int)
    sizes = np.bincount(lab)
    bad_isl = set()
    for k in range(len(sizes)):
        if sizes[k] >= FIX_ISLAND:
            continue
        vs = np.where(lab == k)[0]
        if any(i in skip for i in vs):
            continue
        if any(anyarm[i] for i in vs) and any(hip[i] for i in vs):
            bad_isl.add(k)
        elif sizes[k] < FIX_ISLAND_LEG and any(leg[i] for i in vs) and any(torso[i] for i in vs):
            bad_isl.add(k)
    new = {}
    if bad_isl:
        co = np.empty(nv * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
        good = [i for i in range(nv) if lab[i] not in bad_isl and W[i]]
        kd = KDTree(len(good))
        for j, i in enumerate(good):
            kd.insert(co[i].tolist(), j)
        kd.balance()
        for k in bad_isl:
            vs = np.where(lab == k)[0]
            best = None
            for i in vs:
                _, j, dist = kd.find(co[i].tolist())
                if j is not None and (best is None or dist < best[0]):
                    best = (dist, good[j])
            if best:
                for i in vs:
                    new[int(i)] = dict(W[best[1]])
    nfix = 0
    for i in range(nv):
        if i in new or i in skip or not (low[i] and hip[i]):
            continue
        w = {n: x for n, x in W[i].items() if not _LOWARM_RE.search(n)}
        s = sum(w.values())
        if s > 1e-4:
            new[i] = {n: x / s for n, x in w.items()}
            nfix += 1
    if not new:
        return 0, 0
    for i, w in new.items():
        for gi in [e.group for e in me.vertices[i].groups if e.group in deform]:
            body.vertex_groups[gi].remove([i])
        for n, x in w.items():
            (body.vertex_groups.get(n) or body.vertex_groups.new(name=n)).add([i], x, "REPLACE")
    return len(bad_isl), nfix


SMOOTH_DIFF = 0.3     # 이웃 정점과 웨이트가 이만큼(L1/2) 넘게 다르면 '딱 끊긴 경계'
SMOOTH_RINGS = 2      # 경계에서 몇 칸까지 부드럽게
SMOOTH_ITER = 4


def _body_auto_bones(arm):
    """bones the automatic body passes make (body template, face, breast). Bip bones are checked by prefix"""
    auto = set(_flow_face_bone_names()) | set(BREAST_BAST) | set(BREAST_BAST.values())
    try:
        import body_template as _bt
        auto |= set(_bt._load(_bt.TPL_PATH)["bones"])
    except Exception as e:
        print("body auto bones: no body template:", e)
    return auto


def smooth_boundaries(arm, body, limit=4, skip=None):
    """10/30 사용자 규칙: 이어진 메쉬의 웨이트 경계는 언제나 그라데이션.
    이웃 정점끼리 웨이트가 크게 다른 곳만 찾아서 그 둘레 몇 칸을 이웃 평균으로 부드럽게.
    10/31: 파츠 본(바디 자동 본이 아닌 본)이 한쪽이라도 낀 경계에서만 시작. 바디 템플릿끼리 경계(손가락·팔꿈치)는 그대로.
    skip = 지킬 정점(사람이 고친 값)은 바꾸지 않음.
    떨어진 조각끼리는 엣지가 없어서 섞이지 않음. returns 고친 정점 수"""
    import numpy as np
    me = body.data
    nv = len(me.vertices)
    if not nv:
        return 0
    deform = [g for g in body.vertex_groups if g.name in arm.data.bones and arm.data.bones[g.name].use_deform]
    if not deform:
        return 0
    pre = bip_prefix(arm) or "Bip01"
    auto = _body_auto_bones(arm)
    part = np.array([not (g.name.startswith(pre) or g.name in auto or g.name.lower() in auto) for g in deform])
    if not part.any():
        return 0
    col = {g.index: j for j, g in enumerate(deform)}
    Wm = np.zeros((nv, len(deform)), np.float32)
    for v in me.vertices:
        for e in v.groups:
            j = col.get(e.group)
            if j is not None:
                Wm[v.index, j] = e.weight
    s = Wm.sum(1, keepdims=True)
    Wm = np.where(s > 1e-6, Wm / np.maximum(s, 1e-6), Wm)
    ed = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", ed)
    ed = ed.reshape(-1, 2)
    if not len(ed):
        return 0
    diff = np.abs(Wm[ed[:, 0]] - Wm[ed[:, 1]]).sum(1) / 2.0
    inpart = Wm[:, part].sum(1) > 0.01
    zone = np.zeros(nv, bool)
    hard = ed[(diff > SMOOTH_DIFF) & (inpart[ed[:, 0]] | inpart[ed[:, 1]])]
    zone[hard.ravel()] = True
    for _ in range(SMOOTH_RINGS):
        z2 = zone.copy()
        m = zone[ed[:, 0]] | zone[ed[:, 1]]
        z2[ed[m].ravel()] = True
        zone = z2
    if skip:
        zone[[i for i in skip if 0 <= i < nv]] = False
    if not zone.any():
        return 0
    deg = np.bincount(ed.ravel(), minlength=nv).astype(np.float32)
    W0 = Wm.copy()
    for _ in range(SMOOTH_ITER):
        acc = np.zeros_like(Wm)
        np.add.at(acc, ed[:, 0], Wm[ed[:, 1]])
        np.add.at(acc, ed[:, 1], Wm[ed[:, 0]])
        nb = acc / np.maximum(deg, 1.0)[:, None]
        Wm[zone] = 0.5 * Wm[zone] + 0.5 * nb[zone]
    # 10/31: 섞는 건 파츠 몫(파츠 ↔ 몸 비율)만. 몸 본끼리 나눈 비율은 템플릿 값 그대로 (파츠 몫이 없는 정점은 안 바뀜)
    pz = Wm[zone][:, part].sum(1, keepdims=True)
    b0 = W0[zone][:, ~part]
    bs = b0.sum(1, keepdims=True)
    body_new = np.where(bs > 1e-6, b0 / np.maximum(bs, 1e-6) * (1.0 - pz), Wm[zone][:, ~part])
    sub = Wm[zone]
    sub[:, ~part] = body_new
    Wm[zone] = sub
    # 정점당 최대 limit 개, 합 1
    idx = np.where(zone)[0]
    sub = Wm[idx]
    if sub.shape[1] > limit:
        cut = np.partition(sub, -limit, axis=1)[:, -limit][:, None]
        sub = np.where(sub >= cut, sub, 0.0)
    sub = sub / np.maximum(sub.sum(1, keepdims=True), 1e-6)
    Wm[idx] = sub
    changed = idx[np.abs(Wm[idx] - W0[idx]).sum(1) > 1e-3]
    for i in changed:
        i = int(i)
        for e in list(me.vertices[i].groups):
            if e.group in col:
                body.vertex_groups[e.group].remove([i])
        for j in np.where(Wm[i] > 1e-4)[0]:
            deform[j].add([i], float(Wm[i, j]), "REPLACE")
    return int(len(changed))

def _ob_max_parts(mb):
    """Max 바디 AppData 7760 (파트 면) + '#@#' + 7761 (본 이름 앞부분) 글자 그대로"""
    # 2.5: Rig Tools 파트 함수가 아직 안 읽힌 Max 면 먼저 읽음 (없으면 실패 → 파츠 웨이트가 조용히 몸 웨이트로 바뀌던 것)
    s = mb.send('(if rts_pmBody == undefined do try (fileIn (RigTools.sbgDir() + "rts_blender.ms")) catch (); local b = rts_pmBody(); if b == undefined then "" else ((local a = getAppData b 7760; if a == undefined then "" else a) + "#@#" + (local c = getAppData b 7761; if c == undefined then "" else c)))',
                timeout=60).strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return s


# 2.6 (정현 11-01, 카르멘): ④ 기록에 도구 판·Max 파트 면 기록 지문·파츠 본 이름을 같이 저장. 다시 계산할 수 있는 바디
# (Max 파트 면 기록이 있음)는 셋 중 하나라도 다르면 기록을 버리고 Max 본으로 다시 계산 (옛 판 기록이 새 판정 위에 다시 쓰이던 것).
# 파트 면 기록이 없는 바디(멜리타 프리셋)는 다시 계산할 수 없어 예전처럼 기록을 씀 (2.1: 새 블렌더에서 웨이트 0 되던 것).
OB_REC_VER = "2.6"
_OB_PART_RE = re.compile(r"^bone_(skirt\d*|cape\d*|obj\d+)_", re.I)


def _ob_part_bones(arm):
    return sorted(b.name for b in arm.data.bones if b.use_deform and _OB_PART_RE.match(b.name))


def _ob_parts_sig(s):
    import hashlib
    return hashlib.sha1(s.encode("utf-8")).hexdigest() if s.partition("#@#")[0].strip() else ""


def _ob_rebuild_from_max(scene, arm, body, mb):
    """Max body AppData 7760 (part faces: kind|chains|segs|v1,v2.. Max 1-based) + 7761 (bone prefixes) -> object bone weights"""
    s = _ob_max_parts(mb)
    a, _, c = s.partition("#@#")
    lines = [l for l in a.replace("\\n", "\n").split("\n") if l.strip()]
    pres = [p.strip() for p in c.split("|")]
    marks = []
    for l in lines:
        f = l.strip().split("|")
        kind = f[0] if f else ""
        vids = [int(x) - 1 for x in (f[3].split(",") if len(f) > 3 and f[3] else []) if x.strip().isdigit()]
        marks.append((kind, vids))
    return _ob.weights_from_bones(scene, arm, body, marks, pres[:len(marks)])


def _ob_path(mb, body):
    """④ object bone weight record of this Max file + mesh (%LOCALAPPDATA%\\GE_RigJobs\\ob\\<file>__<mesh>.json)"""
    import rig_template as _rt
    char = os.path.splitext(mb.send("maxFileName", timeout=30).strip().strip('"'))[0]
    return os.path.join(_rt.JOB_DIR, "ob", "%s__%s.json" % (char, body.name)) if char else None


def _ob_save(scene, mb, body):
    """11/01: 스킨 적용 때 쓴 ④ 웨이트(scene W_KEY)를 기록 → 새 블렌더 세션의 다시 적용이 같은 값으로 시작"""
    try:
        W = json.loads(scene.get(_ob.W_KEY, "{}") or "{}")
        p = _ob_path(mb, body)
        if W and p:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            # 집 확인 (11/01): uv 로 계산한 정점 목록도 같이 (새 세션의 스킨 적용이 그 정점을 경계 그라데이션에서 빼게)
            uv = _ob.uv_verts(scene) if hasattr(_ob, "uv_verts") else []
            arm = flow_objects(bpy.context)[0]
            json.dump({"nv": len(body.data.vertices), "W": W, "uv": uv, "ver": OB_REC_VER, "parts": _ob_parts_sig(_ob_max_parts(mb)),
                       "part_bones": _ob_part_bones(arm) if arm is not None else []}, open(p, "w", encoding="utf-8"))
    except Exception as e:
        print("ob save:", e)


def _ob_load(scene, arm, body, mb):
    """기록이 이 바디(정점 수)와 지금 뼈대(본 이름 모두 있음)에 맞으면 scene W_KEY 로. returns 정점 수 (0 = 안 씀)"""
    try:
        p = _ob_path(mb, body)
        if not p or not os.path.exists(p):
            return 0
        d = json.load(open(p, encoding="utf-8"))
        W = d.get("W") or {}
        # 집 확인 (2026-11-01): 기록 뒤 Max 에서 지우거나 이름을 바꾼 본은 빼고 씀 (같은 블렌더에서 적용할 때와 같은 동작:
        #   그 본 몫은 그 정점의 몸 웨이트로). 절반 넘게 없으면 다른 뼈대로 보고 안 씀
        miss = [n for n in W if n not in arm.data.bones and n != _ob.BODY_TOKEN]
        if d.get("nv") != len(body.data.vertices) or not W or len(miss) * 2 > len(W):
            print("ob load: 기록이 지금 바디·본과 안 맞아 안 씀")
            return 0
        sig = _ob_parts_sig(_ob_max_parts(mb))
        if sig:       # 2.6: Max 파트 면 기록이 있어 다시 계산할 수 있으면, 판·면 기록·새 파츠 본이 다른 기록은 안 씀
            why = ("도구 판 %s → %s" % (d.get("ver") or "2.5 이하", OB_REC_VER) if d.get("ver") != OB_REC_VER else
                   "Max 파트 면 기록이 바뀜" if d.get("parts") != sig else
                   "기록에 없는 파츠 본 %d개" % len(set(_ob_part_bones(arm)) - set(d.get("part_bones") or [])) if set(_ob_part_bones(arm)) - set(d.get("part_bones") or []) else "")
            if why:
                print("ob load: 지난 기록을 안 씀 (%s) → Max 본으로 다시 계산" % why)
                return 0
        if miss:
            # 2.3 (수정안 A, 정현 11-01): 없는 본 몫이 있던 정점은 남은 값(Pelvis 0.05 등)을 100% 로 맞추지 않고 정점 전체를 몸 웨이트로
            #   (위젤 손목 장식: 정점 일부만 Pelvis 100% 가 되어 팔을 들면 늘어나던 것)
            W, nd = _ob.drop_dead(W, miss, body)
            print("ob load: 기록에 있지만 지금 없는 본 %d개는 뺌 (그 정점 %d개는 몸 웨이트로): %s" % (len(miss), nd, ", ".join(miss[:8])))
        if d.get("uv") and hasattr(_ob, "UV_KEY"):
            scene[_ob.UV_KEY] = json.dumps([int(v) for v in d["uv"]])
        scene[_ob.W_KEY] = json.dumps(W)
        return len({v for lst in W.values() for v, _ in lst})
    except Exception as e:
        print("ob load:", e)
        return 0


class MSR_OT_flow_weights(bpy.types.Operator):
    """바디는 Bip(트위스트·가슴 포함), 얼굴·이는 얼굴 본으로 자동 웨이트 (기존 웨이트 교체)"""
    bl_idname = "msr.flow_weights"
    bl_label = "자동 웨이트"
    bl_options = {"REGISTER", "UNDO"}
    body_on: bpy.props.BoolProperty(name="바디", default=True)
    face_on: bpy.props.BoolProperty(name="얼굴 · 이", default=True)
    body_tpl: bpy.props.BoolProperty(
        name="바디 템플릿 (작업자 값)",
        description="기본 바디 웨이트를 작업자(멜리타 User) 웨이트 템플릿으로 채워요 (보조본 포함, Bip 뼈대 비율로 맞춤). 끄면 자동 웨이트",
        default=True)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="자동 웨이트: 선택한 메쉬의 웨이트를 새로 넣어요")

    def execute(self, context):
        wm = context.window_manager
        arm, body, face, tooth = flow_objects(context)
        if arm is None:
            self.report({"WARNING"}, "Bip이 없어요. 먼저 'Max에서 가져오기'")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        msgs = []
        mb = _max_bridge()
        if mb is not None:
            try:
                k = pull_bones_from_max(arm, mb, _flow_face_bone_names() + ["Bone_breast_L", "Bone_breast_R"])
                if k:
                    msgs.append("Max에서 빠진 본 %d개 가져옴" % k)
            except Exception as e:
                print("pull bones:", e)
        try:
            if self.body_on and body and "Bone_breast_L" not in arm.data.bones and _bast_pairs(arm):
                # breast bones live only in Blender (Max has bone_bast): a re-import from Max drops them -> remake (same as ②)
                add_breast_bones(arm, body, to_max=False)
                msgs.append("가슴 본이 없어 bone_bast 위치로 다시 만듦")
            if self.body_on and body and _ob is not None:
                # 10/30: ② 웨이트가 Blender 에 없으면 (다른 파일 작업으로 정리됨) Max 의 실제 본 + 파트 면 기록으로 다시 계산
                nr = 0
                if mb is not None and not json.loads(context.scene.get(_ob.W_KEY, "{}") or "{}"):
                    # 11/01: 지난 스킨 적용 때 쓴 ④ 웨이트 기록이 있으면 그대로 (멜리타 프리셋 값 등이 새 세션에서 바뀌지 않게)
                    nr = _ob_load(context.scene, arm, body, mb)
                    if nr:
                        msgs.append("치마·망토 웨이트: 지난 적용 값 그대로 (정점 %d)" % nr)
                if mb is not None and not json.loads(context.scene.get(_ob.W_KEY, "{}") or "{}"):
                    try:
                        nr = _ob_rebuild_from_max(context.scene, arm, body, mb)
                    except Exception as e:
                        print("object bone weights from Max bones:", e)
                    if nr:
                        msgs.append("치마·망토 웨이트: Max 본 위치로 다시 계산 (정점 %d)" % nr)
                # new Blender session after ①: keep the object bone weights that came from the Max skin
                nk = 0 if nr else _ob.recover_weights(context.scene, arm, body)
                if nk:
                    msgs.append("Max 스킨의 오브젝트 본 웨이트 보관: 정점 %d" % nk)
            if self.body_on and body:
                # with the body template the distance pass only feeds the breast weights: keep that pass as it was
                # (old twist lookup) so the chosen breast result does not move; without the template use the rig twists
                n, _ = bip_auto_weights(arm, body, use_twist=True, limit=wm.msr_limit, twist_ci=not self.body_tpl)
                msgs.append("바디: 본 %d개" % n)
                if self.body_tpl:
                    try:
                        import sys as _sys
                        _d = os.path.dirname(os.path.abspath(__file__))
                        if _d not in _sys.path:
                            _sys.path.insert(0, _d)
                        import body_template as _bt
                        # template with breast bones (worker values, review1) wins; without them keep the auto breast weights
                        # 10/30: [리깅 완료] 로 저장된 캐릭터 중 체형이 가장 가까운 몸 템플릿 (없으면 멜리타)
                        tpath, tlabel = None, "멜리타 (기본)"
                        try:
                            import rig_template as _rt
                            tpath, tlabel = _rt.pick_body_template(arm)
                        except Exception as e:
                            print("pick body template:", e)
                        tp = tpath or _bt.TPL_PATH
                        brk = list(BREAST_BAST) + [b.lower() for b in BREAST_BAST.values()] + list(BREAST_BAST.values())
                        cap = {} if _bt.has_bones(brk, tp) else _breast_capture(body)
                        msgs.append("몸 템플릿: " + tlabel)
                        msgs.append(_bt.apply(arm, body, path=tp, limit=wm.msr_limit))
                        if cap:
                            msgs.append("가슴 웨이트 유지: 정점 %d" % _breast_restore(body, cap, wm.msr_limit))
                    except Exception as e:
                        msgs.append("바디 템플릿 건너뜀: %s" % str(e)[:120])
                if _ob is not None and (arm.get(_ob.ARM_KEY) or json.loads(context.scene.get(_ob.W_KEY, "{}") or "{}")):
                    # ④ object bones made before: the body weights are new, put the object bone weights back on top
                    context.scene[_ob.ORIG_KEY] = "{}"
                    nob = _ob.apply_weights(context.scene, arm, body)
                    if nob:
                        msgs.append("오브젝트 본 웨이트 다시 얹음: 정점 %d" % nob)
                try:
                    sk = {v for lst in json.loads(context.scene.get(_ob.W_KEY, "{}") or "{}").values() for v, _ in lst} if _ob is not None else set()
                    ni, nf = _fix_arm_hip_mix(arm, body, sk)
                    if ni or nf:
                        msgs.append("팔에 끌려갈 장식 정리: 조각 %d · 정점 %d" % (ni, nf))
                except Exception as e:
                    print("arm/hip fix:", e)
            if self.face_on and face:
                if "Bone_jaw" in arm.data.bones:
                    nf, nt = face_auto_weights(arm, _find_head_bone(arm), face, tooth)
                    msgs.append("얼굴: 본 %d개%s" % (nf, " · 이 완료" if tooth else ""))
                    msgs += EYE_WARN
                else:
                    msgs.append("얼굴 본이 없어 얼굴은 건너뜀 (② 얼굴·가슴 본 추가 먼저)")
        except Exception as e:
            wm.msr_status = "자동 웨이트 실패 | %s" % str(e)[:200]
            self.report({"ERROR"}, wm.msr_status)
            return {"CANCELLED"}
        if body:
            _select_only(context, [body], body)
        wm.msr_status = " | ".join(msgs) + " | 다음: 보정 (칠하기 / 수치)"
        self.report({"INFO"}, wm.msr_status)
        return {"FINISHED"}


class MSR_OT_flow_edit(bpy.types.Operator):
    """보정할 메쉬를 골라 웨이트 편집 시작. 칠하기 = 브러시, 수치 = 정점 선택 후 값 입력"""
    bl_idname = "msr.flow_edit"
    bl_label = "보정 시작"
    bl_options = {"REGISTER", "UNDO"}
    target: bpy.props.EnumProperty(items=[("BODY", "바디", ""), ("FACE", "얼굴", ""), ("TOOTH", "이", "")], default="BODY")
    mode: bpy.props.EnumProperty(items=[("PAINT", "칠하기", ""), ("VERTEX", "수치", ""), ("KEEP", "유지", "")], default="KEEP")

    def execute(self, context):
        wm = context.window_manager
        arm, body, face, tooth = flow_objects(context)
        obj = {"BODY": body, "FACE": face, "TOOTH": tooth}[self.target]
        if self.mode == "KEEP":
            cur = mesh_obj(context)
            mode = "VERTEX" if (cur and cur.data.use_paint_mask_vertex and context.mode == "PAINT_WEIGHT") else "PAINT"
        else:
            mode = self.mode
            obj = mesh_obj(context) if (context.mode == "PAINT_WEIGHT" and mesh_obj(context)) else obj
        if obj is None:
            self.report({"WARNING"}, "그 메쉬가 없어요")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        a = armature_of(obj) or arm
        _select_only(context, [o for o in (a, obj) if o], obj)
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        ts = context.tool_settings
        ts.use_auto_normalize = True
        if a:
            a.show_in_front = True
        obj.data.use_paint_mask_vertex = (mode == "VERTEX")
        try:
            if mode == "VERTEX":
                bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
            else:
                bpy.ops.wm.tool_set_by_id(name="builtin.brush")
                bpy.ops.brush.asset_activate(asset_library_type="ESSENTIALS",
                                             relative_asset_identifier=WEIGHT_BRUSHES + "Paint")
        except Exception as e:
            print("flow_edit tool:", e)
        wm.msr_status = "%s 보정 중 (%s) | Ctrl+클릭으로 본 선택" % (obj.name, "칠하기" if mode == "PAINT" else "수치")
        return {"FINISHED"}


class MSR_OT_flow_brush(bpy.types.Operator):
    """웨이트 브러시 바꾸기"""
    bl_idname = "msr.flow_brush"
    bl_label = "브러시"
    brush: bpy.props.StringProperty(default="Paint")

    def execute(self, context):
        if context.mode != "PAINT_WEIGHT":
            return {"CANCELLED"}
        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.brush")
            bpy.ops.brush.asset_activate(asset_library_type="ESSENTIALS",
                                         relative_asset_identifier=WEIGHT_BRUSHES + self.brush)
        except Exception as e:
            self.report({"WARNING"}, str(e))
            return {"CANCELLED"}
        return {"FINISHED"}


def set_skin_pose_once(arm, mb):
    """Max: bones under the Bip root (not Biped itself) get 'Set as Skin Pose' once (first skin send / newly made bones),
    so a worker can always go back with 'Assume Skin Pose'. Marked with user prop rt_skinpose, later sends skip them."""
    root = bip_prefix(arm) or "Bip01"
    try:
        r = mb.send('(local st = sliderTime; sliderTime = 0f; local root = getNodeByName "%s" exact:true; local n = 0; if root != undefined do '
                    'for o in objects where o != root and not (isKindOf o Biped_Object) and (classOf o as string) != "Footsteps" '
                    'and getUserProp o "rt_skinpose" == undefined do (local t = o; while t.parent != undefined do t = t.parent; '
                    'if t == root do (try (o.setSkinPose(); setUserProp o "rt_skinpose" "1"; n += 1) catch ())); sliderTime = st; n as string)'
                    % root, timeout=60)
        return r.strip().strip('"')
    except Exception as e:
        return "실패(%s)" % str(e)[:60]


def _eye_skin_rigid(mb, name):
    """separate eyeball mesh: new Skin, each vertex 1.0 on the nearer Bone_eyeball_L / _R"""
    try:
        return mb.send(('(local o = getNodeByName "%s" exact:true; local bl = getNodeByName "Bone_eyeball_L" exact:true; '
                        'local br = getNodeByName "Bone_eyeball_R" exact:true; '
                        'if o == undefined or bl == undefined or br == undefined then "본 없음" else ('
                        'for i = o.modifiers.count to 1 by -1 where classOf o.modifiers[i] == Skin do deleteModifier o i; '
                        'local m = snapshotAsMesh o; local sk = Skin(); addModifier o sk; max modify mode; select o; modPanel.setCurrentObject sk; '
                        'skinOps.addBone sk bl 0; skinOps.addBone sk br 1; classOf o; '
                        'local il = 1; local ir = 2; if skinOps.GetBoneName sk 1 0 != "Bone_eyeball_L" do (il = 2; ir = 1); '
                        'local nv = skinOps.GetNumberVertices sk; local nl = 0; '
                        'if nv != m.numverts then (delete m; "정점 수 다름") else ('
                        'for v = 1 to nv do (local p = getVert m v; local l = distance p bl.pos < distance p br.pos; if l do nl += 1; '
                        'skinOps.ReplaceVertexWeights sk v (if l then il else ir) 1.0); delete m; '
                        '"L " + nl as string + " / R " + (nv - nl) as string)))') % name, timeout=120).strip().strip('"')
    except Exception as e:
        return "실패(%s)" % str(e)[:60]


_TOOL_BONE_RE = re.compile(r"^bone_(skirt|cape|obj\d+|hair)_", re.I)


def _manual_keep(arm, body):
    """vertices whose weights now (from the Max skin, or ④ in this session) use a bone the automatic passes do not make:
    object bones and bones added by hand in Max. {vertex: {bone: weight}} - the batch apply keeps these as they are"""
    pre = bip_prefix(arm) or "Bip01"
    auto = _body_auto_bones(arm)
    bones = arm.data.bones
    names = {g.index: g.name for g in body.vertex_groups if g.name in bones and bones[g.name].use_deform}
    out = {}
    for v in body.data.vertices:
        d = {names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 0}
        # 10/30: 이 도구가 만든 치마·망토·기타·헤어 본(bone_skirt_/bone_cape_/bone_objNN_/bone_hair_)은 매번 다시 계산 →
        # 예전 자동 값이 '손으로 칠한 값' 으로 남아 잘못된 웨이트가 계속 유지되던 것 막음
        if any(n not in auto and n.lower() not in auto and not n.startswith(pre) and not _TOOL_BONE_RE.match(n) for n in d):
            out[v.index] = d
    return out


SENT_KEEP_DIFF = 0.02   # 지난 스킨 적용 때 보낸 값과 본 하나라도 이만큼 넘게 다르면 '사람이 고친 정점'
SENT_STALE = 0.3        # 이 비율 넘게 다르면 기록이 이 스킨 것이 아님 (저장 안 하고 다시 연 파일 등) → 기록 안 씀
_SENT_KEEP = {}         # 메쉬 이름 -> {정점: {본: 웨이트}} 일괄 적용이 지킬 정점 → flow_send 가 맨 끝에 그대로 씀 (경계 섞기 제외)


def _sent_keep(arm, body, mb):
    """10/31: vertices whose weights now (from the Max skin) differ from what the last skin apply sent
    (rig_template.keep_sent record) = hand edits, whatever the bone. {vertex: {bone: weight}}; None = no record"""
    try:
        import rig_template as _rt
        char = mb.send("maxFileName", timeout=30).strip().strip('"')
        sent = _rt.read_sent(os.path.join(_rt.SENT_DIR, "%s__%s.txt" % (os.path.splitext(char)[0], body.name)))
    except Exception as e:
        print("sent keep:", e)
        return None
    me = body.data
    if sent is None or len(sent) != len(me.vertices):
        return None
    alias = {}
    for a, b in BREAST_BAST.items():
        alias[a.lower()] = alias[b.lower()] = a.lower()

    def canon(d):
        out = {}
        for n, w in d.items():
            k = alias.get(n.lower(), n.lower())
            out[k] = out.get(k, 0.0) + w
        s = sum(out.values())
        return {k: w / s for k, w in out.items()} if s > 1e-6 else out

    bones = arm.data.bones
    names = {g.index: g.name for g in body.vertex_groups if g.name in bones and bones[g.name].use_deform}
    out = {}
    for v in me.vertices:
        d = {names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 0}
        if not d:
            continue
        a, b = canon(d), canon(sent[v.index])
        if any(abs(a.get(k, 0.0) - b.get(k, 0.0)) > SENT_KEEP_DIFF for k in set(a) | set(b)):
            out[v.index] = d
    if len(out) > SENT_STALE * len(me.vertices):
        # 적용 뒤 저장 안 하고 다시 연 파일·같은 이름의 다른 파일: 기록이 지금 스킨과 맞지 않음 → 기록 안 씀
        print("sent keep: 기록과 %d/%d 정점이 달라 안 씀" % (len(out), len(me.vertices)))
        return None
    return out


class MSR_OT_flow_apply_all(bpy.types.Operator):
    """일괄: 바디 템플릿·가슴·얼굴·파츠(오브젝트 본) 웨이트를 지금 계산해서 Max 스킨에 한 번에 적용.
Max에서 칠한 파츠·손 본 웨이트(자동 계산에 없는 본)가 있는 정점은 그 값 그대로"""
    bl_idname = "msr.flow_apply_all"
    bl_label = "스킨 적용 (일괄)"
    bl_options = {"REGISTER"}
    face_on: bpy.props.BoolProperty(name="얼굴 · 이", default=True)
    keep_manual: bpy.props.BoolProperty(name="Max에서 칠한 파츠·손 본 웨이트 유지", default=True)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self, title="웨이트를 새로 계산해서 Max 스킨을 교체해요 (Max에서 Ctrl+Z 가능)")

    def execute(self, context):
        wm = context.window_manager
        arm, body, face, tooth = flow_objects(context)
        if arm is None or body is None:
            self.report({"WARNING"}, "Bip·바디가 없어요. 먼저 'Max에서 가져오기'")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if _ob is not None and _ob.pieces():
            _ob.clear(context, body)              # ③ split copies are not needed any more (body visible again)
        mb = _max_bridge()
        first = False
        if mb is not None:
            try:
                first = mb.send('(local o = getNodeByName "%s" exact:true; (o != undefined and getUserProp o "rt_batch" == undefined) as string)'
                                % body.name, timeout=30).strip().strip('"').lower() == "true"
            except Exception as e:
                print("batch mark:", e)
        # first batch apply on this file: the old skin is not hand work (new characters come skinned) -> nothing kept
        # 10/31: 지난 적용 때 보낸 값 기록이 있으면, 그 값과 다른 정점(사람이 고친 정점)만 본 종류와 상관없이 그대로 (보내기 직전에 다시 씀)
        #        나머지는 새로 계산 (지난 값을 지키면 경계 섞기가 겹쳐 쌓임). 기록이 없으면 예전처럼 '도구가 안 만드는 본' 정점 유지
        skeep = _sent_keep(arm, body, mb) if self.keep_manual and not first and mb is not None else None
        keep = _manual_keep(arm, body) if self.keep_manual and not first and skeep is None else {}
        skeep = skeep or {}
        _SENT_KEEP.clear()
        if skeep:
            _SENT_KEEP[body.name] = skeep
        r = bpy.ops.msr.flow_weights("EXEC_DEFAULT", body_on=True, face_on=self.face_on, body_tpl=True)
        if "FINISHED" not in r:
            _SENT_KEEP.clear()
            self.report({"ERROR"}, wm.msr_status)
            return {"CANCELLED"}
        if keep and _ob is not None:
            # kept vertices become the object bone weights the send puts on (so nothing recomputes them)
            sc = context.scene
            W = json.loads(sc.get(_ob.W_KEY, "{}") or "{}")
            W = {n: [e for e in lst if e[0] not in keep] for n, lst in W.items()}
            for vi, d in keep.items():
                for n, w in d.items():
                    W.setdefault(n, []).append([vi, float(w)])
            sc[_ob.W_KEY] = json.dumps({n: lst for n, lst in W.items() if lst})
            _ob.apply_weights(sc, arm, body)
        r = bpy.ops.msr.flow_send("EXEC_DEFAULT", body_on=True, face_on=self.face_on, tooth_on=self.face_on)
        _SENT_KEEP.clear()
        extra = ""
        if "FINISHED" in r and mb is not None:
            try:
                mb.send('(local o = getNodeByName "%s" exact:true; if o != undefined do setUserProp o "rt_batch" "1"; "OK")' % body.name, timeout=30)
            except Exception as e:
                print("batch mark:", e)
            if self.face_on:
                extra = "".join(" | 눈알 %s: %s" % (eo.name, _eye_skin_rigid(mb, eo.name)) for eo in list(_EYE_OBJ))
            if _hb is not None:
                try:
                    extra += _hb.batch_send(context, arm, mb, wm.msr_limit)
                except Exception as e:
                    extra += " | 헤어 실패: %s" % str(e)[:120]
        wm.msr_status = "일괄 적용 | " + wm.msr_status + extra + (
            " | 처음 적용: 원래 스킨 대신 새로 계산" if first else "") + (" | Max·④ 손 웨이트 유지: 정점 %d" % len(keep) if keep else "") + (
            " | 사람이 고친 정점 유지: %d" % len(skeep) if skeep else "")
        self.report({"INFO"} if "FINISHED" in r else {"ERROR"}, wm.msr_status)
        return {"FINISHED"} if "FINISHED" in r else {"CANCELLED"}


class MSR_OT_flow_send(bpy.types.Operator):
    """최종: 웨이트 정리(정점당 최대 본·정규화) → 없는 본은 Max에 만들고 → Max Skin에 바로 적용"""
    bl_idname = "msr.flow_send"
    bl_label = "Max에 스킨 적용"
    bl_options = {"REGISTER"}
    body_on: bpy.props.BoolProperty(name="바디", default=True)
    face_on: bpy.props.BoolProperty(name="얼굴", default=True)
    tooth_on: bpy.props.BoolProperty(name="이", default=True)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self, title="Max의 같은 이름 메쉬 Skin을 교체해요 (Max에서 Ctrl+Z 가능)")

    def execute(self, context):
        wm = context.window_manager
        arm, body, face, tooth = flow_objects(context)
        mb = _max_bridge()
        if mb is None:
            wm.msr_status = "Max Bridge 애드온이 꺼져 있어요"
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        objs = [o for o, on in ((body, self.body_on), (face, self.face_on), (tooth, self.tooth_on))
                if o is not None and on and len(o.vertex_groups)]
        if not objs:
            self.report({"WARNING"}, "보낼 메쉬가 없어요")
            return {"CANCELLED"}
        out = []
        try:
            if arm and body in objs and _ob is not None:
                nob = _ob.apply_weights(context.scene, arm, body)   # ④ 오브젝트 본 웨이트를 바디에 얹기
                if nob:
                    out.append("오브젝트 본 정점 %d" % nob)
            if arm and body in objs:
                skeep = _SENT_KEEP.get(body.name, {})
                try:
                    # 11/01: ④ (u,v) 로 계산한 치마 정점은 이미 매끈하고 겹끼리 같은 값이라 문지르지 않음 (문지르면 겹마다 달라져 틈)
                    uvv = _ob.uv_verts(context.scene) if (_ob is not None and hasattr(_ob, "uv_verts")) else []
                    ns = smooth_boundaries(arm, body, wm.msr_limit, skip=(list(skeep) + uvv) if uvv else skeep)
                    if uvv:
                        out.append("uv 정점 %d 는 그라데이션 제외" % len(uvv))
                    if ns:
                        out.append("경계 그라데이션 정점 %d" % ns)
                except Exception as e:
                    print("smooth boundaries:", e)
                if skeep:                                   # 사람이 고친 정점: 지난번 Max 값 그대로
                    bones = arm.data.bones
                    dg = {g.index for g in body.vertex_groups if g.name in bones and bones[g.name].use_deform}
                    for vi, d in skeep.items():
                        for gi in [e.group for e in body.data.vertices[vi].groups if e.group in dg]:
                            body.vertex_groups[gi].remove([vi])
                        for n, w in d.items():
                            (body.vertex_groups.get(n) or body.vertex_groups.new(name=n)).add([vi], w, "REPLACE")
            for o in objs:
                limit_normalize(o, wm.msr_limit)
            if arm:
                used = set()
                for o in objs:
                    used |= {g.name for g in o.vertex_groups}
                extra = [n for n in used if n in arm.data.bones and
                         (n.startswith("Bone_") and (n in _flow_face_bone_names() or "breast" in n))]
                if _bast_pairs(arm):
                    extra = [n for n in extra if n not in BREAST_BAST]
                extra += [n for n in arm.get("msr_ob_bones", []) if n not in extra]   # ④ 오브젝트 본 (Max에 없으면)
                k = push_bones_to_max(arm, extra, mb)
                if k:
                    out.append("Max에 없던 본 %d개 생성" % k)
                sp = set_skin_pose_once(arm, mb)
                if sp:
                    out.append("스킨 포즈 저장 %s개" % sp)
            for o in objs:
                zero, _ = weight_stats(o, wm.msr_limit)
                r = send_weights_to_max(o, o.name, mb, wm.msr_limit)
                out.append("%s OK%s" % (o.name, (" (미할당 %d)" % zero) if zero else ""))
                print(r)
                if o is body and _ob is not None:
                    _ob_save(context.scene, mb, body)
        except Exception as e:
            out.append("실패: %s" % str(e)[:220])
            wm.msr_status = " | ".join(out)
            self.report({"ERROR"}, wm.msr_status)
            return {"CANCELLED"}
        wm.msr_status = "Max 스킨 적용 완료 | " + " | ".join(out)
        self.report({"INFO"}, wm.msr_status)
        return {"FINISHED"}


# ============================================================ 포즈 테스트
import json as _json
from mathutils import Matrix as _Mx, Vector as _Vc

_PT_LAST = {}   # 메쉬 이름 -> 지난 결과(비교용)


def _pt_bone(arm, suffix):
    for b in arm.pose.bones:
        if b.name.startswith("Bip0") and b.name.endswith(" " + suffix):
            return b
    return None


def _pt_rotate(arm, pb, axis, deg):
    """본 머리를 중심으로 아마추어 공간 axis 기준 deg 회전"""
    import math
    if pb is None or axis.length < 1e-6:
        return
    h = pb.head.copy()
    R = _Mx.Rotation(math.radians(deg), 4, axis.normalized())
    pb.matrix = _Mx.Translation(h) @ R @ _Mx.Translation(-h) @ pb.matrix
    bpy.context.view_layer.update()


def _pt_dir(pb):
    kids = [c for c in pb.children if "Nub" not in c.name and c.name.startswith("Bip0")]
    if kids:
        return (kids[0].head - pb.head).normalized()
    return (pb.tail - pb.head).normalized()


def _pt_front(arm):
    """캐릭터 정면(아마추어 공간): 허벅지 L→R 방향과 위쪽의 외적"""
    l, r = _pt_bone(arm, "L Thigh"), _pt_bone(arm, "R Thigh")
    if l and r:
        side = (l.head - r.head).normalized()       # 캐릭터 왼쪽
        up = _Vc((0, 0, 1))
        f = side.cross(up)                            # 왼쪽 x 위 = 앞
        if f.length > 1e-6:
            return f.normalized()
    return _Vc((0, -1, 0))


def _pt_region(name):
    n = name.lower()
    if any(k in n for k in ("upperarm", "forearm", "hand", "finger", "clavicle", "elbow", "arm")):
        return "팔·어깨"
    if any(k in n for k in ("thigh", "calf", "foot", "toe", "knee", "leg")):
        return "다리"
    if any(k in n for k in ("head", "neck", "face", "jaw", "lip", "eye", "brow", "cheek", "tooth", "hair")):
        return "머리·목"
    if any(k in n for k in ("skirt", "coat", "cape", "belt")):
        return "치마·코트"
    return "몸통"


def _pt_measure(arm, objs, ratio):
    """늘어난 엣지 수 (포즈 길이 / 기본 길이 > ratio), 부위별"""
    import numpy as np
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for o in objs:
        me = o.data
        n = len(me.vertices)
        rest = np.empty(n * 3, dtype=np.float64); me.vertices.foreach_get("co", rest); rest = rest.reshape(-1, 3)
        ev = o.evaluated_get(dg); em = ev.to_mesh()
        if len(em.vertices) != n:
            ev.to_mesh_clear(); out.append((o.name, None, {})); continue
        pos = np.empty(n * 3, dtype=np.float64); em.vertices.foreach_get("co", pos); pos = pos.reshape(-1, 3)
        ev.to_mesh_clear()
        ed = np.empty(len(me.edges) * 2, dtype=np.int64); me.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
        l0 = np.linalg.norm(rest[ed[:, 0]] - rest[ed[:, 1]], axis=1)
        l1 = np.linalg.norm(pos[ed[:, 0]] - pos[ed[:, 1]], axis=1)
        ok = l0 > 1e-6
        bad = np.zeros(len(ed), dtype=bool); bad[ok] = l1[ok] / l0[ok] > ratio
        # 정점별 가장 큰 웨이트 본 → 부위
        names = {g.index: g.name for g in o.vertex_groups}
        regs = {}
        bad_v = set(ed[bad].ravel().tolist())
        for vi in bad_v:
            v = me.vertices[vi]
            best = max(v.groups, key=lambda g: g.weight, default=None)
            r = _pt_region(names.get(best.group, "")) if best else "웨이트 없음"
            regs[r] = regs.get(r, 0) + 1
        out.append((o.name, (int(bad.sum()), len(ed)), regs, bad))
    return out


class MSR_OT_pose_test(bpy.types.Operator):
    """정해진 테스트 포즈(양팔 70° 들기, 왼팔꿈치 90°, 왼허벅지 60°, 왼무릎 90°, 허리 20°, 머리 30°)를 주고 늘어난 엣지를 셈. 데이터는 '원래대로'로 복구"""
    bl_idname = "msr.pose_test"
    bl_label = "포즈 테스트"
    bl_options = {"REGISTER", "UNDO"}
    ratio: bpy.props.FloatProperty(name="늘어남 기준(배)", default=1.5, min=1.1, max=5.0)

    def execute(self, context):
        wm = context.window_manager
        arm = flow_objects(context)[0]
        if arm is None:
            self.report({"WARNING"}, "Bip이 없어요. 먼저 'Max에서 가져오기'"); return {"CANCELLED"}
        objs = [o for o in context.scene.objects if o.type == "MESH" and any(md.type == "ARMATURE" and md.object == arm for md in o.modifiers)]
        if not objs:
            self.report({"WARNING"}, "이 Bip에 연결된(웨이트 된) 메쉬가 없어요"); return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        _pt_begin(arm)
        up = _Vc((0, 0, 1)); front = _pt_front(arm)
        sp = _pt_bone(arm, "Spine1")
        if sp: _pt_rotate(arm, sp, _pt_dir(sp).cross(front), 20)          # 허리 앞으로
        hd = _pt_bone(arm, "Head")
        if hd: _pt_rotate(arm, hd, up, 30)                                  # 머리 돌리기
        for side in ("L", "R"):
            ua = _pt_bone(arm, side + " UpperArm")
            if ua: _pt_rotate(arm, ua, _pt_dir(ua).cross(up), 70)           # 팔 들기
        fa = _pt_bone(arm, "L Forearm")
        if fa: _pt_rotate(arm, fa, _pt_dir(fa).cross(front), 90)            # 왼팔꿈치 앞으로 굽힘
        th = _pt_bone(arm, "L Thigh")
        if th: _pt_rotate(arm, th, _pt_dir(th).cross(front), 60)            # 왼허벅지 앞으로
        ca = _pt_bone(arm, "L Calf")
        if ca: _pt_rotate(arm, ca, _pt_dir(ca).cross(-front), 90)           # 왼무릎 뒤로
        res = _pt_measure(arm, objs, self.ratio)
        lines = ["포즈 테스트 (%.1f배 넘게 늘어난 엣지)" % self.ratio]
        for r in res:
            name, cnt, regs = r[0], r[1], r[2]
            if cnt is None:
                lines.append("%s: 다른 모디파이어 때문에 측정 못함" % name); continue
            prev = _PT_LAST.get(name)
            diff = "" if prev is None else "  (지난번 %d)" % prev
            _PT_LAST[name] = cnt[0]
            top = ", ".join("%s %d" % (k, v) for k, v in sorted(regs.items(), key=lambda x: -x[1])[:4])
            lines.append("%s: %d / %d%s" % (name, cnt[0], cnt[1], diff))
            if top:
                lines.append("   부위(정점): " + top)
        wm.msr_status = " | ".join(lines)
        self.report({"INFO"}, lines[0] + " — 결과는 패널 아래")
        tag_redraw(context)
        return {"FINISHED"}


def _pt_begin(arm):
    """포즈 테스트 시작: 처음이면 원래 포즈·애니 저장, 애니 잠시 끄고 저장된 자세로 되돌림"""
    if "msr_pt_basis" not in arm:
        arm["msr_pt_basis"] = _json.dumps({pb.name: [v for row in pb.matrix_basis for v in row] for pb in arm.pose.bones})
        act = arm.animation_data.action if arm.animation_data else None
        arm["msr_pt_action"] = act.name if act else ""
    if arm.animation_data:
        arm.animation_data.action = None
    data = _json.loads(arm["msr_pt_basis"])
    for pb in arm.pose.bones:
        v = data.get(pb.name)
        if v:
            pb.matrix_basis = _Mx([v[i*4:i*4+4] for i in range(4)])
    bpy.context.view_layer.update()


def _pt_move(pb, d):
    """아마추어 공간에서 평행 이동"""
    if pb is None:
        return
    pb.matrix = _Mx.Translation(d) @ pb.matrix
    bpy.context.view_layer.update()


def _ft_region(name):
    n = name.lower()
    if "jaw" in n or "tongue" in n: return "턱"
    if "lip" in n: return "입술"
    if "brow" in n: return "눈썹"
    if "eye" in n: return "눈"
    if "cheek" in n: return "볼"
    return "머리(고정)"


class MSR_OT_face_test(bpy.types.Operator):
    """얼굴 테스트: 입 벌리기(턱 20°), 눈 감기, 눈썹 올리기, 입꼬리 올리기. 얼굴·이 메쉬가 부위별로 몇 정점 움직였는지와 늘어난 엣지를 셈"""
    bl_idname = "msr.face_test"
    bl_label = "얼굴 테스트"
    bl_options = {"REGISTER", "UNDO"}
    ratio: bpy.props.FloatProperty(name="늘어남 기준(배)", default=1.5, min=1.1, max=5.0)

    def execute(self, context):
        import numpy as np
        wm = context.window_manager
        arm, body, face, tooth = flow_objects(context)
        if arm is None:
            self.report({"WARNING"}, "Bip이 없어요"); return {"CANCELLED"}
        P = arm.pose.bones
        g = lambda n: P.get(n)
        if g("Bone_jaw") is None:
            self.report({"WARNING"}, "얼굴 본이 없어요 (② 얼굴·가슴 본 추가 먼저)"); return {"CANCELLED"}
        objs = [o for o in (face, tooth) if o is not None and any(md.type == "ARMATURE" and md.object == arm for md in o.modifiers)]
        if not objs:
            self.report({"WARNING"}, "웨이트 된 얼굴·이 메쉬가 없어요"); return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        _pt_begin(arm)
        up = _Vc((0, 0, 1)); front = _pt_front(arm)
        # 기준 크기: 눈 위·아래 본 간격, 입꼬리 간격
        eu, ed = g("Bone_eye_L_up"), g("Bone_eye_L_dn")
        eye_gap = (eu.head - ed.head).length if eu and ed else 0.5
        ll, lr = g("Bone_lip_L"), g("Bone_lip_R")
        mouth = (ll.head - lr.head).length if ll and lr else 2.0
        # 1) 입 벌리기: 턱 끝이 아래로 20°
        jaw = g("Bone_jaw")
        jd = (P["Bone_lip_dn"].head - jaw.head) if g("Bone_lip_dn") else front
        _pt_rotate(arm, jaw, jd.normalized().cross(-up), 20)
        # 2) 눈 감기: 위 눈꺼풀 내리고 아래 눈꺼풀 살짝 올림
        for sd in ("L", "R"):
            if g("Bone_eye_%s_up_in" % sd):      # 45 rig: lids pivot at the eyeball -> rotate shut
                side_ax = (P["Bone_lip_L"].head - P["Bone_lip_R"].head).normalized() if g("Bone_lip_L") else _Vc((1, 0, 0))
                for suf in ("_in", "", "_out"):
                    a, b = g("Bone_eye_%s_up%s" % (sd, suf)), g("Bone_eye_%s_dn%s" % (sd, suf))
                    if not (a and b):
                        continue
                    da, db = (a.tail - a.head), (b.tail - b.head)
                    ang = da.angle(db) * 57.2958
                    _pt_rotate(arm, a, side_ax, ang * (0.182, 0.456, 0.423)[("_in", "", "_out").index(suf)])  # eye-close standard r2 (Blender lid layout)
                    _pt_rotate(arm, b, side_ax, -ang * (0.176, 0.250, 0.395)[("_in", "", "_out").index(suf)])
                continue
            a, b = g("Bone_eye_%s_up" % sd), g("Bone_eye_%s_dn" % sd)
            if a and b:
                gap = (a.head - b.head).length
                _pt_move(a, -up * gap * 0.7)
                _pt_move(b, up * gap * 0.2)
        # 3) 눈썹 올리기
        for n in ("Bone_brow_L_in", "Bone_brow_L_mid", "Bone_brow_L_out", "Bone_brow_R_in", "Bone_brow_R_mid", "Bone_brow_R_out"):
            _pt_move(g(n), up * eye_gap * 0.8)
        # 4) 입꼬리 올리기(미소)
        if ll and lr:
            side = (ll.head - lr.head).normalized()
            _pt_move(g("Bone_lip_L"), (side * 0.1 + up * 0.12) * mouth)
            _pt_move(g("Bone_lip_R"), (-side * 0.1 + up * 0.12) * mouth)
        # 측정
        dg = context.evaluated_depsgraph_get()
        lines = ["얼굴 테스트 (입 벌림·눈 감기·눈썹·미소)"]
        for o in objs:
            me = o.data; n = len(me.vertices)
            rest = np.empty(n * 3); me.vertices.foreach_get("co", rest); rest = rest.reshape(-1, 3)
            ev = o.evaluated_get(dg); em = ev.to_mesh()
            if len(em.vertices) != n:
                ev.to_mesh_clear(); lines.append("%s: 측정 못함" % o.name); continue
            pos = np.empty(n * 3); em.vertices.foreach_get("co", pos); pos = pos.reshape(-1, 3); ev.to_mesh_clear()
            # 머리만 따라간 움직임을 빼려고 Bip Head만의 변형과 비교하는 대신, 머리 본이 고정이라 그대로 비교
            moved = np.linalg.norm(pos - rest, axis=1) > max(eye_gap * 0.05, 0.01)
            names = {gg.index: gg.name for gg in o.vertex_groups}
            regs = {}
            for vi in np.nonzero(moved)[0].tolist():
                v = me.vertices[vi]
                best = max(v.groups, key=lambda e: e.weight, default=None)
                r = _ft_region(names.get(best.group, "")) if best else "웨이트 없음"
                regs[r] = regs.get(r, 0) + 1
            ed2 = np.empty(len(me.edges) * 2, dtype=np.int64); me.edges.foreach_get("vertices", ed2); ed2 = ed2.reshape(-1, 2)
            l0 = np.linalg.norm(rest[ed2[:, 0]] - rest[ed2[:, 1]], axis=1); l1 = np.linalg.norm(pos[ed2[:, 0]] - pos[ed2[:, 1]], axis=1)
            ok = l0 > 1e-6; bad = int((l1[ok] / l0[ok] > self.ratio).sum())
            top = ", ".join("%s %d" % (k, v) for k, v in sorted(regs.items(), key=lambda x: -x[1]))
            lines.append("%s: 움직인 정점 %d / %d · %.1f배 넘게 늘어난 엣지 %d" % (o.name, int(moved.sum()), n, self.ratio, bad))
            if top:
                lines.append("   부위: " + top)
        miss = [k for k in ("턱", "입술", "눈", "눈썹") if not any(k in l for l in lines[1:])]
        if miss:
            lines.append("안 움직인 부위: " + ", ".join(miss) + " (웨이트 확인)")
        wm.msr_status = " | ".join(lines)
        self.report({"INFO"}, lines[0] + " — 결과는 패널 아래")
        tag_redraw(context)
        return {"FINISHED"}


class MSR_OT_pose_reset(bpy.types.Operator):
    """포즈 테스트 전 상태(포즈·애니)로 되돌림"""
    bl_idname = "msr.pose_reset"
    bl_label = "원래대로"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm = flow_objects(context)[0]
        if arm is None or "msr_pt_basis" not in arm:
            self.report({"INFO"}, "되돌릴 포즈 테스트가 없어요"); return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        data = _json.loads(arm["msr_pt_basis"])
        for pb in arm.pose.bones:
            v = data.get(pb.name)
            if v:
                pb.matrix_basis = _Mx([v[i*4:i*4+4] for i in range(4)])
        an = arm.get("msr_pt_action", "")
        if an and an in bpy.data.actions:
            if arm.animation_data is None:
                arm.animation_data_create()
            arm.animation_data.action = bpy.data.actions[an]
        del arm["msr_pt_basis"]
        if "msr_pt_action" in arm:
            del arm["msr_pt_action"]
        context.view_layer.update()
        context.window_manager.msr_status = "포즈 테스트 전으로 되돌림"
        tag_redraw(context)
        return {"FINISHED"}


class MSR_OT_mirror_bone(bpy.types.Operator):
    """지금 고른 본이 영향을 주는 정점의 웨이트 전체를 X축 반대편에 복사 (Bip01 L/R 이름도 바꿔줌)"""
    bl_idname = "msr.mirror_bone"
    bl_label = "이 본 → 반대편 복사"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = mesh_obj(context)
        if obj is None or obj.vertex_groups.active is None:
            self.report({"WARNING"}, "메쉬와 본(버텍스 그룹)을 먼저 고르세요"); return {"CANCELLED"}
        g = obj.vertex_groups.active
        gi = g.index
        with DataMode(context):
            me = obj.data
            keep_sel = [v.select for v in me.vertices]
            ids, xs, ws = [], [], []
            for v in me.vertices:
                for e in v.groups:
                    if e.group == gi and e.weight > 0.0001:
                        ids.append(v.index); xs.append(v.co.x); ws.append(e.weight); break
            if not ids:
                self.report({"WARNING"}, "'%s' 웨이트가 있는 정점이 없어요" % g.name); return {"CANCELLED"}
            mean = sum(x * w for x, w in zip(xs, ws)) / max(sum(ws), 1e-9)
            side = 1.0 if mean >= 0 else -1.0
            if flip_name(g.name) == g.name:     # 가운데 본(척추 등)은 L쪽(+X) → R쪽으로
                side = 1.0
            for v in me.vertices:
                v.select = False
            n = 0
            for vi, x in zip(ids, xs):
                if x * side > 0:
                    me.vertices[vi].select = True; n += 1
        r = bpy.ops.msr.mirror()
        with DataMode(context):
            for v, s_ in zip(obj.data.vertices, keep_sel):
                v.select = s_
        msg = "%s 영역 정점 %d개 → 반대편(%s) 복사" % (g.name, n, flip_name(g.name))
        context.window_manager.msr_status = msg
        self.report({"INFO"}, msg)
        tag_redraw(context)
        return {"FINISHED"}


class MSR_PT_flow(bpy.types.Panel):
    bl_label = "리깅 순서 (Max → 블렌더 → Max)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = TAB
    bl_order = 0

    def draw(self, context):
        lay = self.layout
        wm = context.window_manager
        arm, body, face, tooth = flow_objects(context)

        box = lay.box()
        box.label(text="1. Max: Biped를 모델에 맞추기", icon="CHECKBOX_HLT")
        box.label(text="   Max에서 바디·얼굴·이·Bip 선택")

        box = lay.box()
        box.label(text="2. 블렌더: 본 만들기 → Max에 본 생성", icon="BONE_DATA")
        c = box.column(align=True)
        c.scale_y = 1.3
        c.operator("msr.flow_import", text="① Max에서 가져오기", icon="IMPORT")
        if arm or body:
            g = box.column(align=True)
            g.scale_y = 0.85
            g.prop_search(wm, "msr_arm", bpy.data, "objects", text="Bip")
            g.prop_search(wm, "msr_body", bpy.data, "objects", text="바디")
            g.prop_search(wm, "msr_face", bpy.data, "objects", text="얼굴")
            g.prop_search(wm, "msr_tooth", bpy.data, "objects", text="이")
        c = box.column(align=True)
        c.scale_y = 1.3
        c.enabled = arm is not None
        has_face = bool(arm and "Bone_jaw" in arm.data.bones)
        has_br = bool(arm and "Bone_breast_L" in arm.data.bones)
        c.operator("msr.flow_bones", text="② 얼굴·가슴 본%s" % ("  (있음)" if has_face and has_br else ""),
                   icon="BONE_DATA")
        for s in wm.msr_bones_last.split(" | ")[:3] if wm.msr_bones_last else []:
            box.label(text=s)
        if _hb is not None:     # 2.2: 헤어 본을 파츠 본 위로
            sub = box.box()
            sub.label(text="③ 헤어 본 (가닥 자동)", icon="OUTLINER_OB_CURVES")
            _hb.draw(sub, context)
        if _ob is not None:
            sub = box.box()
            sub.label(text="③ 파츠 본 (오브젝트)", icon="MOD_EXPLODE")
            _ob.draw(sub, context)
        info = box.box()
        info.label(text="Max에서 본을 더하거나 링크를 바꿨으면", icon="INFO")
        info.label(text="→ ① 다시 가져오기 (본·링크·Max 웨이트를 읽어요)")

        box = lay.box()
        box.label(text="3. Max에 스킨 적용 (일괄)", icon="EXPORT")
        c = box.column(align=True)
        c.scale_y = 1.5
        c.enabled = arm is not None and body is not None
        c.operator("msr.flow_apply_all", text="스킨 적용 (일괄 계산 + Max 적용)", icon="EXPORT")
        box.label(text="바디 템플릿·가슴·얼굴·파츠·헤어 웨이트를 이때 계산")
        box.label(text="Max에서 칠한 파츠·손 본·헤어 웨이트는 그대로")
        pt = box.box()
        pt.label(text="⑤ 포즈 테스트 (잘 붙었나 확인)", icon="ARMATURE_DATA")
        row = pt.row(align=True)
        row.scale_y = 1.3
        row.enabled = arm is not None
        testing = bool(arm and "msr_pt_basis" in arm)
        row.operator("msr.pose_test", text="몸", icon="POSE_HLT")
        row.operator("msr.face_test", text="얼굴", icon="USER")
        row.operator("msr.pose_reset", text="원래대로", icon="LOOP_BACK", depress=testing)
        if testing:
            pt.label(text="테스트 중 · 확인 후 '원래대로'를 눌러요", icon="INFO")

        r = box.row()
        r.prop(wm, "msr_fix_open", text="블렌더에서 보정하기 (선택)",
               icon="TRIA_DOWN" if wm.msr_fix_open else "TRIA_RIGHT", emboss=False)
        if wm.msr_fix_open:
            sub = box.box()
            sub.operator("msr.flow_weights", text="웨이트만 다시 계산 (Max에 안 보냄)", icon="MOD_VERTEX_WEIGHT")
            row = sub.row(align=True)
            for key, lbl, o in (("BODY", "바디", body), ("FACE", "얼굴", face), ("TOOTH", "이", tooth)):
                r = row.row(align=True)
                r.enabled = o is not None
                cur = context.mode == "PAINT_WEIGHT" and mesh_obj(context) is o and o is not None
                op = r.operator("msr.flow_edit", text=lbl, depress=cur)
                op.target, op.mode = key, "KEEP"
            obj = mesh_obj(context)
            painting = context.mode == "PAINT_WEIGHT" and obj is not None
            vmode = painting and obj.data.use_paint_mask_vertex
            row = sub.row(align=True)
            op = row.operator("msr.flow_edit", text="칠하기 (브러시)", icon="BRUSH_DATA", depress=painting and not vmode)
            op.target, op.mode = "BODY", "PAINT"
            op = row.operator("msr.flow_edit", text="수치 (정점 선택)", icon="VERTEXSEL", depress=bool(vmode))
            op.target, op.mode = "BODY", "VERTEX"
            if not painting:
                sub.label(text="위에서 메쉬를 누르면 편집 시작")
            else:
                g = obj.vertex_groups.active
                sub.label(text="본: " + (g.name if g else "(없음)") + "   · Ctrl+클릭으로 본 선택", icon="BONE_DATA")
                mrow = sub.row(align=True)
                mrow.enabled = g is not None
                mrow.operator("msr.mirror_bone", text="이 본 → 반대편 복사", icon="MOD_MIRROR")
                if obj.data.use_mirror_x and g is not None and bpy.utils.flip_name(g.name) == g.name and flip_name(g.name) != g.name:
                    warn = sub.box()
                    warn.label(text="Bip 이름(예: Bip01 L Thigh)은 블렌더 대칭이", icon="ERROR")
                    warn.label(text="반대편 본을 못 찾아 같은 본으로 칠해져요")
                    warn.label(text="→ 대칭 끄고 칠한 뒤 '이 본 → 반대편 복사'")
                sub.template_list("MESH_UL_vgroups", "", obj, "vertex_groups", obj.vertex_groups, "active_index", rows=4)
                if not vmode:
                    ts = context.tool_settings
                    ups = ts.weight_paint.unified_paint_settings
                    br = ts.weight_paint.brush
                    row = sub.row(align=True)
                    for b, lbl in (("Paint", "칠하기"), ("Blur", "부드럽게"), ("Average", "평균"), ("Smear", "문지르기")):
                        row.operator("msr.flow_brush", text=lbl, depress=bool(br and br.name == b)).brush = b
                    col = sub.column(align=True)
                    for p, lbl in (("weight", "웨이트 값"), ("size", "크기 ([ ])"), ("strength", "세기")):
                        src = ups if getattr(ups, "use_unified_" + p, False) or br is None else br
                        if hasattr(src, p):
                            col.prop(src, p, text=lbl, slider=(p != "size"))
                    row = sub.row(align=True)
                    row.prop(obj.data, "use_mirror_x", text="좌우 대칭", toggle=True)
                    if hasattr(obj.data, "use_mirror_vertex_groups"):
                        row.prop(obj.data, "use_mirror_vertex_groups", text="L/R 본 대칭", toggle=True)
                    sub.label(text="Ctrl 누르고 칠하기 = 빼기")
                else:
                    for vals in ((0.0, 0.1, 0.25, 0.5), (0.75, 0.9, 1.0)):
                        row = sub.row(align=True)
                        for v in vals:
                            row.operator("msr.set_weight", text=("%g" % v)).value = v
                    row = sub.row(align=True)
                    row.operator("msr.set_weight", text="+").delta = wm.msr_step
                    row.operator("msr.set_weight", text="-").delta = -wm.msr_step
                    row.prop(wm, "msr_step", text="")
                    row = sub.row(align=True)
                    row.operator("msr.blend", text="Blend")
                    row.operator("msr.mirror", text="Mirror")
                    row.operator("msr.copy", text="Copy")
                    row.operator("msr.paste", text="Paste")
                    row = sub.row(align=True)
                    row.operator("msr.grow", text="Grow").shrink = False
                    row.operator("msr.grow", text="Shrink").shrink = True
                    row.operator("msr.ring_loop", text="Loop").ring = False
                    row.operator("msr.ring_loop", text="Ring").ring = True
                    row = sub.row(align=True)
                    row.operator("msr.select_bone_verts", text="이 본 정점 선택")
                sub.operator("msr.check", text="웨이트 검사 (문제 정점 선택)", icon="CHECKMARK").limit = wm.msr_limit
            c = sub.column(align=True)
            c.scale_y = 1.3
            c.enabled = body is not None or face is not None
            c.operator("msr.flow_send", text="보정한 그대로 Max에 적용", icon="EXPORT")
            sub.label(text="정리(정점당 %d본·합계 1) 후 보내요" % wm.msr_limit)

        if wm.msr_status:
            sb = lay.box()
            for line in wm.msr_status.split(" | "):
                sb.label(text=line[:80])


def _adv_poll(cls, context):
    return context.window_manager.msr_advanced


# ============================================================ UI
class MSR_PT_main(bpy.types.Panel):
    bl_label = "Max 작업 환경 (단축키)"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 1
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = TAB

    def draw(self, context):
        lay = self.layout
        prefs = context.preferences.addons[__name__].preferences
        col = lay.column(align=True)
        row = col.row(align=True)
        row.operator("msr.quad_view", icon="VIEW_ORTHO")
        row.operator("view3d.toggle_xray", text="반투명(Alt+X)", icon="XRAY")
        row = col.row(align=True)
        row.prop(prefs, "max_keys", text="Max 단축키 사용")
        wm = context.window_manager
        row.prop(wm, "msr_show_keys", text="", icon="QUESTION")
        if prefs.max_keys and wm.msr_show_keys:
            box = lay.box()
            for t in ("이 PC Max 단축키(Sun.kbdx)와 같아요",
                      "F 앞  B 뒤  T 위  Ctrl+E 왼쪽  Ctrl+R 오른쪽  P 퍼스펙  U 직교  C 카메라",
                      "Q 선택  W/E/R 이동·회전·스케일",
                      "S·. 다음 프레임  A·, 이전 프레임  Space 재생  Home/End 처음·끝",
                      "X·K 키  (N 은 Blender 사이드바 그대로)",
                      "1·PgUp 부모  2·PgDn 자식  Ctrl+A/D/I 전체·해제·반전  H 이름으로",
                      "Z 선택 줌  Ctrl+Alt+Z 전체 줌  Alt+Z 줌  Ctrl+W 영역 줌  Alt+W 최대화",
                      "F3 와이어  F4 엣지  G 그리드  Alt+Q 고립  Alt+X 반투명",
                      "편집 메쉬: 1 점 2 선 4 면 6 오브젝트  Alt+H/I/U 숨기기",
                      "휠클릭 이동  Alt+휠클릭 회전  Ctrl+Alt+휠클릭 줌  Ctrl+Y 다시"):
                box.label(text=t)


class MSR_PT_figure(bpy.types.Panel):
    poll = classmethod(_adv_poll)
    bl_label = "1. 골격 맞추기"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = TAB

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("msr.from_max", icon="IMPORT")
        on = context.mode == "EDIT_ARMATURE"
        col.operator("msr.figure_mode", text="피규어 모드 끄기" if on else "피규어 모드 (골격 맞추기)",
                     icon="ARMATURE_DATA", depress=on)
        if on:
            col.prop(context.active_object.data, "use_mirror_x", text="좌우 대칭 편집")
            col.label(text="본 끝을 잡고 W(이동)로 메쉬에 맞추세요", icon="INFO")
        box = self.layout.box()
        box.label(text="Rigify로 시작", icon="OUTLINER_OB_ARMATURE")
        c = box.column(align=True)
        c.operator("msr.rigify_metarig", icon="ADD")
        c.operator("msr.rigify_generate", icon="POSE_HLT")
        c.label(text="Max: BipFit '뼈대 종류 = Rigify'로 Biped 맞춤")
        box = self.layout.box()
        box.label(text="게임용 얼굴 본 (45개)", icon="USER")
        c = box.column(align=True)
        c.operator("msr.face_bones", icon="BONE_DATA")
        c.label(text="얼굴 메쉬 선택 후 실행 · Bip 머리 아래 생성")


class MSR_PT_weight(bpy.types.Panel):
    poll = classmethod(_adv_poll)
    bl_label = "2. 웨이트 툴 (Skin)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = TAB

    def draw(self, context):
        lay = self.layout
        wm = context.window_manager
        obj = mesh_obj(context)
        box = lay.box()
        box.label(text="바디 자동 웨이트 (Bip 직접)", icon="ARMATURE_DATA")
        c = box.column(align=True)
        c.operator("msr.breast_bones", icon="BONE_DATA")
        c.operator("msr.bip_auto_weights", icon="MOD_VERTEX_WEIGHT")
        lay.operator("msr.weight_mode", icon="MOD_VERTEX_WEIGHT")
        if obj is None:
            lay.label(text="메쉬를 선택하세요")
            return
        g = obj.vertex_groups.active
        lay.label(text="본: " + (g.name if g else "(없음)"), icon="BONE_DATA")
        lay.template_list("MESH_UL_vgroups", "", obj, "vertex_groups", obj.vertex_groups, "active_index", rows=5)

        box = lay.box()
        box.label(text="웨이트 값")
        for vals in ((0.0, 0.1, 0.25, 0.5), (0.75, 0.9, 1.0)):
            row = box.row(align=True)
            for v in vals:
                op = row.operator("msr.set_weight", text=("%g" % v))
                op.value = v
        row = box.row(align=True)
        row.prop(wm, "msr_value", text="")
        op = row.operator("msr.set_weight", text="Set")
        op.value = wm.msr_value
        row = box.row(align=True)
        op = row.operator("msr.set_weight", text="+")
        op.delta = wm.msr_step
        op = row.operator("msr.set_weight", text="-")
        op.delta = -wm.msr_step
        row.prop(wm, "msr_step", text="")
        row = box.row(align=True)
        row.operator("msr.blend", icon="MOD_SMOOTH")
        row.operator("msr.copy", icon="COPYDOWN")
        row.operator("msr.paste", icon="PASTEDOWN")
        box.operator("msr.mirror", icon="MOD_MIRROR")

        box = lay.box()
        box.label(text="선택")
        row = box.row(align=True)
        op = row.operator("msr.grow", text="Grow")
        op.shrink = False
        op = row.operator("msr.grow", text="Shrink")
        op.shrink = True
        row = box.row(align=True)
        op = row.operator("msr.ring_loop", text="Ring")
        op.ring = True
        op = row.operator("msr.ring_loop", text="Loop")
        op.ring = False
        box.operator("msr.select_bone_verts", icon="RESTRICT_SELECT_OFF")

        # weights of the reference vertex
        if context.mode in ("PAINT_WEIGHT", "OBJECT"):
            me = obj.data
            deform = deform_group_indices(obj)
            sel = [v for v in me.vertices if v.select] if len(me.vertices) < 200000 else []
            if sel:
                box = lay.box()
                box.label(text="선택 정점 %d개 · 첫 정점 #%d 웨이트" % (len(sel), sel[0].index))
                d = sorted(vweights(sel[0], deform).items(), key=lambda kv: -kv[1])
                for k, w in d[:8]:
                    r = box.row(align=True)
                    op = r.operator("msr.set_active_group", text=obj.vertex_groups[k].name, emboss=False,
                                    depress=(g is not None and k == g.index))
                    op.name = obj.vertex_groups[k].name
                    r.label(text="%.3f" % w)


class MSR_PT_finish(bpy.types.Panel):
    poll = classmethod(_adv_poll)
    bl_label = "3. 정리 · Max로 보내기"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = TAB

    def draw(self, context):
        lay = self.layout
        wm = context.window_manager
        col = lay.column(align=True)
        col.prop(wm, "msr_limit", text="정점당 최대 본")
        op = col.operator("msr.check", icon="CHECKMARK")
        op.limit = wm.msr_limit
        op = col.operator("msr.clean", icon="BRUSH_DATA")
        op.limit = wm.msr_limit
        col.separator()
        col.prop(wm, "msr_target", text="Max 메쉬 이름")
        col.operator("msr.send_weights", icon="EXPORT")
        if wm.msr_status:
            box = lay.box()
            for line in wm.msr_status.split(" | "):
                box.label(text=line[:80])


# ============================================================ Max keymap
addon_keymaps = []


def _add(km, idname, key, value="PRESS", **kw):
    props = kw.pop("props", {})
    kmi = km.keymap_items.new(idname, key, value, **kw)
    for k, v in props.items():
        setattr(kmi.properties, k, v)
    addon_keymaps.append((km, kmi))
    return kmi


# Max 단축키: 이 PC Max 의 키보드 파일 (D:\1_Sun_Work\Sun.kbdx, 2026-10-29) 과 같게.
#   Max 기본에서 바꾼 것: B 뒤 / Ctrl+R 오른쪽 / Ctrl+E 왼쪽 / S·A 한 프레임 앞·뒤 / Space 재생 / X 키 / 1·2 부모·자식 선택
#   (Blender 기본 키보다 먼저 적용됨. Max 리깅 탭 > 'Max 단축키 사용' 끄면 Blender 기본으로)
MAX_VIEW_KEYS = (("T", {}, "TOP"), ("B", {}, "BACK"), ("F", {}, "FRONT"), ("E", {"ctrl": True}, "LEFT"),
                 ("R", {"ctrl": True}, "RIGHT"), ("P", {}, "PERSP"), ("U", {}, "USER"), ("C", {}, "CAMERA"))


def register_keys():
    kc = bpy.context.window_manager.keyconfigs.addon
    if not kc:
        return
    modes = ["Object Mode", "Pose", "Armature", "Mesh"]
    allk = modes + ["Weight Paint", "3D View"]

    def km_of(name):
        return kc.keymaps.new(name=name, space_type="VIEW_3D" if name == "3D View" else "EMPTY")
    # 도구: Q 선택 W 이동 E 회전 R 스케일
    for name in modes:
        km = km_of(name)
        _add(km, "wm.tool_set_by_id", "W", props={"name": "builtin.move"})
        _add(km, "wm.tool_set_by_id", "E", props={"name": "builtin.rotate"})
        _add(km, "wm.tool_set_by_id", "R", props={"name": "builtin.scale"})
        _add(km, "wm.tool_set_by_id", "Q", props={"name": "builtin.select_box"})
    km = km_of("Weight Paint")
    _add(km, "wm.tool_set_by_id", "Q", props={"name": "builtin.select_box"})
    _add(km, "brush.scale_size", "LEFT_BRACKET", props={"scalar": 0.9})
    _add(km, "brush.scale_size", "RIGHT_BRACKET", props={"scalar": 1.0 / 0.9})
    for name in allk:
        km = km_of(name)
        # 뷰
        for key, mods, view in MAX_VIEW_KEYS:
            _add(km, "msr.max_view", key, props={"view": view}, **mods)
        # 애니: S·. 한 프레임 앞, A·, 한 프레임 뒤, Space·/ 재생, Home·End 처음·끝, X·K 키 (N 은 Blender 사이드바 그대로)
        for key, d in (("S", 1), ("PERIOD", 1), ("A", -1), ("COMMA", -1)):
            _add(km, "screen.frame_offset", key, props={"delta": d})
        _add(km, "screen.animation_play", "SPACE")
        _add(km, "screen.animation_play", "SLASH")
        _add(km, "screen.frame_jump", "HOME", props={"end": False})
        _add(km, "screen.frame_jump", "END", props={"end": True})
        if name in ("Object Mode", "Pose"):
            _add(km, "anim.keyframe_insert", "X")
            _add(km, "anim.keyframe_insert", "K")
        # 뷰포트
        _add(km, "msr.zoom", "Z")
        _add(km, "view3d.view_all", "Z", ctrl=True, alt=True, props={"center": False})
        _add(km, "view3d.view_all", "Z", ctrl=True, shift=True, props={"use_all_regions": True, "center": False})
        _add(km, "view3d.zoom", "Z", alt=True)
        _add(km, "view3d.zoom_border", "W", ctrl=True)
        _add(km, "view3d.move", "P", ctrl=True)
        _add(km, "screen.screen_full_area", "W", alt=True)
        _add(km, "view3d.toggle_shading", "F3", props={"type": "WIREFRAME"})
        _add(km, "wm.context_toggle", "F4", props={"data_path": "space_data.overlay.show_wireframes"})
        _add(km, "wm.context_toggle", "G", props={"data_path": "space_data.overlay.show_floor"})
        _add(km, "view3d.toggle_xray", "X", alt=True)
        _add(km, "view3d.localview", "Q", alt=True)
        if name != "Weight Paint":
            _add(km, "view3d.zoom", "RIGHT_BRACKET", props={"delta": -1})
            _add(km, "view3d.zoom", "LEFT_BRACKET", props={"delta": 1})
        _add(km, "view3d.zoom", "EQUAL", ctrl=True, props={"delta": 1})
        _add(km, "view3d.zoom", "MINUS", ctrl=True, props={"delta": -1})
        # 마우스: 휠클릭 이동, Alt+휠클릭 회전, Ctrl+Alt+휠클릭 줌
        _add(km, "view3d.move", "MIDDLEMOUSE")
        _add(km, "view3d.rotate", "MIDDLEMOUSE", alt=True)
        _add(km, "view3d.zoom", "MIDDLEMOUSE", ctrl=True, alt=True)
    # 선택: Ctrl+A 전체 / Ctrl+D 해제 / Ctrl+I 반전, 1·PgUp 부모 / 2·PgDn 자식, H 이름으로 선택, Ctrl+V 복제
    sel = {"Object Mode": "object.select_all", "Pose": "pose.select_all", "Armature": "armature.select_all", "Mesh": "mesh.select_all"}
    for name, op in sel.items():
        km = km_of(name)
        _add(km, op, "A", ctrl=True, props={"action": "SELECT"})
        _add(km, op, "D", ctrl=True, props={"action": "DESELECT"})
        _add(km, op, "I", ctrl=True, props={"action": "INVERT"})
    hier = {"Object Mode": "object.select_hierarchy", "Pose": "pose.select_hierarchy", "Armature": "armature.select_hierarchy"}
    for name, op in hier.items():
        km = km_of(name)
        for key in ("ONE", "PAGE_UP"):
            _add(km, op, key, props={"direction": "PARENT", "extend": False})
        for key in ("TWO", "PAGE_DOWN"):
            _add(km, op, key, props={"direction": "CHILD", "extend": False})
    km = km_of("Object Mode")
    _add(km, "object.select_pattern", "H")
    _add(km, "object.duplicate_move", "V", ctrl=True)
    _add(km, "object.select_grouped", "PAGE_DOWN", ctrl=True, props={"type": "CHILDREN_RECURSIVE", "extend": True})
    # Editable Poly: 1 점 2 선 3 경계(선) 4·5 면 6 오브젝트, Ctrl+PgUp/PgDn 넓히기/줄이기, Alt+H/U/I 숨기기
    km = km_of("Mesh")
    for key, t in (("ONE", "VERT"), ("TWO", "EDGE"), ("THREE", "EDGE"), ("FOUR", "FACE"), ("FIVE", "FACE")):
        _add(km, "mesh.select_mode", key, props={"type": t})
    _add(km, "object.mode_set", "SIX", props={"mode": "OBJECT"})
    _add(km, "mesh.select_more", "PAGE_UP", ctrl=True)
    _add(km, "mesh.select_less", "PAGE_DOWN", ctrl=True)
    _add(km, "mesh.hide", "H", alt=True, props={"unselected": False})
    _add(km, "mesh.hide", "I", alt=True, props={"unselected": True})
    _add(km, "mesh.reveal", "U", alt=True)
    _add(km, "view3d.edit_mesh_extrude_move_normal", "E", shift=True)
    _add(km, "mesh.knife_tool", "C", alt=True)
    # 되돌리기: Ctrl+Z / Ctrl+Y
    km = kc.keymaps.new(name="Screen", space_type="EMPTY")
    _add(km, "ed.redo", "Y", ctrl=True)


def unregister_keys():
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    addon_keymaps.clear()


def _keys_update(self, context):
    unregister_keys()
    if self.max_keys:
        register_keys()


class MSR_Prefs(bpy.types.AddonPreferences):
    bl_idname = __name__
    max_keys: bpy.props.BoolProperty(name="Max 단축키", default=True, update=_keys_update)

    def draw(self, context):
        self.layout.prop(self, "max_keys")


class _NoLayout:
    """stand-in layout that ignores every call (hides the ④ 보정 block in 오브젝트 본 mode)"""
    def __getattr__(self, name):
        return lambda *a, **k: self

    def __setattr__(self, name, value):
        pass


# ④ 오브젝트 본 (object_bones.py next to this file)
try:
    import sys as _sys
    _d = os.path.dirname(os.path.abspath(__file__))
    if _d not in _sys.path:
        _sys.path.insert(0, _d)
    import object_bones as _ob
except Exception as _e:
    print("object_bones:", _e)
    _ob = None
# 헤어 본 (hair_bones.py next to this file)
try:
    import hair_bones as _hb
except Exception as _e:
    print("hair_bones:", _e)
    _hb = None


classes = (
    MSR_Prefs, MSR_OT_set_weight, MSR_OT_blend, MSR_OT_copy, MSR_OT_paste, MSR_OT_mirror, MSR_OT_clean,
    MSR_OT_select_bone_verts, MSR_OT_grow, MSR_OT_ring_loop, MSR_OT_set_active_group, MSR_OT_check,
    MSR_OT_weight_mode, MSR_OT_figure_mode, MSR_OT_rigify_metarig, MSR_OT_rigify_generate, MSR_OT_face_bones, MSR_OT_breast_bones, MSR_OT_bip_auto_weights, MSR_OT_zoom, MSR_OT_max_view, MSR_OT_quad_view, MSR_OT_send_weights, MSR_OT_from_max,
    MSR_OT_flow_import, MSR_OT_flow_bones, MSR_OT_flow_weights, MSR_OT_flow_edit, MSR_OT_flow_brush, MSR_OT_flow_send, MSR_OT_flow_apply_all, MSR_OT_flow_fit, MSR_OT_flow_fit_mirror, MSR_OT_flow_fit_apply, MSR_OT_pose_test, MSR_OT_face_test, MSR_OT_pose_reset, MSR_OT_mirror_bone,
    MSR_PT_flow, MSR_PT_main,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    WM = bpy.types.WindowManager
    WM.msr_clip = bpy.props.StringProperty(default="")
    WM.msr_body = bpy.props.StringProperty(default="")
    WM.msr_show_keys = bpy.props.BoolProperty(default=False, description="단축키 목록 보기")
    WM.msr_status = bpy.props.StringProperty(default="")
    WM.msr_target = bpy.props.StringProperty(name="Max 메쉬 이름", default="",
                                             description="비우면 블렌더 오브젝트 이름과 같은 Max 메쉬")
    WM.msr_value = bpy.props.FloatProperty(default=0.5, min=0.0, max=1.0, precision=3)
    WM.msr_step = bpy.props.FloatProperty(default=0.05, min=0.001, max=0.5, precision=3)
    WM.msr_limit = bpy.props.IntProperty(default=4, min=1, max=8)
    WM.msr_arm = bpy.props.StringProperty(name="Bip", default="")
    WM.msr_face = bpy.props.StringProperty(name="얼굴", default="")
    WM.msr_tooth = bpy.props.StringProperty(name="이", default="")
    WM.msr_advanced = bpy.props.BoolProperty(name="예전 도구 모두 보기", default=False)
    WM.msr_bones_last = bpy.props.StringProperty(default="")
    WM.msr_fix_open = bpy.props.BoolProperty(default=False, description="블렌더에서 웨이트를 칠하거나 수치로 고친 뒤 그대로 보내기")
    WM.msr_p4 = bpy.props.EnumProperty(items=[("EDIT", "보정", "웨이트 칠하기·수치"), ("OB", "오브젝트 본", "파츠별 본 자동 생성")], default="OB")
    if _ob is not None:
        _ob.register()
    if _hb is not None:
        _hb.register()
    try:
        if bpy.context.preferences.addons[__name__].preferences.max_keys:
            register_keys()
    except Exception:
        register_keys()


def unregister():
    unregister_keys()
    if _ob is not None:
        _ob.unregister()
    if _hb is not None:
        _hb.unregister()
    WM = bpy.types.WindowManager
    for p in ("msr_clip", "msr_body", "msr_show_keys", "msr_status", "msr_target", "msr_value", "msr_step", "msr_limit", "msr_arm", "msr_face", "msr_tooth", "msr_advanced", "msr_p4", "msr_bones_last", "msr_fix_open"):
        try:
            delattr(WM, p)
        except Exception:
            pass
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
