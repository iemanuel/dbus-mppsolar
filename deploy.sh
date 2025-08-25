#!/bin/bash

# dbus-mppsolar Complete Deployment Script for VenusOS
# This script automates the complete installation and startup process from GitHub

set -e  # Exit on any error

# Configuration
REPO_URL="https://github.com/iemanuel/dbus-mppsolar"
INSTALL_DIR="/data/etc/dbus-mppsolar"
SERVICE_TEMPLATE_DIR="/opt/victronenergy/service-templates/mppsolar"
SERIAL_STARTER_CONF="/opt/victronenergy/serial-starter/mppsolar.conf"
BACKUP_DIR="/data/etc/dbus-mppsolar.backup.$(date +%Y%m%d_%H%M%S)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Check if running on VenusOS
check_venusos() {
    if [[ ! -d "/opt/victronenergy" ]]; then
        error "This script is designed for VenusOS. Please run on a VenusOS system."
        exit 1
    fi
}

# Check system requirements
check_requirements() {
    log "Checking system requirements..."
    
    # Check Python version
    if ! command -v python3 &> /dev/null; then
        error "Python3 is not installed. Installing..."
        /opt/victronenergy/swupdate-scripts/set-feed.sh release
        opkg update
        opkg install python3-pip
    else
        log "Python3 is already installed"
    fi
    
    # Check Git
    if ! command -v git &> /dev/null; then
        error "Git is not installed. Installing..."
        opkg install git
    else
        log "Git is already installed"
    fi
    
    # Check if velib_python exists in system (optional check)
    # Note: velib_python is included as a submodule in this repository
    VELIB_PYTHON_FOUND=false
    VELIB_PYTHON_PATHS=(
        "/opt/victronenergy/velib_python"
        "/opt/victronenergy/venus-gw/velib_python"
        "/opt/victronenergy/venus-os/velib_python"
        "/opt/victronenergy/venus/velib_python"
    )
    
    for path in "${VELIB_PYTHON_PATHS[@]}"; do
        if [[ -d "$path" ]]; then
            log "Found system velib_python at: $path"
            VELIB_PYTHON_FOUND=true
            break
        fi
    done
    
    if [[ "$VELIB_PYTHON_FOUND" == false ]]; then
        log "System velib_python not found - will use the one included in the repository"
    fi
}

# Clean installation - always fresh install
clean_installation() {
    log "Performing clean installation..."
    
    # Remove any existing installation completely
    if [[ -d "$INSTALL_DIR" ]]; then
        log "Removing existing installation directory: $INSTALL_DIR"
        rm -rf "$INSTALL_DIR"
        log "✓ Existing installation removed"
    fi
    
    # Remove any existing service template files
    if [[ -d "$SERVICE_TEMPLATE_DIR" ]]; then
        log "Removing existing service template files: $SERVICE_TEMPLATE_DIR"
        rm -rf "$SERVICE_TEMPLATE_DIR"
        log "✓ Existing service template files removed"
    fi
    
    # Clean up any leftover Python path files
    PYTHON_SITE_PACKAGES=$(python3 -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || echo "")
    if [[ -n "$PYTHON_SITE_PACKAGES" ]] && [[ -d "$PYTHON_SITE_PACKAGES" ]]; then
        PYTHON_PATH_FILE="$PYTHON_SITE_PACKAGES/dbus-mppsolar.pth"
        if [[ -f "$PYTHON_PATH_FILE" ]]; then
            log "Removing existing Python path file: $PYTHON_PATH_FILE"
            rm -f "$PYTHON_PATH_FILE"
            log "✓ Python path file removed"
        fi
    fi
    
    log "✓ Clean installation ready"
}

