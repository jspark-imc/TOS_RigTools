# rig_template.py  (Claude, 2026-10-30)
# Rig Tools [6. 리깅 완료] → Max 가 내보낸 캐시(tplcache/<id>)를 템플릿 폴더에 정리해서 저장하고,
#   ① 찢어짐 검사 (테스트 키 프레임에서 엣지가 3배 넘게 늘어난 곳)
#   ② 몸 웨이트 템플릿 (body_template 형식, 체형 비율과 함께) → 다음 캐릭터는 체형이 가장 가까운 템플릿 사용
#   ③ 세컨더리(치마·망토·헤어·장식) 웨이트 수치 → secondary_weight_ref.json 다시 계산 (rig_test 기준값 + 저장된 캐릭터)
#   ④ 자동 값(스킨 적용 때 보낸 값) → 최종 값 차이 (사람이 어디를 얼마나 고쳤는지)
# 원본(raw/)은 다시 분석할 수 있게 전부 압축 보관.
import os, re, json, gzip, shutil, time, getpass
from collections import Counter, defaultdict
import numpy as np
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
JOB_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "GE_RigJobs")
SENT_DIR = os.path.join(JOB_DIR, "sent")
DIR_FILE = os.path.join(JOB_DIR, "tpl_dir.txt")
DEFAULT_DIR = r"E:\anisrc\ani_tip\ai\00_3_리깅 웨이트 템플릿"
REF_PATH = os.path.join(HERE, "secondary_weight_ref.json")
QC_BAD_EDGES = 20          # 찢어진 엣지가 이보다 많으면 참고값·템플릿 계산에서 뺌 (기록은 남김)
SKIP_TPL = ("skirt", "cape", "hair", "bone_obj")
FRAME_NAMES = {10: "팔 위로", 30: "팔 앞으로", 50: "팔꿈치 굽힘", 70: "손목 비틀기", 100: "허리 숙이기", 110: "허리 옆으로",
               120: "허리 비틀기", 180: "앞차기", 200: "무릎 굽힘", 210: "스쿼트", 230: "다리 옆으로"}


# ---------------------------------------------------------------- 폴더
def tpl_dir():
    try:
        d = open(DIR_FILE, encoding="utf-8").read().strip()
        if d and os.path.isdir(d):
            return d
    except Exception:
        pass
    return DEFAULT_DIR if os.path.isdir(DEFAULT_DIR) else ""


# ---------------------------------------------------------------- 캐시 읽기
def read_info(d):
    info = {"meshes": [], "frames": []}
    for l in open(os.path.join(d, "info.txt"), encoding="utf-8-sig"):
        p = l.rstrip("\n").split("\t")
        if p[0] == "mesh" and len(p) >= 4:
            info["meshes"].append(dict(k=int(p[1]), name=p[2], nv=int(p[3]), nf=int(p[4]) if len(p) > 4 else 0,
                                       limit=int(float(p[5])) if len(p) > 5 and p[5] else 4))
        elif p[0] == "frames":
            info["frames"] = [int(x) for x in re.findall(r"\d+", p[1] if len(p) > 1 else "")]
        elif len(p) > 1:
            info[p[0]] = "\t".join(p[1:])
    return info


def read_xyz(path, cols=3):
    if not os.path.exists(path):
        return None
    a = np.loadtxt(path, ndmin=2, encoding="utf-8-sig")
    return a[:, :cols] if a.size else np.zeros((0, cols))


def read_weights(path):
    out = []
    for l in open(path, encoding="utf-8-sig"):
        w = {}
        for t in l.rstrip("\n").split("\t"):
            if "=" in t:
                n, x = t.rsplit("=", 1)
                w[n] = w.get(n, 0.0) + float(x)
        out.append(w)
    return out


