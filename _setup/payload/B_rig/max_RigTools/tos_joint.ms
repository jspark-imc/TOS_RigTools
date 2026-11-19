-- ======================================================================
--  TOS_RigTools - 5. 스킨: 관절 부위 웨이트 학습 (TOS 레퍼런스 ani\Character\PC 의 스킨에서)
--  관절마다 (관절 축 위치 t × 축 둘레 방향 8칸) 칸에서 관절 둘레 본들의 웨이트 비율 평균을 배워 두고
--  [스킨 적용] 때 몸 정점(세컨더리·작은 장식 조각 제외)의 그 본들 몫을 배운 비율로 다시 나눔
--  관절: 엉덩이·무릎·발목·어깨·팔꿈치·손목 (L·R), 허리, 목
--  데이터: tos_joint_m.ms · tos_joint_f.ms (global TOS_JointData_m / _f)
--  학습: tosjt_make <PC 폴더> <저장 폴더> <#m|#f> [perJob] - 직업 폴더마다 스킨 있는 _set.max 를 고르게 perJob 개
-- ======================================================================
global TOS_JointData_m, TOS_JointData_f
global tos_skSeg, tos_skNormTop   -- tos_skin.ms 에서 정의 (이 파일을 먼저 읽어도 찾게 미리 선언. 안 하면 "Call needs function ... undefined")
global tosjt_nA = 8   -- 방향 칸 수
global tosjt_mix = 1.0   -- 적용 때 배운 값 몫 (나머지 = 몸 웨이트 모음에서 온 값). 관절별 값은 아래
global tosjt_mixOf = #()   -- 관절별 몫 #(#("knee", 0.5) ...). 시험(vulture·bunnygambler)에서 모두 1.0 이 가장 나아서 비워 둠
global tosjt_skipJoints = #("neck")   -- 배워 두지만 적용하지 않는 관절 (목: 정점이 적고 옷마다 달라 시험에서 나빠짐)

