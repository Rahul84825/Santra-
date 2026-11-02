"""Safe File Engineering, Atomic Writes, Verification, and Change Rollback."""

import os
import ast
import json
import time
import uuid
import difflib
import hashlib
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from config import BASE_DIR
from core.project_intelligence.models import FilePatch

logger = logging.getLogger("Jarvis.FileEngineer")


class FileEngineer:
    """Performs safe, atomic, verified file modifications with full rollback journaling."""

    SENSITIVE_PATTERNS = [
        r"^\.env(?:\..+)?$",
        r"^\.git(?:/|\\).+$",
        r"^credentials\.json$",
        r"^client_secret.*\.json$",
        r"^service_account.*\.json$",
        r"^id_rsa(?:\.pub)?$",
        r"^id_ed25519(?:\.pub)?$",
        r"^id_ecdsa(?:\.pub)?$",
        r"^.+\.pem$",
        r"^.+\.key$",
        r"^.+\.pfx$",
        r"^.+\.p12$",
        r"^.+\.pkcs12$",
        r"^secrets?\..+$",
        r"^passwd$",
        r"^shadow$"
    ]

    SECRET_RE_PATTERNS = [
        (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*['\"]?)([^'\";\s]{8,})(['\"]?)"), r"\1[REDACTED]\3"),
        (re.compile(r"(?i)(secret[_-]?key\s*[:=]\s*['\"]?)([^'\";\s]{8,})(['\"]?)"), r"\1[REDACTED]\3"),
        (re.compile(r"(?i)(password\s*[:=]\s*['\"]?)([^'\";\s]+)(['\"]?)"), r"\1[REDACTED]\3"),
        (re.compile(r"(?i)(token\s*[:=]\s*['\"]?)([^'\";\s]{8,})(['\"]?)"), r"\1[REDACTED]\3"),
        (re.compile(r"\b(sk-[a-zA-Z0-9_-]{20,})\b"), "[REDACTED_API_KEY]"),
        (re.compile(r"\b(ghp_[a-zA-Z0-9]{36,})\b"), "[REDACTED_GH_TOKEN]"),
        # JWT tokens: header.payload.signature
        (re.compile(r"\beyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b"), "[REDACTED_JWT]"),
        # Bearer tokens
        (re.compile(r"(?i)\bBearer\s+[a-zA-Z0-9_\-\.]{16,}\b"), "Bearer [REDACTED]"),
        # Database connection strings with passwords
        (re.compile(r"(?i)(postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://([^:]+):([^@]+)@"), r"\1://\2:[REDACTED]@"),
        # AWS Access Keys
        (re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "[REDACTED_AWS_KEY]"),
        # RSA / EC / OpenSSH Private Key blocks
        (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]")
    ]

    MAX_JOURNAL_LINES = 5000

    def __init__(self, journal_path: Optional[str] = None):
        self.journal_path = Path(journal_path) if journal_path else BASE_DIR / "logs" / "file_change_journal.jsonl"
        self._patches: Dict[str, FilePatch] = {}
        self._load_journal()

    def _is_sensitive_file(self, path: Path) -> bool:
        """Determines if a target file is a security-sensitive credential or secret file."""
        fname = path.name.lower()
        for pat in self.SENSITIVE_PATTERNS:
            if re.match(pat, fname, re.IGNORECASE):
                return True
        return False

    def _validate_safe_path(self, file_path: str) -> Tuple[bool, Optional[Path], Optional[str]]:
        """Validates path against null bytes, traversal attacks, and security blocklists."""
        if "\x00" in file_path:
            return False, None, "Path contains invalid null byte."
        try:
            p = Path(file_path).resolve()
        except Exception as e:
            return False, None, f"Invalid file path: {e}"

        if self._is_sensitive_file(p):
            return False, p, f"Modification of sensitive file '{p.name}' is prohibited by security policy."

        return True, p, None

    def _redact_secrets(self, text: str) -> str:
        """Sanitizes sensitive secret patterns before persisting to journal logs."""
        if not text:
            return ""
        result = text
        for pattern, replacement in self.SECRET_RE_PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    def _load_journal(self):
        """Loads patch history from journal."""
        if self.journal_path.exists():
            try:
                with open(self.journal_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            p = FilePatch(
                                patch_id=data["patch_id"],
                                file_path=data["file_path"],
                                original_content=data.get("original_content", ""),
                                patched_content=data.get("patched_content", ""),
                                diff=data.get("diff", ""),
                                description=data.get("description", ""),
                                timestamp=data.get("timestamp", 0.0),
                                verified=data.get("verified", False),
                                rolled_back=data.get("rolled_back", False)
                            )
                            self._patches[p.patch_id] = p
            except Exception as e:
                logger.debug(f"[FILE_ENGINEER] Journal load warning: {e}")

    def _rotate_journal_if_needed(self):
        """Rotates journal file if it exceeds MAX_JOURNAL_LINES."""
        if not self.journal_path.exists():
            return
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) >= self.MAX_JOURNAL_LINES:
                backup = self.journal_path.with_suffix(".1.jsonl")
                if backup.exists():
                    try:
                        backup.unlink()
                    except Exception:
                        pass
                os.replace(self.journal_path, backup)
                # Keep latest 1000 lines in new file
                retained = lines[-1000:]
                with open(self.journal_path, "w", encoding="utf-8") as f:
                    f.writelines(retained)
                logger.info(f"[FILE_ENGINEER] Rotated journal: retained {len(retained)} recent entries.")
        except Exception as e:
            logger.debug(f"[FILE_ENGINEER] Journal rotation error: {e}")

    def _append_journal(self, patch: FilePatch):
        """Appends a new change record to the persistent journal with sensitive secret redaction and rotation."""
        self._rotate_journal_if_needed()
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.journal_path, "a", encoding="utf-8") as f:
                rec = {
                    "patch_id": patch.patch_id,
                    "file_path": patch.file_path,
                    "original_content": self._redact_secrets(patch.original_content),
                    "patched_content": self._redact_secrets(patch.patched_content),
                    "diff": self._redact_secrets(patch.diff),
                    "description": patch.description,
                    "timestamp": patch.timestamp,
                    "verified": patch.verified,
                    "rolled_back": patch.rolled_back
                }
                f.write(json.dumps(rec) + "\n")
            self._patches[patch.patch_id] = patch
        except Exception as e:
            logger.error(f"[FILE_ENGINEER] Failed to write journal record: {e}")

    def _compute_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

    def _verify_syntax(self, file_path: str, content: str) -> Tuple[bool, Optional[str]]:
        """Validates that modified content does not contain syntax errors."""
        ext = Path(file_path).suffix.lower()
        if ext == ".py":
            try:
                ast.parse(content, filename=file_path)
                return True, None
            except SyntaxError as e:
                return False, f"Python SyntaxError at line {e.lineno}: {e.msg}"
        elif ext == ".json":
            try:
                json.loads(content)
                return True, None
            except json.JSONDecodeError as e:
                return False, f"JSON DecodeError: {e.msg}"
        return True, None

    def read_file(
        self,
        file_path: str,
        start_line: int = 1,
        end_line: Optional[int] = None
    ) -> Dict[str, Any]:
        """Reads file contents or a specific slice of lines."""
        p = Path(file_path).resolve()
        if not p.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        if not p.is_file():
            return {"success": False, "error": f"Target is a directory: {file_path}"}

        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            s_idx = max(0, start_line - 1)
            e_idx = min(total_lines, end_line) if end_line is not None else total_lines
            selected = "".join(lines[s_idx:e_idx])

            return {
                "success": True,
                "file_path": str(p),
                "content": selected,
                "total_lines": total_lines,
                "start_line": start_line,
                "end_line": e_idx
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_file(
        self,
        file_path: str,
        content: str,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """Atomically creates a new file with syntax validation and security policy enforcement."""
        safe, p, err = self._validate_safe_path(file_path)
        if not safe or p is None:
            return {"success": False, "reason": "security_blocklist" if "prohibited" in (err or "") else "invalid_path", "error": err}

        if p.exists() and not overwrite:
            return {"success": False, "error": f"File already exists: {file_path}. Use overwrite=True if intended."}

        # Syntax check
        valid, err = self._verify_syntax(str(p), content)
        if not valid:
            return {"success": False, "reason": "syntax_error", "error": f"Pre-creation syntax check failed: {err}"}

        original_content = ""
        if p.exists():
            try:
                original_content = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

        patch_id = f"patch-{uuid.uuid4().hex[:8]}"
        diff_str = "\n".join(difflib.unified_diff(
            original_content.splitlines(),
            content.splitlines(),
            fromfile=f"a/{p.name}",
            tofile=f"b/{p.name}",
            lineterm=""
        ))

        # Atomic Write via temp file in same directory
        temp_path = p.parent / f".tmp_{p.name}_{uuid.uuid4().hex[:6]}"
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Atomic swap
            os.replace(temp_path, p)

            patch = FilePatch(
                patch_id=patch_id,
                file_path=str(p),
                original_content=original_content,
                patched_content=content,
                diff=diff_str,
                description=f"Created file '{p.name}'" if not original_content else f"Overwrote file '{p.name}'",
                verified=True
            )
            self._append_journal(patch)

            logger.info(f"[FILE_ENGINEER] Created/Wrote file '{p}' (Patch ID: {patch_id})")
            return {
                "success": True,
                "patch_id": patch_id,
                "file_path": str(p),
                "lines": len(content.splitlines()),
                "message": f"Successfully created/updated '{p.name}'."
            }
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            return {"success": False, "error": str(e)}

    def create_or_update_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """Atomically creates or overwrites a file with syntax check and journal logging."""
        return self.create_file(file_path=file_path, content=content, overwrite=True)

    def patch_file(
        self,
        file_path: str,
        target_content: str,
        replacement_content: str,
        expected_hash: Optional[str] = None,
        description: str = ""
    ) -> Dict[str, Any]:
        """Convenience alias for apply_patch."""
        return self.apply_patch(
            file_path=file_path,
            target_content=target_content,
            replacement_content=replacement_content,
            expected_hash=expected_hash,
            description=description
        )

    def apply_patch(
        self,
        file_path: str,
        target_content: str,
        replacement_content: str,
        expected_hash: Optional[str] = None,
        description: str = ""
    ) -> Dict[str, Any]:
        """Safely applies a text replacement patch with conflict detection, security policy, and syntax validation."""
        safe, p, err = self._validate_safe_path(file_path)
        if not safe or p is None:
            return {"success": False, "reason": "security_blocklist" if "prohibited" in (err or "") else "invalid_path", "error": err}

        if not p.exists() or not p.is_file():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                current_text = f.read()
        except Exception as e:
            return {"success": False, "error": f"Failed to read file: {e}"}

        # Conflict Detection: check expected hash if supplied
        if expected_hash and self._compute_hash(current_text) != expected_hash:
            return {
                "success": False,
                "conflict": True,
                "reason": "conflict",
                "error": "Conflict detected: The file has been modified externally since last read. Please re-read and reconcile."
            }

        # Target occurrence check
        if target_content not in current_text:
            return {
                "success": False,
                "reason": "conflict",
                "error": "Target content not found in file. Ensure the target string matches the existing code exactly."
            }

        # Generate replacement
        new_text = current_text.replace(target_content, replacement_content, 1)

        # Syntax check
        valid, err = self._verify_syntax(str(p), new_text)
        if not valid:
            return {"success": False, "error": f"Modification rejected due to syntax error: {err}"}

        # Generate diff
        patch_id = f"patch-{uuid.uuid4().hex[:8]}"
        diff_str = "\n".join(difflib.unified_diff(
            current_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"a/{p.name}",
            tofile=f"b/{p.name}",
            lineterm=""
        ))

        # Atomic Write
        temp_path = p.parent / f".tmp_{p.name}_{uuid.uuid4().hex[:6]}"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(new_text)

            os.replace(temp_path, p)

            patch = FilePatch(
                patch_id=patch_id,
                file_path=str(p),
                original_content=current_text,
                patched_content=new_text,
                diff=diff_str,
                description=description or f"Patched '{p.name}'",
                verified=True
            )
            self._append_journal(patch)

            logger.info(f"[FILE_ENGINEER] Patched '{p.name}' (Patch ID: {patch_id})")
            return {
                "success": True,
                "patch_id": patch_id,
                "file_path": str(p),
                "diff": diff_str,
                "message": f"Successfully patched '{p.name}'."
            }
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            return {"success": False, "error": str(e)}

    def rollback_patch(self, patch_id: str) -> Dict[str, Any]:
        """Reverses a previously applied patch by restoring original content, ensuring no post-patch modifications occurred."""
        patch = self._patches.get(patch_id)
        if not patch:
            return {"success": False, "error": f"Patch ID not found: {patch_id}"}
        if patch.rolled_back:
            return {"success": False, "error": f"Patch {patch_id} was already rolled back."}

        safe, p, err = self._validate_safe_path(patch.file_path)
        if not safe or p is None:
            return {"success": False, "reason": "security_blocklist" if "prohibited" in (err or "") else "invalid_path", "error": err}

        if not p.exists() or not p.is_file():
            return {"success": False, "error": f"Target file for rollback not found: {p}"}

        try:
            current_disk_content = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"success": False, "error": f"Failed to read file for rollback: {e}"}

        # Safe Rollback: Verify file has not been modified externally after patch was applied
        if current_disk_content != patch.patched_content:
            return {
                "success": False,
                "conflict": True,
                "reason": "conflict",
                "error": f"Rollback conflict: '{p.name}' was modified externally after patch {patch_id} was applied. Manual reconciliation required."
            }

        temp_path = p.parent / f".tmp_{p.name}_{uuid.uuid4().hex[:6]}"

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(patch.original_content)

            os.replace(temp_path, p)
            patch.rolled_back = True

            # Record rollback in journal
            rollback_record = FilePatch(
                patch_id=f"rollback-{uuid.uuid4().hex[:8]}",
                file_path=str(p),
                original_content=patch.patched_content,
                patched_content=patch.original_content,
                diff="[ROLLED BACK]",
                description=f"Rolled back patch {patch_id}",
                verified=True,
                rolled_back=True
            )
            self._append_journal(rollback_record)

            logger.info(f"[FILE_ENGINEER] Rolled back patch {patch_id} on '{p.name}'")
            return {
                "success": True,
                "patch_id": patch_id,
                "file_path": str(p),
                "message": f"Successfully rolled back patch {patch_id} on '{p.name}'."
            }
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            return {"success": False, "error": f"Failed to rollback patch: {e}"}


file_engineer = FileEngineer()
