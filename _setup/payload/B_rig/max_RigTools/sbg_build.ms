-- ======================================================================
--  SecBoneGen — Biped 자동 생성 (TOS_RigTools 의 "2. Biped 자동 생성" 단계, 성별 레퍼런스 = tos_bip_ref.ms)
--  노란 지정점(sbg_*)으로 Biped 를 만들고 손가락·발가락·트위스트·쇄골까지 맞춘다.
--  지정점은 Blender [관절 자동 감지](Max Bridge 패널) 가 놓거나, SecBoneGen 창에서 직접 놓는다.
--    몸: sbg_Spine  sbg_SpineWidth  sbg_Neck  sbg_NeckEnd  sbg_Head  sbg_HeadEnd
--        sbg_L_Thigh  sbg_L_Calf  sbg_L_Foot  sbg_L_Clavicle  sbg_L_UpperArm  sbg_L_Forearm  sbg_L_Hand  sbg_L_HandEnd
--    손가락(있으면): tsbg_f<손가락 1~5: 엄지~소지>_<1~4: 뿌리~끝>   발가락(있으면): sbg_L_Toe
--    빨간 점 = 자동 감지가 의심스러운 곳 (확인 필요)
--  같은 폴더의 SecBoneGen_v0.11_step1_biped.ms · sbg_fingers.ms 를 불러 쓴다.
-- ======================================================================
global TSBG_noDialog = true
fileIn ((getFilenamePath (getThisScriptFilename())) + "SecBoneGen_v0.11_step1_biped.ms")
fileIn ((getFilenamePath (getThisScriptFilename())) + "sbg_fingers.ms")
TSBG_noDialog = false

global trts_sbgBuild, TOS_BipRef, trts_layerTidy, TosRig
global tsbg_savePts, tsbg_restorePts   -- 아래(수정/완료)에서 정의
global trts_sbgVersion = "1.4"
-- 뼈 굵기 비율: 팀 정답 리그 5개(Bacha2·theia·meira·behemoth·leviathan) 평균. #len = 그 뼈 길이 기준, #h = 키(목~발목) 기준
-- 발·발가락은 비율 대신 메쉬로 맞춤 (tsbg_fitFootToe)
global TSBG_thickRule = #( \
	#("Head", #h, 0.14931, 0.12956), \
	#("L Calf", #h, 0.10429, 0.09065), \
	#("L Clavicle", #h, 0.08207, 0.08863), \
	#("L Finger0", #h, 0.02193, 0.02412), \
	#("L Finger01", #h, 0.01829, 0.02001), \
	#("L Finger02", #h, 0.01621, 0.01641), \
	#("L Finger1", #len, 0.59272, 0.53005), \
	#("L Finger11", #len, 0.84451, 0.77666), \
	#("L Finger12", #len, 0.73443, 0.68408), \
	#("L Finger2", #h, 0.01346, 0.01355), \
	#("L Finger21", #h, 0.01293, 0.01273), \
	#("L Finger22", #len, 0.66269, 0.64396), \
	#("L Finger3", #len, 0.52296, 0.50616), \
	#("L Finger31", #len, 0.71142, 0.71278), \
	#("L Finger32", #len, 0.66287, 0.66482), \
	#("L Finger4", #h, 0.01116, 0.01113), \
	#("L Finger41", #len, 0.73363, 0.73363), \
	#("L Finger42", #len, 0.64475, 0.64475), \
	#("L Forearm", #h, 0.06602, 0.06411), \
	#("L Hand", #h, 0.03440, 0.05602), \
	#("L Thigh", #len, 0.40168, 0.34677), \
	#("L UpperArm", #len, 0.45889, 0.42267), \
	#("Neck", #h, 0.06757, 0.07032), \
	#("Pelvis", #len, 1.47414, 1.27314), \
	#("Spine", #h, 0.14493, 0.16577), \
	#("Spine1", #h, 0.15665, 0.18140), \
	#("Spine2", #h, 0.18086, 0.20001) )

fn trts_sbgPt nm = (
	local n = getNodeByName nm
	if n == undefined or (isDeleted n) then undefined else n.transform.pos
)


fn tsbg_allBipPos = ( for o in objects where classof o == Biped_Object and not (matchPattern o.name pattern:"*Footsteps*") collect #(o, o.transform.pos) )

-- 굵기를 바꾸되, Biped 의 어떤 피봇이라도 움직이면 되돌림
fn tsbg_fitDirWidthSafe node dir target axes = (
	local cur = tsbg_boneExtent node dir
	if cur < 1e-4 do return #fail
	if (abs (target - cur)) < (target * 0.01) do return #ok
	local all = tsbg_allBipPos()
	for axis in axes do (
		local s0 = biped.getTransform node #scale
		local s = copy s0
		s[axis] *= (target / cur)
		biped.setTransform node #scale s false
		local mv = 0.0
		for a in all do ( local d = distance a[1].transform.pos a[2]; if d > mv do mv = d )
		local w1 = tsbg_boneExtent node dir
		if mv < 0.01 and (abs (w1 - target)) < ((abs (cur - target)) * 0.5) then (
			if w1 > 1e-4 and (abs (w1 - target)) > (target * 0.01) do (
				local s2 = biped.getTransform node #scale
				s2[axis] *= (target / w1)
				biped.setTransform node #scale s2 false
				local mv2 = 0.0
				for a in all do ( local d = distance a[1].transform.pos a[2]; if d > mv2 do mv2 = d )
				if mv2 >= 0.01 do biped.setTransform node #scale s false
			)
			return #ok
		)
		biped.setTransform node #scale s0 false
	)
	#fail
)

-- 표준 굵기 적용. 피봇이 움직이는 축은 건너뜀 (손 두께는 따로: 늘린 뒤 손가락을 다시 맞춤)
fn tsbg_applyThickness bip = (
	local lF = biped.getNode bip #lleg link:3
	local nk = biped.getNode bip #neck link:1
	local h = nk.transform.pos.z - lF.transform.pos.z
	local skipped = #()
	local nOk = 0
	for r in TSBG_thickRule do (
		local names = if (matchPattern r[1] pattern:"L *") then #("Bip01 " + r[1], "Bip01 R" + (substring r[1] 2 -1)) else #("Bip01 " + r[1])
		for nm in names do (
			local n = getNodeByName nm
			if n != undefined and r[1] != "L Hand" do (
				local base = if r[2] == #len then (tsbg_boneExtent n (normalize n.transform.row1)) else h
				local ry = tsbg_fitDirWidthSafe n (normalize n.transform.row2) (r[3] * base) #(2, 3)
				local rz = tsbg_fitDirWidthSafe n (normalize n.transform.row3) (r[4] * base) #(2, 3)
				if ry == #ok and rz == #ok then nOk += 1 else append skipped (nm + (if ry != #ok then " 두께" else "") + (if rz != #ok then " 너비" else ""))
			)
		)
	)
	-- 손: 두께·너비를 맞춘 뒤 손가락을 지정점에 다시 맞춤 (손가락 피봇은 지정점 기준이라 그대로)
	local hr = undefined
	for r in TSBG_thickRule where r[1] == "L Hand" do hr = r
	if hr != undefined do (
		for k in #(#larm, #rarm) do (
			local hd = biped.getNode bip k link:4
			tsbg_fitDirWidth hd (normalize hd.transform.row2) (hr[3] * h) #() #(2, 3)
			tsbg_fitDirWidth hd (normalize hd.transform.row3) (hr[4] * h) #() #(2, 3)
		)
	)
	#(nOk, skipped)
)

