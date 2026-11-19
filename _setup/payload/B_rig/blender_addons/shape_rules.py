# shape_rules.py (Claude, 2026-11-01) · 3단계: 치마·망토 밖 조각의 '모양 규칙' (템플릿·캐릭터 이름 없음)
# object_bones.recommend_parts 가 조각 묶음마다 여기 classify() 로 구조를 정하고, generate 가 plan_ring()/split_lr() 로 마디를 놓음.
# 출처: tools\parts\ps_build.py (10-24) 7방식 — 늘어진 체인 / 아래→위 체인(목도리 앞자락) / 목 둘레 링 / 고정 1본 / 좌우 줄 /
#       가까운 웨이트 따라가기(= 1.8 겹친 조각 묶음, object_bones 쪽 그대로) / 몸에 그대로 — 와 2_dev\ClothBones v0.7 CB_autoPart 판정.
# 좌표는 모두 Max 단위(cm), Z 위, -Y 앞, +X 왼쪽.
#
# 형태 종류 (구조)                        판정                                             체인 × 마디
#   ring   목 둘레(목도리)        목 높이 띠(−12~+8)가 12칸 중 75%↑ 덮음, 높이 25 미만      4칸 × 1 (칸마다 안쪽 위→바깥 아래 본)
#                                 변형 1: 목 앞 아래로 내려온 앞자락을 갈라 좌우 2갈래 체인 추가(아래→위, 부모 가장 가까운 척추)
#   hood   덮개·후드              위가 목 높이−6↑, 목 뒤(+Y), 폭 10↑, 등 가운데를 가로지름   1 × 마디(높이/8, 2↑)
#   apron  앞치마                 위가 골반 ±12, 앞(−Y), 폭 14↑, 높이 15↑, 높이 < 폭×3    변형 0: 짧으면(밑단이 치마 절반 위) 본 없음, 길면 좌우 2갈래 / 1: 항상 좌우 2갈래 × 마디
#   hang   매달린 물건            높이·폭 20 미만 (약병·가방·펜던트·배지)                 1 × 마디(높이/8, 1↑). 3cm 안에 있는 작은 조각끼리 한 묶음
#   strand 가닥·띠·사슬           높이 > 폭 × 2.5                                          갈래(폭/12, 1~4) × 마디(높이/8, 2↑)
#   flat   그 밖 장식 천          나머지                                                   갈래(폭/12, 1~4) × 마디(높이/8, 2↑)
#   (본 없음) 몸에 붙은 장식      6cm 미만 조각 / 몸을 감싸는 조각 / 팔·다리에 붙은 조각 / 높이 8 미만의 납작한 띠 → object_bones 쪽 규칙
# 둘러싼 천(치마·코트)·뒷판(망토)은 1.72 guess_kind 그대로 (여기서 안 봄). 모든 체인은 root·_00·마디·_end (generate 의 force_root).
# 구조 후보 A/B = STRUCT_VARIANT 숫자. 시험용 환경변수 MSR_VARIANT="apron=1,ring=1" 로 덮어씀. 미리보기 UI 는 나중.
import os
import numpy as np

REC_SMALL = 6.0       # 이보다 작은 조각(단추·장식 판)은 본 없이
REC_TOUCH = 1.0       # 이보다 가까이 붙은 조각끼리는 한 파트
REC_SEG = 8.0         # 마디 하나 길이 목표
REC_CHAIN_W = 12.0    # 갈래 하나가 맡는 폭
RING_COVER = 0.75     # 목 둘레 각도 칸(12칸) 중 이 비율 이상 덮으면 고리
RING_N = 4            # 고리 칸 수 (RF·RB·LB·LF)
RING_MAX_H = 25.0     # 목 둘레 고리는 이 높이 미만 (머리에서 길게 늘어진 베일·후드는 고리가 아님)
HANG_SIZE = 20.0      # 높이·폭 둘 다 이 미만이면 매달린 물건 (가방 18, 약병 홀더 16 포함)
HANG_NEAR = 3.0       # 매달린 물건 조각끼리 이 거리 안이면 한 묶음 (약병 + 홀더 끈)
FLAT_BAND_H = 8.0     # 이 높이 미만의 납작한 띠(벨트 앞판·버클)는 본 없이 몸에
STRAND_RATIO = 2.5    # 높이/폭 이 비율 넘으면 가닥
SEG_MIN_CHAIN = 2     # 늘어진 체인(hood·strand·flat·apron) 최소 마디

STRUCT_LABEL = {"ring": "목 둘레", "hood": "덮개·후드", "hang": "매달린 물건", "strand": "가닥·띠", "apron": "앞치마", "flat": "장식 천", "flap": "앞자락"}
STRUCT_VARIANT = {"apron": 0, "ring": 0, "line": 0, "hang": 0}
# line: 망토·치마에 붙은 줄 — 0 = 따라가기, 1 = 자기 체인(망토 쪽만; 치마 쪽은 msr_ob_bundle 끄기)
# hang: 매달린 물건 — 0 = 물건 몸통만 체인(끈은 몸 웨이트), 1 = 끈부터 체인 (11/01 정현)


