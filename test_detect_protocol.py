#!/usr/bin/env python3
import logging
import serial
import time
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(levelname)s - %(message)s')

def calculate_crc(data: bytes) -> bytes:
    """Calculate CRC for MPP-Solar protocol."""
    crc = 0
    for byte in data:
        crc += byte
    crc = ((~crc) & 0xFFFF) + 1
    return bytes([crc >> 8, crc & 0xFF])  # Returns high byte, low byte

def format_command(cmd: str) -> bytes:
    """Format command with proper prefix, length and CRC."""
    # Start with ^P, add 3 digit length, add command
    cmd_without_crc = f"^P{len(cmd):03d}{cmd}".encode()
    
    # Calculate and append CRC
    crc = calculate_crc(cmd_without_crc)
    return cmd_without_crc + crc + b'\r'

class ProtocolDetector:
    def __init__(self, port: str = "/dev/ttyUSB0"):
        self.port = port
        self.serial = None
        self.baud_rates = [2400, 9600, 4800]
        self.serial_configs = [
            # (bytesize, parity, stopbits)
            (serial.EIGHTBITS, serial.PARITY_NONE, serial.STOPBITS_ONE),
            (serial.EIGHTBITS, serial.PARITY_EVEN, serial.STOPBITS_ONE),
            (serial.EIGHTBITS, serial.PARITY_ODD, serial.STOPBITS_ONE),
        ]
        
        # Comprehensive test commands based on protocol doc
        self.test_commands = [
            # Basic identification
            'PI',    # Protocol ID
            'ID',    # Device Serial Number
            'VFW',   # CPU Version
            
            # Status commands
            'GS',    # General Status
            'MOD',   # Working Mode
            'PIRI',  # Rated Information
            'FWS',   # Fault/Warning Status
            
            # Additional status
            'T',     # Current Time
            'ET',    # Total Generated Energy
            'FLAG',  # Enable/Disable Status
            
            # Configuration queries
            'DI',    # Default Parameters
            'MCHGCR',# Max Charging Current Options
            'MUCHGCR',# Max AC Charging Current Options
            
            # Parallel system queries (if applicable)
            'PGS0',  # Parallel General Status
            'PRI0',  # Parallel Rated Info
        ]
        
    def _open_serial(self, baud: int, bytesize: int, parity: str, stopbits: float) -> bool:
        try:
            if self.serial:
                self.serial.close()
            
            self.serial = serial.Serial(
                port=self.port,
                baudrate=baud,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                timeout=1
            )
            return True
        except Exception as e:
            logging.error(f"Failed to open {self.port}: {e}")
            return False

    def _send_command(self, cmd: bytes) -> Optional[bytes]:
        """Send a command and return the response."""
        try:
            self.serial.write(cmd)
            self.serial.flush()
            time.sleep(0.1)  # Give device time to respond
            
            response = b''
            start_time = time.time()
            
            while (time.time() - start_time) < 1.0:  # 1 second timeout
                if self.serial.in_waiting:
                    byte = self.serial.read()
                    response += byte
                    if byte == b'\r':  # End of response
                        break
                time.sleep(0.01)
                    
            return response if response else None
            
        except Exception as e:
            logging.error(f"Communication error: {e}")
            return None

    def _validate_response(self, response: bytes) -> Tuple[bool, bool]:
        """
        Validate response format and CRC.
        Returns (is_valid_format, is_valid_crc)
        """
        if not response or len(response) < 5:
            return False, False
            
        # Check basic format (^D...)
        if not response.startswith(b'^D'):
            # Also accept NAK responses
            if response.startswith(b'(NAK'):
                return True, True
            return False, False
            
        # Extract CRC if present (last 3 bytes should be CRC + \r)
        if len(response) > 4:
            data = response[:-3]
            received_crc = response[-3:-1]
            calculated_crc = calculate_crc(data)
            return True, (received_crc == calculated_crc)
            
        return True, False

    def _test_protocol_command(self, cmd: str) -> Tuple[bool, bool, bytes]:
        """Test a specific protocol command."""
        cmd_bytes = format_command(cmd)
        response = self._send_command(cmd_bytes)
        
        if not response:
            return False, False, b''
            
        valid_format, valid_crc = self._validate_response(response)
        return valid_format, valid_crc, response

    def detect(self) -> Dict[str, any]:
        results = {
            'recommended_protocol': None,
            'baud_rate': None,
            'serial_config': None,
            'valid_format_responses': 0,
            'valid_crc_responses': 0,
            'any_responses': 0,
            'sample_responses': {},
            'best_config': None
        }

        for baud in self.baud_rates:
            for config in self.serial_configs:
                if not self._open_serial(baud, *config):
                    continue
                    
                logging.info(f"Testing baud={baud}, config={config}")
                
                valid_format_count = 0
                valid_crc_count = 0
                any_responses = 0
                responses = {}
                
                for cmd in self.test_commands:
                    valid_format, valid_crc, response = self._test_protocol_command(cmd)
                    
                    if response:
                        any_responses += 1
                        try:
                            responses[cmd] = response.decode('ascii', errors='replace')
                        except:
                            responses[cmd] = str(response)
                            
                    if valid_format:
                        valid_format_count += 1
                    if valid_crc:
                        valid_crc_count += 1

                # Update results if this config is better
                if (valid_format_count > results['valid_format_responses'] or 
                    valid_crc_count > results['valid_crc_responses']):
                    results.update({
                        'baud_rate': baud,
                        'serial_config': config,
                        'valid_format_responses': valid_format_count,
                        'valid_crc_responses': valid_crc_count,
                        'any_responses': any_responses,
                        'sample_responses': responses,
                        'best_config': {
                            'baud': baud,
                            'bytesize': config[0],
                            'parity': config[1],
                            'stopbits': config[2]
                        }
                    })
                    
                    # If we got valid protocol responses, this is likely PI18SV
                    if valid_format_count > 0:
                        results['recommended_protocol'] = 'PI18SV'

                self.serial.close()

        return results

def main():
    print("🔍 Enhanced Protocol Detection Tool")
    print("==================================")
    
    detector = ProtocolDetector("/dev/ttyUSB0")
    results = detector.detect()
    
    print("\n📊 Detection Results:")
    print(f"Recommended Protocol: {results['recommended_protocol']}")
    print(f"Best Configuration:")
    print(f"  Baud Rate: {results['baud_rate']}")
    print(f"  Serial Config: Bytesize={results['best_config']['bytesize']}, "
          f"Parity={results['best_config']['parity']}, "
          f"Stopbits={results['best_config']['stopbits']}")
    print(f"\nResponse Statistics:")
    print(f"  Valid Format Responses: {results['valid_format_responses']}")
    print(f"  Valid CRC Responses: {results['valid_crc_responses']}")
    print(f"  Total Responses: {results['any_responses']}")
    
    print("\nSample Responses:")
    for cmd, response in results['sample_responses'].items():
        print(f"• {cmd}: {response}")

if __name__ == "__main__":
    main()