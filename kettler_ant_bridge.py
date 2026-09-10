import threading
import time

from openant.easy.node import Node
from openant.easy.channel import Channel

from kettler_trainer import KettlerTrainer


ANT_NETWORK_KEY = [
    0xB9, 0xA5, 0x21, 0xFB,
    0xBD, 0x72, 0xC3, 0x45,
]

DEVICE_NUMBER = 12345
DEVICE_TYPE = 11
TRANSMISSION_TYPE = 5

CHANNEL_PERIOD = 8182
RF_FREQUENCY = 57

KETTLER_POLL_INTERVAL = 1.0


class KettlerAntBridge:
    def __init__(self):
        self.kettler = KettlerTrainer()

        self.node = None
        self.channel = None

        self.running = False
        self.poll_thread = None

        self.lock = threading.Lock()

        self.power = 0
        self.cadence = 0

        self.event_count = 0
        self.accumulated_power = 0

    def read_kettler_loop(self):
        while self.running:
            try:
                status = self.kettler.get_status()

                if status:
                    with self.lock:
                        self.power = int(
                            status["actual_watt"]
                        )

                        self.cadence = int(
                            status["rpm"]
                        )

                    print(
                        f"Kettler: "
                        f"{self.power:3d} W | "
                        f"{self.cadence:3d} rpm"
                    )

            except Exception as exc:
                print(
                    "Fehler beim Lesen "
                    "des Kettlers:",
                    exc
                )

            time.sleep(
                KETTLER_POLL_INTERVAL
            )

    def build_power_page(self):
        with self.lock:
            power = self.power
            cadence = self.cadence

        power = max(
            0,
            min(power, 65535)
        )

        cadence = max(
            0,
            min(cadence, 254)
        )

        self.event_count = (
            self.event_count + 1
        ) & 0xFF

        self.accumulated_power = (
            self.accumulated_power
            + power
        ) & 0xFFFF

        return [
            0x10,
            self.event_count,
            0xFF,
            cadence,
            self.accumulated_power & 0xFF,
            (
                self.accumulated_power >> 8
            ) & 0xFF,
            power & 0xFF,
            (
                power >> 8
            ) & 0xFF,
        ]

    def on_broadcast_tx(self, data):
        page = self.build_power_page()

        self.channel.send_broadcast_data(
            page
        )

    def start(self):
        print()
        print("Kettler Trainer -> ANT+ Bridge")
        print("-------------------------")
        print(
            f"ANT+ Sensor-ID: "
            f"{DEVICE_NUMBER}"
        )
        print()

        self.kettler.connect()

        print(
            "Kettler:",
            self.kettler.get_id()
        )

        print(
            "Version:",
            self.kettler.get_version()
        )

        self.node = Node()

        self.node.set_network_key(
            0x00,
            ANT_NETWORK_KEY
        )

        self.channel = self.node.new_channel(
            Channel.Type.BIDIRECTIONAL_TRANSMIT
        )

        self.channel.set_period(
            CHANNEL_PERIOD
        )

        self.channel.set_rf_freq(
            RF_FREQUENCY
        )

        self.channel.set_id(
            DEVICE_NUMBER,
            DEVICE_TYPE,
            TRANSMISSION_TYPE
        )

        self.channel.on_broadcast_tx_data = (
            self.on_broadcast_tx
        )

        self.running = True

        self.poll_thread = threading.Thread(
            target=self.read_kettler_loop,
            daemon=True
        )

        self.poll_thread.start()

        self.channel.open()

        #
        # Erste ANT+-Datenseite senden.
        #
        self.channel.send_broadcast_data(
            self.build_power_page()
        )

        print(
            "ANT+ Sender läuft."
        )
        print(
            "Garmin-Sensor 12345 "
            "kann jetzt verwendet werden."
        )
        print(
            "Abbruch mit Ctrl-C"
        )
        print()

        self.node.start()

    def stop(self):
        self.running = False

        if self.poll_thread:
            self.poll_thread.join(
                timeout=2
            )

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

        try:
            self.kettler.close()
        except Exception:
            pass


def main():
    bridge = KettlerAntBridge()

    try:
        bridge.start()

    except KeyboardInterrupt:
        print()
        print(
            "Bridge wird beendet ..."
        )

    finally:
        bridge.stop()

        print(
            "Geräte geschlossen."
        )


if __name__ == "__main__":
    main()
