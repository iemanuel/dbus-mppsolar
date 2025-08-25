#!/usr/bin/env python3

"""
Diagnostic tool for MPP Solar inverter communication issues.
This tool helps identify why the inverter is returning empty responses.
"""

import serial
import time
import logging
import argparse
import sys
import os

# Add local mpp-solar to path
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'mpp-solar'))
import mppsolar

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

def crc16(data):
    """Calculate CRC16 for command validation."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc

def format_command(cmd: str) -> bytes:
    """Format a command with proper CRC and termination."""
    cmd_bytes = f"^P{len(cmd):03d}{cmd}".encode('ascii')
    crc = crc16(cmd_bytes)
    crc_bytes = bytes([crc >> 8, crc & 0xFF])
    return cmd_bytes + crc_bytes + b'\r'

def test_raw_serial(port: str, baud: int = 2400):
    """Test raw serial communication with various configurations."""
    configs = [
        # (bytesize, parity, stopbits, description)
        (8, 'N', 1, "8N1 (Standard)"),
        (8, 'N', 2, "8N2"),
        (8, 'E', 1, "8E1 (Even parity)"),
        (8, 'O', 1, "8O1 (Odd parity)"),
        (7, 'N', 1, "7N1"),
        (7, 'E', 1, "7E1"),
    ]
    
    commands = ['PI', 'ID', 'GS', 'PIRI']
    
    print(f"\n=== Testing Raw Serial Communication ===")
    print(f"Port: {port}, Baud: {baud}")
    
    for bytesize, parity, stopbits, desc in configs:
        print(f"\n--- Testing {desc} ---")
        
        try:
            with serial.Serial(port, baud, bytesize=bytesize, parity=parity, 
                             stopbits=stopbits, timeout=3, write_timeout=2) as ser:
                
                for cmd in commands:
                    formatted_cmd = format_command(cmd)
                    print(f"Testing command: {cmd}")
                    print(f"Formatted: {formatted_cmd}")
                    
                    # Clear buffers
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                    
                    # Send command
                    bytes_written = ser.write(formatted_cmd)
                    ser.flush()
                    print(f"Wrote {bytes_written} bytes")
                    
                    # Wait for response
                    time.sleep(0.5)
                    
                    # Check what's waiting
                    waiting = ser.in_waiting
                    print(f"Bytes waiting: {waiting}")
                    
                    if waiting > 0:
                        response = ser.read(waiting)
                        print(f"Response: {response}")
                        print(f"Response (hex): {response.hex()}")
                        print(f"Response (ascii): {response.decode('ascii', errors='replace')}")
                        
                        if response:
                            print(f"✓ Got response for {cmd} with {desc}")
                            return True, desc, cmd, response
                    else:
                        print(f"✗ No response for {cmd}")
                    
                    time.sleep(0.2)  # Small delay between commands
                    
        except Exception as e:
            print(f"Error with {desc}: {e}")
    
    return False, None, None, None

def test_mppsolar_library(port: str, baud: int = 2400):
    """Test using the mppsolar library directly."""
    print(f"\n=== Testing MPP-Solar Library ===")
    
    protocols = ['PI18SV', 'PI30', 'PI16', 'PI17', 'PI18']
    commands = ['PI', 'ID', 'GS', 'PIRI']
    
    for protocol in protocols:
        print(f"\n--- Testing Protocol: {protocol} ---")
        
        try:
            # Get device
            device = mppsolar.helpers.get_device_class("mppsolar")(
                port=port,
                protocol=protocol,
                baud=baud
            )
            
            for cmd in commands:
                print(f"Testing command: {cmd}")
                
                try:
                    result = device.run_command(command=cmd)
                    print(f"Result: {result}")
                    
                    if result and not (isinstance(result, dict) and 'error' in result):
                        print(f"✓ Success with protocol {protocol}, command {cmd}")
                        return True, protocol, cmd, result
                    else:
                        print(f"✗ No valid response")
                        
                except Exception as e:
                    print(f"✗ Command error: {e}")
                
                time.sleep(0.5)  # Delay between commands
                
        except Exception as e:
            print(f"Error initializing protocol {protocol}: {e}")
    
    return False, None, None, None

def diagnose_timeouts(port: str, baud: int = 2400):
    """Test different timeout values to find optimal settings."""
    print(f"\n=== Testing Different Timeouts ===")
    
    timeouts = [0.5, 1.0, 2.0, 3.0, 5.0]
    cmd = 'PI'
    formatted_cmd = format_command(cmd)
    
    for timeout in timeouts:
        print(f"\n--- Testing timeout: {timeout}s ---")
        
        try:
            with serial.Serial(port, baud, timeout=timeout, write_timeout=2) as ser:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                start_time = time.time()
                ser.write(formatted_cmd)
                ser.flush()
                
                response = ser.read_until(b'\r')
                actual_time = time.time() - start_time
                
                print(f"Response: {response}")
                print(f"Actual time: {actual_time:.2f}s")
                
                if response and len(response) > 0:
                    print(f"✓ Got response with {timeout}s timeout in {actual_time:.2f}s")
                    return timeout, response
                
        except Exception as e:
            print(f"Error with timeout {timeout}: {e}")
        
        time.sleep(0.2)
    
    return None, None

def main():
    parser = argparse.ArgumentParser(description="Diagnose MPP Solar inverter communication")
    parser.add_argument("--port", "-p", required=True, help="Serial port (e.g., /dev/ttyUSB0)")
    parser.add_argument("--baud", "-b", type=int, default=2400, help="Baud rate (default: 2400)")
    parser.add_argument("--test", "-t", choices=['raw', 'library', 'timeouts', 'all'], 
                       default='all', help="Test type to run")
    
    args = parser.parse_args()
    
    print(f"Diagnosing inverter communication on {args.port} at {args.baud} baud")
    
    # Check if port exists
    if not os.path.exists(args.port):
        print(f"Error: Port {args.port} does not exist")
        return 1
    
    results = {}
    
    if args.test in ['raw', 'all']:
        success, config, cmd, response = test_raw_serial(args.port, args.baud)
        results['raw'] = (success, config, cmd, response)
    
    if args.test in ['library', 'all']:
        success, protocol, cmd, response = test_mppsolar_library(args.port, args.baud)
        results['library'] = (success, protocol, cmd, response)
    
    if args.test in ['timeouts', 'all']:
        optimal_timeout, response = diagnose_timeouts(args.port, args.baud)
        results['timeouts'] = (optimal_timeout, response)
    
    # Summary
    print(f"\n{'='*50}")
    print("DIAGNOSIS SUMMARY")
    print(f"{'='*50}")
    
    if 'raw' in results:
        success, config, cmd, response = results['raw']
        if success:
            print(f"✓ Raw serial communication WORKS with {config}")
            print(f"  Command: {cmd}")
            print(f"  Response: {response}")
        else:
            print("✗ Raw serial communication FAILED with all configurations")
    
    if 'library' in results:
        success, protocol, cmd, response = results['library']
        if success:
            print(f"✓ MPP-Solar library WORKS with protocol {protocol}")
            print(f"  Command: {cmd}")
            print(f"  Response: {response}")
        else:
            print("✗ MPP-Solar library FAILED with all protocols")
    
    if 'timeouts' in results:
        optimal_timeout, response = results['timeouts']
        if optimal_timeout:
            print(f"✓ Optimal timeout found: {optimal_timeout}s")
            print(f"  Response: {response}")
        else:
            print("✗ No timeout value worked")
    
    # Recommendations
    print(f"\n{'='*50}")
    print("RECOMMENDATIONS")
    print(f"{'='*50}")
    
    if any(r[0] for r in results.values() if isinstance(r[0], bool)):
        print("✓ Communication is possible! Try these solutions:")
        
        if 'raw' in results and results['raw'][0]:
            config = results['raw'][1]
            print(f"1. Use serial configuration: {config}")
        
        if 'library' in results and results['library'][0]:
            protocol = results['library'][1]
            print(f"2. Use protocol: {protocol}")
        
        if 'timeouts' in results and results['timeouts'][0]:
            timeout = results['timeouts'][0]
            print(f"3. Increase timeout to: {timeout}s")
        
        print("4. Try running dbus-mppsolar with DEBUG logging:")
        print(f"   python3 dbus-mppsolar.py -s {args.port} -b {args.baud} -l DEBUG")
    else:
        print("✗ No communication possible. Check:")
        print("1. Inverter is powered on and responding")
        print("2. Serial cable is properly connected")
        print("3. Correct serial port device")
        print("4. Try different baud rates: 2400, 9600, 19200")
        print("5. Check if inverter uses different protocol/cable")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
