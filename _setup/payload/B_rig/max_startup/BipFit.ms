-- BipFit.ms v0.6 (3ds Max 2014)
-- v0.6: 관절 맞추기에서 손·손가락 비틀림을 손바닥 면에 맞춤 (Y = 손바닥 쪽, Z = 손 폭), 엄지는 Biped 기본 엄지 축을 실제 엄지 방향으로 돌려 사용. 팔꿈치가 거의 곧거나 뒤로 꺾였으면 기본 축 사용. Biped 만들기 기본 = triangleNeck 켬, trianglePelvis 끔(팀 기준). 기존 파일은 test\anim\BipHandFix_test.ms로 수정
-- Biped Figure Mode 관절 맞추기: 기존 뼈대(Rigify ORG- 또는 Bip 이름 뼈대) 관절 위치에 Biped를 맞춘다.
-- 사용: fileIn "C:\\claude\\max_blender\\BipFit.ms" 후 Claude > BipFit, 또는 BipFit.fit $Bip001 1 "Bip01"
-- v0.5: 창 제목·연결 본에 버전 기록, 긴 작업 진행 표시줄(취소 가능), LMA 추출 전 점검 버튼
-- v0.4: AccuRIG/CC(CC_Base_) 뼈대 프리셋, AccuRIG UE5(UE 이름) 프리셋 추가
-- v0.3: Biped 자동 생성(뼈대 방향), 맞추기 때 골반 X 스케일로 척추 시작 높이 보정, 연결 시 매핑 없는 DEF 규칙 연결, 스킨 본 정리
global BipFit
global BipFit_version = "0.6"
-- Load Envelopes 창 자동 확인 (Match by Name → OK)
global BipFit_envAutoOK
fn BipFit_envAutoOK = (
	local h = DialogMonitorOPS.GetWindowHandle()
	local tt = UIAccessor.GetWindowText h
	if tt != undefined and tt == "Load Envelopes" do (
		UIAccessor.PressButtonByName h "Match by Name"
		UIAccessor.PressButtonByName h "OK")
	true)
fn BipFit_isBiped o = classOf o == Biped_Object

