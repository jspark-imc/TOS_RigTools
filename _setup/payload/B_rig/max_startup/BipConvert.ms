-- BipConvert.ms v0.1 (3ds Max 2014) — FBX 애니 → .bip 변환 + Biped 축 검사
-- 사용: Max 메뉴 Claude > BipConvert (또는 MAXScript > Run Script). BipFit.ms가 같은 폴더(또는 startup)에 있어야 함
-- 흐름: FBX를 빈 장면에 불러옴 → 같은 체형의 변환용 Biped를 만들어 관절 맞춤(BipFit) → 프레임마다 굽기 → 키 정리 → .bip 저장
--       캐릭터에서는 Motion 패널 > Load File로 .bip를 불러오면 됨 (.bip는 원본 1프레임부터, 바인드 포즈 제외)
-- 팀 Biped 구조: 척추 3, 목 1, 손가락 5x3, 발가락 1x1, triangle Neck 켬, triangle Pelvis 끔 (BipFit.createBiped 기본값)
-- 만든 사람: Claude (2026-10-18). 원본 테스트 코드: test\anim\BipBake_test.ms, BipConvert_test.ms
global BipConvert_version = "0.1"
global BipFit  -- startup에서 BipFit.ms보다 먼저 읽혀도 함수 안 BipFit이 지역변수가 되지 않게
global BCV_dir = getFilenamePath (getThisScriptFilename())

