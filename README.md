# Kettler E4 Trainer

Linux-based training controller for the Kettler E4 ergometer with
ANT+ integration and a browser-based training cockpit.

The project allows an older Kettler E4 ergometer with an RS-232
interface to be controlled by modern, freely configurable training
profiles.

## Features

- Control of the Kettler E4 via RS-232
- Programmable training profiles in JSON
- Constant-power and ramp training steps
- Live power, cadence, speed and distance data
- Garmin ANT+ heart-rate reception
- Virtual ANT+ Bicycle Power sensor
- Virtual ANT+ Speed/Cadence sensor
- Garmin watch integration
- Browser-based training cockpit
- Live graphical display of the training profile
- CSV logging of training sessions
- Configurable heart-rate training zones
- Heart-rate zone indicator in the web interface

## Tested hardware

The current implementation has been tested with:

- Kettler E4 ergometer
- LogiLink AU0002B USB-to-RS232 adapter (Prolific PL2303)
- Dynastream ANTUSB-m
- Garmin ANT+ heart-rate chest strap
- Garmin Instinct 2 Solar

Other compatible devices may work but have not necessarily been tested.

## Architecture

The Linux computer acts as the central controller:

```text
Kettler E4
    |
    | RS-232
    v
Linux computer
    |
    +---- FastAPI ----> Web browser / smartphone
    |
    +---- ANT+ Power --------+
    |                        |
    +---- ANT+ Speed/Cadence +----> Garmin watch
                             |
Heart-rate chest strap ------+
```

The Garmin watch can record the activity independently and synchronize
it with Garmin Connect.

## Kettler protocol

The Kettler E4 communicates via its serial interface using:

- 9600 baud
- 8 data bits
- no parity
- 1 stop bit
- no hardware handshake

The project currently uses commands including:

- `ID` – device identification
- `VE` – version
- `ST` – training status
- `CM` – command mode
- `PW <watts>` – set target power

## Installation

Clone the repository:

```bash
git clone https://github.com/stofflkind/kettler-e4-trainer.git
cd kettler-e4-trainer
```

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the required Python dependencies:

```bash
pip install -r requirements.txt
```

## Starting the web application

Activate the virtual environment and start FastAPI:

```bash
source .venv/bin/activate
uvicorn webapp:app --host 0.0.0.0 --port 8000
```

The cockpit can then be opened locally at:

```text
http://127.0.0.1:8000
```

To use a smartphone or tablet, open the IP address of the Linux
computer on the same local network, for example:

```text
http://192.168.x.x:8000
```

Do not expose the training controller directly to the public Internet.

## Training profiles

Training sessions are defined as JSON files in the `profiles`
directory.

Example:

```json
{
  "name": "Example training",
  "heart_rate": {
    "min": 100,
    "max": 130
  },
  "steps": [
    {
      "name": "Warm-up",
      "type": "steady",
      "duration": 300,
      "watts": 80
    },
    {
      "name": "Training",
      "type": "steady",
      "duration": 600,
      "watts": 120
    },
    {
      "name": "Cool-down",
      "type": "steady",
      "duration": 300,
      "watts": 80
    }
  ]
}
```

Heart-rate values in example profiles are examples only and are not
training or medical recommendations.

## Heart-rate zones

A training profile can optionally contain a heart-rate range:

```json
"heart_rate": {
  "min": 100,
  "max": 130
}
```

The web cockpit indicates whether the measured heart rate is below,
inside or above the configured range.

The heart-rate range is informational only. It does not automatically
control the resistance of the ergometer.

## Training logs

Training sessions can be written to CSV files in the `logs` directory.

Training logs may contain personal health and activity data. The
`logs` directory should therefore not be committed to a public
repository.

## Safety and medical disclaimer

This software is an independent hobby/open-source project.

It is not a medical device and is not intended to diagnose, prevent,
monitor, predict, treat or alleviate disease or medical conditions.

Power levels, heart-rate limits and training profiles must be selected
by the user. Heart-rate ranges included in example files are examples
only.

If training is performed as part of cardiac rehabilitation or under
medical supervision, use only the limits and training instructions
provided by the responsible physician or rehabilitation team.

The software may contain errors, lose sensor data, report incorrect
values or fail to control the ergometer as expected. Do not rely on
the software as a safety system.

## License

This project is licensed under the MIT License.

See [LICENSE](LICENSE) for details.