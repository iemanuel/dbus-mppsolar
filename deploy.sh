#!/bin/bash

# dbus-mppsolar Deployment Script for VenusOS
# This script automates the installation process from GitHub

set -e  # Exit on any error

# Configuration
REPO_URL="https://github.com/iemanuel/dbus-mppsolar"
INSTALL_DIR="/data/etc/dbus-mppsolar"
SERVICE_TEMPLATE_DIR="/opt/victronenergy/service-templates/dbus-mppsolar"
SERIAL_STARTER_CONF="/etc/venus/serial-starter.conf"
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

# Backup existing installation
backup_existing() {
    if [[ -d "$INSTALL_DIR" ]]; then
        log "Backing up existing installation to $BACKUP_DIR"
        mkdir -p "$BACKUP_DIR"
        cp -R "$INSTALL_DIR"/* "$BACKUP_DIR/"
        log "Backup completed"
    fi
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
        if [[ -d "$INSTALL_DIR/velib_python" ]]; then
            log "✓ velib_python submodule found"
        else
            warn "velib_python submodule not found - this may cause issues"
        fi
        
        # Check if mpp-solar submodule was cloned
        if [[ -d "$INSTALL_DIR/mpp-solar" ]]; then
            log "✓ mpp-solar submodule found"
        else
            warn "mpp-solar submodule not found - this may cause issues"
        fi
        
    else
        error "Failed to clone repository"
        error "Please check your internet connection and GitHub accessibility"
        exit 1
    fi
}

# Install service
install_service() {
    log "Installing service to VenusOS"
    
    # Create service template directory
    mkdir -p "$SERVICE_TEMPLATE_DIR"
    
    # Copy service files
    cp -R "$INSTALL_DIR/service"/* "$SERVICE_TEMPLATE_DIR/"
    
    # Make service files executable
    chmod +x "$SERVICE_TEMPLATE_DIR/run"
    chmod +x "$SERVICE_TEMPLATE_DIR/down"
    
    # Make main script executable
    chmod +x "$INSTALL_DIR/dbus-mppsolar.py"
    chmod +x "$INSTALL_DIR/start-dbus-mppsolar.sh"
    
    log "Service installed successfully"
}

# Configure serial starter
configure_serial_starter() {
    log "Configuring serial starter..."
    
    if [[ ! -f "$SERIAL_STARTER_CONF" ]]; then
        error "Serial starter configuration file not found: $SERIAL_STARTER_CONF"
        warn "You may need to manually configure the serial starter"
        return 1
    fi
    
    # Create backup of original config
    cp "$SERIAL_STARTER_CONF" "${SERIAL_STARTER_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Check if mppsolar service is already configured
    if grep -q "service mppsolar" "$SERIAL_STARTER_CONF"; then
        log "mppsolar service is already configured in serial starter"
        return 0
    fi
    
    # Add mppsolar service to the services section
    if grep -q "^service" "$SERIAL_STARTER_CONF"; then
        # Find the last service line and add mppsolar after it
        sed -i '/^service/a service mppsolar        dbus-mppsolar' "$SERIAL_STARTER_CONF"
        log "Added mppsolar service to serial starter configuration"
    else
        warn "Could not find services section in serial starter config"
        warn "You may need to manually add: service mppsolar        dbus-mppsolar"
    fi
    
    # Check if mppsolar is in the default alias
    if grep -q "alias.*default.*mppsolar" "$SERIAL_STARTER_CONF"; then
        log "mppsolar is already in default alias"
    else
        # Find the default alias line and add mppsolar to it
        if grep -q "^alias.*default" "$SERIAL_STARTER_CONF"; then
            sed -i 's/^alias.*default.*/&:mppsolar/' "$SERIAL_STARTER_CONF"
            log "Added mppsolar to default alias"
        else
            warn "Could not find default alias in serial starter config"
            warn "You may need to manually add mppsolar to the default alias"
        fi
    fi
}

# Install Python dependencies
install_dependencies() {
    log "Installing Python dependencies..."
    
    # Check if mpp-solar is already installed
    if python3 -c "import mppsolar" 2>/dev/null; then
        log "mpp-solar is already installed"
    else
        log "Installing mpp-solar..."
        pip3 install mppsolar
    fi
    
    # Install other required packages
    log "Installing additional Python packages..."
    pip3 install dbus-python PyGObject
}

# Set permissions
set_permissions() {
    log "Setting proper permissions..."
    
    # Set ownership to root
    chown -R root:root "$INSTALL_DIR"
    
    # Set executable permissions
    chmod +x "$INSTALL_DIR/dbus-mppsolar.py"
    chmod +x "$INSTALL_DIR/start-dbus-mppsolar.sh"
    
    # Set service permissions
    chmod +x "$SERVICE_TEMPLATE_DIR/run"
    chmod +x "$SERVICE_TEMPLATE_DIR/down"
}

# Test installation
test_installation() {
    log "Testing installation..."
    
    # Check if main script exists and is executable
    if [[ -x "$INSTALL_DIR/dbus-mppsolar.py" ]]; then
        log "✓ Main script is executable"
    else
        error "✗ Main script is not executable"
        return 1
    fi
    
    # Check if service files exist
    if [[ -f "$SERVICE_TEMPLATE_DIR/run" ]] && [[ -f "$SERVICE_TEMPLATE_DIR/down" ]]; then
        log "✓ Service files are installed"
    else
        error "✗ Service files are missing"
        return 1
    fi
    
    # Check if Python dependencies are available
    if python3 -c "import mppsolar, dbus, gi" 2>/dev/null; then
        log "✓ Python dependencies are available"
    else
        error "✗ Python dependencies are missing"
        return 1
    fi
    
    log "Installation test completed successfully"
}

# Display post-installation information
show_post_install_info() {
    echo
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Installation Completed Successfully!${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    echo -e "${GREEN}Next steps:${NC}"
    echo "1. Restart VenusOS or reconnect USB-Serial devices"
    echo "2. Check if the service starts automatically with USB connections"
    echo "3. Monitor logs at: $SERVICE_TEMPLATE_DIR/log/run"
    echo
    echo -e "${GREEN}Manual configuration (if needed):${NC}"
    echo "• Edit $SERIAL_STARTER_CONF to add mppsolar service"
    echo "• Add mppsolar to default alias: alias default mppsolar:gps:vedirect"
    echo
    echo -e "${GREEN}Troubleshooting:${NC}"
    echo "• Check service logs: tail -f $SERVICE_TEMPLATE_DIR/log/run"
    echo "• Restart service: svc -t $SERVICE_TEMPLATE_DIR"
    echo "• Check USB device detection: dmesg | grep tty"
    echo
    echo -e "${GREEN}Backup location:${NC}"
    echo "• Previous installation backed up to: $BACKUP_DIR"
    echo
}

# Main installation function
main() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  dbus-mppsolar Deployment Script${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    
    # Run checks
    check_root
    check_venusos
    check_requirements
    
    # Installation steps
    backup_existing
    clone_repository
    install_service
    configure_serial_starter
    install_dependencies
    set_permissions
    test_installation
    
    # Show completion info
    show_post_install_info
}

# Run main function
main "$@"