# Clone repository with submodules
clone_repository() {
    log "Cloning repository from $REPO_URL"
    
    # Check network connectivity to GitHub
    log "Checking network connectivity to GitHub..."
    if ! ping -c 1 github.com &> /dev/null; then
        error "Cannot reach GitHub. Please check your internet connection."
        exit 1
    fi
    log "✓ Network connectivity to GitHub confirmed"
    
    # Remove existing directory if it exists
    if [[ -d "$INSTALL_DIR" ]]; then
        log "Removing existing installation directory"
        rm -rf "$INSTALL_DIR"
    fi
    
    # Create parent directory if it doesn't exist
    mkdir -p "$(dirname "$INSTALL_DIR")"
    
    # Clone with submodules
    log "Cloning repository (this may take a few minutes)..."
    if git clone --recurse-submodules "$REPO_URL" "$INSTALL_DIR"; then
        log "Repository cloned successfully"
        
        # Verify the clone
        if [[ -d "$INSTALL_DIR" ]] && [[ -f "$INSTALL_DIR/dbus-mppsolar.py" ]]; then
            log "✓ Main script found: $INSTALL_DIR/dbus-mppsolar.py"
        else
            error "Repository cloned but main script not found"
            exit 1
        fi
        
        # Check if velib_python submodule was cloned
        if [[ -d "$INSTALL_DIR/velib_python" ]] && [[ "$(ls -A "$INSTALL_DIR/velib_python")" ]]; then
            log "✓ velib_python submodule found and populated"
        else
            error "velib_python submodule is empty or missing - cloning failed"
            exit 1
        fi
        
        # Check if mpp-solar submodule was cloned
        if [[ -d "$INSTALL_DIR/mpp-solar" ]] && [[ "$(ls -A "$INSTALL_DIR/mpp-solar")" ]]; then
            log "✓ mpp-solar submodule found and populated"
        else
            error "mpp-solar submodule is empty or missing - cloning failed"
            exit 1
        fi
        
    else
        error "Failed to clone repository"
        error "Please check your internet connection and GitHub accessibility"
        exit 1
    fi
}

# Install service template
install_service_template() {
    log "Installing mppsolar service template to VenusOS"
    
    # Create service template directory
    mkdir -p "$SERVICE_TEMPLATE_DIR"
    
    # Copy service template files
    if [[ -d "$INSTALL_DIR/service-template" ]]; then
        cp -R "$INSTALL_DIR/service-template"/* "$SERVICE_TEMPLATE_DIR/"
        log "✓ Service template files copied from repository"
    else
        # Create service template files if they don't exist in repo
        log "Creating service template files..."
        
        # Create main run script
        cat > "$SERVICE_TEMPLATE_DIR/run" << 'EOF'
#!/bin/sh
echo "*** starting mppsolar service ***"
exec 2>&1
exec /data/etc/dbus-mppsolar/start-dbus-mppsolar.sh $1
EOF
        
        # Create log directory and script
        mkdir -p "$SERVICE_TEMPLATE_DIR/log"
        cat > "$SERVICE_TEMPLATE_DIR/log/run" << 'EOF'
#!/bin/sh
exec 2>&1
exec multilog t s25000 n4 /var/log/mppsolar.TTY
EOF
        
        log "✓ Service template files created"
    fi
    
    # Make service files executable
    chmod +x "$SERVICE_TEMPLATE_DIR/run"
    chmod +x "$SERVICE_TEMPLATE_DIR/log/run"
    
    # Make main script executable
    chmod +x "$INSTALL_DIR/dbus-mppsolar.py"
    chmod +x "$INSTALL_DIR/start-dbus-mppsolar.sh"
    
    # Create log directory
    mkdir -p /var/log/mppsolar.TTY
    
    log "✓ Service template installed successfully"
}

# Configure serial starter
configure_serial_starter() {
    log "Configuring serial starter..."
    
    # Create mppsolar.conf in serial-starter directory
    SERIAL_STARTER_DIR="/opt/victronenergy/serial-starter"
    if [[ ! -d "$SERIAL_STARTER_DIR" ]]; then
        error "Serial starter directory not found: $SERIAL_STARTER_DIR"
        return 1
    fi
    
    # Create mppsolar.conf
    cat > "$SERIAL_STARTER_DIR/mppsolar.conf" << 'EOF'
# MPP Solar inverter configuration for serial-starter
# This file maps mppsolar service to dbus-mppsolar

# Map mppsolar service to dbus-mppsolar
service mppsolar dbus-mppsolar

# Optional: Add specific product mappings if needed
# product "MPP Solar" mppsolar
# product "Easun" mppsolar
# product "SRNE" mppsolar
EOF
    
    log "✓ Created mppsolar.conf in serial-starter directory"
    
    # Check if mppsolar service is already configured in main serial-starter.conf
    MAIN_CONF="/etc/venus/serial-starter.conf"
    if [[ -f "$MAIN_CONF" ]]; then
        # Create backup of original config
        cp "$MAIN_CONF" "${MAIN_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
        
        # Check if mppsolar service is already configured
        if grep -q "service mppsolar" "$MAIN_CONF"; then
            log "mppsolar service is already configured in main serial starter config"
        else
            # Add mppsolar service to the services section
            if grep -q "^service" "$MAIN_CONF"; then
                # Find the last service line and add mppsolar after it
                sed -i '/^service/a service mppsolar        dbus-mppsolar' "$MAIN_CONF"
                log "✓ Added mppsolar service to main serial starter configuration"
            else
                warn "Could not find services section in main serial starter config"
                warn "You may need to manually add: service mppsolar        dbus-mppsolar"
            fi
        fi
        
        # Check if mppsolar is in the default alias
        if grep -q "alias.*default.*mppsolar" "$MAIN_CONF"; then
            log "mppsolar is already in default alias"
        else
            # Find the default alias line and add mppsolar to it
            if grep -q "^alias.*default" "$MAIN_CONF"; then
                sed -i 's/^alias.*default.*/&:mppsolar/' "$MAIN_CONF"
                log "✓ Added mppsolar to default alias"
            else
                warn "Could not find default alias in main serial starter config"
                warn "You may need to manually add mppsolar to the default alias"
            fi
        fi
    else
        warn "Main serial starter config not found: $MAIN_CONF"
        warn "The mppsolar.conf file should be sufficient for basic operation"
    fi
}

