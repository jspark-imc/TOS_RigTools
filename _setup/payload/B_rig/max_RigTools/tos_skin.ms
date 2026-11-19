-- ======================================================================
--  TOS_RigTools 1.0 - 5. 스킨 적용 (레퍼런스 웨이트)
--  1) 몸 웨이트: 같은 성별 레퍼런스 코스튬(스킨 있음)들의 바인드 자세 정점에서 가장 가까운 정점 4개의 웨이트를 섞어 옮김
--     (tos_skindb_<m|f>.txt). 레퍼런스의 치마·망토·기타 본 웨이트는 그 본의 Biped 조상으로 모음
--  2) 세컨더리(망토·치마) 웨이트: 이 캐릭터에 [4. 세컨더리 본] 으로 만든 Bone_cloak_* / Bone_Skirt_* 본에 거리로 줌
--     (몸 뼈보다 세컨더리 본에 확실히 가까운 정점, 메쉬 조각(element) 단위로 다수결)
--  3) Max Skin 에 넣음 (정점당 최대 4본, 합 1). 바인드 = Figure Mode 자세
-- ======================================================================
global tos_skinApply
global tos_skNormTop, tos_skSpineFix   -- 아래에서 정의 (먼저 정의된 함수가 부를 때 처음 읽을 때도 찾게 미리 선언)
fn tos_skByD a b = (if a[2] < b[2] then -1 else if a[2] > b[2] then 1 else 0)
fn tos_skByW a b vals: = (if vals[a] > vals[b] then -1 else if vals[a] < vals[b] then 1 else 0)
global tos_secIsMesh, tos_secBuild   -- tos_secondary.ms 에서 정의 (이 파일을 먼저 읽어도 되게 미리 선언)
global tos_skJointOff, tosjt_apply, tosjt_segs, tosjt_nearSeg, TOS_JointData_m, TOS_JointData_f   -- 관절 학습값 (tos_joint.ms). tos_skJointOff = true 면 끔 (시험용)
global tos_skinDB = #(undefined, undefined)   -- 1 = 남, 2 = 여: #(본이름들, 조상들, 위치들, 웨이트들, 격자)

fn tos_skDBFile g = (TosRig.dataFile ("tos_skindb_" + (g as string) + ".txt"))

