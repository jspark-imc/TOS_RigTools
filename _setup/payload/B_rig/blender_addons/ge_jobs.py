# GE 작업 실행기: Max(MTOS_RigTools)의 Blender 버튼을 받아 Blender 에서 실행한다.
#   Max 가 %LOCALAPPDATA%\GE_RigJobs\job_<id>.json 을 쓰면 이 애드온이 1초 안에 집어서 실행하고
#   st_<id>.txt (진행), res_<id>.json (결과) 를 쓴다. 작업마다 그 Max 의 브리지 포트로 연결한다.
#   Blender 가 여러 개 떠 있어도 실행기는 하나만 (runner.json 하트비트를 가진 쪽).
bl_info = {
    "name": "GE 작업 실행기 (Max 버튼 → Blender)",
    "author": "ani 팀",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "자동 (Max MTOS_RigTools 의 Blender 버튼)",
    "description": "Max Rig Tools 버튼으로 가져오기·얼굴/가슴 본·헤어 본·치마/망토 본·스킨 적용을 Blender 에서 실행",
    "category": "Rigging",
}

import bpy, os, json, re, time, traceback

JOB_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "GE_RigJobs")
STALE = 8.0           # 하트비트가 이보다 오래되면 실행기가 없는 것으로 봄 (초)
_ME = {"on": False, "busy": False, "last": 0.0}
# 2.7: 실행기를 '작업자 / Claude' 로 나눔. 이 블렌더가 보내는 Max 포트(max_bridge.PORT)가 9878~9899 면 Claude 쪽.
#   Claude 쪽 블렌더는 Claude Max(9878~9899) 작업만, 작업자 블렌더는 그 밖의 포트(9877·9901~) 작업만 실행
#   (예전: runner.json 하나 → 작업자 블렌더가 Claude Max 작업을, Claude 블렌더가 작업자 작업을 돌릴 수 있었음).
#   Max 리그툴(rts_blAge)도 자기 포트 쪽 파일을 봄: 작업자 runner.json / Claude runner_claude.json


def _is_claude_port(p):
    try:
        return 9878 <= int(p) <= 9899
    except Exception:
        return False


def _my_claude():
    try:
        import max_bridge
        return _is_claude_port(max_bridge.PORT)
    except Exception:
        return False


def _runner_path():
    return os.path.join(JOB_DIR, "runner_claude.json" if _my_claude() else "runner.json")


def _job_port(path):
    try:
        return int(json.load(open(path, encoding="utf-8")).get("port", 0))
    except Exception:
        return None

STEP_NAMES = {"import": "① Max 에서 가져오기", "bones": "② 얼굴·가슴 본", "hair": "③ 헤어 본",
              "split": "① 파츠 나누기", "parts": "③ 파트 본 (치마·망토·기타)", "parts_edit": "③ 파트 Blender 에서 고치기", "skin": "④ 스킨 적용 (일괄)",
              "tplsave": "⑥ 리깅 완료 (템플릿 저장)"}
KIND_STEPS = {"import": ["import"], "bones": ["import", "bones"], "hair": ["import", "hair"],
              "split": ["import", "split"], "parts": ["import", "parts"], "parts_edit": ["import", "parts_edit"], "skin": ["import", "skin"], "tplsave": ["tplsave"],
              "all": ["import", "bones", "hair", "parts", "skin"]}


# ---------------------------------------------------------------- 실행기 자리 (하트비트)
def _read_runner():
    try:
        return json.load(open(_runner_path(), encoding="utf-8"))
    except Exception:
        return None


def _beat():
    d = {"pid": os.getpid(), "time": time.time(), "busy": _ME["busy"]}
    rp = _runner_path()
    tmp = rp + ".%d.tmp" % os.getpid()
    try:
        json.dump(d, open(tmp, "w", encoding="utf-8"))
        os.replace(tmp, rp)
    except Exception:
        pass


def _i_am_runner():
    r = _read_runner()
    if r is None or r.get("pid") == os.getpid() or time.time() - float(r.get("time", 0)) > STALE:
        _beat()
        return True
    return False


# ---------------------------------------------------------------- 도우미
def _ctx():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return dict(window=win, area=area, region=region)


