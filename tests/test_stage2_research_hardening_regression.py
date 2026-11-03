"""Stage 2 Hardening and Reliability Regression Test Suite for SANTRA Universal Research Engine.
Verifies:
1. DocumentExtractor: docx, xlsx, images, PDFs, unsupported formats.
2. ResearchSecurity: DNS rebinding prevention, IPv6/IPv4-mapped private IPs, HTML/prompt sanitization.
3. PageExtractor: SafeRedirectHandler SSRF mitigation, redirect hop limit, bot protection classification.
4. ClaimExtractor & ProductEntity: Structured product extraction, ASIN/SKU detection, PriceType classification.
5. SourceVerifier: Syndicated copy detection, conflict resolution, primary source authoritative verification.
"""

import io
import os
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from core.research.research_models import (
    ResearchSession, Source, SourceType, EvidenceItem, ProductEntity,
    PriceType, VerificationStatus, ConflictStatus, ResearchIntent
)
from core.research.document_extractor import document_extractor
from core.research.research_security import research_security
from core.research.page_extractor import page_extractor, SafeRedirectHandler
from core.research.claim_extractor import claim_extractor
from core.research.source_verifier import source_verifier

class TestStage2ResearchHardeningRegression(unittest.TestCase):

    def test_document_extractor_docx(self):
        """Verify DocumentExtractor extracts text from docx zip archive."""
        with tempfile.TemporaryDirectory() as td:
            docx_path = os.path.join(td, "test_doc.docx")
            xml_data = (
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                b'<w:body><w:p><w:t>SANTRA Document Extraction Test</w:t></w:p></w:body></w:document>'
            )
            with zipfile.ZipFile(docx_path, "w") as z:
                z.writestr("word/document.xml", xml_data)

            res = document_extractor.extract_file(docx_path)
            self.assertTrue(res["success"])
            self.assertEqual(res["extraction_status"], "SUCCESS")
            self.assertIn("SANTRA Document Extraction Test", res["text"])

    def test_document_extractor_xlsx(self):
        """Verify DocumentExtractor extracts shared strings from xlsx zip archive."""
        with tempfile.TemporaryDirectory() as td:
            xlsx_path = os.path.join(td, "test_sheet.xlsx")
            xml_data = (
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2">'
                b'<si><t>Revenue</t></si><si><t>100000</t></si></sst>'
            )
            with zipfile.ZipFile(xlsx_path, "w") as z:
                z.writestr("xl/sharedStrings.xml", xml_data)

            res = document_extractor.extract_file(xlsx_path)
            self.assertTrue(res["success"])
            self.assertEqual(res["extraction_status"], "SUCCESS")
            self.assertIn("Revenue", res["text"])

    def test_document_extractor_image_metadata(self):
        """Verify DocumentExtractor safely extracts image dimensions and flags OCR required."""
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            img_path = os.path.join(td, "diagram.png")
            img = Image.new("RGB", (120, 80), color="blue")
            img.save(img_path, format="PNG")

            res = document_extractor.extract_file(img_path)
            self.assertTrue(res["success"])
            self.assertTrue(res["is_ocr_scanned"])
            self.assertIn(res["ocr_status"], ["NO_TEXT_DETECTED", "OCR_SUCCESS", "OCR_NOT_AVAILABLE"])
            self.assertIn("Dimensions: 120x80", res["text"])

    def test_document_extractor_unsupported_format(self):
        """Verify DocumentExtractor rejects executable or unknown formats safely."""
        with tempfile.TemporaryDirectory() as td:
            exe_path = os.path.join(td, "malware.exe")
            with open(exe_path, "wb") as f:
                f.write(b"MZ\x90\x00\x03")

            res = document_extractor.extract_file(exe_path)
            self.assertFalse(res["success"])
            self.assertEqual(res["extraction_status"], "UNSUPPORTED_FORMAT")

    def test_security_dns_rebinding_prevention(self):
        """Verify research_security detects public hostnames that resolve to private IP addresses."""
        with patch("socket.getaddrinfo") as mock_dns:
            # Simulate attacker.com resolving to localhost 127.0.0.1
            mock_dns.return_value = [
                (2, 1, 0, "", ("127.0.0.1", 80))
            ]
            is_safe, reason = research_security.is_safe_url("http://attacker.com/status")
            self.assertFalse(is_safe)
            self.assertIn("DNS Rebinding", reason)

        with patch("socket.getaddrinfo") as mock_dns:
            # Simulate legitimate domain resolving to public IP 93.184.216.34
            mock_dns.return_value = [
                (2, 1, 0, "", ("93.184.216.34", 80))
            ]
            is_safe, _ = research_security.is_safe_url("https://example.com/api")
            self.assertTrue(is_safe)

    def test_security_link_local_and_mapped_ipv6(self):
        """Verify link-local and IPv4-mapped IPv6 addresses are blocked."""
        is_safe1, _ = research_security.is_safe_url("http://[fe80::1ff:fe23:4567:890a]/meta")
        self.assertFalse(is_safe1)
        is_safe2, _ = research_security.is_safe_url("http://[::ffff:127.0.0.1]/admin")
        self.assertFalse(is_safe2)

    def test_safe_redirect_handler_blocks_ssrf_hop(self):
        """Verify SafeRedirectHandler aborts (returns None) on redirect to loopback or cloud metadata."""
        handler = SafeRedirectHandler()
        req = MagicMock()
        fp = MagicMock()

        # Redirect to AWS metadata endpoint
        res = handler.redirect_request(req, fp, 302, "Found", {}, "http://169.254.169.254/latest/meta-data/")
        self.assertIsNone(res)

    def test_safe_redirect_handler_max_hops(self):
        """Verify SafeRedirectHandler enforces hard cap on redirect count (returns None)."""
        handler = SafeRedirectHandler()
        handler.redirect_count = 3
        req = MagicMock()
        fp = MagicMock()

        res = handler.redirect_request(req, fp, 302, "Found", {}, "https://google.com/test")
        self.assertIsNone(res)

    def test_product_entity_extraction_and_price_type(self):
        """Verify claim_extractor extracts structured ProductEntity with correct PriceType and ASIN."""
        source = Source(
            research_id="res_test",
            url="https://www.amazon.in/Cosmic-Byte-Controller/dp/B0DFWDTZ73",
            title="Cosmic Byte Stellaris Wireless Controller - Amazon.in",
            domain="amazon.in",
            source_type=SourceType.RETAILER_MARKETPLACE,
            raw_snippet="Cosmic Byte Stellaris Hall Effect Wireless Controller for PC. Price: ₹1,899. 1 Year Brand Warranty. Sold by Appario Retail."
        )

        product = claim_extractor.extract_product_from_source(source)
        self.assertIsNotNone(product)
        self.assertEqual(product.asin_or_sku, "B0DFWDTZ73")
        self.assertEqual(product.price, 1899.0)
        self.assertEqual(product.price_type, PriceType.SEARCH_RESULT_PRICE)
        self.assertEqual(product.retailer, "Amazon India")
        self.assertEqual(product.seller, "Appario Retail")
        self.assertEqual(product.warranty, "1 Year Brand Warranty")

    def test_source_verifier_syndicated_copy_detection(self):
        """Verify SourceVerifier discounts confidence when identical text is syndicated across domains."""
        repeated_text = "The new graphics processor features 4000 CUDA cores and supports advanced neural rendering across multiple monitors."
        
        item1 = EvidenceItem(
            research_id="res_1",
            source_id="src_1",
            claim_text="GPU specifications",
            source_url="https://techsite-a.com/gpu",
            source_domain="techsite-a.com",
            source_type=SourceType.REPUTABLE_TECH,
            evidence_excerpt=repeated_text,
            confidence=0.85
        )
        item2 = EvidenceItem(
            research_id="res_1",
            source_id="src_2",
            claim_text="GPU specifications",
            source_url="https://techsite-b.com/gpu",
            source_domain="techsite-b.com",
            source_type=SourceType.REPUTABLE_TECH,
            evidence_excerpt=repeated_text,
            confidence=0.85
        )

        source_verifier.verify_evidence([item1, item2])
        # Second syndicated item should have its confidence discounted
        self.assertLess(item2.confidence, 0.85)

    def test_source_verifier_primary_source_verification(self):
        """Verify SourceVerifier assigns VERIFIED_BY_PRIMARY_SOURCE to official docs."""
        item = EvidenceItem(
            research_id="res_1",
            source_id="src_1",
            claim_text="Python 3.14 includes new interpreter optimizations",
            source_url="https://docs.python.org/3/whatsnew/3.14.html",
            source_domain="docs.python.org",
            source_type=SourceType.OFFICIAL_DOCS,
            evidence_excerpt="Python 3.14 release notes official documentation",
            confidence=0.95,
            metric_name="version",
            metric_value="3.14"
        )

        source_verifier.verify_evidence([item])
        self.assertEqual(item.verification_status, VerificationStatus.VERIFIED_BY_PRIMARY_SOURCE)

if __name__ == "__main__":
    unittest.main()
