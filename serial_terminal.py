#!/usr/bin/env python3
"""
Serial Terminal Monitor
Two-way terminal for communicating with devices over a serial port.

Requirements:
    pip install pyserial
    or
    python -m pip install pyserial

Usage:
    python serial_terminal.py
    or
    python .\serial_terminal.py
"""

import sys
import threading
import time
import os
import queue
import codecs
import re

try:
    import serial
    import serial.tools.list_ports
except ImportError as e:
    print(f"Error importing pyserial: {e}")
    print()
    print("   Possible causes:")
    print("   1. There is a file named 'serial.py' in the same folder - rename it!")
    print("   2. pip and python point to different installations.")
    print()
    print("   Try:")
    print(f"     {sys.executable} -m pip install pyserial")
    print()
    print(f"   Python executable: {sys.executable}")
    sys.exit(1)

# Enable ANSI colours in the Windows console (VT mode)
if os.name == "nt":
    os.system("")


# === Configuration ========================================================

COMMON_BAUD_RATES = [
    300, 1200, 2400, 4800, 9600, 14400,
    19200, 28800, 38400, 57600, 115200,
    230400, 460800, 921600
]
DEFAULT_BAUD = 9600

# Line ending appended when sending in TEXT mode
EOL_OPTIONS = {
    "lf":   b"\n",
    "crlf": b"\r\n",
    "cr":   b"\r",
    "none": b"",
}

COLORS = {
    "reset":   "\033[0m",
    "bold":    "\033[1m",
    "dim":     "\033[2m",
    "green":   "\033[92m",
    "cyan":    "\033[96m",
    "yellow":  "\033[93m",
    "red":     "\033[91m",
    "magenta": "\033[95m",
    "blue":    "\033[94m",
    "white":   "\033[97m",
}

C = COLORS
BOX_W = 50  # inner width of the boxes


def cls():
    """Clears the screen (cross-platform)."""
    if os.name == "nt":
        os.system("cls")
    else:
        print("\033[2J\033[H", end="", flush=True)


def center_text(text, width):
    """Centres text in a fixed-width field."""
    text_len = len(text)
    if text_len >= width:
        return text[:width]
    pad_left = (width - text_len) // 2
    pad_right = width - text_len - pad_left
    return " " * pad_left + text + " " * pad_right


def banner():
    """Draws the aligned ASCII banner."""
    w = BOX_W
    title = "SERIAL TERMINAL MONITOR"
    subtitle = "< two-way communication >"

    print()
    print(f"  {C['cyan']}{C['bold']}+{'-' * w}+")
    print(f"  |{center_text(title, w)}|")
    print(f"  |{center_text(subtitle, w)}|")
    print(f"  +{'-' * w}+{C['reset']}")
    print()


# === Keyboard input (one background thread for the whole program) ========

_input_queue = queue.Queue()
_input_thread = None


def _stdin_worker():
    """Reads lines from stdin into the queue. None means EOF."""
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt, OSError):
            _input_queue.put(None)
            return
        _input_queue.put(line)


def read_line(timeout=None):
    """
    Returns the next line typed on the keyboard.
    Returns None on timeout; raises EOFError if input is closed.
    The main thread stays free, so Ctrl+C and disconnects are noticed at once.
    """
    global _input_thread
    if _input_thread is None:
        _input_thread = threading.Thread(target=_stdin_worker, daemon=True)
        _input_thread.start()

    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        try:
            line = _input_queue.get(timeout=0.1)
        except queue.Empty:
            if deadline is not None and time.monotonic() >= deadline:
                return None
            continue
        if line is None:
            _input_queue.put(None)  # keep EOF for later calls
            raise EOFError
        return line


def prompt(text):
    """Prints a prompt without a newline."""
    print(text, end="", flush=True)


# === Step 1: Scan and select a port =======================================

def get_port_list():
    """Returns a sorted list of available serial ports."""
    return sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)