def _status(jid, s):
    try:
        open(os.path.join(JOB_DIR, "st_%s.txt" % jid), "w", encoding="utf-8").write(s)
    except Exception:
        pass
    _beat()
    print("[GE 작업]", s)


def _flow():
    import sys
    return sys.modules.get("max_style_rig")


def _wm_status():
    try:
        return bpy.context.window_manager.msr_status
    except Exception:
        return ""


def _run_op(op, *a, **k):
    with bpy.context.temp_override(**_ctx()):
        if bpy.context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass
        r = op("EXEC_DEFAULT", *a, **k)
    return "FINISHED" in r


# ---------------------------------------------------------------- 단계
def _reset_model():
    """다른 모델(다른 Max 파일·포트)을 가져오기 전에 이전 모델의 흔적을 지움 (파츠·웨이트·가져온 오브젝트)"""
    sc = bpy.context.scene
    try:
        import object_bones
        with bpy.context.temp_override(**_ctx()):
            object_bones.clear(bpy.context, None)
    except Exception:
        traceback.print_exc()
    for k in list(sc.keys()):
        if k.startswith("msr_"):
            del sc[k]
    f = _flow()
    col = bpy.data.collections.get(getattr(f, "FLOW_COL", "FromMax"))
    objs = list(col.objects) if col else []
    objs += [o for o in bpy.data.objects if o.name.endswith("_이전")]
    for o in set(objs):
        try:
            bpy.data.objects.remove(o, do_unlink=True)
        except Exception:
            pass
    for blk in (bpy.data.meshes, bpy.data.armatures):
        for d in list(blk):
            if d.users == 0:
                blk.remove(d)


def _reset_if_new_model(job):
    """다른 Max 파일(또는 다른 Max)에서 온 작업이면 이전 모델의 가져온 물체·파트·웨이트 기록을 지움"""
    key = "%s|%s" % ((job or {}).get("file", ""), (job or {}).get("port", ""))
    sc = bpy.context.scene
    if sc.get("ge_model") == key:
        return False
    try:
        import object_bones
        with bpy.context.temp_override(**_ctx()):
            object_bones.clear(bpy.context, None)
    except Exception as e:
        print("[GE 작업] 조각 정리:", e)
    flow = _flow()
    col = bpy.data.collections.get(getattr(flow, "FLOW_COL", "FromMax")) if flow else None
    dead = list(col.objects) if col else []
    dead += [o for o in bpy.data.objects if o.name.endswith("_이전") or "_이전." in o.name]
    for o in set(dead):
        try:
            bpy.data.objects.remove(o)
        except Exception:
            pass
    for k in [k for k in sc.keys() if k.startswith("msr_")]:
        del sc[k]
    sc["ge_model"] = key
    return True


def step_import(mb, job=None):
    # Max: 보이는 메쉬(헬퍼 박스·지정점 제외) + Biped 전체를 선택
    if _reset_if_new_model(job):
        _reset_model()      # 2.5: 안 쓰는 메쉬·뼈대 데이터까지 (예전엔 아래 비교가 늘 같아 실행되지 않던 것)
        print("[GE 작업] 새 모델: 이전 상태를 정리했어요")
    n = mb.send(r'''(
clearSelection()
local ms = for o in geometry where not o.isHidden and classof o != Biped_Object and classof o != BoneGeometry and classof o != Box and \
	not (matchPattern o.name pattern:"sbg_*") and (canConvertTo o Editable_Mesh) collect o
select ms
for o in objects where classof o == Biped_Object and o.parent == undefined do selectMore o
((for o in selection where classof o == Biped_Object collect o).count as string) + "|" + (ms.count as string)
)''', timeout=60).strip().strip('"')
    nb, _, nm = n.partition("|")
    if nb in ("", "0"):
        raise RuntimeError("Max 에 Biped 가 없어요. Rig Tools [1.5 Biped 생성] 을 먼저 하세요.")
    if nm in ("", "0"):
        raise RuntimeError("Max 에 보이는 메쉬가 없어요.")
    if not _run_op(bpy.ops.msr.flow_import):
        raise RuntimeError("가져오기 실패: " + _wm_status())
    arm, body, face, tooth = _flow().flow_objects(bpy.context)
    return "가져옴: Bip %s · 바디 %s · 얼굴 %s · 이 %s" % (
        arm.name if arm else "없음", body.name if body else "없음", face.name if face else "없음", tooth.name if tooth else "없음")