fn BCV_needBipFit =
(
	if BipFit == undefined do (
		local cands = #(BCV_dir + "BipFit.ms")
		try (append cands ((getDir #userStartupScripts) + "\\BipFit.ms")) catch()
		try (append cands ((getDir #startupScripts) + "\\BipFit.ms")) catch()
		for f in cands while BipFit == undefined do if doesFileExist f do fileIn f)
	BipFit != undefined
)

-- ===== 기본 Biped 축 (Figure Mode, COM 로컬: X = 앞, Y = 왼쪽, Z = 위) =====
global BCV_REF = #(
	#("Pelvis",[0.0000,-0.0000,1.0000],[-0.0000,1.0000,0.0000]),
	#("Spine",[0.0008,0.0000,1.0000],[0.0000,1.0000,0.0000]),
	#("Spine1",[0.0008,0.0000,1.0000],[0.0000,1.0000,0.0000]),
	#("Spine2",[0.0008,0.0000,1.0000],[0.0000,1.0000,0.0000]),
	#("L Clavicle",[0.0000,0.9801,-0.1987],[0.0000,0.1987,0.9801]),
	#("L UpperArm",[-0.0993,0.0998,-0.9900],[0.0100,0.9950,0.0993]),
	#("L Forearm",[0.1003,0.0978,-0.9901],[0.0100,0.9950,0.0993]),
	#("L Hand",[0.1003,0.0978,-0.9901],[-0.9949,0.0206,-0.0988]),
	#("L Finger0",[0.2663,-0.1479,-0.9525],[-0.5213,0.8091,-0.2713]),
	#("L Finger01",[0.0716,-0.2754,-0.9587],[-0.5213,0.8091,-0.2713]),
	#("L Finger02",[-0.1270,-0.3880,-0.9129],[-0.5213,0.8091,-0.2713]),
	#("L Finger1",[0.1003,0.0978,-0.9901],[-0.9949,0.0198,-0.0988]),
	#("L Finger11",[0.0953,-0.1349,-0.9863],[-0.9949,0.0198,-0.0988]),
	#("L Finger12",[0.0851,-0.3603,-0.9290],[-0.9949,0.0198,-0.0988]),
	#("L Finger2",[0.1003,0.0978,-0.9901],[-0.9949,0.0198,-0.0988]),
	#("L Finger21",[0.0953,-0.1349,-0.9863],[-0.9949,0.0198,-0.0988]),
	#("L Finger22",[0.0851,-0.3603,-0.9290],[-0.9949,0.0198,-0.0988]),
	#("L Finger3",[0.1003,0.0978,-0.9901],[-0.9949,0.0198,-0.0988]),
	#("L Finger31",[0.0953,-0.1349,-0.9863],[-0.9949,0.0198,-0.0988]),
	#("L Finger32",[0.0851,-0.3603,-0.9290],[-0.9949,0.0198,-0.0988]),
	#("L Finger4",[0.1003,0.0978,-0.9901],[-0.9949,0.0198,-0.0988]),
	#("L Finger41",[0.0953,-0.1349,-0.9863],[-0.9949,0.0198,-0.0988]),
	#("L Finger42",[0.0851,-0.3603,-0.9290],[-0.9949,0.0198,-0.0988]),
	#("R Clavicle",[0.0000,-0.9801,-0.1987],[0.0000,0.1987,-0.9801]),
	#("R UpperArm",[-0.0993,-0.0998,-0.9900],[-0.0100,0.9950,-0.0993]),
	#("R Forearm",[0.1003,-0.0978,-0.9901],[-0.0100,0.9950,-0.0993]),
	#("R Hand",[0.1003,-0.0978,-0.9901],[0.9949,0.0206,0.0988]),
	#("R Finger0",[0.2663,0.1479,-0.9525],[0.5213,0.8091,0.2713]),
	#("R Finger01",[0.0716,0.2754,-0.9587],[0.5213,0.8091,0.2713]),
	#("R Finger02",[-0.1270,0.3880,-0.9129],[0.5213,0.8091,0.2713]),
	#("R Finger1",[0.1003,-0.0978,-0.9901],[0.9949,0.0198,0.0988]),
	#("R Finger11",[0.0953,0.1349,-0.9863],[0.9949,0.0198,0.0988]),
	#("R Finger12",[0.0851,0.3603,-0.9290],[0.9949,0.0198,0.0988]),
	#("R Finger2",[0.1003,-0.0978,-0.9901],[0.9949,0.0198,0.0988]),
	#("R Finger21",[0.0953,0.1349,-0.9863],[0.9949,0.0198,0.0988]),
	#("R Finger22",[0.0851,0.3603,-0.9290],[0.9949,0.0198,0.0988]),
	#("R Finger3",[0.1003,-0.0978,-0.9901],[0.9949,0.0198,0.0988]),
	#("R Finger31",[0.0953,0.1349,-0.9863],[0.9949,0.0198,0.0988]),
	#("R Finger32",[0.0851,0.3603,-0.9290],[0.9949,0.0198,0.0988]),
	#("R Finger4",[0.1003,-0.0978,-0.9901],[0.9949,0.0198,0.0988]),
	#("R Finger41",[0.0953,0.1349,-0.9863],[0.9949,0.0198,0.0988]),
	#("R Finger42",[0.0851,0.3603,-0.9290],[0.9949,0.0198,0.0988]),
	#("Neck",[0.0008,0.0000,1.0000],[0.0000,1.0000,0.0000]),
	#("Head",[-0.0000,0.0000,1.0000],[0.0000,1.0000,0.0000]),
	#("L Thigh",[0.0998,0.0000,-0.9950],[0.0000,-1.0000,0.0000]),
	#("L Calf",[-0.0998,0.0000,-0.9950],[0.0000,-1.0000,0.0000]),
	#("L Foot",[0.0000,0.0000,-1.0000],[0.0000,-1.0000,0.0000]),
	#("L Toe0",[1.0000,0.0000,0.0000],[0.0000,-1.0000,0.0000]),
	#("R Thigh",[0.0998,0.0000,-0.9950],[0.0000,-1.0000,0.0000]),
	#("R Calf",[-0.0998,0.0000,-0.9950],[0.0000,-1.0000,0.0000]),
	#("R Foot",[0.0000,0.0000,-1.0000],[0.0000,-1.0000,0.0000]),
	#("R Toe0",[1.0000,0.0000,0.0000],[0.0000,-1.0000,0.0000]))

fn BCV_swingZ rx rz ax =
(
	local k = cross rx ax; local sn = length k; local cs = dot rx ax
	if sn > 0.0001 then (k = k / sn; rz * cs + (cross k rz) * sn + k * (dot k rz) * (1 - cs)) else rz
)
fn BCV_signedAng a b ax = atan2 (dot (cross a b) ax) (dot a b)
fn BCV_orthAng z ax want = (local w = normalize (want - (dot want ax) * ax); BCV_signedAng w (normalize (z - (dot z ax) * ax)) ax)
fn BCV_ent mp nm = (if mp == undefined then undefined else (for e in mp where e[1] == nm collect e)[1])
fn BCV_jp mp nm k = (local e = BCV_ent mp nm; if e == undefined or e[k] == undefined then undefined else (local n = getNodeByName e[k]; if n == undefined then undefined else n.transform.pos))

-- ===== 축 검사 =====
-- 부위마다 정답 기준: 척추·목·머리·골반·다리·발 = 기본 Biped / 위팔·허벅지 = 뼈대가 굽은 면 / 아래팔·종아리 = 위 마디와 같은 축
--                    손·손가락 = 손 폭(검지 뿌리 - 새끼 뿌리) / 엄지 = 기본 엄지 축을 실제 엄지 방향으로 돌린 축 / 쇄골 = 참고
-- map: 뼈대 매핑(BipFit.mapFor). 뼈대가 없으면 기본 Biped 기준만 (참고로 표시)
fn BCV_axisCheck bipRoot map:undefined thr:15.0 =
(
	local bn = bipRoot.name
	local ctl = bipRoot.controller
	local was = ctl.figureMode
	ctl.figureMode = true
	local cr = bipRoot.transform.rotation as matrix3
	local rows = #()
	for r in BCV_REF do (
		local o = getNodeByName (bn + " " + r[1]) exact:true
		if o != undefined do (
			local ax = normalize o.transform.row1
			local z = o.transform.row3
			local sd = r[1][1]
			local kind = "기본"; local a = undefined
			local isArmLeg = (matchPattern r[1] pattern:"* UpperArm") or (matchPattern r[1] pattern:"* Thigh")
			local isLow = (matchPattern r[1] pattern:"* Forearm") or (matchPattern r[1] pattern:"* Calf")
			local isHand = (matchPattern r[1] pattern:"* Hand") or ((matchPattern r[1] pattern:"* Finger*") and not (matchPattern r[1] pattern:"* Finger0*"))
			local isThumb = matchPattern r[1] pattern:"* Finger0*"
			if isLow then (
				local up = getNodeByName (bn + " " + sd + (if matchPattern r[1] pattern:"*Forearm" then " UpperArm" else " Thigh")) exact:true
				kind = "위 마디와 같은 축"; a = BCV_signedAng (normalize up.transform.row3) (normalize z) ax)
			else if isArmLeg and map != undefined then (
				local lowN = sd + (if matchPattern r[1] pattern:"*UpperArm" then " Forearm" else " Calf")
				local p1 = BCV_jp map r[1] 2; local p2 = BCV_jp map r[1] 3; local p3 = BCV_jp map lowN 3
				if p1 != undefined and p2 != undefined and p3 != undefined do (
					local bendA = acos (amin 1.0 (dot (normalize (p2 - p1)) (normalize (p3 - p2))))
					if bendA > 5 do (
						local cz = normalize (cross (p2 - p1) (p3 - p2))
						if (dot cz z) < 0 do cz = -cz
						kind = "뼈대 굽힘 면 (" + (formattedPrint bendA format:".0f") + "° 굽음)"; a = BCV_orthAng z ax cz)))
			else if isHand and map != undefined then (
				local pi1 = BCV_jp map (sd + " Finger1") 2; local pp4 = BCV_jp map (sd + " Finger4") 2
				if pi1 != undefined and pp4 != undefined do (
					local lat = pi1 - pp4; if sd == "L" do lat = -lat
					kind = "손 폭"; a = BCV_orthAng z ax lat))
			else if isThumb and map != undefined then (
				local H = getNodeByName (bn + " " + sd + " Hand") exact:true
				local t1 = BCV_jp map (sd + " Finger0") 2; local t2 = BCV_jp map (sd + " Finger0") 3
				if H != undefined and t1 != undefined and t2 != undefined do (
					local thD = if sd == "L" then [0.955,0.239,-0.174] else [0.955,0.239,0.174]
					local thZ = if sd == "L" then [0.296,-0.772,0.562] else [-0.296,0.772,0.562]
					local hr = H.transform.rotation as matrix3
					local pi1 = BCV_jp map (sd + " Finger1") 2; local pp4 = BCV_jp map (sd + " Finger4") 2
					if pi1 != undefined and pp4 != undefined do (
						local hx = normalize H.transform.row1
						local lat = pi1 - pp4; if sd == "L" do lat = -lat
						local hz = normalize (lat - (dot lat hx) * hx)
						hr = matrix3 hx (normalize (cross hz hx)) hz [0,0,0])
					local zz = BCV_swingZ (normalize (thD * hr)) (normalize (thZ * hr)) (normalize (t2 - t1))
					kind = "엄지 규칙"; a = BCV_orthAng z ax zz))
			if a == undefined do (
				local zr = BCV_swingZ (normalize (r[2] * cr)) (normalize (r[3] * cr)) ax
				kind = if isArmLeg or isHand or isThumb then "기본(뼈대 없음, 참고)" else if matchPattern r[1] pattern:"*Clavicle" then "기본(쇄골, 참고)" else "기본"
				a = BCV_orthAng z ax zr)
			append rows #(r[1], a, kind)))
	ctl.figureMode = was
	local s = ""; local worst = 0.0; local nBad = 0
	for t in rows do (
		local ref_ = matchPattern t[3] pattern:"*참고*"
		if not ref_ do worst = amax worst (abs t[2])
		if abs t[2] > thr do (
			if not ref_ do nBad += 1
			s += (if ref_ then "  (참고) " else "  X ") + t[1] + ": " + (formattedPrint t[2] format:".1f") + "°  [" + t[3] + "]\r\n"))
	s = (if nBad == 0 then "축 검사 통과" else ("축 문제 " + (nBad as string) + "곳")) + " (기준 " + (thr as string) + "°, 최대 " + (formattedPrint worst format:".1f") + "°)\r\n" + s
	#(s, worst, nBad)
)

-- 장면의 뼈대 종류: 3 = AccuRIG/CC (CC_Base_), 4 = UE 이름 (pelvis, spine_01), 0 = 모름
fn BCV_detect =
(
	if (getNodeByName "CC_Base_Hip") != undefined and (getNodeByName "CC_Base_L_Thigh") != undefined then 3
	else if (getNodeByName "pelvis") != undefined and (getNodeByName "spine_01") != undefined and (getNodeByName "thigh_l") != undefined then 4
	else 0
)
-- 무게중심: 위치를 따라갈 노드, 회전을 따라갈 노드
fn BCV_comNodes preset = (if preset == 3 then #("CC_Base_Hip", "CC_Base_Pelvis") else #("pelvis", "pelvis"))

-- ===== 불러오기 =====
global BCV_src = #()
fn BCV_import f =
(
	local before = for o in objects collect o
	FBXImporterSetParam "Mode" #create
	FBXImporterSetParam "Animation" true
	FBXImporterSetParam "ImportBoneAsDummy" false
	try (FBXImporterSetParam "FillTimeline" false) catch()
	importFile f #noPrompt using:FBXIMP
	BCV_src = for o in objects where (findItem before o) == 0 collect o
	local lay = layerManager.getLayerFromName "BC_Source"
	if lay == undefined do lay = layerManager.newLayerFromName "BC_Source"
	for o in BCV_src do lay.addNode o
	BCV_src.count
)
-- 원본 키 중 가장 늦은 프레임
fn BCV_srcEnd =
(
	local mx = 0
	for o in BCV_src do (
		for i = 1 to 3 do (local sc = try (o.controller[i].controller) catch undefined
			if sc != undefined do (
				for k in sc.keys do mx = amax mx (k.time.frame as integer)
				for j = 1 to sc.numSubs do (local c3 = try (sc[j].controller) catch undefined; if c3 != undefined do for k in c3.keys do mx = amax mx (k.time.frame as integer)))))
	mx
)

-- ===== 굽기 =====
fn BCV_aim x zHint =
(
	x = normalize x
	local z = zHint - (dot zHint x) * x
	if length z < 0.001 do (local h2 = [0,0,1]; if abs (dot h2 x) > 0.9 do h2 = [0,1,0]; z = h2 - (dot h2 x) * x)
	z = normalize z
	matrix3 x (normalize (cross z x)) z [0,0,0]
)
fn BCV_rot n = ((n.transform.rotation) as matrix3)
fn BCV_setAim b x zs = (local m = BCV_aim x zs; biped.setTransform b #rotation m.rotation true)
fn BCV_angErr b h t = acos (amin 1.0 (amax -1.0 (dot (normalize b.transform.row1) (normalize (t.transform.pos - h.transform.pos)))))

-- 원본 뼈대(restT = 바인드 포즈 프레임)를 기준으로 f1..f2를 Biped에 키
-- 끝 관절이 있으면 방향을 맞추고 비틀림은 원본 뼈를 따라감, 없으면 회전 변화량. 위팔·허벅지는 접히는 면 양쪽을 시도, 아래 마디 Z = 위 마디 Z
fn BCV_bake bipRoot map comNm restT f1 f2 =
(
	local bn = bipRoot.name
	bipRoot.controller.figureMode = false
	local parts = #()
	for e in map do (
		local b = getNodeByName (bn + " " + e[1]) exact:true
		local h = if e[2] == undefined then undefined else getNodeByName e[2] exact:true
		local t = if e[3] == undefined then undefined else getNodeByName e[3] exact:true
		if b != undefined and h != undefined do (
			local isFoot = (matchPattern e[1] pattern:"* Foot") or (matchPattern e[1] pattern:"* Toe0")
			local Rb = at time 0 BCV_rot b
			local S0 = at time restT BCV_rot h
			if t != undefined and not isFoot then (
				local fr0 = BCV_aim (at time restT (t.transform.pos - h.transform.pos)) Rb.row3
				append parts #(b, h, t, #aim, fr0.row3 * (inverse S0), e[1]))
			else append parts #(b, h, t, #delta, Rb * (inverse S0), e[1])))
	local sh = getNodeByName comNm[1] exact:true; local sp = getNodeByName comNm[2] exact:true
	local comR0 = at time 0 BCV_rot bipRoot
	local comP0 = at time 0 bipRoot.transform.pos
	local pS0 = at time restT BCV_rot sp
	local hS0 = at time restT sh.transform.pos
	local ratio = comP0.z / hS0.z
	local legA = #("L Thigh","R Thigh","L UpperArm","R UpperArm")
	for f = f1 to f2 do at time f with animate on (
		biped.setTransform bipRoot #pos (comP0 + (sh.transform.pos - hS0) * ratio) true
		local comR = comR0 * (inverse pS0) * (BCV_rot sp)
		biped.setTransform bipRoot #rotation comR.rotation true
		local done = #()
		for i = 1 to parts.count where (findItem done i) == 0 do (
			local p = parts[i]
			local b = p[1]; local h = p[2]; local t = p[3]
			local Sf = BCV_rot h
			if p[4] == #aim then (
				local x = t.transform.pos - h.transform.pos
				local zs = p[5] * Sf
				local j = 0
				if (findItem legA p[6]) > 0 do (
					local lowN = if matchPattern p[6] pattern:"*Thigh" then (p[6][1] + " Calf") else (p[6][1] + " Forearm")
					j = (for k = 1 to parts.count where parts[k][6] == lowN collect k)[1]
					if j == undefined or parts[j][3] == undefined do j = 0)
				if j == 0 then BCV_setAim b x zs
				else (
					local q = parts[j]
					local nxt = q[3]
					local cands = #(zs, -zs)
					local cr = cross x (nxt.transform.pos - t.transform.pos)
					if (length cr) > 0.05 * (length x) * (distance t.transform.pos nxt.transform.pos) do (local zb = normalize cr; cands = #(zb, -zb, zs))
					local best = 1e9; local bz = cands[1]
					for zc in cands do (
						BCV_setAim b x zc
						BCV_setAim q[1] (nxt.transform.pos - t.transform.pos) zc
						local e = (BCV_angErr b h t) + (BCV_angErr q[1] t nxt)
						if e < best do (best = e; bz = zc))
					BCV_setAim b x bz
					BCV_setAim q[1] (nxt.transform.pos - t.transform.pos) bz
					append done j))
			else (
				local m = p[5] * Sf
				if (matchPattern p[6] pattern:"*Finger?2") and b.parent != undefined then (
					-- 손가락 끝마디: 앞 마디가 접히는 면 안으로 투영 (Biped 손가락은 한 축 관절)
					local zp = normalize b.parent.transform.row3
					local xt = m.row1 - (dot m.row1 zp) * zp
					if (length xt) > 0.001 do BCV_setAim b xt zp)
				else biped.setTransform b #rotation m.rotation true)))
	parts.count
)
fn BCV_err bipRoot map f1 f2 =
(
	local worst = 0.0; local wn = ""; local sum = 0.0; local cnt = 0
	for f = f1 to f2 do at time f (
		for e in map where e[3] != undefined and not (matchPattern e[1] pattern:"* Foot") do (
			local b = getNodeByName (bipRoot.name + " " + e[1]) exact:true
			local h = getNodeByName e[2] exact:true; local t = getNodeByName e[3] exact:true
			if b != undefined and h != undefined and t != undefined do (
				local a = BCV_angErr b h t
				sum += a; cnt += 1
				if a > worst do (worst = a; wn = e[1] + " @" + (f as string)))))
	"평균 " + (formattedPrint (sum / amax cnt 1) format:".2f") + "°, 최대 " + (formattedPrint worst format:".2f") + "° (" + wn + ")"
)

-- ===== 키 정리 =====
-- Biped 트랙(COM 이동·회전, 척추, 목+머리, L/R 팔(손가락 포함), L/R 다리(발가락 포함))마다 키를 하나씩 지워 보고,
-- 앞뒤 키 사이 프레임에서 (부모 기준) 회전 오차 > rotTol 또는 COM·발가락 위치 오차 > posTol이면 되살림
global BCR_parts = #(); global BCR_refL = #(); global BCR_refCOM = #(); global BCR_refToe = #()
global BCR_f1 = 0; global BCR_f2 = 0
fn BCR_local o = (if o.parent == undefined or classOf o.parent != Biped_Object then (o.transform.rotation as matrix3) else ((o.transform.rotation as matrix3) * inverse (o.parent.transform.rotation as matrix3)))
fn BCR_angM a b = (local q = (a as quat) * inverse (b as quat); local v = abs q.angle; if v > 180 then 360 - v else v)
fn BCR_idx o = findItem BCR_parts o
fn BCR_record bipRoot f1 f2 =
(
	BCR_f1 = f1; BCR_f2 = f2
	BCR_parts = for o in objects where classOf o == Biped_Object and o != bipRoot and not (matchPattern o.name pattern:"*Nub") and not (matchPattern o.name pattern:"*Footsteps") collect o
	BCR_refL = for o in BCR_parts collect (for f = f1 to f2 collect (at time f BCR_local o))
	BCR_refCOM = for f = f1 to f2 collect (at time f bipRoot.transform)
	local lt = getNodeByName (bipRoot.name + " L Toe0") exact:true; local rt = getNodeByName (bipRoot.name + " R Toe0") exact:true
	BCR_refToe = for f = f1 to f2 collect (at time f #(lt.transform.pos, rt.transform.pos))
)
fn BCR_pp bn pat = for o in BCR_parts where matchPattern o.name pattern:(bn + " " + pat) collect o
fn BCR_tracks bipRoot =
(
	local bn = bipRoot.name
	local c = bipRoot.controller
	#(
		#("COM 이동", #(c.vertical.controller, c.horizontal.controller), #(), #pos),
		#("COM 회전", #(c.turning.controller), #(), #rot),
		#("척추", #((getNodeByName (bn + " Spine") exact:true).controller), (BCR_pp bn "Spine*"), #part),
		#("목·머리", #((getNodeByName (bn + " Neck") exact:true).controller), (BCR_pp bn "Neck*") + (BCR_pp bn "Head"), #part),
		#("L 팔", #((getNodeByName (bn + " L Clavicle") exact:true).controller), (BCR_pp bn "L Clavicle") + (BCR_pp bn "L UpperArm") + (BCR_pp bn "L Forearm") + (BCR_pp bn "L Hand") + (BCR_pp bn "L Finger*"), #part),
		#("R 팔", #((getNodeByName (bn + " R Clavicle") exact:true).controller), (BCR_pp bn "R Clavicle") + (BCR_pp bn "R UpperArm") + (BCR_pp bn "R Forearm") + (BCR_pp bn "R Hand") + (BCR_pp bn "R Finger*"), #part),
		#("L 다리", #((getNodeByName (bn + " L Thigh") exact:true).controller), (BCR_pp bn "L Thigh") + (BCR_pp bn "L Calf") + (BCR_pp bn "L Foot") + (BCR_pp bn "L Toe*"), #part),
		#("R 다리", #((getNodeByName (bn + " R Thigh") exact:true).controller), (BCR_pp bn "R Thigh") + (BCR_pp bn "R Calf") + (BCR_pp bn "R Foot") + (BCR_pp bn "R Toe*"), #part))
)
fn BCR_keyIdx c t = (local r = 0; for i = 1 to c.keys.count where (c.keys[i].time.frame as integer) == t do r = i; r)
fn BCR_keyTimes c = for k in c.keys collect (k.time.frame as integer)
fn BCR_ok bipRoot tr a b rotTol posTol =
(
	local lt = getNodeByName (bipRoot.name + " L Toe0") exact:true; local rt = getNodeByName (bipRoot.name + " R Toe0") exact:true
	local good = true
	for f = a to b while good do at time f (
		local fi = f - BCR_f1 + 1
		if tr[4] == #pos then (if (distance bipRoot.transform.pos BCR_refCOM[fi].pos) > posTol do good = false)
		else if tr[4] == #rot then (if (BCR_angM (bipRoot.transform.rotation as matrix3) (BCR_refCOM[fi].rotation as matrix3)) > rotTol do good = false)
		else for o in tr[3] while good do (if (BCR_angM (BCR_local o) BCR_refL[BCR_idx o][fi]) > rotTol do good = false)
		if good do (if (distance lt.transform.pos BCR_refToe[fi][1]) > posTol or (distance rt.transform.pos BCR_refToe[fi][2]) > posTol do good = false))
	good
)
fn BCR_restore bipRoot tr t =
(
	local fi = t - BCR_f1 + 1
	at time t with animate on (
		if tr[4] == #pos then biped.setTransform bipRoot #pos BCR_refCOM[fi].pos true
		else if tr[4] == #rot then biped.setTransform bipRoot #rotation BCR_refCOM[fi].rotation true
		else for o in tr[3] do (
			local w = if o.parent != undefined and classOf o.parent == Biped_Object then BCR_refL[BCR_idx o][fi] * (o.parent.transform.rotation as matrix3) else BCR_refL[BCR_idx o][fi]
			biped.setTransform o #rotation w.rotation true))
)
fn BCR_reduce bipRoot f1 f2 rotTol:1.0 posTol:0.2 =
(
	BCR_record bipRoot f1 f2
	local before = 0; local after = 0
	for tr in BCR_tracks bipRoot do (
		local c0 = tr[2][1]
		local ts = BCR_keyTimes c0
		before += ts.count
		for t in ts where t > f1 and t < f2 do (
			local cur = BCR_keyTimes c0
			local i = findItem cur t
			if i > 1 and i < cur.count do (
				local a = cur[i - 1]; local b = cur[i + 1]
				for c in tr[2] do (local k = BCR_keyIdx c t; if k > 0 do deleteKey c k)
				if not (BCR_ok bipRoot tr (a + 1) (b - 1) rotTol posTol) do BCR_restore bipRoot tr t))
		after += c0.keys.count)
	#(before, after)
)

-- ===== FBX 한 개 변환 =====
-- 장면을 비우고 진행함 (호출하는 쪽에서 hold/fetch). 반환: 보고 문자열
fn BCV_convertOne fbx outBip outMax:undefined preset:0 fps:30 reduce:true rotTol:1.0 posPct:0.53 =
(
	local t0 = timeStamp()
	resetMaxFile #noPrompt
	frameRate = fps
	BCV_import fbx
	local pr = if preset == 0 then BCV_detect() else preset
	if pr == 0 do return "  실패: 뼈대 이름을 알 수 없음 (CC_Base_ / UE 이름 아님)"
	local nF = BCV_srcEnd()
	if nF < 2 do return "  실패: 애니메이션이 없음 (키 " + (nF as string) + "프레임까지)"
	animationRange = interval 0 nF
	sliderTime = 0
	local map = BipFit.mapFor pr ""
	local b = BipFit.createBiped pr prefix:"Bip001"
	if b == undefined do return "  실패: Biped 만들기 - " + BipFit.log
	local fitLog = BipFit.fit b pr
	local fl = filterString fitLog "\n"
	local ax = BCV_axisCheck b map:map
	BCV_bake b map (BCV_comNodes pr) 0 0 nF
	local er = BCV_err b map 1 nF
	local red = ""
	if reduce do (
		local rr = BCR_reduce b 1 nF rotTol:rotTol posTol:((at time 0 b.transform.pos.z) * posPct / 100.0)
		red = " | 키 " + (rr[1] as string) + " → " + (rr[2] as string))
	biped.saveBipFileSegment b.controller outBip 1 nF
	if outMax != undefined do saveMaxFile outMax quiet:true
	"  " + (if pr == 3 then "CC" else "UE") + " 뼈대, 1~" + (nF as string) + "프레임 | " + fl[fl.count] + " | " + ((filterString ax[1] "\r\n")[1]) + " | 굽기 오차 " + er + red + " | " + (formattedPrint ((timeStamp() - t0) / 1000.0) format:".1f") + "초" +
		(if ax[3] > 0 then "\r\n" + ax[1] else "")
)

fn BCV_writeUtf8 f txt = ((dotNetClass "System.IO.File").WriteAllText f txt (dotNetObject "System.Text.UTF8Encoding" true))


-- ===== 여러 개 변환 =====
-- 지금 장면은 hold → 변환 → fetch로 되돌림. 결과: FBX와 같은 폴더에 이름.bip (+ 이름_convert.max), 첫 FBX 폴더에 BipConvert_report.txt
fn BCV_log logCtrl s = (if logCtrl != undefined do (logCtrl.text += s + "\r\n"); format "%\n" s; windows.processPostedMessages())
fn BCV_batch files preset:0 fps:30 reduce:true rotTol:1.0 posPct:0.53 saveMax:true logCtrl:undefined =
(
	if not (BCV_needBipFit()) do return "BipFit.ms를 찾을 수 없음"
	-- 지금 장면: 저장된 파일이면 끝나고 다시 열고, 저장 안 된 변경이 있으면 hold/fetch (fetch는 파일 이름이 비워짐)
	local orig = maxFilePath + maxFileName
	local dirty = getSaveRequired()
	local useHold = dirty or orig == ""
	if useHold do holdMaxFile()
	local rep = "BipConvert v" + BipConvert_version + "  " + localTime + "\r\n"
	local ok_ = 0
	progressStart "BipConvert"
	for i = 1 to files.count do (
		local f = files[i]
		local nm = getFilenameFile f
		local outB = (getFilenamePath f) + nm + ".bip"
		local outM = if saveMax then ((getFilenamePath f) + nm + "_convert.max") else undefined
		BCV_log logCtrl ("[" + (i as string) + "/" + (files.count as string) + "] " + nm + " ...")
		if doesFileExist outB do deleteFile outB
		local r = try (BCV_convertOne f outB outMax:outM preset:preset fps:fps reduce:reduce rotTol:rotTol posPct:posPct) catch ("  오류: " + (getCurrentException()))
		if doesFileExist outB and not (matchPattern r pattern:"*실패*") and not (matchPattern r pattern:"*오류*") do ok_ += 1
		BCV_log logCtrl r
		rep += nm + "\r\n" + r + "\r\n"
		if not (progressUpdate (100.0 * i / files.count)) do exit)
	progressEnd()
	local back = ""
	if useHold then (
		fetchMaxFile quiet:true
		back = if orig != "" then (" 저장 안 된 장면을 되돌렸지만 파일 이름이 비어 있음 → 필요하면 " + (filenameFromPath orig) + "로 다시 저장하세요.") else " 장면을 되돌림.")
	else (
		loadMaxFile orig quiet:true
		back = " " + (filenameFromPath orig) + " 다시 열음.")
	local sumL = "완료: " + (ok_ as string) + " / " + (files.count as string) + "개 변환." + back
	BCV_log logCtrl sumL
	rep += sumL + "\r\n"
	local rf = (getFilenamePath files[1]) + "BipConvert_report.txt"
	try (BCV_writeUtf8 rf rep; BCV_log logCtrl ("보고서: " + rf)) catch()
	rep
)

-- ===== 창 =====
try (destroyDialog BipConvertRoll) catch()
rollout BipConvertRoll "BipConvert v0.1 - FBX 애니 → .bip"
(
	local files = #()
	group "1. FBX 파일"
	(
		listbox lbFiles "" height:8
		button btAdd "FBX 추가..." across:3 width:85
		button btDir "폴더 추가..." width:85
		button btClr "비우기" width:85
	)
	group "2. 설정"
	(
		dropdownlist ddSk "뼈대 종류" items:#("자동 감지", "AccuRIG / CC (CC_Base_)", "UE 이름 (pelvis, spine_01)")
		spinner spFps "FPS " range:[1,120,30] type:#integer fieldwidth:40 align:#left
		checkbox ckRed "키 정리" checked:true across:2
		checkbox ckMax "확인용 .max 저장" checked:true
		spinner spRot "회전 허용 (도) " range:[0.1,10,1.0] fieldwidth:40 align:#left
		spinner spPos "위치 허용 (키의 %) " range:[0.05,5,0.53] fieldwidth:40 align:#left
		label lbOut "결과: FBX와 같은 폴더에 이름.bip" align:#left
	)
	button btRun "변환 시작" width:270 height:30
	group "3. 캐릭터 축 검사"
	(
		label lbAx "Biped를 하나 선택하고 누르세요 (.bip 불러오기 전 확인)" align:#left
		button btAxis "Biped 축 검사" width:250
	)
	edittext etLog "" height:220 readOnly:true

	fn refresh = (lbFiles.items = for f in files collect (filenameFromPath f))
	fn logLine s = (etLog.text += s + "\r\n"; windows.processPostedMessages())

	on btAdd pressed do (
		local dlg = dotNetObject "System.Windows.Forms.OpenFileDialog"
		dlg.Filter = "FBX (*.fbx)|*.fbx"
		dlg.Multiselect = true
		dlg.Title = "변환할 FBX 선택"
		if (dlg.ShowDialog()).ToString() == "OK" do (
			for f in dlg.FileNames where (findItem files f) == 0 do append files f
			refresh()))
	on btDir pressed do (
		local d = getSavePath caption:"FBX가 있는 폴더"
		if d != undefined do (
			for f in (getFiles (d + "\\*.fbx")) where (findItem files f) == 0 do append files f
			refresh()))
	on btClr pressed do (files = #(); refresh())

	on btRun pressed do (
		if files.count == 0 do (messageBox "FBX 파일을 먼저 추가하세요." title:"BipConvert"; return false)
		if not (BCV_needBipFit()) do (messageBox ("BipFit.ms를 찾을 수 없습니다.\n" + BCV_dir) title:"BipConvert"; return false)
		if getSaveRequired() do
			if not (queryBox "지금 장면이 저장되지 않았습니다.\n변환은 빈 장면에서 진행되고, 끝나면 지금 장면으로 되돌립니다(Hold/Fetch).\n단, 되돌린 장면은 파일 이름이 비워지니 직접 저장해야 합니다.\n계속할까요?" title:"BipConvert") do return false
		local pr = ddSk.selection; if pr == 2 then pr = 3 else if pr == 3 then pr = 4 else pr = 0
		etLog.text = ""
		BCV_batch files preset:pr fps:spFps.value reduce:ckRed.checked rotTol:spRot.value posPct:spPos.value saveMax:ckMax.checked logCtrl:etLog
	)

	on btAxis pressed do (
		if not (BCV_needBipFit()) do (messageBox "BipFit.ms를 찾을 수 없습니다." title:"BipConvert"; return false)
		local root = undefined
		for o in selection where classOf o == Biped_Object while root == undefined do root = o.controller.rootNode
		if root == undefined do for o in objects where classOf o == Biped_Object and o.controller.rootNode == o while root == undefined do root = o
		if root == undefined do (messageBox "장면에 Biped가 없습니다." title:"BipConvert"; return false)
		local pr = BCV_detect()
		local map = if pr == 0 then undefined else (BipFit.mapFor pr "")
		local r = BCV_axisCheck root map:map
		etLog.text = root.name + " 축 검사" + (if map == undefined then " (스킨 뼈대 이름을 몰라 기본 Biped 기준만)" else (if pr == 3 then " (CC 뼈대 기준)" else " (UE 뼈대 기준)")) + "\r\n" + r[1]
	)
)

macroScript BipConvertTool category:"Claude" buttonText:"BipConvert" tooltip:"FBX 애니 → .bip 변환 + Biped 축 검사"
(
	try (destroyDialog BipConvertRoll) catch()
	createDialog BipConvertRoll 300 640
)

-- 메뉴 Claude > BipConvert (Claude 메뉴가 없으면 만듦). Max 시작 때는 다른 startup 스크립트가 다 읽힌 뒤 실행
fn BCV_addMenu create:true =
(
	try (
		local mn = menuMan.findMenu "Claude"
		if mn == undefined and not create do return false
		if mn == undefined do (
			mn = menuMan.createMenu "Claude"
			(menuMan.getMainMenuBar()).addItem (menuMan.createSubMenuItem "Claude" mn) -1)
		local has = false
		for i = 1 to mn.numItems() do if (mn.getItem i).getTitle() == "BipConvert" do has = true
		if not has do mn.addItem (menuMan.createActionItem "BipConvertTool" "Claude") -1
		menuMan.updateMenuBar())
	catch ()
)
callbacks.removeScripts id:#BipConvertMenu
callbacks.addScript #postSystemStartup "BCV_addMenu()" id:#BipConvertMenu
-- 지금 바로(스크립트 실행 시)는 Claude 메뉴가 이미 있을 때만 추가 (Max 시작 중이면 RigTools가 메뉴를 먼저 만들도록)
BCV_addMenu create:false