def variant(struct):
    """구조 후보 번호: 환경변수 MSR_VARIANT="apron=1,ring=1" 이 있으면 그 값, 없으면 STRUCT_VARIANT"""
    s = os.environ.get("MSR_VARIANT", "")
    for kv in s.split(","):
        k, _, v = kv.partition("=")
        if k.strip() == struct and v.strip().isdigit():
            return int(v)
    return STRUCT_VARIANT.get(struct, 0)


def segs_for(hz, struct):
    n = int(round(hz / REC_SEG))
    if struct == "hang":
        return max(1, min(n, 6))
    return max(SEG_MIN_CHAIN, min(n, 6))


def chains_for(wdt):
    return int(np.clip(round(wdt / REC_CHAIN_W), 1, 4))


def extent(Q):
    """(높이, 수평 긴 쪽 폭, 수평 짧은 쪽 폭)"""
    hz = float(Q[:, 2].max() - Q[:, 2].min())
    XY = Q[:, :2] - Q[:, :2].mean(0)
    if len(Q) > 3:
        ev = np.linalg.eigh(np.cov(XY.T))[1]
        w1, w2 = float(np.ptp(XY @ ev[:, -1])), float(np.ptp(XY @ ev[:, 0]))
    else:
        w1 = w2 = 0.0
    return hz, w1, w2


def neck_cover(Q, nk):
    """목 높이 띠 정점이 목 둘레 12칸 중 몇 비율을 덮는지 (0~1), 띠 정점이 20개 미만이면 0"""
    band = Q[(Q[:, 2] > nk[2] - 12.0) & (Q[:, 2] < nk[2] + 8.0)]
    if len(band) <= 20:
        return 0.0
    ang = np.arctan2(band[:, 1] - nk[1], band[:, 0] - nk[0])
    return len(np.unique(np.floor((ang + np.pi) / (2 * np.pi) * 12).astype(int) % 12)) / 12.0


def classify(Q, pel, sp2, nk):
    """Q: 조각 묶음 정점(Max 단위). pel/sp2/nk: Bip Pelvis·Spine2·Neck 머리 위치(없으면 None)
    returns dict(struct, chains, segs, parent('Spine2'|None = 위쪽에서 가까운 몸통 본), hz, wdt, why)"""
    hz, wdt, _ = extent(Q)
    top, ymean = float(np.percentile(Q[:, 2], 97)), float(Q[:, 1].mean())
    if nk is not None:
        cov = neck_cover(Q, nk)
        if cov >= RING_COVER and top >= nk[2] - 12.0 and hz < RING_MAX_H:
            return dict(struct="ring", chains=RING_N, segs=1, parent="Spine2", hz=hz, wdt=wdt, why="목 둘레 %.0f%% 덮음" % (100 * cov))
        across = float(Q[:, 0].min()) < nk[0] - 3.0 and float(Q[:, 0].max()) > nk[0] + 3.0     # 등 가운데를 가로지름 (어깨 장식 제외)
        if top >= nk[2] - 6.0 and ymean > nk[1] + 2.0 and wdt > 10.0 and across:
            return dict(struct="hood", chains=1, segs=segs_for(hz, "hood"), parent="Spine2", hz=hz, wdt=wdt, why="목 뒤 위에서 내려옴")
    # 앞치마: 골반 앞에 걸린 넓은 천. 높이가 폭의 3배를 넘는 긴 띠(코트 앞자락이 무릎까지 늘어진 것)는 앞치마가 아니라 가닥
    if pel is not None and abs(top - pel[2]) < 12.0 and ymean < pel[1] - 2.0 and wdt > 14.0 and hz > 15.0 and hz < 3.0 * wdt:
        return dict(struct="apron", chains=2, segs=segs_for(hz, "apron"), parent=None, hz=hz, wdt=wdt, why="골반 앞 넓은 천")
    if hz < HANG_SIZE and wdt < HANG_SIZE:
        return dict(struct="hang", chains=1, segs=segs_for(hz, "hang"), parent=None, hz=hz, wdt=wdt, why="작은 물건")
    if hz > STRAND_RATIO * wdt:
        return dict(struct="strand", chains=chains_for(wdt), segs=segs_for(hz, "strand"), parent=None, hz=hz, wdt=wdt, why="높이가 폭의 %.1f배" % (hz / max(wdt, 1e-6)))
    return dict(struct="flat", chains=chains_for(wdt), segs=segs_for(hz, "flat"), parent=None, hz=hz, wdt=wdt, why="나머지")


