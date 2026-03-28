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


# === Konfiguratsia ========================================================

COMMON_BAUD_RATES = [
    300, 1200, 2400, 4800, 9600, 14400,
    19200, 28800, 38400, 57600, 115200,
    230400, 460800, 921600
]

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
    """Tsentrira tekst v pole s fiksirana shirina (ASCII-bezopasno)."""
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
    known_ports = []
    input_ready = threading.Event()
    user_choice = [None]
    should_stop = threading.Event()

    def input_worker():
        """Fonov thread, koito chaka potrebitelski vhod."""
        while not should_stop.is_set():
            try:
                line = input(f"  {C['cyan']}> Избери порт (номер) или 'q' за изход: {C['reset']}").strip()
                user_choice[0] = line
                input_ready.set()
                return
            except EOFError:
                user_choice[0] = "q"
                input_ready.set()
                return

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

            # Novi portove sa namereni, restartirami menyuto
            continue

        # Ima portove - pokazvame gi
        display_ports(ports)
        known_set = set(p.device for p in ports)

        # Startirame input thread
        input_ready.clear()
        should_stop.clear()
        user_choice[0] = None
        t = threading.Thread(target=input_worker, daemon=True)
        t.start()

        # Dokato chakame vhod, skanirame za promeni
        while not input_ready.is_set():
            time.sleep(1.5)
            new_ports = get_port_list()
            new_set = set(p.device for p in new_ports)

            if new_set != known_set:
                added = new_set - known_set
                removed = known_set - new_set
                if added:
                    for dev in added:
                        print(f"\n  {C['green']}+ Нов порт открит: {dev}{C['reset']}")
                if removed:
                    for dev in removed:
                        print(f"\n  {C['red']}- Порт премахнат: {dev}{C['reset']}")

                known_set = new_set
                ports = new_ports
                print()
                display_ports(ports)
                print(f"  {C['cyan']}> Избери порт (номер) или 'q' за изход: {C['reset']}", end="", flush=True)

        # Obrabotvame izbora
        should_stop.set()
        choice = user_choice[0]

        if choice and choice.lower() == "q":
            print(f"\n  {C['yellow']}Довиждане!{C['reset']}\n")
            sys.exit(0)

        try:
            idx = int(choice) - 1
            current_ports = get_port_list()
            if 0 <= idx < len(current_ports):
                selected = current_ports[idx]
                print(f"  {C['green']}Избран: {selected.device}{C['reset']}\n")
                return selected.device
        except (ValueError, TypeError, IndexError):
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
        marker = f"{C['magenta']}*{C['reset']}" if baud == 9600 else " "
        end = "\n" if i % per_row == 0 else ""
        print(f"    {marker} {C['green']}{i:>2}.{C['reset']} {baud:<10}", end=end)
    if len(COMMON_BAUD_RATES) % per_row != 0:
        print()
    print()

    while True:
        try:
            choice = input(
                f"  {C['cyan']}> Избери baud rate [1-{len(COMMON_BAUD_RATES)}] "
                f"или въведи custom: {C['reset']}"
            ).strip()
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


# === Chetene ot serijniya port (fonov thread) =============================

def reader_thread(ser, stop_event, disconnect_event):
    """Nepreksanato chete ot serijniya port i pechata na ekrana."""
    while not stop_event.is_set():
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                text = data.decode("utf-8", errors="replace")
                print(f"{C['green']}{text}{C['reset']}", end="", flush=True)
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

