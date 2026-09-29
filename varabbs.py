import sys
import os
import socket
import threading
import time
import re
import json
import queue
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "varabbs_data.json")

class VaraBBSClient(tk.Tk):
    def __init__(self):
        super().__init__()

        # Station & Modem Defaults
        self.default_call = "N3MEL"
        self.default_host = "192.168.86.34"
        self.default_mode = "HF"  # "HF" or "FM"
        self.default_cmd_port = "8358"
        self.default_data_port = "8359"
        self.default_bw = "BW500"
        
        self.default_signature = (
            "---\n"
            "73, Glenn - N3MEL\n"
            "Grid: FM29dx | Southeastern PA\n"
            "TPRFN EPA Hub Station"
        )
        
        # Default Contacts Split by Mode
        self.default_hf_contacts = [
            {"bbs": "MELBBS", "digi": ""},
            {"bbs": "W3PND-1", "digi": ""},
            {"bbs": "K3PGB-1", "digi": ""},
            {"bbs": "N3LGN-1", "digi": ""},
            {"bbs": "WB3KAS-1", "digi": ""}
        ]
        self.default_fm_contacts = [
            {"bbs": "MELBBS-1", "digi": "W3PND-2"},
            {"bbs": "W3PND-4", "digi": ""},
            {"bbs": "K3PGB-4", "digi": "WIDE1-1"},
            {"bbs": "CCAR-BBS", "digi": ""}
        ]

        # Network State & Command Queue
        self.cmd_sock = None
        self.data_sock = None
        self.worker_thread = None
        self.abort_requested = False
        self.tx_manual_queue = queue.Queue()

        # Load Persistent Storage
        self.saved_geometry = "1280x840"
        self.hf_contacts = []
        self.fm_contacts = []
        self.inbox_msgs = []
        self.draft_msgs = []
        self.outbox_msgs = []
        self.sent_msgs = []
        self.trash_msgs = []
        self._load_data()

        # Window Setup: Set remembered geometry, then force maximize
        self.title(f"VARA HF/FM Mail & Terminal Client by N3MEL- [{self.default_call}]")
        self.geometry(self.saved_geometry)
        self.after(50, self._maximize_window)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_ui()
        self._refresh_bbs_dropdown()
        self._update_folder_counts()
        self._on_folder_select(None)

    # ==========================================
    # PERSISTENT STORAGE HANDLERS (JSON)
    # ==========================================
    def _maximize_window(self):
        """Forces GUI window to open maximized across Windows and Linux."""
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
        
        self.hf_contacts = list(self.default_hf_contacts)
        self.fm_contacts = list(self.default_fm_contacts)

    def _save_data(self):
        try:
            self.saved_geometry = self.geometry()
        except Exception:
            pass

        data = {
            "window_geometry": self.saved_geometry,
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

    def _get_active_contacts(self):
        mode = self.mode_combo.get() if hasattr(self, "mode_combo") else self.default_mode
        return self.hf_contacts if mode == "HF" else self.fm_contacts

    def _build_ui(self):
        top_bar = ttk.Frame(self, padding=8)
        top_bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top_bar, text="Target BBS:").pack(side=tk.LEFT, padx=(0, 4))
        self.bbs_combo = ttk.Combobox(top_bar, width=12)
        self.bbs_combo.pack(side=tk.LEFT, padx=(0, 4))
        self.bbs_combo.bind("<<ComboboxSelected>>", self._on_bbs_selected)

        self.btn_add_bbs = ttk.Button(top_bar, text="➕ Add", command=self.add_bbs_station)
        self.btn_add_bbs.pack(side=tk.LEFT, padx=1)

        self.btn_del_bbs = ttk.Button(top_bar, text="🗑️ Del", command=self.delete_bbs_station)
        self.btn_del_bbs.pack(side=tk.LEFT, padx=(1, 8))

        ttk.Label(top_bar, text="Via Digi:").pack(side=tk.LEFT, padx=(0, 4))
        self.digi_entry = ttk.Entry(top_bar, width=10)
        self.digi_entry.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_send_rcv = ttk.Button(top_bar, text="📥 Send/Recv", command=self.start_auto_session)
        self.btn_send_rcv.pack(side=tk.LEFT, padx=3)

        self.btn_manual_conn = ttk.Button(top_bar, text="⚡ Connect (Term)", command=self.start_manual_session)
        self.btn_manual_conn.pack(side=tk.LEFT, padx=3)

        self.btn_disconnect = ttk.Button(top_bar, text="⏹️ Disconnect", state=tk.DISABLED, command=self.manual_disconnect)
        self.btn_disconnect.pack(side=tk.LEFT, padx=3)

        self.btn_new_msg = ttk.Button(top_bar, text="✏️ New Message", command=self.open_composer)
        self.btn_new_msg.pack(side=tk.LEFT, padx=3)

        self.status_lbl = ttk.Label(top_bar, text="Idle", foreground="gray", font=("Arial", 10, "bold"))
        self.status_lbl.pack(side=tk.RIGHT, padx=10)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X)

        body_container = ttk.Frame(self)
        body_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Left Column (360px fixed width)
        left_col = ttk.Frame(body_container, width=360)
        left_col.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))
        left_col.pack_propagate(False)

        folder_group = ttk.LabelFrame(left_col, text="Mailboxes", padding=6)
        folder_group.pack(fill=tk.X, pady=(0, 6))

        self.folder_tree = ttk.Treeview(folder_group, selectmode="browse", show="tree", height=5)
        self.folder_tree.pack(fill=tk.X)

        self.f_inbox = self.folder_tree.insert("", "end", text="📥 Inbox (0)", values=("inbox",))
        self.f_drafts = self.folder_tree.insert("", "end", text="📝 Drafts (0)", values=("drafts",))
        self.f_outbox = self.folder_tree.insert("", "end", text="📤 Outbox (0)", values=("outbox",))
        self.f_sent = self.folder_tree.insert("", "end", text="📁 Sent (0)", values=("sent",))
        self.f_trash = self.folder_tree.insert("", "end", text="🗑️ Trash (0)", values=("trash",))
        self.folder_tree.bind("<<TreeviewSelect>>", self._on_folder_select)
        self.folder_tree.selection_set(self.f_inbox)

        settings_group = ttk.LabelFrame(left_col, text="⚙️ Station & Modem Settings", padding=6)
        settings_group.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(settings_group, text="Modem Type:").pack(anchor=tk.W, pady=(1, 0))
        self.mode_combo = ttk.Combobox(settings_group, values=["HF", "FM"], state="readonly")
        self.mode_combo.set(self.default_mode)
        self.mode_combo.pack(fill=tk.X, pady=(0, 3))
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)

        ttk.Label(settings_group, text="My Callsign:").pack(anchor=tk.W, pady=(1, 0))
        self.my_call_entry = ttk.Entry(settings_group)
        self.my_call_entry.insert(0, self.default_call)
        self.my_call_entry.pack(fill=tk.X, pady=(0, 3))

        ttk.Label(settings_group, text="Modem Host IP:").pack(anchor=tk.W, pady=(1, 0))
        self.vara_host_entry = ttk.Entry(settings_group)
        self.vara_host_entry.insert(0, self.default_host)
        self.vara_host_entry.pack(fill=tk.X, pady=(0, 3))

        ports_row = ttk.Frame(settings_group)
        ports_row.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(ports_row, text="Cmd:").pack(side=tk.LEFT)
        self.cmd_port_entry = ttk.Entry(ports_row, width=6)
        self.cmd_port_entry.insert(0, self.default_cmd_port)
        self.cmd_port_entry.pack(side=tk.LEFT, padx=(2, 6))
        ttk.Label(ports_row, text="Data:").pack(side=tk.LEFT)
        self.data_port_entry = ttk.Entry(ports_row, width=6)
        self.data_port_entry.insert(0, self.default_data_port)
        self.data_port_entry.pack(side=tk.LEFT, padx=2)

        ttk.Label(settings_group, text="Bandwidth / Mode:").pack(anchor=tk.W, pady=(1, 0))
        self.bw_combo = ttk.Combobox(settings_group, values=["BW500", "BW2300", "BW2750"], state="readonly")
        self.bw_combo.set(self.default_bw)
        self.bw_combo.pack(fill=tk.X, pady=(0, 3))

        ttk.Label(settings_group, text="Station Signature (6 Lines):").pack(anchor=tk.W, pady=(1, 0))
        self.sig_text = scrolledtext.ScrolledText(settings_group, height=6, font=("Courier", 9))
        self.sig_text.insert("1.0", self.default_signature)
        self.sig_text.pack(fill=tk.X, expand=False, pady=(0, 2))

        # ----------------------------------------------------
        # 3-COLUMN NODE & BBS COMMANDS MENU
        # ----------------------------------------------------
        node_group = ttk.LabelFrame(left_col, text="📡 Node & BBS Commands", padding=6)
        node_group.pack(fill=tk.BOTH, expand=True)

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

        # ----------------------------------------------------
        # BBS COMMAND QUICK REFERENCE INSTRUCTIONS
        # ----------------------------------------------------
        ref_frame = ttk.LabelFrame(node_group, text="📖 Command Quick Reference", padding=4)
        ref_frame.grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=(2, 0))

        guide_lines = [
            ("Read", "Dbl-Click msg# in Term"),
            ("Personal", "SP callsign"),
            ("Bulletin", "SB ha route"),
            ("Msg Reply", "SR msg#"),
            ("NTS", "ST zip & st")
        ]

        for desc, syntax in guide_lines:
            row_frame = ttk.Frame(ref_frame)
            row_frame.pack(fill=tk.X, pady=1)
            ttk.Label(row_frame, text=f"• {desc}:", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
            ttk.Label(row_frame, text=syntax, font=("Consolas", 8, "bold"), foreground="#0284c7").pack(side=tk.RIGHT)

        # ----------------------------------------------------
        # RIGHT COLUMN: DYNAMIC PANEDWINDOW
        # ----------------------------------------------------
        right_paned = ttk.PanedWindow(body_container, orient=tk.VERTICAL)
        right_paned.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ====================================================
        # UPPER PANE: MESSAGE RECEIVED WINDOW
        # ====================================================
        msg_list_frame = ttk.LabelFrame(right_paned, text="Received Messages", padding=4)
        right_paned.add(msg_list_frame, weight=1)

        list_toolbar = ttk.Frame(msg_list_frame)
        list_toolbar.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))
        self.btn_del_msg = ttk.Button(list_toolbar, text="🗑 Delete Message", command=self.delete_selected_message)
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

        # ====================================================
        # LOWER PANE: TERMINAL & MONITOR
        # ====================================================
        term_frame = ttk.LabelFrame(right_paned, text="Live BBS Terminal & Traffic Monitor", padding=4)
        right_paned.add(term_frame, weight=2)

        input_bar = ttk.Frame(term_frame)
        input_bar.pack(side=tk.TOP, fill=tk.X, padx=2, pady=(2, 4))

        ttk.Label(input_bar, text="Type-Ahead:").pack(side=tk.LEFT, padx=(0, 4))
        self.cmd_entry = ttk.Entry(input_bar)
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.cmd_entry.bind("<Return>", lambda event: self.send_manual_command())

        self.btn_send_cmd = ttk.Button(input_bar, text="Send ↵", width=8, command=self.send_manual_command)
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
        
        # Double-click message number to read
        self.term_view.bind("<Double-Button-1>", self._on_term_double_click)
        
        self.term_print("[*] Terminal ready. Double-click any message number to fetch & read.\n")

    # ==========================================
    # TERMINAL DOUBLE-CLICK TO READ MESSAGE
    # ==========================================
    def _on_term_double_click(self, event):
        """Extracts the message number under the cursor and sends 'R <num>' to the BBS."""
        index = self.term_view.index(f"@{event.x},{event.y}")
        line_start = f"{index.split('.')[0]}.0"
        line_end = f"{index.split('.')[0]}.end"
        line_text = self.term_view.get(line_start, line_end).strip()

        # Matches lines starting with message numbers like: 28345 29-Sep B$ ...
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
                my_call = self.my_call_entry.get().strip().upper()
                header = f"\n{'='*55}\nFrom:    {local_msg.get('from', 'BBS')}\nSubject: {local_msg.get('subj', '')}\nDate:    {local_msg.get('date', '')}\n{'-'*55}\n"
                self.term_print(header + local_msg.get("body", "") + f"\n{'='*55}\n")
            else:
                if self.worker_thread and self.worker_thread.is_alive() and self.data_sock:
                    self.term_print(f"\n[*] Fetching message #{msg_num} from remote BBS...\n")
                    self.tx_manual_queue.put(f"R {msg_num}")
                else:
                    self.term_print(f"\n[!] Cannot fetch #{msg_num}: Not connected to BBS. Connect first to read.\n")
            return "break"

    # ==========================================
    # MODEM MODE AUTO-CONFIG & CONTACT SWAPPING
    # ==========================================
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
        mode = self.mode_combo.get()
        if mode == "HF":
            self.cmd_port_entry.delete(0, tk.END)
            self.cmd_port_entry.insert(0, "8358")
            self.data_port_entry.delete(0, tk.END)
            self.data_port_entry.insert(0, "8359")
            self.bw_combo.config(values=["BW500", "BW2300", "BW2750"])
            self.bw_combo.set("BW500")
            self.term_print("[*] Switched to VARA HF (Ports 8358/8359, BW500, HF Contact List).\n")
        else:
            self.cmd_port_entry.delete(0, tk.END)
            self.cmd_port_entry.insert(0, "8300")
            self.data_port_entry.delete(0, tk.END)
            self.data_port_entry.insert(0, "8301")
            self.bw_combo.config(values=["NARROW", "WIDE"])
            self.bw_combo.set("NARROW")
            self.term_print("[*] Switched to VARA FM (Ports 8300/8301, NARROW, FM Contact List).\n")

        self._refresh_bbs_dropdown()

    # ==========================================
    # BBS & DIGI SELECTION / MANAGEMENT
    # ==========================================
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

    # ==========================================
    # TERMINAL DISPLAY & TYPE-AHEAD LOGIC
    # ==========================================
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
        else:
            self.term_print("[!] Not connected to BBS. Command not sent.\n")

    def send_node_command(self, cmd):
        self.term_print(f">>> {cmd}\n")
        if self.worker_thread and self.worker_thread.is_alive() and self.data_sock:
            self.tx_manual_queue.put(cmd)
        else:
            self.term_print("[!] Not connected to Node/BBS. Connect first to run this command.\n")

    # ==========================================
    # UI ACTIONS & FOLDER LOGIC
    # ==========================================
    def _update_folder_counts(self):
        self.folder_tree.item(self.f_inbox, text=f"📥 Inbox ({len(self.inbox_msgs)})")
        self.folder_tree.item(self.f_drafts, text=f"📝 Drafts ({len(self.draft_msgs)})")
        self.folder_tree.item(self.f_outbox, text=f"📤 Outbox ({len(self.outbox_msgs)})")
        self.folder_tree.item(self.f_sent, text=f"📁 Sent ({len(self.sent_msgs)})")
        self.folder_tree.item(self.f_trash, text=f"🗑️ Trash ({len(self.trash_msgs)})")

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
                from_to = msg.get("to", "(No Recipient)")
                num_col = f"D-{i+1}"
            elif tag == "outbox":
                status = "Queued"
                from_to = msg.get("to", "")
                num_col = "OUT"
            elif tag == "sent":
                status = msg.get("date", "Sent")
                from_to = msg.get("to", "")
                num_col = f"S-{i+1}"
            else:  # trash
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
            header = f"\n{'='*55}\nFrom:    {msg.get('from', my_call)}\nTo:      {msg.get('to', '')}\nSubject: {msg.get('subj', '')}\n{'-'*55}\n"
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
            self.open_composer(pre_to=draft.get("to", ""), pre_subj=draft.get("subj", ""), pre_body=draft.get("body", ""))

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
    # COMPOSER WITH SAVE AS DRAFT
    # ==========================================
    def open_composer(self, pre_to="", pre_subj="", pre_body=None):
        win = tk.Toplevel(self)
        win.title("Compose Message")
        win.geometry("580x500")

        f = ttk.Frame(win, padding=10)
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text="To Callsign:").grid(row=0, column=0, sticky=tk.W, pady=4)
        to_entry = ttk.Entry(f, width=20)
        to_entry.insert(0, pre_to)
        to_entry.grid(row=0, column=1, sticky=tk.W, pady=4)

        ttk.Label(f, text="Subject:").grid(row=1, column=0, sticky=tk.W, pady=4)
        subj_entry = ttk.Entry(f, width=45)
        subj_entry.insert(0, pre_subj)
        subj_entry.grid(row=1, column=1, sticky=tk.W, pady=4)

        ttk.Label(f, text="Body:").grid(row=2, column=0, sticky=tk.NW, pady=4)
        body_text = scrolledtext.ScrolledText(f, width=45, height=14, font=("Courier", 10))
        body_text.grid(row=2, column=1, sticky=tk.NSEW, pady=4)

        if pre_body is not None:
            body_text.insert("1.0", pre_body)
        else:
            active_sig = self.sig_text.get("1.0", tk.END).strip()
            body_text.insert("1.0", f"\n\n{active_sig}")
            body_text.mark_set("insert", "1.0")

        btn_row = ttk.Frame(f)
        btn_row.grid(row=3, column=1, sticky=tk.E, pady=10)

        def save_draft():
            dest = to_entry.get().strip().upper()
            subj = subj_entry.get().strip()
            body = body_text.get("1.0", tk.END).strip()
            self.draft_msgs.append({"to": dest, "subj": subj, "body": body})
            self._save_data()
            self._update_folder_counts()
            self._on_folder_select(None)
            self.term_print(f"[*] Saved message draft.\n")
            win.destroy()

        def queue_outbound():
            dest = to_entry.get().strip().upper()
            subj = subj_entry.get().strip()
            body = body_text.get("1.0", tk.END).strip()
            if not dest or not subj:
                messagebox.showerror("Error", "Callsign and Subject required to send.", parent=win)
                return
            self.outbox_msgs.append({"to": dest, "subj": subj, "body": body})
            self._save_data()
            self._update_folder_counts()
            self._on_folder_select(None)
            self.term_print(f"[*] Queued outbound message for {dest} to Outbox.\n")
            win.destroy()

        ttk.Button(btn_row, text="💾 Save as Draft", command=save_draft).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="Queue to Outbox", command=queue_outbound).pack(side=tk.LEFT, padx=4)

    # ==========================================
    # SESSION LAUNCHERS
    # ==========================================
    def _prepare_session(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Busy", "A connection session is already active.")
            return None

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

        return host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call, signature, mode

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
        self.worker_thread = threading.Thread(target=self._run_manual_session, args=params, daemon=True)
        self.worker_thread.start()

    # ==========================================
    # VARA HF / FM NETWORKING ENGINE
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

    # ----------------------------------------------------
    # MULTI-MESSAGE EXTRACTION & INBOX REFRESH HELPER
    # ----------------------------------------------------
    def _create_inbox_messages_from_rm(self, raw_text):
        """Robustly extracts all incoming messages from an RM response block."""
        clean_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

        # Strip ending prompt artifacts
        clean_text = re.sub(r'\n[^\n]*[>?]\s*$', '', clean_text).strip()

        # Split on standard packet BBS message headers
        split_pattern = r'(?m)(?=^(?:Msg|Message)\s*#?\s*:?\s*\d+|^(?:From|F):\s*[A-Za-z0-9\-@/.]+)'
        raw_parts = re.split(split_pattern, clean_text)

        created_count = 0
        for part in raw_parts:
            item_text = part.strip()
            if not item_text or len(item_text) < 15:
                continue

            # Strip leading prompt fragments (e.g. 'de N3MEL>')
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

    # ----------------------------------------------------
    # MODE 1: AUTOMATED SEND/RECEIVE EXCHANGE (RM ONLY + GATED OUTBOX)
    # ----------------------------------------------------
    def _run_auto_session(self, host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call, signature, mode):
        try:
            if not self._connect_rf(host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call):
                return

            self._handle_auto_bbs_exchange(signature, mode)

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

    def _handle_auto_bbs_exchange(self, signature, mode):
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

        wait_seconds = 40.0 if mode == "HF" else 1.2
        start_wait = time.time()
        while time.time() - start_wait < wait_seconds:
            if self.abort_requested:
                return
            time.sleep(0.2)

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

        outbox_wait = 40.0 if mode == "HF" else 1.2
        while self.outbox_msgs and not self.abort_requested:
            msg = self.outbox_msgs.pop(0)

            start_w = time.time()
            while time.time() - start_w < outbox_wait:
                if self.abort_requested:
                    break
                time.sleep(0.2)

            self.term_print(f">>> SP {msg['to']}\n")
            self._send_data(f"SP {msg['to']}\r")

            self._recv_data_until_prompt(timeout=40.0 if mode == "HF" else 15.0, quiet_delay=1.2)
            if self.abort_requested:
                break

            start_w = time.time()
            while time.time() - start_w < outbox_wait:
                if self.abort_requested:
                    break
                time.sleep(0.2)

            self.term_print(f">>> {msg['subj']}\n")
            self._send_data(f"{msg['subj']}\r")

            self._recv_data_until_prompt(timeout=40.0 if mode == "HF" else 15.0, quiet_delay=1.2)
            if self.abort_requested:
                break

            start_w = time.time()
            while time.time() - start_w < outbox_wait:
                if self.abort_requested:
                    break
                time.sleep(0.2)

            body_content = msg['body'].strip()
            sig_check = signature.splitlines()[0] if signature else ""
            if sig_check and sig_check not in body_content:
                body_content = f"{body_content}\n\n{signature}"

            clean_body = body_content.replace("\r\n", "\r").replace("\n", "\r")
            payload = f"{clean_body}\r/EX\r"

            self.term_print(">>> [Sending Message Body + /EX]\n")
            self._send_data(payload)

            self._recv_data_until_prompt(timeout=40.0 if mode == "HF" else 20.0, quiet_delay=1.5)

            msg["date"] = time.strftime("%m/%d %H:%M")
            self.sent_msgs.append(msg)
            self.term_print(f"[+] Message successfully posted to {msg['to']}!\n")

        self._save_data()
        self.after(0, self._update_folder_counts)
        self.after(0, lambda: self._on_folder_select(None))

    # ----------------------------------------------------
    # MODE 2: INTERACTIVE TERMINAL LOOP (MANUAL CLI)
    # ----------------------------------------------------
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
        self.term_print("\n[!] Disconnect button pressed: Sending ABORT to VARA modem...\n")
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

if __name__ == "__main__":
    app = VaraBBSClient()
    app.mainloop()