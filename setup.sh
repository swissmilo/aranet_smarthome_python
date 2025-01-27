#!/bin/bash

# Install required system packages
sudo apt-get update
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    bluetooth \
    bluez \
    libbluetooth-dev

# Add user to bluetooth group
sudo usermod -a -G bluetooth $USER

# Create bluetooth configuration
sudo tee /etc/dbus-1/system.d/bluetooth.conf > /dev/null << EOL
<?xml version="1.0" encoding="UTF-8"?>
<busconfig>
  <policy user="root">
    <allow own="org.bluez"/>
    <allow send_destination="org.bluez"/>
  </policy>
  <policy user="$USER">
    <allow send_destination="org.bluez"/>
    <allow send_interface="org.bluez.GattCharacteristic1"/>
    <allow send_interface="org.bluez.GattDescriptor1"/>
    <allow send_interface="org.freedesktop.DBus.ObjectManager"/>
    <allow send_interface="org.freedesktop.DBus.Properties"/>
  </policy>
  <policy context="default">
    <deny send_destination="org.bluez"/>
  </policy>
</busconfig>
EOL

# Ensure bluetooth service is enabled and started
sudo systemctl enable bluetooth
sudo systemctl restart bluetooth

# Wait for bluetooth service to fully start
sleep 5

# Reset bluetooth adapter
sudo hciconfig hci0 down
sudo hciconfig hci0 up

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Set up Bluetooth permissions
sudo setcap 'cap_net_raw,cap_net_admin+eip' $(readlink -f $(which python3))

# Add bluetooth group to current session
newgrp bluetooth

echo "Setup complete! Please reboot your Raspberry Pi before running the program." 