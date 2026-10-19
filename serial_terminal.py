#!/usr/bin/env python3
"""
Serial Terminal Monitor
Двупосочен терминал за комуникация с устройства през сериен порт.

Iziskvania:
    pip install pyserial
    или
    python -m pip install pyserial

Upotreba:
    python serial_terminal.py
    или
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
    print(f"Greska pri import na pyserial: {e}")
    print()
    print("   Vazmozhni prichini:")
    print("   1. Imash fail 'serial.py' v sashtata papka - preimenovai go!")
    print("   2. pip i python sochat kam razlichni instalatsii.")
    print()
    print("   Opitai:")
    print(f"     {sys.executable} -m pip install pyserial")
    print()
    print(f"   Python executable: {sys.executable}")
    sys.exit(1)

# Vklyuchva ANSI tsvetovete v Windows konzolata (VT rezhim)
if os.name == "nt":
    os.system("")


# === Konfiguratsia ========================================================

COMMON_BAUD_RATES = [
    300, 1200, 2400, 4800, 9600, 14400,
    19200, 28800, 38400, 57600, 115200,
    230400, 460800, 921600
]
DEFAULT_BAUD = 9600

# Kraj na reda pri izprashtane v TEXT rezhim
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
BOX_W = 50  # shirina na kutiyata (vatreshnost)


def cls():
    """Izchistva ekrana krosplatformeno."""
    if os.name == "nt":
        os.system("cls")
    else:
        print("\033[2J\033[H", end="", flush=True)


def center_text(text, width):
    """Tsentrira tekst v pole s fiksirana shirina."""
    text_len = len(text)
    if text_len >= width:
        return text[:width]
    pad_left = (width - text_len) // 2
    pad_right = width - text_len - pad_left
    return " " * pad_left + text + " " * pad_right


def banner():
    """Risuva perfektno podravnen baner s ASCII simvoli."""
    w = BOX_W
    title = "SERIAL TERMINAL MONITOR"
    subtitle = "< двупосочна комуникация >"

    print()
    print(f"  {C['cyan']}{C['bold']}+{'-' * w}+")
    print(f"  |{center_text(title, w)}|")
    print(f"  |{center_text(subtitle, w)}|")
    print(f"  +{'-' * w}+{C['reset']}")
    print()


# === Vhod ot klaviaturata (edin fonov thread za tsyalata programa) =========

_input_queue = queue.Queue()
_input_thread = None


def _stdin_worker():
    """Chete redove ot stdin i gi slaga v opashkata. None oznachava EOF."""
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt, OSError):
            _input_queue.put(None)
            return
        _input_queue.put(line)


def read_line(timeout=None):
    """
    Vrashta sledvashtiya red ot klaviaturata.
    Vrashta None pri timeout; hvarlya EOFError ako vhodat e zatvoren.
    Glavniyat thread ostava svoboden - Ctrl+C i disconnect se zabelyazvat vednaga.
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
            _input_queue.put(None)  # EOF ostava za sledvashtite izvikvania
            raise EOFError
        return line


def prompt(text):
    """Pechata podkana bez nov red."""
    print(text, end="", flush=True)


# === Stypka 1: Skanirane i izbor na port ==================================

def get_port_list():
    """Vrashta sortiran spisak s nalichni seriyni portove."""
    return sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)


