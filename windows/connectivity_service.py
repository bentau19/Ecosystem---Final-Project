import sys
import os
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
dll_path = os.path.join(script_dir, "..", "TauSync", "windows", "TauSync.Lib", "bin", "Debug", "net8.0", "TauSync.Lib.dll")
dll_path = os.path.abspath(dll_path)

if not os.path.exists(dll_path):
    print(f"Error: DLL not found at {dll_path}")
    print("Please build the C# project first: dotnet build ../TauSync/windows/TauSync.Lib/TauSync.Lib.csproj")
    sys.exit(1)

# הוספת הרפרנס
clr.AddReference(dll_path)

# ייבוא המחלקה מתוך ה-Namespace
from TauSync.Lib import TauSyncEngine  # pyright: ignore[reportMissingImports]

if __name__ == '__main__':
    engine = TauSyncEngine()
    print("✅ Success!")
    print(f"Engine Status: {engine.GetStatus()}")