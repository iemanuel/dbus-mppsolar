#!/bin/bash

# Direct deployment script for dbus-mppsolar from GitHub
# This script can be run directly or downloaded and executed

set -e

# Default configuration
DEFAULT_REPO="iemanuel/dbus-mppsolar"
DEFAULT_BRANCH="main"
DEFAULT_SCRIPT="deploy.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Function to show usage
show_usage() {
    echo -e "${BLUE}Usage:${NC}"
    echo "  $0 [options]"
    echo
    echo -e "${BLUE}Options:${NC}"
    echo "  -r, --repo REPO     GitHub repository (default: $DEFAULT_REPO)"
    echo "  -b, --branch BRANCH GitHub branch (default: $DEFAULT_BRANCH)"
    echo "  -s, --script SCRIPT Script name to run (default: $DEFAULT_SCRIPT)"
    echo "  -h, --help          Show this help message"
    echo
    echo -e "${BLUE}Examples:${NC}"
    echo "  $0                                    # Use defaults"
    echo "  $0 -r username/repo -b develop       # Custom repo and branch"
    echo "  $0 --repo username/repo --branch main # Long form options"
    echo
    echo -e "${BLUE}One-liner usage:${NC}"
    echo "  curl -sSL https://raw.githubusercontent.com/$DEFAULT_REPO/$DEFAULT_BRANCH/$DEFAULT_SCRIPT | sudo bash"
    echo "  wget -qO- https://raw.githubusercontent.com/$DEFAULT_REPO/$DEFAULT_BRANCH/$DEFAULT_SCRIPT | sudo bash"
}

# Parse command line arguments
REPO="$DEFAULT_REPO"
BRANCH="$DEFAULT_BRANCH"
SCRIPT="$DEFAULT_SCRIPT"

while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--repo)
            REPO="$2"
            shift 2
            ;;
        -b|--branch)
            BRANCH="$2"
            shift 2
            ;;
        -s|--script)
            SCRIPT="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_usage
            exit 1
            ;;
    esac
done

# Construct the GitHub raw URL
GITHUB_RAW_URL="https://raw.githubusercontent.com/$REPO/$BRANCH/$SCRIPT"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  dbus-mppsolar Direct Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo
echo -e "${GREEN}Repository:${NC} $REPO"
echo -e "${GREEN}Branch:${NC} $BRANCH"
echo -e "${GREEN}Script:${NC} $SCRIPT"
echo -e "${GREEN}URL:${NC} $GITHUB_RAW_URL"
echo

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Check if running on VenusOS
if [[ ! -d "/opt/victronenergy" ]]; then
    echo -e "${RED}This script is designed for VenusOS. Please run on a VenusOS system.${NC}"
    exit 1
fi

# Check if curl is available
if ! command -v curl &> /dev/null; then
    echo -e "${RED}curl is not installed. Installing...${NC}"
    /opt/victronenergy/swupdate-scripts/set-feed.sh release
    opkg update
    opkg install curl
fi

echo -e "${YELLOW}Downloading deployment script from GitHub...${NC}"

# Download and execute the script
if curl -sSL "$GITHUB_RAW_URL" | bash; then
    echo -e "${GREEN}Deployment completed successfully!${NC}"
else
    echo -e "${RED}Deployment failed!${NC}"
    echo -e "${YELLOW}You can try downloading the script manually:${NC}"
    echo "  curl -sSL $GITHUB_RAW_URL > deploy.sh"
    echo "  sudo bash deploy.sh"
    exit 1
fi
