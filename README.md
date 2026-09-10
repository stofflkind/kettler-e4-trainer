# Kettler E4 / CTR1 Trainer

Linux-based training controller for older Kettler fitness equipment with
ANT+ integration and a browser-based training cockpit.

The project allows compatible Kettler ergometers and cross trainers with
an RS-232 interface to be controlled by modern, freely configurable
training profiles.

The software was originally developed for the Kettler E4 ergometer.
Testing has shown that the Kettler CTR1 cross trainer uses the same
serial command structure and can be controlled by the same training
engine.

## Features

- Control of compatible Kettler fitness equipment via RS-232
- Automatic identification of supported devices
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

## Supported and tested equipment

The current implementation has been tested with:

### Kettler E4

- Device identification: `SD4B3035`
- RS-232 control
- Status monitoring
- Power control
- Constant-power training
- Ramp training

### Kettler CTR1

- Device identification: `CTRS`
- Firmware/version tested: `165`
- RS-232 control
- Status monitoring
- Power control
- Constant-power training
- Ramp training

The CTR1 has been successfully tested with the same training engine
used for the E4.

### Additional hardware

The current setup has also been tested with:

- LogiLink AU0002B USB-to-RS232 adapter (Prolific PL2303)
- Dynastream ANTUSB-m
- Garmin ANT+ heart-rate chest strap
- Garmin Instinct 2 Solar

Other Kettler devices using a compatible serial protocol may also work,
but should be considered unsupported until their protocol behaviour has
been verified.

## Architecture

The Linux computer acts as the central controller:

```text
Kettler E4 / CTR1
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
Heart-rate chest strap ----------+
```

The Garmin watch can record the activity independently and synchronize
it with Garmin Connect.

## Kettler serial protocol

Both the Kettler E4 and Kettler CTR1 tested with this project communicate
via their serial interface using:

- 9600 baud
- 8 data bits
- no parity
- 1 stop bit
- no hardware handshake
- CR/LF command termination

The project currently uses the following commands:

- `ID` – device identification
- `VE` – firmware/version information
- `ST` – training status
- `CM` – enter command mode
- `PW <watts>` – set target power

### Device identification

Known device IDs:

```text
SD4B3035  -> Kettler E4
CTRS      -> Kettler CTR1
```

The common Python interface is implemented by `KettlerTrainer`.

Unknown device IDs are not assumed to be compatible automatically.

## Status data

The `ST` command returns eight tab-separated fields on both tested
devices:

```text
Pulse
Cadence / RPM
Speed
Distance
Target power
Energy
Training time
Actual power
```

The current implementation converts speed and distance to the units
used by the training engine and web cockpit.

## Power control

After entering command mode with:

```text
CM
```

the target power can be changed with:

```text
PW <watts>
```

For example:

```text
PW 100
```

sets the target power to 100 watts.

Both the E4 and CTR1 have been successfully tested with dynamic power
changes and ramp training.

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

## Serial device

The software currently uses:

```text
/dev/kettler-e4
```

as the default serial device.

A persistent udev symlink is recommended when using a USB-to-RS232
adapter.

The default device name is historical and does not mean that only the
E4 is supported. The CTR1 can use the same serial device configuration.

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

## Ramp training

In addition to constant-power steps, the training engine supports
ramps.

Example:

```json
{
  "name": "Ramp",
  "type": "ramp",
  "duration": 60,
  "start_watts": 80,
  "end_watts": 140
}
```

The training engine progressively adjusts the target power during the
ramp.

Ramp control has been tested successfully on both the Kettler E4 and
Kettler CTR1.

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
control the resistance of the training device.

## ANT+ integration

The Linux computer can receive heart-rate data from an ANT+ heart-rate
sensor.

It can simultaneously transmit training data as virtual ANT+ sensors:

- Bicycle Power
- Speed/Cadence

This allows a compatible Garmin watch to record data produced by the
Kettler training device together with heart-rate data.

The Garmin activity recording itself is independent of the training
controller.

## Training logs

Training sessions can be written to CSV files in the `logs` directory.

Logged values include data such as:

- elapsed time
- training step
- target power
- actual power
- heart rate
- cadence
- speed
- distance
- energy

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
values or fail to control the training device as expected. Do not rely
on the software as a safety system.

## License

This project is licensed under the MIT License.

See [LICENSE](LICENSE) for details.