def display_ports(ports):
    """Prints the list of ports."""
    print(f"  {C['yellow']}Serial ports found:{C['reset']}\n")
    for i, port in enumerate(ports, 1):
        desc = port.description or "-"
        hwid = port.hwid or ""
        vid_pid = ""
        if "VID:PID" in hwid:
            try:
                vid_pid = f" {C['dim']}[{hwid.split('VID:PID=')[1].split()[0]}]{C['reset']}"
            except IndexError:
                pass
        print(f"    {C['green']}{i}.{C['reset']} {C['bold']}{port.device}{C['reset']}  "
              f"{C['dim']}- {desc}{C['reset']}{vid_pid}")
    print()


def select_port():
    """
    Keeps scanning for ports and shows them.
    The user can enter a number at any time.
    If there are no ports, waits and refreshes automatically.
    """
    port_prompt = f"  {C['cyan']}> Select a port (number) or 'q' to quit: {C['reset']}"

    while True:
        ports = get_port_list()

        if not ports:
            print(f"  {C['dim']}No serial ports found.{C['reset']}")
            print(f"  {C['dim']}Connect a device... (scanning every 2 s){C['reset']}")
            print()

            # Wait for a port to appear
            while True:
                time.sleep(2)
                ports = get_port_list()
                if ports:
                    break
                # Move the cursor up and overwrite the line
                count_str = f"  {C['dim']}Scanning... ({time.strftime('%H:%M:%S')}){C['reset']}"
                print(f"\033[A\033[2K{count_str}")

        # Ports found - show them
        display_ports(ports)
        known_set = set(p.device for p in ports)
        prompt(port_prompt)

        # While waiting for input, watch for changes
        choice = None
        while choice is None:
            choice = read_line(timeout=1.5)
            if choice is not None:
                break

            new_ports = get_port_list()
            new_set = set(p.device for p in new_ports)
            if new_set != known_set:
                for dev in sorted(new_set - known_set):
                    print(f"\n  {C['green']}+ New port found: {dev}{C['reset']}")
                for dev in sorted(known_set - new_set):
                    print(f"\n  {C['red']}- Port removed: {dev}{C['reset']}")

                known_set = new_set
                ports = new_ports
                print()
                if ports:
                    display_ports(ports)
                else:
                    print(f"  {C['dim']}No serial ports found.{C['reset']}\n")
                prompt(port_prompt)

        # Handle the choice against the list that was shown
        choice = choice.strip()
        if choice.lower() == "q":
            print(f"\n  {C['yellow']}Goodbye!{C['reset']}\n")
            sys.exit(0)

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                selected = ports[idx]
                print(f"  {C['green']}Selected: {selected.device}{C['reset']}\n")
                return selected.device
        except ValueError:
            pass

        print(f"  {C['red']}Invalid choice. Try again.{C['reset']}")
        time.sleep(1)
        print(f"  {C['dim']}{'-' * BOX_W}{C['reset']}")


# === Step 2: Select a baud rate ===========================================

def select_baud(default=DEFAULT_BAUD):
    """Shows the list of baud rates and reads the choice. Enter selects default."""
    print(f"  {C['yellow']}Standard baud rates:{C['reset']}\n")
    per_row = 4
    for i, baud in enumerate(COMMON_BAUD_RATES, 1):
        marker = f"{C['magenta']}*{C['reset']}" if baud == default else " "
        end = "\n" if i % per_row == 0 else ""
        print(f"    {marker} {C['green']}{i:>2}.{C['reset']} {baud:<10}", end=end)
    if len(COMMON_BAUD_RATES) % per_row != 0:
        print()
    print()

    while True:
        prompt(
            f"  {C['cyan']}> Select a baud rate [1-{len(COMMON_BAUD_RATES)}] "
            f"or enter a custom one (Enter = {default}): {C['reset']}"
        )
        choice = read_line().strip()
        try:
            if not choice:
                baud = default
            else:
                num = int(choice)
                if 1 <= num <= len(COMMON_BAUD_RATES):
                    baud = COMMON_BAUD_RATES[num - 1]
                elif num > 0:
                    baud = num
                else:
                    raise ValueError
            print(f"  {C['green']}Baud rate: {baud}{C['reset']}\n")
            return baud
        except ValueError:
            print(f"  {C['red']}Invalid value. Try again.{C['reset']}")


# === Session helpers ======================================================

