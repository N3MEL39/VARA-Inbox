import sys
import os
import socket
import threading
import subprocess
import time
import re
import json
import queue
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "varabbs_data.json")

POPULAR_RIGS = [
    ("Icom IC-7300", "3073"),
    ("Icom IC-705", "3085"),
    ("Icom IC-7100", "3070"),
    ("Icom IC-7610", "3078"),
    ("Yaesu FT-891", "1035"),
    ("Yaesu FT-991A", "1036"),
    ("Elecraft KX3", "2029"),
    ("Elecraft K3", "2024"),
    ("Kenwood TS-590SG", "2031"),
    ("Generic CI-V (Icom)", "3000")
]

# =====================================================================
# HAMLIB (RIGCTLD) TCP CONTROLLER & DAEMON MANAGER
# =====================================================================
class HamlibController:
    """Manages CAT frequency, mode, filter passband, PTT, telemetry, and daemon."""
    def __init__(self, host="127.0.0.1", port=4532, enabled=True):
        self.host = host.strip() or "127.0.0.1"
        self.port = int(port)
        self.enabled = enabled
        self.lock = threading.Lock()
        self.last_status = "Standby"
        self.is_connected = False
        self.daemon_proc = None

    def update_config(self, host, port, enabled):
        with self.lock:
            self.host = host.strip() or "127.0.0.1"
            self.port = int(port)
            self.enabled = enabled

    def _find_rigctld_binary(self):
        base_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        candidates = [
            os.path.join(base_x86, "hamlib", "bin", "rigctld.exe"),
            os.path.join(base_x86, "bin", "rigctld.exe"),
        ]

        if os.path.isdir(base_x86):
            for entry in os.listdir(base_x86):
                if entry.lower().startswith("hamlib"):
                    candidates.append(os.path.join(base_x86, entry, "bin", "rigctld.exe"))
                    candidates.append(os.path.join(base_x86, entry, "rigctld.exe"))

        candidates.extend([
            r"C:\hamlib\bin\rigctld.exe",
            r"C:\Program Files\hamlib\bin\rigctld.exe",
            r"C:\WSJT\wsjtx\bin\rigctld.exe"
        ])

        for path in candidates:
            if os.path.isfile(path):
                return path

        return "rigctld"

    def start_daemon(self, model_id, com_port, baud_rate):
        if self.host not in ("127.0.0.1", "localhost", ""):
            return True, f"Connecting to remote host {self.host}:{self.port} (skipped local daemon)."

        self.stop_daemon()
        rigctld_bin = self._find_rigctld_binary()

        cmd = [
            rigctld_bin,
            "-m", str(model_id).strip(),
            "-r", str(com_port).strip(),
            "-s", str(baud_rate).strip(),
            "-t", str(self.port)
        ]
        try:
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW

            self.daemon_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
            time.sleep(0.5)
            return True, f"Started {os.path.basename(rigctld_bin)} ({com_port}@{baud_rate})"
        except FileNotFoundError:
            return False, f"Could not find rigctld at {rigctld_bin} or in system PATH."
        except Exception as e:
            return False, f"Failed to launch rigctld: {e}"

    def stop_daemon(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.6)
            s.connect((self.host, self.port))
            s.sendall(b"q\n")
            s.close()
            time.sleep(0.2)
        except Exception:
            pass

        if self.daemon_proc:
            try:
                self.daemon_proc.terminate()
                self.daemon_proc.wait(timeout=1.0)
            except Exception:
                try:
                    self.daemon_proc.kill()
                except Exception:
                    pass
            self.daemon_proc = None

        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "rigctld.exe"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except Exception:
                pass

        self.is_connected = False
        return True, "Stopped rigctld daemon and released COM port."

    def _send_cmd(self, cmd_str, expect_reply=True, timeout=1.0):
        if not self.enabled:
            return False, "Hamlib disabled"
        with self.lock:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect((self.host, self.port))
                s.sendall(f"{cmd_str}\n".encode("ascii"))
                if expect_reply:
                    reply = s.recv(1024).decode("latin-1", errors="ignore").strip()
                else:
                    reply = "OK"
                s.close()
                self.is_connected = True
                return True, reply
            except Exception as e:
                self.is_connected = False
                return False, str(e)

    def set_frequency(self, freq_khz):
        try:
            freq_hz = int(round(float(freq_khz) * 1000.0))
            ok, reply = self._send_cmd(f"F {freq_hz}")
            if ok:
                return True, f"Frequency set to {freq_khz} kHz"
            return False, f"Hamlib Freq Error: {reply}"
        except Exception as e:
            return False, str(e)

    def get_mode(self):
        ok, reply = self._send_cmd("m")
        if ok:
            parts = reply.split()
            if len(parts) >= 2:
                return parts[0], parts[1]
            elif len(parts) == 1:
                return parts[0], "0"
        return "PKTUSB", "0"

    def set_mode_and_filter(self, mode_str="PKTUSB", filter_num=1):
        clean = mode_str.strip().upper()
        if "DATA" in clean or "USB-D" in clean or "PKT" in clean:
            target_mode = "PKTUSB"
        elif "LSB" in clean:
            target_mode = "LSB"
        elif "FM" in clean:
            target_mode = "PKTFM" if "D" in clean else "FM"
        elif "CW" in clean:
            target_mode = "CW"
        elif "RTTY" in clean:
            target_mode = "RTTY"
        else:
            target_mode = "USB"

        filter_passbands = {1: 3000, 2: 2400, 3: 500}
        pb = filter_passbands.get(filter_num, 0)

        ok, reply = self._send_cmd(f"M {target_mode} {pb}")
        if ok:
            return True, f"Mode: {target_mode}, Filter: FIL{filter_num} ({pb}Hz)"
        ok2, reply2 = self._send_cmd(f"M USB {pb}")
        return ok2, f"Mode fallback USB FIL{filter_num}: {reply2}"

    def set_ptt(self, ptt_on=True):
        val = 1 if ptt_on else 0
        ok, reply = self._send_cmd(f"T {val}")
        return ok, reply

    def get_meter_levels(self):
        swr_val = 1.0
        alc_val = 0.0
        pwr_val = 0.0

        ok_swr, r_swr = self._send_cmd(r"\get_level SWR")
        if ok_swr:
            try:
                swr_val = float(r_swr.strip().split()[-1])
            except Exception:
                pass

        ok_alc, r_alc = self._send_cmd(r"\get_level ALC")
        if ok_alc:
            try:
                alc_val = float(r_alc.strip().split()[-1])
            except Exception:
                pass

        ok_pwr, r_pwr = self._send_cmd(r"\get_level RFPOWER_METER_WATTS")
        if not ok_pwr:
            ok_pwr, r_pwr = self._send_cmd(r"\get_level RFPOWER")
        if ok_pwr:
            try:
                pwr_val = float(r_pwr.strip().split()[-1])
            except Exception:
                pass

        return swr_val, alc_val, pwr_val

    def trigger_autotune(self):
        ok, reply = self._send_cmd(r"\set_func TUNER 1")
        if not ok:
            ok, reply = self._send_cmd("U TUNER 1")
        return ok, reply

    def send_tune_carrier(self, duration=3.0, target_power=0.10):
        orig_mode, orig_pb = self.get_mode()
        orig_power = None
        ok_pwr, r_pwr = self._send_cmd(r"\get_level RFPOWER")
        if ok_pwr:
            try:
                orig_power = float(r_pwr.strip().split()[-1])
            except Exception:
                pass

        try:
            self._send_cmd(f"\\set_level RFPOWER {target_power}")
            self._send_cmd("M RTTY 0")
            time.sleep(0.1)
            self.set_ptt(True)

            t_end = time.time() + duration
            while time.time() < t_end:
                time.sleep(0.1)
        finally:
            self.set_ptt(False)
            time.sleep(0.1)
            self._send_cmd(f"M {orig_mode} {orig_pb}")
            if orig_power is not None:
                self._send_cmd(f"\\set_level RFPOWER {orig_power}")

        return True, "Carrier tune completed."

    def get_status(self):
        if not self.enabled:
            return "Disabled"
        ok, reply = self._send_cmd("f")
        if ok:
            try:
                freq_hz = float(reply.split()[0])
                freq_khz = freq_hz / 1000.0
                return f"Online ({freq_khz:.2f} kHz)"
            except Exception:
                return f"Online ({reply})"
        return f"Offline ({reply})"


