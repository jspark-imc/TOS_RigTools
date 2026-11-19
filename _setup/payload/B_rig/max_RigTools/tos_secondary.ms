-- ======================================================================
--  TOS_RigTools 1.0 - 4. 세컨더리 본 (3ds Max 2016)
--  레퍼런스(tos_secondary_ref.ms, 이 PC 의 ...\Asset\PC\costume\Body 에서 뽑음)의 이름·체인 구조 그대로 만든다.
--    Skirt   : Bone_Skirt_all (부모 Bip01 Spine) 아래
--              Skirt_S = Bone_Skirt_S_01~12_01~05 (짧은 치마, 4마디 + 끝, Warrior_Skirt_S_Bone)
--              Skirt   = Bone_Skirt_01~12_01~07   (발목까지, 6마디 + 끝, Warrior_Skirt_Bone)
--              Skirt_W = Bone_Skirt_W_01~12_01~07 (폭이 넓은 치마, 6마디 + 끝, Warrior_Skirt_W_Bone)
--              (줄 모양은 레퍼런스 줄 그대로, 마디만 고르게 다시 나눔. 마디 수 = tos_secSkirtSegs, 창에서 줄 수·마디 지정 가능)
--    Cloak   : Bone_cloak_All (부모 Bip01 Spine2) 아래 N줄 (기본 5줄 = L·B·R 안쪽 + L·R 바깥, 줄 수·마디 수는 UI 에서, Warrior_Cloak_Bone)
--              발   = 레퍼런스 표준 그대로 (8마디 + _1 끝: Bone_cloak_L01~L08 + L08_1, 바깥 L09~L16 + L16_1)
--              무릎 = 표준 망토 선을 무릎(Bip01 L Calf 높이)에서 잘라 5마디 + 끝 (L01~L06, 바깥 L07~L12)
--              허리 = 표준 망토 선을 허리(Spine 과 Spine1 사이 높이)에서 잘라 3마디 + 끝 (L01~L04, 바깥 L05~L08)
--                     (허리 길이 이름 규칙은 레퍼런스 costume_m_romantic_set 의 짧은 망토와 같음. 무릎 길이는 레퍼런스에 예시가 없어 같은 규칙으로)
--  위치: 레퍼런스 기준 관절(Spine / Spine2)에서의 거리 × 키 비율(목~발목)로 대상 Biped 에 맞춤. 방향은 레퍼런스 그대로.
--    Clavicle: 레퍼런스 costume_m_ep18darkenforcerpriest_set 의 Bone_Spine2_* (tos_clavicle_ref.ms). L·R Clavicle 아래 옆마다 N줄 + Bone_Spine2_Base(Spine2) 아래 가운데 1줄, 줄 수·마디 수는 UI 에서
--  만든 본 표식: user prop TOS_sec = 종류, TOS_layer = 레이어 (레이어 정리에서 씀)
-- ======================================================================
global TOS_SecRef
global tos_secBuild, tos_secItems, tos_secPick, tos_secDelete
global tos_secKeys = #()
-- 치마 줄마다 마디 수 (끝 본 빼고): Skirt_S, Skirt, Skirt_W
global tos_secSkirtSegs = #(4, 6, 6)

fn tos_secRefLoad = (local f = TosRig.dataFile "tos_secondary_ref.ms"; if TOS_SecRef == undefined and (doesFileExist f) do fileIn f; TOS_SecRef != undefined)
fn tos_secFindRef kind g = (local r = undefined; for s in TOS_SecRef where s[1] == kind and s[2] == g do r = s; r)
fn tos_secHeight pre =
(
	local b = getNodeByName pre exact:true
	local nk = biped.getNode b #neck link:1, lF = biped.getNode b #lleg link:3
	nk.transform.pos.z - lF.transform.pos.z
)