def read_sent(path):
    """스킨 적용 때 보낸 값 (#BONES 헤더 + 'i:w' 줄, Max 정점 순서)"""
    if not os.path.exists(path):
        return None
    f = open(path, encoding="utf-8")
    names = f.readline().rstrip("\n").split("\t")[1:]
    out = []
    for l in f:
        w = {}
        for t in l.split():
            i, x = t.split(":")
            w[names[int(i)]] = float(x)
        out.append(w)
    return out


def read_bones(d):
    B = {}
    p_ = os.path.join(d, "bones.txt")
    if not os.path.exists(p_):
        return B
    for l in open(p_, encoding="utf-8-sig"):
        p = l.rstrip("\n").split("\t")
        if len(p) < 6:
            continue
        B[p[0]] = dict(layer=p[1], parent=p[2], cls=p[3], h=np.array([float(x) for x in p[4].split()]),
                       t=np.array([float(x) for x in p[5].split()]))
    return B


# ---------------------------------------------------------------- Biped → Blender 뼈대 (스킨 파이프라인과 같은 가져오기)
def bip_segments(fbx):
    import body_template as bt
    win = bpy.context.window
    old = win.scene
    sc = bpy.data.scenes.new("tpl_tmp")
    win.scene = sc
    try:
        bpy.ops.import_scene.fbx(filepath=fbx, use_anim=False, ignore_leaf_bones=False, force_connect_children=False,
                                 automatic_bone_orientation=False, primary_bone_axis="Y", secondary_bone_axis="X")
        arm = [o for o in sc.objects if o.type == "ARMATURE"][0]
        segs = bt._segments(arm)
        s = float(arm.matrix_world.to_scale()[0])
    finally:
        objs = list(sc.objects)
        win.scene = old
        for o in objs:
            dat = o.data
            bpy.data.objects.remove(o)
            try:
                if dat is not None and dat.users == 0:
                    bpy.data.armatures.remove(dat)
            except Exception:
                pass
        bpy.data.scenes.remove(sc)
    return segs, s


def feat_of(segs):
    """체형 비율: 관절 사이 거리 / 키 (Head - Foot 높이)"""
    S = {n: np.array(h) for n, h, t, R, L in segs}
    try:
        H = float(S["Bip01 Head"][2] - S["Bip01 L Foot"][2])

        def d(a, b):
            return float(np.linalg.norm(S[a] - S[b])) / H
        return dict(thigh=d("Bip01 L Thigh", "Bip01 L Calf"), calf=d("Bip01 L Calf", "Bip01 L Foot"),
                    upper=d("Bip01 L UpperArm", "Bip01 L Forearm"), fore=d("Bip01 L Forearm", "Bip01 L Hand"),
                    torso=d("Bip01 Pelvis", "Bip01 Neck"), neck=d("Bip01 Neck", "Bip01 Head"),
                    hip=d("Bip01 L Thigh", "Bip01 R Thigh"), shoulder=d("Bip01 L UpperArm", "Bip01 R UpperArm"))
    except Exception:
        return {}


FEAT_KEYS = ("thigh", "calf", "upper", "fore", "torso", "neck", "hip", "shoulder")


def feat_dist(a, b):
    ks = [k for k in FEAT_KEYS if k in a and k in b]
    if not ks:
        return 1e9
    return float(np.sqrt(sum((a[k] - b[k]) ** 2 for k in ks) / len(ks)))


# ---------------------------------------------------------------- 메쉬 종류
def mesh_role(W):
    n = len(W) or 1
    body = sum(1 for w in W if w and (lambda t: t.lower().startswith("bip01") and "head" not in t.lower())(max(w, key=w.get)))
    return body / n


