"""PreviousDeviceStore has been removed.

Previous-device persistence is now handled by DeviceRepository using
sqlite3 — there is no separate file-based store for previous-device data.
Repository-level tests live in repositories/test_device.py.
"""
