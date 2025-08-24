#!/usr/bin/env python3
"""
Real-device protocol and settings detector for EASUN/PI18-family inverters.

Probes a serial device (default /dev/ttyUSB0) across common baud rates using
PI18 and PI18SV protocols, sending a small set of safe commands. Reports the
best working protocol and baud, with sample responses.
"""

import argparse
import os
import sys
import time
from typing import List, Tuple, Optional


# Ensure local submodules are importable when run from repo root
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(REPO_DIR, "mpp-solar"))

try:
    import serial  # pyserial
except Exception as exc:
    print(f"✗ pyserial not available: {exc}")
    sys.exit(1)


# Lazy import protocol classes
def load_protocols():
    from mppsolar.protocols.pi18 import pi18  # type: ignore
    from mppsolar.protocols.pi18sv import pi18sv  # type: ignore
    return [("PI18", pi18), ("PI18SV", pi18sv)]


SAFE_COMMANDS = [
    "PI",   # Protocol inquiry
    "GS",   # General status
    "MOD",  # Mode inquiry
    "PIRI", # Rating information
]


def try_command(ser: serial.Serial, proto_name: str, proto_obj, cmd: str, read_bytes: int) -> Tuple[bool, bool, bytes]:
    """Send one command using protocol's get_full_command, return tuple:
    (got_any_response, got_data_response, raw_bytes)
    - got_any_response: any bytes received
    - got_data_response: not a pure ACK/NAK control token; likely data (e.g., starts with ^D or contains payload)
    """
    try:
        full = proto_obj.get_full_command(cmd)
        if not full:
            return (False, False, b"")
        # Clear input buffer, write command
        ser.reset_input_buffer()
        ser.write(full)
        ser.flush()
        # Small wait for device to respond
        time.sleep(0.2)
        resp = ser.read(read_bytes)
        if not resp:
            return (False, False, b"")
        # Heuristic classification
        # ACK patterns for PI18 family commonly are b"^1\x0b\xc2\r"; NAK b"^0\x1b\xe3\r"
        is_ack = resp.startswith(b"^1") and resp.endswith(b"\r") and len(resp) <= 6
        is_nak = resp.startswith(b"^0") and resp.endswith(b"\r") and len(resp) <= 6
        is_data = (not is_ack) and (not is_nak)
        return (True, is_data, resp)
    except Exception:
        return (False, False, b"")


def score_protocol_on_baud(port: str, baud: int, timeout: float, read_bytes: int, proto_name: str, proto_cls) -> dict:
    result = {
        "proto": proto_name,
        "baud": baud,
        "any": 0,        # num commands with any response
        "data": 0,       # num commands with data-like response
        "samples": [],   # (cmd, hex/printable snippet)
    }
    try:
        with serial.Serial(port, baudrate=baud, timeout=timeout) as ser:
            proto = proto_cls()
            for cmd in SAFE_COMMANDS:
                got_any, got_data, raw = try_command(ser, proto_name, proto, cmd, read_bytes)
                if got_any:
                    result["any"] += 1
                if got_data:
                    result["data"] += 1
                if raw:
                    snippet = raw[:64]
                    try:
                        # Attempt a readable snippet
                        preview = snippet.decode(errors="replace")
                    except Exception:
                        preview = snippet.hex()
                    result["samples"].append((cmd, preview))
                else:
                    result["samples"].append((cmd, "<no response>"))
    except Exception as exc:
        result["error"] = str(exc)
    return result


def pick_best(results: List[dict]) -> Optional[dict]:
    if not results:
        return None
    # Sort by: highest data responses, then any responses, then lower baud preferred (often PI18 = 2400)
    return sorted(
        results,
        key=lambda r: (r.get("data", 0), r.get("any", 0), -r.get("baud", 0)),
        reverse=True,
    )[0]


def main():
    parser = argparse.ArgumentParser(description="Detect best protocol and serial settings for PI18-family inverters.")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default: /dev/ttyUSB0)")
    parser.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout in seconds (default: 1.0)")
    parser.add_argument("--read-bytes", type=int, default=200, help="Max bytes to read per command (default: 200)")
    parser.add_argument(
        "--baud-list",
        default="2400,4800,9600,19200,38400,57600,115200",
        help="Comma-separated baud list to try",
    )
    args = parser.parse_args()

    try:
        baud_list = [int(b.strip()) for b in args.baud_list.split(",") if b.strip()]
    except Exception:
        print("✗ Invalid --baud-list")
        return 2

    print("🚀 Detecting inverter protocol and serial settings")
    print("=" * 60)
    print(f"📁 Port: {args.port}")
    print(f"⏱  Timeout: {args.timeout}s")
    print(f"🔢 Bauds: {baud_list}")
    print()

    protos = load_protocols()
    all_results: List[dict] = []
    for baud in baud_list:
        for pname, pcls in protos:
            print(f"→ Trying {pname} @ {baud}...")
            res = score_protocol_on_baud(
                port=args.port,
                baud=baud,
                timeout=args.timeout,
                read_bytes=args.read_bytes,
                proto_name=pname,
                proto_cls=pcls,
            )
            if "error" in res:
                print(f"  ✗ Error: {res['error']}")
            else:
                print(f"  ✓ Any responses:  {res['any']}")
                print(f"  ✓ Data responses: {res['data']}")
                for cmd, preview in res["samples"]:
                    print(f"    - {cmd}: {preview}")
            all_results.append(res)
            print()

    best = pick_best(all_results)
    print("=" * 60)
    print("📊 Detection Summary")
    print("=" * 60)
    if not best:
        print("✗ No viable responses detected. Check wiring/port/baud and retry.")
        return 1

    print(f"🏆 Recommended: Protocol={best['proto']}  Baud={best['baud']}")
    print(f"   Data responses: {best.get('data', 0)}  Any responses: {best.get('any', 0)}")
    print("   Sample responses:")
    for cmd, preview in best.get("samples", [])[:4]:
        print(f"     • {cmd}: {preview}")

    print()
    print("✅ Next steps:")
    print(f"  • Run service directly: /data/etc/dbus-mppsolar/start-dbus-mppsolar.sh {os.path.basename(args.port)}")
    print("  • If needed, update dbus-mppsolar to use the recommended protocol in its logic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


