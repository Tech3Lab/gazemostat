#!/usr/bin/env python3
"""
OLED Diagnostic Script (SSD1306 over I2C via RP2040 firmware)

This mirrors `test_neopixels.py` but triggers the on-device OLED integrity test:
  - Sends: OLED:TEST
  - Expects: OLED:OK  (or OLED:FAIL:<reason>)
"""

import sys
import time

import serial
import serial.tools.list_ports


def list_serial_ports():
    """List all available serial ports"""
    print("\n=== Available Serial Ports ===")
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("  No serial ports found!")
        return []

    for port in ports:
        print(f"  {port.device} - {port.description}")
    return [p.device for p in ports]


def open_serial(port_name, baud=115200):
    """Open serial connection to RP2040"""
    print("\n=== Opening Serial Connection ===")
    print(f"Port: {port_name}")
    print(f"Baud: {baud}")

    try:
        ser = serial.Serial(port_name, baud, timeout=0.5)
        print("  ✓ Serial port opened successfully")
        time.sleep(0.5)
        if ser.in_waiting > 0:
            ser.reset_input_buffer()
            print("  ✓ Cleared input buffer")
        return ser
    except serial.SerialException as e:
        print(f"  ✗ Failed to open serial port: {e}")
        return None


def wait_for_hello(ser, timeout_s=5.0):
    """Wait for HELLO messages from firmware"""
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
        print("  ⚠ No HELLO received; trying PING...")
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
        print("  ✓ HELLO OLED received")
    else:
        print("  ⚠ HELLO OLED not observed (firmware might still support OLED; continuing)")

    return got_oled


def run_oled_integrity_test(ser, timeout_s=12.0):
    """Trigger OLED:TEST and wait for OLED:OK / OLED:FAIL"""
    print("\n=== Running OLED Integrity Test ===")
    cmd = "OLED:TEST"
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
                # e.g. OLED:FAIL:<reason>
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    fail_reason = parts[2]
                else:
                    fail_reason = "Unknown failure"
                return False, fail_reason

        # If firmware is chatty, it may emit intermediate lines; keep waiting.
        # If nothing comes back for a while, we still keep waiting until timeout.
        if time.time() - last_line_time > 3.0:
            # Give a small hint but don't spam
            last_line_time = time.time()
            print("  (waiting...)")

        time.sleep(0.05)

    return False, "Timed out waiting for OLED:OK / OLED:FAIL"


def main():
    print("=" * 60)
    print("OLED Diagnostic Tool")
    print("=" * 60)

    ports = list_serial_ports()
    if not ports:
        print("\n✗ No serial ports found!")
        print("\nTroubleshooting:")
        print("  1. Make sure RP2040 is connected via USB")
        print("  2. Check USB cable connection")
        print("  3. Try unplugging and replugging USB cable")
        print("  4. Check dmesg / device permissions (Linux)")
        return 1

    if len(ports) == 1:
        port = ports[0]
        print(f"\nUsing only available port: {port}")
    else:
        print("\nMultiple ports found. Please select:")
        for i, p in enumerate(ports):
            print(f"  {i+1}. {p}")
        try:
            choice = input("\nEnter port number (or press Enter to use first): ").strip()
            if choice:
                port = ports[int(choice) - 1]
            else:
                port = ports[0]
        except (ValueError, IndexError):
            print("Invalid choice, using first port")
            port = ports[0]

    ser = open_serial(port)
    if ser is None:
        return 1

    try:
        wait_for_hello(ser)
        ok, reason = run_oled_integrity_test(ser)
        if ok:
            print("\n✓ OLED integrity test PASSED")
            print("If the screen is connected, you should have seen:")
            print("  - A border + text")
            print("  - A checkerboard pattern")
            print('  - "OLED OK" message')
            return 0

        print("\n✗ OLED integrity test FAILED")
        print(f"Reason: {reason}")
        print("\nTroubleshooting:")
        print("  - Confirm wiring: 3.3V, GND, SDA=GP4, SCL=GP5")
        print("  - Confirm your OLED is SSD1306 I2C and address is 0x3C (or 0x3D)")
        print("  - Make sure the bonnet is powered from 3.3V (not 5V) if required")
        return 2
    finally:
        ser.close()
        print("\nSerial port closed")


if __name__ == "__main__":
    sys.exit(main())

