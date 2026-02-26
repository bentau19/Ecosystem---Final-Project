"""
Example: Using Python callback for interrupt handling in ConnectionManager

This demonstrates how to pass a Python function to ConnectionManager constructor
that will be called when an interrupt (unsolicited small message) is received.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 1. Load CoreCLR for .NET 8
try:
    from pythonnet import load
    load("coreclr")
except Exception as e:
    print(f"ERROR: Failed to load coreclr: {e}")
    sys.exit(1)

# 2. Import clr
try:
    import clr
except ImportError:
    print("ERROR: pythonnet is not installed. Install with: pip install pythonnet")
    sys.exit(1)

# 3. Add reference to DLL
script_dir = os.path.dirname(os.path.abspath(__file__))
dll_path = os.path.join(script_dir, "..", "..", "TauSync", "windows", "TauSync.Lib", "bin", "Debug", "net8.0", "TauSync.Lib.dll")
dll_path = os.path.abspath(dll_path)

if not os.path.exists(dll_path):
    print(f"ERROR: DLL not found at {dll_path}")
    print("Please build the C# project first.")
    sys.exit(1)

clr.AddReference(dll_path)

# 4. Import System types needed for Action<byte[]>
from System import Action, Array, Byte
from TauSync.Implementations.Management import ConnectionManager  # pyright: ignore[reportMissingImports]


def my_python_interrupt_handler(message_bytes):
    """
    Python function that will be called when an interrupt is received.
    
    Args:
        message_bytes: byte[] - The interrupt message data
    """
    try:
        # Convert byte[] to Python bytes
        # Python.NET automatically converts System.Byte[] to Python bytes
        if hasattr(message_bytes, '__iter__'):
            # Convert System.Byte[] to Python bytes
            python_bytes = bytes(message_bytes)
        else:
            python_bytes = message_bytes
        
        # Decode as UTF-8 string (or handle as binary)
        try:
            message_text = python_bytes.decode('utf-8')
            print(f"🔔 INTERRUPT RECEIVED (as text): {message_text}")
        except UnicodeDecodeError:
            # If not valid UTF-8, treat as binary
            print(f"🔔 INTERRUPT RECEIVED (as binary): {len(python_bytes)} bytes")
            print(f"   First 50 bytes: {python_bytes[:50]}")
        
        # Your custom interrupt handling logic here
        # For example: update UI, log to file, trigger action, etc.
        
    except Exception as e:
        print(f"❌ Error in Python interrupt handler: {e}")


def main():
    """Main function demonstrating Python callback usage"""
    
    print("=" * 60)
    print("Python Callback Example for ConnectionManager")
    print("=" * 60)
    
    # Method 1: Create Action<byte[]> from Python function
    # Python.NET automatically converts Python functions to C# delegates
    print("\n1. Creating Action<byte[]> from Python function...")
    
    # Create Action<byte[]> delegate from Python function
    # Python.NET handles this conversion automatically when you use Action[Array[Byte]]
    action_type = Action[Array[Byte]]
    python_action = action_type(my_python_interrupt_handler)
    
    print("✅ Python function converted to Action<byte[]>")
    
    # Method 2: Create ConnectionManager with Python callback
    print("\n2. Creating ConnectionManager with Python callback...")
    
    try:
        # Pass the Action<byte[]> delegate - Python.NET will handle the conversion
        # The Python function will be called automatically when interrupts arrive
        connection_manager = ConnectionManager(python_action)
        print("✅ ConnectionManager created with Python callback!")
        
        # Now when an interrupt is received, my_python_interrupt_handler will be called
        print("\n📝 Note: When an interrupt is received, 'my_python_interrupt_handler' will be called")
        print("   The interrupt will be passed as byte[] to the Python function")
        
    except Exception as e:
        print(f"❌ Error creating ConnectionManager: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Example: The interrupt handler will be called automatically when:
    # - A small unsolicited message (< 32KB) is received
    # - The message is not a valid TransferRequest (handshake)
    # - The message is routed to the message handler
    
    print("\n" + "=" * 60)
    print("Setup complete! ConnectionManager is ready to receive interrupts.")
    print("=" * 60)
    
    # Keep the connection manager alive (in real usage, you'd use it here)
    # connection_manager.Connect("127.0.0.1")
    # ... your code here ...


if __name__ == "__main__":
    main()
