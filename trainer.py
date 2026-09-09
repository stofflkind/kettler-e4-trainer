import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from kettler_e4 import KettlerE4
from ant_hr import GarminHR


DEFAULT_END_WATT = 80
SAMPLE_INTERVAL = 1.0
RAMP_UPDATE_INTERVAL = 2.0


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
            raise ValueError(
                f"Schritt {i}: duration fehlt."
            )

        duration = int(step["duration"])

        if duration <= 0:
            raise ValueError(
                f"Schritt {i}: duration muss > 0 sein."
            )

        if step_type == "steady":
            if "watts" not in step:
                raise ValueError(
                    f"Schritt {i}: watts fehlt."
                )

            watts = int(step["watts"])

            if watts <= 0:
                raise ValueError(
                    f"Schritt {i}: watts muss > 0 sein."
                )

        elif step_type == "ramp":
            if (
                "start_watts" not in step
                or "end_watts" not in step
            ):
                raise ValueError(
                    f"Schritt {i}: "
                    "start_watts oder end_watts fehlt."
                )

            start_watts = int(step["start_watts"])
            end_watts = int(step["end_watts"])

            if start_watts <= 0:
                raise ValueError(
                    f"Schritt {i}: "
                    "start_watts muss > 0 sein."
                )

            if end_watts <= 0:
                raise ValueError(
                    f"Schritt {i}: "
                    "end_watts muss > 0 sein."
                )

        else:
            raise ValueError(
                f"Schritt {i}: "
                f"unbekannter Typ '{step_type}'."
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

    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    filename = (
        f"{timestamp}_"
        f"{slugify(profile_name)}.csv"
    )

    return log_dir / filename


def average(values):
    valid_values = [
        value
        for value in values
        if value is not None
    ]

    if not valid_values:
        return None

    return sum(valid_values) / len(valid_values)


def ramp_watts(step, elapsed):
    duration = float(step["duration"])
    start_watts = float(step["start_watts"])
    end_watts = float(step["end_watts"])

    progress = elapsed / duration

    progress = min(
        1.0,
        max(0.0, progress)
    )

    watts = (
        start_watts
        + (end_watts - start_watts)
        * progress
    )

    return int(round(watts))


def main():
    if len(sys.argv) != 2:
        print("Aufruf:")
        print()
        print(
            "  python3 trainer.py "
            "profiles/grundlage1.json"
        )
        print()

        sys.exit(1)

    profile_path = sys.argv[1]

    try:
        profile = load_profile(profile_path)

    except Exception as exc:
        print(
            f"Profil konnte nicht geladen werden: "
            f"{exc}"
        )
        sys.exit(1)

    kettler = KettlerE4()
    garmin = GarminHR(
        device_number=37409
    )

    total_duration = sum(
        int(step["duration"])
        for step in profile["steps"]
    )

    log_path = create_log_file(
        profile["name"]
    )

    heart_rates = []
    actual_watts = []
    rpms = []

    last_distance = None
    last_energy = None

    training_start = None

    print()
    print("Kettler E4 Trainer")
    print("------------------")
    print(
        f"Profil : "
        f"{profile['name']}"
    )
    print(
        f"Dauer  : "
        f"{format_seconds(total_duration)}"
    )
    print(
        f"Log    : "
        f"{log_path}"
    )
    print()

    try:
        kettler.connect()

        print(
            "Kettler:",
            kettler.get_id()
        )

        print(
            "Version:",
            kettler.get_version()
        )

        response = kettler.enter_command_mode()

        if response != "ACK":
            print(
                "WARNUNG: "
                "Command Mode Antwort:",
                response
            )

        garmin.start()

        print(
            "Garmin HRM gestartet"
        )
        print()
        print(
            "Training startet ..."
        )
        print(
            "Abbruch mit Ctrl-C"
        )
        print()

        with open(
            log_path,
            "w",
            newline="",
            encoding="utf-8"
        ) as csvfile:

            writer = csv.writer(
                csvfile,
                delimiter=";"
            )

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

            next_sample = training_start

            for step_number, step in enumerate(
                profile["steps"],
                start=1
            ):
                duration = int(
                    step["duration"]
                )

                step_name = step["name"]
                step_type = step["type"]

                step_start = time.monotonic()
                step_end = (
                    step_start
                    + duration
                )

                print()
                print(
                    f"Schritt "
                    f"{step_number}/"
                    f"{len(profile['steps'])}: "
                    f"{step_name}"
                )

                current_target = None

                if step_type == "steady":
                    watts = int(
                        step["watts"]
                    )

                    print(
                        f"{watts} W für "
                        f"{format_seconds(duration)}"
                    )

                    kettler.set_power(
                        watts
                    )

                    current_target = watts

                else:
                    start_watts = int(
                        step["start_watts"]
                    )

                    end_watts = int(
                        step["end_watts"]
                    )

                    print(
                        f"Rampe "
                        f"{start_watts} -> "
                        f"{end_watts} W in "
                        f"{format_seconds(duration)}"
                    )

                    kettler.set_power(
                        start_watts
                    )

                    current_target = (
                        start_watts
                    )

                last_ramp_update = (
                    step_start
                )

                while True:
                    now = time.monotonic()

                    if now >= step_end:
                        break

                    step_elapsed = (
                        now - step_start
                    )

                    if step_type == "ramp":
                        desired_target = (
                            ramp_watts(
                                step,
                                step_elapsed
                            )
                        )

                        if (
                            now
                            - last_ramp_update
                            >= RAMP_UPDATE_INTERVAL
                        ):
                            if (
                                desired_target
                                != current_target
                            ):
                                kettler.set_power(
                                    desired_target
                                )

                                current_target = (
                                    desired_target
                                )

                            last_ramp_update = (
                                now
                            )

                    if now < next_sample:
                        time.sleep(
                            next_sample - now
                        )

                    now = time.monotonic()

                    if now >= step_end:
                        break

                    status = (
                        kettler.get_status()
                    )

                    if status is None:
                        print(
                            "Ungültige "
                            "Kettler-Antwort"
                        )

                        next_sample += (
                            SAMPLE_INTERVAL
                        )

                        continue

                    hr = (
                        garmin.get_heart_rate()
                    )

                    elapsed = (
                        now - training_start
                    )

                    remaining_step = (
                        step_end - now
                    )

                    heart_rates.append(hr)

                    actual_watts.append(
                        status[
                            "actual_watt"
                        ]
                    )

                    rpms.append(
                        status["rpm"]
                    )

                    last_distance = (
                        status["distance"]
                    )

                    last_energy = (
                        status["energy"]
                    )

                    writer.writerow([
                        datetime.now().isoformat(
                            timespec="seconds"
                        ),
                        round(elapsed, 1),
                        step_number,
                        step_name,
                        step_type,
                        status[
                            "target_watt"
                        ],
                        status[
                            "actual_watt"
                        ],
                        (
                            hr
                            if hr is not None
                            else ""
                        ),
                        status["rpm"],
                        status["speed"],
                        status["distance"],
                        status["energy"],
                    ])

                    csvfile.flush()

                    if hr is None:
                        hr_text = "---"
                    else:
                        hr_text = f"{hr:3d}"

                    print(
                        f"{format_seconds(elapsed)}"
                        f" | "
                        f"Rest "
                        f"{format_seconds(remaining_step)}"
                        f" | "
                        f"Puls {hr_text}"
                        f" | "
                        f"RPM "
                        f"{status['rpm']:3d}"
                        f" | "
                        f"Soll "
                        f"{status['target_watt']:3d} W"
                        f" | "
                        f"Ist "
                        f"{status['actual_watt']:3d} W"
                        f" | "
                        f"{status['speed']:4.1f} km/h"
                        f" | "
                        f"{status['distance']:4.1f} km"
                    )

                    next_sample += (
                        SAMPLE_INTERVAL
                    )

                #
                # Bei Rampen den definierten
                # Endwert garantiert setzen.
                #
                if step_type == "ramp":
                    end_watts = int(
                        step["end_watts"]
                    )

                    if (
                        current_target
                        != end_watts
                    ):
                        kettler.set_power(
                            end_watts
                        )

                        current_target = (
                            end_watts
                        )

        print()
        print(
            "Training vollständig "
            "abgeschlossen."
        )

    except KeyboardInterrupt:
        print()
        print(
            "Training abgebrochen."
        )

    except Exception as exc:
        print()
        print(
            "FEHLER:",
            exc
        )

    finally:
        if training_start is not None:
            elapsed_total = (
                time.monotonic()
                - training_start
            )
        else:
            elapsed_total = 0

        print()
        print(
            f"Setze Abschlussleistung "
            f"auf {DEFAULT_END_WATT} W ..."
        )

        try:
            kettler.set_power(
                DEFAULT_END_WATT
            )

        except Exception as exc:
            print(
                "WARNUNG: Leistung "
                "konnte nicht "
                "zurückgesetzt werden:",
                exc
            )

        try:
            garmin.stop()

        except Exception:
            pass

        try:
            kettler.close()

        except Exception:
            pass

        avg_hr = average(
            heart_rates
        )

        avg_watt = average(
            actual_watts
        )

        avg_rpm = average(
            rpms
        )

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
        print(
            "Trainingszusammenfassung"
        )
        print(
            "------------------------"
        )

        print(
            f"Dauer:        "
            f"{format_seconds(elapsed_total)}"
        )

        if avg_hr is not None:
            print(
                f"Ø Puls:       "
                f"{avg_hr:.0f} bpm"
            )

            print(
                f"Max Puls:     "
                f"{max(valid_hr)} bpm"
            )

        if avg_watt is not None:
            print(
                f"Ø Leistung:   "
                f"{avg_watt:.0f} W"
            )

            print(
                f"Max Leistung: "
                f"{max(valid_watt)} W"
            )

        if avg_rpm is not None:
            print(
                f"Ø Kadenz:     "
                f"{avg_rpm:.0f} rpm"
            )

        if last_distance is not None:
            print(
                f"Distanz:      "
                f"{last_distance:.1f} km"
            )

        if last_energy is not None:
            print(
                f"Energie:      "
                f"{last_energy} kJ"
            )

        print()
        print(
            f"CSV-Log: "
            f"{log_path}"
        )

        print(
            "Geräte geschlossen."
        )


if __name__ == "__main__":
    main()
