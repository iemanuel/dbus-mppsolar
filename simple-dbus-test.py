#!/usr/bin/env python3
"""
Simple DBus service test to verify Venus OS integration
This creates a minimal service that should appear in Venus OS
"""

import sys
import os
import time
import argparse
import logging

# Add our modules to the path
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'velib_python'))

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

def create_simple_service(tty_device):
    """Create a simple DBus service for testing"""
    from gi.repository import GLib
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from vedbus import VeDbusService
    
    # Set up DBus main loop
    DBusGMainLoop(set_as_default=True)
    
    device_name = tty_device.replace('/dev/', '')
    service_name = f'com.victronenergy.multi.{device_name}'
    
    logging.info(f"Creating service: {service_name}")
    
    try:
        # Try system bus (preferred for Venus OS)
        bus = dbus.SystemBus()
        logging.info("Using system DBus")
    except Exception as e:
        logging.warning(f"System bus failed: {e}, trying session bus")
        try:
            bus = dbus.SessionBus()
            logging.info("Using session DBus")
        except Exception as e2:
            logging.error(f"Both DBus connections failed: {e2}")
            return False
    
    try:
        # Create the service
        service = VeDbusService(service_name, bus)
        
        # Add mandatory paths for Venus OS recognition
        service.add_path('/DeviceInstance', 0)
        service.add_path('/ProductId', 0xB012)  # Use a valid Victron product ID
        service.add_path('/ProductName', 'MPP Solar Inverter')
        service.add_path('/FirmwareVersion', '1.0.0')
        service.add_path('/HardwareVersion', '1.0')
        service.add_path('/Connected', 1)
        
        # Management paths
        service.add_path('/Mgmt/ProcessName', __file__)
        service.add_path('/Mgmt/ProcessVersion', 'Test 1.0')
        service.add_path('/Mgmt/Connection', 'USB Serial')
        
        # Essential inverter paths
        service.add_path('/State', 9)  # 9 = Inverting
        service.add_path('/Mode', 3)   # 3 = On
        service.add_path('/Dc/0/Voltage', 24.5)
        service.add_path('/Dc/0/Current', -10.0)
        service.add_path('/Ac/Out/L1/V', 230.0)
        service.add_path('/Ac/Out/L1/I', 2.2)
        service.add_path('/Ac/Out/L1/P', 500)
        service.add_path('/Ac/Out/L1/F', 50.0)
        
        # Input paths
        service.add_path('/Ac/In/1/L1/V', 235.0)
        service.add_path('/Ac/In/1/L1/F', 50.1)
        service.add_path('/Ac/In/1/L1/P', 0)
        
        # Additional required paths
        service.add_path('/Ac/NumberOfPhases', 1)
        service.add_path('/Ac/ActiveIn/ActiveInput', 0)
        
        logging.info("✓ Service created and registered successfully!")
        logging.info(f"Service {service_name} should now be visible in Venus OS")
        
        # Update data periodically
        def update_data():
            try:
                import random
                # Simulate changing values
                service['/Dc/0/Voltage'] = 24.0 + random.uniform(-0.5, 0.5)
                service['/Ac/Out/L1/P'] = 500 + random.randint(-50, 50)
                service['/Dc/0/Current'] = -10.0 + random.uniform(-2.0, 2.0)
                return True  # Continue updating
            except Exception as e:
                logging.error(f"Update error: {e}")
                return False
        
        # Set up periodic updates
        GLib.timeout_add_seconds(5, update_data)
        
        # Run the main loop
        logging.info("Starting main loop... (Press Ctrl+C to stop)")
        mainloop = GLib.MainLoop()
        mainloop.run()
        
        return True
        
    except Exception as e:
        logging.error(f"Service creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(description="Simple DBus service test")
    parser.add_argument("--serial", "-s", required=True, 
                       help="Serial device path (e.g., /dev/ttyUSB0)")
    
    args = parser.parse_args()
    
    setup_logging()
    
    logging.info("🧪 Starting simple DBus service test")
    logging.info(f"Device: {args.serial}")
    
    success = create_simple_service(args.serial)
    
    if success:
        logging.info("✅ Test completed successfully")
    else:
        logging.error("❌ Test failed")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
