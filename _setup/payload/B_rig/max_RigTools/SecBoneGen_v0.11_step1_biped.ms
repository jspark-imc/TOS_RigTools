-- ============================================================
-- SecBoneGen v0.11 — 1단계: 몸 메쉬 → 관절 지정점 → Biped 생성
-- (v0.9.2 에서 출발. 실패한 v0.10 은 버림)
-- 환경: 3ds Max 2014 + Biped
-- 흐름
--   1) [1. 지정점 놓기] : 저장된 기본값 좌표(sbg_points_default.txt, 없으면 스크립트 기본값)로 노란 지정점을 놓음
--      (몸 메쉬를 선택해 두면 뼈 굵기용 측정도 같이 함. "기본값" 체크를 끄면 예전처럼 메쉬 측정으로 놓음)
--      점을 손본 뒤 [현재 지정점을 기본값으로 저장] 하면 다음 캐릭터부터 그 좌표로 나옴
--   2) 틀린 점은 뷰포트에서 직접 옮김 (팔·다리 점은 한쪽만 있음)
--   3) [2. Biped 생성] : 지정점 현재 위치를 읽어 Biped 를 만들고 피규어 모드로 맞춤. 반대쪽 팔·다리는 거울로 계산
-- v0.11 뼈 굵기 맞춤 (피봇·길이는 건드리지 않음)
--   - 정점을 다리 / 팔 / 몸통(중앙) 덩어리로 나눈 측정 결과를 그대로 씀
--       허벅지·종아리 = 그 쪽 다리 정점만, 위팔·아래팔 = 그 쪽 팔 정점만, 척추·골반·목·머리 = 중앙 정점만
--   - 뼈 길이의 가운데 40~60% 구간 단면만 잼 (점이 너무 적으면 25~75%)
--   - 허벅지·종아리·위팔·아래팔·목·머리 = 뼈 로컬 Y·Z 둘 다 / 척추·골반 = 두께(앞뒤)만 (너비는 기존 방식 유지)
--   - 손·발은 이번 버전에서 맞추지 않음 (발은 바닥 맞춤 유지)
--   - 뼈마다 「현재 폭 → 목표 폭」을 리스너와 창 아래 목록에 찍음
--   - 목표가 현재의 3배를 넘거나 1/3 보다 작으면 오측정으로 보고 그 뼈는 건너뜀
--   - 굵기를 바꿨을 때 다음 뼈 피봇이 움직이면 되돌림 (피봇 보호)
-- 원본 메쉬는 읽기만 하고 수정하지 않음
-- ============================================================

global TSBG_data      -- 마지막 측정 결과
global TSBG_Step1     -- 롤아웃
global TSBG_noDialog  -- true 면 fileIn 때 창을 열지 않음 (Rig Tools 에서 함수만 쓸 때)
global tsbg_footToFloor  -- 정의보다 앞에서 부르므로 미리 선언 (새 Max 첫 실행 오류 방지)
-- 한쪽 지정점 이름 (Biped 뼈 이름 기반). 노드 이름은 "sbg_L_Thigh" 처럼 접두사 sbg_ 를 붙인다
global TSBG_PTNAMES_SIDE = #("L_Thigh", "L_Calf", "L_Foot", "L_UpperArm", "L_Forearm", "L_Hand", "L_HandEnd")

struct TSBG_Side ( sign, hipPt, shoulderPt, kneePt, anklePt, elbowPt, wristPt, tipPt, legN, armN, thighR, calfR, upperR, foreR, legPts, armPts )
struct TSBG_MeasData ( obj, cx, cy, minZ, maxZ, h, crotchZ, armpitZ, neckZ, poseType, torsoHalfW, sideP, sideN, nb, bz, bandClus, bandY, centralPts )
struct TSBG_Prof ( c, dir, binMean, binR, binCnt )

-- ---------- 공통 ----------
fn tsbg_layer nm = (
	local l = LayerManager.getLayerFromName nm
	if l == undefined do l = LayerManager.newLayerFromName nm
	l
)

fn tsbg_worldVerts obj = (
	local m = snapshotAsMesh obj
	local n = getNumVerts m
	local arr = #()
	arr[n] = undefined
	for i = 1 to n do arr[i] = getVert m i
	free m
	arr
)

-- 정렬된 x 값 배열 → 간격 gapTol 이상 떨어진 덩어리 목록 ([시작,끝])
fn tsbg_clusters xs gapTol = (
	local res = #()
	if xs.count == 0 do return res
	local s = xs[1], e = xs[1]
	for i = 2 to xs.count do (
		if (xs[i] - e) > gapTol do ( append res [s, e]; s = xs[i] )
		e = xs[i]
	)
	append res [s, e]
	res
)

-- 중심(x=0)에 가장 가까운 덩어리
fn tsbg_central cl = (
	local best = undefined, bd = 1e30
	for c in cl do (
		local m = abs ((c.x + c.y) * 0.5)
		if m < bd do ( bd = m; best = c )
	)
	best
)

-- 점 집합의 주축을 구하고, 축 방향으로 nbins 구간별 중심점·단면 반지름을 계산
-- topRef 에 가까운 끝이 시작(상단)이 되도록 방향을 맞춤
fn tsbg_profile pts topRef nbins = (
	local n = pts.count
	if n < 30 do return undefined
	local c = [0,0,0]
	for p in pts do c += p
	c /= n
	local xx = 0.0, xy = 0.0, xz = 0.0, yy = 0.0, yz = 0.0, zz = 0.0
	for p in pts do (
		local q = p - c
		xx += q.x*q.x; xy += q.x*q.y; xz += q.x*q.z
		yy += q.y*q.y; yz += q.y*q.z; zz += q.z*q.z
	)
	local dir = normalize [0.37, 0.21, 0.9]
	for it = 1 to 40 do dir = normalize [xx*dir.x + xy*dir.y + xz*dir.z, xy*dir.x + yy*dir.y + yz*dir.z, xz*dir.x + yz*dir.y + zz*dir.z]
	local ts = #(); ts[n] = 0.0
	local tmin = 1e30, tmax = -1e30
	for i = 1 to n do ( ts[i] = dot (pts[i] - c) dir; if ts[i] < tmin do tmin = ts[i]; if ts[i] > tmax do tmax = ts[i] )
	local pA = c + dir*tmin, pB = c + dir*tmax
	if (distance pB topRef) < (distance pA topRef) do (
		dir = -dir
		for i = 1 to n do ts[i] = -ts[i]
		local tmp = tmin; tmin = -tmax; tmax = -tmp
	)
	local span = tmax - tmin
	if span < 1e-6 do return undefined
	local binSum = for i = 1 to nbins collect [0,0,0]
	local binCnt = for i = 1 to nbins collect 0
	local binR   = for i = 1 to nbins collect 0.0
	for i = 1 to n do (
		local b = (floor ((ts[i] - tmin) / span * nbins)) as integer + 1
		if b > nbins do b = nbins
		if b < 1 do b = 1
		binSum[b] += pts[i]
		binCnt[b] += 1
		binR[b] += length ((pts[i] - c) - dir*ts[i])
	)
	local binMean = for i = 1 to nbins collect ( if binCnt[i] > 0 then binSum[i] / binCnt[i] else undefined )
	for i = 1 to nbins do if binCnt[i] > 0 do binR[i] /= binCnt[i]
	-- 5칸 평활
	local sm = for i = 1 to nbins collect 0.0
	for i = 1 to nbins do (
		local s = 0.0, k = 0
		for j = (i-2) to (i+2) do if j >= 1 and j <= nbins and binCnt[j] > 0 do ( s += binR[j]; k += 1 )
		sm[i] = if k > 0 then s / k else 0.0
	)
	TSBG_Prof c:c dir:dir binMean:binMean binR:sm binCnt:binCnt
)

-- 구간 [a,b] (0~1 비율) 안에서 반지름이 가장 작은 칸 번호
fn tsbg_argminRange arr a b = (
	local n = arr.count, bi = 0, bv = 1e30
	local i0 = amax 1 ((ceil (a * n)) as integer)
	local i1 = amin n ((floor (b * n)) as integer)
	for i = i0 to i1 do if arr[i] > 0 and arr[i] < bv do ( bv = arr[i]; bi = i )
	bi
)

-- 구간 [a,b] 의 평균 반지름 (빈 칸 제외)
fn tsbg_avgRange arr a b = (
	local n = arr.count, s = 0.0, k = 0
	local i0 = amax 1 ((ceil (a * n)) as integer)
	local i1 = amin n ((floor (b * n)) as integer)
	for i = i0 to i1 do if arr[i] > 0 do ( s += arr[i]; k += 1 )
	if k > 0 then s / k else undefined
)

fn tsbg_lastValid prof = (
	local r = undefined
	for i = prof.binMean.count to 1 by -1 do if prof.binMean[i] != undefined do ( r = prof.binMean[i]; exit )
	r
)

fn tsbg_clearDebug = (
	delete (for o in objects where (matchPattern o.name pattern:"sbg_*") collect o)
)

global TSBG_keepPts = true   -- 측정 때 이미 있는 지정점은 그대로 둠

