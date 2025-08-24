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
from enum import Enum
import datetime
import dbus
import dbus.service

logging.basicConfig(level=logging.WARNING)

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'velib_python'))
from vedbus import VeDbusService, VeDbusItemExport, VeDbusItemImport

# Workarounds for some inverter specific problem I saw
INVERTER_OFF_ASSUME_BYPASS = True
GUESS_AC_CHARGING = True

# Should we import and call manually, to use our version
USE_SYSTEM_MPPSOLAR = False
if USE_SYSTEM_MPPSOLAR:
    try:
        import mppsolar
    except:
        USE_SYSTEM_MPPSOLAR = FALSE
if not USE_SYSTEM_MPPSOLAR:
    sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'mpp-solar'))
    import mppsolar

# Inverter commands to read from the serial
def runInverterCommands(commands, protocol="PI30"):
    """Run commands with error handling and retries."""
    global args
    global mainloop
    
    try:
        if USE_SYSTEM_MPPSOLAR:
            output = []
            for c in commands:
                try:
                    result = sp.getoutput(f"mpp-solar -b {args.baudrate} -P {protocol} -p {args.serial} -o json -c {c}").split('\n')[0]
                    parsed = json.loads(result)
                except Exception as e:
                    logging.warning(f"Command {c} failed on protocol {protocol}: {str(e)}")
                    parsed = {"error": str(e), "raw_response": ""}
                output.append(parsed)
            return output
        else:
            dev = mppsolar.helpers.get_device_class("mppsolar")(port=args.serial, protocol=protocol, baud=args.baudrate)
            results = []
            for c in commands:
                try:
                    result = dev.run_command(command=c)
                    parsed = mppsolar.outputs.to_json(result, False, None, None)
                except Exception as e:
                    logging.warning(f"Command {c} failed on protocol {protocol}: {str(e)}")
                    parsed = {"error": str(e), "raw_response": ""}
                results.append(parsed)
            return results
    except Exception as e:
        logging.error(f"Failed to execute commands {commands}: {str(e)}")
        return [{"error": str(e), "raw_response": ""} for _ in commands]

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