# =====================================================================
# MAIN WORKSTATION CLIENT
# =====================================================================
class VaraBBSClient(tk.Tk):
    def __init__(self):
        super().__init__()

        self.default_call = "Your Call Here"
        self.default_host = "127.0.0.1"
        self.default_mode = "FM"
        self.default_cmd_port = "8300"
        self.default_data_port = "8301"
        self.default_bw = "NARROW"
        self.default_signature = ""
        self.default_hf_dwell = "20.0"
        self.default_fm_dwell = "1.5"

        self.default_rig_freq = "7103.20"
        self.default_radio_filter = 1
        self.default_hamlib_host = "127.0.0.1"
        self.default_hamlib_port = "4532"
        self.default_hamlib_enabled = True
        self.default_hamlib_model = "3073"
        self.default_hamlib_comm = "COM3"
        self.default_hamlib_baud = "19200"
        
        self.default_hf_contacts = [
            {"bbs": "N3MEL-2", "digi": "", "dwell": "20.0"},
            {"bbs": "N3MEL-7", "digi": "", "dwell": "20.0"}
        ]
        self.default_fm_contacts = [
            {"bbs": "N3MEL-2", "digi": "", "dwell": "1.5"},
            {"bbs": "N3MEL-7", "digi": "", "dwell": "1.5"}
        ]

        self.default_recipients = [
            "ALL@USA",
            "SPACWX@USA",
            "WX@ECBBS",
            "NEWS@WW"
        ]

        self.current_call = self.default_call
        self.current_host = self.default_host
        self.current_mode = self.default_mode
        self.current_cmd_port = self.default_cmd_port
        self.current_data_port = self.default_data_port
        self.current_bw = self.default_bw
        self.current_signature = self.default_signature
        self.hf_dwell = self.default_hf_dwell
        self.fm_dwell = self.default_fm_dwell

        self.rig_freq = self.default_rig_freq
        self.radio_filter = self.default_radio_filter
        self.hamlib_host = self.default_hamlib_host
        self.hamlib_port = self.default_hamlib_port
        self.hamlib_enabled = self.default_hamlib_enabled
        self.hamlib_model = self.default_hamlib_model
        self.hamlib_comm = self.default_hamlib_comm
        self.hamlib_baud = self.default_hamlib_baud

        self.cmd_sock = None
        self.data_sock = None
        self.worker_thread = None
        self.abort_requested = False
        self.tx_manual_queue = queue.Queue()

        self.listener_active = False
        self.listener_thread = None
        self.listener_cmd_sock = None
        self.listener_data_sock = None
        self.listener_stop_event = threading.Event()
        self.mailbox_in_session = False
        self.remote_call = ""
        self.mb_state = "CMD"
        self.mb_rx_msg = {}
        self.mb_line_buffer = ""

        self.dcd_monitor_stop = threading.Event()
        self.dcd_monitor_thread = None

        self.saved_geometry = "1280x840"
        self.theme_mode = "dark"
        self.hf_contacts = []
        self.fm_contacts = []
        self.recent_recipients = []
        self.inbox_msgs = []
        self.draft_msgs = []
        self.outbox_msgs = []
        self.sent_msgs = []
        self.trash_msgs = []
        self._load_data()

        self.cat = HamlibController(
            host=self.hamlib_host,
            port=self.hamlib_port,
            enabled=self.hamlib_enabled
        )

        self.title(f"VARA HF/FM Mail & Terminal Client - [{self.current_call}]")
        self.geometry(self.saved_geometry)
        self.after(50, self._maximize_window)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.style = ttk.Style(self)
        self._build_ui()
        self._apply_theme()
        self._refresh_bbs_dropdown()
        self._update_folder_counts()
        self._on_folder_select(None)

        self.after(500, self._start_live_dcd_monitor)
        self.after(1000, self._poll_cat_status)

    def _maximize_window(self):
        try:
            self.state('zoomed')
        except Exception:
            try:
                self.attributes('-zoomed', True)
            except Exception:
                pass

    def _load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    store = json.load(f)
                    self.saved_geometry = store.get("window_geometry", "1280x840")
                    self.theme_mode = store.get("theme_mode", "dark")
                    self.recent_recipients = store.get("recent_recipients", list(self.default_recipients))
                    self.current_call = store.get("my_call", self.default_call)
                    self.current_host = store.get("modem_host", self.default_host)
                    
                    loaded_mode = str(store.get("modem_mode", self.default_mode)).strip().upper()
                    self.current_mode = "HF" if "HF" in loaded_mode else "FM"

                    self.current_cmd_port = store.get("cmd_port", self.default_cmd_port)
                    self.current_data_port = store.get("data_port", self.default_data_port)
                    
                    if self.current_mode == "FM" and self.current_cmd_port == "8000":
                        self.current_cmd_port = "8300"
                        self.current_data_port = "8301"

                    self.current_bw = store.get("bandwidth", self.default_bw)
                    if self.current_bw not in ("BW500", "BW2300", "BW2750", "NARROW", "WIDE"):
                        self.current_bw = "BW500" if self.current_mode == "HF" else "NARROW"

                    self.current_signature = store.get("signature", self.default_signature)
                    self.hf_dwell = str(store.get("hf_dwell", self.default_hf_dwell))
                    self.fm_dwell = str(store.get("fm_dwell", self.default_fm_dwell))

                    self.rig_freq = str(store.get("rig_freq", self.default_rig_freq))
                    self.radio_filter = int(store.get("radio_filter", self.default_radio_filter))
                    self.hamlib_host = store.get("hamlib_host", self.default_hamlib_host)
                    self.hamlib_port = str(store.get("hamlib_port", self.default_hamlib_port))
                    self.hamlib_enabled = store.get("hamlib_enabled", self.default_hamlib_enabled)
                    self.hamlib_model = str(store.get("hamlib_model", self.default_hamlib_model))
                    self.hamlib_comm = str(store.get("hamlib_comm", self.default_hamlib_comm))
                    self.hamlib_baud = str(store.get("hamlib_baud", self.default_hamlib_baud))

                    raw_hf = store.get("hf_contacts", [])
                    self.hf_contacts = [
                        {
                            "bbs": c["bbs"].strip().upper(),
                            "digi": c.get("digi", "").strip().upper(),
                            "dwell": str(c.get("dwell", self.hf_dwell)).strip()
                        }
                        for c in raw_hf if isinstance(c, dict)
                    ] if raw_hf else list(self.default_hf_contacts)

                    raw_fm = store.get("fm_contacts", [])
                    self.fm_contacts = [
                        {
                            "bbs": c["bbs"].strip().upper(),
                            "digi": c.get("digi", "").strip().upper(),
                            "dwell": str(c.get("dwell", self.fm_dwell)).strip()
                        }
                        for c in raw_fm if isinstance(c, dict)
                    ] if raw_fm else list(self.default_fm_contacts)

                    self.inbox_msgs = store.get("inbox", [])
                    self.draft_msgs = store.get("drafts", [])
                    self.outbox_msgs = store.get("outbox", [])
                    self.sent_msgs = store.get("sent", [])
                    self.trash_msgs = store.get("trash", [])
                    return
            except Exception as e:
                print(f"[!] Warning: Could not parse database ({e}). Using defaults.")
        
        self.current_call = self.default_call
        self.current_host = self.default_host
        self.current_mode = self.default_mode
        self.current_cmd_port = self.default_cmd_port
        self.current_data_port = self.default_data_port
        self.current_bw = self.default_bw
        self.current_signature = self.default_signature
        self.hf_dwell = self.default_hf_dwell
        self.fm_dwell = self.default_fm_dwell

        self.rig_freq = self.default_rig_freq
        self.radio_filter = self.default_radio_filter
        self.hamlib_host = self.default_hamlib_host
        self.hamlib_port = self.default_hamlib_port
        self.hamlib_enabled = self.default_hamlib_enabled
        self.hamlib_model = self.default_hamlib_model
        self.hamlib_comm = self.default_hamlib_comm
        self.hamlib_baud = self.default_hamlib_baud

        self.hf_contacts = list(self.default_hf_contacts)
        self.fm_contacts = list(self.default_fm_contacts)
        self.recent_recipients = list(self.default_recipients)

    def _save_data(self):
        try:
            self.saved_geometry = self.geometry()
        except Exception:
            pass

        if hasattr(self, "cat_freq_entry"):
            self.rig_freq = self.cat_freq_entry.get().strip()

        data = {
            "window_geometry": self.saved_geometry,
            "theme_mode": self.theme_mode,
            "my_call": self.current_call,
            "modem_host": self.current_host,
            "modem_mode": self.current_mode,
            "cmd_port": self.current_cmd_port,
            "data_port": self.current_data_port,
            "bandwidth": self.current_bw,
            "signature": self.current_signature,
            "hf_dwell": self.hf_dwell,
            "fm_dwell": self.fm_dwell,
            "rig_freq": self.rig_freq,
            "radio_filter": self.radio_filter_var.get() if hasattr(self, "radio_filter_var") else self.radio_filter,
            "hamlib_host": self.hamlib_host,
            "hamlib_port": self.hamlib_port,
            "hamlib_enabled": self.hamlib_enabled,
            "hamlib_model": self.hamlib_model,
            "hamlib_comm": self.hamlib_comm,
            "hamlib_baud": self.hamlib_baud,
            "recent_recipients": self.recent_recipients,
            "hf_contacts": self.hf_contacts,
            "fm_contacts": self.fm_contacts,
            "inbox": self.inbox_msgs,
            "drafts": self.draft_msgs,
            "outbox": self.outbox_msgs,
            "sent": self.sent_msgs,
            "trash": self.trash_msgs
        }
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[!] Error saving database: {e}")

    def on_close(self):
        self._save_data()
        self.abort_requested = True
        self.dcd_monitor_stop.set()
        self._stop_listener_service()
        self.cat.stop_daemon()
        try:
            if self.cmd_sock:
                self.cmd_sock.sendall(b"ABORT\rDISCONNECT\r")
            if self.data_sock:
                self.data_sock.close()
            if self.cmd_sock:
                self.cmd_sock.close()
        except Exception:
            pass

        try:
            self.destroy()
        except Exception:
            pass

        os._exit(0)

    # ==========================================
    # MODEM STATUS TELEMETRY & LIVE DCD
    # ==========================================
    def set_modem_led(self, led_name, state=False):
        colors = {
            "pwr": ("#22c55e", "#1e3a24"),
            "conn": ("#3b82f6", "#1e293b"),
            "dcd": ("#eab308", "#382d12"),
            "tx": ("#ef4444", "#3d1416")
        }
        canvas, item = getattr(self, f"led_{led_name}", (None, None))
        if canvas and item:
            on_col, off_col = colors.get(led_name, ("#22c55e", "#1e3a24"))
            fill = on_col if state else off_col
            canvas.itemconfig(item, fill=fill)

    def _start_live_dcd_monitor(self):
        if self.dcd_monitor_thread and self.dcd_monitor_thread.is_alive():
            return
        self.dcd_monitor_stop.clear()
        self.dcd_monitor_thread = threading.Thread(target=self._run_live_dcd_telemetry, daemon=True)
        self.dcd_monitor_thread.start()

    def _run_live_dcd_telemetry(self):
        while not self.dcd_monitor_stop.is_set():
            if (self.worker_thread and self.worker_thread.is_alive()) or self.listener_active:
                time.sleep(1.0)
                continue

            host = self.current_host
            try:
                port = int(self.current_cmd_port)
            except ValueError:
                port = 8358 if self.current_mode == "HF" else 8300

            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3.0)
                sock.connect((host, port))
                self.after(0, lambda: self.set_modem_led("pwr", True))
                sock.settimeout(0.5)

                while not self.dcd_monitor_stop.is_set():
                    if (self.worker_thread and self.worker_thread.is_alive()) or self.listener_active:
                        break
                    try:
                        raw = sock.recv(512).decode("latin-1", errors="ignore")
                        if not raw:
                            break
                        if "BUSY ON" in raw or "DCD ON" in raw:
                            self.after(0, lambda: self.set_modem_led("dcd", True))
                        elif "BUSY OFF" in raw or "DCD OFF" in raw:
                            self.after(0, lambda: self.set_modem_led("dcd", False))
                        if "PTT ON" in raw:
                            self.cat.set_ptt(True)
                            self.after(0, lambda: self.set_modem_led("tx", True))
                        elif "PTT OFF" in raw:
                            self.cat.set_ptt(False)
                            self.after(0, lambda: self.set_modem_led("tx", False))
                    except socket.timeout:
                        pass
            except Exception:
                self.after(0, lambda: self.set_modem_led("pwr", False))
                self.after(0, lambda: self.set_modem_led("dcd", False))
                time.sleep(3.0)
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass

    # ==========================================
    # MODAL: STATION & MODEM SETTINGS
    # ==========================================
    def open_station_settings_window(self):
        win = tk.Toplevel(self)
        win.title("Station & Modem Configuration")
        win.geometry("480x520")
        win.resizable(False, False)

        is_dark = (self.theme_mode == "dark")
        bg_col = "#161922" if is_dark else "#f3f4f6"
        win.configure(bg=bg_col)

        f = ttk.Frame(win, padding=16)
        f.pack(fill=tk.BOTH, expand=True)

        cfg_group = ttk.LabelFrame(f, text="Modem Network Parameters", padding=10)
        cfg_group.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(cfg_group, text="Operating Mode:").grid(row=0, column=0, sticky=tk.W, pady=4)
        mode_var = tk.StringVar(value=self.current_mode)
        mode_combo = ttk.Combobox(cfg_group, textvariable=mode_var, values=["HF", "FM"], state="readonly", width=12)
        mode_combo.grid(row=0, column=1, sticky=tk.W, pady=4)

        ttk.Label(cfg_group, text="Station Callsign:").grid(row=1, column=0, sticky=tk.W, pady=4)
        call_entry = ttk.Entry(cfg_group, width=16)
        call_entry.insert(0, self.current_call)
        call_entry.grid(row=1, column=1, sticky=tk.W, pady=4)
        self.attach_context_menu(call_entry)

        ttk.Label(cfg_group, text="Modem Host / IP:").grid(row=2, column=0, sticky=tk.W, pady=4)
        host_entry = ttk.Entry(cfg_group, width=22)
        host_entry.insert(0, self.current_host)
        host_entry.grid(row=2, column=1, sticky=tk.W, pady=4)
        self.attach_context_menu(host_entry)

        ports_sub = ttk.Frame(cfg_group)
        ports_sub.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=4)

        ttk.Label(ports_sub, text="Cmd Port:").pack(side=tk.LEFT, padx=(0, 2))
        cmd_p_entry = ttk.Entry(ports_sub, width=6)
        cmd_p_entry.insert(0, self.current_cmd_port)
        cmd_p_entry.pack(side=tk.LEFT, padx=(0, 8))
        self.attach_context_menu(cmd_p_entry)

        ttk.Label(ports_sub, text="Data Port:").pack(side=tk.LEFT, padx=(0, 2))
        data_p_entry = ttk.Entry(ports_sub, width=6)
        data_p_entry.insert(0, self.current_data_port)
        data_p_entry.pack(side=tk.LEFT, padx=(0, 8))
        self.attach_context_menu(data_p_entry)

        dwell_sub = ttk.Frame(cfg_group)
        dwell_sub.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=4)

        ttk.Label(dwell_sub, text="HF Dwell (s):").pack(side=tk.LEFT, padx=(0, 2))
        hf_dwell_entry = ttk.Entry(dwell_sub, width=6)
        hf_dwell_entry.insert(0, self.hf_dwell)
        hf_dwell_entry.pack(side=tk.LEFT, padx=(0, 8))
        self.attach_context_menu(hf_dwell_entry)

        ttk.Label(dwell_sub, text="FM Dwell (s):").pack(side=tk.LEFT, padx=(0, 2))
        fm_dwell_entry = ttk.Entry(dwell_sub, width=6)
        fm_dwell_entry.insert(0, self.fm_dwell)
        fm_dwell_entry.pack(side=tk.LEFT)
        self.attach_context_menu(fm_dwell_entry)

        ttk.Label(cfg_group, text="Modem Bandwidth:").grid(row=5, column=0, sticky=tk.W, pady=4)
        bw_var = tk.StringVar(value=self.current_bw)
        bw_combo = ttk.Combobox(cfg_group, textvariable=bw_var, state="readonly", width=14)
        
        def _update_bw_options(*args):
            m = mode_var.get()
            if m == "HF":
                bw_combo.config(values=["BW500", "BW2300", "BW2750"])
                if bw_var.get() not in ("BW500", "BW2300", "BW2750"):
                    bw_var.set("BW500")
            else:
                bw_combo.config(values=["NARROW", "WIDE"])
                if bw_var.get() not in ("NARROW", "WIDE"):
                    bw_var.set("NARROW")

        mode_var.trace_add("write", _update_bw_options)
        _update_bw_options()
        bw_combo.grid(row=5, column=1, sticky=tk.W, pady=4)

        sig_group = ttk.LabelFrame(f, text="Default Station Signature", padding=8)
        sig_group.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        sig_txt = scrolledtext.ScrolledText(sig_group, height=4, font=("Consolas", 9))
        sig_txt.insert("1.0", self.current_signature)
        sig_txt.pack(fill=tk.BOTH, expand=True)
        self.attach_context_menu(sig_txt)

        btn_row = ttk.Frame(f)
        btn_row.pack(fill=tk.X, pady=(4, 0))

        def _save_station_settings():
            old_mode = self.current_mode
            self.current_mode = mode_var.get()
            self.current_call = call_entry.get().strip().upper()
            self.current_host = host_entry.get().strip()
            self.current_cmd_port = cmd_p_entry.get().strip()
            self.current_data_port = data_p_entry.get().strip()
            self.hf_dwell = hf_dwell_entry.get().strip()
            self.fm_dwell = fm_dwell_entry.get().strip()
            self.current_bw = bw_var.get().strip()
            self.current_signature = sig_txt.get("1.0", tk.END).strip()

            self.title(f"VARA HF/FM Mail & Terminal Client - [{self.current_call}]")
            self._save_data()

            if old_mode != self.current_mode:
                if hasattr(self, "op_mode_var"):
                    self.op_mode_var.set(self.current_mode)
                self._on_mode_change()

            self.term_print(f"[*] Station settings updated ({self.current_call} @ {self.current_host})\n")
            win.destroy()

        ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_row, text="Save Settings", command=_save_station_settings).pack(side=tk.RIGHT, padx=4)

    # ==========================================
    # MODAL: QUICK REFERENCE WINDOW
    # ==========================================
    def open_quick_reference_window(self):
        """Displays command reference guides in a floating popup window."""
        win = tk.Toplevel(self)
        win.title("Command Quick Reference")
        win.geometry("380x280")
        win.resizable(False, False)

        is_dark = (self.theme_mode == "dark")
        bg_col = "#161922" if is_dark else "#f3f4f6"
        win.configure(bg=bg_col)

        f = ttk.Frame(win, padding=16)
        f.pack(fill=tk.BOTH, expand=True)

        ref_box = ttk.LabelFrame(f, text="Node & BBS Syntax Guide", padding=10)
        ref_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        guide_lines = [
            ("Read Message", "Dbl-Click msg# in Term / R <#>", "Retrieve mail"),
            ("Personal Mail", "SP <callsign>", "Send private message"),
            ("Bulletin", "SB <category> @ <route>", "Broadcast to group"),
            ("Reply", "SR <msg#>", "Reply to selected msg"),
            ("NTS Traffic", "ST <zip> @ <route>", "National Traffic System"),
            ("Kill / Delete", "KM <msg#>", "Delete own message"),
            ("Disconnect", "B / BYE / QUIT", "Graceful link logoff")
        ]

        for desc, syntax, note in guide_lines:
            row_frame = ttk.Frame(ref_box)
            row_frame.pack(fill=tk.X, pady=2)
            ttk.Label(row_frame, text=f"{desc}:", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
            ttk.Label(row_frame, text=syntax, font=("Consolas", 8, "bold"), foreground="#0284c7").pack(side=tk.RIGHT)

        ttk.Button(f, text="Close", command=win.destroy).pack(anchor=tk.E)

    # ==========================================
    # VFO TUNING, FILTER & HAMLIB CONTROL
    # ==========================================
    def tune_vfo_direct(self):
        freq_str = self.cat_freq_entry.get().strip()
        if not freq_str:
            return
        self.rig_freq = freq_str
        self._save_data()
        filt = self.radio_filter_var.get()
        threading.Thread(target=lambda: self._tune_hamlib(freq_str, "PKTUSB", filt), daemon=True).start()

    def set_preset_frequency(self, freq_str):
        self.cat_freq_entry.delete(0, tk.END)
        self.cat_freq_entry.insert(0, freq_str)
        self.tune_vfo_direct()

    def on_filter_selected(self):
        filt = self.radio_filter_var.get()
        self.radio_filter = filt
        self._save_data()
        self.term_print(f"[*] Radio Filter selected: F{filt}\n")
        self.tune_vfo_direct()

    def start_hamlib_from_panel(self):
        ok, msg = self.cat.start_daemon(self.hamlib_model, self.hamlib_comm, self.hamlib_baud)
        self.term_print(f"[*] {msg}\n")
        time.sleep(0.5)
        st = self.cat.get_status()
        self.cat_status_lbl.config(text=f"CAT: {st}")

    def stop_hamlib_from_panel(self):
        ok, msg = self.cat.stop_daemon()
        self.term_print(f"[*] {msg}\n")
        st = self.cat.get_status()
        self.cat_status_lbl.config(text=f"CAT: {st}")

    # ==========================================
    # SWR / ALC METERING & TUNE POPUP
    # ==========================================
    def open_meter_window(self):
        if hasattr(self, "meter_win") and self.meter_win.winfo_exists():
            self.meter_win.lift()
            return

        self.meter_win = tk.Toplevel(self)
        self.meter_win.title("Radio Meter & Tuner")
        self.meter_win.geometry("360x280")
        self.meter_win.resizable(False, False)

        is_dark = (self.theme_mode == "dark")
        bg_col = "#161922" if is_dark else "#f3f4f6"
        self.meter_win.configure(bg=bg_col)

        f = ttk.Frame(self.meter_win, padding=14)
        f.pack(fill=tk.BOTH, expand=True)

        readout_box = ttk.LabelFrame(f, text="Live Transceiver Metering", padding=10)
        readout_box.pack(fill=tk.X, pady=(0, 10))

        swr_row = ttk.Frame(readout_box)
        swr_row.pack(fill=tk.X, pady=4)
        ttk.Label(swr_row, text="SWR:", font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        self.lbl_swr_val = ttk.Label(swr_row, text="1.00 : 1", font=("Consolas", 15, "bold"), foreground="#22c55e")
        self.lbl_swr_val.pack(side=tk.RIGHT)

        alc_row = ttk.Frame(readout_box)
        alc_row.pack(fill=tk.X, pady=4)
        ttk.Label(alc_row, text="ALC Level:", font=("Arial", 11, "bold")).pack(side=tk.LEFT)
        self.lbl_alc_val = ttk.Label(alc_row, text="0 %", font=("Consolas", 14, "bold"), foreground="#3b82f6")
        self.lbl_alc_val.pack(side=tk.RIGHT)

        pwr_row = ttk.Frame(readout_box)
        pwr_row.pack(fill=tk.X, pady=4)
        ttk.Label(pwr_row, text="Forward Power:", font=("Arial", 10)).pack(side=tk.LEFT)
        self.lbl_pwr_val = ttk.Label(pwr_row, text="0 W", font=("Consolas", 11, "bold"), foreground="#9ca3af")
        self.lbl_pwr_val.pack(side=tk.RIGHT)

        tune_box = ttk.Frame(f)
        tune_box.pack(fill=tk.X, pady=(4, 0))

        btn_grid = ttk.Frame(tune_box)
        btn_grid.pack(fill=tk.X, pady=(2, 4))

        def _do_autotune():
            self.btn_tune_action.config(state=tk.DISABLED, text="Tuning...")
            self.btn_carrier_tune.config(state=tk.DISABLED)
            self.term_print("[*] Initiating ATU automatic antenna tune cycle...\n")
            
            def _tune_bg():
                ok, msg = self.cat.trigger_autotune()
                time.sleep(2.0)
                self.after(0, lambda: self.btn_tune_action.config(state=tk.NORMAL, text="TUNE ATU"))
                self.after(0, lambda: self.btn_carrier_tune.config(state=tk.NORMAL))
                if ok:
                    self.term_print("[+] Antenna tuner cycle completed.\n")
                else:
                    self.term_print(f"[!] Tuner command result: {msg}\n")

            threading.Thread(target=_tune_bg, daemon=True).start()

        def _do_carrier_tune():
            self.btn_carrier_tune.config(state=tk.DISABLED, text="TRANSMITTING...")
            self.btn_tune_action.config(state=tk.DISABLED)
            self.set_modem_led("tx", True)
            self.term_print("[*] Keying low-power carrier tune burst (3s)...\n")

            def _carrier_bg():
                try:
                    self.cat.send_tune_carrier(duration=3.0, target_power=0.10)
                    self.term_print("[+] Tune carrier finished.\n")
                except Exception as e:
                    self.term_print(f"[!] Tune carrier error: {e}\n")
                finally:
                    self.after(0, lambda: self.btn_carrier_tune.config(state=tk.NORMAL, text="TUNE CARRIER"))
                    self.after(0, lambda: self.btn_tune_action.config(state=tk.NORMAL))
                    self.after(0, lambda: self.set_modem_led("tx", False))

            threading.Thread(target=_carrier_bg, daemon=True).start()

        self.btn_tune_action = tk.Button(
            btn_grid, text="TUNE ATU", font=("Arial", 10, "bold"),
            bg="#dc2626", fg="#ffffff", activebackground="#b91c1c",
            activeforeground="#ffffff", relief=tk.RAISED, command=_do_autotune
        )
        self.btn_tune_action.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        self.btn_carrier_tune = tk.Button(
            btn_grid, text="TUNE CARRIER", font=("Arial", 10, "bold"),
            bg="#2563eb", fg="#ffffff", activebackground="#1d4ed8",
            activeforeground="#ffffff", relief=tk.RAISED, command=_do_carrier_tune
        )
        self.btn_carrier_tune.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(3, 0))

        def _poll_meters():
            if not hasattr(self, "meter_win") or not self.meter_win.winfo_exists():
                return
            
            if self.cat.enabled and self.cat.is_connected:
                def _fetch():
                    swr, alc, pwr = self.cat.get_meter_levels()
                    
                    def _update_ui():
                        swr_col = "#22c55e" if swr < 1.5 else ("#eab308" if swr < 2.0 else "#ef4444")
                        self.lbl_swr_val.config(text=f"{swr:.2f} : 1", foreground=swr_col)

                        alc_pct = int(alc * 100) if alc <= 1.0 else int(alc)
                        alc_col = "#22c55e" if alc_pct <= 30 else ("#eab308" if alc_pct <= 60 else "#ef4444")
                        self.lbl_alc_val.config(text=f"{alc_pct} %", foreground=alc_col)
                        self.lbl_pwr_val.config(text=f"{pwr:.1f} W")

                    self.after(0, _update_ui)

                threading.Thread(target=_fetch, daemon=True).start()

            self.meter_win.after(350, _poll_meters)

        _poll_meters()

    # ==========================================
    # HAMLIB CAT SETUP WINDOW
    # ==========================================
    def open_cat_setup_window(self):
        win = tk.Toplevel(self)
        win.title("Hamlib CAT Setup")
        win.geometry("500x500")
        win.resizable(False, False)

        is_dark = (self.theme_mode == "dark")
        bg_col = "#161922" if is_dark else "#f3f4f6"
        win.configure(bg=bg_col)

        f = ttk.Frame(win, padding=14)
        f.pack(fill=tk.BOTH, expand=True)

        enabled_var = tk.BooleanVar(value=self.hamlib_enabled)
        chk_en = ttk.Checkbutton(f, text="Enable Hamlib CAT & PTT Control", variable=enabled_var)
        chk_en.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        hw_group = ttk.LabelFrame(f, text="Hardware Radio & Serial Parameters", padding=8)
        hw_group.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))

        ttk.Label(hw_group, text="Transceiver Model:").grid(row=0, column=0, sticky=tk.W, pady=4)
        model_display_values = [f"{name} ({mid})" for name, mid in POPULAR_RIGS]
        model_combo = ttk.Combobox(hw_group, values=model_display_values, width=28)
        current_display = next((f"{name} ({mid})" for name, mid in POPULAR_RIGS if mid == self.hamlib_model), self.hamlib_model)
        model_combo.set(current_display)
        model_combo.grid(row=0, column=1, sticky=tk.W, pady=4)

        ttk.Label(hw_group, text="Serial COM Port:").grid(row=1, column=0, sticky=tk.W, pady=4)
        com_entry = ttk.Combobox(hw_group, values=["COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "/dev/ttyUSB0"], width=14)
        com_entry.set(self.hamlib_comm)
        com_entry.grid(row=1, column=1, sticky=tk.W, pady=4)

        ttk.Label(hw_group, text="Baud Rate:").grid(row=2, column=0, sticky=tk.W, pady=4)
        baud_combo = ttk.Combobox(hw_group, values=["4800", "9600", "19200", "38400", "57600", "115200"], width=14)
        baud_combo.set(self.hamlib_baud)
        baud_combo.grid(row=2, column=1, sticky=tk.W, pady=4)

        tcp_group = ttk.LabelFrame(f, text="rigctld Network Socket", padding=8)
        tcp_group.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))

        ttk.Label(tcp_group, text="Host / IP:").grid(row=0, column=0, sticky=tk.W, pady=4)
        host_entry = ttk.Entry(tcp_group, width=18)
        host_entry.insert(0, self.hamlib_host)
        host_entry.grid(row=0, column=1, sticky=tk.W, pady=4)

        ttk.Label(tcp_group, text="Port:").grid(row=1, column=0, sticky=tk.W, pady=4)
        port_entry = ttk.Entry(tcp_group, width=8)
        port_entry.insert(0, self.hamlib_port)
        port_entry.grid(row=1, column=1, sticky=tk.W, pady=4)

        status_box = ttk.LabelFrame(f, text="Live Diagnostics", padding=8)
        status_box.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))

        diag_lbl = ttk.Label(status_box, text=f"Status: {self.cat.get_status()}", font=("Consolas", 9, "bold"))
        diag_lbl.pack(anchor=tk.W, pady=2)

        ctrl_row1 = ttk.Frame(status_box)
        ctrl_row1.pack(fill=tk.X, pady=(4, 2))

        def _extract_model_id():
            raw = model_combo.get().strip()
            m = re.search(r'\((\d+)\)', raw)
            return m.group(1) if m else raw

        def _test_connect():
            h = host_entry.get().strip() or "127.0.0.1"
            p = port_entry.get().strip() or "4532"
            self.cat.update_config(h, p, True)
            st = self.cat.get_status()
            diag_lbl.config(text=f"Status: {st}")

        ttk.Button(ctrl_row1, text="Ping Socket", command=_test_connect).pack(side=tk.LEFT, padx=2)

        btn_row = ttk.Frame(f)
        btn_row.grid(row=4, column=0, columnspan=2, sticky=tk.E, pady=(10, 0))

        def _save_cat():
            self.hamlib_model = _extract_model_id()
            self.hamlib_comm = com_entry.get().strip()
            self.hamlib_baud = baud_combo.get().strip()
            self.hamlib_host = host_entry.get().strip() or "127.0.0.1"
            self.hamlib_port = port_entry.get().strip() or "4532"
            self.hamlib_enabled = enabled_var.get()

            self.cat.update_config(self.hamlib_host, self.hamlib_port, self.hamlib_enabled)
            self._save_data()
            self.term_print(f"[*] Hamlib settings saved: Model {self.hamlib_model} on {self.hamlib_comm}@{self.hamlib_baud}\n")
            win.destroy()

        ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="Save & Apply", command=_save_cat).pack(side=tk.LEFT, padx=4)

    def _poll_cat_status(self):
        if hasattr(self, "cat_status_lbl"):
            def _query():
                st = self.cat.get_status()
                self.after(0, lambda: self.cat_status_lbl.config(text=f"CAT: {st}"))
            threading.Thread(target=_query, daemon=True).start()
        self.after(4000, self._poll_cat_status)

    def attach_context_menu(self, widget):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: self._select_all_widget(widget))

        def _show_menu(event):
            is_dark = (self.theme_mode == "dark")
            m_bg = "#1f2430" if is_dark else "#ffffff"
            m_fg = "#e5e7eb" if is_dark else "#111827"
            menu.config(bg=m_bg, fg=m_fg, activebackground="#2563eb", activeforeground="#ffffff")
            menu.tk_popup(event.x_root, event.y_root)

        widget.bind("<Button-3>", _show_menu)
        widget.bind("<Button-2>", _show_menu)

    def _select_all_widget(self, widget):
        if isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox)):
            widget.select_range(0, tk.END)
            widget.icursor(tk.END)
        elif isinstance(widget, (tk.Text, scrolledtext.ScrolledText)):
            widget.tag_add("sel", "1.0", "end-1c")

    def toggle_theme(self):
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        if hasattr(self, "theme_radio_var"):
            self.theme_radio_var.set(self.theme_mode)
        self._apply_theme()
        self._save_data()

    def _on_theme_radio_select(self):
        selected = self.theme_radio_var.get()
        if selected != self.theme_mode:
            self.theme_mode = selected
            self._apply_theme()
            self._save_data()

    def _apply_theme(self):
        is_dark = (self.theme_mode == "dark")
        bg_main = "#161922" if is_dark else "#f3f4f6"
        bg_card = "#1f2430" if is_dark else "#ffffff"
        fg_text = "#e5e7eb" if is_dark else "#111827"
        border_col = "#374151" if is_dark else "#d1d5db"
        tree_sel = "#2563eb" if is_dark else "#3b82f6"

        self.configure(bg=bg_main)
        self.left_canvas.configure(bg=bg_main)

        self.style.theme_use("clam")
        self.style.configure(".", background=bg_main, foreground=fg_text)
        self.style.configure("TFrame", background=bg_main)
        self.style.configure("TLabel", background=bg_main, foreground=fg_text)
        self.style.configure("TLabelframe", background=bg_main, foreground=fg_text)
        self.style.configure("TLabelframe.Label", background=bg_main, foreground=fg_text, font=("Arial", 9, "bold"))
        self.style.configure("TButton", background=bg_card, foreground=fg_text, bordercolor=border_col)
        self.style.map("TButton", background=[("active", border_col)], foreground=[("active", fg_text)])
        self.style.configure("TEntry", fieldbackground=bg_card, foreground=fg_text, bordercolor=border_col)
        self.style.configure("TCombobox", fieldbackground=bg_card, background=bg_main, foreground=fg_text)
        self.style.configure("TRadiobutton", background=bg_main, foreground=fg_text)

        self.style.configure("Treeview", background=bg_card, foreground=fg_text, fieldbackground=bg_card, borderwidth=0, rowheight=24)
        self.style.configure("Treeview.Heading", background=bg_main, foreground=fg_text, bordercolor=border_col, font=("Arial", 9, "bold"))
        self.style.map("Treeview", background=[("selected", tree_sel)], foreground=[("selected", "#ffffff")])

    def _open_html_forms_suite(self):
        webbrowser.open_new_tab("https://www.tprfn.net/html-form-suite")

    def _get_active_contacts(self):
        return self.hf_contacts if self.current_mode == "HF" else self.fm_contacts

    def _on_mode_radio_select(self):
        sel_mode = self.op_mode_var.get()
        if sel_mode != self.current_mode:
            self.current_mode = sel_mode
            self._on_mode_change()
            self._save_data()

    def _on_control_action_select(self):
        action = self.control_action_var.get()
        if action == "STA":
            self.open_station_settings_window()
        elif action == "CAT":
            self.open_cat_setup_window()
        elif action == "HTML":
            self._open_html_forms_suite()
        elif action == "METERS":
            self.open_meter_window()
        elif action == "QREF":
            self.open_quick_reference_window()
        self.control_action_var.set("")

    def _build_ui(self):
        top_bar = ttk.Frame(self, padding=(8, 6))
        top_bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top_bar, text="Target BBS:").pack(side=tk.LEFT, padx=(0, 4))
        self.bbs_combo = ttk.Combobox(top_bar, width=12)
        self.bbs_combo.pack(side=tk.LEFT, padx=(0, 4))
        self.bbs_combo.bind("<<ComboboxSelected>>", self._on_bbs_selected)
        self.attach_context_menu(self.bbs_combo)

        self.btn_add_bbs = ttk.Button(top_bar, text="[+] Add", command=self.add_bbs_station)
        self.btn_add_bbs.pack(side=tk.LEFT, padx=1)

        self.btn_del_bbs = ttk.Button(top_bar, text="[-] Del", command=self.delete_bbs_station)
        self.btn_del_bbs.pack(side=tk.LEFT, padx=(1, 6))

        ttk.Label(top_bar, text="Via Digi:").pack(side=tk.LEFT, padx=(0, 4))
        self.digi_entry = ttk.Entry(top_bar, width=10)
        self.digi_entry.pack(side=tk.LEFT, padx=(0, 6))
        self.attach_context_menu(self.digi_entry)

        self.btn_send_rcv = ttk.Button(top_bar, text="Send/Recv", command=self.start_auto_session)
        self.btn_send_rcv.pack(side=tk.LEFT, padx=3)

        self.btn_manual_conn = ttk.Button(top_bar, text="Connect (Term)", command=self.start_manual_session)
        self.btn_manual_conn.pack(side=tk.LEFT, padx=3)

        self.btn_disconnect = ttk.Button(top_bar, text="Disconnect", state=tk.DISABLED, command=self.manual_disconnect)
        self.btn_disconnect.pack(side=tk.LEFT, padx=3)

        self.btn_listen = ttk.Button(top_bar, text="Mailbox Standby", command=self.toggle_mailbox_listener)
        self.btn_listen.pack(side=tk.LEFT, padx=3)

        self.btn_new_msg = ttk.Button(top_bar, text="New Message", command=self.open_composer)
        self.btn_new_msg.pack(side=tk.LEFT, padx=3)

        lights_frame = ttk.Frame(top_bar, padding=(4, 0))
        lights_frame.pack(side=tk.RIGHT, padx=4)

        def _make_led(parent, label_text, default_off_col):
            box = ttk.Frame(parent)
            box.pack(side=tk.LEFT, padx=3)
            c = tk.Canvas(box, width=13, height=13, highlightthickness=0, bg="#161922")
            c.pack(side=tk.LEFT, padx=(0, 2))
            circle = c.create_oval(1, 1, 12, 12, fill=default_off_col, outline="#374151")
            lbl = ttk.Label(box, text=label_text, font=("Arial", 7, "bold"))
            lbl.pack(side=tk.LEFT)
            return c, circle

        self.led_pwr = _make_led(lights_frame, "PWR", "#1e3a24")
        self.led_conn = _make_led(lights_frame, "CONN", "#1e293b")
        self.led_dcd = _make_led(lights_frame, "DCD", "#382d12")
        self.led_tx = _make_led(lights_frame, "TX", "#3d1416")

        self.status_lbl = ttk.Label(top_bar, text="Idle", foreground="gray", font=("Arial", 9, "bold"))
        self.status_lbl.pack(side=tk.RIGHT, padx=(4, 8))

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X)

        body_container = ttk.Frame(self)
        body_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        left_container = ttk.Frame(body_container, width=370)
        left_container.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))
        left_container.pack_propagate(False)

        self.left_canvas = tk.Canvas(left_container, borderwidth=0, highlightthickness=0)
        self.left_scrollbar = ttk.Scrollbar(left_container, orient=tk.VERTICAL, command=self.left_canvas.yview)
        
        self.scrollable_left = ttk.Frame(self.left_canvas)
        self.scrollable_left.bind("<Configure>", lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all")))

        self.canvas_window = self.left_canvas.create_window((0, 0), window=self.scrollable_left, anchor="nw", width=350)
        self.left_canvas.configure(yscrollcommand=self.left_scrollbar.set)

        self.left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_left_mousewheel(event):
            if event.num == 5 or event.delta < 0:
                self.left_canvas.yview_scroll(2, "units")
            elif event.num == 4 or event.delta > 0:
                self.left_canvas.yview_scroll(-2, "units")
            return "break"

        self.left_canvas.bind("<MouseWheel>", _on_left_mousewheel)
        self.left_canvas.bind("<Button-4>", _on_left_mousewheel)
        self.left_canvas.bind("<Button-5>", _on_left_mousewheel)

        # Mailboxes Tree
        folder_group = ttk.LabelFrame(self.scrollable_left, text="Mailboxes", padding=6)
        folder_group.pack(fill=tk.X, pady=(0, 6))

        folder_frame = ttk.Frame(folder_group)
        folder_frame.pack(fill=tk.X)

        self.folder_v_scroll = ttk.Scrollbar(folder_frame, orient=tk.VERTICAL)
        self.folder_tree = ttk.Treeview(folder_frame, selectmode="browse", show="tree", height=5, yscrollcommand=self.folder_v_scroll.set)
        self.folder_v_scroll.config(command=self.folder_tree.yview)

        self.folder_v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.folder_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.f_inbox = self.folder_tree.insert("", "end", text="Inbox (0)", values=("inbox",))
        self.f_drafts = self.folder_tree.insert("", "end", text="Drafts (0)", values=("drafts",))
        self.f_outbox = self.folder_tree.insert("", "end", text="Outbox (0)", values=("outbox",))
        self.f_sent = self.folder_tree.insert("", "end", text="Sent (0)", values=("sent",))
        self.f_trash = self.folder_tree.insert("", "end", text="Trash (0)", values=("trash",))
        self.folder_tree.bind("<<TreeviewSelect>>", self._on_folder_select)
        self.folder_tree.selection_set(self.f_inbox)

        # Operational VFO & CAT Block
        self.vfo_frame = ttk.LabelFrame(self.scrollable_left, text="HF VFO & CAT Tuning", padding=6)
        if self.current_mode == "HF":
            self.vfo_frame.pack(fill=tk.X, pady=(0, 6))

        hamlib_btn_row = ttk.Frame(self.vfo_frame)
        hamlib_btn_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(hamlib_btn_row, text="Start Hamlib", command=self.start_hamlib_from_panel).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(hamlib_btn_row, text="Stop Hamlib", command=self.stop_hamlib_from_panel).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))

        filter_row = ttk.Frame(self.vfo_frame)
        filter_row.pack(fill=tk.X, pady=(2, 4))
        ttk.Label(filter_row, text="Filter:", font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self.radio_filter_var = tk.IntVar(value=self.radio_filter)
        
        rb_f1 = ttk.Radiobutton(filter_row, text="F1 (3.0k)", variable=self.radio_filter_var, value=1, command=self.on_filter_selected)
        rb_f1.pack(side=tk.LEFT, padx=2)
        rb_f2 = ttk.Radiobutton(filter_row, text="F2 (2.4k)", variable=self.radio_filter_var, value=2, command=self.on_filter_selected)
        rb_f2.pack(side=tk.LEFT, padx=2)
        rb_f3 = ttk.Radiobutton(filter_row, text="F3 (500)", variable=self.radio_filter_var, value=3, command=self.on_filter_selected)
        rb_f3.pack(side=tk.LEFT, padx=2)

        freq_entry_row = ttk.Frame(self.vfo_frame)
        freq_entry_row.pack(fill=tk.X, pady=(2, 4))

        ttk.Label(freq_entry_row, text="Dial (kHz):").pack(side=tk.LEFT)
        self.cat_freq_entry = ttk.Entry(freq_entry_row, width=11)
        self.cat_freq_entry.insert(0, self.rig_freq)
        self.cat_freq_entry.pack(side=tk.LEFT, padx=(4, 6))
        self.attach_context_menu(self.cat_freq_entry)
        self.cat_freq_entry.bind("<Return>", lambda e: self.tune_vfo_direct())

        self.btn_tune_cat = ttk.Button(freq_entry_row, text="Tune Rig", command=self.tune_vfo_direct)
        self.btn_tune_cat.pack(side=tk.RIGHT)

        preset_row = ttk.Frame(self.vfo_frame)
        preset_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(preset_row, text="Presets:").pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(preset_row, text="7103.2", command=lambda: self.set_preset_frequency("7103.20")).pack(side=tk.LEFT, padx=1)
        ttk.Button(preset_row, text="3596.0", command=lambda: self.set_preset_frequency("3596.00")).pack(side=tk.LEFT, padx=1)
        ttk.Button(preset_row, text="14106.5", command=lambda: self.set_preset_frequency("14106.50")).pack(side=tk.LEFT, padx=1)

        self.cat_status_lbl = ttk.Label(self.vfo_frame, text="CAT: Standby", font=("Arial", 8, "italic"), foreground="#0284c7")
        self.cat_status_lbl.pack(anchor=tk.W, pady=(4, 0))

        # Node & BBS Commands Grid
        self.node_group = ttk.LabelFrame(self.scrollable_left, text="Node & BBS Commands", padding=6)
        self.node_group.pack(fill=tk.X, pady=(0, 6))

        self.node_group.columnconfigure(0, weight=1)
        self.node_group.columnconfigure(1, weight=1)
        self.node_group.columnconfigure(2, weight=1)

        grid_commands = [
            ("Nodes (N)", "N", 0, 0),
            ("Routes (R)", "R", 1, 0),
            ("Links (L)", "L", 2, 0),
            ("Stats (S)", "S", 3, 0),
            ("Users (U)", "U", 0, 1),
            ("Chat (CHAT)", "CHAT", 1, 1),
            ("BBS (BBS)", "BBS", 2, 1),
            ("Leave (B)", "B", 3, 1),
            ("List (L)", "L", 0, 2),
            ("List Mine (LM)", "LM", 1, 2),
            ("Read Mine (RM)", "RM", 2, 2),
            ("Kill Mine (KM)", "KM", 3, 2)
        ]

        for label_text, cmd_text, r, c in grid_commands:
            btn = ttk.Button(self.node_group, text=label_text, command=lambda cmd=cmd_text: self.send_node_command(cmd))
            btn.grid(row=r, column=c, padx=2, pady=2, sticky=tk.EW)

        # Configuration & Utilities Panel
        panel_group = ttk.LabelFrame(self.scrollable_left, text="Station Controls & Utilities", padding=6)
        panel_group.pack(fill=tk.X, pady=(0, 6))

        mode_radio_row = ttk.Frame(panel_group)
        mode_radio_row.pack(fill=tk.X, pady=(1, 4))
        ttk.Label(mode_radio_row, text="Modem:", font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        self.op_mode_var = tk.StringVar(value=self.current_mode)
        rb_hf = ttk.Radiobutton(mode_radio_row, text="HF", variable=self.op_mode_var, value="HF", command=self._on_mode_radio_select)
        rb_hf.pack(side=tk.LEFT, padx=3)
        rb_fm = ttk.Radiobutton(mode_radio_row, text="FM", variable=self.op_mode_var, value="FM", command=self._on_mode_radio_select)
        rb_fm.pack(side=tk.LEFT, padx=3)

        ttk.Separator(panel_group, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        ttk.Label(panel_group, text="Windows & Tools:", font=("Arial", 8, "bold")).pack(anchor=tk.W, pady=(0, 3))
        self.control_action_var = tk.StringVar(value="")
        action_grid = ttk.Frame(panel_group)
        action_grid.pack(fill=tk.X, pady=(0, 4))
        action_grid.columnconfigure(0, weight=1)
        action_grid.columnconfigure(1, weight=1)

        tool_options = [
            ("Sta Setup", "STA", 0, 0),
            ("Cat Setup", "CAT", 0, 1),
            ("HTML Forms", "HTML", 1, 0),
            ("Meters & Tune", "METERS", 1, 1),
            ("Quick Reference", "QREF", 2, 0)
        ]

        for lbl, val, r, c in tool_options:
            rb = ttk.Radiobutton(
                action_grid,
                text=lbl,
                variable=self.control_action_var,
                value=val,
                command=self._on_control_action_select
            )
            rb.grid(row=r, column=c, sticky=tk.W, padx=2, pady=2)

        ttk.Separator(panel_group, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        theme_row = ttk.Frame(panel_group)
        theme_row.pack(fill=tk.X, pady=(1, 2))
        ttk.Label(theme_row, text="Theme:", font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        self.theme_radio_var = tk.StringVar(value=self.theme_mode)
        rb_dark = ttk.Radiobutton(theme_row, text="Dark", variable=self.theme_radio_var, value="dark", command=self._on_theme_radio_select)
        rb_dark.pack(side=tk.LEFT, padx=3)
        rb_light = ttk.Radiobutton(theme_row, text="Light", variable=self.theme_radio_var, value="light", command=self._on_theme_radio_select)
        rb_light.pack(side=tk.LEFT, padx=3)

        # Right Operational Panel
        right_paned = ttk.PanedWindow(body_container, orient=tk.VERTICAL)
        right_paned.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        msg_list_frame = ttk.LabelFrame(right_paned, text="Received Messages", padding=4)
        right_paned.add(msg_list_frame, weight=1)

        list_toolbar = ttk.Frame(msg_list_frame)
        list_toolbar.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))
        self.btn_del_msg = ttk.Button(list_toolbar, text="[-] Delete Message", command=self.delete_selected_message)
        self.btn_del_msg.pack(side=tk.LEFT)

        table_container = ttk.Frame(msg_list_frame)
        table_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.table_v_scroll = ttk.Scrollbar(table_container, orient=tk.VERTICAL)
        self.table_v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        cols = ("msg_num", "from_to", "subject", "date")
        self.msg_table = ttk.Treeview(
            table_container, columns=cols, show="headings",
            selectmode="browse", yscrollcommand=self.table_v_scroll.set
        )
        self.table_v_scroll.config(command=self.msg_table.yview)

        self.msg_table.heading("msg_num", text="#")
        self.msg_table.heading("from_to", text="From / To")
        self.msg_table.heading("subject", text="Subject")
        self.msg_table.heading("date", text="Date / Status")

        self.msg_table.column("msg_num", width=70, minwidth=50, anchor=tk.CENTER)
        self.msg_table.column("from_to", width=180, minwidth=140)
        self.msg_table.column("subject", width=380, minwidth=200)
        self.msg_table.column("date", width=130, minwidth=100, anchor=tk.CENTER)

        self.msg_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def _on_tree_mousewheel(event):
            if event.num == 5 or event.delta < 0:
                self.msg_table.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:
                self.msg_table.yview_scroll(-1, "units")
            return "break"

        self.msg_table.bind("<MouseWheel>", _on_tree_mousewheel)
        self.msg_table.bind("<Button-4>", _on_tree_mousewheel)
        self.msg_table.bind("<Button-5>", _on_tree_mousewheel)

        self.msg_table.bind("<<TreeviewSelect>>", self._on_msg_select)
        self.msg_table.bind("<Double-1>", self._on_msg_double_click)
        self.msg_table.bind("<Delete>", lambda e: self.delete_selected_message())

        term_frame = ttk.LabelFrame(right_paned, text="Live BBS Terminal & Traffic Monitor", padding=4)
        right_paned.add(term_frame, weight=2)

        input_bar = ttk.Frame(term_frame)
        input_bar.pack(side=tk.TOP, fill=tk.X, padx=2, pady=(2, 4))

        ttk.Label(input_bar, text="Type-Ahead:").pack(side=tk.LEFT, padx=(0, 4))
        self.cmd_entry = ttk.Entry(input_bar)
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.cmd_entry.bind("<Return>", lambda event: self.send_manual_command())
        self.attach_context_menu(self.cmd_entry)

        self.btn_send_cmd = ttk.Button(input_bar, text="Send Enter", width=10, command=self.send_manual_command)
        self.btn_send_cmd.pack(side=tk.RIGHT)

        self.term_view = scrolledtext.ScrolledText(
            term_frame, wrap=tk.WORD, bg="#0f141c", fg="#22c55e",
            insertbackground="#22c55e", font=("Consolas", 10)
        )
        self.term_view.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))
        self.attach_context_menu(self.term_view)
        
        self.term_view.bind("<Double-Button-1>", self._on_term_double_click)
        self.term_print("[*] Workstation ready. Live DCD and CAT engine active.\n")

    def _on_term_double_click(self, event):
        index = self.term_view.index(f"@{event.x},{event.y}")
        line_start = f"{index.split('.')[0]}.0"
        line_end = f"{index.split('.')[0]}.end"
        line_text = self.term_view.get(line_start, line_end).strip()

        m = re.match(r"^(\d{1,7})\b", line_text)
        if not m:
            word = self.term_view.get(f"{index} wordstart", f"{index} wordend").strip()
            if word.isdigit() and len(word) >= 2:
                m = re.match(r"^(\d{1,7})$", word)

        if m:
            msg_num = m.group(1)
            local_msg = next((msg for msg in self.inbox_msgs if str(msg.get("id")) == str(msg_num)), None)

            if local_msg:
                self.term_print(f"\n[*] Displaying cached message #{msg_num} from Inbox:\n")
                header = f"\n{'='*55}\nFrom:    {local_msg.get('from', 'BBS')}\nTo:      {local_msg.get('to', self.current_call)}\nSubject: {local_msg.get('subj', '')}\nDate:    {local_msg.get('date', '')}\n{'-'*55}\n"
                self.term_print(header + local_msg.get("body", "") + f"\n{'='*55}\n")
            else:
                if self.worker_thread and self.worker_thread.is_alive() and self.data_sock:
                    self.term_print(f"\n[*] Fetching message #{msg_num} from remote BBS...\n")
                    self.tx_manual_queue.put(f"R {msg_num}")
                else:
                    self.term_print(f"\n[!] Cannot fetch #{msg_num}: Not connected to BBS.\n")
            return "break"

    def _refresh_bbs_dropdown(self):
        active_contacts = self._get_active_contacts()
        bbs_names = [c["bbs"] for c in active_contacts]
        self.bbs_combo["values"] = bbs_names

        if bbs_names:
            first_c = active_contacts[0]
            self.bbs_combo.set(first_c["bbs"])
            self.digi_entry.delete(0, tk.END)
            self.digi_entry.insert(0, first_c.get("digi", ""))
        else:
            self.bbs_combo.set("")
            self.digi_entry.delete(0, tk.END)

    def _on_mode_change(self):
        restart_listener = self.listener_active
        if restart_listener:
            self._stop_listener_service()

        if self.current_mode == "HF":
            self.current_cmd_port = "8358"
            self.current_data_port = "8359"
            self.current_bw = "BW500"
            if hasattr(self, "vfo_frame") and hasattr(self, "node_group"):
                self.vfo_frame.pack(fill=tk.X, pady=(0, 6), before=self.node_group)
            self.term_print(f"[*] Switched to VARA HF (Ports 8358/8359, BW500).\n")
        else:
            self.current_cmd_port = "8300"
            self.current_data_port = "8301"
            self.current_bw = "NARROW"
            if hasattr(self, "vfo_frame"):
                self.vfo_frame.pack_forget()
            self.term_print(f"[*] Switched to VARA FM (Ports 8300/8301, NARROW).\n")

        self._refresh_bbs_dropdown()
        if restart_listener:
            self._start_listener_service()

    def _on_bbs_selected(self, event=None):
        selected_bbs = self.bbs_combo.get().strip().upper()
        active_contacts = self._get_active_contacts()
        for contact in active_contacts:
            if contact["bbs"] == selected_bbs:
                self.digi_entry.delete(0, tk.END)
                self.digi_entry.insert(0, contact.get("digi", ""))
                break

    def _tune_hamlib(self, freq_khz, mode_str="PKTUSB", filter_num=1):
        ok, msg = self.cat.set_frequency(freq_khz)
        self.cat.set_mode_and_filter(mode_str, filter_num)
        if ok:
            self.term_print(f"[*] Hamlib CAT: {msg}\n")
        else:
            self.term_print(f"[!] Hamlib CAT warning: {msg}\n")

    def add_bbs_station(self):
        new_bbs = self.bbs_combo.get().strip().upper()
        digi = self.digi_entry.get().strip().upper()
        mode = self.current_mode
        default_dwell = self.hf_dwell if mode == "HF" else self.fm_dwell

        if not new_bbs:
            messagebox.showwarning("Warning", "Enter a callsign in the Target BBS box.")
            return

        active_contacts = self._get_active_contacts()
        updated = False
        for contact in active_contacts:
            if contact["bbs"] == new_bbs:
                contact["digi"] = digi
                updated = True
                break

        if not updated:
            active_contacts.append({
                "bbs": new_bbs,
                "digi": digi,
                "dwell": default_dwell
            })

        self.bbs_combo["values"] = [c["bbs"] for c in active_contacts]
        self.bbs_combo.set(new_bbs)
        self._save_data()

        digi_info = f" via {digi}" if digi else ""
        self.term_print(f"[*] Saved {new_bbs}{digi_info} to {mode} contacts list.\n")

    def delete_bbs_station(self):
        selected_bbs = self.bbs_combo.get().strip().upper()
        mode = self.current_mode
        active_contacts = self._get_active_contacts()

        match = None
        for contact in active_contacts:
            if contact["bbs"] == selected_bbs:
                match = contact
                break

        if match:
            active_contacts.remove(match)
            self._save_data()
            self._refresh_bbs_dropdown()
            self.term_print(f"[*] Removed {selected_bbs} from {mode} contacts list.\n")
        else:
            messagebox.showwarning("Warning", "Selected BBS not found in current list.")

    def term_print(self, text):
        def _append():
            clean_text = text.replace("\r\n", "\n").replace("\r", "\n")
            self.term_view.insert(tk.END, clean_text)
            self.term_view.see(tk.END)

        if threading.current_thread() is threading.main_thread():
            _append()
        else:
            self.after(0, _append)

    def send_manual_command(self):
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return

        self.cmd_entry.delete(0, tk.END)
        self.term_print(f">>> {cmd}\n")

        if self.worker_thread and self.worker_thread.is_alive() and self.data_sock:
            self.tx_manual_queue.put(cmd)
        elif self.mailbox_in_session and self.listener_data_sock:
            self._send_listener_data(f"\n[SYSOP]: {cmd}\r\n")
        else:
            self.term_print("[!] Not connected to BBS or Caller. Command not sent.\n")

    def send_node_command(self, cmd):
        self.term_print(f">>> {cmd}\n")
        if self.worker_thread and self.worker_thread.is_alive() and self.data_sock:
            self.tx_manual_queue.put(cmd)
        else:
            self.term_print("[!] Not connected to Node/BBS. Connect first to run this command.\n")

    def _update_folder_counts(self):
        self.folder_tree.item(self.f_inbox, text=f"Inbox ({len(self.inbox_msgs)})")
        self.folder_tree.item(self.f_drafts, text=f"Drafts ({len(self.draft_msgs)})")
        self.folder_tree.item(self.f_outbox, text=f"Outbox ({len(self.outbox_msgs)})")
        self.folder_tree.item(self.f_sent, text=f"Sent ({len(self.sent_msgs)})")
        self.folder_tree.item(self.f_trash, text=f"Trash ({len(self.trash_msgs)})")

    def _get_active_store(self):
        selected = self.folder_tree.selection()
        if not selected:
            return "inbox", self.inbox_msgs
        tag = self.folder_tree.item(selected[0], "values")[0]
        stores = {
            "inbox": self.inbox_msgs,
            "drafts": self.draft_msgs,
            "outbox": self.outbox_msgs,
            "sent": self.sent_msgs,
            "trash": self.trash_msgs
        }
        return tag, stores.get(tag, self.inbox_msgs)

    def _on_folder_select(self, event):
        tag, store = self._get_active_store()
        my_call = self.current_call

        for item in self.msg_table.get_children():
            self.msg_table.delete(item)

        for i, msg in enumerate(store):
            if tag == "inbox":
                status = msg.get("date", "")
                m_from = msg.get("from", "BBS")
                m_to = msg.get("to", my_call)
                from_to = f"{m_from} -> {m_to}"
                num_col = msg.get("id", str(i+1))
            elif tag == "drafts":
                status = "Draft"
                from_to = f"{msg.get('type', 'SP')}: {msg.get('to', '(No Recipient)')}"
                num_col = f"D-{i+1}"
            elif tag == "outbox":
                status = "Queued"
                from_to = f"{msg.get('type', 'SP')}: {msg.get('to', '')}"
                num_col = "OUT"
            elif tag == "sent":
                status = msg.get("date", "Sent")
                from_to = f"{msg.get('type', 'SP')}: {msg.get('to', '')}"
                num_col = f"S-{i+1}"
            else:
                status = "Deleted"
                m_from = msg.get("from", "")
                m_to = msg.get("to", "")
                from_to = f"{m_from} -> {m_to}" if m_from and m_to else (m_from or m_to)
                num_col = "DEL"

            self.msg_table.insert("", "end", iid=str(i), values=(num_col, from_to, msg.get("subj", ""), status))

    def _on_msg_select(self, event):
        selected = self.msg_table.selection()
        if not selected:
            return
        idx = int(selected[0])
        tag, store = self._get_active_store()

        if idx < len(store):
            msg = store[idx]
            my_call = self.current_call
            m_type = msg.get('type', 'SP')
            m_from = msg.get('from', my_call)
            m_to = msg.get('to', my_call if tag == 'inbox' else '')
            header = f"\n{'='*55}\nType:    {m_type}\nFrom:    {m_from}\nTo:      {m_to}\nSubject: {msg.get('subj', '')}\nDate:    {msg.get('date', '')}\n{'-'*55}\n"
            self.term_print(header + msg.get("body", "") + f"\n{'='*55}\n")

    def _on_msg_double_click(self, event):
        tag, store = self._get_active_store()
        selected = self.msg_table.selection()
        if not selected:
            return
        idx = int(selected[0])
        if tag == "drafts" and idx < len(store):
            draft = store.pop(idx)
            self._save_data()
            self._update_folder_counts()
            self._on_folder_select(None)
            self.open_composer(
                pre_to=draft.get("to", ""),
                pre_subj=draft.get("subj", ""),
                pre_body=draft.get("body", ""),
                pre_type=draft.get("type", "SP")
            )

    def delete_selected_message(self):
        selected = self.msg_table.selection()
        if not selected:
            messagebox.showinfo("Select Message", "Please select a message to delete.")
            return

        idx = int(selected[0])
        tag, store = self._get_active_store()

        if idx < len(store):
            msg = store.pop(idx)
            if tag != "trash":
                self.trash_msgs.append(msg)
                self.term_print(f"[*] Moved message to Trash.\n")
            else:
                self.term_print(f"[*] Permanently deleted message from Trash.\n")

            self._save_data()
            self._update_folder_counts()
            self._on_folder_select(None)

    def update_status(self, text, color="black"):
        self.status_lbl.config(text=text, foreground=color)

    # ==========================================
    # COMPOSER
    # ==========================================
    def open_composer(self, pre_to="", pre_subj="", pre_body=None, pre_type="SP"):
        win = tk.Toplevel(self)
        win.title("Compose Message")
        win.geometry("640x580")

        is_dark = (self.theme_mode == "dark")
        win_bg = "#161922" if is_dark else "#f3f4f6"
        win_card = "#1f2430" if is_dark else "#ffffff"
        win_fg = "#e5e7eb" if is_dark else "#111827"
        border_col = "#374151" if is_dark else "#d1d5db"
        win.configure(bg=win_bg)

        f = ttk.Frame(win, padding=12)
        f.pack(fill=tk.BOTH, expand=True)

        type_row = ttk.Frame(f)
        type_row.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 6))

        ttk.Label(type_row, text="Message Type:").pack(side=tk.LEFT, padx=(0, 8))
        msg_type_var = tk.StringVar(value=pre_type)

        rb_sp = ttk.Radiobutton(type_row, text="SP (Private)", variable=msg_type_var, value="SP")
        rb_sp.pack(side=tk.LEFT, padx=6)

        rb_sb = ttk.Radiobutton(type_row, text="SB (Bulletin)", variable=msg_type_var, value="SB")
        rb_sb.pack(side=tk.LEFT, padx=6)

        to_label = ttk.Label(f, text="To Callsign:")
        to_label.grid(row=1, column=0, sticky=tk.W, pady=4)

        to_row = ttk.Frame(f)
        to_row.grid(row=1, column=1, sticky=tk.EW, pady=4)

        to_combo = ttk.Combobox(to_row, width=24, values=self.recent_recipients)
        to_combo.set(pre_to)
        to_combo.pack(side=tk.LEFT, padx=(0, 6))
        self.attach_context_menu(to_combo)

        def add_to_history():
            entry_val = to_combo.get().strip().upper()
            if not entry_val:
                return
            if entry_val not in self.recent_recipients:
                self.recent_recipients.insert(0, entry_val)
                self.recent_recipients = self.recent_recipients[:30]
                to_combo["values"] = self.recent_recipients
                self._save_data()
            to_combo.set(entry_val)

        def del_from_history():
            entry_val = to_combo.get().strip().upper()
            if entry_val in self.recent_recipients:
                self.recent_recipients.remove(entry_val)
                to_combo["values"] = self.recent_recipients
                to_combo.set("")
                self._save_data()

        btn_add_to = ttk.Button(to_row, text="[+] Add", width=8, command=add_to_history)
        btn_add_to.pack(side=tk.LEFT, padx=2)

        btn_del_to = ttk.Button(to_row, text="[-] Del", width=8, command=del_from_history)
        btn_del_to.pack(side=tk.LEFT, padx=2)

        def _on_type_changed(*args):
            if msg_type_var.get() == "SB":
                to_label.config(text="Bulletin @ Route:")
            else:
                to_label.config(text="To Callsign:")

        msg_type_var.trace_add("write", _on_type_changed)
        _on_type_changed()

        ttk.Label(f, text="Subject:").grid(row=2, column=0, sticky=tk.W, pady=4)
        subj_entry = ttk.Entry(f, width=48)
        subj_entry.insert(0, pre_subj)
        subj_entry.grid(row=2, column=1, sticky=tk.W, pady=4)
        self.attach_context_menu(subj_entry)

        ttk.Label(f, text="Body:").grid(row=3, column=0, sticky=tk.NW, pady=4)
        body_text = scrolledtext.ScrolledText(
            f, width=48, height=14, font=("Courier", 10),
            bg=win_card, fg=win_fg, insertbackground=win_fg, highlightbackground=border_col
        )
        body_text.grid(row=3, column=1, sticky=tk.NSEW, pady=4)
        f.grid_rowconfigure(3, weight=1)
        f.grid_columnconfigure(1, weight=1)
        self.attach_context_menu(body_text)

        if pre_body is not None:
            body_text.insert("1.0", pre_body)
        else:
            if self.current_signature:
                body_text.insert("1.0", f"\n\n{self.current_signature}")
            body_text.mark_set("insert", "1.0")

        btn_row = ttk.Frame(f)
        btn_row.grid(row=4, column=1, sticky=tk.E, pady=10)

        def _remember_recipient(addr):
            clean_addr = addr.strip().upper()
            if clean_addr and clean_addr not in self.recent_recipients:
                self.recent_recipients.insert(0, clean_addr)
                self.recent_recipients = self.recent_recipients[:30]
                to_combo["values"] = self.recent_recipients

        def save_draft():
            dest = to_combo.get().strip().upper()
            subj = subj_entry.get().strip()
            body = body_text.get("1.0", tk.END).strip()
            m_type = msg_type_var.get()

            _remember_recipient(dest)
            self.draft_msgs.append({"type": m_type, "to": dest, "subj": subj, "body": body})
            self._save_data()
            self._update_folder_counts()
            self._on_folder_select(None)
            self.term_print(f"[*] Saved {m_type} message draft.\n")
            win.destroy()

        def deposit_to_pbbs():
            dest = to_combo.get().strip().upper()
            subj = subj_entry.get().strip()
            body = body_text.get("1.0", tk.END).strip()
            m_type = msg_type_var.get()
            if not dest or not subj:
                messagebox.showerror("Error", "Recipient Callsign and Subject required.", parent=win)
                return

            _remember_recipient(dest)
            next_id = str(len(self.inbox_msgs) + 1)
            my_call = self.current_call

            if self.current_signature and self.current_signature.splitlines()[0] not in body:
                body = f"{body}\n\n{self.current_signature}"

            self.inbox_msgs.append({
                "id": next_id, "from": my_call, "to": dest,
                "subj": subj, "date": time.strftime("%m/%d %H:%M"),
                "body": body, "type": m_type
            })
            self._save_data()
            self._update_folder_counts()
            self._on_folder_select(None)
            self.term_print(f"[+] Deposited message #{next_id} for {dest} into local PBBS.\n")
            win.destroy()

        def queue_outbound():
            dest = to_combo.get().strip().upper()
            subj = subj_entry.get().strip()
            body = body_text.get("1.0", tk.END).strip()
            m_type = msg_type_var.get()
            if not dest or not subj:
                messagebox.showerror("Error", "Callsign and Subject required to send.", parent=win)
                return

            _remember_recipient(dest)
            self.outbox_msgs.append({"type": m_type, "to": dest, "subj": subj, "body": body})
            self._save_data()
            self._update_folder_counts()
            self._on_folder_select(None)
            self.term_print(f"[*] Queued outbound {m_type} message for {dest} to Outbox.\n")
            win.destroy()

        ttk.Button(btn_row, text="Save as Draft", command=save_draft).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_row, text="Deposit to PBBS", command=deposit_to_pbbs).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_row, text="Queue to Outbox (Remote BBS)", command=queue_outbound).pack(side=tk.LEFT, padx=3)

    # ==========================================
    # SESSION LAUNCHERS
    # ==========================================
    def _prepare_session(self):
        if self.mailbox_in_session:
            messagebox.showwarning("Busy", "A caller is currently connected to your Mailbox.")
            return None

        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Busy", "A connection session is already active.")
            return None

        if self.listener_active:
            self._stop_listener_service()

        target_bbs = self.bbs_combo.get().strip().upper()
        if not target_bbs:
            messagebox.showerror("Error", "Please select or enter a Target BBS.")
            return None

        raw_digi = self.digi_entry.get().strip().upper()
        my_call = self.current_call
        host = self.current_host
        bw = self.current_bw
        signature = self.current_signature
        mode = self.current_mode

        try:
            cmd_port = int(self.current_cmd_port)
            data_port = int(self.current_data_port)
        except ValueError:
            messagebox.showerror("Error", "Command and Data ports must be numbers.")
            return None

        try:
            dwell_val = float(self.hf_dwell if mode == "HF" else self.fm_dwell)
            if dwell_val < 0:
                dwell_val = 1.5
        except ValueError:
            dwell_val = 20.0 if mode == "HF" else 1.5

        active_contacts = self._get_active_contacts()
        updated = False
        for contact in active_contacts:
            if contact["bbs"] == target_bbs:
                contact["digi"] = raw_digi
                updated = True
                break

        if not updated:
            active_contacts.append({
                "bbs": target_bbs,
                "digi": raw_digi,
                "dwell": str(dwell_val)
            })
            self.bbs_combo["values"] = [c["bbs"] for c in active_contacts]

        self._save_data()

        if mode == "HF" and self.cat.enabled:
            target_freq = self.cat_freq_entry.get().strip() if hasattr(self, "cat_freq_entry") else self.rig_freq
            target_filter = self.radio_filter_var.get() if hasattr(self, "radio_filter_var") else 1
            threading.Thread(target=lambda: self._tune_hamlib(target_freq, "PKTUSB", target_filter), daemon=True).start()

        self.title(f"VARA HF/FM Mail & Terminal Client - [{my_call}]")
        self.abort_requested = False
        while not self.tx_manual_queue.empty():
            self.tx_manual_queue.get_nowait()

        self.btn_send_rcv.config(state=tk.DISABLED)
        self.btn_manual_conn.config(state=tk.DISABLED)
        self.btn_disconnect.config(state=tk.NORMAL)
        self.btn_listen.config(state=tk.DISABLED)

        return host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call, signature, mode, dwell_val

    def start_auto_session(self):
        params = self._prepare_session()
        if not params:
            return
        self.worker_thread = threading.Thread(target=self._run_auto_session, args=params, daemon=True)
        self.worker_thread.start()

    def start_manual_session(self):
        params = self._prepare_session()
        if not params:
            return
        self.worker_thread = threading.Thread(target=self._run_manual_session, args=params[:-1], daemon=True)
        self.worker_thread.start()

    # ==========================================
    # VARA NETWORKING & TRANSMIT ENGINE
    # ==========================================
    def _connect_rf(self, host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call):
        self.update_status(f"Connecting ({host})...", "orange")
        self.term_print(f"[*] Opening sockets to {host} (Cmd:{cmd_port}, Data:{data_port})...\n")

        self.cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.cmd_sock.settimeout(5.0)
        self.cmd_sock.connect((host, cmd_port))

        self.data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.data_sock.settimeout(5.0)
        self.data_sock.connect((host, data_port))

        self.cmd_sock.sendall(f"MYCALL {my_call}\r".encode("ascii"))
        time.sleep(0.1)
        self.cmd_sock.sendall(f"{bw}\r".encode("ascii"))
        time.sleep(0.1)

        self.set_modem_led("pwr", True)

        if self.abort_requested:
            return False

        clean_digi = re.sub(r'^(VIA|V)\s+', '', raw_digi.strip(), flags=re.IGNORECASE)

        if clean_digi:
            conn_cmd = f"CONNECT {my_call} {target_bbs} VIA {clean_digi}\r"
            disp_call = f"{target_bbs} via {clean_digi}"
        else:
            conn_cmd = f"CONNECT {my_call} {target_bbs}\r"
            disp_call = target_bbs

        self.update_status(f"Calling {disp_call}...", "blue")
        self.term_print(f"[*] Issuing RF command: {conn_cmd.strip()} ({bw})...\n")
        self.cmd_sock.sendall(conn_cmd.encode("ascii"))

        threading.Thread(target=self._monitor_vara_cmd_telemetry, daemon=True).start()

        connected = False
        start_t = time.time()
        self.cmd_sock.settimeout(1.0)

        while time.time() - start_t < 60:
            if self.abort_requested:
                return False
            try:
                resp = self.cmd_sock.recv(1024).decode("latin-1", errors="ignore")
                if "CONNECTED" in resp and "DISCONNECTED" not in resp:
                    connected = True
                    self.set_modem_led("conn", True)
                    break
                elif "DISCONNECTED" in resp:
                    break
            except socket.timeout:
                pass

        if not connected or self.abort_requested:
            self.set_modem_led("conn", False)
            self.update_status("Disconnected / Timeout", "red")
            self.term_print("[!] Connection failed or timed out.\n")
            return False

        self.update_status(f"Connected to {target_bbs}", "green")
        self.term_print(f"[+] RF Link established with {target_bbs}!\n\n")
        return True

    def _monitor_vara_cmd_telemetry(self):
        while self.cmd_sock and not self.abort_requested:
            try:
                self.cmd_sock.settimeout(0.4)
                line = self.cmd_sock.recv(512).decode("latin-1", errors="ignore")
                if not line:
                    break

                if "PTT ON" in line:
                    self.cat.set_ptt(True)
                    self.after(0, lambda: self.set_modem_led("tx", True))
                elif "PTT OFF" in line:
                    self.cat.set_ptt(False)
                    self.after(0, lambda: self.set_modem_led("tx", False))

                if "BUSY ON" in line or "DCD ON" in line:
                    self.after(0, lambda: self.set_modem_led("dcd", True))
                elif "BUSY OFF" in line or "DCD OFF" in line:
                    self.after(0, lambda: self.set_modem_led("dcd", False))

                if "DISCONNECTED" in line:
                    self.after(0, lambda: self.set_modem_led("conn", False))

            except socket.timeout:
                pass
            except Exception:
                break
        self.cat.set_ptt(False)
        self.after(0, lambda: self.set_modem_led("tx", False))
        self.after(0, lambda: self.set_modem_led("conn", False))
        self.after(0, lambda: self.set_modem_led("dcd", False))

    def _create_inbox_messages_from_rm(self, raw_text):
        clean_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        clean_text = re.sub(r'\n[^\n]*[>?]\s*$', '', clean_text).strip()

        split_pattern = r'(?m)(?=^(?:Msg|Message)\s*#?\s*:?\s*\d+|^(?:From|F):\s*[A-Za-z0-9\-@/.]+)'
        raw_parts = re.split(split_pattern, clean_text)
        my_call = self.current_call

        created_count = 0
        for part in raw_parts:
            item_text = part.strip()
            if not item_text or len(item_text) < 15:
                continue

            item_text = re.sub(r'^[^\n]*[>:]\s*\n?', '', item_text).strip()

            id_m = re.search(r'(?:Msg|Message)\s*#?\s*:?\s*(\d+)', item_text, re.IGNORECASE)
            from_m = re.search(r'(?:From|F):\s*([A-Za-z0-9\-@/.]+)', item_text, re.IGNORECASE)
            to_m = re.search(r'(?:To|T):\s*([A-Za-z0-9\-@/.]+)', item_text, re.IGNORECASE)
            subj_m = re.search(r'(?:Subject|Subj):\s*(.*)', item_text, re.IGNORECASE)

            if not id_m and not from_m:
                continue

            assigned_id = id_m.group(1) if id_m else str(len(self.inbox_msgs) + 1)
            sender = from_m.group(1).strip() if from_m else "BBS"
            recipient = to_m.group(1).strip() if to_m else my_call
            subject = subj_m.group(1).strip() if subj_m else f"Message #{assigned_id}"
            msg_date = time.strftime("%m/%d %H:%M")

            if any(existing.get("id") == assigned_id and existing.get("from") == sender for existing in self.inbox_msgs):
                continue

            self.inbox_msgs.append({
                "id": assigned_id, "from": sender, "to": recipient,
                "subj": subject, "date": msg_date, "body": item_text
            })
            created_count += 1
            self.term_print(f"[+] Saved message #{assigned_id} from {sender} to {recipient} - '{subject}'\n")

        if created_count > 0:
            self._save_data()
            def _refresh():
                self._update_folder_counts()
                self._on_folder_select(None)
            self.after(0, _refresh)

        return created_count

    def _run_auto_session(self, host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call, signature, mode, dwell_val):
        try:
            if not self._connect_rf(host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call):
                return

            self._handle_auto_bbs_exchange(signature, mode, dwell_val)

            if not self.abort_requested:
                self.update_status("Disconnecting...", "orange")
                self._send_data("B\r")
                time.sleep(2.0)
                self.cmd_sock.sendall(b"DISCONNECT\r")
                self.update_status("Done / Idle", "gray")
                self.term_print("[*] Automated session complete. Disconnected.\n")

        except Exception as e:
            if not self.abort_requested:
                self.update_status("Error", "red")
                self.term_print(f"[!] Session Exception: {e}\n")
        finally:
            self._disconnect_vara()
            self._reset_ui_buttons()

    def _handle_auto_bbs_exchange(self, signature, mode, dwell_val):
        initial_timeout = 40.0 if mode == "HF" else 15.0
        banner = self._recv_data_until_prompt(timeout=initial_timeout, quiet_delay=1.5)
        if self.abort_requested:
            return

        if "command:" in banner.lower() or "}" in banner:
            self.term_print("[*] Connected to Node switch. Sending 'BBS' command...\n")
            self._send_data("BBS\r")
            node_timeout = 40.0 if mode == "HF" else 12.0
            self._recv_data_until_prompt(timeout=node_timeout, quiet_delay=1.5)
            if self.abort_requested:
                return

        self.term_print(f"[*] Dwell delay ({dwell_val}s) before command dispatch...\n")
        start_wait = time.time()
        while time.time() - start_wait < dwell_val:
            if self.abort_requested:
                return
            time.sleep(0.1)

        self.term_print(">>> RM\n")
        self._send_data("RM\r")

        rm_timeout = 40.0 if mode == "HF" else 25.0
        rm_resp = self._recv_data_until_prompt(timeout=rm_timeout, quiet_delay=1.5)
        if self.abort_requested:
            return

        if rm_resp and "no message" not in rm_resp.lower() and len(rm_resp.strip()) > 10:
            self._create_inbox_messages_from_rm(rm_resp)
        else:
            self.term_print("[*] No unread messages returned by RM.\n")

        while self.outbox_msgs and not self.abort_requested:
            msg = self.outbox_msgs.pop(0)
            cmd_prefix = msg.get("type", "SP").upper()

            start_w = time.time()
            while time.time() - start_w < dwell_val:
                if self.abort_requested:
                    break
                time.sleep(0.1)

            self.term_print(f">>> {cmd_prefix} {msg['to']}\n")
            self._send_data(f"{cmd_prefix} {msg['to']}\r")

            self._recv_data_until_prompt(timeout=40.0 if mode == "HF" else 15.0, quiet_delay=1.2)
            if self.abort_requested:
                break

            start_w = time.time()
            while time.time() - start_w < dwell_val:
                if self.abort_requested:
                    break
                time.sleep(0.1)

            self.term_print(f">>> {msg['subj']}\n")
            self._send_data(f"{msg['subj']}\r")

            self._recv_data_until_prompt(timeout=40.0 if mode == "HF" else 15.0, quiet_delay=1.2)
            if self.abort_requested:
                break

            start_w = time.time()
            while time.time() - start_w < dwell_val:
                if self.abort_requested:
                    break
                time.sleep(0.1)

            body_content = msg['body'].strip()
            if signature:
                sig_check = signature.splitlines()[0]
                if sig_check and sig_check not in body_content:
                    body_content = f"{body_content}\n\n{signature}"

            clean_body = body_content.replace("\r\n", "\r").replace("\n", "\r")
            payload = f"{clean_body}\r/EX\r"

            self.term_print(">>> [Sending Message Body + /EX]\n")
            self._send_data(payload)

            self._recv_data_until_prompt(timeout=40.0 if mode == "HF" else 20.0, quiet_delay=1.5)

            msg["date"] = time.strftime("%m/%d %H:%M")
            self.sent_msgs.append(msg)
            self.term_print(f"[+] Message successfully posted as {cmd_prefix} to {msg['to']}!\n")

        self._save_data()
        self.after(0, self._update_folder_counts)
        self.after(0, lambda: self._on_folder_select(None))

    def _run_manual_session(self, host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call, signature, mode):
        try:
            if not self._connect_rf(host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call):
                return

            self.term_print("[*] Terminal active. Type commands above, or use shortcuts on left.\n\n")
            self.data_sock.settimeout(0.3)
            self.cmd_sock.settimeout(0.3)

            while not self.abort_requested:
                while not self.tx_manual_queue.empty():
                    cmd = self.tx_manual_queue.get_nowait()
                    self._send_data(f"{cmd}\r")
                    if cmd.upper() in ["B", "BYE", "QUIT"]:
                        self.term_print("[*] Logoff recognized. Terminating link...\n")
                        time.sleep(2.0)
                        self.abort_requested = True
                        break

                if self.abort_requested:
                    break

                try:
                    chunk = self.data_sock.recv(2048).decode("latin-1", errors="ignore")
                    if chunk:
                        self.term_print(chunk)
                except socket.timeout:
                    pass
                except Exception:
                    break

                try:
                    cmd_resp = self.cmd_sock.recv(1024).decode("latin-1", errors="ignore")
                    if "DISCONNECTED" in cmd_resp:
                        self.term_print("\n[!] Remote BBS disconnected.\n")
                        break
                except socket.timeout:
                    pass
                except Exception:
                    break

            if self.cmd_sock:
                self.cmd_sock.sendall(b"DISCONNECT\r")
            self.update_status("Done / Idle", "gray")
            self.term_print("[*] Session terminated. Disconnected.\n")

        except Exception as e:
            if not self.abort_requested:
                self.update_status("Error", "red")
                self.term_print(f"[!] Session Exception: {e}\n")
        finally:
            self._disconnect_vara()
            self._reset_ui_buttons()

    # ==========================================
    # INCOMING MAILBOX & LISTENER
    # ==========================================
    def toggle_mailbox_listener(self):
        if self.listener_active:
            self._stop_listener_service()
            self.btn_listen.config(text="Mailbox Standby")
            self.update_status("Standby Disabled", "gray")
            self.term_print("[*] Mailbox listener disabled.\n")
        else:
            if self.worker_thread and self.worker_thread.is_alive():
                messagebox.showwarning("Busy", "Cannot enable Standby during active outbound session.")
                return
            self._start_listener_service()

    def _start_listener_service(self):
        self.listener_stop_event.clear()
        self.listener_thread = threading.Thread(target=self._run_mailbox_listener, daemon=True)
        self.listener_thread.start()
        self.listener_active = True
        self.btn_listen.config(text="Stop Standby")

    def _stop_listener_service(self):
        self.listener_active = False
        self.listener_stop_event.set()
        try:
            if self.listener_cmd_sock:
                self.listener_cmd_sock.sendall(b"LISTEN OFF\rDISCONNECT\r")
                time.sleep(0.1)
                self.listener_cmd_sock.close()
            if self.listener_data_sock:
                self.listener_data_sock.close()
        except Exception:
            pass
        self.listener_cmd_sock = None
        self.listener_data_sock = None
        self.mailbox_in_session = False
        self.btn_listen.config(text="Mailbox Standby")

    def _run_mailbox_listener(self):
        host = self.current_host
        my_call = self.current_call
        mode = self.current_mode
        bw = self.current_bw
        try:
            cmd_port = int(self.current_cmd_port)
            data_port = int(self.current_data_port)
        except ValueError:
            return

        self.update_status("Standby (Listening)", "green")
        self.term_print(f"[*] Starting Mailbox Listener on VARA {mode} ({host}:{cmd_port}) for {my_call}...\n")

        try:
            self.listener_cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listener_cmd_sock.settimeout(5.0)
            self.listener_cmd_sock.connect((host, cmd_port))

            self.listener_data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listener_data_sock.settimeout(5.0)
            self.listener_data_sock.connect((host, data_port))

            self.listener_cmd_sock.sendall(f"MYCALL {my_call}\r".encode("ascii"))
            time.sleep(0.1)
            self.listener_cmd_sock.sendall(f"{bw}\r".encode("ascii"))
            time.sleep(0.1)
            self.listener_cmd_sock.sendall(b"LISTEN ON\r")
            self.set_modem_led("pwr", True)
            self.term_print(f"[+] Modem configured. Personal Mailbox standing by for incoming connects...\n")
        except Exception as e:
            self.term_print(f"[!] Could not start Mailbox listener: {e}\n")
            self.after(0, self._stop_listener_service)
            return

        self.listener_cmd_sock.settimeout(0.3)
        self.listener_data_sock.settimeout(0.3)

        cmd_buf = ""
        while not self.listener_stop_event.is_set():
            try:
                cmd_data = self.listener_cmd_sock.recv(1024).decode("latin-1", errors="ignore")
                if cmd_data:
                    cmd_buf += cmd_data
                    while "\r" in cmd_buf:
                        line, cmd_buf = cmd_buf.split("\r", 1)
                        line = line.strip()
                        if line.startswith("CONNECTED"):
                            parts = line.split()
                            self.remote_call = parts[1].upper() if len(parts) > 1 else "CALLER"
                            self.mailbox_in_session = True
                            self.set_modem_led("conn", True)
                            self.update_status(f"Caller: {self.remote_call}", "blue")
                            self.term_print(f"\n[+] Incoming RF Connect from {self.remote_call}!\n")
                            self._send_mailbox_welcome(my_call, mode)
                        elif line.startswith("DISCONNECTED"):
                            if self.mailbox_in_session:
                                self.term_print(f"\n[*] {self.remote_call} disconnected from Mailbox.\n")
                                self.mailbox_in_session = False
                                self.remote_call = ""
                                self.mb_state = "CMD"
                                self.set_modem_led("conn", False)
                                self.update_status("Standby (Listening)", "green")
            except socket.timeout:
                pass
            except Exception:
                break

            if self.mailbox_in_session:
                try:
                    data_in = self.listener_data_sock.recv(2048).decode("latin-1", errors="ignore")
                    if data_in:
                        self.term_print(f"[{self.remote_call}] " + data_in)
                        self._process_mailbox_input(data_in, my_call)
                except socket.timeout:
                    pass
                except Exception:
                    break

        self.after(0, self._stop_listener_service)

    def _send_listener_data(self, txt):
        if self.listener_data_sock:
            try:
                self.listener_data_sock.sendall(txt.encode("latin-1"))
            except Exception:
                pass

    def _send_mailbox_welcome(self, my_call, mode):
        self.mb_state = "CMD"
        self.mb_line_buffer = ""
        
        caller_base = self.remote_call.split('-')[0].upper()
        matching_mail = [
            m for m in self.inbox_msgs 
            if str(m.get("to", "")).strip().upper() in (self.remote_call, caller_base)
        ]
        
        if matching_mail:
            mail_alert = (
                f"\r\n*** YOU HAVE {len(matching_mail)} MESSAGE(S) WAITING IN THIS MAILBOX ***\r\n"
                f"Type LM to list your messages or R <num> to read.\r\n"
            )
        else:
            mail_alert = "\r\nNo personal mail waiting for you.\r\n"

        welcome = (
            f"\r\nWelcome to {my_call} Personal Mailbox [VARA {mode}]\r\n"
            f"Current Station Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\r\n"
            f"{mail_alert}\r\n"
            f"Type ? or H for help.\r\n\r\n"
            f"{my_call} Mailbox > "
        )
        self._send_listener_data(welcome)

    def _process_mailbox_input(self, raw_data, my_call):
        self.mb_line_buffer += raw_data.replace("\n", "\r")
        while "\r" in self.mb_line_buffer:
            line, self.mb_line_buffer = self.mb_line_buffer.split("\r", 1)
            line = line.strip()
            if not line and self.mb_state == "CMD":
                self._send_listener_data(f"{my_call} Mailbox > ")
                continue
            self._handle_mailbox_line(line, my_call)

    def _handle_mailbox_line(self, line, my_call):
        prompt = f"{my_call} Mailbox > "

        if self.mb_state == "CMD":
            cmd = line.upper()
            
            if cmd in ("?", "H", "HELP"):
                help_text = (
                    "\r\n--- Mailbox Commands ---\r\n"
                    "L           - List all messages\r\n"
                    "LM          - List messages addressed to you\r\n"
                    "R <num>     - Read message by number\r\n"
                    "SP <call>   - Send a private message\r\n"
                    "SR <num>    - Send reply to a specific message\r\n"
                    "KM <num>    - Kill/delete your message\r\n"
                    "B, BYE, Q   - Disconnect\r\n\r\n"
                )
                self._send_listener_data(help_text + prompt)

            elif cmd == "L":
                resp = "\r\nMsg #   From       To         Date         Subject\r\n"
                resp += "-" * 55 + "\r\n"
                if not self.inbox_msgs:
                    resp += "(No messages in mailbox)\r\n"
                else:
                    for i, m in enumerate(self.inbox_msgs):
                        m_id = str(m.get("id", i + 1)).ljust(7)
                        m_from = str(m.get("from", "N/A"))[:9].ljust(10)
                        m_to = str(m.get("to", my_call))[:9].ljust(10)
                        m_date = str(m.get("date", ""))[:12].ljust(12)
                        m_subj = str(m.get("subj", "(No Subject)"))[:25]
                        resp += f"{m_id} {m_from} {m_to} {m_date} {m_subj}\r\n"
                self._send_listener_data(resp + "\r\n" + prompt)

            elif cmd == "LM":
                caller_base = self.remote_call.split('-')[0].upper()
                resp = f"\r\nMessages addressed to {self.remote_call}:\r\n"
                resp += "Msg #   From       Date         Subject\r\n"
                resp += "-" * 50 + "\r\n"
                matched = [
                    m for m in self.inbox_msgs 
                    if str(m.get("to", "")).strip().upper() in (self.remote_call, caller_base)
                ]
                if not matched:
                    resp += "(No messages for your callsign)\r\n"
                else:
                    for i, m in enumerate(matched):
                        m_id = str(m.get("id", i + 1)).ljust(7)
                        m_from = str(m.get("from", "N/A"))[:9].ljust(10)
                        m_date = str(m.get("date", ""))[:12].ljust(12)
                        m_subj = str(m.get("subj", "(No Subject)"))[:25]
                        resp += f"{m_id} {m_from} {m_date} {m_subj}\r\n"
                self._send_listener_data(resp + "\r\n" + prompt)

            elif cmd.startswith("R ") or (cmd.startswith("R") and len(cmd) > 1 and cmd[1:].isdigit()):
                num_str = cmd[2:].strip() if cmd.startswith("R ") else cmd[1:].strip()
                matched = next((m for m in self.inbox_msgs if str(m.get("id")) == num_str), None)
                if matched:
                    msg_body = (
                        f"\r\nMessage #{num_str}\r\n"
                        f"From:    {matched.get('from', 'N/A')}\r\n"
                        f"To:      {matched.get('to', my_call)}\r\n"
                        f"Date:    {matched.get('date', 'N/A')}\r\n"
                        f"Subject: {matched.get('subj', '')}\r\n"
                        f"{'-'*45}\r\n"
                        f"{matched.get('body', '')}\r\n"
                        f"{'-'*45}\r\n\r\n"
                    )
                    self._send_listener_data(msg_body + prompt)
                else:
                    self._send_listener_data(f"\r\nMessage #{num_str} not found.\r\n\r\n{prompt}")

            elif cmd.startswith("SR ") or (cmd.startswith("SR") and len(cmd) > 2 and cmd[2:].isdigit()):
                num_str = cmd[3:].strip() if cmd.startswith("SR ") else cmd[2:].strip()
                matched = next((m for m in self.inbox_msgs if str(m.get("id")) == num_str), None)
                if matched:
                    orig_from = matched.get("from", "").strip().upper()
                    dest_call = orig_from if orig_from and orig_from != "BBS" else my_call
                    orig_subj = matched.get("subj", "").strip()
                    reply_subj = orig_subj if orig_subj.upper().startswith("RE:") else f"RE: {orig_subj}"
                    
                    self.mb_rx_msg = {
                        "from": self.remote_call, "to": dest_call,
                        "subj": reply_subj, "body": "", "type": "SP"
                    }
                    self.mb_state = "SP_BODY"
                    self._send_listener_data(
                        f"\r\nReplying to Message #{num_str} (To: {dest_call})\r\n"
                        f"Subject: {reply_subj}\r\n"
                        f"Enter message text. End with /EX or Ctrl+Z on a new line:\r\n"
                    )
                else:
                    self._send_listener_data(f"\r\nMessage #{num_str} not found.\r\n\r\n{prompt}")

            elif cmd.startswith("SP ") or cmd.startswith("SB "):
                dest_call = cmd.split(maxsplit=1)[1].strip().upper()
                if not dest_call:
                    self._send_listener_data(f"\r\nError: Destination callsign required.\r\n{prompt}")
                    return
                self.mb_rx_msg = {
                    "from": self.remote_call, "to": dest_call,
                    "subj": "", "body": "", "type": "SP" if cmd.startswith("SP") else "SB"
                }
                self.mb_state = "SP_SUBJ"
                self._send_listener_data("Enter Subject: ")

            elif cmd.startswith("KM ") or (cmd.startswith("KM") and len(cmd) > 2 and cmd[2:].isdigit()):
                num_str = cmd[3:].strip() if cmd.startswith("KM ") else cmd[2:].strip()
                matched = next((m for m in self.inbox_msgs if str(m.get("id")) == num_str), None)
                if matched:
                    caller_base = self.remote_call.split('-')[0].upper()
                    m_from = str(matched.get("from", "")).strip().upper()
                    m_to = str(matched.get("to", "")).strip().upper()

                    if self.remote_call in (m_from, m_to) or caller_base in (m_from, m_to) or my_call in (m_from, m_to):
                        self.inbox_msgs.remove(matched)
                        self.trash_msgs.append(matched)
                        self._save_data()
                        self.after(0, self._update_folder_counts)
                        self.after(0, lambda: self._on_folder_select(None))
                        self._send_listener_data(f"\r\nMessage #{num_str} killed.\r\n\r\n{prompt}")
                    else:
                        self._send_listener_data(f"\r\nAccess Denied: Not addressed to or sent by {self.remote_call}.\r\n\r\n{prompt}")
                else:
                    self._send_listener_data(f"\r\nMessage #{num_str} not found.\r\n\r\n{prompt}")

            elif cmd in ("B", "BYE", "Q", "QUIT"):
                self._send_listener_data(f"\r\n73 de {my_call}. Disconnecting link...\r\n")
                time.sleep(1.0)
                try:
                    if self.listener_cmd_sock:
                        self.listener_cmd_sock.sendall(b"DISCONNECT\r")
                except Exception:
                    pass

            else:
                self._send_listener_data(f"\r\nUnknown command '{line}'. Type H or ? for help.\r\n\r\n{prompt}")

        elif self.mb_state == "SP_SUBJ":
            self.mb_rx_msg["subj"] = line if line else "No Subject"
            self.mb_state = "SP_BODY"
            self._send_listener_data("\r\nEnter message text. End with /EX or Ctrl+Z on a new line:\r\n")

        elif self.mb_state == "SP_BODY":
            if line.upper() in ("/EX", "\x1a", "EX"):
                next_id = str(len(self.inbox_msgs) + 1)
                self.mb_rx_msg["id"] = next_id
                self.mb_rx_msg["date"] = time.strftime("%m/%d %H:%M")
                self.inbox_msgs.append(dict(self.mb_rx_msg))
                self._save_data()
                
                self.after(0, self._update_folder_counts)
                self.after(0, lambda: self._on_folder_select(None))

                self.term_print(f"\n[+] Mailbox saved message #{next_id} from {self.remote_call} to {self.mb_rx_msg['to']}!\n")
                self._send_listener_data(f"\r\nMessage #{next_id} stored successfully.\r\n\r\n{prompt}")
                self.mb_state = "CMD"
                self.mb_rx_msg = {}
            else:
                if self.mb_rx_msg["body"]:
                    self.mb_rx_msg["body"] += "\n" + line
                else:
                    self.mb_rx_msg["body"] = line

    # ----------------------------------------------------
    # SOCKET & BUFFER UTILITIES
    # ----------------------------------------------------
    def _send_data(self, txt):
        if self.data_sock and not self.abort_requested:
            self.data_sock.sendall(txt.encode("latin-1"))

    def _recv_data_until_prompt(self, timeout=15.0, quiet_delay=1.5):
        buffer = ""
        start_t = time.time()
        last_rx_time = 0
        prompt_seen_time = None

        if self.data_sock:
            self.data_sock.settimeout(0.2)

        while time.time() - start_t < timeout:
            if self.abort_requested:
                break
            try:
                chunk = self.data_sock.recv(2048).decode("latin-1", errors="ignore")
                if chunk:
                    buffer += chunk
                    self.term_print(chunk)
                    last_rx_time = time.time()

                    tail = buffer.strip()
                    if tail.endswith(">") or tail.endswith("?") or tail.endswith(":") or tail.endswith("Command:"):
                        if prompt_seen_time is None:
                            prompt_seen_time = time.time()
                    else:
                        prompt_seen_time = None
            except socket.timeout:
                now = time.time()
                if prompt_seen_time and (now - last_rx_time >= quiet_delay):
                    break
                if buffer and (last_rx_time > 0) and (now - last_rx_time >= 2.5):
                    break
            except Exception:
                break

        return buffer

    def manual_disconnect(self):
        self.abort_requested = True
        self.update_status("Aborting...", "red")
        self.term_print("\n[!] Disconnect requested: Terminating link...\n")
        threading.Thread(target=self._force_disconnect, daemon=True).start()

    def _force_disconnect(self):
        try:
            if self.cmd_sock:
                try:
                    self.cmd_sock.sendall(b"ABORT\r")
                    time.sleep(0.1)
                    self.cmd_sock.sendall(b"DISCONNECT\r")
                except Exception:
                    pass

            if self.data_sock:
                try:
                    self.data_sock.sendall(b"B\r")
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self._disconnect_vara()

    def _disconnect_vara(self):
        try:
            if self.data_sock:
                self.data_sock.close()
                self.data_sock = None
            if self.cmd_sock:
                self.cmd_sock.close()
                self.cmd_sock = None
        except Exception:
            pass
        self.set_modem_led("conn", False)
        self.set_modem_led("tx", False)

    def _reset_ui_buttons(self):
        self.after(0, lambda: self.btn_send_rcv.config(state=tk.NORMAL))
        self.after(0, lambda: self.btn_manual_conn.config(state=tk.NORMAL))
        self.after(0, lambda: self.btn_disconnect.config(state=tk.DISABLED))
        self.after(0, lambda: self.btn_listen.config(state=tk.NORMAL))


if __name__ == "__main__":
    app = VaraBBSClient()
    app.mainloop()