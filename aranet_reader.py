import asyncio
import os
from datetime import datetime, UTC
import json
import signal
import sys
from bleak import BleakScanner, BleakClient
from dotenv import load_dotenv
import aiohttp
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Load environment variables
load_dotenv()

# Configuration with validation
required_configs = {
    'API_ENDPOINT': os.getenv('API_ENDPOINT'),
    'API_KEY': os.getenv('API_KEY'),
    'DEVICE_ID': os.getenv('DEVICE_ID'),
    'TARGET_DEVICE': os.getenv('TARGET_DEVICE'),
    'POLLING_INTERVAL': int(os.getenv('POLLING_INTERVAL', 1800)),  # Default to 1800 if not set
}

# Validate required configurations
missing_configs = [key for key, value in required_configs.items() 
                  if value is None or (key != 'POLLING_INTERVAL' and not value)]
if missing_configs:
    print("Error: Missing required configuration values:")
    for config in missing_configs:
        print(f"- {config}")
    print("\nPlease set these variables in your .env file")
    sys.exit(1)

try:
    # Ensure POLLING_INTERVAL is a valid positive integer
    if required_configs['POLLING_INTERVAL'] <= 0:
        print("Error: POLLING_INTERVAL must be a positive number")
        sys.exit(1)
except (ValueError, TypeError):
    print("Error: POLLING_INTERVAL must be a valid number")
    sys.exit(1)

CONFIG = required_configs

# Aranet4 specific UUIDs
ARANET4_SERVICE_UUID = "f0cd1400-95da-4f4b-9ac8-aa55d312af0c"
ARANET4_CURRENT_READINGS_UUID = "f0cd1503-95da-4f4b-9ac8-aa55d312af0c"

def parse_current_readings(data: bytearray) -> dict:
    """Parse the raw sensor data into readable values."""
    try:
        co2 = int.from_bytes(data[0:2], byteorder='little')
        temperature = int.from_bytes(data[2:4], byteorder='little', signed=True) / 20
        pressure = int.from_bytes(data[4:6], byteorder='little') / 10
        humidity = data[6]
        timestamp = datetime.now(UTC).isoformat()
        
        return {
            'co2': co2,
            'temperature': temperature,
            'humidity': humidity,
            'pressure': pressure,
            'timestamp': timestamp
        }
    except Exception as e:
        raise Exception(f"Failed to parse sensor data: {str(e)}")

async def post_to_server(readings: dict) -> bool:
    """Post readings to the server."""
    try:
        payload = {
            'deviceId': CONFIG['DEVICE_ID'],
            'readings': readings
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                CONFIG['API_ENDPOINT'],
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'X-API-Key': CONFIG['API_KEY']
                }
            ) as response:
                if response.status == 200:
                    print('Successfully posted to server')
                    return True
                else:
                    print(f'Server responded with status: {response.status}')
                    return False
    except Exception as e:
        print(f'Error posting to server: {str(e)}')
        return False

async def send_error_email(error: Exception):
    """Send error notification email."""
    try:
        sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
        message = Mail(
            from_email=os.getenv('EMAIL_FROM'),
            to_emails=os.getenv('EMAIL_TO'),
            subject=f"Aranet Reader Error - {CONFIG['DEVICE_ID']}",
            plain_text_content=f"""
Error Report from Aranet Reader

Time: {datetime.now(UTC).isoformat()}
Device: {CONFIG['DEVICE_ID']}
Location: {CONFIG['DEVICE_ID'].replace('aranet4-', '')}

Error Details:
{str(error)}

System Info:
- Python Version: {sys.version}
- Platform: {sys.platform}
- Process ID: {os.getpid()}

Please check the device and restart if necessary.
            """
        )
        response = sg.send(message)
        if response.status_code == 202:
            print('Error notification email sent successfully')
    except Exception as e:
        print(f'Failed to send error notification email: {str(e)}')

