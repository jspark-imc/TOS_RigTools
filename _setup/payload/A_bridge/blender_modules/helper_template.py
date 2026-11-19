"""Helper / secondary-bone templates for Biped characters (3ds Max 2014, via MaxBridge).

extract(names, out_json)   - run while the TEMPLATE character (e.g. Ivelar standard) is open in Max.
apply(template_json, ...)  - run while the TARGET character (Biped already fitted, figure mode) is open.

Positions are stored relative to the parent and scaled per Biped segment length
(e.g. a knee helper on the Thigh scales with thigh length). Constraints are rebuilt by name.
"""
import json, os, re
import max_bridge as mb

TEMPLATE_DIR = r"C:\claude\max_blender\templates"

# first version scope: knee / elbow / shoulder volume helpers + thigh / calf secondary bones
LIMB_SET = [
    # legs L
    "Point_L Thigh", "Bone_L Thigh", "Bone_L Thigh_Nub", "Point_leg_L", "Point_up_L", "Box_Knee_L",
    "Point_L Calf", "Bone_L Calf", "Bone_L Calf_Nub", "Point_dn_L",  # Point_* Calf: knee spread control
    # legs R
    "Point_R Thigh", "Bone_R Thigh", "Bone_R Thigh_Nub", "Point_leg_R", "Point_up_R", "Box_Knee_R",
    "Point_R Calf", "Bone_R Calf", "Bone_R Calf_Nub", "Point_dn_R",
    # elbows
    "Point_elbowL_dn", "Point_elbowL_up", "Box_elbow_L",
    "Point_elbowR_dn", "Point_elbowR_up", "Box_elbow_R",
    # shoulders L (Point002 -> Point001 -> Point003 drive the two boxes)
    "Point002", "Point001", "Point003", "Box_ Clavicle_L_01", "Box_UpperArm_L_002",
    # shoulders R
    "Point005", "Point004", "Point006", "Box_ Clavicle_R_01", "Box_UpperArm_L_003",
]

# Biped part -> the joint its length is measured to
SEG_NEXT = {"Clavicle": "UpperArm", "UpperArm": "Forearm", "Forearm": "Hand", "Thigh": "Calf", "Calf": "Foot",
            "Pelvis": "Spine", "Spine": "Spine1", "Spine1": "Spine2", "Spine2": "Neck", "Neck": "Head"}

MS_COMMON = r'''
fn _nn n = if n == undefined then "-" else n.name
fn _f v = (formattedPrint v format:".6g")
fn _bipPrefix = (local r = for o in objects where classOf o == Biped_Object and o.parent == undefined collect o; if r.count > 0 then r[1].name else "Bip01")
fn _bipAnc o = (local p = o.parent; while p != undefined and classOf p != Biped_Object do p = p.parent; p)
fn _part o pre = (if o == undefined then "" else substituteString o.name (pre + " ") "")
'''

