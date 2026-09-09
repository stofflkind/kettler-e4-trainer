import csv
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from openant.easy.channel import Channel
from openant.easy.node import Node

from kettler_e4 import KettlerE4


DEFAULT_END_WATT = 80
SAMPLE_INTERVAL = 1.0
RAMP_UPDATE_INTERVAL = 2.0

ANT_NETWORK_KEY = [
    0xB9, 0xA5, 0x21, 0xFB,
    0xBD, 0x72, 0xC3, 0x45,
]

HR_DEVICE_NUMBER = 37409
HR_DEVICE_TYPE = 120
HR_CHANNEL_PERIOD = 8070

POWER_DEVICE_NUMBER = 12345
POWER_DEVICE_TYPE = 11
POWER_TRANSMISSION_TYPE = 5
POWER_CHANNEL_PERIOD = 8182

# Virtual ANT+ combined Bicycle Speed & Cadence sensor
BSC_DEVICE_NUMBER = 12346
BSC_DEVICE_TYPE = 121
BSC_TRANSMISSION_TYPE = 1
BSC_CHANNEL_PERIOD = 8086

# Garmin must use the same virtual wheel circumference.
VIRTUAL_WHEEL_CIRCUMFERENCE_M = 2.100

ANT_RF_FREQUENCY = 57


