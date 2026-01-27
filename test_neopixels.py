#!/usr/bin/env python3
"""
NeoPixel Diagnostic Script
Tests NeoPixel communication and helps identify issues
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

def test_serial_connection(port_name, baud=115200):
    """Test serial connection to RP2040"""
    print(f"\n=== Testing Serial Connection ===")
    print(f"Port: {port_name}")
    print(f"Baud: {baud}")
    
    try:
        ser = serial.Serial(port_name, baud, timeout=2.0)
        print("  ✓ Serial port opened successfully")
        
        # Wait a bit for connection
        time.sleep(0.5)
        
        # Clear buffer
        if ser.in_waiting > 0:
            ser.reset_input_buffer()
            print("  ✓ Cleared input buffer")
        
        # Try to read HELLO message
        print("\n  Waiting for HELLO message (5 seconds)...")
        start_time = time.time()
        hello_received = False
        
        while time.time() - start_time < 5.0:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        print(f"  Received: {line}")
                        if "HELLO" in line.upper() and "NEOPIXEL" in line.upper():
                            hello_received = True
                            print("  ✓ HELLO NEOPIXEL message received!")
                except Exception as e:
                    print(f"  Error reading: {e}")
            time.sleep(0.1)
        
        if not hello_received:
            print("  ⚠ No HELLO message received (firmware might not be running)")
            print("  Trying PING command...")
            
            # Try sending PING
            ser.write(b"PING\n")
            ser.flush()
            time.sleep(0.5)
            
            if ser.in_waiting > 0:
                response = ser.readline().decode('utf-8', errors='ignore').strip()
                print(f"  Response: {response}")
                if "HELLO" in response.upper():
                    hello_received = True
                    print("  ✓ Device responded to PING!")
        
        return ser, hello_received
        
    except serial.SerialException as e:
        print(f"  ✗ Failed to open serial port: {e}")
        return None, False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return None, False

def test_commands(ser):
    """Test NeoPixel commands"""
    print(f"\n=== Testing NeoPixel Commands ===")
    
    commands = [
        ("INIT:4:76", "Initialize 4 pixels at 30% brightness"),
        ("ALL:ON:255:255:255", "Turn all pixels white"),
        ("ALL:OFF", "Turn all pixels off"),
        ("PIXEL:0:255:0:0", "Set pixel 0 to red"),
        ("PIXEL:1:0:255:0", "Set pixel 1 to green"),
        ("PIXEL:2:0:0:255", "Set pixel 2 to blue"),
        ("PIXEL:3:255:255:0", "Set pixel 3 to yellow"),
        ("ALL:OFF", "Turn all pixels off"),
    ]
    
    for cmd, description in commands:
        print(f"\n  Testing: {description}")
        print(f"    Command: {cmd}")
        
        try:
            ser.write(f"{cmd}\n".encode('utf-8'))
            ser.flush()
            time.sleep(0.3)
            
            # Check for response
            if ser.in_waiting > 0:
                response = ser.readline().decode('utf-8', errors='ignore').strip()
                print(f"    Response: {response}")
                if "ERROR" in response.upper():
                    print(f"    ⚠ Error from device!")
                elif "ACK" in response.upper():
                    print(f"    ✓ Command acknowledged")
            else:
                print(f"    ⚠ No response from device")
            
            # Wait a bit between commands
            time.sleep(0.5)
            
        except Exception as e:
            print(f"    ✗ Error sending command: {e}")

def test_brightness(ser):
    """Test brightness levels"""
    print(f"\n=== Testing Brightness Levels ===")
    
    brightness_levels = [0, 50, 100, 150, 200, 255]
    
    for brightness in brightness_levels:
        print(f"\n  Setting brightness to {brightness} ({(brightness/255)*100:.1f}%)")
        try:
            ser.write(f"BRIGHTNESS:{brightness}\n".encode('utf-8'))
            ser.flush()
            ser.write(b"ALL:ON:255:255:255\n")
            ser.flush()
            time.sleep(0.3)
            
            if ser.in_waiting > 0:
                response = ser.readline().decode('utf-8', errors='ignore').strip()
                print(f"    Response: {response}")
            
            time.sleep(1.0)  # Wait to see the brightness
            
        except Exception as e:
            print(f"    ✗ Error: {e}")
    
    # Turn off
    ser.write(b"ALL:OFF\n")
    ser.flush()
    time.sleep(0.3)

def main():
    print("=" * 60)
    print("NeoPixel Diagnostic Tool")
    print("=" * 60)
    
    # List available ports
    ports = list_serial_ports()
    
    if not ports:
        print("\n✗ No serial ports found!")
        print("\nTroubleshooting:")
        print("  1. Make sure RP2040 is connected via USB")
        print("  2. Check USB cable connection")
        print("  3. Try unplugging and replugging USB cable")
        print("  4. Check Device Manager (Windows) or dmesg (Linux)")
        return 1
    
    # Ask user which port to use
    if len(ports) == 1:
        port = ports[0]
        print(f"\nUsing only available port: {port}")
    else:
        print(f"\nMultiple ports found. Please select:")
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
    
    # Test connection
    ser, hello_received = test_serial_connection(port)
    
    if ser is None:
        print("\n✗ Could not establish serial connection!")
        print("\nTroubleshooting:")
        print("  1. Check that the port is correct")
        print("  2. Make sure no other program is using the port")
        print("  3. Try closing Arduino IDE Serial Monitor if open")
        print("  4. Check USB cable connection")
        return 1
    
    if not hello_received:
        print("\n⚠ Warning: Device did not respond with HELLO message")
        print("This could mean:")
        print("  - Firmware is not uploaded to RP2040")
        print("  - Firmware is not running")
        print("  - Wrong baud rate (should be 115200)")
        print("\nTrying to continue anyway...")
    
    # Test commands
    try:
        test_commands(ser)
        
        # Ask if user wants to test brightness
        print("\n" + "=" * 60)
        response = input("Test brightness levels? (y/n): ").strip().lower()
        if response == 'y':
            test_brightness(ser)
        
        # Final test - turn all on
        print("\n" + "=" * 60)
        print("Final test: Turning all pixels white at 30% brightness")
        ser.write(b"BRIGHTNESS:76\n")
        ser.flush()
        time.sleep(0.2)
        ser.write(b"ALL:ON:255:255:255\n")
        ser.flush()
        time.sleep(0.3)
        
        if ser.in_waiting > 0:
            response = ser.readline().decode('utf-8', errors='ignore').strip()
            print(f"Response: {response}")
        
        print("\n✓ Diagnostic complete!")
        print("\nIf NeoPixels still don't light up, check:")
        print("  1. Hardware wiring:")
        print("     - NeoPixel DIN connected to RP2040 GPIO pin (GP1)")
        print("     - NeoPixel VCC connected to 5V power")
        print("     - NeoPixel GND connected to ground")
        print("     - Common ground between RP2040 and NeoPixel power")
        print("  2. Power supply:")
        print("     - NeoPixels need 5V power (not 3.3V)")
        print("     - Check power supply can provide enough current")
        print("  3. Firmware:")
        print("     - Make sure firmware is uploaded to RP2040")
        print("     - Check NEOPIXEL_PIN matches your wiring")
        print("     - Check NEOPIXEL_COUNT matches your setup")
        
        input("\nPress Enter to turn off all pixels and exit...")
        ser.write(b"ALL:OFF\n")
        ser.flush()
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n✗ Error during testing: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ser:
            ser.close()
            print("\nSerial port closed")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