fn tsbg_addDebugPoint nm pos sz = (
	local ex = getNodeByName nm
	if TSBG_keepPts and ex != undefined and not (isDeleted ex) do return ex
	if ex != undefined and not (isDeleted ex) do delete ex
	local p = point pos:pos size:sz cross:true box:false centermarker:false axistripod:false wirecolor:yellow name:nm
	(tsbg_layer "sbg_debug").addNode p
	p
)

-- ---------- 측정 ----------
fn tsbg_cmpOut a b sgn: = (
	local ma = ((a.x + a.y) * 0.5) * sgn, mb = ((b.x + b.y) * 0.5) * sgn
	if ma > mb then -1 else if ma < mb then 1 else 0
)

-- 띠의 덩어리 중 sgn 쪽(중앙 덩어리 제외)을 바깥쪽부터 정렬해 돌려줌
fn tsbg_sideClusters cl sgn centralW = (
	local res = #()
	for c in cl do (
		local m = (c.x + c.y) * 0.5
		if (m * sgn) > 0 and (abs m) > centralW do append res c
	)
	qsort res tsbg_cmpOut sgn:sgn
	res
)

fn tsbg_measureSide v d sgn = (
	local s = TSBG_Side sign:sgn
	local legPts = #(), armPts = #()
	local armZlo = d.crotchZ - 0.12 * d.h
	local armZhi = d.armpitZ + 0.12 * d.h
	local xlim = d.torsoHalfW * 1.05
	local centralW = d.torsoHalfW * 0.5
	if d.poseType == "A" then (
		-- A자: 띠마다 덩어리를 보고, 이 쪽의 가장 바깥 덩어리가 팔(아래쪽에서는 다리 덩어리가 하나 더 있을 때만)
		for p in v do (
			local xr = p.x - d.cx
			local dx = xr * sgn
			if dx > 0 and p.z > armZlo and p.z < armZhi do (
				local bi = (floor ((p.z - d.minZ) / d.bz)) as integer + 1
				if bi > d.nb do bi = d.nb
				if bi < 1 do bi = 1
				local sc = tsbg_sideClusters d.bandClus[bi] sgn centralW
				local isArm = false
				if sc.count > 0 do (
					local outer = sc[1]
					local inOuter = (xr >= outer.x and xr <= outer.y)
					if p.z >= d.crotchZ then isArm = inOuter
					else isArm = (sc.count >= 2 and inOuter)
				)
				if isArm then append armPts p
				else if p.z < d.crotchZ do append legPts p
			)
			if dx > 0 and p.z <= armZlo do append legPts p
		)
	) else (
		-- T자: 몸통 반폭 바깥은 팔, 가랑이 아래는 다리
		for p in v do (
			local dx = (p.x - d.cx) * sgn
			if dx > 0 do (
				if p.z < d.crotchZ then append legPts p
				else if p.z > armZlo and p.z < armZhi and dx > xlim do append armPts p
			)
		)
	)
	local legPts2 = legPts
	s.legN = legPts2.count
	s.armN = armPts.count
	-- v0.11: 굵기 맞춤용으로 분류된 정점을 보관
	s.legPts = legPts2
	s.armPts = armPts
	-- 다리
	local legTop = [d.cx + sgn * 0.06 * d.h, d.cy, d.crotchZ + 0.02 * d.h]
	local lp = tsbg_profile legPts2 legTop 40
	if lp != undefined do (
		local kb = tsbg_argminRange lp.binR 0.38 0.62
		local ab = tsbg_argminRange lp.binR 0.76 0.94
		if kb > 0 do s.kneePt  = lp.binMean[kb]
		if ab > 0 do s.anklePt = lp.binMean[ab]
		s.thighR = tsbg_avgRange lp.binR 0.12 0.35
		s.calfR  = tsbg_avgRange lp.binR 0.55 0.75
	)
	-- 팔
	local armTop = [d.cx + sgn * d.torsoHalfW, d.cy, d.armpitZ + 0.05 * d.h]
	local ap = tsbg_profile armPts armTop 40
	if ap != undefined do (
		local eb = tsbg_argminRange ap.binR 0.35 0.62
		local wb = tsbg_argminRange ap.binR 0.70 0.92
		if eb > 0 do s.elbowPt = ap.binMean[eb]
		if wb > 0 do s.wristPt = ap.binMean[wb]
		s.tipPt = tsbg_lastValid ap
		s.upperR = tsbg_avgRange ap.binR 0.10 0.35
		s.foreR  = tsbg_avgRange ap.binR 0.50 0.72
	)
	s
)

fn tsbg_bandYAt d z = (
	local bi = (floor ((z - d.minZ) / d.bz)) as integer + 1
	if bi > d.nb do bi = d.nb
	if bi < 1 do bi = 1
	local y = d.bandY[bi]
	if y == undefined then d.cy else y
)

fn tsbg_measure obj hipPct shoulderPct = (
	local d = TSBG_MeasData obj:obj
	local v = tsbg_worldVerts obj
	local n = v.count
	local minZ = 1e30, maxZ = -1e30, minX = 1e30, maxX = -1e30, sy = 0.0
	for p in v do ( if p.z < minZ do minZ = p.z; if p.z > maxZ do maxZ = p.z; if p.x < minX do minX = p.x; if p.x > maxX do maxX = p.x; sy += p.y )
	-- 좌우 중심은 정점 밀도에 안 흔들리게 바운딩 박스 중앙으로
	d.minZ = minZ; d.maxZ = maxZ; d.h = maxZ - minZ; d.cx = (minX + maxX) * 0.5; d.cy = sy / n
	if d.h < 1e-6 do return undefined

	-- 높이 띠별 x 분포, 띠별 평균 y
	local nb = 200
	local bz = d.h / nb
	local bandX = for i = 1 to nb collect #()
	local bandYs = for i = 1 to nb collect 0.0
	local bandN  = for i = 1 to nb collect 0
	for p in v do (
		local bi = (floor ((p.z - minZ) / bz)) as integer + 1
		if bi > nb do bi = nb
		if bi < 1 do bi = 1
		append bandX[bi] (p.x - d.cx)
		bandYs[bi] += p.y; bandN[bi] += 1
	)
	d.bandY = for i = 1 to nb collect ( if bandN[i] > 0 then bandYs[i] / bandN[i] else undefined )
	local gapTol = d.h * 0.015
	local clus = for i = 1 to nb collect ( sort bandX[i]; tsbg_clusters bandX[i] gapTol )
	d.nb = nb; d.bz = bz; d.bandClus = clus

	-- 가랑이: 아래 60% 중 덩어리가 2개 이상인 가장 높은 띠의 바로 위
	local crotchB = 0
	for i = 1 to ((nb * 0.6) as integer) do if clus[i].count >= 2 do crotchB = i
	if crotchB == 0 do crotchB = (nb * 0.45) as integer
	crotchB += 1
	d.crotchZ = minZ + (crotchB - 0.5) * bz

	-- 겨드랑이: 위에서 내려오며 덩어리 3개(팔·몸·팔)가 처음 나오는 띠 = A자 포즈
	local armpitB = 0
	for i = nb to ((nb * 0.45) as integer) by -1 do if clus[i].count >= 3 do ( armpitB = i; exit )
	if armpitB > 0 then d.poseType = "A"
	else (
		d.poseType = "T"
		local ext = for i = 1 to nb collect ( if bandX[i].count > 0 then (bandX[i][bandX[i].count] - bandX[i][1]) else 0.0 )
		local wMin = 1e30
		for i = (crotchB + (nb * 0.10) as integer) to ((nb * 0.70) as integer) do if ext[i] > 0 and ext[i] < wMin do wMin = ext[i]
		for i = ((nb * 0.50) as integer) to nb do if ext[i] > 2.2 * wMin do ( armpitB = i; exit )
		if armpitB == 0 do armpitB = (nb * 0.78) as integer
	)
	d.armpitZ = minZ + (armpitB - 0.5) * bz

	-- 몸통 반폭: 겨드랑이 바로 아래 6% 구간의 중앙 덩어리 최대 반폭
	local thw = 0.0
	for i = (amax 1 (armpitB - (nb * 0.06) as integer)) to (amax 1 (armpitB - 1)) do (
		local c = tsbg_central clus[i]
		if c != undefined do ( local w = (c.y - c.x) * 0.5; if w > thw do thw = w )
	)
	if thw < 1e-6 do thw = d.h * 0.12
	d.torsoHalfW = thw

	-- 목 시작: 겨드랑이 위 ~ 머리 끝 5% 아래 사이에서 중앙 덩어리 폭이 가장 좁은 띠
	local neckB = 0, nw = 1e30
	for i = (armpitB + (nb * 0.02) as integer) to ((nb * 0.95) as integer) do (
		local c = tsbg_central clus[i]
		if c != undefined do ( local w = c.y - c.x; if w < nw do ( nw = w; neckB = i ) )
	)
	if neckB == 0 do neckB = (nb * 0.84) as integer
	d.neckZ = minZ + (neckB - 0.5) * bz - d.h * 0.01   -- 손 보정 샘플 기준: 가장 좁은 띠보다 약 1% 아래

	-- v0.11: 중앙(몸통·목·머리) 정점 = 가랑이 위에서 띠마다 중앙 덩어리에 든 정점
	local cpts = #()
	for p in v where p.z >= d.crotchZ do (
		local bi = (floor ((p.z - minZ) / bz)) as integer + 1
		if bi > nb do bi = nb
		if bi < 1 do bi = 1
		local c = tsbg_central clus[bi]
		local xr = p.x - d.cx
		if c != undefined and xr >= c.x and xr <= c.y do append cpts p
	)
	d.centralPts = cpts

	d.sideP = tsbg_measureSide v d  1
	d.sideN = tsbg_measureSide v d -1
	-- 허벅지 시작·위팔 시작 초기 추정 (사용자가 옮기는 것을 전제)
	for s in #(d.sideP, d.sideN) do (
		local hz = d.crotchZ + d.h * hipPct * 0.01
		s.hipPt = [d.cx + s.sign * d.h * 0.055, tsbg_bandYAt d hz, hz]
		local sz = d.armpitZ + d.h * shoulderPct * 0.01
		s.shoulderPt = [d.cx + s.sign * d.torsoHalfW * 0.87, tsbg_bandYAt d sz, sz]
	)
	d
)

