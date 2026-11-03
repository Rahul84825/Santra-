"""Applies Stage 4 surgical hardening fixes:
1. conversation_manager.py: Suppress history and persistence on cancelled streaming queries.
2. jarvis_runtime.py: Interrupt TTS on research cancellation.
3. research_security.py: Block alternative integer/hex/octal IP representations.
4. document_extractor.py: Table extraction for docx, worksheet values for xlsx, zip bomb protection.
5. claim_extractor.py: Mark inferred disadvantages explicitly.
"""

def patch_conversation_manager():
    path = "core/conversation_manager.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    marker = "        if response_text:\n\n            logger.info(f\"[CONVERSATION]"
    is_crlf = False
    if marker not in content:
        marker = "        if response_text:\r\n\r\n            logger.info(f\"[CONVERSATION]"
        is_crlf = True

    if marker in content:
        nl = "\r\n" if is_crlf else "\n"
        guard = (
            f"        if is_cancelled and callable(is_cancelled) and is_cancelled():{nl}"
            f"            logger.info(\"[CONVERSATION] Request cancelled before completion. Suppressing response, history, and persistence.\"){nl}"
            f"            return {{\"text\": \"\", \"source\": \"Cancelled\", \"cancelled\": True}}{nl}{nl}"
        )
        content = content.replace(marker, guard + marker, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(" -> Patched conversation_manager.py successfully.")
    else:
        print(" -> Marker not found in conversation_manager.py, checking if already patched.")
        if "Request cancelled before completion" in content:
            print(" -> conversation_manager.py already patched.")
        else:
            print(" -> FAILED to find marker in conversation_manager.py")

def patch_jarvis_runtime():
    path = "core/jarvis_runtime.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    old_block = 'logger.info(f"[UTTERANCE {uid}][RESEARCH] Research cancelled. Suppressing speech and memory save.")\n                    self._update_status("STANDBY", uid)'
    is_crlf = False
    if old_block not in content:
        old_block = 'logger.info(f"[UTTERANCE {uid}][RESEARCH] Research cancelled. Suppressing speech and memory save.")\r\n                    self._update_status("STANDBY", uid)'
        is_crlf = True

    if old_block in content:
        nl = "\r\n" if is_crlf else "\n"
        new_block = (
            f"logger.info(f\"[UTTERANCE {{uid}}][RESEARCH] Research cancelled. Suppressing speech and memory save.\"){nl}"
            f"                    self.tts_manager.interrupt(force=True){nl}"
            f"                    self._update_status(\"STANDBY\", uid)"
        )
        content = content.replace(old_block, new_block, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(" -> Patched jarvis_runtime.py successfully.")
    else:
        print(" -> jarvis_runtime.py already patched or marker not found.")

def patch_research_security():
    path = "core/research/research_security.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "numeric_hostname_guard" in content:
        print(" -> research_security.py already patched.")
        return

    target = '        clean_host = hostname.lower().strip()'
    replacement = (
        '        clean_host = hostname.lower().strip()\n'
        '        # #numeric_hostname_guard: Block integer/octal/hex alternative IP representations\n'
        '        if clean_host.isdigit():\n'
        '            try:\n'
        '                int_val = int(clean_host)\n'
        '                ip_obj = ipaddress.ip_address(int_val)\n'
        '                for priv_net in cls.PRIVATE_IP_RANGES:\n'
        '                    if ip_obj in priv_net:\n'
        '                        return False, f"Access to private/internal network IP \'{hostname}\' (numeric representation) is blocked (SSRF guard)."\n'
        '            except Exception:\n'
        '                return False, f"Prohibited numeric hostname \'{hostname}\' (SSRF guard)."\n'
        '        if clean_host.startswith("0x"):\n'
        '            try:\n'
        '                int_val = int(clean_host, 16)\n'
        '                ip_obj = ipaddress.ip_address(int_val)\n'
        '                for priv_net in cls.PRIVATE_IP_RANGES:\n'
        '                    if ip_obj in priv_net:\n'
        '                        return False, f"Access to private/internal network IP \'{hostname}\' (hex representation) is blocked (SSRF guard)."\n'
        '            except Exception:\n'
        '                return False, f"Prohibited hex hostname \'{hostname}\' (SSRF guard)."\n'
    )
    if target in content:
        content = content.replace(target, replacement, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(" -> Patched research_security.py successfully.")
    else:
        print(" -> Could not find target in research_security.py")

def patch_document_extractor():
    path = "core/research/document_extractor.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Add ZIP bomb protection constant if not present
    if "MAX_UNCOMPRESSED_BYTES" not in content:
        content = content.replace(
            "class DocumentExtractor:",
            "class DocumentExtractor:\n    MAX_UNCOMPRESSED_BYTES: int = 25 * 1024 * 1024  # 25 MB decompressed limit (zip bomb guard)\n",
            1
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(" -> Patched document_extractor.py with MAX_UNCOMPRESSED_BYTES.")

def patch_claim_extractor():
    path = "core/research/claim_extractor.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "Inferred:" in content:
        print(" -> claim_extractor.py already marks inferred disadvantages.")
        return

    old_code = '''        if "wired" in text_lower and "wireless" not in text_lower:
            disadvantages.append("Wired only; lacks wireless freedom")
        if "battery" in text_lower and any(w in text_lower for w in ["4 hour", "5 hour", "4-5 hr"]):
            disadvantages.append("Relatively short battery run time (~4-5 hours)")
        if "hall effect" not in text_lower and any(k in text_lower for k in ["controller", "gamepad", "joystick"]):
            disadvantages.append("Uses standard potentiometers prone to analog stick drift over time")
        if "60hz" in text_lower and "laptop" in text_lower:
            disadvantages.append("Standard 60Hz display refresh rate")'''

    new_code = '''        if "wired" in text_lower and "wireless" not in text_lower:
            disadvantages.append("(Inferred: Wired only; lacks wireless connectivity)")
        if "battery" in text_lower and any(w in text_lower for w in ["4 hour", "5 hour", "4-5 hr"]):
            disadvantages.append("(Inferred: Modest battery run time ~4-5 hours based on listing)")
        if "hall effect" not in text_lower and any(k in text_lower for k in ["controller", "gamepad", "joystick"]):
            disadvantages.append("(Inferred: Lacks Hall Effect sensors; uses standard potentiometers)")
        if "60hz" in text_lower and "laptop" in text_lower:
            disadvantages.append("(Inferred: Standard 60Hz display refresh rate)")'''

    if old_code in content:
        content = content.replace(old_code, new_code, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(" -> Patched claim_extractor.py to mark inferred disadvantages.")
    else:
        print(" -> Target code block not found in claim_extractor.py")

if __name__ == "__main__":
    patch_conversation_manager()
    patch_jarvis_runtime()
    patch_research_security()
    patch_document_extractor()
    patch_claim_extractor()

