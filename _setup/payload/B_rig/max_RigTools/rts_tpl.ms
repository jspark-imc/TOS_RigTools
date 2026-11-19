-- ======================================================================
--  TOS_RigTools - 8. 리깅 완료 (템플릿 저장, 2026-10-30)
--  리깅이 끝난 캐릭터의 전체 데이터를 템플릿 폴더에 저장 → Blender 가 정리·검사하고
--  몸 웨이트 템플릿·세컨더리 참고값을 다시 계산 (다음 캐릭터부터 자동 반영)
--  저장: 메쉬(위치·노멀·면·UV 채널1)·스킨 웨이트·본/헬퍼 구조(트랜스폼·크기·컨트롤러·컨스트레인트)·
--        파트 면 기록(7760·7761)·테스트 키 프레임 모양·Biped FBX·전체 리그 FBX
-- ======================================================================
global trts_tplDirDefault = @"E:\anisrc\ani_tip\ai\00_3_리깅 웨이트 템플릿"
global trts_tplDir, trts_rigDone, trts_tplWriteNodes

fn trts_tplIni = ((getDir #plugcfg) + "\\TosRig.ini")

-- 저장 폴더: 팀 기본 폴더 → 이 PC 에서 고른 폴더(기억) → 없으면 한 번 물어보고 기억
fn trts_tplDir ask:true = (
	if doesDirectoryExist trts_tplDirDefault do return trts_tplDirDefault
	local d = getINISetting (trts_tplIni()) "template" "dir"
	if d != "" and doesDirectoryExist d do return d
	if not ask do return undefined
	local p = getSavePath caption:"리깅 웨이트 템플릿을 저장할 폴더를 골라 주세요 (팀 공용: ...\\ai\\00_3_리깅 웨이트 템플릿)" initialDir:(getDir #maxroot)
	if p == undefined do return undefined
	setINISetting (trts_tplIni()) "template" "dir" p
	p
)

fn trts_tplEsc s = ( substituteString (substituteString (s as string) "\t" " ") "\n" " " )

-- 본·헬퍼·Biped·스킨 메쉬 노드 정보 (탭 구분 key=value 한 줄씩)
fn trts_tplWriteNodes path = (
	local f = createFile path encoding:#utf8
	for o in objects do (
		local c = classOf o
		local skinned = (MaxBridge.getSkin o) != undefined
		if not (c == BoneGeometry or c == Biped_Object or c == Point or c == Dummy or isKindOf o Helper or c == Box or skinned) do continue
		local tm = o.transform
		format "name=%\tclass=%\tparent=%\tlayer=%\thidden=%\twire=%\t" (trts_tplEsc o.name) (c as string) (if o.parent == undefined then "" else trts_tplEsc o.parent.name) (try (trts_tplEsc o.layer.name) catch "") o.isHidden (o.wirecolor as string) to:f
		format "tm=% % % % % % % % % % % %\t" tm.row1.x tm.row1.y tm.row1.z tm.row2.x tm.row2.y tm.row2.z tm.row3.x tm.row3.y tm.row3.z tm.row4.x tm.row4.y tm.row4.z to:f
		if c == BoneGeometry do format "bone=% % % % % %\t" o.width o.height o.length o.taper (try o.boxMode catch "?") o.renderable to:f
		if c == Box do format "box=% % %\t" o.length o.width o.height to:f
		if c == Point do format "point=%\t" o.size to:f
		local pc = try (o.position.controller) catch undefined, rc = try (o.rotation.controller) catch undefined
		format "posCtrl=%\trotCtrl=%\tctrl=%\t" (classOf pc) (classOf rc) (classOf o.controller) to:f
		-- 컨스트레인트 대상과 웨이트 (리스트 컨트롤러 안쪽까지)
		local cons = #()
		for cc in #(pc, rc) where cc != undefined do (
			local subs = #(cc)
			try (if isKindOf cc Rotation_List or isKindOf cc Position_List do subs = for i = 1 to cc.count collect cc[i].controller) catch ()
			for s in subs do (
				local n = try (s.getNumTargets()) catch 0
				if n > 0 do (
					local t = (classOf s) as string + ":"
					for i = 1 to n do t += (try (trts_tplEsc (s.getNode i).name) catch "?") + "@" + (try ((s.getWeight i) as string) catch "?") + ","
					try (t += "relative=" + (s.relative as string)) catch ()
					append cons t
				)
				try (if isKindOf s Position_Expression or isKindOf s Float_Expression or isKindOf s Rotation_Expression do append cons ((classOf s) as string + ":expr=" + (trts_tplEsc (s.getExpression()))) ) catch ()
			)
		)
		local lk = try (o.lookat) catch undefined
		format "cons=%\t" (if cons.count == 0 then "" else (cons as string)) to:f
		format "user=%\tskinned=%\n" (trts_tplEsc (getUserPropBuffer o)) skinned to:f
	)
	close f
)

fn trts_rigDone = (
	if trts_blJob != undefined do return ("이미 Blender 작업 중이에요: " + (trts_blName trts_blJob[2]) + "\n끝난 뒤에 다시 누르세요.")
	if MaxBridge == undefined do return "Max Bridge 가 없어요. 설치기를 먼저 실행하세요."
	local ms = MaxBridge.skinnedMeshes()
	if ms.count == 0 do return "스킨이 있는 메쉬가 없어요. 스킨 적용 뒤에 눌러 주세요."
	local hasKeys = false
	for o in objects where classOf o == Biped_Object while not hasKeys do (try (if o.controller.keys.count > 0 do hasKeys = true) catch ())
	if not hasKeys do (
		if not (queryBox "테스트 키가 없어서 찢어짐 검사를 못 해요.\n[7. 테스트 키 생성] 을 먼저 하면 검사까지 해서 저장해요.\n\n그래도 지금 저장할까요?" title:"Rig Tools - 리깅 완료") do return "취소했어요. (변경 없음)"
	)
	local dir = trts_tplDir()
	if dir == undefined do return "취소했어요. (저장 폴더를 고르지 않음)"
	local t0 = timeStamp()
	local cache = trts_blDir() + "tplcache\\" + (t0 as string) + "\\"
	makeDir cache all:true
	local sel = selection as array, mode = getCommandPanelTaskMode(), st = sliderTime
	trts_blSay "리깅 완료: Max 데이터 내보내는 중... (메쉬·웨이트·본 구조, 1~3분)"
	local frames = if hasKeys then #(10, 30, 50, 70, 100, 110, 120, 180, 200, 210, 230) else #()
	local info = createFile (cache + "info.txt") encoding:#utf8
	format "file\t%\npath\t%\nunits\t%\t%\nuser\t%\nframes\t%\n" maxFileName maxFilePath (units.SystemType as string) (units.SystemScale as string) (sysInfo.username) (if frames.count == 0 then "" else ((for t in frames collect t as string) as string)) to:info
	try (format "range\t% %\n" (animationRange.start.frame as integer) (animationRange.end.frame as integer) to:info) catch ()
	disableSceneRedraw()
	try (
		sliderTime = 0
		for k = 1 to ms.count do (
			local o = ms[k], sk = MaxBridge.getSkin o
			-- 바인드 모양 (스킨 끄고)
			local sks = for md in o.modifiers where classOf md == Skin and md.enabled collect md
			for md in sks do md.enabled = false
			local m = snapshotAsMesh o
			for md in sks do md.enabled = true
			local nv = m.numverts
			format "mesh\t%\t%\t%\t%\t%\n" k o.name nv m.numfaces (try (sk.bone_Limit) catch 4) to:info
			local f = createFile (cache + "mesh_" + (k as string) + ".txt") encoding:#utf8
			for v = 1 to nv do (local p = getVert m v, n = getNormal m v; format "% % % % % %\n" p.x p.y p.z n.x n.y n.z to:f)
			close f
			f = createFile (cache + "faces_" + (k as string) + ".txt") encoding:#utf8
			for i = 1 to m.numfaces do (local fc = getFace m i; format "% % %\n" (fc.x as integer) (fc.y as integer) (fc.z as integer) to:f)
			close f
			try (
				if meshop.getMapSupport m 1 do (
					f = createFile (cache + "uv_" + (k as string) + ".txt") encoding:#utf8
					for i = 1 to m.numfaces do (local tf = meshop.getMapFace m 1 i; local a = meshop.getMapVert m 1 tf.x, b = meshop.getMapVert m 1 tf.y, c = meshop.getMapVert m 1 tf.z; format "% % % % % %\n" a.x a.y b.x b.y c.x c.y to:f)
					close f
				)
			) catch ()
			delete m
			MaxBridge.dumpSkinNamed o.name (cache + "weights_" + (k as string) + ".txt")
			-- 테스트 키 프레임 모양 (스킨 켠 채)
			for t in frames do (
				local mm = at time t snapshotAsMesh o
				if mm.numverts == nv do (
					f = createFile (cache + "pose_" + (k as string) + "_" + (t as string) + ".txt") encoding:#utf8
					for v = 1 to nv do (local p = getVert mm v; format "% % %\n" p.x p.y p.z to:f)
					close f
				)
				delete mm
			)
			-- 파트 면 기록 (Max 수정 / ② 로 고른 면)
			local a7760 = getAppData o 7760, a7761 = getAppData o 7761
			if a7760 != undefined do (f = createFile (cache + "parts_" + (k as string) + ".txt") encoding:#utf8; format "%\n#MAP\t%\n" a7760 (if a7761 == undefined then "" else a7761) to:f; close f)
		)
		-- 스킨에 쓰인 본의 실제 모양 (Blender 분석용)
		local names = MaxBridge.skinInfluences()
		local f = createFile (cache + "bones.txt") encoding:#utf8
		for n in names do (
			local o = getNodeByName n
			if o == undefined do continue
			local sg = MaxBridge.boneSeg o
			format "%\t%\t%\t%\t% % %\t% % %\n" n (try o.layer.name catch "") (if o.parent == undefined then "" else o.parent.name) ((classof o) as string) sg[1].x sg[1].y sg[1].z sg[2].x sg[2].y sg[2].z to:f
		)
		close f
		trts_tplWriteNodes (cache + "nodes.txt")
		clearSelection()
		select (for o in objects where classof o == Biped_Object collect o)
		local r1 = MaxBridge.exportFBX (cache + "bip.fbx") selOnly:true anim:false
		clearSelection()
		select (for o in objects where (MaxBridge.getSkin o) != undefined or classOf o == BoneGeometry or classOf o == Biped_Object or classOf o == Point or classOf o == Dummy collect o)
		local r2 = MaxBridge.exportFBX (cache + "rig.fbx") selOnly:true anim:false
		format "fbx\t%\nrigfbx\t%\n" r1 r2 to:info
	) catch (
		format "error\t%\n" (getCurrentException()) to:info
	)
	close info
	clearSelection(); if sel.count > 0 do select sel
	sliderTime = st
	setCommandPanelTaskMode mode
	enableSceneRedraw()
	completeRedraw()
	local ex = ", \"cache\": \"" + (substituteString cache "\\" "/") + "\", \"tpldir\": \"" + (substituteString dir "\\" "/") + "\", \"maxsec\": " + (((timeStamp() - t0) / 1000) as string)
	trts_blStart "tplsave" extra:ex
)
