from pathlib import Path
import json
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from kettler_e4 import KettlerE4
from ant_hr import GarminHR


BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "profiles"

app = FastAPI()

templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)


class StartRequest(BaseModel):
    profile: str


state = {
    "running": False,
    "profile": None,
    "step": None,
    "step_name": None,
    "elapsed": 0,
    "remaining": 0,
    "heart_rate": None,
    "rpm": 0,
    "speed": 0.0,
    "distance": 0.0,
    "target_watt": 0,
    "actual_watt": 0,
    "energy": 0,
    "error": None,
}


stop_event = threading.Event()
trainer_thread = None


def format_profile_filename(name):
    path = PROFILE_DIR / name

    if not path.exists():
        raise FileNotFoundError(name)

    if path.suffix.lower() != ".json":
        raise ValueError("Ungültiges Profil")

    return path


def run_training(profile_path):
    global state

    kettler = KettlerE4()
    garmin = GarminHR(device_number=37409)

    try:
        with open(
            profile_path,
            "r",
            encoding="utf-8"
        ) as f:
            profile = json.load(f)

        state["running"] = True
        state["profile"] = profile["name"]
        state["error"] = None

        kettler.connect()
        kettler.enter_command_mode()

        garmin.start()

        training_start = time.monotonic()

        for step_number, step in enumerate(
            profile["steps"],
            start=1
        ):
            if stop_event.is_set():
                break

            duration = int(step["duration"])
            step_name = step.get(
                "name",
                f"Schritt {step_number}"
            )

            step_type = step.get(
                "type",
                "steady"
            )

            step_start = time.monotonic()
            step_end = step_start + duration

            state["step"] = step_number
            state["step_name"] = step_name

            if step_type == "steady":
                target = int(step["watts"])
                kettler.set_power(target)

            elif step_type == "ramp":
                start_watts = int(
                    step["start_watts"]
                )

                end_watts = int(
                    step["end_watts"]
                )

                kettler.set_power(
                    start_watts
                )

                target = start_watts

            else:
                raise ValueError(
                    f"Unbekannter Step-Typ: "
                    f"{step_type}"
                )

            last_ramp_update = step_start

            while not stop_event.is_set():
                now = time.monotonic()

                if now >= step_end:
                    break

                if step_type == "ramp":
                    progress = (
                        (now - step_start)
                        / duration
                    )

                    desired_target = round(
                        start_watts
                        + (
                            end_watts
                            - start_watts
                        )
                        * progress
                    )

                    if (
                        now - last_ramp_update
                        >= 2.0
                    ):
                        kettler.set_power(
                            desired_target
                        )

                        target = desired_target
                        last_ramp_update = now

                status = kettler.get_status()

                if status:
                    state["heart_rate"] = (
                        garmin.get_heart_rate()
                    )

                    state["rpm"] = status["rpm"]
                    state["speed"] = status["speed"]
                    state["distance"] = (
                        status["distance"]
                    )

                    state["target_watt"] = (
                        status["target_watt"]
                    )

                    state["actual_watt"] = (
                        status["actual_watt"]
                    )

                    state["energy"] = (
                        status["energy"]
                    )

                    state["elapsed"] = int(
                        now - training_start
                    )

                    state["remaining"] = int(
                        step_end - now
                    )

                time.sleep(1)

            if step_type == "ramp":
                kettler.set_power(
                    end_watts
                )

        kettler.set_power(80)

    except Exception as exc:
        state["error"] = str(exc)

    finally:
        state["running"] = False

        try:
            kettler.set_power(80)
        except Exception:
            pass

        try:
            garmin.stop()
        except Exception:
            pass

        try:
            kettler.close()
        except Exception:
            pass


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    profiles = sorted(
        p.name
        for p in PROFILE_DIR.glob("*.json")
    )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "profiles": profiles,
        },
    )	

@app.get("/api/status")
def api_status():
    return state


@app.post("/api/start")
def api_start(data: StartRequest):
    global trainer_thread

    if state["running"]:
        raise HTTPException(
            status_code=409,
            detail="Training läuft bereits."
        )

    try:
        profile_path = (
            format_profile_filename(
                data.profile
            )
        )
    except Exception:
        raise HTTPException(
            status_code=404,
            detail="Profil nicht gefunden."
        )

    stop_event.clear()

    trainer_thread = threading.Thread(
        target=run_training,
        args=(profile_path,),
        daemon=True,
    )

    trainer_thread.start()

    return {
        "status": "started",
        "profile": data.profile,
    }


@app.post("/api/stop")
def api_stop():
    if not state["running"]:
        return {
            "status": "not_running"
        }

    stop_event.set()

    return {
        "status": "stopping"
    }
