# Previously-connected device list has been removed from DeviceViewModel.
# Connection is phone-initiated only — the PC cannot dial out, so the
# "Connect" affordance was non-functional.
#
# The methods and signals removed:
#   - load_devices()
#   - connect_to_device()
#   - previous_devices_updated signal
#   - _on_all_devices_fetched()
#   - _to_prev_device_dto()
#
# Safe to delete: git rm desktop/tests/viewmodels/test_viewmodel_previous_device.py