def step_bones(mb, job=None):
    if not _run_op(bpy.ops.msr.flow_bones):
        raise RuntimeError("얼굴·가슴 본 실패: " + _wm_status())
    try:
        return bpy.context.window_manager.msr_bones_last or _wm_status()
    except Exception:
        return _wm_status()


def step_hair(mb, job=None):
    import hair_bones
    if hair_bones.hair_obj(bpy.context) is None:
        return "머리카락 메쉬가 없어 건너뜀"
    br = str((job or {}).get("branch", "BASIC") or "BASIC").upper()      # 1.62: Max 갈래 버튼 [기본]/[간단]
    if not _run_op(bpy.ops.msr.hair_generate, branch=br if br in ("BASIC", "SIMPLE") else "BASIC"):
        raise RuntimeError(_wm_status())
    return ("갈래 간단 (뒤 3갈래) | " if br == "SIMPLE" else "") + _wm_status()


def _read_parts(mb):
    import numpy as np
    txt = mb.send("rts_partData()", timeout=180).strip().strip('"')
    plist = []
    for line in txt.replace("\\n", "\n").split("\n"):
        f = line.split("|")
        if len(f) == 5 and f[0] == "none":           # 지운 파트 자리 (번호 유지)
            plist.append(("none", 0, 0, f[3], None))
            continue
        if len(f) != 5 or f[0] not in ("skirt", "cape", "etc", "auto") or not f[4]:
            continue
        P = np.array([[float(x) for x in t.split(",")] for t in f[4].strip(";").split(";") if t])
        plist.append((f[0], int(f[1]), int(f[2]), f[3], P))
    if not [q for q in plist if q[0] != "none"]:
        raise RuntimeError("지정한 파트가 없어요. Max 에서 바디 메쉬의 면을 선택하고 [Max 수정] 을 누르세요.")
    return plist


def step_split(mb, job=None):
    """① 파츠 나누기: 바디를 떨어진 조각으로 나눠 둠 (멜리타 바디면 멜리타 파츠·본까지 자동)"""
    import object_bones
    arm, body, face, tooth = _flow().flow_objects(bpy.context)
    if body is None:
        raise RuntimeError("바디 메쉬가 없어요.")
    auto = object_bones.is_preset_body(body)
    if not _run_op(bpy.ops.msr.ob_split, auto=auto):
        raise RuntimeError(_wm_status())
    if auto:
        return "멜리타 바디: " + _wm_status()
    import hair_bones
    pcs = object_bones.pieces()
    cnt = {"skirt": 0, "cape": 0}
    for o in pcs:
        k = object_bones.guess_kind(arm, [o]) if len(o.data.vertices) >= 30 else ""
        if k in cnt:
            cnt[k] += 1
    hair = hair_bones.hair_obj(bpy.context)
    return ("바디 %s → 조각 %d개 (치마 후보 %d · 망토 후보 %d) · 머리카락 메쉬 %s\n"
            "다음: ② [헤어 본] → ③ 치마·망토·기타는 [파트 추가] 로 지정하거나, 지정 없이 [파트 본 만들기] (자동 판별)"
            % (body.name, len(pcs), cnt["skirt"], cnt["cape"], hair.name if hair else "없음"))


def _noroot_apply(parts, job):
    """[root 본] 끔: root·_00 없이 체인을 작업자가 고른 부모 본에 붙임"""
    if not (job or {}).get("noroot"):
        return None
    par = (job or {}).get("parent") or ""
    for x in parts:
        x["no_root"] = True
        if par:
            x["parent_fix"] = par
    return par


