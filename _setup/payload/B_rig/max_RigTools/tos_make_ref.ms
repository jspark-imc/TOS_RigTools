-- ======================================================================
--  tos_make_ref.ms - 이 PC 의 TOS 레퍼런스 폴더(...\ani\Character\PC) → TOS_RigTools 2. Biped 기준 데이터
--  TOS_RigTools 창 [레퍼런스 다시 읽기] 가 부름: tos_makeRef <PC 폴더> <저장 폴더>
--  만드는 파일: tos_bip_ref.ms · tos_bip_<직업>_<성별>.fig (archer·cleric·mage·warrior × m·f = 8개, 2. Biped = 레퍼런스 Biped 그대로) + 여자 Dummy_Chast 값
--  Twist(3.)·세컨더리(4.)·스킨(5.) 데이터는 MTOS 와 같은 설치본을 그대로 씀 (여기서 만들지 않음)
--  레퍼런스를 차례로 열므로 지금 장면은 닫힘 (저장 안 함)
--  경로: <PC 폴더>\Ver*_<직업>_<성별>\costume\... (절대 경로 없음). 직업·성별마다 6th_greenschool 코스튬, 없으면 Biped 가 있는 첫 _set.max
-- ======================================================================
global tsbg_boneExtent, TSBG_noDialog, tosdb_make, tos_skinDB   -- SecBoneGen 에서 정의 (아래 함수들이 먼저 컴파일되므로 미리 선언)
global tosmr_jobs = #("archer", "cleric", "mage", "warrior")
global tosmr_prefCostume = "6th_greenschool"   -- 8개 직업·성별 폴더에 모두 있는 코스튬 (Biped 는 직업·성별마다 같음)
global tosmr_chastName = "Dummy_Chast"
fn tosmr_pick dir names =(local r = undefined; for n in names while r == undefined do if doesFileExist (dir + n) do r = dir + n; r)
global tsbg_boneExtent, TSBG_noDialog, tosdb_make, tos_skinDB   -- SecBoneGen 에서 정의 (아래 함수들이 먼저 컴파일되므로 미리 선언)
fn tosmr_heightOf bip = (local nk = biped.getNode bip #neck link:1, lF = biped.getNode bip #lleg link:3; nk.transform.pos.z - lF.transform.pos.z)
fn tosmr_bipRoot = (local r = for o in objects where classOf o == Biped_Object and o.parent == undefined collect o; if r.count > 0 then r[1] else undefined)

-- 성별 Biped 기준
fn tosmr_bipInfo g mf ruleKinds figPath =
(
	loadMaxFile mf useFileUnits:true quiet:true
	local b = tosmr_bipRoot()
	local c = b.controller
	c.figureMode = true
	local bt0 = c.bodyType
	local lay = b.layer.name
	local twl = (for o in objects where classOf o == Biped_Object and matchPattern o.name pattern:"*Twist*" collect o)
	local twLay = if twl.count > 0 then twl[1].layer.name else "twist"
	local h = tosmr_heightOf b
	-- 굵기는 도구가 맞추는 몸 모양(Classic)에서 잰다 (생성 뒤 레퍼런스 bodyType 으로 돌림)
	c.bodyType = 3
	local thick = #()
	for r in ruleKinds do
	(
		local n = getNodeByName ("Bip01 " + r[1]) exact:true
		if n != undefined do
		(
			local base = if r[2] == #len then (tsbg_boneExtent n (normalize n.transform.row1)) else h
			append thick #(r[1], r[2], (tsbg_boneExtent n (normalize n.transform.row2)) / base, (tsbg_boneExtent n (normalize n.transform.row3)) / base)
		)
	)
	c.bodyType = bt0
	-- 레퍼런스 Biped 그대로 (2. [Biped 생성] 이 불러옴)
	if not (biped.saveFigFile c figPath) do format "[tos_make_ref] .fig 저장 실패: %\n" figPath
	#(g, (filenameFromPath mf), c.height, h, c.spineLinks, c.neckLinks, c.fingers, c.fingerLinks, c.toes, c.toeLinks, \
		c.triangleNeck, c.trianglePelvis, (try c.prop2Exists catch false), \
		#(c.thighTwistLinks, c.calfTwistLinks, c.forearmTwistLinks, c.upperarmTwistLinks), c.ankleAttach, bt0, lay, twLay, thick)
)

-- 세컨더리 본: root 노드와 그 아래 전부 (layerPat 에 맞는 것만), 세계 행렬로
fn tosmr_secEntries root layerPat =
(
	local out = #(), q = #(root)
	while q.count > 0 do
	(
		local o = q[1]; deleteItem q 1
		if matchPattern o.layer.name pattern:layerPat or o == root do
			append out #(o.name, ((classOf o) as string), (if o.parent == undefined then "-" else o.parent.name), o.layer.name, (at time 0 o.transform), (trts_dims o), o.wirecolor, \
				#(o.boneEnable, o.boneFreezeLength, o.boneAutoAlign, o.boneScaleType))
		for ch in o.children where classOf ch == BoneGeometry do append q ch
	)
	out
)
-- 어깨(Clavicle) 세컨더리: Bone_Spine2_Base(부모 Spine2) 아래 가운데 줄 + L·R Clavicle 아래 줄들 (레퍼런스 costume_m_ep18darkenforcerpriest_set)
-- 반환: #("clavicle", 성별, 파일, "Spine2", Spine2 위치, 목~발목 높이, 본 엔트리, #(L Clavicle 위치, R Clavicle 위치)) 또는 undefined
fn tosmr_clavCapture g mf = (
	loadMaxFile mf useFileUnits:true quiet:true
	local b = tosmr_bipRoot()
	if b == undefined do return undefined
	b.controller.figureMode = true
	local base = getNodeByName "Bone_Spine2_Base" exact:true
	local lc = getNodeByName "Bip01 L Clavicle" exact:true, rc = getNodeByName "Bip01 R Clavicle" exact:true
	if base == undefined or lc == undefined or rc == undefined do return undefined
	local ents = tosmr_secEntries base "*Spine2*"
	for c in #(rc, lc) do for ch in c.children where classOf ch == BoneGeometry and matchPattern ch.name pattern:"Bone_Spine2_*" do join ents (tosmr_secEntries ch "*Spine2*")
	#("clavicle", g, (filenameFromPath mf), "Spine2", (getNodeByName "Bip01 Spine2" exact:true).transform.pos, (tosmr_heightOf b), ents, #(lc.transform.pos, rc.transform.pos))
)
fn tosmr_clavWrite outDir ents = (
	local fs = stringStream ""
	format "-- TOS_RigTools 4. 세컨더리 본 Clavicle(어깨) 레퍼런스 (tos_make_ref.ms 로 자동 생성 %)\n" (trts_stamp()) to:fs
	format "-- #(종류, 성별, 레퍼런스, 기준 관절, 기준 관절 위치, 목~발목 높이, 본 #(이름, 클래스, 부모, 레이어, 세계 행렬, 크기, 색, 본 속성), #(L Clavicle 위치, R Clavicle 위치))\n" to:fs
	format "global TOS_ClavRef = #(\n" to:fs
	for i = 1 to ents.count do format "\t%%\n" (trts_txt ents[i]) (if i < ents.count then "," else "") to:fs
	format ")\n" to:fs
	(dotNetClass "System.IO.File").WriteAllText (outDir + "tos_clavicle_ref.ms") (fs as string) (dotNetObject "System.Text.UTF8Encoding" true)
)
fn tosmr_chainOk root n =(local ok = root.children.count == 5; for ch in root.children do (local c = ch, k = 1; while c.children.count > 0 do (c = c.children[1]; k += 1); if k != n do ok = false); ok)

-- 직업·성별 폴더(Ver5_Archer_f 등)에서 레퍼런스 .max 하나 고르기: 6th_greenschool 코스튬의 _set.max → 없으면 Biped 가 있는 첫 _set.max
fn tosmr_jobDir pcDir job g = (
	local r = undefined
	for d in getDirectories (pcDir + "*_" + job + "_" + g) while r == undefined do r = d
	r
)
fn tosmr_hasBiped mf = (
	if not (loadMaxFile mf useFileUnits:true quiet:true) do return false
	(tosmr_bipRoot()) != undefined
)
fn tosmr_jobFile jd = (
	local c = jd + "costume\\"
	if not (doesFileExist c) do c = jd
	local pref = getFiles (c + tosmr_prefCostume + "\\*_set.max")
	if pref.count == 0 do pref = getFiles (c + tosmr_prefCostume + "\\*.max")
	local r = undefined
	for f in pref while r == undefined do if tosmr_hasBiped f do r = f
	if r == undefined do (
		for d in getDirectories (c + "*") while r == undefined do
			for f in getFiles (d + "*_set.max") while r == undefined do if tosmr_hasBiped f do r = f
	)
	r
)
-- 여자 가슴 더미 값: #(이름, 부모 Biped 뼈(Bip01 뒤), 상자 크기, 부모 기준 행렬, 레이어, 색) (지금 열린 레퍼런스에서)
fn tosmr_chastInfo = (
	local o = getNodeByName tosmr_chastName exact:true
	if o == undefined or o.parent == undefined do return undefined
	local pre = (tosmr_bipRoot()).name
	local pn = o.parent.name
	if not (matchPattern pn pattern:(pre + " *")) do return undefined
	#(o.name, (substring pn (pre.count + 2) -1), (try o.boxsize.x catch 5.0), (o.transform * (inverse o.parent.transform)), o.layer.name, o.wirecolor)
)

fn tos_makeRef bodyDir outDir =
(
	local pcDir = (trimRight bodyDir "\\") + "\\"
	if not (doesFileExist pcDir) do return ("오류: 레퍼런스 폴더가 없어요: " + pcDir)
	if TosRig == undefined or TosRigStd == undefined or trts_txt == undefined do return "오류: TOS_RigTools 가 읽혀 있지 않아요."
	-- 직업·성별마다 레퍼런스 파일
	local jobs = #()
	for j in tosmr_jobs do for g in #("m", "f") do (
		local jd = tosmr_jobDir pcDir j g
		if jd != undefined do append jobs #(j, g, jd)
	)
	if jobs.count == 0 do return ("오류: 직업별 폴더(Ver5_Archer_f 등)가 없어요: " + pcDir)
	makeDir outDir all:true
	outDir = (trimRight outDir "\\") + "\\"
	TSBG_noDialog = true
	fileIn (TosRig.sbgDir() + "SecBoneGen_v0.11_step1_biped.ms")
	TSBG_noDialog = false
	-- GE 정답 리그에서 쓰던 굵기 규칙 이름·기준(#h = 키, #len = 그 뼈 길이). 값은 레퍼런스에서 다시 잼
	local ruleKinds = #(#("Head", #h), #("L Calf", #h), #("L Clavicle", #h), #("L Finger0", #h), #("L Finger01", #h), #("L Finger02", #h), \
		#("L Finger1", #len), #("L Finger11", #len), #("L Finger12", #len), #("L Finger2", #h), #("L Finger21", #h), #("L Finger22", #len), \
		#("L Finger3", #len), #("L Finger31", #len), #("L Finger32", #len), #("L Finger4", #h), #("L Finger41", #len), #("L Finger42", #len), \
		#("L Forearm", #h), #("L Hand", #h), #("L Thigh", #len), #("L UpperArm", #len), #("Neck", #h), #("Pelvis", #len), \
		#("Spine", #h), #("Spine1", #h), #("Spine2", #h))
	local log = "", ents = #(), chastStd = undefined, miss = #()
	for e in jobs do (
		local mf = tosmr_jobFile e[3]
		if mf == undefined then append miss (e[1] + "_" + e[2])
		else (
			local key = e[1] + "_" + e[2]
			local bi = tosmr_bipInfo (e[2] as name) mf ruleKinds (outDir + "tos_bip_" + key + ".fig")   -- 이 파일이 열린 채로 끝남
			local ch = if e[2] == "f" then (tosmr_chastInfo()) else undefined
			if ch != undefined and chastStd == undefined do chastStd = ch
			append ents #(key, bi, ch)
			log += "  " + key + ": " + (filenameFromPath mf) + " (Biped 레이어 " + bi[17] + (if ch != undefined then (", " + ch[1] + " 있음") else "") + ")\n"
		)
	)
	-- 여자인데 레퍼런스에 Dummy_Chast 가 없는 직업: 다른 여자 레퍼런스의 값 (레이어 twist)
	local fs = stringStream ""
	format "-- TOS_RigTools 2. Biped 자동 생성 기준 (tos_make_ref.ms 로 자동 생성 %)\n" (trts_stamp()) to:fs
	format "-- #(직업_성별, #(성별, 레퍼런스, Biped 키, 목~발목 높이, 척추, 목, 손가락, 손가락 마디, 발가락, 발가락 마디, Triangle Neck, Triangle Pelvis, Prop2, 트위스트 #(허벅지 종아리 아래팔 위팔), Ankle Attach, bodyType, Biped 레이어, 트위스트 레이어, 굵기), 여자 Dummy_Chast #(이름, 부모 뼈, 상자 크기, 부모 기준 행렬, 레이어, 색) 또는 undefined)\n" to:fs
	format "global TOS_BipRefData = #(\n" to:fs
	for i = 1 to ents.count do (
		local x = ents[i]
		if x[3] == undefined and chastStd != undefined and (matchPattern x[1] pattern:"*_f") do x[3] = #(chastStd[1], chastStd[2], chastStd[3], chastStd[4], "twist", chastStd[6])
		format "\t%%\n" (trts_txt x) (if i < ents.count then "," else "") to:fs
	)
	format ")\n" to:fs
	local hdr = "struct TOS_BipRefItem (key, job, g, file, height, h, spine, neck, fingers, fingerLinks, toes, toeLinks, triNeck, triPelvis, prop2, twist, ankle, bodyType, layer, twistLayer, thick, chast)\n"
	local getFn = "struct TOS_BipRefStruct (\n" + \
		"\tfn mk x = (local d = x[2]; local p = filterString x[1] \"_\"; TOS_BipRefItem key:x[1] job:p[1] g:d[1] file:d[2] height:d[3] h:d[4] spine:d[5] neck:d[6] fingers:d[7] fingerLinks:d[8] toes:d[9] toeLinks:d[10] triNeck:d[11] triPelvis:d[12] prop2:d[13] twist:d[14] ankle:d[15] bodyType:d[16] layer:d[17] twistLayer:d[18] thick:d[19] chast:x[3]),\n" + \
		"\t-- 직업_성별 (job 이 없거나 그 직업 데이터가 없으면 같은 성별 첫 데이터)\n" + \
		"\tfn get g job:undefined = (local r = undefined, k = if job != undefined then (job + \"_\" + (g as string)) else \"\"; for x in TOS_BipRefData while r == undefined do if x[1] == k do r = x; if r == undefined do for x in TOS_BipRefData while r == undefined do if x[2][1] == g do r = x; if r == undefined then undefined else (mk r)),\n" + \
		"\tfn keys = (for x in TOS_BipRefData collect x[1])\n)\n"
	(dotNetClass "System.IO.File").WriteAllText (outDir + "tos_bip_ref.ms") (hdr + (fs as string) + getFn + "global TOS_BipRef = TOS_BipRefStruct()\n") (dotNetObject "System.Text.UTF8Encoding" true)
	-- 5. 스킨: TOS 레퍼런스 웨이트 모음 (tos_skindb_m/f.txt, 후보 = tos_skindb.ms 의 상대 경로)
	fileIn (TosRig.sbgDir() + "tos_skindb.ms")
	local dbLog = (tosdb_make pcDir outDir #m) + "\n" + (tosdb_make pcDir outDir #f) + "\n"
	tos_skinDB = #(undefined, undefined)
	-- 5. 스킨: 관절 부위 웨이트 학습 (tos_joint_m/f.ms, 직업 폴더마다 스킨 있는 _set.max 10개)
	fileIn (TosRig.sbgDir() + "tos_joint.ms")
	dbLog += (tosjt_make pcDir outDir #m) + "\n" + (tosjt_make pcDir outDir #f) + "\n"
	TOS_JointData_m = undefined; TOS_JointData_f = undefined
	resetMaxFile #noPrompt
	"레퍼런스를 다시 읽었어요 (" + pcDir + ")\n" + "tos_bip_ref.ms · tos_bip_<직업>_<성별>.fig " + (ents.count as string) + "개:\n" + log + dbLog + \
		(if miss.count > 0 then ("주의: Biped 가 있는 레퍼런스를 못 찾음: " + (miss as string) + "\n") else "") + \
		(if chastStd == undefined then "주의: 여자 레퍼런스에서 Dummy_Chast 를 못 찾았어요 (설치본 값을 써요)\n" else "") + \
		"Twist·세컨더리 기준은 설치본(MTOS 와 같음)을 그대로 써요."
)
