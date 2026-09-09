import serial
import time

PORT = "/dev/ttyUSB1"
TEST_WATT = 125
TEST_SECONDS = 10


def send_command(ser, command, wait=0.25):
    """Befehl senden und eventuelle direkte Antwort lesen."""
    ser.reset_input_buffer()
    ser.write((command + "\r\n").encode("ascii"))
    ser.flush()

    time.sleep(wait)
    response = ser.read_all()

    if response:
        print(f"{command} -> {response!r}")

    return response


def read_status(ser):
    ser.reset_input_buffer()
    ser.write(b"ST\r\n")
    ser.flush()

    response = ser.readline().decode(
        "ascii",
        errors="replace"
    ).strip()

    fields = response.split("\t")

    if len(fields) != 8:
        print("Ungültige ST-Antwort:", repr(response))
        return None

    try:
        return {
            "pulse": int(fields[0]),
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


with serial.Serial(
    port=PORT,
    baudrate=9600,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=1,
) as ser:

    print("Aktuellen Zustand abfragen ...")

    status = read_status(ser)

    if status is None:
        raise RuntimeError("Kettler-Status konnte nicht gelesen werden.")

    original_watt = status["target_watt"]

    print(f"Aktueller Sollwert: {original_watt} W")
    print(f"Testwert:            {TEST_WATT} W")
    print()

    try:
        print("Command Mode einschalten ...")
        send_command(ser, "CM")

        print(f"Setze Leistung auf {TEST_WATT} W ...")
        send_command(ser, f"PW {TEST_WATT}")

        print()
        print("Beobachte den E4:")
        print()

        for _ in range(TEST_SECONDS):
            status = read_status(ser)

            if status:
                print(
                    f"{status['training_time']} | "
                    f"RPM {status['rpm']:3d} | "
                    f"Soll {status['target_watt']:3d} W | "
                    f"Ist {status['actual_watt']:3d} W"
                )

            time.sleep(1)

    finally:
        print()
        print(f"Stelle ursprüngliche Leistung {original_watt} W wieder her ...")

        try:
            send_command(ser, f"PW {original_watt}")
        except Exception as exc:
            print("WARNUNG: Rückstellen fehlgeschlagen:", exc)

        time.sleep(0.5)

        final_status = read_status(ser)

        if final_status:
            print(
                f"Endzustand: Soll {final_status['target_watt']} W, "
                f"Ist {final_status['actual_watt']} W"
            )
