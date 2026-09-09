import time

from openant.easy.node import Node
from openant.easy.channel import Channel


ANT_NETWORK_KEY = [
    0xB9, 0xA5, 0x21, 0xFB,
    0xBD, 0x72, 0xC3, 0x45,
]

DEVICE_NUMBER = 12345
DEVICE_TYPE = 11
TRANSMISSION_TYPE = 5

CHANNEL_PERIOD = 8182
RF_FREQUENCY = 57

POWER = 100
CADENCE = 60


def main():
    node = Node()

    node.set_network_key(
        0x00,
        ANT_NETWORK_KEY
    )

    channel = node.new_channel(
        Channel.Type.BIDIRECTIONAL_TRANSMIT
    )

    channel.set_period(
        CHANNEL_PERIOD
    )

    channel.set_rf_freq(
        RF_FREQUENCY
    )

    channel.set_id(
        DEVICE_NUMBER,
        DEVICE_TYPE,
        TRANSMISSION_TYPE
    )

    event_count = 0
    accumulated_power = 0

    def send_power_page():
        nonlocal event_count
        nonlocal accumulated_power

        event_count = (
            event_count + 1
        ) & 0xFF

        accumulated_power = (
            accumulated_power + POWER
        ) & 0xFFFF

        #
        # ANT+ Bicycle Power
        # Data Page 16 / 0x10
        #
        data = [
            0x10,
            event_count,
            0xFF,
            CADENCE,
            accumulated_power & 0xFF,
            (
                accumulated_power >> 8
            ) & 0xFF,
            POWER & 0xFF,
            (
                POWER >> 8
            ) & 0xFF,
        ]

        channel.send_broadcast_data(
            data
        )

    def on_tx(data):
        send_power_page()

    channel.on_broadcast_tx_data = on_tx

    try:
        print()
        print("Virtueller ANT+ Leistungsmesser")
        print("--------------------------------")
        print(
            f"Device Number : {DEVICE_NUMBER}"
        )
        print(
            f"Leistung      : {POWER} W"
        )
        print(
            f"Kadenz        : {CADENCE} rpm"
        )
        print()
        print(
            "ANT+ Sender wird gestartet ..."
        )
        print(
            "Auf der Garmin-Uhr jetzt "
            "nach Leistungssensoren suchen."
        )
        print()
        print(
            "Abbruch mit Ctrl-C"
        )
        print()

        channel.open()

        #
        # Erste Datenseite bereitstellen.
        #
        send_power_page()

        node.start()

    except KeyboardInterrupt:
        print()
        print("ANT+ Sender beendet.")

    finally:
        try:
            channel.close()
        except Exception:
            pass

        try:
            node.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
