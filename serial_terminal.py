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
import json
import shutil
from collections import deque

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

# Colour themes. "dark" uses the terminal's own palette and background;
# "light" paints its own background with true colours (24-bit).
_LIGHT_BASE = "[38;2;56;58;66m[48;2;250;250;250m"
THEMES = {
    "dark": {
        "reset":      "[0m",
        "bold":       "[1m",
        "dim":        "[38;5;245m",
        "green":      "[92m",
        "cyan":       "[96m",
        "yellow":     "[93m",
        "red":        "[91m",
        "magenta":    "[95m",
        "blue":       "[94m",
        "white":      "[97m",
        "black":      "[30m",
        "bg_bar":     "[48;5;236m",
        "bg_green":   "[102m",
        "bg_magenta": "[105m",
    },
    "light": {
        "reset":      "[0m" + _LIGHT_BASE,
        "bold":       "[1m",
        "dim":        "[38;2;154;156;165m",
        "green":      "[38;2;47;143;58m",
        "cyan":       "[38;2;15;124;153m",
        "yellow":     "[38;2;160;106;0m",
        "red":        "[38;2;209;52;62m",
        "magenta":    "[38;2;166;38;164m",
        "blue":       "[38;2;64;120;242m",
        "white":      "[38;2;32;34;39m",
        "black":      "[38;2;255;255;255m",
        "bg_bar":     "[48;2;230;231;234m",
        "bg_green":   "[48;2;47;143;58m",
        "bg_magenta": "[48;2;166;38;164m",
    },
}
DEFAULT_THEME = "dark"
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".serial_terminal.json")

C = dict(THEMES[DEFAULT_THEME])  # active colours, updated in place by set_theme()
BOX_W = 50  # inner width of the boxes


ANSI_RE = re.compile(r"\[[0-9;?]*[A-Za-z]")
_theme = {"name": DEFAULT_THEME, "re": None, "names": {}}


def set_theme(name):
    """Switches the active colour theme (C is updated in place)."""
    C.clear()
    C.update(THEMES[name])
    _theme["name"] = name
    # Colour codes -> names, so stored lines can be redrawn in another theme
    _theme["names"] = {code: key for key, code in C.items()}
    codes = sorted(_theme["names"], key=len, reverse=True)
    _theme["re"] = re.compile("|".join(re.escape(c) for c in codes))
    print(C["reset"], end="", flush=True)


def to_tokens(text):
    """Replaces the active theme's colour codes with theme-neutral tokens."""
    return _theme["re"].sub(lambda m: f"\x00{_theme['names'][m.group(0)]}\x00", text)


def from_tokens(text):
    """Renders tokens produced by to_tokens() in the active theme."""
    return re.sub(r"\x00(\w+)\x00", lambda m: C[m.group(1)], text)


def load_theme():
    """Returns the theme saved by /theme, or the default."""
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            name = json.load(f).get("theme")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_THEME
    return name if name in THEMES else DEFAULT_THEME


