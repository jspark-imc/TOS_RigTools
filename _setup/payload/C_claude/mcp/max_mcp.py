"""3ds Max 2014 MCP server (stdlib only, same pattern as blender_mcp_lite.py).

Talks to MaxBridge.ms (127.0.0.1:9878 default, env MAXBRIDGE_PORT) directly, so Claude can drive Max
without going through Blender. Protocol: send MAXScript text, half-close,
read the result text until Max closes the connection.

Run with any Python 3 (registered in .mcp.json with Blender's bundled Python).
"""

import json
import os
import socket
import sys

HOST = "127.0.0.1"
# 9877 = user Max (never used by Claude). Claude Max = 9878-9899 (launch\Max_Claude_multi.bat). Override with env MAXBRIDGE_PORT.
PORT = int(os.environ.get("MAXBRIDGE_PORT", "9878"))
EXCHANGE = r"C:\claude\max_blender\exchange"
CHARACTER_LIMIT = 8000


def log(msg):
    sys.stderr.write("[max_mcp] %s\n" % msg)
    sys.stderr.flush()


# ---------------------------------------------------------------- core
def pick_port(args):
    # optional per-call port (a window reserved with launch\Max_Claude_lock.bat). Only Claude Max 9878-9899.
    p = args.get("port")
    if p in (None, "", 0):
        return PORT
    p = int(p)
    if not 9878 <= p <= 9899:
        raise ValueError("port %d refused: Claude Max is 9878-9899 (9877 = user's Max)" % p)
    return p


def max_send(code, timeout=300.0, port=None):
    s = socket.create_connection((HOST, port or PORT), timeout=5)
    s.settimeout(timeout)
    try:
        s.sendall(code.encode("utf-8"))
        s.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            b = s.recv(65536)
            if not b:
                break
            chunks.append(b)
    finally:
        s.close()
    return b"".join(chunks).decode("utf-8-sig", errors="replace")


def ms_path(p):
    return '@"' + p.replace('"', "") + '"'


def ms_bool(v):
    return "true" if v else "false"


def text(s):
    return [{"type": "text", "text": s}]


def clip(s):
    if len(s) <= CHARACTER_LIMIT:
        return s
    os.makedirs(EXCHANGE, exist_ok=True)
    path = os.path.join(EXCHANGE, "max_mcp_last_output.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)
    return s[:CHARACTER_LIMIT] + "\n... (%d자 중 일부. 전체: %s)" % (len(s), path)


# ---------------------------------------------------------------- tools
def t_ping(args):
    return text(max_send('"pong " + MaxBridge.version', timeout=10, port=pick_port(args)))


def t_scene_info(args):
    n = int(args.get("max_objects", 500))
    return text(clip(max_send("MaxBridge.info maxObjects:%d" % n, port=pick_port(args))))


def t_check_rig(args):
    out = os.path.join(EXCHANGE, "rig_check.txt")
    return text(clip(max_send("MaxBridge.checkRig outPath:%s" % ms_path(out), port=pick_port(args))))


def t_export_fbx(args):
    path = args.get("path") or os.path.join(EXCHANGE, "max_to_blender.fbx")
    return text(max_send("MaxBridge.exportFBX %s selOnly:%s anim:%s" % (
        ms_path(path), ms_bool(args.get("selected_only", True)), ms_bool(args.get("anim", True))), port=pick_port(args)))


def t_import_fbx(args):
    layer = (args.get("layer_name") or "FromBlender").replace('"', "")
    return text(max_send('MaxBridge.importFBX %s layerName:"%s"' % (ms_path(args["path"]), layer), port=pick_port(args)))


def t_execute(args):
    return text(clip(max_send(args["code"], timeout=float(args.get("timeout", 300)), port=pick_port(args))))


PORT_PROP = {"type": "integer", "description": "Claude Max port 9878-9899 reserved with launch\\Max_Claude_lock.bat claim (default: env MAXBRIDGE_PORT or 9878). 9877 is refused."}

RO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}

