global trts_sbgBuild, trts_sbgBuildRef, TSBG_noDialog  -- SecBoneGen Biped 자동 생성 (scripts\SecBoneGen\sbg_build.ms, 1.5)
global TosRigStd, trts_testKeys, trts_mirrorLR, trts_layerTidy, trts_romKeys  -- defined in TOS_RigToolsStd.ms, which loads after this file (alphabetical); declare first so the buttons see them
global TOS_RigTools_version = "1.0"   -- 설치 점검(2_CHECK.bat)이 이 값으로 TOS_RigTools 가 읽혔는지 봄
global tos_secBuildClav, tos_skinApply, TOS_RigDirOverride, TOS_SecRef, tos_makeRef, TOS_BipRef, tos_secBuild, tos_secItems, tos_secPick, tos_secDelete  -- scripts\TOS_RigTools\tos_bip_ref.ms · tos_secondary.ms
-- template data (generated from limb_helpers.json, source: Ivelar_06_standard + user calf structure 2026-10-17)
-- #(name, class, parent, bipPart, localMatrix12, posCtrl, posExpr, rotCtrl, targets, relative, local_world, lookat, dims, wire, layer, boneEnable, renderable)
global TosRigTpl = #(
	#("Point_L Thigh", "Point", "Bip01 L Thigh", "L Thigh", #(1,0,0,0,-1,-3.25863e-07,0,3.2583e-07,-1,-7.62939e-06,0,3.8147e-06), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(10,true,true,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Bone_L Thigh", "BoneGeometry", "Point_L Thigh", "L Thigh", #(1,0,0,0,1,0,0,0,1,0,0,0), "Position_XYZ", undefined, "Orientation_Constraint", #(#("-",50),#("Point_leg_L",0)), false, 1, undefined, #(42.2061,9,9,0,false,false,false), (color 174 186 203), "bone_body", true, false),
	#("Bone_L Thigh_Nub", "BoneGeometry", "Bone_L Thigh", "L Thigh", #(1,0,-1.80677e-07,0,1,1.98089e-06,1.82074e-07,-1.94992e-06,1,42.2061,0,-7.62939e-06), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(10.5515,4.5,4.5,0,false,false,false), (color 174 186 203), "B_Standard", true, false),
	#("Point_leg_L", "Point", "Bip01 L Thigh", "L Thigh", #(0.99969,-0.0249035,2.31899e-07,0.0249034,0.99969,0,-3.16184e-07,0,1,-3.05176e-05,-8.64267e-07,-2.28882e-05), "Position_XYZ", undefined, "LookAt_Constraint", #(#("-",50),#("-",50),#("Bip01 L Foot",50)), false, 0, #(0,false,false,"Bip01 L Thigh",1,2,false,2), #(20,true,true,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Point_up_L", "Point", "Bip01 L Thigh", "L Thigh", #(0.999999,0,-1.62516e-07,0,1,-3.34472e-07,1.2666e-07,3.29301e-07,1,41.7751,-2.38419e-07,1.90735e-06), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(15,true,true,false,false), (color 224 86 86), "Bone_helper", false, false),
	#("Box_Knee_L", "Box", "Bip01 L Thigh", "L Thigh", #(1.39698e-07,-1.50809e-07,-1,0.999999,-0.00129156,1.31316e-07,-0.00129155,-0.999999,1.50243e-07,41.7751,-4.76837e-07,-3.8147e-06), "Position_Expression", [41.7751,-4.76837e-07,-3.8147e-06], "Orientation_Constraint", #(#("Point_dn_L",50),#("Point_up_L",50)), true, 0, undefined, #(4,10,-8.30674), (color 177 88 27), "bone_body", true, false),
	#("Point_dn_L", "Point", "Bip01 L Calf", "L Calf", #(0.999999,0,-1.50409e-07,0,1,-3.37459e-07,1.27591e-07,3.37459e-07,1,0,0,0), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(25,true,false,false,false), (color 224 86 86), "Bone_helper", false, false),
	#("Point_R Thigh", "Point", "Bip01 R Thigh", "R Thigh", #(1,0,0,0,-1,-4.52067e-06,0,4.57603e-06,-1,0,0,-2.28882e-05), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(10,true,true,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Bone_R Thigh", "BoneGeometry", "Point_R Thigh", "R Thigh", #(1,0,0,0,1,0,0,0,1,0,0,0), "Position_XYZ", undefined, "Orientation_Constraint", #(#("Point_leg_R",0),#("-",50)), false, 1, undefined, #(42.2061,9,9,0,false,false,false), (color 174 186 203), "bone_body", true, false),
	#("Bone_R Thigh_Nub", "BoneGeometry", "Bone_R Thigh", "R Thigh", #(1,0,0,0,1,2.95745e-06,0,-2.94264e-06,1,42.206,0,4.76837e-06), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(10.5515,4.5,4.5,0,false,false,false), (color 174 186 203), "B_Standard", true, false),
	#("Point_leg_R", "Point", "Bip01 R Thigh", "R Thigh", #(0.99969,-0.0249035,2.01631e-07,0.0249034,0.99969,0,-1.94181e-07,0,1,-7.62939e-06,-1.04308e-06,-2.28882e-05), "Position_XYZ", undefined, "LookAt_Constraint", #(#("-",50),#("Bip01 R Foot",50)), false, 0, #(0,false,false,"Bip01 R Thigh",1,2,false,2), #(20,true,true,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Point_up_R", "Point", "Bip01 R Thigh", "R Thigh", #(0.999999,0,0,0,1,0,0,0,1,41.7751,7.15256e-07,2.86102e-06), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(15,true,true,false,false), (color 224 86 86), "Bone_helper", false, false),
	#("Box_Knee_R", "Box", "Bip01 R Thigh", "R Thigh", #(0.000128819,-0.000129211,-1,0.999998,-0.00195959,0.000129114,-0.00195965,-0.999998,0.000128959,41.7751,-1.78814e-07,1.04904e-05), "Position_Expression", [41.7751,-1.6205e-07,9.53674e-06], "Orientation_Constraint", #(#("Point_dn_R",50),#("Point_up_R",50)), true, 0, undefined, #(4,10,-8.30674), (color 177 88 27), "bone_body", true, false),
	#("Point_dn_R", "Point", "Bip01 R Calf", "R Calf", #(1,2.08952e-05,0,-2.08952e-05,1,-0.000182628,0,0.000182629,1,3.8147e-06,-2.38419e-07,9.53674e-06), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(25,true,false,false,false), (color 224 86 86), "Bone_helper", false, false),
	#("Point_elbowL_dn", "Point", "Bip01 L Forearm", "L Forearm", #(1,0,1.19209e-07,0,1,0,0,0,1,0,0,0), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(15,true,false,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Point_elbowL_up", "Point", "Bip01 L UpperArm", "L UpperArm", #(1,0,0,0,1,-1.56462e-07,1.78814e-07,1.63913e-07,1,22.416,0,0), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(15,true,false,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Box_elbow_L", "Box", "Bip01 L Forearm", "L Forearm", #(-0.994779,-0.102053,3.00705e-05,1.01328e-05,0.00019704,1,-0.102053,0.994779,-0.000194877,0.000175476,-3.8147e-05,0.00025177), "Position_XYZ", undefined, "Orientation_Constraint", #(#("Point_elbowL_dn",50),#("Point_elbowL_up",50)), true, 0, undefined, #(5.05013,2.09415,3.59281), (color 225 143 87), "bone_body", false, false),
	#("Point_elbowR_dn", "Point", "Bip01 R Forearm", "R Forearm", #(1,3.27826e-07,0,-3.22238e-07,1,-1.44821e-07,0,1.64378e-07,1,0,0,0), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(15,true,false,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Point_elbowR_up", "Point", "Bip01 R UpperArm", "R UpperArm", #(1,0,0,0,1,-1.3411e-07,0,1.41561e-07,1,22.416,0,0), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(15,true,false,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Box_elbow_R", "Box", "Bip01 R Forearm", "R Forearm", #(-0.994779,-0.102054,-2.38419e-07,2.98023e-07,-1.27591e-07,-1,-0.102054,0.994779,-1.67638e-07,-7.62939e-06,0,1.52588e-05), "Position_XYZ", undefined, "Orientation_Constraint", #(#("Point_elbowR_up",50),#("Point_elbowR_dn",50)), true, 0, undefined, #(5.05013,2.09415,3.59281), (color 225 143 87), "bone_body", false, false),
	#("Point002", "Point", "Bip01 L UpperArm", "L UpperArm", #(1,0,0,0,1,0,0,0,1,7.97115,0,0), "Position_Expression", [7.97115,-1.43051e-06,1.09139e-11], "Euler_XYZ", #(), false, 0, undefined, #(10,true,false,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Point001", "Point", "Bip01 L Clavicle", "L Clavicle", #(0.918409,0.0424418,-0.393349,-0.0461631,0.998934,0,0.39293,0.0181582,0.919389,9.53674e-07,-2.38419e-07,-4.57764e-05), "Position_XYZ", undefined, "LookAt_Constraint", #(#("Point002",50)), false, 0, #(0,false,false,"Bip01 L Clavicle",1,2,false,2), #(10,false,true,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Point003", "Point", "Bip01 L UpperArm", "L UpperArm", #(1,0,-5.66244e-07,0,0.993176,-0.116624,6.85453e-07,0.116624,0.993176,7.62939e-06,0,1.52588e-05), "Position_XYZ", undefined, "LookAt_Constraint", #(#("Bip01 L ForeTwist",50)), false, 0, #(0,false,false,"Point001",1,2,false,2), #(10,true,true,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Box_ Clavicle_L_01", "Box", "Bip01 L UpperArm", "L UpperArm", #(0.959718,-0.00747181,0.280867,0.0282429,0.997149,-0.0699788,-0.279543,0.0750924,0.957192,7.62939e-06,0,1.52588e-05), "Position_XYZ", undefined, "Orientation_Constraint", #(#("Bip01 L UpperArm",3),#("Point001",7)), false, 0, undefined, #(8,5,5), (color 225 198 87), "bone_body", true, false),
	#("Box_UpperArm_L_002", "Box", "Bip01 L UpperArm", "L UpperArm", #(1,0,-3.8743e-07,0,0.996654,-0.0817314,3.8743e-07,0.0817315,0.996655,2.76956,1.90735e-06,1.52588e-05), "Position_XYZ", undefined, "Orientation_Constraint", #(#("Bip01 L UpperArm",3),#("Point003",7)), false, 0, undefined, #(8,5,5), (color 225 198 87), "bone_body", true, false),
	#("Point005", "Point", "Bip01 R UpperArm", "R UpperArm", #(1,5.66244e-07,-1.19209e-07,-5.43892e-07,1,8.64267e-07,-2.08616e-07,-7.6741e-07,1,7.97112,-1.90735e-06,-1.52588e-05), "Position_Expression", [7.97112,-1.19209e-06,-1.52588e-05], "Euler_XYZ", #(), false, 0, undefined, #(10,true,false,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Point004", "Point", "Bip01 R Clavicle", "R Clavicle", #(0.918408,0.0424416,0.393351,-0.0461629,0.998934,0,-0.392932,-0.0181582,0.919389,9.53674e-07,-2.38419e-07,-1.52588e-05), "Position_XYZ", undefined, "LookAt_Constraint", #(#("Point005",50)), false, 0, #(0,false,false,"Bip01 R Clavicle",1,2,false,2), #(10,false,true,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Point006", "Point", "Bip01 R UpperArm", "R UpperArm", #(1,0,1.19209e-07,0,0.993176,0.116623,-3.27826e-07,-0.116623,0.993177,-1.52588e-05,0,-7.62939e-06), "Position_XYZ", undefined, "LookAt_Constraint", #(#("Bip01 R ForeTwist",50)), false, 0, #(0,false,false,"Point004",1,2,false,2), #(10,true,true,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Box_ Clavicle_R_01", "Box", "Bip01 R UpperArm", "R UpperArm", #(-0.992558,0.00582543,0.121637,-0.00966304,-0.999473,-0.0309839,-0.121392,0.0319286,-0.992091,0.000267029,3.24249e-05,-0.000335693), "Position_XYZ", undefined, "Orientation_Constraint", #(#("Bip01 R UpperArm",7),#("Point004",3)), false, 0, undefined, #(8,5,5), (color 225 198 87), "bone_body", true, false),
	#("Box_UpperArm_L_003", "Box", "Bip01 R UpperArm", "R UpperArm", #(-1,0,0,0,-0.996654,-0.0817313,2.08616e-07,0.0817312,-0.996654,2.76969,3.8147e-05,-0.000175476), "Position_XYZ", undefined, "Orientation_Constraint", #(#("Bip01 R UpperArm",3),#("Point006",7)), false, 0, undefined, #(8,5,5), (color 225 198 87), "bone_body", true, false),
	#("Point_L Calf", "Point", "Bip01 L Calf", "L Calf", #(-1,4.91738e-07,-1.63913e-07,-4.47035e-07,-1,0,-1.71363e-07,0,1,42.7329,-9.676706e-07,-5.80603e-06), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(20,true,true,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("Point_R Calf", "Point", "Bip01 R Calf", "R Calf", #(-1,8.04663e-07,-1.19209e-07,-7.97212e-07,-1,6.35441e-06,-1.3411e-07,6.34883e-06,1,42.7329,-9.676706e-07,0), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(20,true,true,false,false), (color 14 255 2), "Bone_helper", false, false),
	#("B_Calf_L", "BoneGeometry", "Point_L Calf", "L Calf", #(-1,0,4.91738e-07,0,-1,0,5.06639e-07,0,1,42.7329,2.128873e-05,1.354735e-05), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(42.6056,9,9,0,false,false,false), (color 255 200 0), "B_Standard", true, false),
	#("B_Calf_L_Nub", "BoneGeometry", "B_Calf_L", "L Calf", #(1,-4.76837e-07,4.69387e-07,4.84288e-07,1,0,-5.1409e-07,0,1,42.60556,-9.676706e-07,1.935343e-06), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(10.6514,4.5,4.5,0,false,false,false), (color 255 200 0), "B_Standard", true, false),
	#("B_Calf_R", "BoneGeometry", "Point_R Calf", "R Calf", #(-1,-8.49366e-07,-2.38419e-07,8.79169e-07,-1,6.41309e-06,-1.3411e-07,6.46338e-06,1,42.7329,3.580378e-05,3.870687e-06), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(42.6056,9,9,0,false,false,false), (color 255 200 0), "B_Standard", true, false),
	#("B_Calf_R_Nub", "BoneGeometry", "B_Calf_R", "R Calf", #(1,0,0,0,1,2.6729e-07,0,-2.36556e-07,1,42.60556,0,0), "Position_XYZ", undefined, "Euler_XYZ", #(), false, 0, undefined, #(10.6514,4.5,4.5,0,false,false,false), (color 255 200 0), "B_Standard", true, false)
)
global TosRigFol = #(#("B_Vol_Elbow_L", "Box_elbow_L"), #("B_Vol_Clavicle_L_01", "Box_ Clavicle_L_01"), #("B_Vol_UpperArm_L_02", "Box_UpperArm_L_002"), #("B_Vol_Elbow_R", "Box_elbow_R"), #("B_Vol_Clavicle_R_01", "Box_ Clavicle_R_01"), #("B_Vol_UpperArm_R_02", "Box_UpperArm_L_003"), #("B_Vol_Knee_L", "Box_Knee_L"), #("B_Thigh_L", "Bone_L Thigh"), #("B_Vol_Knee_R", "Box_Knee_R"), #("B_Thigh_R", "Bone_R Thigh"))
global TosRigSeg = #(#("L Clavicle", 7.97113), #("L UpperArm", 22.416), #("L Forearm", 24.9245), #("L Thigh", 42.2061), #("L Calf", 42.7329), #("R Clavicle", 7.97113), #("R UpperArm", 22.416), #("R Forearm", 24.9245), #("R Thigh", 42.2061), #("R Calf", 42.7329), #("Spine2", 20.0107), #("Pelvis", 27.641))  -- torso: Ivelar Spine2->Neck, Pelvis->Spine2

