"""blender_mcp_lite: dependency-free MCP (stdio) server for the Blender MCP addon.

Uses only the Python standard library, so it runs on Blender's bundled Python
without pip/PyPI. Talks to the addon's socket server (default localhost:9876).
"""
import base64
import json
import os
import socket
import sys
import tempfile
import threading

HOST = os.environ.get("BLENDER_HOST", "localhost")
# 9876 = user Blender (never used by Claude). Claude Blender = 9866 (C:\claude\max_blender\launch\Blender_Claude.bat). Override with env BLENDER_PORT.
PORT = int(os.environ.get("BLENDER_PORT", "9866"))
LOG_PATH = os.path.join(tempfile.gettempdir(), "blender_mcp_lite.log")
_lock = threading.Lock()


def log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def blender_command(cmd_type, params=None, timeout=180.0):
    with _lock:
        s = socket.create_connection((HOST, PORT), timeout=10)
        try:
            s.sendall(json.dumps({"type": cmd_type, "params": params or {}}).encode("utf-8"))
            s.settimeout(timeout)
            buf = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
                try:
                    resp = json.loads(buf.decode("utf-8"))
                    break
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
            else:
                pass
            resp = json.loads(buf.decode("utf-8"))
        finally:
            s.close()
    if resp.get("status") == "error":
        raise RuntimeError(resp.get("message", "Unknown error from Blender"))
    return resp.get("result", {})


def text(obj):
    if not isinstance(obj, str):
        obj = json.dumps(obj, ensure_ascii=False, indent=2)
    return [{"type": "text", "text": obj}]


def t_get_scene_info(args):
    return text(blender_command("get_scene_info"))


def t_get_object_info(args):
    return text(blender_command("get_object_info", {"name": args["object_name"]}))


def t_execute_blender_code(args):
    return text(blender_command("execute_code", {"code": args["code"]}))


def t_get_viewport_screenshot(args):
    path = os.path.join(tempfile.gettempdir(), "blender_mcp_lite_%d.png" % os.getpid())
    res = blender_command("get_viewport_screenshot", {
        "max_size": int(args.get("max_size", 800)), "filepath": path, "format": "png"})
    if isinstance(res, dict) and res.get("error"):
        raise RuntimeError(res["error"])
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    try:
        os.remove(path)
    except OSError:
        pass
    return [{"type": "image", "data": data, "mimeType": "image/png"}]


TOOLS = {
    "get_scene_info": (t_get_scene_info, "Get information about the current Blender scene (objects, materials, etc.).",
                       {"type": "object", "properties": {}}),
    "get_object_info": (t_get_object_info, "Get detailed information about one object in the Blender scene.",
                        {"type": "object", "properties": {"object_name": {"type": "string", "description": "Name of the object"}},
                         "required": ["object_name"]}),
    "execute_blender_code": (t_execute_blender_code,
                             "Execute arbitrary Python (bpy) code inside the running Blender. Use print() to return output. Work in small steps.",
                             {"type": "object", "properties": {"code": {"type": "string", "description": "Python code to run in Blender"}},
                              "required": ["code"]}),
    "get_viewport_screenshot": (t_get_viewport_screenshot, "Capture a screenshot of the current Blender 3D viewport.",
                                {"type": "object", "properties": {"max_size": {"type": "integer", "description": "Max size in px of the largest dimension (default 800)"}}}),
}


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
            "serverInfo": {"name": "blender-mcp-lite", "version": "1.0.0"}}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": rid, "result": {}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": n, "description": d, "inputSchema": s} for n, (_, d, s) in TOOLS.items()]}})
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
        except ConnectionRefusedError:
            send({"jsonrpc": "2.0", "id": rid, "result": {"isError": True, "content": text(
                "Could not connect to Blender on %s:%d. Start the Claude Blender with C:\\claude\\max_blender\\launch\\Blender_Claude.bat (the user's Blender on 9876 is not used)." % (HOST, PORT))}})
        except Exception as e:
            log("tool error %s: %r" % (name, e))
            send({"jsonrpc": "2.0", "id": rid, "result": {"isError": True, "content": text("Error: %s" % e)}})
    elif method in ("resources/list",):
        send({"jsonrpc": "2.0", "id": rid, "result": {"resources": []}})
    elif method in ("prompts/list",):
        send({"jsonrpc": "2.0", "id": rid, "result": {"prompts": []}})
    else:
        send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found: %s" % method}})


def main():
    log("started; python=%s" % sys.executable)
    for raw in sys.stdin.buffer:
        line = raw.decode("utf-8", errors="replace").strip()
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
