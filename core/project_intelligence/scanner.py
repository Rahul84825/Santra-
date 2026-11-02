"""Project Scanner and Multi-Language Code Extractor."""

import os
import re
import ast
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Set, Union

from core.project_intelligence.models import (
    ProjectFile,
    CodeSymbol,
    SymbolType,
    DependencyRelation,
    ProjectOverview,
    AnalysisConfidence
)

logger = logging.getLogger("Jarvis.ProjectScanner")


class ProjectScanner:
    """Recursively scans folders, extracts AST symbols, and discovers project dependencies."""

    # Standard directories to safely ignore
    DEFAULT_EXCLUDES: Set[str] = {
        "node_modules", ".git", ".svn", ".hg", ".venv", "venv", "env",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".tox", "dist",
        "build", ".egg-info", ".idea", ".vscode", ".next", ".nuxt",
        "target", "vendor", "bin", "obj", ".cache", "logs", "benchmark_audio"
    }

    # Sensitive files that must NEVER enter full-text indexing or expose secret values
    SENSITIVE_FILE_PATTERNS: List[str] = [
        r"^\.env(?:\..+)?$",
        r"^.*credentials?.*\.(?:json|ya?ml|toml|ini|txt|conf)$",
        r"^.*secrets?.*\.(?:json|ya?ml|toml|ini|txt|conf)$",
        r"^client_secret.*\.json$",
        r"^.*service[-_]account.*\.(?:json|ya?ml)$",
        r"^\.npmrc$",
        r"^\.pypirc$",
        r"^\.netrc$",
        r"^\.git-credentials$",
        r"^\.dockercfg$",
        r"^id_.*(?:\.pub)?$",
        r"^.+\.(?:pem|key|pfx|p12|pkcs12|jks|keystore)$",
        r"^(?:passwd|shadow|master\.passwd|sam|system)$"
    ]

    def _is_sensitive_file(self, filename: str) -> bool:
        """Determines if a target filename is a protected sensitive file."""
        fname_lower = Path(filename).name.lower()
        for pat in self.SENSITIVE_FILE_PATTERNS:
            if re.match(pat, fname_lower, re.IGNORECASE):
                return True
        return False

    # Extension to language mapping
    LANGUAGE_MAP: Dict[str, str] = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript_react",
        ".ts": "typescript",
        ".tsx": "typescript_react",
        ".c": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".h": "c_header",
        ".hpp": "cpp_header",
        ".java": "java",
        ".sql": "sql",
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".scss": "scss",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".md": "markdown",
        ".txt": "text",
        ".csv": "csv",
        ".pdf": "pdf",
        ".docx": "word_document",
        ".xlsx": "excel_spreadsheet",
        ".pptx": "powerpoint_presentation",
        ".sh": "shell",
        ".bat": "batch",
        ".ps1": "powershell"
    }

    BINARY_EXTS: Set[str] = {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".bmp",
        ".exe", ".dll", ".so", ".dylib", ".bin", ".dat", ".db",
        ".sqlite", ".sqlite3", ".zip", ".tar", ".gz", ".7z",
        ".mp3", ".wav", ".mp4", ".avi", ".mkv", ".pyc"
    }

    def __init__(self, max_file_size_bytes: int = 2 * 1024 * 1024, max_files: int = 5000):
        self.max_file_size_bytes = max_file_size_bytes
        self.max_files = max_files

    def scan_directory(
        self,
        root_path: str,
        custom_excludes: Optional[Set[str]] = None,
        project_name: Optional[str] = None
    ) -> Tuple[ProjectOverview, List[ProjectFile], List[DependencyRelation]]:
        """Recursively scans project root, extracting files, symbols, and dependencies."""
        root = Path(root_path).resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Invalid project directory: {root_path}")

        proj_name = project_name or root.name

        excludes = self.DEFAULT_EXCLUDES | (custom_excludes or set())
        scanned_files: List[ProjectFile] = []
        all_dependencies: List[DependencyRelation] = []

        lang_counts: Dict[str, int] = {}
        total_lines = 0
        entry_points: List[str] = []
        doc_files: List[str] = []
        test_files_count = 0

        for current_root, dirs, files in os.walk(root):
            # Prune excluded directories and untrusted symlinks in-place
            clean_dirs = []
            for d in dirs:
                if d in excludes or d.startswith("."):
                    continue
                d_path = Path(current_root) / d
                is_link_or_junction = d_path.is_symlink() or os.path.isjunction(d_path)
                if is_link_or_junction:
                    try:
                        resolved_d = d_path.resolve()
                        if not (resolved_d == root or root in resolved_d.parents):
                            logger.warning(f"[SCANNER] Blocked symlink/junction directory pointing outside root: {d_path} -> {resolved_d}")
                            continue
                    except Exception:
                        continue
                clean_dirs.append(d)
            dirs[:] = clean_dirs

            for filename in files:
                if len(scanned_files) >= self.max_files:
                    logger.warning(f"[SCANNER] Reached max file limit of {self.max_files} files.")
                    break

                file_path = Path(current_root) / filename

                # Block symlink traversal pointing outside root
                if file_path.is_symlink():
                    try:
                        resolved_f = file_path.resolve()
                        if not (resolved_f == root or root in resolved_f.parents):
                            logger.warning(f"[SCANNER] Blocked symlink file pointing outside root: {file_path} -> {resolved_f}")
                            continue
                    except Exception:
                        continue

                rel_path = file_path.relative_to(root).as_posix()
                ext = file_path.suffix.lower()

                # Identify language
                is_binary = ext in self.BINARY_EXTS
                language = self.LANGUAGE_MAP.get(ext, "binary" if is_binary else "unknown")

                # Track statistics
                try:
                    stat = file_path.stat()
                    size_bytes = stat.st_size
                    last_mod = stat.st_mtime
                except Exception:
                    continue

                # SENSITIVE FILE PROTECTION: Never index sensitive file contents or secrets!
                if self._is_sensitive_file(filename):
                    config_symbols = []
                    if filename.startswith(".env") or filename.endswith(".env"):
                        try:
                            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                                for line_idx, line in enumerate(f):
                                    line_clean = line.strip()
                                    if line_clean and not line_clean.startswith("#") and "=" in line_clean:
                                        var_name = line_clean.split("=")[0].strip()
                                        config_symbols.append(CodeSymbol(
                                            name=var_name,
                                            symbol_type=SymbolType.CONFIG,
                                            file_path=str(file_path),
                                            relative_path=rel_path,
                                            line_number=line_idx + 1,
                                            signature=f"{var_name}=[PROTECTED_CONFIG_KEY]"
                                        ))
                        except Exception:
                            pass

                    p_file = ProjectFile(
                        path=str(file_path),
                        relative_path=rel_path,
                        extension=ext,
                        language="config" if config_symbols else "sensitive_excluded",
                        size_bytes=size_bytes,
                        line_count=0,
                        last_modified=last_mod,
                        file_hash="",
                        symbols=config_symbols,
                        dependencies=[],
                        is_binary=True  # Marked binary to block full-text FTS indexing
                    )
                    scanned_files.append(p_file)
                    continue

                if is_binary or size_bytes > self.max_file_size_bytes:
                    p_file = ProjectFile(
                        path=str(file_path),
                        relative_path=rel_path,
                        extension=ext,
                        language=language,
                        size_bytes=size_bytes,
                        line_count=0,
                        last_modified=last_mod,
                        file_hash="",
                        is_binary=is_binary
                    )
                    scanned_files.append(p_file)
                    continue

                # Read text and extract symbols
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    
                    line_count = len(content.splitlines())
                    total_lines += line_count
                    f_hash = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()

                    symbols, deps = self._extract_symbols_and_deps(file_path, rel_path, language, content)
                    all_dependencies.extend(deps)

                    # Language breakdown
                    lang_counts[language] = lang_counts.get(language, 0) + 1

                    # Check for entry points
                    if filename.lower() in ["main.py", "app.py", "index.js", "index.ts", "server.js", "server.ts", "launcher.py", "application.java", "main.cpp"]:
                        entry_points.append(rel_path)

                    # Check for documentation
                    if ext in [".md", ".rst", ".txt"] and any(k in filename.lower() for k in ["readme", "guide", "docs", "architecture"]):
                        doc_files.append(rel_path)

                    # Check for test files
                    if "test" in filename.lower() or "tests/" in rel_path.lower():
                        test_files_count += 1

                    p_file = ProjectFile(
                        path=str(file_path),
                        relative_path=rel_path,
                        extension=ext,
                        language=language,
                        size_bytes=size_bytes,
                        line_count=line_count,
                        last_modified=last_mod,
                        file_hash=f_hash,
                        symbols=symbols,
                        dependencies=[d.target_module for d in deps],
                        is_binary=False
                    )
                    scanned_files.append(p_file)

                except Exception as e:
                    logger.debug(f"[SCANNER] Failed to parse file '{rel_path}': {e}")

        # Detect frameworks
        frameworks = self._detect_frameworks(root, scanned_files)

        overview = ProjectOverview(
            project_name=proj_name,
            root_path=str(root),
            total_files=len(scanned_files),
            total_lines=total_lines,
            languages=lang_counts,
            frameworks=frameworks,
            entry_points=entry_points,
            test_files_count=test_files_count,
            documentation_files=doc_files
        )

        logger.info(f"[SCANNER] Scanned '{root.name}': {len(scanned_files)} files, {total_lines} lines, {len(all_dependencies)} dependencies.")
        return overview, scanned_files, all_dependencies

    def scan_single_file(
        self,
        file_path: Union[str, Path],
        root_path: Union[str, Path]
    ) -> Tuple[Optional[ProjectFile], List[DependencyRelation]]:
        """Scans a single file, extracting its symbols and dependencies."""
        file_path = Path(file_path).resolve()
        root = Path(root_path).resolve()
        if not file_path.exists() or not file_path.is_file():
            return None, []

        # Path Traversal Guard: ensure file is inside root_path
        if not (file_path == root or root in file_path.parents):
            logger.warning(f"[SCANNER] Path traversal blocked in scan_single_file: {file_path} is outside root {root}")
            return None, []

        try:
            rel_path = file_path.relative_to(root).as_posix()
        except ValueError:
            rel_path = file_path.name

        filename = file_path.name
        ext = file_path.suffix.lower()
        is_binary = ext in self.BINARY_EXTS
        language = self.LANGUAGE_MAP.get(ext, "binary" if is_binary else "unknown")

        try:
            stat = file_path.stat()
            size_bytes = stat.st_size
            last_mod = stat.st_mtime
        except Exception:
            return None, []

        if self._is_sensitive_file(filename):
            config_symbols = []
            if filename.startswith(".env") or filename.endswith(".env"):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        for line_idx, line in enumerate(f):
                            line_clean = line.strip()
                            if line_clean and not line_clean.startswith("#") and "=" in line_clean:
                                var_name = line_clean.split("=")[0].strip()
                                config_symbols.append(CodeSymbol(
                                    name=var_name,
                                    symbol_type=SymbolType.CONFIG,
                                    file_path=str(file_path),
                                    relative_path=rel_path,
                                    line_number=line_idx + 1,
                                    signature=f"{var_name}=[PROTECTED_CONFIG_KEY]"
                                ))
                except Exception:
                    pass

            p_file = ProjectFile(
                path=str(file_path),
                relative_path=rel_path,
                extension=ext,
                language="config" if config_symbols else "sensitive_excluded",
                size_bytes=size_bytes,
                line_count=0,
                last_modified=last_mod,
                file_hash="",
                symbols=config_symbols,
                dependencies=[],
                is_binary=True
            )
            return p_file, []

        if is_binary or size_bytes > self.max_file_size_bytes:
            p_file = ProjectFile(
                path=str(file_path),
                relative_path=rel_path,
                extension=ext,
                language=language,
                size_bytes=size_bytes,
                line_count=0,
                last_modified=last_mod,
                file_hash="",
                is_binary=is_binary
            )
            return p_file, []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            line_count = len(content.splitlines())
            f_hash = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()
            symbols, deps = self._extract_symbols_and_deps(file_path, rel_path, language, content)

            p_file = ProjectFile(
                path=str(file_path),
                relative_path=rel_path,
                extension=ext,
                language=language,
                size_bytes=size_bytes,
                line_count=line_count,
                last_modified=last_mod,
                file_hash=f_hash,
                symbols=symbols,
                dependencies=[d.target_module for d in deps],
                is_binary=False
            )
            return p_file, deps
        except Exception as e:
            logger.debug(f"[SCANNER] Single file scan error '{rel_path}': {e}")
            return None, []


    def _extract_symbols_and_deps(
        self,
        file_path: Path,
        rel_path: str,
        language: str,
        content: str
    ) -> Tuple[List[CodeSymbol], List[DependencyRelation]]:
        """Extracts AST symbols and dependencies based on file language."""
        if language == "python":
            return self._extract_python_symbols(file_path, rel_path, content)
        elif language in ["javascript", "typescript", "javascript_react", "typescript_react"]:
            return self._extract_js_ts_symbols(file_path, rel_path, content)
        elif language == "java":
            return self._extract_java_symbols(file_path, rel_path, content)
        elif language in ["c", "cpp", "c_header", "cpp_header"]:
            return self._extract_cpp_symbols(file_path, rel_path, content)
        elif language == "sql":
            return self._extract_sql_symbols(file_path, rel_path, content)

        return [], []

    def _extract_python_symbols(
        self,
        file_path: Path,
        rel_path: str,
        content: str
    ) -> Tuple[List[CodeSymbol], List[DependencyRelation]]:
        """Uses Python AST parser to extract symbols, classes, functions, routes, models, and dependencies."""
        symbols: List[CodeSymbol] = []
        deps: List[DependencyRelation] = []

        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return symbols, deps

        is_test_file = "test" in rel_path.lower()

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node) or ""
                # Detect Model / Entity / Middleware classes
                base_names = [b.id if isinstance(b, ast.Name) else (b.attr if isinstance(b, ast.Attribute) else "") for b in node.bases]
                is_model = any(k in b.lower() for b in base_names for k in ["model", "base", "entity", "schema", "table"])
                is_middleware = "middleware" in node.name.lower() or any("middleware" in b.lower() for b in base_names)
                if is_middleware:
                    sym_type = SymbolType.MIDDLEWARE
                elif is_model:
                    sym_type = SymbolType.MODEL
                else:
                    sym_type = SymbolType.CLASS

                symbols.append(CodeSymbol(
                    name=node.name,
                    symbol_type=sym_type,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    docstring=doc
                ))

                if is_middleware:
                    deps.append(DependencyRelation(
                        source_file=str(file_path),
                        target_module=node.name,
                        imported_symbol="middleware",
                        line_number=node.lineno,
                        dependency_kind="middleware",
                        is_inferred=False,
                        confidence=1.0,
                        confidence_level=AnalysisConfidence.CONFIRMED.value
                    ))

                # Inspect class body for methods and ForeignKeys
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_doc = ast.get_docstring(item) or ""
                        symbols.append(CodeSymbol(
                            name=f"{node.name}.{item.name}",
                            symbol_type=SymbolType.METHOD,
                            file_path=str(file_path),
                            relative_path=rel_path,
                            line_number=item.lineno,
                            end_line=getattr(item, "end_lineno", item.lineno),
                            docstring=m_doc
                        ))
                    elif isinstance(item, ast.Assign):
                        # Detect ForeignKey / relationship references
                        for val in ast.walk(item.value):
                            if isinstance(val, ast.Call):
                                func_name = val.func.id if isinstance(val.func, ast.Name) else (val.func.attr if isinstance(val.func, ast.Attribute) else "")
                                if "foreignkey" in func_name.lower() or "relationship" in func_name.lower():
                                    if val.args and isinstance(val.args[0], ast.Constant) and isinstance(val.args[0].value, str):
                                        target_tbl = val.args[0].value.split(".")[0]
                                        deps.append(DependencyRelation(
                                            source_file=str(file_path),
                                            target_module=target_tbl,
                                            imported_symbol=node.name,
                                            line_number=item.lineno,
                                            dependency_kind="foreign_key",
                                            is_inferred=False,
                                            confidence=1.0,
                                            confidence_level=AnalysisConfidence.CONFIRMED.value
                                        ))

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node) or ""
                params = [arg.arg for arg in node.args.args]

                # Check if function itself is an auth guard or permission validator
                if any(k in node.name.lower() for k in ["login_required", "jwt_required", "auth_required", "authenticate_user", "permission_required", "require_auth", "auth_guard"]):
                    symbols.append(CodeSymbol(
                        name=node.name,
                        symbol_type=SymbolType.AUTH_GUARD,
                        file_path=str(file_path),
                        relative_path=rel_path,
                        line_number=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        docstring=doc,
                        parameters=params,
                        signature=f"def {node.name}(...)"
                    ))

                # Check for Web Route decorators (@app.route, @router.get, etc.)
                is_route = False
                route_path = ""
                route_method = "GET"
                for dec in node.decorator_list:
                    dec_name = ""
                    if isinstance(dec, ast.Name):
                        dec_name = dec.id
                    elif isinstance(dec, ast.Attribute):
                        dec_name = dec.attr
                    elif isinstance(dec, ast.Call):
                        dec_name = dec.func.id if isinstance(dec.func, ast.Name) else (dec.func.attr if isinstance(dec.func, ast.Attribute) else "")

                    # Detect Auth Guards
                    if any(k in dec_name.lower() for k in ["login_required", "jwt_required", "auth_required", "authenticated", "permission_required", "require_auth"]):
                        symbols.append(CodeSymbol(
                            name=dec_name,
                            symbol_type=SymbolType.AUTH_GUARD,
                            file_path=str(file_path),
                            relative_path=rel_path,
                            line_number=node.lineno,
                            signature=f"@{dec_name} -> {node.name}"
                        ))
                        deps.append(DependencyRelation(
                            source_file=str(file_path),
                            target_module=dec_name,
                            imported_symbol=node.name,
                            line_number=node.lineno,
                            dependency_kind="auth_guard",
                            is_inferred=False,
                            confidence=1.0,
                            confidence_level=AnalysisConfidence.CONFIRMED.value
                        ))

                    dec_call = dec if isinstance(dec, ast.Call) else None
                    if dec_call:
                        call_func = dec_call.func
                        func_attr = call_func.attr if isinstance(call_func, ast.Attribute) else (call_func.id if isinstance(call_func, ast.Name) else "")
                        if func_attr.lower() in ["route", "get", "post", "put", "delete", "patch"]:
                            is_route = True
                            if func_attr.lower() != "route":
                                route_method = func_attr.upper()
                            if dec_call.args and isinstance(dec_call.args[0], ast.Constant) and isinstance(dec_call.args[0].value, str):
                                route_path = dec_call.args[0].value
                            for kw in dec_call.keywords:
                                if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                                    m_list = [elt.value for elt in kw.value.elts if isinstance(elt, ast.Constant)]
                                    if m_list:
                                        route_method = "/".join(m_list)

                if is_route and route_path:
                    symbols.append(CodeSymbol(
                        name=f"{route_method} {route_path}",
                        symbol_type=SymbolType.ROUTE,
                        file_path=str(file_path),
                        relative_path=rel_path,
                        line_number=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        docstring=doc,
                        parameters=params,
                        signature=f"{node.name}() -> {route_path}"
                    ))
                    deps.append(DependencyRelation(
                        source_file=str(file_path),
                        target_module=route_path,
                        imported_symbol=node.name,
                        line_number=node.lineno,
                        dependency_kind="route_handler",
                        is_inferred=False,
                        confidence=1.0,
                        confidence_level=AnalysisConfidence.CONFIRMED.value
                    ))
                else:
                    symbols.append(CodeSymbol(
                        name=node.name,
                        symbol_type=SymbolType.FUNCTION,
                        file_path=str(file_path),
                        relative_path=rel_path,
                        line_number=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        docstring=doc,
                        parameters=params
                    ))

                # Check for Controller -> Service calls
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and isinstance(inner.func.value, ast.Name):
                        recv = inner.func.value.id.lower()
                        if any(k in recv for k in ["service", "controller", "mgr", "manager", "repo", "repository", "dao"]):
                            deps.append(DependencyRelation(
                                source_file=str(file_path),
                                target_module=inner.func.value.id,
                                imported_symbol=inner.func.attr,
                                line_number=inner.lineno,
                                dependency_kind="service_call",
                                is_inferred=True,
                                confidence=0.85,
                                confidence_level=AnalysisConfidence.INFERRED.value
                            ))

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    kind = "test_coverage" if is_test_file else "static_import"
                    deps.append(DependencyRelation(
                        source_file=str(file_path),
                        target_module=alias.name,
                        line_number=node.lineno,
                        dependency_kind=kind,
                        is_inferred=is_test_file,
                        confidence=0.95 if is_test_file else 1.0,
                        confidence_level=AnalysisConfidence.INFERRED.value if is_test_file else AnalysisConfidence.CONFIRMED.value
                    ))

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        kind = "test_coverage" if is_test_file else "static_import"
                        deps.append(DependencyRelation(
                            source_file=str(file_path),
                            target_module=node.module,
                            imported_symbol=alias.name,
                            line_number=node.lineno,
                            dependency_kind=kind,
                            is_inferred=is_test_file,
                            confidence=0.95 if is_test_file else 1.0,
                            confidence_level=AnalysisConfidence.INFERRED.value if is_test_file else AnalysisConfidence.CONFIRMED.value
                        ))

        return symbols, deps

    def _extract_js_ts_symbols(
        self,
        file_path: Path,
        rel_path: str,
        content: str
    ) -> Tuple[List[CodeSymbol], List[DependencyRelation]]:
        """Uses robust regex parsing to extract JavaScript/TypeScript classes, interfaces, types, functions, and imports."""
        symbols: List[CodeSymbol] = []
        deps: List[DependencyRelation] = []

        lines = content.splitlines()
        for idx, line in enumerate(lines):
            line_no = idx + 1
            line_strip = line.strip()

            # ES6 Imports: import { X } from 'module';
            m_imp = re.match(r"^import\s+(?:(?:\{([^}]+)\}|\*\s+as\s+\w+|\w+)\s+from\s+)?['\"]([^'\"]+)['\"]", line_strip)
            if m_imp:
                target_mod = m_imp.group(2) or m_imp.group(1) or ""
                deps.append(DependencyRelation(
                    source_file=str(file_path),
                    target_module=target_mod,
                    line_number=line_no,
                    dependency_kind="static_import",
                    is_inferred=False,
                    confidence=1.0,
                    confidence_level=AnalysisConfidence.CONFIRMED.value
                ))

            # Dynamic import: import('module')
            m_dyn = re.search(r"\bimport\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", line_strip)
            if m_dyn:
                deps.append(DependencyRelation(
                    source_file=str(file_path),
                    target_module=m_dyn.group(1),
                    line_number=line_no,
                    dependency_kind="dynamic_import",
                    is_inferred=True,
                    confidence=0.70,
                    confidence_level=AnalysisConfidence.PARTIALLY_ANALYZED.value
                ))

            # CommonJS require: const x = require('module')
            m_req = re.search(r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", line_strip)
            if m_req and not m_imp:
                deps.append(DependencyRelation(
                    source_file=str(file_path),
                    target_module=m_req.group(1),
                    line_number=line_no,
                    dependency_kind="static_import",
                    is_inferred=False,
                    confidence=1.0,
                    confidence_level=AnalysisConfidence.CONFIRMED.value
                ))

            # Backend Express/Fastify Middleware & Auth Guards: app.use(authMiddleware)
            m_mid = re.search(r"\b(?:app|router)\.use\s*\(\s*([a-zA-Z0-9_$]+)\s*\)", line_strip)
            if m_mid:
                mid_name = m_mid.group(1)
                is_auth = any(k in mid_name.lower() for k in ["auth", "jwt", "login", "session", "passport", "protect", "token"])
                sym_type = SymbolType.AUTH_GUARD if is_auth else SymbolType.MIDDLEWARE
                dep_kind = "auth_guard" if is_auth else "middleware"
                symbols.append(CodeSymbol(
                    name=mid_name,
                    symbol_type=sym_type,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no,
                    signature=f"app.use({mid_name})"
                ))
                deps.append(DependencyRelation(
                    source_file=str(file_path),
                    target_module=mid_name,
                    line_number=line_no,
                    dependency_kind=dep_kind,
                    is_inferred=False,
                    confidence=1.0,
                    confidence_level=AnalysisConfidence.CONFIRMED.value
                ))

            # Classes: class MyClass
            m_cls = re.match(r"^(?:export\s+)?class\s+([a-zA-Z0-9_$]+)", line_strip)
            if m_cls:
                symbols.append(CodeSymbol(
                    name=m_cls.group(1),
                    symbol_type=SymbolType.CLASS,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no
                ))

            # Interfaces: interface MyInterface
            m_iface = re.match(r"^(?:export\s+)?interface\s+([a-zA-Z0-9_$]+)", line_strip)
            if m_iface:
                symbols.append(CodeSymbol(
                    name=m_iface.group(1),
                    symbol_type=SymbolType.INTERFACE,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no
                ))

            # Type Aliases: type MyType = ...
            m_type = re.match(r"^(?:export\s+)?type\s+([a-zA-Z0-9_$]+)\s*=", line_strip)
            if m_type:
                symbols.append(CodeSymbol(
                    name=m_type.group(1),
                    symbol_type=SymbolType.TYPE_ALIAS,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no
                ))

            # Functions: function myFunction(...)
            m_fn = re.match(r"^(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(", line_strip)
            if m_fn:
                symbols.append(CodeSymbol(
                    name=m_fn.group(1),
                    symbol_type=SymbolType.FUNCTION,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no
                ))

            # Const arrow functions: const myFunc = (...) =>
            m_arrow = re.match(r"^(?:export\s+)?const\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", line_strip)
            if m_arrow:
                symbols.append(CodeSymbol(
                    name=m_arrow.group(1),
                    symbol_type=SymbolType.FUNCTION,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no
                ))

            # Backend Express/Fastify Web Routes: app.get('/api/users', ...) or router.post('/api/auth', ...)
            m_rt = re.search(r"\b(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]", line_strip, re.IGNORECASE)
            if m_rt:
                method = m_rt.group(1).upper()
                route_path = m_rt.group(2)
                symbols.append(CodeSymbol(
                    name=f"{method} {route_path}",
                    symbol_type=SymbolType.ROUTE,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no,
                    signature=f"{method} {route_path}"
                ))
                deps.append(DependencyRelation(
                    source_file=str(file_path),
                    target_module=route_path,
                    line_number=line_no,
                    dependency_kind="route_handler",
                    is_inferred=False,
                    confidence=1.0,
                    confidence_level=AnalysisConfidence.CONFIRMED.value
                ))

            # Frontend API Calls: fetch('/api/users') or axios.get('/api/users')
            m_api = re.search(r"\b(?:fetch|axios\.(?:get|post|put|delete|patch)|apiClient\.(?:get|post))\s*\(\s*[`'\"]([^`'\"]+)[`'\"]", line_strip)
            if m_api:
                api_endpoint = m_api.group(1)
                deps.append(DependencyRelation(
                    source_file=str(file_path),
                    target_module=api_endpoint,
                    line_number=line_no,
                    dependency_kind="api_call",
                    is_inferred=True,
                    confidence=0.85,
                    confidence_level=AnalysisConfidence.INFERRED.value
                ))

        return symbols, deps

    def _extract_java_symbols(
        self,
        file_path: Path,
        rel_path: str,
        content: str
    ) -> Tuple[List[CodeSymbol], List[DependencyRelation]]:
        """Extracts Java imports, classes, interfaces, and methods using pattern extraction."""
        symbols: List[CodeSymbol] = []
        deps: List[DependencyRelation] = []

        lines = content.splitlines()
        current_class = ""

        for idx, line in enumerate(lines):
            line_no = idx + 1
            line_strip = line.strip()

            # Imports: import package.Class;
            m_imp = re.match(r"^import\s+(?:static\s+)?([a-zA-Z0-9_.*]+);", line_strip)
            if m_imp:
                deps.append(DependencyRelation(
                    source_file=str(file_path),
                    target_module=m_imp.group(1),
                    line_number=line_no,
                    dependency_kind="static_import",
                    is_inferred=False,
                    confidence=1.0,
                    confidence_level=AnalysisConfidence.CONFIRMED.value
                ))

            # Classes: public class UserService
            m_cls = re.match(r"^(?:public|protected|private|abstract|static|final|\s)*\bclass\s+([a-zA-Z0-9_$]+)", line_strip)
            if m_cls:
                current_class = m_cls.group(1)
                symbols.append(CodeSymbol(
                    name=current_class,
                    symbol_type=SymbolType.CLASS,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no
                ))

            # Interfaces: public interface UserRepository
            m_iface = re.match(r"^(?:public|protected|private|\s)*\binterface\s+([a-zA-Z0-9_$]+)", line_strip)
            if m_iface:
                current_class = m_iface.group(1)
                symbols.append(CodeSymbol(
                    name=current_class,
                    symbol_type=SymbolType.INTERFACE,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no
                ))

            # Methods: public ReturnType methodName(...)
            m_mth = re.match(r"^(?:public|protected|private|static|final|synchronized|\s)+\s*(?:<[^>]+>\s+)?([a-zA-Z0-9_$<>\[\],]+)\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)\s*(?:throws\s+[^{]+)?\s*\{?", line_strip)
            if m_mth and not any(kw in line_strip for kw in ["class", "interface", "enum", "if", "for", "while", "return", "new"]):
                ret_type = m_mth.group(1)
                mth_name = m_mth.group(2)
                raw_params = m_mth.group(3).strip()
                params = [p.strip().split()[-1] for p in raw_params.split(",") if p.strip()] if raw_params else []
                full_name = f"{current_class}.{mth_name}" if current_class else mth_name

                symbols.append(CodeSymbol(
                    name=full_name,
                    symbol_type=SymbolType.METHOD if current_class else SymbolType.FUNCTION,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no,
                    parameters=params,
                    return_type=ret_type
                ))

        return symbols, deps

    def _extract_cpp_symbols(
        self,
        file_path: Path,
        rel_path: str,
        content: str
    ) -> Tuple[List[CodeSymbol], List[DependencyRelation]]:
        """Extracts C/C++ includes, classes, structs, and functions."""
        symbols: List[CodeSymbol] = []
        deps: List[DependencyRelation] = []

        lines = content.splitlines()
        current_scope = ""

        for idx, line in enumerate(lines):
            line_no = idx + 1
            line_strip = line.strip()

            # Reset scope on closing brace
            if line_strip.startswith("};") or line_strip == "}":
                current_scope = ""

            # Includes: #include <vector> or #include "header.h"
            m_inc = re.match(r"^#include\s*[<\"']([^>\"']+)[\>\"']", line_strip)
            if m_inc:
                deps.append(DependencyRelation(
                    source_file=str(file_path),
                    target_module=m_inc.group(1),
                    line_number=line_no,
                    dependency_kind="include"
                ))

            # Classes and structs: class Engine or struct Config
            m_cls = re.match(r"^(?:class|struct)\s+([a-zA-Z0-9_]+)", line_strip)
            if m_cls and not line_strip.endswith(";"):
                current_scope = m_cls.group(1)
                symbols.append(CodeSymbol(
                    name=current_scope,
                    symbol_type=SymbolType.CLASS,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no
                ))

            # Functions: void calculate_hash(...)
            m_fn = re.match(r"^(?:[\w:*&<>]+\s+)+([a-zA-Z0-9_]+)\s*\(([^)]*)\)\s*(?:const)?\s*(?:\{|;)", line_strip)
            if m_fn and not any(kw in line_strip for kw in ["if", "for", "while", "return", "switch", "catch", "class", "struct"]):
                fn_name = m_fn.group(1)
                full_name = f"{current_scope}::{fn_name}" if current_scope else fn_name
                symbols.append(CodeSymbol(
                    name=full_name,
                    symbol_type=SymbolType.METHOD if current_scope else SymbolType.FUNCTION,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no
                ))

        return symbols, deps

    def _extract_sql_symbols(
        self,
        file_path: Path,
        rel_path: str,
        content: str
    ) -> Tuple[List[CodeSymbol], List[DependencyRelation]]:
        """Extracts SQL tables, views, and foreign key relations."""
        symbols: List[CodeSymbol] = []
        deps: List[DependencyRelation] = []

        lines = content.splitlines()
        for idx, line in enumerate(lines):
            line_no = idx + 1
            line_strip = line.strip()

            # CREATE TABLE users (...)
            m_tbl = re.search(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?([a-zA-Z0-9_.]+)[\"`]?", line_strip, re.IGNORECASE)
            if m_tbl:
                symbols.append(CodeSymbol(
                    name=m_tbl.group(1),
                    symbol_type=SymbolType.TABLE,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no
                ))

            # CREATE VIEW user_summary AS ...
            m_view = re.search(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?([a-zA-Z0-9_.]+)[\"`]?", line_strip, re.IGNORECASE)
            if m_view:
                symbols.append(CodeSymbol(
                    name=m_view.group(1),
                    symbol_type=SymbolType.VIEW,
                    file_path=str(file_path),
                    relative_path=rel_path,
                    line_number=line_no
                ))

            # REFERENCES other_table(id)
            m_ref = re.search(r"\bREFERENCES\s+[\"`]?([a-zA-Z0-9_.]+)[\"`]?", line_strip, re.IGNORECASE)
            if m_ref:
                target_table = m_ref.group(1)
                deps.append(DependencyRelation(
                    source_file=str(file_path),
                    target_module=target_table,
                    line_number=line_no,
                    dependency_kind="foreign_key",
                    is_inferred=False
                ))

        return symbols, deps

    def _detect_frameworks(self, root: Path, scanned: List[ProjectFile]) -> List[str]:
        """Infers frameworks from files and manifests (package.json, pyproject.toml, requirements.txt)."""
        frameworks = set()
        file_names = {Path(f.path).name.lower() for f in scanned}

        if "package.json" in file_names:
            try:
                pkg_path = root / "package.json"
                if pkg_path.exists():
                    txt = pkg_path.read_text(encoding="utf-8", errors="ignore").lower()
                    if "react" in txt:
                        frameworks.add("React")
                    if "vue" in txt:
                        frameworks.add("Vue")
                    if "express" in txt:
                        frameworks.add("Express")
                    if "next" in txt:
                        frameworks.add("Next.js")
            except Exception:
                pass

        if "requirements.txt" in file_names or "pyproject.toml" in file_names:
            try:
                req_path = root / "requirements.txt"
                if req_path.exists():
                    txt = req_path.read_text(encoding="utf-8", errors="ignore").lower()
                    if "django" in txt:
                        frameworks.add("Django")
                    if "flask" in txt:
                        frameworks.add("Flask")
                    if "fastapi" in txt:
                        frameworks.add("FastAPI")
                    if "pyqt6" in txt or "pyqt5" in txt:
                        frameworks.add("PyQt")
                    if "torch" in txt or "pytorch" in txt:
                        frameworks.add("PyTorch")
            except Exception:
                pass

        return sorted(list(frameworks))


project_scanner = ProjectScanner()
