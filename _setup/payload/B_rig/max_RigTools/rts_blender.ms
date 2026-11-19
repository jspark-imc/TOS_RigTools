-- ======================================================================
--  TOS_RigTools - Blender 작업 버튼 (2.5 단계)
--  Max 버튼 → %LOCALAPPDATA%\GE_RigJobs\job_<id>.json → Blender(GE 작업 실행기 애드온)가 실행
--  Blender 가 안 떠 있으면 띄움. 기다리는 동안 Max 는 멈추지 않음(타이머로 결과 확인).
--  Blender 는 이 Max 의 브리지 포트(MaxBridge.port)로 연결해서 본·스킨을 넣음.
-- ======================================================================
global trts_blStart, trts_blTick, trts_blTimer, trts_blJob, trts_blT0, trts_blLaunchT
-- 뒤에서 정의되지만 앞 함수들이 부르는 것들 (먼저 선언해야 컴파일 때 찾음)
global trts_skinOff, trts_skinIsOff
global trts_mkSetAll, trts_obCenterToggle, trts_obCenterSet, trts_obMagicaState, trts_obCenterBones, trts_obMagicaExtra, trts_logColor, trts_obColorize, trts_obPalette, trts_obColorName, trts_obColorIdx, trts_obRootExtra, trts_obParentPick, trts_obParentRoll, trts_obParentNames, trts_partMaxFix, trts_partAutoStart, trts_obNodes, trts_obAddTree, trts_pmCaption, trts_pmBody, trts_obItems, trts_obGroups, trts_obKindLabel, trts_obMapSet, trts_obPick, trts_obPickFaces, trts_obDeletePart, trts_obDeleteAll, trts_pmEditing
global trts_blKindName = #(#("all", "한 번에 (얼굴·가슴 + 헤어 + 치마·망토 + 스킨)"), #("import", "Blender 로 가져오기"), #("bones", "얼굴 본"), \
	#("split", "파츠 나누기"), #("hair", "헤어 본"), #("parts", "세컨더리 본 만들기"), #("parts_edit", "파트 Blender 에서 고치기"), #("skin", "스킨 적용 (일괄)"), #("tplsave", "리깅 완료 (템플릿 저장)"))

fn trts_blDir = ( local d = (systemTools.getEnvVariable "LOCALAPPDATA") + "\\GE_RigJobs\\"; makeDir d all:true; d )
fn trts_blRead f = ( try ((dotNetClass "System.IO.File").ReadAllText f) catch "" )
fn trts_blSay s = ( try (TosRigRoll.tLog.ForeColor = trts_logColor false) catch (); try (TosRigRoll.tLog.text = s) catch () )
fn trts_blName k = ( local r = k; for e in trts_blKindName where e[1] == k do r = e[2]; r )

-- 실행기(runner.json) 하트비트가 몇 초 전인지 (없으면 큰 수)
-- 2.7: Claude Max(브리지 포트 9878~9899)는 Claude 블렌더 실행기(runner_claude.json)를 봄 — 작업자 블렌더가 Claude 작업을 안 가져가게
fn trts_blAge = (
	local p = try (MaxBridge.port) catch 0
	local f = trts_blDir() + (if p != undefined and p >= 9878 and p <= 9899 then "runner_claude.json" else "runner.json")
	if not (doesFileExist f) then 1e9 else (
		try (
			local t = (dotNetClass "System.IO.File").GetLastWriteTimeUtc f
			((dotNetClass "System.DateTime").UtcNow.Subtract t).TotalSeconds
		) catch 1e9
	)
)

-- GE 작업 실행기(ge_jobs.py)가 깔린 Blender
fn trts_blFind = (
	local appd = systemTools.getEnvVariable "APPDATA"
	local roots = #("C:\\Program Files\\Blender Foundation\\")
	local pf = systemTools.getEnvVariable "ProgramFiles"
	if pf != undefined do appendIfUnique roots (pf + "\\Blender Foundation\\")
	local best = undefined, any = undefined
	for r in roots do for sub in (getDirectories (r + "Blender*")) do (
		local exe = sub + "blender.exe"
		if doesFileExist exe do (
			any = exe
			local ver = substituteString (filenameFromPath (trimRight sub "\\")) "Blender " ""
			if appd != undefined and doesFileExist (appd + "\\Blender Foundation\\Blender\\" + ver + "\\scripts\\addons\\ge_jobs.py") do best = exe
		)
	)
	if best != undefined then best else any
)

fn trts_blStop = ( try (trts_blTimer.stop()) catch (); trts_blJob = undefined )

