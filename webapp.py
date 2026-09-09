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
    "profile": None,
    "step": None,
    "step_name": None,
    "step_type": None,
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

        update_state({
            "running": False,
            "completed": result["completed"],
            "remaining": 0 if result["completed"] else state["remaining"],
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
        "profile": None,
        "step": None,
        "step_name": None,
        "step_type": None,
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
