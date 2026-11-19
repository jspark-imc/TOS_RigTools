-- ======================================================================
--  TOS_RigTools - 3. Twist 보조 본 템플릿 (3ds Max 2016)
--  레퍼런스의 twist 레이어 구조를 성별로 템플릿에 담아 두고 새 캐릭터에 생성 (MTOS_RigTools 와 같은 템플릿)
--    남자: tos_twist_m.ms (costume_m_astronaut_set)  여자: tos_twist_f.ms (costume_f_astronaut_set)
--  TOS: 여자는 Dummy_Chast 도 (trts_chastMake, 값 = tos_bip_ref.ms 의 직업_성별 레퍼런스)
--  지원: Point / Box / BoneGeometry / Dummy (레퍼런스의 Editable Poly 상자는 Box 로)
--        Position_XYZ, Euler_XYZ, Position_Expression, Position/Orientation/LookAt 구속,
--        Spring(위치), Position/Rotation List, Rotation/Position/Transform Script (+변수)
--  데이터: <userScripts>\TOS_RigTools\tos_twist_<m|f>.ms
--  필요: TOS_RigTools.ms (같은 startup 폴더) - bipPrefix / mapName / resNode / 비율 계산 / 성별 재사용
-- ======================================================================
global TosRig, TosRigRoll, TOS_BipRef   -- TOS_RigTools.ms 에서 정의 (읽는 순서와 상관없게 미리 선언)
global TosRigStdTpl
global TosRigStdInfo
global TosRigStd
global TosRigKnee
global trts_txt, trts_esc, trts_f, trts_sig
global trts_targets, trts_vars, trts_ctrlSpec, trts_listSpec
global trts_depth, trts_bipAncestor, trts_isCandidate, trts_dims, trts_extract
global trts_res, trts_addVars, trts_newCtrl, trts_setup, trts_setupList, trts_assign, trts_make, trts_cmp, trts_stamp, trts_p2, trts_normRot, trts_rdeg, trts_fixRot

-- ---------------------------------------------------------------- 직렬화
fn trts_f v = (formattedPrint (v as float) format:".8g")
fn trts_esc s =
(
	local r = ""
	for i = 1 to s.count do
	(
		local c = s[i]
		if c == "\\" then r += "\\\\"
		else if c == "\"" then r += "\\\""
		else if c == "\n" then r += "\\n"
		else if c == "\r" then r += "\\r"
		else if c == "\t" then r += "\\t"
		else r += c
	)
	r
)
fn trts_txt v =
(
	local c = classOf v
	if v == undefined then "undefined"
	else if c == String then ("\"" + (trts_esc v) + "\"")
	else if c == BooleanClass then (if v then "true" else "false")
	else if c == Float then (trts_f v)
	else if c == Integer then (v as string)
	else if c == Name then ("#" + (v as string))
	else if c == BitArray then (v as string)
	else if c == Array then
	(
		local s = "#("
		for i = 1 to v.count do (if i > 1 do s += ","; s += (trts_txt v[i]))
		s + ")"
	)
	else if c == Color then ("(color " + (trts_f v.r) + " " + (trts_f v.g) + " " + (trts_f v.b) + ")")
	else if c == Point3 then ("[" + (trts_f v.x) + "," + (trts_f v.y) + "," + (trts_f v.z) + "]")
	else if c == Matrix3 then ("(matrix3 " + (trts_txt v.row1) + " " + (trts_txt v.row2) + " " + (trts_txt v.row3) + " " + (trts_txt v.row4) + ")")
	else if c == Quat then ("(quat " + (trts_f v.x) + " " + (trts_f v.y) + " " + (trts_f v.z) + " " + (trts_f v.w) + ")")
	else ("\"UNSUPPORTED_VALUE:" + (trts_esc (c as string)) + "\"")
)
-- 구조 비교용 서명 (위치·행렬 값은 캐릭터 비율에 따라 달라지므로 제외)
fn trts_sig v =
(
	local c = classOf v
	if v == undefined then "u"
	else if c == Array then (local s = "("; for x in v do s += (trts_sig x) + ","; s + ")")
	else if c == Float or c == Integer then (formattedPrint (v as float) format:".2f")
	else if c == Point3 or c == Matrix3 or c == Quat then "~"
	else if c == String then (substituteString v "\r" "")
	else (v as string)
)

-- ---------------------------------------------------------------- 컨트롤러 → 스펙
fn trts_targets c = (for i = 1 to c.getNumTargets() where isValidNode (c.getNode i) collect #((c.getNode i).name, c.getWeight i))

fn trts_vars c =
(
	local res = #()
	for i = 1 to c.NumVariables() do
	(
		local nm = c.GetName i
		if (findItem #("T", "S", "F", "NT") nm) == 0 do
		(
			local tp = (c.GetType nm) as string
			local v = c.GetValue nm
			if tp == "node" then append res #(nm, "node", (if isValidNode v then v.name else "-"))
			else if tp == "object" then append res #(nm, "object", (if isValidNode v then v.name else "-"))
			else if tp == "constant" then append res #(nm, "constant", v)
			else append res #(nm, "UNSUPPORTED_VAR:" + tp, "-")
		)
	)
	res
)

fn trts_listSpec c =
(
	local subs = for i = 1 to c.count collect #(c.getName i, c.weight[i], trts_ctrlSpec c[i].controller)
	#(((classOf c) as string), c.active, subs)
)

fn trts_ctrlSpec c =
(
	local k = toLower ((classOf c) as string)
	if k == "position_xyz" then #("Position_XYZ", c.value)
	else if k == "euler_xyz" then #("Euler_XYZ")
	else if k == "position_expression" then #("Position_Expression", (execute (c.getExpression())))
	else if k == "position_constraint" then #("Position_Constraint", c.relative, (trts_targets c))
	else if k == "orientation_constraint" then #("Orientation_Constraint", c.relative, c.local_world, (trts_targets c))
	else if k == "lookat_constraint" then
	(
		local up = try (c.pickUpNode) catch (undefined)
		#("LookAt_Constraint", c.relative, (trts_targets c), #(c.target_axis, (try (c.target_axisFlip) catch (false)), c.upnode_world, (if isValidNode up then up.name else "-"), c.upnode_ctrl, c.StoUP_axis, (try (c.StoUP_axisFlip) catch (false)), c.upnode_axis))
	)
	else if k == "springpositioncontroller" then
		#("Spring", c.getMass(), c.getDrag(), c.effectHow, c.steps, [c.x_effect, c.y_effect, c.z_effect], c.start, (for i = 1 to c.getSpringCount() collect #(c.getTension i, c.getDampening i)), c.position)
	else if k == "rotation_script" then #("Rotation_Script", c.script, (trts_vars c))
	else if k == "position_script" then #("Position_Script", c.script, (trts_vars c))
	else if k == "transform_script" then #("Transform_Script", c.script, (trts_vars c))
	else if k == "position_list" or k == "rotation_list" then (trts_listSpec c)
	else #("UNSUPPORTED:" + ((classOf c) as string))
)

-- ---------------------------------------------------------------- 노드 → 엔트리
--  1 이름  2 클래스  3 부모  4 Bip 부위(비율)  5 로컬 행렬(부모 기준)  6 크기  7 와이어색  8 레이어
--  9 본 속성 #(boneEnable, freezeLength, autoAlign, scaleType)  10 렌더  11 숨김  12 고정  13 상속 플래그
--  14 위치 컨트롤러  15 회전 컨트롤러  16 트랜스폼 컨트롤러(스크립트 팔로워)
fn trts_depth o = (local d = 0, p = o.parent; while p != undefined do (d += 1; p = p.parent); d)
fn trts_bipAncestor o = (local p = o.parent; while p != undefined and (classOf p) != Biped_Object do p = p.parent; p)
fn trts_isCandidate o =
(
	local c = classOf o
	if c == Biped_Object then false
	else if not (c == Point or c == Box or c == BoneGeometry or c == Dummy) then false
	else if c == Dummy and o.parent != undefined and (classOf o.parent) == Biped_Object and (matchPattern o.name pattern:"*Nub") then false
	else if (for m in o.modifiers where (classOf m) == Skin collect m).count > 0 then false
	else if TosRigKnee != undefined and (TosRigKnee.isKnee o.name) then false
	else (trts_bipAncestor o) != undefined
)
fn trts_dims o =
(
	local c = classOf o
	if c == Point then #(o.size, o.cross, o.box, o.axistripod, o.centermarker, (try (o.constantscreensize) catch (false)), (try (o.drawontop) catch (false)))
	else if c == Box then #(o.length, o.width, o.height)
	else if c == BoneGeometry then #(o.length, o.width, o.height, o.taper, o.sidefins, o.frontfin, o.backfin, o.sidefinssize, o.frontfinsize, o.backfinsize)
	else if c == Dummy then #(o.boxsize)
	else if superClassOf o == GeometryClass then
	(
		-- TOS: Edit Poly 로 뒤집힌 상자(예: Bip01 R Clavicle Twist, 로컬 Z 가 -높이~0) → 실제 메쉬의 로컬 크기로 Box.
		--   높이는 부호를 둠: 메쉬가 피봇 아래(-Z)로 있으면 음수 높이 Box (모양·법선이 레퍼런스와 같음)
		local m = snapshotAsMesh o
		local tmI = inverse o.transform
		local lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9]
		for i = 1 to m.numverts do (local v = (getVert m i) * tmI; lo.x = amin lo.x v.x; lo.y = amin lo.y v.y; lo.z = amin lo.z v.z; hi.x = amax hi.x v.x; hi.y = amax hi.y v.y; hi.z = amax hi.z v.z)
		free m
		local h = hi.z - lo.z
		#(hi.y - lo.y, hi.x - lo.x, (if (abs hi.z) < (abs lo.z) then -h else h))
	)
	else #()
)
fn trts_clsName o = (local c = classOf o; if c == Point or c == Box or c == BoneGeometry or c == Dummy then (c as string) else if superClassOf o == GeometryClass then "Box" else (c as string))
fn trts_extract o pre =
(
	local par = o.parent
	local tm = (at time 0 o.transform) * (inverse (at time 0 par.transform))
	local bp = trts_bipAncestor o
	local part = if bp.name == pre then pre else (substituteString bp.name (pre + " ") "")
	local ps = undefined, rs = undefined, ts = undefined
	if (classOf o.controller) == prs then (ps = trts_ctrlSpec o.pos.controller; rs = trts_ctrlSpec o.rotation.controller)
	else ts = trts_ctrlSpec o.controller
	#(o.name, (trts_clsName o), par.name, part, tm, (trts_dims o), o.wirecolor, o.layer.name,
	  #(o.boneEnable, o.boneFreezeLength, o.boneAutoAlign, o.boneScaleType), o.renderable, o.isHidden, o.isFrozen, (getInheritanceFlags o),
	  ps, rs, ts)
)

