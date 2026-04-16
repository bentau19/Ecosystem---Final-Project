"""DeviceStore has been removed.

Device persistence is now handled directly by DeviceRepository using
sqlite3 — there is no separate file-based store for device data.
Repository-level tests live in repositories/test_device.py.
"""
