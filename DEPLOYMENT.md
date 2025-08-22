# dbus-mppsolar Deployment Guide

This guide explains how to deploy dbus-mppsolar to VenusOS using the provided deployment scripts.

## Quick Deployment (One-liner)

The fastest way to deploy is using a one-liner command that downloads and runs the deployment script directly from GitHub:

```bash
curl -sSL https://raw.githubusercontent.com/iemanuel/dbus-mppsolar/main/deploy.sh | sudo bash
```

Or using wget:

```bash
wget -qO- https://raw.githubusercontent.com/iemanuel/dbus-mppsolar/main/deploy.sh | sudo bash
```

## Alternative Deployment Methods

### Method 1: Download and Run Locally

1. Download the deployment script:
```bash
curl -sSL https://raw.githubusercontent.com/iemanuel/dbus-mppsolar/main/deploy.sh > deploy.sh
```

2. Make it executable and run:
```bash
chmod +x deploy.sh
sudo ./deploy.sh
```

### Method 2: Clone Repository and Deploy

1. Clone the repository:
```bash
git clone --recurse-submodules https://github.com/iemanuel/dbus-mppsolar
cd dbus-mppsolar
```

2. Run the deployment script:
```bash
sudo ./deploy.sh
```

### Method 3: Custom Repository/Branch

If you want to deploy from a different repository or branch:

```bash
# Using the direct deployment script
curl -sSL https://raw.githubusercontent.com/iemanuel/dbus-mppsolar/main/deploy-direct.sh | sudo bash -s -- -r username/repo -b branch-name

# Or download and run with custom parameters
./deploy-direct.sh -r username/repo -b develop
```

## What the Deployment Script Does

The deployment script automates the following steps:

1. **System Checks**: Verifies you're running on VenusOS with root privileges
2. **Requirements**: Installs Python3, Git, and other dependencies if needed
3. **Backup**: Creates a backup of any existing installation
4. **Repository**: Clones the latest code from GitHub with submodules
5. **Service Installation**: Installs the VenusOS service files
6. **Configuration**: Updates serial-starter.conf to include mppsolar service
7. **Dependencies**: Installs Python packages (mpp-solar, dbus-python, PyGObject)
8. **Permissions**: Sets proper file permissions and ownership
9. **Testing**: Verifies the installation is working correctly

## Prerequisites

- VenusOS system (Victron Energy device)
- Root access (sudo)
- Internet connection for downloading from GitHub
- USB-Serial interface for connecting to your inverter

## Post-Deployment

After successful deployment:

1. **Restart VenusOS** or reconnect USB-Serial devices
2. **Check Service Logs**: Monitor at `/opt/victronenergy/service-templates/dbus-mppsolar/log/run`
3. **Verify USB Detection**: Check `dmesg | grep tty` for device detection
4. **Test Connection**: Connect your inverter via USB and check if the service starts automatically

## Troubleshooting

### Common Issues

1. **Permission Denied**: Make sure you're running with `sudo`
2. **Not VenusOS**: This script only works on VenusOS systems
3. **Network Issues**: Check your internet connection and GitHub accessibility
4. **Service Not Starting**: Check logs and verify serial-starter.conf configuration

### Manual Configuration

If automatic configuration fails, you may need to manually edit `/etc/venus/serial-starter.conf`:

```bash
# Add this line to the services section:
service mppsolar        dbus-mppsolar

# Add mppsolar to the default alias:
alias   default         mppsolar:gps:vedirect
```

### Service Management

```bash
# Check service status
svstat /opt/victronenergy/service-templates/dbus-mppsolar

# Restart service
svc -t /opt/victronenergy/service-templates/dbus-mppsolar

# View logs
tail -f /opt/victronenergy/service-templates/dbus-mppsolar/log/run
```

## Rollback

If you need to rollback to a previous version:

1. Check backup directories in `/data/etc/dbus-mppsolar.backup.*`
2. Stop the service: `svc -d /opt/victronenergy/service-templates/dbus-mppsolar`
3. Restore from backup: `cp -R /data/etc/dbus-mppsolar.backup.YYYYMMDD_HHMMSS/* /data/etc/dbus-mppsolar/`
4. Restart the service: `svc -u /opt/victronenergy/service-templates/dbus-mppsolar`

## Support

For issues or questions:
- Check the [main repository](https://github.com/iemanuel/dbus-mppsolar)
- Review VenusOS documentation
- Check service logs for error messages
