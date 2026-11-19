r"""standardize.py  -  one-button "make this Max character standard" pipeline   (v1.0, 2026-10-17)

Runs from Blender (Max Bridge panel > Standardize) against the .max file currently open in 3ds Max 2014.
The original .max is never modified: the result is saved as  <out_dir>\<name>_standard.max

Steps
  0  safety: Max file must be saved (no unsaved changes)
  1  rig check BEFORE  (MaxBridge.checkRig)
  2  dump original weights of every skinned mesh (by bone name)
  3  original deformation in the bind pose and under the fixed test pose (then reload the original)
  4  save a copy  ->  <name>_standard.max
  5  follower bones (B_...) for every problem skin bone: helper class / mirrored / dirty parent chain
  6  rebuild every Skin with the original weights renamed to the followers (same bind pose for all)
  7  Nub bones on skin-bone chain ends, save, rig check AFTER
  8  verify in Max: standard deforms exactly like the original (test pose)
  9  verify in Blender: bind + posed FBX vs Max vertex positions; bones that still break in Blender
     get a follower automatically (up to 2 extra rounds)
 10  report  ->  <run_dir>\report.txt   (+ JSON with every number, for later improvement)
"""
import bpy, os, re, json, time, traceback
import numpy as np
import max_bridge as mb

VERSION = "1.0"
OUT_DIR = r"C:\claude\max_blender\standardized"
TOL_MAX = 0.01      # inches, Max standard vs original
TOL_BLENDER = 0.1   # inches, Blender vs Max
UNIT_TO_IN = {"in": 1.0, "cm": 1 / 2.54, "mm": 1 / 25.4, "m": 39.3701, "ft": 12.0}


class Run:
    def __init__(self, progress=None):
        self.progress = progress or (lambda msg: print("[standardize]", msg))
        self.lines = []
        self.data = {"version": VERSION, "started": time.strftime("%Y-%m-%d %H:%M:%S")}

    def log(self, msg):
        self.lines.append(msg)
        self.progress(msg)

    def ms(self, code, timeout=600):
        r = mb.send(code, timeout=timeout)
        if r.startswith("ERROR"):
            raise RuntimeError("Max: " + r)
        return r


def _p(path):
    return '@"' + path.replace('"', "") + '"'


def read_weights(path, rename=None):
    out = []
    for l in open(path, encoding="utf-8-sig", errors="replace").read().split("\n")[:-1]:
        d = {}
        for t in l.split("\t"):
            if "=" in t:
                k, w = t.rsplit("=", 1)
                if rename:
                    k = rename.get(k, k)
                d[k] = d.get(k, 0.0) + float(w)
        out.append(d)
    return out


def write_apply_file(W, path):
    names = sorted({k for d in W for k in d})
    idx = {n: i for i, n in enumerate(names)}
    with open(path, "w", encoding="utf-8") as f:
        f.write("#BONES\t" + "\t".join(names) + "\n")
        for d in W:
            f.write(" ".join("%d:%.6f" % (idx[k], w) for k, w in d.items()) + "\n")


def read_deform(path):
    data, cur = {}, None
    for line in open(path, encoding="utf-8-sig"):
        if line.startswith("#"):
            n, t, c = line[1:].rstrip("\n").split("\t")
            cur = (n, int(t))
            data[cur] = []
        elif line.strip():
            data[cur].append([float(v) for v in line.split()])
    return {k: np.array(v) for k, v in data.items()}


def follower_name(name, cls, midx, taken):
    base = name.replace(" ", "_")
    for pre in ("NBone_", "Bone_", "Box_", "Dummy_", "Point_", "Bip01_"):
        if base.startswith(pre):
            base = base[len(pre):]
            break
    base = re.sub(r"_+", "_", base).strip("_")
    new = "B_" + ("Vol_" if cls == "Box" else "") + base
    side = re.search(r"(^|_)(L|R)(_|$|\d)", new)
    if side:  # fix wrong side labels using the real position (character's left = +X)
        s = side.group(2)
        if s == "L" and midx < -0.5:
            new = new[: side.start(2)] + "R" + new[side.end(2):]
        elif s == "R" and midx > 0.5:
            new = new[: side.start(2)] + "L" + new[side.end(2):]
    while new in taken:
        new += "_S"
    taken.add(new)
    return new


