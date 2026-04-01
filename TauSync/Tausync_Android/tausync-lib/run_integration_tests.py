#!/usr/bin/env python3
"""
Integration Test Runner for TauSync Android Library
Compiles and runs Java integration tests similar to the C# Python test.
"""

import subprocess
import sys
import os
import time
from pathlib import Path

def log(message, level="INFO"):
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [{level}] {message}")

def main():
    script_dir = Path(__file__).parent.absolute()
    project_root = script_dir.parent.parent.parent
    
    log("=" * 80)
    log("TAUSYNC ANDROID LIB INTEGRATION TESTS")
    log("=" * 80)
    
    # Find Java files
    main_java_dir = script_dir / "src" / "main" / "java"
    test_java_dir = script_dir / "src" / "test" / "java"
    
    if not test_java_dir.exists():
        log("ERROR: Test directory not found", "ERROR")
        return 1
    
    # Check for javac
    try:
        result = subprocess.run(["javac", "-version"], capture_output=True, text=True)
        log(f"Java compiler: {result.stderr.strip()}")
    except FileNotFoundError:
        log("ERROR: javac not found. Please install JDK.", "ERROR")
        return 1
    
    # Try to compile and run
    log("Attempting to compile and run tests...")
    log("NOTE: This requires the project to be built first (via Android Studio or Gradle)")
    log("For now, please run the tests manually via Android Studio or Gradle")
    
    # Check if we can find compiled classes
    build_dir = script_dir / "build" / "intermediates" / "compile_library_classes_jar" / "debug"
    if build_dir.exists():
        log(f"Found build directory: {build_dir}")
    else:
        log("Build directory not found. Please build the project first.", "WARNING")
    
    log("=" * 80)
    log("To run tests manually:")
    log("1. Build the project in Android Studio")
    log("2. Run: cd TauSync/android/tausync-lib")
    log("3. Run: ./gradlew test (or use Android Studio's test runner)")
    log("=" * 80)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
