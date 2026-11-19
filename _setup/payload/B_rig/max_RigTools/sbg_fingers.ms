-- SecBoneGen 손가락 맞춤 (v0.11 추가분)
-- 입력: TSBG_fingerPts = #( #(m1,m2,m3,m4), ... ) 엄지·검지·중지·약지·소지 순서, L 쪽(+X) 좌표
--       m1 = 손가락 뿌리, m2·m3 = 중간 관절, m4 = 손가락 끝
-- Biped 손가락 n 개 × 마디 k 개 (link = (손가락-1)*k + 마디)
-- 비틀림: 손가락 하나의 마디들은 같은 굽힘 축(로컬 Z)을 공유 (정답 리그 Bacha2_t_bip 기준)
--         굽힘 축 = 4점이 이루는 평면의 법선. 손가락이 너무 곧으면 TSBG_fingerRefZ (손 기준 정답 축) 사용
global TSBG_fingerPts = #()
global TSBG_fingerLog = #()
global TSBG_handEndRatio = 0.42   -- 손 뼈 끝 = 중지 뿌리에서 중지 첫 마디의 42% 앞 (Bacha2_t_bip 정답 41.8%)
-- 손 로컬 좌표로 본 손가락 굽힘 축 (Bacha2_t_bip 왼손에서 잰 값)
global TSBG_fingerRefZ = #([0.5675,-0.8193,-0.0813], [0.2358,-0.3062,0.9223], [0.0632,-0.1341,0.9890], [-0.1564,0.0394,0.9869], [-0.2674,0.1452,0.9526])

fn tsbg_fLog s = ( append TSBG_fingerLog s; format "SBG 손가락: %\n" s )

fn tsbg_fingerNub node = (
	local r = undefined
	for c in node.children where (matchPattern c.name pattern:"*Nub*") do r = c
	r
)

fn tsbg_boxLenX h = (
	local xd = normalize h.transform.row1
	local m = snapshotAsMesh h
	local tmax = -1e30
	for i = 1 to (getNumVerts m) do ( local t = dot ((getVert m i) - h.transform.pos) xd; if t > tmax do tmax = t )
	free m
	tmax
)

fn tsbg_mulv v xx xy xz yy yz zz = [xx*v.x + xy*v.y + xz*v.z, xy*v.x + yy*v.y + yz*v.z, xz*v.x + yz*v.y + zz*v.z]

-- 점 4개 평면의 법선 (가장 작은 분산 방향). 곧은 정도(0=곧음)도 돌려줌
fn tsbg_planeNormal pts = (
	local c = [0,0,0]
	for p in pts do c += p
	c /= pts.count
	local xx = 0.0, xy = 0.0, xz = 0.0, yy = 0.0, yz = 0.0, zz = 0.0
	for p in pts do ( local q = p - c; xx += q.x*q.x; xy += q.x*q.y; xz += q.x*q.z; yy += q.y*q.y; yz += q.y*q.z; zz += q.z*q.z )
	-- 가장 큰 분산 방향 2개를 거듭제곱법으로 구한 뒤 외적
	local e1 = normalize [0.6, 0.5, 0.62]
	for it = 1 to 50 do e1 = normalize (tsbg_mulv e1 xx xy xz yy yz zz)
	local l1 = dot e1 (tsbg_mulv e1 xx xy xz yy yz zz)
	local e2 = normalize (cross e1 [0.3, 0.9, 0.2])
	for it = 1 to 50 do (
		e2 = tsbg_mulv e2 xx xy xz yy yz zz
		e2 = normalize (e2 - e1 * (dot e2 e1))
	)
	local l2 = dot e2 (tsbg_mulv e2 xx xy xz yy yz zz)
	#(normalize (cross e1 e2), (if l1 > 1e-9 then l2 / l1 else 0.0))
)

-- 뼈의 X 는 그대로 두고, 로컬 Z 가 hz 쪽을 향하도록 축 둘레로 비틈
fn tsbg_setRoll nd hz = (
	local x = normalize nd.transform.row1
	local z = hz - x * (dot hz x)
	if (length z) < 1e-5 do return false
	z = normalize z
	local y = normalize (cross z x)
	local m = matrix3 x y z nd.transform.pos
	local q = m.rotationpart
	local q0 = biped.getTransform nd #rotation
	local ok = false
	for cand in #(q, inverse q) while not ok do (
		biped.setTransform nd #rotation cand false
		if (dot (normalize nd.transform.row3) z) > 0.995 and (dot (normalize nd.transform.row1) x) > 0.995 do ok = true
	)
	if not ok do biped.setTransform nd #rotation q0 false
	ok
)

