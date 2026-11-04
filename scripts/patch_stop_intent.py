with open("core/intent_engine.py", "r", encoding="utf-8") as f:
    text = f.read().replace("\r\n", "\n")

target = """        # -------------------------------------------------------------
        # 0A. DEDICATED YOUTUBE SEARCH INTENT (TOP PRECEDENCE)
        # -------------------------------------------------------------"""

replacement = """        # -------------------------------------------------------------
        # 0. GLOBAL STOP & CANCELLATION (TOP PRIORITY)
        # -------------------------------------------------------------
        if clean in ["stop", "stop listening", "cancel", "terminate", "halt", "pause", "be quiet", "shut up", "stop talking", "abort"]:
            return {
                "intent": "system_action",
                "action": "stop",
                "target": None,
                "confidence": 1.0,
                "query": clean,
                "raw_text": effective_raw
            }

        # -------------------------------------------------------------
        # 0A. DEDICATED YOUTUBE SEARCH INTENT (TOP PRECEDENCE)
        # -------------------------------------------------------------"""

if target in text:
    text = text.replace(target, replacement)
    with open("core/intent_engine.py", "w", encoding="utf-8") as f:
        f.write(text)
    print("Successfully added global stop intent to core/intent_engine.py")
else:
    print("Could not find target in core/intent_engine.py")

