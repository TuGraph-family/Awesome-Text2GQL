from __future__ import annotations

from dataclasses import dataclass
import os
import platform
from typing import List


@dataclass
class PreflightResult:
    ok: bool
    errors: List[str]
    warnings: List[str]


EXPAT_DYLD_PATH = "/opt/homebrew/opt/expat/lib"


def run_preflight(require_oracle_env: bool = True) -> PreflightResult:
    errors: List[str] = []
    warnings: List[str] = []
    _apply_expat_workaround_if_present(warnings)

    for module_name in ("antlr4", "oracledb"):
        try:
            __import__(module_name)
        except Exception as exc:
            errors.append(f"Failed to import {module_name}: {exc}")

    try:
        from examples.cypher2oracle_sqlpgq import cypher2oracle_sqlpgq  # noqa: F401
    except Exception as exc:
        message = str(exc)
        if "pyexpat" in message or "libexpat" in message:
            warnings.append(_expat_help_text())
        errors.append(f"Failed to import Cypher to Oracle translator: {exc}")

    if require_oracle_env:
        for env_name in ("ORACLE_DSN", "ORACLE_USER", "ORACLE_PASSWORD"):
            if not os.getenv(env_name):
                errors.append(f"Missing required environment variable: {env_name}")

    return PreflightResult(ok=not errors, errors=errors, warnings=warnings)


def _apply_expat_workaround_if_present(warnings: List[str]) -> None:
    if platform.system() != "Darwin":
        return
    current = os.environ.get("DYLD_LIBRARY_PATH", "")
    if EXPAT_DYLD_PATH in current:
        return
    if os.path.isdir(EXPAT_DYLD_PATH):
        os.environ["DYLD_LIBRARY_PATH"] = (
            f"{EXPAT_DYLD_PATH}:{current}" if current else EXPAT_DYLD_PATH
        )
        warnings.append(
            "Applied macOS expat workaround from oracle_sqlpgq_data_generation_workflow.md."
        )


def _expat_help_text() -> str:
    return (
        "pyexpat/libexpat issue detected. Run with "
        'DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib:${DYLD_LIBRARY_PATH:-}" '
        "as documented in doc/en-us/development/oracle_sqlpgq_data_generation_workflow.md."
    )
