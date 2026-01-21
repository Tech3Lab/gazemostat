#!/usr/bin/env python3
"""
RP2040 NeoPixel Firmware Upload Script for Windows
Automatically installs Arduino CLI (if needed), compiles, and uploads firmware to LattePanda Iota RP2040
Windows-specific implementation
"""

import os
import sys
import subprocess
import platform
import shutil
import urllib.request
import zipfile
import json
import string
import time
import argparse
from pathlib import Path

# Verify we're on Windows
if platform.system() != "Windows":
    print("ERROR: This script is designed for Windows only.")
    print(f"Detected platform: {platform.system()}")
    sys.exit(1)

# Configuration
ARDUINO_CLI_VERSION = "0.35.3"  # Latest stable version
DEFAULT_FIRMWARE_FILE = "firmware.ino"  # Default firmware filename
BOARD_FQBN = "rp2040:rp2040:rpipico"  # Raspberry Pi Pico / RP2040
LIBRARY_NAME = "Adafruit NeoPixel"
LIBRARY_VERSION = "1.11.2"  # Or latest
CONFIG_FILE = "config.yaml"  # Configuration file path

# Windows-specific settings
ARDUINO_CLI_NAME = "arduino-cli.exe"
ARDUINO_CLI_URL = f"https://github.com/arduino/arduino-cli/releases/download/v{ARDUINO_CLI_VERSION}/arduino-cli_{ARDUINO_CLI_VERSION}_Windows_64bit.zip"
ARDUINO_CLI_DIR = Path.home() / ".arduino-cli"
ARDUINO_CLI_PATH = ARDUINO_CLI_DIR / ARDUINO_CLI_NAME


def print_step(message):
    """Print a formatted step message"""
    print(f"\n{'='*60}")
    print(f"  {message}")
    print(f"{'='*60}")


def print_info(message):
    """Print an info message"""
    print(f"  [INFO] {message}")


def print_error(message):
    """Print an error message"""
    print(f"  [ERROR] {message}", file=sys.stderr)


def print_success(message):
    """Print a success message"""
    print(f"  [SUCCESS] {message}")


def check_arduino_cli():
    """Check if arduino-cli is available in PATH or in expected location"""
    # Check in PATH first
    if shutil.which("arduino-cli"):
        return shutil.which("arduino-cli")
    
    # Check in expected location
    if ARDUINO_CLI_PATH.exists():
        return str(ARDUINO_CLI_PATH)
    
    return None


