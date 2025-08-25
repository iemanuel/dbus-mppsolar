#!/bin/bash

# Deploy mppsolar service template to Venus OS
# This script should be run on the Raspberry Pi system

echo "Deploying mppsolar service template..."

# Create service template directory
SERVICE_TEMPLATE_DIR="/opt/victronenergy/service-templates/mppsolar"
mkdir -p "$SERVICE_TEMPLATE_DIR"

# Copy service template files
cp service-template/run "$SERVICE_TEMPLATE_DIR/"
cp -r service-template/log "$SERVICE_TEMPLATE_DIR/"

# Make scripts executable
chmod +x "$SERVICE_TEMPLATE_DIR/run"
chmod +x "$SERVICE_TEMPLATE_DIR/log/run"

# Create log directory
mkdir -p /var/log/mppsolar.TTY

# Restart serial-starter to pick up new template
echo "Restarting serial-starter..."
svc -r /service/serial-starter

echo "Service template deployed successfully!"
echo "The mppsolar service should now be detected by the serial-starter."
echo "Check /var/log/serial-starter/current for any errors."