-- ---------- 지정점 ----------
fn tsbg_ptNode nm = ( local n = getNodeByName nm; if n == undefined or (isDeleted n) then undefined else n )
global TSBG_adj = #()   -- #( #("sbg_L_Thigh", [dx,dy,dz]), ... ) 2회 맞춤 때 지정점에 더하는 보정값
fn tsbg_ptPos nm = (
	local n = tsbg_ptNode nm
	if n == undefined do return undefined
	local p = n.transform.pos
	for a in TSBG_adj do if a[1] == nm do p += a[2]
	p
)

-- 지정점의 좌우 중심선 x (척추 점 기준)
fn tsbg_pointsCenterX = (
	local p = tsbg_ptPos "sbg_Spine"
	if p == undefined then undefined else p.x
)

-- 팔·다리 지정점 (sbg_L_*). mirror=true 면 척추 x 기준으로 거울
fn tsbg_sidePt nm mirror = (
	local p = tsbg_ptPos ("sbg_" + nm)
	if p == undefined do return undefined
	if not mirror do return p
	local cx = tsbg_pointsCenterX()
	if cx == undefined then undefined else [2 * cx - p.x, p.y, p.z]
)

fn tsbg_placePoints d ptSign = (
	if not TSBG_keepPts do tsbg_clearDebug()
	local sz = d.h * 0.025
	local spineZ = d.crotchZ + d.h * 0.08
	tsbg_addDebugPoint "sbg_Spine"   [d.cx, tsbg_bandYAt d spineZ, spineZ] sz
	-- 몸통 너비: 척추 높이에서 몸통 옆면 위치 (sbg_Spine 과의 x 거리 ×2 = 너비)
	local sbi = (floor ((spineZ - d.minZ) / d.bz)) as integer + 1
	if sbi > d.nb do sbi = d.nb
	if sbi < 1 do sbi = 1
	local sc = tsbg_central d.bandClus[sbi]
	local halfW = if sc != undefined then (sc.y - sc.x) * 0.5 else d.torsoHalfW
	tsbg_addDebugPoint "sbg_SpineWidth" [d.cx + ptSign * halfW, tsbg_bandYAt d spineZ, spineZ] sz
	tsbg_addDebugPoint "sbg_Neck"    [d.cx, tsbg_bandYAt d d.neckZ, d.neckZ] sz
	local headZ = d.neckZ + (d.maxZ - d.neckZ) * 0.3   -- 머리 피봇(두개골 아래) 초기 추정
	local neckEndZ = d.neckZ + (headZ - d.neckZ) * 0.7  -- 손 보정 샘플: 목 길이는 목 시작~머리 피봇의 70%
	local headEndZ = d.maxZ - d.h * 0.015
	tsbg_addDebugPoint "sbg_NeckEnd" [d.cx, tsbg_bandYAt d neckEndZ, neckEndZ] (sz * 0.7)
	tsbg_addDebugPoint "sbg_Head"    [d.cx, tsbg_bandYAt d headZ, headZ] sz
	tsbg_addDebugPoint "sbg_HeadEnd" [d.cx, tsbg_bandYAt d headEndZ, headEndZ] (sz * 0.7)
	-- 팔·다리 점은 한쪽(ptSign)만 만든다. Biped 생성 때 반대쪽은 거울로 계산.
	local s = if ptSign > 0 then d.sideP else d.sideN
	local g = s.sign, h = d.h
	if s.kneePt  == undefined do s.kneePt  = s.hipPt + [0, 0, -0.25 * h]
	if s.anklePt == undefined do s.anklePt = [s.hipPt.x, s.hipPt.y, d.minZ + 0.05 * h]
	if s.elbowPt == undefined do s.elbowPt = s.shoulderPt + [g * 0.03 * h, 0, -0.17 * h]
	if s.wristPt == undefined do s.wristPt = s.shoulderPt + [g * 0.05 * h, 0, -0.33 * h]
	if s.tipPt   == undefined do s.tipPt   = s.shoulderPt + [g * 0.06 * h, 0, -0.43 * h]
	-- 손 끝점 초기값: 손목 → 손끝(메쉬)의 45% 지점 = 손가락 뿌리 근처
	s.tipPt = s.wristPt + (s.tipPt - s.wristPt) * 0.45
	local pairs = #(#("L_Thigh", s.hipPt), #("L_Calf", s.kneePt), #("L_Foot", s.anklePt), #("L_UpperArm", s.shoulderPt), #("L_Forearm", s.elbowPt), #("L_Hand", s.wristPt), #("L_HandEnd", s.tipPt))
	for pr in pairs do tsbg_addDebugPoint ("sbg_" + pr[1]) pr[2] sz
)


-- ---------- Biped 생성·맞춤 ----------
global TSBG_floor = true     -- 발바닥을 z=0 에 맞춤
global TSBG_fitThick = true  -- v0.11: 뼈 굵기를 메쉬 단면에 맞춤
global TSBG_thick = 1.0      -- v0.11: 굵기 배율 (1.0 = 메쉬 단면과 같게, 0.9 = 살짝 안쪽)
global TSBG_slabA = 0.4      -- 단면을 잴 뼈 길이 구간 (시작 비율)
global TSBG_slabB = 0.6      -- 〃 (끝 비율)
global TSBG_maxRatio = 3.0   -- 목표/현재 폭이 이 배수를 넘으면 오측정으로 보고 건너뜀
global TSBG_thickLog = #()   -- 굵기 맞춤 결과 (창 아래 목록에 표시)
global TSBG_spineRatio = #(0.20, 0.21, 0.59)   -- 척추 마디 길이 비율 (척추 3마디일 때, 정답 리그 5개 평균)
global TSBG_twist = #(1, 1, 1, 0)   -- 트위스트 뼈 수: 허벅지·종아리·아래팔·위팔
global TSBG_triPelvis = false   -- TOS: 레퍼런스(tos_bip_ref.ms)가 Triangle Pelvis 켬

-- ---------- v0.11 굵기 맞춤 도구 ----------
fn tsbg_f v = formattedPrint v format:".1f"

fn tsbg_tlog s = (
	append TSBG_thickLog s
	format "SBG 굵기: %\n" s
)

-- (예전 버전에서 측정한 TSBG_data 에는 centralPts 가 없으므로 try 로 감쌈)
fn tsbg_canThick = (
	local r = false
	try ( r = (TSBG_fitThick and TSBG_data != undefined and TSBG_data.centralPts != undefined) ) catch ( r = false )
	r
)

-- P→E 뼈 축 기준으로 길이 비율 a~b 구간에 드는 점만
fn tsbg_slab pts P E a b = (
	local res = #()
	local ax = E - P
	local L = length ax
	if L < 1e-4 do return res
	ax /= L
	for q in pts do (
		local t = (dot (q - P) ax) / L
		if t >= a and t <= b do append res q
	)
	res
)

-- 점들을 dir 방향으로 투영한 폭 (아래 lo, 위 hi 비율은 튀는 점 제외용)
fn tsbg_extentOf pts dir lo hi = (
	local n = pts.count
	if n == 0 do return 0.0
	local vals = for q in pts collect (dot q dir)
	sort vals
	local i0 = ((floor (lo * (n - 1))) as integer) + 1
	local i1 = ((ceil (hi * (n - 1))) as integer) + 1
	if i0 < 1 do i0 = 1
	if i1 > n do i1 = n
	vals[i1] - vals[i0]
)

-- Biped 뼈 상자의 dir 방향 실제 폭
fn tsbg_boneExtent node dir = (
	local m = snapshotAsMesh node
	local lo = 1e30, hi = -1e30
	for i = 1 to (getNumVerts m) do (
		local t = dot (getVert m i) dir
		if t < lo do lo = t
		if t > hi do hi = t
	)
	free m
	if hi < lo then 0.0 else (hi - lo)
)

