-- ======================================================================
--  TOS_RigTools - 5. 스킨: 레퍼런스 웨이트 모음 만들기 (tos_make_ref.ms 가 [레퍼런스 다시 읽기] 때 부름)
--  성별마다 스킨이 들어간 레퍼런스 코스튬 몇 개(아래 후보 중 그 PC 에 있는 것)를 열어
--  바인드 자세(Figure Mode) 정점 위치 + 웨이트(본 이름)를 tos_skindb_<m|f>.txt 로 저장한다.
--  형식: 1줄 = "BONES" 탭 이름|가까운 Biped 조상;... / 그다음 정점마다 "x y z 본번호 웨이트 ..."
-- ======================================================================
-- TOS: 레퍼런스 폴더(...\ani\Character\PC) 아래 상대 경로. 직업마다 고루, 옷 모양(교복·짧은 치마·바지)도 섞음 (스킨 있음)
--   TOS 레퍼런스는 허벅지에 ThighTwist 웨이트를 주지 않고 아랫배·엉덩이를 Pelvis 가 받음 (MTOS 레퍼런스와 다름)
global tosdb_cand_m = #("Ver5_Archer_m\\costume\\6th_greenschool\\archer_m_6th_greenschool_set.max", "Ver5_Cleric_m\\costume\\6th_cardiganschool\\cleric_m_6th_cardiganschool_set.max", \
	"Ver5_Warrior_m\\costume\\6th_greenschool\\warrior_m_6th_greenschool_set.max", "Ver5_Archer_m\\costume\\cash_ep17bunnygambler01\\archer_m_ep17bunnygambler01_set.max", \
	"Ver5_Cleric_m\\costume\\cash_ep17bunnygambler01\\cleric_m_ep17bunnygambler01_set.max", "Ver5_Mage_m\\costume\\cash_ep17bunnygambler01\\mage_m_ep17bunnygambler01_set.max", \
	"Ver5_Warrior_m\\costume\\cash_ep17bunnygambler01\\warrior_m_ep17bunnygambler01_set.max", "Ver5_Mage_m\\costume\\cash_ep17bunnygambler02\\mage_m_ep17bunnygambler02_set.max")
global tosdb_cand_f = #("Ver5_Archer_f\\costume\\6th_greenschool\\archer_f_6th_greenschool_set.max", "Ver5_Cleric_f\\costume\\6th_cardiganschool\\cleric_f_6th_cardiganschool_set.max", \
	"Ver5_Warrior_f\\costume\\6th_greenschool\\warrior_f_6th_greenschool_set.max", "Ver5_Archer_f\\costume\\Arbalester01\\archer_f_Arbalester01_set.max", \
	"Ver5_Cleric_f\\costume\\bunnygambler\\cleric_f_ep17bunnygambler01_set.max", "Ver5_Mage_f\\costume\\bunnygambler\\mage_f_ep17bunnygambler01_set.max", \
	"Ver5_Warrior_f\\costume\\bunnygambler\\warrior_f_ep17bunnygambler01_set.max", "Ver5_Mage_f\\costume\\cash_f_ep17bunnygambler02\\mage_f_ep17bunnygambler02_set.max")

fn tosdb_bipAncestor o = (local p = o; while p != undefined and classOf p != Biped_Object do p = p.parent; if p == undefined then "" else p.name)

-- 지금 열린 레퍼런스의 스킨 메쉬 → (정점 위치, 웨이트) 를 쌓음. boneIdx: 이름 → 번호 (dotNet Hashtable)
fn tosdb_collect sb boneNames boneCollapse boneIdx = (
	local root = (for o in objects where classOf o == Biped_Object and o.parent == undefined collect o)
	if root.count == 0 do return 0
	root[1].controller.figureMode = true
	local n = 0
	max modify mode
	for o in objects where superClassOf o == GeometryClass and classOf o != Biped_Object and classOf o != BoneGeometry do (
		local sks = for m in o.modifiers where classOf m == Skin collect m
		if sks.count > 0 do (
			local sk = sks[1]
			select o
			modPanel.setCurrentObject sk
			local nb = skinOps.GetNumberBones sk
			-- 본 ID(웨이트가 쓰는 번호, 넣은 순서) → 이름. GetBoneName 도 본 ID 를 받음 (Max 2016 에서 확인)
			local loc = for i = 1 to nb collect (
				local bn = skinOps.GetBoneName sk i 0
				local bnode = getNodeByName bn exact:true
				if not (boneIdx.ContainsKey bn) do (
					append boneNames bn
					append boneCollapse (if bnode == undefined then "" else tosdb_bipAncestor bnode)
					boneIdx.Add bn (boneNames.count - 1)
				)
				boneIdx.Item[bn]
			)
			-- 바인드 자세 위치: 스킨을 잠시 끄고 메쉬를 읽음
			sk.enabled = false
			local tm = snapshotAsMesh o
			sk.enabled = true
			local nv = amin (skinOps.GetNumberVertices sk) tm.numverts
			for v = 1 to nv do (
				local p = getVert tm v
				local c = skinOps.GetVertexWeightCount sk v
				if c > 0 do (
					sb.Append ((formattedPrint p.x format:".3f") + " " + (formattedPrint p.y format:".3f") + " " + (formattedPrint p.z format:".3f"))
					for i = 1 to c do (
						local w = skinOps.GetVertexWeight sk v i
						if w > 0.001 do sb.Append (" " + (loc[skinOps.GetVertexWeightBoneID sk v i] as string) + " " + (formattedPrint w format:".4f"))
					)
					sb.Append "\n"
					n += 1
				)
			)
			free tm
		)
	)
	n
)

-- 성별 g 의 웨이트 모음 만들기. 반환: 로그 문자열
fn tosdb_make refDir outDir g = (
	local cands = if g == #m then tosdb_cand_m else tosdb_cand_f
	local sb = dotNetObject "System.Text.StringBuilder"
	local boneNames = #(), boneCollapse = #(), boneIdx = dotNetObject "System.Collections.Hashtable"
	local used = #(), total = 0
	for c in cands where doesFileExist (refDir + c) do (
		local ok = try (loadMaxFile (refDir + c) useFileUnits:true quiet:true) catch false
		if ok do (
			local n = tosdb_collect sb boneNames boneCollapse boneIdx
			if n > 0 do (append used (c + " " + (n as string)); total += n)
		)
	)
	if total == 0 do return ("주의: " + (g as string) + " 스킨 레퍼런스가 없어 웨이트 모음을 만들지 못했어요")
	local head = "BONES\t"
	for i = 1 to boneNames.count do head += boneNames[i] + "|" + boneCollapse[i] + (if i < boneNames.count then ";" else "")
	(dotNetClass "System.IO.File").WriteAllText (outDir + "tos_skindb_" + (g as string) + ".txt") (head + "\n" + (sb.ToString())) (dotNetObject "System.Text.UTF8Encoding" false)
	"tos_skindb_" + (g as string) + ".txt: 정점 " + (total as string) + "개, 본 " + (boneNames.count as string) + "개 (" + ((used as string)) + ")"
)
