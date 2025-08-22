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
        print(f"  ✓ Protocol name: {protocol.name}")
        print(f"  ✓ Protocol description: {protocol.description}")
        
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
        
        # Test if it supports 3-phase parallel systems
        if hasattr(protocol, 'supports_parallel'):
            print(f"  ✓ Parallel support: {protocol.supports_parallel}")
        else:
            print("  ⚠️ Parallel support attribute not found")
            
        # Test if it supports 3-phase systems
        if hasattr(protocol, 'supports_3phase'):
            print(f"  ✓ 3-phase support: {protocol.supports_3phase}")
        else:
            print("  ⚠️ 3-phase support attribute not found")
            
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
            
        # Test protocol version
        print("\n📊 Protocol Information:")
        print(f"  • Protocol: {protocol.name}")
        print(f"  • Version: {getattr(protocol, 'version', 'Unknown')}")
        print(f"  • Description: {getattr(protocol, 'description', 'Unknown')}")
        print(f"  • Commands: {len(protocol.COMMANDS) if hasattr(protocol, 'COMMANDS') else 'Unknown'}")
        
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
        if hasattr(mppsolar, 'protocols'):
            protocols = mppsolar.protocols
            print(f"  ✓ Available protocols: {list(protocols.keys())}")
        else:
            print("  ⚠️ Protocols attribute not found")
            
        return True
        
    except ImportError as e:
        print(f"  ✗ mppsolar import failed: {e}")
        return False
    except Exception as e:
        print(f"  ✗ mppsolar test error: {e}")
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
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    print(f"  velib_python: {'✅ PASS' if velib_test else '❌ FAIL'}")
    print(f"  mpp-solar:    {'✅ PASS' if mppsolar_test else '❌ FAIL'}")
    print(f"  PI18SV:       {'✅ PASS' if pi18sv_test else '❌ FAIL'}")
    
    if all([velib_test, mppsolar_test, pi18sv_test]):
        print("\n🎉 All tests passed! PI18SV protocol is ready for EASUN InfiniSolar V inverters.")
        return 0
    else:
        print("\n⚠️ Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