-- 지정점 ↔ Biped 피봇 차이 (cm). 반대쪽은 거울
fn tsbg_pivotReport bip = (
	local cx = (trts_sbgPt "sbg_Spine").x
	local pairs = #(#("sbg_L_UpperArm", "UpperArm"), #("sbg_L_Hand", "Hand"), #("sbg_L_Thigh", "Thigh"), #("sbg_L_Foot", "Foot"))
	local out = "", worst = 0.0
	for pr in pairs do (
		local p = trts_sbgPt pr[1]
		if p != undefined do (
			local nl = getNodeByName ("Bip01 L " + pr[2]), nr = getNodeByName ("Bip01 R " + pr[2])
			local lOn = (p.x - cx) * (nl.transform.pos.x - cx) > 0
			local pL = if lOn then p else [2 * cx - p.x, p.y, p.z]
			local pRt = [2 * cx - pL.x, pL.y, pL.z]
			local d = amax (distance nl.transform.pos pL) (distance nr.transform.pos pRt)
			if d > worst do worst = d
			out += pr[2] + " " + (formattedPrint d format:".2f") + "  "
		)
	)
	for pr in #(#("sbg_Neck", "Bip01 Neck"), #("sbg_Head", "Bip01 Head")) do (
		local p = trts_sbgPt pr[1], n = getNodeByName pr[2]
		if p != undefined and n != undefined do ( local d = distance n.transform.pos p; if d > worst do worst = d; out += (substring pr[2] 7 -1) + " " + (formattedPrint d format:".2f") + "  " )
	)
	#(worst, out)
)

-- 굵기·길이를 바꾸되, allow 에 든 뼈 말고는 피봇이 움직이면 되돌림
fn tsbg_fitDirSafeEx node dir target axes allow = (
	local cur = tsbg_boneExtent node dir
	if cur < 1e-4 do return #fail
	if (abs (target - cur)) < (target * 0.005) do return #ok
	local all = for a in tsbg_allBipPos() where (findItem allow a[1]) == 0 collect a
	for axis in axes do (
		local s0 = biped.getTransform node #scale
		for it = 1 to 3 do (
			local c = tsbg_boneExtent node dir
			local s = biped.getTransform node #scale
			s[axis] *= (target / c)
			biped.setTransform node #scale s false
		)
		local mv = 0.0
		for a in all do ( local d = distance a[1].transform.pos a[2]; if d > mv do mv = d )
		if mv < 0.01 and (abs ((tsbg_boneExtent node dir) - target)) < (target * 0.02) then return #ok
		biped.setTransform node #scale s0 false
	)
	#fail
)

fn tsbg_mx p cx mir = if mir then [2 * cx - p.x, p.y, p.z] else p

-- 발: 뒤꿈치(sbg_L_Heel)~발가락 시작(sbg_L_Toe) 길이, 발 너비(sbg_L_FootWidth), 발바닥 Z=0
-- 발가락: 발 상자 앞에 붙은 채로 발끝(sbg_L_ToeEnd)까지, 너비 = 발 너비, 높이 = sbg_L_ToeTop 높이
fn tsbg_fitFootToe bip = (
	local heel = trts_sbgPt "sbg_L_Heel", toeR = trts_sbgPt "sbg_L_Toe", toeE = trts_sbgPt "sbg_L_ToeEnd", fw = trts_sbgPt "sbg_L_FootWidth"
	if heel == undefined or toeR == undefined or toeE == undefined do return "발 지정점(sbg_L_Heel·sbg_L_ToeEnd)이 없어 발은 기본 모양이에요."
	local cx = (trts_sbgPt "sbg_Spine").x
	local out = ""
	for side in #(#l, #r) do (
		local legK = if side == #l then #lleg else #rleg
		local toeK = if side == #l then #ltoes else #rtoes
		local foot = biped.getNode bip legK link:3
		local toe = biped.getNode bip toeK link:1
		local mir = ((heel.x - cx) * (foot.transform.pos.x - cx)) < 0
		local hl = tsbg_mx heel cx mir, tr = tsbg_mx toeR cx mir, te = tsbg_mx toeE cx mir
		local fwd = normalize [0, tr.y - hl.y, 0]
		local L = abs (tr.y - hl.y)
		local W = if fw != undefined then 2 * (abs (fw.x - toeR.x)) else (tsbg_boneExtent foot [1,0,0])
		local toes = for i = 1 to 5 collect (try (biped.getNode bip toeK link:i) catch undefined)
		toes = for o in toes where o != undefined collect o
		local r1 = tsbg_fitDirSafeEx foot fwd L #(2, 3, 1) toes
		local r2 = tsbg_fitDirSafeEx foot [1,0,0] W #(3, 2, 1) toes
		if TSBG_floor do tsbg_footToFloor foot
		-- 발가락: 방향·길이 (피봇은 발 앞에 붙은 채), 너비 = 발 너비
		tsbg_aim toe te
		local tl = distance toe.transform.pos te
		local r3 = tsbg_fitDirSafeEx toe (normalize toe.transform.row1) tl #(1) #()
		local r4 = tsbg_fitDirSafeEx toe [1,0,0] (tsbg_boneExtent foot [1,0,0]) #(3, 2) #()
		-- 발가락 높이 = 발가락 부분 신발 높이 (sbg_L_ToeTop 의 z)
		local tt = trts_sbgPt "sbg_L_ToeTop"
		if tt != undefined and tt.z > 0.1 do tsbg_fitDirSafeEx toe [0,0,1] tt.z #(2, 3) #()
		local gap = distance toe.transform.pos tr
		out += foot.name + ": 길이 " + (formattedPrint (tsbg_boneExtent foot fwd) format:".1f") + "/" + (formattedPrint L format:".1f") + " 너비 " + (formattedPrint (tsbg_boneExtent foot [1,0,0]) format:".1f") + "/" + (formattedPrint W format:".1f") + \
			"  발가락 시작↔지정점 " + (formattedPrint gap format:".2f") + "  " + (r1 as string) + (r2 as string) + (r3 as string) + (r4 as string) + "\n"
	)
	out
)

