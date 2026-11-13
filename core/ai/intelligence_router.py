import re
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List

from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.os.project_registry import ProjectRegistry
from memory.persistent_memory import persistent_memory

logger = logging.getLogger("Jarvis.IntelligenceRouter")

# Mode Constants
MODE_FAST_LOCAL = "FAST_LOCAL"
MODE_CONTEXT = "CONTEXT"
MODE_REASONING = "REASONING"
MODE_QUESTION = "QUESTION"

LAYER_1 = 1  # Reflex / Fast Local
LAYER_2 = 2  # Understanding / Context
LAYER_3 = 3  # Reasoning / Agent

@dataclass
class StructuredRequest:
    """Standardized Structured Request Object passed through the intelligence pipeline."""
    raw_text: str
    normalized_text: str
    mode: str
    layer: int
    intent: str
    action: str = ""
    target: str = ""
    confidence: float = 1.0
    context_required: bool = False
    planning_required: bool = False
    clarification_prompt: str = ""
    entities: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class IntelligenceRouter:
    """Central Intelligence Router for Jarvis.
    Routes user speech across:
      Layer 1 (Reflex / Fast Local) -> Zero-latency deterministic OS tools
      Layer 2 (Understanding / Context) -> Context resolution & preferences
      Layer 3 (Reasoning / Agentic) -> Multi-step ReAct agent planning
    """

    def __init__(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.project_registry = ProjectRegistry()

    def classify(self, raw_text: str, session_context: Optional[Dict[str, Any]] = None, ai_mode: bool = False) -> StructuredRequest:
        """Alias for route() method for classification."""
        return self.route(raw_text, session_context, ai_mode=ai_mode)

    def route(self, raw_text: str, session_context: Optional[Dict[str, Any]] = None, normalized: Optional[str] = None, ai_mode: bool = False) -> StructuredRequest:
        """Analyzes and classifies raw user speech into a StructuredRequest with fast confidence-aware first-stage routing."""
        t0 = time.perf_counter()
        if not raw_text or not raw_text.strip():
            return StructuredRequest(
                raw_text="",
                normalized_text="",
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="EMPTY",
                action="standby",
                target="runtime",
                confidence=1.0,
                context_required=False,
                planning_required=False
            )

        if normalized is None:
            norm_res = self.normalizer.normalize(raw_text)
            normalized = norm_res["normalized"]
        clean = normalized.lower().strip()
        raw_clean = raw_text.lower().strip()
        clean_no_punct = re.sub(r"[^\w\s]", "", clean).strip()

        # Step 0: Explicit Model Prefix Routing (e.g. 'nvidia:', 'nemotron:')
        if any(raw_clean.startswith(pref) for pref in ["nvidia:", "nemotron:"]):
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Classified as LAYER 3 NEMOTRON (Explicit Prefix, Latency={elapsed_ms:.2f}ms)")
            clean_sub = re.sub(r"^(?:nvidia|nemotron):\s*", "", clean).strip()
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_REASONING,
                layer=LAYER_3,
                intent="NEMOTRON_REASONING",
                action="agent_plan_and_execute",
                target=clean_sub or clean,
                confidence=1.0,
                context_required=True,
                planning_required=True
            )

        # Step 0A: Instant Reflex for Stop Talking (Layer 1 Fast Local)
        if clean in ["stop", "stop talking", "stop speaking", "be quiet", "shut up", "hush", "silence"]:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Classified as STOP_TALKING (Reflex, Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="STOP_TALKING",
                action="stop_speech",
                target="tts",
                confidence=1.0,
                context_required=False,
                planning_required=False
            )

        # Step 0B: User Corrections ("no, I meant...", "actually, use...", "Open Brave, not Chrome", "This method failed")
        is_correction = (
            re.search(r"^(?:no|actually|correction)[,:\s]+(?:i meant|use|not|it's|it is|i said)", clean) or
            clean.startswith("no, ") or clean.startswith("no i meant") or
            re.search(r",\s*not\s+[a-zA-Z0-9_\-]+", clean) or
            re.search(r"\bnot\s+(?:the\s+)?(?:folder|directory|file|path)\s+(?:i\s+meant|wanted)\b", clean) or
            re.search(r"\bthat\s+is\s+not\s+(?:the\s+)?(?:folder|directory|file|path)\b", clean) or
            re.search(r"\bthis\s+method\s+failed\b", clean) or
            clean.startswith("instead of ")
        )
        if is_correction:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Classified as CORRECTION (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="CORRECTION",
                action="apply_correction",
                target=clean,
                confidence=0.98,
                context_required=True,
                planning_required=False
            )

        # Step 0C: Explicit Model / Provider Routing ("Ask Nemotron...", "Ask NVIDIA...")
        nemotron_match = re.search(r"^(?:ask\s+)?(?:nvidia|nemotron)(?:\s+to|\s*[,:]\s*|\s+model\s+to|\s+ai\s+to|\s+explain\s+)(.+)$", clean)
        if nemotron_match:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            prompt = nemotron_match.group(1).strip()
            logger.info(f"[ROUTER] Classified as NEMOTRON_REASONING (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_REASONING,
                layer=LAYER_3,
                intent="NEMOTRON_REASONING",
                action="agent_plan_and_execute",
                target=prompt if prompt.startswith("explain") else f"explain {prompt}",
                confidence=0.98,
                context_required=True,
                planning_required=True,
                entities={"prompt": prompt, "provider": "nvidia"}
            )

        # Step 0D: Fast Conversational Small Talk, Greetings & Social Reflexes (Latency < 0.1ms)
        # Dedicated JARVIS / F.R.I.D.A.Y. Fast-Path Greeting Reflex
        greeting_rx1 = re.compile(r"^(?:hello|hey|hi|heya|good\s+(?:morning|afternoon|evening)|greetings)\s*(?:santra|sandra|samtra|jarvis|friday)?[\s!.,?]*$", re.IGNORECASE)
        greeting_rx2 = re.compile(r"^(?:santra|sandra|samtra|jarvis|friday)\s*,\s*(?:hello|hey|hi|heya|good\s+(?:morning|afternoon|evening)|greetings)[\s!.,?]*$", re.IGNORECASE)
        greeting_rx3 = re.compile(r"^(?:santra|sandra|samtra|jarvis|friday)\s+(?:hello|hey|hi|heya|good\s+(?:morning|afternoon|evening)|greetings)[\s!.,?]*$", re.IGNORECASE)

        is_greeting = bool(
            greeting_rx1.match(raw_clean) or greeting_rx1.match(clean) or
            greeting_rx2.match(raw_clean) or greeting_rx2.match(clean) or
            greeting_rx3.match(raw_clean) or greeting_rx3.match(clean) or
            clean in ["hi", "hello", "hey", "heya", "greetings", "good morning", "good afternoon", "good evening", "hi santra", "hello santra", "hey santra"] or
            clean_no_punct in ["hi", "hello", "hey", "heya", "greetings", "good morning", "good afternoon", "good evening", "hi santra", "hello santra", "hey santra"]
        )

        if is_greeting:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as GREETING_REFLEX (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="GREETING_REFLEX",
                action="greeting_reflex",
                target=clean,
                confidence=1.0,
                context_required=False,
                planning_required=False
            )

        # Conversational Inquiries: "How are you?", "How are you doing?", "How's it going?"
        how_are_you_phrases = [
            "how are you", "how are you doing", "how's it going", "how is it going",
            "how have you been", "how r u", "how are things", "how's everything",
            "what's up", "whats up", "what is up", "how do you do", "are you okay", "are you alright"
        ]
        if any(clean_no_punct == p or clean_no_punct.startswith(p + " ") or clean_no_punct.endswith(" " + p) for p in how_are_you_phrases):
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as HOW_ARE_YOU (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="HOW_ARE_YOU",
                action="respond_how_are_you",
                target="how are you",
                confidence=1.0,
                context_required=False,
                planning_required=False
            )

        # Fast Social Humor: "Tell me a joke", "Make me laugh"
        joke_phrases = ["tell me a joke", "tell a joke", "make me laugh", "say something funny", "tell another joke", "another joke", "give me a joke"]
        if any(clean_no_punct == j or clean_no_punct.startswith(j + " ") for j in joke_phrases):
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as SOCIAL_HUMOR (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="SOCIAL_HUMOR",
                action="tell_joke",
                target="joke",
                confidence=1.0,
                context_required=False,
                planning_required=False,
                entities={"action": "tell_joke"}
            )

        # Step 0D2: Fast Stealth / Hologram HUD Voice Summoning Fast Paths (Layer 1 Fast Local)
        show_hud_phrases = [
            "open your panel", "open panel", "show panel", "show hud", "bring up hud",
            "display panel", "open hud", "open the panel", "show the panel", "show the hud",
            "open the hud", "display hud", "display the hud", "santra open your panel", "santra show panel",
            "show dashboard", "open dashboard", "show santra dashboard", "open santra dashboard"
        ]
        if clean in show_hud_phrases or clean_no_punct in show_hud_phrases or re.search(r"^(?:open|show|display|bring\s+up)\s+(?:your\s+|the\s+)?(?:panel|hud|dashboard)\b", clean):
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as SHOW_PANEL (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="SHOW_PANEL",
                action="show_panel",
                target="hud_panel",
                confidence=1.0,
                context_required=False,
                planning_required=False
            )

        hide_hud_phrases = [
            "hide your panel", "hide panel", "close panel", "minimize hud", "go to stealth",
            "hide hud", "hide the panel", "hide the hud", "close the panel", "close hud",
            "close the hud", "stealth mode", "enter stealth mode", "santra hide panel",
            "dismiss panel", "dismiss the panel", "dismiss hud", "dismiss the hud",
            "minimize dashboard", "hide dashboard", "minimize santra dashboard", "hide santra dashboard"
        ]
        if clean in hide_hud_phrases or clean_no_punct in hide_hud_phrases or re.search(r"^(?:hide|close|minimize|dismiss)\s+(?:your\s+|the\s+)?(?:panel|hud|dashboard)\b", clean) or "go to stealth" in clean:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as HIDE_PANEL (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="HIDE_PANEL",
                action="hide_panel",
                target="hud_panel",
                confidence=1.0,
                context_required=False,
                planning_required=False
            )

        # Step 0E: GUI Confirmation & Cancellation Fast Paths (Layer 1 Fast Local)
        confirm_phrases = [
            "yes send it", "yes, send it", "go ahead", "press enter", "confirm send",
            "send it", "submit it", "yes send", "confirm and send", "yes please send it",
            "yes", "send", "confirm", "submit", "please send it", "do it"
        ]
        if clean in confirm_phrases or clean_no_punct in confirm_phrases or clean in ["yes", "send", "confirm", "submit"]:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as CONFIRM_ACTION (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="CONFIRM_ACTION",
                action="confirm_pending_gui_action",
                target="pending_gui_action",
                confidence=1.0,
                context_required=False,
                planning_required=False
            )

        cancel_gui_phrases = [
            "cancel that", "don't send", "dont send", "don t send", "do not send", "cancel send",
            "cancel the send", "discard draft", "do not submit", "don't submit", "dont submit", "don t submit",
            "cancel", "no", "discard", "stop"
        ]
        if clean in cancel_gui_phrases or clean_no_punct in cancel_gui_phrases or re.search(r"^(?:don'?t|don\s+t|do\s+not)\s+send\b", clean) or clean in ["cancel", "no", "discard"]:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as CANCEL_ACTION (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="CANCEL_ACTION",
                action="cancel_pending_gui_action",
                target="pending_gui_action",
                confidence=1.0,
                context_required=False,
                planning_required=False
            )

        # Step 0F: Screen Perception & UI Grounding Fast Paths (Layer 1 Fast Local)
        screen_patterns = [
            r"\b(?:analyze|read|inspect|what(?:'s|s|\s+is)|bots?)\s+(?:on\s+)?(?:the\s+|my\s+)?screen\b",
            r"\b(?:analyze|read|inspect|describe|summarize)?\s*(?:what(?:'s|s|\s+is)\s+)?(?:on\s+)?(?:the\s+|my\s+)?screen\b",
            r"\b(?:screen\s+analysis|read\s+this\s+error|read\s+active\s+window)\b",
            r"^(?:analyze|inspect|read|describe|summarize)\s+(?:my\s+|the\s+|this\s+|current\s+)?(?:screen|active\s+window|display)\b",
            r"^(?:read|check|inspect)\s+(?:this\s+|the\s+)?error\b"
        ]
        if any(re.search(pat, clean, re.IGNORECASE) or re.search(pat, raw_text, re.IGNORECASE) for pat in screen_patterns):
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as SCREEN_ANALYSIS (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="SCREEN_ANALYSIS",
                action="capture_screen_context",
                target="active_window",
                confidence=0.98,
                context_required=False,
                planning_required=False
            )

        # Step 0G: GUI Typing & Input Box Grounding Fast Paths (Layer 1 Fast Local)
        type_match = re.search(r"^(?:type|enter|input|draft)(?:\s+(?:this|a\s+message))?(?:\s+(?:in|into)\s+(?:the\s+)?(?:input\s+box|input\s+field|text\s+box|box))?[:\s]+(.+)$", clean)
        if type_match and not clean.startswith("type of") and not clean.startswith("enter full") and not clean.startswith("enter fullscreen"):
            typed_text = type_match.group(1).strip().strip("\"'")
            # Strip trailing target location phrases (e.g. "into the input box", "in the text box")
            typed_text = re.sub(r"\s+(?:in|into)\s+(?:the\s+)?(?:input\s+box|input\s+field|text\s+box|box)$", "", typed_text, flags=re.IGNORECASE).strip().strip("\"'")
            if typed_text:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.info(f"[ROUTER] Fast-path classified as GUI_TYPE_TEXT (Latency={elapsed_ms:.2f}ms)")
                return StructuredRequest(
                    raw_text=raw_text,
                    normalized_text=normalized,
                    mode=MODE_FAST_LOCAL,
                    layer=LAYER_1,
                    intent="GUI_TYPE_TEXT",
                    action="type_into_input_box",
                    target=typed_text,
                    confidence=0.98,
                    context_required=False,
                    planning_required=False,
                    entities={"text": typed_text, "auto_locate": True, "submit": False}
                )

        # Step 0H: Filesystem CRUD Fast Paths (Layer 1 Fast Local)
        # Create folder with destination target separation (Desktop, Documents, Downloads, etc.)
        create_dir_match = re.search(
            r"^(?:create|make)\s+(?:a\s+)?(?:folder|directory)\s+(?:called|named)?\s*[\"']?([^,\"']+)[\"']?(?:\s*,\s*|\s+)?(?:(?:in|on|at)\s+(?:my\s+|the\s+)?(desktop|documents|downloads|workspace|home))?\s*$",
            clean,
            re.IGNORECASE
        )
        if create_dir_match:
            from modules.system.filesystem_crud import extract_name_and_destination, resolve_path
            raw_target = create_dir_match.group(1).strip()
            explicit_dest = create_dir_match.group(2)

            clean_name, extracted_dest = extract_name_and_destination(raw_target)

            # Preserve exact casing from raw_text if provided (e.g. "Project")
            raw_match = re.search(
                r"^(?:create|make)\s+(?:a\s+)?(?:folder|directory)\s+(?:called|named)?\s*[\"']?([^,\"']+)[\"']?(?:\s*,\s*|\s+)?(?:(?:in|on|at)\s+(?:my\s+|the\s+)?(desktop|documents|downloads|workspace|home))?\s*$",
                raw_text,
                re.IGNORECASE
            )
            if raw_match:
                cased_name, _ = extract_name_and_destination(raw_match.group(1).strip())
                if cased_name:
                    clean_name = cased_name

            final_dest = explicit_dest or extracted_dest
            target_path_obj = resolve_path(clean_name, destination=final_dest)
            target_path_str = str(target_path_obj)
            target_val = target_path_str if final_dest else clean_name

            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as FS_CREATE_FOLDER (Latency={elapsed_ms:.2f}ms, Dest={final_dest})")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="FS_CREATE_FOLDER",
                action="create_folder",
                target=target_val,
                confidence=0.98,
                context_required=False,
                planning_required=False,
                entities={"name": clean_name, "destination": final_dest, "path": target_path_str}
            )

        # Create file
        create_file_match = re.search(r"^(?:create|make)\s+(?:a\s+)?file(?:\s+called|\s+named)?\s+([a-zA-Z0-9_\-\.\s/\\:~]+)$", clean)
        if create_file_match:
            file_name = create_file_match.group(1).strip()
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as FS_CREATE_FILE (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="FS_CREATE_FILE",
                action="create_file",
                target=file_name,
                confidence=0.98,
                context_required=False,
                planning_required=False,
                entities={"path": file_name, "content": ""}
            )

        # List files / directory
        list_dir_match = re.search(r"^(?:list|show)\s+(?:all\s+)?(?:files|directories|folders|directory|items)(?:\s+in\s+([a-zA-Z0-9_\-\.\s/\\:~]+))?$", clean)
        if list_dir_match:
            dir_path = (list_dir_match.group(1) or "").strip()
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as FS_LIST_DIRECTORY (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="FS_LIST_DIRECTORY",
                action="list_directory",
                target=dir_path or "current",
                confidence=0.98,
                context_required=False,
                planning_required=False,
                entities={"path": dir_path or None}
            )

        # Trash / recycle / delete item
        trash_match = re.search(r"^(?:can\s+you\s+|please\s+|could\s+you\s+)?(?:trash|recycle|delete|remove)\s+(?:the\s+)?(?:file|folder|directory|item)?\s*([a-zA-Z0-9_\-\.\s/\\:~]+)$", clean, re.IGNORECASE)
        if trash_match and not clean.startswith("delete history") and not clean.startswith("delete memory"):
            raw_item = trash_match.group(1).strip()
            # Strip generic entity nouns (folder, directory, file) unless it's a pronoun
            clean_item = re.sub(r"\b(folder|directory|file)\b", "", raw_item, flags=re.IGNORECASE).strip().strip(" ,'\"")
            final_target = clean_item if clean_item else raw_item
            if final_target:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.info(f"[ROUTER] Fast-path classified as FS_TRASH_ITEM (Target='{final_target}', Latency={elapsed_ms:.2f}ms)")
                return StructuredRequest(
                    raw_text=raw_text,
                    normalized_text=normalized,
                    mode=MODE_FAST_LOCAL,
                    layer=LAYER_1,
                    intent="FS_TRASH_ITEM",
                    action="trash_item",
                    target=final_target,
                    confidence=0.98,
                    context_required=False,
                    planning_required=False,
                    entities={"path": final_target}
                )

        # Open in IDE / Open With Fast Path (Layer 1 Fast Local)
        open_ide_match = re.search(
            r"\bopen\s+(?:(it|this|that|the\s+folder|the\s+project|the\s+file)|([a-zA-Z0-9_\-\.\s/\\:~]+?))\s+(?:in|with)\s+(vscode|vs\s*code|code|antigravity)\b",
            clean,
            re.IGNORECASE
        )
        if open_ide_match:
            pronoun_group = open_ide_match.group(1)
            target_group = open_ide_match.group(2)
            ide_group = open_ide_match.group(3).lower().replace(" ", "")
            ide_name = "vscode" if ide_group in ("vscode", "code") else "antigravity"

            raw_target = (pronoun_group or target_group or "it").strip()
            is_pronoun = raw_target.lower() in ("it", "this", "that", "the folder", "the project", "the file")
            if is_pronoun:
                target_clean = "it"
            else:
                target_clean = re.sub(r"\b(folder|directory|file)\b", "", raw_target, flags=re.IGNORECASE).strip().strip(" ,'\"")
                if not target_clean:
                    target_clean = "it"
                    is_pronoun = True

            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as OPEN_IN_IDE ({ide_name}, Target={target_clean}, Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="OPEN_IN_IDE",
                action="open_in_ide",
                target=target_clean,
                confidence=1.0,
                context_required=False,
                planning_required=False,
                entities={"ide": ide_name, "target": target_clean, "pronoun": is_pronoun}
            )

        # Read file
        read_file_match = re.search(r"^(?:read|display|cat)\s+(?:the\s+)?file\s+([a-zA-Z0-9_\-\.\s/\\:~]+)$", clean)
        if read_file_match:
            file_path = read_file_match.group(1).strip()
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as FS_READ_FILE (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent="FS_READ_FILE",
                action="read_file",
                target=file_path,
                confidence=0.98,
                context_required=False,
                planning_required=False,
                entities={"path": file_path}
            )

        # Step 1: Detect Complex Multi-Step / Reasoning Requests (Layer 3)
        if self._is_complex_reasoning(clean, raw_text):
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Classified as LAYER 3 REASONING (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_REASONING,
                layer=LAYER_3,
                intent="COMPLEX_TASK",
                action="agent_plan_and_execute",
                target=clean,
                confidence=0.92,
                context_required=True,
                planning_required=True
            )

        # Step 1B: Check Contextual References & Pronominals (Layer 2)
        contextual_req = self._check_contextual_request(raw_text, normalized, clean, session_context)
        if contextual_req:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Classified as LAYER 2 CONTEXT (Latency={elapsed_ms:.2f}ms)")
            return contextual_req

        # Step 2: Deterministic Local Parsing (Layer 1 Fast Direct Commands - < 1.5ms)
        # Parse directly with IntentEngine to execute without unnecessary reasoning loops
        intent_node = self.intent_engine.parse(normalized, raw_text=raw_text)
        intent = intent_node.get("intent", "unknown")
        confidence = intent_node.get("confidence", 0.0)

        deterministic_intents = {
            "open_app", "close_app", "minimize_app", "maximize_app", "window_control", "system_control",
            "open_new_chrome_tab", "open_new_chrome_window", "open_folder", "open_file",
            "screenshot", "time_query", "date_query", "math_calculation",
            "media_control", "open_website", "browser_action", "browser.action", "terminal_execute", "file_access",
            "web_search", "workspace.launch", "workspace_control", "launch_workspace",
            "application.launch", "application.properties", "application.install_dir",
            "application.settings", "application.metadata", "application.status",
            "application.list_installed", "application.refresh",
            "desktop.get_context", "desktop.enter_text", "desktop.search_in_app",
            "desktop.replace_selection", "desktop.send_message",
            "desktop_interaction.type_text", "desktop_interaction.write_reply",
            "desktop_interaction.search_app", "desktop_interaction.replace_selection",
            "desktop_interaction.continue_writing", "desktop_interaction.edit_draft",
            "desktop_interaction.paste_text", "desktop_interaction.send_message",
            "screen.analyze", "screen.explain", "screen_understanding.analyze", "screen_understanding.explain",
            "files.create", "files.search", "files.open", "file_management.create_file", "file_management.search",
            "file_management.open_project", "project.inspect", "ai.get_providers", "ai.update_provider",
            "ai.cache_stats", "ai.clear_cache", "ai.forget_cache",
            "ai_management.list_providers", "ai_management.update_provider",
            "ai_management.cache_stats", "ai_management.clear_cache", "ai_management.forget_cache",
            "system_telemetry", "greeting", "thank_you", "goodbye", "help",
            "identity", "repeat_response", "status_request", "acknowledgement",
            "affirmation", "negation", "cancellation", "how_are_you", "status_check",
            "turn_on_camera", "turn_off_camera", "start_hand_tracking", "stop_hand_tracking", "camera_snapshot",
            "social_humor", "social_personality", "social_chat", "social_greeting", "about",
            "spotify_control", "panel_visibility", "battery_info", "power_control", "power.scheme"
        }

        if (intent in deterministic_intents or
            intent.startswith("application.") or
            intent.startswith("desktop.") or
            intent.startswith("desktop_interaction.") or
            intent.startswith("screen.") or
            intent.startswith("screen_understanding.") or
            intent.startswith("files.") or
            intent.startswith("file_management.") or
            intent.startswith("ai.") or
            intent.startswith("ai_management.") or
            intent.startswith("virtual_lab.") or
            intent.startswith("power.")) and confidence >= 0.75:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] Fast-path classified as LAYER 1 FAST LOCAL ({intent}, Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_FAST_LOCAL,
                layer=LAYER_1,
                intent=intent.upper(),
                action=intent_node.get("action", intent),
                target=intent_node.get("target") or intent_node.get("query") or clean,
                confidence=confidence,
                context_required=False,
                planning_required=False,
                entities=intent_node
            )

        # Step 2.5: Detect Universal Research & Live Knowledge Queries
        if not ai_mode or raw_clean.startswith("research "):
            try:
                from core.research.research_router import research_router, ResearchIntent
                res_intent, res_constraints = research_router.classify_research_intent(raw_text)
                if res_intent and res_intent != ResearchIntent.GENERAL_KNOWLEDGE:
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    logger.info(f"[ROUTER] Classified as UNIVERSAL_RESEARCH ({res_intent.value}, Latency={elapsed_ms:.2f}ms)")
                    return StructuredRequest(
                        raw_text=raw_text,
                        normalized_text=normalized,
                        mode=MODE_REASONING,
                        layer=LAYER_3,
                        intent="UNIVERSAL_RESEARCH",
                        action=res_intent.value,
                        target=clean,
                        confidence=0.96,
                        context_required=True,
                        planning_required=False,
                        entities={"research_intent": res_intent.value, "constraints": res_constraints.to_dict() if res_constraints else {}}
                    )
            except Exception as re_err:
                logger.debug(f"[ROUTER] Research intent classification bypass: {re_err}")

        # Step 3: Detect Informational Questions (Strict Filter)
        if self._is_informational_question(raw_text, clean):
            elapsed_ms = (time.perf_counter() - t0) * 1000
            target_layer = LAYER_3 if ai_mode else LAYER_2
            target_mode = MODE_REASONING if ai_mode else MODE_QUESTION
            target_intent = "NEMOTRON_REASONING" if ai_mode else "informational_question"
            target_action = "agent_plan_and_execute" if ai_mode else "explain"
            logger.info(f"[ROUTER] Classified as QUESTION (Layer {target_layer}, Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=target_mode,
                layer=target_layer,
                intent=target_intent,
                action=target_action,
                target=clean,
                confidence=0.95,
                context_required=True,
                planning_required=ai_mode
            )

        # Step 4: If explicit AI_MODE is active, route exploratory or conversational queries to Layer 3 Nemotron
        if ai_mode:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[ROUTER] AI_MODE ACTIVE: Routing query to LAYER 3 NEMOTRON (Latency={elapsed_ms:.2f}ms)")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_REASONING,
                layer=LAYER_3,
                intent="NEMOTRON_REASONING",
                action="agent_plan_and_execute",
                target=clean,
                confidence=0.98,
                context_required=True,
                planning_required=True,
                entities={"ai_mode": True}
            )

        # Step 5: Fallback / Conversational Understanding (Layer 2)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"[ROUTER] Routed to LAYER 2 CONVERSATION (Fallback, Latency={elapsed_ms:.2f}ms)")
        return StructuredRequest(
            raw_text=raw_text,
            normalized_text=normalized,
            mode=MODE_CONTEXT,
            layer=LAYER_2,
            intent=intent.upper() if intent != "unknown" else "CONVERSATION",
            action=intent_node.get("action", "conversation"),
            target=intent_node.get("target", clean),
            confidence=max(confidence, 0.60),
            context_required=True,
            planning_required=False,
            entities=intent_node
        )

    def _is_informational_question(self, raw: str, clean: str) -> bool:
        """Determines if the request is an informational question rather than an imperative command."""
        # Desktop Intelligence, Screen Understanding & File Creation/Search Bypass
        if (
            re.search(r"^(?:explain|analyze|inspect|summarize)\s+(?:my\s+|this\s+|the\s+|current\s+)?(?:screen|page|website|tab|code|error|graph|pdf|point|section)\b", clean, re.IGNORECASE) or
            re.search(r"^(?:explain|describe|tell\s+me)\s+(?:what\s+is\s+on|what's\s+on)\s+(?:my\s+|this\s+|the\s+)?(?:screen|page)\b", clean, re.IGNORECASE) or
            re.search(r"^what\s+(?:is|'s)\s+on\s+(?:this|my|the)\s+screen\b", clean, re.IGNORECASE) or
            re.search(r"^(?:where\s+did\s+i\s+save|where\s+is\s+my\s+.*(?:program|file|code|repository|project|folder|readme)|find\s+(?:the\s+)?.*(?:created|saved|written))\b", clean, re.IGNORECASE) or
            re.search(r"^(?:what\s+are\s+the\s+important\s+points|what\s+does\s+this\s+error\s+mean|what\s+does\s+that\s+error\s+mean|what\s+is\s+this\s+button\s+used\s+for|what\s+is\s+on\s+my\s+screen|what\s+is\s+on\s+this\s+screen|compare\s+these\s+two)\b", clean, re.IGNORECASE) or
            clean.startswith("explain point ") or clean.startswith("explain the ") or clean.startswith("explain code ") or clean.startswith("explain the code ") or clean.startswith("i still don't understand") or
            "short answer first" in clean or "like i'm a beginner" in clean or
            clean.startswith("create a ") or clean.startswith("write a ") or clean.startswith("generate a ") or clean.startswith("save this explanation") or clean.startswith("save it in ") or
            clean.startswith("search this website") or clean.startswith("search the website") or
            "ai provider" in clean or "ai providers" in clean or "list ai" in clean or
            "cache stat" in clean or "caching save" in clean or "clear cache" in clean or ("forget" in clean and "cache" in clean)
        ):
            return False

        # Explicit search bypass (must be evaluated in Layer 1, not question fallback)
        if clean.startswith("search ") or "search youtube" in clean or "youtube search" in clean or "search the web" in clean or "search brave" in clean or "search chrome" in clean:
            return False

        # Math calculation bypass
        if any(op in clean for op in ["times", "plus", "minus", "divided by", "multiplied by", "+", "*", "/"]) and any(c.isdigit() for c in clean):
            return False

        # Time & Date bypass
        if any(t in clean for t in [
            "what time is it", "what's the time", "whats the time", "what is the time",
            "what is the date", "what's the date", "whats the date", "what day is it",
            "tell me what time", "tell me the time", "current time", "what time do you have",
            "time now", "today's date", "todays date", "today s date", "today date",
            "what date is", "tell me the date", "what is today"
        ]):
            return False

        # Battery & System Telemetry bypass (Route deterministically via Layer 1 tools, zero LLM latency)
        if any(b in clean for b in [
            "battery", "charging", "plugged in", "how long can i use the laptop",
            "how long can i use my laptop", "how long will the battery last", "how much time left on battery",
            "cpu info", "ram info", "disk space", "system uptime"
        ]):
            return False

        # Spotify inquiry bypass
        if any(h in clean for h in [
            "which song is playing", "what song is playing", "what's playing",
            "whats playing", "what is playing", "what is currently playing",
            "what playlists do i have", "what are my playlists", "show my playlists",
            "show playlists", "list my playlists", "list playlists", "spotify"
        ]):
            return False

        # Capabilities, Help, Identity & Social Intelligence bypass
        social_identity_bypass = [
            "what can you do", "what can jarvis do", "what are your capabilities",
            "what commands do you know", "what do you do", "show capabilities",
            "how can you help", "who are you", "who made you", "who built you",
            "who created you", "who is your developer", "who is your creator",
            "what is your name", "what's your name", "what does jarvis stand for",
            "what's jarvis stand for", "what does the name jarvis stand for",
            "what is your purpose", "what's your purpose", "are you a real person",
            "are you an ai", "are you real", "are you human", "are you like chatgpt",
            "what makes you different", "what makes you intelligent",
            "are you always listening", "can you hear me", "can you control my computer",
            "can you control this pc", "can you work without internet", "can you work offline",
            "what can you do offline", "can you search youtube", "can you open applications",
            "can you search the web", "what voice commands do you understand",
            "show all commands", "tell me a joke", "tell me a programming joke",
            "tell me a coding joke", "roast me", "give me a savage reply", "be sarcastic",
            "say something funny", "tell me a dark joke", "give me a nerdy joke",
            "make a joke about programmers", "tell me a random fun fact", "give me a tech fact",
            "introduce yourself dramatically", "roast my code", "say something that sounds like a futuristic ai",
            "fun fact", "another one", "tell me another", "be more funny", "be professional",
            "stop being sarcastic", "talk casually", "keep it short", "explain things in detail",
            "be more dramatic", "use your normal personality", "don't tell jokes for now",
            "enable humor", "disable humor", "i'm bored", "im bored", "guess what",
            "tell me something interesting", "surprise me", "let's talk", "lets talk",
            "how are you", "how are you doing", "how's it going", "how is it going",
            "how have you been", "how r u", "how are things", "how's everything",
            "what's up", "whats up", "what is up", "how do you do", "are you okay", "are you alright"
        ]
        if any(h in clean for h in social_identity_bypass):
            return False

        # Application discovery, properties, installation, and browser inquiry bypass (Phase 6)
        if re.search(r"\b(is|check\s+if)\s+.+?\s+installed\b", clean) or \
           re.search(r"\bwhere\s+is\s+.+?\s+installed\b", clean) or \
           re.search(r"\bwhat\s+version\s+of\s+.+?\s+is\s+installed\b", clean) or \
           re.search(r"\b(?:what\s+apps|what\s+applications|what\s+browsers|which\s+browsers)\b", clean) or \
           "installed applications" in clean or "available browsers" in clean or "my browsers" in clean or \
           "properties" in clean or "install folder" in clean or "installation folder" in clean or \
           "installation directory" in clean or "installed yesterday" in clean:
            return False

        # Desktop Interaction & Text Entry Bypass (Phase 7)
        if any(clean.startswith(p) for p in [
            "write a reply", "write a response", "draft a reply", "draft a response",
            "reply to this", "type this into", "type into", "type this in",
            "paste this into", "enter this code", "fill in the", "put this into",
            "search for", "enter the search term", "replace the selected text",
            "replace selection", "continue writing", "make the current draft", "send the message", "submit the form"
        ]) or "in this application" in clean or "in the current application" in clean or "in the search bar" in clean:
            return False

        question_starters = (
            "how do i", "how can i", "how to", "why does", "why is", "why isn't",
            "what is", "what does", "what are", "tell me about", "can you explain",
            "explain what", "explain why", "explain how", "explain in detail", "explain",
            "should i", "is it possible to", "who is", "where is the documentation for", "describe"
        )
        if any(clean.startswith(q) for q in question_starters):
            # Check if it contains an imperative override
            if not any(clean.startswith(f"{q} open ") or clean.startswith(f"{q} close ") for q in ["can you", "could you"]):
                return True

        if raw.strip().endswith("?") and not any(clean.startswith(p) for p in [
            "open", "close", "lock", "sleep", "restart", "shutdown",
            "take a screenshot", "take a photo", "turn on", "turn off", "start", "stop"
        ]):
            return True

        return False

    def _is_complex_reasoning(self, clean: str, raw_text: str = "") -> bool:
        """Identifies multi-step, investigative, coding, or planning requests (Layer 3)."""
        raw_clean = raw_text.lower().strip()

        # Follow-up questions and single-command task continuations should be routed to context, not complex reasoning
        if any(clean.startswith(p) for p in ["why did it fail", "why did that fail", "what went wrong", "what have you completed", "cancel the task", "stop what you're doing"]):
            return False
        if re.search(r"^(?:now\s+)?open\s+(?:the\s+)?(?:first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|\d+)(?:st|nd|rd|th)?\s+result$", clean):
            return False
        if clean.startswith("do the same on ") or clean in ["try that again", "skip this step", "continue", "continue task"]:
            return False

        reasoning_patterns = [
            r"prepare (?:my|the)?\s*(?:development|dev)?\s*environment",
            r"get (?:my|the)?\s*(?:development|dev)?\s*environment ready",
            r"check why (?:my|the)?\s*(?:backend|server|app|project|build|tests?)",
            r"find (?:the )?bug",
            r"fix (?:the |all )?(?:failing )?tests?",
            r"run (?:the )?tests and (?:fix|tell|report|explain)",
            r"compare (?:these|the)? .* architectures?",
            r"search (?:the )?internet for .* and summarize",
            r"search (?:the )?web and compare",
            r"find (?:the )?file where i implemented",
            r"find (?:the )?project i was working on",
            r"investigate why",
            r"diagnose (?:the )?issue",
            r"check git status, run (?:the )?tests",
            r"set up my project",
            # Multi-step agentic execution patterns
            r"(?:open|launch)\s+[a-zA-Z0-9_\-\s]+(?:,|,\s*and|\s+and|\s+then)\s+(?:search|navigate|write|explain|tell|help)",
            r"search\s+[a-zA-Z0-9_\-\s]+(?:,|,\s*and|\s+and|\s+then)\s+(?:open|tell|explain|navigate)",
            r"open\s+notepad\s+and\s+write",
            r"tell me when the page is ready",
            r"(?:and|then)\s+open\s+(?:the\s+)?(?:first|1st|second|2nd|third|3rd|\d+)\s+result",
            r"find\s+a\s+.*and\s+explain",
            r"help\s+me\s+draft",
            r"(?:find|search)\s+(?:the\s+|a\s+)?.*(?:online|on the web|on the internet|news)?\s+and\s+(?:explain|summarize)(?:\s+it)?",
            r"^(?:ask\s+)?(?:nvidia|nemotron)\b",
            # Programming, DSA, Algorithmic and Cloud Reasoning
            r"(?:solve|write|implement|debug)\s+.*(?:in\s+c\+\+|in\s+cpp|in\s+python|algorithm|data\s+structure|leetcode|binary\s+search|merge\s+sort|quicksort|bfs|dfs|dynamic\s+programming)",
            r"(?:write|implement|solve|code)\s+(?:leetcode|binary\s+search|merge\s+sort|quicksort|depth\s+first|breadth\s+first)",
            r"time\s+(?:and\s+)?(?:space\s+)?complexity|space\s+complexity",
            r"why\s+does\s+my\s+.*(?:algorithm|code|function|solution)\s+fail",
            r"compare\s+.*sort\s+and\s+.*sort",
            r"explain\s+this\s+error\s+and\s+suggest\s+(?:a\s+)?fix",
            r"plan\s+a\s+safe\s+sequence\s+of\s+steps",
            r"based\s+on\s+our\s+previous\s+question,\s+explain",
        ]
        return any(re.search(pat, clean) or re.search(pat, raw_clean) for pat in reasoning_patterns)

    def _check_contextual_request(
        self,
        raw_text: str,
        normalized: str,
        clean: str,
        session_context: Optional[Dict[str, Any]]
    ) -> Optional[StructuredRequest]:
        """Resolves Layer 2 contextual requests (pronominals, user preferences, project context, task follow-ups)."""
        ctx = session_context or {}
        last_target = ctx.get("last_target", "")
        last_action = ctx.get("last_action", "")
        active_project = ctx.get("active_project") or self.project_registry.current_project_alias or "jarvis"
        raw_clean = raw_text.lower().strip()

        # Contextual follow-up 00: Task Follow-ups & Lifecycle Controls
        # Cancellation / Abort
        if clean in [
            "cancel", "cancel that", "cancel the task", "cancel task", "stop what you're doing",
            "abort this workflow", "abort the workflow", "abort workflow", "abort task", "cancel the workflow",
            "forget about that", "never mind", "cancel that operation"
        ] or clean.startswith("cancel the task") or clean.startswith("stop what you're doing") or clean == "stop task" or clean.startswith("cancel that"):
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="cancel",
                target="active_task",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Retry
        if clean in ["try that again", "try again", "retry the task", "retry task", "retry last task", "retry"]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="retry",
                target="last_task",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Skip Step
        if clean in ["skip this step", "skip the current step", "skip step", "skip current step"]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="skip_step",
                target="current_step",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Continue / Resume
        if clean in [
            "continue", "continue task", "continue the task", "continue from where you stopped",
            "resume", "resume task", "resume workflow", "go on", "keep going", "okay continue", "ok continue",
            "now continue", "proceed", "carry on"
        ]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="continue",
                target="active_task",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Task Progress & Status
        if clean in [
            "what have you completed", "what have you completed?", "what did you do", "what did you do?",
            "what have you done", "what have you done?", "what's completed", "what's completed?",
            "what is completed?", "task status", "show task status", "show task progress", "what is the task status"
        ]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="status",
                target="task_status",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Failure Explanation
        if clean in [
            "why did it fail", "why did it fail?", "why did that fail", "why did that fail?",
            "what went wrong", "what went wrong?", "explain the failure", "explain why it failed", "why did the task fail"
        ]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="explain_failure",
                target="failure_reason",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Search Result Follow-up ("now open the second result", "open the 1st result")
        res_match = re.search(r"^(?:now\s+)?open\s+(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|\d+)(?:st|nd|rd|th)?\s+result$", clean)
        if res_match:
            idx_str = res_match.group(1).lower()
            ord_map = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5}
            idx_num = ord_map.get(idx_str, int(idx_str) if idx_str.isdigit() else 1)
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="open_result",
                target=str(idx_num),
                confidence=0.99,
                context_required=True,
                planning_required=False,
                entities={"index": idx_num - 1}
            )

        # Search Provider Switch ("do the same on youtube", "do the same on google")
        if clean in ["do the same on youtube", "try the same on youtube", "search the same on youtube", "do that on youtube", "now do the same on youtube"]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="switch_provider",
                target="youtube",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )
        if clean in ["do the same on google", "try the same on google", "search the same on google", "do that on google", "now do the same on google"]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="switch_provider",
                target="google",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Reopen Recent Tab ("open the tab you just used")
        if clean in ["open the tab you just used", "open the tab we just used", "reopen the tab you just used", "switch to the tab you just used"]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="TASK_FOLLOWUP",
                action="reopen_tab",
                target="recent_tab",
                confidence=0.99,
                context_required=True,
                planning_required=False
            )

        # Contextual follow-up 0A: Social humor "another one" / "tell me another"
        if clean in ["another one", "tell me another", "give me another", "give me another one", "one more", "tell another", "another"] or clean.startswith("another "):
            from core.social_engine import social_engine
            last_soc = getattr(social_engine, "_last_social_type", "joke") or "joke"
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="SOCIAL_HUMOR",
                action="followup",
                target="another",
                confidence=0.98,
                context_required=True,
                planning_required=False,
                entities={"last_social_type": last_soc}
            )

        # Contextual follow-up 0B: Creator other work follow-up
        if any(clean.startswith(p) for p in ["what else did they build", "what else did he build", "what else did she build", "what else did they make", "what else did he make"]):
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="IDENTITY",
                action="explain_identity",
                target="creator_other_work",
                confidence=0.98,
                context_required=True,
                planning_required=False,
                entities={"sub_type": "creator_other_work"}
            )

        # Contextual follow-up 0C: Follow-up to YouTube search capability inquiry
        if ctx.get("last_target") == "youtube" or ctx.get("last_topic") == "youtube":
            find_match = re.match(r"^(?:find(?:\s+me)?|search(?:\s+for)?|look\s+up)\s+(.+)$", clean)
            if find_match:
                extracted = find_match.group(1).strip()
                return StructuredRequest(
                    raw_text=raw_text,
                    normalized_text=normalized,
                    mode=MODE_CONTEXT,
                    layer=LAYER_2,
                    intent="WEB_SEARCH",
                    action="search",
                    target=extracted.lower(),
                    confidence=0.98,
                    context_required=True,
                    planning_required=False,
                    entities={"provider": "youtube", "browser": "default", "query": extracted, "raw_text": raw_text}
                )

        # 1. Pronominals: "close it", "minimize it", "maximize it"
        pronominal_match = re.search(r"^(?:now\s+)?(close|exit|quit|minimize|maximize|kill|shut)\s+(?:it|this|that|the app)$", clean)
        if pronominal_match:
            verb = pronominal_match.group(1)
            target = last_target or "active_app"
            action = "close_application" if verb in ["close", "exit", "quit", "kill", "shut"] else (
                "minimize_application" if verb == "minimize" else "maximize_application"
            )
            intent = "CLOSE_APP" if "close" in action else "WINDOW_CONTROL"
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent=intent,
                action=action,
                target=target,
                confidence=0.95,
                context_required=True,
                planning_required=False,
                entities={"resolved_from_context": True, "pronominal": True, "target": target}
            )

        # 2. Preference lookup: "open the browser I usually use" / "open my favorite editor"
        if "browser i usually use" in clean or "browser i normally use" in clean or "my default browser" in clean:
            pref_browser = persistent_memory.get_preference("default_browser", default="chrome")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="OPEN_APP",
                action="open_application",
                target=pref_browser,
                confidence=0.95,
                context_required=True,
                planning_required=False,
                entities={"preference_resolved": True, "key": "default_browser", "value": pref_browser}
            )

        # 3. Preference lookup: "open my coding environment" / "open my editor"
        if clean in ["open my coding environment", "open my editor", "launch my editor"]:
            pref_editor = persistent_memory.get_preference("default_editor", default="vscode")
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="OPEN_APP",
                action="open_application",
                target=pref_editor,
                confidence=0.95,
                context_required=True,
                planning_required=False,
                entities={"preference_resolved": True, "key": "default_editor", "value": pref_editor}
            )

        # 4. Project context commands: "work on <project>", "switch to <project>"
        switch_match = re.search(r"^(?:work on|switch to)\s+([a-zA-Z0-9_\-]+)$", raw_clean) or re.search(r"^(?:work on|switch to)\s+([a-zA-Z0-9_\-]+)$", clean)
        if switch_match:
            proj_name = switch_match.group(1).lower()
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="PROJECT_CONTROL",
                action="switch_project",
                target=proj_name,
                confidence=0.95,
                context_required=True,
                planning_required=False,
                entities={"project": proj_name}
            )

        # 5. Ambiguous project command: "open my project" / "run the tests"
        if clean in ["open my project", "open the project"]:
            known_projects = persistent_memory.list_projects()
            if not known_projects:
                known_projects = list(self.project_registry.projects.keys())

            if len(known_projects) > 1 and not ctx.get("explicit_project"):
                # Needs clarification
                proj_names = ", ".join([p.get("name", p) if isinstance(p, dict) else str(p).title() for p in known_projects[:3]])
                return StructuredRequest(
                    raw_text=raw_text,
                    normalized_text=normalized,
                    mode=MODE_CONTEXT,
                    layer=LAYER_2,
                    intent="CLARIFICATION_REQUIRED",
                    action="ask_clarification",
                    target="project",
                    confidence=0.90,
                    context_required=True,
                    planning_required=False,
                    clarification_prompt=f"Which project do you want — {proj_names}?",
                    entities={"ambiguous_type": "project", "options": known_projects}
                )
            else:
                return StructuredRequest(
                    raw_text=raw_text,
                    normalized_text=normalized,
                    mode=MODE_CONTEXT,
                    layer=LAYER_2,
                    intent="PROJECT_CONTROL",
                    action="open_project",
                    target=active_project,
                    confidence=0.90,
                    context_required=True,
                    planning_required=False,
                    entities={"project": active_project}
                )

        # 6. "run the tests" / "run tests" -> resolves to active project tests
        if clean in ["run the tests", "run tests", "execute tests"]:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="PROJECT_CONTROL",
                action="run_tests",
                target=active_project,
                confidence=0.95,
                context_required=True,
                planning_required=False,
                entities={"project": active_project}
            )

        # 7. Memory question: "what did I tell you about my project yesterday?" / "what is my name?"
        if "what did i tell you" in clean or "what is my name" in clean or "do you remember" in clean:
            return StructuredRequest(
                raw_text=raw_text,
                normalized_text=normalized,
                mode=MODE_CONTEXT,
                layer=LAYER_2,
                intent="MEMORY_QUERY",
                action="recall_memory",
                target=clean,
                confidence=0.90,
                context_required=True,
                planning_required=False
            )

        return None

# Global singleton
intelligence_router = IntelligenceRouter()