async def find_aranet4():
    """Scan for Aranet4 devices."""
    print("Scanning for Aranet4 devices...")
    
    # Try multiple scans if needed
    for _ in range(3):
        devices = await BleakScanner.discover(timeout=5.0)
        for device in devices:
            if device.name and device.name == CONFIG['TARGET_DEVICE']:
                print(f"Found target device: {device.name}")
                return device
            elif device.name and 'Aranet4' in device.name:
                print(f"Found other Aranet4 device: {device.name}")
        
        await asyncio.sleep(1)  # Brief delay between scans
    
    return None

async def pair_device(device):
    """Pair with Aranet4 device using PIN code."""
    try:
        print("Initiating pairing with device...")
        import subprocess
        
        # First initiate the pairing request
        pair_cmd = f'echo -e "pair {device.address}\\n" | bluetoothctl'
        subprocess.run(pair_cmd, shell=True, check=True)
        
        # Wait a moment for the device to show the PIN
        await asyncio.sleep(2)
        
        print("\nA PIN should now be displayed on your Aranet4 device.")
        print("Enter the PIN shown on the device:")
        pin = input().strip()
        
        if not pin:
            raise Exception("PIN cannot be empty")
        
        # Confirm the pairing with the PIN
        confirm_cmd = f'echo -e "{pin}\\nyes\\n" | bluetoothctl'
        subprocess.run(confirm_cmd, shell=True, check=True)
        
        # Wait for pairing to complete
        await asyncio.sleep(2)
        
        # Trust the device for future connections
        trust_cmd = f'echo -e "trust {device.address}\\n" | bluetoothctl'
        subprocess.run(trust_cmd, shell=True, check=True)
        
        print("Device paired successfully!")
        return True
    except Exception as e:
        print(f"Failed to pair device: {str(e)}")
        return False