# ---------------------------------------------------------------------------------------------- Blender check
def blender_compare(run, fbx, maxdump, frames, sc_in, anim, keep_scene=None):
    """import FBX into a temp scene, compare evaluated meshes with the Max dump (Max units).
    sc_in = Max unit -> inch.  returns {(mesh,frame): (max_in, mean_in, bad_idx)}"""
    to_max = 1.0 / (0.0254 * sc_in)  # Blender metres -> Max units
    main = bpy.context.window.scene
    sc = bpy.data.scenes.new("_std_check")
    bpy.context.window.scene = sc
    res = {}
    try:
        before = set(bpy.data.objects.keys())
        bpy.ops.import_scene.fbx(filepath=fbx, use_anim=anim, anim_offset=0.0, automatic_bone_orientation=True,
                                 ignore_leaf_bones=False, use_custom_normals=True)
        new = [o for o in bpy.data.objects if o.name not in before]
        D = read_deform(maxdump)
        mnames = {k[0] for k in D}
        meshes = {}
        for o in new:
            if o.type == "MESH":
                base = re.sub(r"\.\d{3}$", "", o.name)
                if base in mnames:
                    meshes[base] = o
        for t in frames:
            sc.frame_set(t)
            dg = bpy.context.evaluated_depsgraph_get()
            for n, ob in meshes.items():
                ev = ob.evaluated_get(dg)
                me = ev.to_mesh()
                B = np.array([(ev.matrix_world @ v.co)[:] for v in me.vertices]) * to_max
                ev.to_mesh_clear()
                M = D[(n, t)]
                if len(M) != len(B):
                    res[(n, t)] = (float("inf"), float("inf"), [])
                    continue
                d = np.linalg.norm(M - B, axis=1) * sc_in
                res[(n, t)] = (float(d.max()), float(d.mean()), list(np.where(d > TOL_BLENDER)[0]))
    finally:
        bpy.context.window.scene = main
        if keep_scene:
            sc.name = keep_scene
        else:
            for o in list(sc.objects):
                if len(o.users_scene) == 1:
                    bpy.data.objects.remove(o)
            bpy.data.scenes.remove(sc)
            for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.actions, bpy.data.materials):
                for d in list(coll):
                    if d.users == 0:
                        coll.remove(d)
    return res