MS_EXTRACT = MS_COMMON + r'''
fn _tg c = (local s = ""; for i = 1 to c.getNumTargets() do (if s != "" do s += "|"; s += (_nn (c.getNode i)) + ":" + (_f (c.getWeight i))); s)
fn _line o pre = (
  local s = "N=" + o.name + "\tC=" + (classof o) as string + "\tP=" + (_nn o.parent)
  local a = _bipAnc o
  s += "\tA=" + (_part a pre)
  local L = o.transform * inverse o.parent.transform
  s += "\tM="
  for r in #(L.row1, L.row2, L.row3, L.row4) do s += (_f r.x) + "," + (_f r.y) + "," + (_f r.z) + ","
  local c = o.controller
  local pc = c.position.controller, rc = c.rotation.controller
  s += "\tPT=" + (classof pc) as string
  if classof pc == Position_Expression do s += "\tPE=" + (pc.getExpression())
  s += "\tRT=" + (classof rc) as string
  if classof rc == Orientation_Constraint do s += "\tTG=" + (_tg rc) + "\tREL=" + rc.relative as string + "\tLW=" + rc.local_world as string
  if classof rc == LookAt_Constraint do s += "\tTG=" + (_tg rc) + "\tREL=" + rc.relative as string + "\tTAX=" + rc.target_axis as string + "\tTAF=" + (try (rc.target_axisFlip as string) catch "false") + "\tUPW=" + rc.upnode_world as string + "\tUPN=" + (_nn rc.pickUpNode) + "\tUPC=" + rc.upnode_ctrl as string + "\tSUP=" + rc.StoUP_axis as string + "\tSUF=" + (try (rc.StoUP_axisFlip as string) catch "false") + "\tUPA=" + rc.upnode_axis as string
  case classof o of (
    Box: s += "\tDIM=" + (_f o.length) + "," + (_f o.width) + "," + (_f o.height)
    Point: s += "\tDIM=" + (_f o.size) + "," + o.cross as string + "," + o.box as string + "," + o.axistripod as string + "," + o.centermarker as string
    BoneGeometry: s += "\tDIM=" + (_f o.length) + "," + (_f o.width) + "," + (_f o.height) + "," + (_f o.taper) + "," + o.sidefins as string + "," + o.frontfin as string + "," + o.backfin as string
    default: ()
  )
  s += "\tWC=" + (o.wirecolor.r as integer) as string + "," + (o.wirecolor.g as integer) as string + "," + (o.wirecolor.b as integer) as string
  s += "\tLAY=" + o.layer.name + "\tBE=" + o.boneEnable as string + "\tREN=" + o.renderable as string
  s
)
fn _seg o pre nxt = (local n = getNodeByName (pre + " " + nxt); if o == undefined or n == undefined then 0.0 else distance o.transform.row4 n.transform.row4)
'''


def _ms_list(names):
    return "#(" + ",".join('"%s"' % n.replace('"', '') for n in names) + ")"


def extract(names=None, out_json=None, name="limb_helpers"):
    names = names or LIMB_SET
    out_json = out_json or os.path.join(TEMPLATE_DIR, name + ".json")
    seg_ms = "".join('out += "SEG\\t%s\\t" + (_f (_seg (getNodeByName (pre + " %s")) pre "%s")) + "\\n"\n' % (s, s, t)
                     for side in ("", "L ", "R ") for s0, t0 in SEG_NEXT.items()
                     for s, t in [((side + s0), (side + t0))]
                     if (side == "") == (s0 in ("Pelvis", "Spine", "Spine1", "Spine2", "Neck")))
    code = "(\n" + MS_EXTRACT + r'''
local pre = _bipPrefix()
sliderTime = 0
local out = "SRC\t" + maxFilePath + maxFileName + "\tunits=" + (units.SystemType as string) + "\tfigure=" + (try ((getNodeByName pre).controller.figureMode as string) catch "?") + "\n"
for n in %s do (local o = getNodeByName n exact:true; if o == undefined then out += "MISSING\t" + n + "\n" else out += (_line o pre) + "\n")
for o in objects where classof o.controller == transform_script do (
  local h = try (o.controller.getNode "H") catch undefined
  if h != undefined and findItem %s h.name > 0 do out += "FOL\t" + o.name + "\t" + h.name + "\t" + (classof o) as string + "\n"
)
%s
out
)''' % (_ms_list(names), _ms_list(names), seg_ms)
    r = mb.send(code, timeout=120)
    if r.startswith("ERROR"):
        raise RuntimeError(r)
    tpl = {"source": "", "nodes": [], "followers": [], "seg": {}, "missing": []}
    for line in r.splitlines():
        if not line.strip():
            continue
        if line.startswith("SRC\t"):
            tpl["source"] = line[4:]
        elif line.startswith("MISSING\t"):
            tpl["missing"].append(line.split("\t")[1])
        elif line.startswith("FOL\t"):
            _, new, src, cls = line.split("\t")
            tpl["followers"].append({"name": new, "src": src})
        elif line.startswith("SEG\t"):
            _, part, v = line.split("\t")
            tpl["seg"][part] = float(v)
        elif line.startswith("N="):
            d = dict(kv.split("=", 1) for kv in line.split("\t"))
            n = {"name": d["N"], "class": d["C"], "parent": d["P"], "bip": d["A"],
                 "m": [float(x) for x in d["M"].strip(",").split(",")],
                 "pos": d["PT"], "rot": d["RT"], "wire": [int(x) for x in d["WC"].split(",")],
                 "layer": d["LAY"], "boneEnable": d["BE"] == "true", "renderable": d["REN"] == "true"}
            if "PE" in d: n["expr"] = d["PE"]
            if "DIM" in d: n["dim"] = d["DIM"].split(",")
            if "TG" in d:
                n["targets"] = [[t.rsplit(":", 1)[0], float(t.rsplit(":", 1)[1])] for t in d["TG"].split("|") if t]
                n["relative"] = d["REL"] == "true"
            if "LW" in d: n["local_world"] = int(d["LW"])
            for k in ("TAX", "TAF", "UPW", "UPN", "UPC", "SUP", "SUF", "UPA"):
                if k in d: n.setdefault("lookat", {})[k] = d[k]
            tpl["nodes"].append(n)
    # followers hang their own Nub
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(tpl, f, indent=1, ensure_ascii=False)
    return tpl