-- ---------------------------------------------------------------- 스펙 → 컨트롤러
fn trts_res n pre names = (if n == undefined or n == "-" then undefined else TosRig.resNode (TosRig.mapName n pre names))

fn trts_addVars sc vars pre names =
(
	for v in vars do
	(
		local nm = v[1], exists = false
		for i = 1 to sc.NumVariables() where (sc.GetName i) == nm do exists = true
		if not exists do
		(
			if v[2] == "node" then (local nd = trts_res v[3] pre names; if nd != undefined do sc.AddNode nm nd)
			else if v[2] == "object" then (local nd = trts_res v[3] pre names; if nd != undefined do sc.AddObject nm nd)
			else if v[2] == "constant" then sc.AddConstant nm v[3]
		)
	)
)

fn trts_newCtrl spec =
(
	local k = toLower spec[1]
	if k == "position_xyz" then Position_XYZ()
	else if k == "euler_xyz" then Euler_XYZ()
	else if k == "position_expression" then Position_Expression()
	else if k == "position_constraint" then Position_Constraint()
	else if k == "orientation_constraint" then Orientation_Constraint()
	else if k == "lookat_constraint" then LookAt_Constraint()
	else if k == "spring" then SpringPositionController()
	else if k == "rotation_script" then Rotation_Script()
	else if k == "position_script" then Position_Script()
	else if k == "transform_script" then Transform_Script()
	else if k == "position_list" then Position_List()
	else if k == "rotation_list" then Rotation_List()
	else undefined
)

fn trts_setupList lst spec r pre names =
(
	local subs = spec[3]
	local n0 = lst.count
	for s in subs do
	(
		lst.Available.controller = (trts_newCtrl s[3])
		local k = lst.count
		trts_setup lst[k].controller s[3] r pre names
		lst.setName k s[1]
	)
	for i = n0 to 1 by -1 do lst.delete i
	for i = 1 to subs.count do lst.weight[i] = subs[i][2]
	lst.active = spec[2]
)

-- c: 이미 노드(또는 리스트)에 연결된 컨트롤러
fn trts_setup c spec r pre names =
(
	local k = toLower spec[1]
	if k == "position_xyz" then
	(
		if spec.count > 1 and spec[2] != undefined do (local p = spec[2] * r; c[1].value = p.x; c[2].value = p.y; c[3].value = p.z)
	)
	else if k == "position_expression" then
	(
		local v = spec[2] * r
		c.setExpression ("[" + (trts_f v.x) + ", " + (trts_f v.y) + ", " + (trts_f v.z) + "]")
	)
	else if k == "position_constraint" then
	(
		for t in spec[3] do (local nd = trts_res t[1] pre names; if nd != undefined do c.appendTarget nd t[2])
		c.relative = spec[2]
	)
	else if k == "orientation_constraint" then
	(
		for t in spec[4] do (local nd = trts_res t[1] pre names; if nd != undefined do c.appendTarget nd t[2])
		c.local_world = spec[3]
		c.relative = spec[2]
	)
	else if k == "lookat_constraint" then
	(
		local la = spec[4]
		for t in spec[3] do (local nd = trts_res t[1] pre names; if nd != undefined do c.appendTarget nd t[2])
		c.target_axis = la[1]
		try (c.target_axisFlip = la[2]) catch ()
		c.upnode_world = la[3]
		if (not la[3]) and la[4] != "-" do (local un = trts_res la[4] pre names; if un != undefined do c.pickUpNode = un)
		c.upnode_ctrl = la[5]
		c.StoUP_axis = la[6]
		try (c.StoUP_axisFlip = la[7]) catch ()
		c.upnode_axis = la[8]
		c.relative = spec[2]
	)
	else if k == "spring" then
	(
		c.setMass spec[2]
		c.setDrag spec[3]
		c.effectHow = spec[4]
		c.steps = spec[5]
		c.x_effect = spec[6].x; c.y_effect = spec[6].y; c.z_effect = spec[6].z
		c.start = spec[7]
		c.position = spec[9] * r
		for i = 1 to spec[8].count do try (c.setTension i spec[8][i][1]; c.setDampening i spec[8][i][2]) catch ()
	)
	else if k == "rotation_script" or k == "position_script" or k == "transform_script" then
	(
		trts_addVars c spec[3] pre names
		c.script = spec[2]
	)
	else if k == "position_list" or k == "rotation_list" then trts_setupList c spec r pre names
	ok
)