def display_ports(ports):
    """Izvezhda spisaka s portove na ekrana."""
    print(f"  {C['yellow']}Открити серийни портове:{C['reset']}\n")
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
    Nepreksanato skanira za portove i gi pokazva.
    Potrebitelyat mozhe da vavede nomer po vsyako vreme.
    Ako nyama portove, izchakva i obnovyava avtomatichno.
    """
    port_prompt = f"  {C['cyan']}> Избери порт (номер) или 'q' за изход: {C['reset']}"

    while True:
        ports = get_port_list()

        if not ports:
            print(f"  {C['dim']}Няма открити серийни портове.{C['reset']}")
            print(f"  {C['dim']}Свържи устройство... (сканиране на всеки 2 сек){C['reset']}")
            print()

            # Izchakwame da se poyavi port
            while True:
                time.sleep(2)
                ports = get_port_list()
                if ports:
                    break
                # Premestwame kursora nagore i prezapiswame reda
                count_str = f"  {C['dim']}Сканиране... ({time.strftime('%H:%M:%S')}){C['reset']}"
                print(f"\033[A\033[2K{count_str}")

        # Ima portove - pokazvame gi
        display_ports(ports)
        known_set = set(p.device for p in ports)
        prompt(port_prompt)

        # Dokato chakame vhod, skanirame za promeni
        choice = None
        while choice is None:
            choice = read_line(timeout=1.5)
            if choice is not None:
                break

            new_ports = get_port_list()
            new_set = set(p.device for p in new_ports)
            if new_set != known_set:
                for dev in sorted(new_set - known_set):
                    print(f"\n  {C['green']}+ Нов порт открит: {dev}{C['reset']}")
                for dev in sorted(known_set - new_set):
                    print(f"\n  {C['red']}- Порт премахнат: {dev}{C['reset']}")

                known_set = new_set
                ports = new_ports
                print()
                if ports:
                    display_ports(ports)
                else:
                    print(f"  {C['dim']}Няма открити серийни портове.{C['reset']}\n")
                prompt(port_prompt)

        # Obrabotvame izbora spryamo pokazaniya spisak
        choice = choice.strip()
        if choice.lower() == "q":
            print(f"\n  {C['yellow']}Довиждане!{C['reset']}\n")
            sys.exit(0)

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                selected = ports[idx]
                print(f"  {C['green']}Избран: {selected.device}{C['reset']}\n")
                return selected.device
        except ValueError:
            pass

        print(f"  {C['red']}Невалиден избор. Опитай пак.{C['reset']}")
        time.sleep(1)
        print(f"  {C['dim']}{'-' * BOX_W}{C['reset']}")


# === Stypka 2: Izbor na baud rate =========================================

def select_baud():
    """Pokazva spisak s baud rates i priema izbor."""
    print(f"  {C['yellow']}Стандартни baud rates:{C['reset']}\n")
    per_row = 4
    for i, baud in enumerate(COMMON_BAUD_RATES, 1):
        marker = f"{C['magenta']}*{C['reset']}" if baud == DEFAULT_BAUD else " "
        end = "\n" if i % per_row == 0 else ""
        print(f"    {marker} {C['green']}{i:>2}.{C['reset']} {baud:<10}", end=end)
    if len(COMMON_BAUD_RATES) % per_row != 0:
        print()
    print()

    while True:
        prompt(
            f"  {C['cyan']}> Избери baud rate [1-{len(COMMON_BAUD_RATES)}] "
            f"или въведи custom (Enter = {DEFAULT_BAUD}): {C['reset']}"
        )
        choice = read_line().strip()
        try:
            if not choice:
                baud = DEFAULT_BAUD
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
            print(f"  {C['red']}Невалидна стойност. Опитай пак.{C['reset']}")


# === Pomoshtni funktsii za sesiyata =======================================

def parse_hex(text):
    """
    Preobrazuva HEX tekst v bajtove.
    Priema '01 A2 ff', '0x01,0xA2', '0X1 0XFF', '01A2FF'.
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
    Sled prekusvane chaka sashtiyat port da se poyavi otnovo.
    Vrashta True ako portat se e poyavil, False ako potrebitelyat
    e natisnal Enter (iska drug port).
    """
    print(f"\n  {C['yellow']}Изчакване {port} да се появи отново...{C['reset']}")
    print(f"  {C['dim']}(Enter = избор на друг порт, Ctrl+C = изход){C['reset']}\n")
    while True:
        if read_line(timeout=1) is not None:
            print(f"  {C['dim']}{'=' * BOX_W}{C['reset']}\n")
            return False
        if any(p.device == port for p in get_port_list()):
            print(f"  {C['green']}{port} е открит отново.{C['reset']}")
            time.sleep(1)  # davame vreme na drajvera da se inicializira
            return True


# === Chetene ot serijniya port (fonov thread) =============================

def reader_thread(ser, stop_event, disconnect_event, settings, out):
    """
    Nepreksanato chete ot serijniya port i pechata na ekrana.
    out: obsht rechnik s 'lock' i 'mid_line' (dali posledniyat RX ne e
    zavarshil s nov red), za da ne se smesvat RX i TX na edin red.
    """
    # Inkrementalen dekoder - pazi nepalnite UTF-8 simvoli mezhdu chetenyata
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    while not stop_event.is_set():
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                if settings["hex"]:
                    text = " ".join(f"{b:02X}" for b in data)
                    # Nov red sled 0A, za da ostane chetimo
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
            else:
                time.sleep(0.02)
        except (serial.SerialException, OSError):
            if not stop_event.is_set():
                print(f"\n\n  {C['red']}!! Устройството е изключено !!{C['reset']}")
                disconnect_event.set()
                stop_event.set()
            break
        except Exception as e:
            if not stop_event.is_set():
                print(f"\n  {C['red']}Грешка при четене: {e}{C['reset']}")
                disconnect_event.set()
                stop_event.set()
            break


# === Sesiya: svurzvane i komunikatsiya ====================================

def run_session(port, baud, settings, open_attempts=1):
    """
    Otvarya serijna vruzka i upravlyava komunikatsiyata.
    settings: {'eol': ..., 'hex': ...} - zapazva se mezhdu sesiite.
    Vrushta:
        'disconnected' - ustrojstvoto e izklyucheno po vreme na sesiyata
        'failed'       - portat ne mozhe da bade otvoren
        'quit'         - potrebitelyat iska da izleze
    """
    print(f"  {C['cyan']}Свързване с {port} @ {baud}...{C['reset']}")
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
            print(f"  {C['red']}Неуспешно свързване: {e}{C['reset']}")
            time.sleep(2)
            print(f"\n  {C['dim']}{'=' * BOX_W}{C['reset']}\n")
            return "failed"

    w = BOX_W
    conn_msg = f"SVURZAN  |  {port}  |  {baud} baud"
    print()
    print(f"  {C['green']}{'=' * w}")
    print(f"  {center_text(conn_msg, w)}")
    print(f"  {'=' * w}{C['reset']}")
    print()
    print(f"  {C['dim']}Въведи текст и натисни Enter за изпращане.")
    print(f"  Команди:  /quit  /clear  /hex  /eol [lf|crlf|cr|none]  /info")
    print(f"  Режим: {'HEX' if settings['hex'] else 'TEXT'}   "
          f"Край на реда: {settings['eol'].upper()}{C['reset']}")
    print(f"  {C['dim']}{'-' * w}{C['reset']}")
    print()

    stop_event = threading.Event()
    disconnect_event = threading.Event()
    out = {"lock": threading.Lock(), "mid_line": False}

    reader = threading.Thread(
        target=reader_thread,
        args=(ser, stop_event, disconnect_event, settings, out),
        daemon=True
    )
    reader.start()

    def show(text):
        """Pechata red, kato pri nuzhda zatvarya nezavarsheniya RX red."""
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
                print(f"\n  {C['yellow']}Затваряне...{C['reset']}")
                result = "quit"
                break

            elif cmd == "/clear":
                cls()
                print(f"  {C['dim']}(екранът е изчистен){C['reset']}\n")
                continue

            elif cmd == "/hex":
                settings["hex"] = not settings["hex"]
                mode_str = "HEX" if settings["hex"] else "TEXT"
                show(f"  {C['magenta']}Режим: {mode_str} (изпращане и получаване){C['reset']}")
                continue

            elif cmd == "/eol" or cmd.startswith("/eol "):
                arg = cmd[4:].strip()
                if arg in EOL_OPTIONS:
                    settings["eol"] = arg
                    show(f"  {C['magenta']}Край на реда: {arg.upper()}{C['reset']}")
                else:
                    opts = " | ".join(EOL_OPTIONS)
                    show(f"  {C['magenta']}Край на реда: {settings['eol'].upper()}   "
                         f"{C['dim']}(/eol {opts}){C['reset']}")
                continue

            elif cmd == "/info":
                is_open_str = "Svurzan" if ser.is_open else "Prekusnat"
                mode_str = "HEX" if settings["hex"] else "TEXT"
                show(f"\n  {C['cyan']}+{'=' * 38}+\n"
                     f"  | {'Порт:':<12} {ser.port:<23} |\n"
                     f"  | {'Baud rate:':<12} {ser.baudrate:<23} |\n"
                     f"  | {'Data bits:':<12} {ser.bytesize:<23} |\n"
                     f"  | {'Parity:':<12} {ser.parity:<23} |\n"
                     f"  | {'Stop bits:':<12} {ser.stopbits:<23} |\n"
                     f"  | {'Режим:':<12} {mode_str:<23} |\n"
                     f"  | {'EOL:':<12} {settings['eol'].upper():<23} |\n"
                     f"  | {'Status:':<12} {is_open_str:<23} |\n"
                     f"  +{'=' * 38}+{C['reset']}\n")
                continue

            # Izprashtane na danni
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
                show(f"  {C['red']}Грешка при изпращане: {e}{C['reset']}")
                disconnect_event.set()
                result = "disconnected"
                break
            except ValueError:
                show(f"  {C['red']}Невалиден HEX формат.{C['reset']}")

    except KeyboardInterrupt:
        print(f"\n\n  {C['yellow']}Прекъснато с Ctrl+C{C['reset']}")
        result = "quit"

    # Pochistvane
    stop_event.set()
    reader.join(timeout=1)
    if ser.is_open:
        try:
            ser.close()
        except Exception:
            pass

    return result


# === Glaven tsikul ========================================================

def main():
    """
    Osnoven tsikul na programata.
    Pri disconnect izchakva sashtiyat port i se svarzva otnovo avtomatichno;
    s Enter potrebitelyat mozhe da se varne kam izbora na port.
    """
    banner()
    settings = {"eol": "lf", "hex": False}
    try:
        while True:
            port = select_port()
            baud = select_baud()

            result = run_session(port, baud, settings)
            while result == "disconnected" and wait_for_port(port):
                result = run_session(port, baud, settings, open_attempts=3)

            if result == "quit":
                break
            # 'failed' ili otkaz ot izchakvaneto -> obratno kam izbora na port
    except (KeyboardInterrupt, EOFError):
        print()

    print(f"  {C['green']}Довиждане!{C['reset']}\n")


if __name__ == "__main__":
    main()
