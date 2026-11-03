# Fix 1: core/research/research_security.py trailing \b on colon
with open("core/research/research_security.py", "r", encoding="utf-8") as f:
    sec_code = f.read()

sec_code = sec_code.replace(
    r'(?i)\bsystem\s+instructions?\s*:\b',
    r'(?i)\bsystem\s+instructions?\s*:'
)

with open("core/research/research_security.py", "w", encoding="utf-8") as f:
    f.write(sec_code)
print("Updated research_security.py regex")

# Fix 2: test_stage4_production_verification.py test_04 and test_15
with open("tests/test_stage4_production_verification.py", "r", encoding="utf-8") as f:
    test_code = f.read()

# Fix test_04:
old_test_04 = """    def test_04_cancelled_conversation_suppresses_history_and_persistence(self):
        \"\"\"Verify that when a conversation query is cancelled mid-stream, partial text is discarded.\"\"\"
        cm = ConversationManager()
        cm.persistence = MagicMock()
        cm.provider_manager = MagicMock()
        cm.provider_manager.is_ai_available.return_value = True
        cm.provider_manager.get_active_provider_name.return_value = "NVIDIA Nemotron"

        # Stream yields one sentence and then caller cancels
        cancelled = False
        def mock_stream(messages, is_cancelled=None):
            nonlocal cancelled
            yield "This is the first sentence."
            cancelled = True
            yield "This second sentence should be dropped."

        cm.provider_manager.stream_response = mock_stream
        res = cm.process_query("Tell me a long story", is_cancelled=lambda: cancelled)

        self.assertTrue(res.get("cancelled"), "Expected cancelled status")
        self.assertEqual(res.get("text"), "", "Cancelled query must return empty text")
        # Ensure no assistant turn was appended to history
        assistant_turns = [m for m in cm.history if m.get("role") == "assistant"]
        self.assertEqual(len(assistant_turns), 0, "No partial assistant response should be saved to history")"""

new_test_04 = """    def test_04_cancelled_conversation_suppresses_history_and_persistence(self):
        \"\"\"Verify that when a conversation query is cancelled mid-stream, partial text is discarded.\"\"\"
        cm = ConversationManager()
        cm.persistence = MagicMock()
        
        # Real-like mock provider with stream_response but without mock generate_response trigger
        class DummyStreamProvider:
            def get_active_provider_name(self):
                return "NVIDIA Nemotron"
            def is_ai_available(self):
                return True
            def stream_response(self, messages, is_cancelled=None):
                yield "This is the first sentence. "
                if is_cancelled and is_cancelled():
                    return
                yield "This second sentence should be dropped. "

        cm.provider_manager = DummyStreamProvider()

        # Stream yields one sentence, receiver cancels barge-in
        cancelled = False
        sentences_received = []
        def on_sentence(s):
            nonlocal cancelled
            sentences_received.append(s)
            cancelled = True

        res = cm.process_query("Tell me a long story", on_sentence=on_sentence, is_cancelled=lambda: cancelled)

        self.assertTrue(res.get("cancelled"), "Expected cancelled status")
        self.assertEqual(res.get("text"), "", "Cancelled query must return empty text")
        # Ensure no assistant turn was appended to history
        assistant_turns = [m for m in cm.history if m.get("role") == "assistant"]
        self.assertEqual(len(assistant_turns), 0, "No partial assistant response should be saved to history")"""

test_code_norm = test_code.replace("\r\n", "\n")
old_test_04_norm = old_test_04.replace("\r\n", "\n")
new_test_04_norm = new_test_04.replace("\r\n", "\n")

if old_test_04_norm in test_code_norm:
    test_code_norm = test_code_norm.replace(old_test_04_norm, new_test_04_norm)
    print("Replaced test_04")
else:
    print("Could not find old test_04")

# Fix test_15:
old_test_15 = """        ev_a = EvidenceItem(
            evidence_id="ev_a",
            claim_id="cl_1",
            source_id="src_a",
            source_domain="technews-portal-a.in",
            evidence_excerpt="Lenovo officially launched the LOQ 15 gaming laptop featuring RTX 2050 graphics today in New Delhi.",
            confidence=0.80
        )
        ev_b = EvidenceItem(
            evidence_id="ev_b",
            claim_id="cl_1",
            source_id="src_b",
            source_domain="technews-portal-b.com",
            evidence_excerpt="Lenovo officially launched the LOQ 15 gaming laptop featuring RTX 2050 graphics today in New Delhi.",
            confidence=0.80
        )"""

new_test_15 = """        ev_a = EvidenceItem(
            evidence_id="ev_a",
            claim_text="Lenovo officially launched the LOQ 15 gaming laptop featuring RTX 2050 graphics today in New Delhi.",
            source_id="src_a",
            source_domain="technews-portal-a.in",
            evidence_excerpt="Lenovo officially launched the LOQ 15 gaming laptop featuring RTX 2050 graphics today in New Delhi.",
            confidence=0.80
        )
        ev_b = EvidenceItem(
            evidence_id="ev_b",
            claim_text="Lenovo officially launched the LOQ 15 gaming laptop featuring RTX 2050 graphics today in New Delhi.",
            source_id="src_b",
            source_domain="technews-portal-b.com",
            evidence_excerpt="Lenovo officially launched the LOQ 15 gaming laptop featuring RTX 2050 graphics today in New Delhi.",
            confidence=0.80
        )"""

old_test_15_norm = old_test_15.replace("\r\n", "\n")
new_test_15_norm = new_test_15.replace("\r\n", "\n")

if old_test_15_norm in test_code_norm:
    test_code_norm = test_code_norm.replace(old_test_15_norm, new_test_15_norm)
    print("Replaced test_15")
else:
    print("Could not find old test_15")

with open("tests/test_stage4_production_verification.py", "w", encoding="utf-8") as f:
    f.write(test_code_norm)
print("Updated test_stage4_production_verification.py")