def forced(st, struct, Q):
    """시험용(MSR_OB_FORCE): 판정 결과 st 를 지정한 구조로 바꿈 (체인·마디는 그 구조 규칙대로)"""
    hz, wdt, _ = extent(Q)
    if struct == "ring":
        return dict(st, struct="ring", chains=RING_N, segs=1, parent="Spine2", why="강제")
    if struct == "hood":
        return dict(st, struct="hood", chains=1, segs=segs_for(hz, "hood"), parent="Spine2", why="강제")
    if struct == "apron":
        return dict(st, struct="apron", chains=2, segs=segs_for(hz, "apron"), parent=None, why="강제")
    if struct == "hang":
        return dict(st, struct="hang", chains=1, segs=segs_for(hz, "hang"), parent=None, why="강제")
    if struct == "strand":
        return dict(st, struct="strand", chains=chains_for(wdt), segs=segs_for(hz, "strand"), parent=None, why="강제")
    return dict(st, struct="flat", chains=chains_for(wdt), segs=segs_for(hz, "flat"), parent=None, why="강제")


def is_flat_band(Q, dist):
    """높이 8 미만이고 몸 본에 붙어 있는(중간 거리 10 미만) 납작한 띠·판 → 본 없이 몸에 (벨트 앞판·버클)"""
    hz, wdt, _ = extent(Q)
    return hz < FLAT_BAND_H and dist < 10.0


def near_groups(groups, bbox, is_small):
    """매달린 물건끼리 묶기: 작은 묶음(is_small[g] True)들 중 바운딩 박스 간격이 HANG_NEAR 안이면 합침. groups: [[조각 이름]], bbox: {이름: (min3, max3)}"""
    def gap(a, b):
        lo = np.maximum(a[0], b[0])
        hi = np.minimum(a[1], b[1])
        return float(np.linalg.norm(np.maximum(lo - hi, 0.0)))

    def gbox(g):
        mn = np.min([bbox[n][0] for n in g], axis=0)
        mx = np.max([bbox[n][1] for n in g], axis=0)
        return mn, mx
    out = [list(g) for g in groups]
    changed = True
    while changed:
        changed = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                if is_small(out[i]) and is_small(out[j]) and gap(gbox(out[i]), gbox(out[j])) < HANG_NEAR:
                    out[i] += out[j]
                    del out[j]
                    changed = True
                    break
            if changed:
                break
    return out


# ---------------------------------------------------------------- 마디 놓기
def plan_ring(P, vids, centre, parent, labels=("RF1", "RB1", "LB1", "LF1")):
    """목 둘레 고리: 중심축(목) 둘레를 4칸으로 나눠 칸마다 본 하나(안쪽 위 → 바깥 아래). ps_build 목도리 링.
    P: 정점 세계 좌표(Blender 단위), vids: 바디 정점 번호, centre: 목 위치(Blender 단위). object_bones.plan_part 와 같은 dict"""
    U = 0.0254
    c = np.asarray(centre, float)
    ang = np.degrees(np.arctan2(P[:, 0] - c[0], P[:, 1] - c[1]))     # 0 = 뒤(+Y), +90 = 왼쪽(+X)
    edges = np.linspace(-180.0, 180.0, RING_N + 1)
    out, dirs, labs = [], [], []
    for k in range(RING_N):
        m = (ang >= edges[k]) & (ang < edges[k + 1])
        if not m.any():
            continue
        pc = P[m]
        ctr = pc.mean(0)
        inner = c + (ctr - c) * np.array([0.45, 0.45, 0.0])
        inner[2] = pc[:, 2].max() - 1.0 * U
        outer = ctr.copy()
        outer[2] = pc[:, 2].min() + 1.5 * U
        out.append((vids[m], np.array([inner, outer]), np.zeros(int(m.sum()))))
        mid = np.radians((edges[k] + edges[k + 1]) / 2.0)
        dirs.append(np.array([np.sin(mid), np.cos(mid), 0.0]))
        labs.append(labels[k] if k < len(labels) else "R%d" % (k + 1))
    hub = c.copy()
    hub[2] = float(P[:, 2].max())
    return dict(parent=parent, chains=out, hub=hub, root_pt=hub, center=c, nv=len(P), zc=float(P[:, 2].mean()), centers={}, dirs=dirs,
                bends=[0.0] * len(out), labels=labs)


def flap_mask(Q, nk):
    """목도리 앞자락: 목 앞(−Y)으로 3cm 넘게 나가고 목보다 9cm 넘게 내려온 정점 (ps_build). Q·nk Max 단위"""
    return (Q[:, 1] < nk[1] - 3.0) & (Q[:, 2] < nk[2] - 9.0)


def split_lr(P, x0=None):
    """좌우 2갈래 라벨: x >= 가운데 → 0(왼쪽, +X), 아니면 1. x0 없으면 정점 x 중간값"""
    x0 = float(np.median(P[:, 0])) if x0 is None else x0
    return (P[:, 0] < x0).astype(int)