fn trts_blTick sender args = (
	if trts_blJob == undefined do ( trts_blStop(); return ok )
	local d = trts_blDir(), id = trts_blJob[1], k = trts_blJob[2]
	local sec = ((timeStamp() - trts_blT0) / 1000) as integer
	local rf = d + "res_" + id + ".txt"
	if doesFileExist rf then (
		local t = trts_blRead rf
		trts_blStop()
		local lines = filterString t "\n"
		local okk = lines.count > 0 and lines[1] == "OK"
		local msg = ""
		for i = 3 to lines.count do msg += lines[i] + "\n"
		if okk and (k == "parts" or k == "parts_edit") do try (trts_obColorize()) catch ()
		if okk and k != "import" and trts_layerTidy != undefined do (
			local lt = try (undo "레이어 정리" on (trts_layerTidy())) catch ""
			if lt != "" do msg += "(새 본 레이어 정리함)\n"
		)
		local head = (if okk then "완료: " else "실패: ") + (trts_blName k) + " (" + (sec as string) + "초)\n\n"
		trts_blSay (head + msg + (if okk then "\nBlender 창은 열어 둬요. 웨이트를 손보려면 Blender 의 리깅 순서 패널을 쓰세요." else ""))
		try (deleteFile rf; deleteFile (d + "st_" + id + ".txt")) catch ()
		messageBox (head + msg) title:"TOS_RigTools - Blender"
	) else (
		local jf = d + "job_" + id + ".json"
		local st = trts_blRead (d + "st_" + id + ".txt")
		local waiting = doesFileExist jf
		if waiting and trts_blLaunchT != undefined and (timeStamp() - trts_blLaunchT) > 180000 and (trts_blAge()) > 30 do (
			trts_blStop()
			try (deleteFile jf) catch ()
			trts_blSay "실패: Blender 가 3분 안에 준비되지 않았어요.\nBlender 가 떴는지, 'GE 작업 실행기' 애드온이 켜져 있는지 확인하세요. (담당자에게 문의)"
			return ok
		)
		if sec > 3600 do ( trts_blStop(); trts_blSay "실패: 1시간이 지나도 끝나지 않았어요. Blender 창을 확인하세요."; return ok )
		trts_blSay ((trts_blName k) + " - " + (sec as string) + "초\n" + \
			(if waiting then (if trts_blLaunchT != undefined then "Blender 를 여는 중... (처음엔 20~40초)" else "Blender 가 받기를 기다리는 중...") else (if st == "" then "Blender 작업 중..." else st)) + \
			"\n\n기다리는 동안 이 Max 에서 다른 작업은 하지 마세요.")
	)
	ok
)

-- 이 Max 의 브리지 포트. Max 를 여러 개 켜서 기본 포트(9877)를 다른 Max 가 쓰고 있으면
-- 빈 포트(9901~9940, Claude Max 포트 9878~9899 와 안 겹침)로 옮겨서 켬
fn trts_blPort = (
	local isOn = try (MaxBridge.listener != undefined) catch false
	if isOn do return (try (MaxBridge.port) catch undefined)
	for p = 9901 to 9940 do (
		local r = try (MaxBridge.setPort p) catch "ERROR"
		if (try (MaxBridge.listener != undefined) catch false) do (
			format "[Rig Tools] 기본 포트를 다른 Max 가 써서 이 Max 의 브리지를 %번으로 켰어요.\n" p
			return p
		)
	)
	undefined
)

fn trts_blStart k extra:"" = (
	if trts_blJob != undefined do return ("이미 Blender 작업 중이에요: " + (trts_blName trts_blJob[2]) + "\n끝난 뒤에 다시 누르세요.")
	if MaxBridge == undefined do return "Max Bridge 가 없어요. 설치기를 먼저 실행하세요. (담당자에게 문의)"
	local port = trts_blPort()
	if port == undefined do return "Max Bridge 를 켜지 못했어요. Max 를 다시 켜 보세요. (담당자에게 문의)"
	if (for o in objects where classof o == Biped_Object collect o).count == 0 do return "Biped 가 없어요. [2. Biped 생성] 을 먼저 하세요."
	if k == "all" or k == "skin" do (
		if not (queryBox ((trts_blName k) + "\n\n마지막에 Max 메쉬의 Skin 을 새로 계산한 웨이트로 바꿔요. (Max 에서 Ctrl+Z 가능)\nMax 에서 칠한 파츠·손 본·헤어 웨이트는 그대로 둬요.\n\n진행할까요?") title:"TOS_RigTools - Blender") do return "취소했어요. (변경 없음)"
	)
	local d = trts_blDir()
	trts_blLaunchT = undefined
	if (trts_blAge()) > 8 do (
		local bl = trts_blFind()
		if bl == undefined do return "Blender 를 찾지 못했어요. 설치기를 먼저 실행하세요. (담당자에게 문의)"
		ShellLaunch bl ""
		trts_blLaunchT = timeStamp()
	)
	local id = (timeStamp() as string)
	local tmp = d + "job_" + id + ".tmp"
	local fs = createFile tmp
	format "{\"kind\": \"%\", \"port\": %, \"file\": \"%\"%}" k port (substituteString maxFileName "\"" "") extra to:fs
	close fs
	renameFile tmp (d + "job_" + id + ".json")
	trts_blJob = #(id, k)
	trts_blT0 = timeStamp()
	if trts_blTimer == undefined do trts_blTimer = dotNetObject "System.Windows.Forms.Timer"
	trts_blTimer.stop()
	dotNet.removeAllEventHandlers trts_blTimer
	trts_blTimer.interval = 1000
	dotNet.addEventHandler trts_blTimer "Tick" trts_blTick
	trts_blTimer.start()
	(trts_blName k) + " 시작" + (if trts_blLaunchT != undefined then " - Blender 를 여는 중... (20~40초)" else "") + "\n진행 상황은 여기에 계속 표시돼요."
)


