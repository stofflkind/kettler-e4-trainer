import csv
import json
import re
import sys
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

# ANT+ network / devices
ANT_NETWORK_KEY = [
    0xB9, 0xA5, 0x21, 0xFB,
    0xBD, 0x72, 0xC3, 0x45,
]

# Garmin HRM
HR_DEVICE_NUMBER = 37409
HR_DEVICE_TYPE = 120
HR_CHANNEL_PERIOD = 8070

# Virtual ANT+ Bicycle Power sensor
POWER_DEVICE_NUMBER = 12345
POWER_DEVICE_TYPE = 11
POWER_TRANSMISSION_TYPE = 5
POWER_CHANNEL_PERIOD = 8182

ANT_RF_FREQUENCY = 57


class AntRadio:
    """One ANTUSB-m, two ANT+ channels: HR receive + Bicycle Power transmit."""

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
        self.thread = None

        self.lock = threading.Lock()
        self.heart_rate = None
        self.power = 0
        self.cadence = 0
        self.event_count = 0
        self.accumulated_power = 0

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
        # ANT broadcasts at about 4 Hz, but event_count and accumulated_power
        # change only when update_power() receives a new Kettler sample.
        with self.lock:
            page = self._power_page_locked()

        self.power_channel.send_broadcast_data(page)

    def start(self):
        self.node = Node()
        self.node.set_network_key(0x00, ANT_NETWORK_KEY)

        # Channel 1: Garmin HRM -> computer
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

        # Channel 2: computer -> Garmin watch as virtual power meter
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

        self.hr_channel.open()
        self.power_channel.open()

        # Provide a valid initial page before the first Kettler sample arrives.
        with self.lock:
            page = self._power_page_locked()
        self.power_channel.send_broadcast_data(page)

        self.thread = threading.Thread(
            target=self.node.start,
            daemon=True,
        )
        self.thread.start()

    def update_power(self, power, cadence):
        """Publish one new Kettler sample to the ANT+ Bicycle Power state."""
        power = max(0, min(int(power), 65535))
        cadence = max(0, min(int(cadence), 254))

        with self.lock:
            self.power = power
            self.cadence = cadence
            self.event_count = (self.event_count + 1) & 0xFF
            self.accumulated_power = (
                self.accumulated_power + power
            ) & 0xFFFF

    def get_heart_rate(self):
        with self.lock:
            return self.heart_rate

    def stop(self):
        for channel in (self.hr_channel, self.power_channel):
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

        if "name" not in step:
            step["name"] = f"Schritt {i}"

        if "duration" not in step:
            raise ValueError(f"Schritt {i}: duration fehlt.")

        duration = int(step["duration"])
        if duration <= 0:
            raise ValueError(f"Schritt {i}: duration muss > 0 sein.")

        if step_type == "steady":
            if "watts" not in step:
                raise ValueError(f"Schritt {i}: watts fehlt.")

            watts = int(step["watts"])
            if watts <= 0:
                raise ValueError(f"Schritt {i}: watts muss > 0 sein.")

        elif step_type == "ramp":
            if "start_watts" not in step or "end_watts" not in step:
                raise ValueError(
                    f"Schritt {i}: start_watts oder end_watts fehlt."
                )

            start_watts = int(step["start_watts"])
            end_watts = int(step["end_watts"])

            if start_watts <= 0:
                raise ValueError(
                    f"Schritt {i}: start_watts muss > 0 sein."
                )
            if end_watts <= 0:
                raise ValueError(
                    f"Schritt {i}: end_watts muss > 0 sein."
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
    text = text.replace("ä", "ae")
    text = text.replace("ö", "oe")
    text = text.replace("ü", "ue")
    text = text.replace("ß", "ss")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def create_log_file(profile_name):
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{timestamp}_{slugify(profile_name)}.csv"
    return log_dir / filename


def average(values):
    valid_values = [value for value in values if value is not None]
    if not valid_values:
        return None
    return sum(valid_values) / len(valid_values)


def ramp_watts(step, elapsed):
    duration = float(step["duration"])
    start_watts = float(step["start_watts"])
    end_watts = float(step["end_watts"])

    progress = min(1.0, max(0.0, elapsed / duration))
    watts = start_watts + (end_watts - start_watts) * progress
    return int(round(watts))


def main():
    if len(sys.argv) != 2:
        print("Aufruf:")
        print()
        print("  python3 trainer.py profiles/grundlage1.json")
        print()
        sys.exit(1)

    profile_path = sys.argv[1]

    try:
        profile = load_profile(profile_path)
    except Exception as exc:
        print(f"Profil konnte nicht geladen werden: {exc}")
        sys.exit(1)

    kettler = KettlerE4()
    ant = AntRadio()

    total_duration = sum(
        int(step["duration"])
        for step in profile["steps"]
    )

    log_path = create_log_file(profile["name"])

    heart_rates = []
    actual_watts = []
    rpms = []

    last_distance = None
    last_energy = None
    training_start = None

    print()
    print("Kettler E4 Trainer")
    print("------------------")
    print(f"Profil : {profile['name']}")
    print(f"Dauer  : {format_seconds(total_duration)}")
    print(f"Log    : {log_path}")
    print()

    try:
        kettler.connect()

        print("Kettler:", kettler.get_id())
        print("Version:", kettler.get_version())

        response = kettler.enter_command_mode()
        if response != "ACK":
            print("WARNUNG: Command Mode Antwort:", response)

        ant.start()
        print(
            f"ANT+ gestartet: HRM {HR_DEVICE_NUMBER} empfangen, "
            f"Power-Sensor {POWER_DEVICE_NUMBER} senden"
        )
        print()
        print("Training startet ...")
        print("Abbruch mit Ctrl-C")
        print()

        with open(
            log_path,
            "w",
            newline="",
            encoding="utf-8",
        ) as csvfile:
            writer = csv.writer(csvfile, delimiter=";")
            writer.writerow([
                "timestamp",
                "elapsed_s",
                "step",
                "step_name",
                "step_type",
                "target_watt",
                "actual_watt",
                "heart_rate",
                "rpm",
                "speed_kmh",
                "distance_km",
                "energy_kj",
            ])

            training_start = time.monotonic()

            for step_number, step in enumerate(
                profile["steps"],
                start=1,
            ):
                duration = int(step["duration"])
                step_name = step["name"]
                step_type = step["type"]

                # Schrittgrenzen aus der geplanten Trainingszeit ableiten.
                # Dadurch entstehen an Übergängen keine zusätzlichen
                # Messpunkte durch Laufzeitdrift.
                planned_step_start = sum(
                    int(s["duration"])
                    for s in profile["steps"][:step_number - 1]
                )
                step_start = training_start + planned_step_start
                step_end = step_start + duration

                # Genau ein Messpunkt pro Sekunde und Schritt:
                # t = 0, 1, ..., duration - 1.
                sample_index = 0
                next_sample = step_start

                print()
                print(
                    f"Schritt {step_number}/{len(profile['steps'])}: "
                    f"{step_name}"
                )

                current_target = None

                if step_type == "steady":
                    watts = int(step["watts"])
                    print(
                        f"{watts} W für {format_seconds(duration)}"
                    )
                    kettler.set_power(watts)
                    current_target = watts

                else:
                    start_watts = int(step["start_watts"])
                    end_watts = int(step["end_watts"])
                    print(
                        f"Rampe {start_watts} -> {end_watts} W in "
                        f"{format_seconds(duration)}"
                    )
                    kettler.set_power(start_watts)
                    current_target = start_watts

                last_ramp_update = step_start

                while sample_index < duration:
                    now = time.monotonic()

                    if now < next_sample:
                        time.sleep(next_sample - now)

                    now = time.monotonic()
                    step_elapsed = max(0.0, now - step_start)

                    if step_type == "ramp":
                        desired_target = ramp_watts(step, step_elapsed)

                        if now - last_ramp_update >= RAMP_UPDATE_INTERVAL:
                            if desired_target != current_target:
                                kettler.set_power(desired_target)
                                current_target = desired_target
                            last_ramp_update = now

                    status = kettler.get_status()

                    if status is None:
                        print("Ungültige Kettler-Antwort")
                        sample_index += 1
                        next_sample = (
                            step_start
                            + sample_index * SAMPLE_INTERVAL
                        )
                        continue

                    # This is the single authoritative Kettler sample used for
                    # ANT+ transmission, logging and terminal output.
                    ant.update_power(
                        status["actual_watt"],
                        status["rpm"],
                    )

                    hr = ant.get_heart_rate()
                    elapsed = now - training_start
                    remaining_step = step_end - now

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

                    hr_text = "---" if hr is None else f"{hr:3d}"

                    print(
                        f"{format_seconds(elapsed)}"
                        f" | Rest {format_seconds(remaining_step)}"
                        f" | Puls {hr_text}"
                        f" | RPM {status['rpm']:3d}"
                        f" | Soll {status['target_watt']:3d} W"
                        f" | Ist {status['actual_watt']:3d} W"
                        f" | {status['speed']:4.1f} km/h"
                        f" | {status['distance']:4.1f} km"
                    )

                    sample_index += 1
                    next_sample = (
                        step_start
                        + sample_index * SAMPLE_INTERVAL
                    )

                # Guarantee the defined ramp endpoint is sent to the E4.
                if step_type == "ramp":
                    end_watts = int(step["end_watts"])
                    if current_target != end_watts:
                        kettler.set_power(end_watts)
                        current_target = end_watts

        print()
        print("Training vollständig abgeschlossen.")

    except KeyboardInterrupt:
        print()
        print("Training abgebrochen.")

    except Exception as exc:
        print()
        print("FEHLER:", exc)

    finally:
        if training_start is not None:
            elapsed_total = time.monotonic() - training_start
        else:
            elapsed_total = 0

        print()
        print(
            f"Setze Abschlussleistung auf {DEFAULT_END_WATT} W ..."
        )

        try:
            kettler.set_power(DEFAULT_END_WATT)
        except Exception as exc:
            print(
                "WARNUNG: Leistung konnte nicht zurückgesetzt werden:",
                exc,
            )

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

        avg_hr = average(heart_rates)
        avg_watt = average(actual_watts)
        avg_rpm = average(rpms)

        valid_hr = [
            value
            for value in heart_rates
            if value is not None
        ]
        valid_watt = [
            value
            for value in actual_watts
            if value is not None
        ]

        print()
        print("Trainingszusammenfassung")
        print("------------------------")
        print(f"Dauer:        {format_seconds(elapsed_total)}")

        if avg_hr is not None:
            print(f"Ø Puls:       {avg_hr:.0f} bpm")
            print(f"Max Puls:     {max(valid_hr)} bpm")

        if avg_watt is not None:
            print(f"Ø Leistung:   {avg_watt:.0f} W")
            print(f"Max Leistung: {max(valid_watt)} W")

        if avg_rpm is not None:
            print(f"Ø Kadenz:     {avg_rpm:.0f} rpm")

        if last_distance is not None:
            print(f"Distanz:      {last_distance:.1f} km")

        if last_energy is not None:
            print(f"Energie:      {last_energy} kJ")

        print()
        print(f"CSV-Log: {log_path}")
        print("Geräte geschlossen.")


if __name__ == "__main__":
    main()
