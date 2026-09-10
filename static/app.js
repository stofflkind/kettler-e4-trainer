let profileHeartRate = null;


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


async function loadProfileChart(profileName) {
    const response = await fetch(
        `/api/profile/${encodeURIComponent(profileName)}`
    );

    if (!response.ok) {
        throw new Error(
            "Trainingsprofil konnte nicht geladen werden."
        );
    }

    const profile = await response.json();

    profileHeartRate = profile.heart_rate ?? null;

    drawProfileChart(profile);
}


function drawProfileChart(profile) {
    const svg = document.getElementById("profileChart");

    if (!svg) {
        return;
    }

    const width = 1000;
    const height = 260;

    const padding = {
        left: 60,
        right: 20,
        top: 20,
        bottom: 35
    };

    svg.innerHTML = "";

    if (!profile.steps || profile.steps.length === 0) {
        return;
    }

    const maxWatt = Math.max(
        ...profile.steps.flatMap(step => [
            step.start_watt,
            step.end_watt
        ])
    );

    const minWatt = Math.min(
        ...profile.steps.flatMap(step => [
            step.start_watt,
            step.end_watt
        ])
    );

    const chartWidth =
        width - padding.left - padding.right;

    const chartHeight =
        height - padding.top - padding.bottom;

    const wattPadding = Math.max(
        20,
        Math.round((maxWatt - minWatt) * 0.2)
    );

    const yMin =
        Math.max(0, minWatt - wattPadding);

    const yMax =
        maxWatt + wattPadding;

    function xForTime(seconds) {
        return (
            padding.left
            + (seconds / profile.total_duration) * chartWidth
        );
    }

    function yForWatt(watt) {
        return (
            padding.top
            + (
                1
                - (
                    (watt - yMin)
                    / (yMax - yMin)
                )
            ) * chartHeight
        );
    }

    const ns =
        "http://www.w3.org/2000/svg";


    // Horizontale Hilfslinien und Watt-Achse
    const gridValues = 4;

    for (let i = 0; i <= gridValues; i++) {
        const watt =
            yMin
            + (
                (yMax - yMin)
                * i
                / gridValues
            );

        const y =
            yForWatt(watt);

        const line =
            document.createElementNS(ns, "line");

        line.setAttribute(
            "x1",
            padding.left
        );

        line.setAttribute(
            "x2",
            width - padding.right
        );

        line.setAttribute(
            "y1",
            y
        );

        line.setAttribute(
            "y2",
            y
        );

        line.setAttribute(
            "class",
            "profile-grid-line"
        );

        svg.appendChild(line);

        const label =
            document.createElementNS(ns, "text");

        label.setAttribute(
            "x",
            padding.left - 10
        );

        label.setAttribute(
            "y",
            y + 4
        );

        label.setAttribute(
            "text-anchor",
            "end"
        );

        label.setAttribute(
            "class",
            "profile-axis-label"
        );

        label.textContent =
            `${Math.round(watt)} W`;

        svg.appendChild(label);
    }


    // Zeitachse
    const timeMarks = 5;

    for (let i = 0; i <= timeMarks; i++) {
        const seconds =
            profile.total_duration
            * i
            / timeMarks;

        const x =
            xForTime(seconds);

        const label =
            document.createElementNS(ns, "text");

        label.setAttribute(
            "x",
            x
        );

        label.setAttribute(
            "y",
            height - 10
        );

        label.setAttribute(
            "text-anchor",
            "middle"
        );

        label.setAttribute(
            "class",
            "profile-axis-label"
        );

        label.textContent =
            formatTime(seconds);

        svg.appendChild(label);
    }


    // Profilpfad
    let pathData = "";

    profile.steps.forEach((step, index) => {
        const x1 =
            xForTime(step.start_time);

        const x2 =
            xForTime(step.end_time);

        const y1 =
            yForWatt(step.start_watt);

        const y2 =
            yForWatt(step.end_watt);

        if (index === 0) {
            pathData +=
                `M ${x1} ${y1} `;
        }

        pathData +=
            `L ${x2} ${y2} `;

        const nextStep =
            profile.steps[index + 1];

        if (nextStep) {
            const nextY =
                yForWatt(
                    nextStep.start_watt
                );

            pathData +=
                `L ${x2} ${nextY} `;
        }
    });

    const path =
        document.createElementNS(ns, "path");

    path.setAttribute(
        "d",
        pathData
    );

    path.setAttribute(
        "class",
        "profile-line"
    );

    svg.appendChild(path);


    // Live-Positionsmarker
    const marker =
        document.createElementNS(ns, "line");

    marker.setAttribute(
        "id",
        "profilePosition"
    );

    marker.setAttribute(
        "x1",
        padding.left
    );

    marker.setAttribute(
        "x2",
        padding.left
    );

    marker.setAttribute(
        "y1",
        padding.top
    );

    marker.setAttribute(
        "y2",
        height - padding.bottom
    );

    marker.setAttribute(
        "class",
        "profile-position"
    );

    svg.appendChild(marker);
}