-- 지정점으로 Ankle Attach (뒤꿈치~발가락 시작 사이 발목 위치 비율)
fn tsbg_ankleAttach = (
	local heel = trts_sbgPt "sbg_L_Heel", toeR = trts_sbgPt "sbg_L_Toe", ank = trts_sbgPt "sbg_L_Foot"
	if heel == undefined or toeR == undefined or ank == undefined do return 0.43
	local a = (heel.y - ank.y) / (heel.y - toeR.y)
	if a < 0.1 or a > 0.9 then 0.43 else a
)

-- 관절 자동 감지 (Max 에서 바로): Blender 를 새로 띄워 감지하고 지정점(sbg_*)을 이 Max 에 놓는다.
-- Max Bridge 포트와 상관없이 어느 Max 에서나 된다. 끝나면 Blender 는 저절로 닫힌다.
global trts_sbgDetect

-- sbg_detect 애드온이 깔린 Blender 를 찾음 (Program Files\Blender Foundation\Blender x.y\blender.exe)
fn tsbg_findBlender = (
	local appd = systemTools.getEnvVariable "APPDATA"
	local roots = #("C:\\Program Files\\Blender Foundation\\")
	local pf = systemTools.getEnvVariable "ProgramFiles"
	if pf != undefined do appendIfUnique roots (pf + "\\Blender Foundation\\")
	local best = undefined, any = undefined
	for r in roots do (
		for sub in (getDirectories (r + "Blender*")) do (
			local exe = sub + "blender.exe"
			if doesFileExist exe do (
				any = exe
				local ver = substituteString (filenameFromPath (trimRight sub "\\")) "Blender " ""
				if appd != undefined and doesFileExist (appd + "\\Blender Foundation\\Blender\\" + ver + "\\scripts\\addons\\sbg_detect.py") do best = exe
			)
		)
	)
	if best != undefined then best else any
)

fn tsbg_readText f = ( try ((dotNetClass "System.IO.File").ReadAllText f) catch "" )

fn trts_sbgDetect = (
	local bl = tsbg_findBlender()
	if bl == undefined do return "ERROR: Blender 를 찾지 못했어요. 설치기를 먼저 실행하세요. (담당자에게 문의)"
	local ms = for o in objects where (superclassof o == GeometryClass and classof o != Biped_Object and classof o != BoneGeometry and not o.isHidden and not (matchPattern o.name pattern:"sbg_*")) collect o
	if ms.count == 0 do return "ERROR: 보이는 메쉬가 없어요. 몸 메쉬를 보이게 하고 다시 하세요."
	local d = (getDir #temp) + "\\sbg_detect\\job_" + (timeStamp() as string) + "\\"
	makeDir d all:true
	local fbx = d + "model.fbx"
	-- 1) 보이는 메쉬를 FBX 로
	local old = selection as array
	select ms
	try ( MaxBridge.exportFBX fbx selOnly:true anim:false ) catch ( try (exportFile fbx #noPrompt selectedOnly:true using:FBXEXP) catch () )
	if old.count > 0 then select old else clearSelection()
	if not (doesFileExist fbx) do return "ERROR: 모델을 FBX 로 내보내지 못했어요."
	-- 2) 작업 파일 → Blender 실행
	local jf = d + "job.json"
	local fs = createFile jf
	format "{\"fbx\": \"%\", \"model\": \"%\"}" (substituteString fbx "\\" "/") (substituteString maxFileName "\"" "") to:fs
	close fs
	local args = "--python-expr \"import sbg_detect; sbg_detect.start_job(r'" + (substituteString jf "\\" "/") + "')\""
	ShellLaunch bl args
	-- 3) 기다리기 (진행 막대, [취소] 가능)
	local pm = d + "points.ms", st = d + "status.txt"
	local t0 = timeStamp(), cancelled = false, err = ""
	progressStart "관절 자동 감지 중 - Blender 가 모델을 분석해요 (3~10분)"
	while not (doesFileExist pm) do (
		sleep 1
		local sec = (timeStamp() - t0) / 1000.0
		if not (progressUpdate ((100.0 * sec / (sec + 120.0)) as integer)) do ( cancelled = true; exit )
		if doesFileExist st do ( local s = tsbg_readText st; if matchPattern s pattern:"ERROR*" do ( err = s; exit ) )
		if sec > 1500 do ( err = "ERROR\n25분이 지나도 끝나지 않았어요."; exit )
	)
	progressEnd()
	if cancelled do return "ERROR: 감지를 취소했어요. (열린 Blender 창은 직접 닫아 주세요)"
	if err != "" do return ("ERROR: 관절 감지 실패 - " + (substituteString err "ERROR\n" ""))
	-- 4) 지정점 놓기
	fileIn pm
	local n = (for o in objects where matchPattern o.name pattern:"sbg_*" collect o).count
	local s = substituteString (tsbg_readText st) "OK\n" ""
	if s == "" do s = "지정점 " + (n as string) + "개를 놓았어요."
	s + "  (" + ((((timeStamp() - t0) / 1000) as integer) as string) + "초)"
)