-- 웨이트 모음 읽기 + 격자(셀 크기 cs)
fn tos_skLoad g = (
	local k = if g == #m then 1 else 2
	if tos_skinDB[k] != undefined do return tos_skinDB[k]
	local f = tos_skDBFile g
	if not (doesFileExist f) do return undefined
	local lines = (dotNetClass "System.IO.File").ReadAllLines f
	local head = filterString lines[1] "\t"
	local names = #(), anc = #()
	for e in (filterString head[2] ";") do (local p = filterString e "|"; append names p[1]; append anc (if p.count > 1 then p[2] else ""))
	local pos = #(), wts = #()
	pos.count = lines.count - 1; wts.count = lines.count - 1
	local n = 0
	for i = 2 to lines.count do (
		local t = filterString lines[i] " "
		if t.count >= 5 do (
			n += 1
			pos[n] = [t[1] as float, t[2] as float, t[3] as float]
			wts[n] = for j = 4 to t.count - 1 by 2 collect #((t[j] as integer) + 1, t[j + 1] as float)
		)
	)
	pos.count = n; wts.count = n
	-- 격자
	local cs = 1.5
	local grid = dotNetObject "System.Collections.Hashtable"
	local cells = #()
	for i = 1 to n do (
		local p = pos[i]
		local key = ((floor (p.x / cs)) as integer) as string + "," + ((floor (p.y / cs)) as integer) as string + "," + ((floor (p.z / cs)) as integer) as string
		if grid.ContainsKey key then append cells[grid.Item[key]] i
		else (append cells #(i); grid.Add key cells.count)
	)
	tos_skinDB[k] = #(names, anc, pos, wts, grid, cells, cs)
	tos_skinDB[k]
)

-- 가장 가까운 레퍼런스 정점 kN 개 (번호, 거리)
fn tos_skNear db p kN = (
	local grid = db[5], cells = db[6], cs = db[7], pos = db[3]
	local cx = (floor (p.x / cs)) as integer, cy = (floor (p.y / cs)) as integer, cz = (floor (p.z / cs)) as integer
	local found = #()
	for r = 1 to 8 while found.count < kN do (
		found = #()
		for ix = cx - r to cx + r do for iy = cy - r to cy + r do for iz = cz - r to cz + r do (
			local key = (ix as string) + "," + (iy as string) + "," + (iz as string)
			if grid.ContainsKey key do for i in cells[grid.Item[key]] do append found #(i, distance p pos[i])
		)
	)
	qsort found tos_skByD
	if found.count > kN do found.count = kN
	found
)

fn tos_skIsSec nm = (matchPattern nm pattern:"Bone_cloak_*" or matchPattern nm pattern:"Bone_Skirt_*" or (matchPattern nm pattern:"Bone_Spine2_*" and nm != "Bone_Spine2_Base"))

-- 레퍼런스 본 번호 → 이 장면의 본 노드 (없거나 세컨더리·기타 본이면 Biped 조상)
fn tos_skMapBones db = (
	for i = 1 to db[1].count collect (
		local nm = db[1][i], o = undefined
		if not (matchPattern nm pattern:"Bone_*") do o = getNodeByName nm exact:true
		-- TOS 레퍼런스 이름 차이: "Clavicle Twist2" = 툴이 만든 "Clavicle Twist 2", 가슴 더미 Dummy_Chest·Dummy_L/R_Chest = Dummy_Chast
		if o == undefined and matchPattern nm pattern:"*Twist2" do o = getNodeByName (substituteString nm "Twist2" "Twist 2") exact:true
		if o == undefined and matchPattern nm pattern:"Dummy*Chest" do o = getNodeByName "Dummy_Chast" exact:true
		-- 장면에 없는 레퍼런스 세컨더리 본은 Biped 조상으로. 단 Spine 아래 치마 본(TOS 레퍼런스는 Bone_skirt_All 이 Bip01 Spine 아래)은 Pelvis 로
		--   (Spine 으로 모으면 엉덩이 몸 웨이트가 Spine 으로 가서 골반이 덜 따라옴: catagnan_cat01 엉덩이 Pelvis 0.23 / 레퍼런스 0.53)
		if o == undefined and db[2][i] != "" and (matchPattern db[2][i] pattern:"* Spine") and (matchPattern nm pattern:"*skirt*") do o = getNodeByName (substituteString db[2][i] " Spine" " Pelvis") exact:true
		if o == undefined and db[2][i] != "" do o = getNodeByName db[2][i] exact:true
		o
	)
)

-- 허리~가슴 척추 비율 표: s = 척추 좌표 (Spine 높이 = 1, Spine1 = 2, Spine2 = 3, Neck = 4, 사이는 높이 비율). 값 = Pelvis, Spine, Spine1, Spine2
--   몸 웨이트 모음 8벌은 이 띠에서 Spine1 이 평균 0.16 뿐이라 Spine1 이 약했음.
--   TOS 직업 폴더 _set 40벌 평균(아래 _avg, 몸 가운데 ±4 정점)은 옷마다 경계 높이가 달라 섞이면서 흐려짐 (Spine1 최대 0.5, Spine2 가 가슴에서 0.85).
--   그래서 평균의 경계 위치(Spine→Spine1 은 평균보다 조금 아래 s 약 2.1, Spine1→Spine2 는 평균대로 s 약 2.85)에 레퍼런스처럼 또렷한 경계를 씀:
--   각 척추 본이 자기 관절 위 구간을 주로 가짐 (catagnan_cat01 레퍼런스: s 2~2.25 Spine1 0.66, s 3.25 위 Spine2 1.0)
global tos_skSpineAvg_f = #(#(1.625, 0.15, 0.71, 0.13, 0.00), #(1.875, 0.09, 0.70, 0.19, 0.01), #(2.125, 0.02, 0.59, 0.35, 0.03), #(2.375, 0.01, 0.45, 0.44, 0.10), #(2.625, 0.00, 0.27, 0.51, 0.21), #(2.875, 0.00, 0.06, 0.41, 0.51), #(3.125, 0.00, 0.01, 0.18, 0.76), #(3.375, 0.00, 0.00, 0.03, 0.85))
global tos_skSpineAvg_m = #(#(1.625, 0.12, 0.61, 0.24, 0.02), #(1.875, 0.09, 0.58, 0.29, 0.03), #(2.125, 0.03, 0.50, 0.41, 0.06), #(2.375, 0.01, 0.37, 0.50, 0.12), #(2.625, 0.01, 0.25, 0.44, 0.29), #(2.875, 0.01, 0.08, 0.33, 0.58), #(3.125, 0.00, 0.07, 0.14, 0.75), #(3.375, 0.00, 0.02, 0.08, 0.88))
global tos_skSpineTab_f = #(#(1.625, 0.10, 0.80, 0.10, 0.00), #(1.875, 0.03, 0.70, 0.27, 0.00), #(2.125, 0.00, 0.45, 0.52, 0.03), #(2.375, 0.00, 0.22, 0.70, 0.08), #(2.625, 0.00, 0.08, 0.67, 0.25), #(2.875, 0.00, 0.02, 0.40, 0.58), #(3.125, 0.00, 0.00, 0.10, 0.90), #(3.375, 0.00, 0.00, 0.02, 0.98))
global tos_skSpineTab_m = tos_skSpineTab_f
-- 표 값을 섞는 정도 (1 = 표 그대로, 0 = 몸 웨이트 모음 그대로)
global tos_skSpineMix = 1.0
-- 가슴 더미(Dummy_Chast) 몫을 남기는 비율 (가슴 s 2.5 위, 나머지는 Spine2)
global tos_skChestK = 0.35
-- 몸통 정점(세컨더리 아님, Pelvis·Spine·Spine1·Spine2 몫이 60% 넘음)의 그 네 본 몫을 위 표대로 다시 나눔 (총 몫은 그대로, 팔·목·가슴 더미 등 다른 본은 그대로)
--   s 1.75~3.25 는 표 그대로, 1.5~1.75 와 3.25~3.5 는 원래 값과 섞어 이음. 그 밖(엉덩이·목)은 그대로
fn tos_skSpineFix W tm secAll pre g = (
	local tab = if g == #m then tos_skSpineTab_m else tos_skSpineTab_f
	local js = for n in #("Pelvis", "Spine", "Spine1", "Spine2", "Neck") collect (getNodeByName (pre + " " + n) exact:true)
	if (for j in js where j == undefined collect j).count > 0 do return 0
	local zs = for j in js collect j.transform.pos.z
	local n = 0
	for v = 1 to tm.numverts where not secAll[v] do (
		local z = (getVert tm v).z
		local s = undefined
		for k = 2 to 4 where z >= zs[k] and z < zs[k + 1] do s = (k - 1) + (z - zs[k]) / (zs[k + 1] - zs[k])
		if s == undefined or s < 1.5 do continue
		-- 가슴(s 2.5 위): 가슴 더미(Dummy*) 몫을 0.35 배로, 나머지는 Spine2 로 (여자 _set 40벌 가슴 가운데: Spine2 0.84 · 더미 0.06, 몸 웨이트 모음에서 오면 더미 0.17)
		if s >= 2.5 do (
			local dW = 0.0
			for e in W[v] where matchPattern e[1].name pattern:"Dummy*" do dW += e[2]
			if dW > 0 do (
				local acc0 = for e in W[v] collect (if matchPattern e[1].name pattern:"Dummy*" then #(e[1], e[2] * tos_skChestK) else #(e[1], e[2]))
				append acc0 #(js[4], dW * (1.0 - tos_skChestK))
				W[v] = tos_skNormTop acc0
			)
		)
		if s >= 3.5 do continue
		local tot = 0.0, all = 0.0
		for e in W[v] do (all += e[2]; if findItem js e[1] > 0 and e[1] != js[5] do tot += e[2])
		if all <= 0 or tot < all * 0.6 do continue
		-- 표 값 (가까운 두 줄 사이 직선)
		local pr = undefined
		if s <= tab[1][1] then pr = for i = 2 to 5 collect tab[1][i]
		else if s >= tab[tab.count][1] then pr = for i = 2 to 5 collect tab[tab.count][i]
		else for r = 1 to tab.count - 1 where s >= tab[r][1] and s < tab[r + 1][1] do (
			local u = (s - tab[r][1]) / (tab[r + 1][1] - tab[r][1])
			pr = for i = 2 to 5 collect (tab[r][i] * (1 - u) + tab[r + 1][i] * u)
		)
		local ps = 0.0
		for x in pr do ps += x
		if ps <= 0 do continue
		local a = (if s < 1.75 then (s - 1.5) / 0.25 else if s > 3.25 then (3.5 - s) / 0.25 else 1.0) * tos_skSpineMix
		local acc = #()
		for e in W[v] do (
			if findItem js e[1] > 0 and e[1] != js[5] then append acc #(e[1], e[2] * (1 - a))
			else append acc #(e[1], e[2])
		)
		for i = 1 to 4 where pr[i] > 0 do append acc #(js[i], tot * a * pr[i] / ps)
		W[v] = tos_skNormTop acc
		n += 1
	)
	n
)

-- 조각(면 bitarray el)의 정점 이웃: 배열[정점] = #(이웃 정점...) (조각 밖 정점은 undefined)
fn tos_skAdj tm el = (
	local adj = #()
	adj.count = tm.numverts
	for f in el do (
		local fc = getFace tm f
		local a = fc.x as integer, b = fc.y as integer, c = fc.z as integer
		for pr in #(#(a, b), #(b, c), #(c, a)) do (
			if adj[pr[1]] == undefined do adj[pr[1]] = #()
			if adj[pr[2]] == undefined do adj[pr[2]] = #()
			appendIfUnique adj[pr[1]] pr[2]
			appendIfUnique adj[pr[2]] pr[1]
		)
	)
	adj
)
-- 선분(뼈) 까지 거리와 비율 t
fn tos_skSeg p a b = (
	local ab = b - a, l2 = dot ab ab
	local t = if l2 < 1e-9 then 0.0 else (dot (p - a) ab) / l2
	if t < 0 do t = 0.0
	if t > 1 do t = 1.0
	#(distance p (a + ab * t), t)
)
fn tos_skBoneSeg o = (
	local a = o.transform.pos
	local kids = for c in o.children where classOf c == classOf o and not (matchPattern c.name pattern:"*Twist*") collect c
	local b = if kids.count > 0 then kids[1].transform.pos else (
		if classOf o == BoneGeometry then a + (normalize o.transform.row1) * o.length
		else if o.parent != undefined then a + (a - o.parent.transform.pos) * 0.5 else a)
	#(a, b)
)

fn tos_skNormTop ws = (
	-- ws: #(#(node, w), ...) → 같은 본 합치고, 큰 순 4개, 합 1
	local nodes = #(), vals = #()
	for e in ws where e[1] != undefined and e[2] > 0 do (local i = findItem nodes e[1]; if i == 0 then (append nodes e[1]; append vals e[2]) else vals[i] += e[2])
	local idx = for i = 1 to nodes.count collect i
	qsort idx tos_skByW vals:vals
	if idx.count > 4 do idx.count = 4
	local s = 0.0
	for i in idx do s += vals[i]
	if s < 1e-6 then #() else (for i in idx collect #(nodes[i], vals[i] / s))
)

-- 망토·치마 정점에 섞는 몸 웨이트는 몸통만: 팔 쪽 본 → 그쪽 Clavicle, 다리 쪽 본 → Pelvis (팔·다리를 움직여도 망토 윗단이 끌려가지 않게)
fn tos_skTorso o pre = (
	local nm = o.name
	local side = if matchPattern nm pattern:"* L *" or matchPattern nm pattern:"* L*Twist*" or matchPattern nm pattern:"*LThighTwist*" then "L" else "R"
	if matchPattern nm pattern:"*UpperArm*" or matchPattern nm pattern:"*Forearm*" or matchPattern nm pattern:"*ForeTwist*" or matchPattern nm pattern:"*Hand*" or matchPattern nm pattern:"*Finger*" or matchPattern nm pattern:"*Clavicle Twist*" then
		(local c = getNodeByName (pre + " " + side + " Clavicle") exact:true; if c != undefined then c else o)
	else if matchPattern nm pattern:"*Thigh*" or matchPattern nm pattern:"*Calf*" or matchPattern nm pattern:"*Foot*" or matchPattern nm pattern:"*Toe*" then
		(local c = getNodeByName (pre + " Pelvis") exact:true; if c != undefined then c else o)
	else o
)
-- 허벅지 웨이트 비율표 (TOS: ani\Character\PC 레퍼런스 스킨에서 잰 값, 좌우 같음)
--   여자 11개(4직업 6th_greenschool·6th_cardiganschool, Arbalester01, cleric_f·mage_f ep17bunnygambler01) + 남자 8개 평균.
--   TOS 레퍼런스는 ThighTwist 에 웨이트를 주지 않음 (모두 0) → Pelvis 가 엉덩이~허벅지 중간까지 Thigh 로 넘어감
--   (MTOS 는 monk_m_shenji01_set 값: ThighTwist 가 허벅지 윗부분을 받음)
-- t = 허벅지 축 위치 (0 = Thigh 시작(엉덩이 관절), 1 = Calf 시작(무릎)), 값 = #(Pelvis, ThighTwist, Thigh, Calf)
global tos_skLegT = #(-0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3)
global tos_skLegW = #(#(0.95,0,0.05,0), #(0.85,0,0.15,0), #(0.78,0,0.22,0), #(0.64,0,0.36,0), #(0.55,0,0.45,0), #(0.36,0,0.64,0), #(0.10,0,0.90,0), #(0.08,0,0.92,0), #(0.02,0,0.98,0), #(0,0,1.0,0), #(0,0,0.91,0.09), #(0,0,0.90,0.10), #(0,0,0.48,0.52), #(0,0,0.12,0.88), #(0,0,0.03,0.97), #(0,0,0,1.0))
fn tos_skLegProf t = (
	local n = tos_skLegT.count
	if t <= tos_skLegT[1] then tos_skLegW[1] else if t >= tos_skLegT[n] then tos_skLegW[n] else (
		local i = 1
		while tos_skLegT[i + 1] < t do i += 1
		local k = (t - tos_skLegT[i]) / (tos_skLegT[i + 1] - tos_skLegT[i])
		for j = 1 to 4 collect (tos_skLegW[i][j] * (1 - k) + tos_skLegW[i + 1][j] * k)
	)
)
-- W: 정점 웨이트 #(#(node, w)...). 허벅지 근처 몸 정점의 (Pelvis + 그쪽 Thigh·ThighTwist·Calf) 몫을 비율표대로 다시 나눔.
-- 다른 본(Spine 등) 몫은 그대로. 망토·치마(secAll) 정점은 건드리지 않음. 반환: 고친 정점 수
-- 통째로 움직이는 작은 조각 중 무릎 아래(허벅지 축 t > 1.03)에 있는 것: 그쪽 Thigh·ThighTwist 몫을 Calf 로. 반환: 고친 조각 수
-- 조각이 관절(무릎·발목·팔꿈치·손목)을 가로지르는지: 그 팔다리 가까이 있고, 위 뼈 축 위치 t 가 관절(1) 양쪽에 걸침
global tos_skJointPairs = #(#("Thigh", "Calf"), #("Calf", "Foot"), #("UpperArm", "Forearm"), #("Forearm", "Hand"))
fn tos_skCrossJoint vs tm pre = (
	local cross = false
	for sd in #("L", "R") while not cross do for jp in tos_skJointPairs while not cross do (
		local n1 = getNodeByName (pre + " " + sd + " " + jp[1]) exact:true, n2 = getNodeByName (pre + " " + sd + " " + jp[2]) exact:true
		if n1 == undefined or n2 == undefined do continue
		local a = n1.transform.pos, b = n2.transform.pos, L = distance a b
		if L < 1e-3 do continue
		local ax = normalize (b - a)
		local tMin = 1e9, tMax = -1e9, nNear = 0
		for v in vs do (
			local p = getVert tm v
			local t = (dot (p - a) ax) / L
			local rad = length ((p - a) - ax * (t * L))
			if rad < L * 0.8 and t > 0.3 and t < 1.7 do (nNear += 1; tMin = amin tMin t; tMax = amax tMax t)
		)
		if nNear * 2 > vs.numberSet and tMin < 0.92 and tMax > 1.08 do cross = true
	)
	cross
)
fn tos_skKneeRigid W tm rigidSets pre = (
	local n = 0
	for sd in #("L", "R") do (
		local th = getNodeByName (pre + " " + sd + " Thigh") exact:true, ca = getNodeByName (pre + " " + sd + " Calf") exact:true
		local tw = getNodeByName (pre + " " + sd + "ThighTwist") exact:true
		if th == undefined or ca == undefined do continue
		local a = th.transform.pos, b = ca.transform.pos, L = distance a b
		local ax = normalize (b - a)
		for vs in rigidSets do (
			local c = [0, 0, 0], k = 0
			for v in vs do (c += getVert tm v; k += 1)
			if k == 0 do continue
			c /= k
			local t = dot (c - a) ax / L
			local rad = length ((c - a) - ax * (t * L))
			-- 이 다리의 무릎 아래, 다리 가까이 (반대 다리 조각은 빼고)
			if t <= 1.03 or rad > L * 0.8 do continue
			local hit = false
			for v in vs do (
				local acc = #()
				for e in W[v] do (if e[1] == th or (tw != undefined and e[1] == tw) then (append acc #(ca, e[2]); hit = true) else append acc e)
				W[v] = tos_skNormTop acc
			)
			if hit do n += 1
		)
	)
	n
)
fn tos_skLegFix W tm secAll pre = (
	local pel = getNodeByName (pre + " Pelvis") exact:true
	if pel == undefined do return 0
	local legs = #()
	for sd in #("L", "R") do (
		local th = getNodeByName (pre + " " + sd + " Thigh") exact:true, ca = getNodeByName (pre + " " + sd + " Calf") exact:true
		local tw = getNodeByName (pre + " " + sd + "ThighTwist") exact:true
		if th != undefined and ca != undefined and tw != undefined do append legs #(th, tw, ca, th.transform.pos, ca.transform.pos)
	)
	if legs.count == 0 do return 0
	local n = 0
	for v = 1 to W.count where not secAll[v] do (
		local p = getVert tm v
		-- 가까운 쪽 다리
		local best = undefined, bd = 1e9, bt = 0.0
		for lg in legs do (
			local r = tos_skSeg p lg[4] lg[5]
			if r[1] < bd do (bd = r[1]; best = lg)
		)
		local L = distance best[4] best[5]
		local t = dot (p - best[4]) (normalize (best[5] - best[4])) / L
		if t < -0.25 or t > 1.3 do continue
		-- 축에서 너무 멀면(허벅지 살 밖) 그대로
		local rad = length ((p - best[4]) - (normalize (best[5] - best[4])) * (t * L))
		if rad > L * 0.6 do continue
		local legSum = 0.0, thSum = 0.0, rest = #()
		for e in W[v] do (
			if e[1] == pel then legSum += e[2]
			else if e[1] == best[1] or e[1] == best[2] or e[1] == best[3] then (legSum += e[2]; thSum += e[2])
			else append rest e
		)
		-- 다리·골반 몫이 대부분인 정점만, 엉덩이 위(t<0.1)는 허벅지 웨이트가 조금이라도 있던 정점만
		if legSum < 0.8 do continue
		if t < 0.1 and thSum < 0.05 do continue
		-- 비율표 끝(t 0.9~1.0, -0.25~-0.15)은 원래 웨이트와 섞어 경계를 부드럽게
		local k = if t > 1.2 then (1.3 - t) / 0.1 else if t < -0.15 then (t + 0.25) / 0.1 else 1.0
		local pr = tos_skLegProf t
		local acc = for e in W[v] collect #(e[1], e[2] * (1.0 - k))
		append acc #(pel, pr[1] * legSum * k)
		append acc #(best[2], pr[2] * legSum * k)
		append acc #(best[1], pr[3] * legSum * k)
		append acc #(best[3], pr[4] * legSum * k)
		for e in rest do append acc #(e[1], e[2] * k)
		W[v] = tos_skNormTop acc
		n += 1
	)
	n
)
-- 진행 막대: 메쉬 mi/mn 번째, 단계 구간 [a, b] 안에서 k/n 만큼. 취소 누르면 throw
global tos_skPr_mi = 1, tos_skPr_mn = 1
global tos_skWasFig = undefined
global tos_skinApplyRun
global tos_skPr_nm = "", tos_skCancel = false, tos_skPrRoll
-- Max 기본 진행 막대(progressStart)는 Modify 패널을 비워 skinOps 가 안 되므로 작은 창을 따로 띄움
rollout tos_skPrRoll "TOS 스킨 적용 중... (Esc = 취소)" width:400 height:92 (
	label lb1 "" align:#left width:380 pos:[10,8]
	progressBar pb width:380 height:16 color:(color 70 150 240) pos:[10,28]
	label lb2 "0 %" align:#left width:290 pos:[10,56]
	button bc "취소" width:80 pos:[310,52]
	on bc pressed do tos_skCancel = true
)
fn tos_skPrOpen = (
	tos_skCancel = false
	try (destroyDialog tos_skPrRoll) catch ()
	createDialog tos_skPrRoll style:#(#style_titlebar, #style_border)
	windows.processPostedMessages()
)
fn tos_skPrClose = (try (destroyDialog tos_skPrRoll) catch ())
fn tos_skProg a b k n = (
	if k == 1 or k == n or (mod k 150) == 0 do (
		local f = a + (b - a) * (k as float / (amax 1 n))
		local pct = 100.0 * ((tos_skPr_mi - 1) + f) / tos_skPr_mn
		local st = if a < 0.39 then "몸 웨이트 옮기는 중" else if a < 0.59 then "망토·치마(세컨더리) 나누는 중" else if a < 0.74 then "웨이트 고르는 중" else "Skin 에 웨이트 쓰는 중"
		try (
			tos_skPrRoll.lb1.text = "메쉬 " + (tos_skPr_mi as string) + "/" + (tos_skPr_mn as string) + "  " + tos_skPr_nm
			tos_skPrRoll.pb.value = pct
			tos_skPrRoll.lb2.text = (formattedPrint pct format:".0f") + " %  ·  " + st
		) catch ()
		windows.processPostedMessages()
		if tos_skCancel or keyboard.escPressed do throw "TOS_CANCEL"
	)
	ok
)
fn tos_skinApply meshes:undefined = (
	local r = undefined
	tos_skPrOpen()
	try (r = tos_skinApplyRun meshes) catch (
		local ex = getCurrentException()
		tos_skPrClose()
		enableSceneRedraw()
		-- 취소든 오류든: 끝내지 못한 메쉬는 새 Skin 을 지우고 예전 Skin 을 다시 켬
		for o in objects where superClassOf o == GeometryClass do (
			for i = o.modifiers.count to 1 by -1 where classOf o.modifiers[i] == Skin and o.modifiers[i].name == "TOS_SkinNew" do deleteModifier o i
			for md in o.modifiers where classOf md == Skin and not md.enabled do md.enabled = true
		)
		local pre = TosRig.bipPrefix()
		if pre != undefined and tos_skWasFig != undefined do try ((getNodeByName pre exact:true).controller.figureMode = tos_skWasFig) catch ()
		completeRedraw()
		if ex != undefined and (findString ex "TOS_CANCEL") != undefined then (
			r = "취소했어요. (끝난 메쉬는 새 스킨, 나머지는 예전 그대로)"
		) else throw (if ex == undefined then "스킨 적용 실패" else ex)
	)
	tos_skPrClose()
	r
)
fn tos_skinApplyRun meshes = (
	local pre = TosRig.bipPrefix()
	if pre == undefined do return "오류: 장면에 Biped가 없어요."
	TosRig.secLoad()
	local g = TosRig.gender()
	if g == undefined do return "취소했어요. (성별을 정하지 않음)"
	local t0 = timeStamp()
	local db = tos_skLoad g
	if db == undefined do return ("오류: 레퍼런스 웨이트 모음이 없어요: " + (tos_skDBFile g) + "\n창 아래 [레퍼런스 다시 읽기] 를 눌러 만드세요.")
	local bmap = tos_skMapBones db
	local bip = getNodeByName pre exact:true
	local wasFig = bip.controller.figureMode
	tos_skWasFig = wasFig
	bip.controller.figureMode = true
	-- 대상 메쉬: 넘겨준 것, 아니면 선택한 메쉬, 아니면 보이는 메쉬 (본·Biped·트위스트 상자·점 제외)
	if meshes == undefined do (
		meshes = for o in selection where tos_secIsMesh o and (canConvertTo o Editable_Mesh) collect o
		if meshes.count == 0 do meshes = for o in objects where tos_secIsMesh o and (canConvertTo o Editable_Mesh) collect o
	)
	if meshes.count == 0 do (bip.controller.figureMode = wasFig; return "오류: 스킨을 넣을 메쉬가 없어요.")
	-- 몸 뼈 선분 (세컨더리 판정용) / 세컨더리 본 선분
	local bodyB = for o in objects where classOf o == Biped_Object and not (matchPattern o.name pattern:"*Footsteps") and not (matchPattern o.name pattern:"*Nub") collect o
	local bodyS = for o in bodyB collect (tos_skBoneSeg o)
	local secB = for o in objects where classOf o == BoneGeometry and (tos_skIsSec o.name) and not (matchPattern o.name pattern:"*_All") and not (matchPattern o.name pattern:"*_all") collect o
	local secS = for o in secB collect (tos_skBoneSeg o)
	local h = (getNodeByName (pre + " Neck") exact:true).transform.pos.z - (getNodeByName (pre + " L Foot") exact:true).transform.pos.z
	local secMax = h * 0.15
	local cxy = (getNodeByName (pre + " Spine2") exact:true).transform.pos
	local pelZ = (getNodeByName (pre + " Pelvis") exact:true).transform.pos.z
	-- 몸통 축 (Pelvis → Neck): 어깨·팔 덮는 메쉬 판정에서 팔보다 몸통에 가까운 정점(허리 뒤 등)은 빼려고
	local torsoA = (getNodeByName (pre + " Pelvis") exact:true).transform.pos, torsoB = (getNodeByName (pre + " Neck") exact:true).transform.pos
	-- 어깨·팔을 덮는 메쉬에 쓰는 위팔 정보 (L, R):
	--   #(UpperArm, Clavicle, 어깨 관절 위치, 위팔 방향, 위팔 길이, Clavicle Twist, Clavicle Twist 2, 그쪽 Clavicle 에 붙은 어깨 본(Bone_Spine2_*) 줄이 있나)
	local spAll = for i = 1 to secB.count where matchPattern secB[i].name pattern:"Bone_Spine2_*" collect i
	local armInfo = for sd in #("L", "R") collect (
		local ua = getNodeByName (pre + " " + sd + " UpperArm") exact:true, fa = getNodeByName (pre + " " + sd + " Forearm") exact:true, cl = getNodeByName (pre + " " + sd + " Clavicle") exact:true
		if ua == undefined or fa == undefined or cl == undefined then undefined else (
			local hasC = false
			for i in spAll while not hasC do (
				local q = secB[i].parent
				while q != undefined and not hasC do (
					if q == cl do hasC = true
					q = q.parent
				)
			)
			#(ua, cl, ua.transform.pos, (normalize (fa.transform.pos - ua.transform.pos)), (amax 0.01 (distance ua.transform.pos fa.transform.pos)), (getNodeByName (pre + " " + sd + " Clavicle Twist") exact:true), (getNodeByName (pre + " " + sd + " Clavicle Twist 2") exact:true), hasC)
		)
	)
	local log = ""
	tos_skPr_mn = meshes.count
	for mi = 1 to meshes.count do (
		local m = meshes[mi]
		tos_skPr_mi = mi
		tos_skPr_nm = m.name
		-- 예전 스킨은 잠시 끄고 바인드 위치 읽기 (지우는 건 새 스킨을 넣을 때)
		for md in m.modifiers where classOf md == Skin do md.enabled = false
		local tm = snapshotAsMesh m
		local nv = tm.numverts
		local W = #()
		W.count = nv
		-- 1) 몸 웨이트 (레퍼런스 가까운 정점 4개, 거리 제곱 반비례)
		for v = 1 to nv do (
			tos_skProg 0.0 0.4 v nv
			local p = getVert tm v
			local nb = tos_skNear db p 4
			local acc = #()
			for e in nb do (
				local wi = 1.0 / (e[2] * e[2] + 0.01)
				for bw in db[4][e[1]] do append acc #(bmap[bw[1]], bw[2] * wi)
			)
			W[v] = tos_skNormTop acc
		)
		-- 2) 세컨더리: 몸 뼈보다 세컨더리 뼈에 확실히 가까운 정점 → 메쉬 조각별 다수결
		local nSec = 0, secAll = #{}, nArm = 0, upAll = #{}, upBigAll = #{}
		if secB.count > 0 do (
			local isSec = #{}, near2 = #(), secRat = #()
			secRat.count = nv
			near2.count = nv
			for v = 1 to nv do (
				tos_skProg 0.4 0.6 v nv
				local p = getVert tm v
				local dB = 1e9
				for s in bodyS do (local d = (tos_skSeg p s[1] s[2])[1]; if d < dB do dB = d)
				local ds = for i = 1 to secS.count collect (local r = tos_skSeg p secS[i][1] secS[i][2]; #(i, r[1], r[2]))
				qsort ds tos_skByD
				near2[v] = #(ds[1], (if ds.count > 1 then ds[2] else undefined))
				-- 몸 가운데 축에서 볼 때 그 줄과 같은 쪽에 있어야 (앞가슴 장식이 뒤 망토에 잡히지 않게)
				local sp = (tos_skSeg p secS[ds[1][1]][1] secS[ds[1][1]][2])
				local q = secS[ds[1][1]][1] + (secS[ds[1][1]][2] - secS[ds[1][1]][1]) * sp[2]
				local sameSide = (dot [p.x - cxy.x, p.y - cxy.y, 0] [q.x - cxy.x, q.y - cxy.y, 0]) > 0
				if sameSide and ds[1][2] < secMax and ds[1][2] < dB * 0.75 do isSec[v] = true
				secRat[v] = ds[1][2] / (amax 0.01 dB)
			)
			-- 메쉬 조각(element) 단위 다수결 (조각이 전체의 40% 미만일 때만)
			local done = #{}, faces = #{1..tm.numfaces}, upEl = #{}, upBig = #{}, clCand = #(), cloakV = #{}
			while not faces.isEmpty do (
				local f0 = (faces as array)[1]
				local el = meshop.getElementsUsingFace tm #{f0}
				faces -= el
				local vs = meshop.getVertsUsingFace tm el
				-- 작은 조각은 통째로 (반반 나뉘면 찢어짐)
				-- 큰 조각(정점 100개·전체 5% 이상)에 치마·망토 정점이 15~85% 섞여 있으면 몸과 치마가 한 조각인 옷 → 정점마다 (홀로 떨어진 정점만 이웃 따라 두 번 다듬음)
				--   (예: mage_f_2019xmas01 = 몸·팔·치마가 한 조각 752개 중 치마 176개 → 예전엔 다수결로 치마가 통째로 빠짐)
				local c = (vs * isSec).numberSet, fr = c * 1.0 / vs.numberSet
				local big = vs.numberSet >= (amax 100 (nv * 0.05))
				-- 망토 조각: 세컨더리 후보의 대부분이 망토 본(Bone_cloak_*)에 가깝고 절반 넘게가 후보면 통째로 망토 (아래 섞인 조각 규칙은 몸·치마가 한 조각인 옷용)
				--   (warrior_m_armor_1: 등 망토 198개 중 166개·어깨 망토 228개 중 162개가 후보인데 섞인 조각 규칙에서 다 빠져 몸에만 들어가던 것. 망토 줄 사이 정점이 본에서 멀어 85% 못 넘음)
				local nCk = 0
				for v in vs where isSec[v] and near2[v] != undefined and near2[v][1] != undefined and matchPattern secB[near2[v][1][1]].name pattern:"Bone_cloak_*" do nCk += 1
				local cloakEl = c * 2 > vs.numberSet and nCk >= c * 0.8
				if cloakEl do cloakV += vs
				if big and c >= 20 and fr < 0.85 and not cloakEl then (
					-- 겉에 걸친 천: 정점과 가장 가까운 몸 뼈 축 사이에 다른 면이 있음 (다리·몸 메쉬 바깥에 걸친 치마 안쪽 겹 등)
					--   아래 규칙들(치마 본 0.45 배, 다리 겉면, 안쪽 겹)은 몸 메쉬 자체(스타킹·골반)를 빼려는 것이라, 겉에 걸친 천은 빼지 않음 (warrior_f_7thtaiwan 안쪽 치마 아랫부분)
					local layered = #{}, rayNode = undefined, rmg = undefined
					try (
						rayNode = mesh mesh:tm
						rayNode.isHidden = true
						rmg = RayMeshGridIntersect()
						rmg.Initialize 20
						rmg.addNode rayNode
						rmg.buildGrid()
						for v in vs where isSec[v] do (
							local p = getVert tm v
							local bd = 1e9, bq = undefined
							for s in bodyS do (local r = tos_skSeg p s[1] s[2]; if r[1] < bd do (bd = r[1]; bq = s[1] + (s[2] - s[1]) * r[2]))
							if bq == undefined or bd < 0.2 do continue
							local dir = normalize (bq - p)
							local nh = rmg.intersectRay (p + dir * 0.05) dir false
							for hi = 1 to nh where not layered[v] do (local d = rmg.getHitDist hi; if d > 0.1 and d < bd - 0.15 do layered[v] = true)
						)
					) catch ()
					-- 정점마다: 치마 본이 몸 뼈보다 확실히 가까운 정점만 (치마 본까지 < 몸 뼈까지 × 0.45. 허벅지 겉면처럼 치마 본 근처일 뿐인 정점은 뺌)
					for v in vs where isSec[v] and not layered[v] and secRat[v] != undefined and secRat[v] >= 0.45 do isSec[v] = false
					--   허벅지(위 30% 아래)·종아리 겉면(뼈 축에서 허벅지 길이 0.45 배 안)은 다리 (스타킹·바지). 치마 끝단은 보통 0.55 배 넘게 떨어짐, 허리 쪽 치마는 허벅지 위 30% 라 그대로
					if tosjt_segs == undefined do try (fileIn (TosRig.sbgDir() + "tos_joint.ms")) catch ()
					--   바깥에 다른 메쉬 겹이 있는 정점(로브 안의 다리·몸, 치마 윗단 밑의 골반)은 치마가 아님: 몸 가운데 축에서 바깥으로 쏜 선이 0.7 넘게 떨어진 면에 닿으면 안쪽 겹
					--   (치마 자체의 두께(앞뒤 면)는 0.7 안이라 그대로)
					if rmg != undefined do try (
						--   단 몸 뼈에서 허벅지 길이 0.45 배 넘게 떨어진 정점은 그대로 (두 겹 치마의 안쪽 겹: 겉치마 안에 있어도 몸에서 떨어진 치마. warrior_f_7thtaiwan)
						local thI = getNodeByName (pre + " L Thigh") exact:true, cfI = getNodeByName (pre + " L Calf") exact:true
						local legI = if thI != undefined and cfI != undefined then (distance thI.transform.pos cfI.transform.pos) else 10.0
						for v in vs where isSec[v] do (
							local p = getVert tm v
							local dir = [p.x - cxy.x, p.y - cxy.y, 0]
							if (length dir) < 0.01 do continue
							dir = normalize dir
							local nh = rmg.intersectRay (p + dir * 0.05) dir false
							local inner = false
							for hi = 1 to nh while not inner do if (rmg.getHitDist hi) > 0.7 do inner = true
							if inner do (
								local dB = 1e9
								for s in bodyS do (local d = (tos_skSeg p s[1] s[2])[1]; if d < dB do dB = d)
								if dB < legI * 0.45 and not layered[v] do isSec[v] = false
							)
						)
						--   안쪽(몸 축 쪽)으로 쏜 선이 처음 닿는 면이 다른 조각(다리·몸)이어야 겉에 입은 치마·망토. 같은 조각 가까운 반대편(허벅지 길이 0.6 배 안)에 닿으면 몸 자체(반바지·가슴)라 뺌
						--   (같은 조각이라도 멀리 떨어진 반대편이면 몸을 감싼 로브 반대쪽이라 그대로)
						-- 치마 첫 마디(부모 *_all) 가운데 높이 평균: 그 위는 몸과 섞는 허리 이음매
						local zSeam = 1e9, zsS = 0.0, zsN = 0
						for i = 1 to secB.count where secB[i].parent != undefined and (matchPattern secB[i].parent.name pattern:"*_all" or matchPattern secB[i].parent.name pattern:"*_All") do (zsS += (secS[i][1].z + secS[i][2].z) * 0.5; zsN += 1)
						if zsN > 0 do zSeam = zsS / zsN
						local thR = getNodeByName (pre + " L Thigh") exact:true, cfR = getNodeByName (pre + " L Calf") exact:true
						local legR = if thR != undefined and cfR != undefined then (distance thR.transform.pos cfR.transform.pos) else 10.0
						for v in vs where isSec[v] do (
							local p = getVert tm v
							local dir = [p.x - cxy.x, p.y - cxy.y, 0]
							if (length dir) < 0.01 do continue
							dir = normalize dir
							local nh = rmg.intersectRay (p - dir * 0.05) (-dir) false
							local bd = 1e9, bf = 0
							for hi = 1 to nh do (local d = rmg.getHitDist hi; if d > 0.3 and d < bd do (bd = d; bf = rmg.getHitFace hi))
							if bf != 0 and el[bf] and bd < legR * 0.6 and not (layered[v] and bd < legR * 0.15 and p.z < zSeam) do isSec[v] = false   -- 몸 바로 위에 겹친 천(앞치마: 뼈 축 사이에 몸 면이 있고 그 면이 허벅지 길이 0.15 배 안)은 그대로 (warrior_f_ep13maid02). 치마 첫 마디 가운데 위(몸과 섞는 허리 이음매)는 그대로 빠짐 (12animal01 로브 윗단)
						)
					) catch ()
					try (rmg.free()) catch ()
					try (delete rayNode) catch ()
					if tosjt_segs != undefined do (
						local segsL = tosjt_segs pre
						local thN = getNodeByName (pre + " L Thigh") exact:true, cfN = getNodeByName (pre + " L Calf") exact:true
						local legL = if thN != undefined and cfN != undefined then (distance thN.transform.pos cfN.transform.pos) else 10.0
						for v in vs where isSec[v] do (
							local nsL = tosjt_nearSeg segsL (getVert tm v)
							if nsL != undefined and ((nsL[1] == "thigh" and nsL[3] > 0.3) or nsL[1] == "calf") and nsL[4] < legL * 0.45 and not layered[v] do isSec[v] = false
							--   아래팔·손, 위팔 팔꿈치 쪽(0.6 넘어)은 소매·장갑 (로브와 한 조각이어도 치마 본에 같이 가지 않게, TOS 레퍼런스도 로브만 치마 본)
							--   (몸과 섞인 큰 조각에서만. 따로 떨어진 망토·치마 조각은 팔을 내린 자세에서 손 옆에 있어도 그대로 통째로)
							if nsL != undefined and (nsL[1] == "fa" or nsL[1] == "hand" or (nsL[1] == "ua" and nsL[3] > 0.6)) do isSec[v] = false
						)
					)
					local adjE = tos_skAdj tm el
					--   치마 부분은 끝단(열린 가장자리)까지 이어져야 함: 열린 가장자리 정점에서 시작해 치마 후보끼리 이어진 것만 남김
					--   (몸 메쉬의 골반·엉덩이처럼 치마 본 근처일 뿐 끝단과 안 이어진 덩어리는 뺌)
					--   (끝단 = 골반보다 허벅지 길이 1/4 넘게 아래의 열린 가장자리. 골반 높이의 열린 테두리(치마 자락이 붙는 자리)는 끝단이 아님)
					local openV = meshop.getVertsUsingEdge tm (meshop.getOpenEdges tm)
					local thO = getNodeByName (pre + " L Thigh") exact:true, cfO = getNodeByName (pre + " L Calf") exact:true
					local hemZ = pelZ - (if thO != undefined and cfO != undefined then (distance thO.transform.pos cfO.transform.pos) else 10.0) * 0.25
					local reach = #{}, stack = for v in vs where isSec[v] and openV[v] and (getVert tm v).z < hemZ collect v
					for v in stack do reach[v] = true
					while stack.count > 0 do (
						local v = stack[stack.count]
						stack.count = stack.count - 1
						local nb = adjE[v]
						if nb != undefined do for u in nb where isSec[u] and not reach[u] do (reach[u] = true; append stack u)
					)
					for v in vs where isSec[v] and not reach[v] do isSec[v] = false
					for it = 1 to 2 do (
						local nxt = copy isSec
						for v in vs do (
							local nb = adjE[v]
							-- 홀로 떨어진 정점만 뒤집음 (이웃 80% 이상이 반대일 때). 치마 끝단처럼 가장자리 정점이 지워지지 않게
							if nb != undefined and nb.count > 0 do (
								local k = 0
								for u in nb where isSec[u] do k += 1
								if k >= nb.count * 0.8 then nxt[v] = true else if k <= nb.count * 0.2 do nxt[v] = false
							)
						)
						isSec = nxt
					)
				)
				else if c * 2 > vs.numberSet then (
					isSec += vs
					-- 작은 조각인데 정점 70% 넘게가 다리 겉면(허벅지 위 30% 아래·종아리·발, 뼈 축에서 허벅지 길이 0.45 배 안)이면 부츠·다리 장식 → 치마 아님
					--   (긴 치마 본이 종아리까지 내려와 부츠 윗단이 치마 본에 잡히던 것. 다리 둘레에 떨어져 걸린 로브 자락은 0.45 배 넘게 떨어져 그대로)
					if tosjt_segs == undefined do try (fileIn (TosRig.sbgDir() + "tos_joint.ms")) catch ()
					if tosjt_segs != undefined do (
						local segsK = tosjt_segs pre
						local thK = getNodeByName (pre + " L Thigh") exact:true, cfK = getNodeByName (pre + " L Calf") exact:true
						local legK = if thK != undefined and cfK != undefined then (distance thK.transform.pos cfK.transform.pos) else 10.0
						local nLeg = 0
						for v in vs do (
							local nsK = tosjt_nearSeg segsK (getVert tm v)
							if nsK != undefined and (((nsK[1] == "thigh" and nsK[3] > 0.3) or nsK[1] == "calf" or nsK[1] == "foot") and nsK[4] < legK * 0.45 or (nsK[1] == "thigh" and nsK[4] < legK * 0.3)) do nLeg += 1   -- 허벅지 윗부분은 다리에 붙은 것만 (가터 끈: warrior_f_ep13maid02, 레퍼런스 Thigh·Pelvis)
						)
						if nLeg > vs.numberSet * 0.7 do isSec -= vs
					)
					-- 어깨 본(Bone_Spine2_*)에 잡힌 작은 조각(정점 100개 미만: 깃·어깨 장식) 후보 → 아래(조각 다 본 뒤)에서 몸을 따라갈지 정함
					if vs.numberSet < 100 do (
						local nCl = 0
						for v in vs where near2[v] != undefined and near2[v][1] != undefined and matchPattern secB[near2[v][1][1]].name pattern:"Bone_Spine2_*" do nCl += 1
						if nCl * 2 > vs.numberSet do append clCand vs
					)
				)
				else isSec -= vs
				-- 허리(Pelvis) 위에서 끝나는 큰 조각 = 어깨 망토 (긴 망토·치마, 사슬 고리·방울 같은 작은 장식 조각은 아님)
				local zl = 1e9
				for v in vs do (local z = (getVert tm v).z; if z < zl do zl = z)
				if zl > pelZ and vs.numberSet >= (amax 30 (nv * 0.02)) do upEl += vs
				-- 어깨 망토처럼 큰 조각 (정점 100개 이상): 아래 어깨 본 규칙에서 등·앞 줄까지 거리로 씀 (깃 같은 작은 조각은 아님)
				if zl > pelZ and vs.numberSet >= 100 do upBig += vs
			)
			-- 깃·어깨 장식: 어깨 본 후보 조각끼리 맞닿아(키의 2% 안) 묶은 덩어리가 정점 200개 미만이면 몸을 따라감 (catagnan_cat01 깃 56·72 → 레퍼런스처럼 Spine2·Clavicle)
			--   (noel 어깨 망토·스카프처럼 작은 띠 조각 여러 개가 이어진 큰 덩어리는 그대로 어깨 본)
			if clCand.count > 0 do (
				local gapC = h * 0.02
				local bbs = for vs in clCand collect (
					local lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9]
					for v in vs do (local p = getVert tm v; lo.x = amin lo.x p.x; lo.y = amin lo.y p.y; lo.z = amin lo.z p.z; hi.x = amax hi.x p.x; hi.y = amax hi.y p.y; hi.z = amax hi.z p.z)
					#(lo - [gapC, gapC, gapC], hi + [gapC, gapC, gapC])
				)
				local grp = for i = 1 to clCand.count collect i
				local changed = true
				while changed do (
					changed = false
					for i = 1 to clCand.count do for j = i + 1 to clCand.count where grp[i] != grp[j] do (
						local a = bbs[i], b = bbs[j]
						if a[1].x <= b[2].x and b[1].x <= a[2].x and a[1].y <= b[2].y and b[1].y <= a[2].y and a[1].z <= b[2].z and b[1].z <= a[2].z do (
							local g = amin grp[i] grp[j], o = amax grp[i] grp[j]
							for k = 1 to grp.count where grp[k] == o do grp[k] = g
							changed = true
						)
					)
				)
				for i = 1 to clCand.count do (
					local tot = 0
					for k = 1 to clCand.count where grp[k] == grp[i] do tot += clCand[k].numberSet
					if tot < 200 do isSec -= clCand[i]
				)
			)
			for v in isSec do (
				local a = near2[v][1], b = near2[v][2]
				-- 망토 조각 정점은 망토 본에만 (뒤쪽 치마 줄이 더 가까워도. armor_1 등 망토 아래쪽)
				if cloakV[v] and not (matchPattern secB[a[1]].name pattern:"Bone_cloak_*") do (
					local p = getVert tm v
					local dc = for i = 1 to secS.count where matchPattern secB[i].name pattern:"Bone_cloak_*" collect (local rr = tos_skSeg p secS[i][1] secS[i][2]; #(i, rr[1], rr[2]))
					if dc.count > 0 do (qsort dc tos_skByD; a = dc[1]; b = if dc.count > 1 then dc[2] else undefined)
				)
				if cloakV[v] and b != undefined and not (matchPattern secB[b[1]].name pattern:"Bone_cloak_*") do b = undefined
				local ws = #(#(secB[a[1]], 1.0 / (a[2] * a[2] + 0.01)))
				if b != undefined and b[2] < a[2] * 1.5 do append ws #(secB[b[1]], 1.0 / (b[2] * b[2] + 0.01))
				local sw = tos_skNormTop ws
				-- 줄 첫 마디 위쪽 절반은 몸 웨이트와 섞어 이음매를 부드럽게
				local first = secB[a[1]].parent != undefined and (matchPattern secB[a[1]].parent.name pattern:"*_All" or matchPattern secB[a[1]].parent.name pattern:"*_all")
				-- 어깨·팔을 덮는 메쉬 = 허리(Pelvis) 위에서 끝나는 세컨더리 조각(어깨 망토·털 단)의 어깨 관절 바깥(위팔 쪽) 정점:
				--   그쪽 Clavicle 에 붙은 어깨 본 줄이 있으면(옆 줄 4개 등) → 가까운 어깨 본(Bone_Spine2_*) 2개로 (망토 본에 잡혔어도)
				--   없으면(옆 줄 2개 등, 어깨 위에 어깨 본이 없음) → 팔 트위스트로: Clavicle → Clavicle Twist (t 0 → 0.15) → Clavicle Twist 2 (t 0.15 → 0.5)
				--   위팔 축 위치 t: -0.1 → 0, 0.25 → 1 로 점점, 0.9 → 1.1 에서 다시 0 (팔꿈치 넘어는 그대로) / 위팔 축에서 위팔 길이의 1.4배 넘게 떨어지면 줄임 (2.0배에서 0). 긴 망토·치마 조각은 그대로
				local armK = 0.0, armT = undefined
				if upEl[v] do (
					local p = getVert tm v
					local ai = if p.x > cxy.x then armInfo[1] else armInfo[2]
					if ai != undefined do (
						local t = (dot (p - ai[3]) ai[4]) / ai[5]
						local rad = length ((p - ai[3]) - ai[4] * (t * ai[5]))
						armK = (amax 0.0 (amin 1.0 ((t + 0.1) / 0.35))) * (amax 0.0 (amin 1.0 ((1.1 - t) / 0.2))) * (amax 0.0 (amin 1.0 ((2.0 - rad / ai[5]) / 0.6)))
						-- TOS: 팔보다 몸통(Pelvis~Neck 축)에 가까운 정점은 빼기 (팔을 내린 바인드 자세에서 허리 뒤가 팔 쪽으로 잡히던 것). 팔 쪽이 0.25L 더 가까워야 다 줌
						if armK > 0 do (
							local dArm = (tos_skSeg p ai[3] (ai[3] + ai[4] * ai[5]))[1], dTor = (tos_skSeg p torsoA torsoB)[1]
							armK *= amax 0.0 (amin 1.0 ((dTor - dArm) / (0.25 * ai[5])))
						)
						if armK > 0 do (
							if ai[8] then (
								local dsp = for i in spAll collect #(i, (tos_skSeg p secS[i][1] secS[i][2])[1])
								if dsp.count > 0 do (
									qsort dsp tos_skByD
									local ws2 = #(#(secB[dsp[1][1]], 1.0 / (dsp[1][2] * dsp[1][2] + 0.01)))
									if dsp.count > 1 and dsp[2][2] < dsp[1][2] * 1.5 do append ws2 #(secB[dsp[2][1]], 1.0 / (dsp[2][2] * dsp[2][2] + 0.01))
									armT = tos_skNormTop ws2
								)
							) else (
								local c = amax 0.0 (amin 1.0 (t / 0.15))
								local u = amax 0.0 (amin 1.0 ((t - 0.15) / 0.35))
								local t1 = if ai[6] != undefined then ai[6] else ai[1]
								local t2 = if ai[7] != undefined then ai[7] else ai[1]
								armT = #(#(ai[2], 1.0 - c), #(t1, c * (1.0 - u)), #(t2, c * u))
							)
						)
					)
				)
				if first and a[3] < 0.5 then (
					local k = a[3] * 2.0
					local mix = for e in sw collect #(e[1], e[2] * k)
					for e in W[v] do append mix #((tos_skTorso e[1] pre), e[2] * (1.0 - k))
					W[v] = tos_skNormTop mix
				) else W[v] = sw
				if armK > 0 and armT != undefined do (
					local mix = for e in W[v] collect #(e[1], e[2] * (1.0 - armK))
					for e in armT where e[2] > 0 do append mix #(e[1], e[2] * armK)
					W[v] = tos_skNormTop mix
					nArm += 1
				)
			)
			nSec = isSec.numberSet
			secAll = isSec
			upAll = upEl
			upBigAll = upBig
		)
		-- 2-a) 몸 웨이트 고르기: 이웃 정점과 2번 섞음 (다른 레퍼런스에서 온 웨이트가 이웃끼리 크게 다르면 늘어나므로). 망토·치마 정점은 빼고
		local nbr = for v = 1 to nv collect #()
		for f = 1 to tm.numfaces do (
			local fc = getFace tm f
			local a = fc.x as integer, b = fc.y as integer, c = fc.z as integer
			appendIfUnique nbr[a] b; appendIfUnique nbr[a] c
			appendIfUnique nbr[b] a; appendIfUnique nbr[b] c
			appendIfUnique nbr[c] a; appendIfUnique nbr[c] b
		)
		for it = 1 to 2 do (
			local W2 = #()
			W2.count = nv
			for v = 1 to nv do (
				tos_skProg (0.6 + 0.075 * (it - 1)) (0.6 + 0.075 * it) v nv
				if secAll[v] or nbr[v].count == 0 then W2[v] = W[v]
				else (
					local acc = for e in W[v] collect #(e[1], e[2])
					local k = 0
					for u in nbr[v] where not secAll[u] do k += 1
					if k > 0 do for u in nbr[v] where not secAll[u] do for e in W[u] do append acc #(e[1], e[2] / k)
					W2[v] = tos_skNormTop acc
				)
			)
			W = W2
		)
		-- 2-a') 허리~가슴 척추 비율을 레퍼런스 40벌 평균으로 (Spine1 이 약하던 것)
		local nSpine = tos_skSpineFix W tm secAll pre g
		-- 2-b) 작은 장식 조각(버클·방울·고리 등)은 통째로 한 웨이트 (레퍼런스가 섞여 늘어나지 않게)
		local nRigid = 0, rigidSets = #()
		local faces2 = #{1..tm.numfaces}
		while not faces2.isEmpty do (
			local f0 = (faces2 as array)[1]
			local el = meshop.getElementsUsingFace tm #{f0}
			faces2 -= el
			local vs = meshop.getVertsUsingFace tm el
			-- 관절(무릎·발목·팔꿈치·손목)을 가로지르는 조각(스타킹·소매 등)은 통째로 하지 않음
			if vs.numberSet < (amax 30 (nv * 0.02)) and (vs * secAll).isEmpty and not (tos_skCrossJoint vs tm pre) do (
				local acc = #()
				for v in vs do for e in W[v] do append acc e
				local avg = tos_skNormTop acc
				for v in vs do W[v] = avg
				nRigid += 1
				append rigidSets vs
			)
		)
		-- 2-c) 허벅지: Pelvis·ThighTwist·Thigh·Calf 비율을 monk_m_shenji01 처럼 (허벅지 윗부분은 ThighTwist 가 받게).
		--      작은 조각 통째로 다음에 함: 바지 조각이 통째로 한 웨이트가 되면 허벅지를 들 때 늘어나므로
		-- TOS: 관절 부위 웨이트를 레퍼런스에서 배운 값으로 (tos_joint.ms · tos_joint_<m|f>.ms). 없으면 예전 비율표
		local nLeg = 0, nJoint = -1
		if tosjt_apply == undefined do try (fileIn (TosRig.sbgDir() + "tos_joint.ms")) catch ()
		local jdF = TosRig.dataFile ("tos_joint_" + (g as string) + ".ms")
		if tosjt_apply != undefined and (doesFileExist jdF) and tos_skJointOff != true do (
			if (if g == #m then TOS_JointData_m else TOS_JointData_f) == undefined do try (fileIn jdF) catch ()
			-- 작은 조각도 관절 값으로 고친 뒤 조각마다 다시 평균 (팔 위 어깨 장식이 가슴 웨이트로 통째로 남던 것)
			--   새 값은 몸통(Pelvis·Spine·Neck·Head) 몫이 0.2 넘게 팔·다리 쪽으로 옮겨진 조각만 받음. 아니면 예전 평균 그대로 (장갑·부츠 장식 등은 가까운 레퍼런스 값이 더 맞음)
			local skipJ = copy secAll
			skipJ.count = tm.numverts
			local rigOld = for vs in rigidSets collect W[(vs as array)[1]]
			nJoint = try (tosjt_apply W tm skipJ pre g) catch -1
			if nJoint >= 0 do for ri = 1 to rigidSets.count do (
				local vs = rigidSets[ri]
				local acc = #()
				for v in vs do for e in W[v] do append acc e
				local avg = tos_skNormTop acc
				local tOld = 0.0, tNew = 0.0
				for e in rigOld[ri] where (matchPattern e[1].name pattern:"*Spine*" or matchPattern e[1].name pattern:"*Pelvis" or matchPattern e[1].name pattern:"*Neck" or matchPattern e[1].name pattern:"*Head") do tOld += e[2]
				for e in avg where (matchPattern e[1].name pattern:"*Spine*" or matchPattern e[1].name pattern:"*Pelvis" or matchPattern e[1].name pattern:"*Neck" or matchPattern e[1].name pattern:"*Head") do tNew += e[2]
				local use = if (tOld - tNew) > 0.2 then avg else rigOld[ri]
				for v in vs do W[v] = use
			)
		)
		if nJoint < 0 do nLeg = tos_skLegFix W tm secAll pre
		-- 2-c') 어깨 본이 있으면 어깨를 덮는 몸 쪽 조각도 어깨 본으로 (어깨 바깥은 옆 줄 4개 등 Clavicle 에 줄이 있을 때, 큰 조각의 등·앞 줄 근처는 늘):
		--   허리(Pelvis) 위에서 끝나는 따로 떨어진 조각(어깨 망토·견장, 세컨더리 판정에 안 걸린 것)의 어깨 관절 바깥(위팔 쪽) 정점 → 가까운 어깨 본(Bone_Spine2_*) 2개
		--   (위 세컨더리 정점의 어깨·팔 덮는 규칙과 같은 범위: 위팔 축 t -0.1 → 0.25 에서 점점, 팔꿈치 0.9~1.1 에서 다시 0, 축에서 위팔 길이 1.4~2.0 배에서 줄임, 몸통 축에 더 가까우면 뺌)
		--   깃처럼 목 쪽에 있는 조각은 위팔 축 t 가 -0.1 아래라 그대로 몸 (catagnan_cat01 깃 56·72)
		--   관절 학습 다음에 함 (학습값이 팔 관절 둘레 본 밖의 웨이트를 빼므로)
		if spAll.count > 0 do for v in upAll where not secAll[v] do (
			local p = getVert tm v
			local ai = if p.x > cxy.x then armInfo[1] else armInfo[2]
			-- 위팔 축 범위(어깨 바깥)는 그쪽 Clavicle 에 붙은 어깨 줄이 있을 때만 (옆 줄 2개처럼 어깨 위 줄이 없으면 그 부분은 몸 웨이트·관절 학습의 팔 트위스트 그대로)
			--   아래 큰 조각 거리 규칙은 줄 수와 상관없이 (옆 줄 2개여도 등·앞 줄은 있음)
			local armK = 0.0
			if ai != undefined and ai[8] do (
				local t = (dot (p - ai[3]) ai[4]) / ai[5]
				local rad = length ((p - ai[3]) - ai[4] * (t * ai[5]))
				armK = (amax 0.0 (amin 1.0 ((t + 0.1) / 0.35))) * (amax 0.0 (amin 1.0 ((1.1 - t) / 0.2))) * (amax 0.0 (amin 1.0 ((2.0 - rad / ai[5]) / 0.6)))
			)
			if armK > 0 do (
				local dArm = (tos_skSeg p ai[3] (ai[3] + ai[4] * ai[5]))[1], dTor = (tos_skSeg p torsoA torsoB)[1]
				armK *= amax 0.0 (amin 1.0 ((dTor - dArm) / (0.25 * ai[5])))
			)
			local dsp = for i in spAll collect #(i, (tos_skSeg p secS[i][1] secS[i][2])[1])
			qsort dsp tos_skByD
			-- 어깨 망토처럼 큰 조각(정점 100개 이상)은 등·앞 줄 어깨 본에도: 어깨 본까지 거리가 몸 뼈까지의 0.5 배 안이면 다, 1.0 배에서 0
			--   (등 쪽 줄은 Clavicle 이 아니라 Bone_Spine2_Base 아래라 위팔 축 범위 밖. 어깨 본을 망토 메쉬 표면에 맞춰 두므로 망토 정점은 어깨 본에 훨씬 가까움)
			if upBigAll[v] do (
				local dB = 1e9
				for s in bodyS do (local d = (tos_skSeg p s[1] s[2])[1]; if d < dB do dB = d)
				local kP = amax 0.0 (amin 1.0 ((1.0 - dsp[1][2] / (amax 0.01 dB)) / 0.5))
				armK = amax armK kP
			)
			if armK <= 0 do continue
			local ws2 = #(#(secB[dsp[1][1]], 1.0 / (dsp[1][2] * dsp[1][2] + 0.01)))
			if dsp.count > 1 and dsp[2][2] < dsp[1][2] * 1.5 do append ws2 #(secB[dsp[2][1]], 1.0 / (dsp[2][2] * dsp[2][2] + 0.01))
			local armT = tos_skNormTop ws2
			local mix = for e in W[v] collect #(e[1], e[2] * (1.0 - armK))
			for e in armT where e[2] > 0 do append mix #(e[1], e[2] * armK)
			W[v] = tos_skNormTop mix
			nArm += 1
		)
		-- 2-d) 무릎 아래 작은 조각(부츠 털 단·끈 등)은 Calf 로만 (허벅지 몫이 섞이면 무릎을 굽힐 때 떠 버림)
		local nKnee = tos_skKneeRigid W tm rigidSets pre
		free tm
		-- 3) Skin 넣기 (예전 Skin 은 꺼진 채 두고, 새 Skin 을 다 쓴 뒤에 지움 → 중간에 취소해도 예전 그대로)
		tos_skProg 0.75 0.8 1 1
		local oldSk = for md in m.modifiers where classOf md == Skin collect md
		local used = #()
		for v = 1 to nv do for e in W[v] do appendIfUnique used e[1]
		local sk = Skin name:"TOS_SkinNew"
		addModifier m sk
		max modify mode
		select m
		modPanel.setCurrentObject sk
		sk.bone_Limit = 4
		for i = 1 to used.count do skinOps.addBone sk used[i] (if i == used.count then 1 else 0)
		-- 새 Skin 이 정점을 알게 (평가 전이면 정점 수 0)
		sliderTime = sliderTime
		classOf m
		completeRedraw()
		local skv = skinOps.GetNumberVertices sk
		if skv < nv do (modPanel.setCurrentObject sk; completeRedraw(); skv = skinOps.GetNumberVertices sk)
		if skv < nv do (enableSceneRedraw(); throw ("Skin 이 정점을 못 읽었어요 (" + (skv as string) + "/" + (nv as string) + ")"))
		local idOf = dotNetObject "System.Collections.Hashtable"
		-- 이름 → 본 ID (GetBoneName·ReplaceVertexWeights 모두 본 ID = 넣은 순서, Max 2016 에서 확인)
		for i = 1 to (skinOps.GetNumberBones sk) do idOf.Add (skinOps.GetBoneName sk i 0) i
		disableSceneRedraw()
		try (
			for v = 1 to nv do (
				tos_skProg 0.8 1.0 v nv
				local ids = for e in W[v] collect idOf.Item[e[1].name]
				local ws = for e in W[v] collect e[2]
				if ids.count > 0 do (
					-- Max 2016: ReplaceVertexWeights 가 이미 있던 영향(엔벨로프 등)을 남기므로 먼저 0 으로
					local cnt = skinOps.GetVertexWeightCount sk v
					if cnt > 0 do (
						local cur = for j = 1 to cnt collect (skinOps.GetVertexWeightBoneID sk v j)
						skinOps.unNormalizeVertex sk v true
						skinOps.SetVertexWeights sk v cur (for c in cur collect 0.0)
					)
					skinOps.ReplaceVertexWeights sk v ids ws
					skinOps.unNormalizeVertex sk v false
				)
			)
		) catch (enableSceneRedraw(); throw())
		try (skinOps.RemoveZeroWeights sk) catch ()
		for md in oldSk do deleteModifier m md
		sk.name = "Skin"
		enableSceneRedraw()
		log += m.name + ": 정점 " + (nv as string) + " · 본 " + (used.count as string) + " · 세컨더리(망토·치마) 정점 " + (nSec as string) + " · 통째로 움직이는 작은 조각 " + (nRigid as string) + (if nJoint >= 0 then (" · 관절 부위 레퍼런스 학습값으로 맞춘 정점 " + (nJoint as string)) else (" · 허벅지 비율 맞춘 정점 " + (nLeg as string))) +" · 허리~가슴 척추 비율 맞춘 정점 " + (nSpine as string) + " · 무릎 아래 조각 Calf 로 " + (nKnee as string) + " · 어깨·팔 덮는 정점(어깨 본 또는 팔 트위스트로) " + (nArm as string) + "\n"
	)
	bip.controller.figureMode = wasFig
	completeRedraw()
	"스킨 적용 (레퍼런스 웨이트, " + (TosRig.genderText g) + ") " + (((timeStamp() - t0) / 1000.0) as string) + "초\n" + log + \
		"몸 = 레퍼런스 코스튬 웨이트 (" + (filenameFromPath (tos_skDBFile g)) + "), 망토·치마 = 이 캐릭터의 세컨더리 본\n다시 누르면 예전 스킨을 지우고 새로 계산해요."
)
format "[tos_skin] loaded\n"
