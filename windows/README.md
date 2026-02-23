# TauSync Python Client

Python client for communicating with Android app using TauSync protocol.

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Send a message to Android:
```bash
python tausync_client.py <android_ip> "Hello from Python!"
```

### Receive messages from Android:
```bash
python tausync_client.py <android_ip>
```

## Example

```python
from tausync_client import TauSyncClient

# Create client
client = TauSyncClient("192.168.1.100")  # Android device IP

# Connect
client.connect()

# Send message
client.send_message("Hello Android!")

# Receive message
message = client.receive_message(timeout=5.0)
print(f"Received: {message}")

# Disconnect
client.disconnect()
```

## Notes

- Both devices must use the same shared key for encryption
- Default port is 8888
- The Android app must be running and listening for connections
