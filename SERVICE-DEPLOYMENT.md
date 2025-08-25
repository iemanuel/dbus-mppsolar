# MPP Solar Service Deployment Guide

## Overview
This guide explains how to deploy the mppsolar service template to Venus OS so it can be properly detected and managed by the serial-starter.

## Problem Identified
The service was failing to start because:
1. **Missing Service Template**: The serial-starter expects a service template in `/opt/victronenergy/service-templates/mppsolar/`
2. **Symbolic Link Issues**: The serial-starter was encountering "too many levels of symbolic links" errors
3. **Service Registration**: The service wasn't being properly registered with the serial-starter

## Solution
Create a proper service template that the serial-starter can recognize and manage.

## Files Created
- `service-template/run` - Main service startup script
- `service-template/log/run` - Log service script
- `deploy-service-template.sh` - Deployment script
- `SERVICE-DEPLOYMENT.md` - This guide

## Deployment Steps

### 1. Copy Files to Raspberry Pi
```bash
# Copy the service template files to your Raspberry Pi
scp -r service-template/ user@raspberrypi:/tmp/
scp deploy-service-template.sh user@raspberrypi:/tmp/
```

### 2. Run Deployment Script
```bash
# SSH to your Raspberry Pi
ssh user@raspberrypi

# Navigate to temp directory
cd /tmp

# Make deployment script executable
chmod +x deploy-service-template.sh

# Run deployment script (requires root)
sudo ./deploy-service-template.sh
```

### 3. Verify Deployment
```bash
# Check if service template was created
ls -la /opt/victronenergy/service-templates/mppsolar/

# Check serial-starter status
svstat /service/serial-starter

# Check serial-starter logs
tail -20 /var/log/serial-starter/current
```

### 4. Test Service
```bash
# Check if mppsolar service is now detected
grep -i mppsolar /var/log/serial-starter/current

# Check service status
svstat /service/dbus-mppsolar.ttyUSB0

# Check service logs
tail -20 /var/log/mppsolar.TTY/current
```

## Expected Results
After deployment:
1. ✅ The serial-starter should detect the mppsolar service template
2. ✅ The service should start automatically when TTY devices are detected
3. ✅ The service should appear in Venus OS interface
4. ✅ No more "too many levels of symbolic links" errors

## Troubleshooting

### Service Still Not Starting
1. Check serial-starter logs: `tail -20 /var/log/serial-starter/current`
2. Check service logs: `tail -20 /var/log/mppsolar.TTY/current`
3. Verify TTY device exists: `ls -la /dev/ttyUSB*`
4. Check service template permissions: `ls -la /opt/victronenergy/service-templates/mppsolar/`

### Permission Issues
```bash
# Fix permissions if needed
sudo chmod +x /opt/victronenergy/service-templates/mppsolar/run
sudo chmod +x /opt/victronenergy/service-templates/mppsolar/log/run
```

### Manual Testing
```bash
# Test the script manually
cd /data/etc/dbus-mppsolar
python3 dbus-mppsolar.py --serial /dev/ttyUSB0 --log-level DEBUG
```

## Venus OS Integration
Once the service is running:
1. **Device Recognition**: Venus OS should detect the inverter as a Multi/Quattro device
2. **DBus Service**: The service will be available at `com.victronenergy.multi.ttyUSB0`
3. **Interface Display**: The inverter should appear in the Venus OS dashboard
4. **Data Monitoring**: Real-time inverter data will be available through DBus

## Next Steps
After successful deployment:
1. Monitor the service logs for any errors
2. Check Venus OS interface for inverter recognition
3. Verify DBus service is accessible
4. Test inverter communication and data retrieval

## Support
If issues persist, check:
- Serial-starter configuration in `/opt/victronenergy/serial-starter/`
- Venus OS system logs
- DBus service availability
- TTY device permissions and access