def save_theme(name):
    """Remembers the theme for the next start (errors are ignored)."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"theme": name}, f)
    except OSError:
        pass


def toggle_theme():
    """Switches between the light and dark theme and saves the choice."""
    name = "light" if _theme["name"] == "dark" else "dark"
    set_theme(name)
    save_theme(name)
    return name


def cls():
    """Clears the screen, painted with the theme background."""
    print(f"{C['reset']}[2J[H", end="", flush=True)


def vlen(text):
    """Visible length of text (colour codes not counted)."""
    return len(ANSI_RE.sub("", text))


def _symbols():
    """Unicode symbols when the console can print them, ASCII otherwise."""
    fancy = {
        "tx": "▶", "rx": "◀", "prompt": "❯", "eol": "⏎", "dot": "●", "ring": "○", "half": "◐",
        "sep": "│", "rule": "─", "heavy": "━", "tl": "┌", "tr": "┐", "bl": "└", "br": "┘",
        "lt": "├", "rt": "┤", "check": "✓", "diamond": "◆", "cross": "×", "arrow": "→",
        "mid": "·", "ell": "…", "full": "█", "shade": "░",
    }
    try:
        "".join(fancy.values()).encode(sys.stdout.encoding or "ascii")
        return fancy
    except (UnicodeEncodeError, LookupError):
        return {
            "tx": ">", "rx": "<", "prompt": ">", "eol": "", "dot": "*", "ring": "o", "half": "o",
            "sep": "|", "rule": "-", "heavy": "=", "tl": "+", "tr": "+", "bl": "+", "br": "+",
            "lt": "+", "rt": "+", "check": "+", "diamond": "*", "cross": "x", "arrow": "->",
            "mid": "-", "ell": "...", "full": "#", "shade": ".",
        }


SYM = _symbols()
VERSION = "2.0"
WIZ_W = 76  # width of the wizard header box


def banner():
    """Draws the header box of the wizard."""
    w = WIZ_W - 2
    left = (f"  {C['cyan']}{C['bold']}SERIAL MONITOR{C['reset']}  "
            f"{C['dim']}{SYM['mid']} two-way terminal for serial devices{C['reset']}")
    right = f"{C['dim']}v{VERSION}{C['reset']}   "
    pad = " " * max(1, w - vlen(left) - vlen(right))
    print()
    print(f"  {C['cyan']}{SYM['tl']}{SYM['rule'] * w}{SYM['tr']}{C['reset']}")
    print(f"  {C['cyan']}{SYM['sep']}{C['reset']}{left}{pad}{right}{C['cyan']}{SYM['sep']}{C['reset']}")
    print(f"  {C['cyan']}{SYM['bl']}{SYM['rule'] * w}{SYM['br']}{C['reset']}")
    print()


def section(step, title):
    """Prints a 'STEP 1/2  Port -----' heading."""
    head = f"{C['yellow']}{C['bold']}STEP {step}{C['reset']}  {C['yellow']}{title}{C['reset']} "
    print(f"  {head}{C['dim']}{SYM['rule'] * (WIZ_W + 2 - vlen(head))}{C['reset']}\n")


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


def port_info(port):
    """Returns (description, 'VID:PID') of a port; either may be empty."""
    desc = (port.description or "").replace(f" ({port.device})", "")  # Windows repeats the name
    hwid = port.hwid or ""
    vid_pid = (hwid.split("VID:PID=")[1].split() or [""])[0] if "VID:PID=" in hwid else ""
    return desc, vid_pid


def display_ports(ports, new):
    """Prints the port table; ports in `new` get a 'new' badge."""
    pw = max(8, max(len(p.device) for p in ports) + 1)
    dw = 35
    r = SYM["rule"]
    print(f"    {C['dim']}{'#':<2}  {'PORT':<{pw}} {'DESCRIPTION':<{dw}}  VID:PID{C['reset']}")
    print(f"    {C['dim']}{r * 2}  {r * pw} {r * dw}  {r * 9}{C['reset']}")
    for i, port in enumerate(ports, 1):
        desc, vid_pid = port_info(port)
        if len(desc) > dw:
            desc = desc[:dw - len(SYM["ell"])] + SYM["ell"]
        badge = f"   {C['bg_bar']}{C['green']} new {C['reset']}" if port.device in new else ""
        print(f"    {C['green']}{i:<2}{C['reset']}  {C['white']}{C['bold']}{port.device:<{pw}}{C['reset']} "
              f"{desc:<{dw}}  {C['dim']}{vid_pid:<9}{C['reset']}{badge}")
    print()


def watching_line(count):
    """The '○ watching for devices · 3 found · q = quit' line under the port table."""
    mid = SYM["mid"]
    if count:
        state = f"{count} found {mid} q = quit {mid} /theme = light/dark"
    else:
        state = f"none found {mid} last scan {time.strftime('%H:%M:%S')}"
    return f"    {C['dim']}{SYM['ring']} watching for devices {mid} {state}{C['reset']}"


def draw_port_step(ports, first, note):
    """Clears the screen and draws the header and step 1 (the port table)."""
    cls()
    banner()
    section("1/2", "Port")
    if ports:
        display_ports(ports, {p.device for p in ports} - first)
    else:
        print(f"    {C['dim']}No serial ports found. Connect a device...{C['reset']}\n")
    if note:
        print(f"    {note}{C['reset']}\n")
    print(watching_line(len(ports)))


def select_port():
    """
    Keeps scanning for ports and shows them.
    The user can enter a number at any time.
    If there are no ports, waits and refreshes automatically.
    """
    first = None  # ports present when the wizard opened; later ones are marked 'new'
    note = ""
    while True:
        ports = get_port_list()
        if first is None:
            first = {p.device for p in ports}
        draw_port_step(ports, first, note)
        note = ""

        if not ports:
            # Wait for a port to appear, then redraw the table
            while not ports:
                time.sleep(2)
                ports = get_port_list()
                if not ports:
                    print(f"\033[A\033[2K{watching_line(0)}")
            continue

        print()
        prompt(f"  {C['cyan']}{SYM['prompt']} Port{C['reset']} {C['dim']}[1-{len(ports)}]{C['reset']} ")

        # While waiting for input, watch for changes
        known = {p.device for p in ports}
        gone = []
        choice = None
        while choice is None:
            choice = read_line(timeout=1.5)
            if choice is None:
                now = {p.device for p in get_port_list()}
                if now != known:
                    gone = sorted(known - now)
                    break
        if choice is None:
            if gone:
                note = f"{C['red']}{', '.join(gone)} removed"
            continue

        # Handle the choice against the list that was shown
        choice = choice.strip()
        if choice.lower() == "q":
            print(f"\n  {C['yellow']}Goodbye!{C['reset']}\033[0m\n")
            sys.exit(0)

        if choice.lower() == "/theme":
            toggle_theme()
            continue

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                selected = ports[idx]
                desc = port_info(selected)[0]
                print(f"  {C['green']}{SYM['check']} {selected.device}{C['reset']}  "
                      f"{C['dim']}{desc}{C['reset']}\n")
                return selected.device
        except ValueError:
            pass

        note = f"{C['red']}Invalid choice '{choice}'. Enter a number from 1 to {len(ports)}."


# === Step 2: Select a baud rate ===========================================

def select_baud(default=DEFAULT_BAUD):
    """Shows the list of baud rates and reads the choice. Enter selects default."""
    section("2/2", "Baud rate")
    per_row = 4
    cells = []
    for i, baud in enumerate(COMMON_BAUD_RATES, 1):
        if baud == default:
            value = f"{C['bg_bar']}{C['green']}{C['bold']} {baud} {SYM['diamond']} {C['reset']}"
        else:
            value = f" {baud}"
        cells.append(f"{C['green']}{i:>2}{C['reset']} {value}{' ' * (10 - vlen(value))}")
    rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
    note = f"{C['dim']}{SYM['diamond']} default {SYM['mid']} or type any custom value{C['reset']}"
    if len(rows[-1]) < per_row:
        rows[-1].append(note)
    else:
        rows.append([note])
    for row in rows:
        print("    " + "  ".join(row))
    print()

    while True:
        prompt(f"  {C['cyan']}{SYM['prompt']} Baud{C['reset']} {C['dim']}[1-{len(COMMON_BAUD_RATES)} "
               f"{SYM['mid']} Enter = {default}]{C['reset']} ")
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
            print(f"  {C['green']}{SYM['check']} {baud} baud{C['reset']}\n")
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


def wait_for_port(port, screen):
    """
    After a disconnect, waits for the same port to appear again.
    Returns True if the port came back, False if the user pressed
    Enter (wants a different port).
    """
    screen.waiting()
    attempt = 0
    while True:
        if read_line(timeout=1) is not None:
            return False
        attempt += 1
        found = any(p.device == port for p in get_port_list())
        screen.waiting(attempt)
        if found:
            time.sleep(1)  # give the driver time to initialise
            return True


# === Session screen =======================================================

COMMANDS = " /quit  /port  /clear  /hex  /eol  /ping  /info  /log  /theme"
RX_IDLE = 0.15       # an unfinished RX line (or HEX message) is shown after this many seconds
HEX_MAX = 256        # a HEX message this long is shown without waiting for a pause
ENTRY_INDENT = 22    # width of '  12:00:00.000  TX >  ' before the text of an entry
RX_ERROR_RE = re.compile(r"^(ERROR|\+CM[ES] ERROR\b)")
REVERSE = "\033[7m"  # reverse video: a badge in the current colour


def fmt_bytes(n):
    """1234 -> '1.2 KB'."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def fmt_duration(secs):
    """75 -> '1 min 15 s'."""
    return f"{secs} s" if secs < 60 else f"{secs // 60} min {secs % 60} s"


