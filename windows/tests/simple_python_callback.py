"""
Simple example: Python callback for interrupts in ConnectionManager

This is a minimal example showing how to pass a Python function to ConnectionManager.
"""

import sys
import os
from pythonnet import load

# Load CoreCLR
load("coreclr")
import clr

# Add DLL reference
script_dir = os.path.dirname(os.path.abspath(__file__))
dll_path = os.path.join(script_dir, "..", "..", "TauSync", "windows", "TauSync.Lib", "bin", "Debug", "net8.0", "TauSync.Lib.dll")
clr.AddReference(os.path.abspath(dll_path))

from System import Action, Array, Byte
from TauSync.Implementations.Management import ConnectionManager  # pyright: ignore[reportMissingImports]


def handle_interrupt(data):
    """This Python function will be called when an interrupt is received"""
    # Convert System.Byte[] to Python bytes
    python_bytes = bytes(data) if hasattr(data, '__iter__') else data
    
    # Try to decode as string, or print as binary
    try:
        text = python_bytes.decode('utf-8')
        print(f"📨 Interrupt received: {text}")
    except:
        print(f"📨 Interrupt received: {len(python_bytes)} bytes")


# Create Action<byte[]> from Python function
action = Action[Array[Byte]](handle_interrupt)

# Create ConnectionManager with Python callback
manager = ConnectionManager(action)

print("✅ ConnectionManager created with Python callback!")
print("   When an interrupt arrives, 'handle_interrupt' will be called automatically")