-- mirror=true 면 x 를 뒤집어 반대쪽 손에 씀
fn tsbg_fitFingers bip fKey mirror nFing nLink = (
	if TSBG_fingerPts.count < nFing do ( tsbg_fLog "손가락 좌표가 모자라서 건너뜀"; return false )
	local mx = if mirror then -1 else 1
	local armKey = if fKey == #lfingers then #larm else #rarm
	local hand = biped.getNode bip armKey link:4
	for i = 1 to nFing do (
		local raw = TSBG_fingerPts[i]
		local m = for p in raw collect [p.x * mx, p.y, p.z]
		local nodes = for j = 1 to nLink collect (biped.getNode bip fKey link:((i - 1) * nLink + j))
		local tgt = #()
		if nLink == 3 then tgt = m
		else for j = 1 to (nLink + 1) do (
			local t = (j - 1) * 3.0 / nLink
			local a = (floor t) as integer + 1
			if a >= 4 then append tgt m[4]
			else append tgt (m[a] + (m[a + 1] - m[a]) * (t - (a - 1)))
		)
		-- 굽힘 축 (마디를 맞추기 전에 구함): 굽힘 평면 법선 (손 기준 정답 축과 같은 쪽으로 부호 맞춤)
		local refZ = if i <= TSBG_fingerRefZ.count then TSBG_fingerRefZ[i] else [0,0,1]
		-- 오른손: Biped 오른손 축은 왼손 축을 좌우로 뒤집고 Z 만 반대 → 손 기준 좌표 (-a,-b,c)
		if fKey == #rfingers do refZ = [-refZ.x, -refZ.y, refZ.z]
		local refW = normalize (refZ * (hand.transform.rotationpart as matrix3))
		local pn = tsbg_planeNormal m
		local hz = pn[1]
		local src = "평면"
		if i == 1 then ( hz = refW; src = "정답축(엄지)" )
		else if pn[2] < 0.002 then ( hz = refW; src = "정답축(곧은 손가락)" )
		else if (dot hz refW) < 0 do hz = -hz
		local rollFail = 0
		-- 1) 뿌리 위치
		try ( biped.setTransform nodes[1] #pos tgt[1] false ) catch ( tsbg_fLog (nodes[1].name + " 뿌리 이동 실패") )
		local err0 = distance nodes[1].transform.pos tgt[1]
		-- 2) 마디마다 방향·길이
		for j = 1 to nLink do (
			local nd = nodes[j]
			local nx = if j < nLink then nodes[j + 1] else (tsbg_fingerNub nd)
			tsbg_aim nd tgt[j + 1]
			-- 방향을 맞춘 직후 비틀림 (자식 마디는 이 뒤에 맞추므로 끌려가지 않음)
			if not (tsbg_setRoll nd hz) do rollFail += 1
			if nx != undefined do (
				for it = 1 to 2 do (
					local cur = distance nd.transform.pos nx.transform.pos
					local want = distance nd.transform.pos tgt[j + 1]
					if cur > 1e-4 and want > 1e-4 do (
						local s = biped.getTransform nd #scale
						s.x *= want / cur
						biped.setTransform nd #scale s false
					)
				)
			)
		)
		-- 결과
		local errMax = err0
		for j = 2 to nLink do ( local e = distance nodes[j].transform.pos tgt[j]; if e > errMax do errMax = e )
		local tip = tsbg_fingerNub nodes[nLink]
		if tip != undefined do ( local e = distance tip.transform.pos tgt[nLink + 1]; if e > errMax do errMax = e )
		tsbg_fLog (nodes[1].name + "  최대 오차 " + (formattedPrint errMax format:".2f") + "cm  비틀림=" + src + (if rollFail > 0 then ("  비틀림실패 " + (rollFail as string)) else ""))
	)
	true
)

-- 손 뼈 끝을 중지 뿌리에서 첫 마디의 TSBG_handEndRatio 만큼 앞으로. 손가락 맞춤 전에 부름 (목표는 감지 좌표)
fn tsbg_fitHandEnd bip armKey mirror = (
	if TSBG_fingerPts.count < 3 do return false
	local h = biped.getNode bip armKey link:4
	if h == undefined do return false
	local mx = if mirror then -1 else 1
	local a = TSBG_fingerPts[3][1], b = TSBG_fingerPts[3][2]
	a = [a.x * mx, a.y, a.z]; b = [b.x * mx, b.y, b.z]
	local tgt = a + (b - a) * TSBG_handEndRatio
	tsbg_aim h tgt
	for it = 1 to 3 do (
		local cur = tsbg_boxLenX h
		local want = distance h.transform.pos tgt
		if cur > 1e-4 do ( local sc = biped.getTransform h #scale; sc.x *= want / cur; biped.setTransform h #scale sc false )
	)
	true
)

-- 발가락 피봇을 지정 위치로 (피규어 모드). 정답 리그 기준: 발 피봇에서 앞쪽, 바닥 높이
fn tsbg_fitToe bip toeKey toePt = (
	local t1 = biped.getNode bip toeKey link:1
	if t1 == undefined or toePt == undefined do return false
	try ( biped.setTransform t1 #pos toePt false ) catch ( tsbg_fLog (t1.name + " 이동 실패"); return false )
	tsbg_fLog (t1.name + " 오차 " + (formattedPrint (distance t1.transform.pos toePt) format:".2f") + "cm")
	true
)
