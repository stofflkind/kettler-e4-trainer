import threading

from openant.easy.node import Node
from openant.easy.channel import Channel


ANT_NETWORK_KEY = [
    0xB9, 0xA5, 0x21, 0xFB,
    0xBD, 0x72, 0xC3, 0x45,
]


class GarminHR:
    def __init__(self, device_number=37409):
        self.device_number = device_number
        self.heart_rate = None
        self.lock = threading.Lock()

        self.node = None
        self.channel = None
        self.thread = None

    def _on_data(self, data):
        if len(data) >= 8:
            with self.lock:
                self.heart_rate = data[7]

    def start(self):
        self.node = Node()
        self.node.set_network_key(0x00, ANT_NETWORK_KEY)

        self.channel = self.node.new_channel(
            Channel.Type.BIDIRECTIONAL_RECEIVE
        )

        self.channel.on_broadcast_data = self._on_data
        self.channel.on_burst_data = self._on_data

        self.channel.set_period(8070)
        self.channel.set_search_timeout(12)
        self.channel.set_rf_freq(57)

        self.channel.set_id(
            self.device_number,
            120,
            0
        )

        self.channel.open()

        self.thread = threading.Thread(
            target=self.node.start,
            daemon=True
        )

        self.thread.start()

    def get_heart_rate(self):
        with self.lock:
            return self.heart_rate

    def stop(self):
        if self.channel:
            try:
                self.channel.close()
            except Exception:
                pass

        if self.node:
            try:
                self.node.stop()
            except Exception:
                pass
