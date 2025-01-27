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
  <policy user="$USER">
    <allow own="org.bluez"/>
    <allow send_destination="org.bluez"/>
    <allow send_interface="org.bluez.GattCharacteristic1"/>
    <allow send_interface="org.bluez.GattDescriptor1"/>
    <allow send_interface="org.freedesktop.DBus.ObjectManager"/>
    <allow send_interface="org.freedesktop.DBus.Properties"/>
  </policy>
</busconfig>
EOL

# Restart bluetooth service
sudo systemctl restart bluetooth

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Set up Bluetooth permissions
sudo setcap 'cap_net_raw,cap_net_admin+eip' $(readlink -f $(which python3))

echo "Setup complete! You can now run the reader with: python aranet_reader.py" 