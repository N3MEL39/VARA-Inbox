import sys
import os
import socket
import threading
import time
import re
import json
import queue
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "varabbs_data.json")

# ==========================================
# ZERO-DEPENDENCY SPELL CHECKER WITH USER DICTIONARY
# ==========================================
class SimpleSpellEngine:
    def __init__(self, user_words=None):
        self.words = set()
        self.user_words = set(w.lower() for w in (user_words or []))
        
        core_vocab = (
            "the of and a to in is you that it he was for on are as with his they I "
            "at be this have from or one had by word but not what all were we when "
            "your can said there use an each which she do how their if will up other "
            "about out many then them these so some her would make like him into time "
            "has look two more write go see number no way could people my than first "
            "water been call who oil its now find long down day did get come made may "
            "part over new sound take only little work know place year live me back give "
            "most very after thing our just name good sentence man think say great where "
            "help through much before line right too mean old any same tell boy follow "
            "came want show also around form three small set put end does another well "
            "large must big even such because turn here why ask went men read need land "
            "different home us move try kind hand picture again change off play spell air "
            "away animal house point page letter mother answer found study still learn "
            "should America world high every near add food between own below country plant "
            "last school father keep tree never start city earth eye light thought head under "
            "story saw left few along while might close something seem next hard open example "
            "begin life always those both paper together got group often run important until "
            "children side feet car mile night walk white sea began grow took river four carry "
            "state once book hear stop without second late miss idea enough eat face watch "
            "far real almost let above girl sometimes mountain cut young talk soon list song "
            "being leave family radio packet station antenna net traffic emergency weather "
            "message subject report checks check roster chief volunteer county status sitrep "
            "bulletin radiogram digipeater modem tactical rig frequencies"
        )
        for w in core_vocab.split():
            self.words.add(w.lower())

        for path in ["/usr/share/dict/words", "/usr/dict/words"]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            w = line.strip().lower()
                            if w.isalpha():
                                self.words.add(w)
                    break
                except Exception:
                    pass

    def add_word(self, word):
        w = word.strip().lower()
        if w:
            self.user_words.add(w)
            self.words.add(w)

    def is_correct(self, word):
        w = word.strip().lower()
        if not w or len(w) <= 1 or w.isdigit():
            return True
        if re.match(r'^[A-Z0-9]{1,3}\d[A-Z0-9]{1,4}(?:-\d{1,2})?$', word.upper()):
            return True
        if re.match(r'^[A-R]{2}\d{2}[A-X]{2}$', word.upper()):
            return True
        return (w in self.words) or (w in self.user_words)

    def suggest(self, word):
        w = word.lower()
        all_vocab = self.words.union(self.user_words)
        candidates = []
        for known in all_vocab:
            if abs(len(known) - len(w)) <= 1 and (known.startswith(w[:2]) if len(w) > 2 else True):
                diff = sum(1 for a, b in zip(w, known) if a != b) + abs(len(w) - len(known))
                if diff <= 2:
                    candidates.append((diff, known))
        candidates.sort(key=lambda x: x[0])
        return [c[1] for c in candidates[:4]]