-- 종류별 이름 패턴·레이어
fn tos_secSkirtPat k = (if k == #skirt_S then "Bone_Skirt_S_*" else if k == #skirt_W then "Bone_Skirt_W_*" else "Bone_Skirt_*")
fn tos_secSkirtLayer k = (if k == #skirt_S then "Warrior_Skirt_S_Bone" else if k == #skirt_W then "Warrior_Skirt_W_Bone" else "Warrior_Skirt_Bone")
fn tos_secIsKind o k =
(
	if k == #cloak then matchPattern o.name pattern:"Bone_cloak_*"
	else if k == #clavicle then matchPattern o.name pattern:"Bone_Spine2_*"
	else if k == #skirt_N then (matchPattern o.name pattern:"Bone_Skirt_*" and not (matchPattern o.name pattern:"Bone_Skirt_S_*") and not (matchPattern o.name pattern:"Bone_Skirt_W_*") and not (matchPattern o.name pattern:"Bone_Skirt_all"))
	else matchPattern o.name pattern:(tos_secSkirtPat k)
)
fn tos_secNodes k = (for o in objects where classOf o == BoneGeometry and (tos_secIsKind o k) collect o)

-- 레퍼런스 위치 → 대상 위치
fn tos_secTM tm jRef jT r = (local m = copy tm; m.row4 = jT + (tm.row4 - jRef) * r; m)

fn tos_secTag o kind lay =
(
	setUserProp o "TOS_sec" (kind as string)
	setUserProp o "TOS_layer" lay
	(TosRig.getLayer lay).addNode o
)

-- 레퍼런스 엔트리대로 본 만들기 (부모 먼저 순서). 부모가 엔트리에 없으면 joint 에 붙임
fn tos_secMakeEntries ents jRef jT r joint kind made =
(
	local names = for e in ents collect e[1]
	local nodes = for e in ents collect undefined
	for i = 1 to ents.count do
	(
		local e = ents[i]
		local o = getNodeByName e[1] exact:true
		if o == undefined then
		(
			o = trts_make e r
			o.name = e[1]
			o.wirecolor = e[7]
			local pIdx = findItem names e[3]
			o.parent = if pIdx > 0 and nodes[pIdx] != undefined then nodes[pIdx] else joint
			o.transform = tos_secTM e[5] jRef jT r
			o.boxMode = false
			o.renderable = false
			tos_secTag o (if e[1] == "Bone_Skirt_all" then "skirt_all" else kind) e[4]
			append made #(o, e)
		)
		nodes[i] = o
	)
	nodes
)

-- 본 속성 (배치가 끝난 뒤에 켬, 레퍼런스처럼)
fn tos_secBoneProps made =
(
	for m in made do try (local o = m[1], bp = m[2][8]; o.boneEnable = bp[1]; o.boneFreezeLength = bp[2]; o.boneAutoAlign = bp[3]; o.boneScaleType = bp[4]) catch ()
	for m in made where m[1].boneEnable and m[1].children.count > 0 do try (m[1].ResetBoneStretch()) catch ()
)

-- 표준(발) 망토 한 줄을 bottomZ 에서 잘라 nb 마디 + 끝으로 다시 만듦
fn tos_secCloakChain chain jRef jT r bottomZ nb newStart parentNode kind made meshLine:undefined footEnd:false =
(
	-- 대상 위치로 옮긴 관절 점 (마디 시작점들 + 마지막 끝 본 위치). meshLine 이 있으면 메쉬 표면을 따라 잰 선을 씀
	local pts = if meshLine != undefined then meshLine else (for e in chain collect (tos_secTM e[5] jRef jT r).row4)
	-- bottomZ 에서 자르기
	local cut = #(pts[1])
	local done = false
	for i = 2 to pts.count while not done do
	(
		local a = pts[i - 1], b = pts[i]
		if b.z <= bottomZ and a.z > bottomZ then (local t = (a.z - bottomZ) / (a.z - b.z); append cut (a + (b - a) * t); done = true)
		else append cut b
	)
	local segL = for i = 2 to cut.count collect (distance cut[i - 1] cut[i])
	local total = 0.0
	for s in segL do total += s
	-- 메쉬 선이면 끝 본(마지막 짧은 본)까지 합쳐 메쉬 밑단에서 끝나게: 마디 nb 개 = 전체 - 끝 본 길이
	local tipL = if meshLine != undefined then (amin (chain[chain.count][6][1] * r) (total * 0.06)) else 0.0
	local span = total - tipL
	-- 길이를 nb 등분한 점 (+ 메쉬 선이면 맨 끝 = 밑단)
	local q = #(cut[1])
	for k = 1 to (if meshLine != undefined then nb + 1 else nb) do
	(
		local want = if k <= nb then span * k / nb else total
		local acc = 0.0, p = cut[cut.count]
		local found = false
		for i = 1 to segL.count while not found do
		(
			if acc + segL[i] >= want - 1e-5 then (local t = if segL[i] > 1e-6 then (want - acc) / segL[i] else 0.0; p = cut[i] + (cut[i + 1] - cut[i]) * t; found = true)
			else acc += segL[i]
		)
		append q p
	)
	-- 이름: Bone_cloak_<L|B|R><번호 2자리>
	local nm0 = chain[1][1]
	local pref = substring nm0 1 (nm0.count - 2)
	local e0 = chain[1], eEnd = chain[chain.count]
	local par = parentNode
	for k = 1 to nb + 1 do
	(
		local idx = newStart + k - 1
		local nm = pref + (if idx < 10 then "0" else "") + (idx as string)
		if footEnd and k == nb + 1 do (local li = idx - 1; nm = pref + (if li < 10 then "0" else "") + (li as string) + "_1")   -- 발 길이: 레퍼런스처럼 끝 본 = 마지막 마디 + _1
		local src = chain[amin chain.count (1 + ((k - 1) * (chain.count - 1)) / nb)]
		local z = normalize (tos_secTM src[5] jRef jT r).row3
		local p0 = q[amin k q.count]
		local p1 = if k <= nb or q.count > nb + 1 then q[k + 1] else (p0 + (normalize (q[nb + 1] - q[nb])) * (eEnd[6][1] * r))
		if (distance p0 p1) < 0.05 do p1 = p0 + (normalize (q[nb + 1] - q[nb])) * 0.05
		local o = BoneSys.createBone p0 p1 z
		o.name = nm
		o.width = e0[6][2] * r; o.height = e0[6][3] * r; o.taper = e0[6][4]
		o.sidefins = false; o.frontfin = false; o.backfin = false
		o.wirecolor = e0[7]
		o.parent = par
		o.boxMode = false
		o.renderable = false
		tos_secTag o kind e0[4]
		append made #(o, (if k <= nb then e0 else eEnd))
		par = o
	)
	ok
)

-- ---------------------------------------------------------------------------
-- 망토를 메쉬 모양에 맞춤: 줄마다 그 줄 방향(몸 가운데 → 줄 시작점)으로 높이별 수평 광선을 바깥에서 쏴서
--   가장 바깥 표면(망토)을 찾고, 밑단(광선이 빗나가거나 몸 쪽으로 확 들어가는 곳)까지의 선을 만든다
-- meshes: 맞출 메쉬 (선택한 메쉬, 없으면 보이는 메쉬 전부)
fn tos_secIsMesh o = (superClassOf o == GeometryClass and classOf o != BoneGeometry and classOf o != Biped_Object and classOf o != TargetObject and \
	not (matchPattern o.name pattern:"Bip01*") and not (matchPattern o.name pattern:"Bone_*") and not (matchPattern o.name pattern:"sbg_*") and not o.isHidden)
-- 임시 메쉬 + 면 → 조각(element) 번호 표. 반환: #(#(tmpMesh, faceElem 배열), ...)
fn tos_secTmpMeshes meshes = (
	for m in meshes collect (
		local tm = Editable_Mesh()
		tm.mesh = (snapshotAsMesh m)
		update tm
		tm.isHidden = true
		local fe = #()
		fe.count = tm.numfaces
		local faces = #{1..tm.numfaces}, id = 0
		while not faces.isEmpty do (
			local el = meshop.getElementsUsingFace tm #{(faces as array)[1]}
			id += 1
			for f in el do fe[f] = id
			faces -= el
		)
		#(tm, fe)
	)
)
global tos_secDbg
fn tos_secByD a b = (if a[1] > b[1] then -1 else if a[1] < b[1] then 1 else 0)
-- 한 높이에서 바깥 → 안쪽으로 지나가는 모든 면: #(#(거리, 조각키), ...) 바깥(거리 큰) 순
fn tos_secRayLayers c dir tmps = (
	local hits = #()
	for mi = 1 to tmps.count do (
		local tm = tmps[mi][1], fe = tmps[mi][2]
		local org = c + dir * 300.0
		for n = 1 to 12 do (
			local h = intersectRayEx tm (ray org (-dir))
			if h == undefined do exit
			local d = dot (h[1].pos - c) dir
			-- 몸 가운데 축을 넘어간 면(반대쪽 망토 등)은 안 봄
			if d <= 0 do exit
			append hits #(d, mi * 100000 + fe[h[2]])
			org = h[1].pos - dir * 0.01
		)
	)
	qsort hits tos_secByD
	hits
)
-- 조각 하나만 보고 위에서 밑단까지 따라감: #(zs 인덱스별 거리 or undefined) → #(끝 인덱스, 점들)
fn tos_secTrace layers ek zs startP center dir r nTop:4 = (
	local inset = 0.3 * r, dropMax = 4.0 * r
	-- 높이별 이 조각의 가장 바깥 면
	local ds = for L in layers collect (local b = undefined; for h in L where h[2] == ek while b == undefined do b = h[1]; b)
	-- 튀는 값 줄이기: 앞뒤 5칸 중앙값
	local dm = for i = 1 to ds.count collect (
		if ds[i] == undefined then undefined else (
			local w = for j = (amax 1 (i - 5)) to (amin ds.count (i + 5)) where ds[j] != undefined collect ds[j]
			sort w
			w[(w.count + 1) / 2]
		)
	)
	-- 밑단: 2칸 넘게 빗나가거나, 바로 앞 3칸 평균보다 dropMax 이상 몸 쪽으로 들어가면 멈춤
	local pts = #(startP), miss = 0, gotAny = false, recent = #(), last = 0
	for i = 1 to dm.count do (
		if dm[i] == undefined then (miss += 1; if (gotAny and miss > 2) or (not gotAny and miss > nTop) do exit)
		else (
			if recent.count > 0 do (
				local avg = 0.0
				for v in recent do avg += v
				avg /= recent.count
				if dm[i] < avg - dropMax do exit
			)
			miss = 0
			gotAny = true
			append recent dm[i]
			if recent.count > 3 do deleteItem recent 1
			append pts ([center.x, center.y, zs[i]] + dir * (amax 0.0 (dm[i] - inset)))
			last = i
		)
	)
	#(last, pts, ek)
)
-- 망토 줄 하나의 메쉬 선. 광선이 지나가는 모든 겹(목도리·망토·몸 등)을 조각별로 나눠
-- 맨 위에서 시작하는 겹 중 가장 길게(아래까지) 내려가는 겹을 따라가고, 그 겹의 밑단에 끝점을 둠
fn tos_secMeshLine startP center tmps r = (
	local dir = [startP.x - center.x, startP.y - center.y, 0]
	if (length dir) < 1e-4 do dir = [0, 1, 0]
	dir = normalize dir
	local step = 1.0 * r
	local minZ = 1e9
	for t in tmps do minZ = amin minZ t[1].min.z
	local zs = #(), layers = #()
	local z = startP.z - step
	while z > minZ do (
		append zs z
		append layers (tos_secRayLayers [center.x, center.y, z] dir tmps)
		z -= step
	)
	if zs.count < 3 do return undefined
	-- 몸: 높이의 25% 넘게 걸쳐 있고 그중 60% 넘게 가장 안쪽 겹인 조각 (짧은 밑단 테두리는 몸이 아님)
	local eks = #(), nIn = #(), nAll = #()
	for L in layers where L.count > 0 do (
		local seen = #()
		for h in L where findItem seen h[2] == 0 do (
			append seen h[2]
			local i = findItem eks h[2]
			if i == 0 do (append eks h[2]; append nIn 0; append nAll 0; i = eks.count)
			nAll[i] += 1
			if h[2] == L[L.count][2] do nIn[i] += 1
		)
	)
	local body = for i = 1 to eks.count where nAll[i] >= (amax 3 (zs.count * 0.25)) and nIn[i] > nAll[i] * 0.6 collect eks[i]
	-- 후보: 위쪽 15% 안에서 맞은 겹 중 몸이 아닌 것 (목도리·어깨 망토가 위를 덮어 망토가 조금 아래에서 시작해도 됨)
	local nTop = amax 4 ((zs.count * 0.15) as integer)
	local cands = #()
	for i = 1 to (amin nTop layers.count) do for h in layers[i] where findItem body h[2] == 0 do appendIfUnique cands h[2]
	local best = undefined
	for ek in cands do (
		local tr = tos_secTrace layers ek zs startP center dir r nTop:nTop
		if tos_secDbg != undefined do tos_secDbg += "start " + (startP as string) + " ek " + (ek as string) + " last " + (tr[1] as string) + " z " + (if tr[1] > 0 then zs[tr[1]] as string else "-") + " n " + (tr[2].count as string) + "\n"
		if tr[2].count >= 3 and (best == undefined or tr[1] > best[1]) do best = tr
	)
	-- 후보가 없으면(망토와 몸이 한 조각 등) 맨 위 바깥 겹
	if cands.count == 0 do for i = 1 to (amin 4 layers.count) where layers[i].count > 0 and cands.count == 0 do append cands layers[i][1][2]
	if best == undefined do for ek in cands do (
		local tr = tos_secTrace layers ek zs startP center dir r
		if tr[2].count >= 3 and (best == undefined or tr[1] > best[1]) do best = tr
	)
	if best == undefined do return undefined
	-- 밑단 다듬기: 마지막으로 맞은 높이와 한 칸 아래 사이를 반씩 나눠 그 겹이 끝나는 높이를 찾음
	local pts = best[2], i0 = best[1], ek = best[3]
	-- 밑단 테두리(금색 단 등)가 따로 떨어진 조각이면 이어서 내려감: 망토 마지막 높이에서 망토 바로 바깥/안쪽(2.5r 안)에 있는 다른 조각
	if i0 > 0 do (
		local dEk = undefined
		for h in layers[i0] where h[2] == ek and dEk == undefined do dEk = h[1]
		local ext = undefined
		if dEk != undefined do for h in layers[i0] where h[2] != ek and (findItem body h[2]) == 0 and abs (h[1] - dEk) < 2.5 * r do (
			local e2 = h[2], prevD = h[1], add = #(), last2 = i0
			for i = i0 + 1 to layers.count do (
				local d = undefined
				for h2 in layers[i] where h2[2] == e2 and d == undefined do d = h2[1]
				if d == undefined or abs (d - prevD) > 2.5 * r do exit
				append add ([center.x, center.y, zs[i]] + dir * (amax 0.0 (d - 0.3 * r)))
				prevD = d
				last2 = i
			)
			if add.count > 0 and (ext == undefined or last2 > ext[1]) do ext = #(last2, add, e2)
		)
		if ext != undefined do (join pts ext[2]; i0 = ext[1]; ek = ext[3])
	)
	(
		local hiZ = zs[i0], loZ = zs[i0] - step, hiD = undefined
		for k = 1 to 6 do (
			local mz = (hiZ + loZ) * 0.5, d = undefined
			for h in (tos_secRayLayers [center.x, center.y, mz] dir tmps) where h[2] == ek while d == undefined do d = h[1]
			if d != undefined then (hiZ = mz; hiD = d) else loZ = mz
		)
		if hiD != undefined do append pts ([center.x, center.y, hiZ] + dir * (amax 0.0 (hiD - 0.3 * r)))
	)
	pts
)
-- 망토 2줄: 등에 걸린 가장 긴 조각(등 쪽 정점 80% 이상, 위쪽 등에서 시작, 몸 높이의 25% 넘게 내려옴)을 찾아
--   그 조각 윗부분(위 1/3)의 몸 가운데(jT)에서의 옆 거리·등 쪽 거리 → #(옆 거리, 등 쪽 거리, 조각 이름) (못 찾으면 undefined)
--   조각이 등 가운데에 있으면(옆 거리 < 윗부분 폭의 1/4) 옆 거리 = 윗부분 폭의 1/2 (양쪽으로 벌림)
--   sB: 등 쪽 y 부호 (+1 / -1)
fn tos_secBackPick tmps jT hC sB = (
	-- 후보: 등 쪽 정점 80% 이상, 위쪽 등(Spine2 - 키 25%) 위에서 시작, 몸 높이 25% 넘게 내려옴, 폭이 키의 35% 안 (팔까지 덮는 넓은 겹 제외)
	--   그중 가장 등 쪽(정점 평균 등 쪽 거리가 후보 최대값의 60% 이상)인 것들에서 가장 긴 것
	local cands = #()
	for mi = 1 to tmps.count do (
		local tm = tmps[mi][1], fe = tmps[mi][2]
		local els = #()
		for f = 1 to tm.numfaces do (
			local id = fe[f]
			if els[id] == undefined do els[id] = #{}
			local fc = getFace tm f
			els[id][fc.x as integer] = true; els[id][fc.y as integer] = true; els[id][fc.z as integer] = true
		)
		for id = 1 to els.count where els[id] != undefined and els[id].numberSet >= 8 do (
			local vs = els[id] as array
			local zl = 1e9, zh = -1e9, nB = 0, ym = 0.0
			for v in vs do (local p = getVert tm v; zl = amin zl p.z; zh = amax zh p.z; if (p.y - jT.y) * sB > 0 do nB += 1; ym += (p.y - jT.y) * sB)
			local L = zh - zl
			if nB < vs.count * 0.8 or zh < jT.z - hC * 0.25 or L < hC * 0.25 do continue
			local zc = zh - L / 3.0, c = [0, 0, 0], n = 0, xl = 1e9, xh = -1e9, axl = 1e9, axh = -1e9
			for v in vs do (local p = getVert tm v; axl = amin axl p.x; axh = amax axh p.x; if p.z >= zc do (c += p; n += 1; xl = amin xl p.x; xh = amax xh p.x))
			if n == 0 or (axh - axl) > hC * 0.35 do continue
			c /= n
			local w = (xh - xl) * 0.5
			local ox = abs (c.x - jT.x)
			if ox < w * 0.5 do ox = w * 0.5
			append cands #(ox, abs (c.y - jT.y), L, ym / vs.count, c.x - jT.x)
		)
	)
	if cands.count == 0 do return undefined
	local mb = 0.0
	for c in cands do mb = amax mb c[4]
	local best = undefined
	for c in cands where c[4] >= mb * 0.6 and (best == undefined or c[3] > best[3]) do best = c
	best
)
fn tos_secDeleteNodes ns =(local ok2 = for o in ns where isValidNode o collect o; if ok2.count > 0 do delete ok2; ok2.count)

-- kind: #cloak_waist #cloak_knee #cloak_foot #skirt_S #skirt_N #skirt_W
fn tos_secByAng a b = (if a[1] < b[1] then -1 else if a[1] > b[1] then 1 else 0)
fn tos_secByNum a b = (if a[1] == undefined or b[1] == undefined then 0 else if a[1] < b[1] then -1 else if a[1] > b[1] then 1 else 0)
fn tos_secByX a b =(if a[3] < b[3] then -1 else if a[3] > b[3] then 1 else 0)
-- rows: 망토 줄 수 (Bone_cloak_All 아래), bones: 줄마다 마디 수 (undefined = 허리 3 / 무릎 5 / 발 8)
-- skRows / skSegs: 치마 줄 수·줄마다 마디 수 (undefined = 레퍼런스 12줄 · tos_secSkirtSegs)
fn tos_secBuild kind rows:5 bones:undefined skRows:undefined skSegs:undefined =
(
	if not (tos_secRefLoad()) do return ("오류: 세컨더리 레퍼런스 파일이 없어요: " + TosRig.sbgDir() + "tos_secondary_ref.ms")
	local pre = TosRig.bipPrefix()
	if pre == undefined do return "오류: 장면에 Biped가 없어요. [2. Biped 생성] 을 먼저 하세요."
	local g = TosRig.gender()
	if g == undefined do return "취소했어요. (성별을 정하지 않음)"
	local isCloak = matchPattern (kind as string) pattern:"cloak*"
	local ref = tos_secFindRef (if isCloak then "cloak" else "skirt") g
	if ref == undefined do return ("오류: " + (TosRig.genderText g) + " " + (if isCloak then "망토" else "치마") + " 레퍼런스가 없어요.")
	local joint = getNodeByName (pre + " " + ref[4]) exact:true
	if joint == undefined do return ("오류: " + pre + " " + ref[4] + " 이 없어요.")
	local jT = (at time 0 joint.transform).row4
	local r = (tos_secHeight pre) / ref[6]
	-- 이미 있는 같은 종류는 지우고 다시 (물어봄)
	local old = tos_secNodes (if isCloak then #cloak else kind)
	local kname = case kind of (#cloak_waist: "Cloak 허리"; #cloak_knee: "Cloak 무릎"; #cloak_foot: "Cloak 발"; #cloak_custom: "Cloak"; #skirt_S: "Skirt_S"; #skirt_N: "Skirt"; #skirt_W: "Skirt_W"; default: (kind as string))
	if old.count > 0 and not (queryBox ("이미 " + (if isCloak then "망토" else kname) + " 본이 " + (old.count as string) + "개 있어요.\n지우고 " + kname + " 로 다시 만들까요? (Ctrl+Z 가능)") title:"TOS_RigTools - 세컨더리 본") do return "취소했어요. (변경 없음)"
	local made = #(), nFit = 0, tmps = #(), meshNames = "", nbUsed = 0, nSkRows = 12
	if isCloak do
	(
		-- 망토를 맞출 메쉬: 선택한 메쉬, 없으면 보이는 메쉬 전부 (본·Biped·트위스트 상자·점 제외)
		local ms = for o in selection where tos_secIsMesh o collect o
		if ms.count == 0 do ms = for o in objects where tos_secIsMesh o collect o
		for m in ms do meshNames += m.name + " "
		undo off (tmps = tos_secTmpMeshes ms)
	)
	with animate off at time 0
	(
		undo "TOS 세컨더리 본" on
		(
			tos_secDeleteNodes old
			local ents = ref[7]
			if isCloak then
			(
				-- root + 줄 나누기
				local rootE = ents[1]
				local chains = #()
				for e in ents where e[3] == rootE[1] do
				(
					local ch = #(e), cur = e, more = true
					while more do (more = false; for x in ents where x[3] == cur[1] do (append ch x; cur = x; more = true))
					append chains ch
				)
				local rootN = (tos_secMakeEntries #(rootE) ref[5] jT r joint kind made)[1]
				local nb = case kind of (#cloak_waist: 3; #cloak_knee: 5; default: 8)
				if bones != undefined do nb = bones
				nbUsed = nb
				local bottomZ = if kind == #cloak_waist then \
					(((at time 0 (getNodeByName (pre + " Spine") exact:true).transform).row4.z + (at time 0 (getNodeByName (pre + " Spine1") exact:true).transform).row4.z) * 0.5) \
					else if kind == #cloak_knee then (at time 0 (getNodeByName (pre + " L Calf") exact:true).transform).row4.z else -1e9
				-- 레퍼런스 줄을 몸 둘레 순서로: L 바깥 → L 안쪽 → B → R 안쪽 → R 바깥 (레퍼런스 공간 각도)
				local jR = ref[5]
				local ord = for ch in chains collect (local p = ch[1][5].row4 - jR; #(atan2 p.y p.x, ch))
				qsort ord tos_secByAng
				local refCh = for o in ord collect o[2]
				local nR = refCh.count
				-- 줄 수만큼 시작점을 레퍼런스 시작점 사이에 고르게 (5줄이면 레퍼런스 그대로)
				local newCh = #()   -- #(옆(L/B/R), 줄(엔트리 복사본))
				-- 2줄: 등에 걸린 가장 긴 조각 기준으로 등 쪽에 좌우 대칭 (레퍼런스 양 끝 줄은 옆구리라 엉뚱한 데 생기던 것, warrior_m_arborday_fairy)
				--   본보기 = 레퍼런스 등 가운데 줄(옆 거리 가장 작은 줄), 시작점 방향만 그 조각 쪽으로 돌림. 길이는 아래 메쉬 표면 맞춤으로 그 조각 밑단까지
				local pick2 = undefined, tmpl = undefined
				if rows == 2 and tmps.count > 0 do (
					for c in refCh where tmpl == undefined or abs (c[1][5].row4.x - jR.x) < abs (tmpl[1][5].row4.x - jR.x) do tmpl = c
					local sB = if (tmpl[1][5].row4.y - jR.y) >= 0 then 1 else -1
					pick2 = tos_secBackPick tmps jT (tos_secHeight pre) sB
					if pick2 != undefined do (
						local v0 = tmpl[1][5].row4 - jR
						local rr = length [v0.x, v0.y]
						for sd in #(1, -1) do (
							local dv2 = normalize [sd * pick2[1], sB * pick2[2], 0]
							local p = jR + [dv2.x * rr, dv2.y * rr, v0.z]
							local ch = deepCopy tmpl
							local dv = p - tmpl[1][5].row4
							for e in ch do (local m = e[5]; m.row4 = m.row4 + dv; e[5] = m)
							append newCh #((if sd > 0 then "L" else "R"), ch, abs (p.x - jR.x))
						)
						-- 대칭: 그 조각 쪽 줄만 메쉬 표면에 맞추고, 반대쪽은 그 선을 좌우로 뒤집어 씀 (반대쪽에 같은 조각이 없어도 같은 길이·모양)
						local iP = if pick2[5] >= 0 then 1 else 2, iO = if pick2[5] >= 0 then 2 else 1
						local sP = tos_secMeshLine (tos_secTM newCh[iP][2][1][5] ref[5] jT r).row4 jT tmps r
						if sP != undefined then (
							append newCh[iP] sP
							append newCh[iO] (for q in sP collect [2.0 * jT.x - q.x, q.y, q.z])
						) else (append newCh[1] #none; append newCh[2] #none)
					)
				)
				-- 2줄인데 등 조각을 못 찾으면 레퍼런스 안쪽 두 줄(등 쪽 L·R)
				if rows == 2 and pick2 == undefined and nR >= 4 do (
					for ci in #(2, nR - 1) do (
						local ch = deepCopy refCh[ci]
						local px = ch[1][5].row4.x - jR.x
						append newCh #((if px > 0 then "L" else "R"), ch, abs px)
					)
					pick2 = #()
				)
				if pick2 == undefined do for i = 1 to rows do (
					local u = if rows == 1 then (nR - 1) * 0.5 else (i - 1) * (nR - 1.0) / (rows - 1)
					local a = (floor u) as integer + 1, k = u - (floor u)
					local b = amin nR (a + 1)
					local pA = refCh[a][1][5].row4, pB = refCh[b][1][5].row4
					local p = pA + (pB - pA) * k
					local ni = if k < 0.5 then a else b
					local near = refCh[ni]
					local ch = deepCopy near
					local dv = p - near[1][5].row4
					for e in ch do (local m = e[5]; m.row4 = m.row4 + dv; e[5] = m)
					local px = p.x - jR.x
					local side = if px > 0.05 * (amax 1.0 (length (p - jR))) then "L" else if px < -0.05 * (amax 1.0 (length (p - jR))) then "R" else "B"
					append newCh #(side, ch, abs px)
				)
				-- 옆마다 안쪽(가운데에 가까운 줄)부터 번호
				local isFoot = kind == #cloak_foot and nb == 8
				local blk = if isFoot then nb else nb + 1
				for sd in #("L", "B", "R") do (
					local mine = for c in newCh where c[1] == sd collect c
					qsort mine tos_secByX
					for oi = 1 to mine.count do (
						local ch = mine[oi][2]
						ch[1][1] = "Bone_cloak_" + sd + "01"
						local start = (oi - 1) * blk + 1
						-- 메쉬 표면을 따라 밑단까지 (못 찾으면 레퍼런스 모양)
						--   2줄 대칭이면 위에서 정한 선 (#none = 레퍼런스 모양으로 양쪽 같게)
							local surfPts = if mine[oi].count >= 4 then (if mine[oi][4] == #none then undefined else mine[oi][4]) else if tmps.count > 0 then (tos_secMeshLine (tos_secTM ch[1][5] ref[5] jT r).row4 jT tmps r) else undefined
						if surfPts != undefined then (nFit += 1; tos_secCloakChain ch ref[5] jT r -1e9 nb start rootN kind made meshLine:surfPts footEnd:isFoot)
						else tos_secCloakChain ch ref[5] jT r bottomZ nb start rootN kind made footEnd:isFoot
					)
				)
			)
			else
			(
				-- Bone_Skirt_all + 그 종류의 줄만
				local lay = tos_secSkirtLayer kind
				local pat = tos_secSkirtPat kind
				local sel = for e in ents where e[1] == "Bone_Skirt_all" or (matchPattern e[1] pattern:pat and (kind != #skirt_N or (not (matchPattern e[1] pattern:"Bone_Skirt_S_*") and not (matchPattern e[1] pattern:"Bone_Skirt_W_*")))) collect e
				-- Bone_Skirt_all 은 레퍼런스 그대로, 12줄은 레퍼런스 줄(시작~끝 본 시작)을 따라 마디 수만큼 고르게 다시 나눔 + 짧은 끝 본
				--   마디 수: Skirt_S 4 · Skirt 6 · Skirt_W 6 (레퍼런스는 5 · 8 · 8)
				--   skRows / skSegs (UI 의 줄 수·마디): 지정하면 그 값. 줄 수가 레퍼런스(12)와 다르면 01 줄(앞 가운데)부터 몸 둘레를 고르게 나눈 각도에
				--   가장 가까운 레퍼런스 줄을 몸 가운데 축(Z) 둘레로 돌려 씀 (줄 모양·길이는 그 레퍼런스 줄 그대로)
				local allN = (tos_secMakeEntries (for e in sel where e[1] == "Bone_Skirt_all" collect e) ref[5] jT r joint kind made)[1]
				local jR = ref[5]
				local rows0 = #()   -- #(번호, 각도, 줄)
				for e0 in sel where e0[3] == "Bone_Skirt_all" do (
					local ch = #(e0), cur = e0, more = true
					while more do (more = false; for x in sel where x[3] == cur[1] do (append ch x; cur = x; more = true))
					local p = e0[5].row4 - jR
					append rows0 #(((substring e0[1] (e0[1].count - 4) 2) as integer), (atan2 p.y p.x), ch)
				)
				qsort rows0 tos_secByNum
				local nbK = if kind == #skirt_S then tos_secSkirtSegs[1] else if kind == #skirt_W then tos_secSkirtSegs[3] else tos_secSkirtSegs[2]
				if skSegs != undefined do nbK = amax 1 skSegs
				nSkRows = rows0.count
				if skRows == undefined or skRows == rows0.count or rows0.count < 2 then (
					for rw in rows0 do tos_secCloakChain rw[3] jR jT r -1e9 nbK 1 allN kind made
				) else (
					nSkRows = amax 1 skRows
					local nm0 = rows0[1][3][1][1]
					local pref = substring nm0 1 (nm0.count - 5)   -- "Bone_Skirt_" / "Bone_Skirt_S_" / "Bone_Skirt_W_"
					local a1 = rows0[1][2]
					local d12 = rows0[2][2] - a1
					while d12 > 180.0 do d12 -= 360.0
					while d12 <= -180.0 do d12 += 360.0
					local dir = if d12 >= 0 then 1.0 else -1.0
					for i = 1 to nSkRows do (
						local ang = a1 + dir * (i - 1) * 360.0 / nSkRows
						local best = undefined, bd = 1e9, bDel = 0.0
						for rw in rows0 do (
							local dd = ang - rw[2]
							while dd > 180.0 do dd -= 360.0
							while dd <= -180.0 do dd += 360.0
							if abs dd < bd do (bd = abs dd; best = rw; bDel = dd)
						)
						local ch = deepCopy best[3]
						local rot = (transMatrix (-jR)) * (rotateZMatrix bDel) * (transMatrix jR)
						for e in ch do e[5] = e[5] * rot
						ch[1][1] = pref + (if i < 10 then "0" else "") + (i as string) + "_01"
						tos_secCloakChain ch jR jT r -1e9 nbK 1 allN kind made
					)
				)
				nbUsed = nbK
			)
			tos_secBoneProps made
		)
	)
	undo off (for tm in tmps where isValidNode tm[1] do delete tm[1])
	completeRedraw()
	"[세컨더리 본] " + kname + " " + (made.count as string) + "개 만듦 (" + (TosRig.genderText g) + " 레퍼런스 " + ref[3] + ", 키 비율 " + (formattedPrint r format:".3f") + ")\n" + \
		(if isCloak then "부모: " + pre + " Spine2 → Bone_cloak_All → " + (rows as string) + "줄 × " + (nbUsed as string) + "마디\n메쉬 모양에 맞춘 줄 " + (nFit as string) + "/" + (rows as string) + " (메쉬: " + meshNames + ")" + (if nFit < rows then "\n못 맞춘 줄은 레퍼런스 모양 그대로예요. 망토 메쉬만 선택하고 다시 누르면 더 잘 맞아요." else "") else "부모: " + pre + " Spine → Bone_Skirt_all → " + (nSkRows as string) + "줄 × " + (nbUsed as string) + "마디") + \
		(if old.count > 0 then "\n예전 본 " + (old.count as string) + "개는 지웠어요." else "") + "\nCtrl+Z 로 되돌릴 수 있어요."
)

-- ---------------------------------------------------------------------------
-- Clavicle(어깨): 레퍼런스 costume_m_ep18darkenforcerpriest_set 의 Bone_Spine2_* (tos_clavicle_ref.ms)
--   옆마다 rows 줄 + 가운데 1줄, 줄마다 segs 마디 + 짧은 끝 본
--   부모: 앞 바깥·어깨 위 줄 = Bip01 L/R Clavicle, 앞 안쪽·등·가운데 줄(+ 등 쪽에 더한 줄) = Bone_Spine2_Base(부모 Spine2)
--   줄 모양: 레퍼런스 옆 4줄(앞 안쪽 → 앞 바깥 → 어깨 위 → 등) 사이를 rows 개로 고르게 섞음 (4줄 × 3마디 = 레퍼런스 그대로)
--   이름: Bone_Spine2_01~ (R 앞 안쪽 → R 등 → 가운데 → L 등 → L 앞 안쪽 순, 레퍼런스와 같은 순서)
global TOS_ClavRef
fn tos_secClavRefLoad = (local f = TosRig.dataFile "tos_clavicle_ref.ms"; if TOS_ClavRef == undefined and (doesFileExist f) do fileIn f; TOS_ClavRef != undefined)
-- 점 목록을 길이로 n 등분한 n+1 점
fn tos_secResample pts n = (
	local segL = for i = 2 to pts.count collect (distance pts[i - 1] pts[i])
	local total = 0.0
	for s in segL do total += s
	for k = 0 to n collect (
		local want = total * k / n, acc = 0.0, p = pts[pts.count], found = false
		for i = 1 to segL.count while not found do (
			if acc + segL[i] >= want - 1e-5 then (local t = if segL[i] > 1e-6 then (want - acc) / segL[i] else 0.0; p = pts[i] + (pts[i + 1] - pts[i]) * t; found = true)
			else acc += segL[i]
		)
		p
	)
)
-- 엔트리 줄 → 관절 점들 (마디 시작점들 + 끝 본 끝)
fn tos_secChainPts ch = (
	local pts = for e in ch collect e[5].row4
	local last = ch[ch.count]
	append pts (last[5].row4 + (normalize last[5].row1) * last[6][1])
	pts
)
fn tos_secNameIdx nm = ((substring nm (nm.count - 1) 2) as integer)
fn tos_secByIdx a b = (local x = tos_secNameIdx a[1][1], y = tos_secNameIdx b[1][1]; if x < y then -1 else if x > y then 1 else 0)
-- 줄 하나 만들기: 대상 공간 점 pts(마디 끝들, 마지막 = 끝 본 끝), z 축, 이름 번호 start
fn tos_secMakeChainPts pts zAx e0 eEnd start parentNode kind made = (
	local par = parentNode
	for k = 1 to pts.count - 1 do (
		local idx = start + k - 1
		local o = BoneSys.createBone pts[k] pts[k + 1] zAx
		o.name = "Bone_Spine2_" + (if idx < 10 then "0" else "") + (idx as string)
		local e = if k < pts.count - 1 then e0 else eEnd
		o.width = e[6][2]; o.height = e[6][3]; o.taper = e[6][4]
		o.sidefins = false; o.frontfin = false; o.backfin = false
		o.wirecolor = e0[7]
		o.parent = par
		o.boxMode = false
		o.renderable = false
		tos_secTag o kind e0[4]
		append made #(o, e)
		par = o
	)
	ok
)
-- 옆 하나: rows 줄 → #(점들, z 축, 크기를 가져올 레퍼런스 줄, 등쪽인지)
--   chains = 레퍼런스 옆 4줄 (앞 안쪽 · 앞 바깥 · 어깨 위 · 등), cPts/cZ = 가운데(등) 줄 (대상 공간)
--   4줄 이상: 앞 3줄은 레퍼런스 그대로, 나머지는 어깨 위 → 등 → 가운데 사이(등 쪽)에 고르게 (4줄 = 레퍼런스 그대로)
--   3줄 이하: 레퍼런스 4줄 사이를 고르게
fn tos_secClavSide chains rows jRef jT r nPt cPts cZ = (
	local res = for ch in chains collect (for p in (tos_secResample (tos_secChainPts ch) nPt) collect (jT + (p - jRef) * r))
	local zs = for ch in chains collect (normalize ch[1][5].row3)
	local nR = chains.count
	if rows < nR then (
		for i = 1 to rows collect (
			local u = if rows == 1 then (nR - 1) * 0.5 else (i - 1) * (nR - 1.0) / (rows - 1)
			local a = (floor u) as integer + 1
			local k = u - (floor u)
			local b = amin nR (a + 1)
			local pts = for j = 1 to nPt + 1 collect (res[a][j] * (1 - k) + res[b][j] * k)
			local ni = if k < 0.5 then a else b
			#(pts, (normalize (zs[a] * (1 - k) + zs[b] * k)), chains[ni], (u > nR - 1.5), ni)
		)
	) else (
		local out = for i = 1 to nR - 1 collect #(res[i], zs[i], chains[i], false, i)
		local nB = rows - (nR - 1)
		for j = 1 to nB do (
			local s = j * 2.0 / (nB + 1)
			local pA = undefined, pB = undefined, zA = undefined, zB = undefined, k = 0.0
			if s <= 1.0 then (pA = res[nR - 1]; pB = res[nR]; zA = zs[nR - 1]; zB = zs[nR]; k = s)
			else (pA = res[nR]; pB = cPts; zA = zs[nR]; zB = cZ; k = s - 1.0)
			local pts = for q = 1 to nPt + 1 collect (pA[q] * (1 - k) + pB[q] * k)
			append out #(pts, (normalize (zA * (1 - k) + zB * k)), chains[nR], true, nR)
		)
		out
	)
)
-- 등쪽 줄을 메쉬 표면에 맞춤: 몸 가운데 축에서 그 줄 방향으로 높이마다 수평 광선,
--   줄 가운데 높이에서 가장 바깥 조각(어깨 망토)을 골라 그 조각을 위에서 끝(털 단 앞)까지 따라감. 못 찾으면 undefined
-- 줄 가운데 높이·방향에서 가장 바깥 조각 (등쪽 줄 여러 개 중 가장 많이 나온 조각 = 어깨 망토)
fn tos_secSurfEk guide center tmps r = (
	local mid = guide[(guide.count + 1) / 2]
	local dir = [mid.x - center.x, mid.y - center.y, 0]
	if (length dir) < 1e-4 do return undefined
	local L = tos_secRayLayers [center.x, center.y, mid.z] (normalize dir) tmps
	if L.count > 0 then L[1][2] else undefined
)
-- ekWant: 이 조각이 줄 가운데 높이에서 맞으면 그것을 따라감 (목도리처럼 위에 덮인 조각 대신 어깨 망토)
fn tos_secSurfLine guide center tmps r ekWant:undefined = (
	local mid = guide[(guide.count + 1) / 2]
	local dir = [mid.x - center.x, mid.y - center.y, 0]
	if (length dir) < 1e-4 do return undefined
	dir = normalize dir
	local startP = guide[1]
	local step = 0.5 * r
	local minZ = 1e9
	for t in tmps do minZ = amin minZ t[1].min.z
	local zs = #(), layers = #()
	local z = startP.z - step
	while z > minZ do (
		append zs z
		append layers (tos_secRayLayers [center.x, center.y, z] dir tmps)
		z -= step
	)
	if zs.count < 3 do return undefined
	-- 줄 가운데 높이의 가장 바깥 조각
	local iMid = 1, bd = 1e9
	for i = 1 to zs.count do (local d = abs (zs[i] - mid.z); if d < bd do (bd = d; iMid = i))
	local ek = undefined
	if ekWant != undefined do for i = iMid to (amin zs.count (iMid + 4)) where ek == undefined do (for h in layers[i] where h[2] == ekWant do ek = ekWant)
	for i = iMid to (amin zs.count (iMid + 4)) where ek == undefined and layers[i].count > 0 do ek = layers[i][1][2]
	if ek == undefined do return undefined
	local tr = tos_secTrace layers ek zs startP center dir r nTop:iMid
	local pts = tr[2], i0 = tr[1]
	if pts.count < 3 do return undefined
	-- 끝 다듬기: 마지막으로 맞은 높이와 한 칸 아래 사이를 반씩 나눔
	local hiZ = zs[i0], loZ = zs[i0] - step, hiD = undefined
	for k = 1 to 6 do (
		local mz = (hiZ + loZ) * 0.5, d = undefined
		for h in (tos_secRayLayers [center.x, center.y, mz] dir tmps) where h[2] == ek while d == undefined do d = h[1]
		if d != undefined then (hiZ = mz; hiD = d) else loZ = mz
	)
	if hiD != undefined do append pts ([center.x, center.y, hiZ] + dir * (amax 0.0 (hiD - 0.3 * r)))
	pts
)-- 선 pts 를 (전체 - 끝 본 길이 tipL) 까지 segs 등분 + 맨 끝 점
-- fr: 마디 끝 위치 비율(0~1, segs+1 개) 이 있으면 그 간격으로 (레퍼런스와 마디 수가 같을 때 레퍼런스 간격 그대로)
fn tos_secClavPts pts segs tipL fr:undefined = (
	local all = tos_secResample pts 200
	local cum = #(0.0)
	for i = 2 to all.count do append cum (cum[i - 1] + (distance all[i - 1] all[i]))
	local total = cum[cum.count]
	local span = amax (total * 0.5) (total - tipL)
	local marks = for k = 0 to segs collect (if fr != undefined and fr.count == segs + 1 then span * fr[k + 1] else span * k / segs)
	append marks total
	for m in marks collect (
		local p = all[all.count], found = false
		for i = 2 to all.count while not found do (
			if cum[i] >= m - 1e-5 do (
				local d = cum[i] - cum[i - 1]
				local t = if d > 1e-6 then (m - cum[i - 1]) / d else 0.0
				p = all[i - 1] + (all[i] - all[i - 1]) * t
				found = true
			)
		)
		p
	)
)
-- 레퍼런스 줄의 마디 간격 비율 (끝 본 제외)
fn tos_secChainFr ch = (
	local pts = for e in ch collect e[5].row4
	local cum = #(0.0)
	for i = 2 to pts.count do append cum (cum[i - 1] + (distance pts[i - 1] pts[i]))
	local tot = cum[cum.count]
	for c in cum collect (if tot > 1e-6 then c / tot else 0.0)
)
-- 줄 하나의 최종 점: 등쪽이면 메쉬 표면에 맞춤 (못 맞추면 레퍼런스 모양)
fn tos_secClavFinal s segs tipL ch jSp tmps r ekWant:undefined = (
	local fit = if s[4] and tmps.count > 0 then (tos_secSurfLine s[1] jSp tmps r ekWant:ekWant) else undefined
	if fit != undefined then #((tos_secClavPts fit segs tipL), true)
	else #((tos_secClavPts s[1] segs tipL fr:(tos_secChainFr ch)), false)
)
fn tos_secBuildClav rows segs = (
	if not (tos_secClavRefLoad()) do return ("오류: 어깨 레퍼런스 파일이 없어요: " + (TosRig.dataFile "tos_clavicle_ref.ms"))
	local pre = TosRig.bipPrefix()
	if pre == undefined do return "오류: 장면에 Biped가 없어요. [2. Biped 생성] 을 먼저 하세요."
	local g = TosRig.gender()
	if g == undefined do return "취소했어요. (성별을 정하지 않음)"
	local ref = undefined
	for s in TOS_ClavRef where s[1] == "clavicle" and s[2] == g do ref = s
	if ref == undefined do ref = TOS_ClavRef[1]   -- 여자는 남자 레퍼런스를 키 비율로
	local sp2 = getNodeByName (pre + " Spine2") exact:true
	local lc = getNodeByName (pre + " L Clavicle") exact:true, rc = getNodeByName (pre + " R Clavicle") exact:true
	if sp2 == undefined or lc == undefined or rc == undefined do return "오류: Biped 에 Spine2 / Clavicle 이 없어요."
	local r = (tos_secHeight pre) / ref[6]
	local jSp = (at time 0 sp2.transform).row4, jL = (at time 0 lc.transform).row4, jR = (at time 0 rc.transform).row4
	local old = tos_secNodes #clavicle
	if old.count > 0 and not (queryBox ("이미 어깨 본이 " + (old.count as string) + "개 있어요.\n지우고 " + (rows as string) + "줄 × " + (segs as string) + "마디로 다시 만들까요? (Ctrl+Z 가능)") title:"TOS_RigTools - 세컨더리 본") do return "취소했어요. (변경 없음)"
	-- 레퍼런스 줄 나누기
	local ents = ref[7]
	local baseE = undefined
	for e in ents where e[1] == "Bone_Spine2_Base" do baseE = e
	local chainsL = #(), chainsR = #(), chainC = undefined
	for e in ents where e[3] == "Bip01 L Clavicle" or e[3] == "Bip01 R Clavicle" or e[3] == "Bone_Spine2_Base" do (
		local ch = #(e), cur = e, more = true
		while more do (more = false; for x in ents where x[3] == cur[1] do (append ch x; cur = x; more = true))
		if e[3] == "Bip01 L Clavicle" then append chainsL ch else if e[3] == "Bip01 R Clavicle" then append chainsR ch else chainC = ch
	)
	-- 옆마다 앞 안쪽 → 등 순서 (R 은 번호 오름차순, L 은 내림차순 = 레퍼런스 번호 규칙)
	qsort chainsR tos_secByIdx
	qsort chainsL tos_secByIdx
	chainsL = for i = chainsL.count to 1 by -1 collect chainsL[i]
	local nPt = 24
	local made = #(), nFit = 0, nBack = 0
	-- 등쪽 줄을 맞출 메쉬: 선택한 메쉬, 없으면 보이는 메쉬 전부
	local ms = for o in selection where tos_secIsMesh o collect o
	if ms.count == 0 do ms = for o in objects where tos_secIsMesh o collect o
	local tmps = #()
	undo off (tmps = tos_secTmpMeshes ms)
	-- 가운데 줄 (대상 공간): 등쪽 줄을 나눌 때도 씀
	local cPts = for p in (tos_secResample (tos_secChainPts chainC) nPt) collect (jSp + (p - ref[5]) * r)
	local cZ = normalize chainC[1][5].row3
	with animate off at time 0 (
		undo "TOS 세컨더리 어깨" on (
			tos_secDeleteNodes old
			local sideR = tos_secClavSide chainsR rows ref[8][2] jR r nPt cPts cZ
			local sideL = tos_secClavSide chainsL rows ref[8][1] jL r nPt cPts cZ
			local baseN = (tos_secMakeEntries #(baseE) ref[5] jSp r sp2 #clavicle made)[1]
			-- 등쪽 줄들이 가장 많이 맞는 겉 조각 (어깨 망토)
			local eks = #(), cnt = #(), ekMain = undefined
			if tmps.count > 0 do for s in (sideR + sideL) where s[4] do (
				local e = tos_secSurfEk s[1] jSp tmps r
				if e != undefined do (local i = findItem eks e; if i == 0 then (append eks e; append cnt 1) else cnt[i] += 1)
			)
			local best = 0
			for i = 1 to eks.count where cnt[i] > best do (best = cnt[i]; ekMain = eks[i])
			local blk = segs + 1, idx = 1
			for s in sideR do (
				local ch = s[3], tipL = ch[ch.count][6][1] * r
				local fp = tos_secClavFinal s segs tipL ch jSp tmps r ekWant:ekMain
				if s[4] do (nBack += 1; if fp[2] do nFit += 1)
				-- 부모: 앞 바깥·어깨 위 줄 = R Clavicle, 앞 안쪽·등 줄 = Bone_Spine2_Base
				tos_secMakeChainPts fp[1] s[2] ch[1] ch[ch.count] idx (if s[5] == 2 or s[5] == 3 then rc else baseN) #clavicle made
				idx += blk
			)
			local tipC = chainC[chainC.count][6][1] * r
			-- 가운데(등) 줄도 어깨 망토 표면에 (목도리 꼬리 밑의 어깨 망토를 따라감)
			local fpC = tos_secClavFinal #(cPts, cZ, chainC, true) segs tipC chainC jSp tmps r ekWant:ekMain
			nBack += 1; if fpC[2] do nFit += 1
			tos_secMakeChainPts fpC[1] cZ chainC[1] chainC[chainC.count] idx baseN #clavicle made
			idx += blk
			-- L 은 등 → 앞 안쪽 순서로 번호 (레퍼런스 21 = 등)
			for i = sideL.count to 1 by -1 do (
				local s = sideL[i], ch = s[3], tipL = ch[ch.count][6][1] * r
				local fp = tos_secClavFinal s segs tipL ch jSp tmps r ekWant:ekMain
				if s[4] do (nBack += 1; if fp[2] do nFit += 1)
				tos_secMakeChainPts fp[1] s[2] ch[1] ch[ch.count] idx (if s[5] == 2 or s[5] == 3 then lc else baseN) #clavicle made
				idx += blk
			)
			tos_secBoneProps made
			-- Base 는 자식(가운데 줄)이 붙으면 길이가 바뀌므로 레퍼런스 길이로 되돌림
			try (baseN.length = baseE[6][1] * r) catch ()
		)
	)
	undo off (for tm in tmps where isValidNode tm[1] do delete tm[1])
	completeRedraw()
	"[세컨더리 본] Clavicle(어깨) " + (made.count as string) + "개 만듦 (레퍼런스 " + ref[3] + ", 키 비율 " + (formattedPrint r format:".3f") + ")\n" + \
		"옆마다 " + (rows as string) + "줄 + 가운데 1줄, 줄마다 " + (segs as string) + "마디 + 끝\n부모: 앞 바깥·어깨 위 줄 = " + pre + " L/R Clavicle, 앞 안쪽·등·가운데 줄 = Bone_Spine2_Base (" + pre + " Spine2 아래)\n등쪽 줄 메쉬 표면에 맞춤 " + (nFit as string) + "/" + (nBack as string) + (if nFit < nBack then " (못 맞춘 줄은 레퍼런스 모양. 어깨 망토 메쉬만 선택하고 다시 누르면 더 잘 맞아요)" else "") + \
		(if old.count > 0 then "\n예전 본 " + (old.count as string) + "개는 지웠어요." else "") + "\nCtrl+Z 로 되돌릴 수 있어요."
)

-- 본 목록: #cloak / #skirt_S / #skirt_N / #skirt_W 중 장면에 있는 것
fn tos_secItems =
(
	tos_secKeys = #()
	local out = #()
	for k in #(#cloak, #clavicle, #skirt_S, #skirt_N, #skirt_W) do
	(
		local ns = tos_secNodes k
		if ns.count > 0 do
		(
			local lbl = case k of (#cloak: "Cloak"; #clavicle: "Clavicle (어깨)"; #skirt_S: "Skirt_S"; #skirt_N: "Skirt"; #skirt_W: "Skirt_W")
			if k == #cloak do
			(
				local t = undefined
				for o in ns where t == undefined do (local p = getUserProp o "TOS_sec"; if p != undefined and p != "skirt_all" do t = p as string)
				lbl += case t of ("cloak_waist": " (허리)"; "cloak_knee": " (무릎)"; "cloak_foot": " (발)"; default: "")
			)
			append out (lbl + "  -  본 " + (ns.count as string) + "개")
			append tos_secKeys k
		)
	)
	out
)
fn tos_secPick i =
(
	if i < 1 or i > tos_secKeys.count do return "목록에서 고르세요."
	local ns = tos_secNodes tos_secKeys[i]
	if ns.count == 0 then "본이 없어요." else (select ns; (ns.count as string) + "개 선택")
)
fn tos_secDelete i =
(
	if i < 1 or i > tos_secKeys.count do return "목록에서 고르세요."
	local k = tos_secKeys[i]
	local ns = tos_secNodes k
	local n = 0
	undo "TOS 세컨더리 삭제" on
	(
		n = tos_secDeleteNodes ns
		-- 치마 줄이 하나도 안 남으면 Bone_Skirt_all 도 지움
		if k != #cloak and k != #clavicle and (tos_secNodes #skirt_S).count == 0 and (tos_secNodes #skirt_N).count == 0 and (tos_secNodes #skirt_W).count == 0 do
		(
			local a = getNodeByName "Bone_Skirt_all" exact:true
			if a != undefined and a.children.count == 0 do (delete a; n += 1)
		)
	)
	completeRedraw()
	"본 " + (n as string) + "개를 지웠어요. (Ctrl+Z 가능)"
)
format "[tos_secondary] loaded\n"