# ---------------------------------------------------------------- apply
def _q(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _target_seg(pre, parts):
    seg_ms = "".join('out += "%s\\t" + (_f (_seg (getNodeByName (pre + " %s")) pre "%s")) + "\\n"\n' % (p, p, " ".join(p.split(" ")[:-1] + [SEG_NEXT[p.split(" ")[-1]]]))
                     for p in parts)
    code = "(\n" + MS_EXTRACT + "\nlocal pre = _bipPrefix()\nlocal out = \"PRE\\t\" + pre + \"\\n\"\n" + seg_ms + "out\n)"
    r = mb.send(code, timeout=60)
    if r.startswith("ERROR"):
        raise RuntimeError(r)
    d = {}
    for line in r.splitlines():
        if "\t" in line:
            k, v = line.split("\t", 1)
            d[k] = v if k == "PRE" else float(v)
    return d


def apply(template_json=None, save_as=None, replace=False, log=print):
    """Build the template's helpers onto the Biped in the open Max scene. Returns a report dict."""
    template_json = template_json or os.path.join(TEMPLATE_DIR, "limb_helpers.json")
    tpl = json.load(open(template_json, encoding="utf-8"))
    nodes = tpl["nodes"]
    names = {n["name"] for n in nodes}
    parts = sorted({n["bip"] for n in nodes if n["bip"]})
    tseg = _target_seg("", parts)
    pre = tseg.pop("PRE")
    ratio = {}
    for p in parts:
        a, b = tpl["seg"].get(p, 0.0), tseg.get(p, 0.0)
        ratio[p] = (b / a) if a > 1e-6 and b > 1e-6 else 1.0
    log("segment ratios: " + ", ".join("%s=%.3f" % kv for kv in ratio.items()))

    def mapname(n):
        if n in names or n == "-":
            return n
        return re.sub(r"^Bip\d+", pre, n)

    # order so parents come first
    order, done = [], set()
    while len(order) < len(nodes):
        before = len(order)
        for n in nodes:
            if n["name"] in done:
                continue
            if n["parent"] not in names or n["parent"] in done:
                order.append(n); done.add(n["name"])
        if len(order) == before:
            raise RuntimeError("parent loop in template")

    L = []
    L.append("(\nlocal pre = %s\nlocal made = 0\nlocal skipped = #()" % _q(pre))
    L.append("sliderTime = 0")
    L.append("fn _res n = (local o = getNodeByName n exact:true; if o == undefined do o = getNodeByName (substituteString (substituteString n \"ForeTwist\" \"Forearm\") \"CalfTwist\" \"Calf\") exact:true; if o == undefined do append skipped (\"target:\" + n); o)")
    L.append("fn _lay n = (local l = LayerManager.getLayerFromName n; if l == undefined do l = LayerManager.newLayerFromName n; l)")
    if replace:
        L.append("for n in %s do (local o = getNodeByName n exact:true; if o != undefined do delete o)" %
                 _ms_list([n["name"] for n in nodes][::-1] + [f["name"] for f in tpl["followers"]] + [f["name"] + "_Nub" for f in tpl["followers"]]))
    for n in order:
        r = ratio.get(n["bip"], 1.0)
        m = n["m"]
        pos = [m[9] * r, m[10] * r, m[11] * r]
        par = mapname(n["parent"])
        nm = n["name"]
        cls = n["class"]
        dim = n.get("dim", [])
        L.append("if getNodeByName %s exact:true != undefined then append skipped %s else (" % (_q(nm), _q(nm)))
        L.append("  local par = getNodeByName %s exact:true" % _q(par))
        if cls == "Point":
            L.append("  local o = Point size:%g cross:%s box:%s axistripod:%s centermarker:%s" % (float(dim[0]) * r, dim[1], dim[2], dim[3], dim[4]))
        elif cls == "Box":
            L.append("  local o = Box length:%g width:%g height:%g" % (float(dim[0]) * r, float(dim[1]) * r, float(dim[2]) * r))
        elif cls == "BoneGeometry":
            L.append("  local o = BoneSys.createBone [0,0,0] [%g,0,0] [0,0,1]" % (float(dim[0]) * r))
            L.append("  o.width = %g; o.height = %g; o.taper = %g; o.sidefins = %s; o.frontfin = %s; o.backfin = %s"
                     % (float(dim[1]) * r, float(dim[2]) * r, float(dim[3]), dim[4], dim[5], dim[6]))
        else:
            L.append("  local o = Dummy()")
        L.append("  o.name = %s" % _q(nm))
        L.append("  o.wirecolor = color %d %d %d; o.renderable = %s" % (n["wire"][0], n["wire"][1], n["wire"][2], str(n["renderable"]).lower()))
        L.append("  (_lay %s).addNode o" % _q(n["layer"]))
        L.append("  o.parent = par")
        L.append("  o.transform = (matrix3 [%g,%g,%g] [%g,%g,%g] [%g,%g,%g] [%g,%g,%g]) * par.transform"
                 % tuple(m[:9] + pos))
        L.append("  o.boneEnable = %s" % str(n["boneEnable"]).lower())
        L.append("  made += 1\n)")
    # constraints after every node exists
    rep_lines = []
    for n in order:
        nm = n["name"]
        r = ratio.get(n["bip"], 1.0)
        L.append("(local o = getNodeByName %s exact:true" % _q(nm))
        L.append("if o != undefined and findItem skipped o.name == 0 do (")
        L.append("  local W = o.transform")
        if n["pos"] == "Position_Expression" and n.get("expr"):
            vals = [float(x) * r for x in re.findall(r"[-\d\.e]+", n["expr"])[:3]]
            if len(vals) == 3:
                L.append("  local pe = Position_Expression(); pe.setExpression \"[%g, %g, %g]\"; o.position.controller = pe" % tuple(vals))
        if n["rot"] in ("Orientation_Constraint", "LookAt_Constraint"):
            tg = [(mapname(t), w) for t, w in n.get("targets", []) if t != "-"]
            # ForeTwist etc. may not exist on the target Biped: fall back to the Forearm / Calf / parent part
            L.append("  local tg = #(%s)" % ",".join("#(_res %s, %g)" % (_q(t), w) for t, w in tg))
            L.append("  tg = for t in tg where t[1] != undefined collect t")
            L.append("  local wsum = 0.0; for t in tg do wsum += t[2]")
            L.append("  if wsum > 0 then (")
            if n["rot"] == "Orientation_Constraint":
                L.append("    local c = Orientation_Constraint(); o.rotation.controller = c")
                L.append("    for t in tg do c.appendTarget t[1] t[2]")
                L.append("    c.local_world = %d" % n.get("local_world", 0))
                L.append("    c.relative = %s" % str(n.get("relative", False)).lower())
            else:
                la = n["lookat"]
                L.append("    local c = LookAt_Constraint(); o.rotation.controller = c")
                L.append("    for t in tg do c.appendTarget t[1] t[2]")
                L.append("    c.target_axis = %s; try (c.target_axisFlip = %s) catch ()" % (la["TAX"], la["TAF"]))
                L.append("    c.upnode_world = %s" % la["UPW"])
                if la["UPW"] == "false" and la["UPN"] != "-":
                    L.append("    c.pickUpNode = getNodeByName %s exact:true" % _q(mapname(la["UPN"])))
                L.append("    c.upnode_ctrl = %s; c.StoUP_axis = %s; try (c.StoUP_axisFlip = %s) catch (); c.upnode_axis = %s"
                         % (la["UPC"], la["SUP"], la["SUF"], la["UPA"]))
                L.append("    c.relative = %s" % str(n.get("relative", False)).lower())
            L.append("  )")
        L.append("  local D = o.transform * inverse W")
        L.append("  out_dev += o.name + \"\\t\" + (formattedPrint (length D.row4) format:\".4f\") + \"\\t\" + (formattedPrint (acos (amin 1.0 ((D.row1.x + D.row2.y + D.row3.z - 1)/2.0))) format:\".2f\") + \"\\n\"")
        L.append("))")
    # followers (skin bones per the standard) + their Nubs
    for f in tpl["followers"]:
        L.append("if getNodeByName %s exact:true == undefined and getNodeByName %s exact:true != undefined do (" % (_q(f["name"]), _q(f["src"])))
        L.append("  out_fol += (MaxBridge.makeFollower %s %s) + \"\\n\"" % (_q(f["src"]), _q(f["name"])))
        L.append("  local b = getNodeByName %s exact:true" % _q(f["name"]))
        L.append("  if b != undefined and classOf b == BoneGeometry and b.children.count == 0 do (")
        L.append("    local s = MaxBridge.boneSeg b, d = normalize (s[2] - s[1])")
        L.append("    local nb = BoneSys.createBone s[2] (s[2] + d * (amax #(b.length * 0.25, 0.2))) (normalize b.transform.row3)")
        L.append("    nb.name = b.name + \"_Nub\"; nb.width = b.width * 0.5; nb.height = b.height * 0.5; nb.parent = b; nb.wirecolor = b.wirecolor; (_lay \"B_Standard\").addNode nb")
        L.append("  )\n)")
    L.append("\"MADE\\t\" + made as string + \"\\nSKIPPED\\t\" + (skipped as string) + \"\\n\" + out_dev + out_fol\n)")
    code = "\n".join(L).replace("(\nlocal pre", "(\nlocal out_dev = \"\"\nlocal out_fol = \"\"\nlocal pre", 1)
    with open(os.path.join(TEMPLATE_DIR, "_last_apply.ms"), "w", encoding="utf-8") as f:
        f.write(code)
    res = mb.send(code, timeout=300)
    if res.startswith("ERROR"):
        raise RuntimeError(res)
    rep = {"ratio": ratio, "raw": res, "dev": {}, "followers": []}
    for line in res.splitlines():
        parts_ = line.split("\t")
        if len(parts_) == 3 and parts_[0] in names:
            rep["dev"][parts_[0]] = (float(parts_[1]), float(parts_[2]))
        elif "<-" in line:
            rep["followers"].append(line)
    if save_as:
        rep["saved"] = mb.send("(saveMaxFile %s quiet:true; maxFilePath + maxFileName)" % ('@"' + save_as + '"'), timeout=120)
    return rep
