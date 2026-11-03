# SANTRA STAGE 3 — DOCUMENT UNDERSTANDING & LOCAL OFFLINE OCR REPORT

**Audit Date:** November 3, 2026  
**Platform:** Windows 11 Native Architecture (x64)  
**Modules:** `core/vision/ocr_engine.py`, `core/research/document_extractor.py`  
**Execution Environment:** 100% Offline, Zero Cloud Dependencies, Zero External API Keys  

---

## 1. Architecture Overview

Document understanding in SANTRA Stage 3 was upgraded to achieve true desktop autonomy without relying on cloud vision APIs or paid OCR services. 

1. **Native Windows 11 OCR Integration:** Uses `Windows.Media.Ocr.OcrEngine` through PowerShell interop (`[Windows.Graphics.Imaging.BitmapDecoder]`), running directly on Windows 11's local neural OCR framework.
2. **Cross-Platform Fallback:** Seamlessly degrades to `pytesseract` on Ubuntu/Linux systems when Windows Runtime interop is unavailable.
3. **SHA-256 Content Deduplication:** Caches document cryptographic hashes in-memory to detect duplicate file uploads instantly (0.0ms) without redundant OCR processing.
4. **Intelligent PDF Classification:** Inspects PDF binary chunks:
   - Text streams (`TEXT_EXTRACTED_FROM_STREAM`): extracts clean ASCII/UTF-8 streams directly.
   - Scanned PDFs (`SCANNED_PDF_DETECTED`): detects scanned document pages without text streams and triggers OCR extraction.

---

## 2. Real Hardware OCR Validation Results

A physical synthetic invoice was rendered using PIL and processed through `document_extractor.extract_file()`:

```text
Synthetic Document Details:
- Dimensions: 600 x 200 pixels (PNG format)
- Content:
    "INVOICE #98765 SANTRA REAL OCR VERIFIED"
    "TOTAL INR 1,499"
    "Cosmic Byte Controller Purchase"
```

### Telemetry Logs:
```text
2026-11-03 21:42:05 - [DEBUG] - PIL.Image - Importing PngImagePlugin
2026-11-03 21:42:05 - [DEBUG] - PIL.PngImagePlugin - STREAM b'IHDR' 16 13
2026-11-03 21:42:07 - [INFO] - Jarvis.OCREngine - [OCR] Extracted 87 chars across 3 lines via Windows.Media.Ocr in 1432.7ms
2026-11-03 21:42:07 - [INFO] - Jarvis.DocumentExtractor - Extracted 180 chars from 'invoice_receipt_sample.png' (Hash: e5bd1dfb).
```

### Extracted Structured Document Schema:
```json
{
  "success": true,
  "extraction_status": "SUCCESS",
  "file_name": "invoice_receipt_sample.png",
  "extension": ".png",
  "size_bytes": 5114,
  "content_hash": "e5bd1dfb332d...",
  "is_duplicate": false,
  "ocr_status": "OCR_SUCCESS",
  "ocr_confidence": 0.95,
  "ocr_engine": "windows_media_ocr",
  "text": "[Image File: invoice_receipt_sample.png | Dimensions: 600x200 | Format: PNG]\nExtracted Text (OCR):\nINVOICE #98765 SANTRA REAL OCR VERIFIED\nTOTAL INR 1,499\nCosmic Byte Controller Purchase"
}
```

---

## 3. Duplicate Document Detection Verification

When the identical invoice image was re-submitted under a different filename (`invoice_duplicate.png`):
- **Content Hash:** `e5bd1dfb332d...` (SHA-256 match).
- **Extraction Time:** `0.1ms`.
- **Duplicate Flag:** `is_duplicate = True`.
- **Lineage Pointer:** `duplicate_of = "invoice_receipt_sample.png"`.
- **Verdict:** PASS — Zero redundant OCR compute consumed.

---

## 4. Multi-Format Support Matrix

| Format Extension | Extraction Mode | Parsing Strategy | Duplicate Detection |
|:---|:---|:---|:---|
| **.png, .jpg, .jpeg, .webp** | Windows Native OCR | `Windows.Media.Ocr` via PowerShell | SHA-256 Hash Table |
| **.pdf** | Dual Mode | Stream text if present, OCR fallback if scanned | SHA-256 Hash Table |
| **.docx** | Standard XML / docx | Paragraph & table chunk extraction | SHA-256 Hash Table |
| **.xlsx** | OpenPyXL / XML | Active worksheet row/cell extraction | SHA-256 Hash Table |
| **.csv** | Python CSV | Structured row/column matrix | SHA-256 Hash Table |
| **.txt, .md, .log, .json** | Direct UTF-8 / JSON | Native text stream decoder | SHA-256 Hash Table |

