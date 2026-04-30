import threading
from typing import Callable

from services.connectivity import ConnectivityService
from utils.decorators import threaded


class PhoneRequestService:
    def __init__(self, connectivity_service: ConnectivityService) -> None:
        self.connectivity_service: ConnectivityService = connectivity_service
        self.threads: list[threading.Thread] = []

        self.operations: dict[str, Callable[[str], None]] = {

        }

    def start(self) -> None:
        self.listen_to_channels()

    def stop(self) -> None:
        for thread in self.threads:
            thread.join()

    @threaded
    def listen_to_channels(self):
        tau = self.connectivity_service.tau
        channels = tau.get_peer_waiting_words()
        for channel in channels:
            self.operations[channel](channel)
