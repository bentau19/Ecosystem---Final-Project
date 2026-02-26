
import sys
import os
import time
import socket
import struct
# 1. ייבוא פונקציית הטעינה של pythonnet
from pythonnet import load

# 2. הכרחת הפייתון להשתמש ב-CoreCLR (עבור .NET 5, 6, 7, 8)
# זה חייב לקרות לפני import clr
try:
    load("coreclr")
except Exception as e:
    print(f"Note: CoreCLR load status: {e}")

# כעת אפשר לייבא את clr כרגיל
try:
    import clr
except ImportError:
    print("Error: pythonnet is not installed. Install it with: pip install pythonnet")
    sys.exit(1)

# ניהול נתיבים
script_dir = os.path.dirname(os.path.abspath(__file__))
dll_path = os.path.join(script_dir, "..", "..", "TauSync", "windows", "TauSync.Lib", "bin", "Debug", "net8.0", "TauSync.Lib.dll")
dll_path = os.path.abspath(dll_path)

if not os.path.exists(dll_path):
    print(f"Error: DLL not found at {dll_path}")
    print("Please build the C# project first: dotnet build ../TauSync/windows/TauSync.Lib/TauSync.Lib.csproj")
    sys.exit(1)

# הוספת הרפרנס
clr.AddReference(dll_path)

# ייבוא המחלקה מתוך ה-Namespace
from TauSync.Implementations.Management import ConnectionManager  # pyright: ignore[reportMissingImports]
from TauSync.Implementations.Transport import SocketTransport  # pyright: ignore[reportMissingImports]
from System import Action, Array, Byte

def handle_interrupt(data):
    """This Python function will be called when an interrupt is received by the server"""
    # Convert System.Byte[] to Python bytes
    python_bytes = bytes(data) if hasattr(data, '__iter__') else data
    
    # Try to decode as string, or print as binary
    try:
        text = python_bytes.decode('utf-8')
        print(f"📨 Interrupt received by server: {text}")
    except:
        print(f"📨 Interrupt received by server: {len(python_bytes)} bytes")

def send_interrupt_via_socket(client_socket, message):
    """Send an unsolicited interrupt message via Python socket.
    
    Protocol format: [4-byte Length (Big-Endian)][16-byte CorrelationID][Payload]
    For unsolicited messages, correlation ID is 16 bytes of zeros.
    """
    try:
        print(f"Sending interrupt message: {message}")
        
        # Create interrupt message (unsolicited = all zeros correlation ID)
        interrupt_data = message.encode('utf-8')
        
        # Prepend 16 bytes of zeros (correlation ID header for unsolicited messages)
        # Protocol: [4-byte Length][16-byte CorrelationID][Payload]
        correlation_id_header = bytes(16)  # 16 bytes of zeros
        message_with_header = correlation_id_header + interrupt_data
        
        # Calculate total length (16-byte header + payload)
        total_length = len(message_with_header)
        
        # Send length prefix (4 bytes, Big-Endian/Network Byte Order)
        length_bytes = struct.pack('>I', total_length)  # '>I' = Big-Endian unsigned int (4 bytes)
        client_socket.sendall(length_bytes)
        
        # Send the message with header
        client_socket.sendall(message_with_header)
        
        print(f"✅ Interrupt sent successfully: {message}")
        
    except Exception as e:
        print(f"Error sending interrupt: {e}")

def startTest():
    # Create Action<byte[]> from Python function
    action = Action[Array[Byte]](handle_interrupt)
    
    # Create ConnectionManager with Python callback (this is the SERVER)
    connectionManager = ConnectionManager(action)
    print("✅ ConnectionManager (SERVER) created with Python callback!")
    print("   When an interrupt arrives, 'handle_interrupt' will be called automatically")
    
    # Create SocketTransport for the server
    
    # Wait a bit for server to be ready
    time.sleep(0.5)
    
    # Now create CLIENT using Python socket (not SocketTransport)
    print("\n🔌 Creating CLIENT using Python socket to send interrupt...")
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        server_ip = "127.0.0.1"
        server_port = 8888
        print(f"Connecting to {server_ip}:{server_port}...")
        client_socket.connect((server_ip, server_port))
        print("✅ Client connected to server!")
        
        # Wait a bit for connection to stabilize
        time.sleep(0.3)
        
        # Send interrupt message from client to server
        interrupt_message = "Hello from Python Client! This is an interrupt!"
        print(f"\n📤 Sending interrupt from client: '{interrupt_message}'")
        send_interrupt_via_socket(client_socket, interrupt_message)
        
        # Wait a bit for the interrupt to be received and processed
        print("\n⏳ Waiting for server to receive interrupt...")
        time.sleep(1.0)
        
    except ConnectionRefusedError:
        print("❌ Error: The server is not running or the port is blocked.")
    except Exception as e:
        print(f"❌ Error occurred: {e}")
    finally:
        # Cleanup
        client_socket.close()
        print("\n✅ Test completed!")
        print("   Check above for 'Interrupt received by server' message")


if __name__ == "__main__":
    startTest()