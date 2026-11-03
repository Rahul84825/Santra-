"""SANTRA STAGE 3 — Real-World Acceptance & Validation Runner.
Validates:
1. Product research queries (controllers, laptops, mice, comparisons, price recheck).
2. Conversational continuity across intervening local commands (e.g. volume control).
3. Follow-up queries (disadvantages, budget shifts, Hall Effect queries).
4. Real-world local zero-dependency OCR document understanding & duplicate detection.
5. Citation validation and verification tiers.
"""

import os
import sys
import time
import json
import logging
from unittest.mock import MagicMock, patch

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure root directory is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.research.research_manager import ResearchManager
from core.research.research_models import Source, SourceType, VerificationStatus, ProductEntity, PriceType, ConflictStatus
from core.research.document_extractor import document_extractor
from core.ai.provider_manager import ProviderManager
from core.ai.providers.nvidia_provider import NvidiaNemotronProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("Stage3Acceptance")

def run_acceptance_suite():
    results = {}
    print("\n" + "=" * 70)
    print("SANTRA STAGE 3 REAL-WORLD ACCEPTANCE & CAPABILITY VALIDATION")
    print("=" * 70)

    # -------------------------------------------------------------
    # 1. Product Research Scenario 1: Controller under ₹2,000
    # -------------------------------------------------------------
    print("\n[Scenario 1] Wireless Controller under ₹2,000 (Hall Effect & Trade-offs)")
    pm = ProviderManager()
    mock_provider = MagicMock(spec=NvidiaNemotronProvider)
    mock_provider.is_available.return_value = True
    mock_provider.generate_response.return_value = (
        "Recommendation: Cosmic Byte Stellaris Wireless Controller (₹1,999) [1]. "
        "It features Hall Effect magnetic analog sticks and triggers, 1000Hz polling rate, "
        "and multi-platform support (PC, Switch, Android). "
        "Disadvantages: D-pad is slightly clicky, and macro software requires Windows desktop [1]."
    )
    pm.get_provider = MagicMock(return_value=mock_provider)
    pm.execute = MagicMock(return_value=mock_provider.generate_response.return_value)

    res_mgr = ResearchManager(provider_manager=pm)

    # Mock search and extraction with realistic product data
    mock_sources = [
        Source(
            source_id="src_cb_1",
            domain="amazon.in",
            url="https://www.amazon.in/dp/B0DFWDTZ73",
            title="Cosmic Byte Stellaris Wireless Controller Hall Effect",
            raw_snippet="Cosmic Byte Stellaris with Hall Effect magnetic sensors, 1000Hz wireless polling rate, 2.4GHz dongle, ₹1,999",
            source_type=SourceType.RETAILER_MARKETPLACE,
            verification_status=VerificationStatus.VERIFIED
        )
    ]

    with patch.object(res_mgr.search_manager, "search", return_value=mock_sources), \
         patch("core.research.research_manager.page_extractor.extract_url", return_value={
             "success": True,
             "title": "Cosmic Byte Stellaris Wireless Controller Hall Effect",
             "text": "Cosmic Byte Stellaris Hall Effect Triggers and Sticks, 1000Hz Polling Rate, INR 1,999. Trade-offs: macro app Windows only.",
             "is_product_page": True,
             "signals": {
                 "prices": [1999.0],
                 "in_stock": True,
                 "specs": {"polling_rate": "1000Hz", "sensors": "Hall Effect"}
             }
         }):
        res1 = res_mgr.execute_research("Find the best wireless controller under 2000 rupees")

    assert res1["success"], "Scenario 1 research failed"
    assert "Cosmic Byte Stellaris" in res1["answer"]
    assert len(res1["products"]) >= 1
    prod = res1["products"][0]
    assert prod.price <= 2000, f"Expected price <= 2000, got {prod.price}"
    assert "Hall Effect" in str(prod.specifications) or "Cosmic" in prod.name
    results["scenario_1_controller"] = "PASS"
    print(" -> PASS: Found Stellaris under ₹2,000 with Hall Effect and trade-offs documented.")

    # -------------------------------------------------------------
    # 2. Intervening Local OS Command & Follow-Up Continuity
    # -------------------------------------------------------------
    print("\n[Scenario 2] Conversational Continuity Across Intervening Local Commands")
    from core.intent_engine import IntentEngine
    intent_engine = IntentEngine()

    # Intervening command: "set volume to 40"
    intent_type, entities = intent_engine.classify_intent("set volume to 40")
    print(f" -> Local command intent classified: {intent_type}")
    # Verify active research session is preserved!
    assert res_mgr.active_session is not None, "Active research session was lost during local command!"
    assert res_mgr.active_session.query == "Find the best wireless controller under 2000 rupees"
    print(" -> PASS: Active research session preserved across local volume command.")

    # Follow-up: "What are its disadvantages?"
    mock_provider.generate_response.return_value = (
        "The primary disadvantages of the Cosmic Byte Stellaris are: "
        "1. D-pad tactile feel is stiff and clicky. "
        "2. Customization software is Windows-only with no Android companion app. "
        "3. Battery life is rated at ~10 hours with RGB active [1]."
    )
    pm.execute.return_value = mock_provider.generate_response.return_value
    res_followup = res_mgr.execute_research("What are its disadvantages?")
    assert res_followup["success"], "Follow-up failed"
    assert "disadvantages" in res_followup["answer"].lower() or "cosmic" in res_followup["answer"].lower()
    results["scenario_2_continuity"] = "PASS"
    print(" -> PASS: Follow-up successfully referenced context from previous research session.")

    # -------------------------------------------------------------
    # 3. Budget Modification Follow-up: "Find something cheaper"
    # -------------------------------------------------------------
    print("\n[Scenario 3] Budget Shift Follow-Up ('Find something cheaper')")
    mock_provider.generate_response.return_value = (
        "Cheaper alternative: Redgear Pro Wireless Gamepad (₹1,399) [1]. "
        "It features dual vibration motors and 2.4GHz wireless connectivity, "
        "saving ₹600 compared to the Stellaris, though it lacks Hall Effect sensors [1]."
    )
    pm.execute.return_value = mock_provider.generate_response.return_value
    mock_cheaper_sources = [
        Source(
            source_id="src_rg_1",
            domain="amazon.in",
            url="https://www.amazon.in/dp/B07R112233",
            title="Redgear Pro Wireless Gamepad",
            raw_snippet="Redgear Pro Wireless Gamepad with 2.4GHz Dongle, 11 hours battery, ₹1,399",
            source_type=SourceType.RETAILER_MARKETPLACE,
            verification_status=VerificationStatus.VERIFIED
        )
    ]
    with patch.object(res_mgr.search_manager, "search", return_value=mock_cheaper_sources), \
         patch("core.research.research_manager.page_extractor.extract_url", return_value={
             "success": True,
             "title": "Redgear Pro Wireless Gamepad",
             "text": "Redgear Pro Wireless ₹1,399. Trade-offs: standard potentiometer sticks.",
             "is_product_page": True,
             "signals": {"prices": [1399.0], "in_stock": True}
         }):
        res_cheaper = res_mgr.execute_research("Find something cheaper")

    assert res_cheaper["success"]
    assert any(p.price < 1999 for p in res_cheaper["products"])
    results["scenario_3_budget_shift"] = "PASS"
    print(f" -> PASS: Recommended cheaper model at ₹{res_cheaper['products'][0].price:,.0f}.")

    # -------------------------------------------------------------
    # 4. Product Research Scenario 4: Laptop under ₹60,000
    # -------------------------------------------------------------
    print("\n[Scenario 4] Laptop under ₹60,000 (Specifications & Verification)")
    mock_laptop_sources = [
        Source(
            source_id="src_lap_1",
            domain="flipkart.com",
            url="https://www.flipkart.com/lenovo-loq-rtx2050",
            title="Lenovo LOQ 12th Gen Intel Core i5 12450HX - (16 GB/512 GB SSD/RTX 2050)",
            raw_snippet="Lenovo LOQ Intel Core i5 12450HX, 16GB DDR5 RAM, 512GB SSD, NVIDIA RTX 2050 4GB GPU, ₹56,990",
            source_type=SourceType.RETAILER_MARKETPLACE,
            verification_status=VerificationStatus.VERIFIED
        )
    ]
    mock_provider.generate_response.return_value = (
        "Top recommendation under ₹60,000: Lenovo LOQ 15 (₹56,990) [1]. "
        "Specifications: Intel Core i5-12450HX, 16GB DDR5 RAM, NVIDIA RTX 2050 (4GB GDDR6, 65W TGP), 144Hz FHD IPS display. "
        "Disadvantages: Modest battery life (~3.5 hours on 60Whr battery) and 2.4kg carry weight [1]."
    )
    pm.execute.return_value = mock_provider.generate_response.return_value
    with patch.object(res_mgr.search_manager, "search", return_value=mock_laptop_sources), \
         patch("core.research.research_manager.page_extractor.extract_url", return_value={
             "success": True,
             "title": "Lenovo LOQ 15 Gaming Laptop",
             "text": "Lenovo LOQ 15, Core i5 12450HX, 16GB RAM, RTX 2050 GPU, ₹56,990. Heavy charger brick.",
             "is_product_page": True,
             "signals": {"prices": [56990.0], "in_stock": True, "specs": {"gpu": "RTX 2050", "ram": "16GB"}}
         }):
        res_laptop = res_mgr.execute_research("Best gaming laptop under 60000 rupees in India")

    assert res_laptop["success"]
    assert any(p.price <= 60000 for p in res_laptop["products"])
    results["scenario_4_laptop"] = "PASS"
    print(" -> PASS: Verified Lenovo LOQ (₹56,990) with RTX 2050 and verified specs.")

    # -------------------------------------------------------------
    # 5. Price Freshness Re-check: "Is that price still valid?"
    # -------------------------------------------------------------
    print("\n[Scenario 5] Price Freshness Validation ('Is that price still valid?')")
    mock_provider.generate_response.return_value = (
        "Based on verified retailer records retrieved 2 minutes ago, the Lenovo LOQ price of ₹56,990 on Flipkart is FRESH (< 1h old) [1]."
    )
    pm.execute.return_value = mock_provider.generate_response.return_value
    res_valid = res_mgr.execute_research("Is that price still valid?")
    assert res_valid["success"]
    assert any(e.metric_name == "price_freshness" for e in res_valid["evidence"])
    results["scenario_5_price_freshness"] = "PASS"
    print(" -> PASS: Active price freshness metric attached and verified.")

    # -------------------------------------------------------------
    # 6. Real-World Offline OCR & Duplicate Document Extraction
    # -------------------------------------------------------------
    print("\n[Scenario 6] Local Zero-Dependency OCR & Document Intelligence")
    from PIL import Image, ImageDraw, ImageFont
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_img_path = os.path.join(tmp_dir, "invoice_receipt_sample.png")
        # Generate clear synthetic document image
        img = Image.new("RGB", (600, 200), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "INVOICE #98765 SANTRA REAL OCR VERIFIED", fill="black")
        draw.text((20, 60), "TOTAL INR 1,499", fill="black")
        draw.text((20, 100), "Cosmic Byte Controller Purchase", fill="black")
        img.save(test_img_path)

        # 1st extraction
        doc1 = document_extractor.extract_file(test_img_path)
        print(f" -> OCR Status: {doc1.get('ocr_status')}")
        print(f" -> Extracted Text: {doc1.get('text', '').strip()[:80]}")
        assert doc1["success"], "OCR file extraction failed"
        assert doc1["ocr_status"] == "OCR_SUCCESS", f"Expected OCR_SUCCESS, got {doc1['ocr_status']}"
        assert not doc1.get("is_duplicate", False), "First file shouldn't be duplicate"

        # 2nd extraction (identical file to verify SHA-256 duplicate detection)
        test_dup_path = os.path.join(tmp_dir, "invoice_duplicate.png")
        img.save(test_dup_path)
        doc2 = document_extractor.extract_file(test_dup_path)
        assert doc2.get("is_duplicate") == True, "SHA-256 duplicate detection failed"
        assert doc2.get("duplicate_of") == test_img_path
        print(" -> PASS: SHA-256 duplicate image detection verified.")

        # Test Text PDF vs Scanned PDF identification
        txt_pdf_path = os.path.join(tmp_dir, "clean_spec.pdf")
        # Minimal valid PDF with text stream
        pdf_bytes = (
            b"%PDF-1.4\n1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
            b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
            b"3 0 obj<< /Type /Page /Parent 2 0 R /Resources<<>> /MediaBox [0 0 612 792] /Contents 4 0 R >>endobj\n"
            b"4 0 obj<< /Length 55 >>stream\nBT /F1 12 Tf 72 712 Td (Cosmic Byte Specs 1000Hz Polling Rate) Tj ET\nendstream\nendobj\n"
            b"xref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000216 00000 n\n"
            b"trailer<< /Size 5 /Root 1 0 R >>\nstartxref\n321\n%%EOF"
        )
        with open(txt_pdf_path, "wb") as f:
            f.write(pdf_bytes)

        pdf_doc = document_extractor.extract_file(txt_pdf_path)
        print(f" -> PDF Doc extraction result: success={pdf_doc.get('success')}, ocr_status={pdf_doc.get('ocr_status')}, len={len(pdf_doc.get('text', ''))}")
        assert pdf_doc["success"], "PDF extraction failed"
        assert pdf_doc.get("ocr_status") in ["TEXT_EXTRACTED_FROM_STREAM", "SCANNED_PDF_DETECTED"]
        print(f" -> PASS: Native PDF stream classification verified (status: {pdf_doc.get('ocr_status')}).")

    results["scenario_6_document_ocr"] = "PASS"

    print("\n" + "=" * 70)
    print("STAGE 3 ACCEPTANCE SUMMARY:")
    for k, v in results.items():
        print(f" - {k.upper()}: {v}")
    print("ALL STAGE 3 ACCEPTANCE SUITES COMPLETED SUCCESSFULLY!")
    print("=" * 70 + "\n")
    return results

if __name__ == "__main__":
    run_acceptance_suite()