def install_arduino_cli():
    """Download and install Arduino CLI"""
    print_step("Installing Arduino CLI")
    
    try:
        # Create directory
        ARDUINO_CLI_DIR.mkdir(parents=True, exist_ok=True)
        
        # Download
        print_info(f"Downloading Arduino CLI v{ARDUINO_CLI_VERSION}...")
        zip_path = ARDUINO_CLI_DIR / "arduino-cli.zip"
        
        urllib.request.urlretrieve(ARDUINO_CLI_URL, zip_path)
        print_success("Download complete")
        
        # Extract (Windows uses ZIP)
        print_info("Extracting...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(ARDUINO_CLI_DIR)
        
        # Clean up
        zip_path.unlink()
        
        print_success(f"Arduino CLI installed to {ARDUINO_CLI_DIR}")
        return str(ARDUINO_CLI_PATH)
        
    except Exception as e:
        print_error(f"Failed to install Arduino CLI: {e}")
        return None


def run_arduino_cli(cli_path, args, check=True):
    """Run arduino-cli command"""
    cmd = [cli_path] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr
    except FileNotFoundError:
        print_error(f"Arduino CLI not found at {cli_path}")
        return False, "", ""


def setup_arduino_cli(cli_path):
    """Initialize Arduino CLI and install board support"""
    print_step("Setting up Arduino CLI")
    
    # Initialize config
    print_info("Initializing Arduino CLI configuration...")
    success, stdout, stderr = run_arduino_cli(cli_path, ["config", "init", "--overwrite"])
    if not success:
        print_error(f"Failed to initialize config: {stderr}")
        return False
    
    # Add board manager URL
    print_info("Adding RP2040 board support URL...")
    board_url = "https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json"
    success, stdout, stderr = run_arduino_cli(cli_path, [
        "config", "add", "board_manager.additional_urls", board_url
    ])
    if not success and "already exists" not in stderr.lower():
        print_error(f"Failed to add board URL: {stderr}")
        return False
    
    # Update board index
    print_info("Updating board index...")
    success, stdout, stderr = run_arduino_cli(cli_path, ["core", "update-index"])
    if not success:
        print_error(f"Failed to update board index: {stderr}")
        return False
    
    # Install RP2040 core
    print_info("Installing RP2040 core...")
    success, stdout, stderr = run_arduino_cli(cli_path, ["core", "install", "rp2040:rp2040"])
    if not success:
        print_error(f"Failed to install RP2040 core: {stderr}")
        return False
    
    print_success("RP2040 core installed")
    
    # Install NeoPixel library
    print_info(f"Installing {LIBRARY_NAME} library...")
    success, stdout, stderr = run_arduino_cli(cli_path, [
        "lib", "install", LIBRARY_NAME
    ])
    if not success:
        print_error(f"Failed to install library: {stderr}")
        return False
    
    print_success(f"{LIBRARY_NAME} library installed")
    return True


def find_rp2040_bootloader_drive():
    """Find RPI-RP2 bootloader drive on Windows"""
    print_info("Scanning for RP2040 bootloader drive (RPI-RP2)...")
    
    # Check all drive letters
    drives = []
    for letter in string.ascii_uppercase:
        drive_path = Path(f"{letter}:\\")
        if drive_path.exists():
            # Check if it's the RP2040 bootloader drive
            try:
                volume_name = subprocess.check_output(
                    ['wmic', 'logicaldisk', 'get', 'name,volumename'],
                    shell=True,
                    text=True
                )
                if 'RPI-RP2' in volume_name or f'{letter}:' in volume_name:
                    # Double-check by looking for INFO_UF2.TXT
                    info_file = drive_path / "INFO_UF2.TXT"
                    if info_file.exists():
                        drives.append(f"{letter}:")
            except:
                pass
    
    return drives


def find_arduino_ports(cli_path):
    """Find available COM ports for RP2040 on Windows"""
    print_info("Scanning for RP2040 COM ports...")
    success, stdout, stderr = run_arduino_cli(cli_path, ["board", "list"])
    
    if not success:
        print_error(f"Failed to list boards: {stderr}")
        return []
    
    ports = []
    for line in stdout.split('\n'):
        # Look for COM ports (Windows format: COM3, COM4, etc.)
        if 'COM' in line.upper():
            parts = line.split()
            for part in parts:
                if part.upper().startswith('COM') and part.upper()[3:].isdigit():
                    ports.append(part.upper())
    
    # Also check Windows Device Manager via PowerShell
    try:
        ps_cmd = 'Get-PnPDevice -Class Ports | Where-Object {$_.FriendlyName -like "*USB*" -or $_.FriendlyName -like "*Serial*"} | Select-Object -ExpandProperty FriendlyName'
        result = subprocess.run(
            ['powershell', '-Command', ps_cmd],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'COM' in line:
                    # Extract COM port number
                    import re
                    com_match = re.search(r'COM(\d+)', line)
                    if com_match:
                        com_port = f"COM{com_match.group(1)}"
                        if com_port not in ports:
                            ports.append(com_port)
    except:
        pass  # PowerShell check is optional
    
    return ports


def compile_firmware(cli_path, firmware_path):
    """Compile the firmware"""
    print_step("Compiling Firmware")
    
    if not os.path.exists(firmware_path):
        print_error(f"Firmware file not found: {firmware_path}")
        return False
    
    print_info(f"Compiling {firmware_path}...")
    success, stdout, stderr = run_arduino_cli(cli_path, [
        "compile",
        "--fqbn", BOARD_FQBN,
        "--verbose",
        firmware_path
    ])
    
    if not success:
        print_error("Compilation failed!")
        print_error(stderr)
        return False
    
    print_success("Compilation successful!")
    return True


def upload_via_uf2(firmware_path):
    """Upload firmware via UF2 file copy (Windows bootloader mode)"""
    print_step("Uploading via UF2 (Bootloader Mode)")
    
    # Find bootloader drive
    drives = find_rp2040_bootloader_drive()
    if not drives:
        print_error("RP2040 bootloader drive (RPI-RP2) not found!")
        print_info("\nPlease enter bootloader mode:")
        print_info("  1. Hold the BOOTSEL button on LattePanda Iota")
        print_info("  2. Press and release the RST button")
        print_info("  3. Release the BOOTSEL button")
        print_info("  4. Windows should show a drive named 'RPI-RP2'")
        print_info("  5. Run this script again")
        return False
    
    bootloader_drive = drives[0]
    print_info(f"Found bootloader drive: {bootloader_drive}")
    
    # Compile to get UF2 file location
    print_info("Compiling to generate UF2 file...")
    script_dir = Path(firmware_path).parent
    build_dir = script_dir / "build"
    build_dir.mkdir(exist_ok=True)
    
    # Use arduino-cli to compile and get UF2
    cli_path = check_arduino_cli()
    if not cli_path:
        print_error("Arduino CLI not found")
        return False
    
    # Compile with output directory
    success, stdout, stderr = run_arduino_cli(cli_path, [
        "compile",
        "--fqbn", BOARD_FQBN,
        "--output-dir", str(build_dir),
        firmware_path
    ])
    
    if not success:
        print_error("Compilation failed!")
        print_error(stderr)
        return False
    
    # Find the UF2 file (arduino-cli creates it in build directory)
    uf2_files = list(build_dir.glob("*.uf2"))
    if not uf2_files:
        # Sometimes it's in a subdirectory
        uf2_files = list(build_dir.rglob("*.uf2"))
    
    if not uf2_files:
        print_error("UF2 file not found after compilation")
        print_info("Trying alternative method...")
        # Try to find in Arduino's build directory
        arduino_data = Path.home() / "AppData" / "Local" / "Arduino15"
        uf2_files = list(arduino_data.rglob("*.uf2"))
        # Filter to most recent
        if uf2_files:
            uf2_files = [max(uf2_files, key=lambda p: p.stat().st_mtime)]
    
    if not uf2_files:
        print_error("Could not locate UF2 file")
        return False
    
    uf2_file = uf2_files[0]
    print_info(f"Found UF2 file: {uf2_file.name}")
    
    # Copy UF2 to bootloader drive
    print_info(f"Copying UF2 to {bootloader_drive}...")
    try:
        dest_file = Path(f"{bootloader_drive}\\{uf2_file.name}")
        shutil.copy2(uf2_file, dest_file)
        
        # Wait for upload to complete (drive will disappear)
        print_info("Waiting for upload to complete...")
        time.sleep(3)
        
        # Verify drive is gone (upload complete)
        if not Path(bootloader_drive).exists():
            print_success("Upload successful! RP2040 is rebooting...")
            return True
        else:
            print_info("Upload may still be in progress...")
            print_success("Upload initiated - RP2040 will reboot automatically")
            return True
            
    except Exception as e:
        print_error(f"Failed to copy UF2 file: {e}")
        return False


def upload_firmware(cli_path, firmware_path, port=None):
    """Upload firmware to RP2040 (Windows-specific)"""
    print_step("Uploading Firmware")
    
    # First, try to find bootloader drive (easier method)
    bootloader_drives = find_rp2040_bootloader_drive()
    if bootloader_drives:
        print_info("RP2040 is in bootloader mode - using UF2 method")
        return upload_via_uf2(firmware_path)
    
    # Otherwise, try normal upload via COM port
    if not port:
        ports = find_arduino_ports(cli_path)
        if ports:
            port = ports[0]
            print_info(f"Auto-detected COM port: {port}")
        else:
            print_error("No RP2040 COM port found!")
            print_info("\nOptions:")
            print_info("  1. Enter bootloader mode (recommended):")
            print_info("     - Hold BOOTSEL button")
            print_info("     - Press and release RST button")
            print_info("     - Release BOOTSEL button")
            print_info("     - Run this script again")
            print_info("  2. Or connect normally and specify COM port manually")
            return False
    
    print_info(f"Uploading to {port}...")
    
    cmd = [
        "upload",
        "--fqbn", BOARD_FQBN,
        "--port", port,
        "--verbose",
        firmware_path
    ]
    
    success, stdout, stderr = run_arduino_cli(cli_path, cmd, check=False)
    
    if not success:
        print_error("Upload failed!")
        print_error(stderr)
        print_info("\nTroubleshooting:")
        print_info("  - Try entering bootloader mode (BOOTSEL + RST)")
        print_info("  - Check USB cable connection")
        print_info("  - Try a different USB port")
        print_info("  - Make sure no other program is using the COM port")
        return False
    
    print_success("Upload successful!")
    print_success("RP2040 will reboot automatically")
    return True


def load_config_firmware_path():
    """Load firmware path from config.yaml if available"""
    script_dir = Path(__file__).parent
    config_path = script_dir / CONFIG_FILE
    
    if not config_path.exists():
        print_info(f"Config file not found at {config_path}, using default")
        return None
    
    try:
        import yaml
    except ImportError:
        print_info("PyYAML not available, cannot load config.yaml - using default")
        return None
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            if config and 'firmware_path' in config:
                firmware_path_str = config['firmware_path']
                if not firmware_path_str:
                    print_info("firmware_path is empty in config.yaml, using default")
                    return None
                
                # If relative, resolve from config file's directory (project root)
                firmware_path = Path(firmware_path_str)
                if not firmware_path.is_absolute():
                    firmware_path = script_dir / firmware_path
                
                resolved_path = firmware_path.resolve()
                print_info(f"Loaded firmware_path from config.yaml: {firmware_path_str} -> {resolved_path}")
                return resolved_path
            else:
                print_info("firmware_path not found in config.yaml, using default")
                return None
    except Exception as e:
        print_error(f"Error loading config.yaml: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main function"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Upload NeoPixel firmware to LattePanda Iota RP2040",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python upload_firmware.py
  python upload_firmware.py --firmware firmware.ino
  python upload_firmware.py --firmware C:\\path\\to\\firmware.ino
        """
    )
    parser.add_argument(
        '--firmware', '-f',
        type=str,
        default=None,
        help=f'Path to firmware .ino file (default: from config.yaml or {DEFAULT_FIRMWARE_FILE} in script directory)'
    )
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("  RP2040 NeoPixel Firmware Upload Script")
    print("="*60)
    
    # Determine firmware file path (priority: CLI arg > config.yaml > default)
    if args.firmware:
        # User specified a path via command line (highest priority)
        firmware_path = Path(args.firmware).resolve()
        print_info(f"Using firmware path from command line: {firmware_path}")
    else:
        # Try to load from config.yaml first
        config_firmware_path = load_config_firmware_path()
        if config_firmware_path and config_firmware_path.exists():
            firmware_path = config_firmware_path
            print_info(f"Using firmware path from config.yaml: {firmware_path}")
        else:
            # Fall back to default: look in script directory
            script_dir = Path(__file__).parent
            firmware_path = script_dir / DEFAULT_FIRMWARE_FILE
            if config_firmware_path:
                print_info(f"Config path {config_firmware_path} not found, using default: {firmware_path}")
            else:
                print_info(f"Using default firmware path: {firmware_path}")
    
    # Check if firmware file exists
    if not firmware_path.exists():
        print_error(f"Firmware file not found: {firmware_path}")
        if args.firmware:
            print_info("Check that the specified path is correct")
        else:
            print_info(f"Make sure firmware file exists at the configured path")
            print_info(f"  - Check config.yaml 'firmware_path' setting")
            print_info(f"  - Or specify a path with: python upload_firmware.py --firmware <path>")
        return 1
    
    print_info(f"Using firmware file: {firmware_path}")
    
    # Check/install Arduino CLI
    cli_path = check_arduino_cli()
    if not cli_path:
        print_info("Arduino CLI not found, installing...")
        cli_path = install_arduino_cli()
        if not cli_path:
            print_error("Failed to install Arduino CLI")
            return 1
    else:
        print_success(f"Arduino CLI found at: {cli_path}")
    
    # Setup Arduino CLI (install cores and libraries)
    if not setup_arduino_cli(cli_path):
        print_error("Failed to setup Arduino CLI")
        return 1
    
    # Compile firmware
    if not compile_firmware(cli_path, str(firmware_path)):
        return 1
    
    # Upload firmware
    if not upload_firmware(cli_path, str(firmware_path)):
        return 1
    
    print_step("All Done!")
    print_success("Firmware uploaded successfully!")
    print_info("The RP2040 should now be running the NeoPixel controller firmware")
    print_info("You can test it by opening a serial monitor at 115200 baud")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nUpload cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
