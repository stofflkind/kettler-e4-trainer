import sys

from trainer_engine import (
    TrainerEngine,
    format_seconds,
    load_profile,
)


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

    total_duration = sum(
        int(step["duration"])
        for step in profile["steps"]
    )

    print()
    print("Kettler E4 Trainer")
    print("------------------")
    print(f"Profil : {profile['name']}")
    print(f"Dauer  : {format_seconds(total_duration)}")
    print()
    print("Training startet ...")
    print("Abbruch mit Ctrl-C")
    print()

    last_step = None

    def message(text):
        print(text)

    def status(data):
        nonlocal last_step

        if data.get("step") is None:
            return

        if data["step"] != last_step:
            last_step = data["step"]
            print()
            print(
                f"Schritt {data['step']}: "
                f"{data['step_name']}"
            )

        hr = data["heart_rate"]
        hr_text = "---" if hr is None else f"{hr:3d}"

        print(
            f"{format_seconds(data['elapsed'])}"
            f" | Rest {format_seconds(data['remaining'])}"
            f" | Puls {hr_text}"
            f" | RPM {data['rpm']:3d}"
            f" | Soll {data['target_watt']:3d} W"
            f" | Ist {data['actual_watt']:3d} W"
            f" | {data['speed']:4.1f} km/h"
            f" | {data['distance']:4.1f} km"
        )

    engine = TrainerEngine(
        status_callback=status,
        message_callback=message,
    )

    try:
        result = engine.run(profile_path)
    except KeyboardInterrupt:
        engine.request_stop()
        print()
        print("Training abgebrochen.")
        return
    except Exception as exc:
        print()
        print("FEHLER:", exc)
        return

    print()
    if result["completed"]:
        print("Training vollständig abgeschlossen.")
    else:
        print("Training abgebrochen.")

    print()
    print("Trainingszusammenfassung")
    print("------------------------")
    print(
        f"Dauer:        "
        f"{format_seconds(result['duration'])}"
    )

    if result["average_hr"] is not None:
        print(f"Ø Puls:       {result['average_hr']:.0f} bpm")
        print(f"Max Puls:     {result['max_hr']} bpm")

    if result["average_watt"] is not None:
        print(f"Ø Leistung:   {result['average_watt']:.0f} W")
        print(f"Max Leistung: {result['max_watt']} W")

    if result["average_rpm"] is not None:
        print(f"Ø Kadenz:     {result['average_rpm']:.0f} rpm")

    if result["distance"] is not None:
        print(f"Distanz:      {result['distance']:.1f} km")

    if result["energy"] is not None:
        print(f"Energie:      {result['energy']} kJ")

    print()
    print(f"CSV-Log: {result['log']}")
    print("Geräte geschlossen.")


if __name__ == "__main__":
    main()