def paint(parts):
    """[(colour, text), ...] -> one string with a colour code only where the colour changes."""
    out, last = "", None
    for colour, text in parts:
        if colour != last:
            out += C["reset"] + colour
            last = colour
        out += text
    return out + C["reset"]


def hex_rows(data, colour, per_row):
    """
    Formats bytes as hex dump rows: offset, the bytes in groups of 8 and an
    ASCII column. Control bytes (CR, LF, NUL...) are dimmed.
    """
    rows = []
    for off in range(0, len(data), per_row):
        chunk = data[off:off + per_row]
        cells, text = [], []
        for i in range(per_row):
            sep = "" if i == 0 else "  " if i == 8 else " "
            if i >= len(chunk):
                cells.append(("", sep + "  "))
                continue
            b = chunk[i]
            ctrl = b < 0x20 or b == 0x7F
            cells.append((C["dim"] if ctrl else colour, f"{sep}{b:02X}"))
            text.append((colour, chr(b)) if 0x20 <= b < 0x7F else (C["dim"], "."))
        bar = f"{C['dim']}{SYM['sep']}{C['reset']}"
        rows.append(f"{C['dim']}{off:04X}{C['reset']}  {paint(cells)}  "
                    f"{bar}{paint(text)}{' ' * (per_row - len(chunk))}{bar}")
    return rows


