#!/usr/bin/env python3
"""
Debug script for dbus-mppsolar service
This script helps identify why the inverter is not showing up in Venus OS
"""

import sys
import os
import subprocess
import time
import json
import logging
from pathlib import Path

# Add our modules to the path
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'velib_python'))
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'mpp-solar'))

def setup_logging():
    """Setup basic logging for debugging"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('/tmp/dbus-debug.log')
        ]
    )

def check_system_requirements():
    """Check if all system requirements are met"""
    print("🔍 Checking system requirements...")
    
    # Check Python version
    print(f"Python version: {sys.version}")
    
    # Check for required modules
    modules_to_check = ['dbus', 'gi', 'gi.repository.GLib']
    for module in modules_to_check:
        try:
            if module == 'gi.repository.GLib':
                from gi.repository import GLib
                print(f"✓ {module} available")
            else:
                __import__(module)
                print(f"✓ {module} available")
        except ImportError as e:
            print(f"✗ {module} NOT available: {e}")
            return False
    
    # Check for our custom modules
    try:
        import mppsolar
        print(f"✓ mppsolar available (version: {getattr(mppsolar, '__version__', 'unknown')})")
    except ImportError as e:
        print(f"✗ mppsolar NOT available: {e}")
        return False
    
    try:
        from vedbus import VeDbusService
        print(f"✓ vedbus available")
    except ImportError as e:
        print(f"✗ vedbus NOT available: {e}")
        return False
    
    return True

def check_serial_devices():
    """Check for available serial devices"""
    print("\n🔌 Checking serial devices...")
    
    devices = []
    for device_pattern in ['/dev/ttyUSB*', '/dev/ttyACM*', '/dev/ttyS*']:
        try:
            result = subprocess.run(['ls', '-la'] + [device_pattern], 
                                  capture_output=True, text=True, shell=False)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line and '/dev/tty' in line:
                        device = line.split()[-1]
                        devices.append(device)
                        print(f"✓ Found device: {device}")
        except Exception as e:
            print(f"Error checking devices: {e}")
    
    if not devices:
        print("✗ No serial devices found!")
        print("Please connect your MPP Solar inverter via USB/Serial")
        return []
    
    return devices

def test_mppsolar_communication(device, protocol='PI18SV'):
    """Test direct communication with mppsolar"""
    print(f"\n📡 Testing mppsolar communication on {device} with {protocol}...")
    
    try:
        import mppsolar
        from mppsolar.helpers import get_device_class
        
        # Create device instance
        device_class = get_device_class("mppsolar")
        dev = device_class(port=device, protocol=protocol, baud=2400)
        
        # Test basic commands
        test_commands = ['QPI', 'QID', 'QVFW', 'QGS', 'QMOD']
        
        for cmd in test_commands:
            try:
                print(f"  Testing command: {cmd}")
                result = dev.run_command(command=cmd)
                if result:
                    print(f"    ✓ Response: {result}")
                else:
                    print(f"    ✗ No response")
            except Exception as e:
                print(f"    ✗ Error: {e}")
        
        return True
        
    except Exception as e:
        print(f"✗ Communication test failed: {e}")
        return False

def check_dbus_system():
    """Check DBus system availability"""
    print("\n🚌 Checking DBus system...")
    
    try:
        import dbus
        
        # Try to connect to system bus
        try:
            system_bus = dbus.SystemBus()
            print("✓ System DBus available")
        except Exception as e:
            print(f"✗ System DBus not available: {e}")
            return False
        
        # Try to connect to session bus
        try:
            session_bus = dbus.SessionBus()
            print("✓ Session DBus available")
        except Exception as e:
            print(f"✗ Session DBus not available: {e}")
        
        # Check for existing services
        try:
            service_names = system_bus.list_names()
            victron_services = [name for name in service_names if 'victronenergy' in name]
            print(f"✓ Found {len(victron_services)} Victron services:")
            for service in victron_services[:5]:  # Show first 5
                print(f"    - {service}")
            if len(victron_services) > 5:
                print(f"    ... and {len(victron_services) - 5} more")
        except Exception as e:
            print(f"✗ Error listing services: {e}")
        
        return True
        
    except ImportError as e:
        print(f"✗ DBus module not available: {e}")
        return False

def test_dbus_service_creation(device):
    """Test creating a simple DBus service"""
    print(f"\n🔧 Testing DBus service creation for {device}...")
    
    try:
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
        from vedbus import VeDbusService
        
        # Set up DBus main loop
        DBusGMainLoop(set_as_default=True)
        
        # Create a test service
        device_name = device.replace('/dev/', '')
        service_name = f'com.victronenergy.multi.test_{device_name}'
        
        print(f"Creating test service: {service_name}")
        
        # Try system bus first
        try:
            system_bus = dbus.SystemBus()
            test_service = VeDbusService(service_name, system_bus)
            
            # Add basic paths
            test_service.add_path('/DeviceInstance', 999)
            test_service.add_path('/ProductName', 'Test MPP Solar')
            test_service.add_path('/Connected', 1)
            
            print("✓ Test service created successfully on system bus")
            
            # Clean up
            del test_service
            return True
            
        except Exception as e:
            print(f"✗ System bus test failed: {e}")
            
            # Try session bus as fallback
            try:
                session_bus = dbus.SessionBus()
                test_service = VeDbusService(service_name, session_bus)
                
                test_service.add_path('/DeviceInstance', 999)
                test_service.add_path('/ProductName', 'Test MPP Solar')
                test_service.add_path('/Connected', 1)
                
                print("✓ Test service created successfully on session bus")
                del test_service
                return True
                
            except Exception as e2:
                print(f"✗ Session bus test also failed: {e2}")
                return False
        
    except Exception as e:
        print(f"✗ Service creation test failed: {e}")
        return False

def check_service_logs():
    """Check service logs for errors"""
    print("\n📋 Checking service logs...")
    
    log_locations = [
        '/var/log/dbus-mppsolar.log',
        '/var/log/mppsolar.ttyUSB0/current',
        '/var/log/serial-starter/current',
        '/tmp/dbus-debug.log'
    ]
    
    for log_path in log_locations:
        if os.path.exists(log_path):
            print(f"✓ Found log: {log_path}")
            try:
                with open(log_path, 'r') as f:
                    lines = f.readlines()
                    if lines:
                        print(f"  Last few lines:")
                        for line in lines[-5:]:
                            print(f"    {line.strip()}")
                    else:
                        print("  (empty)")
            except Exception as e:
                print(f"  Error reading log: {e}")
        else:
            print(f"✗ Log not found: {log_path}")

def run_service_test(device):
    """Run the actual service for a short test"""
    print(f"\n🧪 Running short service test on {device}...")
    
    try:
        # Import our service
        from dbus.mainloop.glib import DBusGMainLoop
        DBusGMainLoop(set_as_default=True)
        
        # Import after setting up DBus loop
        sys.path.insert(0, os.path.dirname(__file__))
        
        # Create a simple test version of the service
        import dbus
        from vedbus import VeDbusService
        from gi.repository import GLib
        
        device_name = device.replace('/dev/', '')
        service_name = f'com.victronenergy.multi.debug_{device_name}'
        
        print(f"Creating debug service: {service_name}")
        
        # Use session bus if system bus fails
        try:
            bus = dbus.SystemBus()
            print("Using system bus")
        except:
            bus = dbus.SessionBus()
            print("Using session bus")
        
        service = VeDbusService(service_name, bus)
        
        # Add mandatory paths
        service.add_path('/DeviceInstance', 0)
        service.add_path('/ProductName', 'Debug MPP Solar')
        service.add_path('/ProductId', 'DEBUG001')
        service.add_path('/FirmwareVersion', '1.0')
        service.add_path('/HardwareVersion', '1.0')
        service.add_path('/Connected', 1)
        service.add_path('/Mgmt/ProcessName', __file__)
        service.add_path('/Mgmt/ProcessVersion', 'Debug 1.0')
        service.add_path('/Mgmt/Connection', 'Debug interface')
        
        # Add some basic inverter paths
        service.add_path('/State', 9)  # Inverting
        service.add_path('/Mode', 3)   # On
        service.add_path('/Dc/0/Voltage', 24.5)
        service.add_path('/Dc/0/Current', -10.0)
        service.add_path('/Ac/Out/L1/V', 230.0)
        service.add_path('/Ac/Out/L1/P', 500)
        
        print("✓ Debug service registered successfully!")
        print("Service should now be visible in Venus OS interface")
        print("Let it run for 30 seconds to register...")
        
        # Run for 30 seconds
        def timeout_handler():
            print("Test completed - stopping service")
            mainloop.quit()
            return False
        
        mainloop = GLib.MainLoop()
        GLib.timeout_add_seconds(30, timeout_handler)
        
        try:
            mainloop.run()
            print("✓ Service test completed successfully")
            return True
        except KeyboardInterrupt:
            print("Service test interrupted by user")
            return True
        
    except Exception as e:
        print(f"✗ Service test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main debugging function"""
    print("🚀 Starting dbus-mppsolar debugging session")
    print("=" * 50)
    
    setup_logging()
    
    # Step 1: Check system requirements
    if not check_system_requirements():
        print("\n❌ System requirements not met. Please install missing dependencies.")
        return False
    
    # Step 2: Check serial devices
    devices = check_serial_devices()
    if not devices:
        return False
    
    # Step 3: Check DBus system
    if not check_dbus_system():
        print("\n❌ DBus system not available. This might be why the service isn't visible.")
        return False
    
    # Step 4: Test communication with first device
    test_device = devices[0]
    if not test_mppsolar_communication(test_device):
        print(f"\n⚠️  Communication test failed with {test_device}")
        print("This might indicate a hardware or protocol issue.")
    
    # Step 5: Test DBus service creation
    if not test_dbus_service_creation(test_device):
        print("\n❌ DBus service creation failed.")
        return False
    
    # Step 6: Check existing logs
    check_service_logs()
    
    # Step 7: Run a short service test
    print(f"\n🎯 Running final service test with {test_device}")
    print("This will create a debug service that should appear in Venus OS...")
    
    if run_service_test(test_device):
        print("\n✅ Debug session completed successfully!")
        print("\nNext steps:")
        print("1. Check if the debug service appeared in Venus OS interface")
        print("2. If it did, the issue is in the main service logic")
        print("3. If it didn't, the issue is with DBus configuration or Venus OS")
        return True
    else:
        print("\n❌ Debug session completed with errors.")
        return False

if __name__ == "__main__":
    main()