-- TOS: 허벅지 트위스트가 작동하게 (Figure Mode 끄기 → Bip01 L/R Thigh → Twist Poses [Add] → [Default])
--   레퍼런스·새 Biped 모두 트위스트 포즈가 0개라 ThighTwist 가 허벅지를 100% 따라가기만 함. Default 뒤에는 비틀림을 나눠 받음
global trts_sbgThighTwistPoses, trts_sbgAnimFromFigure
fn trts_sbgDepth o = (local d = 0, p = o.parent; while p != undefined do (d += 1; p = p.parent); d)
-- Figure Mode 를 끄면 새 Biped 는 기본 애니 자세(발·발가락이 다름)가 나옴 → 0프레임 자세를 Figure 자세와 같게 (레퍼런스 파일처럼)
fn trts_sbgAnimFromFigure bip = (
	local c = bip.controller
	c.figureMode = true
	local nodes = for o in objects where classOf o == Biped_Object and not (matchPattern o.name pattern:"*Footsteps") and not (matchPattern o.name pattern:"*Twist*") collect o
	local maxD = 0, sorted = #()
	for o in nodes do (local d = trts_sbgDepth o; if d > maxD do maxD = d)
	for d = 0 to maxD do for o in nodes where (trts_sbgDepth o) == d do append sorted o
	local tms = for o in sorted collect o.transform
	c.figureMode = false
	with animate off at time 0 (
		for pass = 1 to 2 do for i = 1 to sorted.count do (
			local o = sorted[i], t = tms[i]
			try (biped.setTransform o #rotation t.rotation false) catch ()
			if o == bip or matchPattern o.name pattern:"*Foot" or (pass == 1 and (matchPattern o.name pattern:"*Pelvis" or matchPattern o.name pattern:"*Clavicle" or matchPattern o.name pattern:"*Thigh")) do try (biped.setTransform o #pos t.row4 false) catch ()
		)
	)
	local worst = 0.0
	for i = 1 to sorted.count do (local d = distance sorted[i].transform.row4 tms[i].row4; if d > worst do worst = d)
	"0프레임 자세 = Figure 자세 (최대 차이 " + (formattedPrint worst format:".3f") + ")  "
)
fn trts_sbgThighTwistPoses bip = (
	local c = bip.controller, out = ""
	c.figureMode = false
	for side in #("L", "R") do (
		local th = getNodeByName ("Bip01 " + side + " Thigh") exact:true
		if th == undefined then out += side + " Thigh 없음 "
		else (
			local r = try (biped.createTwistPose th; biped.setDefaultTwistPoses th; "OK") catch ("실패 " + getCurrentException())
			out += side + " Thigh 트위스트 포즈 " + (try ((biped.numTwistPoses th) as string) catch "?") + "개 " + r + "  "
		)
	)
	-- 트위스트 포즈를 만든 뒤 0프레임 자세를 Figure 자세와 같게 (마지막에 Figure Mode 끔)
	out += trts_sbgAnimFromFigure bip
	out
)
-- TOS: [Biped 생성] = 성별 레퍼런스 Biped 를 그대로 (레퍼런스 .fig: 구조·뼈 길이·굵기·자세·위치 모두 같음)
--   .fig = 레퍼런스 .max 의 Biped 를 figure 모드에서 저장한 것 (tos_bip_m.fig / tos_bip_f.fig, [레퍼런스 다시 읽기] 로 다시 만듦)
global trts_sbgBuildRef
-- Biped 오브젝트 속성 (Object Properties): Show Frozen in Gray 끔, Display as Box 켬, Renderable 끔
fn trts_sbgObjProps = (
	local n = 0
	for o in objects where classOf o == Biped_Object do (
		try (o.showFrozenInGray = false; o.boxMode = true; o.renderable = false; n += 1) catch ()
	)
	"오브젝트 속성: Biped " + (n as string) + "개 (Show Frozen in Gray 끔 · Display as Box · Renderable 끔)"
)
fn trts_sbgBuildRef ask:true = (
	-- TOS: 레퍼런스 = 직업_성별 (예: archer_f → tos_bip_archer_f.fig)
	local j = TosRig.job()
	if j == undefined do return "직업을 모르겠어요. 창의 [직업] 칸에서 Archer·Cleric·Mage·Warrior 중 하나를 고른 뒤 다시 누르세요.\n(자동 = 캐릭터 이름·파일 이름 앞부분 archer_f_... 또는 파일 위치의 Ver5_<직업>_<성별> 폴더)"
	local g = TosRig.gender()
	if g == undefined do return "취소했어요. (성별을 정하지 않음)"
	if not (TosRig.bipRefLoad()) do return ("오류: Biped 레퍼런스 파일이 없어요: " + TosRig.sbgDir() + "tos_bip_ref.ms")
	local ref = TOS_BipRef.get g job:j
	if ref == undefined do return ("오류: " + (TosRig.jobText j) + " " + (TosRig.genderText g) + " Biped 레퍼런스가 없어요. 창 아래 [레퍼런스 다시 읽기] 를 눌러 만드세요.")
	local fig = TosRig.dataFile ("tos_bip_" + ref.key + ".fig")
	if not (doesFileExist fig) do return ("오류: 레퍼런스 Biped 파일이 없어요: " + fig + "\n창 아래 [레퍼런스 다시 읽기] 를 눌러 만드세요.")
	local bips = for o in objects where classof o == Biped_Object collect o
	if bips.count > 0 and ask and not (queryBox ("이미 Biped 가 있어요 (뼈 " + (bips.count as string) + "개).\n지우고 " + (TosRig.jobText j) + " " + (TosRig.genderText g) + " 레퍼런스 Biped 로 새로 만들까요? (Ctrl+Z 가능)") title:"TOS_RigTools - Biped 생성") do return "취소했어요. (변경 없음)"
	local bip = undefined, ok = false, out = ""
	undo "TOS 레퍼런스 Biped" on (
		for b in bips where not (isDeleted b) do try ( delete b ) catch ()
		bip = biped.createNew ref.height 0 [0, 0, 0] arms:true neckLinks:ref.neck spineLinks:ref.spine legLinks:3 tailLinks:0 ponytail1Links:0 ponytail2Links:0 \
			fingers:ref.fingers fingerLinks:ref.fingerLinks toes:ref.toes toeLinks:ref.toeLinks ankleAttach:ref.ankle trianglePelvis:ref.triPelvis
		local c = bip.controller
		try ( c.rootName = "Bip01" ) catch ()
		c.figureMode = true
		try ( c.triangleNeck = ref.triNeck ) catch ()
		try ( c.prop2Exists = ref.prop2 ) catch ()
		try ( c.twists = true; c.thighTwistLinks = ref.twist[1]; c.calfTwistLinks = ref.twist[2]; c.forearmTwistLinks = ref.twist[3]; c.upperarmTwistLinks = ref.twist[4] ) catch ( out += "트위스트 설정 실패\n" )
		ok = biped.loadFigFile c fig
		try ( c.bodyType = ref.bodyType ) catch ()
		out += (trts_sbgThighTwistPoses bip) + "(Figure Mode 끔)\n"
		if trts_layerTidy != undefined do out += (try (trts_layerTidy()) catch ("레이어 정리 오류: " + getCurrentException())) + "\n"
		out += (trts_sbgObjProps()) + "\n"
	)
	if not ok do return (out + "오류: 레퍼런스 Biped(.fig)를 불러오지 못했어요: " + fig)
	local nb = (for o in objects where classof o == Biped_Object collect o).count
	select bip
	redrawViews()
	"Biped 생성 완료 (레퍼런스 그대로): 뼈 " + (nb as string) + "개\n" + \
		"기준: " + (TosRig.jobText j) + " " + (TosRig.genderText g) + " 레퍼런스 " + ref.file + " 의 Biped (구조·뼈 길이·굵기·자세·위치 같음, 레이어 " + ref.layer + ")\n" + \
		"파일: " + fig + "\n" + out + \
		"모델이 레퍼런스 몸과 다르면 [관절 다시 감지] → [수정] → [완료] 로 지정점에 맞춰 다시 만들 수 있어요."
)

fn trts_sbgBuild ask:true = (
	-- TOS: 성별 레퍼런스 (캐릭터 이름의 _m / _f → tos_bip_ref.ms). 감지(3~10분) 전에 먼저 정함
	local g = TosRig.gender()
	if g == undefined do return "취소했어요. (성별을 정하지 않음)"
	if not (TosRig.bipRefLoad()) do return ("오류: Biped 레퍼런스 파일이 없어요: " + TosRig.sbgDir() + "tos_bip_ref.ms")
	local ref = TOS_BipRef.get g job:(TosRig.job())
	if ref == undefined do return ("오류: " + (TosRig.genderText g) + " Biped 레퍼런스가 없어요. 창 아래 [레퍼런스 다시 읽기] 를 눌러 만드세요.")
	local need =#("sbg_Spine", "sbg_Neck", "sbg_Head", "sbg_L_Thigh", "sbg_L_Foot", "sbg_L_UpperArm", "sbg_L_Hand")
	local miss = for n in need where (trts_sbgPt n) == undefined collect n
	-- 지정점이 없지만 이 파일에 저장해 둔 지정점(지난 [완료] 때)이 있으면 그걸 다시 놓음
	if miss.count > 0 and (tsbg_restorePts()) > 0 do miss = for n in need where (trts_sbgPt n) == undefined collect n
	local detMsg = ""
	if miss.count > 0 do (
		if not (queryBox "노란 지정점(관절 위치)이 없어요.\n\n지금 관절 자동 감지를 할까요?\n- Blender 가 새로 열려서 모델을 분석해요 (3~10분)\n- 끝나면 Blender 는 저절로 닫히고 바로 Biped 를 만들어요" title:"TOS_RigTools - Biped 자동 생성") do
			return "취소했어요. (변경 없음)\n지정점을 직접 놓으려면 [관절 다시 감지] 를 누르세요."
		detMsg = trts_sbgDetect()
		if matchPattern detMsg pattern:"ERROR*" do return (substituteString detMsg "ERROR: " "")
		miss = for n in need where (trts_sbgPt n) == undefined collect n
		if miss.count > 0 do (
			local s = "감지 후에도 빠진 지정점이 있어요:"
			for n in miss do s += " " + n
			return (s + "\n점을 직접 놓은 뒤 다시 누르세요.")
		)
		local reds0 = for o in objects where (matchPattern o.name pattern:"sbg_*" and o.wirecolor == red) collect o.name
		if reds0.count > 0 do (
			local q = "감지가 끝났어요. 확인이 필요한 빨간 점이 " + (reds0.count as string) + "개 있어요:\n"
			for r in reds0 do q += "  " + r + "\n"
			q += "\n그래도 바로 Biped 를 만들까요?\n(아니오: 빨간 점을 옮긴 뒤 [Biped 생성] 을 다시 누르세요)"
			if not (queryBox q title:"TOS_RigTools - Biped 자동 생성") do return (detMsg + "\n\n빨간 점을 확인하고 [Biped 생성] 을 다시 누르세요.")
		)
		detMsg = "관절 자동 감지: " + detMsg + "\n"
	)
	local bips = for o in objects where classof o == Biped_Object collect o
	if bips.count > 0 do (
		if ask and not (queryBox ("이미 Biped 가 있어요 (뼈 " + (bips.count as string) + "개).\n지우고 지정점으로 새로 만들까요? (Ctrl+Z 가능)") title:"TOS_RigTools - Biped 자동 생성") do return "취소했어요. (변경 없음)"
	)
	local out = ""
	local bip = undefined
	undo "Biped 자동 생성" on (
		if bips.count > 0 do ( for b in bips where not (isDeleted b) do try ( delete b ) catch () )
		TSBG_data = undefined
		TSBG_fitThick = false; TSBG_thick = 1.0; TSBG_floor = true; TSBG_keepPts = true
		-- TOS 레퍼런스 구조 (남·여 같음: 척추 3 · 목 1 · 손가락 5×3 · 발가락 1×1 · Triangle Pelvis · 허벅지/아래팔 트위스트 1)
		--   Ankle Attach = 레퍼런스 값 (남 0.22 / 여 0.20), 뼈 굵기 = 레퍼런스 Biped 에서 잰 비율
		TSBG_twist = ref.twist
		TSBG_triPelvis = ref.triPelvis
		TSBG_thickRule = ref.thick
		local aa = ref.ankle
		bip = tsbg_buildBiped ref.spine ref.neck ref.fingers ref.fingerLinks ref.toes ref.toeLinks 1.0 true -90 aa ref.triNeck ref.prop2 false
		if bip != undefined do (
			TSBG_fingerLog = #()
			local lH = biped.getNode bip #larm link:4
			local lMir = lH.transform.pos.x < 0
			-- 손가락 지정점 (20개 모두 있을 때만)
			local fp = #(), okF = true
			for i = 1 to 5 do (
				local ch = for j = 1 to 4 collect (trts_sbgPt ("tsbg_f" + (i as string) + "_" + (j as string)))
				for p in ch where p == undefined do okF = false
				append fp ch
			)
			if okF then (
				TSBG_fingerPts = fp
				tsbg_fitHandEnd bip #larm lMir
				tsbg_fitHandEnd bip #rarm (not lMir)
				tsbg_fitFingers bip #lfingers lMir 5 3
				tsbg_fitFingers bip #rfingers (not lMir) 5 3
			) else (
				TSBG_fingerPts = #()
				out += "손가락 지정점이 없어 손가락은 Biped 기본 모양이에요.\n"
			)
			-- 뼈 굵기 (팀 표준 비율). 피봇은 움직이지 않음
			local th = tsbg_applyThickness bip
			if okF do (
				tsbg_fitFingers bip #lfingers lMir 5 3
				tsbg_fitFingers bip #rfingers (not lMir) 5 3
			)
			out += "뼈 굵기 " + (th[1] as string) + "개 맞춤 (TOS 레퍼런스 비율)"
			if th[2].count > 0 do (
				out += ", 피봇이 움직여서 건너뜀:"
				for s in th[2] do out += " " + (substring s 7 -1)
			)
			out += "\n"
			-- 발·발가락 (Ankle Attach 는 생성 때 지정점으로 계산)
			out += "Ankle Attach " + (formattedPrint aa format:".3f") + " (레퍼런스)\n"
			out += tsbg_fitFootToe bip
			-- 몸 모양(bodyType)을 레퍼런스대로 (맞추는 동안은 Classic)
			try ( bip.controller.bodyType = ref.bodyType ) catch ( out += "bodyType 설정 실패\n" )
			out += (trts_sbgThighTwistPoses bip) + "(Figure Mode 끔)\n"
			-- 레이어: Biped = Warrior_m_Bip / Warrior_Bip, 트위스트 = twist, Footsteps·Nub = nubs
			if trts_layerTidy != undefined do out += "\n" + (try (trts_layerTidy()) catch ("레이어 정리 오류: " + getCurrentException())) + "\n"
			out += (trts_sbgObjProps()) + "\n"
		)
	)
	if bip == undefined do return (out + "Biped 를 만들지 못했어요. 리스너(F11)를 확인하세요.")
	local nb = (for o in objects where classof o == Biped_Object collect o).count
	local tw = (for o in objects where (classof o == Biped_Object and matchPattern o.name pattern:"*Twist*") collect o).count
	out = detMsg + "Biped 생성 완료: 뼈 " + (nb as string) + "개 (트위스트 " + (tw as string) + "개), 피규어 모드\n" + "기준: " + (TosRig.genderText g) + " 레퍼런스 " + ref.file + "\n" + out
	local fMax = 0.0
	for s in TSBG_fingerLog do (
		local i = findString s "최대 오차 "
		if i != undefined do ( local v = ((filterString (substring s (i + 6) -1) "c")[1]) as float; if v != undefined and v > fMax do fMax = v )
	)
	if TSBG_fingerPts.count == 5 do out += "손가락 10개 맞춤 (최대 오차 " + (formattedPrint fMax format:".2f") + "cm)\n"
	local pv = tsbg_pivotReport bip
	out += "지정점↔피봇 차이(cm): " + pv[2] + "\n"
	if pv[1] > 0.05 do out += "※ 지정점과 피봇이 " + (formattedPrint pv[1] format:".2f") + "cm 어긋난 곳이 있어요.\n"
	local reds = for o in objects where (matchPattern o.name pattern:"sbg_*" and o.wirecolor == red) collect o.name
	if reds.count > 0 do (
		out += "\n※ 확인 필요 (빨간 점):"
		for r in reds do out += " " + r
		out += "\n   자동 감지가 의심스러운 곳이에요. 점을 옮긴 뒤 다시 [Biped 생성] 하세요.\n"
	)
	out += "\n고치려면 [수정] → 노란 점 옮기기 → [완료] (완료하면 지정점은 지워져요)"
	tsbg_savePts()
	select bip
	redrawViews()
	out
)

-- TOS [수정] / [완료]: 지금 Biped(레퍼런스로 만든 것)를 기준으로 관절 위치만 고침
--   [수정] 지금 Biped 관절 피봇마다 노란 점(sbg_*)을 놓고, Biped·메쉬는 잠시 얼림 → 점을 옮기기
--          가운데: sbg_Spine · sbg_Spine1 · sbg_Spine2 · sbg_Neck · sbg_Head · sbg_HeadEnd
--          왼쪽(L): sbg_L_Thigh · sbg_L_Calf · sbg_L_Foot · sbg_L_Clavicle · sbg_L_UpperArm · sbg_L_Forearm · sbg_L_Hand  (오른쪽은 L 을 거울로)
--   [완료] 얼린 것 풀기 → 지금 Biped 를 점 위치에 맞춤(뼈 방향·길이만, 굵기·손가락·발은 그대로) → 허벅지 트위스트 포즈·0프레임 자세 다시 → 점 삭제
global trts_sbgEditStart, trts_sbgEditDone, trts_sbgFitToPts
global trts_sbgEditCenter = #(#("sbg_Spine", "Spine"), #("sbg_Spine1", "Spine1"), #("sbg_Spine2", "Spine2"), #("sbg_Neck", "Neck"), #("sbg_Head", "Head"), #("sbg_HeadEnd", "HeadNub"))
global trts_sbgEditSide = #("Thigh", "Calf", "Foot", "Clavicle", "UpperArm", "Forearm", "Hand")

fn tsbg_ptNodes = ( for o in objects where (matchPattern o.name pattern:"sbg_*") collect o )

fn trts_sbgBipRoot = ( local r = for o in objects where classOf o == Biped_Object and o.parent == undefined collect o; if r.count > 0 then r[1] else undefined )

fn trts_sbgEditStart = (
	local bip = trts_sbgBipRoot()
	if bip == undefined do return "Biped 가 없어요. [Biped 생성] 을 먼저 누르세요."
	local pre = bip.name
	local pts = tsbg_ptNodes()
	if pts.count == 0 do (
		-- 지금 Biped 관절에 점 놓기 (Figure Mode 에서)
		bip.controller.figureMode = true
		local lay = LayerManager.getLayerFromName "sbg_debug"
		if lay == undefined do lay = LayerManager.newLayerFromName "sbg_debug"
		local h = 0.0
		try ( h = (getNodeByName (pre + " Neck")).transform.pos.z - (getNodeByName (pre + " L Foot")).transform.pos.z ) catch ( h = 50.0 )
		local sz = amax 1.0 (h * 0.04)
		local mk = for e in trts_sbgEditCenter collect #(e[1], pre + " " + e[2])
		for s in trts_sbgEditSide do append mk #("sbg_L_" + s, pre + " L " + s)
		for e in mk do (
			local n = getNodeByName e[2] exact:true
			if n != undefined do (
				local p = point pos:n.transform.pos name:e[1] size:sz cross:true box:true centermarker:false axistripod:false wirecolor:yellow
				lay.addNode p
			)
		)
		pts = tsbg_ptNodes()
	)
	local lay = LayerManager.getLayerFromName "sbg_debug"
	if lay != undefined do ( lay.on = true; lay.isFrozen = false )
	for p in pts do ( unhide p; unfreeze p )
	-- Biped·보이는 메쉬를 잠시 얼림 (원래 얼어 있던 건 건드리지 않음, 완료 때 되돌림)
	for o in objects where not (matchPattern o.name pattern:"sbg_*") and not o.isFrozen and not o.isHidden and \
		(classOf o == Biped_Object or superclassof o == GeometryClass) do (
		freeze o
		setUserProp o "sbg_tmpFrozen" true
	)
	clearSelection()
	max move
	redrawViews()
	"수정 중: 노란 점(지금 Biped 관절 위치)을 옮기세요. Biped·메쉬는 잠시 얼려 뒀어요.\n" + \
	"  가운데: Spine·Spine1·Spine2·Neck·Head·HeadEnd  /  왼쪽: Thigh·Calf·Foot·Clavicle·UpperArm·Forearm·Hand (오른쪽은 왼쪽을 거울로)\n" + \
	"다 옮기면 [완료] → 지금 Biped 를 점 위치에 맞춰 갱신하고 점은 지워요."
)

fn tsbg_unfreezeTmp = (
	for o in objects where (getUserProp o "sbg_tmpFrozen") == true do (
		unfreeze o
		setUserProp o "sbg_tmpFrozen" false
	)
)

-- 뼈 길이만(굵기 그대로) child 피봇까지 targetLen 이 되게
fn trts_sbgLenX node childNode targetLen = (
	for it = 1 to 3 do (
		local cur = distance node.transform.pos childNode.transform.pos
		if cur > 1e-4 and targetLen > 1e-4 and (abs (cur - targetLen)) > 0.002 do tsbg_scaleX node (targetLen / cur)
	)
)
-- 뼈의 X축을 targetPt 쪽으로 (tsbg_aim 과 같지만 아주 작은 각도도 돌림)
fn trts_sbgAim node targetPt = (
	for pass = 1 to 3 do (
		local d1 = normalize (targetPt - node.transform.pos), d0 = normalize node.transform.row1
		local dd = dot d0 d1
		if dd > 1 do dd = 1
		if dd < -1 do dd = -1
		local ang = acos dd
		if ang < 0.001 do exit
		local ax = cross d0 d1
		if (length ax) < 1e-9 do exit
		ax = normalize ax
		local r0 = biped.getTransform node #rotation
		local q = quat ang ax
		-- 회전 순서는 뼈마다 다를 수 있어 네 가지를 시험하고 가장 잘 맞는 것을 씀
		local cands = #(r0 * q, q * r0, r0 * (inverse q), (inverse q) * r0)
		local best = r0, bestDot = dd
		for cq in cands do (
			biped.setTransform node #rotation cq false
			local dn = dot (normalize node.transform.row1) d1
			if dn > bestDot do (best = cq; bestDot = dn)
		)
		biped.setTransform node #rotation best false
	)
)-- 다음 관절(childNode) 피봇이 pt 에 오도록 뼈 방향·길이를 맞춤. 이미 pt 에 있으면 그대로 (안 옮긴 점은 Biped 를 바꾸지 않음)
-- Biped 뼈 X축이 다음 관절과 조금 어긋난 경우(쇄골 등)도 맞도록 겨눌 곳을 보정하며 반복
fn trts_sbgBoneTo node childNode pt = (
	if pt != undefined and node != undefined and childNode != undefined and (distance childNode.transform.pos pt) > 0.005 do (
		local tgt = pt
		for it = 1 to 12 do (
			trts_sbgAim node tgt
			trts_sbgLenX node childNode (distance node.transform.pos pt)
			local er = pt - childNode.transform.pos
			if (length er) < 0.002 then exit else tgt += er
		)
	)
)-- 무릎·팔꿈치는 Biped 에서 경첩(로컬 Z 축으로만 굽음): 윗뼈를 자기 축으로 돌려 끝점(발목·손목)이 굽는 평면에 오게 한 뒤 아랫뼈를 겨눔
fn trts_sbgRoll parentNode K F = (
	local x = normalize parentNode.transform.row1
	local v = F - K
	local vp = v - x * (dot v x)
	if (length vp) < 1e-5 do return ok
	vp = normalize vp
	local z = normalize parentNode.transform.row3
	local zp = normalize (z - x * (dot z x))
	local zt = normalize (cross x vp)
	if (dot zt zp) < 0 do zt = -zt
	local dd = dot zp zt
	if dd > 1 do dd = 1
	if dd < -1 do dd = -1
	local ang = acos dd
	if ang < 0.001 do return ok
	local r0 = biped.getTransform parentNode #rotation
	for q in #((quat ang x), (quat -ang x)) do (
		biped.setTransform parentNode #rotation (r0 * q) false
		if (dot (normalize parentNode.transform.row3) zt) > 0.9999 do return ok
	)
	biped.setTransform parentNode #rotation r0 false
	ok
)
-- 윗뼈(upper)→가운데 관절(mid, 점 midPt)→끝 관절(endN, 점 endPt). 이미 점에 있으면 그대로
fn trts_sbgHinge upper mid endN midPt endPt = (
	if upper == undefined or mid == undefined or endN == undefined do return ok
	local K = if midPt != undefined then midPt else mid.transform.pos
	for it = 1 to 6 do (
		trts_sbgBoneTo upper mid K
		if endPt != undefined and (distance endN.transform.pos endPt) > 0.002 do (
			trts_sbgRoll upper K endPt
			trts_sbgAim mid endPt
			trts_sbgLenX mid endN (distance mid.transform.pos endPt)
		)
		if (distance mid.transform.pos K) < 0.002 and (endPt == undefined or (distance endN.transform.pos endPt) < 0.002) do exit
	)
)
fn trts_sbgMoveTo node pt = ( if pt != undefined and node != undefined and (distance node.transform.pos pt) > 0.002 do try ( biped.setTransform node #pos pt false ) catch () )

fn trts_sbgPtAt nm = ( local o = getNodeByName nm exact:true; if o == undefined then undefined else o.transform.pos )
-- 왼쪽 점 그대로(L) 또는 몸 가운데(cx) 기준 거울(R)
fn trts_sbgPtSide nm side cx = (
	local o = getNodeByName ("sbg_L_" + nm) exact:true
	if o == undefined then undefined else (if side == "R" then [2 * cx - o.transform.pos.x, o.transform.pos.y, o.transform.pos.z] else o.transform.pos)
)
fn trts_sbgFitToPts bip = (
	local pre = bip.name
	local c = bip.controller
	c.figureMode = true
	local cx = (getNodeByName (pre + " Pelvis") exact:true).transform.pos.x
	with animate off (
		-- 1) 골반 폭·위치: 허벅지 시작점
		local tL = trts_sbgPtSide "Thigh" "L" cx, tR = trts_sbgPtSide "Thigh" "R" cx
		local lT = getNodeByName (pre + " L Thigh") exact:true, rT = getNodeByName (pre + " R Thigh") exact:true
		if tL != undefined do (
			if (abs ((distance tL tR) - (distance lT.transform.pos rT.transform.pos))) > 0.002 do tsbg_fitPelvis bip (distance tL tR)
			local d = (tL + tR) * 0.5 - (lT.transform.pos + rT.transform.pos) * 0.5
			if (length d) > 0.002 do biped.setTransform bip #pos ((biped.getTransform bip #pos) + d) false
		)
		-- 2) 척추·목·머리
		local spN = for s in #("Spine", "Spine1", "Spine2") collect getNodeByName (pre + " " + s) exact:true
		local spP = for s in #("sbg_Spine", "sbg_Spine1", "sbg_Spine2") collect trts_sbgPtAt s
		local neck = getNodeByName (pre + " Neck") exact:true, head = getNodeByName (pre + " Head") exact:true
		local neckP = trts_sbgPtAt "sbg_Neck", headP = trts_sbgPtAt "sbg_Head", headEndP = trts_sbgPtAt "sbg_HeadEnd"
		trts_sbgMoveTo spN[1] spP[1]
		for i = 1 to 3 do (
			local nxN = if i < 3 then spN[i + 1] else neck
			local nxP = if i < 3 then spP[i + 1] else neckP
			trts_sbgBoneTo spN[i] nxN nxP
		)
		trts_sbgMoveTo neck neckP
		trts_sbgBoneTo neck head headP
		trts_sbgMoveTo head headP
		local nub = getNodeByName (pre + " HeadNub") exact:true
		if headEndP != undefined and nub != undefined do trts_sbgBoneTo head nub headEndP
		-- 3) 팔·다리 (L = 점, R = 거울)
		for side in #("L", "R") do (
			local th = getNodeByName (pre + " " + side + " Thigh") exact:true, ca = getNodeByName (pre + " " + side + " Calf") exact:true, ft = getNodeByName (pre + " " + side + " Foot") exact:true
			trts_sbgHinge th ca ft (trts_sbgPtSide "Calf" side cx) (trts_sbgPtSide "Foot" side cx)
			local cl = getNodeByName (pre + " " + side + " Clavicle") exact:true, ua = getNodeByName (pre + " " + side + " UpperArm") exact:true
			local fa = getNodeByName (pre + " " + side + " Forearm") exact:true, hd = getNodeByName (pre + " " + side + " Hand") exact:true
			trts_sbgMoveTo cl (trts_sbgPtSide "Clavicle" side cx)
			trts_sbgBoneTo cl ua (trts_sbgPtSide "UpperArm" side cx)
			trts_sbgHinge ua fa hd (trts_sbgPtSide "Forearm" side cx) (trts_sbgPtSide "Hand" side cx)
		)
	)
	-- 점 ↔ 관절 차이 보고
	local worst = 0.0, wn = ""
	for e in trts_sbgEditCenter do ( local q = trts_sbgPtAt e[1], n = getNodeByName (pre + " " + e[2]) exact:true; if q != undefined and n != undefined do ( local d = distance q n.transform.pos; if d > worst do (worst = d; wn = e[2]) ) )
	for side in #("L", "R") do for s in trts_sbgEditSide do ( local q = trts_sbgPtSide s side cx, n = getNodeByName (pre + " " + side + " " + s) exact:true; if q != undefined and n != undefined do ( local d = distance q n.transform.pos; if d > worst do (worst = d; wn = side + " " + s) ) )
	"점 ↔ 관절 최대 차이 " + (formattedPrint worst format:".3f") + " (" + wn + ")"
)