fn tsbg_maxMove nodes oldPos = (
	local mv = 0.0
	for i = 1 to nodes.count do (
		local dd = distance nodes[i].transform.pos oldPos[i]
		if dd > mv do mv = dd
	)
	mv
)

-- 뼈의 dir 방향 폭을 target 으로. axes 의 스케일 축을 차례로 시험해서 맞는 축을 씀
-- guard 노드(다음 뼈 등)의 위치가 움직이면 그 축은 되돌림 → 피봇 보호
fn tsbg_fitDirWidth node dir target guard axes = (
	local cur = tsbg_boneExtent node dir
	if cur < 1e-4 do return #fail
	if (abs (target - cur)) < (target * 0.01) do return #ok
	local gpos = for g in guard collect g.transform.pos
	for axis in axes do (
		local s0 = biped.getTransform node #scale
		local s = copy s0
		s[axis] *= (target / cur)
		biped.setTransform node #scale s false
		local w1 = tsbg_boneExtent node dir
		local moved = tsbg_maxMove guard gpos
		if moved < 0.05 and (abs (w1 - target)) < ((abs (cur - target)) * 0.5) then (
			-- 한 번 더 다듬기
			if w1 > 1e-4 and (abs (w1 - target)) > (target * 0.01) do (
				local s2 = biped.getTransform node #scale
				s2[axis] *= (target / w1)
				biped.setTransform node #scale s2 false
				if (tsbg_maxMove guard gpos) >= 0.05 do biped.setTransform node #scale s false
			)
			return #ok
		)
		biped.setTransform node #scale s0 false
	)
	#fail
)

-- 뼈 로컬 Y·Z 방향 (스케일 전에 구해 둠)
fn tsbg_yzDirs node = #( #("Y", normalize node.transform.row2), #("Z", normalize node.transform.row3) )

-- 뼈 로컬 Y·Z 중 월드 앞뒤(Y)에 가까운 쪽 = 두께 방향
fn tsbg_depthDirs node = (
	local r2 = normalize node.transform.row2, r3 = normalize node.transform.row3
	#( #("두께", (if (abs r2.y) >= (abs r3.y) then r2 else r3)) )
)

-- 뼈 하나: pts 중 P→E 가운데 구간 단면을 재서 dirs 방향마다 폭을 맞춤
fn tsbg_fitBone node P E pts dirs guard axes a b = (
	if node == undefined or P == undefined or E == undefined or pts == undefined do return false
	local sl = tsbg_slab pts P E a b
	if sl.count < 12 do sl = tsbg_slab pts P E 0.25 0.75
	if sl.count < 12 do (
		tsbg_tlog (node.name + ": 단면 점 부족 (" + (sl.count as string) + "개) → 건너뜀")
		return false
	)
	for di in dirs do (
		local dir = di[2]
		local cur = tsbg_boneExtent node dir
		local tgt = (tsbg_extentOf sl dir 0.02 0.98) * TSBG_thick
		local msg = node.name + " " + di[1] + ": " + (tsbg_f cur) + " → " + (tsbg_f tgt)
		if cur < 1e-4 or tgt < 1e-3 then msg += "  (측정 실패, 건너뜀)"
		else if tgt > (cur * TSBG_maxRatio) or tgt < (cur / TSBG_maxRatio) then msg += "  (3배 넘게 차이 → 오측정으로 보고 건너뜀)"
		else (
			local r = tsbg_fitDirWidth node dir tgt guard axes
			if r == #fail do msg += "  (맞출 축을 못 찾음, 그대로 둠)"
		)
		tsbg_tlog msg
	)
	true
)

-- 뼈 위치(가운데)가 있는 쪽의 다리/팔 정점
fn tsbg_limbPts kind nodeA nodeB = (
	local mid = (nodeA.transform.pos + nodeB.transform.pos) * 0.5
	local s = if mid.x >= TSBG_data.cx then TSBG_data.sideP else TSBG_data.sideN
	if kind == #leg then s.legPts else s.armPts
)

-- 길이를 맞추면서 굵기(Y·Z)도 같은 비율로 줄여 뼈 모양이 지정점 사이에 딱 들어가게 함
fn tsbg_setLen node childNode targetLen = (
	local cur = distance node.transform.pos childNode.transform.pos
	if cur > 1e-4 and targetLen > 1e-4 do (
		local s = biped.getTransform node #scale
		local r = targetLen / cur
		s.x *= r
		s.y *= r
		s.z *= r
		biped.setTransform node #scale s false
	)
)

fn tsbg_scaleX node ratio = (
	local s = biped.getTransform node #scale
	s.x *= ratio
	biped.setTransform node #scale s false
)

-- 본의 X축(길이 방향)이 targetPt 를 향하게 회전
fn tsbg_aim node targetPt = (
	local p = node.transform.pos
	local d1 = normalize (targetPt - p)
	local d0 = normalize node.transform.row1
	local dd = dot d0 d1
	if dd > 1 do dd = 1
	if dd < -1 do dd = -1
	local ang = acos dd
	if ang < 0.3 do return ok
	local ax = cross d0 d1
	if (length ax) < 1e-6 do return ok
	ax = normalize ax
	local q = quat ang ax
	local q2 = quat (-ang) ax
	if (dot (normalize (d0 * (q2 as matrix3))) d1) > (dot (normalize (d0 * (q as matrix3))) d1) do q = q2
	local r0 = biped.getTransform node #rotation
	biped.setTransform node #rotation (r0 * q) false
	if (dot (normalize node.transform.row1) d1) < 0.95 do (
		biped.setTransform node #rotation (q * r0) false
		if (dot (normalize node.transform.row1) d1) < 0.95 do biped.setTransform node #rotation (r0 * q) false
	)
)

fn tsbg_sideNodes bip key = (
	local res = #()
	for i = 1 to 40 do (
		local n = undefined
		try ( n = biped.getNode bip key link:i ) catch ()
		if n == undefined then exit else append res n
	)
	res
)