-- 관절 정의: #(이름, 쪽("L"/"R"/""), 자식 뼈(축 시작), 축 끝 뼈, 본 묶음, t 최소, t 최대, t 칸 크기, 축 거리 한계(자식 뼈 길이 배))
--   본 이름은 "Bip01 " 뒤 이름. "@" 는 쪽 (L/R) 으로 바뀜. 트위스트 뼈 이름은 Biped 그대로 (LThighTwist, L ForeTwist)
fn tosjt_defs = #(
	#("hip",      "@", "@ Thigh",    "@ Calf",    #("Pelvis", "@ Thigh", "@ThighTwist"),                   -0.2, 0.9, 0.1, 0.9),
	-- 무릎~종아리 아래(발목 바로 위)까지: 종아리 축 t 1.1 까지 (발목 위 높이로 Calf·Foot 를 나눔). 발은 아래 발목 표 (발 축)
	#("knee",     "@", "@ Calf",     "@ Foot",    #("@ Thigh", "@ThighTwist", "@ Calf", "@ Foot"),          -0.5, 1.1, 0.1, 0.8),
	#("ankle",    "@", "@ Foot",     "@ Toe0",    #("@ Calf", "@ Foot", "@ Toe0"),                          -0.8, 1.2, 0.2, 1.2),
	#("shoulder", "@", "@ UpperArm", "@ Forearm", #("Spine2", "Neck", "@ Clavicle", "@ Clavicle Twist", "@ Clavicle Twist 2", "@ UpperArm"), -0.7, 0.8, 0.1, 0.9),
	#("elbow",    "@", "@ Forearm",  "@ Hand",    #("@ UpperArm", "@ Clavicle Twist 2", "@ Forearm", "@ ForeTwist", "@ Hand"), -0.5, 1.0, 0.1, 0.8),
	#("wrist",    "@", "@ Hand",     "@ Finger2", #("@ Forearm", "@ ForeTwist", "@ Hand"),                  -1.0, 0.8, 0.2, 1.2),
	#("neck",     "",  "Neck",       "Head",      #("Spine2", "Neck", "Head", "L Clavicle", "R Clavicle"),   -1.5, 2.0, 0.25, 2.5)
)
-- 허리(Pelvis~Spine2)는 관절 표를 쓰지 않음: 옷마다(코트·치마·몸에 붙는 옷) 너무 달라 평균이 흐려짐 → 몸 웨이트 모음(가까운 레퍼런스) 그대로
-- 쪽마다 펼친 관절 목록: #(정의, 쪽, 본 이름 배열(Bip01 뒤))
fn tosjt_list = (
	local out = #()
	for d in tosjt_defs() do (
		local sides = if d[2] == "@" then #("L", "R") else #("")
		for sd in sides do (
			local bn = for b in d[5] collect (substituteString b "@" sd)
			append out #(d, sd, bn, (substituteString d[3] "@" sd), (substituteString d[4] "@" sd))
		)
	)
	out
)
-- 관절 좌표: #(관절 위치, 축 방향, 길이, 앞 기준, 옆 기준) (지금 장면, Biped 접두어 pre)
fn tosjt_frame pre j = (
	local a = getNodeByName (pre + " " + j[4]) exact:true, b = getNodeByName (pre + " " + j[5]) exact:true
	if a == undefined or b == undefined do return undefined
	local p0 = a.transform.pos, ax = normalize (b.transform.pos - p0), L = distance p0 b.transform.pos
	if L < 0.01 do return undefined
	local refV = if (abs (dot ax [0, 1, 0])) > 0.7 then [0, 0, 1] else [0, -1, 0]
	local f = normalize (refV - ax * (dot refV ax))
	local s = cross ax f
	if j[2] == "R" do s = -s   -- 좌우 거울: 바깥쪽이 같은 칸
	#(p0, ax, L, f, s)
)
-- 정점 p 의 (t, 방향 칸 0~nA-1 소수, 축 거리/L) 또는 undefined
fn tosjt_coord fr p = (
	local d = p - fr[1]
	local t = (dot d fr[2]) / fr[3]
	local r = d - fr[2] * (t * fr[3])
	local rl = length r
	local ang = if rl < 1e-5 then 0.0 else (atan2 (dot r fr[5]) (dot r fr[4]))
	if ang < 0 do ang += 360.0
	#(t, ang / (360.0 / tosjt_nA), rl / fr[3])
)
-- 정점이 쓸 관절: t 범위·축 거리 안인 관절 중 관절 위치에 가장 가까운 것. 반환 #(관절 번호, 좌표) 또는 undefined
fn tosjt_pick js frs p = (
	local best = undefined, bd = 1e9
	for i = 1 to js.count where frs[i] != undefined do (
		local d = js[i][1], c = tosjt_coord frs[i] p
		if c[1] >= d[6] and c[1] <= d[7] and c[3] <= d[9] do (
			local dist = distance p frs[i][1]
			if dist < bd do (bd = dist; best = #(i, c))
		)
	)
	best
)

-- ---------------------------------------------------------------- 학습
-- acc: 관절마다 표 [t 칸][방향 칸] = #(본마다 합..., 정점 수)
fn tosjt_newAcc js = (
	for j in js collect (
		local d = j[1], nT = ((ceil ((d[7] - d[6]) / d[8] - 0.001)) as integer)
		for ti = 1 to nT collect (for ai = 1 to tosjt_nA collect (for k = 1 to (j[3].count + 1) collect 0.0))
	)
)
fn tosjt_learnScene acc js = (
	local bip = (for o in objects where classOf o == Biped_Object and o.parent == undefined collect o)
	if bip.count == 0 do return 0
	bip[1].controller.figureMode = true
	local pre = bip[1].name
	local frs = for j in js collect (tosjt_frame pre j)
	local segs = tosjt_segs pre
	local n = 0
	max modify mode
	for m in objects where superClassOf m == GeometryClass and classOf m != Biped_Object and classOf m != BoneGeometry and m.modifiers[#Skin] != undefined do (
		local sk = m.modifiers[#Skin]
		select m; modPanel.setCurrentObject sk
		sk.enabled = false; local tm = snapshotAsMesh m; sk.enabled = true
		local nb = skinOps.GetNumberBones sk
		-- 이름 맞추기: "Clavicle Twist2" = "Clavicle Twist 2" (레퍼런스마다 띄어쓰기가 다름)
		local bnames = for i = 1 to nb collect (local s = skinOps.GetBoneName sk i 0; s = substituteString s "Twist2" "Twist 2"; if matchPattern s pattern:(pre + " *") then (substring s (pre.count + 2) -1) else ("#" + s))
		for v = 1 to (amin tm.numverts (skinOps.GetNumberVertices sk)) do (
			local p = getVert tm v
			-- 적용 때와 같게: 팔·다리 정점은 가장 가까운 뼈로 관절을 고름 (종아리 = 무릎 표 …)
			local pk = undefined
			local ns = tosjt_nearSeg segs p
			local lj = if ns != undefined then (tosjt_limbJoint ns[1] ns[3]) else undefined
			if lj != undefined do for q = 1 to js.count while pk == undefined do if js[q][1][1] == lj and js[q][2] == ns[2] and frs[q] != undefined do (
				local cq = tosjt_coord frs[q] p, dq = js[q][1]
				if cq[1] >= dq[6] and cq[1] < dq[7] and cq[3] <= dq[9] * 1.5 do pk = #(q, cq)
			)
			if pk == undefined do pk = tosjt_pick js frs p
			if pk == undefined do continue
			local j = js[pk[1]], c = pk[2], d = j[1]
			local sh = for k = 1 to j[3].count collect 0.0
			local tot = 0.0, all = 0.0
			for q = 1 to (skinOps.GetVertexWeightCount sk v) do (
				local w = skinOps.GetVertexWeight sk v q, nm = bnames[skinOps.GetVertexWeightBoneID sk v q]
				all += w
				local k = findItem j[3] nm
				if k > 0 do (sh[k] += w; tot += w)
			)
			-- 몸 정점만 (관절 본들이 80% 넘게 받는 정점)
			if all < 1e-4 or tot / all < 0.8 do continue
			local ti = ((floor ((c[1] - d[6]) / d[8])) as integer) + 1, ai = ((mod ((floor c[2]) as integer) tosjt_nA) as integer) + 1
			local cell = acc[pk[1]][amin ti acc[pk[1]].count][ai]
			for k = 1 to sh.count do cell[k] += sh[k] / tot
			cell[sh.count + 1] += 1
			n += 1
		)
		free tm
	)
	clearSelection()
	n
)
-- 직업 폴더마다 스킨 있는 _set.max 를 이름 순으로 고르게 perJob 개
fn tosjt_files pcDir g perJob = (
	local out = #()
	for jd in getDirectories (pcDir + "*_" + (g as string)) do (
		local fs = #()
		for d in getDirectories (jd + "costume\\*") do join fs (getFiles (d + "*_set.max"))
		sort fs
		if fs.count > 0 do (
			local k = amin perJob fs.count
			for i = 1 to k do append out fs[(floor ((i - 0.5) * fs.count / k)) as integer + 1]
		)
	)
	out
)
fn tosjt_make pcDir outDir g perJob:10 = (
	pcDir = (trimRight pcDir "\\") + "\\"
	outDir = (trimRight outDir "\\") + "\\"
	local js = tosjt_list()
	local acc = tosjt_newAcc js
	local used = 0, nv = 0
	for f in (tosjt_files pcDir g perJob) do (
		local ok = try (loadMaxFile f useFileUnits:true quiet:true) catch false
		if ok do (local n = try (tosjt_learnScene acc js) catch 0; if n > 0 do (used += 1; nv += n))
	)
	if used == 0 do return ("주의: " + (g as string) + " 관절 학습용 스킨 레퍼런스가 없어요")
	-- 평균으로 바꿔 저장: 관절마다 #(이름, 쪽, 본 이름들, 표[t][방향] = #(비율..., 정점 수))
	local fs = stringStream ""
	format "-- TOS_RigTools 5. 스킨 관절 부위 웨이트 (tos_joint.ms 로 학습 %, 레퍼런스 % 개, 정점 %)\n" (trts_stamp()) used nv to:fs
	format "global TOS_JointData_% = #(\n" (g as string) to:fs
	for i = 1 to js.count do (
		local j = js[i]
		local tab = for row in acc[i] collect (for cell in row collect (
			local c = cell[cell.count]
			if c < 1 then #(0) else (append (for k = 1 to cell.count - 1 collect ((floor (cell[k] / c * 1000.0 + 0.5)) / 1000.0)) c)
		))
		format "\t#(%, %, %, %)%\n" (trts_txt j[1][1]) (trts_txt j[2]) (trts_txt j[3]) (trts_txt tab) (if i < js.count then "," else "") to:fs
	)
	format ")\n" to:fs
	(dotNetClass "System.IO.File").WriteAllText (outDir + "tos_joint_" + (g as string) + ".ms") (fs as string) (dotNetObject "System.Text.UTF8Encoding" true)
	"tos_joint_" + (g as string) + ".ms: 레퍼런스 " + (used as string) + "개, 관절 정점 " + (nv as string) + "개"
)

-- ---------------------------------------------------------------- 적용
-- 표 값: t·방향 사이를 섞음 (정점 수 3 미만 칸은 빼고). 반환: 비율 배열 또는 undefined
fn tosjt_lookup tab d c nb = (
	local tf = (c[1] - d[6]) / d[8] - 0.5, af = c[2] - 0.5
	local t0 = (floor tf) as integer, a0 = (floor af) as integer
	local kt = tf - t0, ka = af - a0
	local sum = for k = 1 to nb collect 0.0, ws = 0.0
	for dt = 0 to 1 do for da = 0 to 1 do (
		local ti = amax 1 (amin tab.count (t0 + dt + 1))
		local ai = ((mod (a0 + da + tosjt_nA) tosjt_nA) as integer) + 1
		local cell = tab[ti][ai]
		if cell.count > 1 and cell[cell.count] >= 3 do (
			local w = (if dt == 0 then 1 - kt else kt) * (if da == 0 then 1 - ka else ka)
			for k = 1 to nb do sum[k] += cell[k] * w
			ws += w
		)
	)
	if ws < 0.3 then undefined else (for k = 1 to nb collect sum[k] / ws)
)
-- 몸 뼈 선분: #(종류, 쪽, 시작, 끝). 종류 torso·clav·ua·fa·hand·thigh·calf·foot
fn tosjt_segs pre = (
	local out = #()
	local chain = #("Pelvis", "Spine", "Spine1", "Spine2", "Neck", "Head")
	for i = 1 to chain.count - 1 do (
		local a = getNodeByName (pre + " " + chain[i]) exact:true, b = getNodeByName (pre + " " + chain[i + 1]) exact:true
		if a != undefined and b != undefined do append out #("torso", "", a.transform.pos, b.transform.pos)
	)
	for sd in #("L", "R") do (
		local lst = #(#("clav", "Clavicle", "UpperArm"), #("ua", "UpperArm", "Forearm"), #("fa", "Forearm", "Hand"), #("hand", "Hand", "Finger2"), #("thigh", "Thigh", "Calf"), #("calf", "Calf", "Foot"), #("foot", "Foot", "Toe0"))
		for x in lst do (
			local a = getNodeByName (pre + " " + sd + " " + x[2]) exact:true, b = getNodeByName (pre + " " + sd + " " + x[3]) exact:true
			if a != undefined and b != undefined do append out #(x[1], sd, a.transform.pos, b.transform.pos)
		)
	)
	out
)
-- 정점이 가장 가까운 몸 뼈 선분: #(종류, 쪽, 선분 위 t, 거리, 선분 길이)
fn tosjt_nearSeg segs p = (
	local best = undefined, bd = 1e9
	for s in segs do (
		local r = tos_skSeg p s[3] s[4]
		if r[1] < bd do (bd = r[1]; best = #(s[1], s[2], r[2], r[1], (distance s[3] s[4])))
	)
	best
)
-- 팔·다리 정점이면 쓸 관절 이름 (뼈 선분 위 위치로): 위팔 앞쪽 절반 = 어깨, 뒤쪽 = 팔꿈치 …
fn tosjt_limbJoint k t = (
	if k == "ua" then (if t < 0.5 then "shoulder" else "elbow")
	else if k == "fa" then (if t < 0.6 then "elbow" else "wrist")
	else if k == "thigh" then (if t < 0.55 then "hip" else "knee")
	else if k == "calf" then "knee"
	else if k == "foot" then "ankle"
	else undefined
)
-- W: 정점 웨이트 #(#(node, w)...). skip: 건드리지 않을 정점 (세컨더리·작은 조각). 반환: 고친 정점 수
--   팔·다리 정점(가장 가까운 몸 뼈가 위팔·아래팔·손·허벅지·종아리·발)은 뼈에서 멀어도(두꺼운 옷·탈 같은 옷) 그 관절의 배운 값으로 웨이트 전부를 정함
--   (몸 웨이트 모음은 위치로 옮겨서, 팔이 두꺼우면 가슴(Spine2) 웨이트가 섞여 팔을 들어도 따라오지 않던 것). 팔 정점에는 Spine2·Neck 몫을 주지 않음 (어깨 바로 옆 제외)
fn tosjt_apply W tm skip pre g = (
	local data = if g == #m then TOS_JointData_m else TOS_JointData_f
	if data == undefined do return 0
	local js = tosjt_list()
	local frs = for j in js collect (tosjt_frame pre j)
	local nodes = for j in js collect (for b in j[3] collect (getNodeByName (pre + " " + b) exact:true))
	-- 장면에 없는 본(예: 트위스트 뼈 없음)의 몫은 묶음의 앞 본 쪽으로: 허벅지 트위스트 → Thigh, 아래팔 트위스트 → Forearm
	local segs = tosjt_segs pre
	-- 어깨 옆 판정용: 좌우 어깨 관절(UpperArm 시작) 위치, Spine2 높이, 몸 가운데
	local uaL = getNodeByName (pre + " L UpperArm") exact:true, uaR = getNodeByName (pre + " R UpperArm") exact:true
	local sp2 = getNodeByName (pre + " Spine2") exact:true
	local cx = if sp2 != undefined then sp2.transform.pos.x else 0.0, sp2z = if sp2 != undefined then sp2.transform.pos.z else 0.0
	local n = 0
	for v = 1 to tm.numverts where not skip[v] do (
		local p = getVert tm v
		-- 팔·다리 정점인가
		local ns = tosjt_nearSeg segs p, limb = false, pk = undefined
		-- 몸통 선에 가깝게 잡혔어도 어깨 높이에서 어깨 관절보다 바깥이면 어깨(위팔 시작)로 (두꺼운 어깨 장식·탈)
		if ns != undefined and (ns[1] == "torso" or ns[1] == "clav") and uaL != undefined and uaR != undefined and p.z > sp2z do (
			local ua = if p.x > cx then uaL else uaR
			if (abs (p.x - cx)) > (abs (ua.transform.pos.x - cx)) * 0.85 do ns = #("ua", (if p.x > cx then "L" else "R"), 0.0, ns[4], ns[5])
		)
		local lj = if ns != undefined then (tosjt_limbJoint ns[1] ns[3]) else undefined
		-- 보통 길(관절 둘레 범위 안 + 관절 본 몫 절반 이상)로 되는 정점은 그대로 보통 길로. 안 되는 팔·다리 정점만 팔·다리 길로
		--   팔(위팔 시작 0.25 넘어·아래팔)은 늘 팔 길로: 가슴(Spine2) 웨이트가 섞이면 팔을 들어도 안 따라옴
		--   종아리도 늘 종아리 축(무릎 표)으로: 관절 위치로 고르면 발목 위가 발 축 표로 가서 Foot 몫이 커짐 (부츠가 늘어남)
		--   허벅지(엉덩이 관절 0.15 아래)도: 몸 웨이트 모음의 Spine 이 다리에 남으면(치마 옷 레퍼런스에서 옴) 골반·다리가 덜 따라옴
		local armV = ns != undefined and ((ns[1] == "ua" and ns[3] > 0.25) or ns[1] == "fa" or ns[1] == "calf" or (ns[1] == "thigh" and ns[3] > 0.15))
		-- 몸통 옆 정점은 팔로 보지 않음: 팔을 내린 바인드 자세에서 허리·등 옆이 몸통 축보다 위팔·아래팔 축에 더 가까움
		--   몸 웨이트에서 척추(Pelvis·Spine·Spine1·Spine2) 몫 0.6 이상 + 허리 쪽(Pelvis·Spine·Spine1) 몫 0.2 이상이면 그대로 (catagnan_cat01 등 옆 허리 Spine1 0.23 → 레퍼런스 0.59)
		--   (겨드랑이는 Spine1 몫이 거의 없어 그대로 팔 값)
		if ns != undefined and (ns[1] == "ua" or ns[1] == "fa" or ns[1] == "hand") do (
			local aw = 0.0, cw = 0.0, lw = 0.0
			for e in W[v] do (
				aw += e[2]
				local nmE = e[1].name
				local isL = matchPattern nmE pattern:"* Pelvis" or matchPattern nmE pattern:"* Spine" or matchPattern nmE pattern:"* Spine1"
				if isL do lw += e[2]
				if isL or matchPattern nmE pattern:"* Spine2" do cw += e[2]
			)
			if aw > 1e-4 and cw / aw >= 0.6 and lw / aw >= 0.2 do continue
		)
		local pk0 = if armV then undefined else (tosjt_pick js frs p)
		if pk0 != undefined do (
			local nd0 = nodes[pk0[1]], t0 = 0.0, a0 = 0.0
			for e in W[v] do (a0 += e[2]; if (findItem nd0 e[1]) > 0 do t0 += e[2])
			if a0 > 1e-4 and t0 / a0 >= 0.5 and (findItem tosjt_skipJoints js[pk0[1]][1][1]) == 0 do lj = undefined
		)
		if lj != undefined do (
			for q = 1 to js.count while pk == undefined do if js[q][1][1] == lj and js[q][2] == ns[2] and frs[q] != undefined do (
				local c = tosjt_coord frs[q] p, d = js[q][1]
				c[1] = amax d[6] (amin (d[7] - 0.001) c[1])
				pk = #(q, c)
			)
			if pk != undefined do limb = true
		)
		if pk == undefined do pk = tosjt_pick js frs p
		if pk == undefined do continue
		local i = pk[1], j = js[i]
		if (findItem tosjt_skipJoints j[1][1]) > 0 do continue
		local tab = undefined
		for x in data while tab == undefined do if x[1] == j[1][1] and x[2] == j[2] do tab = x[4]
		if tab == undefined do continue
		local nd = nodes[i]
		local tot = 0.0, all = 0.0
		for e in W[v] do (all += e[2]; if (findItem nd e[1]) > 0 do tot += e[2])
		if not limb and (all < 1e-4 or tot / all < 0.5) do continue
		local r = tosjt_lookup tab j[1] pk[2] nd.count
		if r == undefined do continue
		if limb do (
			-- 팔 정점: 가슴·목 몫 빼기 (위팔 시작 0.25 안쪽은 그대로). 웨이트 전부를 관절 본으로 (몸통에서 온 다른 웨이트 버림)
			local outSh = false
			if ns[1] == "ua" and uaL != undefined and uaR != undefined do (local ua = if p.x > cx then uaL else uaR; outSh = (abs (p.x - cx)) > (abs (ua.transform.pos.x - cx)))
			if (ns[1] == "ua" and (ns[3] > 0.25 or outSh)) or ns[1] == "fa" or ns[1] == "hand" do (
				for q = 1 to j[3].count where j[3][q] == "Spine2" or j[3][q] == "Neck" do r[q] = 0.0
				local s = 0.0
				for x in r do s += x
				if s > 1e-4 do r = for x in r collect x / s
			)
			W[v] = for e in W[v] where (findItem nd e[1]) > 0 collect e
			tot = 1.0
		)
		-- 배운 비율과 지금 비율(몸 웨이트 모음 = 가장 가까운 레퍼런스 옷)을 섞음: tosjt_mix = 배운 값 몫
		local k = if tosjt_mix == undefined then 1.0 else tosjt_mix
		for x in tosjt_mixOf where x[1] == j[1][1] do k = x[2]
		if k < 1.0 do (
			local cs = for b in nd collect 0.0
			for e in W[v] do (local q = findItem nd e[1]; if q > 0 do cs[q] += e[2] / tot)
			r = for q = 1 to nd.count collect (r[q] * k + cs[q] * (1.0 - k))
		)
		local mix = for e in W[v] where (findItem nd e[1]) == 0 collect e
		for k = 1 to nd.count where r[k] > 0.001 do (
			local b = nd[k]
			if b == undefined do (
				-- 없는 본 → 같은 묶음에서 이름이 비슷한 본 (LThighTwist → L Thigh, L ForeTwist → L Forearm)
				local nm = j[3][k]
				local sd = if j[2] != "" then j[2] else (substring nm 1 1)
				local alt = if matchPattern nm pattern:"*ThighTwist" then (sd + " Thigh") else if matchPattern nm pattern:"*ForeTwist" then (sd + " Forearm") else if matchPattern nm pattern:"*Clavicle Twist*" then (sd + " UpperArm") else ""
				b = getNodeByName (pre + " " + alt) exact:true
			)
			if b != undefined do append mix #(b, r[k] * tot)
		)
		W[v] = tos_skNormTop mix
		n += 1
	)
	n
)