fn trts_sbgEditDone = (
	tsbg_unfreezeTmp()
	local pts = tsbg_ptNodes()
	if pts.count == 0 do return "점이 없어요. [수정] 을 먼저 누르세요."
	local bip = trts_sbgBipRoot()
	if bip == undefined do return "Biped 가 없어요. [Biped 생성] 을 먼저 누르세요."
	local r = "", tw = ""
	undo "TOS Biped 관절 수정" on (
		r = trts_sbgFitToPts bip
		tw = trts_sbgThighTwistPoses bip
		delete (tsbg_ptNodes())
		local lay = LayerManager.getLayerFromName "sbg_debug"
		if lay != undefined do (
			(LayerManager.getLayer 0).current = true
			local nodes = #()
			lay.nodes &nodes
			if nodes.count > 0 do delete nodes
			LayerManager.deleteLayerByName "sbg_debug"
		)
	)
	select bip
	redrawViews()
	"완료: 지금 Biped 를 점 위치에 맞춰 갱신했어요 (뼈 방향·길이만, 굵기·손가락·발 모양은 그대로). 점과 sbg_debug 레이어는 지웠어요.\n" + r + "\n" + tw + "(Figure Mode 끔)\nCtrl+Z 로 되돌릴 수 있어요. 다시 고치려면 [수정]."
)