-- ======================================================================
--  4_2 파트 지정 (치마·망토·기타): 바디 메쉬에서 면을 선택하고 [파트 추가]
--  파트마다 종류·체인·마디를 따로 가짐 (반원 치마 + 앞치마처럼 여러 조각, 리본·꼬리 같은 기타)
--  그 메쉬의 AppData 7760 에 저장: 줄마다 "종류|체인|마디|정점,정점,..."  (파일과 같이 저장됨)
-- ======================================================================
global trts_partAdd, trts_partDel, trts_partShow, trts_partClear, trts_partItems, trts_partInfo, trts_partData
global trts_mkKinds = #(#("skirt", "치마"), #("cape", "망토"), #("etc", "기타"), #("auto", "Max 지정"))
fn trts_mkLabel k = ( local r = k; for e in trts_mkKinds where e[1] == k do r = e[2]; r )
fn trts_mkOk o = ( isValidNode o and (classof o.baseObject == Editable_Poly or classof o.baseObject == Editable_mesh) )
-- 파트 목록 읽기/쓰기: #(#(종류, 체인, 마디, 정점 bitArray), ...)
fn trts_mkRead o = (
	local s = getAppData o 7760
	if s == undefined or s == "" then #() else (
		for ln in (filterString s "\n") where (filterString ln "|").count >= 3 collect (
			local f = filterString ln "|", b = #{}
			if f.count >= 4 do for t in (filterString f[4] ",") do b[t as integer] = true   -- "none|0|0|" = 지운 파트 자리 (번호 유지)
			#(f[1], f[2] as integer, f[3] as integer, b)
		)
	)
)
fn trts_mkWrite o parts = (
	if parts.count == 0 then deleteAppData o 7760 else (
		local ss = stringStream ""
		for p in parts do (
			format "%|%|%|" p[1] p[2] p[3] to:ss
			local first = true
			for i in p[4] do ( if not first do format "," to:ss; format "%" i to:ss; first = false )
			format "\n" to:ss
		)
		setAppData o 7760 (ss as string)
	)
)
fn trts_mkNodes = ( for o in geometry where (trts_mkOk o) and (getAppData o 7760) != undefined collect o )
-- 목록 상자에 보일 줄들 (모든 메쉬의 파트를 차례대로)
fn trts_partItems = (
	local out = #()
	for o in trts_mkNodes() do (
		local ps = trts_mkRead o
		for i = 1 to ps.count do (
			local p = ps[i]
			append out ((out.count + 1) as string + ". " + (trts_mkLabel p[1]) + "  " + (p[2] as string) + "×" + (p[3] as string) + "  (" + (p[4].numberSet as string) + "점, " + o.name + ")")
		)
	)
	out
)
-- 목록 번호 → #(노드, 그 노드 안 번호)
fn trts_mkAt idx = (
	local n = 0
	for o in trts_mkNodes() do ( local ps = trts_mkRead o; for i = 1 to ps.count do ( n += 1; if n == idx do return #(o, i) ) )
	undefined
)
fn trts_partInfo = ( local n = (trts_partItems()).count; if n == 0 then "파트: 없음" else ("파트 " + (n as string) + "개") )

fn trts_mkSelVerts o = (
	local b = o.baseObject
	if classof b == Editable_Poly then polyop.getVertsUsingFace b (polyop.getFaceSelection b)
	else ( local m = b.mesh; meshop.getVertsUsingFace m (getFaceSelection m) )
)

fn trts_partAdd k ch sg = (
	if selection.count != 1 do return "바디 메쉬 하나를 선택하고, 수정 패널에서 파트가 될 면(Polygon / Element)을 선택한 뒤 누르세요."
	local o = selection[1]
	if not (trts_mkOk o) do return (o.name + " 은(는) Editable Mesh / Poly 가 아니에요. 바디 메쉬를 선택하세요.")
	local v = trts_mkSelVerts o
	if v.numberSet == 0 do return "선택한 면이 없어요.\n수정 패널에서 Editable Mesh/Poly 의 면(Polygon) 또는 Element 를 선택하세요.\n(Skin 이 있으면 스택 맨 아래 Editable Mesh/Poly 를 고르고 선택)"
	local ps = trts_mkRead o, cut = 0
	for p in ps do ( local ov = (p[4] * v).numberSet; if ov > 0 do ( cut += ov; p[4] = p[4] - v ) )
	ps = for p in ps where p[4].numberSet > 0 collect p
	append ps #(k, ch, sg, v)
	trts_mkWrite o ps
	(trts_mkLabel k) + " 파트를 추가했어요: " + o.name + " 정점 " + (v.numberSet as string) + "개" + (if k == "auto" then " (종류·체인·마디는 Blender 가 자동)" else (", 체인 " + (ch as string) + " × 마디 " + (sg as string))) + \
		(if cut > 0 then "\n(다른 파트와 겹친 " + (cut as string) + "점은 그 파트에서 뺐어요)" else "") + \
		""
)

fn trts_partDel idx = (
	local pa = trts_mkAt idx
	if pa == undefined do return "목록에서 지울 파트를 고르세요."
	local ps = trts_mkRead pa[1]
	local lab = trts_mkLabel ps[pa[2]][1]
	deleteItem ps pa[2]
	trts_mkWrite pa[1] ps
	(idx as string) + "번 " + lab + " 파트를 지웠어요. (이미 만든 본은 [파트 본 만들기] 를 다시 누르면 정리돼요)"
)

fn trts_partShow idx = (
	local pa = trts_mkAt idx
	if pa == undefined do return "목록에서 볼 파트를 고르세요."
	local o = pa[1], p = (trts_mkRead o)[pa[2]]
	select o
	max modify mode
	try (modPanel.setCurrentObject o.baseObject) catch ()
	local b = o.baseObject
	subObjectLevel = 1
	if classof b == Editable_Poly then polyop.setVertSelection b p[4] else ( setVertSelection b.mesh p[4]; update o )
	redrawViews()
	(idx as string) + "번 " + (trts_mkLabel p[1]) + " 파트의 정점을 선택해 보여요 (" + (p[4].numberSet as string) + "점)."
)

fn trts_partClear = (
	local ns = trts_mkNodes()
	if ns.count == 0 do return "지울 파트가 없어요."
	if not (queryBox "파트 지정을 모두 지울까요?\n(이미 만든 본은 그대로)" title:"Rig Tools - 파트 지우기") do return "취소했어요."
	for o in ns do deleteAppData o 7760
	"파트 지정을 모두 지웠어요."
)

-- Blender 용: "종류|체인|마디|노드|x,y,z;x,y,z..." 줄들 (월드 좌표, Max 단위)
fn trts_partData = (
	local ss = stringStream ""
	for o in trts_mkNodes() do (
		local b = o.baseObject, tm = o.objectTransform
		for p in (trts_mkRead o) do (
			format "%|%|%|%|" p[1] p[2] p[3] o.name to:ss
			for i in p[4] do (
				local q = if classof b == Editable_Poly then (polyop.getVert b i node:o) else ((getVert b.mesh i) * tm)
				format "%,%,%;" q.x q.y q.z to:ss
			)
			format "\n" to:ss
		)
	)
	ss as string
)



-- ======================================================================
--  4_2 ② [Max 수정]: 바디 메쉬에서 고른 면 = 파트 (종류·체인·마디는 Blender 가 자동) → 바로 본 다시 만들기
-- ======================================================================
global trts_partMaxFix, trts_pmEditing, trts_obNodes, trts_obAddTree
global trts_obLayers = #("bone_body", "bone_skirt", "bone_cape", "bone_etc")   -- 10/30: 새로 만드는 본은 bone_body (옛 장면은 bone_skirt 등)
fn trts_obAddTree o out = ( appendIfUnique out o; for c in o.children where classof c != Biped_Object do trts_obAddTree c out; ok )
-- [② 치마·망토 본 만들기] 로 만든 본 (bone_skirt / bone_cape / bone_etc 레이어 + 그 자식 _end 등)
fn trts_obNodes = (
	local out = #()
	-- 레이어만 보면 bone_body 의 다른 본까지 잡히므로 이름(bone_skirt / bone_cape / bone_obj)도 같이 봄
	for o in objects where classof o == BoneGeometry and (findItem trts_obLayers (toLower o.layer.name)) > 0 and \
		(matchPattern o.name pattern:"bone_skirt*" or matchPattern o.name pattern:"bone_cape*" or matchPattern o.name pattern:"bone_obj*") do trts_obAddTree o out
	out
)
fn trts_pmCaption s = ( try (TosRigRoll.bPtMax.caption = s) catch () )
-- 바디 메쉬: 파트 지정이 있는 메쉬, 없으면 보이는 Editable Mesh/Poly 중 정점이 가장 많은 것
fn trts_pmBody = (
	local ns = trts_mkNodes()
	if ns.count > 0 then ns[1] else (
		local best = undefined, bn = 0
		for o in geometry where not o.isHidden and (trts_mkOk o) and classof o != Biped_Object do (
			local n = try (getNumVerts o.baseObject.mesh) catch 0
			if n > bn do ( best = o; bn = n )
		)
		best
	)
)
-- [Max 수정]
--   1번째 누름 (면 선택 없음): 만든 치마·망토 본과 이전 Max 지정을 지우고, 바디 메쉬를 선택해 둠 → 버튼이 [선택한 면으로 본 만들기] 로 바뀜
--   2번째 누름 (면 선택 있음): 그 면을 파트로 지정하고 본 만들기 (파트가 여러 개면 하나씩 골라 누름)
fn trts_partMaxFix = (
	local o = if selection.count == 1 then selection[1] else undefined
	local v = if o != undefined and (trts_mkOk o) then (try (trts_mkSelVerts o) catch #{}) else #{}
	if v.numberSet > 0 then (
		local rx = trts_obRootExtra()
		if not rx[1] do return "취소했어요. (부모 본을 고르지 않음)"
		select o
		-- 고른 면이 이미 만든 파트와 "많이"(작은 쪽의 절반 이상) 겹치면 그 파트를 같은 번호 그대로 바꿈 = 다시 수정.
		-- 경계 정점 몇 개만 닿는 것은 새 파트 (10/30: 맞닿은 장식이 기존 파트를 덮어쓰던 문제)
		-- 번호는 절대 밀리지 않게: 같이 겹친 다른 파트는 빈 자리(none)로 둠
		local ps = trts_mkRead o, keep = #(), idx = 0
		local nCh = try (TosRigRoll.spObCh.value) catch 0, nSg = try (TosRigRoll.spObSg.value) catch 0   -- 0 = 자동
		for p in ps do (
			local ov = (p[4] * v).numberSet
			local small = amin p[4].numberSet v.numberSet
			if p[1] != "none" and small > 0 and ov * 2 >= small then (
				if idx == 0 then ( append keep #("auto", nCh, nSg, v); idx = keep.count )
				else append keep #("none", 0, 0, #{})
			) else append keep p
		)
		local isNew = idx == 0
		if isNew do ( append keep #("auto", nCh, nSg, v); idx = keep.count )
		trts_mkWrite o keep
		local before = 0
		for x in trts_mkNodes() while x != o do before += (trts_mkRead x).count
		local gi = before + idx
		(if isNew then ((gi as string) + "번 파트를 추가했어요") else ((gi as string) + "번 파트를 고른 면으로 바꿨어요")) + \
			" (" + o.name + " 정점 " + (v.numberSet as string) + "개, 둘레 체인 " + (if nCh > 0 then (nCh as string) else "자동") + " · 마디 " + (if nSg > 0 then (nSg as string) else "자동") + "). 이 파트 본만 다시 만들어요.\n\n" + \
			(trts_blStart "parts" extra:(", \"inc\": " + (gi as string) + rx[2]))
	) else (
		-- 10/30: 면을 안 고르고 누르면 지우지 않고 고르기 준비만 (다른 파트 본은 그대로 남음)
		trts_pmEditing = true
		trts_pmCaption "선택한 면으로 본 만들기"
		local b = trts_pmBody()
		if b != undefined do ( select b; max modify mode )
		redrawViews()
		(if b != undefined then ("바디 메쉬(" + b.name + ")를 선택해 뒀어요.\n") else "바디 메쉬를 선택하세요.\n") + \
			"수정 패널 맨 아래 Editable Mesh / Poly 에서 고칠 부분(또는 새로 본을 붙일 부분)의 면을 고르고 [선택한 면으로 본 만들기] 를 누르세요.\n" + \
			"이미 있는 파트와 많이 겹치면 그 파트만 다시 만들고, 겹치지 않으면 새 파트로 추가해요. 다른 파트 본은 그대로예요.\n" + \
			"(Skin 경고 창이 뜨면 Yes)"
	)
)

-- [② 치마·망토 본 만들기] = 자동: Max 지정을 지우고 수정 모드를 끝냄
global trts_partAutoStart
fn trts_partAutoStart lev:0 ask:false = (
	-- 1.61: lev = 파츠 본 범위 1/2/3 (0 = 블렌더 기본값). ask = 범위 버튼: Max 에서 선택한 면으로 고친 파트가 있으면 지우기 전에 확인 (블렌더 범위 버튼과 같게)
	if ask do (
		local n = 0
		for o in trts_mkNodes() do for p in (trts_mkRead o) where p[1] == "auto" do n += 1
		if n > 0 and not (queryBox ("Max 에서 선택한 면으로 고친 파트 " + (n as string) + "개가 지워지고 범위 " + (lev as string) + " 로 자동으로 새로 만들어요. 계속할까요?") title:("Rig Tools - 파츠 본 범위 " + (lev as string))) do return "취소했어요. (변경 없음)"
	)
	local rx = trts_obRootExtra()
	if not rx[1] do return "취소했어요. (부모 본을 고르지 않음)"
	for x in trts_mkNodes() do ( deleteAppData x 7761; deleteAppData x 7760 )
	trts_pmEditing = false
	trts_pmCaption "Max 수정"
	trts_blStart "parts" extra:(rx[2] + (if lev > 0 then (", \"level\": " + (lev as string)) else ""))
)

-- [치마·망토 본 일괄 삭제]: bone_skirt / bone_cape / bone_etc 레이어 본과 그 끝본(_end)을 모두 지움 (Max 지정 면은 그대로)
global trts_obDeleteAll
fn trts_obDeleteAll = (
	local ns = trts_obNodes()
	local nm = (trts_partItems()).count
	if ns.count == 0 and nm == 0 and trts_pmEditing != true do return "지울 치마·망토 본이 없어요.\n[② 치마·망토 본 만들기] 또는 [Max 수정] 으로 만드세요."
	if not (queryBox ("치마·망토·기타 본 " + (ns.count as string) + "개를 모두 지우고 처음 상태로 돌릴까요?\n(끝본 _end 포함. Max 에서 고른 파트 면 지정도 지워요)\n\n본은 Ctrl+Z 로 되돌릴 수 있어요") title:"Rig Tools - 치마·망토 본 일괄 삭제") do return "취소했어요. (변경 없음)"
	if ns.count > 0 do undo "치마·망토 본 일괄 삭제" on (
		for x in ns do try (x.rotation.controller = Euler_XYZ(); x.position.controller = Position_XYZ()) catch ()
		for x in ns where isValidNode x do try (delete x) catch ()
	)
	for x in trts_mkNodes() do ( deleteAppData x 7761; deleteAppData x 7760 )
	trts_pmEditing = false
	trts_pmCaption "Max 수정"
	redrawViews()
	"치마·망토·기타 본 " + (ns.count as string) + "개를 지웠어요" + (if nm > 0 then (" (Max 파트 지정 " + (nm as string) + "개도 지움)") else "") + ".\n" + \
		"다시 만들기: [② 치마·망토 본 만들기] = 자동 / [Max 수정] = 면을 직접 골라서"
)

-- ======================================================================
--  4_2 본 목록: 만든 파트(본 이름 앞부분 bone_skirt_ / bone_cape2_ / bone_obj02_)별로
--  클릭 = 그 파트 본 선택 / 더블클릭 = 그 파트를 만든 면 선택 (Max 지정 파트만)
--  파트 번호 → 앞부분: 바디 메쉬 AppData 7761 "bone_skirt_|bone_obj02_|..." (Blender 가 [Max 수정] 뒤에 적어 줌)
-- ======================================================================
global trts_obGroups, trts_obItems, trts_obPick, trts_obPickFaces, trts_obMapSet
fn trts_obGroups = (
	local keys = #(), grp = #()
	for o in trts_obNodes() do (
		local t = filterString o.name "_"
		if t.count >= 3 do (
			local k = toLower (t[1] + "_" + t[2] + "_")
			local i = findItem keys k
			if i == 0 do ( append keys k; append grp #(); i = keys.count )
			append grp[i] o
		)
	)
	-- 만든 순서(파트 번호) 대로: 바디 메쉬 기록(7761) 순서, 기록에 없는 것은 뒤로
	local bd = try (trts_pmBody()) catch undefined
	local mp = if bd != undefined then (getAppData bd 7761) else undefined
	local order = if mp == undefined then #() else (filterString mp "|")
	local idx = for k in keys collect (local j = findItem order k; if j == 0 then 1000 + (findItem keys k) else j)
	local ks = #(), gs = #()
	for n = 1 to keys.count do (
		local best = 0, bv = 1e9
		for i = 1 to keys.count where idx[i] < bv do ( best = i; bv = idx[i] )
		append ks keys[best]; append gs grp[best]; idx[best] = 1e10
	)
	#(ks, gs)
)
fn trts_obKindLabel k = ( if matchPattern k pattern:"bone_skirt*" then "치마" else if matchPattern k pattern:"bone_cape*" then "망토" else "기타" )
fn trts_obItems = (
	local g = trts_obGroups()
	for i = 1 to g[1].count collect ((i as string) + ". " + (trts_obKindLabel g[1][i]) + "   " + (trimRight g[1][i] "_") + "   본 " + (g[2][i].count as string) + "개   (" + (try (trts_obColorName g[1][i]) catch "-") + ")")
)
fn trts_obMapSet keys = (
	local b = trts_pmBody()
	if b != undefined do (
		local s = ""
		for k in keys do s += (if s == "" then "" else "|") + (toLower k)
		setAppData b 7761 s
	)
	try (TosRigRoll.lbObParts.items = trts_obItems()) catch ()
	"OK"
)
fn trts_obPick i = (
	local g = trts_obGroups()
	if i < 1 or i > g[1].count do return "목록에서 파트를 고르세요."
	local ns = g[2][i]
	for o in ns do ( try (o.layer.isHidden = false) catch (); o.isHidden = false )
	max create mode
	select ns
	redrawViews()
	(i as string) + "번 " + (trts_obKindLabel g[1][i]) + " (" + (trimRight g[1][i] "_") + ") 본 " + (ns.count as string) + "개를 선택했어요 (_end 포함).\n" + \
		"미세 조정하세요. 이 파트를 만든 면을 다시 고르려면 목록을 더블클릭."
)
fn trts_obPickFaces i = (
	local g = trts_obGroups()
	if i < 1 or i > g[1].count do return "목록에서 파트를 고르세요."
	local k = g[1][i]
	local b = trts_pmBody()
	local mp = if b != undefined then (getAppData b 7761) else undefined
	local idx = if mp == undefined then 0 else (findItem (filterString mp "|") k)
	local pa = if idx > 0 then (trts_mkAt idx) else undefined
	if pa == undefined do return ((i as string) + "번 파트는 [② 치마·망토 본 만들기] 로 자동으로 만든 파트라 고른 면 기록이 없어요.\n고치려면 [Max 수정] → 면 선택 → [선택한 면으로 본 만들기].")
	local o = pa[1], v = (trts_mkRead o)[pa[2]][4]
	local bo = o.baseObject, fs = #{}
	if classof bo == Editable_Poly then (
		for f in (polyop.getFacesUsingVert bo v) do ( local inside = true; for x in (polyop.getFaceVerts bo f) where not v[x] do inside = false; if inside do fs[f] = true )
	) else (
		local m = bo.mesh
		for f in (meshop.getFacesUsingVert m v) do ( local fv = getFace m f; if v[fv.x] and v[fv.y] and v[fv.z] do fs[f] = true )
	)
	select o
	max modify mode
	modPanel.setCurrentObject bo        -- Skin 이 있으면 Max 가 경고 창을 띄움 (Yes)
	subObjectLevel = 4
	if classof bo == Editable_Poly then polyop.setFaceSelection bo fs else ( setFaceSelection bo.mesh fs; update o )
	redrawViews()
	trts_pmEditing = true
	trts_pmCaption "선택한 면으로 본 만들기"
	(i as string) + "번 " + (trts_obKindLabel k) + " 파트를 만든 면 " + (fs.numberSet as string) + "개를 선택했어요.\n" + \
		"면을 더하거나 빼고 [선택한 면으로 본 만들기] 를 누르면 이 파트만 다시 만들어요."
)

-- 본 목록에서 고른 파트 하나만 지움: 그 파트 본 + 고른 면 기록 (번호는 "none" 자리로 남겨서 다른 파트 이름이 안 바뀜)
global trts_obDeletePart
fn trts_obDeletePart i = (
	local g = trts_obGroups()
	if i < 1 or i > g[1].count do return "본 목록에서 지울 파트를 고르세요."
	local k = g[1][i], ns = g[2][i]
	if not (queryBox ((i as string) + "번 " + (trts_obKindLabel k) + " (" + (trimRight k "_") + ") 본 " + (ns.count as string) + "개를 지울까요?\n(Ctrl+Z 로 되돌릴 수 있어요. 다른 파트는 그대로)") title:"Rig Tools - 파트 삭제") do return "취소했어요. (변경 없음)"
	undo "파트 본 삭제" on (
		for x in ns do try (x.rotation.controller = Euler_XYZ(); x.position.controller = Position_XYZ()) catch ()
		for x in ns where isValidNode x do try (delete x) catch ()
	)
	-- 고른 면 기록도 비움 (자리는 남김)
	local b = trts_pmBody()
	local mp = if b != undefined then (getAppData b 7761) else undefined
	local idx = if mp == undefined then 0 else (findItem (filterString mp "|") k)
	local pa = if idx > 0 then (trts_mkAt idx) else undefined
	if pa != undefined do (
		local ps = trts_mkRead pa[1]
		ps[pa[2]] = #("none", 0, 0, #{})
		trts_mkWrite pa[1] ps
	)
	try (TosRigRoll.lbObParts.items = trts_obItems()) catch ()
	redrawViews()
	(i as string) + "번 " + (trts_obKindLabel k) + " 본 " + (ns.count as string) + "개를 지웠어요." + (if pa != undefined then " (고른 면 기록도 지움)" else "")
)

-- [root 본] 체크를 끄면: 체인을 붙일 부모 본을 뷰포트에서 고르게 함 (root·_00 연결 본은 안 만듦)
-- returns #(계속할지, job 에 붙일 글자)
global trts_obRootExtra, trts_obParentPick, trts_obParentRoll, trts_obParentNames
-- 부모 후보: Biped 본(Nub·Footsteps 빼고) + 보조 본(bone_helper 등, 치마·망토·헤어 본 빼고)
fn trts_obParentNames = (
	local bip = for o in objects where classof o == Biped_Object and not (matchPattern o.name pattern:"*Nub") and not (matchPattern o.name pattern:"*Footsteps") collect o.name
	local sec = #("bone_skirt", "bone_cape", "bone_etc", "bone_hair", "nub")
	local bn = for o in objects where classof o == BoneGeometry and (findItem sec (toLower o.layer.name)) == 0 collect o.name
	sort bn
	bip + bn
)
-- [root 본] 체크를 끄면: 뷰포트에서 부모 본을 클릭해서 고름 (root 는 안 만들고, 그 본에서 _00 연결 본이 시작)
-- 안내는 Rig Tools 아래 결과 글상자에 노란 글씨로 (10/30)
-- returns #(계속할지, job 에 붙일 글자)
fn trts_obMagicaExtra = ( ", \"magica\": 1" )   -- 10/30 (16:49): 매지카용이 기본. 앞·뒤 가운데 줄도 다른 줄처럼 혼자 움직임 (켜기/끄기 없앰)
fn trts_obRootExtra = (
	local useRoot = try (TosRigRoll.chkObRoot.checked) catch true
	if useRoot then #(true, trts_obMagicaExtra()) else (
		try (
			TosRigRoll.tLog.text = "root 본을 껐어요.\n체인을 붙일 부모 본을 뷰포트에서 클릭하세요. (Esc = 취소)"
			TosRigRoll.tLog.ForeColor = trts_logColor true
		) catch ()
		max create mode
		local o = try (pickObject message:"체인을 붙일 부모 본을 클릭하세요 (Esc = 취소)") catch undefined
		try (TosRigRoll.tLog.ForeColor = trts_logColor false) catch ()
		if not (isValidNode o) then #(false, "") else #(true, ", \"noroot\": 1, \"parent\": \"" + (substituteString o.name "\"" "") + "\"" + trts_obMagicaExtra())
	)
)

-- 파트마다 다른 본 색 (10/30): 목록 번호(만든 순서) 기준. 본 목록에 색 이름도 보임
trts_obPalette = #( \
	#("빨강", color 230 60 60), #("주황", color 245 150 40), #("노랑", color 235 215 40), #("연두", color 140 220 50), \
	#("초록", color 40 180 80), #("청록", color 40 200 190), #("하늘", color 70 160 240), #("파랑", color 60 90 230), \
	#("보라", color 150 80 220), #("분홍", color 235 100 190), #("갈색", color 160 110 60), #("회색", color 150 150 150))
fn trts_obColorIdx k = (
	local b = trts_pmBody()
	local mp = if b != undefined then (getAppData b 7761) else undefined
	local i = if mp == undefined then 0 else (findItem (filterString mp "|") k)
	if i == 0 do i = findItem ((trts_obGroups())[1]) k
	if i == 0 do i = 1
	trts_obPalette[(mod (i - 1) trts_obPalette.count) as integer + 1]
)
fn trts_obColorName k = (trts_obColorIdx k)[1]
fn trts_obColorize = (
	local g = trts_obGroups()
	for i = 1 to g[1].count do ( local c = (trts_obColorIdx g[1][i])[2]; for o in g[2][i] do o.wirecolor = c )
	try (TosRigRoll.lbObParts.items = trts_obItems()) catch ()
	redrawViews()
	"OK"
)

-- [가운데 줄 따라가기 켜기/끄기] (10/30): 앞·뒤 가운데 줄(FC·BC)이 같은 높이 양옆 본의 중간(50:50)을 따라가게 묶거나 풂.
-- 이미 만든 본에 언제든. 본 위치·방향은 그대로. i = 본 목록 번호 (0 이면 전부)
-- 고른 파트(들)의 가운데 줄 본 (_FC / _BC, _00·_end 제외)
fn trts_obCenterBones ids g = (
	local cen = #()
	for k in ids do for o in g[2][k] where (matchPattern o.name pattern:"*_FC*" or matchPattern o.name pattern:"*_BC*") and \
		not (matchPattern o.name pattern:"*_00") and not (matchPattern o.name pattern:"*_end") and classof o == BoneGeometry do append cen o
	cen
)
-- 본 목록 i 번 파트가 매지카용(가운데 줄 묶지 않음)인지: true / false / undefined(가운데 줄 없음)
fn trts_obMagicaState i = (
	local g = trts_obGroups()
	if i < 1 or i > g[1].count do return undefined
	local cen = trts_obCenterBones #(i) g
	if cen.count == 0 then undefined else ((for o in cen where isKindOf o.rotation.controller Orientation_Constraint collect o).count == 0)
)
-- [매지카용] 체크 (10/30): 켬 = 앞·뒤 가운데 줄(FC·BC)을 양옆에 묶지 않음(매지카 클로스로 흔들 때),
-- 끔 = 가운데 줄이 같은 높이 양옆 본의 중간(50:50)을 따라감(Max 에서 손으로 키 잡을 때). 본 위치·방향은 그대로.
-- i = 본 목록 번호 (0 이면 전부)
fn trts_obCenterSet i magica = (
	local g = trts_obGroups()
	if g[1].count == 0 do return "치마·망토·기타 본이 없어요."
	local ids = if i >= 1 and i <= g[1].count then #(i) else (for k = 1 to g[1].count collect k)
	local cen = trts_obCenterBones ids g
	if cen.count == 0 do return "고른 파트에는 가운데 줄(FC·BC)이 없어서 매지카용 설정이 필요 없어요."
	fn depth o = ( local d = 0; local p = o.parent; while p != undefined do ( d += 1; p = p.parent ); d )
	local order = for o in cen collect #(depth o, o)
	qsort order (fn cmp a b = a[1] - b[1])
	local n = 0
	undo "매지카용" on (
		if magica then (
			local tms = for e in order collect e[2].transform
			for k = 1 to order.count do (
				local o = order[k][2]
				if isKindOf o.rotation.controller Orientation_Constraint do (
					o.rotation.controller = Euler_XYZ()
					o.transform = tms[k]
					n += 1
				)
			)
		) else (
			for e in order where not (isKindOf e[2].rotation.controller Orientation_Constraint) do (
				local o = e[2]
				local nm = o.name
				local suf = substring nm (nm.count - 2) 3
				local us = filterString nm "_"
				local pre = us[1] + "_" + us[2] + "_"
				local L = undefined, R = undefined, dl = 1e9, dr = 1e9
				for c in objects where classof c == BoneGeometry and c != o and matchPattern c.name pattern:(pre + "*" + suf) and \
					not (matchPattern c.name pattern:"*_FC*") and not (matchPattern c.name pattern:"*_BC*") do (
					local d = distance c.transform.pos o.transform.pos
					if c.transform.pos.x > o.transform.pos.x then ( if d < dl do ( dl = d; L = c ) ) else ( if d < dr do ( dr = d; R = c ) )
				)
				if L != undefined and R != undefined do (
					local oc = Orientation_Constraint()
					o.rotation.controller = oc          -- 순서 중요: 본에 먼저 → 처음 방향 유지 → 대상
					oc.relative = true
					oc.appendTarget L 50
					oc.appendTarget R 50
					n += 1
				)
			)
		)
	)
	redrawViews()
	local what = if ids.count == 1 then ((trts_obKindLabel g[1][ids[1]]) + " ") else "모든 파트 "
	what + "매지카용: " + (if magica then "켬" else "끔") + " (바뀐 가운데 줄 본 " + (n as string) + "개)" + \
		(if magica then "\n가운데 줄(FC·BC)을 양옆에 묶지 않았어요. 매지카 클로스로 흔들 때." else "\n가운데 줄(FC·BC)이 양옆 줄 중간을 따라가요. Max 에서 손으로 키를 잡을 때.")
)
-- 예전 버튼 이름 호환
fn trts_obCenterToggle i = ( local st = trts_obMagicaState (amax i 1); trts_obCenterSet i (st != true) )

-- [② 치마·망토 본 만들기] 뒤에 Blender 가 파트마다 쓴 면(정점)을 기록해 둠 → [Max 수정] 이 고른 부분만 바꾸고 나머지는 남김 (10/30)
global trts_mkSetAll
fn trts_mkSetAll s = ( local b = trts_pmBody(); if b != undefined do setAppData b 7760 s; "OK" )


-- ======================================================================
--  6. 스킨 끄기 (본 위치 고칠 때, 10/30): 모든 스킨 메쉬의 Skin 을 잠시 끔 → 메쉬가 본을 안 따라옴. 웨이트는 그대로
-- ======================================================================
fn trts_skinIsOff = (
	local r = false
	for o in MaxBridge.skinnedMeshes() while not r do for m in o.modifiers where classOf m == Skin and not m.enabled do r = true
	r
)
fn trts_skinOff isOff = (
	local n = 0, names = #()
	for o in MaxBridge.skinnedMeshes() do (
		for m in o.modifiers where classOf m == Skin do ( m.enabled = not isOff; m.enabledInViews = not isOff; n += 1 )
		append names o.name
	)
	redrawViews()
	if n == 0 then "스킨이 있는 메쉬가 없어요." else (
		if isOff then ("스킨 꺼짐: " + (names.count as string) + "개 메쉬\n본을 옮겨도 메쉬가 따라오지 않아요. 웨이트는 그대로 있어요.\n본을 고친 뒤 [스킨 적용 (일괄)] 을 누르거나 체크를 풀면 다시 켜져요.")
		else ("스킨 다시 켬: " + (names.count as string) + "개 메쉬")
	)
)
