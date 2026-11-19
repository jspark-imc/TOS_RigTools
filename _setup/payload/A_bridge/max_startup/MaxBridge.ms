-- ============================================================================
-- MaxBridge.ms  v1.4.5   (3ds Max 2014 or later, MAXScript + .NET only)
-- Blender / Claude  <->  3ds Max bridge.
-- Listens ONLY on 127.0.0.1 (this PC). Each connection sends MAXScript text;
-- it is executed in Max and the result is sent back as text.
-- Port: env MAXBRIDGE_PORT if set (Claude Max = 9878-9899, started by launch\Max_Claude_multi.bat),
--       otherwise 9877 (the user's normal Max).
-- Put this file in:  %LOCALAPPDATA%\Autodesk\3dsMax\2014 - 64bit\<LANG>\scripts\startup
-- Listener commands:  MBstatus()  = who am I (port, env, file)
--                     MBport 9879 = switch port (a normal Max may not take 9878-9899)
--                     MaxBridge.stop() / MaxBridge.start()
-- v1.4.3: port-busy message printed once (then silent retry), port guard, slot scan cap, 5s read timeout
-- v1.4.5: if serveOnce fails (e.g. resetMaxFile inside a request), busy is cleared so the bridge keeps answering
-- ============================================================================
(
	global MaxBridge
	global MaxBridge_onTick
	global MaxBridge_onRetry

	if MaxBridge != undefined do try (MaxBridge.stop()) catch ()

	struct MaxBridgeStruct
	(
		port = 9877,
		listener = undefined,
		timer = undefined,
		retryTimer = undefined,   -- v1.3: port busy at startup -> retry every 5s
		retryWarned = false,      -- v1.4.3: print the port-busy message only once
		busy = false,
		version = "1.4.6",

		-- ---------- helpers ----------
		fn jsonStr s =
		(
			s = s as string
			s = substituteString s "\\" "\\\\"
			s = substituteString s "\"" "\\\""
			s = substituteString s "\r" ""
			s = substituteString s "\n" "\\n"
			s = substituteString s "\t" " "
			"\"" + s + "\""
		),

		fn unitName =
		(
			case units.SystemType of
			(
				#millimeters: "mm"
				#centimeters: "cm"
				#meters: "m"
				#kilometers: "km"
				#inches: "in"
				#feet: "ft"
				#miles: "mi"
				default: "cm"
			)
		),

		-- ---------- scene info as JSON ----------
		fn info maxObjects:500 =
		(
			local ss = stringStream ""
			format "{\"bridge\":%,\"max_version\":%,\"file\":%,\"system_unit\":%,\"system_scale\":%,\"frame_start\":%,\"frame_end\":%,\"fps\":%,\"object_count\":%,\"selection_count\":%,\"objects\":[" \
				(jsonStr version) ((maxVersion())[1]) (jsonStr (maxFilePath + maxFileName)) (jsonStr (unitName())) units.SystemScale \
				(animationRange.start.frame as integer) (animationRange.end.frame as integer) frameRate objects.count selection.count to:ss
			local i = 0
			for o in objects while i < maxObjects do
			(
				if i > 0 do format "," to:ss
				i += 1
				local pc = try (getPolygonCount o) catch (#(0, 0))
				local mods = ""
				for m in o.modifiers do (if mods != "" do mods += ","; mods += jsonStr (m.name))
				local matName = "", matClass = ""
				if o.material != undefined do (matName = o.material.name; matClass = (classOf o.material) as string)
				local par = if o.parent != undefined then o.parent.name else ""
				format "{\"name\":%,\"class\":%,\"parent\":%,\"faces\":%,\"verts\":%,\"material\":%,\"material_class\":%,\"modifiers\":[%],\"hidden\":%,\"selected\":%,\"layer\":%}" \
					(jsonStr o.name) (jsonStr ((classOf o) as string)) (jsonStr par) pc[1] pc[2] (jsonStr matName) (jsonStr matClass) mods o.isHidden o.isSelected (jsonStr o.layer.name) to:ss
			)
			format "]}" to:ss
			ss as string
		),

		-- ---------- FBX export (Max -> Blender) ----------
		fn setE n v = (try (FBXExporterSetParam n v) catch ()),
		fn setI n v = (try (FBXImporterSetParam n v) catch ()),

		fn exportFBX path selOnly:true anim:true =
		(
			if selOnly and selection.count == 0 do return "ERROR: nothing selected in 3ds Max"
			makeDir (getFilenamePath path) all:true
			try (FBXExporterSetParam "ResetExport") catch ()
			setE "FileVersion" "FBX201400"
			setE "ASCII" false
			setE "UpAxis" "Z"
			setE "ConvertUnit" (unitName())
			setE "SmoothingGroups" true
			setE "SmoothMeshExport" false
			setE "TangentSpaceExport" false
			setE "Triangulate" false
			setE "Skin" true
			setE "Shape" true
			setE "Cameras" false
			setE "Lights" false
			setE "EmbedTextures" false
			setE "Animation" anim
			setE "BakeAnimation" anim
			setE "BakeFrameStart" (animationRange.start.frame as integer)
			setE "BakeFrameEnd" (animationRange.end.frame as integer)
			setE "BakeFrameStep" 1
			setE "BakeResampleAnimation" anim   -- force a key on every frame (keeps Max curve shapes exactly)
			setE "ShowWarnings" false
			setE "GenerateLog" false
			local n = if selOnly then selection.count else objects.count
			local ok = exportFile path #noPrompt selectedOnly:selOnly using:FBXEXP
			if (doesFileExist path) then ("OK: exported " + (n as string) + " objects (" + (unitName()) + ") to " + path) else "ERROR: FBX export failed"
		),

		-- ---------- FBX import (Blender -> Max). Never overwrites: new objects go to their own layer ----------
		fn importFBX path layerName:"FromBlender" =
		(
			if not (doesFileExist path) do return ("ERROR: file not found " + path)
			try (holdMaxFile()) catch ()
			local before = for o in objects collect o.inode.handle
			try (FBXImporterSetParam "ResetImport") catch ()
			setI "Mode" #create
			setI "ConvertUnit" (unitName())
			setI "ScaleConversion" true
			setI "UpAxis" "Z"
			setI "Animation" true
			setI "Skin" true
			setI "Shape" true
			setI "SmoothingGroups" true
			setI "Cameras" false
			setI "Lights" false
			setI "ImportBoneAsDummy" false
			setI "ShowWarnings" false
			setI "GenerateLog" false
			importFile path #noPrompt using:FBXIMP
			local newObjs = for o in objects where (findItem before o.inode.handle) == 0 collect o
			-- Blender adds its armature object as an extra root node: remove it when it is a plain identity dummy
			local removed = 0
			for o in newObjs where (classOf o == Dummy) and (o.parent == undefined) and (o.children.count > 0) and (matchPattern o.name pattern:"Armature*") do
			(
				local tm = o.transform
				if (distance tm.row4 [0,0,0]) < 0.001 and (abs (tm.row1.x - 1.0)) < 0.001 and (abs (tm.row2.y - 1.0)) < 0.001 and (abs (tm.row3.z - 1.0)) < 0.001 do
				(
					local kids = for ch in o.children collect ch
					for c in kids do c.parent = undefined
					delete o
					removed += 1
				)
			)
			newObjs = for o in newObjs where isValidNode o collect o
			local lay = LayerManager.getLayerFromName layerName
			if lay == undefined do lay = LayerManager.newLayerFromName layerName
			for o in newObjs do lay.addNode o
			"OK: imported " + (newObjs.count as string) + " objects into layer '" + layerName + "' (Edit > Fetch to undo)"
		),

		-- ---------- skin helpers ----------
		fn getSkin o = (local s = for m in o.modifiers where classOf m == Skin collect m; if s.count > 0 then s[1] else undefined),
		fn skinnedMeshes = (for o in objects where (getSkin o) != undefined collect o),

		-- real start/end of a node as a bone (BoneGeometry length, Biped extent, helper bbox long axis)
		fn boneSeg o =
		(
			local tm = o.transform, p0 = tm.row4, c = classOf o
			if c == BoneGeometry then #(p0, p0 + (normalize tm.row1) * o.length, "bone")
			else
			(
				local bb = nodeGetBoundingBox o tm
				local mn = bb[1], mx = bb[2], ext = mx - mn
				if (amax #(ext.x, ext.y, ext.z)) < 0.001 then #(p0, p0, "point")
				else if c == Biped_Object then #(p0, (point3 mx.x 0 0) * tm, "biped")
				else
				(
					local ax = if ext.x >= ext.y and ext.x >= ext.z then 1 else (if ext.y >= ext.z then 2 else 3)
					local ctr = (mn + mx) / 2.0, a = [0,0,0]
					a[ax] = ext[ax] / 2.0
					#((ctr - a) * tm, (ctr + a) * tm, "helper")
				)
			)
		),

		-- Skin bone names by SLOT.  Max keeps an empty slot for every deleted bone: GetNumberBones counts only live
		-- bones but GetBoneName takes slot numbers, so scan slots until all live bones are found.  returns #(names, emptySlots)
		fn skinBoneNames sk =
		(
			-- v1.4.3: also stop after 2000 empty slots in a row (a bone with an empty name would otherwise scan 10000 slots)
			local nb = skinOps.GetNumberBones sk, names = #(), found = 0, i = 0, empty = 0, run = 0
			while found < nb and i < nb + 10000 and run < 2000 do
			(
				i += 1
				local n = try (skinOps.GetBoneName sk i 1) catch undefined
				if n == undefined or n == "" then (empty += 1; run += 1) else (append names n; found += 1; run = 0)
			)
			#(names, empty)
		),

		-- writes every skin influence's real geometry (for Blender rig_weights.apply_max_segments)
		fn dumpSegments outPath =
		(
			sliderTime = 0
			local names = #()
			max modify mode
			for o in skinnedMeshes() do
			(
				local sk = getSkin o
				select o
				modPanel.setCurrentObject sk
				for n in (skinBoneNames sk)[1] do appendIfUnique names n
			)
			clearSelection()
			max create mode
			local f = createFile outPath encoding:#utf8
			for n in names do
			(
				local o = getNodeByName n
				if o != undefined do
				(
					local s = boneSeg o, tm = o.transform
					format "%\t%\t%\t% % %\t% % %\t%\t%\n" n (classOf o) s[3] s[1].x s[1].y s[1].z s[2].x s[2].y s[2].z (if o.parent != undefined then o.parent.name else "") (dot (cross tm.row1 tm.row2) tm.row3) to:f
				)
			)
			close f
			"OK: " + (names.count as string) + " influences"
		),

		-- per-vertex weights as  boneName=weight<TAB>...  (uses list IDs correctly on Max 2014)
		fn dumpSkinNamed n path =
		(
			local o = getNodeByName n, sk = getSkin o
			max modify mode
			select o
			modPanel.setCurrentObject sk
			local f = createFile path encoding:#utf8
			local nv = skinOps.GetNumberVertices sk
			for v = 1 to nv do
			(
				for k = 1 to (skinOps.GetVertexWeightCount sk v) do
				(
					local w = skinOps.GetVertexWeight sk v k
					if w > 0.0001 do format "%=%\t" (skinOps.GetBoneNameByListID sk (skinOps.GetVertexWeightBoneID sk v k) 1) w to:f
				)
				format "\n" to:f
			)
			close f
			clearSelection()
			nv
		),

		-- replaces the mesh's Skin with weights from Blender (#BONES header + index:weight lines)
		fn applyWeights n path limit:4 =
		(
			local o = getNodeByName n
			local f = openFile path encoding:#utf8
			local hdr = filterString (readLine f) "\t"
			local names = for i = 2 to hdr.count collect hdr[i]
			local missing = for b in names where (getNodeByName b) == undefined collect b
			if missing.count > 0 then (close f; "ERROR missing bones: " + (missing as string))
			else
			(
				for i = o.modifiers.count to 1 by -1 where classOf o.modifiers[i] == Skin do deleteModifier o i
				local sk = Skin()
				addModifier o sk
				max modify mode
				select o
				modPanel.setCurrentObject sk
				sk.bone_Limit = limit
				for i = 1 to names.count do skinOps.addBone sk (getNodeByName names[i]) (if i == names.count then 1 else 0)
				classOf o
				completeRedraw()
				modPanel.setCurrentObject sk
				local nb = skinOps.GetNumberBones sk
				local skNames = for i = 1 to nb collect (skinOps.GetBoneName sk i 1)
				local idmap = for b in names collect (findItem skNames b)
				local nv = skinOps.GetNumberVertices sk, v = 0
				disableSceneRedraw()
				while not eof f do
				(
					local l = readLine f
					v += 1
					if v <= nv do
					(
						local ids = #(), ws = #()
						for t in (filterString l " ") do (local p = filterString t ":"; append ids idmap[(p[1] as integer) + 1]; append ws (p[2] as float))
						if ids.count > 0 do (for k = 1 to (skinOps.GetVertexWeightCount sk v) do (local id = skinOps.GetVertexWeightBoneID sk v k; if (findItem ids id) == 0 do (append ids id; append ws 0.0)); skinOps.ReplaceVertexWeights sk v ids ws)  -- [v1.4.4 fix 2026-10-24] Max 2014: 목록에 없는 본(Skin 엔벨로프 자동값)은 0으로 명시해야 섞이지 않음
					)
				)
				enableSceneRedraw()
				close f
				clearSelection()
				max create mode
				"OK: " + n + " verts " + (nv as string) + ", bones " + (nb as string)
			)
		),

		-- ---------- standardizing: clean follower bone ----------
		fn isCleanChain o =
		(
			local ok2 = true, p = o
			while p != undefined do
			(
				local tm = p.transform
				if (dot (cross tm.row1 tm.row2) tm.row3) < 0 or not (classOf p == BoneGeometry or classOf p == Biped_Object) do ok2 = false
				p = p.parent
			)
			ok2
		),
		fn cleanAncestor o = (local p = o.parent; while p != undefined and not (isCleanChain p) do p = p.parent; p),

		-- creates (or re-uses) bone <newName> that rigidly follows <srcName>, hung under the nearest clean bone.
		-- Max deformation stays identical; Blender gets a clean, positive bone chain.
		fn makeFollower srcName newName =
		(
			sliderTime = 0
			local H = getNodeByName srcName, b = getNodeByName newName
			if H == undefined do return ("ERROR: no node " + srcName)
			if b == undefined do
			(
				local s = boneSeg H, tm = H.transform
				local d = normalize (s[2] - s[1]), z = normalize tm.row3
				if abs (dot d z) > 0.99 do z = normalize tm.row2
				b = BoneSys.createBone s[1] s[2] z
				b.name = newName
				if classOf H == BoneGeometry then (b.width = H.width; b.height = H.height) else (b.width = (distance s[1] s[2]) * 0.25; b.height = b.width)
				b.wirecolor = (color 255 200 0)
				local lay = LayerManager.getLayerFromName "B_Standard"
				if lay == undefined do lay = LayerManager.newLayerFromName "B_Standard"
				lay.addNode b
			)
			if classOf b.controller == transform_script then ("skip " + newName)
			else
			(
				local B0 = b.transform, P = cleanAncestor H
				local L = B0 * (inverse H.transform)
				b.parent = P
				local sc = transform_script()
				b.controller = sc
				sc.addNode "H" H
				-- isValidNode guard: if the followed node is briefly missing (delete/undo), stay put instead of flooding error dialogs
				if P != undefined then (sc.addNode "P" P; sc.addConstant "L" L; sc.script = "if isValidNode H and isValidNode P then (L * H.transform) * (inverse P.transform) else L")
				else (sc.addConstant "L" L; sc.script = "if isValidNode H then L * H.transform else L")
				newName + " <- " + srcName + " under " + (if P != undefined then P.name else "world")
			)
		),

		-- ---------- pipeline helpers (used by the Blender "Standardize" button) ----------
		fn skinnedNames = (local s = ""; for o in skinnedMeshes() do (if s != "" do s += "\t"; s += o.name); s),

		fn skinInfluences =
		(
			local infl = #()
			max modify mode
			for o in skinnedMeshes() do
			(
				local sk = getSkin o
				select o
				modPanel.setCurrentObject sk
				for n in (skinBoneNames sk)[1] do appendIfUnique infl n
			)
			clearSelection()
			max create mode
			infl
		),

		-- skin bones that break Blender: helper class, mirrored, or a dirty parent chain.  name<TAB>reasons<TAB>midX<TAB>class
		fn problemInfluences =
		(
			local ss = stringStream ""
			for n in skinInfluences() do
			(
				local o = getNodeByName n, c = classOf o, tm = o.transform, r = ""
				if classOf o.controller == transform_script do continue
				if not (c == BoneGeometry or c == Biped_Object) do r += "helper,"
				if (dot (cross tm.row1 tm.row2) tm.row3) < 0 do r += "mirror,"
				if o.parent != undefined and not (isCleanChain o.parent) do r += "chain,"
				if r != "" do
				(
					local s = boneSeg o
					format "%\t%\t%\t%\n" n (trimRight r ",") (((s[1] + s[2]) / 2.0).x) c to:ss
				)
			)
			ss as string
		),

		fn addNubs =
		(
			local n = 0, lay = LayerManager.getLayerFromName "B_Standard"
			if lay == undefined do lay = LayerManager.newLayerFromName "B_Standard"
			for nm in skinInfluences() do
			(
				local o = getNodeByName nm
				if o != undefined and classOf o == BoneGeometry and o.children.count == 0 do
				(
					local s = boneSeg o, d = normalize (s[2] - s[1])
					local b = BoneSys.createBone s[2] (s[2] + d * (amax #(o.length * 0.25, 0.2))) (normalize o.transform.row3)
					b.name = nm + "_Nub"
					b.width = o.width * 0.5
					b.height = o.height * 0.5
					b.parent = o
					lay.addNode b
					n += 1
				)
			)
			n
		),

		fn bipedPrefix = (local r = for o in objects where classOf o == Biped_Object and o.parent == undefined collect o; if r.count > 0 then r[1].name else "Bip01"),

		fn rotBip n ang axis t =
		(
			local o = getNodeByName n
			if o != undefined do (local q = at time 0 o.transform.rotation; sliderTime = t; biped.setTransform o #rotation ((quat ang axis) * q) true; sliderTime = 0)
		),

		-- knee / elbow style hinge: rotate about the part's own Z axis (Biped ignores other axes on hinges)
		fn rotBipHinge n ang t =
		(
			local o = getNodeByName n
			if o != undefined do (local q = at time 0 o.transform.rotation; local ax = normalize (at time 0 o.transform.row3); sliderTime = t; biped.setTransform o #rotation (q * (quat ang ax)) true; sliderTime = 0)
		),

		-- the same fixed test pose for any Biped character (arms, elbows, legs, spine, head, skirt/hair/face bones)
		fn testPose =
		(
			local p = bipedPrefix()
			try ((getNodeByName p).controller.figureMode = false) catch ()
			-- a Biped with no animation keys moves on every frame at once: key the rest pose at frame 0 first
			sliderTime = 0
			for o in objects where classOf o == Biped_Object and (matchPattern o.name pattern:(p + "*")) and not (matchPattern o.name pattern:"*Nub") and not (matchPattern o.name pattern:"*Footsteps") do
				try (biped.setTransform o #rotation o.transform.rotation true) catch ()
			try (biped.setTransform (getNodeByName p) #pos (getNodeByName p).transform.pos true) catch ()
			rotBip (p + " L UpperArm") 70 [0,1,0] 10
			rotBip (p + " R UpperArm") -70 [0,1,0] 10
			rotBip (p + " L Forearm") 90 [0,0,1] 20
			rotBip (p + " R Forearm") 90 [0,0,1] 20
			rotBip (p + " L Thigh") 60 [1,0,0] 30
			rotBip (p + " R Thigh") -40 [1,0,0] 30
			rotBipHinge (p + " L Calf") -90 30
			rotBipHinge (p + " R Calf") -45 30
			rotBip (p + " Spine1") 25 [0,0,1] 40
			rotBip (p + " Head") 40 [0,0,1] 40
			for o in objects where classOf o == BoneGeometry and not (matchPattern o.name pattern:"B_*") and not (matchPattern o.name pattern:"*Nub") and classOf o.controller != transform_script do
			(
				local nm = toLower o.name, ang = 0
				if (matchPattern nm pattern:"*skirt*") or (matchPattern nm pattern:"*hair*") or (matchPattern nm pattern:"*cloth*") or (matchPattern nm pattern:"*cape*") then ang = 30
				else if (matchPattern nm pattern:"*eye*") or (matchPattern nm pattern:"*lip*") or (matchPattern nm pattern:"*brow*") then ang = 15
				if ang != 0 do with animate on (at time 50 (in coordsys local rotate o (eulerangles 0 ang 0)))
			)
			"OK"
		),

		fn dumpDeform names frames path =
		(
			local f = createFile path encoding:#utf8
			for n in names do
			(
				local o = getNodeByName n
				for t in frames do
				(
					local m = at time t (snapshotAsMesh o)
					format "#%\t%\t%\n" n t m.numverts to:f
					for i = 1 to m.numverts do (local p = getVert m i; format "% % %\n" p.x p.y p.z to:f)
					delete m
				)
			)
			close f
			"OK"
		),

		-- ---------- rig standard checker ----------
		fn isAsciiName s = (local ok2 = true; for i = 1 to s.count do (if (bit.charAsInt s[i]) > 127 do ok2 = false); ok2),

		fn checkSkin o =
		(
			local ss = stringStream "", sk = getSkin o
			max modify mode
			select o
			modPanel.setCurrentObject sk
			local bad = (skinBoneNames sk)[2]
			if bad > 0 do format "ERROR\t%: % deleted/invalid bone entries in Skin\n" o.name bad to:ss
			local nv = skinOps.GetNumberVertices sk, over = 0, unnorm = 0, none = 0
			for v = 1 to nv do
			(
				local nz = 0, s = 0.0
				for k = 1 to (skinOps.GetVertexWeightCount sk v) do (local w = skinOps.GetVertexWeight sk v k; if w > 0.0001 do (nz += 1; s += w))
				if nz > 4 do over += 1
				if nz == 0 then none += 1 else (if abs (s - 1.0) > 0.01 do unnorm += 1)
			)
			if over > 0 do format "WARN\t%: % vertices have more than 4 bones (game limit 4)\n" o.name over to:ss
			if unnorm > 0 do format "WARN\t%: % vertices not normalized\n" o.name unnorm to:ss
			if none > 0 do format "ERROR\t%: % vertices have no weight\n" o.name none to:ss
			local m0 = at time 0 (snapshotAsMesh o), base = o.baseObject.mesh, tm = o.objectTransform, d = 0.0
			if m0.numverts == base.numverts do for i = 1 to m0.numverts do d = amax d (distance (getVert m0 i) ((getVert base i) * tm))
			delete m0
			if d > 0.01 do format "ERROR\t%: frame 0 is not the bind pose (moves up to % units)\n" o.name d to:ss
			clearSelection()
			max create mode
			ss as string
		),

		fn checkBones =
		(
			local ss = stringStream "", infl = #()
			max modify mode
			for o in skinnedMeshes() do
			(
				local sk = getSkin o
				select o
				modPanel.setCurrentObject sk
				for n in (skinBoneNames sk)[1] do appendIfUnique infl n
			)
			clearSelection()
			max create mode
			local seen = #(), dup = #()
			for o in objects do (if findItem seen o.name > 0 then appendIfUnique dup o.name else append seen o.name)
			for n in dup do format "ERROR\tduplicate object name: %\n" n to:ss
			for n in infl do
			(
				local o = getNodeByName n, c = classOf o, tm = o.transform
				local det = dot (cross tm.row1 tm.row2) tm.row3
				if c != BoneGeometry and c != Biped_Object do format "ERROR\t%: % used as a skin bone (use a real Bone linked to it instead)\n" n c to:ss
				if det < 0 do format "ERROR\t%: mirrored bone (negative scale) - Blender cannot represent it\n" n to:ss
				if c == BoneGeometry and o.length < 0.001 do format "ERROR\t%: zero-length bone\n" n to:ss
				local sc = tm.scalepart
				if (abs (sc.x - 1) > 0.01) or (abs (sc.y - 1) > 0.01) or (abs (sc.z - 1) > 0.01) do format "WARN\t%: scaled bone % (reset scale)\n" n sc to:ss
				if not (isAsciiName n) do format "WARN\t%: non-English characters in name\n" n to:ss
				if c == BoneGeometry and o.children.count == 0 do format "INFO\t%: chain end has no Nub bone\n" n to:ss
				-- every parent up the chain must be a clean (bone, non-mirrored) node, or Blender poses it wrong
				local p = o.parent, badp = ""
				while p != undefined do
				(
					local pt = p.transform
					if (dot (cross pt.row1 pt.row2) pt.row3) < 0 or not (classOf p == BoneGeometry or classOf p == Biped_Object) do (if badp == "" do badp = p.name + " (" + ((classOf p) as string) + ")")
					p = p.parent
				)
				if badp != "" do format "ERROR\t%: parent chain contains % - link it to a clean bone (follower)\n" n badp to:ss
			)
			format "INFO\t% skin bones checked\n" infl.count to:ss
			ss as string
		),

		fn checkRig outPath:"" =
		(
			local r = checkBones()
			for o in skinnedMeshes() do r += checkSkin o
			local nE = 0, nW = 0
			for l in (filterString r "\n") do (if matchPattern l pattern:"ERROR*" do nE += 1; if matchPattern l pattern:"WARN*" do nW += 1)
			r = "RIG CHECK  " + maxFileName + "   errors " + (nE as string) + "   warnings " + (nW as string) + "\n" + r
			if outPath != "" do (local f = createFile outPath encoding:#utf8; format "%" r to:f; close f)
			r
		),

		-- ---------- socket server ----------
		fn serveOnce =
		(
			if busy or listener == undefined do return ok
			if not (listener.Pending()) do return ok
			busy = true
			local client = undefined
			try
			(
				client = listener.AcceptTcpClient()
				local stream = client.GetStream()
				stream.ReadTimeout = 5000   -- v1.4.3: was 15000 (a silent client froze Max that long)
				local enc = dotNetObject "System.Text.UTF8Encoding" false
				local reader = dotNetObject "System.IO.StreamReader" stream enc
				local cmd = reader.ReadToEnd()
				local res = ""
				try
				(
					local r = execute cmd
					res = if r == undefined then "OK" else (r as string)
				)
				catch
				(
					res = "ERROR: " + (getCurrentException())
				)
				local writer = dotNetObject "System.IO.StreamWriter" stream enc
				-- v1.4.6 (Max 2016): a MAXScript string picked the Write(char) overload -> only the first character was sent. Pass a .NET String
				writer.Write (dotNet.ValueToDotNetObject res (dotNetClass "System.String"))
				writer.Flush()
				client.Close()
			)
			catch
			(
				try (client.Close()) catch ()
				format "[MaxBridge] error: %\n" (getCurrentException())
			)
			busy = false
			ok
		),

		fn start =
		(
			if listener != undefined do return "already running"
			try
			(
				local ip = (dotNetClass "System.Net.IPAddress").Loopback
				listener = dotNetObject "System.Net.Sockets.TcpListener" ip port
				listener.Start()
			)
			catch
			(
				listener = undefined
				if not retryWarned do
				(
					format "[MaxBridge] could not open port % (another Max is using it). Retrying quietly every 5s. Stop: MaxBridge.stop()\n" port
					retryWarned = true
				)
				if retryTimer == undefined do
				(
					retryTimer = dotNetObject "System.Windows.Forms.Timer"
					retryTimer.Interval = 5000
					dotNet.addEventHandler retryTimer "Tick" MaxBridge_onRetry
					dotNet.setLifetimeControl retryTimer #mxs
					retryTimer.Start()
				)
				return "ERROR: port in use (retrying)"
			)
			if retryTimer != undefined do (try (retryTimer.Stop()) catch (); retryTimer = undefined)
			retryWarned = false
			timer = dotNetObject "System.Windows.Forms.Timer"
			timer.Interval = 100
			dotNet.addEventHandler timer "Tick" MaxBridge_onTick
			dotNet.setLifetimeControl timer #mxs
			timer.Start()
			format "[MaxBridge] v% listening on 127.0.0.1:%\n" version port
			"OK"
		),

		fn stop =
		(
			try (timer.Stop()) catch ()
			try (retryTimer.Stop()) catch ()
			retryTimer = undefined
			retryWarned = false
			try (listener.Stop()) catch ()
			timer = undefined
			listener = undefined
			"stopped"
		),

		-- v1.4.2: switch this Max's port without restarting.  MaxBridge.setPort 9878   (1025-65535)
		fn setPort newPort force:false =
		(
			local p = try (newPort as integer) catch undefined
			if p == undefined or p < 1025 or p > 65535 do return "ERROR: port must be a number 1025-65535"
			-- v1.4.3 guard: a normal Max (no env MAXBRIDGE_PORT) must not take a Claude port, or Claude tools would drive it
			local ev = try (systemTools.getEnvVariable "MAXBRIDGE_PORT") catch undefined
			local isClaude = ev != undefined and ev != ""
			if not force and not isClaude and p >= 9878 and p <= 9899 do return "ERROR: 9878-9899 are Claude Max ports. This is a normal Max (no MAXBRIDGE_PORT). Use force:true only if you are sure."
			if not force and isClaude and p == 9877 do return "ERROR: 9877 is the user's Max port. This is a Claude Max (MAXBRIDGE_PORT=" + ev + ")."
			if p == port and listener != undefined do return ("already on " + (port as string))
			stop()
			port = p
			local r = start()
			format "[MaxBridge] port -> % (%)\n" port r
			r + " port=" + (port as string)
		),

		-- v1.4.2: who am I?  MaxBridge.status()
		fn status =
		(
			local ev = try (systemTools.getEnvVariable "MAXBRIDGE_PORT") catch undefined
			"MaxBridge v" + version + " port=" + (port as string) + " listening=" + ((listener != undefined) as string) + " env=" + (if ev == undefined or ev == "" then "(none)" else ev) + " file=" + (if maxFileName == "" then "(none)" else (maxFilePath + maxFileName))
		)
	)

	MaxBridge = MaxBridgeStruct()
	-- v1.4: a second Max launched with env MAXBRIDGE_PORT (e.g. Claude worker = 9878) uses that port; normal Max stays 9877
	(
		local ev = try (systemTools.getEnvVariable "MAXBRIDGE_PORT") catch undefined
		if ev != undefined and ev != "" do (local pn = ev as integer; if pn != undefined and pn > 1024 do MaxBridge.port = pn)
	)
	-- v1.4.5: an error escaping serveOnce left busy = true forever (port open, no answers). Clear it and go on.
	fn MaxBridge_onTick sender args = (try (MaxBridge.serveOnce()) catch (try (MaxBridge.busy = false) catch (); format "[MaxBridge] recovered after error: %\n" (getCurrentException())))
	-- shortcuts for the Listener:  MBstatus() = show port/file,  MBport 9879 = switch port (9877 = user Max, 9878-9899 = Claude Max)
	fn MBstatus = (MaxBridge.status())
	fn MBport newp = (MaxBridge.setPort newp)
	fn MaxBridge_onRetry sender args = (if MaxBridge != undefined and MaxBridge.listener == undefined do MaxBridge.start())
	MaxBridge.start()
)