def parse_hex(text):
    """
    Converts HEX text to bytes.
    Accepts '01 A2 ff', '0x01,0xA2', '0X1 0XFF', '01A2FF'.
    """
    tokens = [t for t in re.split(r"[\s,;]+", text) if t]
    parts = []
    for tok in tokens:
        if tok[:2].lower() == "0x":
            tok = tok[2:]
        if len(tok) % 2:
            tok = "0" + tok
        parts.append(tok)
    return bytes.fromhex("".join(parts))


def wait_for_port(port):
    """
    After a disconnect, waits for the same port to appear again.
    Returns True if the port came back, False if the user pressed
    Enter (wants a different port).
    """
    print(f"\n  {C['yellow']}Waiting for {port} to come back...{C['reset']}")
    print(f"  {C['dim']}(Enter = choose another port, Ctrl+C = quit){C['reset']}\n")
    while True:
        if read_line(timeout=1) is not None:
            print(f"  {C['dim']}{'=' * BOX_W}{C['reset']}\n")
            return False
        if any(p.device == port for p in get_port_list()):
            print(f"  {C['green']}{port} found again.{C['reset']}")
            time.sleep(1)  # give the driver time to initialise
            return True


# === Reading from the serial port (background thread) =====================

def reader_thread(ser, stop_event, disconnect_event, settings, out):
    """
    Continuously reads from the serial port and prints to the screen.
    out: shared dict with 'lock' and 'mid_line' (whether the last RX did not
    end with a newline), so RX and TX are not mixed on one line.
    """
    # Incremental decoder - keeps incomplete UTF-8 characters between reads
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    while not stop_event.is_set():
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                if settings["hex"]:
                    text = " ".join(f"{b:02X}" for b in data)
                    # New line after 0A to keep it readable
                    mid_line = not data.endswith(b"\n")
                    text += " " if mid_line else "\n"
                else:
                    text = decoder.decode(data)
                    if not text:
                        continue
                    mid_line = not text.endswith("\n")
                with out["lock"]:
                    print(f"{C['green']}{text}{C['reset']}", end="", flush=True)
                    out["mid_line"] = mid_line
                    # During /ping also collect the reply
                    if out["ping"] is not None:
                        if out["ping"]["t"] is None:
                            out["ping"]["t"] = time.monotonic()
                        out["ping"]["buf"] += data
            else:
                time.sleep(0.02)
        except (serial.SerialException, OSError):
            if not stop_event.is_set():
                print(f"\n\n  {C['red']}!! Device disconnected !!{C['reset']}")
                disconnect_event.set()
                stop_event.set()
            break
        except Exception as e:
            if not stop_event.is_set():
                print(f"\n  {C['red']}Read error: {e}{C['reset']}")
                disconnect_event.set()
                stop_event.set()
            break


# === Session: connect and communicate =====================================

def session_header(port, baud, settings):
    """Prints the connection banner, the command list and the current mode."""
    w = BOX_W
    conn_msg = f"CONNECTED  |  {port}  |  {baud} baud"
    print()
    print(f"  {C['green']}{'=' * w}")
    print(f"  {center_text(conn_msg, w)}")
    print(f"  {'=' * w}{C['reset']}")
    print()
    print(f"  {C['dim']}Type text and press Enter to send.")
    print(f"  Commands:  /quit  /port  /clear  /hex  /eol [lf|crlf|cr|none]  /ping  /info")
    print(f"  Mode: {'HEX' if settings['hex'] else 'TEXT'}   "
          f"Line ending: {settings['eol'].upper()}{C['reset']}")
    print(f"  {C['dim']}{'-' * w}{C['reset']}")
    print()


def escape_bytes(data):
    """Shows bytes as text with visible control characters (\\r, \\n, \\xNN)."""
    text = data.decode("utf-8", errors="backslashreplace")
    return "".join(
        ch.encode("unicode_escape").decode("ascii") if ch < " " or ch == "\x7f" else ch
        for ch in text
    )


