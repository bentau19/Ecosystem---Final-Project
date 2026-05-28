import threading

from tausync_py import TauSync
from desktop.domain.enums.device_info_channels import DeviceInfoChannels


def write(c: str):
    print(c)
    if c == DeviceInfoChannels.LAST_SEEN.value:
        with tau.connect(c) as stream1:
            stream1.write_string("2022-04-19")
        return
    with tau.connect(c) as stream1:
        stream1.write_string("1234")


tau = TauSync()
tau.connect_to("192.168.68.27")

while True:
    for s in tau.get_peer_waiting_words():
        if s == DeviceInfoChannels.ID:
            with tau.connect(s) as stream:
                stream.write_string("11111\n")
                r = stream.read_all()
                continue
        write(s)
