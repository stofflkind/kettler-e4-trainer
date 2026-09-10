import serial


DEVICE_NAMES = {
    "SD4B3035": "Kettler E4",
    "CTRS": "Kettler CTR1",
}


class KettlerTrainer:
    def __init__(self, port="/dev/kettler-e4"):
        self.port = port
        self.ser = None

    def connect(self):
        self.ser = serial.Serial(
            port=self.port,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1,
        )

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    def command(self, command):
        self.ser.reset_input_buffer()
        self.ser.write((command + "\r\n").encode("ascii"))
        self.ser.flush()
        return self.ser.readline().decode(
            "ascii",
            errors="replace",
        ).strip()

    def get_id(self):
        return self.command("ID")

    def get_device_name(self):
        device_id = self.get_id()
        return DEVICE_NAMES.get(
            device_id,
            f"Unknown Kettler device ({device_id})",
        )

    def get_version(self):
        return self.command("VE")

    def enter_command_mode(self):
        return self.command("CM")

    def set_power(self, watts):
        return self.command(f"PW {int(watts)}")

    def get_status(self):
        response = self.command("ST")
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