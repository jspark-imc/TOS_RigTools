-- ============================================================================
-- MaxVirusGuard.ms  v1.2  (3ds Max 2014, MAXScript only)
-- Guard against scene-borne MAXScript worms (ALC "CleanBeta", CRP, ADSL families).
--   * At Max start and after every scene open / merge / import: removes worm nodes
--     (objects whose transform script controllers carry worm code), worm globals,
--     persistent globals and callbacks, and quarantines worm files dropped into the
--     startup folders (moved to C:\claude\_격리\auto\, not deleted).
--   * Before every save: cleans again so an infected scene is never written back.
-- Log: Listener + C:\claude\_격리\MaxVirusGuard_log.txt
-- Install: put this file in  %LOCALAPPDATA%\Autodesk\3dsMax\2014 - 64bit\ENU\scripts\startup
--          (the "!" in the file name makes it load before the other startup scripts)
-- ============================================================================
(
	global MVG_version = "1.2"
	global MVG_isBadText, MVG_cleanScene, MVG_quarantineStartup, MVG_log, MVG_onEvent

	-- worm CODE signatures (lower case): function definitions / payload of the worm itself.
	-- (antivirus scripts only list the names like #runMainCleanBeta, so plain names are not used here)
	local sigs = #("fn pointnodecleanbeta", "pointnodecleanbeta=(", "fn runmaincleanbeta", "runmaincleanbeta()", "fn checklicsersubcleanbeta",
		"fn px_simulatorsavecleanbeta", "vrdematcleanbeta", "crp_bscript=", "crp_bscript =", "adsl_bscript=", "adsl_bscript =",
		"fn physxpluginmfx", "physxpluginmfx=")
	-- global names belonging to the worms (lower-case substrings)
	local globSigs = #("cleanbeta", "crp_bscript", "crp_ascript", "crp_writeascript", "adsl_bscript", "adsl_ascript", "physxpluginmfx", "physxpluginstpglb")
	-- callback ids used by the worms
	local cbIds = #(#RenderLicCleanBeta, #PhysXCleanBetaRBKSysInfo, #AutodeskLicCleanBeta, #AutodeskLicences,
		#PhysXCreateRBKSysInfo, #RenderLicences, #AutodeskLicAlpha, #PhysXAlphaRBKSysInfo, #RenderLicAlpha,
		#AutodeskLicCleanAlpha, #PhysXCleanAlphaRBKSysInfo, #RenderLicCleanAlpha,
		#ID_CRP_filePostOpen, #ID_CRP_filePostMerge, #ID_CRP_postImport, #ID_CRP_preRenderP, #ID_CRP_filePostOpenP, #ID_CRP_viewportChangeP,
		#ADSL_filePostOpen, #ADSL_filePostMerge, #ADSL_postImport, #PhysXPluginMfx)
	-- dropped worm file names in startup folders
	local filePats = #("*vrdemat*", "*cleanbeta*", "*crp_*", "*adsl*", "*physxpluginmfx*", "*alc_beta*")
	local qRoot = "C:\\claude\\_격리\\auto\\"
	local logFile = "C:\\claude\\_격리\\MaxVirusGuard_log.txt"

	fn MVG_log s =
	(
		local line = (localTime as string) + "  " + s
		format "[VirusGuard] %\n" s
		try (
			makeDir (getFilenamePath logFile) all:true
			(dotNetClass "System.IO.File").AppendAllText logFile (line + "\r\n") (dotNetObject "System.Text.UTF8Encoding" true)
		) catch ()
	)

	fn MVG_isBadText t =
	(
		local bad = false
		if t != undefined do (
			local s = toLower (t as string)
			for k in sigs while not bad do if (findString s k) != undefined do bad = true
		)
		bad
	)

	-- transform controllers of a node that can hold script text
	fn nodeScripts o =
	(
		-- v1.2: every access is guarded (Biped objects etc. have no .position/.rotation/.scale)
		local out = #()
		local cs = #()
		try (append cs o.position.controller) catch ()
		try (append cs o.rotation.controller) catch ()
		try (append cs o.scale.controller) catch ()
		for c in cs where c != undefined do (
			try (append out c.script) catch ()
			-- list controllers: check their sub controllers too
			try (for i = 1 to c.numSubs do (local sc = try (c[i].controller) catch undefined; if sc != undefined do try (append out sc.script) catch ())) catch ()
		)
		out
	)

	fn MVG_quarantineStartup =
	(
		local moved = 0
		local dirs = #()
		try (appendIfUnique dirs (getDir #userStartupScripts)) catch ()
		try (appendIfUnique dirs (getDir #startupScripts)) catch ()
		local stamp = (dotNetClass "System.DateTime").Now.ToString "yyyyMMdd_HHmmss"
		for d in dirs where d != undefined and d != "" do (
			for f in getFiles (d + "\\*.*") do (
				local nm = toLower (filenameFromPath f)
				if (matchPattern nm pattern:"!maxvirusguard*") do continue
				local hit = false
				for p in filePats while not hit do if matchPattern nm pattern:p do hit = true
				-- plain .ms/.mcr in startup that carry worm code
				if not hit and ((getFilenameType f) == ".ms" or (getFilenameType f) == ".mcr") do (
					local txt = ""
					try (txt = (dotNetClass "System.IO.File").ReadAllText f) catch ()
					if (MVG_isBadText txt) and not (matchPattern nm pattern:"*safeprune*") do hit = true
				)
				if hit do (
					local qd = qRoot + stamp + "\\"
					makeDir qd all:true
					local done = false
					try ((dotNetClass "System.IO.File").Move f (qd + (filenameFromPath f) + ".quarantine"); done = true) catch ()
					if not done do try (done = deleteFile f) catch ()
					moved += 1
					MVG_log ("startup worm file " + (if done then "quarantined: " else "COULD NOT REMOVE: ") + f)
				)
			)
		)
		moved
	)

	-- returns number of things removed from the current scene / session
	fn MVG_cleanScene why =
	(
		local n = 0
		-- 1) worm nodes
		local badNodes = #()
		for o in objects where isValidNode o do (
			local isBad = false
			try (for t in (nodeScripts o) while not isBad do if MVG_isBadText t do isBad = true) catch ()
			if isBad do append badNodes o
		)
		if badNodes.count > 0 do (
			local names = ""
			for o in badNodes do names += o.name + "; "
			try (delete badNodes; n += badNodes.count; MVG_log ("[" + why + "] worm nodes removed (" + (badNodes.count as string) + "): " + names + " file=" + maxFilePath + maxFileName)) catch (MVG_log ("[" + why + "] could not delete worm nodes: " + getCurrentException()))
		)
		-- 2) worm globals and persistent globals
		local gl = #()
		for v in globalVars.gather() do (
			local s = toLower (v as string)
			for k in globSigs do if (findString s k) != undefined do appendIfUnique gl v
		)
		for v in (try (persistents.gather()) catch #()) do (
			local val = try (globalVars.get v) catch undefined
			if (MVG_isBadText (v as string)) or ((classOf val == String) and (MVG_isBadText val)) do appendIfUnique gl v
		)
		for g in gl do (
			try (if persistents.isPersistent g do persistents.remove g) catch ()
			try (globalVars.remove g) catch ()
			n += 1
		)
		if gl.count > 0 do MVG_log ("[" + why + "] worm globals removed: " + (gl as string))
		-- 3) worm callbacks
		for id in cbIds do try (callbacks.removeScripts id:id) catch ()
		-- 4) files dropped into startup folders
		n += MVG_quarantineStartup()
		n
	)

	fn MVG_onEvent why =
	(
		try (
			local n = MVG_cleanScene why
			if n > 0 and why != "save" do MVG_log ("[" + why + "] scene was infected and has been cleaned in memory. SAVE the file to store the clean version: " + maxFilePath + maxFileName)
		) catch (MVG_log ("error: " + getCurrentException()))
	)

	callbacks.removeScripts id:#MaxVirusGuard
	callbacks.addScript #filePostOpen  "MVG_onEvent \"open\""   id:#MaxVirusGuard
	callbacks.addScript #filePostMerge "MVG_onEvent \"merge\""  id:#MaxVirusGuard
	callbacks.addScript #postImport    "MVG_onEvent \"import\"" id:#MaxVirusGuard
	callbacks.addScript #filePreSave   "MVG_onEvent \"save\""   id:#MaxVirusGuard
	callbacks.addScript #systemPostReset "MVG_onEvent \"reset\"" id:#MaxVirusGuard
	callbacks.addScript #systemPostNew   "MVG_onEvent \"new\""   id:#MaxVirusGuard

	MVG_onEvent "start"
	format "[VirusGuard] v% active\n" MVG_version
)
