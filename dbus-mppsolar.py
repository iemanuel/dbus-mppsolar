#!/usr/bin/env python3

"""
Handle automatic connection with MPP Solar inverter compatible device (VEVOR)
This will output 2 dbus services, one for Inverter data another one for control
via VRM of the features.
"""
VERSION = 'v0.2' 

from gi.repository import GLib
import platform
import argparse
import logging
import sys
import os
import subprocess as sp
import json
import datetime
import time
import dbus
import dbus.service

# Configure logging with timestamps and more detail

def setup_logging(log_level=logging.INFO, log_file='/var/log/dbus-mppsolar.log', max_size=1024*1024, backup_count=5):
    """Configure logging with detailed formatting and rotation.
    
    Args:
        log_level: Logging level (default: INFO)
        log_file: Path to log file (default: /var/log/dbus-mppsolar.log)
        max_size: Maximum size of log file before rotation in bytes (default: 1MB)
        backup_count: Number of backup files to keep (default: 5)
    """
    log_format = '%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Set up rotating file handler for persistent logs
    try:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_size,
            backupCount=backup_count
        )
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        
        # Also log to console with less verbose format
        console_handler = logging.StreamHandler()
        console_format = '%(levelname)s: %(message)s'
        console_handler.setFormatter(logging.Formatter(console_format))
        
        # Configure root logger
        root_logger = logging.getLogger()
        # Clear any existing handlers to prevent duplicates
        root_logger.handlers.clear()
        root_logger.setLevel(log_level)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        logging.info("Logging initialized - dbus-mppsolar %s (level: %s, file: %s)", 
                    VERSION, logging.getLevelName(log_level), log_file)
    except Exception as e:
        # Fallback to basic logging if file logging fails
        logging.basicConfig(
            level=log_level,
            format=console_format
        )
        logging.warning("Failed to set up file logging: %s", str(e))

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'velib_python'))
from vedbus import VeDbusService, VeDbusItemExport, VeDbusItemImport

# Configuration constants
INVERTER_OFF_ASSUME_BYPASS = True  # When inverter is off, assume AC input is directly connected to output
GUESS_AC_CHARGING = True  # Estimate AC charging current when not directly available
USE_SYSTEM_MPPSOLAR = False  # If True, use system-installed mppsolar package; if False, use local version
if USE_SYSTEM_MPPSOLAR:
    try:
        import mppsolar
    except:
        USE_SYSTEM_MPPSOLAR = False
if not USE_SYSTEM_MPPSOLAR:
    sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'mpp-solar'))
    import mppsolar

# Inverter commands to read from the serial
def runInverterCommands(commands, protocol="PI30", retries=3, retry_delay=0.5):
    """Run commands with error handling, retries and detailed logging.
    
    Args:
        commands: List of commands to execute
        protocol: Protocol to use (default: PI30)
        retries: Number of retries for failed commands (default: 2)
        retry_delay: Base delay between retries in seconds (default: 0.5)
    
    Returns:
        List of command results, or None if all commands failed
    """
    global args
    global mainloop
    
    def log_command_result(cmd, result, attempt=None):
        """Log command execution details with consistent formatting."""
        attempt_str = f" (attempt {attempt}/{retries})" if attempt else ""
        if isinstance(result, dict):
            if "error" in result:
                logging.error(f"Command '{cmd}' failed{attempt_str}: {result['error']}")
                if "raw_response" in result:
                    logging.debug(f"Raw response: {result['raw_response']}")
            else:
                logging.debug(f"Command '{cmd}' succeeded{attempt_str}: {result}")
        else:
            logging.debug(f"Command '{cmd}' returned{attempt_str}: {result}")

    def execute_command(dev, cmd, attempt_num=None):
        """Execute single command with consistent error handling.
        
        Args:
            dev: Device instance to use
            cmd: Command to execute
            attempt_num: Current attempt number for retry logging
        
        Returns:
            Parsed command result or error dict
        """
        attempt_str = f" (attempt {attempt_num})" if attempt_num else ""
        start_time = datetime.datetime.now()
        result = None
        
        try:
            if USE_SYSTEM_MPPSOLAR:
                cmd_str = f"mpp-solar -b {args.baudrate} -P {protocol} -p {args.serial} -o json -c {cmd}"
                logging.debug(f"Executing{attempt_str}: {cmd_str}")
                result = sp.getoutput(cmd_str).split('\n')[0]
                return json.loads(result)
            
            # Try command with current protocol
            logging.debug(f"Executing command {cmd} with protocol {protocol}")
            
            # Get a fresh device instance if needed
            if dev is None:
                dev = mppsolar.helpers.get_device_class("mppsolar")(
                    port=args.serial,
                    protocol=protocol,
                    baud=args.baudrate
                )
            
            # Execute command with timing - some inverters need longer delays
            time.sleep(0.3)  # Increased delay between commands (was 0.2)
            result = dev.run_command(command=cmd)
            
            if not result:
                return {"error": "No response", "raw_response": ""}
            
            # Check for empty response (but allow it if command structure is valid)
            if isinstance(result, dict) and result.get('raw_response') == ['', '']:
                # This is actually OK - the inverter responded but has no data to report
                # This is common in certain inverter states
                logging.debug(f"Command '{cmd}' returned empty data (inverter may be in standby or no data available)")
                return result  # Return the structured response even if data is empty
            
            if isinstance(result, dict):
                return result
            
            # Parse non-dict response
            parsed = mppsolar.outputs.to_json(result, False, None, None)
            if parsed and not 'error' in parsed:
                return parsed
            
            return {"error": "Invalid response", "raw_response": str(result)}
            
        except Exception as e:
            error_msg = f"Command execution failed: {str(e)}"
            logging.debug(error_msg)
            return {"error": error_msg, "raw_response": str(result) if result else ""}
        finally:
            duration = (datetime.datetime.now() - start_time).total_seconds()
            logging.debug(f"Command completed in {duration:.3f}s")

    try:
        # Initialize device once for all commands
        dev = None
        if not USE_SYSTEM_MPPSOLAR:
            logging.debug(f"Initializing device with protocol={protocol}, port={args.serial}, baud={args.baudrate}")
            dev = mppsolar.helpers.get_device_class("mppsolar")(
                port=args.serial, 
                protocol=protocol, 
                baud=args.baudrate
            )

        results = []
        for cmd in commands:
            result = None
            for attempt in range(retries):
                try:
                    result = execute_command(dev, cmd, attempt+1)
                    
                    # Check for success
                    if not isinstance(result, dict) or "error" not in result:
                        break  # Success
                        
                    # Handle retry
                    if attempt < retries - 1:
                        delay = retry_delay * (2 ** attempt)  # Exponential backoff
                        logging.info(f"Retrying command '{cmd}' after failure in {delay:.1f}s")
                        time.sleep(delay)
                        
                except Exception as e:
                    error_msg = f"Attempt {attempt+1} failed for '{cmd}': {str(e)}"
                    if attempt < retries - 1:
                        logging.warning(error_msg)
                        time.sleep(retry_delay * (2 ** attempt))
                    else:
                        logging.error(error_msg)
                        result = {"error": str(e), "raw_response": ""}

            log_command_result(cmd, result)
            results.append(result)

            # Add delay between different commands - critical for inverter stability
            if len(commands) > 1 and cmd != commands[-1]:
                time.sleep(0.25)  # Increased delay between commands (was 0.1)

        return results

    except Exception as e:
        error_msg = f"Failed to execute command batch: {str(e)}"
        logging.error(error_msg, exc_info=True)
        return [{"error": error_msg, "raw_response": ""} for _ in commands]

def setOutputSource(source):
    #POP<NN>: Setting device output source priority
    #    NN = 00 for utility first, 01 for solar first, 02 for SBU priority
    return runInverterCommands(['POP{:02d}'.format(source)])

