# SANTRA STAGE 4 — OCR, DOCUMENT UNDERSTANDING & CROSS-PLATFORM AUDIT

**Date:** November 3, 2026  
**Auditor:** Principal Python Desktop Systems Engineer  
**Scope:** Document Extractor (`core/research/document_extractor.py`), Windows UIA, and Linux Fallback Architecture  
**Verdict:** **VERIFIED & HARDENED (PASS)**

---

## 1. DOCUMENT EXTRACTION & COMPRESSION SECURITY

### ZIP Bomb Decompression Guard
Malicious or malformed Office OpenXML files (`.docx`, `.xlsx`, `.pptx`) can contain compressed XML streams that expand into gigabytes in RAM, freezing desktop systems.
- **Ceiling Enforced:** `MAX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024` (25 MB).
- **Test:** A synthetic 30 MB decompressed payload in `test_09_zip_bomb_protection_aborts_excessive_decompressed_payload` raised `ValueError("Decompressed XML exceeds safe threshold (ZIP bomb guard)")`.
- **Status:** **PASS**.

### DOCX Table Structure & XLSX Value Extraction
- Extractor parses both raw paragraph nodes (`<w:p>`) and table grid structures (`<w:tbl>`, `<w:tc>`).
- Preserves row / cell tabulations for spreadsheet and tabular invoice analysis.
- Tested on DOCX and XLSX with verified character counts.

---

## 2. OCR & SCREEN CONTEXT (WINDOWS VS. UBUNTU)

| Feature | Windows 11 Native | Ubuntu Linux Fallback | Status |
| :--- | :--- | :--- | :---: |
| **OCR Backend** | `pytesseract` / Tesseract OCR engine | `pytesseract` / `tesseract-ocr` package | **PASS** |
| **Desktop UI Context** | Windows UI Automation (comtypes `CUIAutomation`) | `xdotool` / `wmctrl` / `pygetwindow` fallback | **PASS** |
| **Active Window Title** | Win32 `GetForegroundWindow` / UIA | `xdotool getactivewindow getwindowname` | **PASS** |
| **COM Initialization** | Guarded with `CoInitializeEx` / `CoUninitialize` | Bypassed safely on Linux (`platform.system() != "Windows"`) | **PASS** |

---

## 3. SUMMARY

Document understanding and OCR pipelines function with memory safety guarantees (ZIP bomb defense) and clean cross-platform abstraction layers.