class SessionScreen:
    """
    Session layout: a status bar on the top row, a scrolling log in the
    middle and the command bar with the input prompt at the bottom.
    The log is an ANSI scroll region, so incoming data never moves the line
    being typed. Falls back to plain printing when stdout is not a terminal.
    """

    def __init__(self, port, baud, settings, stats):
        self.port, self.baud = port, baud
        self.settings = settings  # eol, hex, log file and history
        self.stats = stats        # rx/tx counters and start time
        self.lock = threading.Lock()
        self.last_tick = 0
        self.state = "connected"   # "disconnected" while waiting for the port to return
        self.lost = None           # time.time() of the disconnect
        self.attempt = 0           # port checks since the disconnect
        self.last_hex = b""        # last bytes sent in HEX mode (shown in the command bar)
        self.after_header = False  # the HEX column header is the last line of the log
        self.fancy = sys.stdout.isatty() and shutil.get_terminal_size().lines >= 10
        if self.fancy:
            self._layout()

    # -- drawing (call with self.lock held) --------------------------------

    def _out(self, text):
        sys.stdout.write(text)
        sys.stdout.flush()

    def _layout(self):
        """Draws the whole screen for the current terminal size."""
        self.size = tuple(shutil.get_terminal_size())
        rows = self.size[1]
        self.top, self.bottom = 3, rows - 4  # row 2 stays empty under the status bar
        self.row = self.top  # where the next log line goes
        self._out(f"{C['reset']}\033[r\033[2J\033[{self.top};{self.bottom}r")
        self._draw_status()
        self._draw_footer()
        for line in list(self.settings["history"])[-(self.bottom - self.top + 1):]:
            self._put(from_tokens(line))
        self._prompt()

    def _rows(self, line):
        """Screen rows a log line takes after wrapping."""
        return min(max(1, -(-vlen(line) // self.size[0])), self.bottom - self.top + 1)

    def _put(self, line):
        """Writes one line at the end of the log, scrolling it if needed."""
        n = self._rows(line)
        over = self.row + n - 1 - self.bottom
        if over > 0:
            self._out(f"{C['reset']}\033[{self.bottom};1H" + "\n" * over)
            self.row -= over
        self._out(f"\033[{self.row};1H{C['reset']}\033[2K{line}{C['reset']}")
        self.row += n

    def _draw_status(self):
        cols = self.size[0]
        s, st = self.settings, self.stats
        bar = C["bg_bar"]
        sep = f"{C['dim']}{SYM['sep']}{C['reset']}{bar}"
        up = int(time.monotonic() - st["start"])
        if s["hex"]:
            mode = f"{C['bg_magenta']}{C['black']}{C['bold']} HEX {C['reset']}{bar}"
        else:
            mode = f"{C['cyan']} TEXT {C['reset']}{bar}"
        if self.state == "connected":
            badge = f"{C['bg_green']}{C['black']}{C['bold']} {SYM['dot']} CONNECTED {C['reset']}{bar}"
        else:
            badge = f"{C['reset']}{C['red']}{REVERSE}{C['bold']} {SYM['ring']} DISCONNECTED {C['reset']}{bar}"
        segs = [
            badge,
            f"{C['white']}{C['bold']} {self.port} {C['reset']}{bar}",
            f"{sep} {self.baud} 8N1 ",
            f"{sep}{mode}",
            f"{sep}{C['dim']} EOL {C['reset']}{bar}{C['yellow']}{s['eol'].upper()} {C['reset']}{bar}",
        ]
        if self.state == "connected":
            segs += [
                f"{sep} {C['green']}RX {fmt_bytes(st['rx'])}{C['reset']}{bar}  "
                f"{C['magenta']}TX {fmt_bytes(st['tx'])} {C['reset']}{bar}",
                f"{sep}{C['dim']} up {up // 3600:02d}:{up // 60 % 60:02d}:{up % 60:02d} {C['reset']}{bar}",
            ]
        else:
            attempt = f" {SYM['mid']} attempt {self.attempt}" if self.attempt else ""
            segs.append(f"{sep}{C['yellow']} reconnecting{attempt} {C['reset']}{bar}")
        if s["log"]:
            segs.append(f"{sep}{C['red']}{C['bold']} {SYM['dot']} LOG {C['reset']}{bar}")
        line, width = bar, 0
        for seg in segs:  # drop the last segments on narrow terminals
            w = len(ANSI_RE.sub("", seg))
            if width + w > cols:
                break
            line += seg
            width += w
        self._out(f"\0337\033[1;1H{line}{' ' * (cols - width)}{C['reset']}\0338")

    def _draw_footer(self):
        cols, rows = self.size
        if self.state != "connected":
            cmds, hint = "", "Ctrl+C exit "
        elif self.settings["hex"]:
            probe = " ".join(f"{b:02X}" for b in self.last_hex[:8]) or "<bytes>"
            if len(self.last_hex) > 8:
                probe += SYM["ell"]
            cmds, hint = f" /hex back to text   /ping {probe}   /clear   /quit", ""
        else:
            cmds, hint = COMMANDS, "Ctrl+C exit "
        if len(cmds) + len(hint) + 2 <= cols:
            cmds += " " * (cols - len(cmds) - len(hint)) + hint
        self._out(f"\0337\033[{rows - 3};1H{C['reset']}\033[2K{C['dim']}{SYM['rule'] * cols}"
                  f"\033[{rows - 2};1H{C['reset']}\033[2K{C['dim']}{cmds[:cols]}{C['reset']}\0338")

    def _prompt(self):
        """Clears the input line and puts the cursor after the prompt."""
        rows = self.size[1]
        badge = ""
        if self.settings["hex"] and self.state == "connected":
            badge = f"{C['bg_magenta']}{C['black']}{C['bold']}HEX{C['reset']} "
        self._out(f"{C['reset']}\033[{rows};1H\033[2K\033[{rows - 1};1H\033[2K"
                  f" {C['magenta']}{C['bold']}{SYM['prompt']}{C['reset']} {badge}")

    # -- public ------------------------------------------------------------

    def cols(self):
        """Width of the terminal."""
        return self.size[0] if self.fancy else shutil.get_terminal_size().columns

    def write(self, text):
        """Adds lines to the log (and to the log file, if /log is on)."""
        with self.lock:
            log = self.settings["log"]
            for line in text.split("\n"):
                self.settings["history"].append(to_tokens(line))
                if log:
                    log.write(ANSI_RE.sub("", line) + "\n")
                if self.fancy:
                    self._out("\0337")
                    self._put(line)
                    self._out("\0338")
                else:
                    print(line + C["reset"])
            if log:
                log.flush()

    def replace(self, back, line):
        """Replaces the log line `back` lines from the end (lines after it must not wrap)."""
        with self.lock:
            history = self.settings["history"]
            history[-back] = to_tokens(line)
            if self.fancy:
                row = self.row - sum(self._rows(from_tokens(history[-i])) for i in range(1, back + 1))
                if row >= self.top:
                    self._out(f"\0337\033[{row};1H{C['reset']}\033[2K{line}{C['reset']}\0338")

    def entry(self, kind, text, more=(), gap=False):
        """
        Adds a timestamped TX / RX / SYS line. `more` lines continue it
        under the text; `gap` puts an empty line before it.
        """
        t = time.time()
        stamp = time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t % 1 * 1000):03d}"
        tag = {
            "tx":  f"{C['magenta']}{C['bold']}TX {SYM['tx']}",
            "rx":  f"{C['green']}{C['bold']}RX {SYM['rx']}",
            "sys": f"{C['cyan']}{C['bold']}SYS ",
        }[kind]
        lines = [""] if gap else []
        lines.append(f"  {C['dim']}{stamp}{C['reset']}  {tag}{C['reset']}  {text}{C['reset']}")
        lines += [f"{' ' * ENTRY_INDENT}{line}{C['reset']}" for line in more]
        self.write("\n".join(lines))

    def _per_row(self):
        """Bytes per hex dump row: 16 when the terminal is wide enough, else 8."""
        return 16 if self.cols() >= ENTRY_INDENT + 83 else 8

    def hex_header(self):
        """Adds the 'offset 00 01 ... 0F ascii' header of the hex dump columns."""
        per_row = self._per_row()
        labels = "".join(("" if i == 0 else "  " if i == 8 else " ") + f"{i:02X}" for i in range(per_row))
        self.write(f"{' ' * (ENTRY_INDENT - 2)}{C['dim']}offset  {labels}   ascii{C['reset']}")
        self.after_header = True

    def dump(self, kind, data, latency=None):
        """
        Adds a hex dump of sent ('tx') or received ('rx') bytes. `latency` is
        the time from the last HEX send to this reply, in seconds.
        """
        rows = hex_rows(data, C["white"] if kind == "tx" else C["green"], self._per_row())
        if latency is not None:
            rows[0] += f"  {C['dim']}+{int(latency * 1000)} ms{C['reset']}"
        # An empty line before each exchange; a reply stays with its request
        gap = not self.after_header and (kind == "tx" or latency is None)
        self.after_header = False
        self.entry(kind, rows[0], rows[1:], gap)

    def _banner(self, colour, mark, title, detail):
        """A '━━━ / × TITLE  detail / ━━━' banner across the log."""
        rule = f"  {colour}{SYM['heavy'] * min(66, self.cols() - 4)}{C['reset']}"
        return [rule, f"    {colour}{C['bold']}{mark}  {title}{C['reset']}   {C['dim']}{detail}{C['reset']}", rule]

    def disconnected(self, when, error=None):
        """Shows the disconnect banner and switches the status bar to DISCONNECTED."""
        stamp = time.strftime("%H:%M:%S", time.localtime(when)) + f".{int(when % 1 * 10)}"
        lines = ["", *self._banner(C["red"], SYM["cross"], "DEVICE DISCONNECTED",
                                   f"{self.port} vanished at {stamp}")]
        if error:
            lines.append(f"    {C['dim']}Read error: {error}{C['reset']}")
        self.write("\n".join(lines + [""]))
        with self.lock:
            self.state, self.lost, self.attempt = "disconnected", when, 0
        self.refresh()

    def waiting(self, attempt=0):
        """
        Adds the 'Waiting for the port' line (attempt 0) or updates its
        spinner, the time offline and the attempt in the status bar.
        """
        frames = (SYM["ring"], SYM["half"], SYM["dot"], SYM["half"])
        secs = int(time.time() - self.lost)
        line = (f"  {C['yellow']}{frames[attempt % 4]} Waiting for {self.port} to come back{C['reset']}  "
                f"{C['dim']}{secs // 60:02d}:{secs % 60:02d} {SYM['mid']} "
                f"baud, mode and EOL will be restored{C['reset']}")
        if attempt == 0:
            self.write("\n".join([
                line, "",
                f"    {C['white']}{C['bold']}Enter{C['reset']}   {C['dim']}choose another port{C['reset']}",
                f"    {C['white']}{C['bold']}Ctrl+C{C['reset']}  {C['dim']}quit{C['reset']}",
            ]))
            return
        self.replace(4, line)
        self.attempt = attempt
        self.tick(force=True)

    def reconnected(self, stats):
        """Shows the reconnect banner and switches back to CONNECTED with new counters."""
        offline = int(time.time() - self.lost)
        with self.lock:
            self.stats, self.state, self.attempt = stats, "connected", 0
        self.write("\n".join(["", *self._banner(
            C["green"], SYM["dot"], "RECONNECTED",
            f"{self.port} @ {self.baud} {SYM['mid']} offline for {fmt_duration(offline)}"), ""]))
        self.refresh()

    def tick(self, force=False):
        """Updates the status bar once a second (or now); redraws after a resize."""
        if not self.fancy:
            return
        with self.lock:
            if tuple(shutil.get_terminal_size()) != self.size:
                self._layout()
            elif force or int(time.monotonic()) != self.last_tick:
                self.last_tick = int(time.monotonic())
                self._draw_status()

    def refresh(self):
        """Redraws the status bar, command bar and prompt (after a command changed them)."""
        if self.fancy:
            with self.lock:
                self._draw_status()
                self._draw_footer()
                self._prompt()

    def redraw(self):
        """Redraws everything, e.g. after a theme change."""
        if self.fancy:
            with self.lock:
                self._layout()

    def input_done(self):
        """Clears the typed line after Enter."""
        if self.fancy:
            with self.lock:
                self._prompt()

    def clear(self):
        """Empties the log (/clear)."""
        with self.lock:
            self.settings["history"].clear()
            if self.fancy:
                self._layout()

    def toggle_log(self):
        """Starts or stops saving the log to a file in the current folder (/log)."""
        log = self.settings["log"]
        if log:
            self.entry("sys", f"{C['cyan']}Logging stopped: {log.name}")
            with self.lock:
                log.close()
                self.settings["log"] = None
        else:
            safe = re.sub(r"[^\w.-]", "_", os.path.basename(self.port))
            name = f"serial_{safe}_{time.strftime('%Y-%m-%d_%H%M%S')}.log"
            try:
                log = open(name, "a", encoding="utf-8")
            except OSError as e:
                self.entry("sys", f"{C['red']}Cannot open log file: {e}")
                return
            with self.lock:
                self.settings["log"] = log
            self.entry("sys", f"{C['cyan']}Logging to {os.path.abspath(name)}")
        self.refresh()

    def close(self):
        """Restores normal scrolling; later output continues below the log."""
        with self.lock:
            if self.fancy:
                self.fancy = False
                row = min(self.row, self.bottom + 1)
                self._out(f"{C['reset']}\033[r\033[{row};1H\033[J")


# === Reading from the serial port (background thread) =====================

def escape_text(text):
    """Shows control characters as text (\\r, \\n, \\xNN)."""
    return "".join(
        ch.encode("unicode_escape").decode("ascii") if ch < " " or ch == "\x7f" else ch
        for ch in text
    )


def escape_bytes(data):
    """Shows bytes as text with visible control characters (\\r, \\n, \\xNN)."""
    return escape_text(data.decode("utf-8", errors="backslashreplace"))


def reader_thread(ser, stop_event, disconnect_event, settings, out, screen):
    """
    Continuously reads from the serial port and adds each received line to
    the session log. A line still unfinished after RX_IDLE seconds is shown
    as it is (e.g. a '> ' prompt without a newline). In HEX mode the bytes
    received until a pause of RX_IDLE seconds are shown as one hex dump.
    out: shared dict with 'lock', the byte counters, the time of the last
    HEX send and the /ping capture.
    """
    # Incremental decoder - keeps incomplete UTF-8 characters between reads
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    text_buf = ""             # unfinished text line
    hex_buf = bytearray()     # unfinished hex message
    hex_latency = None        # reply time of hex_buf after the last HEX send
    last_rx = 0.0

    def emit(line):
        color = C["red"] if RX_ERROR_RE.match(line) else C["green"]
        screen.entry("rx", f"{color}{line}")

    def flush():
        nonlocal text_buf, hex_buf
        if text_buf:
            emit(escape_text(text_buf.expandtabs(4)))
            text_buf = ""
        if hex_buf:
            screen.dump("rx", bytes(hex_buf), hex_latency)
            hex_buf = bytearray()

    while not stop_event.is_set():
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                last_rx = time.monotonic()
                with out["lock"]:
                    out["rx"] += len(data)
                    latency = None if out["last_tx"] is None else last_rx - out["last_tx"]
                    out["last_tx"] = None
                    # During /ping also collect the reply
                    if out["ping"] is not None:
                        if out["ping"]["t"] is None:
                            out["ping"]["t"] = last_rx
                        out["ping"]["buf"] += data
                if settings["hex"]:
                    if text_buf:
                        flush()
                    if not hex_buf:
                        hex_latency = latency
                    hex_buf += data
                    if len(hex_buf) >= HEX_MAX:
                        flush()
                else:
                    if hex_buf:
                        flush()
                    text_buf += decoder.decode(data)
                    # CR, LF and CRLF all end a line; empty lines are skipped
                    text_buf = text_buf.replace("\r\n", "\n").replace("\r", "\n")
                    *lines, text_buf = text_buf.split("\n")
                    for line in lines:
                        if line:
                            emit(escape_text(line.expandtabs(4)))
            else:
                if (text_buf or hex_buf) and time.monotonic() - last_rx > RX_IDLE:
                    flush()
                time.sleep(0.02)
        except (serial.SerialException, OSError):
            if not stop_event.is_set():
                out["lost"] = time.time()
                disconnect_event.set()
                stop_event.set()
            break
        except Exception as e:
            if not stop_event.is_set():
                out["lost"] = time.time()
                out["error"] = str(e)
                disconnect_event.set()
                stop_event.set()
            break
    flush()


# === Session: connect and communicate =====================================

PING_TIMEOUT = 2.0  # seconds to wait for the first byte of a /ping reply
PING_BAR = 20       # width of the latency bar on the /ping card


def ping(ser, arg, settings, out):
    """
    Connectivity test: checks the port and line signals, sends a probe
    and waits for any reply.
    arg: probe to send (empty = 'AT' + CRLF). In HEX mode arg is hex bytes,
    in TEXT mode the current line ending is added.
    Returns {'probe', 'open', 'signals', 'reply', 'ms'} for ping_card().
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

    signals = {label: signal(label.lower()) for label in ("CTS", "DSR", "CD", "RI")}
    is_open = ser.is_open

    with out["lock"]:
        out["ping"] = {"buf": bytearray(), "t": None}
    try:
        start = time.monotonic()
        ser.write(probe)
        with out["lock"]:
            out["tx"] += len(probe)
        # Wait up to 2 s for the first byte, then a little longer for the rest
        while time.monotonic() - start < PING_TIMEOUT and out["ping"]["t"] is None:
            time.sleep(0.02)
        if out["ping"]["t"] is not None:
            time.sleep(0.3)
    finally:
        with out["lock"]:
            reply, first = bytes(out["ping"]["buf"]), out["ping"]["t"]
            out["ping"] = None

    ms = int((first - start) * 1000) if reply else None
    return {"probe": probe, "open": is_open, "signals": signals, "reply": reply, "ms": ms}


def ping_card(port, res, hex_mode, cols):
    """Formats a ping() result as a box: probe, port, signals, reply, latency and a verdict."""
    inner = max(40, min(72, cols - 6))
    ok = bool(res["reply"])
    border = C["dim"] if ok else C["red"]
    rule = SYM["rule"]
    title = f"PING {SYM['mid']} {port}"
    edge = f"{border}{SYM['sep']}{C['reset']}"
    room = inner - 12  # width left for a value
    timeout_ms = int(PING_TIMEOUT * 1000)

    def show(data):
        return " ".join(f"{b:02X}" for b in data) if hex_mode else f'"{escape_bytes(data)}"'

    def clip(text, width):
        return text if len(text) <= width else text[:max(0, width - len(SYM["ell"]))] + SYM["ell"]

    def row(label, value):
        text = f"  {C['dim']}{label:<9}{C['reset']}{value}" if label else f"  {value}"
        return f"  {edge}{text}{' ' * max(0, inner - vlen(text))}{edge}"

    lines = [f"  {border}{SYM['tl']}{rule}{C['reset']} {C['green'] if ok else C['red']}{title}{C['reset']} "
             f"{border}{rule * max(0, inner - 3 - len(title))}{SYM['tr']}{C['reset']}"]
    lines.append(row("Probe", f"{C['white']}{clip(show(res['probe']), room)}{C['reset']}"))
    if res["open"]:
        lines.append(row("Port", f"{C['green']}{SYM['dot']} open{C['reset']}"))
    else:
        lines.append(row("Port", f"{C['red']}{SYM['ring']} closed{C['reset']}"))
    signals = ""
    for name, state in res["signals"].items():
        if state == "on":
            signals += f"{C['green']}{SYM['dot']} {name}{C['reset']}   "
        else:
            signals += f"{C['dim']}{SYM['ring']} {name}{C['reset']}   "
    if "on" not in res["signals"].values():
        signals += f"{C['dim']}n/a on most USB adapters{C['reset']}"
    lines.append(row("Signals", signals.rstrip()))

    if ok:
        ms = res["ms"]
        n = len(res["reply"])
        head = (f"{C['white']}{C['bold']}{n}{C['reset']}{C['white']} byte{'s' if n != 1 else ''} in "
                f"{C['bold']}{ms} ms{C['reset']}  {C['dim']}{SYM['arrow']}{C['reset']} ")
        reply = clip(show(res["reply"]), room - vlen(head))
        lines.append(row("Reply", f"{head}{C['green']}{reply}{C['reset']}"))
        filled = min(PING_BAR, max(1, round(ms / timeout_ms * PING_BAR)))
        bar = (f"{C['green']}{SYM['full'] * filled}{C['reset']}"
               f"{C['dim']}{SYM['shade'] * (PING_BAR - filled)}{C['reset']}")
        lines.append(row("Latency", f"{bar}  {C['dim']}{ms} / {timeout_ms} ms{C['reset']}"))
        verdict = (f"{C['bg_green']}{C['black']}{C['bold']} OK {C['reset']}  "
                   f"{C['green']}the device is responding{C['reset']}")
    else:
        lines.append(row("Reply", f"{C['red']}nothing within {timeout_ms} ms{C['reset']}"))
        verdict = (f"{C['red']}{REVERSE}{C['bold']} NO REPLY {C['reset']}  "
                   f"{C['dim']}check baud rate, line ending and the probe{C['reset']}")
    lines.append(f"  {border}{SYM['lt']}{rule * inner}{SYM['rt']}{C['reset']}")
    lines.append(row("", verdict))
    lines.append(f"  {border}{SYM['bl']}{rule * inner}{SYM['br']}{C['reset']}")
    return lines


def run_session(port, baud, settings, open_attempts=1):
    """
    Opens the serial connection and handles communication.
    settings: {'eol', 'hex', 'log', 'history', 'screen'} - kept between sessions.
    'screen' is the session screen kept open after a disconnect; when it is
    set, this session is a reconnect and continues on that screen.
    Returns:
        'disconnected' - the device was unplugged during the session
        'failed'       - the port could not be opened
        'switch'       - the user wants to choose another port (/port)
        'quit'         - the user wants to exit
    """
    screen = settings["screen"]
    if screen is None:
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
            if screen:
                screen.entry("sys", f"{C['red']}Connection failed: {e}")
                time.sleep(2)
                screen.close()
                settings["screen"] = None
            else:
                print(f"  {C['red']}Connection failed: {e}{C['reset']}")
                time.sleep(2)
            print(f"\n  {C['dim']}{'=' * BOX_W}{C['reset']}\n")
            return "failed"

    stop_event = threading.Event()
    disconnect_event = threading.Event()
    out = {"lock": threading.Lock(), "ping": None, "rx": 0, "tx": 0, "last_tx": None,
           "start": time.monotonic(), "error": None, "lost": None}

    if screen:
        screen.reconnected(out)
    else:
        screen = SessionScreen(port, baud, settings, out)
        screen.entry("sys", f"{C['cyan']}Connected to {port} at {baud} baud (8N1). "
                            f"Type text and press Enter to send.")
        if settings["hex"]:
            screen.hex_header()
    settings["screen"] = None  # set again if the device disconnects

    reader = threading.Thread(
        target=reader_thread,
        args=(ser, stop_event, disconnect_event, settings, out, screen),
        daemon=True
    )
    reader.start()

    show = screen.write
    result = "quit"
    farewell = f"\n  {C['yellow']}Closing...{C['reset']}"

    try:
        while True:
            screen.tick()
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
            screen.input_done()

            if disconnect_event.is_set():
                result = "disconnected"
                break

            cmd = user_input.strip().lower()

            if cmd == "/quit":
                result = "quit"
                break

            elif cmd == "/port":
                farewell = (f"\n  {C['yellow']}Closing {port}, back to port selection...{C['reset']}\n"
                            f"  {C['dim']}{'=' * BOX_W}{C['reset']}\n")
                result = "switch"
                break

            elif cmd == "/clear":
                screen.clear()
                if settings["hex"]:
                    screen.hex_header()
                continue

            elif cmd == "/theme":
                name = toggle_theme()
                screen.redraw()
                screen.entry("sys", f"{C['cyan']}Theme: {name.upper()}")
                continue

            elif cmd == "/log":
                screen.toggle_log()
                continue

            elif cmd == "/hex":
                settings["hex"] = not settings["hex"]
                mode_str = "HEX" if settings["hex"] else "TEXT"
                screen.entry("sys", f"{C['cyan']}Mode set to {mode_str} (send and receive)")
                if settings["hex"]:
                    mid = SYM["mid"]
                    screen.write(
                        f"  {C['dim']}Control bytes (CR, LF, NUL{SYM['ell']}) are dimmed "
                        f"so the payload stands out.{C['reset']}\n"
                        f"  {C['dim']}Input formats:  41 54 0D 0A  {mid}  0x41,0x42  {mid}  "
                        f"41540D0A  {mid}  0xF {SYM['arrow']} 0F{C['reset']}\n")
                    screen.hex_header()
                screen.refresh()
                continue

            elif cmd == "/eol" or cmd.startswith("/eol "):
                arg = cmd[4:].strip()
                if arg in EOL_OPTIONS:
                    settings["eol"] = arg
                    screen.entry("sys", f"{C['cyan']}Line ending set to {arg.upper()}")
                    screen.refresh()
                else:
                    opts = " | ".join(EOL_OPTIONS)
                    screen.entry("sys", f"{C['cyan']}Line ending: {settings['eol'].upper()}   "
                                        f"{C['dim']}(/eol {opts})")
                continue

            elif cmd == "/ping" or cmd.startswith("/ping "):
                screen.entry("tx", f"{C['white']}{user_input.strip()}")
                try:
                    res = ping(ser, user_input.strip()[5:].strip(), settings, out)
                except serial.SerialException as e:
                    screen.entry("sys", f"{C['red']}Send error: {e}")
                    disconnect_event.set()
                    result = "disconnected"
                    break
                except ValueError:
                    screen.entry("sys", f"{C['red']}Invalid HEX format.")
                    continue
                show("\n".join(["", *ping_card(port, res, settings["hex"], screen.cols()), ""]))
                continue

            elif cmd == "/info":
                is_open_str = "Connected" if ser.is_open else "Disconnected"
                mode_str = "HEX" if settings["hex"] else "TEXT"
                log_str = os.path.basename(settings["log"].name) if settings["log"] else "off"
                show(f"\n  {C['cyan']}+{'=' * 38}+\n"
                     f"  | {'Port:':<12} {ser.port:<23} |\n"
                     f"  | {'Baud rate:':<12} {ser.baudrate:<23} |\n"
                     f"  | {'Data bits:':<12} {ser.bytesize:<23} |\n"
                     f"  | {'Parity:':<12} {ser.parity:<23} |\n"
                     f"  | {'Stop bits:':<12} {ser.stopbits:<23} |\n"
                     f"  | {'Mode:':<12} {mode_str:<23} |\n"
                     f"  | {'Line ending:':<12} {settings['eol'].upper():<23} |\n"
                     f"  | {'Log file:':<12} {log_str[:23]:<23} |\n"
                     f"  | {'Status:':<12} {is_open_str:<23} |\n"
                     f"  +{'=' * 38}+{C['reset']}\n")
                continue

            # Send data
            try:
                if settings["hex"]:
                    data = parse_hex(user_input)
                    if not data:
                        continue
                    with out["lock"]:
                        out["last_tx"] = time.monotonic()  # for the reply time
                    ser.write(data)
                    with out["lock"]:
                        out["tx"] += len(data)
                    screen.dump("tx", data)
                    screen.last_hex = data
                    screen.refresh()
                    continue

                data = user_input.encode("utf-8") + EOL_OPTIONS[settings["eol"]]
                if not data:
                    continue
                display = escape_text(user_input)
                if EOL_OPTIONS[settings["eol"]]:
                    display += f"{C['dim']}{SYM['eol']}"

                ser.write(data)
                with out["lock"]:
                    out["tx"] += len(data)
                screen.entry("tx", f"{C['white']}{display}")

            except serial.SerialException as e:
                screen.entry("sys", f"{C['red']}Send error: {e}")
                disconnect_event.set()
                result = "disconnected"
                break
            except ValueError:
                screen.entry("sys", f"{C['red']}Invalid HEX format.")

    except KeyboardInterrupt:
        farewell = f"\n  {C['yellow']}Interrupted with Ctrl+C{C['reset']}"
        result = "quit"

    finally:
        # Cleanup
        stop_event.set()
        reader.join(timeout=1)
        if result != "disconnected":
            screen.close()
        if ser.is_open:
            try:
                ser.close()
            except Exception:
                pass

    if result == "disconnected":
        # The screen stays open while main() waits for the port to return
        screen.disconnected(out["lost"] or time.time(), out["error"])
        settings["screen"] = screen
        return result
    print(farewell)
    return result


# === Main loop ============================================================

def main():
    """
    Main program loop.
    After a disconnect, waits for the same port and reconnects automatically;
    pressing Enter returns to the port selection.
    """
    set_theme(load_theme())
    settings = {"eol": "lf", "hex": False, "log": None, "history": deque(maxlen=1000),
                "screen": None}
    baud = DEFAULT_BAUD
    try:
        while True:
            port = select_port()
            baud = select_baud(default=baud)

            result = run_session(port, baud, settings)
            while result == "disconnected" and wait_for_port(port, settings["screen"]):
                result = run_session(port, baud, settings, open_attempts=3)

            if settings["screen"]:  # waiting cancelled with Enter
                settings["screen"].close()
                settings["screen"] = None
            if result == "quit":
                break
            # 'switch', 'failed' or waiting cancelled -> back to port selection
    except (KeyboardInterrupt, EOFError):
        if settings["screen"]:
            settings["screen"].close()
        print()

    if settings["log"]:
        settings["log"].close()
    print(f"  {C['green']}Goodbye!{C['reset']}\033[0m\n")


if __name__ == "__main__":
    main()