def _noroot_reparent(mb, prefixes, par):
    """Max: root 없이 만든 파트 — 고른 부모 본에서 각 체인 첫 마디까지 _00 연결 본을 만들고 그 아래에 체인을 붙임.
    연결 본은 기존 규칙: 굵기 1×1, Display as Box 끔, Renderable 끔, 체인과 같은 레이어 (10/30)"""
    if not par or not prefixes:
        return
    pats = ",".join('"%s*"' % p for p in prefixes)
    mb.send(r'''(
local P = getNodeByName "%s" exact:true
local made = 0
if P != undefined do for pat in #(%s) do (
	local tops = for o in objects where classof o == BoneGeometry and matchPattern o.name pattern:pat and \
		(o.parent == undefined or not (matchPattern o.parent.name pattern:pat)) collect o
	for o in tops do (
		local nm = o.name
		local ln = if matchPattern nm pattern:"*_01" then ((substring nm 1 (nm.count - 3)) + "_00") else (nm + "_00")
		local old = getNodeByName ln exact:true
		if old != undefined do try (delete old) catch ()
		local a = P.transform.pos, b = o.transform.pos
		if distance a b < 0.01 then o.parent = P else (
			local d = normalize (b - a)
			local up = if abs d.z > 0.9 then [0,-1,0] else [0,0,1]
			local L = BoneSys.createBone a b up
			L.name = ln
			L.width = 1.0; L.height = 1.0; L.boxMode = false; L.renderable = false
			L.wirecolor = o.wirecolor
			o.layer.addNode L
			L.parent = P
			o.parent = L
			made += 1
		)
	)
)
made as string
)''' % (par, pats), timeout=60)


def _skip_summary(skipped, top=6):
    """recommend_parts 가 뺀 조각 → '이유: 개수' 몇 줄 (괄호 안 수치는 빼고 묶음)"""
    cnt = {}
    for _, why in skipped or []:
        k = re.sub(r"\s*\(.*$", "", str(why)).strip() or str(why)
        cnt[k] = cnt.get(k, 0) + 1
    if not cnt:
        return "(나눈 조각이 없어요)"
    rows = sorted(cnt.items(), key=lambda kv: -kv[1])
    s = "\n".join("- %s: %d개" % kv for kv in rows[:top])
    if len(rows) > top:
        s += "\n- 그 밖: %d개" % sum(v for _, v in rows[top:])
    return s


