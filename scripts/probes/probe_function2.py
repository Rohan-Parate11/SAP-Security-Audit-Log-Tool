"""Ad-hoc spike helper: inspect a remote-enabled function module using pyrfc's
own metadata API (richer than RFC_GET_FUNCTION_INTERFACE for nested structures).

Usage:
    python scripts\\probe_function2.py SYSTEM_ID FUNCTION_NAME
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal import config  # noqa: F401  sets up PATH before importing pyrfc
import pyrfc
from sal.sap_connector import SapConnection, SapConnectionError


def describe_type(field, indent=2):
    pad = " " * indent
    type_desc = field.get("type_description")
    print(f"{pad}{field['name']:<20} rfc_type={field.get('field_type')} nuc_length={field.get('nuc_length')}")
    if type_desc is not None:
        for sub in type_desc.fields:
            describe_type(sub, indent + 4)


def main(system_id: str, function_name: str) -> int:
    try:
        with SapConnection(system_id) as conn:
            fd = conn._conn.get_function_description(function_name)
            print(f"Function module: {function_name}")
            for p in fd.parameters:
                print(f"- {p['name']} ({p['direction']}) type={p['parameter_type']}")
                type_desc = p.get("type_description")
                if type_desc is not None:
                    for sub in type_desc.fields:
                        describe_type(sub, 4)
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1
    except pyrfc.RFCError as exc:
        print(f"RFC ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