class AntRadio:
    """Ein ANTUSB-m mit HR-Empfang und virtuellem Bicycle-Power-Sender."""

    def __init__(
        self,
        hr_device_number=HR_DEVICE_NUMBER,
        power_device_number=POWER_DEVICE_NUMBER,
    ):
        self.hr_device_number = hr_device_number
        self.power_device_number = power_device_number
        self.node = None
        self.hr_channel = None
        self.power_channel = None
        self.bsc_channel = None
        self.thread = None
        self.lock = threading.Lock()

        self.heart_rate = None

        # Bicycle Power state
        self.power = 0
        self.cadence = 0
        self.event_count = 0
        self.accumulated_power = 0

        # Bicycle Speed & Cadence state.
        # ANT+ event times use 1/1024 second units.
        self.bsc_cadence_event_time = 0
        self.bsc_cadence_rev_count = 0
        self.bsc_speed_event_time = 0
        self.bsc_speed_rev_count = 0
        self._cadence_fraction = 0.0
        self._speed_fraction = 0.0

    def _on_hr_data(self, data):
        if len(data) >= 8:
            with self.lock:
                self.heart_rate = int(data[7])

    def _power_page_locked(self):
        power = max(0, min(int(self.power), 65535))
        cadence = max(0, min(int(self.cadence), 254))
        return [
            0x10,
            self.event_count,
            0xFF,
            cadence,
            self.accumulated_power & 0xFF,
            (self.accumulated_power >> 8) & 0xFF,
            power & 0xFF,
            (power >> 8) & 0xFF,
        ]

    def _on_power_tx(self, data):
        with self.lock:
            page = self._power_page_locked()
        self.power_channel.send_broadcast_data(page)

    def _bsc_page_locked(self):
        """ANT+ combined Bicycle Speed & Cadence data page."""
        return [
            self.bsc_cadence_event_time & 0xFF,
            (self.bsc_cadence_event_time >> 8) & 0xFF,
            self.bsc_cadence_rev_count & 0xFF,
            (self.bsc_cadence_rev_count >> 8) & 0xFF,
            self.bsc_speed_event_time & 0xFF,
            (self.bsc_speed_event_time >> 8) & 0xFF,
            self.bsc_speed_rev_count & 0xFF,
            (self.bsc_speed_rev_count >> 8) & 0xFF,
        ]

    def _on_bsc_tx(self, data):
        with self.lock:
            page = self._bsc_page_locked()
        self.bsc_channel.send_broadcast_data(page)

    def _update_bsc_state_locked(self, cadence_rpm, speed_kmh):
        """Advance virtual crank/wheel events for one Kettler 1 s sample."""
        cadence_rpm = max(0.0, float(cadence_rpm))
        speed_kmh = max(0.0, float(speed_kmh))

        # Cadence: convert RPM to crank revolutions per 1 second sample.
        cadence_revs = cadence_rpm / 60.0
        self._cadence_fraction += cadence_revs
        whole_cadence_revs = int(self._cadence_fraction)

        if whole_cadence_revs > 0 and cadence_rpm > 0:
            self._cadence_fraction -= whole_cadence_revs
            cadence_period_s = 60.0 / cadence_rpm
            cadence_ticks = int(round(cadence_period_s * 1024))
            self.bsc_cadence_rev_count = (
                self.bsc_cadence_rev_count + whole_cadence_revs
            ) & 0xFFFF
            self.bsc_cadence_event_time = (
                self.bsc_cadence_event_time
                + whole_cadence_revs * cadence_ticks
            ) & 0xFFFF

        # Speed: convert Kettler km/h into virtual wheel revolutions.
        speed_mps = speed_kmh / 3.6
        wheel_revs = speed_mps / VIRTUAL_WHEEL_CIRCUMFERENCE_M
        self._speed_fraction += wheel_revs
        whole_speed_revs = int(self._speed_fraction)

        if whole_speed_revs > 0 and speed_mps > 0:
            self._speed_fraction -= whole_speed_revs
            wheel_period_s = (
                VIRTUAL_WHEEL_CIRCUMFERENCE_M / speed_mps
            )
            speed_ticks = int(round(wheel_period_s * 1024))
            self.bsc_speed_rev_count = (
                self.bsc_speed_rev_count + whole_speed_revs
            ) & 0xFFFF
            self.bsc_speed_event_time = (
                self.bsc_speed_event_time
                + whole_speed_revs * speed_ticks
            ) & 0xFFFF

    def start(self):
        self.node = Node()
        self.node.set_network_key(0x00, ANT_NETWORK_KEY)

        self.hr_channel = self.node.new_channel(
            Channel.Type.BIDIRECTIONAL_RECEIVE
        )
        self.hr_channel.on_broadcast_data = self._on_hr_data
        self.hr_channel.on_burst_data = self._on_hr_data
        self.hr_channel.set_period(HR_CHANNEL_PERIOD)
        self.hr_channel.set_search_timeout(12)
        self.hr_channel.set_rf_freq(ANT_RF_FREQUENCY)
        self.hr_channel.set_id(
            self.hr_device_number,
            HR_DEVICE_TYPE,
            0,
        )

        self.power_channel = self.node.new_channel(
            Channel.Type.BIDIRECTIONAL_TRANSMIT
        )
        self.power_channel.set_period(POWER_CHANNEL_PERIOD)
        self.power_channel.set_rf_freq(ANT_RF_FREQUENCY)
        self.power_channel.set_id(
            self.power_device_number,
            POWER_DEVICE_TYPE,
            POWER_TRANSMISSION_TYPE,
        )
        self.power_channel.on_broadcast_tx_data = self._on_power_tx

        # Channel 3: virtual combined Bicycle Speed & Cadence sensor.
        self.bsc_channel = self.node.new_channel(
            Channel.Type.BIDIRECTIONAL_TRANSMIT
        )
        self.bsc_channel.set_period(BSC_CHANNEL_PERIOD)
        self.bsc_channel.set_rf_freq(ANT_RF_FREQUENCY)
        self.bsc_channel.set_id(
            BSC_DEVICE_NUMBER,
            BSC_DEVICE_TYPE,
            BSC_TRANSMISSION_TYPE,
        )
        self.bsc_channel.on_broadcast_tx_data = self._on_bsc_tx

        self.hr_channel.open()
        self.power_channel.open()
        self.bsc_channel.open()

        with self.lock:
            power_page = self._power_page_locked()
            bsc_page = self._bsc_page_locked()

        self.power_channel.send_broadcast_data(power_page)
        self.bsc_channel.send_broadcast_data(bsc_page)

        self.thread = threading.Thread(
            target=self.node.start,
            daemon=True,
        )
        self.thread.start()

    def update_power(self, power, cadence, speed=0.0):
        """Publish one Kettler sample to ANT+ Power and Speed/Cadence."""
        power = max(0, min(int(power), 65535))
        cadence = max(0, min(int(cadence), 254))
        speed = max(0.0, float(speed))

        with self.lock:
            self.power = power
            self.cadence = cadence
            self.event_count = (self.event_count + 1) & 0xFF
            self.accumulated_power = (
                self.accumulated_power + power
            ) & 0xFFFF
            self._update_bsc_state_locked(cadence, speed)

    def get_heart_rate(self):
        with self.lock:
            return self.heart_rate

    def stop(self):
        for channel in (
            self.hr_channel,
            self.power_channel,
            self.bsc_channel,
        ):
            if channel:
                try:
                    channel.close()
                except Exception:
                    pass
        if self.node:
            try:
                self.node.stop()
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)


