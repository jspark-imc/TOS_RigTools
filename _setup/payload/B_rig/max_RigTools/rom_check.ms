-- ======================================================================
--  ROM / 표정 체크 애니메이션 (3ds Max 2014, Biped + 45 얼굴 본)
--  frame 0 = 바인드 포즈. 짝수 10프레임마다 [포즈 / 바인드] 반복.
--  r9 | TosRomCheck.build()  -> 키 생성,  TosRomCheck.saveClips dir -> .bip + .xaf 저장
-- ======================================================================
global TosRomCheck
struct TosRomCheckStruct
(
	pre = "Bip01",
	bodyParts = #("Pelvis","Spine","Spine1","Spine2","Neck","Head",
		"L Clavicle","L UpperArm","L Forearm","L Hand","R Clavicle","R UpperArm","R Forearm","R Hand",
		"L Thigh","L Calf","L Foot","R Thigh","R Calf","R Foot"),
	bindRot = #(),     -- world rotation matrices at bind (same order as bodyParts)
	bindCom = undefined,
	faceBones = #(),
	faceBind = #(),
	faceVals = #(),    -- bind values of every pos/rot sub-controller (per face bone)
	log = "",

	fn node n = getNodeByName (pre + " " + n) exact:true,
	fn rotAbout ax ang = (local q = quat ang (normalize ax); q as matrix3),   -- world axis rotation (row convention)

	fn storeBind =
	(
		bindRot = for n in bodyParts collect (local o = node n; if o == undefined then undefined else (o.transform.rotationpart as matrix3))
		bindCom = (getNodeByName pre).transform.pos
		faceBones = for o in objects where classOf o == BoneGeometry and (matchPattern o.name pattern:"Bone_*") and \
			(findItem #("Bone_jaw","Bone_chin","Bone_tongue_01","Bone_tongue_02","Bone_tongue_03") o.name > 0 or \
			 matchPattern o.name pattern:"Bone_lip*" or matchPattern o.name pattern:"Bone_eye*" or matchPattern o.name pattern:"Bone_brow*" or \
			 matchPattern o.name pattern:"Bone_cheek*" or matchPattern o.name pattern:"Bone_nose*" or matchPattern o.name pattern:"Bone_sneer*") collect o
		faceBind = for o in faceBones collect (in coordsys parent o.transform)
		faceVals = for o in faceBones collect (
			local vv = #()
			for c in #(o.pos.controller, o.rotation.controller) do for k = 1 to c.numSubs do append vv (try (at time 0 c[k].controller.value) catch undefined)
			vv)
	),

	-- pose spec: array of #(part, axisMode, axis, angle)   axisMode: #world (vector) or #local (1=x,2=y,3=z of the posed node)
	fn keyBody t spec comDz:0 =
	(
		local acc = #()     -- accumulated world rotation per part (applied after bind)
		for i = 1 to bodyParts.count do acc[i] = matrix3 1
		sliderTime = t
		for i = 1 to bodyParts.count do
		(
			local o = node bodyParts[i]
			if o == undefined or bindRot[i] == undefined do continue
			-- parent accumulation
			local pidx = 0
			if o.parent != undefined do (local pn = substring o.parent.name (pre.count + 2) -1; pidx = findItem bodyParts pn)
			local R = if pidx > 0 then copy acc[pidx] else (matrix3 1)
			for s in spec where s[1] == bodyParts[i] do
			(
				local cur = bindRot[i] * R
				local ax = if s[2] == #world then s[3] else (if s[3] == 1 then cur.row1 else (if s[3] == 2 then cur.row2 else cur.row3))
				R = R * (rotAbout ax s[4])
			)
			acc[i] = R
			local m = bindRot[i] * R
			biped.setTransform o #rotation (m.rotationpart) true
		)
		local com = getNodeByName pre
		biped.setTransform com #pos (bindCom + [0,0,comDz]) true
	),

	fn keyAll o t vals:undefined =
	(
		-- explicit keys on every sub-track (auto-key skips values that did not change);
		-- with vals: the key value is set to the stored bind value exactly
		local n = 0
		for c in #(o.pos.controller, o.rotation.controller) do
			for k = 1 to c.numSubs do
			(
				n += 1
				try (
					local ctl = c[k].controller
					local key = addNewKey ctl t
					if vals != undefined and vals[n] != undefined do key.value = vals[n]
				) catch ()
			)
	),
	fn keyFace t ops =
	(
		sliderTime = t
		with animate on at time t
		(
			-- Max bones re-aim their parent when a child moves (auto align): off while keying
			local aa = for o in faceBones collect (try o.boneAutoAlign catch undefined)
			for o in faceBones do try (o.boneAutoAlign = false) catch ()
			for i = 1 to faceBones.count do keyAll faceBones[i] t vals:faceVals[i]
			for op in ops do
			(
				local o = getNodeByName op[1] exact:true
				if o == undefined do continue
				if op[2] == #rot then (local p = o.transform.pos; in coordsys world (rotate o (angleaxis op[4] op[3])); o.pos = p)
				else in coordsys world (move o op[3])
			)
			for i = 1 to faceBones.count where aa[i] != undefined do try (faceBones[i].boneAutoAlign = aa[i]) catch ()
		)
	),
	fn keyFaceBind t = keyFace t #(),
	fn clearKeys =
	(
		-- remove previous check keys (biped body + face bones) so build() can be run again
		local b = getNodeByName pre
		for o in (execute ("$'" + pre + "'...*")) where classOf o == Biped_Object do (try (biped.deleteKeys o.controller #allKeys) catch ())
		try (biped.deleteKeys b.controller #allKeys) catch ()
		-- [10/30] COM(Bip01) 의 수직·수평·회전 트랙은 따로 지워야 함 (위 한 줄로는 높이·이동 키가 남음)
		if b != undefined do for t in #("vertical","horizontal","turning") do (
			local tc = try (getProperty b.controller t) catch undefined
			if tc != undefined do try (biped.deleteKeys tc #allKeys) catch (try (deleteKeys tc #allKeys) catch ())
		)
		for o in faceBones do (try (deleteKeys o.controller #allKeys) catch ())
	),

	-- [eye r9, Claude 2026-10-24] 눈 감기 표준: 위·아래 본 끝 사이 열림각 a 에 부위별 비율 (멜리타 측정, tools\eyeclose)
	-- 눈꺼풀 본 끝이 눈꺼풀 가장자리에 맞춰져 있어야 함 (TosRig 눈 본 맞추기). amt 는 예전 호환용 (쓰지 않음)
	lidKUp = #(0.182, 0.456, 0.423),  -- [2026-10-24 r2] 블렌더 얼굴 본 생성 배치(작업자가 맞추기 편한 배치) 기준. 이전 TosRig 눈 본 맞추기 배치 기준: 위 0.272/0.720/0.575, 아래 0.263/0.395/0.536
	
	lidKDn = #(0.176, 0.250, 0.395),
	fn lidOps amt =
	(
		local ops = #()
		for s in #("L","R") do for i = 1 to 3 do
		(
			local suf = #("_in","","_out")[i]
			local u = getNodeByName ("Bone_eye_" + s + "_up" + suf), d = getNodeByName ("Bone_eye_" + s + "_dn" + suf)
			if u != undefined and d != undefined do
			(
				local a = acos (dot (normalize u.transform.row1) (normalize d.transform.row1))
				append ops #(u.name, #rot, [1,0,0], a * lidKUp[i])
				append ops #(d.name, #rot, [1,0,0], -a * lidKDn[i])
			)
		)
		ops
	),

	fn build =
	(
		local b = getNodeByName pre
		if b == undefined do return "Biped(Bip01)가 없어요"
		b.controller.figureMode = false
		sliderTime = 0
		storeBind()
		local X = [1,0,0], Y = [0,1,0], Z = [0,0,1]
		animationRange = interval 0 480
		-- ------------------------------------------------------------ body ROM
		-- (sign of each axis was chosen so that: arms go UP / FORWARD, hands come forward, head turns, feet go forward)
		local body = #(
			#(10,  #(#("L UpperArm",#world,Y, 120), #("R UpperArm",#world,Y,-120)), 0, "팔 위로"),
			#(30,  #(#("L UpperArm",#world,X, 75), #("R UpperArm",#world,X, 75)), 0, "팔 앞으로"),
			#(50,  #(#("L Forearm",#local,3, 120), #("R Forearm",#local,3, 120)), 0, "팔꿈치 굽힘"),
			#(70,  #(#("L Hand",#local,1, 80), #("R Hand",#local,1,-80)), 0, "손목 비틀기 +"),
			#(80,  #(#("L Hand",#local,1,-80), #("R Hand",#local,1, 80)), 0, "손목 비틀기 -"),
			#(100, #(#("Spine",#world,X,-25), #("Spine1",#world,X,-25), #("Spine2",#world,X,-20)), 0, "허리 숙이기"),
			#(110, #(#("Spine",#world,Y, 18), #("Spine1",#world,Y, 18), #("Spine2",#world,Y, 15)), 0, "허리 옆으로"),
			#(120, #(#("Spine",#world,Z, 22), #("Spine1",#world,Z, 22), #("Spine2",#world,Z, 18)), 0, "허리 비틀기"),
			#(140, #(#("Head",#world,Z, 60)), 0, "고개 돌리기"),
			#(150, #(#("Neck",#world,X,-15), #("Head",#world,X,-25)), 0, "고개 숙이기"),
			#(160, #(#("Neck",#world,Y, 12), #("Head",#world,Y, 20)), 0, "고개 기울이기"),
			#(180, #(#("L Thigh",#world,X, 80), #("R Thigh",#world,X,-30)), 0, "앞차기"),
			#(200, #(#("L Calf",#local,3, 110), #("R Calf",#local,3, 110)), 0, "무릎 굽힘"),
			#(210, #(#("L Thigh",#world,X, 90), #("R Thigh",#world,X, 90), #("L Calf",#local,3, 110), #("R Calf",#local,3, 110)), -30, "스쿼트"),
			#(230, #(#("L Thigh",#world,Y, 45), #("R Thigh",#world,Y,-45)), 0, "다리 옆으로")
		)
		local poseFrames = for p in body collect p[1]
		local bindFrames = #(0, 20, 40, 60, 90, 130, 170, 190, 220, 240, 300, 480)
		undo "ROM 체크 키" on
		(
			clearKeys()
			sliderTime = 0
			storeBind()   -- r8: 키를 지운 뒤(= 피규어 자세) 다시 바인드 기록
			for t in bindFrames do keyBody t #()
			for p in body do keyBody p[1] p[2] comDz:p[3]
			-- ---------------------------------------------------------- face (body stays at bind)
			for t in #(240, 300, 320, 340, 360, 380, 400, 420, 440, 460, 480) do keyFaceBind t
			local L = $'Bone_lip_L', R = $'Bone_lip_R'
			keyFace 310 #(#("Bone_jaw",#rot,X,24))
			keyFace 330 #(#("Bone_jaw",#rot,X,6), #("Bone_lip_L",#move,[0.35,0,0.1]), #("Bone_lip_R",#move,[-0.35,0,0.1]),
				#("Bone_lip_up",#move,[0,0,0.08]), #("Bone_lip_dn",#move,[0,0,-0.05]))
			keyFace 350 #(#("Bone_jaw",#rot,X,10), #("Bone_lip_L",#move,[-0.45,-0.25,0]), #("Bone_lip_R",#move,[0.45,-0.25,0]),
				#("Bone_lip_up",#move,[0,-0.3,0]), #("Bone_lip_dn",#move,[0,-0.3,0]), #("Bone_lip_L_up",#move,[-0.15,-0.25,0]), #("Bone_lip_R_up",#move,[0.15,-0.25,0]),
				#("Bone_lip_L_dn",#move,[-0.15,-0.25,0]), #("Bone_lip_R_dn",#move,[0.15,-0.25,0]))
			keyFace 370 (lidOps 0.82)
			keyFace 390 #(#("Bone_lip_L",#move,[0.25,0.15,0.4]), #("Bone_lip_R",#move,[-0.25,0.15,0.4]), #("Bone_lip_L_up_out",#move,[0.1,0.05,0.2]), #("Bone_lip_R_up_out",#move,[-0.1,0.05,0.2]),
				#("Bone_lip_L_dn_out",#move,[0.1,0.05,0.25]), #("Bone_lip_R_dn_out",#move,[-0.1,0.05,0.25]), #("Bone_cheek_L",#move,[0,-0.05,0.25]), #("Bone_cheek_R",#move,[0,-0.05,0.25]),
				#("Bone_cheek_L_dn",#move,[0.05,-0.05,0.2]), #("Bone_cheek_R_dn",#move,[-0.05,-0.05,0.2]))
			keyFace 410 #(#("Bone_brow_L_in",#move,[-0.15,-0.05,-0.35]), #("Bone_brow_R_in",#move,[0.15,-0.05,-0.35]), #("Bone_brow_L_mid",#move,[0,0,-0.15]), #("Bone_brow_R_mid",#move,[0,0,-0.15]),
				#("Bone_sneer_L",#move,[0,0,0.2]), #("Bone_sneer_R",#move,[0,0,0.2]), #("Bone_nose_L",#move,[0.05,0,0.12]), #("Bone_nose_R",#move,[-0.05,0,0.12]),
				#("Bone_lip_L",#move,[0,0,-0.15]), #("Bone_lip_R",#move,[0,0,-0.15]))
			keyFace 430 #(#("Bone_brow_L_in",#move,[0,0,0.5]), #("Bone_brow_R_in",#move,[0,0,0.5]), #("Bone_brow_L_mid",#move,[0,0,0.6]), #("Bone_brow_R_mid",#move,[0,0,0.6]),
				#("Bone_brow_L_out",#move,[0,0,0.4]), #("Bone_brow_R_out",#move,[0,0,0.4]), #("Bone_jaw",#rot,X,15))
			keyFace 450 #(#("Bone_brow_L_in",#move,[-0.1,0,0.35]), #("Bone_brow_R_in",#move,[0.1,0,0.35]), #("Bone_brow_L_out",#move,[0,0,-0.15]), #("Bone_brow_R_out",#move,[0,0,-0.15]),
				#("Bone_lip_L",#move,[0,0,-0.3]), #("Bone_lip_R",#move,[0,0,-0.3]), #("Bone_lip_dn",#move,[0,-0.1,0.08]))
			keyFace 470 #(#("Bone_sneer_L",#move,[0,0,0.3]), #("Bone_nose_L",#move,[0.05,0,0.2]), #("Bone_lip_L_up",#move,[0,0,0.25]), #("Bone_lip_L_up_out",#move,[0,0,0.2]),
				#("Bone_cheek_L_dn",#move,[0,0,0.15]))
		)
		sliderTime = 0
		-- notes on the timeline
		log = "ROM 0-240 / 표정 300-480 | "
		for p in body do log += (p[1] as string) + ":" + p[4] + " "
		log += "| 310 아 / 330 이 / 350 우 / 370 눈감기 / 390 웃음 / 410 화남 / 430 놀람 / 450 슬픔 / 470 찡그림(왼쪽)"
		log
	),

	fn saveClips dir =
	(
		makeDir dir all:true
		local bipF = dir + "\\rom_body_check.bip", xafF = dir + "\\rom_face_check.xaf"
		local r = ""
		try (biped.saveBipFile (getNodeByName pre).controller bipF; r += "bip OK " ) catch (r += "bip 실패: " + getCurrentException() + " ")
		try (LoadSaveAnimation.saveAnimation xafF faceBones #() #() animatedTracks:true; r += "xaf OK") catch (r += "xaf 실패: " + getCurrentException())
		r + " | " + dir
	)
)
TosRomCheck = TosRomCheckStruct()
