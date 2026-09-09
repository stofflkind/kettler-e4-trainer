function formatTime(seconds) {
    seconds = Math.max(
        0,
        Math.floor(seconds || 0)
    );

    const minutes = Math.floor(
        seconds / 60
    );

    const secs = seconds % 60;

    return (
        String(minutes).padStart(2, "0")
        + ":"
        + String(secs).padStart(2, "0")
    );
}


async function updateStatus() {
    try {
        const response = await fetch(
            "/api/status"
        );

        const data = await response.json();

        document.getElementById(
            "actualWatt"
        ).textContent =
            data.actual_watt ?? 0;

        document.getElementById(
            "targetWatt"
        ).textContent =
            data.target_watt ?? 0;

        document.getElementById(
            "heartRate"
        ).textContent =
            data.heart_rate ?? "---";

        document.getElementById(
            "rpm"
        ).textContent =
            data.rpm ?? 0;

        document.getElementById(
            "speed"
        ).textContent =
            Number(
                data.speed || 0
            ).toFixed(1);

        document.getElementById(
            "distance"
        ).textContent =
            Number(
                data.distance || 0
            ).toFixed(1);

        document.getElementById(
            "energy"
        ).textContent =
            data.energy ?? 0;

        document.getElementById(
            "profileName"
        ).textContent =
            data.profile || "-";

        document.getElementById(
            "stepName"
        ).textContent =
            data.step_name || "-";

        document.getElementById(
            "elapsed"
        ).textContent =
            formatTime(
                data.elapsed
            );

        document.getElementById(
            "remaining"
        ).textContent =
            formatTime(
                data.remaining
            );

        const errorBox =
            document.getElementById(
                "error"
            );

        if (data.error) {
            errorBox.textContent =
                data.error;
        } else {
            errorBox.textContent = "";
        }

        document.getElementById(
            "startButton"
        ).disabled = data.running;

        document.getElementById(
            "stopButton"
        ).disabled = !data.running;

    } catch (error) {
        console.error(error);
    }
}


document.getElementById(
    "startButton"
).addEventListener(
    "click",
    async () => {

        const profile =
            document.getElementById(
                "profile"
            ).value;

        const response = await fetch(
            "/api/start",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({
                    profile: profile
                })
            }
        );

        if (!response.ok) {
            const data =
                await response.json();

            alert(
                data.detail ||
                "Training konnte nicht gestartet werden."
            );
        }

        updateStatus();
    }
);


document.getElementById(
    "stopButton"
).addEventListener(
    "click",
    async () => {

        await fetch(
            "/api/stop",
            {
                method: "POST"
            }
        );

        updateStatus();
    }
);


updateStatus();

setInterval(
    updateStatus,
    1000
);