-- 한쪽 팔·다리를 지정점에 맞춤. mirror=true 면 지정점을 거울로 사용(반대쪽)
fn tsbg_fitLimb bip legKey armKey mirror doAim handRatio fingers fingerLinks = (
	local hip = tsbg_sidePt "L_Thigh" mirror, knee = tsbg_sidePt "L_Calf" mirror, ankle = tsbg_sidePt "L_Foot" mirror
	local sho = tsbg_sidePt "L_UpperArm" mirror, elbow = tsbg_sidePt "L_Forearm" mirror, wrist = tsbg_sidePt "L_Hand" mirror, tip = tsbg_sidePt "L_HandEnd" mirror
	-- 다리: Foot 피봇을 확정하고 Calf 피봇은 Thigh~Foot 사이에 보간 (비율은 Calf 지정점 위치로 정함)
	local thigh = biped.getNode bip legKey link:1
	local calf  = biped.getNode bip legKey link:2
	local foot  = biped.getNode bip legKey link:3
	if ankle != undefined do (
		local hp = thigh.transform.pos
		local r = 0.5
		if knee != undefined then (
			local a = distance hp knee, b = distance knee ankle
			if (a + b) > 1e-4 do r = a / (a + b)
		) else (
			local a = distance thigh.transform.pos calf.transform.pos, b = distance calf.transform.pos foot.transform.pos
			if (a + b) > 1e-4 do r = a / (a + b)
		)
		local K = hp + (ankle - hp) * r
		if doAim do tsbg_aim thigh K
		tsbg_setLen thigh calf (distance hp K)
		if doAim do tsbg_aim calf ankle
		tsbg_setLen calf foot (distance K ankle)
		-- v0.11 굵기: 이 쪽 다리 정점만으로 뼈 가운데 단면을 잼
		if tsbg_canThick() do (
			local lp = tsbg_limbPts #leg thigh calf
			tsbg_fitBone thigh thigh.transform.pos calf.transform.pos lp (tsbg_yzDirs thigh) #(calf) #(2, 3) TSBG_slabA TSBG_slabB
			lp = tsbg_limbPts #leg calf foot
			tsbg_fitBone calf calf.transform.pos foot.transform.pos lp (tsbg_yzDirs calf) #(foot) #(2, 3) TSBG_slabA TSBG_slabB
		)
		if TSBG_floor do ( if not (tsbg_footToFloor foot) do format "SBG: % 발바닥 z=0 맞춤 실패\n" foot.name )
	)
	-- 팔 (link 1=쇄골, 2=위팔, 3=아래팔, 4=손)
	local clav  = biped.getNode bip armKey link:1
	local upper = biped.getNode bip armKey link:2
	local fore  = biped.getNode bip armKey link:3
	local hand  = biped.getNode bip armKey link:4
	if sho != undefined do (
		local clavPt = tsbg_sidePt "L_Clavicle" mirror
		if clavPt != undefined then (
			-- v0.11: 쇄골 지정점(sbg_L_Clavicle)이 있으면 쇄골 피봇을 거기 두고, 위팔 피봇(sho)까지 방향·길이를 맞춤
			try ( biped.setTransform clav #pos clavPt false ) catch ( format "SBG: 쇄골 이동 실패 %\n" (getCurrentException()) )
			-- 위팔 피봇이 sbg_L_UpperArm 에 정확히 오도록: 겨누고 늘린 뒤 남은 차이만큼 겨눌 곳을 보정하며 반복
			local tgt = sho
			for it = 1 to 10 do (
				if doAim do tsbg_aim clav tgt
				tsbg_setLen clav upper (distance clav.transform.pos tgt)
				local er = sho - upper.transform.pos
				if (length er) < 0.005 then exit else tgt += er
			)
			-- 그래도 남은 미세한 차이는 쇄골 피봇을 옮겨서 없앰 (쇄골 시작점은 조건이 아님)
			local er2 = sho - upper.transform.pos
			if (length er2) > 0.005 do try ( biped.setTransform clav #pos (clav.transform.pos + er2) false ) catch ()
		) else (
			-- UpperArm 피봇을 먼저 지정점에: 쇄골의 기본 방향·길이는 두고 쇄골 피봇을 평행 이동
			local clavOff = upper.transform.pos - clav.transform.pos
			try ( biped.setTransform clav #pos (sho - clavOff) false ) catch ( format "SBG: 쇄골 이동 실패 %\n" (getCurrentException()) )
			-- 남은 오차는 쇄골 방향·길이로 보정
			if (distance upper.transform.pos sho) > 0.01 do (
				if doAim do tsbg_aim clav sho
				tsbg_setLen clav upper (distance clav.transform.pos sho)
			)
		)
	)
	-- 팔: Hand 피봇을 확정하고 Forearm 피봇은 UpperArm~Hand 사이에 보간 (비율은 Forearm 지정점 위치로)
	if wrist != undefined do (
		local up = upper.transform.pos
		local r = 0.5
		if elbow != undefined then (
			local a = distance up elbow, b = distance elbow wrist
			if (a + b) > 1e-4 do r = a / (a + b)
		) else (
			local a = distance upper.transform.pos fore.transform.pos, b = distance fore.transform.pos hand.transform.pos
			if (a + b) > 1e-4 do r = a / (a + b)
		)
		local E = up + (wrist - up) * r
		if doAim do tsbg_aim upper E
		tsbg_setLen upper fore (distance up E)
		if doAim do tsbg_aim fore wrist
		tsbg_setLen fore hand (distance E wrist)
		-- v0.11 굵기: 이 쪽 팔 정점만으로 뼈 가운데 단면을 잼
		if tsbg_canThick() do (
			local ap = tsbg_limbPts #arm upper fore
			tsbg_fitBone upper upper.transform.pos fore.transform.pos ap (tsbg_yzDirs upper) #(fore) #(2, 3) TSBG_slabA TSBG_slabB
			ap = tsbg_limbPts #arm fore hand
			tsbg_fitBone fore fore.transform.pos hand.transform.pos ap (tsbg_yzDirs fore) #(hand) #(2, 3) TSBG_slabA TSBG_slabB
		)
		if tip != undefined and fingers > 0 do (
			local fKey = if armKey == #larm then #lfingers else #rfingers
			local midIdx = if fingers >= 3 then (2 * fingerLinks + 1) else 1
			local fRoot = biped.getNode bip fKey link:midIdx
			-- 손 뼈: 피봇(sbg_L_Hand) → 끝(sbg_L_HandEnd) 길이·방향 그대로
			if doAim do tsbg_aim hand tip
			if fRoot != undefined do tsbg_setLen hand fRoot (distance wrist tip)
		)
	)
)

-- 척추 마디 너비(좌우): 월드 x 폭이 targetW 가 되도록 Y/Z 축 중 맞는 축을 스케일
fn tsbg_fitSpineWidth bip targetW = (
	if targetW < 1e-4 do return false
	local spineNodes = tsbg_sideNodes bip #spine
	for sn in spineNodes do (
		local w0 = sn.max.x - sn.min.x
		if w0 < 1e-4 do continue
		local ratio = targetW / w0
		local done = false
		for axis in #(2, 3) while not done do (
			local s0 = biped.getTransform sn #scale
			local s = copy s0
			s[axis] *= ratio
			biped.setTransform sn #scale s false
			local w1 = sn.max.x - sn.min.x
			if (abs (w1 - targetW)) < (abs (w0 - targetW)) * 0.5 then done = true
			else biped.setTransform sn #scale s0 false
		)
	)
	true
)

fn tsbg_dirOf n mx = ( local v = normalize n.transform.row1; [v.x * mx, v.y, v.z] )

-- 뼈 메쉬가 피봇을 넘어 뒤(−X)로 나온 길이
fn tsbg_overshoot node = (
	local ov = 0.0
	try (
		local m = snapshotAsMesh node
		local p = node.transform.pos, xd = normalize node.transform.row1
		for i = 1 to (getNumVerts m) do ( local t = dot ((getVert m i) - p) (-xd); if t > ov do ov = t )
		free m
	) catch ()
	ov
)

-- 발: 메쉬 최저점이 월드 z=0 이 되게 발 두께 축을 스케일 (어느 축인지 시험해서 결정)
fn tsbg_footToFloor foot = (
	local m = snapshotAsMesh foot
	local lo = 1e30
	for i = 1 to (getNumVerts m) do ( local z = (getVert m i).z; if z < lo do lo = z )
	free m
	local pz = foot.transform.pos.z
	if (abs lo) < 0.05 or (pz - lo) < 1e-4 do return true
	local r = pz / (pz - lo)
	for axis in #(3, 2, 1) do (
		local s0 = biped.getTransform foot #scale
		local s = copy s0
		s[axis] *= r
		biped.setTransform foot #scale s false
		local m2 = snapshotAsMesh foot
		local lo2 = 1e30
		for i = 1 to (getNumVerts m2) do ( local z = (getVert m2 i).z; if z < lo2 do lo2 = z )
		free m2
		if (abs lo2) < (abs lo) * 0.5 then return true
		biped.setTransform foot #scale s0 false
	)
	false
)

-- 골반 폭: 양쪽 허벅지 시작점 거리에 맞춤 (어느 축이 폭인지 시험해서 결정)
fn tsbg_fitPelvis bip targetW = (
	local pelvis = biped.getNode bip #pelvis
	local lT = biped.getNode bip #lleg link:1
	local rT = biped.getNode bip #rleg link:1
	local cur = distance lT.transform.pos rT.transform.pos
	if cur < 1e-4 or targetW < 1e-4 do return false
	local ratio = targetW / cur
	for axis = 1 to 3 do (
		local s0 = biped.getTransform pelvis #scale
		local s = copy s0
		s[axis] *= ratio
		biped.setTransform pelvis #scale s false
		local nw = distance lT.transform.pos rT.transform.pos
		if (abs (nw - targetW)) < (abs (cur - targetW)) * 0.5 then return true
		biped.setTransform pelvis #scale s0 false
	)
	false
)

-- 지정점 현재 위치(+보정)로 Biped 전체를 맞춤. 여러 번 불러도 됨
fn tsbg_fitAll bip lMirror doAim handRatio fingers fingerLinks = (
	TSBG_thickLog = #()
	if TSBG_fitThick and not (tsbg_canThick()) do
		tsbg_tlog "몸 메쉬 측정값이 없어 굵기 맞춤을 건너뜀 → 몸 메쉬를 선택하고 [1. 지정점 놓기] 를 다시 누른 뒤 생성하세요"
	local P = tsbg_ptPos
	local hipL = tsbg_sidePt "L_Thigh" false, hipR = tsbg_sidePt "L_Thigh" true
	local spinePt = P "sbg_Spine", neckPt = P "sbg_Neck", headPt = P "sbg_Head"
	local hipMidPt = (hipL + hipR) * 0.5
	local lThigh = biped.getNode bip #lleg link:1
	local rThigh = biped.getNode bip #rleg link:1
	local spineNodes = tsbg_sideNodes bip #spine
	local neckNodes  = tsbg_sideNodes bip #neck
	local head = biped.getNode bip #head

	-- 1) 골반 폭 → 허벅지 시작점 간격
	tsbg_fitPelvis bip (distance hipL hipR)
	-- v0.11 골반 두께: 가랑이 ~ 척추 시작 높이 사이 중앙 정점의 앞뒤 폭 (허벅지·척추 피봇이 움직이는 축은 안 씀)
	if tsbg_canThick() and spinePt != undefined and spinePt.z > TSBG_data.crotchZ do (
		local pelvis = biped.getNode bip #pelvis
		local pA = [TSBG_data.cx, TSBG_data.cy, TSBG_data.crotchZ]
		local pB = [TSBG_data.cx, TSBG_data.cy, spinePt.z]
		local g = #(lThigh, rThigh)
		if spineNodes.count > 0 do append g spineNodes[1]
		tsbg_fitBone pelvis pA pB TSBG_data.centralPts (tsbg_depthDirs pelvis) g #(2, 3, 1) 0.3 0.9
	)
	-- 2) COM 이동 → 허벅지 시작 중점을 지정점에
	local hipMid = (lThigh.transform.pos + rThigh.transform.pos) * 0.5
	local comPos = biped.getTransform bip #pos
	biped.setTransform bip #pos (comPos + (hipMidPt - hipMid)) false

	-- 3) 척추 시작: 피규어 모드에서는 Spine 첫 마디를 직접 옮길 수 있음
	if spinePt != undefined and spineNodes.count > 0 do (
		try ( biped.setTransform spineNodes[1] #pos spinePt false ) catch ( format "SBG: 척추 시작점 이동 실패 %\n" (getCurrentException()) )
	)
	-- 척추 너비
	local swPt = P "sbg_SpineWidth"
	if swPt != undefined and spinePt != undefined do tsbg_fitSpineWidth bip (2 * (abs (swPt.x - spinePt.x)))
	-- 척추 길이: 척추는 기본(수직) 기울기 그대로 두고, 목 시작 높이까지 길이를 맞춤
	-- v0.11: 마디 비율은 팀 리그 기준 (Bacha2_t_bip·pc_set_theia_r11 평균 21% · 20% · 59%). 마디 수가 다르면 기존처럼 비율 유지
	if spineNodes.count > 0 and neckNodes.count > 0 do (
		local tgt = neckPt.z - spineNodes[1].transform.pos.z
		if tgt > 1e-4 do (
			if spineNodes.count == TSBG_spineRatio.count then (
				for it = 1 to 3 do (
					for i = 1 to spineNodes.count do (
						local nx = if i < spineNodes.count then spineNodes[i + 1] else neckNodes[1]
						local cur = distance spineNodes[i].transform.pos nx.transform.pos
						local want = tgt * TSBG_spineRatio[i]
						if cur > 1e-4 do tsbg_scaleX spineNodes[i] (want / cur)
					)
				)
			) else (
				local cur = distance spineNodes[1].transform.pos neckNodes[1].transform.pos
				if cur > 1e-4 do for sn in spineNodes do tsbg_scaleX sn (tgt / cur)
			)
		)
		-- 목 피봇은 지정점으로 직접 이동
		try ( biped.setTransform neckNodes[1] #pos neckPt false ) catch ()
	)
	-- 4) 목: sbg_Neck ~ sbg_NeckEnd 길이·방향. 머리: 피봇은 sbg_Head 로 직접 이동, 길이·방향은 sbg_HeadEnd 까지
	local neckEndPt = P "sbg_NeckEnd"
	local headEndPt = P "sbg_HeadEnd"
	if neckEndPt == undefined do neckEndPt = headPt
	if neckNodes.count > 0 and head != undefined do (
		if doAim do tsbg_aim neckNodes[1] neckEndPt
		local cur = distance neckNodes[1].transform.pos head.transform.pos
		local tgt = distance neckNodes[1].transform.pos neckEndPt
		if cur > 1e-4 and tgt > 1e-4 do for nn in neckNodes do tsbg_scaleX nn (tgt / cur)
		try ( biped.setTransform head #pos headPt false ) catch ( format "SBG: 머리 피봇 이동 실패 %\n" (getCurrentException()) )
		if headEndPt != undefined do (
			if doAim do tsbg_aim head headEndPt
			-- v0.11: 머리 끝 = HeadNub 위치 (HeadNub 이 sbg_HeadEnd 에 오도록 길이 맞춤)
			local tgtH = distance head.transform.pos headEndPt
			local nub = undefined
			for c in head.children where (matchPattern c.name pattern:"*HeadNub*") do nub = c
			if nub != undefined then (
				for it = 1 to 3 do (
					local cur = distance head.transform.pos nub.transform.pos
					if cur > 1e-4 and tgtH > 1e-4 do tsbg_scaleX head (tgtH / cur)
				)
			) else (
				local bb = nodeLocalBoundingBox head
				local headLen = abs (bb[2].x - bb[1].x)
				if headLen > 1e-4 and tgtH > 1e-4 do tsbg_scaleX head (tgtH / headLen)
			)
		)
	)

	-- v0.11 몸통·목·머리 굵기 (중앙 정점만). 팔·다리보다 먼저 해야 쇄골 맞춤이 뒤에서 다시 잡힘
	if tsbg_canThick() do (
		local cp = TSBG_data.centralPts
		-- 척추 마디: 두께(앞뒤)만, 너비는 sbg_SpineWidth 유지
		for i = 1 to spineNodes.count do (
			local sn = spineNodes[i]
			local nx = if i < spineNodes.count then spineNodes[i + 1] else (if neckNodes.count > 0 then neckNodes[1] else head)
			if nx != undefined do
				tsbg_fitBone sn sn.transform.pos nx.transform.pos cp (tsbg_depthDirs sn) #(nx) #(2, 3) TSBG_slabA TSBG_slabB
		)
		-- 목 마디: Y·Z
		for i = 1 to neckNodes.count do (
			local nn = neckNodes[i]
			local nx = if i < neckNodes.count then neckNodes[i + 1] else head
			if nx != undefined do
				tsbg_fitBone nn nn.transform.pos nx.transform.pos cp (tsbg_yzDirs nn) #(nx) #(2, 3) TSBG_slabA TSBG_slabB
		)
		-- 머리: 피봇 ~ sbg_HeadEnd, Y·Z
		if head != undefined and headEndPt != undefined do
			tsbg_fitBone head head.transform.pos headEndPt cp (tsbg_yzDirs head) #() #(2, 3) TSBG_slabA TSBG_slabB
	)

	-- 5) 팔·다리
	tsbg_fitLimb bip #lleg #larm lMirror doAim handRatio fingers fingerLinks
	tsbg_fitLimb bip #rleg #rarm (not lMirror) doAim handRatio fingers fingerLinks
	ok
)