function updateProfilePosition(
    elapsed,
    totalDuration
) {
    const marker =
        document.getElementById(
            "profilePosition"
        );

    if (!marker || !totalDuration) {
        return;
    }

    const width = 1000;
    const paddingLeft = 60;
    const paddingRight = 20;

    const chartWidth =
        width
        - paddingLeft
        - paddingRight;

    const progress =
        Math.max(
            0,
            Math.min(
                1,
                Number(elapsed || 0)
                / Number(totalDuration)
            )
        );

    const x =
        paddingLeft
        + progress * chartWidth;

    marker.setAttribute(
        "x1",
        x
    );

    marker.setAttribute(
        "x2",
        x
    );
}


async function updateStatus() {
    try {
        const response =
            await fetch("/api/status");

        if (!response.ok) {
            throw new Error(
                `Status konnte nicht geladen werden (${response.status})`
            );
        }

        const data =
            await response.json();

        document.getElementById(
            "actualWatt"
        ).textContent =
            data.actual_watt ?? 0;

        document.getElementById(
            "targetWatt"
        ).textContent =
            data.target_watt ?? 0;

        const heartRateElement =
            document.getElementById(
                "heartRate"
            );

        const heartRate =
            data.heart_rate == null
            ? null
            : Number(data.heart_rate);

        heartRateElement.classList.remove(
            "heart-rate-high"
        );

        if (
            heartRate == null
            || !Number.isFinite(heartRate)
        ) {
            heartRateElement.textContent = "---";

        } else if (
            !profileHeartRate
            || profileHeartRate.min == null
            || profileHeartRate.max == null
        ) {
            heartRateElement.textContent =
                `${heartRate}`;

        } else {
            const minHeartRate =
                Number(profileHeartRate.min);

            const maxHeartRate =
                Number(profileHeartRate.max);

            let indicator = "✓";

            if (heartRate < minHeartRate) {
                indicator = "↓";
            } else if (heartRate > maxHeartRate) {
                indicator = "↑";
            }

            heartRateElement.textContent =
                `${heartRate} ${indicator}`;

            if (
                heartRate > maxHeartRate * 1.10
            ) {
                heartRateElement.classList.add(
                    "heart-rate-high"
                );
            }
        }

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
            data.profile || "–";

        document.getElementById(
            "stepName"
        ).textContent =
            data.step_name
            || "Noch kein Training";

        document.getElementById(
            "stepElapsed"
        ).textContent =
            formatTime(
                data.step_elapsed
            );

        document.getElementById(
            "stepRemaining"
        ).textContent =
            formatTime(
                data.step_remaining
            );

        document.getElementById(
            "stepDuration"
        ).textContent =
            formatTime(
                data.step_duration
            );

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

        document.getElementById(
            "totalDuration"
        ).textContent =
            formatTime(
                data.total_duration
            );

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

        updateProfilePosition(
            data.elapsed,
            data.total_duration
        );

        updateNextStep(data);

        updateTrainingBadge(
            data.running,
            data.completed
        );

        const errorBox =
            document.getElementById(
                "error"
            );

        if (data.error) {
            errorBox.textContent =
                data.error;

            errorBox.classList.add(
                "visible"
            );
        } else {
            errorBox.textContent = "";

            errorBox.classList.remove(
                "visible"
            );
        }

        document.getElementById(
            "startButton"
        ).disabled =
            Boolean(data.running);

        document.getElementById(
            "stopButton"
        ).disabled =
            !data.running;

        document.getElementById(
            "profile"
        ).disabled =
            Boolean(data.running);

    } catch (error) {
        console.error(error);

        const errorBox =
            document.getElementById(
                "error"
            );

        errorBox.textContent =
            "Verbindung zum Trainer-Backend unterbrochen.";

        errorBox.classList.add(
            "visible"
        );
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

        try {
            const response =
                await fetch(
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


document.getElementById(
    "stopButton"
).addEventListener(
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


const profileSelect =
    document.getElementById(
        "profile"
    );

if (profileSelect) {
    loadProfileChart(
        profileSelect.value
    ).catch(console.error);

    profileSelect.addEventListener(
        "change",
        () => {
            loadProfileChart(
                profileSelect.value
            ).catch(console.error);
        }
    );
}


updateStatus();

setInterval(
    updateStatus,
    1000
);