def step_parts(mb, job=None):
    """Max 에서 지정한 파트(Rig Tools 4_2 [파트 추가])가 있으면 그것으로,
    없으면 Blender [파츠 나누기] → 치마·망토 조각 자동 판별 → 본 (멜리타 바디면 멜리타 파츠 그대로)"""
    import object_bones
    del object_bones.LAST_MINI[:]
    try:
        plist = _read_parts(mb)
    except RuntimeError:
        plist = []
    inc = int((job or {}).get("inc", 0) or 0)       # Rig Tools [Max 수정]: 이 번호 파트만 다시 (다른 파트 본은 그대로)
    if inc and plist:
        mb.send("max create mode; clearSelection(); \"ok\"", timeout=30)
        with bpy.context.temp_override(**_ctx()):
            found = object_bones.marked_parts(bpy.context, plist)
            parts = object_bones.get_parts(bpy.context.scene)
            # 이미 Max 에 만든 파트는 그때 이름 그대로 (앞 파트를 지워도 bone_skirt2_ 가 bone_skirt_ 로 바뀌지 않게)
            try:
                old = mb.send('(local b = rts_pmBody(); if b == undefined then "" else (local s = getAppData b 7761; if s == undefined then "" else s))',
                              timeout=30).strip().strip('"').split("|")
            except Exception:
                old = []
            taken = {}
            for x in parts:
                pre = old[x["id"] - 1] if 0 < x["id"] <= len(old) else ""
                m = re.match(r"bone_(skirt\d*|cape\d*)_$", pre or "")
                if m and x.get("kind") and m.group(1).startswith(x["kind"]):
                    taken[x["id"]] = m.group(1)
            used = set(taken.values())
            for x in parts:
                if x["id"] in taken:
                    x["name"] = taken[x["id"]]
                elif x.get("kind"):
                    k = x["kind"]
                    x["name"] = next(nm for nm in [k] + [k + str(i) for i in range(2, 99)] if nm not in used)
                    used.add(x["name"])
            object_bones.set_parts(bpy.context.scene, parts)
        q = next((x for x in parts if x["id"] == inc), parts[-1])
        only = [object_bones.part_prefix(q)]
        nr_par = _noroot_apply([q], job)
        if nr_par is not None:
            with bpy.context.temp_override(**_ctx()):
                object_bones.set_parts(bpy.context.scene, parts)
        # 이 파트의 예전 본만 Max 에서 먼저 지움 (가운데 체인 구속·위치 컨트롤러를 풀고 한 번에 — 전체 만들기와 같은 방법)
        mb.send('(local d = for o in objects where matchPattern o.name pattern:"%s*" collect o\n'
                'for o in d do try (o.rotation.controller = Euler_XYZ(); o.position.controller = Position_XYZ()) catch ()\n'
                'for o in d where isValidNode o do try (delete o) catch ()\n'
                'd.count as string)' % only[0], timeout=60)
        if not _run_op(bpy.ops.msr.ob_generate, only=json.dumps(only), nocenter=bool((job or {}).get("magica"))):
            raise RuntimeError(_wm_status())
        if "Max 연결 없음" in _wm_status():
            raise RuntimeError("Max 에 본을 보내지 못했어요 (Max 연결 없음). | " + _wm_status())
        if nr_par:
            _noroot_reparent(mb, only, nr_par)
        if _wm_status().startswith("본 0개"):
            raise RuntimeError("본을 하나도 만들지 못했어요 (파트 위치를 계산하지 못함). 면을 다시 골라 보세요. | " + _wm_status())
        try:     # Max 본 목록: 파트 번호 → 본 이름 앞부분 (더블클릭으로 그 파트 면 선택)
            byid = {x["id"]: object_bones.part_prefix(x) for x in parts}
            mb.send("rts_obMapSet #(%s)" % ",".join('"%s"' % byid.get(i, "-") for i in range(1, max(byid) + 1)), timeout=30)
        except Exception as e:
            print("[GE 작업] 본 목록 기록:", e)
        return ("%d번 파트 %s 만 다시 만들었어요 (다른 파트 본은 그대로): " % (inc, object_bones._part_label(q)) + _wm_status()
                + "\n\n본을 미세 조정한 뒤, 다음 파트 면을 고르고 다시 누르세요. 만든 파트를 고치려면 그 면을 다시 고르고 누르면 돼요.")
    try:
        mb.send("max create mode; clearSelection(); \"ok\"", timeout=30)   # 선택·수정 패널이 본 생성을 막지 않게
        # 예전에 이 도구가 만든 파트 본(bone_skirt / bone_cape / bone_etc 레이어의 bone_skirt*·bone_cape*·bone_obj*) 정리
        mb.send('''(local d = for o in objects where (findItem #("bone_skirt", "bone_cape", "bone_etc", "bone_body", "nub") (toLower o.layer.name)) > 0 and \\
(matchPattern o.name pattern:"bone_skirt*" or matchPattern o.name pattern:"bone_cape*" or matchPattern o.name pattern:"bone_obj*") collect o
for o in d do try (o.rotation.controller = Euler_XYZ(); o.position.controller = Position_XYZ()) catch ()
for o in d where isValidNode o do try (delete o) catch ()
d.count as string)''', timeout=60)
    except Exception as e:
        # 2.7: 예전 본을 못 지운 채 계속하면 Max 에 같은 이름 본이 두 벌 생김 → 여기서 멈춤
        raise RuntimeError("Max 의 예전 파트 본을 지우지 못했어요 (Max 연결 확인): %s" % e)
    if plist:
        with bpy.context.temp_override(**_ctx()):
            found = object_bones.marked_parts(bpy.context, plist)
        how = "Max 지정 파트"
    else:
        arm, body, face, tooth = _flow().flow_objects(bpy.context)
        if body is not None and object_bones.is_preset_body(body):
            if not _run_op(bpy.ops.msr.ob_split, auto=True):
                raise RuntimeError(_wm_status())
            if "Max 연결 없음" in _wm_status():
                raise RuntimeError("Max 에 본을 보내지 못했어요 (Max 연결 없음). | " + _wm_status())
            return "멜리타 바디: 멜리타 파츠 그대로 | " + _wm_status()
        with bpy.context.temp_override(**_ctx()):
            object_bones.set_parts(bpy.context.scene, [])
            # 10/30: 치마·망토만이 아니라 바디 전체에서 본이 필요한 조각을 Blender 가 추천해서 모두 만듦
            jl = int((job or {}).get("level", 0) or 0)      # 1.61: Max 범위 버튼 [1·2·3] / Max [세컨더리 본 만들기] = 3
            if jl in (1, 2, 3):
                object_bones._LEVEL_NEXT = jl
            try:
                found, skipped = object_bones.recommend_parts(bpy.context)
            finally:
                if jl in (1, 2, 3):
                    object_bones._LEVEL_NEXT = 0
            lev = int(bpy.context.scene.get(object_bones.LEVEL_KEY, 0) or 0)
            retried = 0
            if not found and 0 < lev < 3:
                # 2.7: 범위 1·2 에서 본 붙일 조각이 하나도 없으면 범위 3(전부)으로 한 번 더 (0개일 때만)
                found, skipped = object_bones.recommend_parts(bpy.context, level=3)
                retried = lev
            parts = object_bones.get_parts(bpy.context.scene)
            nr_par = _noroot_apply(parts, job)
            if nr_par is not None:
                object_bones.set_parts(bpy.context.scene, parts)
        if not found:
            raise RuntimeError("본을 붙일 조각이 없어요 (조각을 모두 몸 웨이트로 뺐어요).\n" + _skip_summary(skipped)
                               + "\nMax 에서 바디 메쉬의 치마·망토 면을 고르고 [Max 수정] 을 누르세요.")
        how = "추천 (바디 전체: 본 붙일 파트 %d개 · 본 없이 둔 조각 %d개)" % (len(found), len(skipped))
        if retried:
            how = "범위 %d 에서 본 붙일 조각이 없어 범위 3(전부)으로 만들었어요. " % retried + how
    mini = sorted(set(getattr(object_bones, "LAST_MINI", [])))
    if mini:
        # 2.7: 짧은 치마(미니 치마) 조건으로 치마가 된 조각 — 잘못 잡혔으면 Max 에서 그 파트를 지우거나 종류를 바꾸면 됨
        how += " | 미니 치마로 판정한 조각 %d개 (%s)" % (len(mini), ", ".join(mini))
    if not _run_op(bpy.ops.msr.ob_generate, nocenter=bool((job or {}).get("magica"))):
        raise RuntimeError(_wm_status())
    if "Max 연결 없음" in _wm_status():
        raise RuntimeError("Max 에 본을 보내지 못했어요 (Max 연결 없음). | " + _wm_status())
    try:     # 본 목록 순서·색 = 파트 번호 (자동으로 만든 것도)
        allp = object_bones.get_parts(bpy.context.scene)
        byid = {x["id"]: object_bones.part_prefix(x) for x in allp}
        if byid and not plist:
            mb.send("rts_obMapSet #(%s)" % ",".join('"%s"' % byid.get(i, "-") for i in range(1, max(byid) + 1)), timeout=30)
            # 파트마다 쓴 바디 정점(Max 번호 = Blender 번호 + 1)을 Max 에 기록 → [Max 수정] 이 그 파트만 바꿀 수 있게 (10/30)
            pid = {x["id"]: x for x in allp}
            lines = []
            for i in range(1, max(byid) + 1):
                x = pid.get(i)
                objs = [bpy.data.objects.get(n) for n in (x or {}).get("pieces", [])]
                objs = [o for o in objs if o]
                if not x or not objs:
                    lines.append("none|0|0|")
                    continue
                vv = sorted({int(v) + 1 for o in objs for v in object_bones._vids(o)})
                lines.append("%s|%d|%d|%s" % (x.get("kind") or "etc", int(x.get("chains", 1)), int(x.get("segs", 3)), ",".join(map(str, vv))))
            mb.send('(rts_mkSetAll "%s")' % "\\n".join(lines), timeout=60)
    except Exception as e:
        print("[GE 작업] 본 목록 기록:", e)
    try:
        if (job or {}).get("noroot"):
            _noroot_reparent(mb, [object_bones.part_prefix(x) for x in object_bones.get_parts(bpy.context.scene)], (job or {}).get("parent"))
    except Exception as e:
        print("[GE 작업] 부모 붙이기:", e)
    if _wm_status().startswith("본 0개"):
        raise RuntimeError("본을 하나도 만들지 못했어요 (파트 위치를 계산하지 못함). Max 에서 면을 고르고 [Max 수정] 으로 다시 해 보세요. | " + _wm_status())
    msg = how + ": " + " / ".join(found) + " | " + _wm_status()
    _edit_view(focus=False)     # Blender 는 바로 고칠 수 있는 화면으로 둠 (앞으로는 안 나옴)
    return msg + "\n\nMax 에서 본을 검수하세요. 파츠 범위가 어긋나면 바디 메쉬에서 면을 고르고 [Max 수정]."


