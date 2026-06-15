# GitHub Actions Test Hang Fix

## Problem
The `windows-test` job in `.github/workflows/tests.yml` was hanging indefinitely when running `pytest desktop/`. Tests never completed.

## Root Cause
The desktop tests use **PySide6/Qt with `pytest-qt`** (the `qtbot` fixture). On headless CI runners (GitHub Actions), Qt tries to initialize a graphical platform but no display is available:

1. `pytest desktop/` is invoked
2. `pytest-qt` creates a `QApplication` 
3. On Windows CI runner, Qt tries to initialize the native Windows graphics backend
4. Without explicit `QT_QPA_PLATFORM=offscreen`, Qt hangs waiting for a display that never materializes
5. Test hangs indefinitely (or until GitHub Actions timeout of 6 hours)

## Solution Applied

### 1. **Workflow Fix** — `.github/workflows/tests.yml`

Added three changes to the `windows-test` job:

```yaml
- name: Install dependencies
  run: |
    pip install -r TauSync/windows/requirements.txt
    pip install -r desktop/requirements.txt
    pip install TauSync/windows
    pip install pytest pytest-timeout  # ← Added pytest-timeout

- name: Run tests
  env:
    QT_QPA_PLATFORM: offscreen  # ← Force offscreen rendering
  run: pytest desktop/ --timeout=300 -v  # ← Add 5-min timeout + verbose output
```

**Why each part matters:**
- `QT_QPA_PLATFORM=offscreen` → Tells Qt to use software rendering (no display needed)
- `pytest-timeout` package → Prevents indefinite hangs; 300s = 5 minutes per test
- `-v` (verbose) → Shows which test is running; helps spot slow tests in logs

### 2. **Project Configuration** — `pyproject.toml` (NEW)

Created root-level pytest configuration to apply settings globally:

```toml
[tool.pytest.ini_options]
addopts = "--timeout=300 -v"
testpaths = ["desktop/tests", "FileDetection/tests"]
```

Benefits:
- Timeout applies to local test runs too (not just CI)
- Developers immediately see slow tests
- No need to remember pytest flags

### 3. **Qt Initialization Fix** — `desktop/tests/conftest.py`

Added two safeguards:

```python
# Auto-set QT_QPA_PLATFORM for non-Windows headless environments
if "QT_QPA_PLATFORM" not in os.environ:
    has_display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if not has_display and sys.platform != "win32":
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Ensure QApplication exists before any tests run."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
```

Benefits:
- Explicit `qapp` fixture prevents race conditions during QApplication initialization
- Auto-detection of headless environments (Linux/macOS)
- Windows CI explicitly sets the env var in workflow (more predictable)

### 4. **FileDetection Tests** — `pyproject.toml` included in testpaths

Also added `--timeout=300` to FileDetection tests for consistency and safety.

---

## Testing the Fix Locally

Before pushing, verify the fix works:

```powershell
cd desktop/

# Set offscreen mode (if no display)
$env:QT_QPA_PLATFORM = "offscreen"

# Run with timeout
pytest --timeout=300 -v

# Or just use the default (reads from pyproject.toml)
pytest
```

Expected behavior:
- Tests complete within 5 minutes
- Each test name appears in output
- No `TIMEOUT` errors appear (unless a test is actually slow)

---

## CI Behavior After Fix

### windows-test
- ✅ Runs with `QT_QPA_PLATFORM=offscreen`
- ✅ Timeout: 300 seconds per test (5 min)
- ✅ Logs show each test name (`-v` flag)
- ✅ Job fails cleanly if a test hangs (no 6-hour wait)

### FileDetection tests
- ✅ Timeout: 300 seconds per test
- ✅ Consistent with desktop tests

---

## Edge Cases Handled

| Scenario | Before | After |
|----------|--------|-------|
| Local Windows run (with display) | Works | Works (display available, Qt uses native platform) |
| Local Linux headless | Hangs indefinitely | Works (conftest auto-sets `QT_QPA_PLATFORM=offscreen`) |
| GitHub Actions (no display) | Hangs indefinitely | Works (`QT_QPA_PLATFORM=offscreen` in workflow) |
| Test takes >5 min | Hangs forever | Fails with timeout error (allows job to fail fast) |
| Missing `pytest-timeout` | `--timeout` flag ignored silently | Now explicitly installed |

---

## References

- [PySide6 Platform Selection](https://doc.qt.io/qt-6/qpa.html)
- [pytest-qt documentation](https://pytest-qt.readthedocs.io/)
- [pytest-timeout plugin](https://pytest-timeout.readthedocs.io/)
