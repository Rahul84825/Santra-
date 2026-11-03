import re

# 1. Update core/research/research_security.py
with open("core/research/research_security.py", "r", encoding="utf-8") as f:
    sec_code = f.read()

old_sec_pattern = """    INJECTION_PATTERNS = [
        r"(?i)\\bignore\\s+(?:all\\s+)?previous\\s+instructions\\b",
        r"(?i)\\bdisregard\\s+(?:all\\s+)?prior\\s+prompts?\\b",
        r"(?i)\\byou\\s+are\\s+now\\s+(?:an?\\s+)?unrestricted\\b",
        r"(?i)\\bsystem\\s*:\\s*you\\s+must\\b",
        r"(?i)\\bdeveloper\\s+mode\\s+enabled\\b",
        r"(?i)\\bdelete\\s+(?:all\\s+)?files\\b",
        r"(?i)\\brun\\s+(?:powershell|cmd|bash|terminal)\\b",
        r"(?i)\\bformat\\s+c:\\b",
        r"(?i)\\bexecute\\s+(?:the\\s+following\\s+code|os\\.system|subprocess)\\b"
    ]"""

new_sec_pattern = """    INJECTION_PATTERNS = [
        r"(?i)\\bignore\\s+(?:all\\s+)?previous\\s+instructions\\b",
        r"(?i)\\bdisregard\\s+(?:all\\s+)?prior\\s+(?:orders?|instructions?|prompts?)\\b",
        r"(?i)\\bsystem\\s+instructions?\\s*:\\b",
        r"(?i)\\byou\\s+are\\s+now\\s+(?:an?\\s+)?unrestricted\\b",
        r"(?i)\\bsystem\\s*:\\s*you\\s+must\\b",
        r"(?i)\\bdeveloper\\s+mode\\s+enabled\\b",
        r"(?i)\\bdelete\\s+(?:all\\s+)?(?:user\\s+)?(?:files|records|data)\\b",
        r"(?i)\\brun\\s+(?:powershell|cmd|bash|terminal)\\b",
        r"(?i)\\bformat\\s+c:\\b",
        r"(?i)\\bexecute\\s+(?:the\\s+following\\s+code|os\\.system|subprocess)\\b"
    ]"""

sec_code_norm = sec_code.replace("\r\n", "\n")
old_sec_norm = old_sec_pattern.replace("\r\n", "\n")
if old_sec_norm in sec_code_norm:
    sec_code_norm = sec_code_norm.replace(old_sec_norm, new_sec_pattern)
    with open("core/research/research_security.py", "w", encoding="utf-8") as f:
        f.write(sec_code_norm)
    print("Successfully updated research_security.py")
else:
    print("Could not find old pattern in research_security.py")

# 2. Update tests/test_stage4_production_verification.py
with open("tests/test_stage4_production_verification.py", "r", encoding="utf-8") as f:
    test_code = f.read()

test_code_norm = test_code.replace("\r\n", "\n")

# Replace test_04 cm instantiation
test_code_norm = test_code_norm.replace(
    "cm = ConversationManager(persistence_enabled=False)",
    "cm = ConversationManager()\n        cm.persistence = MagicMock()"
)

# Replace test_15 to use EvidenceItem and verify_evidence
old_test_15 = """    def test_15_syndicated_wire_copy_discounted(self):
        \"\"\"Verify that identical syndicated text across multiple domains is discounted.\"\"\"
        src_a = Source(
            source_id="src_a",
            domain="technews-portal-a.in",
            title="Exclusive Laptop Launch Review",
            raw_snippet="Lenovo officially launched the LOQ 15 gaming laptop featuring RTX 2050 graphics today in New Delhi.",
            authority_score=0.80
        )
        src_b = Source(
            source_id="src_b",
            domain="technews-portal-b.com",
            title="Lenovo LOQ 15 Arrives",
            raw_snippet="Lenovo officially launched the LOQ 15 gaming laptop featuring RTX 2050 graphics today in New Delhi.",
            authority_score=0.80
        )
        # Process through source verifier
        verified = source_verifier.verify_sources([src_a, src_b])
        # Second source with identical excerpt should be recognized as syndicated copy
        self.assertLessEqual(verified[1].authority_score, 0.70)"""

new_test_15 = """    def test_15_syndicated_wire_copy_discounted(self):
        \"\"\"Verify that identical syndicated text across multiple domains is discounted.\"\"\"
        from core.research.research_models import EvidenceItem
        ev_a = EvidenceItem(
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
        )
        # Process through source verifier
        verified = source_verifier.verify_evidence([ev_a, ev_b])
        # Second evidence item with identical excerpt should be discounted for syndication
        self.assertLessEqual(verified[1].confidence, 0.70)"""

if old_test_15 in test_code_norm:
    test_code_norm = test_code_norm.replace(old_test_15, new_test_15)
    print("Replaced test_15 in test_stage4_production_verification.py")
else:
    print("Could not find old test_15 in test_code")

with open("tests/test_stage4_production_verification.py", "w", encoding="utf-8") as f:
    f.write(test_code_norm)
print("Successfully written test_stage4_production_verification.py")

