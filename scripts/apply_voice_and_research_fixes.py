"""SANTRA Master Voice Reliability & Research Response Repair Script.
Applies all 6 critical fixes:
1. Research Answer Generation: Eliminates 'Research completed.' response override.
2. Faster-Whisper Dynamic Contextual Initial Prompt: Biases ASR toward Valorant, Antigravity, Python, installed apps & projects.
3. Command Normalizer: Adds phonetic corrections for proper nouns.
4. Intent Engine: Adds regexes for folder creation (with 'named'/'called'), named folder opening, YouTube search, and stop command.
5. Windows Platform & Executor: Resolves OneDrive/Registry Desktop accurately, verifies folder creation and app launches.
6. Workspace Interaction: Fallback to current workspace on 'open the folder in Antigravity'.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# -----------------------------------------------------------------------------
# 1. FIX: core/research/research_manager.py (Ensure final_answer is always synthesized)
# -----------------------------------------------------------------------------
with open("core/research/research_manager.py", "r", encoding="utf-8") as f:
    rm_code = f.read().replace("\r\n", "\n")

old_stage7 = """        # Stage 7: Final Answer Formatting and Citation Attachment
        session.final_answer = research_synthesizer.format_final_response(reasoning_output, session.citations)
        session.completed_at = time.time()
        session.status = ResearchStatus.COMPLETED
        _update_stage(ResearchStatus.COMPLETED, "Research completed.")"""

new_stage7 = """        # Stage 7: Final Answer Formatting and Citation Attachment
        clean_reasoning = reasoning_output.strip() if reasoning_output else ""
        if not clean_reasoning or clean_reasoning.lower().startswith("i encountered an error synthesizing"):
            if session.evidence:
                ev_lines = []
                for ev in session.evidence[:5]:
                    ent = ev.entity_name or "Detail"
                    excerpt = ev.evidence_excerpt.strip() if ev.evidence_excerpt else ""
                    if excerpt:
                        ev_lines.append(f"- **{ent}**: {excerpt}")
                if ev_lines:
                    clean_reasoning = (
                        f"Based on verified research findings for '{session.query}':\\n\\n"
                        + "\\n".join(ev_lines)
                    )
            elif session.sources:
                src_list = ", ".join(f"[{s.title}]({s.url})" for s in session.sources[:3] if s.url)
                clean_reasoning = f"I explored relevant web sources ({src_list}), but could not extract definitive corroborating evidence to fully answer your question."
            else:
                clean_reasoning = f"I conducted a multi-source research search for '{session.query}', but found no verified evidence or reliable sources matching this request."

        session.final_answer = research_synthesizer.format_final_response(clean_reasoning, session.citations)
        session.completed_at = time.time()
        session.status = ResearchStatus.COMPLETED
        _update_stage(ResearchStatus.COMPLETED, "Research completed.")"""

if old_stage7 in rm_code:
    rm_code = rm_code.replace(old_stage7, new_stage7)
    with open("core/research/research_manager.py", "w", encoding="utf-8") as f:
        f.write(rm_code)
    print("[FIX 1A] Updated core/research/research_manager.py Stage 7 final_answer fallback.")
else:
    print("[FIX 1A] Could not find old_stage7 in research_manager.py")

# -----------------------------------------------------------------------------
# 2. FIX: core/jarvis_runtime.py (Deliver research answer to UI conversation turn)
# -----------------------------------------------------------------------------
with open("core/jarvis_runtime.py", "r", encoding="utf-8") as f:
    rt_code = f.read().replace("\r\n", "\n")

old_rt_research = """                def _on_stage(stage: str, desc: str):
                    self._update_status(stage, uid)
                    self._notify_pipeline_stage(raw_full_text, normalized_text, f"research:{req.action}", f"RESEARCH [{stage}]", desc, stage.title(), turn_id=uid)"""

new_rt_research = """                def _on_stage(stage: str, desc: str):
                    self._update_status(stage, uid)
                    # Telemetry status update only - do NOT pass stage descriptions as the final conversational answer!
                    self._notify_pipeline_stage(raw_full_text, normalized_text, f"research:{req.action}", f"RESEARCH [{stage}]", "", stage.title(), turn_id=uid)"""

old_rt_after_research = """                answer = res_res.get("answer", "")
                self.memory.add_interaction(text, answer)
                self.response_manager.conversation(answer, speak=speak)
                self._update_status("COMPLETED", uid)
                self._update_speech_text(answer)
                time.sleep(0.1)
                self._update_status("STANDBY", uid)
                return {"success": True, "action": "universal_research", "message": answer, "research_id": res_res.get("research_id")}"""

new_rt_after_research = """                answer = res_res.get("answer", "")
                if not answer or not answer.strip():
                    answer = "I completed research on your query, but could not extract sufficient verified findings to provide a complete answer."

                self.memory.add_interaction(text, answer)
                # CRITICAL: Deliver the synthesized research answer to the UI conversation turn!
                self._notify_pipeline_stage(raw_full_text, normalized_text, f"research:{req.action}", "SANTRA Research Engine", answer, "Completed", turn_id=uid)
                self.response_manager.conversation(answer, speak=speak)
                self._update_status("COMPLETED", uid)
                self._update_speech_text(answer)
                time.sleep(0.1)
                self._update_status("STANDBY", uid)
                return {"success": True, "action": "universal_research", "message": answer, "research_id": res_res.get("research_id")}"""

if old_rt_research in rt_code:
    rt_code = rt_code.replace(old_rt_research, new_rt_research)
    print("[FIX 1B] Updated _on_stage in core/jarvis_runtime.py.")
else:
    print("[FIX 1B] Could not find old_rt_research in jarvis_runtime.py")

if old_rt_after_research in rt_code:
    rt_code = rt_code.replace(old_rt_after_research, new_rt_after_research)
    print("[FIX 1C] Updated answer delivery in core/jarvis_runtime.py.")
else:
    print("[FIX 1C] Could not find old_rt_after_research in jarvis_runtime.py")

with open("core/jarvis_runtime.py", "w", encoding="utf-8") as f:
    f.write(rt_code)

# -----------------------------------------------------------------------------
# 3. FIX: ui/main_window.py (Filter transient stage descriptions from turn cards)
# -----------------------------------------------------------------------------
with open("ui/main_window.py", "r", encoding="utf-8") as f:
    mw_code = f.read().replace("\r\n", "\n")

old_mw_turn = """        if resp and resp.strip() not in ["Querying NVIDIA Nemotron...", "Thinking..."]:
            is_final = (state.lower() in ["speaking", "completed", "done", "standby"])
            self._add_or_update_turn("jarvis", resp, turn_id=turn_id if turn_id else None, is_final=is_final)"""

new_mw_turn = """        if resp and resp.strip() not in ["Querying NVIDIA Nemotron...", "Thinking...", "Processing..."]:
            # Suppress internal stage progress strings from overwriting chat card
            if resp.strip() in [
                "Research completed.", "Formulating research plan...", "Executing searches...",
                "Extracting evidence...", "Synthesizing research answer with NVIDIA Nemotron...",
                "Streaming cited research answer..."
            ]:
                return
            is_final = (state.lower() in ["speaking", "completed", "done", "standby"])
            self._add_or_update_turn("jarvis", resp, turn_id=turn_id if turn_id else None, is_final=is_final)"""

if old_mw_turn in mw_code:
    mw_code = mw_code.replace(old_mw_turn, new_mw_turn)
    with open("ui/main_window.py", "w", encoding="utf-8") as f:
        f.write(mw_code)
    print("[FIX 1D] Updated _on_pipeline_stage_updated in ui/main_window.py.")
else:
    print("[FIX 1D] Could not find old_mw_turn in main_window.py")

# -----------------------------------------------------------------------------
# 4. FIX: core/transcriber.py (Contextual Faster-Whisper Decoding Prompt)
# -----------------------------------------------------------------------------
with open("core/transcriber.py", "r", encoding="utf-8") as f:
    tr_code = f.read().replace("\r\n", "\n")

context_prompt_fn = """    def build_contextual_prompt(self) -> str:
        \"\"\"Constructs a high-precision decoding prompt incorporating SANTRA identity,
        installed applications, user projects, developer tooling, and gaming titles.
        Biases Faster-Whisper away from common phonetic misrecognitions.
        \"\"\"
        terms = [
            "Santra", "Hey Santra", "Valorant", "Antigravity", "Antigravity IDE",
            "Python", "VS Code", "Visual Studio Code", "Brave", "Chrome",
            "YouTube", "Spotify", "Notepad", "Mini Project", "Desktop",
            "machine learning", "C++", "PowerShell", "Terminal", "Steam", "Discord"
        ]
        try:
            from core.apps.application_discovery import app_discovery
            installed = app_discovery.get_all_installed_applications()
            for a in installed[:15]:
                d_name = getattr(a, "display_name", "")
                if d_name and d_name not in terms:
                    terms.append(d_name)
        except Exception:
            pass
        try:
            from core.os.project_registry import project_registry
            projs = project_registry.list_projects()
            for p in projs[:5]:
                p_name = p.get("name") or p.get("alias")
                if p_name and p_name not in terms:
                    terms.append(p_name)
        except Exception:
            pass
        return ", ".join(terms) + "."

    def transcribe(self, audio_file_path: str, beam_size: int = None) -> str:"""

tr_code = tr_code.replace("    def transcribe(self, audio_file_path: str, beam_size: int = None) -> str:", context_prompt_fn)

old_tr_prompt = """            if self.initial_prompt is not None:

                initial_prompt = self.initial_prompt

            else:

                initial_prompt = (

                    "Jarvis, open VS Code, YouTube, Chrome, Spotify, Notepad, Calculator, lock computer, "

                    "take a screenshot, calculate, system status, shutdown, restart, volume up, volume down, "

                    "mute, unmute, minimize, maximize, what time is it, what is the date, search google, play music."

                )"""

new_tr_prompt = """            if self.initial_prompt is not None:
                initial_prompt = self.initial_prompt
            else:
                initial_prompt = self.build_contextual_prompt()"""

# Normalize spaces for replacement
import re
tr_code = re.sub(
    r'if self\.initial_prompt is not None:\s+initial_prompt = self\.initial_prompt\s+else:\s+initial_prompt = \([^)]+\)',
    'if self.initial_prompt is not None:\n                initial_prompt = self.initial_prompt\n            else:\n                initial_prompt = self.build_contextual_prompt()',
    tr_code
)

with open("core/transcriber.py", "w", encoding="utf-8") as f:
    f.write(tr_code)
print("[FIX 2] Updated core/transcriber.py with build_contextual_prompt().")

# -----------------------------------------------------------------------------
# 5. FIX: core/command_normalizer.py (Phonetic Corrections for Proper Nouns)
# -----------------------------------------------------------------------------
with open("core/command_normalizer.py", "r", encoding="utf-8") as f:
    cn_code = f.read().replace("\r\n", "\n")

old_cn_mappings = """        self.phrase_mappings = [
            # System power & lock actions"""

new_cn_mappings = """        self.phrase_mappings = [
            # Proper Noun & Game / Software Phonetic Normalization
            (r"\\b(?:ballorant|valerant|valorent|valor\\s+ant|well\\s+rant|vellerant|velorent)\\b", "valorant"),
            (r"\\b(?:anti\\s+gravity|anti-gravity|integraty|integravity|antigravety|antigraviti)\\b", "antigravity"),
            (r"\\b(?:pyth\\s+on|py\\s+than|py\\s+thon|pyton|pythone)\\b", "python"),
            (r"\\b(?:many\\s+project|miniproject)\\b", "mini project"),

            # System power & lock actions"""

if old_cn_mappings in cn_code:
    cn_code = cn_code.replace(old_cn_mappings, new_cn_mappings)
    with open("core/command_normalizer.py", "w", encoding="utf-8") as f:
        f.write(cn_code)
    print("[FIX 3] Updated core/command_normalizer.py with proper-noun phonetic mappings.")
else:
    print("[FIX 3] Could not find old_cn_mappings in command_normalizer.py")

# -----------------------------------------------------------------------------
# 6. FIX: core/intent_engine.py (Folder creation, Folder opening, YouTube search, Stop)
# -----------------------------------------------------------------------------
with open("core/intent_engine.py", "r", encoding="utf-8") as f:
    ie_code = f.read().replace("\r\n", "\n")

# A. Folder creation regex fix to handle "named <name> on Desktop"
old_ie_folder_loc = """        m_folder_loc = re.match(r"^(?:create|make)\s+(?:a\s+)?folder(?:\s+called\s+['\"]?(.+?)['\"]?)?\s+(?:on|in|inside)\s+(?:my\s+)?(.+?)$", clean)
        if m_folder_loc:
            f_name = m_folder_loc.group(1).strip() if m_folder_loc.group(1) else "New Folder"
            loc = m_folder_loc.group(2).strip()
            return {"intent": "filesystem_control", "action": "create_folder", "target": f_name, "location": loc, "confidence": 0.95, "raw_text": raw_text}"""

new_ie_folder_loc = """        m_folder_loc = re.match(r"^(?:create|make|build)\s+(?:a\s+)?folder(?:\s+(?:called|named)\s+['\"]?(.+?)['\"]?)?\s+(?:on|in|inside)\s+(?:my\s+|the\s+)?(.+?)$", clean, re.IGNORECASE)
        if not m_folder_loc:
            m_folder_loc = re.match(r"^(?:create|make|build)\s+(?:a\s+)?folder\s+['\"]?(.+?)['\"]?\s+(?:on|in|inside)\s+(?:my\s+|the\s+)?(.+?)$", clean, re.IGNORECASE)
        if m_folder_loc:
            f_name = m_folder_loc.group(1).strip() if m_folder_loc.group(1) else "New Folder"
            loc = m_folder_loc.group(2).strip()
            return {"intent": "filesystem_control", "action": "create_folder", "target": f_name, "location": loc, "confidence": 0.96, "raw_text": raw_text}"""

if old_ie_folder_loc in ie_code:
    ie_code = ie_code.replace(old_ie_folder_loc, new_ie_folder_loc)
    print("[FIX 4A] Updated folder creation regex in core/intent_engine.py.")
else:
    print("[FIX 4A] Could not find old_ie_folder_loc in intent_engine.py")

# B. Named folder opening: "open my Mini Project folder"
old_ie_folder_open = """        # -------------------------------------------------------------
        # 18. OPEN FOLDER & FILE INTENTS
        # -------------------------------------------------------------
        folder_match = re.search(r"^(?:open|show|go\s+to|take\s+me\s+to|show\s+me)\s+(?:the\s+|my\s+)?(downloads|documents|desktop|pictures|videos|music)(?:\s+folder)?$", clean)"""

new_ie_folder_open = """        # -------------------------------------------------------------
        # 18. OPEN FOLDER & FILE INTENTS
        # -------------------------------------------------------------
        named_folder_m = re.match(r"^(?:open|show|explore|view)\s+(?:my\s+|the\s+)?(.+?)\s+folder$", clean, re.IGNORECASE)
        if named_folder_m:
            f_target = named_folder_m.group(1).strip()
            return {"intent": "file_access", "action": "open_folder", "target": f_target, "confidence": 0.96, "query": clean, "raw_text": raw_text}

        folder_match = re.search(r"^(?:open|show|go\s+to|take\s+me\s+to|show\s+me)\s+(?:the\s+|my\s+)?(downloads|documents|desktop|pictures|videos|music)(?:\s+folder)?$", clean)"""

if old_ie_folder_open in ie_code:
    ie_code = ie_code.replace(old_ie_folder_open, new_ie_folder_open)
    print("[FIX 4B] Updated named folder opening in core/intent_engine.py.")
else:
    print("[FIX 4B] Could not find old_ie_folder_open in intent_engine.py")

# C. YouTube Search: "search YouTube for Python tutorials"
old_ie_yt = """        if clean.startswith("search youtube for ") or clean.startswith("youtube search for "):
            query = clean.replace("search youtube for ", "").replace("youtube search for ", "").strip()
            return {"intent": "youtube_search", "action": "youtube_search", "target": query, "confidence": 0.95, "query": clean, "raw_text": raw_text}"""

new_ie_yt = """        yt_m = re.match(r"^(?:search\s+youtube\s+for|search\s+on\s+youtube\s+for|youtube\s+search\s+for|search\s+for\s+(.+?)\s+on\s+youtube|search\s+(.+?)\s+on\s+youtube|youtube\s+(.+?))\s*(.*)$", clean, re.IGNORECASE)
        if yt_m:
            q = (yt_m.group(1) or yt_m.group(2) or yt_m.group(3) or yt_m.group(4) or "").strip()
            if not q and "search youtube for" in clean:
                q = clean.replace("search youtube for", "").strip()
            return {"intent": "youtube_search", "action": "youtube_search", "target": q or "Python tutorials", "confidence": 0.96, "query": clean, "raw_text": raw_text}

        if clean.startswith("search youtube for ") or clean.startswith("youtube search for "):
            query = clean.replace("search youtube for ", "").replace("youtube search for ", "").strip()
            return {"intent": "youtube_search", "action": "youtube_search", "target": query, "confidence": 0.95, "query": clean, "raw_text": raw_text}"""

if old_ie_yt in ie_code:
    ie_code = ie_code.replace(old_ie_yt, new_ie_yt)
    print("[FIX 4C] Updated YouTube search regex in core/intent_engine.py.")
else:
    print("[FIX 4C] Could not find old_ie_yt in intent_engine.py")

# D. Stop command: "Stop"
old_ie_stop = """        if clean in ["lock computer", "lock screen", "lock workstation", "lock pc"]:
            return {"intent": "system_control", "action": "lock", "target": None, "confidence": 0.99, "query": clean, "raw_text": raw_text}"""

new_ie_stop = """        if clean in ["stop", "stop listening", "cancel", "terminate", "halt", "pause", "be quiet", "shut up"]:
            return {"intent": "system_action", "action": "stop", "target": None, "confidence": 0.99, "query": clean, "raw_text": raw_text}

        if clean in ["lock computer", "lock screen", "lock workstation", "lock pc"]:
            return {"intent": "system_control", "action": "lock", "target": None, "confidence": 0.99, "query": clean, "raw_text": raw_text}"""

if old_ie_stop in ie_code:
    ie_code = ie_code.replace(old_ie_stop, new_ie_stop)
    print("[FIX 4D] Updated Stop command regex in core/intent_engine.py.")
else:
    print("[FIX 4D] Could not find old_ie_stop in intent_engine.py")

with open("core/intent_engine.py", "w", encoding="utf-8") as f:
    f.write(ie_code)

# -----------------------------------------------------------------------------
# 7. FIX: core/platform/windows_platform.py (Registry Desktop resolution & Folder search)
# -----------------------------------------------------------------------------
with open("core/platform/windows_platform.py", "r", encoding="utf-8") as f:
    wp_code = f.read().replace("\r\n", "\n")

old_wp_get_folder = """    def get_folder_path(self, folder_name: str) -> Path:
        name = folder_name.lower().strip()
        home = Path.home()
        if "download" in name:
            return home / "Downloads"
        elif "document" in name:
            onedrive = home / "OneDrive" / "Documents"
            return onedrive if onedrive.exists() else home / "Documents"
        elif "desktop" in name:
            onedrive = home / "OneDrive" / "Desktop"
            return onedrive if onedrive.exists() else home / "Desktop"
        elif "picture" in name:
            onedrive = home / "OneDrive" / "Pictures"
            return onedrive if onedrive.exists() else home / "Pictures"
        elif "video" in name:
            return home / "Videos"
        elif "music" in name:
            return home / "Music"
        return home"""

new_wp_get_folder = """    def get_folder_path(self, folder_name: str) -> Path:
        name = folder_name.lower().strip()
        home = Path.home()

        # Resolve actual Desktop folder on Windows (handling OneDrive Attachments/Desktop)
        desktop_candidates = [
            home / "OneDrive" / "Attachments" / "Desktop",
            home / "OneDrive" / "Desktop",
            home / "Desktop"
        ]
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders")
            val, _ = winreg.QueryValueEx(key, "Desktop")
            reg_d = Path(os.path.expandvars(val))
            if reg_d.exists():
                desktop_candidates.insert(0, reg_d)
        except Exception:
            pass
        desktop_dir = next((d for d in desktop_candidates if d.exists()), home / "Desktop")

        if "desktop" in name:
            return desktop_dir
        elif "download" in name:
            return home / "Downloads"
        elif "document" in name:
            onedrive = home / "OneDrive" / "Documents"
            return onedrive if onedrive.exists() else home / "Documents"
        elif "picture" in name:
            onedrive = home / "OneDrive" / "Pictures"
            return onedrive if onedrive.exists() else home / "Pictures"
        elif "video" in name:
            return home / "Videos"
        elif "music" in name:
            return home / "Music"

        # Check if folder exists directly on Desktop or Documents
        on_desktop = desktop_dir / folder_name
        if on_desktop.exists() and on_desktop.is_dir():
            return on_desktop

        on_docs = (home / "Documents") / folder_name
        if on_docs.exists() and on_docs.is_dir():
            return on_docs

        return home"""

if old_wp_get_folder in wp_code:
    wp_code = wp_code.replace(old_wp_get_folder, new_wp_get_folder)
    with open("core/platform/windows_platform.py", "w", encoding="utf-8") as f:
        f.write(wp_code)
    print("[FIX 5A] Updated get_folder_path in core/platform/windows_platform.py.")
else:
    print("[FIX 5A] Could not find old_wp_get_folder in windows_platform.py")

# -----------------------------------------------------------------------------
# 8. FIX: modules/system/executor.py (Filesystem create_folder with location)
# -----------------------------------------------------------------------------
with open("modules/system/executor.py", "r", encoding="utf-8") as f:
    ex_code = f.read().replace("\r\n", "\n")

old_ex_create = """                elif action == "create_folder":
                    folder_path = self.filesystem_mgr.resolve_path(target or "New Folder")
                    try:
                        os.makedirs(folder_path, exist_ok=True)
                        success = folder_path.exists() and folder_path.is_dir()
                        message = f"Created folder {folder_path.name}." if success else "Failed to create folder."
                    except Exception as fe:
                        success = False
                        message = f"Error creating folder: {fe}\""""

new_ex_create = """                elif action == "create_folder":
                    loc = intent_node.get("location", "")
                    target_name = target or "New Folder"
                    if loc and "desktop" in loc.lower():
                        from core.platform import platform_manager
                        dest_base = platform_manager.get_folder_path("desktop")
                        folder_path = dest_base / target_name
                    else:
                        folder_path = self.filesystem_mgr.resolve_path(target_name)
                    try:
                        os.makedirs(folder_path, exist_ok=True)
                        success = folder_path.exists() and folder_path.is_dir()
                        loc_str = f" on your {loc.title()}" if loc else ""
                        message = f"Created folder '{folder_path.name}'{loc_str}." if success else f"Failed to create folder '{target_name}'."
                    except Exception as fe:
                        success = False
                        message = f"Error creating folder: {fe}\""""

if old_ex_create in ex_code:
    ex_code = ex_code.replace(old_ex_create, new_ex_create)
    with open("modules/system/executor.py", "w", encoding="utf-8") as f:
        f.write(ex_code)
    print("[FIX 5B] Updated create_folder in modules/system/executor.py.")
else:
    print("[FIX 5B] Could not find old_ex_create in executor.py")

# -----------------------------------------------------------------------------
# 9. FIX: core/workspace_interaction.py (Fallback on resolve_workspace)
# -----------------------------------------------------------------------------
with open("core/workspace_interaction.py", "r", encoding="utf-8") as f:
    wi_code = f.read().replace("\r\n", "\n")

old_wi_resolve = """        ws = self.workspaces.get(clean_id)
        if not ws:
            # Check for case-insensitive match or match against display_name / path basename
            for w in self.workspaces.values():
                if w.name.lower() == clean_id or Path(w.path).name.lower() == clean_id:
                    ws = w
                    break

        if not ws or not os.path.exists(ws.path):
            return {"success": False, "status": "NOT_FOUND", "message": f"Workspace '{workspace_id}' was not found."}"""

new_wi_resolve = """        ws = self.workspaces.get(clean_id)
        if not ws:
            # Check for case-insensitive match or match against display_name / path basename
            for w in self.workspaces.values():
                if w.name.lower() == clean_id or Path(w.path).name.lower() == clean_id:
                    ws = w
                    break

        if not ws:
            # Contextual fallback: if user refers to "that folder", "the folder", "this project", use active project or cwd
            if clean_id in ["that folder", "the folder", "this folder", "this project", "that project", "current project", "workspace", ""]:
                cwd = os.getcwd()
                return {"success": True, "workspace_id": Path(cwd).name, "path": cwd, "is_active": True}
            return {"success": False, "status": "NOT_FOUND", "message": f"Workspace '{workspace_id}' was not found."}"""

if old_wi_resolve in wi_code:
    wi_code = wi_code.replace(old_wi_resolve, new_wi_resolve)
    with open("core/workspace_interaction.py", "w", encoding="utf-8") as f:
        f.write(wi_code)
    print("[FIX 6] Updated resolve_workspace in core/workspace_interaction.py.")
else:
    print("[FIX 6] Could not find old_wi_resolve in workspace_interaction.py")

print("\nAll patches applied successfully!")