fn tsbg_buildBiped spine neck fingers fingerLinks toes toeLinks handRatio doAim angleZ ankleAtt triNeck prop2 boxStart = (
	local P = tsbg_ptPos
	local hipL = tsbg_sidePt "L_Thigh" false, hipR = tsbg_sidePt "L_Thigh" true
	local spinePt = P "sbg_Spine", neckPt = P "sbg_Neck", headPt = P "sbg_Head"
	if hipL == undefined or hipR == undefined or neckPt == undefined or headPt == undefined do (
		messageBox "sbg_L_Thigh·sbg_Spine·sbg_Neck·sbg_Head 지정점이 있어야 합니다." title:"SecBoneGen"
		return undefined
	)
	local hipMidPt = (hipL + hipR) * 0.5
	local ankL = tsbg_sidePt "L_Foot" false, ankR = tsbg_sidePt "L_Foot" true
	local floorZ = hipMidPt.z - (distance hipMidPt headPt)  -- 임시
	if ankL != undefined and ankR != undefined do floorZ = (amin ankL.z ankR.z)
	local topZ = if TSBG_data != undefined then TSBG_data.maxZ else (headPt.z + (headPt.z - neckPt.z) * 2.5)
	local h = topZ - floorZ
	if h < 1e-3 do h = 100.0

	local bip = undefined
	-- 팀 구조: Classic, Triangle Neck, Prop2, Ankle Attach 0.43, Triangle Pelvis 끔
	try (
		bip = biped.createNew h angleZ [hipMidPt.x, hipMidPt.y, floorZ] arms:true neckLinks:neck spineLinks:spine legLinks:3 \
			tailLinks:0 ponytail1Links:0 ponytail2Links:0 fingers:fingers fingerLinks:fingerLinks \
			toes:toes toeLinks:toeLinks ankleAttach:ankleAtt trianglePelvis:(TSBG_triPelvis == true) triangleNeck:triNeck prop2Exists:prop2
	) catch (
		bip = biped.createNew h angleZ [hipMidPt.x, hipMidPt.y, floorZ] arms:true neckLinks:neck spineLinks:spine legLinks:3 \
			tailLinks:0 ponytail1Links:0 ponytail2Links:0 fingers:fingers fingerLinks:fingerLinks \
			toes:toes toeLinks:toeLinks ankleAttach:ankleAtt trianglePelvis:(TSBG_triPelvis == true)
		try ( bip.controller.triangleNeck = triNeck ) catch ( format "SBG: triangleNeck 설정 실패\n" )
		try ( bip.controller.prop2Exists = prop2 ) catch ( format "SBG: prop2 설정 실패\n" )
	)
	local ctrl = bip.controller
	-- 바디 타입: Classic (createNew 기본은 Skeleton 이라 뼈 끝이 둥글어 피봇 뒤로 메쉬가 나옴)
	try ( ctrl.bodyType = 3 ) catch ( format "SBG: bodyType 설정 실패 %\n" (getCurrentException()) )
	-- 이름: Bip01
	local renamed = false
	try ( ctrl.rootName = "Bip01"; renamed = true ) catch ()
	if not renamed do (
		local oldPre = bip.name
		for o in objects where (o.name == oldPre or (matchPattern o.name pattern:(oldPre + " *"))) do
			o.name = "Bip01" + (substring o.name (oldPre.count + 1) -1)
	)
	ctrl.figureMode = true
	-- v0.11: 트위스트 뼈 (팀 정답 리그 기준 허벅지·종아리·아래팔 1개, 위팔 0개). 순서: 허벅지·종아리·아래팔·위팔
	try ( ctrl.twists = true ) catch ()
	try ( ctrl.thighTwistLinks = TSBG_twist[1] ) catch ( format "SBG: 허벅지 트위스트 설정 실패\n" )
	try ( ctrl.calfTwistLinks = TSBG_twist[2] ) catch ( format "SBG: 종아리 트위스트 설정 실패\n" )
	try ( ctrl.forearmTwistLinks = TSBG_twist[3] ) catch ( format "SBG: 아래팔 트위스트 설정 실패\n" )
	try ( ctrl.upperarmTwistLinks = TSBG_twist[4] ) catch ( format "SBG: 위팔 트위스트 설정 실패\n" )

	local lThigh = biped.getNode bip #lleg link:1
	local rThigh = biped.getNode bip #rleg link:1
	local lIsPX = lThigh.transform.pos.x >= rThigh.transform.pos.x
	-- 지정점(sbg_L_*)이 놓인 세계 쪽과 Biped L 쪽이 다르면 L 에 거울 점을 쓴다
	local lpt = tsbg_sidePt "L_Thigh" false
	local cxp = tsbg_pointsCenterX()
	local lMirror = if lpt == undefined or cxp == undefined then false else ((lpt.x >= cxp) != lIsPX)

	TSBG_adj = #()
	tsbg_fitAll bip lMirror doAim handRatio fingers fingerLinks
	if boxStart do (
		-- 2회 맞춤: 뼈마다 메쉬가 피봇 뒤로 나온 길이를 재서 그만큼 지정점을 뼈 방향으로 밀고 다시 맞춤
		local mx = if lMirror then -1 else 1
		local thigh = biped.getNode bip #lleg link:1, calf = biped.getNode bip #lleg link:2
		local upper = biped.getNode bip #larm link:2, fore = biped.getNode bip #larm link:3, hand = biped.getNode bip #larm link:4
		local sp1 = biped.getNode bip #spine link:1, nk1 = biped.getNode bip #neck link:1, hd = biped.getNode bip #head
		local items = #(#("sbg_L_Thigh", thigh, thigh), #("sbg_L_Calf", calf, thigh), #("sbg_L_UpperArm", upper, upper), \
			#("sbg_L_Forearm", fore, upper), #("sbg_L_Hand", hand, fore), #("sbg_Spine", sp1, sp1), #("sbg_Neck", nk1, nk1), #("sbg_Head", hd, hd))
		for it in items do (
			local ov = tsbg_overshoot it[2]
			format "SBG: % 메쉬 넘침 = %\n" it[2].name ov
			local m2 = if (it[1] == "sbg_Spine" or it[1] == "sbg_Neck" or it[1] == "sbg_Head") then 1 else mx
			if ov > 0.01 do append TSBG_adj #(it[1], (tsbg_dirOf it[3] m2) * ov)
		)
		tsbg_fitAll bip lMirror doAim handRatio fingers fingerLinks
		TSBG_adj = #()
	)

	-- 구조 확인: 쇄골 부모를 리스너에 출력
	local lClav = biped.getNode bip #larm link:1
	if lClav != undefined and lClav.parent != undefined do format "SBG: % 의 부모 = %\n" lClav.name lClav.parent.name

	-- 레이어 정리 (팀 규칙: Biped = bip) + Display as Box
	local lay = tsbg_layer "bip"
	local pre = bip.name
	for o in objects where (o.name == pre or (matchPattern o.name pattern:(pre + " *"))) do (
		lay.addNode o
		try ( o.boxMode = true ) catch ()
		try ( if not o.boxMode do o.boxMode = true ) catch ()
	)
	bip
)