-- slot: #pos / #rot / #tm.  결과: ok 또는 경고 문자열
-- 관절 맞춤 목록: #(본, 맞출 관절, 끝이 향할 관절, 끝 길이 비율)
-- 조준 맞춤 목록: #(본, LookAt 대상). 대상을 옮겨 본 방향 = 템플릿 방향(부모 관절 기준)으로 맞춤
-- (몸통 비율은 세로 길이 기준이라 좌우 오프셋까지 줄이면 본이 가슴 쪽으로 틀어짐)
global trts_aims = #(#("bone_spine_l", "Point007"), #("bone_spine_r", "Point008"))
fn trts_aimFix onlyMade:undefined =
(
	local out = #()
	for a in trts_aims do
	(
		local o = getNodeByName a[1] exact:true, t = getNodeByName a[2] exact:true
		if o == undefined or t == undefined or o.parent == undefined do continue
		if onlyMade != undefined and (findItem onlyMade o) == 0 do continue
		local e = undefined
		for x in TosRigStdTpl where (toLower x[1]) == (toLower a[1]) do e = x
		if e == undefined do continue
		local piv = (at time 0 o.transform).row4
		local dir = normalize (e[5] * (at time 0 o.parent.transform)).row1
		local d = distance piv (at time 0 t.transform).row4
		with animate off (at time 0 (in coordsys world t.pos = piv + dir * d))
		append out (a[1] + ": 대상 " + a[2] + " 방향 맞춤")
	)
	out
)
-- 가슴 본 맞춤: 메쉬 가슴 앞쪽(좌우 평균)에 point_bast_*02 끝이 오도록 point_bast_*01 위치를 옮김 (방향·길이는 템플릿 그대로)
-- 표준값 (2026-10-25, 정현 Melitta f_new 조정): 왼쪽은 자동 맞춤 위치에서 [바깥, 앞, 위] 로 어깨 반폭 x 이 비율만큼 더 옮기고,
--   오른쪽은 왼쪽을 Spine2 기준 좌우 대칭으로 둠
global trts_breastOfs = [0.0511941, 0.0, 0.0]
fn trts_breastFix onlyMade:undefined =
(
	local out = #()
	local pre = TosRig.bipPrefix()
	if pre == undefined do return out
	local sp = getNodeByName (pre + " Spine2") exact:true, ua = getNodeByName (pre + " L UpperArm") exact:true, nk = getNodeByName (pre + " Neck") exact:true
	local P1 = #(getNodeByName "point_bast_L01" exact:true, getNodeByName "point_bast_R01" exact:true)
	local P2 = #(getNodeByName "point_bast_L02" exact:true, getNodeByName "point_bast_R02" exact:true)
	local BB = #(getNodeByName "bone_bast_l" exact:true, getNodeByName "bone_bast_r" exact:true)
	if sp == undefined or ua == undefined or nk == undefined do return out
	for i = 1 to 2 do if P1[i] == undefined or P2[i] == undefined do return out
	if onlyMade != undefined and (findItem onlyMade P1[1]) == 0 do return out
	local spT = at time 0 sp.transform
	local c = spT.row4, upv = normalize spT.row1, frv = normalize spT.row2, lat = normalize spT.row3
	local half = abs (dot ((at time 0 ua.transform).row4 - c) lat)
	local h1 = dot ((at time 0 nk.transform).row4 - c) upv
	local best = #(-1e9, -1e9), acc = #([0,0,0], [0,0,0]), cnt = #(0, 0)
	local pts = #(#(), #())
	local meshes = for o in geometry where (canConvertTo o TriMeshGeometry) and classOf o != BoneGeometry and classOf o != Biped_Object and (getUserProp o "RigTools_tpl") == undefined and not (matchPattern o.name pattern:(pre + "*")) collect o
	local sk = for o in meshes where o.modifiers[#Skin] != undefined collect o
	if sk.count > 0 do meshes = sk   -- 스킨이 있으면 스킨 메쉬만, 없으면(생성 단계) 모델 메쉬 전체
	for o in meshes do
	(
		local sks = for md in o.modifiers where classOf md == Skin collect md
		local was = for md in sks collect md.enabled
		for md in sks do md.enabled = false
		local m = at time 0 (snapshotAsMesh o)
		for k = 1 to sks.count do sks[k].enabled = was[k]
		for v = 1 to m.numverts do
		(
			local q = (getVert m v) - c
			local h = dot q upv, l = dot q lat, f = dot q frv
			if h > -0.5 * h1 and h < 0.6 * h1 and (abs l) > 0.25 * half and (abs l) < 0.6 * half do
			(
				local sd = if l > 0 then 1 else 2
				append pts[sd] [l, f, h]
				if f > best[sd] do best[sd] = f
			)
		)
		delete m
	)
	if pts[1].count == 0 or pts[2].count == 0 do (append out "가슴 본: 메쉬에서 가슴 위치를 못 찾아 건너뜀"; return out)
	for sd = 1 to 2 do for q in pts[sd] where q.y > best[sd] - 0.08 * half do (acc[sd] += q; cnt[sd] += 1)
	local aL = acc[1] / cnt[1], aR = acc[2] / cnt[2]
	local la = ((abs aL.x) + (abs aR.x)) / 2.0, fa = (aL.y + aR.y) / 2.0, ha = (aL.z + aR.z) / 2.0
	local inset = 0.08 * half
	for i = 1 to 2 do
	(
		local sg = if i == 1 then 1.0 else -1.0
		local T = c + lat * (sg * la) + frv * (fa - inset) + upv * ha
		local D = normalize (at time 0 P1[i].transform).row1
		local Lb = length P2[i].pos.controller.position
		local R = T - D * Lb
		if i == 1 then R += lat * (trts_breastOfs.x * half) + frv * (trts_breastOfs.y * half) + upv * (trts_breastOfs.z * half)
		else (local pL = (at time 0 P1[1].transform).row4 - c; R = c - lat * (dot pL lat) + frv * (dot pL frv) + upv * (dot pL upv))
		with animate off (P1[i].pos.controller.position = R * (inverse spT))
		if i == 2 do
		(
			-- 오른쪽은 위치뿐 아니라 축(회전)까지 왼쪽 point_bast_L01·L02 의 Spine2 좌우면 거울상으로 (템플릿 축 차이 무시)
			for k = 1 to 2 do
			(
				local src = if k == 1 then P1[1] else P2[1], dst = if k == 1 then P1[2] else P2[2]
				local m = at time 0 src.transform
				local r1 = m.row1 - 2.0 * (dot m.row1 lat) * lat, r2 = m.row2 - 2.0 * (dot m.row2 lat) * lat, r3 = m.row3 - 2.0 * (dot m.row3 lat) * lat
				local p = m.row4 - c
				with animate off (at time 0 (dst.transform = matrix3 r1 r2 r3 (c + p - 2.0 * (dot p lat) * lat)))
			)
		)
		if BB[i] != undefined do try (BB[i].ResetBoneStretch()) catch ()
		append out (P1[i].name + (if i == 1 then ": 가슴 앞쪽에 맞춤 (+표준 오프셋)" else ": 왼쪽 대칭으로 맞춤 (위치·축)"))
	)
	out
)
-- 허리 본 맞춤 (2026-10-25 정현 Melitta f_new 기준): 바이패드는 그대로 두고 bone_waist 를 Pelvis~Spine 사이에 맞춤
--   회전 = Orientation 구속 Spine 50 : Pelvis 50 (리스트 없음), 시작 = Pelvis 기준 Spine 높이의 trts_waistStart 지점,
--   길이 = 구속이 정한 축 방향으로 끝이 Spine 높이에 닿을 때까지, bone_waist_nub 는 끝으로
global trts_waistStart = 0.51558
fn trts_waistFix onlyMade:undefined =
(
	local out = #()
	local pre = TosRig.bipPrefix()
	if pre == undefined do return out
	local pel = getNodeByName (pre + " Pelvis") exact:true, sp = getNodeByName (pre + " Spine") exact:true
	local bw = getNodeByName "bone_waist" exact:true, bn = getNodeByName "bone_waist_nub" exact:true
	if pel == undefined or sp == undefined or bw == undefined do return out
	if onlyMade != undefined and (findItem onlyMade bw) == 0 do return out
	local oc = Orientation_Constraint()
	oc.appendTarget sp 50.0
	oc.appendTarget pel 50.0
	oc.relative = false
	bw.rotation.controller = oc
	local pT = at time 0 pel.transform
	local sL = (at time 0 sp.transform).row4 * inverse pT
	local p = bw.pos.controller.value
	with animate off (bw.pos.controller.value = [sL.x * trts_waistStart, p.y, p.z])
	local bT = at time 0 bw.transform
	local st = bT.row4 * inverse pT, ax = normalize (bT.row1 * inverse pT.rotationpart)
	if (abs ax.x) < 0.1 do (append out "bone_waist: 축이 Spine 쪽을 향하지 않아 길이 맞춤 건너뜀"; return out)
	local L = (sL.x - st.x) / ax.x
	try (bw.length = L) catch ()
	if bn != undefined do with animate off (bn.pos.controller.value = [L, 0, 0])
	try (bw.ResetBoneStretch()) catch ()
	append out ("bone_waist: Pelvis~Spine 사이에 맞춤 (시작 " + (formattedPrint st.x format:".2f") + ", 길이 " + (formattedPrint L format:".2f") + ", 구속 Spine 50 : Pelvis 50)")
	out
)
-- 파이프라인에서 Skin에 들어가는 보조본 (이름은 모두 소문자, 비교도 소문자로)
global trts_skinPlan = #("bone_neck", "bone_waist", "bone_hip_l", "bone_hip_r", "bone_l clavicle", "bone_r clavicle", \
	"bone_leg_lup", "bone_leg_ldn", "bone_leg_rup", "bone_leg_rdn", "bone_knee_l", "bone_knee_r", "bone_elbow_l", "bone_elbow_r", \
	"bone l thigh twist", "bone r thigh twist", "bone l calf twist", "bone r calf twist", "bone l upperarm twist", "bone l upperarm twist1", \
	"bone r upperarm twist", "bone r upperarm twist1", "bone l forearm twist", "bone l forearm twist1", "bone r forearm twist", "bone r forearm twist1")