# Our MPP solar service that conencts to 2 dbus services (multi & vebus)
class DbusMppSolarService(object):
    def __init__(self, tty, deviceinstance, productname='MPPSolar', connection='MPPSolar interface'):
        self._tty = tty
        self._queued_updates = []

        # Try to get the protocol version of the inverter
        try:
            self._invProtocol = runInverterCommands(['QPI'])[0].get('protocol_id', 'PI30')
        except:
            try:
                self._invProtocol = runInverterCommands(['PI'])[0].get('protocol_id', 'PI17')
            except:
                logging.error("Protocol detection error, will probably fail now in the next steps")
                self._invProtocol = "QPI"
        
        # Refine the protocol received, it may be the inverter is lying
        if self._invProtocol == 'PI30':
            try:
                raw = runInverterCommands(['QPIGS','QMOD','QPIWS']) 
            except:
                logging.warning(f"Protocol PI30 is failing, switching to PI30MAX")
                self._invProtocol = 'PI30MAX'

        # Get inverter data based on protocol
        if self._invProtocol == 'PI17':
            self._invData = runInverterCommands(['ID','VFW'], self._invProtocol)
        elif self._invProtocol == 'PI30' or self._invProtocol == 'PI30MAX':
            self._invData = runInverterCommands(['QID','QVFW'], self._invProtocol)
        else:
            logging.error(f"Detected inverter on {tty} ({self._invProtocol}), protocol not supported, using PI30 as fallback")       
            self._invProtocol = 'PI30'
        logging.warning(f"Connected to inverter on {tty} ({self._invProtocol}), setting up dbus with /DeviceInstance = {deviceinstance}")
        
        # Create a listener to the DC system power, we need it to give some values
        self._systemDcPower = None        
        self._dcLast = 0
        self._chargeLast = 0
        
        # Create the services
        self._dbusmulti = VeDbusService(f'com.victronenergy.multi.mppsolar.{tty}', dbusconnection(), register=False)
        self._dbusvebus = VeDbusService(f'com.victronenergy.acsystem.mppsolar.{tty}', dbusconnection(), register=False)

        # Set up default paths
        self.setupDefaultPaths(self._dbusmulti, connection, deviceinstance, f"Inverter {productname}")
        self.setupDefaultPaths(self._dbusvebus, connection, deviceinstance, f"Vebus {productname}")

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

        # Register on the bus
        self._dbusmulti.register()
        self._dbusvebus.register() # Comment to not add it to the path

        GLib.timeout_add(10000 if USE_SYSTEM_MPPSOLAR else 2000, self._update)
    
    def setupDefaultPaths(self, service, connection, deviceinstance, productname):
        # self._dbusmulti.add_mandatory_paths(__file__, 'version f{VERSION}, and running on Python ' + platform.python_version(), connection,
		# 	deviceinstance, self._invData[0].get('serial_number', 0), productname, self._invData[1].get('main_cpu_firmware_version', 0), 0, 1)

        # Create the management objects, as specified in the ccgx dbus-api document
        service.add_path('/Mgmt/ProcessName', __file__)
        service.add_path('/Mgmt/ProcessVersion', 'version f{VERSION}, and running on Python ' + platform.python_version())
        service.add_path('/Mgmt/Connection', connection)

        # Create the mandatory objects
        service.add_path('/DeviceInstance', deviceinstance)
        service.add_path('/ProductId', self._invData[0].get('serial_number', 0))
        service.add_path('/ProductName', productname)
        service.add_path('/FirmwareVersion', self._invData[1].get('main_cpu_firmware_version', 0))
        service.add_path('/HardwareVersion', 0)
        service.add_path('/Connected', 1)

        # Create the paths for modifying the system manually
        service.add_path('/Settings/Reset', None, writeable=True, onchangecallback=self._change)
        service.add_path('/Settings/Charger', None, writeable=True, onchangecallback=self._change)
        service.add_path('/Settings/Output', None, writeable=True, onchangecallback=self._change)

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
        global mainloop
        self._connectToDc()
        logging.info("{} updating".format(datetime.datetime.now().time()))
        try: 
            if self._invProtocol == 'PI30' or self._invProtocol == 'PI30MAX':
                return self._update_PI30()
            elif self._invProtocol == 'PI17':
                return self._update_PI17()
            elif self._invProtocol == 'PI18SV':
                return self._update_PI18SV()
            else:
                logging.warning(f"Unknown protocol {self._invProtocol}, defaulting to PI18SV")
                self._invProtocol = 'PI18SV'
                return self._update_PI18SV()
        except:
            logging.exception('Error in update loop', exc_info=True)
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
            elif self._invProtocol == 'PI18SV':
                return self._change_PI18SV(path, value)
            else:
                logging.warning(f"Unknown protocol {self._invProtocol}, defaulting to PI18SV")
                self._invProtocol = 'PI18SV'
                return self._change_PI18SV(path, value)
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

    def _update_PI18SV(self):
        """Update handler for PI18SV protocol with 3-phase support."""
        try:
            # Check parallel/3-phase configuration
            parallel_info = []
            for i in range(3):  # Check all 3 phases
                try:
                    info = runInverterCommands([f'PGS{i}'], self._invProtocol)[0]
                    if not isinstance(info, dict) or 'error' in info:
                        continue
                    parallel_info.append(info)
                except Exception as e:
                    logging.debug(f"Phase {i} not present: {str(e)}")
                    continue

            is_parallel = len(parallel_info) > 1
            logging.warning(f"PI18SV running in {'parallel' if is_parallel else 'single'} mode")

            # Get general status
            if is_parallel:
                # Use parallel status commands
                raw_data = []
                for i in range(len(parallel_info)):
                    try:
                        phase_data = runInverterCommands([f'PGS{i}', f'PRI{i}'], self._invProtocol)
                        raw_data.extend(phase_data)
                    except Exception as e:
                        logging.error(f"Failed to get phase {i} data: {str(e)}")
            else:
                # Use single phase commands
                try:
                    raw_data = runInverterCommands(['GS', 'MOD', 'PIRI', 'FWS'], self._invProtocol)
                except Exception as e:
                    logging.error(f"Failed to get single phase data: {str(e)}")
                    raw_data = []

            if not raw_data:
                logging.error("No valid data received from inverter")
                return False

            with self._dbusmulti as m, self._dbusvebus as v:
                # Process data based on mode
                if is_parallel:
                    self._process_parallel_data(raw_data, m, v)
                else:
                    self._process_single_data(raw_data, m, v)

                # Update internal state
                self._updateInternal()

            return True

        except Exception as e:
            logging.exception(f"Error in PI18SV update: {str(e)}")
            return False

    def _process_parallel_data(self, raw_data, m, v):
        """Process data for parallel/3-phase configuration."""
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--baudrate","-b", default=2400, type=int)
    parser.add_argument("--serial","-s", required=True, type=str)
    global args
    args = parser.parse_args()

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