struct BipFitStruct
(
	headFactor = 2.2,
	prevToe = 4.7,      -- 발가락 끝 정보가 없을 때 길이
	footDir = [0,-1,0],
	keepWidth = false,   -- 머리 끝 정보가 없을 때: 목 길이 x 이 값
	tipFactor  = 0.85,  -- 끝마디(손가락, 발가락) 길이 = 앞마디 x 이 값
	log = "",
	-- 얼굴·머리카락 계열 DEF 본 이름(앞부분): 매핑에 없으면 Head에 붙임
	faceNames = #("ear","teeth","nose","eye_master","eye","eye_iris","lid","lid_glue","chin","tongue","jaw","jaw_master","lip","brow","cheek","forehead","temple","hair","hair1","hair2","hair3"),

	-- 진행 표시: Skin 작업 중에는 progressStart를 쓰면 Skin 패널이 잠겨 멈추므로 상태줄 글자 + Esc 취소로 대신함
	fn tick msg = (replacePrompt (msg + "   (Esc: 취소)"); windows.processPostedMessages(); keyboard.escPressed),

	fn nd nm = (if nm == undefined then undefined else getNodeByName nm exact:true),

	-- 프리셋별 매핑: #(Biped 파트 이름, 시작 관절 노드, 끝 관절 노드)  {S}=L/R  {s}=.L/.R
	fn rigifyMap =
	(
		local m = #(
			#("Spine","ORG-spine.001","ORG-spine.002"), #("Spine1","ORG-spine.002","ORG-spine.003"),
			#("Spine2","ORG-spine.003","ORG-spine.004"), #("Neck","ORG-spine.004","ORG-spine.006"),
			#("Head","ORG-spine.006",undefined) )
		local fing = #("thumb","f_index","f_middle","f_ring","f_pinky")
		local side = #(#("{S} Clavicle","ORG-shoulder{s}","ORG-upper_arm{s}"), #("{S} UpperArm","ORG-upper_arm{s}","ORG-forearm{s}"),
			#("{S} Forearm","ORG-forearm{s}","ORG-hand{s}"), #("{S} Hand","ORG-hand{s}","ORG-f_middle.01{s}"),
			#("{S} Thigh","ORG-thigh{s}","ORG-shin{s}"), #("{S} Calf","ORG-shin{s}","ORG-foot{s}"),
			#("{S} Foot","ORG-foot{s}","ORG-toe{s}"), #("{S} Toe0","ORG-toe{s}",undefined))
		for f = 1 to 5 do for k = 1 to 3 do (
			local suf = if k == 1 then "" else ((k-1) as string)
			local a = "ORG-" + fing[f] + ".0" + (k as string) + "{s}"
			local b = if k < 3 then "ORG-" + fing[f] + ".0" + ((k+1) as string) + "{s}" else undefined
			append side #("{S} Finger" + ((f-1) as string) + suf, a, b))
		for sd in #(#("L",".L"), #("R",".R")) do for e in side do (
			local r = for x in e collect (if x == undefined then undefined else substituteString (substituteString x "{S}" sd[1]) "{s}" sd[2])
			append m r)
		m
	),

	-- AccuRIG / Character Creator 뼈대 (CC_Base_ 이름) → Biped 파트
	fn ccMap =
	(
		local m = #(
			#("Spine","CC_Base_Waist","CC_Base_Spine01"), #("Spine1","CC_Base_Spine01","CC_Base_Spine02"),
			#("Spine2","CC_Base_Spine02","CC_Base_NeckTwist01"), #("Neck","CC_Base_NeckTwist01","CC_Base_Head"),
			#("Head","CC_Base_Head",undefined) )
		local fing = #("Thumb","Index","Mid","Ring","Pinky")
		local side = #(#("{S} Clavicle","CC_Base_{S}_Clavicle","CC_Base_{S}_Upperarm"), #("{S} UpperArm","CC_Base_{S}_Upperarm","CC_Base_{S}_Forearm"),
			#("{S} Forearm","CC_Base_{S}_Forearm","CC_Base_{S}_Hand"), #("{S} Hand","CC_Base_{S}_Hand","CC_Base_{S}_Mid1"),
			#("{S} Thigh","CC_Base_{S}_Thigh","CC_Base_{S}_Calf"), #("{S} Calf","CC_Base_{S}_Calf","CC_Base_{S}_Foot"),
			#("{S} Foot","CC_Base_{S}_Foot","CC_Base_{S}_ToeBase"), #("{S} Toe0","CC_Base_{S}_ToeBase",undefined))
		for f = 1 to 5 do for k = 1 to 3 do (
			local suf = if k == 1 then "" else ((k-1) as string)
			local a = "CC_Base_{S}_" + fing[f] + (k as string)
			local b = if k < 3 then "CC_Base_{S}_" + fing[f] + ((k+1) as string) else undefined
			append side #("{S} Finger" + ((f-1) as string) + suf, a, b))
		for sd in #("L","R") do for e in side do (
			local r = for x in e collect (if x == undefined then undefined else substituteString x "{S}" sd)
			append m r)
		m
	),

	-- AccuRIG UE5 프리셋 / UE 마네킹 이름 (pelvis, spine_01~05, upperarm_l ...) → Biped 파트
	fn ueMap =
	(
		local m = #(
			#("Spine","spine_01","spine_03"), #("Spine1","spine_03","spine_04"),
			#("Spine2","spine_04","neck_01"), #("Neck","neck_01","head"),
			#("Head","head",undefined) )
		local fing = #("thumb","index","middle","ring","pinky")
		local side = #(#("{S} Clavicle","clavicle_{s}","upperarm_{s}"), #("{S} UpperArm","upperarm_{s}","lowerarm_{s}"),
			#("{S} Forearm","lowerarm_{s}","hand_{s}"), #("{S} Hand","hand_{s}","middle_01_{s}"),
			#("{S} Thigh","thigh_{s}","calf_{s}"), #("{S} Calf","calf_{s}","foot_{s}"),
			#("{S} Foot","foot_{s}","ball_{s}"), #("{S} Toe0","ball_{s}",undefined))
		for f = 1 to 5 do for k = 1 to 3 do (
			local suf = if k == 1 then "" else ((k-1) as string)
			local a = fing[f] + "_0" + (k as string) + "_{s}"
			local b = if k < 3 then fing[f] + "_0" + ((k+1) as string) + "_{s}" else undefined
			append side #("{S} Finger" + ((f-1) as string) + suf, a, b))
		for sd in #(#("L","l"), #("R","r")) do for e in side do (
			local r = for x in e collect (if x == undefined then undefined else substituteString (substituteString x "{S}" sd[1]) "{s}" sd[2])
			append m r)
		m
	),


	-- 스킨 본 이름 패턴 (연결 대상)
	fn skinPattern preset = (if preset == 3 then "CC_Base_*" else "DEF-*"),

	-- Bip 이름 뼈대(예: Bip01, FBX로 들어온 일반 본) → 같은 이름 파트로 맞춤
	fn bipMap pre =
	(
		local m = #(#("Spine","Spine","Spine1"), #("Spine1","Spine1","Spine2"), #("Spine2","Spine2","Neck"), #("Neck","Neck","Head"), #("Head","Head",undefined))
		local side = #(#("{S} Clavicle","{S} UpperArm"), #("{S} UpperArm","{S} Forearm"), #("{S} Forearm","{S} Hand"), #("{S} Hand","{S} Finger2"),
			#("{S} Thigh","{S} Calf"), #("{S} Calf","{S} Foot"), #("{S} Foot","{S} Toe0"), #("{S} Toe0",undefined))
		for f = 0 to 4 do (append side #("{S} Finger" + (f as string), "{S} Finger" + (f as string) + "1"); append side #("{S} Finger" + (f as string) + "1", "{S} Finger" + (f as string) + "2"); append side #("{S} Finger" + (f as string) + "2", undefined))
		for e in side do append m #(e[1], e[1], e[2])
		local out = #()
		for sd in #("L","R") do for e in m do (
			if (findString e[1] "{S}") != undefined or sd == "L" do
				append out (for i = 1 to 3 collect (if e[i] == undefined then undefined else (if i == 1 then "" else pre + " ") + substituteString e[i] "{S}" sd)))
		out
	),

	-- v0.6.1: bipMap보다 뒤에 정의해야 프리셋 2(Bip 이름 뼈대)가 동작함
	fn mapFor preset prefix = (if preset == 1 then rigifyMap() else if preset == 3 then ccMap() else if preset == 4 then ueMap() else bipMap prefix),
	fn jointPos n = n.transform.pos,
	fn entry mp nm = (for e in mp where e[1] == nm collect e)[1],

	-- 끝 관절이 없을 때 끝점 추정
	fn tailOf n tailNode prevLen part =
	(
		if tailNode != undefined then jointPos tailNode
		-- FBX로 들어온 BoneGeometry는 길이가 0에 가깝고 방향(X축)도 실제 뼈 방향이 아닐 수 있음 -> 의미 있는 길이일 때만 사용
		-- v0.6: 뼈 X축이 실제 뼈 방향(부모→나)과 30° 이내일 때만 사용 (CC 뼈대는 X축이 뼈 방향과 90° 어긋남 → 손가락 끝이 꺾였음)
		else if classOf n == BoneGeometry and n.length > prevLen * 0.2 and (n.parent == undefined or (dot (normalize n.transform.row1) (normalize (jointPos n - jointPos n.parent))) > 0.866) then (n.transform.pos + n.transform.row1 * n.length)
		else if (matchPattern part pattern:"Head") then (jointPos n + [0,0,1] * prevLen * headFactor)
		else (
			local p = n.parent
			local d = if p != undefined then normalize (jointPos n - jointPos p) else [0,0,1]
			jointPos n + d * prevLen * tipFactor)
	),

	-- Biped 링크 하나를 시작→끝 방향, 길이로 맞춤 (X축 = 길이 방향, 현재 Z축으로 비틀림 유지)
	fn setLinkOnce b head tail L zHint:undefined =
	(
		local x = normalize (tail - head)
		local cur = b.transform
		local hint = if zHint != undefined then zHint else cur.row3
		local z = hint - (dot hint x) * x
		if length z < 0.001 do (hint = cur.row2; z = hint - (dot hint x) * x)
		z = normalize z
		local y = normalize (cross z x)
		local m = matrix3 x y z head
		biped.setTransform b #rotation m.rotation false
		local s = biped.getTransform b #scale
		-- 두께(Y, Z)는 원래 길이 대비 비율 유지
		-- Biped 팔다리·손가락·목·쇄골은 스케일 XYZ가 같아야 기본 두께가 됨. 척추·머리·발은 몸 폭이라 유지
		local keep = keepWidth or (matchPattern b.name pattern:"*Spine*") or (matchPattern b.name pattern:"*Head") or (matchPattern b.name pattern:"*Foot")
		if keep then biped.setTransform b #scale [L, s.y, s.z] false
		else biped.setTransform b #scale [L, L, L] false
		L
	),

	fn setLink b head tail zHint:undefined =
	(
		local L = distance head tail
		if L < 0.0001 do return 0
		-- Biped가 회전을 살짝 보정하는 경우가 있어 끝점 오차만큼 목표를 옮겨 3번까지 다시 맞춤
		local aim = tail
		for it = 1 to 4 do (
			setLinkOnce b head aim L zHint:zHint
			local got = b.transform.pos + b.transform.row1 * L
			if (distance got tail) < 0.01 do exit
			aim = aim + (tail - got)
		)
		L
	),

	fn fit bipRoot preset prefix:"Bip01" =
	(
		log = ""
		local ctl = bipRoot.controller
		local bn = bipRoot.name
		local map = mapFor preset prefix
		ctl.figureMode = true
		-- 1) 무게중심 + 골반 폭 (허벅지 시작점 기준)
		local tl = nd (entry map "L Thigh")[2]; local tr = nd (entry map "R Thigh")[2]
		if tl == undefined or tr == undefined do (log += "허벅지 노드를 찾을 수 없음\n"; return log)
		local hipW = distance (jointPos tl) (jointPos tr)
		local com = (jointPos tl + jointPos tr) / 2.0
		biped.setTransform bipRoot #pos com false
		local pel = getNodeByName (bn + " Pelvis")
		local ps = biped.getTransform pel #scale
		biped.setTransform pel #scale [ps.x, ps.y, hipW] false
		-- 척추 시작 높이: Biped는 Pelvis 스케일 X가 Spine 시작점 높이를 결정(선형). 목표에 맞춰야 첫 Spine 링크가 뒤집히지 않음
		local spB = getNodeByName (bn + " Spine")
		local spT = nd (entry map "Spine")[2]
		if spB != undefined and spT != undefined do (
			local want = (jointPos spT).z - com.z
			local have = spB.transform.pos.z - bipRoot.transform.pos.z
			if want > 0.01 and have > 0.01 do (
				local s2 = biped.getTransform pel #scale
				biped.setTransform pel #scale [s2.x * want / have, s2.y, s2.z] false
				log += "골반 X 스케일 보정: 척추 시작 높이 " + (formattedPrint have format:".2f") + " -> " + (formattedPrint want format:".2f") + "\n"))
		-- 무릎 보정: 무릎 관절이 엉덩이-발목 선보다 뒤에 있으면(Biped 무릎은 앞으로만 굽음) 선 위 살짝 앞으로 옮김
		local kneeOv = #()
		local lv0 = (jointPos tl) - (jointPos tr)
		local fw0 = normalize (cross [lv0.x, lv0.y, 0] [0,0,1])
		for sd in #("L","R") do (
			local th = entry map (sd + " Thigh"); local ca = entry map (sd + " Calf")
			if th != undefined and ca != undefined do (
				local hpN = nd th[2]; local knN = nd th[3]; local anN = nd ca[3]
				if hpN != undefined and knN != undefined and anN != undefined do (
					local HP = jointPos hpN; local KN = jointPos knN; local AN = jointPos anN
					local ax = normalize (AN - HP)
					local pr = HP + ax * (dot (KN - HP) ax)
					local f = normalize (fw0 - ax * (dot fw0 ax))
					local dd = dot (KN - pr) f
					local minD = (distance HP AN) * 0.01
					if dd < minD do (
						append kneeOv #(sd, pr + f * minD)
						log += sd + " 무릎이 뒤로 " + (formattedPrint (minD - dd) format:".2f") + " 꺾여 있어 보정\n"))))
		-- 2) 위에서 아래 순서로 링크 맞춤
		local miss = #()
		for pass = 1 to 2 do (
		local prevLen = 10.0
		miss = #()
		for e in map do (
			local b = getNodeByName (bn + " " + e[1])
			local hn = nd e[2]; local tn = nd e[3]
			if b == undefined or hn == undefined then append miss e[1]
			else (
				local h = jointPos hn
				local sdK = e[1][1]
				local kOv = (for kk in kneeOv where kk[1] == sdK collect kk[2])[1]
				if kOv != undefined and (matchPattern e[1] pattern:"* Calf") do h = kOv
				if (matchPattern e[1] pattern:"*Clavicle") or (matchPattern e[1] pattern:"*Finger?") do try (biped.setTransform b #pos h false) catch()
				if matchPattern e[1] pattern:"* Foot" then (
					-- Biped 발: 발목에서 바닥으로 수직, 길이 = 발목 높이, 발 길이(Y)는 발가락 위치가 맞도록 반복 보정
					local toeN = tn
					local ground = if toeN != undefined then (jointPos toeN).z else 0.0
					setLink b h [h.x, h.y, ground]
					if toeN != undefined do (
						local toeB = getNodeByName (bn + " " + (substituteString e[1] "Foot" "Toe0"))
						local tp = jointPos toeN
						for it = 1 to 4 where toeB != undefined do (
							local hb = toeB.transform.pos
							local want = length ([tp.x, tp.y, 0] - [h.x, h.y, 0])
							local have = length ([hb.x, hb.y, 0] - [h.x, h.y, 0])
							if have > 0.01 do (local sc = biped.getTransform b #scale; biped.setTransform b #scale [sc.x, sc.y * want / have, sc.z] false)
						)
						footDir = normalize ([tp.x, tp.y, 0] - [h.x, h.y, 0])
					)
				)
				else if matchPattern e[1] pattern:"* Toe0" then (
					local L = prevToe
					if tn != undefined then setLink b h (jointPos tn) else setLink b h (h + footDir * L)
				)
				else (
					local t = tailOf hn tn prevLen e[1]
					if kOv != undefined and (matchPattern e[1] pattern:"* Thigh") do t = kOv
					-- 위팔·허벅지: 다음 마디(아래팔·종아리)가 접히는 면에 맞춰 비틀림 지정 (Biped 팔꿈치·무릎은 한 면으로만 굽음)
					local zH = undefined
					local nxtE = if matchPattern e[1] pattern:"* UpperArm" then (entry map (sdK + " Forearm")) else if matchPattern e[1] pattern:"* Thigh" then (entry map (sdK + " Calf")) else undefined
					if nxtE != undefined and (nd nxtE[3]) != undefined do (
						local nx = jointPos (nd nxtE[3])
						if matchPattern e[1] pattern:"* UpperArm" then (
							-- v0.6 팔꿈치: Biped 팔꿈치는 -Z 회전으로만 접힘(굽는 방향 = X × Z). 기본 Biped 축(COM 기준)을 위팔 방향으로 돌린 Z를 기준으로,
							-- 뼈대가 3° 이상 앞으로 굽어 있으면 그 면(Z = 굽는방향 × X)을 쓰고, 거의 곧거나 뒤로 꺾였으면 기본 축 사용
							local ax = normalize (t - h)
							local comR = bipRoot.transform.rotation as matrix3
							local rX = normalize ((if sdK == "L" then [-0.0993,0.0998,-0.9900] else [-0.0993,-0.0998,-0.9900]) * comR)
							local rZ = normalize ((if sdK == "L" then [0.0100,0.9950,0.0993] else [-0.0100,0.9950,-0.0993]) * comR)
							local kk = cross rX ax; local ks = length kk; local kc = dot rX ax
							if ks > 0.0001 do (kk = kk / ks; rZ = rZ * kc + (cross kk rZ) * ks + kk * (dot kk rZ) * (1 - kc))
							rZ = normalize (rZ - (dot rZ ax) * ax)
							zH = rZ
							local v = nx - t
							local bd = v - (dot v ax) * ax
							local bendA = atan2 (length bd) (dot v ax)
							if bendA > 3.0 do (
								local zb = normalize (cross bd ax)
								if (dot zb rZ) > 0 then zH = zb
								else log += sdK + " 팔꿈치가 뒤로 " + (formattedPrint bendA format:".1f") + "° 꺾여 있어 기본 축 사용\n")
						) else (
						local cr = cross (t - h) (nx - t)
						if (length cr) > 0.0001 * (distance h t) * (distance t nx) do (
							zH = normalize cr
							if (dot zH b.transform.row3) < 0 do zH = -zH)))
					-- v0.6 아래팔: Biped 팔꿈치는 앞(X × Z 방향)으로만 접힘 → 손목이 뒤쪽이면 곧게 폄
					if matchPattern e[1] pattern:"* Forearm" do (
						local ub = getNodeByName (bn + " " + sdK + " UpperArm")
						if ub != undefined do (
							local ux = normalize ub.transform.row1
							local nf = normalize (cross ux ub.transform.row3)
							local v = t - h
							if (dot v nf) < 0.01 * (length v) do (
								log += sdK + " 아래팔이 뒤로 꺾여 있어 곧게 맞춤 (손목 오차 " + (formattedPrint (length (cross (normalize v) ux) * (length v)) format:".2f") + ")\n"
								t = h + ux * (length v))))
					-- v0.6 손·손가락(엄지 제외): Biped 규칙 Y = 손바닥 쪽, Z = 손 폭 방향(손가락 접히는 축). L은 엄지쪽이 -Z, R은 +Z → 검지·새끼 뿌리 관절로 계산
					if (matchPattern e[1] pattern:"* Hand") or ((matchPattern e[1] pattern:"* Finger*") and not (matchPattern e[1] pattern:"* Finger0*")) do (
						local ixE = entry map (sdK + " Finger1"); local pkE = entry map (sdK + " Finger4")
						if ixE != undefined and pkE != undefined and (nd ixE[2]) != undefined and (nd pkE[2]) != undefined do (
							local lat = jointPos (nd ixE[2]) - jointPos (nd pkE[2])
							if (length lat) > 0.001 do zH = if sdK == "L" then -lat else lat))
					-- v0.6 엄지: Biped 기본 엄지 축(손 로컬)을 실제 엄지 방향으로 최소 회전 → 접으면 손바닥+새끼 쪽으로 감
					if matchPattern e[1] pattern:"* Finger0*" do (
						local hB = getNodeByName (bn + " " + sdK + " Hand")
						local t0E = entry map (sdK + " Finger0")
						if hB != undefined and t0E != undefined and (nd t0E[2]) != undefined and (nd t0E[3]) != undefined do (
							local thX = normalize (jointPos (nd t0E[3]) - jointPos (nd t0E[2]))
							local thD = if sdK == "L" then [0.955,0.239,-0.174] else [0.955,0.239,0.174]
							local thZ = if sdK == "L" then [0.296,-0.772,0.562] else [-0.296,0.772,0.562]
							local thR = hB.transform.rotation as matrix3
							thD = normalize (thD * thR); thZ = normalize (thZ * thR)
							local thK = cross thD thX; local thS = length thK; local thC = dot thD thX
							if thS > 0.0001 do (thK = thK / thS; thZ = thZ * thC + (cross thK thZ) * thS + thK * (dot thK thZ) * (1 - thC))
							zH = thZ))
					local L = setLink b h t zHint:zH
					if L > 0 do prevLen = L
				)
			)
		)
		)
		-- 3) 오차 보고: Biped 관절 위치 vs 뼈대 관절 위치
		local worst = 0.0; local wn = ""
		for e in map do (
			local b = getNodeByName (bn + " " + e[1]); local hn = nd e[2]
			if b != undefined and hn != undefined do (local d = distance b.transform.pos (jointPos hn); if d > worst do (worst = d; wn = e[1]))
		)
		log += "맞춤 완료: " + (map.count as string) + "개 파트, 못 찾음 " + (miss as string) + "\n최대 관절 오차 " + (formattedPrint worst format:".2f") + " (" + wn + ")\n"
		log
	),


	-- ===== 연결: 뼈대(스킨 본)가 Biped를 따라 움직이게 =====
	-- AccuRIG / CC 본 이름 → Biped 파트 (트위스트·Share 본은 부모 파트, 얼굴은 Head)
	fn ccPart nm =
	(
		if not (matchPattern nm pattern:"CC_Base_*") do return undefined
		local n = substring nm 9 -1
		local sd = undefined
		if (matchPattern n pattern:"L_*") or (matchPattern n pattern:"R_*") do (sd = n[1]; n = substring n 3 -1)
		local center = #(#("Hip","Pelvis"), #("Pelvis","Pelvis"), #("Waist","Spine"), #("Spine01","Spine1"), #("Spine02","Spine2"),
			#("NeckTwist01","Neck"), #("NeckTwist02","Neck"), #("Head","Head"))
		if sd == undefined do (
			for e in center where e[1] == n do return e[2]
			return "Head")   -- FacialBone, JawRoot, Tongue, Teeth, UpperJaw, Eye 등
		if n == "Eye" do return "Head"
		local fing = #("Thumb","Index","Mid","Ring","Pinky")
		for f = 1 to 5 where matchPattern n pattern:(fing[f] + "?") do (
			local k = (n[n.count] as integer)
			if k != undefined do return sd + " Finger" + ((f-1) as string) + (if k == 1 then "" else ((k-1) as string)))
		local pre = #(#("Clavicle","Clavicle"), #("UpperarmTwist","UpperArm"), #("Upperarm","UpperArm"), #("ElbowShareBone","Forearm"),
			#("ForearmTwist","Forearm"), #("Forearm","Forearm"), #("Hand","Hand"), #("ThighTwist","Thigh"), #("Thigh","Thigh"),
			#("KneeShareBone","Calf"), #("CalfTwist","Calf"), #("Calf","Calf"), #("Foot","Foot"), #("ToeBase","Toe0"))
		for e in pre where matchPattern n pattern:(e[1] + "*") do return sd + " " + e[2]
		if matchPattern n pattern:"*Toe*" do return sd + " Toe0"
		undefined
	),

	-- UE 이름(AccuRIG UE5) 본 → Biped 파트. #skip = 연결 안 함(root, ik_*)
	fn uePart nm =
	(
		local n = toLower nm
		if n == "root" or (matchPattern n pattern:"ik_*") do return #skip
		local sd = undefined
		if (matchPattern n pattern:"*_l") or (matchPattern n pattern:"cc_base_l_*") then sd = "L"
		else if (matchPattern n pattern:"*_r") or (matchPattern n pattern:"cc_base_r_*") do sd = "R"
		local center = #(#("pelvis","Pelvis"), #("cc_base_pelvis","Pelvis"), #("spine_01","Spine"), #("spine_02","Spine"), #("spine_03","Spine1"),
			#("spine_04","Spine2"), #("spine_05","Spine2"), #("neck_01","Neck"), #("neck_02","Neck"), #("head","Head"))
		for e in center where e[1] == n do return e[2]
		if sd == undefined do (
			if matchPattern n pattern:"cc_base_*" do return "Head"   -- facialbone, jawroot, tongue, teeth, upperjaw
			return undefined)
		if matchPattern n pattern:"*_eye" do return "Head"
		if (matchPattern n pattern:"*ribstwist*") or (matchPattern n pattern:"*breast*") do return "Spine2"
		local fing = #("thumb","index","middle","ring","pinky")
		for f = 1 to 5 do (
			if matchPattern n pattern:(fing[f] + "_metacarpal_*") do return sd + " Hand"
			for k = 1 to 3 where matchPattern n pattern:(fing[f] + "_0" + (k as string) + "_*") do
				return sd + " Finger" + ((f-1) as string) + (if k == 1 then "" else ((k-1) as string)))
		local pre = #(#("*clavicle*","Clavicle"), #("*upperarm*","UpperArm"), #("*elbowsharebone*","Forearm"), #("*forearmtwist*","Forearm"),
			#("lowerarm_*","Forearm"), #("hand_*","Hand"), #("*thigh*","Thigh"), #("*kneesharebone*","Calf"), #("*calf*","Calf"),
			#("foot_*","Foot"), #("ball_*","Toe0"), #("*toebasesharebone*","Toe0"), #("*toe1","Toe0"))
		for e in pre where matchPattern n pattern:e[1] do return sd + " " + e[2]
		undefined
	),

	-- Rigify DEF- 본 이름 → Biped 파트
	fn defPart nm =
	(
		if not (matchPattern nm pattern:"DEF-*") do return undefined
		local n = substring nm 5 -1
		local sd = undefined
		local i = findString n ".L"; if i == undefined do (i = findString n ".R")
		if i != undefined do (sd = n[i+1]; n = substring n 1 (i-1))
		local spineMap = #(#("spine","Pelvis"), #("spine.001","Spine"), #("spine.002","Spine1"), #("spine.003","Spine2"), #("spine.004","Neck"), #("spine.005","Neck"), #("spine.006","Head"))
		for e in spineMap where e[1] == n do return e[2]
		if sd == undefined do return undefined
		local simple = #(#("pelvis","Pelvis",false), #("breast","Spine2",false), #("shoulder","Clavicle",true), #("upper_arm","UpperArm",true), #("forearm","Forearm",true),
			#("hand","Hand",true), #("thigh","Thigh",true), #("shin","Calf",true), #("foot","Foot",true), #("toe","Toe0",true))
		for e in simple where e[1] == n do return (if e[3] then sd + " " + e[2] else e[2])
		if matchPattern n pattern:"palm.*" do return sd + " Hand"
		local fing = #("thumb","f_index","f_middle","f_ring","f_pinky")
		for f = 1 to 5 where matchPattern n pattern:(fing[f] + ".0?") do (
			local k = (n[n.count] as integer)
			return sd + " Finger" + ((f-1) as string) + (if k == 1 then "" else ((k-1) as string)))
		undefined
	),

	-- 하나 연결: 지금 상대 위치(L)를 고정하고 Biped 파트를 따라감 (팔로워 방식)
	fn follow d b =
	(
		-- 링크 방식: 스킨 본을 Biped 파트의 자식으로 (월드 위치 유지). 원래 부모 이름은 BipFit_parent에 저장
		-- (예전 스크립트 컨트롤러 방식은 계층이 깊으면 평가 순서가 꼬여 키 사이 프레임에서 메쉬가 튐)
		if (getUserProp d "BipFit_parent") == undefined or (getUserProp d "BipFit_parent") == "" do
			setUserProp d "BipFit_parent" (if d.parent == undefined then "-" else d.parent.name)
		if classOf d.controller == transform_script do (local tm = d.transform; d.controller = prs(); d.transform = tm)
		local tm2 = d.transform
		d.parent = b
		d.transform = tm2
		setUserProp d "BipFit_follow" b.name
		setUserProp d "BipFit_ver" BipFit_version
	),

	-- 점(p)과 선분(a-b) 사이 거리
	fn segDist p a b =
	(
		local ab = b - a
		local l2 = dot ab ab
		if l2 < 0.000001 then (distance p a)
		else (
			local t = (dot (p - a) ab) / l2
			if t < 0.0 do t = 0.0
			if t > 1.0 do t = 1.0
			distance p (a + ab * t))
	),

	-- 몸 Biped 파트 중 점에 가장 가까운 파트 이름 (파트 선분 = 시작점 + X축 * 길이)
	fn nearestPart bipRoot p =
	(
		local names = #("Pelvis","Spine","Spine1","Spine2","Neck","Head")
		for sd in #("L","R") do for pt in #("Clavicle","UpperArm","Forearm","Hand","Thigh","Calf","Foot","Toe0") do append names (sd + " " + pt)
		local best = undefined
		local bd = 1000000000.0
		for nm in names do (
			local b = getNodeByName (bipRoot.name + " " + nm)
			if b != undefined do (
				local a = b.transform.pos
				local len = (biped.getTransform b #scale).x
				local dd = segDist p a (a + b.transform.row1 * len)
				if dd < bd do (bd = dd; best = nm)))
		best
	),

	-- 매핑에 없는 DEF 본이 따라갈 Biped 파트: 얼굴류 -> Head, knee -> Calf, butt -> Pelvis, 그 외 -> 가장 가까운 파트
	fn fallbackPart bipRoot d =
	(
		local n = if matchPattern d.name pattern:"DEF-*" then (substring d.name 5 -1) else d.name
		local k = (filterString n ".")[1]
		local sd = if (findString n ".L") != undefined then "L" else if (findString n ".R") != undefined then "R" else undefined
		if k == "knee" and sd != undefined then (sd + " Calf")
		else if k == "butt" then "Pelvis"
		else if (findItem faceNames k) != 0 then "Head"
		else (nearestPart bipRoot d.transform.pos)
	),

	-- UE 이름 뼈대 연결: Biped가 아닌 본/더미 전부 대상, root·ik_ 제외
	fn connectUE bipRoot fallback:true =
	(
		local done = 0
		local extra = 0
		local miss = #()
		local ds = for o in objects where (classOf o == BoneGeometry or classOf o == Dummy) and o.parent != undefined and not (matchPattern o.name pattern:(bipRoot.name + "*")) collect o
		local cancelled = false
		progressStart "BipFit: 뼈대 연결"
		for i = 1 to ds.count while not cancelled do (
			local d = ds[i]
			progressUpdate (100.0 * i / ds.count)
			if getProgressCancel() do (cancelled = true)
			local part = uePart d.name
			if part != #skip do (
				local b = if part == undefined then undefined else getNodeByName (bipRoot.name + " " + part)
				if b != undefined then (follow d b; done += 1)
				else if fallback then (
					local fp = nearestPart bipRoot d.transform.pos
					local fb = if fp == undefined then undefined else getNodeByName (bipRoot.name + " " + fp)
					if fb != undefined then (follow d fb; extra += 1) else append miss d.name)
				else append miss d.name))
		progressEnd()
		local ms = ""
		for i = 1 to (amin 8 miss.count) do ms += miss[i] + " "
		(if cancelled then "[취소됨] Ctrl+Z로 되돌리세요\n" else "") + "연결 " + (done as string) + "개 + 규칙 연결 " + (extra as string) + "개, 못 찾음 " + (miss.count as string) + (if miss.count > 0 then (": " + ms) else "")
	),

	fn connect bipRoot pattern:"DEF-*" fallback:true =
	(
		local done = 0
		local extra = 0
		local miss = #()
		local ds = for o in objects where matchPattern o.name pattern:pattern collect o
		local cancelled = false
		progressStart "BipFit: 뼈대 연결"
		for i = 1 to ds.count while not cancelled do (
			local d = ds[i]
			progressUpdate (100.0 * i / ds.count)
			if getProgressCancel() do (cancelled = true)
			local part = if matchPattern d.name pattern:"CC_Base_*" then (ccPart d.name) else (defPart d.name)
			local b = if part == undefined then undefined else getNodeByName (bipRoot.name + " " + part)
			if b != undefined then (follow d b; done += 1)
			else if fallback then (
				local fp = fallbackPart bipRoot d
				local fb = if fp == undefined then undefined else getNodeByName (bipRoot.name + " " + fp)
				if fb != undefined then (follow d fb; extra += 1) else append miss d.name)
			else append miss d.name)
		progressEnd()
		local ms = ""
		for i = 1 to (amin 8 miss.count) do ms += miss[i] + " "
		(if cancelled then "[취소됨] Ctrl+Z로 되돌리세요\n" else "") + "연결 " + (done as string) + "개 + 규칙 연결 " + (extra as string) + "개, 못 찾음 " + (miss.count as string) + (if miss.count > 0 then (": " + ms) else "")
	),
	-- 연결 해제: 지금 자세 그대로 일반 PRS로 되돌림
	fn disconnect pattern:"*" =
	(
		-- 0프레임(바인드 자세)에서 원래 부모로 되돌림
		local n = 0
		local ds = for d in objects where (matchPattern d.name pattern:pattern) and (getUserProp d "BipFit_follow") != undefined and (getUserProp d "BipFit_follow") != "" collect d
		local tms = for d in ds collect (at time 0 d.transform)
		for i = 1 to ds.count do (
			local d = ds[i]
			if classOf d.controller == transform_script do d.controller = prs()
			local pn = getUserProp d "BipFit_parent"
			if pn != undefined and pn != "" do d.parent = (if pn == "-" then undefined else getNodeByName pn)
			setUserProp d "BipFit_follow" ""
			setUserProp d "BipFit_parent" ""
			n += 1)
		for i = 1 to ds.count do (at time 0 ds[i].transform = tms[i])
		"해제 " + (n as string) + "개"
	),

	-- Biped 만들기: 뼈대의 L/R 허벅지로 정면 방향을, 목·머리 위치로 키를 구해 만든다 (스파인 3, 손가락 5x3, 발가락 1)
	fn createBiped preset prefix:"Bip01" delOld:false =
	(
		log = ""
		local map = mapFor preset prefix
		local tl = nd (entry map "L Thigh")[2]
		local tr = nd (entry map "R Thigh")[2]
		local hd = nd (entry map "Head")[2]
		local nk = nd (entry map "Neck")[2]
		if tl == undefined or tr == undefined or hd == undefined or nk == undefined do (log = "뼈대에서 허벅지/목/머리 노드를 찾을 수 없음\n"; return undefined)
		local old = for o in objects where classOf o == Biped_Object collect o
		if old.count > 0 do (
			if delOld then delete (for o in objects where (classOf o == Biped_Object or classOf o == Footsteps) collect o)
			else (log = "이미 Biped가 있음: " + old[1].name + "\n('기존 Biped 삭제 후 만들기'를 체크하면 다시 만듦)\n"; return undefined))
		-- 정면 = (왼쪽 방향) x (위). 왼쪽 = L 허벅지 - R 허벅지
		local lv = (jointPos tl) - (jointPos tr)
		lv = normalize [lv.x, lv.y, 0]
		local fw = cross lv [0,0,1]
		local ang = atan2 fw.y fw.x
		local ph = jointPos hd
		local pn = jointPos nk
		local h = ph.z + (ph.z - pn.z) * headFactor
		local b = biped.createNew h ang [0,0,0] arms:true neck:true triangleNeck:true trianglePelvis:false spineLinks:3 legLinks:3 fingers:5 fingerLinks:3 toes:1 toeLinks:1 ankleAttach:0.2
		log = "Biped 생성: " + b.name + " (키 " + (formattedPrint h format:".1f") + ", 방향 " + (formattedPrint ang format:".0f") + "도)\n"
		b
	),

	-- 스킨 정리 ---------------------------------------------------
	fn skinOf o =
	(
		local sk = undefined
		for m in o.modifiers where classOf m == Skin do (if sk == undefined do sk = m)
		sk
	),

	-- 웨이트가 하나도 없는 본을 Skin에서 제거 (정점 웨이트·변형은 그대로)
	fn cleanSkin o =
	(
		local sk = skinOf o
		if sk == undefined do return (o.name + ": Skin 없음")
		select o
		max modify mode
		modPanel.setCurrentObject sk
		completeRedraw()
		local nb = skinOps.GetNumberBones sk
		local nv = skinOps.GetNumberVertices sk
		if nb == 0 or nv == 0 do return (o.name + ": 스킨 정보를 읽지 못함")
		-- 사용 중인 본(UI 목록 번호)
		local usedL = #{}
		local cancelled = tick ("BipFit 스킨 정리: " + o.name + " 정점 " + (nv as string) + "개 확인 중")
		for v = 1 to nv while not cancelled do (
			if (mod v 2000) == 0 do (if keyboard.escPressed do cancelled = true)
			local c = skinOps.GetVertexWeightCount sk v
			-- 웨이트 0으로만 남아 있는 항목은 사용으로 치지 않음 (지워도 변형이 바뀌지 않음)
			for k = 1 to c where (skinOps.GetVertexWeight sk v k) > 0.0001 do (usedL[skinOps.GetVertexWeightBoneID sk v k] = true)
		)
		replacePrompt ""
		if cancelled do return (o.name + ": [취소됨] 바뀐 것 없음")
		local usedNames = for i in usedL collect (skinOps.GetBoneNameByListID sk i 0)
		-- 현재 Skin의 모든 본 이름(목록 순서)과 안 쓰는 본
		local namesL = for i = 1 to nb collect (skinOps.GetBoneNameByListID sk i 0)
		local unused = for nm in namesL where (findItem usedNames nm) == 0 collect nm
		if unused.count == 0 do return (o.name + ": 안 쓰는 본 없음 (" + (nb as string) + "개)")
		-- 본을 지우면 번호(ID)가 다시 매겨지지 않고 빈 번호가 남으므로, 안 쓰는 본의 실제 번호를 찾아서 지움
		local rmIds = #()
		local idn = 0
		while rmIds.count < unused.count and idn < 5000 do (
			idn += 1
			local nmI = try (skinOps.GetBoneName sk idn 0) catch (undefined)
			if nmI != undefined and (findItem unused nmI) != 0 do append rmIds idn
		)
		for i = rmIds.count to 1 by -1 do skinOps.removeBone sk rmIds[i]
		o.name + ": 본 " + (nb as string) + " -> " + ((skinOps.GetNumberBones sk) as string) + " (제거 " + (rmIds.count as string) + ")"
	),

	fn skinTargets sel = (for o in sel where (skinOf o) != undefined collect o),

	fn cleanSkins tg =
	(
		local s = ""
		for o in tg do s += (cleanSkin o) + "\n"
		if tg.count > 0 do select tg
		s
	),
	-- 스킨 뼈대 표시 ------------------------------------------------
	-- FBX로 들어온 본은 길이가 0에 가까워 점처럼 보임 -> 부모-자식 연결선으로 표시 (본 회전·스킨은 그대로)
	-- 대상: Biped가 아닌 BoneGeometry/Dummy. 연결된 본(BipFit_follow)=스킨 본, 나머지=참조 뼈대(ORG 등)
	fn rigNodes =
	(
		local skinB = #()
		local refB = #()
		for o in objects where (classOf o == BoneGeometry or classOf o == Dummy) and not (matchPattern o.name pattern:"Bip0*") do (
			local f = getUserProp o "BipFit_follow"
			if f != undefined and f != "" then append skinB o else append refB o)
		#(skinB, refB)
	),

	fn setBoneDisplay mode =
	(
		local r = rigNodes()
		local skinB = r[1]
		local refB = r[2]
		local msg = ""
		if mode == #lines then (
			for o in skinB do (o.isHidden = false; o.showLinks = true; o.showLinksOnly = true)
			for o in refB do (o.showLinks = false; o.showLinksOnly = false; o.isHidden = true)
			msg = "스킨 본은 선으로, 참조 뼈대는 숨김")
		else if mode == #hide then (
			for o in skinB do (o.isHidden = true)
			for o in refB do (o.isHidden = true)
			msg = "모두 숨김")
		else (
			for o in skinB do (o.isHidden = false; o.showLinks = false; o.showLinksOnly = false)
			for o in refB do (o.isHidden = false; o.showLinks = false; o.showLinksOnly = false)
			msg = "원래대로")
		completeRedraw()
		"스킨 본 " + (skinB.count as string) + "개, 참조 뼈대 " + (refB.count as string) + "개: " + msg
	),

	-- ===== 리깅 FBX(AccuRIG 정리본 등) 웨이트를 씬의 원본 메쉬로 =====
	-- 정점 번호 기준 복사. 원본 메쉬는 이름(대소문자 무시)과 정점 수로 짝을 맞춤
	-- 엔벌로프 파일(.env)로 복사: Max 자체 저장·불러오기라 정점마다 스크립트를 부르지 않아 빠름. 정점은 번호, 본은 이름으로 연결
	fn copySkinEnv src dst boneNodes envDir:"" =
	(
		local ssk = src.modifiers[#Skin]
		select src; max modify mode; modPanel.setCurrentObject ssk; completeRedraw()
		local snames = for i = 1 to (skinOps.GetNumberBones ssk) collect (skinOps.GetBoneNameByListID ssk i 0)
		local nv = skinOps.GetNumberVertices ssk
		if envDir == "" do envDir = (getDir #temp) + "\\BipFit_env\\"
		makeDir envDir all:true
		local ef = envDir + dst.name + ".env"
		skinOps.saveEnvelope ssk ef
		local old = dst.modifiers[#Skin]
		if old != undefined do deleteModifier dst old
		local dsk = Skin()
		addModifier dst dsk
		dsk.bone_Limit = 4
		select dst; modPanel.setCurrentObject dsk; completeRedraw()
		for i = 1 to snames.count do (
			local bnode = (for b in boneNodes where b.name == snames[i] collect b)[1]
			if bnode != undefined do skinOps.addBone dsk bnode (if i == snames.count then 1 else 0))
		completeRedraw()
		DialogMonitorOPS.unRegisterNotification id:#BipFitEnv
		DialogMonitorOPS.RegisterNotification BipFit_envAutoOK id:#BipFitEnv
		DialogMonitorOPS.Enabled = true
		skinOps.loadEnvelope dsk ef
		DialogMonitorOPS.Enabled = false
		DialogMonitorOPS.unRegisterNotification id:#BipFitEnv
		-- .env에는 원본(FBX) Skin의 바인드 상태가 같이 들어옴. FBX 가져오기 바인드가 뼈대와 조금 어긋날 수 있어 현재 뼈대 기준으로 다시 바인드
		select dst; modPanel.setCurrentObject dsk
		dsk.always_deform = false
		dsk.always_deform = true
		completeRedraw()
		-- 확인 1: 바인드 자세에서 원본 위치 그대로인지
		local mb = snapshotAsMesh dst
		local d = 0.0
		local bo = dst.baseObject
		local isPoly = classOf bo == Editable_Poly
		for v = 1 to mb.numverts by 3 do (
			local p0 = if isPoly then (polyop.getVert bo v) * dst.objectTransform else (getVert bo.mesh v) * dst.objectTransform
			local x = distance p0 (getVert mb v); if x > d do d = x)
		delete mb
		-- 확인 2: 표본 정점 웨이트가 src와 같은지
		local bad = 0
		local samples = for k = 1 to 50 collect (1 + ((k - 1) * nv) / 50)
		local sw = #()
		select src; modPanel.setCurrentObject ssk
		for v in samples do (local c = skinOps.GetVertexWeightCount ssk v; append sw (for k = 1 to c collect #(snames[skinOps.GetVertexWeightBoneID ssk v k], skinOps.GetVertexWeight ssk v k)))
		select dst; modPanel.setCurrentObject dsk
		local dnames = for i = 1 to (skinOps.GetNumberBones dsk) collect (skinOps.GetBoneNameByListID dsk i 0)
		for i = 1 to samples.count do (
			local v = samples[i]
			local c = skinOps.GetVertexWeightCount dsk v
			for e in sw[i] do (
				local found = false
				for k = 1 to c do (if dnames[skinOps.GetVertexWeightBoneID dsk v k] == e[1] and (abs ((skinOps.GetVertexWeight dsk v k) - e[2])) < 0.002 do found = true)
				if not found do bad += 1))
		dst.name + ": 정점 " + (nv as string) + ", 본 " + (snames.count as string) + ", 바인드 위치 차이 " + (formattedPrint d format:".4f") + ", 표본 웨이트 불일치 " + (bad as string)
	),

	fn copySkinByIndex src dst boneNodes =
	(
		local ssk = src.modifiers[#Skin]
		select src; max modify mode; modPanel.setCurrentObject ssk; completeRedraw()
		local snames = for i = 1 to (skinOps.GetNumberBones ssk) collect (skinOps.GetBoneNameByListID ssk i 0)
		local nv = skinOps.GetNumberVertices ssk
		-- 원본에 이미 Skin이 있으면 지우고 새로
		local old = dst.modifiers[#Skin]
		if old != undefined do deleteModifier dst old
		local dsk = Skin()
		addModifier dst dsk
		dsk.bone_Limit = 4
		select dst; modPanel.setCurrentObject dsk; completeRedraw()
		for i = 1 to snames.count do (
			local bnode = (for b in boneNodes where b.name == snames[i] collect b)[1]
			if bnode != undefined do skinOps.addBone dsk bnode (if i == snames.count then 1 else 0))
		completeRedraw()
		local dorder = for i = 1 to (skinOps.GetNumberBones dsk) collect (skinOps.GetBoneName dsk i 0)
		local miss = 0
		local v0 = 1
		while v0 <= nv do (
			local v1 = amin (v0 + 4999) nv
			select src; modPanel.setCurrentObject ssk
			local ids = #(); local ws = #()
			for v = v0 to v1 do (
				local c = skinOps.GetVertexWeightCount ssk v
				append ids (for k = 1 to c collect snames[skinOps.GetVertexWeightBoneID ssk v k])
				append ws (for k = 1 to c collect (skinOps.GetVertexWeight ssk v k)))
			select dst; modPanel.setCurrentObject dsk
			for v = v0 to v1 do (
				local k = v - v0 + 1
				local bid = for n in ids[k] collect (findItem dorder n)
				if (findItem bid 0) != 0 then miss += 1 else skinOps.ReplaceVertexWeights dsk v bid ws[k])
			v0 = v1 + 1)
		-- 확인: 같은 자세에서 정점 위치 비교
		local ma = snapshotAsMesh src; local mb = snapshotAsMesh dst
		local d = 0.0
		for v = 1 to ma.numverts do (local x = distance (getVert ma v) (getVert mb v); if x > d do d = x)
		delete ma; delete mb
		dst.name + ": 정점 " + (nv as string) + ", 본 " + (snames.count as string) + ", 못 찾은 본 정점 " + (miss as string) + ", 위치 차이 최대 " + (formattedPrint d format:".4f")
	),

	fn importRigWeights f =
	(
		log = ""
		if not (doesFileExist f) do (log = "파일 없음: " + f; return log)
		local origs = for o in objects where (classOf o.baseObject == Editable_Poly or classOf o.baseObject == Editable_mesh) collect o
		if origs.count == 0 do (log = "씬에 원본 메쉬가 없음 (원본 모델 파일을 먼저 여세요)"; return log)
		local before = for o in objects collect o
		FBXImporterSetParam "ResetImport"
		FBXImporterSetParam "Mode" #create
		FBXImporterSetParam "ImportBoneAsDummy" false
		FBXImporterSetParam "Animation" false
		FBXImporterSetParam "Shape" false
		importFile f #noPrompt using:FBXIMP
		local newO = for o in objects where (findItem before o) == 0 collect o
		local newM = for o in newO where superClassOf o == GeometryClass and classOf o != BoneGeometry and o.modifiers[#Skin] != undefined collect o
		local boneNodes = for o in newO where classOf o == BoneGeometry or classOf o == Dummy collect o
		local sc = for o in newO where o.parent == undefined collect (o.transform.scale)
		log += "가져옴: 본 " + (boneNodes.count as string) + ", 스킨 메쉬 " + (newM.count as string) + "\n"
		for s in sc where (abs (s.x - 1.0)) > 0.001 do (log += "경고: 루트 스케일 " + (s as string) + " (블렌더 'AccuRIG 정리'를 거친 FBX인지 확인)\n"; exit)
		local done = #()
		local cancelled = false
		for mi = 1 to newM.count while not cancelled do (
			local m = newM[mi]
			if tick ("BipFit 웨이트 복사 " + (mi as string) + "/" + (newM.count as string) + ": " + m.name) do (cancelled = true; log += "[취소됨] 남은 메쉬는 복사하지 않음\n")
			if cancelled do continue
			local nm = toLower m.name
			local nv = getNumVerts m
			local dst = (for o in origs where (toLower o.name) == nm and (try (getNumVerts o) catch (-1)) == nv collect o)[1]
			if dst == undefined do dst = (for o in origs where (try (getNumVerts o) catch (-1)) == nv collect o)[1]
			if dst == undefined then log += m.name + ": 짝이 되는 원본 메쉬 없음 (남겨 둠)\n"
			else (log += (copySkinEnv m dst boneNodes) + "\n"; append done m))
		replacePrompt ""
		delete done
		clearSelection(); max create mode
		log += "가져온 메쉬 " + (done.count as string) + "개는 웨이트 복사 후 삭제\n"
		log
	),

	-- 옛 연결(스크립트 컨트롤러) → 링크 방식으로 바꾸기. 0프레임(바인드 자세) 기준
	fn relinkLegacy =
	(
		local ds = for o in objects where classOf o.controller == transform_script and (getUserProp o "BipFit_follow") != undefined and (getUserProp o "BipFit_follow") != "" collect o
		if ds.count == 0 do return "스크립트 방식으로 연결된 본이 없음"
		local t0 = sliderTime
		sliderTime = 0
		local n = 0; local miss = #(); local todo = #()
		-- 스킨 바인드 위치: 이 위치로 되돌려 연결하면 0프레임 메쉬가 원본과 정확히 같아짐
		local bindN = #(); local bindT = #()
		for m in objects where m.modifiers[#Skin] != undefined do (
			local sk = m.modifiers[#Skin]
			select m; max modify mode; modPanel.setCurrentObject sk
			for i = 1 to (skinOps.GetNumberBones sk) do (
				local bnm = skinOps.GetBoneNameByListID sk i 0
				if (findItem bindN bnm) == 0 do (
					local bnode = getNodeByName bnm
					local bt = try (skinUtils.GetBoneBindTM m bnode) catch (undefined)
					if bt != undefined do (append bindN bnm; append bindT bt))))
		clearSelection(); max create mode
		for d in ds do (
			local pn = getUserProp d "BipFit_follow"
			local b = getNodeByName pn
			-- Biped 이름을 바꾼 경우(예: Bip001 -> Bip01): 앞 단어만 지금 Biped 이름으로 바꿔서 찾기
			if b == undefined do (
				local sp = findString pn " "
				if sp != undefined do (
					local rest = substring pn (sp + 1) -1
					for r in objects where classOf r == Biped_Object and r.parent == undefined while b == undefined do b = getNodeByName (r.name + " " + rest)))
			if b != undefined then (
				-- 스크립트에 저장된 상대 위치(L)로 정확한 월드 위치 계산 (스크립트 평가값은 계층이 깊으면 오차가 있음)
				local Lc = try (d.controller.getConstant "L") catch (undefined)
				local bi = findItem bindN d.name
				local wtm = if bi > 0 then bindT[bi] else if classOf Lc == Matrix3 then (Lc * b.transform) else d.transform
				if (getUserProp d "BipFit_parent") == undefined or (getUserProp d "BipFit_parent") == "" do
					setUserProp d "BipFit_parent" (if d.parent == undefined then "-" else d.parent.name)
				append todo #(d, b, wtm)
				n += 1)
			else append miss d.name)
		-- 모두 계산한 뒤 한꺼번에 바꿈 (바꾸는 도중 다른 본 스크립트 값이 흔들리지 않게)
		for e in todo do (e[1].controller = prs(); e[1].parent = e[2]; setUserProp e[1] "BipFit_follow" e[2].name)
		for e in todo do e[1].transform = e[3]
		-- 현재(바인드) 자세로 Skin 다시 바인드 (FBX 가져오기 바인드 오차 제거)
		for m in objects where m.modifiers[#Skin] != undefined do (
			local sk = m.modifiers[#Skin]
			select m; max modify mode; modPanel.setCurrentObject sk
			sk.always_deform = false; sk.always_deform = true)
		clearSelection(); max create mode
		sliderTime = t0
		"링크로 변환 " + (n as string) + "개" + (if miss.count > 0 then (", Biped 파트 못 찾음 " + (miss.count as string)) else "")
	),

	-- ===== LMA 추출 전 점검 (고치지 않고 알려 주기만) =====
	-- 숨긴 메쉬·본(LMA는 숨긴 노드를 빼고 내보냄), Figure Mode, 정점당 본 4개 초과, 맵 채널, 재질 ID
	fn checkExport =
	(
		local selSave = selection as array
		local skinned = for o in objects where (skinOf o) != undefined collect o
		if skinned.count == 0 do return "Skin 메쉬가 없음"
		local out = ""
		local warn = 0
		for r in objects where classOf r == Biped_Object and r.parent == undefined do (
			if r.controller.figureMode do (out += "[!] " + r.name + ": Figure Mode가 켜져 있음 (끄고 추출)\n"; warn += 1))
		local cancelled = false
		for i = 1 to skinned.count while not cancelled do (
			local o = skinned[i]
			if tick ("BipFit 점검 " + (i as string) + "/" + (skinned.count as string) + ": " + o.name) do (cancelled = true; continue)
			local sk = skinOf o
			if o.isHidden do (out += "[!] " + o.name + ": 메쉬가 숨겨져 있음\n"; warn += 1)
			select o; max modify mode; modPanel.setCurrentObject sk
			-- 숨긴 본
			local hidB = #()
			for b = 1 to (skinOps.GetNumberBones sk) do (
				local nm = skinOps.GetBoneNameByListID sk b 0
				local n = getNodeByName nm exact:true
				if n != undefined and n.isHidden do append hidB nm)
			if hidB.count > 0 do (out += "[!] " + o.name + ": 숨긴 본 " + (hidB.count as string) + "개 (예: " + hidB[1] + ") -> 표시 '원래대로'\n"; warn += 1)
			-- 정점당 본 수
			local nv = skinOps.GetNumberVertices sk
			local over = 0
			for v = 1 to nv while not cancelled do (
				if (mod v 2000) == 0 do (if keyboard.escPressed do cancelled = true)
				local c = skinOps.GetVertexWeightCount sk v
				if c > 4 do (
					local k = 0
					for j = 1 to c do (if (skinOps.GetVertexWeight sk v j) > 0.0001 do k += 1)
					if k > 4 do over += 1))
			if over > 0 do (out += "[!] " + o.name + ": 본 4개 넘는 정점 " + (over as string) + "개\n"; warn += 1)
			-- 맵 채널·재질 ID
			local m = snapshotAsMesh o
			if not (meshop.getMapSupport m 1) do (out += "[!] " + o.name + ": UV(맵 채널 1) 없음\n"; warn += 1)
			local extra = for ch = 2 to ((meshop.getNumMaps m) - 1) where (meshop.getMapSupport m ch) collect ch
			if extra.count > 0 do (out += "[!] " + o.name + ": 맵 채널 " + (extra as string) + " 사용 중 (0/1만 권장, 2는 섀도맵과 짝이어야 함)\n"; warn += 1)
			local ids = #{}
			for f = 1 to m.numfaces do ids[getFaceMatID m f] = true
			local idA = ids as array
			local mat = o.material
			if mat == undefined then (out += "[!] " + o.name + ": 재질 없음\n"; warn += 1)
			else if classOf mat == Multimaterial then (
				local bad = for id in idA where (findItem mat.materialIDList id) == 0 collect id
				if bad.count > 0 do (out += "[!] " + o.name + ": 재질에 없는 재질 ID " + (bad as string) + "\n"; warn += 1))
			else (
				if idA.count != 1 or idA[1] != 1 do (out += "[!] " + o.name + ": 단일 재질인데 재질 ID " + (idA as string) + " (1이어야 함)\n"; warn += 1))
			delete m
		)
		replacePrompt ""
		clearSelection(); max create mode
		if selSave.count > 0 do select selSave
		local head = "추출 전 점검: Skin 메쉬 " + (skinned.count as string) + "개, 문제 " + (warn as string) + "건" + (if cancelled then " [취소됨, 일부만 검사]" else "") + "\n"
		if warn == 0 and not cancelled then head + "문제 없음 - 추출해도 됩니다" else head + out
	),

	fn report bipRoot preset prefix:"Bip01" =
	(
		local map = mapFor preset prefix
		local s = ""
		for e in map do (
			local b = getNodeByName (bipRoot.name + " " + e[1]); local hn = nd e[2]
			if b != undefined and hn != undefined do (
				local d = distance b.transform.pos (jointPos hn)
				if d > 0.5 do s += e[1] + ": " + (formattedPrint d format:".2f") + "\n"))
		if s == "" then "모든 관절 0.5 이내" else s
	)
)
BipFit = BipFitStruct()

rollout BipFitRoll "BipFit v0.6 - Biped 맞추기·연결"
(
	pickbutton pkBip "Biped 고르기 (아무 Biped 노드)" width:200 filter:BipFit_isBiped
	dropdownlist ddPreset "뼈대 종류" items:#("Rigify (ORG- 본)", "Bip 이름 뼈대 (FBX 일반 본)", "AccuRIG / CC (CC_Base_ 본)", "AccuRIG UE5 / UE 이름 (pelvis, spine_01)")
	edittext edPre "뼈대 접두어" text:"Bip01"
	spinner spHead "머리 길이 배수" range:[0.5,5,2.2] type:#float
	group "0. 리깅 FBX 가져오기"
	(
		button btImp "리깅 FBX → 원본 메쉬 (웨이트)" width:190
	)
	group "1. Biped 만들기·맞추기"
	(
		button btMk "Biped 만들기 (뼈대 방향·크기에 맞춰)" width:190
		checkbox ckRep "기존 Biped 삭제 후 만들기"
		button btFig "Figure Mode 켜기/끄기" width:190
		button btFit "관절 맞추기" width:190 height:28
		button btRep "오차 확인" width:190
	)
	group "2. 뼈대 연결"
	(
		checkbox ckFb "매핑 없는 본도 규칙으로 연결" checked:true
		button btCon "뼈대 연결 (스킨 본 → Biped)" width:190
		button btDis "연결 해제" width:190
		button btRelink "옛 연결(스크립트) → 링크" width:190
	)
	group "스킨 뼈대 표시"
	(
		button btLines "선으로 보기" width:62 across:3
		button btHideB "숨기기" width:62
		button btNormB "원래대로" width:62
	)
	group "3. 스킨 정리"
	(
		button btClean "스킨 본 정리 (안 쓰는 본 제거)" width:190
	)
	group "4. 추출 전 점검"
	(
		button btChk "LMA 추출 전 점검" width:190 height:28
	)
	label lb1 "" height:110 align:#left
	local root
	on pkBip picked o do (root = o.controller.rootNode; pkBip.text = root.name)
	on btMk pressed do (
		BipFit.headFactor = spHead.value
		local r = undefined
		undo "BipFit create biped" on (r = BipFit.createBiped ddPreset.selection prefix:edPre.text delOld:ckRep.checked)
		if r != undefined do (root = r; pkBip.text = r.name)
		lb1.text = BipFit.log
		completeRedraw())
	on btFig pressed do if root != undefined do root.controller.figureMode = not root.controller.figureMode
	on btFit pressed do if root != undefined do (
		BipFit.headFactor = spHead.value
		undo "BipFit" on (lb1.text = BipFit.fit root ddPreset.selection prefix:edPre.text)
		completeRedraw())
	on btCon pressed do if root != undefined do (undo "BipFit connect" on (lb1.text = (if ddPreset.selection == 4 then (BipFit.connectUE root fallback:ckFb.checked) else (BipFit.connect root pattern:(BipFit.skinPattern ddPreset.selection) fallback:ckFb.checked))))
	on btDis pressed do (undo "BipFit disconnect" on (lb1.text = BipFit.disconnect()))
	on btRep pressed do if root != undefined do messageBox (BipFit.report root ddPreset.selection prefix:edPre.text) title:"BipFit"
	on btLines pressed do (undo "BipFit bone display" on (lb1.text = BipFit.setBoneDisplay #lines))
	on btHideB pressed do (undo "BipFit bone display" on (lb1.text = BipFit.setBoneDisplay #hide))
	on btNormB pressed do (undo "BipFit bone display" on (lb1.text = BipFit.setBoneDisplay #normal))
	on btImp pressed do (
		local f = getOpenFileName caption:"리깅 FBX (블렌더 'AccuRIG 정리' 결과)" types:"FBX (*.fbx)|*.fbx"
		if f != undefined do (
			lb1.text = "가져오는 중... (메쉬가 크면 1분 넘게 걸릴 수 있음)"
			windows.processPostedMessages()
			undo "BipFit import rig" on (lb1.text = BipFit.importRigWeights f)
			format "%\n" BipFit.log))
	on btChk pressed do (
		lb1.text = "점검 중..."
		windows.processPostedMessages()
		local r = BipFit.checkExport()
		lb1.text = r
		format "%\n" r
		messageBox r title:"BipFit 추출 전 점검")
	on btRelink pressed do (undo "BipFit relink" on (lb1.text = BipFit.relinkLegacy()))
	on btClean pressed do (
		local tg = BipFit.skinTargets selection
		if tg.count == 0 do (
			if queryBox "선택한 Skin 메쉬가 없습니다.\n씬의 모든 Skin 메쉬에서 사용하지 않는 본을 제거할까요?" title:"BipFit" do tg = BipFit.skinTargets objects)
		if tg.count > 0 then (
			local s = ""
			for i = 1 to tg.count do (
				lb1.text = "스킨 정리 중 (" + (i as string) + "/" + (tg.count as string) + "): " + tg[i].name + "\n(메쉬 하나에 수십 초~1분 넘게 걸릴 수 있음)"
				windows.processPostedMessages()
				s += (BipFit.cleanSkin tg[i]) + "\n")
			select tg
			lb1.text = s
			format "%\n" s)
		else lb1.text = "정리할 Skin 메쉬가 없음")
)

macroScript BipFitTool category:"Claude" buttonText:"BipFit" tooltip:"Biped 맞추기·연결"
(
	try (destroyDialog BipFitRoll) catch()
	createDialog BipFitRoll 230 740
)
