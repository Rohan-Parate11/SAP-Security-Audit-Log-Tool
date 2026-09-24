"""Environment/config loading for SAL.

Must be imported before ``pyrfc`` anywhere in the codebase, because it puts the
NW RFC SDK's ``lib`` directory on PATH so Windows can locate sapnwrfc.dll and
its dependencies at import time.
"""
import os
import re
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

_sdk_home = os.environ.get("SAPNWRFC_HOME", "").strip()
if _sdk_home:
    _sdk_home_path = Path(_sdk_home)
    if not _sdk_home_path.is_absolute():
        _sdk_home_path = BASE_DIR / _sdk_home_path
    os.environ["SAPNWRFC_HOME"] = str(_sdk_home_path)

    _lib_dir = str(_sdk_home_path / "lib")
    if _lib_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _lib_dir + os.pathsep + os.environ.get("PATH", "")

_REQUIRED_KEYS = ("ASHOST", "SYSNR", "CLIENT", "USER", "PASSWD")


def sap_system_config(system_id: str) -> dict:
    """Connection parameters for one SAP system - checks the central
    credential store first (sal/credentials.py, added 2026-09-16), falling
    back to the original all-.env lookup below when nothing is stored
    there for this system_id. The import is deferred to call time, not
    module level: sal/systems.py (which sal.credentials.resolve_stored_
    config() needs) already imports this module at module level, so a
    module-level import here would be circular - config.py must stay
    importable with zero sal.* dependencies of its own, since it must be
    importable before pyrfc anywhere in the codebase (see this module's
    own top docstring).

    Falls back to reading ``SAL_SAP_<SYSTEM_ID>_<FIELD>`` environment
    variables, e.g. ``SAL_SAP_S23_ASHOST``.
    """
    from . import credentials
    stored = credentials.resolve_stored_config(system_id)
    if stored is not None:
        return stored

    prefix = f"SAL_SAP_{system_id.upper()}_"
    missing = []
    cfg = {}
    for key in _REQUIRED_KEYS:
        value = os.environ.get(prefix + key)
        if not value:
            missing.append(prefix + key)
        else:
            cfg[key.lower()] = value
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s) for SAP system '{system_id}': "
            + ", ".join(missing)
        )
    return cfg


_SYSTEM_ID_PATTERN = re.compile(r"^SAL_SAP_([A-Z0-9]+)_ASHOST$")


def list_configured_systems() -> list[dict]:
    """Discover SAP system profiles present in the environment.

    Returns one entry per system ID that has a SAL_SAP_<ID>_ASHOST variable,
    so the UI can offer a system/client picker instead of a free-text field.
    """
    systems = []
    seen = set()
    for key in os.environ:
        match = _SYSTEM_ID_PATTERN.match(key)
        if not match:
            continue
        system_id = match.group(1)
        if system_id in seen:
            continue
        seen.add(system_id)
        systems.append({
            "system_id": system_id,
            "client": os.environ.get(f"SAL_SAP_{system_id}_CLIENT", ""),
            "description": os.environ.get(f"SAL_SAP_{system_id}_DESCRIPTION", system_id),
        })
    return sorted(systems, key=lambda s: s["system_id"])