-- 레이어 정리 (TOS 레퍼런스 양식: Asset\PC\costume\Body)
--   Warrior_m_Bip (남) / Warrior_Bip (여) = Biped
--   twist  = Biped 트위스트 뼈 + [3. 생성] 으로 만든 Twist 보조 본 (Point·Clavicle Twist 상자)
--   nubs   = Bip01 Footsteps, Biped 끝(Nub) Dummy
--   Warrior_Cloak_Bone / Warrior_Skirt_Bone / Warrior_Skirt_S_Bone / Warrior_Skirt_W_Bone = [4. 세컨더리 본] 으로 만든 본
-- 메쉬·다른 레이어에 있는 노드는 건드리지 않음. 레이어만 옮기고 위치·회전·연결·컨트롤러는 그대로 (끝나고 전후 transform 비교)
global trts_layerNames = #("Warrior_m_Bip", "Warrior_Bip", "twist", "nubs")
fn trts_layerGet nm =
(
	local l = LayerManager.getLayerFromName nm
	if l == undefined then l = LayerManager.newLayerFromName nm
	l
)
-- TOS: 여자 가슴 더미 Dummy_Chast. 기준 = 직업_성별 레퍼런스 데이터(tos_bip_ref.ms 의 chast: #(이름, 부모 Biped 뼈, 상자 크기, 부모 기준 행렬(스케일 포함), 레이어, 색))
--   레퍼런스 파일에 없는 직업(warrior_f = 좌우 Dummy_L/R_Chest, mage_f = Dummy_Chest)은 archer_f·cleric_f 의 값 (레이어 twist)
fn trts_chastMake pre =
(
	if not (TosRig.bipRefLoad()) do return "Dummy_Chast: Biped 레퍼런스 데이터가 없어 건너뜀"
	local rf = TOS_BipRef.get #f job:(TosRig.job())
	local c = if rf != undefined then rf.chast else undefined
	if c == undefined do return "Dummy_Chast: 레퍼런스 값이 없어 건너뜀"
	if (getNodeByName c[1] exact:true) != undefined do return ("Dummy_Chast: 이미 있어서 건너뜀 (" + c[1] + ")")
	local par = getNodeByName (pre + " " + c[2]) exact:true
	if par == undefined do return ("Dummy_Chast: 부모 " + pre + " " + c[2] + " 가 없어 건너뜀")
	local d = undefined
	undo "TOS Dummy_Chast" on
	(
		with animate off at time 0
		(
			d = Dummy name:c[1] boxsize:[c[3], c[3], c[3]]
			try (d.wirecolor = c[6]) catch ()
			(TosRig.getLayer c[5]).addNode d
			d.parent = par
			d.transform = c[4] * par.transform
			d.renderable = false
		)
	)
	"Dummy_Chast 만듦: 부모 " + par.name + ", 상자 " + (formattedPrint c[3] format:".2f") + ", 레이어 " + c[5] + " (기준 " + rf.file + ")"
)
fn trts_isTwistHelper o =(local p = getUserProp o "RigTools_tpl"; p != undefined and (matchPattern (p as string) pattern:"tos_twist*"))
fn trts_layerTidy =
(
	local pre = TosRig.bipPrefix()
	(LayerManager.getLayer 0).current = true
	local g = try (TosRig.gender ask:false) catch undefined
	-- TOS: Biped 레이어 = 직업_성별 레퍼런스의 레이어 (Archer_f_Bip · Wiz_f_Bip · Warrior_Bip · Bip ...). 레퍼런스를 모르면 MTOS 와 같은 이름
	local bipLay = undefined
	if g != undefined do try (if (TosRig.bipRefLoad()) do (local rf = TOS_BipRef.get g job:(TosRig.job()); if rf != undefined and rf.layer != undefined and rf.layer != "" and rf.layer != "0" do bipLay = rf.layer)) catch ()
	if bipLay == undefined do bipLay = if g == #m then "Warrior_m_Bip" else if g == #f then "Warrior_Bip" else undefined
	if bipLay == undefined do
	(
		-- 성별을 모르면 지금 Biped 가 있는 레이어 그대로 (없으면 Warrior_Bip)
		local b = if pre != undefined then getNodeByName pre exact:true else undefined
		bipLay = if b != undefined and b.layer.name != "0" then b.layer.name else "Warrior_Bip"
	)
	local nodesAll = for o in objects collect o
	local tms = for o in nodesAll collect o.transform
	local cnt = #(0, 0, 0, 0), keep = 0
	for o in nodesAll do
	(
		local c = classOf o
		local isBip = pre != undefined and matchPattern o.name pattern:(pre + "*")
		local secLay = getUserProp o "TOS_layer"
		local dst = undefined, k = 0
		if c == Biped_Object and matchPattern o.name pattern:"*Footsteps" then (dst = "nubs"; k = 4)
		else if c == Biped_Object and matchPattern o.name pattern:"*Twist*" then (dst = "twist"; k = 3)
		else if c == Biped_Object then (dst = bipLay; k = 1)
		else if isBip and c == Dummy and matchPattern o.name pattern:"*Nub" then (dst = "nubs"; k = 4)
		else if trts_isTwistHelper o then (dst = "twist"; k = 3)
		else if secLay != undefined and (getUserProp o "TOS_sec") != undefined then (dst = secLay as string; k = 2)
		if dst == undefined then keep += 1
		else ((trts_layerGet dst).addNode o; cnt[k] += 1)
	)
	local moved = 0
	for i = 1 to nodesAll.count do if not (isValidNode nodesAll[i]) or (distance nodesAll[i].transform.row4 tms[i].row4) > 1e-4 or (length (nodesAll[i].transform.row1 - tms[i].row1)) > 1e-5 or (length (nodesAll[i].transform.row3 - tms[i].row3)) > 1e-5 do moved += 1
	"레이어 정리: " + bipLay + "=" + (cnt[1] as string) + " twist=" + (cnt[3] as string) + " nubs=" + (cnt[4] as string) + " 세컨더리=" + (cnt[2] as string) + \
		" | 그대로(메쉬·다른 레이어) " + (keep as string) + " | transform 변화 " + (moved as string)
)

-- 테스트 키 (몸 ROM 0~240 + 얼굴 표정 300~480): rom_check.ms 사용. 0프레임(바인드)이 그대로인지 전후 비교해서 보고
fn trts_romFile =
(
	local a = TosRig.sbgDir() + "rom_check.ms"
	if doesFileExist a then a else (if doesFileExist @"C:\claude\max_blender\tools\checkanim\rom_check.ms" then @"C:\claude\max_blender\tools\checkanim\rom_check.ms" else undefined)
)
fn trts_frame0State =
(
	local nodes = for o in objects collect o
	local tms = for o in nodes collect (at time 0 o.transform)
	local verts = #()
	for o in nodes where o.modifiers[#Skin] != undefined do
	(
		local m = at time 0 (snapshotAsMesh o)
		append verts #(o, for i = 1 to m.numverts collect (getVert m i))
		delete m
	)
	#(nodes, tms, verts)
)
fn trts_frame0Diff st =
(
	local nmove = 0, vmax = 0.0
	for i = 1 to st[1].count where isValidNode st[1][i] do
	(
		local a = st[2][i], b = at time 0 st[1][i].transform
		if (distance a.row4 b.row4) > 1e-3 or (length (a.row1 - b.row1)) > 1e-4 or (length (a.row2 - b.row2)) > 1e-4 do nmove += 1
	)
	for e in st[3] where isValidNode e[1] do
	(
		local m = at time 0 (snapshotAsMesh e[1])
		for i = 1 to (amin m.numverts e[2].count) do (local d = distance (getVert m i) e[2][i]; if d > vmax do vmax = d)
		delete m
	)
	#(nmove, vmax)
)
fn trts_romKeys mode =
(
	local f = trts_romFile()
	if f == undefined do return "오류: rom_check.ms 를 찾을 수 없어요 (scripts\\TOS_RigTools 폴더)"
	fileIn f
	local st = trts_frame0State()
	local t0 = timeStamp()
	local r = if mode == #make then (execute "TosRomCheck.build()") \
		else (execute "(TosRomCheck.storeBind(); undo \"테스트 키 지우기\" on (TosRomCheck.clearKeys()); sliderTime = 0; \"테스트 키를 지웠어요 (Biped·얼굴 본 키 전부)\")")
	local d = trts_frame0Diff st
	local chk = if d[1] == 0 and d[2] < 0.01 then "0프레임(바인드) 그대로: 노드 변화 0, 메쉬 최대 차이 " + (formattedPrint d[2] format:".4f") \
		else "주의: 0프레임이 달라졌어요 (노드 " + d[1] as string + "개, 메쉬 최대 " + (formattedPrint d[2] format:".3f") + ") - Ctrl+Z로 되돌려 주세요"
	(r as string) + "\n" + chk + " | " + ((timeStamp() - t0) / 1000) as string + "초"
)
-- TOS 테스트 키: 성별 테스트 bip (남 pc_m_set_test.bip / 여 pc_f_set_test.bip, scripts\TOS_RigTools\) 를 Biped 에 불러옴
--   원본: E:\TOS_SVN\Asset\PC\costume\ (설치 묶음에 들어 있음). 0프레임 = 바인드 자세인지 전후 비교해서 보고
global trts_testKeys, trts_sbgAnimFromFigure
fn trts_testBipFile g = (TosRig.sbgDir() + "pc_" + (if g == #m then "m" else "f") + "_set_test.bip")
fn trts_testKeys mode =
(
	local pre = TosRig.bipPrefix()
	if pre == undefined do return "오류: 장면에 Biped가 없어요."
	local bip = getNodeByName pre exact:true
	local c = bip.controller
	if mode == #make then
	(
		local g = TosRig.gender()
		if g == undefined do return "취소했어요. (성별을 정하지 않음)"
		local f = trts_testBipFile g
		if not (doesFileExist f) do return ("오류: 테스트 bip 파일이 없어요: " + f)
		if c.figureMode do c.figureMode = false
		local st = trts_frame0State()
		if (getAppData rootNode 7742) == undefined do setAppData rootNode 7742 (((animationRange.start.frame as integer) as string) + "," + ((animationRange.end.frame as integer) as string))
		local t0 = timeStamp()
		local ok = biped.loadBipFile c f
		if not ok do return ("오류: 테스트 bip 를 불러오지 못했어요: " + f)
		sliderTime = 0
		local d = trts_frame0Diff st
		"테스트 키 생성: " + (filenameFromPath f) + " (" + (TosRig.genderText g) + ")  프레임 " + ((animationRange.start.frame as integer) as string) + "~" + ((animationRange.end.frame as integer) as string) + "\n" + \
			(if d[2] < 0.01 then "0프레임(바인드) 그대로: 메쉬 최대 차이 " + (formattedPrint d[2] format:".4f") + (if d[1] > 0 then " (뼈 " + (d[1] as string) + "개 0.01 미만 미세 차이)" else "") \
			else "주의: 0프레임이 바인드 자세와 달라요 (노드 " + (d[1] as string) + "개, 메쉬 최대 " + (formattedPrint d[2] format:".3f") + ")") + \
			"\n지우려면 [테스트 키 지우기]. (" + (((timeStamp() - t0) / 1000.0) as string) + "초)"
	)
	else
	(
		if c.figureMode do c.figureMode = false
		biped.clearAllAnimation c
		-- 프레임 범위 되돌리기
		local rs = getAppData rootNode 7742
		if rs != undefined do
		(
			local p = filterString rs ","
			try (animationRange = interval (p[1] as integer) (p[2] as integer)) catch ()
			deleteAppData rootNode 7742
		)
		-- 키를 지우면 0프레임 자세가 Biped 기본 자세로 바뀜 → Figure(바인드) 자세로 다시 맞춤
		if trts_sbgAnimFromFigure == undefined do try (fileIn (TosRig.sbgDir() + "sbg_build.ms")) catch ()
		local m = try (trts_sbgAnimFromFigure bip) catch ("자세 맞춤 실패: " + getCurrentException())
		sliderTime = 0
		"테스트 키를 지웠어요 (Biped 키 전부). " + m
	)
)
-- 좌우대칭: 왼쪽(L) 보조본·헬퍼 위치를 오른쪽(R)에 거울 복사 (위치만, 회전·컨트롤러·연결은 그대로)
fn trts_mirName n =
(
	local rx = dotNetClass "System.Text.RegularExpressions.Regex"
	local r = rx.Replace n "(?<![A-Za-z])L(?![a-z])" "R"
	rx.Replace r "(?<=[a-z])L(?=_)" "R"
)
fn trts_relNames o =
(
	local r = for c in o.children collect c.name
	for d in refs.dependents o where isValidNode d and d != o do appendIfUnique r d.name
	if o.parent != undefined do append r ("^" + o.parent.name)
	r
)
fn trts_mirrorPairs =
(
	local pre = TosRig.bipPrefix()
	local pairs = #(), used = #()
	local cand = for o in objects where (classOf o == BoneGeometry or classOf o == Point or classOf o == Dummy or classOf o == ExposeTm) and not (pre != undefined and matchPattern o.name pattern:(pre + "*")) collect o
	-- 1) 이름으로 (_L / L / elbowL_ → R)
	for o in cand do
	(
		local m = trts_mirName o.name
		if m != o.name and (findItem used o.name) == 0 do
		(
			local r = getNodeByName m exact:true
			if r != undefined and (findItem cand r) > 0 and (findItem used m) == 0 do (append pairs #(o, r); append used o.name; append used m)
		)
	)
	-- 2) 이름에 L/R 이 없는 노드: 대칭 부모 아래에서 관계(자식·구속 대상)가 대칭인 노드 먼저, 남은 건 위치로
	for pass = 1 to 2 do
		for a in cand where (findItem used a.name) == 0 and a.parent != undefined and (trts_mirName a.parent.name) != a.parent.name do
		(
			local mp = trts_mirName a.parent.name
			local ra = for x in (trts_relNames a) where x[1] != "^" collect (trts_mirName x)
			local best = undefined, bs = 0, bd = 1e9
			for b in cand where b != a and (findItem used b.name) == 0 and b.parent != undefined and b.parent.name == mp and classOf b == classOf a do
			(
				local rb = trts_relNames b
				local sc = (for x in ra where (findItem rb x) > 0 collect x).count
				local pa = (at time 0 a.transform).pos, pb = (at time 0 b.transform).pos
				local d = distance [-pa.x, pa.y, pa.z] pb
				if sc > bs or (sc == bs and d < bd) do (best = b; bs = sc; bd = d)
			)
			if best != undefined and ((pass == 1 and bs > 0) or (pass == 2 and bd < 1.0)) do (append pairs #(a, best); append used a.name; append used best.name)
		)
	pairs
)
fn trts_mirrorLR =
(
	local pre = TosRig.bipPrefix()
	local cx = if pre != undefined and (getNodeByName (pre + " Pelvis") exact:true) != undefined then (at time 0 (getNodeByName (pre + " Pelvis") exact:true).transform).pos.x else 0.0
	local st = trts_frame0State()
	local moved = #(), skipped = #()
	undo "좌우대칭 (L -> R)" on with animate off at time 0
	(
		for p in trts_mirrorPairs() do
		(
			local a = p[1], b = p[2]
			-- 이름상 L 이 원본 (위치로도 확인: 원본이 오른쪽에 있으면 서로 바꿈)
			local aL = (trts_mirName a.name) != a.name, bL = (trts_mirName b.name) != b.name
			if (bL and not aL) or ((aL == bL) and (a.transform.pos.x - cx) < (b.transform.pos.x - cx)) do (local t = a; a = b; b = t)
			local pa = a.transform.pos, pb = b.transform.pos
			local want = [2 * cx - pa.x, pa.y, pa.z]
			if (distance want pb) > 1e-3 do
			(
				local c = b.pos.controller
				if classOf c == Position_XYZ or classOf c == SpringPositionController or classOf c == Bezier_Position then
				(
					in coordsys world b.pos = want
					append moved (b.name + " (" + (formattedPrint (distance want pb) format:".2f") + ")")
				)
				else append skipped (b.name + ": " + (classOf c) as string)
			)
		)
	)
	local d = trts_frame0Diff st
	local res = "좌우대칭 (L → R): 옮긴 오른쪽 노드 " + moved.count as string
	if moved.count > 0 do res += "\n  " + (moved as string)
	if skipped.count > 0 do res += "\n  구속·스크립트라 건너뜀: " + (skipped as string)
	res += "\n메쉬 0프레임 최대 차이 " + (formattedPrint d[2] format:".4f") + (if d[2] > 0.05 then "  ← 스킨 적용 뒤라 모양이 달라졌어요. 블렌더에서 스킨을 다시 적용하거나 Ctrl+Z" else "")
	res
)
global trts_snaps = #(#("bone_neck", "Neck", "Head", 0.85))
fn trts_snapJoint o j j2 k =
(
	-- 관절 위치·방향(= Ivelar 에서와 같이 관절 방향과 일치)으로 맞추고, LookAt 은 그 자세를 초기 오프셋으로 다시 잡음
	local want = copy (at time 0 j.transform)
	local rc = o.rotation.controller
	local msg = "관절 위치·방향으로 이동"
	if classOf rc == LookAt_Constraint then
	(
		local tg = for i = 1 to rc.getNumTargets() collect #(rc.getNode i, rc.getWeight i)
		local up = rc.pickUpNode, uw = rc.upnode_world, ua = rc.upnode_axis, uc = rc.upnode_ctrl
		local sa = rc.StoUP_axis, sf = rc.StoUP_axisFlip, ta = rc.target_axis, tf = rc.target_axisFlip, vl = rc.lookat_vector_length
		o.rotation.controller = Euler_XYZ()
		o.transform = want
		local c = LookAt_Constraint()
		o.rotation.controller = c
		c = o.rotation.controller
		c.target_axis = ta; c.target_axisFlip = tf; c.upnode_world = uw; c.upnode_ctrl = uc
		c.StoUP_axis = sa; c.StoUP_axisFlip = sf; c.lookat_vector_length = vl
		if up != undefined do c.pickUpNode = up
		try (c.upnode_axis = ua) catch ()
		c.relative = true
		for x in tg do c.appendTarget x[1] x[2]
		msg += ", LookAt 초기 오프셋 다시 잡음"
	)
	else o.transform = want
	if j2 != undefined do
	(
		local L = (distance want.row4 (at time 0 j2.transform).row4) * k
		for c in o.children where classOf c == BoneGeometry do (try (c.pos.controller.value = [L, 0, 0]) catch ())
		try (o.ResetBoneStretch()) catch ()
		msg += ", 끝 길이 " + (formattedPrint L format:".2f")
	)
	msg
)

fn trts_assign o spec slot r pre names =
(
	if spec == undefined then ok
	else
	(
		local k = toLower spec[1]
		if (slot == #pos and k == "position_xyz") or (slot == #rot and k == "euler_xyz") then ok
		else
		(
			local c = trts_newCtrl spec
			if c == undefined then ("지원 안 됨: " + spec[1])
			else
			(
				if slot == #pos then (o.pos.controller = c; c = o.pos.controller)
				else if slot == #rot then (o.rotation.controller = c; c = o.rotation.controller)
				else (o.controller = c; c = o.controller)
				trts_setup c spec r pre names
			)
		)
	)
)

fn trts_make e r =
(
	local d = e[6], o = undefined
	if e[2] == "Point" then
	(
		o = Point()
		o.size = d[1] * r; o.cross = d[2]; o.box = d[3]; o.axistripod = d[4]; o.centermarker = d[5]
		try (o.constantscreensize = d[6]; o.drawontop = d[7]) catch ()
	)
	else if e[2] == "Box" then o = Box length:(d[1] * r) width:(d[2] * r) height:(d[3] * r)
	else if e[2] == "BoneGeometry" then
	(
		o = BoneSys.createBone [0,0,0] [d[1] * r, 0, 0] [0,0,1]
		o.boneEnable = false
		o.width = d[2] * r; o.height = d[3] * r; o.taper = d[4]
		o.sidefins = d[5]; o.frontfin = d[6]; o.backfin = d[7]
		try (o.sidefinssize = d[8] * r; o.frontfinsize = d[9] * r; o.backfinsize = d[10] * r) catch ()
	)
	else if e[2] == "Dummy" then (o = Dummy(); o.boxsize = d[1] * r)
	else o = Dummy()
	o
)

fn trts_rdeg a b = (local q1 = a.rotation, q2 = b.rotation; local d = abs (q1.x*q2.x + q1.y*q2.y + q1.z*q2.z + q1.w*q2.w); if d > 1.0 do d = 1.0; 2.0 * (acos d))

-- 비교용 정규화: LookAt 업노드 축 반전 무시 / 보정된 리스트(비상대 방향 구속 + Euler)는 상대 방향 구속과 같은 것으로
fn trts_normRot s =
(
	if s == undefined then s
	else if (toLower s[1]) == "lookat_constraint" then (local c = deepCopy s; c[4][7] = "~"; c)
	else if (toLower s[1]) == "rotation_list" and s[3].count == 2 and (toLower s[3][1][3][1]) == "orientation_constraint" and (toLower s[3][2][3][1]) == "euler_xyz" then
	(
		local oc = s[3][1][3]
		#("Orientation_Constraint", true, oc[3], oc[4])
	)
	else s
)

-- 생성 직후 기준 포즈(want)와 비교해서 보정. 결과: "" 또는 보정 내용
--  * LookAt 이 180도 뒤집힘 → 업노드 축 반전
--  * 상대(초기 오프셋 유지) 방향 구속의 오프셋이 스크립트로 안 들어감 → 리스트(비상대 구속 + Euler 오프셋)
fn trts_fixRot o e want pre names =
(
	local rs = e[15], msg = ""
	if rs != undefined and (classOf o.controller) == prs do
	(
		local k = toLower rs[1]
		local d0 = trts_rdeg (at time 0 o.transform) want
		if k == "lookat_constraint" and d0 > 90.0 do
		(
			local c = o.rotation.controller
			c.StoUP_axisFlip = not c.StoUP_axisFlip
			local d1 = trts_rdeg (at time 0 o.transform) want
			if d1 < d0 then msg = "LookAt 업노드 축 반전으로 맞춤 (" + (formattedPrint d0 format:".1f") + "도 → " + (formattedPrint d1 format:".2f") + "도)"
			else c.StoUP_axisFlip = not c.StoUP_axisFlip
		)
		if k == "orientation_constraint" and rs[2] and d0 > 0.1 do
		(
			local lst = Rotation_List()
			o.rotation.controller = lst
			lst = o.rotation.controller
			local n0 = lst.count
			lst.Available.controller = Orientation_Constraint()
			local c = lst[lst.count].controller
			for t in rs[4] do (local nd = trts_res t[1] pre names; if nd != undefined do c.appendTarget nd t[2])
			c.local_world = rs[3]
			c.relative = false
			lst.Available.controller = Euler_XYZ()
			for i = n0 to 1 by -1 do lst.delete i
			lst.active = 2
			local B = at time 0 o.transform
			lst[2].controller.value = (want * (inverse B)).rotation
			local d1 = trts_rdeg (at time 0 o.transform) want
			msg = "상대 방향 구속 오프셋을 리스트(구속+Euler)로 보정 (" + (formattedPrint d0 format:".2f") + "도 → " + (formattedPrint d1 format:".3f") + "도)"
		)
	)
	msg
)

-- 템플릿 엔트리 e 와 씬에서 뽑은 엔트리 s 의 구조 비교 (값 비율 차이는 무시)
fn trts_cmp e s pre names =
(
	local w = ""
	if e[2] != s[2] do w += "종류  "
	local wantPar = TosRig.mapName e[3] pre names
	if wantPar != s[3] do w += "부모(" + s[3] + " → " + wantPar + ")  "
	if e[8] != s[8] do w += "레이어  "
	if (trts_sig e[14]) != (trts_sig s[14]) do w += "위치 컨트롤러  "
	if (trts_sig (trts_normRot e[15])) != (trts_sig (trts_normRot s[15])) do w += "회전 컨트롤러  "
	if (trts_sig e[16]) != (trts_sig s[16]) do w += "트랜스폼 스크립트  "
	w
)

fn trts_p2 n = (if n < 10 then "0" + (n as string) else (n as string))
fn trts_stamp =
(
	try
	(
		local t = getLocalTime()
		(t[1] as string) + (trts_p2 t[2]) + (trts_p2 t[4]) + "_" + (trts_p2 t[5]) + (trts_p2 t[6]) + (trts_p2 t[7])
	)
	catch ((timeStamp()) as string)
)

-- ---------------------------------------------------------------- 도구
struct TosRigStdStruct
(
	version = "TOS 1.0",
	tplId = "tos_twist_f",   -- 지금 읽힌 템플릿 (성별에 따라 tos_twist_m / tos_twist_f)

	fn tplDir = (trimRight (TosRig.sbgDir()) "\\"),
	fn tplFile = (TosRig.dataFile (tplId + ".ms")),   -- 이 PC Body 폴더에서 다시 읽은 데이터가 있으면 그것
	fn tplFor g = ("tos_twist_" + (if g == #m then "m" else "f")),

	-- 템플릿을 뽑은 레퍼런스 캐릭터의 마디 길이 (TosRigStdInfo[7])
	fn stdSegs = (if TosRigStdInfo != undefined and TosRigStdInfo.count >= 7 and (classOf TosRigStdInfo[7]) == Array then TosRigStdInfo[7] else undefined),
	-- g: #m / #f / undefined(지금 읽힌 것 그대로). 성별이 바뀌면 그 성별 템플릿을 다시 읽음
	fn ensureLoaded g:undefined =
	(
		if g != undefined and (tplFor g) != tplId do (tplId = tplFor g; TosRigStdTpl = undefined; TosRigStdInfo = undefined)
		if TosRigStdTpl == undefined and (doesFileExist (tplFile())) do fileIn (tplFile())
		TosRigStdTpl != undefined
	),

	fn info = (if (ensureLoaded()) then ("Twist 템플릿 " + TosRigStdInfo[1] + "@" + TosRigStdInfo[2] + " / 노드 " + (TosRigStdTpl.count as string) + "개 / 레퍼런스 " + TosRigStdInfo[3]) else ("Twist 템플릿 없음: " + (tplFile()))),

	-- (관리용) 지금 씬(TOS 레퍼런스 파일)의 twist 레이어 보조 본 → tos_twist_<g>.ms. outDir 를 주면 거기에 저장
	-- 예: TosRigStd.captureTwist #m outDir:@"D:\work"  (UI 에는 없음)
	fn captureTwist g outDir:undefined =
	(
		local pre = TosRig.bipPrefix()
		if pre == undefined do return "오류: 장면에 Biped가 없어요."
		local cand = for o in objects where classOf o != Biped_Object and (matchPattern o.layer.name pattern:"*twist*") and (trts_bipAncestor o) != undefined collect o
		local maxD = 0
		for o in cand do (local d = trts_depth o; if d > maxD do maxD = d)
		local sorted = #()
		for d = 0 to maxD do for o in cand where (trts_depth o) == d do append sorted o
		local entries = for o in sorted collect (trts_extract o pre)
		local id = tplFor g
		local dir = if outDir != undefined then outDir else tplDir()
		makeDir dir all:true
		local f = dir + "\\" + id + ".ms"
		local segs = for s in TosRigSeg collect #(s[1], (TosRig.segLen pre s[1]))
		local inf = #(id, version, maxFileName, (trts_stamp()), entries.count, pre, segs)
		local fs = stringStream ""
		format "-- TOS_RigTools Twist 보조 본 템플릿 (레퍼런스에서 자동 생성: TosRigStd.captureTwist)\n" to:fs
		format "global TosRigStdInfo = %\n" (trts_txt inf) to:fs
		format "global TosRigStdTpl = #(\n" to:fs
		for i = 1 to entries.count do format "\t%%\n" (trts_txt entries[i]) (if i < entries.count then "," else "") to:fs
		format ")\n" to:fs
		(dotNetClass "System.IO.File").WriteAllText f (fs as string) (dotNetObject "System.Text.UTF8Encoding" true)
		TosRigStdTpl = undefined
		"[Twist 템플릿 저장] " + (entries.count as string) + "개 노드 → " + f
	),

	-- [3. 생성] 으로 만든 Twist 보조 본 목록 (템플릿 이름 + 표식, Biped 제외)
	fn helperNodes =
	(
		ensureLoaded()
		local out = #()
		if TosRigStdTpl != undefined do for e in TosRigStdTpl do (local o = getNodeByName e[1] exact:true; if o != undefined and (getUserProp o "RigTools_tpl") != undefined do appendIfUnique out o)
		for o in objects where (local p = getUserProp o "RigTools_tpl"; p != undefined and (matchPattern (p as string) pattern:"tos_twist*")) do appendIfUnique out o
		for o in out where classOf o != Biped_Object collect o
	),
	fn inSkin nodes = (local r = false; for o in nodes while not r do (for d in (refs.dependents o) where classOf d == Skin do r = true); r),
	-- [3. 생성] 성별 레퍼런스의 Twist 보조 본 생성 (이미 있는 이름은 건너뜀, Ctrl+Z 한 번으로 되돌림)
	fn build =
	(
		local g = TosRig.gender()
		if g == undefined do return "취소했어요. (성별을 정하지 않음)"
		if not (ensureLoaded g:g) do return ("오류: Twist 템플릿 파일이 없어요: " + (tplFile()))
		local pre = TosRig.bipPrefix()
		if pre == undefined do return "오류: 장면에 Biped가 없어요."
		local names = for e in TosRigStdTpl collect e[1]
		local rr = TosRig.calcRatios pre segs:(stdSegs())
		local parts = rr[1], ratios = rr[2]
		local made = #(), madeE = #(), skipped = #(), warn = #(), fixes = #()
		sliderTime = 0
		with animate off
		(
			undo "TOS Twist 보조 본" on
			(
				-- 1) 노드 (부모 먼저)
				for e in TosRigStdTpl do
				(
					if (getNodeByName e[1] exact:true) != undefined then append skipped e[1]
					else
					(
						local par = getNodeByName (TosRig.mapName e[3] pre names) exact:true
						if par == undefined then append skipped (e[1] + "(부모 없음)")
						else
						(
							local r = TosRig.ratioOf e[4] parts ratios
							local o = trts_make e r
							o.name = e[1]
							o.wirecolor = e[7]
							(TosRig.getLayer e[8]).addNode o
							o.parent = par
							local m = copy e[5]
							m.row4 = m.row4 * r
							o.transform = m * par.transform
							try (o.boneEnable = false) catch ()
							o.renderable = e[10]
							try (setInheritanceFlags o e[13] keepPos:true) catch ()
							append made o
							append madeE #(e, r)
						)
					)
				)
				-- 2) 컨트롤러 (모든 노드가 생긴 뒤)
				for i = 1 to made.count do
				(
					local o = made[i], e = madeE[i][1], r = madeE[i][2]
					local res = #()
					if e[16] != undefined then append res (try (trts_assign o e[16] #tm r pre names) catch ("오류 " + (getCurrentException())))
					else
					(
						append res (try (trts_assign o e[14] #pos r pre names) catch ("오류 " + (getCurrentException())))
						append res (try (trts_assign o e[15] #rot r pre names) catch ("오류 " + (getCurrentException())))
					)
					for x in res where x != ok do append warn (e[1] + ": " + (x as string))
				)
				-- 2-b) 기준 포즈 확인·자동 보정 (부모 먼저)
				for i = 1 to made.count do
				(
					local o = made[i], e = madeE[i][1]
					local m = copy e[5]
					m.row4 = m.row4 * madeE[i][2]
					local want = m * (at time 0 o.parent.transform)
					local fx = try (trts_fixRot o e want pre names) catch ("오류 " + (getCurrentException()))
					if fx != "" do append fixes (e[1] + ": " + fx)
				)
				-- 2-c) 본 속성은 배치·구속이 다 끝난 뒤에
				for i = 1 to made.count do
				(
					local o = made[i], e = madeE[i][1]
					try (o.boneEnable = e[9][1]; o.boneFreezeLength = e[9][2]; o.boneAutoAlign = e[9][3]; o.boneScaleType = e[9][4]) catch ()
				)
				for i = 1 to made.count where made[i].boneEnable and made[i].children.count > 0 do try (made[i].ResetBoneStretch()) catch ()
				-- 3) 숨김·고정·표식 (레퍼런스처럼 렌더 안 함)
				for i = 1 to made.count do
				(
					local o = made[i], e = madeE[i][1]
					o.isHidden = e[11]
					o.isFrozen = e[12]
					o.renderable = false
					setUserProp o "RigTools_tpl" (tplId + "@" + TosRigStdInfo[2])
					setUserProp o "RigTools_ratio" (formattedPrint madeE[i][2] format:".4f")
				)
			)
		)
		-- TOS: 여자는 가슴 더미 Dummy_Chast (archer_f·cleric_f 레퍼런스와 같은 자리·크기·스케일, 부모 Bip01 Spine2)
		local chLog = if g == #f then (try (trts_chastMake pre) catch ("Dummy_Chast 오류: " + getCurrentException())) else ""
		completeRedraw()
		local log = "[Twist 보조 본 생성] " + (if g == #m then "남자" else "여자") + " 레퍼런스 " + TosRigStdInfo[3] + " (" + TosRigStdInfo[1] + ")\n"
		if chLog != "" do log += chLog + "\n"
		-- Biped 트위스트 뼈 확인 (레퍼런스: 허벅지·아래팔 1개, 종아리·위팔 0개)
		try
		(
			local bc = (getNodeByName pre exact:true).controller
			local rf = if TOS_BipRef != undefined then (TOS_BipRef.get g job:(TosRig.job())) else undefined
			local want = if rf != undefined then rf.twist else #(1, 0, 1, 0)
			local cur = #(bc.thighTwistLinks, bc.calfTwistLinks, bc.forearmTwistLinks, bc.upperarmTwistLinks)
			if (cur as string) != (want as string) or not bc.twists do log += "※ Biped 트위스트 뼈가 레퍼런스와 달라요 (지금 허벅지·종아리·아래팔·위팔 " + (cur as string) + " / 레퍼런스 " + (want as string) + "). [2. Biped 생성] 으로 다시 만들면 맞춰져요.\n"
		) catch ()
		local rl = ""
		for i = 1 to parts.count do rl += parts[i] + "=" + (formattedPrint ratios[i] format:".2f") + "  "
		log += "마디 비율(대상/레퍼런스): " + rl + "\n"
		log += "생성 " + (made.count as string) + "개 / 건너뜀 " + (skipped.count as string) + "개 (템플릿 " + (TosRigStdTpl.count as string) + "개)\n"
		if skipped.count > 0 and skipped.count <= 20 do log += "건너뜀: " + (skipped as string) + "\n"
		if fixes.count > 0 do (log += "자동 보정 " + (fixes.count as string) + "개:\n"; for x in fixes do log += "  " + x + "\n")
		if warn.count > 0 do (log += "경고 " + (warn.count as string) + "개:\n"; for w in warn do log += "  " + w + "\n")
		log + "Ctrl+Z 한 번으로 되돌릴 수 있어요."
	),

	-- 씬과 템플릿 비교 (읽기 전용)
	fn check =
	(
		if not (ensureLoaded()) do return ("오류: Twist 템플릿 파일이 없어요: " + (tplFile()))
		local pre = TosRig.bipPrefix()
		if pre == undefined do return "오류: 장면에 Biped가 없어요."
		local names = for e in TosRigStdTpl collect e[1]
		local rr = TosRig.calcRatios pre segs:(stdSegs())
		local parts = rr[1], ratios = rr[2]
		local missing = #(), diff = #(), same = 0
		for e in TosRigStdTpl do
		(
			local o = getNodeByName e[1] exact:true
			if o == undefined then append missing e[1]
			else if o.parent == undefined then append diff #(e[1], "부모 없음  ")
			else
			(
				local w = trts_cmp e (trts_extract o pre) pre names
				local par = getNodeByName (TosRig.mapName e[3] pre names) exact:true
				if par != undefined do
				(
					local r = TosRig.ratioOf e[4] parts ratios
					local m = copy e[5]
					m.row4 = m.row4 * r
					local want = m * (at time 0 par.transform)
					local cur = at time 0 o.transform
					local dp = distance cur.row4 want.row4
					if dp > 0.01 do w += "위치 " + (formattedPrint dp format:".3f") + "  "
					local da = TosRig.rotDiffDeg cur want
					if da > 0.1 do w += "회전 " + (formattedPrint da format:".2f") + "도  "
				)
				-- 본 늘어남: 보이는 본 끝이 자식 위치와 맞는지 / Box 등은 늘어남이 없어야 함
				if o.boneEnable do
				(
					local st = (at time 0 o.stretchTM).scalepart
					if (classOf o) == BoneGeometry and o.children.count > 0 then
					(
						local vis = o.length * st.x
						local cd = distance (at time 0 o.children[1].transform).row4 (at time 0 o.transform).row4
						if (abs (vis - cd)) > 0.05 do w += "본 길이(보이는 " + (formattedPrint vis format:".2f") + " / 자식까지 " + (formattedPrint cd format:".2f") + ")  "
					)
					else if (abs (st.x - 1)) > 0.01 or (abs (st.y - 1)) > 0.01 or (abs (st.z - 1)) > 0.01 do w += "늘어남 " + (st as string) + "  "
				)
				if w == "" then same += 1 else append diff #(e[1], w)
			)
		)
		local extra = for o in objects where (trts_isCandidate o) and (findItem names o.name) == 0 collect o.name
		local log = "[Twist 비교] " + (info()) + "\n"
		log += "일치 " + (same as string) + " / 다름 " + (diff.count as string) + " / 없음 " + (missing.count as string) + " / 템플릿에 없는 노드 " + (extra.count as string) + "\n"
		if diff.count > 0 do (log += "다름:\n"; for d in diff do log += "  " + d[1] + ": " + d[2] + "\n")
		if missing.count > 0 do log += "없음(생성 대상): " + (missing as string) + "\n"
		if extra.count > 0 do log += "템플릿에 없는 노드: " + (extra as string) + "\n"
		log
	)
)
TosRigStd = TosRigStdStruct()

format "[TOS_RigToolsStd] % loaded\n" TosRigStd.version