class VaraBBSClient(tk.Tk):
    def __init__(self):
        super().__init__()

        # Station & Modem Fallback Defaults
        self.default_call = "Your Call Here"
        self.default_host = "127.0.0.1"
        self.default_mode = "FM"
        self.default_cmd_port = "8300"
        self.default_data_port = "8301"
        self.default_bw = "NARROW"
        self.default_signature = ""
        self.default_hf_dwell = "20.0"
        self.default_fm_dwell = "1.5"
        
        self.default_hf_contacts = [
            {"bbs": "N3MEL-2", "digi": ""},
            {"bbs": "N3MEL-7", "digi": ""}
        ]
        self.default_fm_contacts = [
            {"bbs": "N3MEL-2", "digi": ""},
            {"bbs": "N3MEL-7", "digi": ""}
        ]

        self.default_recipients = [
            "ALL@USA",
            "SPACWX@USA",
            "WX@ECBBS",
            "NEWS@WW"
        ]

        # Active Settings Variables
        self.current_call = self.default_call
        self.current_host = self.default_host
        self.current_mode = self.default_mode
        self.current_cmd_port = self.default_cmd_port
        self.current_data_port = self.default_data_port
        self.current_bw = self.default_bw
        self.current_signature = self.default_signature
        self.hf_dwell = self.default_hf_dwell
        self.fm_dwell = self.default_fm_dwell

        # Network State & Command Queue
        self.cmd_sock = None
        self.data_sock = None
        self.worker_thread = None
        self.abort_requested = False
        self.tx_manual_queue = queue.Queue()

        # Inbound Host Listener & Mailbox Engine State
        self.listener_active = False
        self.listener_thread = None
        self.listener_cmd_sock = None
        self.listener_data_sock = None
        self.listener_stop_event = threading.Event()
        self.mailbox_in_session = False
        self.remote_call = ""
        self.mb_state = "CMD"  # "CMD", "SP_SUBJ", "SP_BODY"
        self.mb_rx_msg = {}
        self.mb_line_buffer = ""

        # Load Persistent Storage
        self.saved_geometry = "1280x840"
        self.theme_mode = "light"
        self.user_dictionary = []
        self.hf_contacts = []
        self.fm_contacts = []
        self.recent_recipients = []
        self.inbox_msgs = []
        self.draft_msgs = []
        self.outbox_msgs = []
        self.sent_msgs = []
        self.trash_msgs = []
        self._load_data()

        self.spell = SimpleSpellEngine(user_words=self.user_dictionary)

        # Window Setup
        self.title(f"VARA HF/FM Mail & Terminal Client by N3MEL - [{self.current_call}]")
        self.geometry(self.saved_geometry)
        self.after(50, self._maximize_window)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.style = ttk.Style(self)
        self._build_ui()
        self._apply_theme()
        self._refresh_bbs_dropdown()
        self._update_folder_counts()
        self._on_folder_select(None)

    # ==========================================
    # PERSISTENT STORAGE HANDLERS (JSON)
    # ==========================================
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
                    self.theme_mode = store.get("theme_mode", "light")
                    self.recent_recipients = store.get("recent_recipients", list(self.default_recipients))
                    self.user_dictionary = store.get("user_dictionary", [])

                    self.current_call = store.get("my_call", self.default_call)
                    self.current_host = store.get("modem_host", self.default_host)
                    
                    loaded_mode = str(store.get("modem_mode", self.default_mode)).strip().upper()
                    if "HF" in loaded_mode:
                        self.current_mode = "HF"
                    else:
                        self.current_mode = "FM"

                    self.current_cmd_port = store.get("cmd_port", self.default_cmd_port)
                    self.current_data_port = store.get("data_port", self.default_data_port)
                    
                    if self.current_mode == "FM" and self.current_cmd_port == "8000":
                        self.current_cmd_port = "8300"
                        self.current_data_port = "8301"

                    self.current_bw = store.get("bandwidth", self.default_bw)
                    if self.current_bw not in ("BW500", "BW2300", "BW2750", "NARROW", "WIDE"):
                        self.current_bw = "BW500" if self.current_mode == "HF" else "NARROW"

                    self.current_signature = store.get("signature", self.default_signature)

                    # Load per-mode dwell settings
                    self.hf_dwell = str(store.get("hf_dwell", self.default_hf_dwell))
                    self.fm_dwell = str(store.get("fm_dwell", self.default_fm_dwell))

                    raw_hf = store.get("hf_contacts", [])
                    if not raw_hf and "bbs_contacts" in store:
                        raw_hf = store["bbs_contacts"]
                    elif not raw_hf and "bbs_list" in store:
                        raw_hf = [{"bbs": b, "digi": ""} for b in store["bbs_list"]]

                    self.hf_contacts = [
                        {"bbs": c["bbs"].strip().upper(), "digi": c.get("digi", "").strip().upper()}
                        for c in raw_hf if isinstance(c, dict)
                    ] if raw_hf else list(self.default_hf_contacts)

                    raw_fm = store.get("fm_contacts", [])
                    self.fm_contacts = [
                        {"bbs": c["bbs"].strip().upper(), "digi": c.get("digi", "").strip().upper()}
                        for c in raw_fm if isinstance(c, dict)
                    ] if raw_fm else list(self.default_fm_contacts)

                    self.inbox_msgs = store.get("inbox", [])
                    self.draft_msgs = store.get("drafts", [])
                    self.outbox_msgs = store.get("outbox", [])
                    self.sent_msgs = store.get("sent", [])
                    self.trash_msgs = store.get("trash", [])
                    return
            except Exception as e:
                print(f"[!] Warning: Could not parse database file ({e}). Starting with defaults.")
        
        self.current_call = self.default_call
        self.current_host = self.default_host
        self.current_mode = self.default_mode
        self.current_cmd_port = self.default_cmd_port
        self.current_data_port = self.default_data_port
        self.current_bw = self.default_bw
        self.current_signature = self.default_signature
        self.hf_dwell = self.default_hf_dwell
        self.fm_dwell = self.default_fm_dwell

        self.hf_contacts = list(self.default_hf_contacts)
        self.fm_contacts = list(self.default_fm_contacts)
        self.recent_recipients = list(self.default_recipients)
        self.user_dictionary = []

    def _save_data(self):
        try:
            self.saved_geometry = self.geometry()
        except Exception:
            pass

        # Update cache for current mode's dwell time from GUI entry if initialized
        if hasattr(self, "dwell_entry") and hasattr(self, "mode_combo"):
            current_ui_mode = self.mode_combo.get().strip().upper()
            dwell_val = self.dwell_entry.get().strip()
            if current_ui_mode == "HF":
                self.hf_dwell = dwell_val
            else:
                self.fm_dwell = dwell_val

        data = {
            "window_geometry": self.saved_geometry,
            "theme_mode": self.theme_mode,
            "my_call": self.my_call_entry.get().strip().upper() if hasattr(self, "my_call_entry") else self.current_call,
            "modem_host": self.vara_host_entry.get().strip() if hasattr(self, "vara_host_entry") else self.current_host,
            "modem_mode": self.mode_combo.get().strip() if hasattr(self, "mode_combo") else self.current_mode,
            "cmd_port": self.cmd_port_entry.get().strip() if hasattr(self, "cmd_port_entry") else self.current_cmd_port,
            "data_port": self.data_port_entry.get().strip() if hasattr(self, "data_port_entry") else self.current_data_port,
            "bandwidth": self.bw_combo.get().strip() if hasattr(self, "bw_combo") else self.current_bw,
            "signature": self.sig_text.get("1.0", tk.END).strip() if hasattr(self, "sig_text") else self.current_signature,
            "hf_dwell": self.hf_dwell,
            "fm_dwell": self.fm_dwell,
            "recent_recipients": self.recent_recipients,
            "user_dictionary": self.user_dictionary,
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
        self._stop_listener_service()
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
    # RIGHT-CLICK CONTEXT MENU (COPY / PASTE)
    # ==========================================
    def attach_context_menu(self, widget):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: self._select_all_widget(widget))

        def _show_menu(event):
            is_dark = (self.theme_mode == "dark")
            m_bg = "#282c34" if is_dark else "#ffffff"
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

    # ==========================================
    # THEME TOGGLE & STYLING ENGINE
    # ==========================================
    def toggle_theme(self):
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        self._apply_theme()
        self._save_data()

    def _apply_theme(self):
        is_dark = (self.theme_mode == "dark")
        self.btn_theme_toggle.config(text="[Light]" if is_dark else "[Dark]")

        bg_main = "#1e222b" if is_dark else "#f3f4f6"
        bg_card = "#282c34" if is_dark else "#ffffff"
        fg_text = "#e5e7eb" if is_dark else "#111827"
        border_col = "#3f4451" if is_dark else "#d1d5db"
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

        self.style.configure("Treeview", background=bg_card, foreground=fg_text, fieldbackground=bg_card, borderwidth=0)
        self.style.configure("Treeview.Heading", background=bg_main, foreground=fg_text, bordercolor=border_col, font=("Arial", 9, "bold"))
        self.style.map("Treeview", background=[("selected", tree_sel)], foreground=[("selected", "#ffffff")])

        self.sig_text.config(
            bg=bg_card,
            fg=fg_text,
            insertbackground=fg_text,
            highlightbackground=border_col,
            highlightcolor=tree_sel
        )

        for child in self.ref_frame.winfo_children():
            if isinstance(child, ttk.Frame):
                child.configure(style="TFrame")

    def _open_html_forms_suite(self):
        webbrowser.open_new_tab("https://www.tprfn.net/html-form-suite")

    def _get_active_contacts(self):
        mode = self.mode_combo.get() if hasattr(self, "mode_combo") else self.current_mode
        return self.hf_contacts if mode == "HF" else self.fm_contacts

    def _build_ui(self):
        top_bar = ttk.Frame(self, padding=8)
        top_bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top_bar, text="Target BBS:").pack(side=tk.LEFT, padx=(0, 4))
        self.bbs_combo = ttk.Combobox(top_bar, width=12)
        self.bbs_combo.pack(side=tk.LEFT, padx=(0, 4))
        self.bbs_combo.bind("<<ComboboxSelected>>", self._on_bbs_selected)
        self.attach_context_menu(self.bbs_combo)

        self.btn_add_bbs = ttk.Button(top_bar, text="[+] Add", command=self.add_bbs_station)
        self.btn_add_bbs.pack(side=tk.LEFT, padx=1)

        self.btn_del_bbs = ttk.Button(top_bar, text="[-] Del", command=self.delete_bbs_station)
        self.btn_del_bbs.pack(side=tk.LEFT, padx=(1, 8))

        ttk.Label(top_bar, text="Via Digi:").pack(side=tk.LEFT, padx=(0, 4))
        self.digi_entry = ttk.Entry(top_bar, width=10)
        self.digi_entry.pack(side=tk.LEFT, padx=(0, 8))
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

        self.btn_forms = ttk.Button(top_bar, text="HTML Forms", command=self._open_html_forms_suite)
        self.btn_forms.pack(side=tk.LEFT, padx=4)

        self.btn_theme_toggle = ttk.Button(top_bar, text="[Dark]", width=8, command=self.toggle_theme)
        self.btn_theme_toggle.pack(side=tk.LEFT, padx=4)

        self.status_lbl = ttk.Label(top_bar, text="Idle", foreground="gray", font=("Arial", 10, "bold"))
        self.status_lbl.pack(side=tk.RIGHT, padx=10)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X)

        body_container = ttk.Frame(self)
        body_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Scrollable Left Sidebar
        left_container = ttk.Frame(body_container, width=380)
        left_container.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))
        left_container.pack_propagate(False)

        self.left_canvas = tk.Canvas(left_container, borderwidth=0, highlightthickness=0)
        self.left_scrollbar = ttk.Scrollbar(left_container, orient=tk.VERTICAL, command=self.left_canvas.yview)
        
        self.scrollable_left = ttk.Frame(self.left_canvas)
        self.scrollable_left.bind(
            "<Configure>",
            lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))
        )

        self.canvas_window = self.left_canvas.create_window((0, 0), window=self.scrollable_left, anchor="nw", width=360)
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

        # Mailboxes
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

        # Settings
        settings_group = ttk.LabelFrame(self.scrollable_left, text="Station & Modem Settings", padding=6)
        settings_group.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(settings_group, text="Modem Type:").pack(anchor=tk.W, pady=(1, 0))
        self.mode_combo = ttk.Combobox(settings_group, values=["HF", "FM"], state="readonly")
        self.mode_combo.set(self.current_mode)
        self.mode_combo.pack(fill=tk.X, pady=(0, 3))
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)

        ttk.Label(settings_group, text="My Callsign:").pack(anchor=tk.W, pady=(1, 0))
        self.my_call_entry = ttk.Entry(settings_group)
        self.my_call_entry.insert(0, self.current_call)
        self.my_call_entry.pack(fill=tk.X, pady=(0, 3))
        self.attach_context_menu(self.my_call_entry)

        ttk.Label(settings_group, text="Modem Host IP:").pack(anchor=tk.W, pady=(1, 0))
        self.vara_host_entry = ttk.Entry(settings_group)
        self.vara_host_entry.insert(0, self.current_host)
        self.vara_host_entry.pack(fill=tk.X, pady=(0, 3))
        self.attach_context_menu(self.vara_host_entry)

        ports_row = ttk.Frame(settings_group)
        ports_row.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(ports_row, text="Cmd:").pack(side=tk.LEFT)
        self.cmd_port_entry = ttk.Entry(ports_row, width=5)
        self.cmd_port_entry.insert(0, self.current_cmd_port)
        self.cmd_port_entry.pack(side=tk.LEFT, padx=(2, 4))
        self.attach_context_menu(self.cmd_port_entry)

        ttk.Label(ports_row, text="Data:").pack(side=tk.LEFT)
        self.data_port_entry = ttk.Entry(ports_row, width=5)
        self.data_port_entry.insert(0, self.current_data_port)
        self.data_port_entry.pack(side=tk.LEFT, padx=(2, 4))
        self.attach_context_menu(self.data_port_entry)

        ttk.Label(ports_row, text="Dwell (s):").pack(side=tk.LEFT)
        self.dwell_entry = ttk.Entry(ports_row, width=5)
        active_dwell = self.hf_dwell if self.current_mode == "HF" else self.fm_dwell
        self.dwell_entry.insert(0, active_dwell)
        self.dwell_entry.pack(side=tk.LEFT, padx=(2, 0))
        self.attach_context_menu(self.dwell_entry)

        ttk.Label(settings_group, text="Bandwidth / Mode:").pack(anchor=tk.W, pady=(1, 0))
        bw_options = ["BW500", "BW2300", "BW2750"] if self.current_mode == "HF" else ["NARROW", "WIDE"]
        self.bw_combo = ttk.Combobox(settings_group, values=bw_options, state="readonly")
        self.bw_combo.set(self.current_bw)
        self.bw_combo.pack(fill=tk.X, pady=(0, 3))

        ttk.Label(settings_group, text="Station Signature (6 Lines):").pack(anchor=tk.W, pady=(1, 0))
        self.sig_text = scrolledtext.ScrolledText(settings_group, height=5, font=("Courier", 9))
        self.sig_text.insert("1.0", self.current_signature)
        self.sig_text.pack(fill=tk.X, expand=False, pady=(0, 2))
        self.attach_context_menu(self.sig_text)

        # 3-Column Node Commands Menu
        node_group = ttk.LabelFrame(self.scrollable_left, text="Node & BBS Commands", padding=6)
        node_group.pack(fill=tk.X, pady=(0, 6))

        node_group.columnconfigure(0, weight=1)
        node_group.columnconfigure(1, weight=1)
        node_group.columnconfigure(2, weight=1)

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
            btn = ttk.Button(
                node_group,
                text=label_text,
                command=lambda cmd=cmd_text: self.send_node_command(cmd)
            )
            btn.grid(row=r, column=c, padx=2, pady=2, sticky=tk.EW)

        ttk.Separator(node_group, orient=tk.HORIZONTAL).grid(row=4, column=0, columnspan=3, pady=(6, 4), sticky=tk.EW)

        self.ref_frame = ttk.LabelFrame(node_group, text="Command Quick Reference", padding=4)
        self.ref_frame.grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=(2, 0))

        guide_lines = [
            ("Read", "Dbl-Click msg# in Term"),
            ("Personal", "SP callsign"),
            ("Bulletin", "SB ha route"),
            ("Msg Reply", "SR msg#"),
            ("NTS", "ST zip & st")
        ]

        for desc, syntax in guide_lines:
            row_frame = ttk.Frame(self.ref_frame)
            row_frame.pack(fill=tk.X, pady=1)
            ttk.Label(row_frame, text=f"* {desc}:", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
            ttk.Label(row_frame, text=syntax, font=("Consolas", 8, "bold"), foreground="#0284c7").pack(side=tk.RIGHT)

        # Right Column
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
            table_container,
            columns=cols,
            show="headings",
            selectmode="browse",
            yscrollcommand=self.table_v_scroll.set
        )
        self.table_v_scroll.config(command=self.msg_table.yview)

        self.msg_table.heading("msg_num", text="#")
        self.msg_table.heading("from_to", text="From / To")
        self.msg_table.heading("subject", text="Subject")
        self.msg_table.heading("date", text="Date / Status")

        self.msg_table.column("msg_num", width=70, minwidth=50, anchor=tk.CENTER)
        self.msg_table.column("from_to", width=140, minwidth=100)
        self.msg_table.column("subject", width=420, minwidth=200)
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
            term_frame,
            wrap=tk.WORD,
            bg="#0f141c",
            fg="#22c55e",
            insertbackground="#22c55e",
            font=("Consolas", 10)
        )
        self.term_view.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))
        self.attach_context_menu(self.term_view)
        
        self.term_view.bind("<Double-Button-1>", self._on_term_double_click)
        self.term_print("[*] Terminal ready. Double-click any message number to fetch & read.\n")

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
                header = f"\n{'='*55}\nFrom:    {local_msg.get('from', 'BBS')}\nSubject: {local_msg.get('subj', '')}\nDate:    {local_msg.get('date', '')}\n{'-'*55}\n"
                self.term_print(header + local_msg.get("body", "") + f"\n{'='*55}\n")
            else:
                if self.worker_thread and self.worker_thread.is_alive() and self.data_sock:
                    self.term_print(f"\n[*] Fetching message #{msg_num} from remote BBS...\n")
                    self.tx_manual_queue.put(f"R {msg_num}")
                else:
                    self.term_print(f"\n[!] Cannot fetch #{msg_num}: Not connected to BBS. Connect first to read.\n")
            return "break"

    def _refresh_bbs_dropdown(self):
        active_contacts = self._get_active_contacts()
        bbs_names = [c["bbs"] for c in active_contacts]
        self.bbs_combo["values"] = bbs_names

        if bbs_names:
            self.bbs_combo.set(bbs_names[0])
            self.digi_entry.delete(0, tk.END)
            self.digi_entry.insert(0, active_contacts[0].get("digi", ""))
        else:
            self.bbs_combo.set("")
            self.digi_entry.delete(0, tk.END)

    def _on_mode_change(self, event=None):
        new_mode = self.mode_combo.get().strip().upper()
        
        # Save outgoing mode dwell value before swapping
        if hasattr(self, "dwell_entry"):
            old_dwell = self.dwell_entry.get().strip()
            if self.current_mode == "HF":
                self.hf_dwell = old_dwell
            else:
                self.fm_dwell = old_dwell

        self.current_mode = new_mode

        restart_listener = self.listener_active
        if restart_listener:
            self._stop_listener_service()

        if new_mode == "HF":
            self.cmd_port_entry.delete(0, tk.END)
            self.cmd_port_entry.insert(0, "8358")
            self.data_port_entry.delete(0, tk.END)
            self.data_port_entry.insert(0, "8359")
            self.dwell_entry.delete(0, tk.END)
            self.dwell_entry.insert(0, self.hf_dwell)
            self.bw_combo.config(values=["BW500", "BW2300", "BW2750"])
            self.bw_combo.set("BW500")
            self.term_print(f"[*] Switched to VARA HF (Ports 8358/8359, BW500, Dwell: {self.hf_dwell}s).\n")
        else:
            self.cmd_port_entry.delete(0, tk.END)
            self.cmd_port_entry.insert(0, "8300")
            self.data_port_entry.delete(0, tk.END)
            self.data_port_entry.insert(0, "8301")
            self.dwell_entry.delete(0, tk.END)
            self.dwell_entry.insert(0, self.fm_dwell)
            self.bw_combo.config(values=["NARROW", "WIDE"])
            self.bw_combo.set("NARROW")
            self.term_print(f"[*] Switched to VARA FM (Ports 8300/8301, NARROW, Dwell: {self.fm_dwell}s).\n")

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

    def add_bbs_station(self):
        new_bbs = self.bbs_combo.get().strip().upper()
        digi = self.digi_entry.get().strip().upper()
        mode = self.mode_combo.get()

        if not new_bbs:
            messagebox.showwarning("Warning", "Enter a callsign in the Target BBS box to add.")
            return

        active_contacts = self._get_active_contacts()
        updated = False
        for contact in active_contacts:
            if contact["bbs"] == new_bbs:
                contact["digi"] = digi
                updated = True
                break

        if not updated:
            active_contacts.append({"bbs": new_bbs, "digi": digi})

        self.bbs_combo["values"] = [c["bbs"] for c in active_contacts]
        self.bbs_combo.set(new_bbs)
        self._save_data()

        digi_info = f" via {digi}" if digi else ""
        self.term_print(f"[*] Saved {new_bbs}{digi_info} to {mode} contacts list.\n")

    def delete_bbs_station(self):
        selected_bbs = self.bbs_combo.get().strip().upper()
        mode = self.mode_combo.get()
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

        for item in self.msg_table.get_children():
            self.msg_table.delete(item)

        for i, msg in enumerate(store):
            if tag == "inbox":
                status = msg.get("date", "")
                from_to = msg.get("from", "")
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
                from_to = msg.get("from", msg.get("to", ""))
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
            my_call = self.my_call_entry.get().strip().upper()
            header = f"\n{'='*55}\nType:    {msg.get('type', 'SP')}\nFrom:    {msg.get('from', my_call)}\nTo:      {msg.get('to', '')}\nSubject: {msg.get('subj', '')}\n{'-'*55}\n"
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
    # COMPOSER WITH SPELLCHECK & USER DICTIONARY
    # ==========================================
    def open_composer(self, pre_to="", pre_subj="", pre_body=None, pre_type="SP"):
        win = tk.Toplevel(self)
        win.title("Compose Message")
        win.geometry("640x580")

        is_dark = (self.theme_mode == "dark")
        win_bg = "#1e222b" if is_dark else "#f3f4f6"
        win_card = "#282c34" if is_dark else "#ffffff"
        win_fg = "#e5e7eb" if is_dark else "#111827"
        border_col = "#3f4451" if is_dark else "#d1d5db"
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
            f,
            width=48,
            height=14,
            font=("Courier", 10),
            bg=win_card,
            fg=win_fg,
            insertbackground=win_fg,
            highlightbackground=border_col
        )
        body_text.grid(row=3, column=1, sticky=tk.NSEW, pady=4)
        f.grid_rowconfigure(3, weight=1)
        f.grid_columnconfigure(1, weight=1)

        err_bg = "#7f1d1d" if is_dark else "#fecaca"
        err_fg = "#fca5a5" if is_dark else "#991b1b"
        body_text.tag_configure("misspelled", background=err_bg, foreground=err_fg)

        spell_menu = tk.Menu(win, tearoff=0)

        def run_spell_check(event=None):
            body_text.tag_remove("misspelled", "1.0", "end")
            lines = body_text.get("1.0", "end-1c").split("\n")
            for line_no, line in enumerate(lines, start=1):
                for match in re.finditer(r"\b[A-Za-z']+\b", line):
                    word = match.group()
                    if not self.spell.is_correct(word):
                        start_idx = f"{line_no}.{match.start()}"
                        end_idx = f"{line_no}.{match.end()}"
                        body_text.tag_add("misspelled", start_idx, end_idx)

        def replace_word(w_start, w_end, replacement):
            body_text.delete(w_start, w_end)
            body_text.insert(w_start, replacement)
            run_spell_check()

        def add_word_to_user_dict(word):
            clean_w = word.strip().lower()
            if clean_w and clean_w not in self.user_dictionary:
                self.user_dictionary.append(clean_w)
                self.spell.add_word(clean_w)
                self._save_data()
            run_spell_check()

        def show_body_context_menu(event):
            is_d = (self.theme_mode == "dark")
            m_bg = "#282c34" if is_d else "#ffffff"
            m_fg = "#e5e7eb" if is_d else "#111827"
            spell_menu.delete(0, tk.END)

            click_idx = body_text.index(f"@{event.x},{event.y}")
            tags = body_text.tag_names(click_idx)

            if "misspelled" in tags:
                w_start = body_text.index(f"{click_idx} wordstart")
                w_end = body_text.index(f"{click_idx} wordend")
                clicked_word = body_text.get(w_start, w_end).strip()

                candidates = self.spell.suggest(clicked_word)
                if candidates:
                    for cand in candidates:
                        spell_menu.add_command(
                            label=f"Suggested: {cand}",
                            font=("Arial", 9, "bold"),
                            command=lambda s=w_start, e=w_end, r=cand: replace_word(s, e, r)
                        )
                else:
                    spell_menu.add_command(label="(No spelling suggestions)", state=tk.DISABLED)

                spell_menu.add_command(
                    label=f"[+] Add '{clicked_word}' to Dictionary",
                    command=lambda w=clicked_word: add_word_to_user_dict(w)
                )
                spell_menu.add_separator()

            spell_menu.add_command(label="Cut", command=lambda: body_text.event_generate("<<Cut>>"))
            spell_menu.add_command(label="Copy", command=lambda: body_text.event_generate("<<Copy>>"))
            spell_menu.add_command(label="Paste", command=lambda: body_text.event_generate("<<Paste>>"))
            spell_menu.add_separator()
            spell_menu.add_command(label="Select All", command=lambda: self._select_all_widget(body_text))

            spell_menu.config(bg=m_bg, fg=m_fg, activebackground="#2563eb", activeforeground="#ffffff")
            spell_menu.tk_popup(event.x_root, event.y_root)

        body_text.bind("<KeyRelease>", run_spell_check)
        body_text.bind("<Button-3>", show_body_context_menu)
        body_text.bind("<Button-2>", show_body_context_menu)

        if pre_body is not None:
            body_text.insert("1.0", pre_body)
        else:
            active_sig = self.sig_text.get("1.0", tk.END).strip()
            if active_sig:
                body_text.insert("1.0", f"\n\n{active_sig}")
            body_text.mark_set("insert", "1.0")

        self.after(100, run_spell_check)

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

        def queue_outbound():
            dest = to_combo.get().strip().upper()
            subj = subj_entry.get().strip()
            body = body_text.get("1.0", tk.END).strip()
            m_type = msg_type_var.get()
            if not dest or not subj:
                messagebox.showerror("Error", "Callsign/Target and Subject required to send.", parent=win)
                return

            _remember_recipient(dest)
            self.outbox_msgs.append({"type": m_type, "to": dest, "subj": subj, "body": body})
            self._save_data()
            self._update_folder_counts()
            self._on_folder_select(None)
            self.term_print(f"[*] Queued outbound {m_type} message for {dest} to Outbox.\n")
            win.destroy()

        ttk.Button(btn_row, text="Save as Draft", command=save_draft).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="Queue to Outbox", command=queue_outbound).pack(side=tk.LEFT, padx=4)

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
        my_call = self.my_call_entry.get().strip().upper()
        host = self.vara_host_entry.get().strip()
        bw = self.bw_combo.get().strip()
        signature = self.sig_text.get("1.0", tk.END).strip()
        mode = self.mode_combo.get().strip().upper()

        try:
            cmd_port = int(self.cmd_port_entry.get().strip())
            data_port = int(self.data_port_entry.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Command and Data ports must be numbers.")
            return None

        try:
            dwell_val = float(self.dwell_entry.get().strip())
            if dwell_val < 0:
                dwell_val = 1.5
        except ValueError:
            dwell_val = 20.0 if mode == "HF" else 1.5

        if mode == "HF":
            self.hf_dwell = str(dwell_val)
        else:
            self.fm_dwell = str(dwell_val)

        active_contacts = self._get_active_contacts()
        updated = False
        for contact in active_contacts:
            if contact["bbs"] == target_bbs:
                contact["digi"] = raw_digi
                updated = True
                break
        if not updated:
            active_contacts.append({"bbs": target_bbs, "digi": raw_digi})
            self.bbs_combo["values"] = [c["bbs"] for c in active_contacts]

        self._save_data()

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
        # Omit dwell_val for interactive terminal sessions
        self.worker_thread = threading.Thread(target=self._run_manual_session, args=params[:-1], daemon=True)
        self.worker_thread.start()

    # ==========================================
    # VARA HF / FM OUTBOUND NETWORKING ENGINE
    # ==========================================
    def _connect_rf(self, host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call):
        self.update_status(f"Connecting to VARA ({host})...", "orange")
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
                    break
                elif "DISCONNECTED" in resp:
                    break
            except socket.timeout:
                pass

        if not connected or self.abort_requested:
            self.update_status("Disconnected / Timeout", "red")
            self.term_print("[!] Connection failed or timed out.\n")
            return False

        self.update_status(f"Connected to {target_bbs}", "green")
        self.term_print(f"[+] RF Link established with {target_bbs}!\n\n")
        return True

    def _create_inbox_messages_from_rm(self, raw_text):
        clean_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        clean_text = re.sub(r'\n[^\n]*[>?]\s*$', '', clean_text).strip()

        split_pattern = r'(?m)(?=^(?:Msg|Message)\s*#?\s*:?\s*\d+|^(?:From|F):\s*[A-Za-z0-9\-@/.]+)'
        raw_parts = re.split(split_pattern, clean_text)

        created_count = 0
        for part in raw_parts:
            item_text = part.strip()
            if not item_text or len(item_text) < 15:
                continue

            item_text = re.sub(r'^[^\n]*[>:]\s*\n?', '', item_text).strip()

            id_m = re.search(r'(?:Msg|Message)\s*#?\s*:?\s*(\d+)', item_text, re.IGNORECASE)
            from_m = re.search(r'(?:From|F):\s*([A-Za-z0-9\-@/.]+)', item_text, re.IGNORECASE)
            subj_m = re.search(r'(?:Subject|Subj):\s*(.*)', item_text, re.IGNORECASE)

            if not id_m and not from_m:
                continue

            assigned_id = id_m.group(1) if id_m else str(len(self.inbox_msgs) + 1)
            sender = from_m.group(1).strip() if from_m else "BBS"
            subject = subj_m.group(1).strip() if subj_m else f"Message #{assigned_id}"
            msg_date = time.strftime("%m/%d %H:%M")

            if any(existing.get("id") == assigned_id and existing.get("from") == sender for existing in self.inbox_msgs):
                continue

            self.inbox_msgs.append({
                "id": assigned_id,
                "from": sender,
                "subj": subject,
                "date": msg_date,
                "body": item_text
            })
            created_count += 1
            self.term_print(f"[+] Saved message #{assigned_id} from {sender} - '{subject}'\n")

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

        # Dwell before initial RM query
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

        # Step through queued outbox items using dwell timing between commands
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

            self.term_print("[*] Terminal active. Type commands above, or click Node & BBS Commands on the left.\n\n")
            self.data_sock.settimeout(0.3)
            self.cmd_sock.settimeout(0.3)

            while not self.abort_requested:
                while not self.tx_manual_queue.empty():
                    cmd = self.tx_manual_queue.get_nowait()
                    self._send_data(f"{cmd}\r")
                    if cmd.upper() in ["B", "BYE", "QUIT"]:
                        self.term_print("[*] Logoff command recognized. Terminating link...\n")
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
    # INCOMING MAILBOX & LISTENER ENGINE
    # ==========================================
    def toggle_mailbox_listener(self):
        if self.listener_active:
            self._stop_listener_service()
            self.btn_listen.config(text="Mailbox Standby")
            self.update_status("Standby Disabled", "gray")
            self.term_print("[*] Mailbox listener disabled.\n")
        else:
            if self.worker_thread and self.worker_thread.is_alive():
                messagebox.showwarning("Busy", "Cannot enable Standby while an outbound session is running.")
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
        host = self.vara_host_entry.get().strip()
        my_call = self.my_call_entry.get().strip().upper()
        mode = self.mode_combo.get().strip().upper()
        bw = self.bw_combo.get().strip()
        try:
            cmd_port = int(self.cmd_port_entry.get().strip())
            data_port = int(self.data_port_entry.get().strip())
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
                            self.update_status(f"Caller: {self.remote_call}", "blue")
                            self.term_print(f"\n[+] Incoming RF Connect from {self.remote_call}!\n")
                            self._send_mailbox_welcome(my_call, mode)
                        elif line.startswith("DISCONNECTED"):
                            if self.mailbox_in_session:
                                self.term_print(f"\n[*] {self.remote_call} disconnected from Mailbox.\n")
                                self.mailbox_in_session = False
                                self.remote_call = ""
                                self.mb_state = "CMD"
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

        # STATE: Normal Command Prompt
        if self.mb_state == "CMD":
            cmd = line.upper()
            
            # Help
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

            # List All (L)
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

            # List Mine (LM)
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

            # Read (R <num>)
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

            # Send Reply (SR <msg#>)
            elif cmd.startswith("SR ") or (cmd.startswith("SR") and len(cmd) > 2 and cmd[2:].isdigit()):
                num_str = cmd[3:].strip() if cmd.startswith("SR ") else cmd[2:].strip()
                matched = next((m for m in self.inbox_msgs if str(m.get("id")) == num_str), None)
                if matched:
                    orig_from = matched.get("from", "").strip().upper()
                    dest_call = orig_from if orig_from and orig_from != "BBS" else my_call
                    orig_subj = matched.get("subj", "").strip()
                    reply_subj = orig_subj if orig_subj.upper().startswith("RE:") else f"RE: {orig_subj}"
                    
                    self.mb_rx_msg = {
                        "from": self.remote_call,
                        "to": dest_call,
                        "subj": reply_subj,
                        "body": "",
                        "type": "SP"
                    }
                    self.mb_state = "SP_BODY"
                    self._send_listener_data(
                        f"\r\nReplying to Message #{num_str} (To: {dest_call})\r\n"
                        f"Subject: {reply_subj}\r\n"
                        f"Enter message text. End with /EX or Ctrl+Z on a new line:\r\n"
                    )
                else:
                    self._send_listener_data(f"\r\nMessage #{num_str} not found.\r\n\r\n{prompt}")

            # Send Personal Message (SP <call>)
            elif cmd.startswith("SP ") or cmd.startswith("SB "):
                dest_call = cmd.split(maxsplit=1)[1].strip().upper()
                if not dest_call:
                    self._send_listener_data(f"\r\nError: Destination callsign required.\r\n{prompt}")
                    return
                self.mb_rx_msg = {
                    "from": self.remote_call,
                    "to": dest_call,
                    "subj": "",
                    "body": "",
                    "type": "SP" if cmd.startswith("SP") else "SB"
                }
                self.mb_state = "SP_SUBJ"
                self._send_listener_data("Enter Subject: ")

            # Kill/Delete Message (KM <num>)
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

            # Disconnect / Logoff
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

        # STATE: Awaiting Subject
        elif self.mb_state == "SP_SUBJ":
            self.mb_rx_msg["subj"] = line if line else "No Subject"
            self.mb_state = "SP_BODY"
            self._send_listener_data("\r\nEnter message text. End with /EX or Ctrl+Z on a new line:\r\n")

        # STATE: Collecting Body Lines until /EX
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
        self.update_status("Aborting transmission...", "red")
        self.term_print("\n[!] Disconnect button pressed: Terminating RF connection...\n")
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

    def _reset_ui_buttons(self):
        self.after(0, lambda: self.btn_send_rcv.config(state=tk.NORMAL))
        self.after(0, lambda: self.btn_manual_conn.config(state=tk.NORMAL))
        self.after(0, lambda: self.btn_disconnect.config(state=tk.DISABLED))
        self.after(0, lambda: self.btn_listen.config(state=tk.NORMAL))


if __name__ == "__main__":
    app = VaraBBSClient()
    app.mainloop()