# Check Python dependencies (no pip installations)
check_dependencies() {
    log "Checking Python dependencies..."
    
    # Note: We don't install packages via pip since they often fail to build on embedded systems
    # Instead, we use the included modules from the repository submodules
    
    log "Checking for system dbus-python..."
    if python3 -c "import dbus" 2>/dev/null; then
        log "✓ System dbus-python is available"
    else
        log "System dbus-python not found - will use included version"
    fi
    
    log "Checking for system PyGObject..."
    if python3 -c "import gi" 2>/dev/null; then
        log "✓ System PyGObject is available"
    else
        log "System PyGObject not found - will use included version"
    fi
    
    log "Note: Using included mpp-solar and velib_python modules from repository"
}

# Set permissions and Python path
set_permissions() {
    log "Setting proper permissions..."
    
    # Set ownership to root
    chown -R root:root "$INSTALL_DIR"
    chown -R root:root "$SERVICE_TEMPLATE_DIR"
    
    # Set executable permissions
    chmod +x "$INSTALL_DIR/dbus-mppsolar.py"
    chmod +x "$INSTALL_DIR/start-dbus-mppsolar.sh"
    
    # Set service permissions
    chmod +x "$SERVICE_TEMPLATE_DIR/run"
    chmod +x "$SERVICE_TEMPLATE_DIR/log/run"
    
    # Create a Python path configuration file to ensure our modules are used
    log "Configuring Python path for included modules..."
    
    # Create a .pth file to add our paths to Python's sys.path
    PYTHON_PATH_FILE="$INSTALL_DIR/dbus-mppsolar.pth"
    cat > "$PYTHON_PATH_FILE" << EOF
# dbus-mppsolar Python path configuration
# This ensures the included velib_python and mpp-solar modules are used
$INSTALL_DIR/velib_python
$INSTALL_DIR/mpp-solar
EOF
    
    # Find Python site-packages directory
    PYTHON_SITE_PACKAGES=$(python3 -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || echo "")
    
    if [[ -n "$PYTHON_SITE_PACKAGES" ]] && [[ -d "$PYTHON_SITE_PACKAGES" ]]; then
        # Copy .pth file to site-packages
        cp "$PYTHON_PATH_FILE" "$PYTHON_SITE_PACKAGES/"
        log "✓ Python path configured in: $PYTHON_SITE_PACKAGES"
        
        # Also create a wrapper script that sets PYTHONPATH explicitly
        WRAPPER_SCRIPT="$INSTALL_DIR/run-with-path.sh"
        cat > "$WRAPPER_SCRIPT" << EOF
#!/bin/bash
# Wrapper script to run dbus-mppsolar with correct Python path
export PYTHONPATH="$INSTALL_DIR/velib_python:$INSTALL_DIR/mpp-solar:\$PYTHONPATH"
exec "$INSTALL_DIR/dbus-mppsolar.py" "\$@"
EOF
        chmod +x "$WRAPPER_SCRIPT"
        
        # Update the service to use the wrapper for better reliability
        if [[ -f "$SERVICE_TEMPLATE_DIR/run" ]]; then
            sed -i 's|exec /data/etc/dbus-mppsolar/start-dbus-mppsolar.sh|exec /data/etc/dbus-mppsolar/run-with-path.sh|' "$SERVICE_TEMPLATE_DIR/run"
            log "✓ Updated service to use Python path wrapper"
        fi
    else
        # Alternative: create a wrapper script that sets PYTHONPATH
        WRAPPER_SCRIPT="$INSTALL_DIR/run-with-path.sh"
        cat > "$WRAPPER_SCRIPT" << 'EOF'
#!/bin/bash
# Wrapper script to run dbus-mppsolar with correct Python path
export PYTHONPATH="$INSTALL_DIR/velib_python:$INSTALL_DIR/mpp-solar:$PYTHONPATH"
exec "$INSTALL_DIR/dbus-mppsolar.py" "$@"
EOF
        chmod +x "$WRAPPER_SCRIPT"
        
        # Update the service to use the wrapper
        if [[ -f "$SERVICE_TEMPLATE_DIR/run" ]]; then
            sed -i 's|exec /data/etc/dbus-mppsolar/start-dbus-mppsolar.sh|exec /data/etc/dbus-mppsolar/run-with-path.sh|' "$SERVICE_TEMPLATE_DIR/run"
            log "✓ Updated service to use Python path wrapper"
        fi
    fi
}

