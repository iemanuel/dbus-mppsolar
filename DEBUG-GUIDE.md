# 🔧 DBus MPP Solar Debugging Guide

## The Main Issues Found and Fixed

### 1. **DBus Service Registration Problem** ✅ FIXED
**Problem**: Services were created with `register=False` and complex registration logic
**Fix**: Simplified to automatic registration when service is created

### 2. **Missing Product ID** ✅ FIXED  
**Problem**: Used serial number as ProductId instead of proper Victron Product ID
**Fix**: Changed to `0xB012` (valid Victron Multi/Quattro product ID)

### 3. **Protocol Detection Failures** ✅ FIXED
**Problem**: Complex retry logic that could fail silently and prevent service startup
**Fix**: Simplified detection with graceful fallbacks and better error handling

### 4. **Service Template Configuration** 
**Problem**: The deployment script modifies service template to use wrapper scripts
**Fix**: Need to verify wrapper script is working correctly

## 🧪 Debug Steps

### Step 1: Test the Debug Scripts

Run the debug script to identify the exact issue:

```bash
cd /Users/isidoremanuel/Documents/GitHub/dbus-mppsolar
python3 debug-dbus-service.py
```

### Step 2: Test Simple DBus Service

Test if DBus service registration works at all:

```bash
python3 simple-dbus-test.py --serial /dev/ttyUSB0
```

This should create a test service that appears in Venus OS interface within 30 seconds.

### Step 3: Test Fixed Main Service

Test the fixed main service manually:

```bash
python3 dbus-mppsolar.py --serial /dev/ttyUSB0 --log-level DEBUG
```

### Step 4: Check Venus OS Integration

After running any of the above, check in Venus OS:
1. Go to Device List in Venus OS interface
2. Look for "MPP Solar Inverter" or similar
3. Check the device shows up with proper data

## 🔍 What to Look For

### Signs the Service is Working:
- ✅ Log shows "DBus services created" and "registered and ready"
- ✅ Device appears in Venus OS device list
- ✅ Real-time data updates in Venus OS interface
- ✅ No communication errors in logs

### Signs of Problems:
- ❌ "Failed to create DBus services" in logs
- ❌ Communication timeout errors
- ❌ Service not appearing in Venus OS device list
- ❌ Service appears but with no data

## 🛠️ Common Issues and Solutions

### Issue: Service not appearing in Venus OS
**Cause**: DBus system bus not accessible or service name conflict
**Solution**: 
1. Check if other Victron services are visible
2. Try different device instance number
3. Check Venus OS logs: `tail -f /var/log/messages`

### Issue: Service appears but no data
**Cause**: Communication with inverter failing
**Solution**:
1. Check serial connection: `ls -la /dev/ttyUSB*`
2. Verify baud rate (try 2400, 9600, 115200)
3. Test with different protocol (PI30, PI17, PI18SV)

### Issue: Communication timeouts
**Cause**: Wrong protocol or serial settings
**Solution**:
1. Use protocol detection: `python3 test_detect_protocol.py`
2. Try different baud rates
3. Check cable connections

## 🚀 Quick Test Commands

```bash
# 1. Check if inverter responds at all
python3 -c "
import sys, os
sys.path.insert(1, 'mpp-solar')
import mppsolar
dev = mppsolar.helpers.get_device_class('mppsolar')(port='/dev/ttyUSB0', protocol='PI18SV', baud=2400)
print(dev.run_command('QPI'))
"

# 2. Test DBus system
python3 -c "
import dbus
bus = dbus.SystemBus()
services = [s for s in bus.list_names() if 'victron' in s]
print(f'Victron services: {len(services)}')
for s in services[:3]: print(s)
"

# 3. Check if service is running
ps aux | grep dbus-mppsolar

# 4. Check Venus OS logs
tail -f /var/log/messages | grep -i mppsolar
```

## 📋 Checklist for Venus OS Deployment

- [ ] Deploy script completed without errors
- [ ] Service shows as running: `svstat /service/dbus-mppsolar.*`
- [ ] No errors in service logs: `tail -f /var/log/mppsolar.*/current`
- [ ] DBus service is registered: Check with `dbus-send` commands
- [ ] Device appears in Venus OS interface
- [ ] Real-time data is updating

## 🔗 Next Steps if Still Not Working

1. **Check Venus OS Version**: Ensure compatible Venus OS version
2. **Verify Serial Connection**: Test with official Victron tools
3. **Protocol Compatibility**: Some inverters need specific protocol versions
4. **Hardware Issues**: Check USB-to-serial adapter compatibility
5. **Venus OS Logs**: Check system logs for service registration issues

The fixed code should resolve the main DBus registration issues. If problems persist, they're likely related to hardware communication or Venus OS configuration rather than the service code itself.