def _focus_blender():
    try:
        import ctypes
        u = ctypes.windll.user32
        h = u.FindWindowW("GHOST_WindowClass", None)
        if h:
            u.ShowWindow(h, 9)
            u.SetForegroundWindow(h)
    except Exception:
        pass


def _edit_view(focus=True):
    """Blender 화면을 파트 고치기 상태로: 조각 보이기 · 바디 숨기기 · 사이드바 ③ 파츠 본 > 직접 고치기 펼침"""
    import object_bones
    with bpy.context.temp_override(**_ctx()):
        wm = bpy.context.window_manager
        arm, body, face, tooth = _flow().flow_objects(bpy.context)
        if bpy.context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass
        pcs = object_bones.pieces()
        for o in list(bpy.context.view_layer.objects.selected):
            o.select_set(False)
        for o in pcs:
            o.hide_set(False)
        if body and pcs:
            body.hide_set(True)
        for a, v in (("msr_p4", "OB"), ("msr_ob_manual", True)):
            try:
                setattr(wm, a, v)
            except Exception:
                pass
        object_bones._CACHE.clear()
        if focus and pcs:
            for o in pcs:
                o.select_set(True)
            bpy.context.view_layer.objects.active = pcs[0]
            try:
                bpy.ops.view3d.view_selected()
            except Exception:
                pass
            for o in pcs:
                o.select_set(False)
    if focus:
        _focus_blender()