-- ---------- Biped 좌우 대칭 (뼈를 직접 손본 뒤 쓰는 보조 기능) ----------
fn tsbg_bipRoot node = (
	local r = undefined
	try ( r = node.controller.rootNode ) catch ()
	if r == undefined do (
		local nm = node.name
		local sp = findString nm " "
		local pre = if sp == undefined then nm else (substring nm 1 (sp - 1))
		r = getNodeByName pre
	)
	r
)

fn tsbg_mirrorLimbs bip srcSign = (
	local ctrl = bip.controller
	local lThigh = biped.getNode bip #lleg link:1
	local rThigh = biped.getNode bip #rleg link:1
	local lIsPX = lThigh.transform.pos.x >= rThigh.transform.pos.x
	local srcIsL = (srcSign > 0) == lIsPX
	local srcKeys = if srcIsL then #(#lleg, #ltoes, #larm, #lfingers) else #(#rleg, #rtoes, #rarm, #rfingers)
	local dstKeys = if srcIsL then #(#rleg, #rtoes, #rarm, #rfingers) else #(#lleg, #ltoes, #larm, #lfingers)
	local srcNodes = #()
	for k in srcKeys do join srcNodes (tsbg_sideNodes bip k)
	local pasted = false
	try (
		local cc = biped.createCopyCollection ctrl "SBG_sym"
		local cp = biped.copyBipPosture ctrl cc srcNodes #snapNone
		try ( biped.pasteBipPosture ctrl cc cp #pstdefault opposite:true paste_hor:true paste_ver:true paste_turn:true; pasted = true ) catch ()
		if not pasted do try ( biped.pasteBipPosture ctrl cc cp #pstdefault true true true true; pasted = true ) catch ()
		try ( biped.deleteCopyCollection ctrl cc ) catch ()
	) catch ()
	for i = 1 to srcKeys.count do (
		local sn = tsbg_sideNodes bip srcKeys[i]
		local dn = tsbg_sideNodes bip dstKeys[i]
		for j = 1 to (amin sn.count dn.count) do (
			local s = biped.getTransform sn[j] #scale
			biped.setTransform dn[j] #scale s false
		)
	)
	pasted
)

-- ---------- 지정점 기본값 (저장/불러오기) ----------
-- 기본 좌표: KamielRare_t2 에서 손으로 맞춘 값 (2026-10-23)
global TSBG_defaultPts = #( \
	#("sbg_Spine",      [0.0, -3.44453, 119.269]), \
	#("sbg_SpineWidth", [10.8306, -3.44453, 119.269]), \
	#("sbg_Neck",       [0.0, 2.97073, 149.307]), \
	#("sbg_NeckEnd",    [0.0, 1.85107, 154.982]), \
	#("sbg_Head",       [0.0, 0.458337, 157.447]), \
	#("sbg_HeadEnd",    [0.0, 0.458336, 172.655]), \
	#("sbg_L_Thigh",    [7.27198, -1.65046, 103.426]), \
	#("sbg_L_Calf",     [13.3349, -1.66251, 58.3945]), \
	#("sbg_L_Foot",     [17.2733, 1.526, 16.2278]), \
	#("sbg_L_UpperArm", [12.9667, 3.80604, 143.838]), \
	#("sbg_L_Forearm",  [22.8035, 4.72811, 124.178]), \
	#("sbg_L_Hand",     [35.6632, 3.38312, 101.362]), \
	#("sbg_L_HandEnd",  [42.6017, 4.2088, 86.0858]) )
global TSBG_presetPath = "C:\\claude\\max_blender\\test\\sbg_points_default.txt"

-- 파일에 저장된 기본값이 있으면 그걸, 없으면 스크립트 안의 기본값을 돌려줌
fn tsbg_loadPreset = (
	local res = #()
	if doesFileExist TSBG_presetPath do (
		local f = openFile TSBG_presetPath
		if f != undefined do (
			while not (eof f) do (
				local ln = readLine f
				local eq = findString ln "="
				if eq != undefined do (
					local nm = trimRight (trimLeft (substring ln 1 (eq - 1)))
					local vs = trimLeft (substring ln (eq + 1) -1)
					local v = undefined
					try ( v = execute vs ) catch ()
					if classof v == Point3 and (matchPattern nm pattern:"sbg_*") do append res #(nm, v)
				)
			)
			close f
		)
	)
	if res.count == 0 then TSBG_defaultPts else res
)

fn tsbg_savePreset = (
	local pts = for o in objects where (matchPattern o.name pattern:"sbg_*") collect o
	if pts.count == 0 do return false
	local f = createFile TSBG_presetPath
	if f == undefined do return false
	for o in pts do format "% = %\n" o.name o.transform.pos to:f
	close f
	true
)

-- 기본값 좌표로 지정점 놓기 (TSBG_keepPts 가 켜져 있으면 이미 있는 점은 그대로)
fn tsbg_placePreset ptSign sz = (
	local cx = 0.0
	for a in (tsbg_loadPreset()) do (
		local nm = a[1], p = a[2]
		-- L_ 점은 기본값이 +X 에 있음. -X 쪽에 놓으라면 x 를 뒤집음
		if ptSign < 0 and (matchPattern nm pattern:"sbg_L_*") do p = [-p.x, p.y, p.z]
		if ptSign < 0 and nm == "sbg_SpineWidth" do p = [-p.x, p.y, p.z]
		tsbg_addDebugPoint nm p sz
	)
)

-- ---------- UI ----------
try ( destroyDialog TSBG_Step1 ) catch ()

rollout TSBG_Step1 "SecBoneGen v0.11 — 1단계 Biped" width:330 (
	group "Biped 구조 (팀 표준값으로 바꿔 쓰세요)" (
		spinner spSpine "척추 마디" range:[1,10,3] type:#integer fieldwidth:40 across:2
		spinner spNeck  "목 마디"   range:[1,5,1]  type:#integer fieldwidth:40
		spinner spFing  "손가락 수" range:[0,5,5]  type:#integer fieldwidth:40 across:2
		spinner spFingL "손가락 마디" range:[1,3,3] type:#integer fieldwidth:40
		spinner spToes  "발가락 수" range:[0,5,1]  type:#integer fieldwidth:40 across:2
		spinner spToeL  "발가락 마디" range:[1,3,1] type:#integer fieldwidth:40
		spinner spAnkle "Ankle Attach" range:[0,1,0.43] type:#float fieldwidth:40
		checkbox chkTriNeck "Triangle Neck" checked:true across:2
		checkbox chkProp2 "Prop 2" checked:true
	)
	group "자동 측정 초기값" (
		spinner spHip  "허벅지 시작 높이 (가랑이 위, % 키)" range:[0,15,6] type:#float fieldwidth:40
		spinner spSho  "위팔 시작 높이 (겨드랑이 위, % 키)" range:[0,15,5.5] type:#float fieldwidth:40
	)
	group "Biped 맞춤" (
		checkbox chkFloor "발바닥을 월드 Z=0 에 맞춤" checked:true
		checkbox chkThick "뼈 굵기를 메쉬 단면에 맞춤 (몸 메쉬 측정 필요)" checked:true
		spinner spThick "굵기 배율 (1.0 = 메쉬와 같게)" range:[0.5,1.5,1.0] type:#float fieldwidth:40
		checkbox chkAim "뼈 방향도 지정점에 맞춤 (끄면 길이만)" checked:true
		checkbox chkBox "메쉬 넘침 보정 2회 맞춤 (피봇이 안쪽으로 밀림, 보통 끔)" checked:false
		spinner spAngle "Biped 생성 방향 (Z 회전°)" range:[-360,360,-90] type:#float fieldwidth:50
		radiobuttons rbSide "L_ 지정점을 놓을 쪽:" labels:#("+X 쪽", "-X 쪽") default:1
	)
	checkbox chkPreset "저장된 기본값 좌표로 지정점 놓기 (끄면 메쉬 측정으로)" checked:true
	checkbox chkKeep "이미 있는 지정점은 유지 (없는 점만 새로)" checked:true
	button btnMeasure "1. 지정점 놓기  (몸 메쉬 선택하면 굵기도 측정)" width:300 height:28
	button btnSavePreset "현재 지정점을 기본값으로 저장" width:300
	listbox lbInfo "" height:12
	button btnBuild "2. Biped 생성  (지정점 현재 위치, 반대쪽은 거울)" width:300 height:28
	button btnSym "보조: Biped 뼈 좌우 대칭  (뼈 손본 뒤, Biped 뼈 선택)" width:300
	button btnClear "지정점 전부 지우기 (다음 측정 때 새로 놓임)" width:300

	fn fmtPt p = if p == undefined then "(없음)" else (formattedPrint p.x format:".1f") + ", " + (formattedPrint p.y format:".1f") + ", " + (formattedPrint p.z format:".1f")
	fn pct z d = formattedPrint ((z - d.minZ) / d.h * 100) format:".1f"

	on btnMeasure pressed do (
		TSBG_keepPts = chkKeep.checked
		local ptSign = if rbSide.state == 2 then -1 else 1
		local hasMesh = (selection.count == 1 and superclassof selection[1] == GeometryClass)
		if chkPreset.checked then (
			-- 저장된 기본값 좌표로 점 놓기 (메쉬 선택은 굵기 측정용, 없어도 됨)
			local sz = 4.0
			if hasMesh do (
				local d = tsbg_measure selection[1] spHip.value spSho.value
				if d != undefined do ( TSBG_data = d; sz = d.h * 0.025 )
			)
			tsbg_placePreset ptSign sz
			local items = #("기본값 지정점을 놓았습니다 (" + TSBG_presetPath + " 가 있으면 그 값, 없으면 스크립트 기본값).", \
				"점을 옮긴 뒤 [현재 지정점을 기본값으로 저장] 을 누르면 다음부터 그 위치로 나옵니다.")
			if hasMesh and TSBG_data != undefined then (
				append items ("굵기 측정: " + selection[1].name + "  포즈 " + TSBG_data.poseType + "자")
				append items ("  다리 점 " + (TSBG_data.sideP.legN as string) + "/" + (TSBG_data.sideN.legN as string) + \
					"  팔 점 " + (TSBG_data.sideP.armN as string) + "/" + (TSBG_data.sideN.armN as string) + \
					"  몸통 점 " + (TSBG_data.centralPts.count as string))
			) else append items "메쉬를 선택하지 않아 뼈 굵기는 맞추지 않습니다 (Biped 기본값)."
			lbInfo.items = items
			redrawViews()
		) else if not hasMesh then (
			messageBox "측정으로 점을 놓으려면 몸 메쉬(지오메트리) 1개를 선택하세요." title:"SecBoneGen"
		) else (
			local obj = selection[1]
			local d = tsbg_measure obj spHip.value spSho.value
			if d == undefined then messageBox "측정 실패 (높이 0)" title:"SecBoneGen"
			else (
				TSBG_data = d
				local items = #()
				append items ("메쉬: " + obj.name + "   키: " + (formattedPrint d.h format:".1f") + "   포즈: " + d.poseType + "자")
				append items ("가랑이 " + (pct d.crotchZ d) + "%  겨드랑이 " + (pct d.armpitZ d) + "%  목 " + (pct d.neckZ d) + "%  (키 대비)")
				for s in #(d.sideP, d.sideN) do (
					local tag = if s.sign > 0 then "[+X]" else "[-X]"
					append items (tag + " 다리점 " + (s.legN as string) + " / 팔점 " + (s.armN as string))
					append items (tag + " 무릎 " + (fmtPt s.kneePt) + "  발목 " + (fmtPt s.anklePt))
					append items (tag + " 팔꿈치 " + (fmtPt s.elbowPt) + "  손목 " + (fmtPt s.wristPt))
				)
				append items ("몸통 점 " + (d.centralPts.count as string))
				append items "→ 노란 지정점을 확인하고 틀린 것은 옮기세요. 팔·다리는 한쪽만 있고 반대쪽은 거울로 만듭니다."
				lbInfo.items = items
				tsbg_placePoints d (if rbSide.state == 2 then -1 else 1)
				redrawViews()
			)
		)
	)

	on btnSavePreset pressed do (
		if tsbg_savePreset() then messageBox ("저장: " + TSBG_presetPath) title:"SecBoneGen"
		else messageBox "저장 실패 (sbg_* 지정점이 없거나 폴더를 쓸 수 없음)" title:"SecBoneGen"
	)

	on btnBuild pressed do (
		local doAim = chkAim.checked
		TSBG_thick = spThick.value
		TSBG_fitThick = chkThick.checked
		TSBG_floor = chkFloor.checked
		TSBG_thickLog = #()
		local bip = undefined
		undo "SBG Biped" on (
			bip = tsbg_buildBiped spSpine.value spNeck.value spFing.value spFingL.value spToes.value spToeL.value 1.0 doAim spAngle.value spAnkle.value chkTriNeck.checked chkProp2.checked chkBox.checked
		)
		if bip != undefined do (
			select bip
			if TSBG_fitThick then (
				local skipped = 0
				for s in TSBG_thickLog where ((findString s "건너뜀") != undefined or (findString s "그대로 둠") != undefined) do skipped += 1
				local lines = #("뼈 굵기 맞춤 결과 (현재 폭 → 목표 폭, cm) — 건너뛴 항목 " + (skipped as string) + "개")
				join lines TSBG_thickLog
				lbInfo.items = lines
			) else lbInfo.items = #("뼈 굵기 맞춤 꺼짐 (Biped 기본 굵기)")
			redrawViews()
			messageBox "Biped 생성 완료 (피규어 모드). 모양을 확인하세요.\n뼈 굵기 결과는 창 아래 목록과 리스너(F11)에 있습니다." title:"SecBoneGen"
		)
	)

	on btnSym pressed do (
		if selection.count == 0 then messageBox "Biped 뼈를 하나 선택하세요." title:"SecBoneGen"
		else (
			local bip = tsbg_bipRoot selection[1]
			if bip == undefined then messageBox "선택한 것이 Biped 가 아닙니다." title:"SecBoneGen"
			else (
				local srcSign = if rbSide.state == 2 then -1 else 1
				local ok = false
				undo "SBG Mirror" on ( ok = tsbg_mirrorLimbs bip srcSign )
				redrawViews()
				if not ok do messageBox "Biped posture 복사가 안 되어 길이(스케일)만 복사했습니다." title:"SecBoneGen"
			)
		)
	)

	on btnClear pressed do ( tsbg_clearDebug(); redrawViews() )
)

-- Rig Tools(sbg_build.ms)에서 라이브러리로 불러올 때는 창을 열지 않음
if TSBG_noDialog != true do createDialog TSBG_Step1
