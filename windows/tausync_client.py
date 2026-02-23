"""
TauSync Python Client for Windows (No Encryption)
Simple client to send/receive messages via TauSync protocol
"""

import socket
import json
import struct

class TauSyncClient:
    """Simple Python client for TauSync protocol (no encryption)"""
    
    DEFAULT_PORT = 8888
    MAGIC_BYTES = 0x54415553  # "TAUS" in ASCII
    VERSION = 1
    
    def __init__(self, target_ip, port=DEFAULT_PORT):
        """
        Initialize TauSync client.
        
        Args:
            target_ip: IP address of Android device
            port: Port number (default 8888)
        """
        self.target_ip = target_ip
        self.port = port
        self.socket = None
        self.connected = False
    
    def connect(self):
        """Connect to Android device"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.target_ip, self.port))
            self.connected = True
            print(f"Connected to {self.target_ip}:{self.port}")
        except Exception as e:
            self.connected = False
            raise ConnectionError(f"Failed to connect: {e}")
    
    def disconnect(self):
        """Disconnect from Android device"""
        if self.socket:
            self.socket.close()
            self.connected = False
            print("Disconnected")
    
    def send_message(self, message):
        """
        Send a text message to Android device.
        
        Args:
            message: Text message to send
        """
        if not self.connected:
            raise ConnectionError("Not connected. Call connect() first.")
        
        # Convert message to bytes
        payload = message.encode('utf-8')
        
        # Create TransferRequest (no encryption)
        request = {
            "MagicBytes": self.MAGIC_BYTES,
            "Version": self.VERSION,
            "Payload": list(payload),  # Convert to list for JSON
            "Priority": 0,
            "IsCompressed": False,
            "CryptoIV": []  # Empty - no encryption
        }
        
        # Serialize to JSON
        json_data = json.dumps(request)
        json_bytes = json_data.encode('utf-8')
        
        # Send via socket (length + data)
        try:
            # Send length (4 bytes, big-endian)
            self.socket.sendall(struct.pack('>I', len(json_bytes)))
            # Send data
            self.socket.sendall(json_bytes)
            print(f"Message sent: {message}")
        except Exception as e:
            raise ConnectionError(f"Failed to send message: {e}")
    
    def receive_message(self, timeout=None):
        """
        Receive a message from Android device.
        
        Args:
            timeout: Socket timeout in seconds (None for blocking)
        
        Returns:
            Decrypted message string or None if timeout
        """
        if not self.connected:
            raise ConnectionError("Not connected. Call connect() first.")
        
        if timeout:
            self.socket.settimeout(timeout)
        
        try:
            # Read length (4 bytes)
            length_data = self.socket.recv(4)
            if len(length_data) != 4:
                return None
            
            data_length = struct.unpack('>I', length_data)[0]
            
            # Read JSON data
            json_bytes = b''
            while len(json_bytes) < data_length:
                chunk = self.socket.recv(data_length - len(json_bytes))
                if not chunk:
                    return None
                json_bytes += chunk
            
            # Parse JSON
            request = json.loads(json_bytes.decode('utf-8'))
            
            # Validate
            if request.get("MagicBytes") != self.MAGIC_BYTES:
                raise ValueError("Invalid magic bytes")
            if request.get("Version") != self.VERSION:
                raise ValueError("Invalid version")
            
            # Get payload (no decryption needed)
            payload_bytes = bytes(request["Payload"])
            
            # Convert to string
            message = payload_bytes.decode('utf-8')
            print(f"Message received: {message}")
            return message
            
        except socket.timeout:
            return None
        except Exception as e:
            raise ConnectionError(f"Failed to receive message: {e}")


def send_hello_world(android_ip):
    """
    Simple function to send "hello world" to Android using TauSync.
    
    Args:
        android_ip: IP address of Android device
    """
    client = TauSyncClient(android_ip)
    
    try:
        # Connect
        client.connect()
        
        # Send "hello world"
        client.send_message("hello world")
        
        print("Successfully sent 'hello world' to Android!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.disconnect()


def receive_hello_world(android_ip):
    """
    Simple function to receive messages from Android using TauSync.
    
    Args:
        android_ip: IP address of Android device
    """
    client = TauSyncClient(android_ip)
    
    try:
        # Connect
        client.connect()
        
        # Receive message
        print("Waiting for message from Android...")
        message = client.receive_message(timeout=10.0)
        
        if message:
            print(f"Received from Android: {message}")
        else:
            print("No message received (timeout)")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python tausync_client.py <android_ip> [send|receive]")
        print("Example: python tausync_client.py 192.168.1.100 send")
        sys.exit(1)
    
    android_ip = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "send"
    
    if mode == "send":
        send_hello_world(android_ip)
    elif mode == "receive":
        receive_hello_world(android_ip)
    else:
        print("Invalid mode. Use 'send' or 'receive'")