def run_session(port, baud):
    """
    Otvarya serijna vruzka i upravlyava komunikatsiyata.
    Vrushta:
        'reconnect' - port e izklyuchen, vrushtame se v menyuto
        'quit'      - potrebitelyat iska da izleze
    """
    print(f"  {C['cyan']}Свързване с {port} @ {baud}...{C['reset']}")
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
    except serial.SerialException as e:
        print(f"  {C['red']}Неуспешно свързване: {e}{C['reset']}")
        time.sleep(2)
        return "reconnect"

    w = BOX_W
    conn_msg = f"SVURZAN  |  {port}  |  {baud} baud"
    print()
    print(f"  {C['green']}{'=' * w}")
    print(f"  {center_text(conn_msg, w)}")
    print(f"  {'=' * w}{C['reset']}")
    print()
    print(f"  {C['dim']}Въведи текст и натисни Enter за изпращане.")
    print(f"  Команди:  /quit  /clear  /hex  /info{C['reset']}")
    print(f"  {C['dim']}{'-' * w}{C['reset']}")
    print()

    stop_event = threading.Event()
    disconnect_event = threading.Event()
    hex_mode = False

    reader = threading.Thread(
        target=reader_thread,
        args=(ser, stop_event, disconnect_event),
        daemon=True
    )
    reader.start()

    result = "quit"

    try:
        while not stop_event.is_set():
            if disconnect_event.is_set():
                result = "reconnect"
                break

            try:
                user_input = input()
            except EOFError:
                break

            if disconnect_event.is_set():
                result = "reconnect"
                break

            if not user_input:
                try:
                    ser.write(b"\n")
                except serial.SerialException as e:
                    print(f"  {C['red']}Грешка при изпращане: {e}{C['reset']}")
                    disconnect_event.set()
                    result = "reconnect"
                    break
                continue

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
                hex_mode = not hex_mode
                mode_str = "HEX" if hex_mode else "TEXT"
                print(f"  {C['magenta']}Режим: {mode_str}{C['reset']}")
                continue

            elif cmd == "/info":
                print(f"\n  {C['cyan']}+{'=' * 38}+")
                print(f"  | {'Порт:':<12} {ser.port:<23} |")
                print(f"  | {'Baud rate:':<12} {ser.baudrate:<23} |")
                print(f"  | {'Data bits:':<12} {ser.bytesize:<23} |")
                print(f"  | {'Parity:':<12} {ser.parity:<23} |")
                print(f"  | {'Stop bits:':<12} {ser.stopbits:<23} |")
                is_open_str = "Svurzan" if ser.is_open else "Prekusnat"
                print(f"  | {'Status:':<12} {is_open_str:<23} |")
                print(f"  +{'=' * 38}+{C['reset']}\n")
                continue

            # Izprashtane na danni
            try:
                if hex_mode:
                    hex_clean = user_input.replace(" ", "").replace("0x", "")
                    data = bytes.fromhex(hex_clean)
                else:
                    data = (user_input + "\n").encode("utf-8")

                ser.write(data)
                direction = f"{C['blue']}TX >{C['reset']}"
                if hex_mode:
                    display = " ".join(f"{b:02X}" for b in data)
                else:
                    display = user_input
                print(f"  {direction} {C['dim']}{display}{C['reset']}")

            except serial.SerialException as e:
                print(f"  {C['red']}Грешка при изпращане: {e}{C['reset']}")
                disconnect_event.set()
                result = "reconnect"
                break
            except ValueError:
                print(f"  {C['red']}Невалиден HEX формат.{C['reset']}")

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

    if result == "reconnect":
        print(f"\n  {C['yellow']}Връщане към избор на порт след 3 сек...{C['reset']}")
        time.sleep(3)
        print(f"\n  {C['dim']}{'=' * BOX_W}{C['reset']}\n")

    return result


# === Glaven tsikul ========================================================

def main():
    """
    Osnoven tsikul na programata.
    Pri disconnect avtomatichno se vrushta kam izbora na port.
    """
    banner()
    while True:
        port = select_port()
        baud = select_baud()

        result = run_session(port, baud)

        if result == "quit":
            print(f"  {C['green']}Довиждане!{C['reset']}\n")
            break
        # result == "reconnect" -> tsikylyt produlzhava,
        # select_port() shte pokazhe nov spisak s portove


if __name__ == "__main__":
    main()