def ping(ser, arg, settings, out, show):
    """
    Connectivity test: checks the port and line signals, sends a probe
    and waits for any reply.
    arg: probe to send (empty = 'AT' + CRLF). In HEX mode arg is hex bytes,
    in TEXT mode the current line ending is added.
    """
    if not arg:
        probe = b"AT\r\n"
    elif settings["hex"]:
        probe = parse_hex(arg)
    else:
        probe = arg.encode("utf-8") + EOL_OPTIONS[settings["eol"]]

    def signal(name):
        try:
            return "on" if getattr(ser, name) else "off"
        except (serial.SerialException, OSError, AttributeError):
            return "n/a"

    show(f"\n  {C['cyan']}PING {ser.port}  probe: \"{escape_bytes(probe)}\"{C['reset']}")
    show(f"  {C['dim']}Port:     {'open' if ser.is_open else 'closed'}")
    show(f"  Signals:  CTS={signal('cts')}  DSR={signal('dsr')}  CD={signal('cd')}{C['reset']}")

    with out["lock"]:
        out["ping"] = {"buf": bytearray(), "t": None}
    try:
        start = time.monotonic()
        ser.write(probe)
        # Wait up to 2 s for the first byte, then a little longer for the rest
        while time.monotonic() - start < 2 and out["ping"]["t"] is None:
            time.sleep(0.02)
        if out["ping"]["t"] is not None:
            time.sleep(0.3)
    finally:
        with out["lock"]:
            reply, first = bytes(out["ping"]["buf"]), out["ping"]["t"]
            out["ping"] = None

    if reply:
        ms = int((first - start) * 1000)
        show(f"  {C['dim']}Reply:    {len(reply)} bytes in {ms} ms  -> \"{escape_bytes(reply)}\"{C['reset']}")
        show(f"  {C['green']}Result:   OK - the device is responding{C['reset']}\n")
    else:
        show(f"  {C['dim']}Reply:    none within 2 s{C['reset']}")
        show(f"  {C['red']}Result:   NO REPLY - the port is open but the device did not answer{C['reset']}")
        show(f"  {C['dim']}Tip: not every device answers AT. "
             f"Try /ping <a command your device understands>.{C['reset']}\n")