-- ======================================================================
--  TOS_RigTools 1.0 (3ds Max 2016) - TOS 프로젝트용 리깅 도구 (MTOS_RigTools 1.0 을 바탕으로, 2026-11-18. MTOS_RigTools 와 한 Max 에 같이 켜도 됨: 전역 이름이 다름 TosRig·trts_·tsbg_·tos_)
--  메뉴: TOS > TOS_RigTools   (또는 Customize > Toolbars > Category "TOS")
--  기준(레퍼런스): 이 PC 의 <루트>\ani\Character\PC 의 직업별 폴더 Ver5_<직업>_<성별> (자동으로 찾음, ini 에 저장)  (파일 이름 archer_f_... = 직업 archer, 여자)
--  TOS 1.0: 2. Biped = 직업_성별 레퍼런스 Biped 그대로 (tos_bip_ref.ms · tos_bip_<직업>_<성별>.fig, archer·cleric·mage·warrior × m·f)
--           3. Twist 보조 본(tos_twist_m·f.ms, MTOS 와 같음) + 여자는 Dummy_Chast (archer_f·cleric_f 레퍼런스와 같은 자리·크기) / 얼굴 본 칸 삭제
--            4. 세컨더리 본 = Cloak(허리·무릎·발, 줄·마디 지정) · Skirt(Skirt_S·Skirt·Skirt_W) · Clavicle 어깨(줄·마디 지정) (tos_secondary.ms · tos_secondary_ref.ms · tos_clavicle_ref.ms)
--  아래는 바탕이 된 TOS_RigTools 의 판 기록
--  필요: MaxBridge.ms (같은 startup 폴더)
--  1.1: Rebuild(갱신) 모드, 템플릿 버전 표식(user prop), 스킨 경고 Y/N, 작업 시간 기록
--  1.5: "1.5 Biped 자동 생성" 단계 추가 (SecBoneGen: Blender 관절 자동 감지 → 노란 지정점 → Biped)
--  1.6: 2.5 Blender 본·스킨 버튼 (Max 버튼 → Blender 자동 실행: 얼굴·가슴·헤어·치마·망토 본, 스킨 적용)
--  1.6: [Biped 생성] 한 번에 관절 자동 감지까지 (Blender 를 띄워 감지, 어느 Max 에서나), [관절 다시 감지] 버튼
--       필요: scripts\TosRig\ (sbg_build.ms · SecBoneGen_v0.11_step1_biped.ms · sbg_fingers.ms)
--  1.8: 치마·긴 코트 웨이트 (u,v) 계산(uv_weights)·겹친 옷 조각은 치마 본으로 (2026-11-01)
--  1.9: 오브젝트 본 구조 종류 모양 규칙(shape_rules.py: 목 둘레·후드·매달린 물건·가닥·앞치마) (2026-11-01)
--  2.0: 헤어 본 좌우 거울 대칭(hair_bones.py _symmetrize·_even_joints, 블렌더 쪽만. Max 는 버전 표시만) (2026-11-01)
--  2.1: 집 확인 — 헤어 간단판 옵션·멜리타 프리셋 옵션·골반 고리 띠 규칙·④ 웨이트 기록(블렌더 새로 켠 뒤 스킨 적용) (블렌더 쪽만. Max 는 버전 표시만) (2026-11-01)
--  2.2: 블렌더 헤어 패널 — 갈래·마디·코스튬 선택 미리보기·반영·되돌리기, 헤어 본 박스 모양 (블렌더 쪽만. Max 는 버전 표시만) (2026-11-01)
--  1.61: Fix Tools(ClaudeFixTools)·MeshFix(ClaudeMeshFix) 를 리그툴 묶음에서 빼서 QATool 로 분리 (2026-11-02)
--  1.61 (2026-11-02): 5번 칸 [헤어 본 만들기] 아래 갈래 버튼 [기본 (메시대로)][간단 (뒤 3갈래)] (블렌더 헤어 패널 갈래와 같음, 누르면 바로 다시 만들어 Max 에). 작업에 "branch" (ge_jobs.step_hair, hair_bones MSR_OT_hair_generate.branch)
--  1.61 (2026-11-02): 2.8 을 1.61 로 이름 바꿈 + 헤어 본 상자 굵기(좌우 거울·납작함 제한·상한 3) (블렌더 쪽만. Max 는 버전 표시만)
--  1.61: 5번 칸 [세컨더리 본 만들기] 아래 파츠 본 범위 버튼 1·2·3 (블렌더 패널과 같음), [세컨더리 본 만들기] = 범위 3 (전부, 예전 방식) (rts_blender.ms trts_partAutoStart lev:, ge_jobs.py job level)
--  2.8: 치마 밑단보다 한참 아래로 내려가는 다리 옷 조각은 치마 묶음에서 뺌(세레나) (블렌더 쪽만. Max 는 버전 표시만) (2026-11-02)
--  2.7: 치마 본 굵기 고르게·범위 2 에서 0개면 3 으로·실패 표시·블렌더 실행기 작업자/Claude 나눔(rts_blender.ms trts_blAge) (2026-11-02)
--  2.6: 옛 판 ④ 웨이트 기록을 새 판정 위에 다시 쓰지 않게 (블렌더 쪽만. Max 는 버전 표시만) (2026-11-01)
--  2.5: 치마 안쪽 층(안감·속치마) 판정·헤어 되돌리기 주인 확인·초기화·골반 고리 오류 고침 (블렌더 쪽만. Max 는 버전 표시만) (2026-11-01)
--  2.4: 파츠 본 생성 범위 1/2/3(기본 2)·양면 천 선택한 면·소매 판정 고침 (블렌더 쪽만. Max 는 버전 표시만) (2026-11-01)
--  2.3: 지운 파트 본 웨이트 수정(수정안 A, 남은 본 100% 대신 몸 웨이트)·블렌더 헤어 '고급' 칸 숨김 (블렌더 쪽만. Max 는 버전 표시만) (2026-11-01)
--  1.72: 스킨 적용 경계 섞기·손질 유지·멜리타 스카프·파츠 부모·치마 대칭·손 옆 치마·교환 파일 포트별 (2026-11-01)
--  1.71: 팔뚝 트위스트 25/75(rig_standard), 템플릿 이름에서 이벨라 빼기(rig_standard·limb_helpers), 멜리타 바디 템플릿 01 판 (2026-10-31)
--  1.7: 블렌더 멜리타 자동 = 위치로 짝짓기·미리보기 = 만든 본, INSTALL_ALL·UPDATE (Max 쪽 기능은 1.6 과 같음)
-- ======================================================================
global TosRigTplVer = "1.0"
global TosRigTplId = "limb_helpers"
global TosRigTL = #(0, "", "", "")
global TosRigBad = #()
global TosRig
global TosRigRoll
global trts_sbgBuild, trts_sbgDetect, trts_sbgEditStart, trts_sbgEditDone, trts_blStart
global trts_partAdd, trts_partDel, trts_partShow, trts_partClear, trts_partItems, trts_partInfo
-- 결과 글상자 글자색: 보통 = 밝은 회색, 알림 = 노랑 (10/30)
global trts_logColor
fn trts_logColor warn = ( local C = dotNetClass "System.Drawing.Color"; if warn then C.FromArgb 255 220 40 else C.FromArgb 225 225 225 )
global trts_rigDone, trts_tplDir, trts_skinOff, trts_skinIsOff
global trts_partMaxFix, trts_pmEditing, trts_partAutoStart, trts_obDeleteAll, trts_obItems, trts_obPick, trts_obPickFaces, trts_obDeletePart, trts_obRootExtra, trts_obCenterToggle, trts_obCenterSet, trts_obMagicaState
struct TosRigStruct
(
	version = "1.0",
	segNext = #(#("Clavicle","UpperArm"), #("UpperArm","Forearm"), #("Forearm","Hand"), #("Thigh","Calf"), #("Calf","Foot"), #("Spine2","Neck"), #("Pelvis","Spine2")),

	fn bipPrefix = (local r = for o in objects where classOf o == Biped_Object and o.parent == undefined collect o; if r.count > 0 then r[1].name else undefined),

	fn segLen pre part =
	(
		local ps = filterString part " ", last = ps[ps.count], nxt = undefined
		for s in segNext where s[1] == last do nxt = s[2]
		if nxt == undefined then 0.0 else
		(
			local side = if ps.count > 1 then (ps[1] + " ") else ""
			local a = getNodeByName (pre + " " + part) exact:true, b = getNodeByName (pre + " " + side + nxt) exact:true
			if a == undefined or b == undefined then 0.0 else distance a.transform.row4 b.transform.row4
		)
	),

	fn tplNames = (for e in TosRigTpl collect e[1]),
	fn mapName n pre names = (if n == "-" or (findItem names n) > 0 then n else (if matchPattern n pattern:"Bip01*" then (pre + (substring n 6 -1)) else n)),
	fn resNode n =
	(
		local o = getNodeByName n exact:true
		if o == undefined do o = getNodeByName (substituteString (substituteString n "ForeTwist" "Forearm") "CalfTwist" "Calf") exact:true
		o
	),
	fn getLayer n = (local l = LayerManager.getLayerFromName n; if l == undefined do l = LayerManager.newLayerFromName n; l),
	fn ratioOf part parts ratios = (local i = findItem parts part; if i == 0 then 1.0 else ratios[i]),

	-- 마디 비율 (대상 Biped / 표준). segs: 템플릿에 저장된 표준 캐릭터 마디 길이 (없으면 이벨라 기본값)
	fn calcRatios pre segs:undefined =
	(
		local parts = #(), ratios = #()
		local src = if segs != undefined and segs.count > 0 then segs else TosRigSeg
		for s in src do
		(
			local cur = segLen pre s[1]
			append parts s[1]
			append ratios (if s[2] > 0.0001 and cur > 0.0001 then cur / s[2] else 1.0)
		)
		#(parts, ratios)
	),

	-- 템플릿이 원하는 월드 트랜스폼
	fn wantTM e par r =
	(
		local m = e[5]
		(matrix3 [m[1],m[2],m[3]] [m[4],m[5],m[6]] [m[7],m[8],m[9]] ([m[10],m[11],m[12]] * r)) * par.transform
	),

	fn rotDiffDeg tmA tmB =
	(
		local a = tmA.rotation, b = tmB.rotation
		local d = abs (a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w)
		if d > 1.0 do d = 1.0
		2.0 * (acos d)
	),

	-- 템플릿 버전 표식 (파일 안에서 어떤 템플릿으로 만들었는지 알 수 있게)
	fn stamp o r =
	(
		setUserProp o "RigTools_tpl" (TosRigTplId + "@" + TosRigTplVer)
		setUserProp o "RigTools_ver" version
		setUserProp o "RigTools_ratio" (formattedPrint r format:".4f")
	),

	-- 위치 표현식·방향/룩앳 컨스트레인트 설정
	fn applyCtrl e o r pre names =
	(
		if e[6] == "Position_Expression" and e[7] != undefined do
		(
			local v = e[7] * r, pe = Position_Expression()
			pe.setExpression ("[" + (v.x as string) + ", " + (v.y as string) + ", " + (v.z as string) + "]")
			o.position.controller = pe
		)
		if e[8] == "Orientation_Constraint" or e[8] == "LookAt_Constraint" do
		(
			local tg = for t in e[9] where t[1] != "-" collect #(resNode (mapName t[1] pre names), t[2])
			tg = for t in tg where t[1] != undefined collect t
			local ws = 0.0
			for t in tg do ws += t[2]
			if ws > 0 do
			(
				if e[8] == "Orientation_Constraint" then
				(
					local c = Orientation_Constraint()
					o.rotation.controller = c
					for t in tg do c.appendTarget t[1] t[2]
					c.local_world = e[11]
					c.relative = e[10]
				)
				else
				(
					local la = e[12], c = LookAt_Constraint()
					o.rotation.controller = c
					for t in tg do c.appendTarget t[1] t[2]
					c.target_axis = la[1]
					try (c.target_axisFlip = la[2]) catch ()
					c.upnode_world = la[3]
					if (not la[3]) and la[4] != "-" do c.pickUpNode = resNode (mapName la[4] pre names)
					c.upnode_ctrl = la[5]
					c.StoUP_axis = la[6]
					try (c.StoUP_axisFlip = la[7]) catch ()
					c.upnode_axis = la[8]
					c.relative = e[10]
				)
			)
		)
	),

	-- 표준 헬퍼·보조 본 생성 (이미 있는 이름은 건너뜀, Ctrl+Z 한 번으로 되돌림)
	fn addHelpers =
	(
		local pre = bipPrefix()
		if pre == undefined do return "오류: 장면에 Biped가 없어요."
		if (getNodeByName (pre + " L Thigh") exact:true) == undefined do return ("오류: " + pre + " L Thigh 를 찾을 수 없어요.")
		local names = tplNames()
		local rr = calcRatios pre
		local parts = rr[1], ratios = rr[2], log = ""
		for i = 1 to parts.count do log += parts[i] + "=" + (formattedPrint ratios[i] format:".2f") + "  "
		log = "마디 비율(대상/이벨라): " + log + "\n"
		local made = #(), skipped = #()
		sliderTime = 0
		undo "TOS_RigTools Helpers" on
		(
			-- 1) 노드 생성 (부모 먼저)
			for e in TosRigTpl do
			(
				if (getNodeByName e[1] exact:true) != undefined then append skipped e[1]
				else
				(
					local par = getNodeByName (mapName e[3] pre names) exact:true
					if par == undefined then append skipped (e[1] + "(부모 없음)")
					else
					(
						local r = ratioOf e[4] parts ratios
						local d = e[13], o = undefined
						case e[2] of
						(
							"Point": o = Point size:(d[1] * r) cross:d[2] box:d[3] axistripod:d[4] centermarker:d[5]
							"Box": o = Box length:(d[1] * r) width:(d[2] * r) height:(d[3] * r)
							"BoneGeometry": (o = BoneSys.createBone [0,0,0] [d[1] * r, 0, 0] [0,0,1]; o.width = d[2] * r; o.height = d[3] * r; o.taper = d[4]; o.sidefins = d[5]; o.frontfin = d[6]; o.backfin = d[7])
							default: o = Dummy()
						)
						o.name = e[1]
						o.wirecolor = e[14]
						o.renderable = e[17]
						(getLayer e[15]).addNode o
						o.parent = par
						o.transform = wantTM e par r
						o.boneEnable = e[16]
						stamp o r
						append made o
					)
				)
			)
			-- 2) 컨스트레인트 (모든 노드가 생긴 뒤)
			for e in TosRigTpl do
			(
				local o = getNodeByName e[1] exact:true
				if o != undefined and (findItem made o) > 0 do applyCtrl e o (ratioOf e[4] parts ratios) pre names
			)
			-- 3) 스킨용 B_ 팔로워 본 (+Nub)
			local fol = 0
			for f in TosRigFol where (getNodeByName f[1] exact:true) == undefined and (getNodeByName f[2] exact:true) != undefined do
			(
				MaxBridge.makeFollower f[2] f[1]
				local b = getNodeByName f[1] exact:true
				if b != undefined do stamp b 1.0
				if b != undefined and classOf b == BoneGeometry and b.children.count == 0 do
				(
					local sg = MaxBridge.boneSeg b, dd = normalize (sg[2] - sg[1])
					local nb = BoneSys.createBone sg[2] (sg[2] + dd * (amax #(b.length * 0.25, 0.2))) (normalize b.transform.row3)
					nb.name = b.name + "_Nub"; nb.width = b.width * 0.5; nb.height = b.height * 0.5; nb.parent = b; nb.wirecolor = b.wirecolor
					(getLayer "B_Standard").addNode nb
				)
				fol += 1
			)
			log += "생성: 헬퍼·보조 본 " + (made.count as string) + "개, 스킨용 B_ 본 " + (fol as string) + "개\n"
		)
		if skipped.count > 0 do log += "건너뜀(이미 있음 등) " + (skipped.count as string) + "개: " + (skipped as string) + "\n"
		completeRedraw()
		log
	),

	-- ================== Rebuild (갱신) ==================
	fn skinMeshes = (for o in geometry where (for m in o.modifiers where classOf m == Skin collect m).count > 0 collect o),

	-- 현재 파일의 템플릿 노드와 새 템플릿 값을 비교 (읽기 전용)
	-- 결과: #(위치·크기 변경 목록, 컨스트레인트 변경 목록, 없는 노드, 변경 없음 개수)
	fn planRebuild pre names parts ratios =
	(
		local geo = #(), ctl = #(), missing = #(), same = 0
		for e in TosRigTpl do
		(
			local o = getNodeByName e[1] exact:true
			if o == undefined then append missing e[1]
			else
			(
				local par = getNodeByName (mapName e[3] pre names) exact:true
				if par == undefined then append missing (e[1] + "(부모 없음)")
				else
				(
					local r = ratioOf e[4] parts ratios
					local want = wantTM e par r
					local gw = "", cw = ""
					local dp = distance o.transform.row4 want.row4
					if dp > 0.01 do gw += "위치 " + (formattedPrint dp format:".3f") + "  "
					if e[8] == "Euler_XYZ" do
					(
						local da = rotDiffDeg o.transform want
						if da > 0.05 do gw += "회전 " + (formattedPrint da format:".2f") + "도  "
					)
					local d = e[13]
					case e[2] of
					(
						"Point": if (abs (o.size - d[1] * r)) > 0.01 do gw += "크기  "
						"Box": if (abs (o.length - d[1] * r)) > 0.01 or (abs (o.width - d[2] * r)) > 0.01 or (abs (o.height - d[3] * r)) > 0.01 do gw += "크기  "
						"BoneGeometry": if (abs (o.length - d[1] * r)) > 0.01 or (abs (o.width - d[2] * r)) > 0.01 or (abs (o.height - d[3] * r)) > 0.01 do gw += "크기  "
					)
					if e[6] == "Position_Expression" and e[7] != undefined and classOf o.position.controller != Position_Expression do cw += "위치 표현식 없음  "
					if e[8] == "Orientation_Constraint" or e[8] == "LookAt_Constraint" do
					(
						local tg = for t in e[9] where t[1] != "-" collect #(resNode (mapName t[1] pre names), t[2])
						tg = for t in tg where t[1] != undefined collect t
						local ws = 0.0
						for t in tg do ws += t[2]
						if ws > 0 do
						(
							local c = o.rotation.controller
							local wantCls = (if e[8] == "Orientation_Constraint" then Orientation_Constraint else LookAt_Constraint)
							if classOf c != wantCls then cw += "컨스트레인트 종류  "
							else
							(
								-- 삭제돼서 비어 있는 타깃(undefined)은 무시하고 살아 있는 타깃만 비교
								local live = #()
								for i = 1 to c.getNumTargets() do (local nd = c.getNode i; if nd != undefined do append live #(nd, c.getWeight i))
								if live.count != tg.count then cw += "타깃 수  "
								else for i = 1 to tg.count where live[i][1] != tg[i][1] or (abs (live[i][2] - tg[i][2])) > 0.01 do cw += "타깃/가중치(" + (i as string) + ")  "
							)
						)
					)
					if gw != "" then append geo #(e[1], gw)
					if cw != "" then append ctl #(e[1], cw)
					if gw == "" and cw == "" do same += 1
				)
			)
		)
		#(geo, ctl, missing, same)
	),

	-- 파일에 남은 표식 노드 중 템플릿에 없는 것 (지우지 않고 알려주기만)
	fn findOrphans =
	(
		local names = tplNames()
		local fnames = for f in TosRigFol collect f[1]
		local res = #()
		for o in objects where (getUserProp o "RigTools_tpl") != undefined and (findItem names o.name) == 0 and (findItem fnames o.name) == 0 and not (matchPattern o.name pattern:"*_Nub") do append res o.name
		res
	),

	fn stampInfo =
	(
		local ids = #(), cnt = #()
		for e in TosRigTpl do
		(
			local o = getNodeByName e[1] exact:true
			if o != undefined do
			(
				local v = getUserProp o "RigTools_tpl"
				if v == undefined do v = "표식 없음(이전 버전)"
				local i = findItem ids v
				if i == 0 then (append ids v; append cnt 1) else cnt[i] += 1
			)
		)
		local s = ""
		for i = 1 to ids.count do s += ids[i] + " x" + (cnt[i] as string) + "  "
		if s == "" then "(템플릿 노드 없음)" else s
	),

	fn listText arr cap =
	(
		local s = ""
		for i = 1 to (amin #(arr.count, cap)) do s += "  " + arr[i][1] + ": " + arr[i][2] + "\n"
		if arr.count > cap do s += "  ... 외 " + ((arr.count - cap) as string) + "개\n"
		s
	),

	-- dryRun:true  → 바뀔 내용만 보여줌 (아무것도 안 바꿈)
	-- dryRun:false → 적용. 스킨이 있고 변형에 영향 줄 변경이 있으면 Y/N 확인 (Y = 허용)
	-- safeOnly:true → 위치·크기는 건드리지 않고 컨스트레인트·표식·누락 노드만
	-- autoYes:true  → 확인창 생략 (자동 테스트용)
	fn rebuild dryRun:true safeOnly:false autoYes:false =
	(
		local pre = bipPrefix()
		if pre == undefined do return "오류: 장면에 Biped가 없어요."
		if (getNodeByName (pre + " L Thigh") exact:true) == undefined do return ("오류: " + pre + " L Thigh 를 찾을 수 없어요.")
		local names = tplNames()
		local rr = calcRatios pre
		local parts = rr[1], ratios = rr[2]
		local pl = (at time 0 (planRebuild pre names parts ratios))
		local geo = pl[1], ctl = pl[2], missing = pl[3], same = pl[4]
		local skins = skinMeshes()
		local orph = findOrphans()
		local log = "[Rebuild " + (if dryRun then "미리보기" else "적용") + "] 템플릿 " + TosRigTplId + "@" + TosRigTplVer + " / 도구 " + version + "\n"
		log += "파일 표식: " + (stampInfo()) + "\n"
		log += "변경 없음 " + (same as string) + " / 위치·크기 " + (geo.count as string) + " / 컨스트레인트 " + (ctl.count as string) + " / 새로 추가 " + (missing.count as string) + "\n"
		if geo.count > 0 do log += "위치·크기 변경" + (if safeOnly then " (안전 모드: 건너뜀)" else " (스킨 영향 가능)") + ":\n" + (listText geo 12)
		if ctl.count > 0 do log += "컨스트레인트 변경:\n" + (listText ctl 12)
		if missing.count > 0 do log += "추가될 노드: " + (missing as string) + "\n"
		if orph.count > 0 do log += "템플릿에 없는 표식 노드(지우지 않음): " + (orph as string) + "\n"
		if skins.count > 0 do log += "스킨 메쉬 " + (skins.count as string) + "개 있음 → 적용 시 Y/N 확인\n"
		if dryRun do return log

		local applyGeo = (not safeOnly) and geo.count > 0
		local risky = ctl.count
		if applyGeo do risky += geo.count
		if skins.count > 0 and risky > 0 and not autoYes do
		(
			local msg = "스킨이 붙은 메쉬가 " + (skins.count as string) + "개 있어요.\n"
			msg += "위치·크기 변경 " + ((if applyGeo then geo.count else 0) as string) + "개, 컨스트레인트 변경 " + (ctl.count as string) + "개를 적용하면 변형 결과가 달라질 수 있어요.\n\n"
			msg += "한 번 더 진행할까요?\n(Y = 허용하고 적용 / N = 취소, 변경 없음)"
			if not (queryBox msg title:"Rig Tools - 스킨 경고" beep:true) do return (log + "\n취소했어요. (변경 없음)")
		)

		local geoNames = for g in geo collect g[1]
		local ctlNames = for c in ctl collect c[1]
		local stamped = 0, addLog = ""
		sliderTime = 0
		undo "TOS_RigTools Rebuild" on
		(
			for e in TosRigTpl do
			(
				local o = getNodeByName e[1] exact:true
				local par = getNodeByName (mapName e[3] pre names) exact:true
				if o != undefined and par != undefined do
				(
					local r = ratioOf e[4] parts ratios
					local inGeo = applyGeo and (findItem geoNames e[1]) > 0
					if inGeo do
					(
						local want = wantTM e par r
						local d = e[13]
						local rc = classOf o.rotation.controller
						local isCon = (rc == Orientation_Constraint or rc == LookAt_Constraint)
						try (if isCon then o.pos = want.row4 else o.transform = want) catch ()
						case e[2] of
						(
							"Point": o.size = d[1] * r
							"Box": (o.length = d[1] * r; o.width = d[2] * r; o.height = d[3] * r)
							"BoneGeometry": (o.length = d[1] * r; o.width = d[2] * r; o.height = d[3] * r)
						)
					)
					if (findItem ctlNames e[1]) > 0 or (inGeo and e[6] == "Position_Expression") do applyCtrl e o r pre names
					stamp o r
					stamped += 1
				)
			)
			for f in TosRigFol do
			(
				local b = getNodeByName f[1] exact:true
				if b != undefined do stamp b 1.0
			)
			if missing.count > 0 do addLog = addHelpers()
		)
		completeRedraw()
		local pl2 = (at time 0 (planRebuild pre names parts ratios))
		log += "\n적용: 표식 " + (stamped as string) + "개"
		if applyGeo then log += ", 위치·크기 " + (geo.count as string) + "개" else if geo.count > 0 do log += ", 위치·크기 " + (geo.count as string) + "개는 건너뜀"
		log += ", 컨스트레인트 " + (ctl.count as string) + "개 (Ctrl+Z로 되돌림)\n"
		log += "재검사: 위치·크기 남음 " + (pl2[1].count as string) + " / 컨스트레인트 남음 " + (pl2[2].count as string) + "\n"
		if addLog != "" do log += addLog
		log
	),

	-- ================== 모델링 체크 (1.2) ==================
	-- 심각도: 3 = ERROR, 2 = WARN, 1 = INFO
	fn isCheckMesh o =
	(
		if superClassOf o != GeometryClass then false
		else if (classOf o) == BoneGeometry or (classOf o) == Biped_Object then false
		else if (matchPattern o.name pattern:"Footsteps*") then false
		else if (getUserProp o "RigTools_tpl") != undefined then false
		else if (classOf o) == Box and (matchPattern o.name pattern:"Box*") then false
		else if not (canConvertTo o TriMeshGeometry) then false
		else true
	),

	fn checkMeshNode o =
	(
		local iss = #()
		-- 변환: 미러(음수 스케일) / 스케일 / 회전
		local tm = o.transform
		if (dot (cross tm.row1 tm.row2) tm.row3) < 0 do append iss #(3, "미러(음수 스케일) 변환 - 변환 리셋 또는 Flip 필요")
		local sc = o.scale
		if (abs (sc.x - 1.0)) > 0.001 or (abs (sc.y - 1.0)) > 0.001 or (abs (sc.z - 1.0)) > 0.001 do append iss #(2, "스케일이 100%가 아님 " + (sc as string))
		-- 모디파이어 히스토리 (Skin 제외)
		local mods = for m in o.modifiers where (classOf m) != Skin collect ((classOf m) as string)
		if mods.count > 0 do append iss #(2, "스킨 외 모디파이어 남아 있음: " + (mods as string))
		-- 재질 유무
		local mat = o.material
		-- 메쉬 분석
		local m = at time 0 (snapshotAsMesh o)
		local nf = m.numfaces, nv = m.numverts
		if nf == 0 then append iss #(3, "면이 없음")
		else if nf > 300000 then append iss #(1, "면 " + (nf as string) + "개 - 너무 커서 상세 검사 생략")
		else
		(
			-- 맵 채널
			local chans = #()
			for c = 0 to ((meshop.getNumMaps m) - 1) where (meshop.getMapSupport m c) do append chans c
			local hasUV = (findItem chans 1) > 0
			if not hasUV do append iss #(3, "UV(맵 채널 1) 없음")
			if (findItem chans 0) == 0 do append iss #(2, "맵 채널 0 없음 (LMA 추출 실패했던 메쉬가 이 구성 - 추정)")
			local extra = for c in chans where c >= 2 collect c
			if extra.count > 0 do append iss #(2, "맵 채널 2 이상 있음 " + (extra as string) + " (LMA가 섀도맵 UV로 취급할 수 있음 - 추정)")
			-- 면 단위 루프 (면적 0, UV 면적 0, 재질 ID, 엣지 키, 부피)
			local eKey = (nv + 1) as double
			local und = #(), dir = #()
			und.count = nf * 3
			dir.count = nf * 3
			local k = 0, zeroArea = 0, zeroUV = 0, idb = #{}, vol = 0.0
			for i = 1 to nf do
			(
				local f = getFace m i
				local a = f.x as integer, b = f.y as integer, c = f.z as integer
				k += 1; dir[k] = a * eKey + b; und[k] = (if a < b then (a * eKey + b) else (b * eKey + a))
				k += 1; dir[k] = b * eKey + c; und[k] = (if b < c then (b * eKey + c) else (c * eKey + b))
				k += 1; dir[k] = c * eKey + a; und[k] = (if c < a then (c * eKey + a) else (a * eKey + c))
				if (meshop.getFaceArea m i) < 0.000001 do zeroArea += 1
				local mid = getFaceMatID m i
				if mid > 0 and mid < 100000 do idb[mid] = true
				local pa = getVert m a, pb = getVert m b, pc = getVert m c
				vol += (dot pa (cross pb pc)) / 6.0
				if hasUV do
				(
					local uf = meshop.getMapFace m 1 i
					local ua = meshop.getMapVert m 1 (uf.x as integer), ub = meshop.getMapVert m 1 (uf.y as integer), uc = meshop.getMapVert m 1 (uf.z as integer)
					if (abs (((ub.x - ua.x) * (uc.y - ua.y)) - ((uc.x - ua.x) * (ub.y - ua.y)))) < 0.0000001 do zeroUV += 1
				)
			)
			if zeroArea > 0 do append iss #(2, "면적 0인 면 " + (zeroArea as string) + "개")
			if zeroUV > 0 do append iss #(2, "UV 면적 0인 면(빈 UV) " + (zeroUV as string) + "개")
			-- 재질 ID
			local idl = for i in idb collect i
			if mat == undefined then append iss #(2, "재질 없음")
			else if (classOf mat) == Multimaterial then
			(
				local have = try (mat.materialIDList) catch (#())
				local bad = for i in idl where (findItem have i) == 0 collect i
				if bad.count > 0 do append iss #(3, "재질 ID " + (bad as string) + " 에 해당하는 서브 재질 없음")
			)
			else
			(
				local bad = for i in idl where i != 1 collect i
				if bad.count > 0 do append iss #(2, "단일 재질인데 면 재질 ID가 1 외 사용: " + (idl as string) + " (LMA 추출 실패했던 구성 - 추정)")
			)
			-- 엣지: 열린 / 비다양체 / 방향 불일치
			sort und
			sort dir
			local n = und.count, i = 1, openE = 0, nonMan = 0
			while i <= n do
			(
				local j = i
				while j < n and und[j + 1] == und[i] do j += 1
				local cnt = j - i + 1
				if cnt == 1 then openE += 1 else if cnt > 2 do nonMan += 1
				i = j + 1
			)
			local flip = 0
			for q = 2 to n where dir[q] == dir[q - 1] do flip += 1
			if nonMan > 0 do append iss #(2, "비다양체 엣지(면 3개 이상 공유) " + (nonMan as string) + "개")
			if flip > 0 do append iss #(2, "방향 불일치 엣지 " + (flip as string) + "개 (뒤집힌 면 섞임 의심, 비다양체 포함)")
			if openE > 0 do append iss #(1, "열린 엣지 " + (openE as string) + "개 (옷·머리카락 같은 열린 메쉬면 정상)")
			if openE == 0 and nonMan == 0 and flip == 0 and vol < 0.0 do append iss #(2, "닫힌 메쉬인데 부피가 음수 - 전체가 뒤집혔을 수 있음")
			-- 고립 정점 / 겹친 정점 (마지막: 스냅샷 복사본을 건드림)
			local iso = (meshop.getIsoVerts m).numberSet
			if iso > 0 do append iss #(2, "고립 정점 " + (iso as string) + "개")
			local nv0 = m.numverts
			meshop.weldVertsByThreshold m #{1..nv0} 0.0001
			local dup = nv0 - m.numverts
			if dup > 0 do append iss #(2, "겹친 정점 " + (dup as string) + "개 (붙어 있지 않은 조각 경계일 수 있음)")
		)
		iss
	),

	fn modelCheck selOnly:false =
	(
		local t0 = timeStamp()
		local cand = for o in (if selOnly then selection else objects) where (isCheckMesh o) collect o
		if cand.count == 0 do return "검사할 메쉬가 없어요."
		local lines = #(), bad = #(), clean = 0, nE = 0, nW = 0, nI = 0
		-- 이름 중복 (장면 전체)
		local nms = for o in objects collect o.name
		sort nms
		local dups = #()
		for i = 2 to nms.count where nms[i] == nms[i - 1] and (findItem dups nms[i]) == 0 do append dups nms[i]
		if dups.count > 0 do
		(
			append lines ("[ERROR] 장면: 이름 중복 " + (dups.count as string) + "개 - " + ((for i = 1 to (amin #(dups.count, 10)) collect dups[i]) as string))
			nE += 1
		)
		for o in cand do
		(
			local ts = timeStamp()
			local iss = try (checkMeshNode o) catch (#(#(3, "검사 중 오류: " + getCurrentException())))
			local ms = timeStamp() - ts
			if iss.count == 0 then clean += 1
			else
			(
				local worst = 0
				for x in iss do (if x[1] > worst do worst = x[1]; if x[1] == 3 then nE += 1 else if x[1] == 2 then nW += 1 else nI += 1)
				if worst >= 2 do append bad o.name
				append lines (o.name + " (" + (ms as string) + "ms)")
				for x in iss do
				(
					local sv = (if x[1] == 3 then "ERROR" else if x[1] == 2 then "WARN" else "INFO")
					append lines ("  [" + sv + "] " + x[2])
				)
			)
		)
		TosRigBad = bad
		local head = (if nE == 0 then "▶ 치명적 오류(ERROR) 없음 → 리깅 가능\n" else "▶ 치명적 오류(ERROR) " + (nE as string) + "개 → 수정 후 리깅\n")
		head += "[모델링 검사] 메쉬 " + (cand.count as string) + "개 / 문제 없음 " + (clean as string) + "개\n"
		head += "ERROR " + (nE as string) + " / WARN " + (nW as string) + " / INFO " + (nI as string) + "  (" + (formattedPrint ((timeStamp() - t0) / 1000.0) format:".1f") + "초)\n"
		local full = head + "씬: " + maxFileName + "\n"
		for l in lines do full += l + "\n"
		full += "\n검사 안 하는 항목: 겹친 UV(섀도·텍스처 겹침), 비다양체 정점. 위 '추정' 표시는 과거 LMA 추출 실패 사례에서 온 규칙이라 엔진 기준 확인 필요.\n"
		local rp = (if doesFileExist "C:\\claude\\max_blender" then "C:\\claude\\max_blender" else (getDir #export)) + "\\modelcheck_" + (if maxFileName != "" then (getFilenameFile maxFileName) else "scene") + ".txt"
		try ((dotNetClass "System.IO.File").WriteAllText rp full (dotNetObject "System.Text.UTF8Encoding" true)) catch (rp = "(저장 실패)")
		local shortTxt = head
		local cap = amin #(lines.count, 40)
		for i = 1 to cap do shortTxt += lines[i] + "\n"
		if lines.count > cap do shortTxt += "... 외 " + ((lines.count - cap) as string) + "줄\n"
		shortTxt += "전체 리포트: " + rp
		shortTxt
	),

	fn selectBad =
	(
		local ns = for n in TosRigBad where (getNodeByName n exact:true) != undefined collect (getNodeByName n exact:true)
		if ns.count == 0 then "선택할 문제 메쉬가 없어요. 먼저 모델링 검사를 실행하세요."
		else (select ns; "문제 메쉬 " + (ns.count as string) + "개 선택함")
	),

	-- 리깅 전 체크: 모델링 오브젝트 위치 0(피벗 = 원점) + Reset XForm + Editable Mesh 변환
	-- removeSkin:true 이면 Skin도 지우고 원래 메쉬 모양(바인드 포즈)으로 초기화, false 이면 Skin 메쉬는 건너뜀
	fn skinnedCount selOnly:false =
	(
		local n = 0
		for o in (if selOnly then selection else objects) where (isCheckMesh o) and (for m in o.modifiers where (classOf m) == Skin collect m).count > 0 do n += 1
		n
	),
	-- 키 확인·삭제 (Biped 애니 전체 + 다른 노드의 모든 키. 구속·와이어·스크립트 컨트롤러 연결은 그대로)
	fn isBipCtrl c = (local k = classOf c; k == Vertical_Horizontal_Turn or k == BipSlave_Control or k == Footsteps),
	fn subKeyCount sa =
	(
		local n = 0
		local c = try (sa.controller) catch undefined
		if c != undefined and not (isBipCtrl c) do (local k = try (numKeys c) catch 0; if k > 0 do n += k)
		for i = 1 to sa.numSubs do n += subKeyCount sa[i]
		n
	),
	fn subKeyClear sa =
	(
		local c = try (sa.controller) catch undefined
		if c != undefined and not (isBipCtrl c) and (try (numKeys c) catch 0) > 0 do try (deleteKeys c #allKeys) catch ()
		for i = 1 to sa.numSubs do subKeyClear sa[i]
		ok
	),
	fn nodeKeyCount o = (local n = 0; for i = 1 to o.numSubs do n += subKeyCount o[i]; n),
	fn keyInfo =
	(
		local bk = 0
		for o in objects where classOf o == Biped_Object do bk += amax 0 (try (o.controller.keys.count) catch 0)
		local nodes = for o in objects where classOf o != Biped_Object and (nodeKeyCount o) > 0 collect o
		#(bk, nodes)
	),
	fn clearKeys =
	(
		for b in (for o in objects where classOf o == Biped_Object and o.parent == undefined collect o) do
		(
			local c = b.controller, fm = c.figureMode
			if fm do c.figureMode = false
			try (biped.clearAllAnimation c) catch ()
			if fm do c.figureMode = true
		)
		local nodes = for o in objects where classOf o != Biped_Object and (nodeKeyCount o) > 0 collect o
		for o in nodes do for i = 1 to o.numSubs do subKeyClear o[i]
		nodes.count
	),
	fn bipNeed = (local need = false; for b in objects where classOf b == Biped_Object and b.parent == undefined do (local c = b.controller; if c.trianglePelvis or not c.triangleNeck do need = true); need),
	-- Biped 구조 설정: 피규어 모드 켬, Triangle Pelvis 끔, Triangle Neck 켬
	fn bipSetup =
	(
		local roots = for o in objects where classOf o == Biped_Object and o.parent == undefined collect o
		if roots.count == 0 do return #("- Biped 없음\n", false)
		local need = bipNeed()
		local r = ""
		for b in roots do
		(
			local c = b.controller
			local fm = c.figureMode, tp = c.trianglePelvis, tn = c.triangleNeck
			if not fm do c.figureMode = true
			if tp do c.trianglePelvis = false
			if not tn do c.triangleNeck = true
			r += "- " + b.name + ": 피규어 모드 " + (if fm then "켜짐(그대로)" else "꺼짐→켬") + " | Triangle Pelvis " + (if tp then "켜짐→끔" else "꺼짐(그대로)") + " | Triangle Neck " + (if tn then "켜짐(그대로)" else "꺼짐→켬") + "\n"
			if c.trianglePelvis or not c.triangleNeck do r += "  주의: 설정이 바뀌지 않았어요 (Pelvis " + (c.trianglePelvis as string) + " / Neck " + (c.triangleNeck as string) + ")\n"
		)
		#(r, need)
	),
	fn preRigFix selOnly:false removeSkin:true removeKeys:false =
	(
		local ki = keyInfo()
		local hasKeys = ki[1] > 0 or ki[2].count > 0
		local doKeys = removeKeys and hasKeys
		local held = false
		if doKeys or (bipNeed()) do (holdMaxFile(); held = true)
		local kl = ""
		if doKeys then (local n = try (clearKeys()) catch -1; kl = "- 키 삭제: Biped 키 " + (ki[1] as string) + "개 + 다른 노드 " + (n as string) + "개 (메쉬 포함)\n"; local k2 = keyInfo(); if k2[1] > 0 or k2[2].count > 0 do kl += "  주의: 남은 키 Biped " + (k2[1] as string) + " / 노드 " + (k2[2].count as string) + "\n")
		else if hasKeys do kl = "- 키 남김: Biped 키 " + (ki[1] as string) + "개, 키 있는 노드 " + (ki[2].count as string) + "개\n"
		local bs = try (bipSetup()) catch (#("- Biped 설정 오류: " + getCurrentException() + "\n", false))
		bs[1] = kl + bs[1]
		local fetchNote = "Biped 키·구조를 바꿔서 Ctrl+Z가 안 될 수 있어요. 되돌리려면 Edit > Fetch (Alt+Ctrl+F) → 체크 직전 상태로 돌아가요."
		local cand = for o in (if selOnly then selection else objects) where (isCheckMesh o) collect o
		if cand.count == 0 do return ("[리깅 전 체크]\n" + bs[1] + "대상 메쉬가 없어요." + (if held then "\n" + fetchNote else ""))
		local done = #(), conv = 0, flipped = 0, skipped = #(), unskinned = #()
		undo "리깅 전 체크" on
		(
			for o in cand do
			(
				local hasSkin = (for m in o.modifiers where (classOf m) == Skin collect m).count > 0
				if hasSkin and not removeSkin then append skipped (o.name + " (Skin 있음)")
				else try
				(
					-- Skin을 먼저 지워야 애니 자세가 아닌 원래 모양으로 굳어짐
					if hasSkin do
					(
						for i = o.modifiers.count to 1 by -1 where (classOf o.modifiers[i]) == Skin do deleteModifier o i
						append unskinned o.name
					)
					local kids = for c in o.children collect #(c, c.transform)
					local mirrored = (dot (cross o.transform.row1 o.transform.row2) o.transform.row3) < 0
					local wasMesh = (classOf o.baseObject) == Editable_mesh and o.modifiers.count == 0
					o.pivot = [0,0,0]
					ResetXForm o
					convertToMesh o
					if mirrored do (meshop.flipNormals o #{1..o.numfaces}; update o; flipped += 1)
					for k in kids where isValidNode k[1] do k[1].transform = k[2]
					if not wasMesh do conv += 1
					append done o.name
				)
				catch (append skipped (o.name + " (오류: " + getCurrentException() + ")"))
			)
		)
		local r = "[리깅 전 체크] 처리 " + (done.count as string) + "개 / 건너뜀 " + (skipped.count as string) + "개\n" + bs[1]
		r += "- 위치 0,0,0 + Reset XForm 완료 (메쉬 모양은 그대로)\n"
		r += "- Editable Mesh로 바꾼 것 " + (conv as string) + "개 (모디파이어 정리 포함)\n"
		if flipped > 0 do r += "- 미러(음수 스케일)였던 메쉬 " + (flipped as string) + "개는 면 방향도 바로잡음\n"
		if unskinned.count > 0 do (r += "- Skin 지우고 초기화한 메쉬 " + (unskinned.count as string) + "개: "; for x in unskinned do r += x + " "; r += "\n")
		if skipped.count > 0 do (r += "건너뜀:\n"; for x in skipped do r += "  " + x + "\n")
		r += (if held then fetchNote else "Ctrl+Z로 되돌릴 수 있어요.") + " 끝나면 '모델링 검사'를 다시 눌러 확인하세요."
		r
	),

	-- ================== 작업 시간 기록 ==================
	fn pad2 n = (if n < 10 then ("0" + (n as string)) else (n as string)),
	fn nowStr = (local t = getLocalTime(); (t[1] as string) + "-" + (pad2 t[2]) + "-" + (pad2 t[4]) + " " + (pad2 t[5]) + ":" + (pad2 t[6]) + ":" + (pad2 t[7])),
	fn logDir = (if doesFileExist "C:\\claude\\max_blender" then "C:\\claude\\max_blender" else (getDir #export)),
	fn logFile = (logDir() + "\\rigtools_timelog.csv"),
	fn defaultChar = (if maxFileName != "" then (getFilenameFile maxFileName) else "(이름 없음)"),

	fn appendLog startStr charName stage endStr mins note =
	(
		-- UTF-8로 저장 (Max 기본 파일 쓰기는 시스템 코드 페이지라 한글이 깨짐)
		local f = logFile()
		local io = dotNetClass "System.IO.File"
		local ln = (substring startStr 1 10) + "," + (substituteString charName "," "_") + "," + stage + "," + startStr + "," + endStr + "," + (formattedPrint mins format:".2f") + "," + note + "\r\n"
		if not (doesFileExist f) then io.WriteAllText f ("날짜,캐릭터,단계,시작,종료,분,구분\r\n" + ln) (dotNetObject "System.Text.UTF8Encoding" true)
		else io.AppendAllText f ln (dotNetObject "System.Text.UTF8Encoding" false)
	),

	fn tlStop =
	(
		if TosRigTL[1] == 0 then "측정 중인 단계가 없어요."
		else
		(
			local mins = (timeStamp() - TosRigTL[1]) / 60000.0
			appendLog TosRigTL[4] TosRigTL[3] TosRigTL[2] (nowStr()) mins "수동"
			local s = "■ 종료: " + TosRigTL[2] + " " + (formattedPrint mins format:".1f") + "분 (기록 저장)"
			TosRigTL[1] = 0
			s
		)
	),

	fn tlStart stage charName =
	(
		local msg = ""
		if TosRigTL[1] != 0 do msg = (tlStop()) + "\n"
		TosRigTL[1] = timeStamp()
		TosRigTL[2] = stage
		TosRigTL[3] = charName
		TosRigTL[4] = nowStr()
		msg + "▶ 측정 시작: " + stage + " (" + charName + ") " + TosRigTL[4]
	),

	-- 스크립트가 알아서 돈 작업은 자동으로 기록 (ms = 걸린 시간)
	fn autoLog charName stage ms = (appendLog (nowStr()) charName stage (nowStr()) (ms / 60000.0) "자동(스크립트)"),

	fn tlSummary charName =
	(
		local f = logFile()
		if not (doesFileExist f) then "아직 기록이 없어요."
		else
		(
			local lines = (dotNetClass "System.IO.File").ReadAllLines f
			local stages = #(), tot = #(), auto = #()
			for k = 2 to lines.count do
			(
				local ln = lines[k] as string
				local p = filterString ln ","
				if p.count >= 7 and p[2] == charName do
				(
					local i = findItem stages p[3]
					if i == 0 then (append stages p[3]; append tot 0.0; append auto 0.0; i = stages.count)
					local m = p[6] as float
					tot[i] += m
					if p[7] != "수동" do auto[i] += m
				)
			)
			local out = "작업 시간 합계 - " + charName + "\n", sum = 0.0
			for i = 1 to stages.count do
			(
				out += "  " + stages[i] + ": " + (formattedPrint tot[i] format:".1f") + "분"
				if auto[i] > 0 do out += " (스크립트 " + (formattedPrint auto[i] format:".1f") + "분)"
				out += "\n"
				sum += tot[i]
			)
			if stages.count == 0 then "이 캐릭터의 기록이 없어요: " + charName
			else (out + "  합계: " + (formattedPrint sum format:".1f") + "분\n파일: " + f)
		)
	),

	fn exportForBlender =
	(
		local def = (if maxFileName != "" then (maxFilePath + (getFilenameFile maxFileName)) else (getDir #export + "\\scene")) + "_check.fbx"
		local p = getSaveFileName caption:"블렌더 확인용 FBX" filename:def types:"FBX (*.fbx)|*.fbx"
		if p == undefined then "취소했어요." else MaxBridge.exportFBX p selOnly:false anim:true
	),

	fn sbgDir = (if TOS_RigDirOverride != undefined then TOS_RigDirOverride else ((getDir #userScripts) + "\\TOS_RigTools\\")),   -- TOS_RigDirOverride: 설치 없이 시험할 때만

	-- TOS: 캐릭터 성별 (#m / #f). 1) 직접 고른 값(이 파일에 저장) 2) 캐릭터 이름·파일 이름의 _m / _f 3) ask 면 물어봄
	fn genderFromName s =
	(
		local tk = filterString (toLower (getFilenameFile s)) "_-. "
		local m = (findItem tk "m") > 0, f = (findItem tk "f") > 0
		if m and not f then #m else if f and not m then #f else undefined
	),
	fn gender ask:true =
	(
		local s = getAppData rootNode 7741, g = undefined, nm = "", a = undefined
		if s == "m" do g = #m
		if s == "f" do g = #f
		-- 열린 파일 이름의 _m / _f 를 먼저 (창 [캐릭터] 칸은 창을 연 때의 이름이 남아 있을 수 있음: 여자 파일 다음에 남자 파일을 열면 여자로 잘못 판별되던 것)
		if g == undefined do g = genderFromName maxFileName
		if g == undefined and TosRigRoll != undefined and TosRigRoll.open do nm = TosRigRoll.eChar.text
		if g == undefined do g = genderFromName nm
		-- 파일 위치의 직업 폴더 (...\Ver5_Archer_f\...)
		if g == undefined and matchPattern (toLower maxFilePath) pattern:"*\\ver*_*_m\\*" do g = #m
		if g == undefined and matchPattern (toLower maxFilePath) pattern:"*\\ver*_*_f\\*" do g = #f
		if g == undefined and ask do
		(
			a = yesNoCancelBox "캐릭터 이름(파일 이름)에 _m / _f 가 없어서 성별을 모르겠어요.\n\n예 = 남자 (_m 레퍼런스)\n아니오 = 여자 (_f 레퍼런스)\n\n(고른 값은 이 Max 파일에 저장돼요)" title:"TOS_RigTools - 성별"
			if a == #yes do (g = #m; setAppData rootNode 7741 "m")
			if a == #no do (g = #f; setAppData rootNode 7741 "f")
		)
		g
	),
	fn genderText g = (if g == #m then "남자(_m)" else if g == #f then "여자(_f)" else "모름"),
	-- 창 [성별] 에서 고른 값 (undefined = 자동)
	fn genderSet g = (if g == undefined then deleteAppData rootNode 7741 else setAppData rootNode 7741 (g as string)),
	-- TOS: 직업 (archer / cleric / mage / warrior) → 2. Biped 레퍼런스 = 직업_성별 (예: archer_f)
	--   1) 창 [직업] 에서 고른 값 (이 Max 파일에 저장)  2) 캐릭터 이름·파일 이름 앞부분 (archer_f_..., mage_m_..., wizard → mage)  3) 파일 위치의 Ver5_<직업>_<성별> 폴더
	fn jobList = #("archer", "cleric", "mage", "warrior"),
	fn jobFromName s =
	(
		local tk = filterString (toLower (getFilenameFile s)) "_-. ", r = undefined
		for t in tk while r == undefined do
		(
			if (findItem (jobList()) t) > 0 then r = t
			else if t == "wizard" or t == "wiz" do r = "mage"
		)
		r
	),
	fn jobFromPath p = (local r = undefined; for j in jobList() while r == undefined do (if matchPattern (toLower p) pattern:("*\\ver*_" + j + "_*") do r = j); r),
	fn jobPicked = (local s = getAppData rootNode 7742; if s != undefined and (findItem (jobList()) s) > 0 then s else undefined),
	fn job =
	(
		local j = jobPicked(), nm = ""
		if j == undefined do j = jobFromName maxFileName   -- 열린 파일 이름 먼저 (성별과 같은 까닭)
		if j == undefined and TosRigRoll != undefined and TosRigRoll.open do nm = TosRigRoll.eChar.text
		if j == undefined do j = jobFromName nm
		if j == undefined do j = jobFromPath maxFilePath
		j
	),
	fn jobSet j = (if j == undefined then deleteAppData rootNode 7742 else setAppData rootNode 7742 j),
	fn jobText j = (if j == undefined then "모름" else ((toUpper j[1]) + (substring j 2 -1))),
	fn charText = ("직업 " + (jobText (job())) + (if jobPicked() != undefined then " (고름)" else "") + " · 성별 " + (genderText (gender ask:false)) + (if (getAppData rootNode 7741) != undefined then " (고름)" else "")),
	-- TOS 레퍼런스 폴더: 절대 경로를 코드에 두지 않고 PC 마다 ani\Character\PC 를 찾음 (그 아래 직업별 폴더 Ver5_Archer_f · Ver5_Archer_m ...)
	--   1) ini(plugcfg\TOS_RigTools.ini)에 저장된 경로  2) 지금 Max 파일 위치에서 위로 올라가며 <루트>\ani\Character\PC
	--   3) 드라이브마다 X:\ani\..., X:\<폴더>\ani\... (예: X:\TOS\ani\Character\PC)  4) ask 면 폴더 선택 창 → ini 에 저장
	fn bodyRel = "ani\\Character\\PC",
	fn iniFile = ((getDir #plugcfg) + "\\TOS_RigTools.ini"),
	fn bodyOk d = (d != undefined and d != "" and (doesFileExist d) and ((getDirectories (d + "\\*_m")).count + (getDirectories (d + "\\*_f")).count) > 0),
	fn bodySave d = (setINISetting (iniFile()) "Reference" "BodyDir" d; d),
	fn bodyPick =
	(
		local d = getSavePath caption:"TOS 레퍼런스 폴더 고르기 (...\\ani\\Character\\PC)"
		if d != undefined and not (bodyOk d) do (messageBox ("이 폴더에 직업별 폴더(Ver5_Archer_f 등)가 없어요:\n" + d) title:"TOS_RigTools - 레퍼런스 경로"; d = undefined)
		if d != undefined do bodySave d
		d
	),
	fn bodyFind =
	(
		local rel = bodyRel(), found = undefined, p = trimRight maxFilePath "\\", i = undefined, c = "", up = "", drives = #(), okD = false, r = "", subs = #()
		-- 지금 파일 위치에서 위로
		while found == undefined and p != undefined and p.count > 3 do
		(
			i = findString (toLower p) (toLower rel)
			if i != undefined then (c = substring p 1 (i + rel.count - 1); if bodyOk c do found = c)
			else if bodyOk (p + "\\" + rel) do found = p + "\\" + rel
			up = trimRight (getFilenamePath p) "\\"
			p = if up == "" or up == p then undefined else up
		)
		-- 드라이브 (고정·네트워크 드라이브만): X:\ani\... , X:\<폴더>\ani\...
		if found == undefined do drives = try ((dotNetClass "System.IO.DriveInfo").GetDrives()) catch #()
		for dv in drives while found == undefined do
		(
			okD = try (dv.IsReady and ((dv.DriveType.ToString()) == "Fixed" or (dv.DriveType.ToString()) == "Network")) catch false
			if okD do
			(
				r = dv.Name
				if bodyOk (r + rel) then found = r + rel
				else
				(
					subs = getDirectories (r + "*")
					for sd in subs while found == undefined do if bodyOk (sd + rel) do found = sd + rel
				)
			)
		)
		found
	),
	fn bodyDir ask:false =
	(
		local d = getINISetting (iniFile()) "Reference" "BodyDir"
		if not (bodyOk d) do (d = bodyFind(); if d != undefined do bodySave d)
		if d == undefined and ask do d = bodyPick()
		d
	),	-- 기준 데이터 파일: 이 PC 의 Body 폴더에서 다시 읽은 것(plugcfg\TOS_RigTools_ref\)이 있으면 그것, 없으면 설치에 든 기본 데이터
	fn refDataDir = ((getDir #plugcfg) + "\\TOS_RigTools_ref\\"),
	fn dataFile nm = (local u = refDataDir() + nm; if doesFileExist u then u else (sbgDir() + nm)),
	fn dataInfo = (local u = refDataDir() + "tos_bip_ref.ms"; if doesFileExist u then ("Biped = 이 PC 레퍼런스 폴더에서 읽음 (" +(getINISetting (iniFile()) "Reference" "ReadAt") + ")") else "설치 기본 데이터 (2026-11-18)"),
	-- 성별 레퍼런스 데이터 (Biped 구조·굵기)
	fn bipRefLoad = (local f = dataFile "tos_bip_ref.ms"; if TOS_BipRef == undefined and (doesFileExist f) do fileIn f; TOS_BipRef != undefined),
	-- 4. 세컨더리 본 (tos_secondary.ms)
	fn secLoad = (local f = sbgDir() + "tos_secondary.ms"; if tos_secBuild == undefined and (doesFileExist f) do fileIn f; tos_secBuild != undefined),
	-- Body 폴더의 레퍼런스를 다시 읽어 기준 데이터 만들기 (tos_make_ref.ms). 지금 장면은 닫힘
	fn refRead =
	(
		local d = bodyDir ask:true
		if d == undefined do return "취소했어요. (레퍼런스 경로 없음)"
		if not (queryBox ("레퍼런스를 다시 읽을까요?\n" + d + "\n\n직업·성별 레퍼런스(8개)로 Biped 를, 스킨 레퍼런스(성별 8개)로 몸 웨이트를,\n직업 폴더마다 스킨 있는 _set.max 10개(성별 40개)로 관절 부위 웨이트를 다시 배워요.\n지금 장면은 닫혀요 (저장 안 함). 먼저 저장하세요. (20~30분)") title:"TOS_RigTools - 레퍼런스 다시 읽기") do return "취소했어요. (변경 없음)"
		local f = sbgDir() + "tos_make_ref.ms"
		if not (doesFileExist f) do return ("파일이 없어요: " + f)
		fileIn f
		local r = tos_makeRef d (refDataDir())
		if not (matchPattern r pattern:"오류*") do
		(
			setINISetting (iniFile()) "Reference" "ReadAt" (localTime as string)
			TOS_BipRef = undefined; TOS_SecRef = undefined; TosRigStdTpl = undefined; TosRigStdInfo = undefined
		)
		r
	),

	-- 1.5 Biped 자동 생성: 노란 지정점(sbg_*)으로 Biped + 손가락·발가락·트위스트·쇄골
	fn sbgBuild =
	(
		local f = sbgDir() + "sbg_build.ms"
		if not (doesFileExist f) then ("SecBoneGen 파일이 없어요: " + f) else
		(
			fileIn f
			trts_sbgBuildRef()
		)
	),

	-- 관절 자동 감지만 다시 (Blender 를 띄워 지정점을 새로 놓음)
	fn sbgDetect =
	(
		local f = sbgDir() + "sbg_build.ms"
		if not (doesFileExist f) then ("SecBoneGen 파일이 없어요: " + f) else
		(
			fileIn f
			local r = trts_sbgDetect()
			if matchPattern r pattern:"ERROR*" then (substituteString r "ERROR: " "") else ("관절 자동 감지 완료: " + r + "\n노란 점을 확인하고 [Biped 생성] 을 누르세요. (빨간 점은 꼭 확인)")
		)
	),

	-- 3. [생성] 으로 만든 Twist 보조 본 한 번에 숨기기/보이기
	fn helperAll =
	(
		local n = try (TosRigStd.helperNodes()) catch #()
		for o in n where not (isValidNode o) do deleteItem n (findItem n o)
		n
	),
	fn helperHide =
	(
		local n = helperAll()
		if n.count == 0 then "숨길 헬퍼·보조 본이 없어요. ([생성] 을 먼저 하세요)" else
		(
			local vis = (for o in n where not o.isHidden collect o).count
			if vis > 0 then (hide n; "헬퍼·보조 본 " + (n.count as string) + "개를 숨겼어요. (다시 누르면 보여요)")
			else (unhide n; "헬퍼·보조 본 " + (n.count as string) + "개를 다시 보이게 했어요.")
		)
	),

	-- 2.5 Blender 작업 (Blender 를 띄우고 작업 파일로 실행, Max 는 기다리지 않음)
	fn blLoad = (local f = sbgDir() + "rts_blender.ms"; if (trts_partItems == undefined or trts_partMaxFix == undefined or trts_partAutoStart == undefined or trts_obDeleteAll == undefined or trts_obPickFaces == undefined or trts_obDeletePart == undefined or trts_obRootExtra == undefined or trts_obCenterToggle == undefined or trts_obCenterSet == undefined) and (doesFileExist f) do fileIn f; ok),
	fn blJob k extra:"" = (local f = sbgDir() + "rts_blender.ms"; if not (doesFileExist f) then ("파일이 없어요: " + f) else (if trts_blStart == undefined or trts_partItems == undefined or trts_partMaxFix == undefined do fileIn f; trts_blStart k extra:extra)),

	-- [수정] 지정점 고치기 시작 / [완료] Biped 갱신 + 지정점 삭제
	fn sbgEdit = (local f = sbgDir() + "sbg_build.ms"; if not (doesFileExist f) then ("SecBoneGen 파일이 없어요: " + f) else (fileIn f; trts_sbgEditStart())),
	fn sbgDone = (local f = sbgDir() + "sbg_build.ms"; if not (doesFileExist f) then ("SecBoneGen 파일이 없어요: " + f) else (fileIn f; trts_sbgEditDone())),

	-- 지정점을 손으로 놓거나 고치는 SecBoneGen 창
	fn sbgWindow =
	(
		local f = sbgDir() + "SecBoneGen_v0.11_step1_biped.ms"
		if not (doesFileExist f) then ("SecBoneGen 파일이 없어요: " + f) else
		(
			TSBG_noDialog = false
			fileIn f
			"SecBoneGen 창을 열었어요. (지정점 놓기·저장, Biped 생성)"
		)
	),

	fn open = (try (destroyDialog TosRigRoll) catch (); createDialog TosRigRoll)
)
TosRig = TosRigStruct()

rollout TosRigRoll "TOS_RigTools 1.0" width:514 height:780
(
	groupBox gbx1 "0. 작업 시간 기록" pos:[4,6] width:250 height:137
		edittext eChar "캐릭터 " fieldWidth:180 text:"" pos:[14,22]
		dropdownlist dStage "단계" items:#("모델링 체크", "Bip 맞추기", "헬퍼·보조 본", "스킨 웨이트", "치마", "망토", "헤어", "애니", "기타") width:230 pos:[14,43]
		button bTS "▶ 시작" width:110 pos:[14,87]
		button bTE "■ 종료" width:110 pos:[131,87]
		button bTV "이 캐릭터 합계 보기" width:230 pos:[14,112]
	groupBox gbx2 "1. 모델링 체크" pos:[4,149] width:250 height:135
		button bMC "모델링 검사" width:230 height:26 pos:[14,165]
		label lMC1 "치명적 오류(ERROR)만 없으면 리깅 가능" align:#left pos:[14,195]
		checkbox chkMSel "선택한 메쉬만" checked:false pos:[14,212]
		button bMCSel "리깅 전 체크" width:230 height:26 pos:[14,231]
		label lMC2 "위치0·XForm·Mesh·Skin·키 삭제·Biped 설정" align:#left pos:[14,261]
	groupBox gbx3 "2. Biped 자동 생성" pos:[4,290] width:250 height:145
		dropdownlist ddJob "" items:#("직업: 자동", "Archer", "Cleric", "Mage", "Warrior") width:113 tooltip:"Biped 레퍼런스 직업. 자동 = 캐릭터 이름·파일 이름 앞부분(archer_f_...) 또는 파일 위치의 Ver5_<직업>_<성별> 폴더. 고른 값은 이 Max 파일에 저장돼요" pos:[14,305]
		dropdownlist ddGen "" items:#("성별: 자동", "남자 (_m)", "여자 (_f)") width:113 tooltip:"Biped 레퍼런스 성별. 자동 = 이름의 _m / _f. 고른 값은 이 Max 파일에 저장돼요" pos:[131,305]
		label lB2 "관절 고치기: [수정] → 노란 점 옮기기 → [완료]" align:#left pos:[14,337]
		button bSbgBuild "Biped 생성 (레퍼런스 그대로)" width:230 height:28 tooltip:"직업_성별(예: archer_f)에 맞는 TOS 레퍼런스 .max 의 Biped 를 그대로 만들어요 (구조·뼈 길이·굵기·자세·위치·레이어가 레퍼런스와 같음). 레퍼런스 = 창 아래 레퍼런스 폴더의 Ver5_<직업>_<성별>" pos:[14,357]
		button bSbgEdit "수정 (점 고치기)" width:113 tooltip:"지금 Biped 관절마다 노란 점을 놓아요 (Biped·메쉬는 잠시 얼림). 점을 옮긴 뒤 [완료]. 오른쪽은 왼쪽 점을 거울로" pos:[14,389]
		button bSbgDone "완료 (Biped 갱신)" width:113 tooltip:"지금 Biped 를 노란 점 위치에 맞춰 갱신해요 (뼈 방향·길이만, 굵기·손가락·발은 그대로). Ctrl+Z 가능" pos:[131,389]
		label lB3 "완료하면 점·sbg_debug 레이어는 지워져요" align:#left pos:[14,414]
	groupBox gbx4 "3. 헬퍼·보조 본 (Twist)" pos:[4,441] width:250 height:118
		label lH1 "Bip을 메쉬에 맞춘 뒤 실행 (여자는 Dummy_Chast 도)" align:#left pos:[14,457]
		button bHelp "생성" width:230 height:28 tooltip:"성별 레퍼런스의 twist 보조 본(쇄골·위팔 Point, Clavicle Twist 상자)을 만들어요 (twist 레이어, MTOS 와 같음). 여자는 가슴 더미 Dummy_Chast 도 만들어요 (부모 Bip01 Spine2, archer_f·cleric_f 레퍼런스와 같은 자리·크기)" pos:[14,474]
		button bMirror "좌우대칭 (L → R 위치 복사)" width:230 pos:[14,506]
		button bHide "보조본 숨기기·보이기" width:113 tooltip:"[생성] 으로 만든 Twist 보조 본을 한 번에 숨겨요. 다시 누르면 보여요" pos:[14,531]
		button bLayer "레이어 정리" width:113 tooltip:"TOS 레퍼런스 레이어로 정리: Warrior_m_Bip / Warrior_Bip · twist · nubs ([생성] 뒤에는 저절로 해요)" pos:[131,531]
	groupBox gbx6 "4. 세컨더리 본" pos:[260,6] width:250 height:290
		label lCk "Cloak (망토) - 메쉬 모양에 맞춤" align:#left pos:[270,22]
		button bCkWaist "허리" width:74 tooltip:"마디 수를 3 으로 두고 만들어요. Bone_cloak_All 아래 [줄 수] 줄, 3마디 + 끝. 망토 메쉬 표면을 따라 밑단까지 (망토 메쉬를 선택하고 누르면 그 메쉬만 봄, 못 찾은 줄은 허리 높이에서 자름)" pos:[270,38]
		button bCkKnee "무릎" width:74 tooltip:"마디 수를 5 로 두고 만들어요. [줄 수] 줄, 5마디 + 끝. 망토 메쉬 표면을 따라 밑단까지 (못 찾은 줄은 무릎 높이에서 자름)" pos:[348,38]
		button bCkFoot "발" width:74 tooltip:"마디 수를 8 로 두고 만들어요. [줄 수] 줄, 8마디 + _1 끝 (레퍼런스 표준 이름). 망토 메쉬 표면을 따라 밑단까지" pos:[426,38]
		spinner spCkRows "줄 수" range:[1,15,5] type:#integer fieldwidth:28 tooltip:"Bone_cloak_All 아래 줄 수. 5 = 레퍼런스 그대로 (L 바깥·L 안쪽·B·R 안쪽·R 바깥). 다른 수면 레퍼런스 시작점 사이에 고르게 나눠요 (홀수면 가운데 B 줄)" pos:[270,64]
		spinner spCkBones "마디" range:[1,20,8] type:#integer fieldwidth:28 tooltip:"줄마다 마디 수 (+ 짧은 끝 본 1개). 본 끝은 망토 메쉬 밑단" pos:[352,64]
		button bCkMake "만들기" width:64 tooltip:"[줄 수] × [마디] 대로 망토 본을 만들어요 (본 끝 = 망토 메쉬 밑단)" pos:[436,62]
		label lSk "Skirt (치마)" align:#left pos:[270,88]
		spinner spSkRows "줄 수" range:[2,24,12] type:#integer fieldwidth:28 tooltip:"Bone_Skirt_all 아래 줄 수. 12 = 레퍼런스 그대로. 다른 수면 01 줄(앞 가운데)부터 몸 둘레를 고르게 나눠요 (줄 모양은 가까운 레퍼런스 줄)" pos:[330,87]
		spinner spSkSegs "마디" range:[1,20,6] type:#integer fieldwidth:28 tooltip:"줄마다 마디 수 (+ 짧은 끝 본 1개). 이 칸을 고치지 않았으면 버튼마다 기본값 (Skirt_S 4 · Skirt 6 · Skirt_W 6) 을 써요" pos:[412,87]
		button bSkS "Skirt_S" width:74 tooltip:"짧은 치마: Bone_Skirt_S_01~ ([줄 수] 줄 × [마디], 기본 12줄 × 4마디 + 끝, Warrior_Skirt_S_Bone)" pos:[270,106]
		button bSkN "Skirt" width:74 tooltip:"발목까지 오는 일반 치마: Bone_Skirt_01~ ([줄 수] 줄 × [마디], 기본 12줄 × 6마디 + 끝, Warrior_Skirt_Bone)" pos:[348,106]
		button bSkW "Skirt_W" width:74 tooltip:"폭이 넓은 치마: Bone_Skirt_W_01~ ([줄 수] 줄 × [마디], 기본 12줄 × 6마디 + 끝, Warrior_Skirt_W_Bone)" pos:[426,106]
		label lCl "Clavicle (어깨) - darkenforcerpriest 기준" align:#left pos:[270,130]
		spinner spClRows "옆 줄" range:[1,10,4] type:#integer fieldwidth:28 tooltip:"L·R Clavicle 아래 옆마다 줄 수 (+ Spine2 아래 가운데 1줄). 4 = 레퍼런스 그대로 (앞 안쪽 · 앞 바깥 · 어깨 위 · 등). 더 늘리면 등 쪽에 더해요. 등쪽 줄은 어깨 망토 메쉬 표면에 맞춰요 (메쉬를 선택하고 누르면 그 메쉬만 봄)" pos:[270,148]
		spinner spClSegs "마디" range:[1,10,3] type:#integer fieldwidth:28 tooltip:"줄마다 마디 수 (+ 짧은 끝 본 1개). 3 = 레퍼런스 그대로" pos:[352,148]
		button bClMake "만들기" width:64 tooltip:"어깨 세컨더리 본 Bone_Spine2_* 를 [옆 줄] × [마디] 대로 만들어요 (레퍼런스 costume_m_ep18darkenforcerpriest_set, 4줄 × 3마디 = 레퍼런스 그대로 37개). 다시 누르면 바꿔요" pos:[436,146]
		label lObL "본 목록 (클릭 = 본 선택)" align:#left pos:[270,172]
		listbox lbSec "" items:#() height:5 width:230 pos:[270,188]
		button bSecSel "선택" width:113 tooltip:"목록에서 고른 세컨더리 본을 모두 선택해요" pos:[270,264]
		button bSecDel "삭제" width:113 tooltip:"목록에서 고른 세컨더리 본만 지워요 (Ctrl+Z 가능)" pos:[387,264]
	groupBox gbx7 "5. 스킨" pos:[260,302] width:250 height:92
		button bBlSkin "스킨 적용 (레퍼런스 웨이트)" width:230 height:28 tooltip:"몸 = 같은 성별 레퍼런스 코스튬(스킨 있음) 웨이트를 옮김, 망토·치마 = 4. 에서 만든 세컨더리 본. 메쉬를 선택하면 그 메쉬만, 없으면 보이는 메쉬 전부. 예전 Skin 은 지우고 새로 (1~2분, 진행 창에 % 표시, [취소] 또는 Esc 로 멈추면 예전 Skin 그대로)" pos:[270,318]
		label lBl2 "1~2분 · 진행 창 표시 · [취소]/Esc 로 멈춤" align:#left pos:[270,350]
		checkbox chkSkinOff "스킨 끄기 (본 위치 고칠 때)" checked:false tooltip:"체크하면 모든 스킨 메쉬의 Skin 을 잠시 꺼요. 본을 옮겨도 메쉬가 따라오지 않아요 (웨이트는 그대로). 본을 고친 뒤 [스킨 적용 (일괄)] 을 누르거나 체크를 풀면 다시 켜져요" pos:[270,368]
	groupBox gbx8 "6. 리그 체크" pos:[260,400] width:250 height:114
		button bChk "표준 규칙 검사" width:230 pos:[270,416]
		button bRom "테스트 키 생성" width:230 tooltip:"성별 테스트 bip 를 Biped 에 불러와요 (남 pc_m_set_test.bip / 여 pc_f_set_test.bip). 0프레임 = 바인드 자세" pos:[270,441]
		button bRomDel "테스트 키 지우기" width:230 pos:[270,466]
		label lRom "남 pc_m_set_test / 여 pc_f_set_test.bip, 0f = 바인드" align:#left pos:[270,491]
	groupBox gbx9 "7. 리깅 완료" pos:[260,520] width:250 height:70
		label lRd1 "웨이트까지 다 다듬은 뒤에 누르세요" align:#left pos:[270,536]
		button bRigDone "리깅 완료 → 템플릿 저장" width:230 height:28 tooltip:"이 캐릭터의 메쉬·웨이트·본 구조를 템플릿 폴더에 저장해요. 다음 캐릭터부터 몸 웨이트(체형이 가장 비슷한 캐릭터)와 치마·망토·헤어 웨이트 참고값에 반영돼요. 테스트 키가 있으면 찢어짐 검사도 해요" pos:[270,553]
	groupBox gbxR "레퍼런스 폴더 (이 PC 의 ...\ani\Character\PC, 직업별 폴더 Ver5_<직업>_<성별>)" pos:[4,596] width:506 height:62
		edittext eBody "" fieldWidth:296 readOnly:true pos:[10,614]
		button bBodyChg "경로 변경" width:88 tooltip:"TOS 레퍼런스 폴더(...\ani\Character\PC)를 직접 골라요. 고른 경로는 이 PC 의 TOS_RigTools.ini 에 저장돼요" pos:[316,612]
		button bRefRead "레퍼런스 다시 읽기" width:98 tooltip:"직업·성별 폴더마다 레퍼런스 .max 하나(6th_greenschool, 없으면 Biped 가 있는 첫 _set.max)를 열어 Biped 기준 데이터를, 스킨 레퍼런스로 몸 웨이트·관절 부위 웨이트(직업 폴더마다 10개)를 다시 만들어요 (지금 장면은 닫힘, 20~30분). Twist·세컨더리 데이터는 설치본(MTOS 와 같음). 안 하면 설치에 든 기본 데이터를 써요" pos:[408,612]
		label lData "" align:#left width:490 pos:[12,638]
	dotNetControl tLog "System.Windows.Forms.RichTextBox" pos:[2,664] width:508 height:110
	fn say s = (try (tLog.ForeColor = trts_logColor false) catch (); tLog.text = s)
	fn secRefresh = (try (if TosRig.secLoad() do lbSec.items = tos_secItems()) catch ())
	-- 직업·성별 칸 = 이 파일에 저장된 값 (없으면 '자동')
	fn charRefresh = (
		local j = TosRig.jobPicked(), s = getAppData rootNode 7741
		ddJob.selection = if j == undefined then 1 else ((findItem (TosRig.jobList()) j) + 1)
		ddGen.selection = if s == "m" then 2 else if s == "f" then 3 else 1
	)
	fn bodyRefresh = (
		local d = try (TosRig.bodyDir()) catch undefined
		eBody.text = if d == undefined then "(못 찾음 - [경로 변경] 으로 고르세요)" else d
		lData.text = "기준 데이터: " + (try (TosRig.dataInfo()) catch "?")
	)
	fn secMake kind rows:5 bones:undefined skRows:undefined skSegs:undefined =
	(
		if not (TosRig.secLoad()) then say ("파일이 없어요: " + TosRig.sbgDir() + "tos_secondary.ms")
		else
		(
			say "세컨더리 본 만드는 중..."
			local t0 = timeStamp()
			local r = try (if matchPattern (kind as string) pattern:"cloak*" then (tos_secBuild kind rows:rows bones:bones) else (tos_secBuild kind skRows:skRows skSegs:skSegs)) catch ("오류: " + getCurrentException())
			try (TosRig.autoLog eChar.text (if matchPattern (kind as string) pattern:"cloak*" then "망토" else "치마") (timeStamp() - t0)) catch ()
			say r
			secRefresh()
		)
	)
	on TosRigRoll open do (
		try (
			local C = dotNetClass "System.Drawing.Color"
			tLog.ReadOnly = true
			tLog.BackColor = C.FromArgb 58 58 58
			tLog.ForeColor = trts_logColor false
			tLog.BorderStyle = (dotNetClass "System.Windows.Forms.BorderStyle").FixedSingle
			tLog.ScrollBars = (dotNetClass "System.Windows.Forms.RichTextBoxScrollBars").Vertical
			tLog.Font = dotNetObject "System.Drawing.Font" "Malgun Gothic" 9
		) catch ()
		eChar.text = TosRig.defaultChar(); try (TosRig.blLoad()) catch (); secRefresh(); bodyRefresh(); try (chkSkinOff.checked = trts_skinIsOff()) catch ()
		charRefresh()
		-- 다른 파일을 열면 [캐릭터] 칸·직업·성별 칸을 그 파일 것으로 (예전 파일 이름이 남아 성별을 잘못 고르지 않게)
		try (
			callbacks.removeScripts id:#TosRigFileOpen
			callbacks.addScript #filePostOpen "try (if TosRigRoll != undefined and TosRigRoll.open do (TosRigRoll.eChar.text = TosRig.defaultChar(); TosRigRoll.charRefresh(); TosRigRoll.secRefresh())) catch ()" id:#TosRigFileOpen
			callbacks.addScript #systemPostReset "try (if TosRigRoll != undefined and TosRigRoll.open do (TosRigRoll.eChar.text = TosRig.defaultChar(); TosRigRoll.charRefresh(); TosRigRoll.secRefresh())) catch ()" id:#TosRigFileOpen
			callbacks.addScript #systemPostNew "try (if TosRigRoll != undefined and TosRigRoll.open do (TosRigRoll.eChar.text = TosRig.defaultChar(); TosRigRoll.charRefresh(); TosRigRoll.secRefresh())) catch ()" id:#TosRigFileOpen
		) catch ()
		say ("TOS_RigTools " + TosRig.version + "  |  " + (TosRig.charText()) + "  (Biped 레퍼런스 = 직업_성별)"))
	on eChar entered txt do (say (TosRig.charText()))
	on ddJob selected i do (TosRig.jobSet (if i == 1 then undefined else (TosRig.jobList())[i - 1]); say (TosRig.charText()))
	on ddGen selected i do (TosRig.genderSet (if i == 1 then undefined else (if i == 2 then #m else #f)); say (TosRig.charText()))
	on bBodyChg pressed do (local d = TosRig.bodyPick(); bodyRefresh(); say (if d == undefined then "취소했어요. (경로 그대로)" else ("레퍼런스 폴더: " + d + "\n[레퍼런스 다시 읽기] 를 누르면 이 폴더로 기준 데이터를 다시 만들어요.")))
	on bRefRead pressed do (say "레퍼런스 읽는 중... (1~2분)"; say (try (TosRig.refRead()) catch ("오류: " + getCurrentException())); bodyRefresh(); secRefresh(); eChar.text = TosRig.defaultChar(); charRefresh())
	on bTS pressed do (say (TosRig.tlStart dStage.selected eChar.text))
	on bTE pressed do (say (TosRig.tlStop()))
	on bTV pressed do (say (TosRig.tlSummary eChar.text))
	on bMC pressed do
	(
		say "검사 중... (큰 메쉬는 몇 초 걸려요)"
		local t0 = timeStamp()
		local r = try (TosRig.modelCheck selOnly:chkMSel.checked) catch ("오류: " + getCurrentException())
		try (TosRig.autoLog eChar.text "모델링 체크" (timeStamp() - t0)) catch ()
		say r
	)
	on bMCSel pressed do
	(
		local ns = try (TosRig.skinnedCount selOnly:chkMSel.checked) catch (0)
		local rm = true
		if ns > 0 do rm = queryBox ("Skin이 걸린 메쉬 " + (ns as string) + "개가 있어요.\n\n예: Skin도 지우고 Mesh 상태로 초기화 (웨이트 삭제)\n아니오: Skin 메쉬는 건너뛰기\n\n(Ctrl+Z로 되돌릴 수 있어요)") title:"리깅 전 체크"
		local ki = try (TosRig.keyInfo()) catch (#(0, #()))
		local rk = false
		if ki[1] > 0 or ki[2].count > 0 do rk = queryBox ("키가 있어요.\nBiped 키 " + (ki[1] as string) + "개, 본·헬퍼·메쉬 등 " + (ki[2].count as string) + "개 노드\n\n예: 모두 삭제 (Biped 애니·풋스텝 포함)\n아니오: 키는 그대로 두기\n\n(삭제하면 Ctrl+Z 대신 Edit > Fetch로 되돌려요)") title:"리깅 전 체크 - 키 삭제"
		say "정리 중..."
		say (try (TosRig.preRigFix selOnly:chkMSel.checked removeSkin:rm removeKeys:rk) catch ("오류: " + getCurrentException()))
	)
	on bSbgBuild pressed do
	(
		say "레퍼런스 Biped 불러오는 중..."
		local t0 = timeStamp()
		local r = try (TosRig.sbgBuild()) catch ("오류: " + getCurrentException())
		try (TosRig.autoLog eChar.text "Bip 맞추기" (timeStamp() - t0)) catch ()
		say r
	)
	on bSbgEdit pressed do (say (try (TosRig.sbgEdit()) catch ("오류: " + getCurrentException())))
	on bSbgDone pressed do
	(
		say "Biped 다시 만드는 중..."
		say (try (TosRig.sbgDone()) catch ("오류: " + getCurrentException()))
	)
	on bHelp pressed do
	(
		say "생성 중..."
		local t0 = timeStamp()
		local r = try (TosRigStd.build()) catch ("오류: " + getCurrentException())
		if not (matchPattern r pattern:"오류*") and not (matchPattern r pattern:"취소*") do r += "\n" + (try (undo "레이어 정리" on (trts_layerTidy())) catch ("레이어 정리 오류: " + getCurrentException()))
		try (TosRig.autoLog eChar.text "헬퍼·보조 본" (timeStamp() - t0)) catch ()
		say r
	)
	on bMirror pressed do
	(
		say "좌우대칭 중..."
		say (try (trts_mirrorLR()) catch ("오류: " + getCurrentException()))
	)
	on bHide pressed do (say (try (TosRig.helperHide()) catch ("오류: " + getCurrentException())))
	on bLayer pressed do
	(
		say "레이어 정리 중..."
		local res = try (undo "레이어 정리" on (trts_layerTidy())) catch ("오류: " + getCurrentException())
		say res
	)
	on bCkWaist pressed do (spCkBones.value = 3; secMake #cloak_waist rows:spCkRows.value bones:3)
	on bCkKnee pressed do (spCkBones.value = 5; secMake #cloak_knee rows:spCkRows.value bones:5)
	on bCkFoot pressed do (spCkBones.value = 8; secMake #cloak_foot rows:spCkRows.value bones:8)
	on bClMake pressed do (
		if not (TosRig.secLoad()) then say ("파일이 없어요: " + TosRig.sbgDir() + "tos_secondary.ms")
		else (
			say "어깨 본 만드는 중..."
			local r = try (tos_secBuildClav spClRows.value spClSegs.value) catch ("오류: " + getCurrentException())
			say r
			secRefresh()
		)
	)
	on bCkMake pressed do (
		local v = spCkBones.value
		local kd = if v == 3 then #cloak_waist else if v == 5 then #cloak_knee else if v == 8 then #cloak_foot else #cloak_custom
		secMake kd rows:spCkRows.value bones:v
	)
	-- 치마: [마디] 칸을 손으로 고쳤으면 그 값, 아니면 종류별 기본값 (Skirt_S 4 · Skirt 6 · Skirt_W 6)
	local skSegsTouched = false
	on spSkSegs changed v do skSegsTouched = true
	fn skMake kd = (
		local i = if kd == #skirt_S then 1 else if kd == #skirt_W then 3 else 2
		local d = try (tos_secSkirtSegs[i]) catch (#(4, 6, 6)[i])
		if not skSegsTouched do spSkSegs.value = d
		secMake kd skRows:spSkRows.value skSegs:spSkSegs.value
	)
	on bSkS pressed do skMake #skirt_S
	on bSkN pressed do skMake #skirt_N
	on bSkW pressed do skMake #skirt_W
	on lbSec selected i do (say (try (tos_secPick i) catch ("오류: " + getCurrentException())))
	on bSecSel pressed do (if lbSec.selection > 0 then say (try (tos_secPick lbSec.selection) catch ("오류: " + getCurrentException())) else say "목록에서 고르세요.")
	on bSecDel pressed do
	(
		if lbSec.selection == 0 then say "목록에서 지울 항목을 고르세요."
		else (say (try (tos_secDelete lbSec.selection) catch ("오류: " + getCurrentException())); secRefresh())
	)
	on bRigDone pressed do (
		TosRig.blLoad()
		if trts_rigDone == undefined do try (fileIn (TosRig.sbgDir() + "rts_tpl.ms")) catch ()
		say (try (trts_rigDone()) catch ("오류: " + getCurrentException()))
	)
	on bBlSkin pressed do (
		if chkSkinOff.checked do (try (TosRig.blLoad(); trts_skinOff false) catch (); chkSkinOff.checked = false)
		local hasSkin = (for o in objects where superClassOf o == GeometryClass and (for m in o.modifiers where classOf m == Skin collect m).count > 0 collect o).count > 0
		if (not hasSkin) or (queryBox "이미 Skin 이 있는 메쉬는 예전 Skin 을 지우고 새로 계산해요.\n(손으로 다듬은 웨이트도 지워져요)\n\n진행할까요?" title:"TOS_RigTools - 스킨 적용") then
		(
			say "스킨 적용 중... (1~2분) 진행 창에 % 가 보여요. 멈추려면 [취소] 또는 Esc"
			windows.processPostedMessages()
			local t0 = timeStamp()
			if tos_skinApply == undefined do try (fileIn (TosRig.sbgDir() + "tos_skin.ms")) catch ()
			local r = try (tos_skinApply()) catch ("오류: " + getCurrentException())
			try (TosRig.autoLog eChar.text "스킨 웨이트" (timeStamp() - t0)) catch ()
			say r
		)
		else say "취소했어요. (변경 없음)"
	)
	on chkSkinOff changed st do (
		TosRig.blLoad()
		local m = try (trts_skinOff st) catch ("오류: " + getCurrentException())
		try (tLog.ForeColor = trts_logColor st) catch ()
		tLog.text = m
	)
	on bRom pressed do
	(
		local hasKeys = false
		for o in objects where classOf o == Biped_Object while not hasKeys do (try (if o.controller.keys.count > 0 do hasKeys = true) catch ())
		if (not hasKeys) or (queryBox "Biped 에 있는 기존 키를 지우고 테스트 키(테스트 bip)로 바꿀까요?\n(본 위치·스킨·헬퍼는 그대로. 되돌리려면 [테스트 키 지우기])" title:"TOS_RigTools - 테스트 키") then
		(
			say "테스트 키 만드는 중..."
			say (try (trts_testKeys #make) catch ("오류: " + getCurrentException()))
		)
		else say "취소했어요. (변경 없음)"
	)
	on bRomDel pressed do
	(
		if queryBox "Biped 의 키를 모두 지울까요?\n(0프레임은 바인드 자세로 되돌려요)" title:"TOS_RigTools - 테스트 키 지우기" then say (try (trts_testKeys #clear) catch ("오류: " + getCurrentException()))
		else say "취소했어요. (변경 없음)"
	)
	on bChk pressed do
	(
		say "검사 중..."
		local r = try (MaxBridge.checkRig()) catch ("오류: " + getCurrentException())
		say (substituteString r "\t" "  ")
	)
)

macroScript TOS_RigTools category:"TOS" buttonText:"TOS_RigTools" tooltip:"TOS_RigTools"
(
	on execute do TosRig.open()
)

-- TOS 메뉴 (상단 메뉴바에 TOS 가 없으면 만들고, TOS_RigTools 항목이 없으면 넣음)
(
	try
	(
		local sub = menuMan.findMenu "TOS"
		local changed = false
		if sub == undefined do
		(
			sub = menuMan.createMenu "TOS"
			local main = menuMan.getMainMenuBar()
			main.addItem (menuMan.createSubMenuItem "TOS" sub) -1
			changed = true
		)
		local has = false
		for i = 1 to sub.numItems() do (try (if (sub.getItem i).getTitle() == "TOS_RigTools" do has = true) catch ())
		if not has do (sub.addItem (menuMan.createActionItem "TOS_RigTools" "TOS") -1; changed = true)
		if changed do menuMan.updateMenuBar()
	)
	catch (format "[TOS_RigTools] TOS 메뉴를 만들지 못했어요: %\n" (getCurrentException()))
)
format "[TOS_RigTools] % loaded\n" TosRig.version
