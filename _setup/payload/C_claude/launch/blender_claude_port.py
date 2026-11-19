"""Claude work Blender: run with  blender.exe --python blender_claude_port.py  (Blender_Claude.bat does this).

- MCP for Blender listens on CLAUDE_BLENDER_PORT (default 9866) instead of 9876 (= user's Blender).
  The port is a scene property saved in .blend files, so it is forced again after every file load.
- Files saved here are written with the normal 9876, so opening them in the user's Blender changes nothing there.
- Preferences are not auto-saved on exit, so this window never overwrites the user's Blender settings.
- A red "CLAUDE 작업창" label in the top bar tells the two windows apart.
"""
import os
import bpy
from bpy.app.handlers import persistent

PORT = int(os.environ.get("CLAUDE_BLENDER_PORT", "9866"))
USER_PORT = 9876


def _set_port(port):
    for sc in bpy.data.scenes:
        if hasattr(sc, "blendermcp_port"):
            sc.blendermcp_port = port


def _server():
    return getattr(bpy.types, "blendermcp_server", None)


def _ensure_server():
    """Start (or move) the MCP server onto PORT. Retries until the add-on is ready."""
    if not hasattr(bpy.types.Scene, "blendermcp_port"):
        return 1.0
    _set_port(PORT)
    srv = _server()
    if srv is not None and srv.running and srv.port != PORT:
        srv.stop()
    if srv is None or not srv.running:
        try:
            import blender_mcp_addon as m
            if srv is None:
                bpy.types.blendermcp_server = m.BlenderMCPServer(port=PORT)
                srv = bpy.types.blendermcp_server
            srv.port = PORT
            srv.start()
        except Exception as e:
            print("[ClaudeBlender] MCP start failed: %s" % e)
            return 2.0
    for sc in bpy.data.scenes:
        if hasattr(sc, "blendermcp_server_running"):
            sc.blendermcp_server_running = bool(srv and srv.running)
    print("[ClaudeBlender] MCP for Blender on port %d (running=%s)" % (PORT, bool(srv and srv.running)))
    return None if (srv and srv.running) else 2.0


@persistent
def _on_load(_unused):
    _set_port(PORT)
    if not bpy.app.timers.is_registered(_ensure_server):
        bpy.app.timers.register(_ensure_server, first_interval=0.3, persistent=True)


@persistent
def _on_save_pre(_unused):
    _set_port(USER_PORT)


@persistent
def _on_save_post(_unused):
    _set_port(PORT)


def _draw_label(self, context):
    row = self.layout.row()
    row.alert = True
    row.label(text="CLAUDE 작업창 (포트 %d)" % PORT, icon="ERROR")


def main():
    try:
        bpy.context.preferences.use_preferences_save = False
    except Exception:
        pass
    _set_port(PORT)
    for lst, fn in ((bpy.app.handlers.load_post, _on_load),
                    (bpy.app.handlers.save_pre, _on_save_pre),
                    (bpy.app.handlers.save_post, _on_save_post)):
        if fn not in lst:
            lst.append(fn)
    try:
        bpy.types.TOPBAR_HT_upper_bar.append(_draw_label)
    except Exception:
        pass
    if not bpy.app.timers.is_registered(_ensure_server):
        bpy.app.timers.register(_ensure_server, first_interval=0.3, persistent=True)


main()