# Test installation
test_installation() {
    log "Testing installation..."
    
    # Check if main script exists and is executable
    if [[ -x "$INSTALL_DIR/dbus-mppsolar.py" ]]; then
        log "✓ Main script is executable"
    else
        warn "✗ Main script is not executable"
        return 1
    fi
    
    # Check if service template files exist
    if [[ -f "$SERVICE_TEMPLATE_DIR/run" ]] && [[ -f "$SERVICE_TEMPLATE_DIR/log/run" ]]; then
        log "✓ Service template files are installed"
    else
        warn "✗ Service template files are missing"
        return 1
    fi
    
    # Check if mppsolar.conf exists
    if [[ -f "/opt/victronenergy/serial-starter/mppsolar.conf" ]]; then
        log "✓ Serial starter configuration created"
    else
        warn "✗ Serial starter configuration missing"
        return 1
    fi
    
    # Check what Python dependencies are available (non-blocking)
    log "Checking Python dependencies..."
    if python3 -c "import mppsolar" 2>/dev/null; then
        log "✓ mppsolar available"
    else
        warn "✗ mppsolar not available (using included version)"
    fi
    
    if python3 -c "import dbus" 2>/dev/null; then
        log "✓ dbus available"
    else
        warn "✗ dbus not available (may need manual installation)"
    fi
    
    if python3 -c "import gi" 2>/dev/null; then
        log "✓ PyGObject available"
    else
        warn "✗ PyGObject not available (may need manual installation)"
    fi
    
    log "Installation test completed"
    
    # Test Python path configuration
    log "Testing Python path configuration..."
    if python3 -c "
import sys
sys.path.insert(0, '$INSTALL_DIR/velib_python')
sys.path.insert(0, '$INSTALL_DIR/mpp-solar')
try:
    import velib_python.vedbus
    print('✓ velib_python import successful')
except ImportError as e:
    print(f'✗ velib_python import failed: {e}')
try:
    import mppsolar
    print('✓ mppsolar import successful')
except ImportError as e:
    print(f'✗ mppsolar import failed: {e}')
" 2>/dev/null; then
        log "✓ Python path test completed"
    else
        warn "Python path test failed - check manually"
    fi
}

