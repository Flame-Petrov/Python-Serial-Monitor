# Python Serial Monitor

A lightweight, two-way serial terminal for the command line. Pick a port, pick a baud rate, and talk to your
Arduino, ESP32, GSM/USB modem or any other serial device — in plain text or raw hex.

Single file, one dependency ([pyserial](https://pypi.org/project/pyserial/)), works on Windows, Linux and macOS.

![Port and baud rate selection](docs/screenshots/menu.png)

## Features

- **Live port detection** — the port list refreshes on its own while you choose; newly plugged and removed devices are announced.
- **Two-way communication** — incoming data in green, sent data marked with `TX >`.
- **Text and HEX modes** — `/hex` switches both sending and receiving to hex bytes, for binary protocols.
- **Configurable line ending** — send `LF`, `CRLF`, `CR` or nothing after each line (`/eol`).
- **Automatic reconnect** — if the device is unplugged, the monitor waits for the same port to return and reconnects at the same baud rate.
- **Correct UTF-8 handling** — multi-byte characters (e.g. Cyrillic) are decoded correctly even when split across reads.
- **Clean exit** — `Ctrl+C` exits gracefully from any screen.

## Screenshots

**Talking to a USB modem** — `AT` → `OK` in text mode, the same exchange in HEX mode, then `/info`:

![Session in text and hex mode](docs/screenshots/session.png)

**Automatic reconnect** — the device is unplugged mid-session and the monitor reconnects by itself once it is back
(shown with a simulated temperature sensor):

![Disconnect and automatic reconnect](docs/screenshots/reconnect.png)

## Requirements

- Python 3.7+
- pyserial

## Installation

```bash
git clone https://github.com/Flame-Petrov/Python-Serial-Monitor.git
cd Python-Serial-Monitor
python -m pip install -r requirements.txt
```

## Usage

```bash
python serial_terminal.py
```

1. **Choose a port** — type its number from the list (`q` to quit). If no device is connected, the monitor scans every 2 seconds until one appears.
2. **Choose a baud rate** — type a number from the list (1–14), type any custom value, or just press `Enter` for 9600.
3. **Communicate** — type text and press `Enter` to send it. Incoming data appears as it arrives.

### Commands

| Command | Description |
|---|---|
| `/quit` | Close the connection and exit |
| `/clear` | Clear the screen and redraw the connection header with the commands |
| `/hex` | Toggle HEX mode for sending **and** receiving |
| `/eol` | Show the current line ending |
| `/eol lf\|crlf\|cr\|none` | Set the line ending appended to sent text |
| `/info` | Show port settings, mode and connection status |

### HEX mode

In HEX mode, type bytes in any of these formats:

```text
41 54 0D 0A
0x41,0x42,0x0D
41540D0A
0xF 0x1          (single digits are padded: 0F 01)
```

Received bytes are shown as hex, with a new line after every `0A` byte.

### Line endings

The default is `LF` (`\n`), which suits most Arduino sketches. Many devices need something else:

| Device | Setting |
|---|---|
| Arduino / ESP32 (`Serial.readStringUntil('\n')`) | `/eol lf` |
| GSM / USB modems (AT commands) | `/eol crlf` |
| Some older terminals and instruments | `/eol cr` |
| Binary protocols | `/hex` (no line ending is added) |

If the device never answers, the line ending is the first thing to check.

### Automatic reconnect

When the device is unplugged, the monitor shows `!! Device disconnected !!` immediately and waits for the
same port to reappear, then reconnects with the same baud rate, mode and line ending.

- Press `Enter` while waiting to go back to the port list instead.
- Press `Ctrl+C` to exit.

## Connection settings

8 data bits, no parity, 1 stop bit (8N1), no flow control. Baud rate is chosen at startup.

## Troubleshooting

**`Error importing pyserial`** — pyserial is not installed for the Python you are running, or a file named
`serial.py` in the same folder shadows the library. Rename that file and run:

```bash
python -m pip install pyserial
```

**`Connection failed`** — the port is open in another program (Arduino IDE serial monitor,
PuTTY, another terminal). Close it and try again. On Linux, add your user to the `dialout` group.

**Garbled text** — the baud rate does not match the device. Reconnect with the correct one.

**Colour codes like `←[92m` instead of colours** — use Windows Terminal or Windows 10/11; very old consoles do not
support ANSI colours.

## Project structure

```text
serial_terminal.py     the application
requirements.txt       dependencies
docs/screenshots/      images used in this README
```
