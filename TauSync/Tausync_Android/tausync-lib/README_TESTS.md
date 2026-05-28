# Running TauSync Android Integration Tests

The integration tests live in `src/test/java/com/example/tausync_lib/IntegrationTest.java`.
They spin up a local TCP server and client within the same JVM, so no Android device or
emulator is needed — but the project must be compiled first.

---

## What the tests cover

| Test | Description |
|---|---|
| `testStandardFlow` | Full handshake + bidirectional streaming |
| `testInterruptDuringStream` | Interrupt handling during an active full-duplex stream |
| `testConcurrentInterrupts` | Multiple concurrent interrupts during a transfer |

---

## Prerequisites

- JDK 11 or newer on `PATH`
- The project built at least once in Android Studio so `classes.jar` is available

---

## Option 1 — Python runner (recommended)

The repo includes a cross-platform runner that compiles and executes the test class
without needing Android Studio open:

```bash
cd TauSync/Tausync_Android/tausync-lib/
python run_integration_tests.py
```

The script locates `classes.jar` from the Gradle intermediate output, compiles
`IntegrationTest.java`, and runs `com.example.tausync_lib.IntegrationTest`.

---

## Option 2 — Manual (post-build)

After building the project in Android Studio (`Build > Make Project`):

```powershell
# From TauSync/Tausync_Android/tausync-lib/

# 1. Compile the test class against the library JAR
$jar = "build\intermediates\compile_library_classes_jar\debug\bundleLibCompileToJarDebug\classes.jar"
javac -cp "$jar;." -d "build\test-classes" `
      "src\test\java\com\example\tausync_lib\IntegrationTest.java"

# 2. Run
java -cp "build\test-classes;$jar;." com.example.tausync_lib.IntegrationTest
```

---

## Troubleshooting

**`classes.jar not found`**
: Build the project in Android Studio (`Build > Make Project`) and retry.

**Compilation errors (`cannot find symbol`)**
: Clean and rebuild: `Build > Clean Project` → `Build > Rebuild Project`.

**Port already in use**
: The tests use ports 8888, 8898, and 8908. Close any other process occupying those ports.

**`SourceSet with name 'unitTest' not found`**
: Android Studio is trying to run via Gradle. Use Option 1 or Option 2 above instead of
  the Run/Debug configuration in the IDE.
