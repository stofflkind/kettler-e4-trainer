import json
from pathlib import Path
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from trainer_engine import TrainerEngine


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


state_lock = threading.Lock()

state = {
    "running": False,
    "device": None,
    "profile": None,
    "step": None,
    "step_name": None,
    "step_type": None,
    "step_duration": 0,
    "step_elapsed": 0,
    "step_remaining": 0,
    "next_step_name": None,
    "next_target_watt": None,
    "next_step_duration": 0,
    "elapsed": 0,
    "remaining": 0,
    "total_duration": 0,
    "heart_rate": None,
    "rpm": 0,
    "speed": 0.0,
    "distance": 0.0,
    "target_watt": 0,
    "actual_watt": 0,
    "energy": 0,
    "log": None,
    "completed": False,
    "error": None,
}

trainer_thread = None
trainer_engine = None


def update_state(data):
    with state_lock:
        state.update(data)


def trainer_message(text):
    print(text)


def format_profile_filename(name):
    # Nur Dateiname erlauben; verhindert ../ außerhalb von profiles.
    if Path(name).name != name:
        raise ValueError("Ungültiger Profilname")

    path = PROFILE_DIR / name
    if not path.exists() or path.suffix.lower() != ".json":
        raise FileNotFoundError(name)

    return path

def run_training(profile_path):
    global trainer_engine

    try:
        result = trainer_engine.run(profile_path)

        with state_lock:
            final_total_duration = state["total_duration"]
            final_elapsed = state["elapsed"]
            final_step_duration = state["step_duration"]
            final_step_elapsed = state["step_elapsed"]
            final_step_remaining = state["step_remaining"]
            final_remaining = state["remaining"]

        update_state({
            "running": False,
            "completed": result["completed"],
            "elapsed": (
                final_total_duration
                if result["completed"]
                else final_elapsed
            ),
            "remaining": (
                0
                if result["completed"]
                else final_remaining
            ),
            "total_duration": final_total_duration,
            "step_elapsed": (
                final_step_duration
                if result["completed"]
                else final_step_elapsed
            ),
            "step_remaining": (
                0
                if result["completed"]
                else final_step_remaining
            ),
            "log": result["log"],
        })

    except Exception as exc:
        update_state({
            "running": False,
            "completed": False,
            "error": str(exc),
        })

    finally:
        trainer_engine = None

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    profiles = sorted(
        p.name
        for p in PROFILE_DIR.glob("*.json")
    )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"profiles": profiles},
    )


@app.get("/api/status")
def api_status():
    with state_lock:
        return dict(state)

@app.get("/api/profile/{profile_name}")
def api_profile(profile_name: str):
    try:
        profile_path = format_profile_filename(profile_name)
    except Exception:
        raise HTTPException(
            status_code=404,
            detail="Profil nicht gefunden.",
        )

    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    steps = []
    current_time = 0

    for step in profile["steps"]:
        duration = int(step["duration"])
        step_type = step["type"]

        if step_type == "steady":
            start_watt = int(step["watts"])
            end_watt = start_watt

        elif step_type == "ramp":
            start_watt = int(step["start_watts"])
            end_watt = int(step["end_watts"])

        else:
            continue

        steps.append({
            "name": step["name"],
            "type": step_type,
            "duration": duration,
            "start_watt": start_watt,
            "end_watt": end_watt,
            "start_time": current_time,
            "end_time": current_time + duration,
        })

        current_time += duration

    return {
        "name": profile["name"],
        "heart_rate": profile.get("heart_rate"),
        "total_duration": current_time,
        "steps": steps,
    }


@app.post("/api/start")
def api_start(data: StartRequest):
    global trainer_thread, trainer_engine

    with state_lock:
        if state["running"]:
            raise HTTPException(
                status_code=409,
                detail="Training läuft bereits.",
            )

    try:
        profile_path = format_profile_filename(data.profile)
    except Exception:
        raise HTTPException(
            status_code=404,
            detail="Profil nicht gefunden.",
        )

    update_state({
        "running": True,
        "device": None,
        "profile": None,
        "step": None,
        "step_name": None,
        "step_type": None,
        "step_duration": 0,
        "step_elapsed": 0,
        "step_remaining": 0,
        "next_step_name": None,
        "next_target_watt": None,
        "next_step_duration": 0,
        "elapsed": 0,
        "remaining": 0,
        "total_duration": 0,
        "heart_rate": None,
        "rpm": 0,
        "speed": 0.0,
        "distance": 0.0,
        "target_watt": 0,
        "actual_watt": 0,
        "energy": 0,
        "log": None,
        "completed": False,
        "error": None,
    })

    trainer_engine = TrainerEngine(
        status_callback=update_state,
        message_callback=trainer_message,
    )

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
    if trainer_engine is None or not state["running"]:
        return {"status": "not_running"}

    trainer_engine.request_stop()
    return {"status": "stopping"}
