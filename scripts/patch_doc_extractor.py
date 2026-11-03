"""Updates _extract_docx and _extract_xlsx in core/research/document_extractor.py cleanly."""

path = "core/research/document_extractor.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''    def _extract_docx(self, raw_bytes: bytes) -> tuple:
        """Safely extracts text paragraphs from a .docx file without external dependencies."""
        import io
        text_parts = []
        with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as z:
            if "word/document.xml" in z.namelist():
                xml_content = z.read("word/document.xml")
                root = ET.fromstring(xml_content)
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                for p in root.iterfind(".//w:p", ns):
                    p_texts = [node.text for node in p.iterfind(".//w:t", ns) if node.text]
                    if p_texts:
                        text_parts.append("".join(p_texts))
        return "\\n".join(text_parts), {"paragraph_count": len(text_parts)}

    def _extract_xlsx(self, raw_bytes: bytes) -> tuple:
        """Safely extracts text and shared strings from an .xlsx file."""
        import io
        shared_strings = []
        with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as z:
            if "xl/sharedStrings.xml" in z.namelist():
                xml_content = z.read("xl/sharedStrings.xml")
                root = ET.fromstring(xml_content)
                ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for t in root.iterfind(".//s:t", ns):
                    if t.text:
                        shared_strings.append(t.text)
        sample = shared_strings[:50]
        return "\\n".join(sample), {"total_strings": len(shared_strings), "sample": sample[:10]}'''

replacement = '''    def _extract_docx(self, raw_bytes: bytes) -> tuple:
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
        return "\\n".join(text_parts), {"paragraph_count": len(text_parts), "table_count": table_count}

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
        return "\\n".join(sample), {
            "total_strings": len(shared_strings),
            "sheet_count": sheet_count,
            "sample": sample[:10]
        }'''

# Normalize newlines for matching
is_crlf = "\r\n" in content
target_norm = target.replace("\n", "\r\n") if is_crlf else target
rep_norm = replacement.replace("\n", "\r\n") if is_crlf else replacement

if target_norm in content:
    content = content.replace(target_norm, rep_norm, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(" -> Successfully enhanced _extract_docx and _extract_xlsx with table parsing & zip bomb protection.")
else:
    print(" -> Target not found in document_extractor.py")

