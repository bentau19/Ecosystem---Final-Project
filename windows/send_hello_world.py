"""
Simple function to send "hello world" to Android using TauSync
"""

from tausync_client import TauSyncClient

def send_hello_world(android_ip):
    """
    Sends "hello world" to Android device using TauSync protocol.
    
    Args:
        android_ip: IP address of the Android device
    """
    client = TauSyncClient(android_ip)
    
    try:
        # Connect to Android
        client.connect()
        
        # Send "hello world"
        client.send_message("hello world")
        
        print("✓ Successfully sent 'hello world' to Android!")
        
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python send_hello_world.py <android_ip>")
        print("Example: python send_hello_world.py 192.168.1.100")
        sys.exit(1)
    
    android_ip = sys.argv[1]
    send_hello_world(android_ip)