# ---------------------------------------------------------------- ① 찢어짐 검사
def stretch_check(d, info):
    rep = {}
    total = 0
    for m in info["meshes"]:
        k = m["k"]
        P0 = read_xyz(os.path.join(d, "mesh_%d.txt" % k))
        F = read_xyz(os.path.join(d, "faces_%d.txt" % k))
        if P0 is None or F is None or not len(F):
            continue
        F = F.astype(np.int64) - 1
        E = np.unique(np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1), axis=0)
        l0 = np.linalg.norm(P0[E[:, 0]] - P0[E[:, 1]], axis=1)
        ok = l0 > 1e-4
        for t in info["frames"]:
            Pt = read_xyz(os.path.join(d, "pose_%d_%d.txt" % (k, t)))
            if Pt is None or len(Pt) != len(P0):
                continue
            l1 = np.linalg.norm(Pt[E[:, 0]] - Pt[E[:, 1]], axis=1)
            # 3배 넘게 늘어나고 실제로 1cm(Max 1) 넘게 벌어진 엣지만 (아주 짧은 엣지의 작은 흔들림은 빼고)
            bad = int((((l1[ok] / l0[ok]) > 3.0) & ((l1[ok] - l0[ok]) > 1.0)).sum())
            if bad:
                rep.setdefault(m["name"], {})[t] = bad
                total += bad
    return total, rep


# ---------------------------------------------------------------- ② 몸 템플릿
def body_template_data(segs, scale, P, N, W):
    bones = sorted({k for w in W for k in w if not any(s in k.lower() for s in SKIP_TPL)})
    bi = {b: i for i, b in enumerate(bones)}
    rows_i, rows_w, keep = [], [], []
    for v, w in enumerate(W):
        ww = {k: x for k, x in w.items() if k in bi}
        if not ww or sum(ww.values()) < 0.5:
            continue
        it = sorted(ww.items(), key=lambda kv: -kv[1])[:4]
        s = sum(x for _, x in it)
        rows_i.append([bi[k] for k, _ in it] + [-1] * (4 - len(it)))
        rows_w.append([x / s for _, x in it] + [0.0] * (4 - len(it)))
        keep.append(v)
    return dict(version=1, bones=bones,
                segs=[dict(name=n, h=np.asarray(h).tolist(), t=np.asarray(t).tolist(), R=np.asarray(R).tolist(), L=float(L)) for n, h, t, R, L in segs],
                P=np.round(P[keep] * scale, 6).tolist(), N=np.round(N[keep], 4).tolist(), wi=rows_i, ww=np.round(rows_w, 5).tolist())


# ---------------------------------------------------------------- ③ 세컨더리 수치 (rig_test 분석과 같은 방식)
HELPER = re.compile(r"^bone_?(waist|neck$|neck0|leg_?[LR](up|dw|dn)|knee_?[LR]$|hip_?[LR]$|armpit|elbow|arm_?[LR]$|arm_?up_?[LR]\d*$|[LR]_?upperarm|spine_?[LR]\d*$|breast|bast)|twist|^point|^dummy|^ndummy|^nbone|clavicle", re.I)
FACE = re.compile(r"^bone_?(eye|eyebrow|brow|jaw|lip|cheek|tongue|mouth|teeth|nose)|^bone_head", re.I)


def is_sec(n, b):
    if n.lower().startswith("bip01") or HELPER.search(n) or FACE.search(n):
        return False
    if b["layer"].lower() in ("bone_head", "bip"):
        return False
    return b["cls"] == "BoneGeometry"


def kind_of(n):
    l = n.lower()
    return "skirt" if "skirt" in l else "cape" if ("cape" in l or "cloak" in l) else "hair" if "hair" in l else "etc"


def chains(B, sec):
    kids = defaultdict(list)
    for n in sec:
        kids[B[n]["parent"]].append(n)
    out = []

    def walk(n, path):
        ks = kids.get(n, [])
        if len(ks) == 1:
            return walk(ks[0], path + [n])
        out.append(path + [n])
        for k in ks:
            walk(k, [])
    for r in [n for n in sec if B[n]["parent"] not in sec]:
        walk(r, [])
    return out


def _seg_param(p, pts):
    best = (1e18, 0, 0.0)
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        d = b - a
        L2 = d @ d
        s = 0.0 if L2 < 1e-9 else float(np.clip((p - a) @ d / L2, 0, 1))
        q = a + s * d
        e = float((p - q) @ (p - q))
        if e < best[0]:
            best = (e, i, s)
    return best[1], best[2]


