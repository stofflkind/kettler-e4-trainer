import serial
import threading
import time

from openant.easy.node import Node
from openant.easy.channel import Channel


# ------------------------------------------------------------
# Konfiguration
# ------------------------------------------------------------

KETTLER_PORT = "/dev/ttyUSB1"

GARMIN_DEVICE_NUMBER = 37409

ANT_NETWORK_KEY = [
    0xB9, 0xA5, 0x21, 0xFB,
    0xBD, 0x72, 0xC3, 0x45
]


# ------------------------------------------------------------
# Garmin / ANT+
# ------------------------------------------------------------

garmin_hr = None
garmin_lock = threading.Lock()


def on_ant_data(data):
    global garmin_hr

    if len(data) >= 8:
        heart_rate = data[7]

        with garmin_lock:
            garmin_hr = heart_rate


def start_ant():
    node = Node()

    node.set_network_key(0x00, ANT_NETWORK_KEY)

    channel = node.new_channel(
        Channel.Type.BIDIRECTIONAL_RECEIVE
    )

    channel.on_broadcast_data = on_ant_data
    channel.on_burst_data = on_ant_data

    # ANT+ Heart Rate Monitor
    channel.set_period(8070)
    channel.set_search_timeout(12)
    channel.set_rf_freq(57)

    channel.set_id(
        GARMIN_DEVICE_NUMBER,
        120,   # ANT+ Heart Rate
        0
    )

    channel.open()

    return node, channel


# ------------------------------------------------------------
# Kettler
# ------------------------------------------------------------

def read_kettler_status(ser):

    ser.reset_input_buffer()

    ser.write(b"ST\r\n")
    ser.flush()

    response = ser.readline().decode(
        "ascii",
        errors="replace"
    ).strip()

    fields = response.split("\t")

    if len(fields) != 8:
        return None

    try:
        return {
            "kettler_pulse": int(fields[0]),
            "rpm": int(fields[1]),
            "speed": int(fields[2]) / 10,
            "distance": int(fields[3]) / 10,
            "target_watt": int(fields[4]),
            "energy": int(fields[5]),
            "training_time": fields[6],
            "actual_watt": int(fields[7]),
        }

    except ValueError:
        return None


# ------------------------------------------------------------
# Hauptprogramm
# ------------------------------------------------------------

print()
print("Kettler E4 + Garmin HRM Monitor")
print("--------------------------------")
print(f"Kettler : {KETTLER_PORT}")
print(f"Garmin  : ANT+ #{GARMIN_DEVICE_NUMBER}")
print()
print("Abbruch mit Ctrl-C")
print()


node = None
channel = None

try:

    # ANT+ starten
    node, channel = start_ant()

    ant_thread = threading.Thread(
        target=node.start,
        daemon=True
    )

    ant_thread.start()

    # Kettler öffnen
    with serial.Serial(
        port=KETTLER_PORT,
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1
    ) as ser:

        while True:

            status = read_kettler_status(ser)

            if status is None:
                print("Keine gültige Antwort vom Kettler")
                time.sleep(1)
                continue

            with garmin_lock:
                hr = garmin_hr

            if hr is None:
                hr_text = "---"
            else:
                hr_text = f"{hr:3d}"

            print(
                f"{status['training_time']} | "
                f"Puls {hr_text} | "
                f"RPM {status['rpm']:3d} | "
                f"{status['speed']:4.1f} km/h | "
                f"{status['distance']:4.1f} km | "
                f"Soll {status['target_watt']:3d} W | "
                f"Ist {status['actual_watt']:3d} W | "
                f"{status['energy']:4d} kJ"
            )

            time.sleep(1)


except KeyboardInterrupt:

    print()
    print("Training beendet.")


finally:

    if channel is not None:
        try:
            channel.close()
        except Exception:
            pass

    if node is not None:
        try:
            node.stop()
        except Exception:
            pass