def run_session(port, baud, settings, open_attempts=1):
    """
    Opens the serial connection and handles communication.
    settings: {'eol': ..., 'hex': ...} - kept between sessions.
    Returns:
        'disconnected' - the device was unplugged during the session
        'failed'       - the port could not be opened
        'switch'       - the user wants to choose another port (/port)
        'quit'         - the user wants to exit
    """
    print(f"  {C['cyan']}Connecting to {port} @ {baud}...{C['reset']}")
    for attempt in range(1, open_attempts + 1):
        try:
            ser = serial.Serial(
                port=port,
                baudrate=baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
                write_timeout=2,
            )
            time.sleep(0.5)
            break
        except serial.SerialException as e:
            if attempt < open_attempts:
                time.sleep(1)
                continue
            print(f"  {C['red']}Connection failed: {e}{C['reset']}")
            time.sleep(2)
            print(f"\n  {C['dim']}{'=' * BOX_W}{C['reset']}\n")
            return "failed"

    session_header(port, baud, settings)

    stop_event = threading.Event()
    disconnect_event = threading.Event()
    out = {"lock": threading.Lock(), "mid_line": False, "ping": None}

    reader = threading.Thread(
        target=reader_thread,
        args=(ser, stop_event, disconnect_event, settings, out),
        daemon=True
    )
    reader.start()

    def show(text):
        """Prints a line, first ending an unfinished RX line if needed."""
        with out["lock"]:
            if out["mid_line"]:
                print()
                out["mid_line"] = False
            print(text)

    result = "quit"

    try:
        while True:
            if disconnect_event.is_set():
                result = "disconnected"
                break

            try:
                user_input = read_line(timeout=0.1)
            except EOFError:
                result = "quit"
                break
            if user_input is None:
                continue

            if disconnect_event.is_set():
                result = "disconnected"
                break

            cmd = user_input.strip().lower()

            if cmd == "/quit":
                print(f"\n  {C['yellow']}Closing...{C['reset']}")
                result = "quit"
                break

            elif cmd == "/port":
                show(f"\n  {C['yellow']}Closing {port}, back to port selection...{C['reset']}")
                print(f"  {C['dim']}{'=' * BOX_W}{C['reset']}\n")
                result = "switch"
                break

            elif cmd == "/clear":
                with out["lock"]:
                    cls()
                    session_header(port, baud, settings)
                    out["mid_line"] = False
                continue

            elif cmd == "/hex":
                settings["hex"] = not settings["hex"]
                mode_str = "HEX" if settings["hex"] else "TEXT"
                show(f"  {C['magenta']}Mode: {mode_str} (send and receive){C['reset']}")
                continue

            elif cmd == "/eol" or cmd.startswith("/eol "):
                arg = cmd[4:].strip()
                if arg in EOL_OPTIONS:
                    settings["eol"] = arg
                    show(f"  {C['magenta']}Line ending: {arg.upper()}{C['reset']}")
                else:
                    opts = " | ".join(EOL_OPTIONS)
                    show(f"  {C['magenta']}Line ending: {settings['eol'].upper()}   "
                         f"{C['dim']}(/eol {opts}){C['reset']}")
                continue

            elif cmd == "/ping" or cmd.startswith("/ping "):
                try:
                    ping(ser, user_input.strip()[5:].strip(), settings, out, show)
                except serial.SerialException as e:
                    show(f"  {C['red']}Send error: {e}{C['reset']}")
                    disconnect_event.set()
                    result = "disconnected"
                    break
                except ValueError:
                    show(f"  {C['red']}Invalid HEX format.{C['reset']}")
                continue

            elif cmd == "/info":
                is_open_str = "Connected" if ser.is_open else "Disconnected"
                mode_str = "HEX" if settings["hex"] else "TEXT"
                show(f"\n  {C['cyan']}+{'=' * 38}+\n"
                     f"  | {'Port:':<12} {ser.port:<23} |\n"
                     f"  | {'Baud rate:':<12} {ser.baudrate:<23} |\n"
                     f"  | {'Data bits:':<12} {ser.bytesize:<23} |\n"
                     f"  | {'Parity:':<12} {ser.parity:<23} |\n"
                     f"  | {'Stop bits:':<12} {ser.stopbits:<23} |\n"
                     f"  | {'Mode:':<12} {mode_str:<23} |\n"
                     f"  | {'Line ending:':<12} {settings['eol'].upper():<23} |\n"
                     f"  | {'Status:':<12} {is_open_str:<23} |\n"
                     f"  +{'=' * 38}+{C['reset']}\n")
                continue

            # Send data
            try:
                if settings["hex"]:
                    data = parse_hex(user_input)
                    if not data:
                        continue
                    display = " ".join(f"{b:02X}" for b in data)
                else:
                    data = user_input.encode("utf-8") + EOL_OPTIONS[settings["eol"]]
                    if not data:
                        continue
                    display = user_input

                ser.write(data)
                show(f"  {C['blue']}TX >{C['reset']} {C['dim']}{display}{C['reset']}")

            except serial.SerialException as e:
                show(f"  {C['red']}Send error: {e}{C['reset']}")
                disconnect_event.set()
                result = "disconnected"
                break
            except ValueError:
                show(f"  {C['red']}Invalid HEX format.{C['reset']}")

    except KeyboardInterrupt:
        print(f"\n\n  {C['yellow']}Interrupted with Ctrl+C{C['reset']}")
        result = "quit"

    # Cleanup
    stop_event.set()
    reader.join(timeout=1)
    if ser.is_open:
        try:
            ser.close()
        except Exception:
            pass

    return result


# === Main loop ============================================================

def main():
    """
    Main program loop.
    After a disconnect, waits for the same port and reconnects automatically;
    pressing Enter returns to the port selection.
    """
    banner()
    settings = {"eol": "lf", "hex": False}
    baud = DEFAULT_BAUD
    try:
        while True:
            port = select_port()
            baud = select_baud(default=baud)

            result = run_session(port, baud, settings)
            while result == "disconnected" and wait_for_port(port):
                result = run_session(port, baud, settings, open_attempts=3)

            if result == "quit":
                break
            # 'switch', 'failed' or waiting cancelled -> back to port selection
    except (KeyboardInterrupt, EOFError):
        print()

    print(f"  {C['green']}Goodbye!{C['reset']}\n")


if __name__ == "__main__":
    main()
