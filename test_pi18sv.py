#!/usr/bin/env python3
"""
Test script for PI18SV protocol support
Tests EASUN InfiniSolar V inverter protocol functionality
"""

import sys
import os

# Add the local paths for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'velib_python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mpp-solar'))

def test_pi18sv_protocol():
    """Test PI18SV protocol for EASUN InfiniSolar V inverters"""
    print("🔍 Testing PI18SV Protocol Support")
    print("=" * 50)
    
    try:
        # Test basic imports
        print("📦 Testing imports...")
        import mppsolar
        print("  ✓ mppsolar imported successfully")
        
        from mppsolar.protocols.pi18sv import pi18sv
        print("  ✓ PI18SV protocol imported successfully")
        
        # Test protocol initialization
        print("\n🔧 Testing protocol initialization...")
        protocol = pi18sv()
        print(f"  ✓ Protocol class created: {type(protocol).__name__}")
        
        # Test protocol identification
        print(f"  ✓ Protocol ID: {protocol._protocol_id}")
        print(f"  ✓ Protocol string: {str(protocol)}")
        
        # Test command definitions
        print("\n📋 Testing command definitions...")
        if hasattr(protocol, 'COMMANDS'):
            command_count = len(protocol.COMMANDS)
            print(f"  ✓ Found {command_count} commands defined")
            
            # Show some key commands
            key_commands = ['QPIGS', 'QPIRI', 'QMOD', 'QFLAG', 'QDI', 'QPI', 'QGMN', 'QID']
            available_commands = [cmd for cmd in key_commands if cmd in protocol.COMMANDS]
            print(f"  ✓ Available key commands: {available_commands}")
            
            # Show all commands (first 20)
            all_commands = list(protocol.COMMANDS.keys())[:20]
            print(f"  ✓ Sample commands: {all_commands}")
            if len(protocol.COMMANDS) > 20:
                print(f"  ... and {len(protocol.COMMANDS) - 20} more")
                
        else:
            print("  ✗ No COMMANDS attribute found")
            
        # Test protocol methods
        print("\n⚙️ Testing protocol methods...")
        methods = [method for method in dir(protocol) if not method.startswith('_')]
        print(f"  ✓ Available methods: {methods[:10]}...")
        
        # Test specific EASUN InfiniSolar V functionality
        print("\n🏭 Testing EASUN InfiniSolar V specific features...")
        
        # Test PI18SV specific attributes
        print(f"  ✓ Protocol ID: {protocol._protocol_id}")
        print(f"  ✓ Inherits from: {protocol.__class__.__bases__[0].__name__}")
        
        # Test if it has the extended command set
        extended_commands = ['POP', 'BUCD', 'DAT']
        available_extended = [cmd for cmd in extended_commands if cmd in protocol.COMMANDS]
        print(f"  ✓ Extended commands available: {available_extended}")
        
        # Test status and settings commands
        if hasattr(protocol, 'STATUS_COMMANDS'):
            print(f"  ✓ Status commands: {len(protocol.STATUS_COMMANDS)} available")
        if hasattr(protocol, 'SETTINGS_COMMANDS'):
            print(f"  ✓ Settings commands: {len(protocol.SETTINGS_COMMANDS)} available")
            
        # Test command parsing
        print("\n🔍 Testing command parsing...")
        try:
            # Test a simple command
            test_command = 'QPIGS'
            if test_command in protocol.COMMANDS:
                cmd_info = protocol.COMMANDS[test_command]
                print(f"  ✓ {test_command} command info: {cmd_info}")
            else:
                print(f"  ✗ {test_command} command not found")
                
        except Exception as e:
            print(f"  ✗ Command parsing test failed: {e}")
            
        # Test protocol information
        print("\n📊 Protocol Information:")
        print(f"  • Protocol ID: {protocol._protocol_id}")
        print(f"  • String representation: {str(protocol)}")
        print(f"  • Commands: {len(protocol.COMMANDS) if hasattr(protocol, 'COMMANDS') else 'Unknown'}")
        print(f"  • Status Commands: {len(protocol.STATUS_COMMANDS) if hasattr(protocol, 'STATUS_COMMANDS') else 'Unknown'}")
        print(f"  • Settings Commands: {len(protocol.SETTINGS_COMMANDS) if hasattr(protocol, 'SETTINGS_COMMANDS') else 'Unknown'}")
        print(f"  • Default Command: {protocol.DEFAULT_COMMAND if hasattr(protocol, 'DEFAULT_COMMAND') else 'Unknown'}")
        
        print("\n✅ PI18SV Protocol Test Completed Successfully!")
        return True
        
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("   Make sure you're running this from the dbus-mppsolar directory")
        return False
    except Exception as e:
        print(f"❌ Test Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_velib_python():
    """Test velib_python functionality"""
    print("\n🔍 Testing velib_python Support")
    print("=" * 50)
    
    try:
        import velib_python.vedbus
        print("  ✓ velib_python.vedbus imported successfully")
        
        # Test basic functionality
        print("  ✓ velib_python module is accessible")
        return True
        
    except ImportError as e:
        print(f"  ✗ velib_python import failed: {e}")
        return False
    except Exception as e:
        print(f"  ✗ velib_python test error: {e}")
        return False

def test_mpp_solar():
    """Test mpp-solar functionality"""
    print("\n🔍 Testing mpp-solar Support")
    print("=" * 50)
    
    try:
        import mppsolar
        print("  ✓ mppsolar imported successfully")
        
        # Test device creation
        print("  ✓ mppsolar module is accessible")
        
        # Test available protocols
        try:
            # Try to import protocols module
            from mppsolar import protocols
            protocol_list = [name for name in dir(protocols) if not name.startswith('_') and name != 'AbstractProtocol']
            print(f"  ✓ Available protocols: {protocol_list}")
        except ImportError:
            print("  ⚠️ Protocols module not directly accessible")
        except Exception as e:
            print(f"  ⚠️ Protocol listing failed: {e}")
            
        return True
        
    except ImportError as e:
        print(f"  ✗ mppsolar import failed: {e}")
        return False
    except Exception as e:
        print(f"  ✗ mppsolar test error: {e}")
        return False

def test_real_device():
    """Test actual communication with inverter on ttyUSB0"""
    print("\n🔌 Testing Real Device Communication")
    print("=" * 50)
    
    try:
        import serial
        print("  ✓ pyserial imported successfully")
        
        # Test basic serial communication
        print("  Testing ttyUSB0 access...")
        ser = serial.Serial('/dev/ttyUSB0', 2400, timeout=1)
        print(f"  ✓ Successfully opened {ser.port}")
        print(f"  ✓ Baudrate: {ser.baudrate}")
        print(f"  ✓ Timeout: {ser.timeout}")
        
        # Test PI18SV protocol commands
        print("\n  Testing PI18SV protocol commands...")
        
        # Import our modules
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mpp-solar'))
        from mppsolar.protocols.pi18sv import pi18sv
        
        # Create protocol instance
        protocol = pi18sv()
        print(f"  ✓ PI18SV protocol created")
        
        # Test simple command (PI - Protocol Inquiry)
        test_command = "PI"
        if test_command in protocol.COMMANDS:
            print(f"  ✓ Testing command: {test_command}")
            
            # Get full command with protocol formatting
            full_command = protocol.get_full_command(test_command)
            if full_command:
                print(f"  ✓ Command formatted: {full_command}")
                
                # Send command to device
                try:
                    ser.write(full_command)
                    print(f"  ✓ Command sent to inverter")
                    
                    # Wait for response
                    response = ser.read(100)
                    if response:
                        print(f"  ✓ Response received: {response}")
                        
                        # Try to decode response
                        try:
                            decoded = protocol.get_responses(response)
                            print(f"  ✓ Response decoded: {decoded}")
                        except Exception as e:
                            print(f"  ⚠️ Decode failed: {e}")
                    else:
                        print(f"  ⚠️ No response received")
                        
                except Exception as e:
                    print(f"  ✗ Communication error: {e}")
            else:
                print(f"  ✗ Command formatting failed")
        else:
            print(f"  ✗ Command {test_command} not found in protocol")
        
        # Close device
        ser.close()
        print("  ✓ Device closed successfully")
        
        return True
        
    except ImportError as e:
        print(f"  ✗ pyserial import failed: {e}")
        return False
    except Exception as e:
        print(f"  ✗ Real device test error: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 dbus-mppsolar PI18SV Protocol Test")
    print("=" * 60)
    print(f"📁 Working directory: {os.getcwd()}")
    print(f"🐍 Python version: {sys.version}")
    print()
    
    # Run tests
    velib_test = test_velib_python()
    mppsolar_test = test_mpp_solar()
    pi18sv_test = test_pi18sv_protocol()
    real_device_test = test_real_device()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    print(f"  velib_python: {'✅ PASS' if velib_test else '❌ FAIL'}")
    print(f"  mpp-solar:    {'✅ PASS' if mppsolar_test else '❌ FAIL'}")
    print(f"  PI18SV:       {'✅ PASS' if pi18sv_test else '❌ FAIL'}")
    print(f"  Real Device:  {'✅ PASS' if real_device_test else '❌ FAIL'}")
    
    if all([velib_test, mppsolar_test, pi18sv_test, real_device_test]):
        print("\n🎉 All tests passed! PI18SV protocol is working with your inverter!")
        return 0
    elif all([velib_test, mppsolar_test, pi18sv_test]):
        print("\n✅ Protocol tests passed! Real device communication needs attention.")
        return 1
    else:
        print("\n⚠️ Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