def step_parts_edit(mb, job=None):
    """[Blender 에서 고치기]: 지난번 [치마·망토 본 만들기] 의 파트가 Blender 에 있으면 그대로 보여 주고,
    없으면 (Max 지정 파트 → 멜리타 프리셋 → 자동 판별) 로 파트만 정해서 보여 줌. 본은 Blender [생성] 으로"""
    import object_bones
    sc = bpy.context.scene
    parts = object_bones.get_parts(sc)
    if not (parts and object_bones.pieces()):
        try:
            plist = _read_parts(mb)
        except RuntimeError:
            plist = []
        with bpy.context.temp_override(**_ctx()):
            arm, body, face, tooth = _flow().flow_objects(bpy.context)
            if body is None:
                raise RuntimeError("바디 메쉬가 없어요.")
            if plist:
                object_bones.marked_parts(bpy.context, plist)
            elif object_bones.is_preset_body(body):
                object_bones.split(bpy.context, body, bpy.context.window_manager.msr_ob_min)
                object_bones.load_preset(bpy.context, body)
            else:
                object_bones.set_parts(sc, [])
                object_bones.auto_parts(bpy.context)
        parts = object_bones.get_parts(sc)
    _edit_view(focus=True)
    found = ", ".join(object_bones._part_label(q) for q in parts) or "없음 (조각을 클릭해서 정하세요)"
    return ("파트: " + found + "\nBlender 창에서: 조각 클릭 → 종류·체인·마디를 바꾸면 노란 미리보기가 바로 바뀌어요 → [파트 확정] → [생성 (블렌더 웨이트 + Max 본)]."
            "\n만든 본은 이 Max 로 들어와요. Max 에서 다시 검수하세요.")