def load_profile(path):
    with open(path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    if "name" not in profile:
        raise ValueError("Profil enthält keinen Namen.")
    if "steps" not in profile or not profile["steps"]:
        raise ValueError("Profil enthält keine Trainingsschritte.")

    for i, step in enumerate(profile["steps"], start=1):
        step_type = step.get("type", "steady")
        step.setdefault("name", f"Schritt {i}")

        if "duration" not in step:
            raise ValueError(f"Schritt {i}: duration fehlt.")
        duration = int(step["duration"])
        if duration <= 0:
            raise ValueError(f"Schritt {i}: duration muss > 0 sein.")

        if step_type == "steady":
            if "watts" not in step:
                raise ValueError(f"Schritt {i}: watts fehlt.")
            if int(step["watts"]) <= 0:
                raise ValueError(f"Schritt {i}: watts muss > 0 sein.")
        elif step_type == "ramp":
            if "start_watts" not in step or "end_watts" not in step:
                raise ValueError(
                    f"Schritt {i}: start_watts oder end_watts fehlt."
                )
            if int(step["start_watts"]) <= 0 or int(step["end_watts"]) <= 0:
                raise ValueError(
                    f"Schritt {i}: Rampenleistung muss > 0 sein."
                )
        else:
            raise ValueError(
                f"Schritt {i}: unbekannter Typ '{step_type}'."
            )
        step["type"] = step_type

    return profile


def format_seconds(seconds):
    seconds = max(0, int(seconds))
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def slugify(text):
    text = text.lower()
    for old, new in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(old, new)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def create_log_file(profile_name):
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return log_dir / f"{timestamp}_{slugify(profile_name)}.csv"


def average(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def ramp_watts(step, elapsed):
    duration = float(step["duration"])
    start_watts = float(step["start_watts"])
    end_watts = float(step["end_watts"])
    progress = min(1.0, max(0.0, elapsed / duration))
    return int(round(
        start_watts + (end_watts - start_watts) * progress
    ))


class TrainerEngine:
    """Gemeinsame Trainingslogik für CLI und Webfrontend."""

    def __init__(self, status_callback=None, message_callback=None):
        self.status_callback = status_callback
        self.message_callback = message_callback
        self.stop_event = threading.Event()
        self.running = False

    def request_stop(self):
        self.stop_event.set()

    def _message(self, text):
        if self.message_callback:
            self.message_callback(text)

    def _status(self, data):
        if self.status_callback:
            self.status_callback(dict(data))

    def run(self, profile_path):
        profile = load_profile(profile_path)
        kettler = KettlerE4()
        ant = AntRadio()

        total_duration = sum(
            int(step["duration"]) for step in profile["steps"]
        )
        log_path = create_log_file(profile["name"])

        heart_rates = []
        actual_watts = []
        rpms = []
        last_distance = None
        last_energy = None
        training_start = None
        completed = False

        self.stop_event.clear()
        self.running = True

        self._status({
            "running": True,
            "profile": profile["name"],
            "step": None,
            "step_name": None,
            "step_type": None,
            "elapsed": 0,
            "remaining": total_duration,
            "total_duration": total_duration,
            "heart_rate": None,
            "rpm": 0,
            "speed": 0.0,
            "distance": 0.0,
            "target_watt": 0,
            "actual_watt": 0,
            "energy": 0,
            "log": str(log_path),
            "error": None,
        })

        try:
            kettler.connect()
            self._message(f"Kettler: {kettler.get_id()}")
            self._message(f"Version: {kettler.get_version()}")

            response = kettler.enter_command_mode()
            if response != "ACK":
                self._message(
                    f"WARNUNG: Command Mode Antwort: {response}"
                )

            ant.start()
            self._message(
                f"ANT+ gestartet: HRM {HR_DEVICE_NUMBER} empfangen, "
                f"Power-Sensor {POWER_DEVICE_NUMBER} und "
                f"Speed/Cadence-Sensor {BSC_DEVICE_NUMBER} senden"
            )

            with open(
                log_path,
                "w",
                newline="",
                encoding="utf-8",
            ) as csvfile:
                writer = csv.writer(csvfile, delimiter=";")
                writer.writerow([
                    "timestamp", "elapsed_s", "step", "step_name",
                    "step_type", "target_watt", "actual_watt",
                    "heart_rate", "rpm", "speed_kmh",
                    "distance_km", "energy_kj",
                ])

                training_start = time.monotonic()

                for step_number, step in enumerate(
                    profile["steps"],
                    start=1,
                ):
                    if self.stop_event.is_set():
                        break

                    duration = int(step["duration"])
                    step_name = step["name"]
                    step_type = step["type"]

                    planned_step_start = sum(
                        int(s["duration"])
                        for s in profile["steps"][:step_number - 1]
                    )
                    step_start = training_start + planned_step_start
                    step_end = step_start + duration
                    sample_index = 0
                    next_sample = step_start

                    self._message(
                        f"Schritt {step_number}/{len(profile['steps'])}: "
                        f"{step_name}"
                    )

                    if step_type == "steady":
                        current_target = int(step["watts"])
                        kettler.set_power(current_target)
                    else:
                        current_target = int(step["start_watts"])
                        kettler.set_power(current_target)

                    last_ramp_update = step_start

                    while (
                        sample_index < duration
                        and not self.stop_event.is_set()
                    ):
                        now = time.monotonic()
                        if now < next_sample:
                            if self.stop_event.wait(next_sample - now):
                                break

                        now = time.monotonic()
                        step_elapsed = max(0.0, now - step_start)

                        if step_type == "ramp":
                            desired_target = ramp_watts(
                                step,
                                step_elapsed,
                            )
                            if (
                                now - last_ramp_update
                                >= RAMP_UPDATE_INTERVAL
                            ):
                                if desired_target != current_target:
                                    kettler.set_power(desired_target)
                                    current_target = desired_target
                                last_ramp_update = now

                        status = kettler.get_status()
                        if status is None:
                            self._message("Ungültige Kettler-Antwort")
                            sample_index += 1
                            next_sample = (
                                step_start
                                + sample_index * SAMPLE_INTERVAL
                            )
                            continue

                        ant.update_power(
                            status["actual_watt"],
                            status["rpm"],
                            status["speed"],
                        )
                        hr = ant.get_heart_rate()
                        elapsed = now - training_start
                        remaining_total = max(
                            0,
                            total_duration - elapsed,
                        )

                        heart_rates.append(hr)
                        actual_watts.append(status["actual_watt"])
                        rpms.append(status["rpm"])
                        last_distance = status["distance"]
                        last_energy = status["energy"]

                        writer.writerow([
                            datetime.now().isoformat(timespec="seconds"),
                            round(elapsed, 1),
                            step_number,
                            step_name,
                            step_type,
                            status["target_watt"],
                            status["actual_watt"],
                            hr if hr is not None else "",
                            status["rpm"],
                            status["speed"],
                            status["distance"],
                            status["energy"],
                        ])
                        csvfile.flush()

                        self._status({
                            "running": True,
                            "profile": profile["name"],
                            "step": step_number,
                            "step_name": step_name,
                            "step_type": step_type,
                            "elapsed": int(elapsed),
                            "remaining": int(remaining_total),
                            "total_duration": total_duration,
                            "heart_rate": hr,
                            "rpm": status["rpm"],
                            "speed": status["speed"],
                            "distance": status["distance"],
                            "target_watt": status["target_watt"],
                            "actual_watt": status["actual_watt"],
                            "energy": status["energy"],
                            "log": str(log_path),
                            "error": None,
                        })

                        sample_index += 1
                        next_sample = (
                            step_start
                            + sample_index * SAMPLE_INTERVAL
                        )

                    if self.stop_event.is_set():
                        break

                    if step_type == "ramp":
                        end_watts = int(step["end_watts"])
                        if current_target != end_watts:
                            kettler.set_power(end_watts)

                completed = not self.stop_event.is_set()

        finally:
            try:
                kettler.set_power(DEFAULT_END_WATT)
            except Exception:
                pass
            try:
                ant.update_power(0, 0)
            except Exception:
                pass
            try:
                ant.stop()
            except Exception:
                pass
            try:
                kettler.close()
            except Exception:
                pass

            self.running = False

        elapsed_total = (
            time.monotonic() - training_start
            if training_start is not None
            else 0
        )

        result = {
            "completed": completed,
            "duration": elapsed_total,
            "average_hr": average(heart_rates),
            "max_hr": max(
                [x for x in heart_rates if x is not None],
                default=None,
            ),
            "average_watt": average(actual_watts),
            "max_watt": max(actual_watts, default=None),
            "average_rpm": average(rpms),
            "distance": last_distance,
            "energy": last_energy,
            "log": str(log_path),
        }
        return result