# ---------------------------------------------------------------------------------------------- pipeline
def standardize(progress=None, keep_blender_scene=True):
    run = Run(progress)
    t_start = time.time()
    ms = run.ms
    try:
        # 0 ------------------------------------------------------------ safety
        orig_path = ms('maxFilePath + maxFileName')
        if not orig_path:
            raise RuntimeError("Max에 열린 파일이 없어요. 캐릭터 .max 파일을 열어 주세요.")
        if ms('getSaveRequired() as string') == "true":
            raise RuntimeError("Max 파일에 저장 안 된 변경사항이 있어요. 저장하거나 되돌린 뒤 다시 눌러 주세요.")
        name = os.path.splitext(os.path.basename(orig_path))[0]
        rd = os.path.join(OUT_DIR, name + "_run_" + time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(rd, exist_ok=True)
        std_path = os.path.join(OUT_DIR, name + "_standard.max")
        unit = json.loads(mb.send("MaxBridge.info maxObjects:0"))["system_unit"]
        sc_in = UNIT_TO_IN.get(unit, 1.0)  # Max units -> inch
        run.data.update(original=orig_path, standard=std_path, run_dir=rd, unit=unit)
        run.log("원본: %s (단위 %s)" % (orig_path, unit))

        # 1 ------------------------------------------------------------ check before
        r = ms('MaxBridge.checkRig outPath:%s' % _p(os.path.join(rd, "check_before.txt")))
        run.data["check_before"] = r.split("\n")[0]
        run.log("검사(전): " + r.split("\n")[0])

        # 2 ------------------------------------------------------------ dump original weights
        meshes = [m for m in ms("MaxBridge.skinnedNames()").split("\t") if m]
        if not meshes:
            raise RuntimeError("Skin이 걸린 메쉬가 없어요.")
        for m in meshes:
            ms('MaxBridge.dumpSkinNamed "%s" %s' % (m, _p(os.path.join(rd, "w_orig_%s.txt" % m))))
        ms('max create mode; 1')
        run.log("원본 웨이트 저장: 메쉬 %d개" % len(meshes))
        ml = "#(" + ",".join('"%s"' % m for m in meshes) + ")"

        # 3 ------------------------------------------------------------ original deformation
        ms('MaxBridge.testPose()')
        ms('MaxBridge.dumpDeform %s #(50) %s' % (ml, _p(os.path.join(rd, "def_orig_pose.txt"))))
        ms('loadMaxFile %s quiet:true; 1' % _p(orig_path))
        run.log("원본 테스트 포즈 기록")

        # 4 ------------------------------------------------------------ copy
        os.makedirs(OUT_DIR, exist_ok=True)
        ms('saveMaxFile %s quiet:true; 1' % _p(std_path))
        run.log("사본 저장: " + std_path)

        # 5 ------------------------------------------------------------ followers
        mapping = {}
        taken = set(ms('s = ""; for o in objects do s += o.name + "\\t"; s').split("\t"))

        def add_followers(rows):
            made = []
            for row in rows:
                n, reasons, midx, cls = row
                if n in mapping:
                    continue
                newn = follower_name(n, cls, float(midx), taken)
                r = ms('MaxBridge.makeFollower "%s" "%s"' % (n, newn))
                mapping[n] = newn
                made.append((n, newn, reasons))
                run.log("  팔로워 %s <- %s (%s)" % (newn, n, reasons))
            return made

        probs = [l.split("\t") for l in ms("MaxBridge.problemInfluences()").split("\n") if l.strip()]
        made = add_followers(probs)
        run.log("문제 스킨 본 %d개 -> 팔로워 생성" % len(made))

        # 6 ------------------------------------------------------------ rebuild skins
        def rebuild_skins():
            for m in meshes:
                W = read_weights(os.path.join(rd, "w_orig_%s.txt" % m), mapping)
                f = os.path.join(rd, "w_std_%s.txt" % m)
                write_apply_file(W, f)
                ms('MaxBridge.applyWeights "%s" %s' % (m, _p(f)))

        rebuild_skins()
        run.log("Skin 재구성(원본 웨이트 그대로, 전 메쉬 같은 자세에서 바인드)")

        # 7 ------------------------------------------------------------ nubs + check after
        nn = ms("MaxBridge.addNubs()")
        ms('saveMaxFile %s quiet:true; 1' % _p(std_path))
        run.log("Nub 추가 %s개, 저장" % nn)

        # 8 + 9 -------------------------------------------------------- verify (Max, then Blender), auto-fix rounds
        prefix = ms("MaxBridge.bipedPrefix()")
        for rnd in range(3):
            # Max: standard vs original under the test pose
            ms('MaxBridge.dumpDeform %s #(0) %s' % (ml, _p(os.path.join(rd, "def_std_bind.txt"))))
            fbx_bind = os.path.join(rd, "std_bind.fbx")
            ms('MaxBridge.exportFBX %s selOnly:false anim:false' % _p(fbx_bind))
            ms('MaxBridge.testPose()')
            ms('MaxBridge.dumpDeform %s #(25,50) %s' % (ml, _p(os.path.join(rd, "def_std_pose.txt"))))
            fbx_pose = os.path.join(rd, "std_pose.fbx")
            ms('MaxBridge.exportFBX %s selOnly:false anim:true' % _p(fbx_pose), timeout=900)
            ms('loadMaxFile %s quiet:true; 1' % _p(std_path))

            O = read_deform(os.path.join(rd, "def_orig_pose.txt"))
            S = read_deform(os.path.join(rd, "def_std_pose.txt"))
            max_err = {m: float(np.linalg.norm(O[(m, 50)] - S[(m, 50)], axis=1).max()) for m in meshes}
            run.data["max_vs_original_in"] = {m: round(v * sc_in, 4) for m, v in max_err.items()}
            run.log("Max 검증(원본 대비, 테스트 포즈): 최대 %.4f인치" % (max(max_err.values()) * sc_in))

            # Blender: bind pose and posed animation (frame 0 of animated FBX is skipped: helper lag)
            rb = blender_compare(run, fbx_bind, os.path.join(rd, "def_std_bind.txt"), [0], sc_in, False)
            rp = blender_compare(run, fbx_pose, os.path.join(rd, "def_std_pose.txt"), [25, 50], sc_in, True)
            worst = {}
            bad_verts = {}
            for res in (rb, rp):
                for (m, t), (mx, mean, bad) in res.items():
                    worst[m] = max(worst.get(m, 0.0), mx)
                    if bad:
                        bad_verts.setdefault(m, set()).update(bad)
            run.data.setdefault("blender_rounds", []).append({m: round(v, 4) for m, v in worst.items()})
            run.log("블렌더 검증 %d회차: 최대 %.3f인치" % (rnd + 1, max(worst.values()) if worst else -1))
            if not bad_verts:
                break
            # bones that still break in Blender: non-Biped, not yet followers, carrying weight on the bad vertices
            from collections import Counter
            cnt = Counter()
            for m, idxs in bad_verts.items():
                W = read_weights(os.path.join(rd, "w_orig_%s.txt" % m), mapping)
                for i in idxs:
                    for k, w in W[i].items():
                        if w > 0.05 and not k.startswith(prefix) and not k.startswith("B_"):
                            cnt[k] += 1
            cand = [k for k, c in cnt.most_common() if c >= 3]
            if not cand or rnd == 2:
                run.log("  남은 문제 정점: %s" % {m: len(v) for m, v in bad_verts.items()})
                break
            info = [l.split("\t") for l in ms(
                's = ""; for n in #(%s) do (o = getNodeByName n; sg = MaxBridge.boneSeg o; s += n + "\\t" + "flip" + "\\t" + (((sg[1]+sg[2])/2.0).x as string) + "\\t" + ((classOf o) as string) + "\\n"); s'
                % ",".join('"%s"' % k for k in cand)).split("\n") if l.strip()]
            run.log("  블렌더에서만 틀어지는 본 %d개 -> 팔로워 추가" % len(info))
            add_followers(info)
            rebuild_skins()
            ms('MaxBridge.addNubs(); saveMaxFile %s quiet:true; 1' % _p(std_path))

        r = ms('MaxBridge.checkRig outPath:%s' % _p(os.path.join(rd, "check_after.txt")))
        run.data["check_after"] = r.split("\n")[0]
        run.log("검사(후): " + r.split("\n")[0])
        ms('saveMaxFile %s quiet:true; 1' % _p(std_path))

        # keep a Blender scene with the standard character + Biped test controls for inspection
        if keep_blender_scene:
            sc_name = name + "_STANDARD"
            old = bpy.data.scenes.get(sc_name)
            if old:
                for o in list(old.objects):
                    if len(o.users_scene) == 1:
                        bpy.data.objects.remove(o)
                bpy.data.scenes.remove(old)
            blender_compare(run, fbx_bind, os.path.join(rd, "def_std_bind.txt"), [0], sc_in, False, keep_scene=sc_name)
            try:
                import biped_test_rig as bt
                sc = bpy.data.scenes[sc_name]
                main = bpy.context.window.scene
                bpy.context.window.scene = sc
                arm = [o for o in sc.objects if o.type == "ARMATURE"][0]
                for o in sc.objects:
                    if o.type == "EMPTY" or o.name.startswith(("Box_", "Point")):
                        o.hide_set(True)
                bpy.ops.object.select_all(action="DESELECT")
                arm.select_set(True)
                bpy.context.view_layer.objects.active = arm
                bt.build_test_rig(arm)
                bt.make_rom(arm)
                bpy.ops.object.mode_set(mode="OBJECT")
                sc.frame_set(0)
                bpy.context.window.scene = main
                run.log("블렌더 확인용 씬: %s (Biped Test 컨트롤러 포함)" % sc_name)
            except Exception as e:
                run.log("블렌더 확인용 씬 컨트롤러 생략: %s" % e)
        run.data["mapping"] = mapping
        run.data["seconds"] = round(time.time() - t_start, 1)
        run.data["ok"] = True
        run.log("완료 (%.0f초) -> %s" % (time.time() - t_start, std_path))
    except Exception as e:
        run.data["ok"] = False
        run.data["error"] = str(e)
        run.data["traceback"] = traceback.format_exc()
        run.log("실패: " + str(e))
    finally:
        rd = run.data.get("run_dir")
        if rd:
            with open(os.path.join(rd, "report.txt"), "w", encoding="utf-8-sig") as f:
                f.write("Standardize v%s  %s\n\n" % (VERSION, run.data["started"]))
                f.write("\n".join(run.lines) + "\n")
            with open(os.path.join(rd, "report.json"), "w", encoding="utf-8") as f:
                json.dump(run.data, f, ensure_ascii=False, indent=1, default=str)
    return run
