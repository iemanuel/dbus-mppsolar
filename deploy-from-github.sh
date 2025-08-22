#!/bin/bash

# One-liner deployment script for dbus-mppsolar from GitHub
# Usage: curl -sSL https://raw.githubusercontent.com/iemanuel/dbus-mppsolar/main/deploy.sh | sudo bash

echo "Downloading and running dbus-mppsolar deployment script from GitHub..."

# Download the deployment script from GitHub
curl -sSL https://raw.githubusercontent.com/iemanuel/dbus-mppsolar/main/deploy.sh | bash
