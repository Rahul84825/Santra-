"""Document & Local File Knowledge Extractor for SANTRA Research Engine.
Safely extracts text, tables, and metadata from user-provided files (.txt, .md, .csv, .json, .pdf, .docx, .xlsx, images).
Features:
- Windows-native zero-dependency offline OCR (Windows.Media.Ocr) with pytesseract fallback.
- Scanned PDF detection vs text stream extraction.
- SHA-256 content deduplication tracking.
- Strict resource bounds and zero execution of embedded code.
"""

import os
import csv
import json
import zipfile
import hashlib
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger("Jarvis.DocumentExtractor")

class DocumentExtractor:
    MAX_UNCOMPRESSED_BYTES: int = 25 * 1024 * 1024  # 25 MB decompressed limit (zip bomb guard)

    """Safe reader for local user-supplied research files with local OCR capabilities."""

    MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB cap

    SUPPORTED_EXTENSIONS = {
        ".txt", ".md", ".markdown", ".log",
        ".csv", ".json",
        ".pdf",
        ".docx", ".xlsx",
        ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"
    }

    def __init__(self):
        self._seen_hashes: Dict[str, str] = {}  # sha256 -> path
        self._ocr_engine = None

    def _get_ocr_engine(self):
        if self._ocr_engine is None:
            try:
                from core.vision.ocr_engine import OCREngine
                self._ocr_engine = OCREngine()
            except Exception as e:
                logger.debug(f"[DocumentExtractor] Could not initialize OCREngine: {e}")
        return self._ocr_engine

    def extract_file(self, file_path: str) -> Dict[str, Any]:
        """Extracts content, metadata, and hash from a local file path."""
        path = Path(file_path).resolve()
        if not path.exists():
            return {
                "success": False,
                "extraction_status": "FILE_NOT_FOUND",
                "error": f"File does not exist: {file_path}"
            }
        if not path.is_file():
            return {
                "success": False,
                "extraction_status": "NOT_A_REGULAR_FILE",
                "error": f"Path is not a regular file: {file_path}"
            }

        size = path.stat().st_size
        if size > self.MAX_FILE_BYTES:
            return {
                "success": False,
                "extraction_status": "EXCEEDS_FILE_SIZE_LIMIT",
                "error": f"File size ({size} bytes) exceeds {self.MAX_FILE_BYTES // (1024*1024)}MB limit."
            }

        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED_EXTENSIONS:
            return {
                "success": False,
                "extraction_status": "UNSUPPORTED_FORMAT",
                "error": f"Unsupported document format '{suffix}'. Supported: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            }

        try:
            with open(path, "rb") as f:
                raw_bytes = f.read()

            content_hash = hashlib.sha256(raw_bytes).hexdigest()
            is_duplicate = content_hash in self._seen_hashes
            duplicate_of = self._seen_hashes.get(content_hash)
            if not is_duplicate:
                self._seen_hashes[content_hash] = str(path)

            text_content = ""
            structured_data = None
            is_ocr_scanned = False
            ocr_status = "NOT_APPLICABLE"
            ocr_confidence = 0.0
            ocr_engine_used = "none"

            if suffix in [".txt", ".md", ".markdown", ".log"]:
                text_content = raw_bytes.decode("utf-8", errors="ignore")

            elif suffix == ".csv":
                decoded = raw_bytes.decode("utf-8", errors="ignore")
                reader = csv.reader(decoded.splitlines())
                rows = list(reader)
                text_content = "\n".join([", ".join(r) for r in rows[:200]])
                structured_data = {"row_count": len(rows), "sample": rows[:5]}

            elif suffix == ".json":
                decoded = raw_bytes.decode("utf-8", errors="ignore")
                parsed = json.loads(decoded)
                text_content = json.dumps(parsed, indent=2)
                structured_data = {"type": "json_object"}

            elif suffix == ".docx":
                text_content, structured_data = self._extract_docx(raw_bytes)

            elif suffix == ".xlsx":
                text_content, structured_data = self._extract_xlsx(raw_bytes)

            elif suffix in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"]:
                text_content, structured_data, is_ocr_scanned, ocr_status, ocr_confidence, ocr_engine_used = self._extract_image(path, raw_bytes)

            elif suffix == ".pdf":
                decoded = raw_bytes.decode("latin1", errors="ignore")
                streams = []
                for chunk in decoded.split("stream"):
                    if "endstream" in chunk:
                        s_text = chunk.split("endstream")[0]
                        clean = "".join([c for c in s_text if 32 <= ord(c) <= 126 or c in "\n\t "])
                        if len(clean) > 20:
                            streams.append(clean)
                text_content = "\n".join(streams[:50]).strip()
                if not text_content:
                    is_ocr_scanned = True
                    ocr_status = "SCANNED_PDF_DETECTED"
                    text_content = f"[PDF Document: {path.name} (Scanned document without text stream; OCR required)]"
                else:
                    ocr_status = "TEXT_EXTRACTED_FROM_STREAM"

            logger.info(f"[DocumentExtractor] Extracted {len(text_content)} chars from '{path.name}' (Hash: {content_hash[:8]}).")
            return {
                "success": True,
                "extraction_status": "SUCCESS",
                "file_name": path.name,
                "file_path": str(path),
                "extension": suffix,
                "size_bytes": size,
                "content_hash": content_hash,
                "is_duplicate": is_duplicate,
                "duplicate_of": duplicate_of,
                "text": text_content,
                "structured_data": structured_data,
                "is_ocr_scanned": is_ocr_scanned,
                "ocr_status": ocr_status,
                "ocr_confidence": ocr_confidence,
                "ocr_engine": ocr_engine_used
            }

        except Exception as e:
            logger.error(f"[DocumentExtractor] Failed to extract '{file_path}': {e}")
            return {
                "success": False,
                "extraction_status": "EXTRACTION_FAILED",
                "error": str(e),
                "file_path": file_path
            }

    def _extract_docx(self, raw_bytes: bytes) -> tuple:
        """Safely extracts text paragraphs and tables from a .docx file with ZIP-bomb protection."""
        import io
        text_parts = []
        table_count = 0
        total_uncompressed = 0
        with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as z:
            for info in z.infolist():
                total_uncompressed += info.file_size
                if total_uncompressed > self.MAX_UNCOMPRESSED_BYTES:
                    raise ValueError(f"Decompressed file size exceeds {self.MAX_UNCOMPRESSED_BYTES // (1024*1024)}MB (ZIP bomb guard).")

            if "word/document.xml" in z.namelist():
                xml_content = z.read("word/document.xml")
                root = ET.fromstring(xml_content)
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                table_count = len(root.findall(".//w:tbl", ns))
                for p in root.iterfind(".//w:p", ns):
                    p_texts = [node.text for node in p.iterfind(".//w:t", ns) if node.text]
                    if p_texts:
                        text_parts.append("".join(p_texts))
        return "\n".join(text_parts), {"paragraph_count": len(text_parts), "table_count": table_count}

    def _extract_xlsx(self, raw_bytes: bytes) -> tuple:
        """Safely extracts text, shared strings, and worksheet values from an .xlsx file with ZIP-bomb protection."""
        import io
        shared_strings = []
        sheet_values = []
        sheet_count = 0
        total_uncompressed = 0
        with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as z:
            for info in z.infolist():
                total_uncompressed += info.file_size
                if total_uncompressed > self.MAX_UNCOMPRESSED_BYTES:
                    raise ValueError(f"Decompressed file size exceeds {self.MAX_UNCOMPRESSED_BYTES // (1024*1024)}MB (ZIP bomb guard).")

            if "xl/sharedStrings.xml" in z.namelist():
                xml_content = z.read("xl/sharedStrings.xml")
                root = ET.fromstring(xml_content)
                ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for t in root.iterfind(".//s:t", ns):
                    if t.text:
                        shared_strings.append(t.text)

            # Inspect worksheet files for cell values
            sheet_names = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
            sheet_count = len(sheet_names)
            for sname in sheet_names[:5]:
                try:
                    s_xml = z.read(sname)
                    s_root = ET.fromstring(s_xml)
                    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                    for v in s_root.iterfind(".//s:v", ns):
                        if v.text and v.text not in sheet_values:
                            sheet_values.append(v.text)
                except Exception:
                    pass

        sample = shared_strings[:50] or sheet_values[:50]
        return "\n".join(sample), {
            "total_strings": len(shared_strings),
            "sheet_count": sheet_count,
            "sample": sample[:10]
        }

    def _extract_image(self, path: Path, raw_bytes: bytes) -> tuple:
        """Extracts image metadata and executes local zero-dependency offline OCR."""
        metadata = {"file_name": path.name, "size_bytes": len(raw_bytes)}
        ocr_confidence = 0.0
        ocr_status = "OCR_NOT_AVAILABLE"
        ocr_engine_used = "none"
        extracted_text = ""

        if HAS_PIL:
            import io
            try:
                with Image.open(io.BytesIO(raw_bytes)) as img:
                    metadata["format"] = img.format
                    metadata["width"] = img.width
                    metadata["height"] = img.height
                    metadata["mode"] = img.mode

                    # Apply local offline OCR
                    ocr_eng = self._get_ocr_engine()
                    if ocr_eng:
                        try:
                            ocr_res = ocr_eng.extract_text(img, timeout_sec=5.0)
                            if ocr_res.success and ocr_res.has_meaningful_content():
                                ocr_status = "OCR_SUCCESS"
                                ocr_confidence = ocr_res.confidence
                                ocr_engine_used = ocr_res.engine_used
                                extracted_text = ocr_res.text
                                metadata["ocr_lines"] = ocr_res.lines
                            elif ocr_res.success:
                                ocr_status = "NO_TEXT_DETECTED"
                                ocr_confidence = 1.0
                                ocr_engine_used = ocr_res.engine_used
                            else:
                                ocr_status = "OCR_FAILED"
                                metadata["ocr_error"] = ocr_res.error
                        except Exception as oe:
                            logger.debug(f"[DocumentExtractor] OCR extraction exception: {oe}")
                            ocr_status = "OCR_FAILED"
            except Exception as ie:
                metadata["image_parse_error"] = str(ie)
                ocr_status = "IMAGE_PARSE_ERROR"

        header = f"[Image File: {path.name} | Dimensions: {metadata.get('width', 'unknown')}x{metadata.get('height', 'unknown')} | Format: {metadata.get('format', path.suffix.upper())}]"
        if extracted_text:
            text_body = f"{header}\nExtracted Text:\n{extracted_text}"
        else:
            text_body = f"{header} (OCR Status: {ocr_status})"

        return text_body, metadata, True, ocr_status, ocr_confidence, ocr_engine_used

# Singleton instance
document_extractor = DocumentExtractor()