TOOLS = {
    "max_ping": (t_ping, "Check that 3ds Max and MaxBridge are reachable. Returns 'pong <version>'.",
                 {"type": "object", "properties": {"port": PORT_PROP}}, RO),
    "max_scene_info": (t_scene_info, "Get the open Max scene as JSON (read-only): bridge/Max version, file path, system unit and scale, frame range, fps, object and selection counts, and per object: name, class, parent, faces, verts, material, modifiers, hidden, selected, layer. Lists at most max_objects objects; object_count is the real total.",
                       {"type": "object", "properties": {"max_objects": {"type": "integer", "description": "Max objects to list (default 500)"}, "port": PORT_PROP}}, RO),
    "max_check_rig": (t_check_rig, "Run MaxBridge.checkRig() (STANDARD.txt rules). First line has error/warning counts; full report saved to exchange\\rig_check.txt.",
                      {"type": "object", "properties": {"port": PORT_PROP}}, RO),
    "max_export_fbx": (t_export_fbx, "Export from Max to FBX (FBX 2014 binary, Z-up, skin, morphs and baked animation; no cameras or lights). Does not change the scene. Returns 'OK: exported N objects ...' or 'ERROR: ...'; with selected_only=true and nothing selected it returns 'ERROR: nothing selected in 3ds Max'.",
                       {"type": "object", "properties": {
                           "path": {"type": "string", "description": "Output .fbx path (default exchange\\max_to_blender.fbx)"},
                           "selected_only": {"type": "boolean", "description": "Export only the selection (default true)"},
                           "anim": {"type": "boolean", "description": "Include animation (default true)"}, "port": PORT_PROP}},
                       {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}),
    "max_import_fbx": (t_import_fbx, "Import an FBX into Max; new objects go on layer_name (created if missing). Saves a Hold first (undo: Edit > Fetch), never overwrites existing objects, and removes Blender's extra identity 'Armature' root dummy. Returns 'OK: imported N objects ...' or 'ERROR: file not found ...'.",
                       {"type": "object", "properties": {
                           "path": {"type": "string", "description": "Input .fbx path"},
                           "layer_name": {"type": "string", "description": "Layer for imported objects (default FromBlender)"}, "port": PORT_PROP},
                        "required": ["path"]},
                       {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}),
    "max_execute": (t_execute, "Run arbitrary MAXScript in 3ds Max; the last expression's value is returned as text (errors as 'ERROR: ...'). Write large outputs to exchange\\ and return a summary.",
                    {"type": "object", "properties": {
                        "code": {"type": "string", "description": "MAXScript to run, e.g. objects.count"},
                        "timeout": {"type": "number", "description": "Seconds to wait (default 300)"}, "port": PORT_PROP},
                     "required": ["code"]},
                    {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False}),
}


# ---------------------------------------------------------------- JSON-RPC over stdio
def send(msg):
    sys.stdout.buffer.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    if rid is None:
        return  # notification
    if method == "initialize":
        pv = (req.get("params") or {}).get("protocolVersion", "2024-11-05")
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": pv,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "max-mcp", "version": "1.0.0"}}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": rid, "result": {}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": n, "description": d, "inputSchema": s, "annotations": a} for n, (_, d, s, a) in TOOLS.items()]}})
    elif method == "tools/call":
        p = req.get("params") or {}
        name = p.get("name")
        args = p.get("arguments") or {}
        if name not in TOOLS:
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": "Unknown tool: %s" % name}})
            return
        try:
            content = TOOLS[name][0](args)
            send({"jsonrpc": "2.0", "id": rid, "result": {"content": content, "isError": False}})
        except (ConnectionRefusedError, socket.timeout) as e:
            send({"jsonrpc": "2.0", "id": rid, "result": {"isError": True, "content": text(
                "3ds Max에 연결할 수 없음 (%s:%s, %s). Max가 켜져 있고 MAXScript Listener에 "
                "'[MaxBridge] ... listening' 이 보이는지 확인. 꺼져 있으면 Listener에서 MaxBridge.start() 실행." % (HOST, args.get("port") or PORT, e))}})
        except Exception as e:
            log("tool error %s: %r" % (name, e))
            send({"jsonrpc": "2.0", "id": rid, "result": {"isError": True, "content": text("Error: %s" % e)}})
    elif method == "resources/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"resources": []}})
    elif method == "prompts/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"prompts": []}})
    else:
        send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found: %s" % method}})


def main():
    log("started; python=%s" % sys.executable)
    for raw in sys.stdin.buffer:
        line = raw.decode("utf-8", errors="replace").strip().lstrip("﻿")
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            handle(req)
        except Exception as e:
            log("handler error: %r" % e)


if __name__ == "__main__":
    main()
