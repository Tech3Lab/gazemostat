#!/usr/bin/env python3
"""
OLED diagnostic script for RP2040 firmware.

Runs firmware-side integrity checks by sending:
  - OLED:TEST              (auto target)
  - OLED:TEST:SSD1327      (128x128 test)
  - OLED:TEST:SSD1306      (128x64 test)
"""

import argparse
import sys
import time

import serial
import serial.tools.list_ports


def list_serial_ports():
    """List all available serial ports."""
    print("\n=== Available Serial Ports ===")
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("  No serial ports found.")
        return []

    for port in ports:
        print(f"  {port.device} - {port.description}")
    return [p.device for p in ports]


def open_serial(port_name, baud=115200):
    """Open serial connection to RP2040."""
    print("\n=== Opening Serial Connection ===")
    print(f"Port: {port_name}")
    print(f"Baud: {baud}")

    try:
        ser = serial.Serial(port_name, baud, timeout=0.5)
        print("  OK: serial port opened")
        time.sleep(0.5)
        if ser.in_waiting > 0:
            ser.reset_input_buffer()
            print("  OK: cleared input buffer")
        return ser
    except serial.SerialException as e:
        print(f"  FAIL: could not open serial port: {e}")
        return None


def wait_for_hello(ser, timeout_s=5.0):
    """Wait for HELLO messages from firmware."""
    print(f"\n=== Waiting for HELLO (up to {timeout_s:.0f}s) ===")
    start = time.time()
    got_any = False
    got_oled = False

    while time.time() - start < timeout_s:
        if ser.in_waiting > 0:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            got_any = True
            print(f"  Received: {line}")
            if "HELLO" in line.upper() and "OLED" in line.upper():
                got_oled = True
        time.sleep(0.05)

    if not got_any:
        print("  No HELLO received; trying PING...")
        ser.write(b"PING\n")
        ser.flush()
        time.sleep(0.4)
        while ser.in_waiting > 0:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if line:
                print(f"  Received: {line}")
                if "HELLO" in line.upper() and "OLED" in line.upper():
                    got_oled = True

    if got_oled:
        print("  OK: HELLO OLED observed")
    else:
        print("  WARN: HELLO OLED not observed (continuing)")

    return got_oled


def _build_test_command(target: str) -> str:
    t = (target or "auto").strip().lower()
    if t == "auto":
        return "OLED:TEST"
    if t in ("ssd1327", "1327", "128x128"):
        return "OLED:TEST:SSD1327"
    if t in ("ssd1306", "1306", "128x64"):
        return "OLED:TEST:SSD1306"
    raise ValueError(f"Unsupported target: {target}")


def run_oled_integrity_test(ser, target="auto", timeout_s=12.0):
    """Trigger OLED integrity test and wait for OLED:OK / OLED:FAIL."""
    print("\n=== Running OLED Integrity Test ===")
    cmd = _build_test_command(target)
    print(f"  Sending: {cmd}")

    ser.write(f"{cmd}\n".encode("utf-8"))
    ser.flush()

    start = time.time()
    last_line_time = time.time()
    fail_reason = None

    while time.time() - start < timeout_s:
        if ser.in_waiting > 0:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            last_line_time = time.time()
            print(f"  {line}")

            u = line.upper()
            if u == "OLED:OK":
                return True, None
            if u.startswith("OLED:FAIL"):
                parts = line.split(":", 2)
                fail_reason = parts[2] if len(parts) >= 3 else "Unknown failure"
                return False, fail_reason

        if time.time() - last_line_time > 3.0:
            last_line_time = time.time()
            print("  (waiting...)")

        time.sleep(0.05)

    return False, "Timed out waiting for OLED:OK / OLED:FAIL"


def main():
    parser = argparse.ArgumentParser(description="Run RP2040 OLED integrity tests.")
    parser.add_argument(
        "--target",
        default="auto",
        choices=["auto", "ssd1327", "ssd1306"],
        help="Select OLED test target (default: auto).",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("OLED Diagnostic Tool")
    print("=" * 60)
    print(f"Target: {args.target}")

    ports = list_serial_ports()
    if not ports:
        print("\nFAIL: no serial ports found")
        print("\nTroubleshooting:")
        print("  1. Ensure RP2040 is connected via USB")
        print("  2. Check USB cable connection")
        print("  3. Unplug and replug USB cable")
        print("  4. Check device permissions")
        return 1

    if len(ports) == 1:
        port = ports[0]
        print(f"\nUsing only available port: {port}")
    else:
        print("\nMultiple ports found. Please select:")
        for i, p in enumerate(ports):
            print(f"  {i + 1}. {p}")
        try:
            choice = input("\nEnter port number (or press Enter for first): ").strip()
            port = ports[int(choice) - 1] if choice else ports[0]
        except (ValueError, IndexError):
            print("Invalid choice, using first port")
            port = ports[0]

    ser = open_serial(port)
    if ser is None:
        return 1

    try:
        wait_for_hello(ser)
        ok, reason = run_oled_integrity_test(ser, target=args.target)
        if ok:
            print("\nPASS: OLED integrity test passed")
            return 0

        print("\nFAIL: OLED integrity test failed")
        print(f"Reason: {reason}")
        print("\nTroubleshooting:")
        print("  - Confirm wiring: 3.3V, GND, SDA=GP4, SCL=GP5")
        print("  - Confirm OLED type matches --target (SSD1327 or SSD1306)")
        print("  - Confirm address strap is 0x3D or 0x3C")
        return 2
    finally:
        ser.close()
        print("\nSerial port closed")


if __name__ == "__main__":
    sys.exit(main())
