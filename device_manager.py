import json
import os

DEVICE_FILE = "devices.json"

def load_devices():
    """Load device data from JSON file."""
    if not os.path.exists(DEVICE_FILE):
        return []
    
    with open(DEVICE_FILE, "r") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            return []

def save_devices(devices):
    """Save device data to JSON file."""
    with open(DEVICE_FILE, "w") as file:
        json.dump(devices, file, indent=4)

def add_device(device_id, device_name, address):
    """Add a new device to the JSON file."""
    devices = load_devices()
    
    # Check if device_id already exists
    for device in devices:
        if device['device_id'] == device_id:
            return False  # Device ID must be unique
    
    devices.append({"device_id": device_id, "device_name": device_name, "address": address})
    save_devices(devices)
    return True

def update_device(device_id, device_name, address):
    """Update an existing device."""
    devices = load_devices()
    for device in devices:
        if device['device_id'] == device_id:
            device['device_name'] = device_name
            device['address'] = address
            save_devices(devices)
            return True
    return False

def get_devices():
    """Get all devices."""
    return load_devices()
