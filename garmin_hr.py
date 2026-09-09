from openant.easy.node import Node
from openant.easy.channel import Channel

NETWORK_KEY = [
    0xB9, 0xA5, 0x21, 0xFB,
    0xBD, 0x72, 0xC3, 0x45
]

DEVICE_NUMBER = 37409


def on_data(data):
    # ANT+ Heart Rate Profile:
    # Herzfrequenz steht im letzten Byte
    page = data[0]

    if (page & 0x0F) <= 7:
        heart_rate = data[7]
        print(f"Puls: {heart_rate} bpm")


node = Node()

node.set_network_key(0x00, NETWORK_KEY)

channel = node.new_channel(
    Channel.Type.BIDIRECTIONAL_RECEIVE
)

channel.on_broadcast_data = on_data
channel.on_burst_data = on_data

# ANT+ Heart Rate Monitor
channel.set_period(8070)
channel.set_search_timeout(12)
channel.set_rf_freq(57)

# Gerät 37409, Device Type 120 = Heart Rate
channel.set_id(
    DEVICE_NUMBER,
    120,
    0
)

print(f"Suche Garmin HRM #{DEVICE_NUMBER} ...")
print("Abbruch mit Ctrl-C")

try:
    channel.open()
    node.start()

except KeyboardInterrupt:
    print("\nBeendet.")

finally:
    node.stop()