def secondary_stats(B, meshes):
    """meshes: [(P, W)] → {kind: {metric: value, verts, chains}}"""
    sec = {n for n, b in B.items() if is_sec(n, b)}
    CH = chains(B, sec)
    ch_of, idx_of = {}, {}
    for ci, c in enumerate(CH):
        for j, n in enumerate(c):
            ch_of[n] = ci
            idx_of[n] = j
    kind_ch = []
    for c in CH:
        ks = Counter(kind_of(n) for n in c)
        k = next((x for x in ("skirt", "cape", "hair") if ks.get(x, 0) * 2 >= len(c)), "etc")
        kind_ch.append(k)
    pts = [[B[c[0]]["h"]] + [B[n]["t"] for n in c] for c in CH]
    acc = defaultdict(lambda: defaultdict(list))
    used = defaultdict(set)
    for P, W in meshes:
        for v, w in enumerate(W):
            sw = {k: x for k, x in w.items() if k in sec and x > 0.001}
            if not sw:
                continue
            chs = Counter()
            for n, x in sw.items():
                if n in ch_of:
                    chs[ch_of[n]] += x
                    used[ch_of[n]].add(idx_of[n])
            if not chs:
                continue
            ci = chs.most_common(1)[0][0]
            o = acc[kind_ch[ci]]
            tot = sum(w.values()) or 1.0
            bipw = sum(x for n, x in w.items() if n.lower().startswith("bip01")) / tot
            seg, frac = _seg_param(P[v], pts[ci])
            pos = (seg + frac) / max(len(CH[ci]), 1)
            cw = [x for n, x in sw.items() if ch_of.get(n) == ci]
            o["pos"].append(pos)
            o["bip"].append(bipw)
            o["infl"].append(len([x for x in w.values() if x > 0.01]))
            o["rigid"].append(max(w.values()) / tot >= 0.95)
            o["along"].append(len([x for x in cw if x > 0.05]) >= 2)
            o["side"].append(len([1 for x in chs.values() if x > 0.1]) >= 2)
            o["helper"].append(sum(x for n, x in w.items() if HELPER.search(n)) / tot > 0.05)
            for n, x in w.items():
                if n.lower().startswith("bip01") and x / tot > 0.05:
                    o["bipn"].append(n)
    out = {}
    for k, o in acc.items():
        pos = np.array(o["pos"])
        bip = np.array(o["bip"])
        top = pos < 0.25
        out[k] = dict(verts=int(len(pos)), chains=int(sum(1 for x in kind_ch if x == k)),
                      infl_med=float(np.median(o["infl"])), infl_max=int(max(o["infl"])),
                      rigid=float(np.mean(o["rigid"])), along_blend=float(np.mean(o["along"])), side_blend=float(np.mean(o["side"])),
                      bip_mixed=float(np.mean(bip > 0.05)), bip_mixed_top=float(np.mean(bip[top] > 0.05)) if top.any() else 0.0,
                      bip_share_top=float(np.mean(bip[top])) if top.any() else 0.0, helper_mixed=float(np.mean(o["helper"])),
                      bip_names=Counter(o["bipn"]).most_common(6))
    return out


# ---------------------------------------------------------------- ④ 자동 값 → 최종 값
def corrections(B, P, Wfinal, Wsent):
    if Wsent is None or len(Wsent) != len(Wfinal):
        return None
    ch = []
    for a, b in zip(Wsent, Wfinal):
        ks = set(a) | set(b)
        ch.append(sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in ks) / 2.0)
    ch = np.array(ch)
    changed = ch > 0.05
    reg = Counter()
    for v in np.where(changed)[0]:
        top = max(Wfinal[v], key=Wfinal[v].get) if Wfinal[v] else ""
        reg[kind_of(top) if top.lower().startswith("bone_") and not HELPER.search(top) else ("body" if top else "none")] += 1
    s0 = secondary_stats(B, [(P, Wsent)])
    s1 = secondary_stats(B, [(P, Wfinal)])
    delta = {k: {m: round(s1[k][m] - s0[k][m], 4) for m in ("rigid", "along_blend", "side_blend", "bip_mixed_top", "bip_share_top")}
             for k in s1 if k in s0}
    return dict(changed_verts=int(changed.sum()), changed_ratio=float(changed.mean()), by_region=dict(reg), metric_delta=delta)