# Restart services and start mppsolar
restart_and_start_services() {
    log "Restarting services and starting mppsolar..."
    
    # Restart serial-starter to pick up new configuration
    if [[ -d "/service/serial-starter" ]]; then
        log "Restarting serial-starter..."
        # Use the correct svc syntax for this system
        log "Stopping serial-starter with: svc -d /service/serial-starter"
        svc -d /service/serial-starter
        sleep 2
        log "Starting serial-starter with: svc -u /service/serial-starter"
        svc -u /service/serial-starter
        log "✓ Serial-starter restarted"
        
        # Wait for serial-starter to fully restart
        log "Waiting for serial-starter to fully restart..."
        sleep 5
    else
        warn "Serial-starter service not found - may need manual restart"
    fi
    
    # Remove any existing mppsolar service instances
    for service in /service/dbus-mppsolar.*; do
        if [[ -d "$service" ]]; then
            log "Removing existing service instance: $service"
            svc -d "$service"
            rm -rf "$service"
        fi
    done
    
    # Check for available TTY devices
    log "Checking for available TTY devices..."
    TTY_DEVICES=()
    for device in /dev/ttyUSB* /dev/ttyACM*; do
        if [[ -e "$device" ]]; then
            TTY_DEVICES+=("$device")
            log "Found TTY device: $device"
        fi
    done
    
    if [[ ${#TTY_DEVICES[@]} -eq 0 ]]; then
        warn "No TTY devices found. Please connect your MPP Solar inverter via USB."
        log "The service will start automatically when a TTY device is connected."
    else
        log "Found ${#TTY_DEVICES[@]} TTY device(s). Starting mppsolar service..."
        
        # Start mppsolar service for each TTY device
        for device in "${TTY_DEVICES[@]}"; do
            DEVICE_NAME=$(basename "$device")
            log "Starting mppsolar service for $DEVICE_NAME..."
            
            # Create service directory
            SERVICE_DIR="/service/dbus-mppsolar.$DEVICE_NAME"
            mkdir -p "$SERVICE_DIR"
            
            # Create service run script
            cat > "$SERVICE_DIR/run" << EOF
#!/bin/sh
echo "*** starting mppsolar service for $DEVICE_NAME ***"
exec 2>&1
exec /data/etc/dbus-mppsolar/start-dbus-mppsolar.sh $DEVICE_NAME
EOF
            
            # Create service log script
            mkdir -p "$SERVICE_DIR/log"
            cat > "$SERVICE_DIR/log/run" << EOF
#!/bin/sh
exec 2>&1
exec multilog t s25000 n4 /var/log/mppsolar.$DEVICE_NAME
EOF
            
            # Make scripts executable
            chmod +x "$SERVICE_DIR/run"
            chmod +x "$SERVICE_DIR/log/run"
            
            # Start the service
            svc -u "$SERVICE_DIR"
            log "✓ Started mppsolar service for $DEVICE_NAME"
            
            # Wait a moment for service to start
            sleep 2
            
            # Check service status
            if svstat "$SERVICE_DIR" | grep -q "up"; then
                log "✓ Service for $DEVICE_NAME is running"
            else
                warn "Service for $DEVICE_NAME failed to start - check logs"
            fi
        done
    fi
    
    log "✓ Services restarted and mppsolar started"
}

# Test service functionality
test_service_functionality() {
    log "Testing service functionality..."
    
    # Check if any mppsolar services are running
    RUNNING_SERVICES=()
    for service in /service/dbus-mppsolar.*; do
        if [[ -d "$service" ]]; then
            if svstat "$service" | grep -q "up"; then
                RUNNING_SERVICES+=("$service")
                log "✓ Service $service is running"
            else
                warn "Service $service is not running"
            fi
        fi
    done
    
    if [[ ${#RUNNING_SERVICES[@]} -eq 0 ]]; then
        warn "No mppsolar services are currently running"
        return 1
    fi
    
    # Test DBus service availability
    log "Testing DBus service availability..."
    if command -v dbus-send &> /dev/null; then
        # Wait a bit for services to fully initialize
        sleep 3
        
        # Check for mppsolar DBus services
        DBUS_SERVICES=$(dbus-send --system --dest=org.freedesktop.DBus --type=method_call --print-reply /org/freedesktop/DBus org.freedesktop.DBus.ListNames 2>/dev/null | grep -i mppsolar || echo "")
        
        if [[ -n "$DBUS_SERVICES" ]]; then
            log "✓ DBus services found: $DBUS_SERVICES"
        else
            log "DBus services not yet available (may take a few minutes to initialize)"
        fi
    else
        warn "dbus-send not available - cannot test DBus services"
    fi
    
    log "Service functionality test completed"
}

# Display post-installation information
show_post_install_info() {
    echo
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Installation & Startup Completed!${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    echo -e "${GREEN}What was installed and started:${NC}"
    echo "• Main script: $INSTALL_DIR/dbus-mppsolar.py"
    echo "• Service template: $SERVICE_TEMPLATE_DIR/"
    echo "• Serial starter config: /opt/victronenergy/serial-starter/mppsolar.conf"
    echo "• Python modules: velib_python and mpp-solar (included)"
    echo "• Active services: $(ls -d /service/dbus-mppsolar.* 2>/dev/null | wc -l) mppsolar service(s)"
    echo
    echo -e "${GREEN}Current Status:${NC}"
    
    # Show running services
    RUNNING_COUNT=0
    for service in /service/dbus-mppsolar.*; do
        if [[ -d "$service" ]]; then
            if svstat "$service" | grep -q "up"; then
                echo "• $(basename "$service"): ✅ RUNNING"
                ((RUNNING_COUNT++))
            else
                echo "• $(basename "$service"): ❌ STOPPED"
            fi
        fi
    done
    
    if [[ $RUNNING_COUNT -eq 0 ]]; then
        echo "• No services currently running"
    fi
    
    echo
    echo -e "${GREEN}Monitoring:${NC}"
    echo "• Service logs: tail -f /var/log/mppsolar.*/current"
    echo "• Serial starter logs: tail -f /var/log/serial-starter/current"
    echo "• Check for mppsolar detection: grep -i mppsolar /var/log/serial-starter/current"
    echo
    echo -e "${GREEN}Venus OS Integration:${NC}"
    echo "• The inverter should appear in the Venus OS dashboard within a few minutes"
    echo "• DBus service will be available at com.victronenergy.multi.ttyUSB0"
    echo "• Real-time inverter data will be accessible through DBus"
    echo
    echo -e "${GREEN}Troubleshooting:${NC}"
    echo "• Check service status: svstat /service/dbus-mppsolar.*"
    echo "• Manual test: python3 $INSTALL_DIR/dbus-mppsolar.py --serial /dev/ttyUSB0 --log-level DEBUG"
    echo "• Restart serial-starter: svc -r /service/serial-starter"
    echo "• Check TTY devices: ls -la /dev/ttyUSB*"
    echo
    echo -e "${GREEN}Next Steps:${NC}"
    echo "1. Check the Venus OS interface for inverter recognition"
    echo "2. Monitor the service logs for any errors"
    echo "3. Verify DBus service is accessible"
    echo "4. Test inverter communication and data retrieval"
    echo
    echo -e "${GREEN}Backup location:${NC}"
    echo "• Previous installation backed up to: $BACKUP_DIR"
    echo
}

# Main installation function
main() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  dbus-mppsolar Complete Deployment Script${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    
    # Run essential checks
    check_root
    check_venusos
    check_requirements
    
    # Core installation steps
    clean_installation
    clone_repository
    install_service_template
    configure_serial_starter
    set_permissions
    
    # Test installation
    test_installation || warn "Installation test failed - check manually"
    
    # Restart services and start mppsolar
    restart_and_start_services
    
    # Test service functionality
    test_service_functionality || warn "Service functionality test failed - check manually"
    
    # Show completion info
    show_post_install_info
}

# Run main function
main "$@"