def step_skin(mb, job=None):
    if not _run_op(bpy.ops.msr.flow_apply_all):
        raise RuntimeError(_wm_status())
    st = _wm_status()
    if "바디 템플릿 건너뜀" in st:
        # 2.7: 템플릿을 못 쓰면 몸 웨이트가 거리 웨이트로 나감 → 결과 맨 앞에 주의로 보여 줌 (예전엔 긴 글 안에 묻힘)
        st = "주의: 바디 템플릿을 못 써서 몸 웨이트를 거리 기준으로 보냈어요 (팔꿈치·무릎·손가락 확인). | " + st
    return st


def step_tplsave(mb, job=None):
    import importlib, sys as _s
    d = os.path.dirname(os.path.abspath(__file__))
    if d not in _s.path:
        _s.path.insert(0, d)
    import rig_template
    return rig_template.step_tplsave(mb, job)


STEPS = {"tplsave": step_tplsave, "split": step_split, "import": step_import, "bones": step_bones, "hair": step_hair, "parts": step_parts, "parts_edit": step_parts_edit, "skin": step_skin}


def run_job(path, jid):
    job = json.load(open(path, encoding="utf-8"))
    import max_bridge
    port = int(job["port"])
    orig = max_bridge.send

    def send(code, timeout=300, port=None):
        return orig(code, timeout=timeout, port=port_)
    port_ = port
    out, ok = [], True
    t0 = time.time()
    max_bridge.send = send
    try:
        steps = KIND_STEPS.get(job.get("kind"), [])
        for i, s in enumerate(steps, 1):
            _status(jid, "%d/%d %s 중..." % (i, len(steps), STEP_NAMES[s]))
            try:
                out.append("%s: %s" % (STEP_NAMES[s], STEPS[s](max_bridge, job)))
            except Exception as e:
                traceback.print_exc()
                out.append("%s: 실패 - %s" % (STEP_NAMES[s], e))
                ok = False
                break
    finally:
        max_bridge.send = orig
        try:
            if _is_claude_port(port) == _is_claude_port(max_bridge.PORT):
                max_bridge.PORT = port      # 이후 Blender 패널 버튼도 이 Max 로 (2.7: 작업자 ↔ Claude 를 넘어가지는 않음)
        except Exception:
            pass
    _result(jid, ok, "\n".join(out), time.time() - t0)
    return ok


def _result(jid, ok, msg, sec=0):
    """res_<id>.txt: 1줄 OK/ERROR, 2줄 걸린 초, 나머지 메시지 (Max 가 읽음)"""
    tmp = os.path.join(JOB_DIR, "res_%s.tmp" % jid)
    open(tmp, "w", encoding="utf-8", newline="\n").write("%s\n%d\n%s" % ("OK" if ok else "ERROR", int(sec), msg))
    os.replace(tmp, os.path.join(JOB_DIR, "res_%s.txt" % jid))


def _tick():
    if not _ME["on"]:
        return None
    try:
        os.makedirs(JOB_DIR, exist_ok=True)
        if not _i_am_runner():
            return 2.0
        _beat()
        jobs = sorted(f for f in os.listdir(JOB_DIR) if f.startswith("job_") and f.endswith(".json"))
        mine = _my_claude()
        for f in jobs:
            src = os.path.join(JOB_DIR, f)
            jid = f[4:-5]
            jp = _job_port(src)
            if jp is None or _is_claude_port(jp) != mine:
                continue                         # 2.7: 다른 쪽(작업자 ↔ Claude) Max 의 작업은 그쪽 블렌더가
            run = os.path.join(JOB_DIR, "run_%s.json" % jid)
            try:
                os.replace(src, run)             # 집기
            except Exception:
                continue
            _ME["busy"] = True
            try:
                run_job(run, jid)
            except Exception as e:
                traceback.print_exc()
                _result(jid, False, "작업 오류: %s" % e)
            finally:
                _ME["busy"] = False
                try:
                    os.remove(run)
                except Exception:
                    pass
                _beat()
            break
    except Exception:
        traceback.print_exc()
    return 1.0


def register():
    _ME["on"] = True
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=2.0, persistent=True)


def unregister():
    _ME["on"] = False
    try:
        if bpy.app.timers.is_registered(_tick):
            bpy.app.timers.unregister(_tick)
    except Exception:
        pass
