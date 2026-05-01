from tausync_py import TauSync
import threading


def threaded(fn):
    def wrapper(*args, **kwargs):
        t = threading.Thread(target=fn, args=args, kwargs=kwargs)
        t.start()
        return t
    return wrapper


class _Signal:
    def emit(self, *args):
        pass


class ConnectivityService():
    def __init__(self) -> None:
        """
        Initialize ConnectivityService and immediately start listening.

        No-op on subsequent calls — initialization runs exactly once.

        Args:
            parent: Optional parent QObject for memory management.
        """

        self._tau = TauSync()
        self.device_connected = _Signal()
        self.connection_error = _Signal()

        self._threads = []

        # self._listen()


    @threaded
    def connect_to_device(self, ip: str) -> None:
        """Connect to a remote device by IP address.

        Args:
            ip: The IP address of the remote TauSync server.
        """
        try:
            self._tau.connect_to(ip)
            print("Connected to device")
            self.device_connected.emit()
        except Exception as exc:
            print(exc)
            self.connection_error.emit(str(exc))

if __name__ == "__main__":
    import time
    service = ConnectivityService()
    t = service.connect_to_device("192.168.1.50")
    if t:
        t.join()
    print("Finished connection attempt.")