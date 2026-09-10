function formatTime(seconds) {
    seconds = Math.max(0, Math.floor(Number(seconds) || 0));

    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;

    return (
        String(minutes).padStart(2, "0")
        + ":"
        + String(secs).padStart(2, "0")
    );
}


function clampPercent(value) {
    return Math.max(0, Math.min(100, value));
}


function calculateProgress(elapsed, duration) {
    elapsed = Number(elapsed) || 0;
    duration = Number(duration) || 0;

    if (duration <= 0) {
        return 0;
    }

    return clampPercent((elapsed / duration) * 100);
}


function setProgress(elementId, percent) {
    document.getElementById(elementId).style.width =
        `${percent.toFixed(1)}%`;
}


function updateTrainingBadge(running, completed) {
    const badge = document.getElementById("trainingBadge");

    badge.classList.remove("running", "idle", "completed");

    if (running) {
        badge.textContent = "Training läuft";
        badge.classList.add("running");
    } else if (completed) {
        badge.textContent = "Training beendet";
        badge.classList.add("completed");
    } else {
        badge.textContent = "Bereit";
        badge.classList.add("idle");
    }
}


function updateNextStep(data) {
    const nextName = document.getElementById("nextStepName");
    const nextDetails = document.getElementById("nextStepDetails");

    if (!data.running) {
        nextName.textContent = "–";
        nextDetails.textContent = "–";
        return;
    }

    if (!data.next_step_name) {
        nextName.textContent = "Letzter Abschnitt";
        nextDetails.textContent = "Danach ist das Training beendet";
        return;
    }

    nextName.textContent = data.next_step_name;

    const watts = data.next_target_watt == null
        ? "–"
        : `${data.next_target_watt} W`;

    nextDetails.textContent =
        `${watts} · ${formatTime(data.next_step_duration)}`;
}


async function updateStatus() {
    try {
        const response = await fetch("/api/status");

        if (!response.ok) {
            throw new Error(
                `Status konnte nicht geladen werden (${response.status})`
            );
        }

        const data = await response.json();

        document.getElementById("actualWatt").textContent =
            data.actual_watt ?? 0;

        document.getElementById("targetWatt").textContent =
            data.target_watt ?? 0;

        document.getElementById("heartRate").textContent =
            data.heart_rate ?? "---";

        document.getElementById("rpm").textContent =
            data.rpm ?? 0;

        document.getElementById("speed").textContent =
            Number(data.speed || 0).toFixed(1);

        document.getElementById("distance").textContent =
            Number(data.distance || 0).toFixed(1);

        document.getElementById("energy").textContent =
            data.energy ?? 0;

        document.getElementById("profileName").textContent =
            data.profile || "–";

        document.getElementById("stepName").textContent =
            data.step_name || "Noch kein Training";

        document.getElementById("stepElapsed").textContent =
            formatTime(data.step_elapsed);

        document.getElementById("stepRemaining").textContent =
            formatTime(data.step_remaining);

        document.getElementById("stepDuration").textContent =
            formatTime(data.step_duration);

        document.getElementById("elapsed").textContent =
            formatTime(data.elapsed);

        document.getElementById("remaining").textContent =
            formatTime(data.remaining);

        document.getElementById("totalDuration").textContent =
            formatTime(data.total_duration);

        setProgress(
            "stepProgress",
            calculateProgress(
                data.step_elapsed,
                data.step_duration
            )
        );

        setProgress(
            "overallProgress",
            calculateProgress(
                data.elapsed,
                data.total_duration
            )
        );

        updateNextStep(data);
        updateTrainingBadge(data.running, data.completed);

        const errorBox = document.getElementById("error");

        if (data.error) {
            errorBox.textContent = data.error;
            errorBox.classList.add("visible");
        } else {
            errorBox.textContent = "";
            errorBox.classList.remove("visible");
        }

        document.getElementById("startButton").disabled =
            Boolean(data.running);

        document.getElementById("stopButton").disabled =
            !data.running;

        document.getElementById("profile").disabled =
            Boolean(data.running);

    } catch (error) {
        console.error(error);

        const errorBox = document.getElementById("error");

        errorBox.textContent =
            "Verbindung zum Trainer-Backend unterbrochen.";

        errorBox.classList.add("visible");
    }
}


document.getElementById("startButton").addEventListener(
    "click",
    async () => {
        const profile =
            document.getElementById("profile").value;

        try {
            const response = await fetch(
                "/api/start",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        profile: profile
                    })
                }
            );

            if (!response.ok) {
                const data = await response.json();

                alert(
                    data.detail
                    || "Training konnte nicht gestartet werden."
                );
            }
        } catch (error) {
            console.error(error);

            alert(
                "Trainer-Backend ist nicht erreichbar."
            );
        }

        updateStatus();
    }
);


document.getElementById("stopButton").addEventListener(
    "click",
    async () => {
        try {
            await fetch(
                "/api/stop",
                {
                    method: "POST"
                }
            );
        } catch (error) {
            console.error(error);
        }

        updateStatus();
    }
);


updateStatus();

setInterval(updateStatus, 1000);