-- 지정점 저장/복원: max 파일 안(rootNode AppData)에 보관 → [완료] 로 지운 뒤에도 [수정] 하면 다시 나옴
fn tsbg_savePts = (
	local s = ""
	for o in tsbg_ptNodes() where classof o == Point do (
		local p = o.pos, c = o.wirecolor
		s += o.name + "," + (formattedPrint p.x format:".4f") + "," + (formattedPrint p.y format:".4f") + "," + (formattedPrint p.z format:".4f") + "," + \
			((c.r as integer) as string) + "," + ((c.g as integer) as string) + "," + ((c.b as integer) as string) + "," + (formattedPrint o.size format:".3f") + ";"
	)
	if s != "" do setAppData rootNode 7731 s
	s.count
)

fn tsbg_restorePts = (
	local s = getAppData rootNode 7731
	if s == undefined or s == "" do return 0
	local lay = LayerManager.getLayerFromName "sbg_debug"
	if lay == undefined do lay = LayerManager.newLayerFromName "sbg_debug"
	lay.on = true
	lay.isFrozen = false
	local n = 0
	for e in (filterString s ";") do (
		local f = filterString e ","
		if f.count == 8 and (getNodeByName f[1] exact:true) == undefined do (
			local o = point pos:[f[2] as float, f[3] as float, f[4] as float] size:(f[8] as float) cross:true box:false centermarker:false axistripod:false \
				wirecolor:(color (f[5] as integer) (f[6] as integer) (f[7] as integer)) name:f[1]
			lay.addNode o
			n += 1
		)
	)
	redrawViews()
	n
)