# ---------------------------------------------------------------- 저장
def _gz(src, dst):
    with open(src, "rb") as f, gzip.open(dst, "wb", compresslevel=6) as g:
        shutil.copyfileobj(f, g)


def save_record(cache, root, job=None):
    job = job or {}
    info = read_info(cache)
    stamp = time.strftime("%Y%m%d_%H%M")
    char = os.path.splitext(info.get("file", "noname.max"))[0] or "noname"
    out = os.path.join(root, "%s_%s" % (char, stamp))
    raw = os.path.join(out, "raw")
    os.makedirs(raw, exist_ok=True)
    for f in os.listdir(cache):
        src = os.path.join(cache, f)
        if f.endswith(".fbx"):
            shutil.copy2(src, os.path.join(raw, f))
        else:
            _gz(src, os.path.join(raw, f + ".gz"))
    log = []
    # 검사
    nbad, rep = stretch_check(cache, info)
    qc_ok = nbad <= QC_BAD_EDGES if info["frames"] else None
    if info["frames"]:
        log.append("찢어짐 검사: %s (늘어난 엣지 %d)" % ("통과" if qc_ok else "주의", nbad))
        for mn, d in rep.items():
            worst = sorted(d.items(), key=lambda t: -t[1])[:3]
            log.append("  %s: %s" % (mn, ", ".join("%s %d" % (FRAME_NAMES.get(t, t), n) for t, n in worst)))
    else:
        log.append("찢어짐 검사: 테스트 키가 없어 건너뜀")
    # 메쉬별
    B = read_bones(cache)
    meshes = []
    for m in info["meshes"]:
        k = m["k"]
        A = read_xyz(os.path.join(cache, "mesh_%d.txt" % k), 6)
        if A is None or not os.path.exists(os.path.join(cache, "weights_%d.txt" % k)):
            continue
        W = read_weights(os.path.join(cache, "weights_%d.txt" % k))
        if len(W) != len(A):
            log.append("  %s: 스킨 정점 수(%d)와 메쉬(%d)가 달라 건너뜀" % (m["name"], len(W), len(A)))
            continue
        meshes.append(dict(m, P=A[:, :3], N=A[:, 3:], W=W, role=mesh_role(W)))
    rec = dict(version=1, character=char, file=info.get("file"), path=info.get("path"), user=info.get("user") or getpass.getuser(),
               saved=time.strftime("%Y-%m-%d %H:%M"), units=info.get("units"), frames=info["frames"], qc_ok=qc_ok,
               qc_bad_edges=nbad, qc_detail={k: {str(t): n for t, n in d.items()} for k, d in rep.items()},
               meshes=[dict(name=m["name"], verts=len(m["W"]), body_share=round(m["role"], 3)) for m in meshes])
    # 몸 템플릿
    segs, scale = None, 0.0254
    fbx = os.path.join(cache, "bip.fbx")
    if os.path.exists(fbx):
        try:
            segs, scale = bip_segments(fbx)
        except Exception as e:
            log.append("Biped 읽기 실패: %s" % e)
    body = max(meshes, key=lambda m: m["role"] * len(m["W"])) if meshes else None
    if segs and body is not None and body["role"] > 0.2:
        data = body_template_data(segs, scale, body["P"], body["N"], body["W"])
        data["note"] = "%s %s (%s)" % (char, rec["saved"], body["name"])
        with gzip.open(os.path.join(out, "body_template.json.gz"), "wt", encoding="utf-8") as g:
            json.dump(data, g, separators=(",", ":"))
        rec["body_mesh"] = body["name"]
        rec["feat"] = feat_of(segs)
        log.append("몸 템플릿: %s (정점 %d, 본 %d)" % (body["name"], len(data["P"]), len(data["bones"])))
    # 세컨더리
    try:
        st = secondary_stats(B, [(m["P"], m["W"]) for m in meshes])
        json.dump(st, open(os.path.join(out, "secondary_stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        rec["secondary"] = {k: v["verts"] for k, v in st.items()}
        if st:
            log.append("세컨더리: " + ", ".join("%s 정점 %d" % (dict(skirt="치마", cape="망토", hair="헤어", etc="기타")[k], v["verts"]) for k, v in st.items()))
    except Exception as e:
        log.append("세컨더리 수치 실패: %s" % e)
    # 자동 → 최종 차이
    corr = {}
    for m in meshes:
        sent = read_sent(os.path.join(SENT_DIR, "%s__%s.txt" % (char, m["name"])))
        c = corrections(B, m["P"], m["W"], sent) if sent is not None else None
        if c:
            corr[m["name"]] = c
    if corr:
        json.dump(corr, open(os.path.join(out, "corrections.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log.append("자동 값에서 고친 정점: " + ", ".join("%s %d (%.0f%%)" % (k, v["changed_verts"], v["changed_ratio"] * 100) for k, v in corr.items()))
        rec["corrections"] = {k: v["changed_verts"] for k, v in corr.items()}
    else:
        log.append("자동 값 기록 없음 (이 PC 에서 [스킨 적용] 한 적이 없으면 비교 못 함)")
    json.dump(rec, open(os.path.join(out, "record.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    try:
        open(DIR_FILE, "w", encoding="utf-8").write(root)
    except Exception:
        pass
    try:
        shutil.rmtree(cache)
    except Exception:
        pass
    return out, rec, log


# ---------------------------------------------------------------- 참고값 다시 계산
METRICS = ("along_blend", "side_blend", "bip_mixed_top", "bip_share_top", "rigid", "bip_mixed", "helper_mixed")


def rebuild_ref(root):
    try:
        ref = json.load(open(REF_PATH, encoding="utf-8"))
    except Exception:
        ref = {"kinds": {}}
    base = ref.get("baseline_kinds") or ref.get("kinds", {})
    ref["baseline_kinds"] = base
    srcs = defaultdict(list)          # kind -> [(stats, weight_verts, name)]
    for k, v in base.items():
        srcs[k].append((v, float(v.get("verts", 1000)), "rig_test"))
    used = []
    for d in sorted(os.listdir(root)) if root and os.path.isdir(root) else []:
        p = os.path.join(root, d)
        try:
            rec = json.load(open(os.path.join(p, "record.json"), encoding="utf-8"))
            st = json.load(open(os.path.join(p, "secondary_stats.json"), encoding="utf-8"))
        except Exception:
            continue
        if rec.get("qc_ok") is False:
            continue
        used.append(d)
        for k, v in st.items():
            # 새 표준으로 만든 캐릭터라 rig_test 보다 2배 무게
            srcs[k].append((v, 2.0 * v.get("verts", 0), d))
    kinds = {}
    notes = []
    for k, lst in srcs.items():
        agg = {}
        for m in METRICS:
            vals = np.array([s.get(m, np.nan) for s, _, _ in lst], float)
            ws = np.array([w for _, w, _ in lst], float)
            ok = ~np.isnan(vals)
            if not ok.any():
                continue
            med = float(np.median(vals[ok]))
            mad = float(np.median(np.abs(vals[ok] - med))) or 0.02
            w2 = ws.copy()
            far = ok & (np.abs(vals - med) > 2.5 * mad)
            w2[far] *= 0.3                      # 혼자 많이 다른 캐릭터는 덜 반영
            for i in np.where(far)[0]:
                notes.append("%s %s: %s 값이 다른 캐릭터와 많이 달라 덜 반영" % (lst[i][2], k, m))
            agg[m] = float(np.sum(vals[ok] * w2[ok]) / max(np.sum(w2[ok]), 1e-9))
        agg["verts"] = int(sum(s.get("verts", 0) for s, _, _ in lst))
        agg["sources"] = len(lst)
        kinds[k] = agg
    ref["kinds"] = kinds
    ref["templates_used"] = used
    ref["updated"] = time.strftime("%Y-%m-%d %H:%M")
    json.dump(ref, open(REF_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    try:
        import object_bones
        object_bones._REF.clear()
    except Exception:
        pass
    return used, notes


# ---------------------------------------------------------------- 몸 템플릿 고르기 (스킨 적용 때)
def pick_body_template(arm):
    """체형이 가장 가까운 몸 템플릿 경로 (없으면 None = 기본 멜리타). returns (path, label)"""
    import body_template as bt
    root = tpl_dir()
    cands = []
    for d in sorted(os.listdir(root)) if root and os.path.isdir(root) else []:
        p = os.path.join(root, d)
        try:
            rec = json.load(open(os.path.join(p, "record.json"), encoding="utf-8"))
        except Exception:
            continue
        gz = os.path.join(p, "body_template.json.gz")
        if rec.get("qc_ok") is False or not rec.get("feat") or not os.path.exists(gz):
            continue
        cands.append((rec["feat"], gz, rec.get("character", d), rec.get("saved", "")))
    if not cands:
        return None, "멜리타 (기본)"
    try:
        f0 = feat_of(bt._segments(arm))
    except Exception:
        return None, "멜리타 (기본)"
    best = min(cands, key=lambda c: feat_dist(f0, c[0]))
    os.makedirs(os.path.join(JOB_DIR, "tplcache"), exist_ok=True)
    loc = os.path.join(JOB_DIR, "tplcache", "bt_%s.json" % re.sub(r"[^\w\-]", "_", os.path.basename(os.path.dirname(best[1]))))
    if not os.path.exists(loc) or os.path.getmtime(loc) < os.path.getmtime(best[1]):
        with gzip.open(best[1], "rt", encoding="utf-8") as g, open(loc, "w", encoding="utf-8") as f:
            f.write(g.read())
    return loc, "%s (%s, 체형 차이 %.3f)" % (best[2], best[3], feat_dist(f0, best[0]))


# ---------------------------------------------------------------- 스킨 적용 때 보낸 값 기록 (max_style_rig.send_weights_to_max 에서)
def keep_sent(char, mesh, wpath):
    try:
        os.makedirs(SENT_DIR, exist_ok=True)
        shutil.copy2(wpath, os.path.join(SENT_DIR, "%s__%s.txt" % (os.path.splitext(char)[0], mesh)))
    except Exception as e:
        print("[rig_template] 보낸 값 기록 실패:", e)


# ---------------------------------------------------------------- 작업 (ge_jobs)
def step_tplsave(mb, job):
    cache = (job or {}).get("cache", "").replace("/", "\\")
    root = (job or {}).get("tpldir", "").replace("/", "\\") or tpl_dir()
    if not cache or not os.path.isdir(cache):
        raise RuntimeError("Max 가 내보낸 데이터가 없어요: %s" % cache)
    if not root:
        raise RuntimeError("저장 폴더가 없어요")
    os.makedirs(root, exist_ok=True)
    info = read_info(cache)
    if info.get("error"):
        raise RuntimeError("Max 내보내기 오류: %s" % info["error"])
    out, rec, log = save_record(cache, root, job)
    used, notes = rebuild_ref(root)
    log.append("저장: %s" % out)
    log.append("세컨더리 참고값 다시 계산: 저장된 캐릭터 %d개 + rig_test" % len(used))
    log += notes[:5]
    if rec.get("qc_ok") is False:
        log.append("※ 찢어짐이 많아 이 캐릭터는 참고값·몸 템플릿 계산에서 빠져요 (고친 뒤 다시 [리깅 완료])")
    return "\n".join(log)
