from typing import Final

from viewmodels.device import DeviceViewModel


class ViewModelManager:
    def __init__(self) -> None:
        self._device_viewmodel: DeviceViewModel = DeviceViewModel()


device_viewmodel: Final[DeviceViewModel] = DeviceViewModel()