def setChargerPriority(priority):
    #PCP<NN>: Setting device charger priority
    #  For KS: 00 for utility first, 01 for solar first, 02 for solar and utility, 03 for only solar charging
    #  For MKS: 00 for utility first, 01 for solar first, 03 for only solar charging
    return runInverterCommands(['PCP{:02d}'.format(priority)])

def setMaxChargingCurrent(current):
    #MNCHGC<mnnn><cr>: Setting max charging current (More than 100A)
    #  Setting value can be gain by QMCHGCR command.
    #  nnn is max charging current, m is parallel number.
    return runInverterCommands(['MNCHGC0{:04d}'.format(current)])

def setMaxUtilityChargingCurrent(current):
    #MUCHGC<nnn><cr>: Setting utility max charging current
    #  Setting value can be gain by QMCHGCR command.
    #  nnn is max charging current, m is parallel number.
    return runInverterCommands(['MUCHGC{:03d}'.format(current)])

def isNaN(num):
    return num != num


# Allow to have multiple DBUS connections
class SystemBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM) 
class SessionBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)
def dbusconnection():
    return SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else SystemBus()

# Our MPP solar service that connects to 2 dbus services (multi & vebus)
class DbusMppSolarService(object):
    """DBus service for MPP Solar inverters.
    
    This service provides two DBus interfaces:
    1. com.victronenergy.multi.mppsolar.<tty> - Main inverter interface
    2. com.victronenergy.acsystem.mppsolar.<tty> - AC system interface
    
    The service implements the standard paths as specified in the Victron DBus API:
    https://github.com/victronenergy/venus/wiki/dbus-api
    
    Paths are organized by category:
    - /Ac/* - AC-related values (voltage, current, power)
    - /Dc/* - DC-related values (battery voltage, current)
    - /Pv/* - Solar-related values (PV voltage, power)
    - /Settings/* - Configurable settings
    - /State - Overall inverter state
    - /Alarms/* - Various alarm conditions
    """
    
    def __init__(self, tty, deviceinstance, productname='MPPSolar', connection='MPPSolar interface'):
        """Initialize the DBus service.
        
        Args:
            tty: TTY device name (without /dev/)
            deviceinstance: Unique device instance number
            productname: Product name for identification
            connection: Connection description
        """
        self._tty = tty
        self._queued_updates = []
        self._start_time = time.time()  # Service start time
        self._last_update = 0  # Last successful update timestamp
        self._update_interval = 2  # Update interval in seconds

        # Initialize protocol and data - InfiniSolar V uses PI18
        self._invProtocol = "PI18"
        self._invData = []
        protocol_detected = self._detect_protocol()
        
        if not protocol_detected:
            logging.warning("Protocol detection failed, continuing with defaults")
        
        # Create a listener to the DC system power, we need it to give some values
        self._systemDcPower = None        
        self._dcLast = 0
        self._chargeLast = 0
        
        # Create the services - use standard Venus OS naming convention
        try:
            self._dbusmulti = VeDbusService(f'com.victronenergy.multi.{tty}', dbusconnection())
            self._dbusvebus = VeDbusService(f'com.victronenergy.acsystem.{tty}', dbusconnection())
            logging.info(f"✓ DBus services created: multi.{tty} and acsystem.{tty}")
        except Exception as e:
            logging.error(f"✗ Failed to create DBus services: {e}")
            raise

        # Set up default paths with proper product identification
        self.setupDefaultPaths(self._dbusmulti, connection, deviceinstance, "MPP Solar Inverter")
        self.setupDefaultPaths(self._dbusvebus, connection, deviceinstance, "MPP Solar AC System")

        # Create paths for 'multi' - essential inverter interface
        self._setup_multi_paths()
        
        # Create paths for 'vebus' - AC system interface  
        self._setup_vebus_paths()

        # Services are automatically registered when created (removed register=False)
        logging.info("✓ DBus services registered and ready")

        GLib.timeout_add(10000 if USE_SYSTEM_MPPSOLAR else 2000, self._update)

    def _detect_protocol(self):
        """Detect and verify PI18SV protocol support with retries."""
        max_retries = 3
        base_delay = 1.0  # Base delay in seconds

        for attempt in range(max_retries):
            try:
                # Try PI18 protocol commands first (for InfiniSolar V)
                logging.info(f"Attempting PI18 protocol detection (attempt {attempt + 1}/{max_retries})")
                # Try a mix of identification and status commands
                response = runInverterCommands(['PIRI'], "PI18")
                
                if response and not any('error' in r for r in response):
                    # Protocol is working if we get structured responses, even if data is empty
                    # This is common with some inverters that respond but don't populate data
                    successful_commands = 0
                    for r in response:
                        if isinstance(r, dict) and '_command' in r:
                            successful_commands += 1
                    
                    if successful_commands >= 1:  # At least 1 command succeeded
                        logging.info("PI18 protocol confirmed (commands successful)")
                        self._invData = response
                        self._invProtocol = 'PI18'
                        return True
                    else:
                        logging.warning("PI18 partial success, continuing detection")
                        continue

                # For PI18, skip the QPI test as it's not available in this protocol
                logging.debug("PI18 direct test failed, trying fallback data")
                # Set minimal data for PI18
                self._invData = [
                    {"serial_number": "INFINISOLAR_V"},
                    {"main_cpu_firmware_version": "1.0.0"}
                ]
                self._invProtocol = 'PI18'

                # Wait before retry with exponential backoff
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logging.info(f"Protocol detection failed, retrying in {delay:.1f}s")
                    time.sleep(delay)
                    
                    # Additional stabilization delay for serial communication
                    time.sleep(0.2)
                    
            except Exception as e:
                logging.warning(f"Protocol detection attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(base_delay * (2 ** attempt))

        # If all attempts fail, set defaults and continue
        logging.warning("Protocol detection failed after all retries, using defaults")
        self._invProtocol = "PI18"
        self._invData = [
            {"serial_number": "UNKNOWN"},
            {"main_cpu_firmware_version": "1.0.0"}
        ]
        
        logging.info(f"Connected to inverter on {self._tty} ({self._invProtocol}), setting up dbus")
        return False
    
    def _setup_multi_paths(self):
        """Set up DBus paths for the multi/inverter service."""
        # Create paths for 'multi'
        self._dbusmulti.add_path('/Ac/In/1/L1/V', 0)
        self._dbusmulti.add_path('/Ac/In/1/L1/I', 0)
        self._dbusmulti.add_path('/Ac/In/1/L1/P', 0)
        self._dbusmulti.add_path('/Ac/In/1/L1/F', 0)
        #self._dbusmulti.add_path('/Ac/In/2/L1/V', 0)
        #self._dbusmulti.add_path('/Ac/In/2/L1/I', 0)
        #self._dbusmulti.add_path('/Ac/In/2/L1/P', 0)
        #self._dbusmulti.add_path('/Ac/In/2/L1/F', 0)
        self._dbusmulti.add_path('/Ac/Out/L1/V', 0)
        self._dbusmulti.add_path('/Ac/Out/L1/I', 0)
        self._dbusmulti.add_path('/Ac/Out/L1/P', 0)
        self._dbusmulti.add_path('/Ac/Out/L1/S', 0)
        self._dbusmulti.add_path('/Ac/Out/L1/F', 0)
        self._dbusmulti.add_path('/Ac/In/1/Type', 1) #0=Unused;1=Grid;2=Genset;3=Shore
        #self._dbusmulti.add_path('/Ac/In/2/Type', 1) #0=Unused;1=Grid;2=Genset;3=Shore
        self._dbusmulti.add_path('/Ac/In/1/CurrentLimit', 20)
        #self._dbusmulti.add_path('/Ac/In/2/CurrentLimit', 20)
        self._dbusmulti.add_path('/Ac/NumberOfPhases', 1)
        self._dbusmulti.add_path('/Ac/ActiveIn/ActiveInput', 0)
        self._dbusmulti.add_path('/Ac/ActiveIn/Type', 1)
        self._dbusmulti.add_path('/Dc/0/Voltage', 0)
        self._dbusmulti.add_path('/Dc/0/Current', 0)
        #self._dbusmulti.add_path('/Dc/0/Temperature', 10)
        self._dbusmulti.add_path('/Soc', None)
        self._dbusmulti.add_path('/State', 9) #0=Off;1=Low Power;2=Fault;3=Bulk;4=Absorption;5=Float;6=Storage;7=Equalize;8=Passthru;9=Inverting;10=Power assist;11=Power supply;252=External control
        self._dbusmulti.add_path('/Mode', 0, writeable=True, onchangecallback=self._change) #1=Charger Only;2=Inverter Only;3=On;4=Off
        self._dbusmulti.add_path('/Alarms/HighTemperature', 0)
        self._dbusmulti.add_path('/Alarms/HighVoltage', 0)
        self._dbusmulti.add_path('/Alarms/HighVoltageAcOut', 0)
        self._dbusmulti.add_path('/Alarms/LowTemperature', 0)
        self._dbusmulti.add_path('/Alarms/LowVoltage', 0)
        self._dbusmulti.add_path('/Alarms/LowVoltageAcOut', 0)
        self._dbusmulti.add_path('/Alarms/Overload', 0)
        self._dbusmulti.add_path('/Alarms/Ripple', 0)
        self._dbusmulti.add_path('/Yield/Power', 0)
        self._dbusmulti.add_path('/Yield/User', 0)
        self._dbusmulti.add_path('/Relay/0/State', None)
        self._dbusmulti.add_path('/MppOperationMode', 0) #0=Off;1=Voltage/current limited;2=MPPT active;255=Not available
        self._dbusmulti.add_path('/Pv/V', 0)
        self._dbusmulti.add_path('/ErrorCode', 0)
        self._dbusmulti.add_path('/Energy/AcIn1ToAcOut', 0)
        self._dbusmulti.add_path('/Energy/AcIn1ToInverter', 0)
        #self._dbusmulti.add_path('/Energy/AcIn2ToAcOut', 0)
        #self._dbusmulti.add_path('/Energy/AcIn2ToInverter', 0)
        self._dbusmulti.add_path('/Energy/AcOutToAcIn1', 0)
        #self._dbusmulti.add_path('/Energy/AcOutToAcIn2', 0)
        self._dbusmulti.add_path('/Energy/InverterToAcIn1', 0)
        #self._dbusmulti.add_path('/Energy/InverterToAcIn2', 0)
        self._dbusmulti.add_path('/Energy/InverterToAcOut', 0)
        self._dbusmulti.add_path('/Energy/OutToInverter', 0)
        self._dbusmulti.add_path('/Energy/SolarToAcIn1', 0)
        #self._dbusmulti.add_path('/Energy/SolarToAcIn2', 0)
        self._dbusmulti.add_path('/Energy/SolarToAcOut', 0)
        self._dbusmulti.add_path('/Energy/SolarToBattery', 0)
        self._dbusmulti.add_path('/History/Daily/0/Yield', 0)
        self._dbusmulti.add_path('/History/Daily/0/MaxPower', 0)
        self._dbusmulti.add_path('/History/Daily/0/Pv/0/Yield', 0)
        self._dbusmulti.add_path('/History/Daily/0/Pv/0/MaxPower', 0)
        self._dbusmulti.add_path('/Pv/0/V', 0)
        self._dbusmulti.add_path('/Pv/0/P', 0)
        self._dbusmulti.add_path('/Temperature', 123)
        self._dbusmulti.add_path('/Alarms/LowSoc', 0)
        self._dbusmulti.add_path('/Alarms/HighDcVoltage', 0)
        self._dbusmulti.add_path('/Alarms/LowDcVoltage', 0)
        self._dbusmulti.add_path('/Alarms/LineFail', 0)
        self._dbusmulti.add_path('/Alarms/GridLost', 0)
        self._dbusmulti.add_path('/Alarms/Connection', 0)
    
    def _setup_vebus_paths(self):
        """Set up DBus paths for the VE.Bus/AC system service."""
        # Create paths for 'vebus'
        self._dbusvebus.add_path('/Ac/ActiveIn/L1/F', 0)
        self._dbusvebus.add_path('/Ac/ActiveIn/L1/I', 0)
        self._dbusvebus.add_path('/Ac/ActiveIn/L1/V', 0)
        self._dbusvebus.add_path('/Ac/ActiveIn/L1/P', 0)
        self._dbusvebus.add_path('/Ac/ActiveIn/L1/S', 0)
        self._dbusvebus.add_path('/Ac/ActiveIn/P', 0)
        self._dbusvebus.add_path('/Ac/ActiveIn/S', 0)
        self._dbusvebus.add_path('/Ac/ActiveIn/ActiveInput', 0)
        self._dbusvebus.add_path('/Ac/Out/L1/V', 0)
        self._dbusvebus.add_path('/Ac/Out/L1/I', 0)
        self._dbusvebus.add_path('/Ac/Out/L1/P', 0)
        self._dbusvebus.add_path('/Ac/Out/L1/S', 0)
        self._dbusvebus.add_path('/Ac/Out/L1/F', 0)
        self._dbusvebus.add_path('/Ac/NumberOfPhases', 1)
        self._dbusvebus.add_path('/Dc/0/Voltage', 0)
        self._dbusvebus.add_path('/Dc/0/Current', 0)
        self._dbusvebus.add_path('/Ac/In/1/CurrentLimit', 20, writeable=True, onchangecallback=self._change)
        self._dbusvebus.add_path('/Ac/In/1/CurrentLimitIsAdjustable', 1)
        self._dbusvebus.add_path('/Settings/SystemSetup/AcInput1', 1)
        self._dbusvebus.add_path('/Settings/SystemSetup/AcInput2', 0)
        self._dbusvebus.add_path('/Ac/In/1/Type', 1) #0=Unused;1=Grid;2=Genset;3=Shore
        self._dbusvebus.add_path('/Ac/In/2/Type', 0) #0=Unused;1=Grid;2=Genset;3=Shore
        self._dbusvebus.add_path('/Ac/State/IgnoreAcIn1', 0)
        self._dbusvebus.add_path('/Ac/State/IgnoreAcIn2', 1)
        self._dbusvebus.add_path('/Mode', 0, writeable=True, onchangecallback=self._change)
        self._dbusvebus.add_path('/ModeIsAdjustable', 1)
        self._dbusvebus.add_path('/State', 0)
        self._dbusvebus.add_path('/Ac/In/1/L1/V', 0, writeable=False, onchangecallback=self._change)
    
    def setupDefaultPaths(self, service, connection, deviceinstance, productname):
        # self._dbusmulti.add_mandatory_paths(__file__, 'version f{VERSION}, and running on Python ' + platform.python_version(), connection,
		# 	deviceinstance, self._invData[0].get('serial_number', 0), productname, self._invData[1].get('main_cpu_firmware_version', 0), 0, 1)

        # Create the management objects, as specified in the ccgx dbus-api document
        service.add_path('/Mgmt/ProcessName', __file__)
        service.add_path('/Mgmt/ProcessVersion', f'version {VERSION}, and running on Python {platform.python_version()}')
        service.add_path('/Mgmt/Connection', connection)
        
        # Add device type identification for Venus OS
        service.add_path('/DeviceType', 1)  # 1 = Multi/Quattro, 2 = Inverter, 3 = Charger

        # Create the mandatory objects
        service.add_path('/DeviceInstance', deviceinstance)
        service.add_path('/ProductId', 0xB012)  # Use proper Victron product ID for multi/inverter
        service.add_path('/ProductName', productname)
        service.add_path('/FirmwareVersion', self._invData[1].get('main_cpu_firmware_version', '1.0.0'))
        service.add_path('/HardwareVersion', '1.0')
        service.add_path('/Connected', 1)

        # Create paths for service status monitoring
        service.add_path('/Status/LastUpdate', None)  # Timestamp of last successful update
        service.add_path('/Status/UpdateCount', 0)  # Number of successful updates
        service.add_path('/Status/ErrorCount', 0)  # Number of update errors
        service.add_path('/Status/LastError', '')  # Last error message
        service.add_path('/Status/Uptime', 0)  # Service uptime in seconds
        
        # Create paths for modifying the system manually
        service.add_path('/Settings/Reset', None, writeable=True, onchangecallback=self._change)
        service.add_path('/Settings/Charger', None, writeable=True, onchangecallback=self._change)
        service.add_path('/Settings/Output', None, writeable=True, onchangecallback=self._change)
        service.add_path('/Settings/UpdateInterval', self._update_interval, writeable=True, onchangecallback=self._change)

    def _updateInternal(self):
        # Store in the paths all values that were updated from _handleChangedValue
        with self._dbusmulti as m:# self._dbusvebus as v:
            for path, value, in self._queued_updates:
                m[path] = value
                # v[path] = value
            self._queued_updates = []

    def _connectToDc(self):
        if self._systemDcPower is None:
            try:
                self._systemDcPower = VeDbusItemImport(dbusconnection(), 'com.victronenergy.system', '/Dc/System/Power')
                logging.warning("Connected to DC at {}".format(datetime.datetime.now().time()))
            except:
                pass

    def _update(self):
        """Update service data from inverter.
        
        This method is called periodically to update all DBus paths with fresh data.
        It handles protocol selection, error tracking, and status monitoring.
        """
        global mainloop
        
        # Check if it's time to update
        now = time.time()
        if now - self._last_update < self._update_interval:
            return True
            
        self._connectToDc()
        logging.info("Updating at {}".format(datetime.datetime.now().time()))
        
        try:
            # Update service status
            with self._dbusmulti as m:
                m['/Status/LastUpdate'] = int(now)
                m['/Status/Uptime'] = int(now - self._start_time)
            
            # Select appropriate protocol handler
            if self._invProtocol == 'PI30' or self._invProtocol == 'PI30MAX':
                success = self._update_PI30()
            elif self._invProtocol == 'PI17':
                success = self._update_PI17()
            elif self._invProtocol == 'PI18':
                success = self._update_PI18()
            elif self._invProtocol == 'PI18SV':
                success = self._update_PI18SV()
            else:
                logging.warning(f"Unknown protocol {self._invProtocol}, defaulting to PI18")
                self._invProtocol = 'PI18'
                success = self._update_PI18()
            
            # Update status based on result
            with self._dbusmulti as m:
                if success:
                    self._last_update = now
                    m['/Status/UpdateCount'] = m['/Status/UpdateCount'] + 1
                    m['/Status/LastError'] = ''
                else:
                    m['/Status/ErrorCount'] = m['/Status/ErrorCount'] + 1
                    m['/Status/LastError'] = 'Update failed'
            
            return success
            
        except Exception as e:
            error_msg = str(e)
            logging.exception('Error in update loop')
            
            # Update error status
            with self._dbusmulti as m:
                m['/Status/ErrorCount'] = m['/Status/ErrorCount'] + 1
                m['/Status/LastError'] = error_msg
            
            mainloop.quit()
            return False

    def _change(self, path, value):
        global mainloop
        logging.warning("updated %s to %s" % (path, value))
        if path == '/Settings/Reset':
            logging.info("Restarting!")
            mainloop.quit()
            exit
        try: 
            if self._invProtocol == 'PI30' or self._invProtocol == 'PI30MAX':
                return self._change_PI30(path, value)
            elif self._invProtocol == 'PI17':
                return self._change_PI17(path, value)
            elif self._invProtocol == 'PI18':
                return self._change_PI18(path, value)
            elif self._invProtocol == 'PI18SV':
                return self._change_PI18SV(path, value)
            else:
                logging.warning(f"Unknown protocol {self._invProtocol}, defaulting to PI18")
                self._invProtocol = 'PI18'
                return self._change_PI18(path, value)
        except:
            logging.exception('Error in change loop', exc_info=True)
            mainloop.quit()
            return False

    def _update_PI30(self):
        raw = runInverterCommands(['QPIGS','QMOD','QPIWS']) 
        data, mode, warnings = raw
        dcSystem = None
        if  self._systemDcPower != None:
            dcSystem = self._systemDcPower.get_value()
        logging.debug(dcSystem)
        logging.debug(raw)
        with self._dbusmulti as m, self._dbusvebus as v:
            # 1=Charger Only;2=Inverter Only;3=On;4=Off -> Control from outside
            if 'error' in data and 'short' in data['error']:
                m['/State'] = 0
                m['/Alarms/Connection'] = 2
            
            # 0=Off;1=Low Power;2=Fault;3=Bulk;4=Absorption;5=Float;6=Storage;7=Equalize;8=Passthru;9=Inverting;10=Power assist;11=Power supply;252=External control
            invMode = mode.get('device_mode', None)
            if invMode == 'Battery':
                m['/State'] = 9 # Inverting
            elif invMode == 'Line':
                if data.get('is_charging_on', 0) == 1:
                    m['/State'] = 3 # Passthru + Charging? = Bulk
                else:    
                    m['/State'] = 8 # Passthru
            elif invMode == 'Standby':
                m['/State'] = data.get('is_charging_on', 0) * 6 # Standby = 0 -> OFF, Stanby + Charging = 6 -> "Storage" Storing power
            else:
                m['/State'] = 0 # OFF
            v['/State'] = m['/State']

            # Normal operation, read data
            v['/Dc/0/Voltage'] = m['/Dc/0/Voltage'] = data.get('battery_voltage', None)
            m['/Dc/0/Current'] = -data.get('battery_discharge_current', 0)
            v['/Dc/0/Current'] = -m['/Dc/0/Current']
            charging_ac_current = data.get('battery_charging_current', 0)
            load_on =  data.get('is_load_on', 0)
            charging_ac = data.get('is_charging_on', 0)

            v['/Ac/Out/L1/V'] = m['/Ac/Out/L1/V'] = data.get('ac_output_voltage', None)
            v['/Ac/Out/L1/F'] = m['/Ac/Out/L1/F'] = data.get('ac_output_frequency', None)
            v['/Ac/Out/L1/P'] = m['/Ac/Out/L1/P'] = data.get('ac_output_active_power', None)
            v['/Ac/Out/L1/S'] = m['/Ac/Out/L1/S'] = data.get('ac_output_aparent_power', None)

            # For some reason, the system does not detect small values
            if (m['/Ac/Out/L1/P'] == 0) and load_on == 1 and m['/Dc/0/Current'] != None and m['/Dc/0/Voltage'] != None and dcSystem != None:
                dcPower = dcSystem + self._dcLast + 27
                power = 27 if dcPower < 27 else dcPower
                power = 100 if power > 100 else power
                m['/Ac/Out/L1/P'] = power - 27
                self._dcLast = m['/Ac/Out/L1/P'] or 0
            else:
                self._dcLast = 0

            # Also, due to a bug (?), is not possible to get the battery charging current from AC
            if GUESS_AC_CHARGING and dcSystem != None and charging_ac == 1:
                chargePower = dcSystem + self._chargeLast
                self._chargeLast = chargePower - 30
                charging_ac_current = -(chargePower - 30) / m['/Dc/0/Voltage']
            else:
                self._chargeLast = 0

            # For my installation specific case: 
            # - When the load is off the output is unkonwn, the AC1/OUT are connected directly, and inverter is bypassed
            if INVERTER_OFF_ASSUME_BYPASS and load_on == 0:
                m['/Ac/Out/L1/P'] = m['/Ac/Out/L1/S'] = None

            # Charger input, same as AC1 but separate line data
            v['/Ac/ActiveIn/L1/V'] = m['/Ac/In/1/L1/V'] = data.get('ac_input_voltage', None)
            v['/Ac/ActiveIn/L1/F'] = m['/Ac/In/1/L1/F'] = data.get('ac_input_frequency', None)

            # It does not give us power of AC in, we need to compute it from the current state + Output power + Charging on + Current
            if m['/State'] == 0:
                m['/Ac/In/1/L1/P'] = None # Unkown if inverter is off
            else:
                m['/Ac/In/1/L1/P'] = 0 if invMode == 'Battery' else m['/Ac/Out/L1/P']
                m['/Ac/In/1/L1/P'] = (m['/Ac/In/1/L1/P'] or 0) + charging_ac * charging_ac_current * m['/Dc/0/Voltage']
            v['/Ac/ActiveIn/L1/P'] = m['/Ac/In/1/L1/P']

            # Solar charger
            m['/Pv/0/V'] = data.get('pv_input_voltage', None)
            m['/Pv/0/P'] = data.get('pv_input_power', None)
            m['/MppOperationMode'] = 2 if (m['/Pv/0/P'] != None and m['/Pv/0/P'] > 0) else 0
            
            m['/Dc/0/Current'] = m['/Dc/0/Current'] + charging_ac * charging_ac_current - self._dcLast / (m['/Dc/0/Voltage'] or 27)
            # Compute the currents as well?
            # m['/Ac/Out/L1/I'] = m['/Ac/Out/L1/P'] / m['/Ac/Out/L1/V']
            # m['/Ac/In/1/L1/I'] = m['/Ac/In/1/L1/P'] / m['/Ac/In/1/L1/V']

            # Update some Alarms
            def getWarning(string):
                val = warnings.get(string, None)
                if val is None:
                    return 1
                return int(val) * 2
            m['/Alarms/Connection'] = 0
            m['/Alarms/HighTemperature'] = getWarning('over_temperature_fault')
            m['/Alarms/Overload'] = getWarning('overload_fault')
            m['/Alarms/HighVoltage'] = getWarning('bus_over_fault')
            m['/Alarms/LowVoltage'] = getWarning('bus_under_fault')
            m['/Alarms/HighVoltageAcOut'] = getWarning('inverter_voltage_too_high_fault')
            m['/Alarms/LowVoltageAcOut'] = getWarning('inverter_voltage_too_low_fault')
            m['/Alarms/HighDcVoltage'] = getWarning('battery_voltage_to_high_fault')
            m['/Alarms/LowDcVoltage'] = getWarning('battery_low_alarm_warning')
            m['/Alarms/LineFail'] = getWarning('line_fail_warning')

            # Misc
            m['/Temperature'] = data.get('inverter_heat_sink_temperature', None)

            # Execute updates of previously updated values
            self._updateInternal()

        logging.info("{} done".format(datetime.datetime.now().time()))
        return True

    def _change_PI30(self, path, value):
        if path == '/Ac/In/1/CurrentLimit' or path == '/Ac/In/2/CurrentLimit':
            logging.warning("setting max utility charging current to = {} ({})".format(value, setMaxUtilityChargingCurrent(value)))
            self._queued_updates.append((path, value))

        if path == '/Mode': # 1=Charger Only;2=Inverter Only;3=On;4=Off(?)
            if value == 1:
                #logging.warning("setting mode to 'Charger Only'(Charger=Util & Output=Util->solar) ({},{})".format(setChargerPriority(0), setOutputSource(0)))
                logging.warning("setting mode to 'Charger Only'(Charger=Util) ({})".format(setChargerPriority(0)))
            elif value == 2:
                logging.warning("setting mode to 'Inverter Only'(Charger=Solar & Output=SBU) ({},{})".format(setChargerPriority(3), setOutputSource(2)))
            elif value == 3:
                logging.warning("setting mode to 'ON=Charge+Invert'(Charger=Util & Output=SBU) ({},{})".format(setChargerPriority(0), setOutputSource(2)))
            elif value == 4:
                #logging.warning("setting mode to 'OFF'(Charger=Solar & Output=Util->solar) ({},{})".format(setChargerPriority(3), setOutputSource(0)))
                logging.warning("setting mode to 'OFF'(Charger=Solar) ({})".format(setChargerPriority(3)))
            else:
                logging.warning("setting mode not understood ({})".format(value))
            self._queued_updates.append((path, value))
        # Debug nodes
        if path == '/Settings/Charger':
            if value == 0:
                logging.warning("setting charger priority to utility first ({})".format(setChargerPriority(value)))
            elif value == 1:
                logging.warning("setting charger priority to solar first ({})".format(setChargerPriority(value)))
            elif value == 2:
                logging.warning("setting charger priority to solar and utility ({})".format(setChargerPriority(value)))
            else:
                logging.warning("setting charger priority to only solar ({})".format(setChargerPriority(3)))
            self._queued_updates.append((path, value))
        if path == '/Settings/Output':
            if value == 0:
                logging.warning("setting output Utility->Solar priority ({})".format(setOutputSource(value)))
            elif value == 1:
                logging.warning("setting output solar->Utility priority ({})".format(setOutputSource(value)))
            else:
                logging.warning("setting output SBU priority ({})".format(setOutputSource(2)))
            self._queued_updates.append((path, value))
        return True # accept the change

    # THIS IS COMPLETELY UNTESTED
    def _update_PI17(self):
        raw = runInverterCommands(['GS','MOD','WS'])
        data, mode, warnings = raw
        with self._dbusmulti as m:#, self._dbusvebus as v:
            # 1=Charger Only;2=Inverter Only;3=On;4=Off -> Control from outside
            if 'error' in data and 'short' in data['error']:
                m['/State'] = 0
                m['/Alarms/Connection'] = 2
            
            # 0=Off;1=Low Power;2=Fault;3=Bulk;4=Absorption;5=Float;6=Storage;7=Equalize;8=Passthru;9=Inverting;10=Power assist;11=Power supply;252=External control
            invMode = mode.get('device_mode', None)
            if invMode == 'Battery':
                m['/State'] = 9 # Inverting
            elif invMode == 'Line':
                if data.get('is_charging_on', 0) == 1:
                    m['/State'] = 3 # Passthru + Charging? = Bulk
                else:    
                    m['/State'] = 8 # Passthru
            elif invMode == 'Standby':
                m['/State'] = data.get('is_charging_on', 0) * 6 # Standby = 0 -> OFF, Stanby + Charging = 6 -> "Storage" Storing power
            else:
                m['/State'] = 0 # OFF
            # v['/State'] = m['/State']

            # Normal operation, read data
            #v['/Dc/0/Voltage'] = 
            m['/Dc/0/Voltage'] = data.get('battery_voltage', None)
            m['/Dc/0/Current'] = -data.get('battery_discharge_current', 0)
            #v['/Dc/0/Current'] = -m['/Dc/0/Current']
            charging_ac_current = data.get('battery_charging_current', 0)
            load_on =  data.get('is_load_on', 0)
            charging_ac = data.get('is_charging_on', 0)

            #v['/Ac/Out/L1/V'] = 
            m['/Ac/Out/L1/V'] = data.get('ac_output_voltage', None)
            #v['/Ac/Out/L1/F'] = 
            m['/Ac/Out/L1/F'] = data.get('ac_output_frequency', None)
            #v['/Ac/Out/L1/P'] =1 
            m['/Ac/Out/L1/P'] = data.get('ac_output_active_power', None)
            #v['/Ac/Out/L1/S'] = 
            m['/Ac/Out/L1/S'] = data.get('ac_output_aparent_power', None)

            # For my installation specific case: 
            # - When the load is off the output is unkonwn, the AC1/OUT are connected directly, and inverter is bypassed
            if INVERTER_OFF_ASSUME_BYPASS and load_on == 0:
                m['/Ac/Out/L1/P'] = m['/Ac/Out/L1/S'] = None

            # Charger input, same as AC1 but separate line data
            #v['/Ac/ActiveIn/L1/V'] = 
            m['/Ac/In/1/L1/V'] = data.get('ac_input_voltage', None)
            #v['/Ac/ActiveIn/L1/F'] = 
            m['/Ac/In/1/L1/F'] = data.get('ac_input_frequency', None)

            # It does not give us power of AC in, we need to compute it from the current state + Output power + Charging on + Current
            if m['/State'] == 0:
                m['/Ac/In/1/L1/P'] = None # Unkown if inverter is off
            else:
                m['/Ac/In/1/L1/P'] = 0 if invMode == 'Battery' else m['/Ac/Out/L1/P']
                m['/Ac/In/1/L1/P'] = (m['/Ac/In/1/L1/P'] or 0) + charging_ac * charging_ac_current * m['/Dc/0/Voltage']
            #v['/Ac/ActiveIn/L1/P'] = m['/Ac/In/1/L1/P']

            # Solar charger
            m['/Pv/0/V'] = data.get('pv_input_voltage', None)
            m['/Pv/0/P'] = data.get('pv_input_power', None)
            m['/MppOperationMode'] = 2 if (m['/Pv/0/P'] != None and m['/Pv/0/P'] > 0) else 0
            
            m['/Dc/0/Current'] = m['/Dc/0/Current'] + charging_ac * charging_ac_current - self._dcLast / (m['/Dc/0/Voltage'] or 27)
            # Compute the currents as well?
            # m['/Ac/Out/L1/I'] = m['/Ac/Out/L1/P'] / m['/Ac/Out/L1/V']
            # m['/Ac/In/1/L1/I'] = m['/Ac/In/1/L1/P'] / m['/Ac/In/1/L1/V']

            # Update some Alarms
            def getWarning(string):
                val = warnings.get(string, None)
                if val is None:
                    return 1
                return int(val) * 2
            m['/Alarms/Connection'] = 0
            m['/Alarms/HighTemperature'] = getWarning('over_temperature_fault')
            m['/Alarms/Overload'] = getWarning('overload_fault')
            m['/Alarms/HighVoltage'] = getWarning('bus_over_fault')
            m['/Alarms/LowVoltage'] = getWarning('bus_under_fault')
            m['/Alarms/HighVoltageAcOut'] = getWarning('inverter_voltage_too_high_fault')
            m['/Alarms/LowVoltageAcOut'] = getWarning('inverter_voltage_too_low_fault')
            m['/Alarms/HighDcVoltage'] = getWarning('battery_voltage_to_high_fault')
            m['/Alarms/LowDcVoltage'] = getWarning('battery_low_alarm_warning')
            m['/Alarms/LineFail'] = getWarning('line_fail_warning')

            # Misc
            m['/Temperature'] = data.get('inverter_heat_sink_temperature', None)

            # Execute updates of previously updated values
            self._updateInternal()

        return True

    def _change_PI17(self, path, value):
        return True # accept the change

    def _update_PI18(self):
        """Update handler for PI18 protocol (InfiniSolar V)."""
        logging.info("Starting PI18 update cycle for InfiniSolar V")
        try:
            # PI18 commands that work for InfiniSolar V
            raw = runInverterCommands(['PIRI'], self._invProtocol)
            
            if not raw or len(raw) == 0:
                self._handle_protocol_error('communication')
                return False
                
            piri_data = raw[0]  # PIRI response
            
            # Check for errors
            if 'error' in piri_data or 'ERROR' in piri_data:
                self._handle_protocol_error('status_error', {'piri': piri_data})
                return False
            
            # Process PIRI data for InfiniSolar V
            with self._dbusmulti as m, self._dbusvebus as v:
                # PIRI gives us rated/configuration info, not real-time status
                # For now, set basic values to show the device is connected
                
                # Set basic operational state
                m['/State'] = 3  # On (since we got a response)
                v['/State'] = m['/State']
                
                # Set some basic values from PIRI if available
                # PIRI format: various rated parameters
                if 'raw_response' in piri_data and piri_data['raw_response']:
                    raw_response = piri_data['raw_response'][0] if piri_data['raw_response'][0] else ''
                    logging.debug(f"PIRI raw response: {raw_response}")
                    
                    # For now, set static values to show the service is working
                    # These would normally come from a status command like GS
                    m['/Dc/0/Voltage'] = 24.0  # Placeholder
                    v['/Dc/0/Voltage'] = 24.0
                    m['/Dc/0/Current'] = 0.0
                    v['/Dc/0/Current'] = 0.0
                    
                    m['/Ac/Out/L1/V'] = 230.0  # Placeholder
                    v['/Ac/Out/L1/V'] = 230.0
                    m['/Ac/Out/L1/F'] = 50.0
                    v['/Ac/Out/L1/F'] = 50.0
                    m['/Ac/Out/L1/P'] = 0
                    v['/Ac/Out/L1/P'] = 0
                    
                    # Clear connection alarm since we got data
                    m['/Alarms/Connection'] = 0
                else:
                    logging.warning("No raw response data in PIRI")
                
                # Update internal state
                self._updateInternal()
                
                logging.info("PI18 update completed successfully")
                return True
                
        except Exception as e:
            logging.exception(f"Error in PI18 update: {str(e)}")
            return False

    def _change_PI18(self, path, value):
        """Handle settings changes for PI18 protocol."""
        try:
            # PI18 protocol may have different command syntax
            # For now, accept changes but don't send commands since we need to research the protocol
            logging.info(f"PI18 change request: {path} = {value} (not implemented yet)")
            self._queued_updates.append((path, value))
            return True
        except Exception as e:
            logging.error(f"Error in PI18 change handler: {str(e)}")
            return False

    def _handle_protocol_error(self, error_type, error_data=None):
        """Handle protocol-specific errors with appropriate recovery actions."""
        with self._dbusmulti as m:
            if error_type == 'communication':
                m['/Alarms/Connection'] = 2
                m['/State'] = 0
                logging.error("Communication error with inverter")
            elif error_type == 'status_error':
                m['/Alarms/Connection'] = 1
                m['/State'] = 2  # Fault state
                logging.error(f"Status error: {error_data}")
            elif error_type == 'data_error':
                # Keep last known good values, just update alarm
                m['/Alarms/Connection'] = 1
                logging.warning(f"Data error: {error_data}")
            elif error_type == 'timeout':
                m['/Alarms/Connection'] = 1
                logging.warning("Command timeout")
            else:
                m['/Alarms/Connection'] = 1
                logging.warning(f"Unknown error type: {error_type}")

    def _update_PI18SV(self):
        """Update handler for PI18SV protocol."""
        logging.info("Starting PI18SV update cycle")
        try:
            # Define command batches for better performance
            status_batch = ['GS', 'MOD', 'FLAG']  # Basic status and mode
            power_batch = ['PIRI']  # Power ratings and configuration
            
            # Execute status command batch with retry
            max_retries = 2
            for attempt in range(max_retries):
                raw_status = runInverterCommands(status_batch, self._invProtocol)
                if raw_status and len(raw_status) == len(status_batch):
                    break
                if attempt < max_retries - 1:
                    logging.warning(f"Status command retry {attempt + 1}")
                    time.sleep(1)
            
            if not raw_status or len(raw_status) != len(status_batch):
                self._handle_protocol_error('communication')
                return False
                
            # Parse status responses
            data = raw_status[0]  # GS response
            mode = raw_status[1]  # MOD response
            flags = raw_status[2] if len(raw_status) > 2 else {}  # FLAG response
            
            # Check for critical data
            if 'error' in data or 'error' in mode:
                self._handle_protocol_error('status_error', {'data': data, 'mode': mode})
                return False
                
            # Get power configuration (optional)
            try:
                raw_power = runInverterCommands(power_batch, self._invProtocol)
                power_data = raw_power[0] if raw_power else {}
                if 'error' in power_data:
                    self._handle_protocol_error('data_error', {'power': power_data})
            except Exception as e:
                logging.warning(f"Power data retrieval failed: {str(e)}")
                power_data = {}

            # Process the data
            with self._dbusmulti as m, self._dbusvebus as v:
                # Handle inverter state
                if 'error' in data:
                    m['/State'] = 0
                    m['/Alarms/Connection'] = 2
                    return True
            
            # Map working mode to state according to PI18SV protocol
            # 00=Power on mode
            # 01=Standby mode
            # 02=Bypass mode
            # 03=Battery mode
            # 04=Fault mode
            # 05=Hybrid mode (Line mode, Grid mode)
            invMode = mode.get('device_mode', '00')
            if invMode == '03':  # Battery mode
                m['/State'] = 9  # Inverting
            elif invMode == '05':  # Hybrid/Line mode
                if data.get('Battery Charge Current', 0) > 0:
                    m['/State'] = 3  # Bulk charging
                else:    
                    m['/State'] = 8  # Passthru
            elif invMode == '02':  # Bypass mode
                m['/State'] = 8  # Passthru
            elif invMode == '01':  # Standby mode
                m['/State'] = data.get('Battery Charge Current', 0) > 0 and 6 or 0  # Storage or Off
            elif invMode == '04':  # Fault mode
                m['/State'] = 2  # Fault
            else:
                m['/State'] = 0  # Off
            v['/State'] = m['/State']

                            # Helper function for value conversion
            def convert_value(value, scale=1.0, min_val=None, max_val=None):
                """Convert and validate numeric values."""
                try:
                    if value is None:
                        return None
                    val = float(value) * scale
                    if min_val is not None:
                        val = max(min_val, val)
                    if max_val is not None:
                        val = min(max_val, val)
                    return val
                except (ValueError, TypeError) as e:
                    logging.warning(f"Value conversion failed: {str(e)}")
                    return None

            # Battery data
            battery_voltage = convert_value(data.get('Battery Voltage'), scale=0.1, min_val=0, max_val=100)
            v['/Dc/0/Voltage'] = m['/Dc/0/Voltage'] = battery_voltage
            
            discharge_current = convert_value(data.get('Battery Discharge Current', 0), min_val=0)
            m['/Dc/0/Current'] = -discharge_current if discharge_current is not None else 0
            v['/Dc/0/Current'] = -m['/Dc/0/Current']
            
            charging_current = convert_value(data.get('Battery Charge Current', 0), min_val=0)
            if charging_current is None:
                charging_current = 0

            # AC Output data
            v['/Ac/Out/L1/V'] = m['/Ac/Out/L1/V'] = convert_value(
                data.get('AC Output Voltage'), scale=0.1, min_val=0, max_val=300
            )
            v['/Ac/Out/L1/F'] = m['/Ac/Out/L1/F'] = convert_value(
                data.get('AC Output Frequency'), scale=0.1, min_val=45, max_val=65
            )
            v['/Ac/Out/L1/P'] = m['/Ac/Out/L1/P'] = convert_value(
                data.get('AC Output Active Power'), min_val=0
            )
            v['/Ac/Out/L1/S'] = m['/Ac/Out/L1/S'] = convert_value(
                data.get('AC Output Apparent Power'), min_val=0
            )

            # AC Input data
            v['/Ac/ActiveIn/L1/V'] = m['/Ac/In/1/L1/V'] = convert_value(
                data.get('AC Input Voltage'), scale=0.1, min_val=0, max_val=300
            )
            v['/Ac/ActiveIn/L1/F'] = m['/Ac/In/1/L1/F'] = convert_value(
                data.get('AC Input Frequency'), scale=0.1, min_val=45, max_val=65
            )

            # Solar/PV data
            m['/Pv/0/V'] = convert_value(data.get('PV1 Input Voltage'), scale=0.1, min_val=0)
            m['/Pv/0/P'] = convert_value(data.get('PV1 Input Power'), min_val=0)
            m['/MppOperationMode'] = 2 if (m['/Pv/0/P'] or 0) > 0 else 0

            # Process flags/warnings according to PI18SV protocol
            # FLAG command returns:
            # A: Enable/disable silence buzzer or open buzzer
            # B: Enable/Disable overload bypass function
            # C: Enable/Disable LCD display escape to default page after 1min timeout
            # D: Enable/Disable overload restart
            # E: Enable/Disable over temperature restart
            # F: Enable/Disable backlight on
            # G: Enable/Disable alarm on when primary source interrupt
            # H: Enable/Disable fault code record
            flags = flags  # FLAG command response
            
            def get_flag(key, default=0):
                try:
                    return int(flags.get(key, default))
                except:
                    return default

            m['/Alarms/Connection'] = 0
            m['/Alarms/HighTemperature'] = get_flag('E') * 2  # Over temperature restart
            m['/Alarms/Overload'] = get_flag('D') * 2  # Overload restart
            m['/Alarms/HighVoltage'] = get_flag('B') * 2  # Overload bypass
            m['/Alarms/LowVoltage'] = 0  # Not directly available
            m['/Alarms/HighVoltageAcOut'] = 0  # Not directly available
            m['/Alarms/LowVoltageAcOut'] = 0  # Not directly available
            m['/Alarms/HighDcVoltage'] = 0  # Not directly available
            m['/Alarms/LowDcVoltage'] = 0  # Not directly available
            m['/Alarms/LineFail'] = get_flag('G') * 2  # Alarm on primary source interrupt

            # Misc
            m['/Temperature'] = data.get('inverter_heat_sink_temperature')

            # Update internal state
            self._updateInternal()

            return True

        except Exception as e:
            logging.exception(f"Error in PI18SV update: {str(e)}")
            return False

    def _process_parallel_data(self, raw_data, m, v):
        """Process data for parallel/3-phase configuration."""
        logging.info("Processing parallel/3-phase data")
        logging.debug("Raw data received: %s", raw_data)
        try:
            total_ac_output_power = 0
            total_ac_output_apparent = 0
            battery_voltage = None
            battery_current = 0
            pv_total_power = 0

            for i, phase_data in enumerate(raw_data):
                if isinstance(phase_data, dict) and 'error' not in phase_data:
                    # AC Output data per phase
                    phase_power = phase_data.get('AC Output Active Power', 0)
                    phase_apparent = phase_data.get('AC Output Apparent Power', 0)
                    total_ac_output_power += phase_power
                    total_ac_output_apparent += phase_apparent

                    # Set per-phase data
                    phase_prefix = f'L{i+1}'
                    v[f'/Ac/Out/{phase_prefix}/V'] = m[f'/Ac/Out/{phase_prefix}/V'] = phase_data.get('AC Output Voltage')
                    v[f'/Ac/Out/{phase_prefix}/F'] = m[f'/Ac/Out/{phase_prefix}/F'] = phase_data.get('AC Output Frequency')
                    v[f'/Ac/Out/{phase_prefix}/P'] = m[f'/Ac/Out/{phase_prefix}/P'] = phase_power
                    v[f'/Ac/Out/{phase_prefix}/S'] = m[f'/Ac/Out/{phase_prefix}/S'] = phase_apparent

                    # Battery data (use first valid reading)
                    if battery_voltage is None:
                        battery_voltage = phase_data.get('Battery Voltage')
                    battery_current += phase_data.get('Battery Discharge Current', 0)
                    
                    # PV/Solar data
                    pv_power = phase_data.get('PV1 Input Power', 0)
                    pv_total_power += pv_power

            # Set total system values
            v['/Dc/0/Voltage'] = m['/Dc/0/Voltage'] = battery_voltage
            m['/Dc/0/Current'] = -battery_current  # Negative for discharge
            v['/Dc/0/Current'] = -m['/Dc/0/Current']
            
            m['/Pv/0/P'] = pv_total_power
            m['/MppOperationMode'] = 2 if pv_total_power > 0 else 0

            # Set parallel-specific data
            m['/Ac/NumberOfPhases'] = len(raw_data)
            v['/Ac/NumberOfPhases'] = m['/Ac/NumberOfPhases']

        except Exception as e:
            logging.error(f"Error processing parallel data: {str(e)}")

    def _process_single_data(self, raw_data, m, v):
        """Process data for single phase configuration."""
        logging.info("Processing single phase data")
        logging.debug("Raw data received: %s", raw_data)
        try:
            if len(raw_data) < 2:
                logging.error("Insufficient data for single phase processing")
                return

            data, mode = raw_data[0:2]
            
            # Handle inverter state
            if 'error' in data:
                m['/State'] = 0
                m['/Alarms/Connection'] = 2
                return

            # Map working mode to state
            invMode = mode.get('Working mode', 'Unknown')
            if invMode == 'Battery mode':
                m['/State'] = 9  # Inverting
            elif invMode == 'Hybrid mode':
                m['/State'] = 3 if data.get('Battery Charge Current', 0) > 0 else 8  # Bulk or Passthru
            elif invMode == 'Standby mode':
                m['/State'] = 6 if data.get('Battery Charge Current', 0) > 0 else 0  # Storage or Off
            else:
                m['/State'] = 0  # Off
            v['/State'] = m['/State']

            # Battery data
            v['/Dc/0/Voltage'] = m['/Dc/0/Voltage'] = data.get('Battery Voltage')
            m['/Dc/0/Current'] = -(data.get('Battery Discharge Current', 0) or 0)
            v['/Dc/0/Current'] = -m['/Dc/0/Current']

            # AC Output data
            v['/Ac/Out/L1/V'] = m['/Ac/Out/L1/V'] = data.get('AC Output Voltage')
            v['/Ac/Out/L1/F'] = m['/Ac/Out/L1/F'] = data.get('AC Output Frequency')
            v['/Ac/Out/L1/P'] = m['/Ac/Out/L1/P'] = data.get('AC Output Active Power')
            v['/Ac/Out/L1/S'] = m['/Ac/Out/L1/S'] = data.get('AC Output Apparent Power')

            # AC Input data
            v['/Ac/ActiveIn/L1/V'] = m['/Ac/In/1/L1/V'] = data.get('AC Input Voltage')
            v['/Ac/ActiveIn/L1/F'] = m['/Ac/In/1/L1/F'] = data.get('AC Input Frequency')

            # Solar/PV data
            m['/Pv/0/V'] = data.get('PV1 Input Voltage')
            m['/Pv/0/P'] = data.get('PV1 Input Power')
            m['/MppOperationMode'] = 2 if (m['/Pv/0/P'] or 0) > 0 else 0

            # Process warnings if available
            if len(raw_data) > 3:
                warnings = raw_data[3]
                self._process_warnings(warnings, m)

        except Exception as e:
            logging.error(f"Error processing single phase data: {str(e)}")

    def _process_warnings(self, warnings, m):
        """Process warning flags."""
        try:
            def get_warning(key):
                val = warnings.get(key)
                if val is None:
                    return 1
                return int(val) * 2

            m['/Alarms/Connection'] = 0
            m['/Alarms/HighTemperature'] = get_warning('over_temperature_fault')
            m['/Alarms/Overload'] = get_warning('overload_fault')
            m['/Alarms/HighVoltage'] = get_warning('bus_over_fault')
            m['/Alarms/LowVoltage'] = get_warning('bus_under_fault')
            m['/Alarms/HighVoltageAcOut'] = get_warning('inverter_voltage_too_high_fault')
            m['/Alarms/LowVoltageAcOut'] = get_warning('inverter_voltage_too_low_fault')
            m['/Alarms/HighDcVoltage'] = get_warning('battery_voltage_to_high_fault')
            m['/Alarms/LowDcVoltage'] = get_warning('battery_low_alarm_warning')
            m['/Alarms/LineFail'] = get_warning('line_fail_warning')

        except Exception as e:
            logging.error(f"Error processing warnings: {str(e)}")

    def _change_PI18SV(self, path, value):
        """Handle settings changes for PI18SV protocol."""
        try:
            if path == '/Mode':  # 1=Charger Only;2=Inverter Only;3=On;4=Off
                if value == 1:  # Charger Only
                    runInverterCommands(['PCP00', 'POP00'], self._invProtocol)  # Utility first
                elif value == 2:  # Inverter Only
                    runInverterCommands(['PCP02', 'POP01'], self._invProtocol)  # Solar only, Solar first
                elif value == 3:  # On (normal operation)
                    runInverterCommands(['PCP01', 'POP02'], self._invProtocol)  # Solar first, SBU
                elif value == 4:  # Off
                    runInverterCommands(['PCP02'], self._invProtocol)  # Solar only
                self._queued_updates.append((path, value))

            elif path == '/Ac/In/1/CurrentLimit':
                try:
                    current = int(value)
                    runInverterCommands([f'MUCHGC0,{current:03d}'], self._invProtocol)
                    self._queued_updates.append((path, value))
                except Exception as e:
                    logging.error(f"Failed to set current limit: {str(e)}")
            
            elif path == '/Settings/Charger':
                try:
                    if value in [0, 1, 2]:  # Utility first, Solar first, Solar+Utility
                        runInverterCommands([f'PCP0{value}'], self._invProtocol)
                    else:  # Solar only
                        runInverterCommands(['PCP02'], self._invProtocol)
                    self._queued_updates.append((path, value))
                except Exception as e:
                    logging.error(f"Failed to set charger priority: {str(e)}")
            
            elif path == '/Settings/Output':
                try:
                    if value in [0, 1]:  # Utility->Solar, Solar->Utility
                        runInverterCommands([f'POP0{value}'], self._invProtocol)
                    else:  # SBU
                        runInverterCommands(['POP02'], self._invProtocol)
                    self._queued_updates.append((path, value))
                except Exception as e:
                    logging.error(f"Failed to set output priority: {str(e)}")

            return True

        except Exception as e:
            logging.error(f"Error in PI18SV change handler: {str(e)}")
            return False

def main():
    parser = argparse.ArgumentParser(description="DBus service for MPP Solar inverters")
    parser.add_argument("--baudrate", "-b", default=2400, type=int,
                      help="Serial port baud rate (default: 2400)")
    parser.add_argument("--serial", "-s", required=True, type=str,
                      help="Serial port device path")
    parser.add_argument("--log-level", "-l", default="INFO",
                      choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                      help="Logging level (default: INFO)")
    parser.add_argument("--log-file", "-f", default="/var/log/dbus-mppsolar.log",
                      help="Log file path (default: /var/log/dbus-mppsolar.log)")
    
    global args
    args = parser.parse_args()
    
    # Configure logging based on command line arguments
    log_level = getattr(logging, args.log_level.upper())
    setup_logging(log_level=log_level, log_file=args.log_file)

    from dbus.mainloop.glib import DBusGMainLoop
    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)

    mppservice = DbusMppSolarService(tty=args.serial.strip("/dev/"), deviceinstance=0)
    logging.warning('Created service & connected to dbus, switching over to GLib.MainLoop() (= event based)')

    global mainloop
    mainloop = GLib.MainLoop()
    mainloop.run()


if __name__ == "__main__":
    main()