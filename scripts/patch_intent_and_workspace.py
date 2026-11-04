import os
import re

# 1. Update core/intent_engine.py
with open("core/intent_engine.py", "r", encoding="utf-8") as f:
    ie_code = f.read().replace("\r\n", "\n")

# A. Folder creation: add "named" and flexible syntax
old_folder_create = """        m_folder_loc = re.match(r"^(?:create|make)\\s+(?:a\\s+)?folder(?:\\s+called\\s+['\\"]?(.+?)['\\"]?)?\\s+(?:on|in|inside)\\s+(?:my\\s+)?(.+?)$", clean)
        if m_folder_loc:
            f_name = m_folder_loc.group(1).strip() if m_folder_loc.group(1) else "New Folder"
            loc = m_folder_loc.group(2).strip()
            return {"intent": "filesystem_control", "action": "create_folder", "target": f_name, "location": loc, "confidence": 0.95, "raw_text": raw_text}"""

new_folder_create = """        m_folder_loc = re.match(r"^(?:create|make|build)\\s+(?:a\\s+)?folder(?:\\s+(?:called|named)\\s+['\\"]?(.+?)['\\"]?)?\\s+(?:on|in|inside)\\s+(?:my\\s+|the\\s+)?(.+?)$", clean, re.IGNORECASE)
        if not m_folder_loc:
            m_folder_loc = re.match(r"^(?:create|make|build)\\s+(?:a\\s+)?folder\\s+['\\"]?(.+?)['\\"]?\\s+(?:on|in|inside)\\s+(?:my\\s+|the\\s+)?(.+?)$", clean, re.IGNORECASE)
        if m_folder_loc:
            f_name = m_folder_loc.group(1).strip() if m_folder_loc.group(1) else "New Folder"
            loc = m_folder_loc.group(2).strip()
            return {"intent": "filesystem_control", "action": "create_folder", "target": f_name, "location": loc, "confidence": 0.96, "raw_text": raw_text}"""

if old_folder_create in ie_code:
    ie_code = ie_code.replace(old_folder_create, new_folder_create)
    print("Updated folder creation regex in core/intent_engine.py")
else:
    print("Could not find old_folder_create in core/intent_engine.py")

# B. Stop intent at top of system controls
old_lock = """        if clean in ["lock computer", "lock screen", "lock workstation", "lock pc"]:
            return {"intent": "system_control", "action": "lock", "target": None, "confidence": 0.99, "query": clean, "raw_text": raw_text}"""

new_lock = """        if clean in ["stop", "stop listening", "cancel", "terminate", "halt", "pause", "be quiet", "shut up", "stop talking"]:
            return {"intent": "system_action", "action": "stop", "target": None, "confidence": 0.99, "query": clean, "raw_text": raw_text}

        if clean in ["lock computer", "lock screen", "lock workstation", "lock pc"]:
            return {"intent": "system_control", "action": "lock", "target": None, "confidence": 0.99, "query": clean, "raw_text": raw_text}"""

if old_lock in ie_code:
    ie_code = ie_code.replace(old_lock, new_lock)
    print("Updated stop intent in core/intent_engine.py")
else:
    print("Could not find old_lock in core/intent_engine.py")

with open("core/intent_engine.py", "w", encoding="utf-8") as f:
    f.write(ie_code)

# 2. Update core/workspace_interaction/workspace_manager.py
with open("core/workspace_interaction/workspace_manager.py", "r", encoding="utf-8") as f:
    wm_code = f.read().replace("\r\n", "\n")

old_wm_resolve = """        clean = folder_or_project_name.lower().strip()
        if clean in ["that folder", "this folder", "the folder", "this project", "that project", "it"]:
            last = self.get_last_active_folder()
            if last:
                return {"success": True, "path": last, "name": last.name}
            return {"success": False, "status": "NO_PREVIOUS_FOLDER", "message": "No active or recent folder was found."}"""

new_wm_resolve = """        clean = folder_or_project_name.lower().strip()
        if clean in ["that folder", "this folder", "the folder", "this project", "that project", "it", "current folder", "current project", "workspace", ""]:
            last = self.get_last_active_folder()
            if last:
                return {"success": True, "path": last, "name": last.name}
            # Fallback to current working directory or active project
            from pathlib import Path
            cwd = Path(os.getcwd())
            return {"success": True, "path": cwd, "name": cwd.name}"""

if old_wm_resolve in wm_code:
    wm_code = wm_code.replace(old_wm_resolve, new_wm_resolve)
    with open("core/workspace_interaction/workspace_manager.py", "w", encoding="utf-8") as f:
        f.write(wm_code)
    print("Updated resolve_workspace in core/workspace_interaction/workspace_manager.py")
else:
    print("Could not find old_wm_resolve in workspace_manager.py")

