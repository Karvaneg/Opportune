"""Mémoire vive de la machine hôte, pour l'avertissement 1er lancement (OPP-193).

Le modèle local (``ministral-3:3b``, ~3 Go sur disque) demande plusieurs Go de RAM pour
tourner correctement. Au premier démarrage, l'app annonce **honnêtement** si la machine
est en dessous du confortable / de l'utilisable, plutôt que de laisser l'utilisateur
découvrir des lenteurs ou des échecs.

Deux responsabilités séparées pour rester testable :

- :func:`total_memory_bytes` — lecture *best-effort* de la RAM totale selon l'OS (impur,
  dépend de la plateforme ; ``None`` si indéterminable) ;
- :func:`assess_memory` — verdict **pur** à partir d'un total donné, donc testable sans
  dépendre de la machine qui exécute les tests.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

_BYTES_PER_GB = 1024**3

# Seuils (Go de RAM totale). En dessous du minimum, le modèle risque de ne pas tourner ;
# entre minimum et recommandé, ça marche mais lentement. Valeurs volontairement prudentes
# pour un modèle 3B quantifié + l'OS + le navigateur embarqué.
RECOMMENDED_GB = 8
MINIMUM_GB = 4

# Verdicts possibles.
OK = "ok"              # au-dessus du recommandé
TIGHT = "tight"        # utilisable mais juste (entre minimum et recommandé)
INSUFFICIENT = "insufficient"  # sous le minimum
UNKNOWN = "unknown"    # RAM indéterminable (on n'affole pas, mais on le dit)


@dataclass(frozen=True)
class MemoryAssessment:
    """Verdict mémoire : total mesuré (Go) et niveau, pour un message honnête côté UI."""

    level: str
    total_gb: float | None
    recommended_gb: int = RECOMMENDED_GB
    minimum_gb: int = MINIMUM_GB


def assess_memory(
    total_bytes: int | None,
    *,
    recommended_gb: int = RECOMMENDED_GB,
    minimum_gb: int = MINIMUM_GB,
) -> MemoryAssessment:
    """Classe une quantité de RAM totale en :data:`OK` / :data:`TIGHT` / :data:`INSUFFICIENT`.

    ``total_bytes=None`` (lecture impossible) → :data:`UNKNOWN` : on ne bloque pas et on ne
    ment pas. Fonction **pure** : tout le jugement se teste sans toucher à la machine.
    """
    if total_bytes is None or total_bytes <= 0:
        return MemoryAssessment(UNKNOWN, None, recommended_gb, minimum_gb)
    total_gb = total_bytes / _BYTES_PER_GB
    if total_gb < minimum_gb:
        level = INSUFFICIENT
    elif total_gb < recommended_gb:
        level = TIGHT
    else:
        level = OK
    return MemoryAssessment(level, round(total_gb, 1), recommended_gb, minimum_gb)


def total_memory_bytes() -> int | None:
    """RAM totale de la machine en octets, ou ``None`` si indéterminable (best-effort, par OS)."""
    if sys.platform == "win32":
        return _windows_total_memory()
    # Linux : SC_PHYS_PAGES × SC_PAGE_SIZE, exposés par la plupart des libc.
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and page_size > 0:
            return pages * page_size
    except (ValueError, OSError, AttributeError):
        pass
    if sys.platform == "darwin":
        return _macos_total_memory()
    return None


def _macos_total_memory() -> int | None:
    """RAM totale sous macOS via ``sysctl -n hw.memsize`` (SC_PHYS_PAGES y est peu fiable)."""
    import subprocess

    try:
        out = subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5
        )
        return int(out.stdout.strip()) or None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _windows_total_memory() -> int | None:
    """RAM totale sous Windows via ``GlobalMemoryStatusEx`` (ctypes, pas de dépendance)."""
    import ctypes

    class _MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
            return int(status.ullTotalPhys) or None
    except (OSError, AttributeError):
        pass
    return None