async def read_sensor():
    """Read data from the Aranet4 sensor."""
    max_retries = 3
    retry_delay = 5
    connect_delay = 2
    disconnect_retry = 3
    
    for attempt in range(max_retries):
        device = None
        client = None
        try:
            device = await find_aranet4()
            if not device:
                raise Exception("No Aranet4 device found!")
            
            try:
                # Attempt to pair if needed
                if os.getenv('ARANET_NEEDS_PAIRING', 'false').lower() == 'true':
                    if not await pair_device(device):
                        raise Exception("Failed to pair with device")
                    # Set the flag to false after successful pairing
                    os.environ['ARANET_NEEDS_PAIRING'] = 'false'
                
                client = BleakClient(
                    device, 
                    timeout=20.0,
                    disconnected_callback=lambda c: print("Device disconnected!")
                )
                
                # Try to connect multiple times if needed
                connect_attempts = 3
                for connect_try in range(connect_attempts):
                    try:
                        await client.connect()
                        print(f"Connected to {device.name}")
                        break
                    except Exception as connect_error:
                        if connect_try == connect_attempts - 1:
                            raise
                        print(f"Connection attempt {connect_try + 1} failed: {str(connect_error)}")
                        await asyncio.sleep(2)
                
                # Add delay after connection
                await asyncio.sleep(connect_delay)
                
                # Use the services property instead of get_services()
                print("Discovering services...")
                if not client.is_connected:
                    raise Exception("Lost connection before service discovery")
                
                # Find our service
                aranet_service = None
                for service in client.services:
                    if service.uuid == ARANET4_SERVICE_UUID:
                        aranet_service = service
                        break
                
                if not aranet_service:
                    raise Exception("Aranet4 service not found")
                
                # Get the characteristic
                for char in aranet_service.characteristics:
                    if char.uuid == ARANET4_CURRENT_READINGS_UUID:
                        # Verify connection before reading
                        if not client.is_connected:
                            raise Exception("Lost connection before reading characteristic")
                            
                        data = await client.read_gatt_char(char.uuid)
                        readings = parse_current_readings(data)
                        
                        # Print readings
                        current_time = datetime.now().strftime("%I:%M:%S %p")
                        print(f"\n[{current_time}] Readings:")
                        print(f"CO2: {readings['co2']} ppm")
                        print(f"Temperature: {readings['temperature']:.1f}°C")
                        print(f"Humidity: {readings['humidity']}%")
                        print(f"Pressure: {readings['pressure']:.1f} hPa")
                        
                        return readings
                
                raise Exception("Reading characteristic not found")
                
            finally:
                if client:
                    # Try multiple times to disconnect cleanly
                    for _ in range(disconnect_retry):
                        try:
                            if client.is_connected:
                                await client.disconnect()
                                print("Disconnected from device")
                                await asyncio.sleep(1)
                            break
                        except Exception as disconnect_error:
                            print(f"Disconnect attempt failed: {str(disconnect_error)}")
                            await asyncio.sleep(1)
                    
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                print(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                raise

async def power_cycle_bluetooth():
    """Power cycle the Bluetooth adapter."""
    try:
        print("Power cycling Bluetooth adapter...")
        import subprocess
        
        # Stop bluetooth service
        subprocess.run(['sudo', 'systemctl', 'stop', 'bluetooth'], check=True)
        await asyncio.sleep(2)
        
        # Power cycle the adapter
        subprocess.run(['sudo', 'rfkill', 'block', 'bluetooth'], check=True)
        await asyncio.sleep(2)
        subprocess.run(['sudo', 'rfkill', 'unblock', 'bluetooth'], check=True)
        await asyncio.sleep(2)
        
        # Start bluetooth service
        subprocess.run(['sudo', 'systemctl', 'start', 'bluetooth'], check=True)
        await asyncio.sleep(5)  # Give more time for service to fully start
        
        print("Bluetooth power cycle complete")
        return True
    except Exception as e:
        print(f"Failed to power cycle Bluetooth: {str(e)}")
        return False

# Update the reset_bluetooth function to use power cycle as a last resort
async def reset_bluetooth():
    """Reset the Bluetooth adapter."""
    try:
        print("Resetting Bluetooth adapter...")
        # First try soft reset
        import subprocess
        subprocess.run(['sudo', 'hciconfig', 'hci0', 'down'], check=True)
        await asyncio.sleep(2)
        subprocess.run(['sudo', 'hciconfig', 'hci0', 'up'], check=True)
        await asyncio.sleep(3)
        print("Bluetooth adapter reset complete")
        return True
    except Exception as e:
        print(f"Soft reset failed: {str(e)}")
        print("Attempting power cycle...")
        return await power_cycle_bluetooth()

async def main_loop():
    """Main program loop."""
    consecutive_failures = 0
    max_failures_before_reset = 3

    if os.getenv('TEST_EMAIL') == 'true':
        await send_error_email(Exception("Test email"))
        return

    while True:
        try:
            print('Starting new reading cycle...')
            readings = await read_sensor()
            success = await post_to_server(readings)
            
            if success:
                consecutive_failures = 0  # Reset failure counter
                print(f"\nWaiting {CONFIG['POLLING_INTERVAL']} seconds until next reading...")
                await asyncio.sleep(CONFIG['POLLING_INTERVAL'])
            else:
                consecutive_failures += 1
                await send_error_email(Exception("Failed to post readings to server"))
                await asyncio.sleep(30)
                
        except Exception as e:
            consecutive_failures += 1
            print(f'Error during reading: {str(e)}')
            
            if consecutive_failures >= max_failures_before_reset:
                print("Too many consecutive failures, attempting Bluetooth reset...")
                if await reset_bluetooth():
                    consecutive_failures = 0
                await asyncio.sleep(5)
            
            await send_error_email(e)
            await asyncio.sleep(30)

def signal_handler(sig, frame):
    """Handle cleanup on program exit."""
    print('\nCleaning up...')
    sys.exit(0)

if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the main loop
    asyncio.run(main_loop()) 