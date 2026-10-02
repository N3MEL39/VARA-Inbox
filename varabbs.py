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

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "varabbs_data.json")[cite: 2]


class VaraBBSClient(tk.Tk):
    def __init__(self):
        super().__init__()

        # Station & Modem Fallback Defaults
        self.default_call = "Your Call Here"[cite: 2]
        self.default_host = "127.0.0.1"[cite: 2]
        self.default_mode = "FM"[cite: 2]
        self.default_cmd_port = "8300"[cite: 2]
        self.default_data_port = "8301"[cite: 2]
        self.default_bw = "NARROW"[cite: 2]
        self.default_signature = ""[cite: 2]
        self.default_hf_dwell = "20.0"[cite: 2]
        self.default_fm_dwell = "1.5"[cite: 2]
        
        self.default_hf_contacts = [
            {"bbs": "N3MEL-2", "digi": "", "dwell": "20.0"},[cite: 2]
            {"bbs": "N3MEL-7", "digi": "", "dwell": "20.0"}[cite: 2]
        ]
        self.default_fm_contacts = [
            {"bbs": "N3MEL-2", "digi": "", "dwell": "1.5"},[cite: 2]
            {"bbs": "N3MEL-7", "digi": "", "dwell": "1.5"}[cite: 2]
        ]

        self.default_recipients = [
            "ALL@USA",[cite: 2]
            "SPACWX@USA",[cite: 2]
            "WX@ECBBS",[cite: 2]
            "NEWS@WW"[cite: 2]
        ]

        # Active Settings Variables
        self.current_call = self.default_call[cite: 2]
        self.current_host = self.default_host[cite: 2]
        self.current_mode = self.default_mode[cite: 2]
        self.current_cmd_port = self.default_cmd_port[cite: 2]
        self.current_data_port = self.default_data_port[cite: 2]
        self.current_bw = self.default_bw[cite: 2]
        self.current_signature = self.default_signature[cite: 2]
        self.hf_dwell = self.default_hf_dwell[cite: 2]
        self.fm_dwell = self.default_fm_dwell[cite: 2]

        # Network State & Command Queue
        self.cmd_sock = None[cite: 2]
        self.data_sock = None[cite: 2]
        self.worker_thread = None[cite: 2]
        self.abort_requested = False[cite: 2]
        self.tx_manual_queue = queue.Queue()[cite: 2]

        # Inbound Host Listener & Mailbox Engine State
        self.listener_active = False[cite: 2]
        self.listener_thread = None[cite: 2]
        self.listener_cmd_sock = None[cite: 2]
        self.listener_data_sock = None[cite: 2]
        self.listener_stop_event = threading.Event()[cite: 2]
        self.mailbox_in_session = False[cite: 2]
        self.remote_call = ""[cite: 2]
        self.mb_state = "CMD"[cite: 2]
        self.mb_rx_msg = {}[cite: 2]
        self.mb_line_buffer = ""[cite: 2]

        # Load Persistent Storage
        self.saved_geometry = "1280x840"[cite: 2]
        self.theme_mode = "light"[cite: 2]
        self.hf_contacts = [][cite: 2]
        self.fm_contacts = [][cite: 2]
        self.recent_recipients = [][cite: 2]
        self.inbox_msgs = [][cite: 2]
        self.draft_msgs = [][cite: 2]
        self.outbox_msgs = [][cite: 2]
        self.sent_msgs = [][cite: 2]
        self.trash_msgs = [][cite: 2]
        self._load_data()[cite: 2]

        # Window Setup
        self.title(f"VARA HF/FM Mail & Terminal Client by N3MEL - [{self.current_call}] 30")
        self.geometry(self.saved_geometry)[cite: 2]
        self.after(50, self._maximize_window)[cite: 2]

        self.protocol("WM_DELETE_WINDOW", self.on_close)[cite: 2]

        self.style = ttk.Style(self)[cite: 2]
        self._build_ui()[cite: 2]
        self._apply_theme()[cite: 2]
        self._refresh_bbs_dropdown()[cite: 2]
        self._update_folder_counts()[cite: 2]
        self._on_folder_select(None)[cite: 2]

    # ==========================================
    # PERSISTENT STORAGE HANDLERS (JSON)
    # ==========================================
    def _maximize_window(self):
        try:
            self.state('zoomed')[cite: 2]
        except Exception:
            try:
                self.attributes('-zoomed', True)[cite: 2]
            except Exception:
                pass[cite: 2]

    def _load_data(self):
        if os.path.exists(DATA_FILE):[cite: 2]
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:[cite: 2]
                    store = json.load(f)[cite: 2]
                    
                    self.saved_geometry = store.get("window_geometry", "1280x840")[cite: 2]
                    self.theme_mode = store.get("theme_mode", "light")[cite: 2]
                    self.recent_recipients = store.get("recent_recipients", list(self.default_recipients))[cite: 2]

                    self.current_call = store.get("my_call", self.default_call)[cite: 2]
                    self.current_host = store.get("modem_host", self.default_host)[cite: 2]
                    
                    loaded_mode = str(store.get("modem_mode", self.default_mode)).strip().upper()[cite: 2]
                    if "HF" in loaded_mode:[cite: 2]
                        self.current_mode = "HF"[cite: 2]
                    else:
                        self.current_mode = "FM"[cite: 2]

                    self.current_cmd_port = store.get("cmd_port", self.default_cmd_port)[cite: 2]
                    self.current_data_port = store.get("data_port", self.default_data_port)[cite: 2]
                    
                    if self.current_mode == "FM" and self.current_cmd_port == "8000":[cite: 2]
                        self.current_cmd_port = "8300"[cite: 2]
                        self.current_data_port = "8301"[cite: 2]

                    self.current_bw = store.get("bandwidth", self.default_bw)[cite: 2]
                    if self.current_bw not in ("BW500", "BW2300", "BW2750", "NARROW", "WIDE"):[cite: 2]
                        self.current_bw = "BW500" if self.current_mode == "HF" else "NARROW"[cite: 2]

                    self.current_signature = store.get("signature", self.default_signature)[cite: 2]

                    # Load per-mode dwell settings
                    self.hf_dwell = str(store.get("hf_dwell", self.default_hf_dwell))[cite: 2]
                    self.fm_dwell = str(store.get("fm_dwell", self.default_fm_dwell))[cite: 2]

                    raw_hf = store.get("hf_contacts", [])[cite: 2]
                    if not raw_hf and "bbs_contacts" in store:[cite: 2]
                        raw_hf = store["bbs_contacts"][cite: 2]
                    elif not raw_hf and "bbs_list" in store:[cite: 2]
                        raw_hf = [{"bbs": b, "digi": ""} for b in store["bbs_list"]][cite: 2]

                    self.hf_contacts = [
                        {
                            "bbs": c["bbs"].strip().upper(),[cite: 2]
                            "digi": c.get("digi", "").strip().upper(),[cite: 2]
                            "dwell": str(c.get("dwell", self.hf_dwell)).strip()[cite: 2]
                        }
                        for c in raw_hf if isinstance(c, dict)[cite: 2]
                    ] if raw_hf else list(self.default_hf_contacts)[cite: 2]

                    raw_fm = store.get("fm_contacts", [])[cite: 2]
                    self.fm_contacts = [
                        {
                            "bbs": c["bbs"].strip().upper(),[cite: 2]
                            "digi": c.get("digi", "").strip().upper(),[cite: 2]
                            "dwell": str(c.get("dwell", self.fm_dwell)).strip()[cite: 2]
                        }
                        for c in raw_fm if isinstance(c, dict)[cite: 2]
                    ] if raw_fm else list(self.default_fm_contacts)[cite: 2]

                    self.inbox_msgs = store.get("inbox", [])[cite: 2]
                    self.draft_msgs = store.get("drafts", [])[cite: 2]
                    self.outbox_msgs = store.get("outbox", [])[cite: 2]
                    self.sent_msgs = store.get("sent", [])[cite: 2]
                    self.trash_msgs = store.get("trash", [])[cite: 2]
                    return
            except Exception as e:
                print(f"[!] Warning: Could not parse database file ({e}). Starting with defaults.")[cite: 2]
        
        self.current_call = self.default_call[cite: 2]
        self.current_host = self.default_host[cite: 2]
        self.current_mode = self.default_mode[cite: 2]
        self.current_cmd_port = self.default_cmd_port[cite: 2]
        self.current_data_port = self.default_data_port[cite: 2]
        self.current_bw = self.default_bw[cite: 2]
        self.current_signature = self.default_signature[cite: 2]
        self.hf_dwell = self.default_hf_dwell[cite: 2]
        self.fm_dwell = self.default_fm_dwell[cite: 2]

        self.hf_contacts = list(self.default_hf_contacts)[cite: 2]
        self.fm_contacts = list(self.default_fm_contacts)[cite: 2]
        self.recent_recipients = list(self.default_recipients)[cite: 2]

    def _save_data(self):
        try:
            self.saved_geometry = self.geometry()[cite: 2]
        except Exception:
            pass[cite: 2]

        # Update cache for current mode's dwell time and station record
        if hasattr(self, "dwell_entry") and hasattr(self, "mode_combo"):[cite: 2]
            current_ui_mode = self.mode_combo.get().strip().upper()[cite: 2]
            dwell_val = self.dwell_entry.get().strip()[cite: 2]
            if current_ui_mode == "HF":[cite: 2]
                self.hf_dwell = dwell_val[cite: 2]
            else:
                self.fm_dwell = dwell_val[cite: 2]

            target_bbs = self.bbs_combo.get().strip().upper() if hasattr(self, "bbs_combo") else ""[cite: 2]
            if target_bbs:[cite: 2]
                contacts = self._get_active_contacts()[cite: 2]
                for c in contacts:[cite: 2]
                    if c["bbs"] == target_bbs:[cite: 2]
                        c["dwell"] = dwell_val[cite: 2]
                        break[cite: 2]

        data = {
            "window_geometry": self.saved_geometry,[cite: 2]
            "theme_mode": self.theme_mode,[cite: 2]
            "my_call": self.my_call_entry.get().strip().upper() if hasattr(self, "my_call_entry") else self.current_call,[cite: 2]
            "modem_host": self.vara_host_entry.get().strip() if hasattr(self, "vara_host_entry") else self.current_host,[cite: 2]
            "modem_mode": self.mode_combo.get().strip() if hasattr(self, "mode_combo") else self.current_mode,[cite: 2]
            "cmd_port": self.cmd_port_entry.get().strip() if hasattr(self, "cmd_port_entry") else self.current_cmd_port,[cite: 2]
            "data_port": self.data_port_entry.get().strip() if hasattr(self, "data_port_entry") else self.current_data_port,[cite: 2]
            "bandwidth": self.bw_combo.get().strip() if hasattr(self, "bw_combo") else self.current_bw,[cite: 2]
            "signature": self.sig_text.get("1.0", tk.END).strip() if hasattr(self, "sig_text") else self.current_signature,[cite: 2]
            "hf_dwell": self.hf_dwell,[cite: 2]
            "fm_dwell": self.fm_dwell,[cite: 2]
            "recent_recipients": self.recent_recipients,[cite: 2]
            "hf_contacts": self.hf_contacts,[cite: 2]
            "fm_contacts": self.fm_contacts,[cite: 2]
            "inbox": self.inbox_msgs,[cite: 2]
            "drafts": self.draft_msgs,[cite: 2]
            "outbox": self.outbox_msgs,[cite: 2]
            "sent": self.sent_msgs,[cite: 2]
            "trash": self.trash_msgs[cite: 2]
        }
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:[cite: 2]
                json.dump(data, f, indent=2)[cite: 2]
        except Exception as e:
            print(f"[!] Error saving database: {e}")[cite: 2]

    def on_close(self):
        self._save_data()[cite: 2]
        self.abort_requested = True[cite: 2]
        self._stop_listener_service()[cite: 2]
        try:
            if self.cmd_sock:[cite: 2]
                self.cmd_sock.sendall(b"ABORT\rDISCONNECT\r")[cite: 2]
            if self.data_sock:[cite: 2]
                self.data_sock.close()[cite: 2]
            if self.cmd_sock:[cite: 2]
                self.cmd_sock.close()[cite: 2]
        except Exception:
            pass[cite: 2]

        try:
            self.destroy()[cite: 2]
        except Exception:
            pass[cite: 2]

        os._exit(0)[cite: 2]

    # ==========================================
    # RIGHT-CLICK CONTEXT MENU (COPY / PASTE)
    # ==========================================
    def attach_context_menu(self, widget):
        menu = tk.Menu(self, tearoff=0)[cite: 2]
        menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))[cite: 2]
        menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))[cite: 2]
        menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))[cite: 2]
        menu.add_separator()[cite: 2]
        menu.add_command(label="Select All", command=lambda: self._select_all_widget(widget))[cite: 2]

        def _show_menu(event):
            is_dark = (self.theme_mode == "dark")[cite: 2]
            m_bg = "#282c34" if is_dark else "#ffffff"[cite: 2]
            m_fg = "#e5e7eb" if is_dark else "#111827"[cite: 2]
            menu.config(bg=m_bg, fg=m_fg, activebackground="#2563eb", activeforeground="#ffffff")[cite: 2]
            menu.tk_popup(event.x_root, event.y_root)[cite: 2]

        widget.bind("<Button-3>", _show_menu)[cite: 2]
        widget.bind("<Button-2>", _show_menu)[cite: 2]

    def _select_all_widget(self, widget):
        if isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox)):[cite: 2]
            widget.select_range(0, tk.END)[cite: 2]
            widget.icursor(tk.END)[cite: 2]
        elif isinstance(widget, (tk.Text, scrolledtext.ScrolledText)):[cite: 2]
            widget.tag_add("sel", "1.0", "end-1c")[cite: 2]

    # ==========================================
    # THEME TOGGLE & STYLING ENGINE
    # ==========================================
    def toggle_theme(self):
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"[cite: 2]
        self._apply_theme()[cite: 2]
        self._save_data()[cite: 2]

    def _apply_theme(self):
        is_dark = (self.theme_mode == "dark")[cite: 2]
        self.btn_theme_toggle.config(text="[Light]" if is_dark else "[Dark]")[cite: 2]

        bg_main = "#1e222b" if is_dark else "#f3f4f6"[cite: 2]
        bg_card = "#282c34" if is_dark else "#ffffff"[cite: 2]
        fg_text = "#e5e7eb" if is_dark else "#111827"[cite: 2]
        border_col = "#3f4451" if is_dark else "#d1d5db"[cite: 2]
        tree_sel = "#2563eb" if is_dark else "#3b82f6"[cite: 2]

        self.configure(bg=bg_main)[cite: 2]
        self.left_canvas.configure(bg=bg_main)[cite: 2]

        self.style.theme_use("clam")[cite: 2]
        self.style.configure(".", background=bg_main, foreground=fg_text)[cite: 2]
        self.style.configure("TFrame", background=bg_main)[cite: 2]
        self.style.configure("TLabel", background=bg_main, foreground=fg_text)[cite: 2]
        self.style.configure("TLabelframe", background=bg_main, foreground=fg_text)[cite: 2]
        self.style.configure("TLabelframe.Label", background=bg_main, foreground=fg_text, font=("Arial", 9, "bold"))[cite: 2]
        self.style.configure("TButton", background=bg_card, foreground=fg_text, bordercolor=border_col)[cite: 2]
        self.style.map("TButton", background=[("active", border_col)], foreground=[("active", fg_text)])[cite: 2]
        self.style.configure("TEntry", fieldbackground=bg_card, foreground=fg_text, bordercolor=border_col)[cite: 2]
        self.style.configure("TCombobox", fieldbackground=bg_card, background=bg_main, foreground=fg_text)[cite: 2]

        self.style.configure("Treeview", background=bg_card, foreground=fg_text, fieldbackground=bg_card, borderwidth=0)[cite: 2]
        self.style.configure("Treeview.Heading", background=bg_main, foreground=fg_text, bordercolor=border_col, font=("Arial", 9, "bold"))[cite: 2]
        self.style.map("Treeview", background=[("selected", tree_sel)], foreground=[("selected", "#ffffff")])[cite: 2]

        self.sig_text.config(
            bg=bg_card,[cite: 2]
            fg=fg_text,[cite: 2]
            insertbackground=fg_text,[cite: 2]
            highlightbackground=border_col,[cite: 2]
            highlightcolor=tree_sel[cite: 2]
        )

        for child in self.ref_frame.winfo_children():[cite: 2]
            if isinstance(child, ttk.Frame):[cite: 2]
                child.configure(style="TFrame")[cite: 2]

    def _open_html_forms_suite(self):
        webbrowser.open_new_tab("https://www.tprfn.net/html-form-suite")[cite: 2]

    def _get_active_contacts(self):
        mode = self.mode_combo.get() if hasattr(self, "mode_combo") else self.current_mode[cite: 2]
        return self.hf_contacts if mode == "HF" else self.fm_contacts[cite: 2]

    def _build_ui(self):
        top_bar = ttk.Frame(self, padding=8)[cite: 2]
        top_bar.pack(side=tk.TOP, fill=tk.X)[cite: 2]

        ttk.Label(top_bar, text="Target BBS:").pack(side=tk.LEFT, padx=(0, 4))[cite: 2]
        self.bbs_combo = ttk.Combobox(top_bar, width=12)[cite: 2]
        self.bbs_combo.pack(side=tk.LEFT, padx=(0, 4))[cite: 2]
        self.bbs_combo.bind("<<ComboboxSelected>>", self._on_bbs_selected)[cite: 2]
        self.attach_context_menu(self.bbs_combo)[cite: 2]

        self.btn_add_bbs = ttk.Button(top_bar, text="[+] Add", command=self.add_bbs_station)[cite: 2]
        self.btn_add_bbs.pack(side=tk.LEFT, padx=1)[cite: 2]

        self.btn_del_bbs = ttk.Button(top_bar, text="[-] Del", command=self.delete_bbs_station)[cite: 2]
        self.btn_del_bbs.pack(side=tk.LEFT, padx=(1, 8))[cite: 2]

        ttk.Label(top_bar, text="Via Digi:").pack(side=tk.LEFT, padx=(0, 4))[cite: 2]
        self.digi_entry = ttk.Entry(top_bar, width=10)[cite: 2]
        self.digi_entry.pack(side=tk.LEFT, padx=(0, 8))[cite: 2]
        self.attach_context_menu(self.digi_entry)[cite: 2]

        self.btn_send_rcv = ttk.Button(top_bar, text="Send/Recv", command=self.start_auto_session)[cite: 2]
        self.btn_send_rcv.pack(side=tk.LEFT, padx=3)[cite: 2]

        self.btn_manual_conn = ttk.Button(top_bar, text="Connect (Term)", command=self.start_manual_session)[cite: 2]
        self.btn_manual_conn.pack(side=tk.LEFT, padx=3)[cite: 2]

        self.btn_disconnect = ttk.Button(top_bar, text="Disconnect", state=tk.DISABLED, command=self.manual_disconnect)[cite: 2]
        self.btn_disconnect.pack(side=tk.LEFT, padx=3)[cite: 2]

        self.btn_listen = ttk.Button(top_bar, text="Mailbox Standby", command=self.toggle_mailbox_listener)[cite: 2]
        self.btn_listen.pack(side=tk.LEFT, padx=3)[cite: 2]

        self.btn_new_msg = ttk.Button(top_bar, text="New Message", command=self.open_composer)[cite: 2]
        self.btn_new_msg.pack(side=tk.LEFT, padx=3)[cite: 2]

        self.btn_forms = ttk.Button(top_bar, text="HTML Forms", command=self._open_html_forms_suite)[cite: 2]
        self.btn_forms.pack(side=tk.LEFT, padx=4)[cite: 2]

        self.btn_theme_toggle = ttk.Button(top_bar, text="[Dark]", width=8, command=self.toggle_theme)[cite: 2]
        self.btn_theme_toggle.pack(side=tk.LEFT, padx=4)[cite: 2]

        self.status_lbl = ttk.Label(top_bar, text="Idle", foreground="gray", font=("Arial", 10, "bold"))[cite: 2]
        self.status_lbl.pack(side=tk.RIGHT, padx=10)[cite: 2]

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X)[cite: 2]

        body_container = ttk.Frame(self)[cite: 2]
        body_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)[cite: 2]

        # Scrollable Left Sidebar
        left_container = ttk.Frame(body_container, width=380)[cite: 2]
        left_container.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))[cite: 2]
        left_container.pack_propagate(False)[cite: 2]

        self.left_canvas = tk.Canvas(left_container, borderwidth=0, highlightthickness=0)[cite: 2]
        self.left_scrollbar = ttk.Scrollbar(left_container, orient=tk.VERTICAL, command=self.left_canvas.yview)[cite: 2]
        
        self.scrollable_left = ttk.Frame(self.left_canvas)[cite: 2]
        self.scrollable_left.bind(
            "<Configure>",
            lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))[cite: 2]
        )

        self.canvas_window = self.left_canvas.create_window((0, 0), window=self.scrollable_left, anchor="nw", width=360)[cite: 2]
        self.left_canvas.configure(yscrollcommand=self.left_scrollbar.set)[cite: 2]

        self.left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)[cite: 2]
        self.left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)[cite: 2]

        def _on_left_mousewheel(event):
            if event.num == 5 or event.delta < 0:[cite: 2]
                self.left_canvas.yview_scroll(2, "units")[cite: 2]
            elif event.num == 4 or event.delta > 0:[cite: 2]
                self.left_canvas.yview_scroll(-2, "units")[cite: 2]
            return "break"[cite: 2]

        self.left_canvas.bind("<MouseWheel>", _on_left_mousewheel)[cite: 2]
        self.left_canvas.bind("<Button-4>", _on_left_mousewheel)[cite: 2]
        self.left_canvas.bind("<Button-5>", _on_left_mousewheel)[cite: 2]

        # Mailboxes
        folder_group = ttk.LabelFrame(self.scrollable_left, text="Mailboxes", padding=6)[cite: 2]
        folder_group.pack(fill=tk.X, pady=(0, 6))[cite: 2]

        folder_frame = ttk.Frame(folder_group)[cite: 2]
        folder_frame.pack(fill=tk.X)[cite: 2]

        self.folder_v_scroll = ttk.Scrollbar(folder_frame, orient=tk.VERTICAL)[cite: 2]
        self.folder_tree = ttk.Treeview(folder_frame, selectmode="browse", show="tree", height=5, yscrollcommand=self.folder_v_scroll.set)[cite: 2]
        self.folder_v_scroll.config(command=self.folder_tree.yview)[cite: 2]

        self.folder_v_scroll.pack(side=tk.RIGHT, fill=tk.Y)[cite: 2]
        self.folder_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)[cite: 2]

        self.f_inbox = self.folder_tree.insert("", "end", text="Inbox (0)", values=("inbox",))[cite: 2]
        self.f_drafts = self.folder_tree.insert("", "end", text="Drafts (0)", values=("drafts",))[cite: 2]
        self.f_outbox = self.folder_tree.insert("", "end", text="Outbox (0)", values=("outbox",))[cite: 2]
        self.f_sent = self.folder_tree.insert("", "end", text="Sent (0)", values=("sent",))[cite: 2]
        self.f_trash = self.folder_tree.insert("", "end", text="Trash (0)", values=("trash",))[cite: 2]
        self.folder_tree.bind("<<TreeviewSelect>>", self._on_folder_select)[cite: 2]
        self.folder_tree.selection_set(self.f_inbox)[cite: 2]

        # Settings
        settings_group = ttk.LabelFrame(self.scrollable_left, text="Station & Modem Settings", padding=6)[cite: 2]
        settings_group.pack(fill=tk.X, pady=(0, 6))[cite: 2]

        ttk.Label(settings_group, text="Modem Type:").pack(anchor=tk.W, pady=(1, 0))[cite: 2]
        self.mode_combo = ttk.Combobox(settings_group, values=["HF", "FM"], state="readonly")[cite: 2]
        self.mode_combo.set(self.current_mode)[cite: 2]
        self.mode_combo.pack(fill=tk.X, pady=(0, 3))[cite: 2]
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)[cite: 2]

        ttk.Label(settings_group, text="My Callsign:").pack(anchor=tk.W, pady=(1, 0))[cite: 2]
        self.my_call_entry = ttk.Entry(settings_group)[cite: 2]
        self.my_call_entry.insert(0, self.current_call)[cite: 2]
        self.my_call_entry.pack(fill=tk.X, pady=(0, 3))[cite: 2]
        self.attach_context_menu(self.my_call_entry)[cite: 2]

        ttk.Label(settings_group, text="Modem Host IP:").pack(anchor=tk.W, pady=(1, 0))[cite: 2]
        self.vara_host_entry = ttk.Entry(settings_group)[cite: 2]
        self.vara_host_entry.insert(0, self.current_host)[cite: 2]
        self.vara_host_entry.pack(fill=tk.X, pady=(0, 3))[cite: 2]
        self.attach_context_menu(self.vara_host_entry)[cite: 2]

        ports_row = ttk.Frame(settings_group)[cite: 2]
        ports_row.pack(fill=tk.X, pady=(0, 3))[cite: 2]
        ttk.Label(ports_row, text="Cmd:").pack(side=tk.LEFT)[cite: 2]
        self.cmd_port_entry = ttk.Entry(ports_row, width=5)[cite: 2]
        self.cmd_port_entry.insert(0, self.current_cmd_port)[cite: 2]
        self.cmd_port_entry.pack(side=tk.LEFT, padx=(2, 4))[cite: 2]
        self.attach_context_menu(self.cmd_port_entry)[cite: 2]

        ttk.Label(ports_row, text="Data:").pack(side=tk.LEFT)[cite: 2]
        self.data_port_entry = ttk.Entry(ports_row, width=5)[cite: 2]
        self.data_port_entry.insert(0, self.current_data_port)[cite: 2]
        self.data_port_entry.pack(side=tk.LEFT, padx=(2, 4))[cite: 2]
        self.attach_context_menu(self.data_port_entry)[cite: 2]

        ttk.Label(ports_row, text="Dwell (s):").pack(side=tk.LEFT)[cite: 2]
        self.dwell_entry = ttk.Entry(ports_row, width=5)[cite: 2]
        active_dwell = self.hf_dwell if self.current_mode == "HF" else self.fm_dwell[cite: 2]
        self.dwell_entry.insert(0, active_dwell)[cite: 2]
        self.dwell_entry.pack(side=tk.LEFT, padx=(2, 0))[cite: 2]
        self.attach_context_menu(self.dwell_entry)[cite: 2]

        ttk.Label(settings_group, text="Bandwidth / Mode:").pack(anchor=tk.W, pady=(1, 0))[cite: 2]
        bw_options = ["BW500", "BW2300", "BW2750"] if self.current_mode == "HF" else ["NARROW", "WIDE"][cite: 2]
        self.bw_combo = ttk.Combobox(settings_group, values=bw_options, state="readonly")[cite: 2]
        self.bw_combo.set(self.current_bw)[cite: 2]
        self.bw_combo.pack(fill=tk.X, pady=(0, 3))[cite: 2]

        ttk.Label(settings_group, text="Station Signature (6 Lines):").pack(anchor=tk.W, pady=(1, 0))[cite: 2]
        self.sig_text = scrolledtext.ScrolledText(settings_group, height=5, font=("Courier", 9))[cite: 2]
        self.sig_text.insert("1.0", self.current_signature)[cite: 2]
        self.sig_text.pack(fill=tk.X, expand=False, pady=(0, 2))[cite: 2]
        self.attach_context_menu(self.sig_text)[cite: 2]

        # 3-Column Node Commands Menu
        node_group = ttk.LabelFrame(self.scrollable_left, text="Node & BBS Commands", padding=6)[cite: 2]
        node_group.pack(fill=tk.X, pady=(0, 6))[cite: 2]

        node_group.columnconfigure(0, weight=1)[cite: 2]
        node_group.columnconfigure(1, weight=1)[cite: 2]
        node_group.columnconfigure(2, weight=1)[cite: 2]

        grid_commands = [
            ("Nodes (N)", "N", 0, 0),[cite: 2]
            ("Routes (R)", "R", 1, 0),[cite: 2]
            ("Links (L)", "L", 2, 0),[cite: 2]
            ("Stats (S)", "S", 3, 0),[cite: 2]
            ("Users (U)", "U", 0, 1),[cite: 2]
            ("Chat (CHAT)", "CHAT", 1, 1),[cite: 2]
            ("BBS (BBS)", "BBS", 2, 1),[cite: 2]
            ("Leave (B)", "B", 3, 1),[cite: 2]
            ("List (L)", "L", 0, 2),[cite: 2]
            ("List Mine (LM)", "LM", 1, 2),[cite: 2]
            ("Read Mine (RM)", "RM", 2, 2),[cite: 2]
            ("Kill Mine (KM)", "KM", 3, 2)[cite: 2]
        ]

        for label_text, cmd_text, r, c in grid_commands:[cite: 2]
            btn = ttk.Button(
                node_group,
                text=label_text,
                command=lambda cmd=cmd_text: self.send_node_command(cmd)[cite: 2]
            )
            btn.grid(row=r, column=c, padx=2, pady=2, sticky=tk.EW)[cite: 2]

        ttk.Separator(node_group, orient=tk.HORIZONTAL).grid(row=4, column=0, columnspan=3, pady=(6, 4), sticky=tk.EW)[cite: 2]

        self.ref_frame = ttk.LabelFrame(node_group, text="Command Quick Reference", padding=4)[cite: 2]
        self.ref_frame.grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=(2, 0))[cite: 2]

        guide_lines = [
            ("Read", "Dbl-Click msg# in Term"),[cite: 2]
            ("Personal", "SP callsign"),[cite: 2]
            ("Bulletin", "SB ha route"),[cite: 2]
            ("Msg Reply", "SR msg#"),[cite: 2]
            ("NTS", "ST zip & st")[cite: 2]
        ]

        for desc, syntax in guide_lines:[cite: 2]
            row_frame = ttk.Frame(self.ref_frame)[cite: 2]
            row_frame.pack(fill=tk.X, pady=1)[cite: 2]
            ttk.Label(row_frame, text=f"* {desc}:", font=("Arial", 8, "bold")).pack(side=tk.LEFT)[cite: 2]
            ttk.Label(row_frame, text=syntax, font=("Consolas", 8, "bold"), foreground="#0284c7").pack(side=tk.RIGHT)[cite: 2]

        # Right Column
        right_paned = ttk.PanedWindow(body_container, orient=tk.VERTICAL)[cite: 2]
        right_paned.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)[cite: 2]

        msg_list_frame = ttk.LabelFrame(right_paned, text="Received Messages", padding=4)[cite: 2]
        right_paned.add(msg_list_frame, weight=1)[cite: 2]

        list_toolbar = ttk.Frame(msg_list_frame)[cite: 2]
        list_toolbar.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))[cite: 2]
        self.btn_del_msg = ttk.Button(list_toolbar, text="[-] Delete Message", command=self.delete_selected_message)[cite: 2]
        self.btn_del_msg.pack(side=tk.LEFT)[cite: 2]

        table_container = ttk.Frame(msg_list_frame)[cite: 2]
        table_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)[cite: 2]

        self.table_v_scroll = ttk.Scrollbar(table_container, orient=tk.VERTICAL)[cite: 2]
        self.table_v_scroll.pack(side=tk.RIGHT, fill=tk.Y)[cite: 2]

        cols = ("msg_num", "from_to", "subject", "date")[cite: 2]
        self.msg_table = ttk.Treeview(
            table_container,
            columns=cols,
            show="headings",
            selectmode="browse",
            yscrollcommand=self.table_v_scroll.set[cite: 2]
        )
        self.table_v_scroll.config(command=self.msg_table.yview)[cite: 2]

        self.msg_table.heading("msg_num", text="#")[cite: 2]
        self.msg_table.heading("from_to", text="From / To")[cite: 2]
        self.msg_table.heading("subject", text="Subject")[cite: 2]
        self.msg_table.heading("date", text="Date / Status")[cite: 2]

        self.msg_table.column("msg_num", width=70, minwidth=50, anchor=tk.CENTER)[cite: 2]
        self.msg_table.column("from_to", width=180, minwidth=140)
        self.msg_table.column("subject", width=380, minwidth=200)
        self.msg_table.column("date", width=130, minwidth=100, anchor=tk.CENTER)[cite: 2]

        self.msg_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)[cite: 2]

        def _on_tree_mousewheel(event):
            if event.num == 5 or event.delta < 0:[cite: 2]
                self.msg_table.yview_scroll(1, "units")[cite: 2]
            elif event.num == 4 or event.delta > 0:[cite: 2]
                self.msg_table.yview_scroll(-1, "units")[cite: 2]
            return "break"[cite: 2]

        self.msg_table.bind("<MouseWheel>", _on_tree_mousewheel)[cite: 2]
        self.msg_table.bind("<Button-4>", _on_tree_mousewheel)[cite: 2]
        self.msg_table.bind("<Button-5>", _on_tree_mousewheel)[cite: 2]

        self.msg_table.bind("<<TreeviewSelect>>", self._on_msg_select)[cite: 2]
        self.msg_table.bind("<Double-1>", self._on_msg_double_click)[cite: 2]
        self.msg_table.bind("<Delete>", lambda e: self.delete_selected_message())[cite: 2]

        term_frame = ttk.LabelFrame(right_paned, text="Live BBS Terminal & Traffic Monitor", padding=4)[cite: 2]
        right_paned.add(term_frame, weight=2)[cite: 2]

        input_bar = ttk.Frame(term_frame)[cite: 2]
        input_bar.pack(side=tk.TOP, fill=tk.X, padx=2, pady=(2, 4))[cite: 2]

        ttk.Label(input_bar, text="Type-Ahead:").pack(side=tk.LEFT, padx=(0, 4))[cite: 2]
        self.cmd_entry = ttk.Entry(input_bar)[cite: 2]
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))[cite: 2]
        self.cmd_entry.bind("<Return>", lambda event: self.send_manual_command())[cite: 2]
        self.attach_context_menu(self.cmd_entry)[cite: 2]

        self.btn_send_cmd = ttk.Button(input_bar, text="Send Enter", width=10, command=self.send_manual_command)[cite: 2]
        self.btn_send_cmd.pack(side=tk.RIGHT)[cite: 2]

        self.term_view = scrolledtext.ScrolledText(
            term_frame,
            wrap=tk.WORD,
            bg="#0f141c",
            fg="#22c55e",
            insertbackground="#22c55e",
            font=("Consolas", 10)
        )[cite: 2]
        self.term_view.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))[cite: 2]
        self.attach_context_menu(self.term_view)[cite: 2]
        
        self.term_view.bind("<Double-Button-1>", self._on_term_double_click)[cite: 2]
        self.term_print("[*] Terminal ready. Double-click any message number to fetch & read.\n")[cite: 2]

    def _on_term_double_click(self, event):
        index = self.term_view.index(f"@{event.x},{event.y}")[cite: 2]
        line_start = f"{index.split('.')[0]}.0"[cite: 2]
        line_end = f"{index.split('.')[0]}.end"[cite: 2]
        line_text = self.term_view.get(line_start, line_end).strip()[cite: 2]

        m = re.match(r"^(\d{1,7})\b", line_text)[cite: 2]
        if not m:
            word = self.term_view.get(f"{index} wordstart", f"{index} wordend").strip()[cite: 2]
            if word.isdigit() and len(word) >= 2:[cite: 2]
                m = re.match(r"^(\d{1,7})$", word)[cite: 2]

        if m:
            msg_num = m.group(1)[cite: 2]
            local_msg = next((msg for msg in self.inbox_msgs if str(msg.get("id")) == str(msg_num)), None)[cite: 2]

            if local_msg:
                self.term_print(f"\n[*] Displaying cached message #{msg_num} from Inbox:\n")[cite: 2]
                header = f"\n{'='*55}\nFrom:    {local_msg.get('from', 'BBS')}\nTo:      {local_msg.get('to', self.current_call)}\nSubject: {local_msg.get('subj', '')}\nDate:    {local_msg.get('date', '')}\n{'-'*55}\n"
                self.term_print(header + local_msg.get("body", "") + f"\n{'='*55}\n")[cite: 2]
            else:
                if self.worker_thread and self.worker_thread.is_alive() and self.data_sock:[cite: 2]
                    self.term_print(f"\n[*] Fetching message #{msg_num} from remote BBS...\n")[cite: 2]
                    self.tx_manual_queue.put(f"R {msg_num}")[cite: 2]
                else:
                    self.term_print(f"\n[!] Cannot fetch #{msg_num}: Not connected to BBS. Connect first to read.\n")[cite: 2]
            return "break"[cite: 2]

    def _refresh_bbs_dropdown(self):
        active_contacts = self._get_active_contacts()[cite: 2]
        bbs_names = [c["bbs"] for c in active_contacts][cite: 2]
        self.bbs_combo["values"] = bbs_names[cite: 2]

        default_dwell = self.hf_dwell if self.current_mode == "HF" else self.fm_dwell[cite: 2]

        if bbs_names:
            first_c = active_contacts[0][cite: 2]
            self.bbs_combo.set(first_c["bbs"])[cite: 2]
            self.digi_entry.delete(0, tk.END)[cite: 2]
            self.digi_entry.insert(0, first_c.get("digi", ""))[cite: 2]
            
            self.dwell_entry.delete(0, tk.END)[cite: 2]
            self.dwell_entry.insert(0, str(first_c.get("dwell", default_dwell)))[cite: 2]
        else:
            self.bbs_combo.set("")[cite: 2]
            self.digi_entry.delete(0, tk.END)[cite: 2]
            self.dwell_entry.delete(0, tk.END)[cite: 2]
            self.dwell_entry.insert(0, default_dwell)[cite: 2]

    def _on_mode_change(self, event=None):
        new_mode = self.mode_combo.get().strip().upper()[cite: 2]
        
        # Save outgoing mode dwell value before swapping
        if hasattr(self, "dwell_entry"):[cite: 2]
            old_dwell = self.dwell_entry.get().strip()[cite: 2]
            if self.current_mode == "HF":[cite: 2]
                self.hf_dwell = old_dwell[cite: 2]
            else:
                self.fm_dwell = old_dwell[cite: 2]

        self.current_mode = new_mode[cite: 2]

        restart_listener = self.listener_active[cite: 2]
        if restart_listener:[cite: 2]
            self._stop_listener_service()[cite: 2]

        if new_mode == "HF":[cite: 2]
            self.cmd_port_entry.delete(0, tk.END)[cite: 2]
            self.cmd_port_entry.insert(0, "8358")[cite: 2]
            self.data_port_entry.delete(0, tk.END)[cite: 2]
            self.data_port_entry.insert(0, "8359")[cite: 2]
            self.dwell_entry.delete(0, tk.END)[cite: 2]
            self.dwell_entry.insert(0, self.hf_dwell)[cite: 2]
            self.bw_combo.config(values=["BW500", "BW2300", "BW2750"])[cite: 2]
            self.bw_combo.set("BW500")[cite: 2]
            self.term_print(f"[*] Switched to VARA HF (Ports 8358/8359, BW500, Default Dwell: {self.hf_dwell}s).\n")[cite: 2]
        else:
            self.cmd_port_entry.delete(0, tk.END)[cite: 2]
            self.cmd_port_entry.insert(0, "8300")[cite: 2]
            self.data_port_entry.delete(0, tk.END)[cite: 2]
            self.data_port_entry.insert(0, "8301")[cite: 2]
            self.dwell_entry.delete(0, tk.END)[cite: 2]
            self.dwell_entry.insert(0, self.fm_dwell)[cite: 2]
            self.bw_combo.config(values=["NARROW", "WIDE"])[cite: 2]
            self.bw_combo.set("NARROW")[cite: 2]
            self.term_print(f"[*] Switched to VARA FM (Ports 8300/8301, NARROW, Default Dwell: {self.fm_dwell}s).\n")[cite: 2]

        self._refresh_bbs_dropdown()[cite: 2]
        if restart_listener:[cite: 2]
            self._start_listener_service()[cite: 2]

    def _on_bbs_selected(self, event=None):
        selected_bbs = self.bbs_combo.get().strip().upper()[cite: 2]
        active_contacts = self._get_active_contacts()[cite: 2]
        default_dwell = self.hf_dwell if self.current_mode == "HF" else self.fm_dwell[cite: 2]

        for contact in active_contacts:[cite: 2]
            if contact["bbs"] == selected_bbs:[cite: 2]
                self.digi_entry.delete(0, tk.END)[cite: 2]
                self.digi_entry.insert(0, contact.get("digi", ""))[cite: 2]
                
                # Load the station's saved dwell into the UI entry
                station_dwell = str(contact.get("dwell", default_dwell))[cite: 2]
                self.dwell_entry.delete(0, tk.END)[cite: 2]
                self.dwell_entry.insert(0, station_dwell)[cite: 2]
                break[cite: 2]

    def add_bbs_station(self):
        new_bbs = self.bbs_combo.get().strip().upper()[cite: 2]
        digi = self.digi_entry.get().strip().upper()[cite: 2]
        mode = self.mode_combo.get()[cite: 2]
        dwell_str = self.dwell_entry.get().strip()[cite: 2]

        if not new_bbs:[cite: 2]
            messagebox.showwarning("Warning", "Enter a callsign in the Target BBS box to add.")[cite: 2]
            return

        active_contacts = self._get_active_contacts()[cite: 2]
        updated = False[cite: 2]
        for contact in active_contacts:[cite: 2]
            if contact["bbs"] == new_bbs:[cite: 2]
                contact["digi"] = digi[cite: 2]
                contact["dwell"] = dwell_str[cite: 2]
                updated = True[cite: 2]
                break[cite: 2]

        if not updated:[cite: 2]
            active_contacts.append({"bbs": new_bbs, "digi": digi, "dwell": dwell_str})[cite: 2]

        self.bbs_combo["values"] = [c["bbs"] for c in active_contacts][cite: 2]
        self.bbs_combo.set(new_bbs)[cite: 2]
        self._save_data()[cite: 2]

        digi_info = f" via {digi}" if digi else ""[cite: 2]
        self.term_print(f"[*] Saved {new_bbs}{digi_info} (Dwell: {dwell_str}s) to {mode} contacts list.\n")[cite: 2]

    def delete_bbs_station(self):
        selected_bbs = self.bbs_combo.get().strip().upper()[cite: 2]
        mode = self.mode_combo.get()[cite: 2]
        active_contacts = self._get_active_contacts()[cite: 2]

        match = None[cite: 2]
        for contact in active_contacts:[cite: 2]
            if contact["bbs"] == selected_bbs:[cite: 2]
                match = contact[cite: 2]
                break[cite: 2]

        if match:[cite: 2]
            active_contacts.remove(match)[cite: 2]
            self._save_data()[cite: 2]
            self._refresh_bbs_dropdown()[cite: 2]
            self.term_print(f"[*] Removed {selected_bbs} from {mode} contacts list.\n")[cite: 2]
        else:
            messagebox.showwarning("Warning", "Selected BBS not found in current list.")[cite: 2]

    def term_print(self, text):
        def _append():
            clean_text = text.replace("\r\n", "\n").replace("\r", "\n")[cite: 2]
            self.term_view.insert(tk.END, clean_text)[cite: 2]
            self.term_view.see(tk.END)[cite: 2]

        if threading.current_thread() is threading.main_thread():[cite: 2]
            _append()[cite: 2]
        else:
            self.after(0, _append)[cite: 2]

    def send_manual_command(self):
        cmd = self.cmd_entry.get().strip()[cite: 2]
        if not cmd:[cite: 2]
            return

        self.cmd_entry.delete(0, tk.END)[cite: 2]
        self.term_print(f">>> {cmd}\n")[cite: 2]

        if self.worker_thread and self.worker_thread.is_alive() and self.data_sock:[cite: 2]
            self.tx_manual_queue.put(cmd)[cite: 2]
        elif self.mailbox_in_session and self.listener_data_sock:[cite: 2]
            self._send_listener_data(f"\n[SYSOP]: {cmd}\r\n")[cite: 2]
        else:
            self.term_print("[!] Not connected to BBS or Caller. Command not sent.\n")[cite: 2]

    def send_node_command(self, cmd):
        self.term_print(f">>> {cmd}\n")[cite: 2]
        if self.worker_thread and self.worker_thread.is_alive() and self.data_sock:[cite: 2]
            self.tx_manual_queue.put(cmd)[cite: 2]
        else:
            self.term_print("[!] Not connected to Node/BBS. Connect first to run this command.\n")[cite: 2]

    def _update_folder_counts(self):
        self.folder_tree.item(self.f_inbox, text=f"Inbox ({len(self.inbox_msgs)})")[cite: 2]
        self.folder_tree.item(self.f_drafts, text=f"Drafts ({len(self.draft_msgs)})")[cite: 2]
        self.folder_tree.item(self.f_outbox, text=f"Outbox ({len(self.outbox_msgs)})")[cite: 2]
        self.folder_tree.item(self.f_sent, text=f"Sent ({len(self.sent_msgs)})")[cite: 2]
        self.folder_tree.item(self.f_trash, text=f"Trash ({len(self.trash_msgs)})")[cite: 2]

    def _get_active_store(self):
        selected = self.folder_tree.selection()[cite: 2]
        if not selected:[cite: 2]
            return "inbox", self.inbox_msgs[cite: 2]
        tag = self.folder_tree.item(selected[0], "values")[0][cite: 2]
        stores = {
            "inbox": self.inbox_msgs,[cite: 2]
            "drafts": self.draft_msgs,[cite: 2]
            "outbox": self.outbox_msgs,[cite: 2]
            "sent": self.sent_msgs,[cite: 2]
            "trash": self.trash_msgs[cite: 2]
        }
        return tag, stores.get(tag, self.inbox_msgs)[cite: 2]

    def _on_folder_select(self, event):
        tag, store = self._get_active_store()[cite: 2]
        my_call = self.my_call_entry.get().strip().upper() if hasattr(self, "my_call_entry") else self.current_call

        for item in self.msg_table.get_children():[cite: 2]
            self.msg_table.delete(item)[cite: 2]

        for i, msg in enumerate(store):[cite: 2]
            if tag == "inbox":[cite: 2]
                status = msg.get("date", "")[cite: 2]
                m_from = msg.get("from", "BBS")
                m_to = msg.get("to", my_call)
                from_to = f"{m_from} -> {m_to}"
                num_col = msg.get("id", str(i+1))[cite: 2]
            elif tag == "drafts":[cite: 2]
                status = "Draft"[cite: 2]
                from_to = f"{msg.get('type', 'SP')}: {msg.get('to', '(No Recipient)')}"[cite: 2]
                num_col = f"D-{i+1}"[cite: 2]
            elif tag == "outbox":[cite: 2]
                status = "Queued"[cite: 2]
                from_to = f"{msg.get('type', 'SP')}: {msg.get('to', '')}"[cite: 2]
                num_col = "OUT"[cite: 2]
            elif tag == "sent":[cite: 2]
                status = msg.get("date", "Sent")[cite: 2]
                from_to = f"{msg.get('type', 'SP')}: {msg.get('to', '')}"[cite: 2]
                num_col = f"S-{i+1}"[cite: 2]
            else:
                status = "Deleted"[cite: 2]
                m_from = msg.get("from", "")
                m_to = msg.get("to", "")
                from_to = f"{m_from} -> {m_to}" if m_from and m_to else (m_from or m_to)
                num_col = "DEL"[cite: 2]

            self.msg_table.insert("", "end", iid=str(i), values=(num_col, from_to, msg.get("subj", ""), status))[cite: 2]

    def _on_msg_select(self, event):
        selected = self.msg_table.selection()[cite: 2]
        if not selected:[cite: 2]
            return
        idx = int(selected[0])[cite: 2]
        tag, store = self._get_active_store()[cite: 2]

        if idx < len(store):[cite: 2]
            msg = store[idx][cite: 2]
            my_call = self.my_call_entry.get().strip().upper()[cite: 2]
            m_type = msg.get('type', 'SP')
            m_from = msg.get('from', my_call)
            m_to = msg.get('to', my_call if tag == 'inbox' else '')
            header = f"\n{'='*55}\nType:    {m_type}\nFrom:    {m_from}\nTo:      {m_to}\nSubject: {msg.get('subj', '')}\nDate:    {msg.get('date', '')}\n{'-'*55}\n"
            self.term_print(header + msg.get("body", "") + f"\n{'='*55}\n")[cite: 2]

    def _on_msg_double_click(self, event):
        tag, store = self._get_active_store()[cite: 2]
        selected = self.msg_table.selection()[cite: 2]
        if not selected:[cite: 2]
            return
        idx = int(selected[0])[cite: 2]
        if tag == "drafts" and idx < len(store):[cite: 2]
            draft = store.pop(idx)[cite: 2]
            self._save_data()[cite: 2]
            self._update_folder_counts()[cite: 2]
            self._on_folder_select(None)[cite: 2]
            self.open_composer(
                pre_to=draft.get("to", ""),[cite: 2]
                pre_subj=draft.get("subj", ""),[cite: 2]
                pre_body=draft.get("body", ""),[cite: 2]
                pre_type=draft.get("type", "SP")[cite: 2]
            )

    def delete_selected_message(self):
        selected = self.msg_table.selection()[cite: 2]
        if not selected:[cite: 2]
            messagebox.showinfo("Select Message", "Please select a message to delete.")[cite: 2]
            return

        idx = int(selected[0])[cite: 2]
        tag, store = self._get_active_store()[cite: 2]

        if idx < len(store):[cite: 2]
            msg = store.pop(idx)[cite: 2]
            if tag != "trash":[cite: 2]
                self.trash_msgs.append(msg)[cite: 2]
                self.term_print(f"[*] Moved message to Trash.\n")[cite: 2]
            else:
                self.term_print(f"[*] Permanently deleted message from Trash.\n")[cite: 2]

            self._save_data()[cite: 2]
            self._update_folder_counts()[cite: 2]
            self._on_folder_select(None)[cite: 2]

    def update_status(self, text, color="black"):
        self.status_lbl.config(text=text, foreground=color)[cite: 2]

    # ==========================================
    # COMPOSER
    # ==========================================
    def open_composer(self, pre_to="", pre_subj="", pre_body=None, pre_type="SP"):
        win = tk.Toplevel(self)[cite: 2]
        win.title("Compose Message")[cite: 2]
        win.geometry("640x580")[cite: 2]

        is_dark = (self.theme_mode == "dark")[cite: 2]
        win_bg = "#1e222b" if is_dark else "#f3f4f6"[cite: 2]
        win_card = "#282c34" if is_dark else "#ffffff"[cite: 2]
        win_fg = "#e5e7eb" if is_dark else "#111827"[cite: 2]
        border_col = "#3f4451" if is_dark else "#d1d5db"[cite: 2]
        win.configure(bg=win_bg)[cite: 2]

        f = ttk.Frame(win, padding=12)[cite: 2]
        f.pack(fill=tk.BOTH, expand=True)[cite: 2]

        type_row = ttk.Frame(f)[cite: 2]
        type_row.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 6))[cite: 2]

        ttk.Label(type_row, text="Message Type:").pack(side=tk.LEFT, padx=(0, 8))[cite: 2]
        msg_type_var = tk.StringVar(value=pre_type)[cite: 2]

        rb_sp = ttk.Radiobutton(type_row, text="SP (Private)", variable=msg_type_var, value="SP")[cite: 2]
        rb_sp.pack(side=tk.LEFT, padx=6)[cite: 2]

        rb_sb = ttk.Radiobutton(type_row, text="SB (Bulletin)", variable=msg_type_var, value="SB")[cite: 2]
        rb_sb.pack(side=tk.LEFT, padx=6)[cite: 2]

        to_label = ttk.Label(f, text="To Callsign:")[cite: 2]
        to_label.grid(row=1, column=0, sticky=tk.W, pady=4)[cite: 2]

        to_row = ttk.Frame(f)[cite: 2]
        to_row.grid(row=1, column=1, sticky=tk.EW, pady=4)[cite: 2]

        to_combo = ttk.Combobox(to_row, width=24, values=self.recent_recipients)[cite: 2]
        to_combo.set(pre_to)[cite: 2]
        to_combo.pack(side=tk.LEFT, padx=(0, 6))[cite: 2]
        self.attach_context_menu(to_combo)[cite: 2]

        def add_to_history():
            entry_val = to_combo.get().strip().upper()[cite: 2]
            if not entry_val:[cite: 2]
                return
            if entry_val not in self.recent_recipients:[cite: 2]
                self.recent_recipients.insert(0, entry_val)[cite: 2]
                self.recent_recipients = self.recent_recipients[:30][cite: 2]
                to_combo["values"] = self.recent_recipients[cite: 2]
                self._save_data()[cite: 2]
            to_combo.set(entry_val)[cite: 2]

        def del_from_history():
            entry_val = to_combo.get().strip().upper()[cite: 2]
            if entry_val in self.recent_recipients:[cite: 2]
                self.recent_recipients.remove(entry_val)[cite: 2]
                to_combo["values"] = self.recent_recipients[cite: 2]
                to_combo.set("")[cite: 2]
                self._save_data()[cite: 2]

        btn_add_to = ttk.Button(to_row, text="[+] Add", width=8, command=add_to_history)[cite: 2]
        btn_add_to.pack(side=tk.LEFT, padx=2)[cite: 2]

        btn_del_to = ttk.Button(to_row, text="[-] Del", width=8, command=del_from_history)[cite: 2]
        btn_del_to.pack(side=tk.LEFT, padx=2)[cite: 2]

        def _on_type_changed(*args):
            if msg_type_var.get() == "SB":[cite: 2]
                to_label.config(text="Bulletin @ Route:")[cite: 2]
            else:
                to_label.config(text="To Callsign:")[cite: 2]

        msg_type_var.trace_add("write", _on_type_changed)[cite: 2]
        _on_type_changed()[cite: 2]

        ttk.Label(f, text="Subject:").grid(row=2, column=0, sticky=tk.W, pady=4)[cite: 2]
        subj_entry = ttk.Entry(f, width=48)[cite: 2]
        subj_entry.insert(0, pre_subj)[cite: 2]
        subj_entry.grid(row=2, column=1, sticky=tk.W, pady=4)[cite: 2]
        self.attach_context_menu(subj_entry)[cite: 2]

        ttk.Label(f, text="Body:").grid(row=3, column=0, sticky=tk.NW, pady=4)[cite: 2]
        body_text = scrolledtext.ScrolledText(
            f,
            width=48,[cite: 2]
            height=14,[cite: 2]
            font=("Courier", 10),[cite: 2]
            bg=win_card,[cite: 2]
            fg=win_fg,[cite: 2]
            insertbackground=win_fg,[cite: 2]
            highlightbackground=border_col[cite: 2]
        )
        body_text.grid(row=3, column=1, sticky=tk.NSEW, pady=4)[cite: 2]
        f.grid_rowconfigure(3, weight=1)[cite: 2]
        f.grid_columnconfigure(1, weight=1)[cite: 2]
        self.attach_context_menu(body_text)

        if pre_body is not None:[cite: 2]
            body_text.insert("1.0", pre_body)[cite: 2]
        else:
            active_sig = self.sig_text.get("1.0", tk.END).strip()[cite: 2]
            if active_sig:[cite: 2]
                body_text.insert("1.0", f"\n\n{active_sig}")[cite: 2]
            body_text.mark_set("insert", "1.0")[cite: 2]

        btn_row = ttk.Frame(f)[cite: 2]
        btn_row.grid(row=4, column=1, sticky=tk.E, pady=10)[cite: 2]

        def _remember_recipient(addr):
            clean_addr = addr.strip().upper()[cite: 2]
            if clean_addr and clean_addr not in self.recent_recipients:[cite: 2]
                self.recent_recipients.insert(0, clean_addr)[cite: 2]
                self.recent_recipients = self.recent_recipients[:30][cite: 2]
                to_combo["values"] = self.recent_recipients[cite: 2]

        def save_draft():
            dest = to_combo.get().strip().upper()[cite: 2]
            subj = subj_entry.get().strip()[cite: 2]
            body = body_text.get("1.0", tk.END).strip()[cite: 2]
            m_type = msg_type_var.get()[cite: 2]

            _remember_recipient(dest)[cite: 2]
            self.draft_msgs.append({"type": m_type, "to": dest, "subj": subj, "body": body})[cite: 2]
            self._save_data()[cite: 2]
            self._update_folder_counts()[cite: 2]
            self._on_folder_select(None)[cite: 2]
            self.term_print(f"[*] Saved {m_type} message draft.\n")[cite: 2]
            win.destroy()[cite: 2]

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
            my_call = self.my_call_entry.get().strip().upper()

            # Append station signature if defined
            active_sig = self.sig_text.get("1.0", tk.END).strip()
            if active_sig and active_sig.splitlines()[0] not in body:
                body = f"{body}\n\n{active_sig}"

            self.inbox_msgs.append({
                "id": next_id,
                "from": my_call,
                "to": dest,
                "subj": subj,
                "date": time.strftime("%m/%d %H:%M"),
                "body": body,
                "type": m_type
            })
            self._save_data()
            self._update_folder_counts()
            self._on_folder_select(None)
            self.term_print(f"[+] Deposited message #{next_id} for {dest} into local PBBS.\n")
            win.destroy()

        def queue_outbound():
            dest = to_combo.get().strip().upper()[cite: 2]
            subj = subj_entry.get().strip()[cite: 2]
            body = body_text.get("1.0", tk.END).strip()[cite: 2]
            m_type = msg_type_var.get()[cite: 2]
            if not dest or not subj:[cite: 2]
                messagebox.showerror("Error", "Callsign/Target and Subject required to send.", parent=win)[cite: 2]
                return

            _remember_recipient(dest)[cite: 2]
            self.outbox_msgs.append({"type": m_type, "to": dest, "subj": subj, "body": body})[cite: 2]
            self._save_data()[cite: 2]
            self._update_folder_counts()[cite: 2]
            self._on_folder_select(None)[cite: 2]
            self.term_print(f"[*] Queued outbound {m_type} message for {dest} to Outbox.\n")[cite: 2]
            win.destroy()[cite: 2]

        ttk.Button(btn_row, text="Save as Draft", command=save_draft).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_row, text="Deposit to PBBS", command=deposit_to_pbbs).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_row, text="Queue to Outbox (Remote BBS)", command=queue_outbound).pack(side=tk.LEFT, padx=3)

    # ==========================================
    # SESSION LAUNCHERS
    # ==========================================
    def _prepare_session(self):
        if self.mailbox_in_session:[cite: 2]
            messagebox.showwarning("Busy", "A caller is currently connected to your Mailbox.")[cite: 2]
            return None[cite: 2]

        if self.worker_thread and self.worker_thread.is_alive():[cite: 2]
            messagebox.showwarning("Busy", "A connection session is already active.")[cite: 2]
            return None[cite: 2]

        if self.listener_active:[cite: 2]
            self._stop_listener_service()[cite: 2]

        target_bbs = self.bbs_combo.get().strip().upper()[cite: 2]
        if not target_bbs:[cite: 2]
            messagebox.showerror("Error", "Please select or enter a Target BBS.")[cite: 2]
            return None[cite: 2]

        raw_digi = self.digi_entry.get().strip().upper()[cite: 2]
        my_call = self.my_call_entry.get().strip().upper()[cite: 2]
        host = self.vara_host_entry.get().strip()[cite: 2]
        bw = self.bw_combo.get().strip()[cite: 2]
        signature = self.sig_text.get("1.0", tk.END).strip()[cite: 2]
        mode = self.mode_combo.get().strip().upper()[cite: 2]

        try:
            cmd_port = int(self.cmd_port_entry.get().strip())[cite: 2]
            data_port = int(self.data_port_entry.get().strip())[cite: 2]
        except ValueError:
            messagebox.showerror("Error", "Command and Data ports must be numbers.")[cite: 2]
            return None[cite: 2]

        try:
            dwell_val = float(self.dwell_entry.get().strip())[cite: 2]
            if dwell_val < 0:[cite: 2]
                dwell_val = 1.5[cite: 2]
        except ValueError:
            dwell_val = 20.0 if mode == "HF" else 1.5[cite: 2]

        if mode == "HF":[cite: 2]
            self.hf_dwell = str(dwell_val)[cite: 2]
        else:
            self.fm_dwell = str(dwell_val)[cite: 2]

        # Update contact record with current digi and current station-specific dwell
        active_contacts = self._get_active_contacts()[cite: 2]
        updated = False[cite: 2]
        for contact in active_contacts:[cite: 2]
            if contact["bbs"] == target_bbs:[cite: 2]
                contact["digi"] = raw_digi[cite: 2]
                contact["dwell"] = str(dwell_val)[cite: 2]
                updated = True[cite: 2]
                break[cite: 2]
        if not updated:[cite: 2]
            active_contacts.append({"bbs": target_bbs, "digi": raw_digi, "dwell": str(dwell_val)})[cite: 2]
            self.bbs_combo["values"] = [c["bbs"] for c in active_contacts][cite: 2]

        self._save_data()[cite: 2]

        self.title(f"VARA HF/FM Mail & Terminal Client - [{my_call}] 30")
        self.abort_requested = False[cite: 2]
        while not self.tx_manual_queue.empty():[cite: 2]
            self.tx_manual_queue.get_nowait()[cite: 2]

        self.btn_send_rcv.config(state=tk.DISABLED)[cite: 2]
        self.btn_manual_conn.config(state=tk.DISABLED)[cite: 2]
        self.btn_disconnect.config(state=tk.NORMAL)[cite: 2]
        self.btn_listen.config(state=tk.DISABLED)[cite: 2]

        return host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call, signature, mode, dwell_val[cite: 2]

    def start_auto_session(self):
        params = self._prepare_session()[cite: 2]
        if not params:[cite: 2]
            return
        self.worker_thread = threading.Thread(target=self._run_auto_session, args=params, daemon=True)[cite: 2]
        self.worker_thread.start()[cite: 2]

    def start_manual_session(self):
        params = self._prepare_session()[cite: 2]
        if not params:[cite: 2]
            return
        # Omit dwell_val for interactive terminal sessions
        self.worker_thread = threading.Thread(target=self._run_manual_session, args=params[:-1], daemon=True)[cite: 2]
        self.worker_thread.start()[cite: 2]

    # ==========================================
    # VARA HF / FM OUTBOUND NETWORKING ENGINE
    # ==========================================
    def _connect_rf(self, host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call):
        self.update_status(f"Connecting to VARA ({host})...", "orange")[cite: 2]
        self.term_print(f"[*] Opening sockets to {host} (Cmd:{cmd_port}, Data:{data_port})...\n")[cite: 2]

        self.cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)[cite: 2]
        self.cmd_sock.settimeout(5.0)[cite: 2]
        self.cmd_sock.connect((host, cmd_port))[cite: 2]

        self.data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)[cite: 2]
        self.data_sock.settimeout(5.0)[cite: 2]
        self.data_sock.connect((host, data_port))[cite: 2]

        self.cmd_sock.sendall(f"MYCALL {my_call}\r".encode("ascii"))[cite: 2]
        time.sleep(0.1)[cite: 2]
        self.cmd_sock.sendall(f"{bw}\r".encode("ascii"))[cite: 2]
        time.sleep(0.1)[cite: 2]

        if self.abort_requested:[cite: 2]
            return False[cite: 2]

        clean_digi = re.sub(r'^(VIA|V)\s+', '', raw_digi.strip(), flags=re.IGNORECASE)[cite: 2]

        if clean_digi:[cite: 2]
            conn_cmd = f"CONNECT {my_call} {target_bbs} VIA {clean_digi}\r"[cite: 2]
            disp_call = f"{target_bbs} via {clean_digi}"[cite: 2]
        else:
            conn_cmd = f"CONNECT {my_call} {target_bbs}\r"[cite: 2]
            disp_call = target_bbs[cite: 2]

        self.update_status(f"Calling {disp_call}...", "blue")[cite: 2]
        self.term_print(f"[*] Issuing RF command: {conn_cmd.strip()} ({bw})...\n")[cite: 2]
        self.cmd_sock.sendall(conn_cmd.encode("ascii"))[cite: 2]

        connected = False[cite: 2]
        start_t = time.time()[cite: 2]
        self.cmd_sock.settimeout(1.0)[cite: 2]

        while time.time() - start_t < 60:[cite: 2]
            if self.abort_requested:[cite: 2]
                return False[cite: 2]
            try:
                resp = self.cmd_sock.recv(1024).decode("latin-1", errors="ignore")[cite: 2]
                if "CONNECTED" in resp and "DISCONNECTED" not in resp:[cite: 2]
                    connected = True[cite: 2]
                    break[cite: 2]
                elif "DISCONNECTED" in resp:[cite: 2]
                    break[cite: 2]
            except socket.timeout:
                pass[cite: 2]

        if not connected or self.abort_requested:[cite: 2]
            self.update_status("Disconnected / Timeout", "red")[cite: 2]
            self.term_print("[!] Connection failed or timed out.\n")[cite: 2]
            return False[cite: 2]

        self.update_status(f"Connected to {target_bbs}", "green")[cite: 2]
        self.term_print(f"[+] RF Link established with {target_bbs}!\n\n")[cite: 2]
        return True[cite: 2]

    def _create_inbox_messages_from_rm(self, raw_text):
        clean_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")[cite: 2]
        clean_text = re.sub(r'\n[^\n]*[>?]\s*$', '', clean_text).strip()[cite: 2]

        split_pattern = r'(?m)(?=^(?:Msg|Message)\s*#?\s*:?\s*\d+|^(?:From|F):\s*[A-Za-z0-9\-@/.]+)'[cite: 2]
        raw_parts = re.split(split_pattern, clean_text)[cite: 2]

        my_call = self.my_call_entry.get().strip().upper() if hasattr(self, "my_call_entry") else self.current_call

        created_count = 0[cite: 2]
        for part in raw_parts:[cite: 2]
            item_text = part.strip()[cite: 2]
            if not item_text or len(item_text) < 15:[cite: 2]
                continue[cite: 2]

            item_text = re.sub(r'^[^\n]*[>:]\s*\n?', '', item_text).strip()[cite: 2]

            id_m = re.search(r'(?:Msg|Message)\s*#?\s*:?\s*(\d+)', item_text, re.IGNORECASE)[cite: 2]
            from_m = re.search(r'(?:From|F):\s*([A-Za-z0-9\-@/.]+)', item_text, re.IGNORECASE)[cite: 2]
            to_m = re.search(r'(?:To|T):\s*([A-Za-z0-9\-@/.]+)', item_text, re.IGNORECASE)
            subj_m = re.search(r'(?:Subject|Subj):\s*(.*)', item_text, re.IGNORECASE)[cite: 2]

            if not id_m and not from_m:[cite: 2]
                continue[cite: 2]

            assigned_id = id_m.group(1) if id_m else str(len(self.inbox_msgs) + 1)[cite: 2]
            sender = from_m.group(1).strip() if from_m else "BBS"[cite: 2]
            recipient = to_m.group(1).strip() if to_m else my_call
            subject = subj_m.group(1).strip() if subj_m else f"Message #{assigned_id}"[cite: 2]
            msg_date = time.strftime("%m/%d %H:%M")[cite: 2]

            if any(existing.get("id") == assigned_id and existing.get("from") == sender for existing in self.inbox_msgs):[cite: 2]
                continue[cite: 2]

            self.inbox_msgs.append({
                "id": assigned_id,[cite: 2]
                "from": sender,[cite: 2]
                "to": recipient,
                "subj": subject,[cite: 2]
                "date": msg_date,[cite: 2]
                "body": item_text[cite: 2]
            })
            created_count += 1[cite: 2]
            self.term_print(f"[+] Saved message #{assigned_id} from {sender} to {recipient} - '{subject}'\n")

        if created_count > 0:[cite: 2]
            self._save_data()[cite: 2]
            def _refresh():
                self._update_folder_counts()[cite: 2]
                self._on_folder_select(None)[cite: 2]
            self.after(0, _refresh)[cite: 2]

        return created_count[cite: 2]

    def _run_auto_session(self, host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call, signature, mode, dwell_val):
        try:
            if not self._connect_rf(host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call):[cite: 2]
                return

            self._handle_auto_bbs_exchange(signature, mode, dwell_val)[cite: 2]

            if not self.abort_requested:[cite: 2]
                self.update_status("Disconnecting...", "orange")[cite: 2]
                self._send_data("B\r")[cite: 2]
                time.sleep(2.0)[cite: 2]
                self.cmd_sock.sendall(b"DISCONNECT\r")[cite: 2]
                self.update_status("Done / Idle", "gray")[cite: 2]
                self.term_print("[*] Automated session complete. Disconnected.\n")[cite: 2]

        except Exception as e:
            if not self.abort_requested:[cite: 2]
                self.update_status("Error", "red")[cite: 2]
                self.term_print(f"[!] Session Exception: {e}\n")[cite: 2]
        finally:
            self._disconnect_vara()[cite: 2]
            self._reset_ui_buttons()[cite: 2]

    def _handle_auto_bbs_exchange(self, signature, mode, dwell_val):
        initial_timeout = 40.0 if mode == "HF" else 15.0[cite: 2]
        banner = self._recv_data_until_prompt(timeout=initial_timeout, quiet_delay=1.5)[cite: 2]
        if self.abort_requested:[cite: 2]
            return

        if "command:" in banner.lower() or "}" in banner:[cite: 2]
            self.term_print("[*] Connected to Node switch. Sending 'BBS' command...\n")[cite: 2]
            self._send_data("BBS\r")[cite: 2]
            node_timeout = 40.0 if mode == "HF" else 12.0[cite: 2]
            self._recv_data_until_prompt(timeout=node_timeout, quiet_delay=1.5)[cite: 2]
            if self.abort_requested:[cite: 2]
                return

        # Dwell before initial RM query using station-specific dwell
        self.term_print(f"[*] Dwell delay ({dwell_val}s) before command dispatch...\n")[cite: 2]
        start_wait = time.time()[cite: 2]
        while time.time() - start_wait < dwell_val:[cite: 2]
            if self.abort_requested:[cite: 2]
                return
            time.sleep(0.1)[cite: 2]

        self.term_print(">>> RM\n")[cite: 2]
        self._send_data("RM\r")[cite: 2]

        rm_timeout = 40.0 if mode == "HF" else 25.0[cite: 2]
        rm_resp = self._recv_data_until_prompt(timeout=rm_timeout, quiet_delay=1.5)[cite: 2]
        if self.abort_requested:[cite: 2]
            return

        if rm_resp and "no message" not in rm_resp.lower() and len(rm_resp.strip()) > 10:[cite: 2]
            self._create_inbox_messages_from_rm(rm_resp)[cite: 2]
        else:
            self.term_print("[*] No unread messages returned by RM.\n")[cite: 2]

        # Strictly only transmit messages that reside in the Outbox
        while self.outbox_msgs and not self.abort_requested:[cite: 2]
            msg = self.outbox_msgs.pop(0)[cite: 2]
            cmd_prefix = msg.get("type", "SP").upper()[cite: 2]

            start_w = time.time()[cite: 2]
            while time.time() - start_w < dwell_val:[cite: 2]
                if self.abort_requested:[cite: 2]
                    break
                time.sleep(0.1)[cite: 2]

            self.term_print(f">>> {cmd_prefix} {msg['to']}\n")[cite: 2]
            self._send_data(f"{cmd_prefix} {msg['to']}\r")[cite: 2]

            self._recv_data_until_prompt(timeout=40.0 if mode == "HF" else 15.0, quiet_delay=1.2)[cite: 2]
            if self.abort_requested:[cite: 2]
                break

            start_w = time.time()[cite: 2]
            while time.time() - start_w < dwell_val:[cite: 2]
                if self.abort_requested:[cite: 2]
                    break
                time.sleep(0.1)[cite: 2]

            self.term_print(f">>> {msg['subj']}\n")[cite: 2]
            self._send_data(f"{msg['subj']}\r")[cite: 2]

            self._recv_data_until_prompt(timeout=40.0 if mode == "HF" else 15.0, quiet_delay=1.2)[cite: 2]
            if self.abort_requested:[cite: 2]
                break

            start_w = time.time()[cite: 2]
            while time.time() - start_w < dwell_val:[cite: 2]
                if self.abort_requested:[cite: 2]
                    break
                time.sleep(0.1)[cite: 2]

            body_content = msg['body'].strip()[cite: 2]
            if signature:[cite: 2]
                sig_check = signature.splitlines()[0][cite: 2]
                if sig_check and sig_check not in body_content:[cite: 2]
                    body_content = f"{body_content}\n\n{signature}"[cite: 2]

            clean_body = body_content.replace("\r\n", "\r").replace("\n", "\r")[cite: 2]
            payload = f"{clean_body}\r/EX\r"[cite: 2]

            self.term_print(">>> [Sending Message Body + /EX]\n")[cite: 2]
            self._send_data(payload)[cite: 2]

            self._recv_data_until_prompt(timeout=40.0 if mode == "HF" else 20.0, quiet_delay=1.5)[cite: 2]

            msg["date"] = time.strftime("%m/%d %H:%M")[cite: 2]
            self.sent_msgs.append(msg)[cite: 2]
            self.term_print(f"[+] Message successfully posted as {cmd_prefix} to {msg['to']}!\n")[cite: 2]

        self._save_data()[cite: 2]
        self.after(0, self._update_folder_counts)[cite: 2]
        self.after(0, lambda: self._on_folder_select(None))[cite: 2]

    def _run_manual_session(self, host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call, signature, mode):
        try:
            if not self._connect_rf(host, target_bbs, raw_digi, bw, cmd_port, data_port, my_call):[cite: 2]
                return

            self.term_print("[*] Terminal active. Type commands above, or click Node & BBS Commands on the left.\n\n")[cite: 2]
            self.data_sock.settimeout(0.3)[cite: 2]
            self.cmd_sock.settimeout(0.3)[cite: 2]

            while not self.abort_requested:[cite: 2]
                while not self.tx_manual_queue.empty():[cite: 2]
                    cmd = self.tx_manual_queue.get_nowait()[cite: 2]
                    self._send_data(f"{cmd}\r")[cite: 2]
                    if cmd.upper() in ["B", "BYE", "QUIT"]:[cite: 2]
                        self.term_print("[*] Logoff command recognized. Terminating link...\n")[cite: 2]
                        time.sleep(2.0)[cite: 2]
                        self.abort_requested = True[cite: 2]
                        break

                if self.abort_requested:[cite: 2]
                    break

                try:
                    chunk = self.data_sock.recv(2048).decode("latin-1", errors="ignore")[cite: 2]
                    if chunk:[cite: 2]
                        self.term_print(chunk)[cite: 2]
                except socket.timeout:
                    pass[cite: 2]
                except Exception:
                    break[cite: 2]

                try:
                    cmd_resp = self.cmd_sock.recv(1024).decode("latin-1", errors="ignore")[cite: 2]
                    if "DISCONNECTED" in cmd_resp:[cite: 2]
                        self.term_print("\n[!] Remote BBS disconnected.\n")[cite: 2]
                        break
                except socket.timeout:
                    pass[cite: 2]
                except Exception:
                    break[cite: 2]

            if self.cmd_sock:[cite: 2]
                self.cmd_sock.sendall(b"DISCONNECT\r")[cite: 2]
            self.update_status("Done / Idle", "gray")[cite: 2]
            self.term_print("[*] Session terminated. Disconnected.\n")[cite: 2]

        except Exception as e:
            if not self.abort_requested:[cite: 2]
                self.update_status("Error", "red")[cite: 2]
                self.term_print(f"[!] Session Exception: {e}\n")[cite: 2]
        finally:
            self._disconnect_vara()[cite: 2]
            self._reset_ui_buttons()[cite: 2]

    # ==========================================
    # INCOMING MAILBOX & LISTENER ENGINE
    # ==========================================
    def toggle_mailbox_listener(self):
        if self.listener_active:[cite: 2]
            self._stop_listener_service()[cite: 2]
            self.btn_listen.config(text="Mailbox Standby")[cite: 2]
            self.update_status("Standby Disabled", "gray")[cite: 2]
            self.term_print("[*] Mailbox listener disabled.\n")[cite: 2]
        else:
            if self.worker_thread and self.worker_thread.is_alive():[cite: 2]
                messagebox.showwarning("Busy", "Cannot enable Standby while an outbound session is running.")[cite: 2]
                return
            self._start_listener_service()[cite: 2]

    def _start_listener_service(self):
        self.listener_stop_event.clear()[cite: 2]
        self.listener_thread = threading.Thread(target=self._run_mailbox_listener, daemon=True)[cite: 2]
        self.listener_thread.start()[cite: 2]
        self.listener_active = True[cite: 2]
        self.btn_listen.config(text="Stop Standby")[cite: 2]

    def _stop_listener_service(self):
        self.listener_active = False[cite: 2]
        self.listener_stop_event.set()[cite: 2]
        try:
            if self.listener_cmd_sock:[cite: 2]
                self.listener_cmd_sock.sendall(b"LISTEN OFF\rDISCONNECT\r")[cite: 2]
                time.sleep(0.1)[cite: 2]
                self.listener_cmd_sock.close()[cite: 2]
            if self.listener_data_sock:[cite: 2]
                self.listener_data_sock.close()[cite: 2]
        except Exception:
            pass[cite: 2]
        self.listener_cmd_sock = None[cite: 2]
        self.listener_data_sock = None[cite: 2]
        self.mailbox_in_session = False[cite: 2]
        self.btn_listen.config(text="Mailbox Standby")[cite: 2]

    def _run_mailbox_listener(self):
        host = self.vara_host_entry.get().strip()[cite: 2]
        my_call = self.my_call_entry.get().strip().upper()[cite: 2]
        mode = self.mode_combo.get().strip().upper()[cite: 2]
        bw = self.bw_combo.get().strip()[cite: 2]
        try:
            cmd_port = int(self.cmd_port_entry.get().strip())[cite: 2]
            data_port = int(self.data_port_entry.get().strip())[cite: 2]
        except ValueError:
            return

        self.update_status("Standby (Listening)", "green")[cite: 2]
        self.term_print(f"[*] Starting Mailbox Listener on VARA {mode} ({host}:{cmd_port}) for {my_call}...\n")[cite: 2]

        try:
            self.listener_cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)[cite: 2]
            self.listener_cmd_sock.settimeout(5.0)[cite: 2]
            self.listener_cmd_sock.connect((host, cmd_port))[cite: 2]

            self.listener_data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)[cite: 2]
            self.listener_data_sock.settimeout(5.0)[cite: 2]
            self.listener_data_sock.connect((host, data_port))[cite: 2]

            self.listener_cmd_sock.sendall(f"MYCALL {my_call}\r".encode("ascii"))[cite: 2]
            time.sleep(0.1)[cite: 2]
            self.listener_cmd_sock.sendall(f"{bw}\r".encode("ascii"))[cite: 2]
            time.sleep(0.1)[cite: 2]
            self.listener_cmd_sock.sendall(b"LISTEN ON\r")[cite: 2]
            self.term_print(f"[+] Modem configured. Personal Mailbox standing by for incoming connects...\n")[cite: 2]
        except Exception as e:
            self.term_print(f"[!] Could not start Mailbox listener: {e}\n")[cite: 2]
            self.after(0, self._stop_listener_service)[cite: 2]
            return

        self.listener_cmd_sock.settimeout(0.3)[cite: 2]
        self.listener_data_sock.settimeout(0.3)[cite: 2]

        cmd_buf = ""[cite: 2]
        while not self.listener_stop_event.is_set():[cite: 2]
            try:
                cmd_data = self.listener_cmd_sock.recv(1024).decode("latin-1", errors="ignore")[cite: 2]
                if cmd_data:[cite: 2]
                    cmd_buf += cmd_data[cite: 2]
                    while "\r" in cmd_buf:[cite: 2]
                        line, cmd_buf = cmd_buf.split("\r", 1)[cite: 2]
                        line = line.strip()[cite: 2]
                        if line.startswith("CONNECTED"):[cite: 2]
                            parts = line.split()[cite: 2]
                            self.remote_call = parts[1].upper() if len(parts) > 1 else "CALLER"[cite: 2]
                            self.mailbox_in_session = True[cite: 2]
                            self.update_status(f"Caller: {self.remote_call}", "blue")[cite: 2]
                            self.term_print(f"\n[+] Incoming RF Connect from {self.remote_call}!\n")[cite: 2]
                            self._send_mailbox_welcome(my_call, mode)[cite: 2]
                        elif line.startswith("DISCONNECTED"):[cite: 2]
                            if self.mailbox_in_session:[cite: 2]
                                self.term_print(f"\n[*] {self.remote_call} disconnected from Mailbox.\n")[cite: 2]
                                self.mailbox_in_session = False[cite: 2]
                                self.remote_call = ""[cite: 2]
                                self.mb_state = "CMD"[cite: 2]
                                self.update_status("Standby (Listening)", "green")[cite: 2]
            except socket.timeout:
                pass[cite: 2]
            except Exception:
                break[cite: 2]

            if self.mailbox_in_session:[cite: 2]
                try:
                    data_in = self.listener_data_sock.recv(2048).decode("latin-1", errors="ignore")[cite: 2]
                    if data_in:[cite: 2]
                        self.term_print(f"[{self.remote_call}] " + data_in)[cite: 2]
                        self._process_mailbox_input(data_in, my_call)[cite: 2]
                except socket.timeout:
                    pass[cite: 2]
                except Exception:
                    break[cite: 2]

        self.after(0, self._stop_listener_service)[cite: 2]

    def _send_listener_data(self, txt):
        if self.listener_data_sock:[cite: 2]
            try:
                self.listener_data_sock.sendall(txt.encode("latin-1"))[cite: 2]
            except Exception:
                pass[cite: 2]

    def _send_mailbox_welcome(self, my_call, mode):
        self.mb_state = "CMD"[cite: 2]
        self.mb_line_buffer = ""[cite: 2]
        
        caller_base = self.remote_call.split('-')[0].upper()[cite: 2]
        matching_mail = [
            m for m in self.inbox_msgs[cite: 2]
            if str(m.get("to", "")).strip().upper() in (self.remote_call, caller_base)[cite: 2]
        ]
        
        if matching_mail:[cite: 2]
            mail_alert = (
                f"\r\n*** YOU HAVE {len(matching_mail)} MESSAGE(S) WAITING IN THIS MAILBOX ***\r\n"
                f"Type LM to list your messages or R <num> to read.\r\n"
            )[cite: 2]
        else:
            mail_alert = "\r\nNo personal mail waiting for you.\r\n"[cite: 2]

        welcome = (
            f"\r\nWelcome to {my_call} Personal Mailbox [VARA {mode}]\r\n"
            f"Current Station Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\r\n"
            f"{mail_alert}\r\n"
            f"Type ? or H for help.\r\n\r\n"
            f"{my_call} Mailbox > "
        )[cite: 2]
        self._send_listener_data(welcome)[cite: 2]

    def _process_mailbox_input(self, raw_data, my_call):
        self.mb_line_buffer += raw_data.replace("\n", "\r")[cite: 2]
        while "\r" in self.mb_line_buffer:[cite: 2]
            line, self.mb_line_buffer = self.mb_line_buffer.split("\r", 1)[cite: 2]
            line = line.strip()[cite: 2]
            if not line and self.mb_state == "CMD":[cite: 2]
                self._send_listener_data(f"{my_call} Mailbox > ")[cite: 2]
                continue[cite: 2]
            self._handle_mailbox_line(line, my_call)[cite: 2]

    def _handle_mailbox_line(self, line, my_call):
        prompt = f"{my_call} Mailbox > "[cite: 2]

        # STATE: Normal Command Prompt
        if self.mb_state == "CMD":[cite: 2]
            cmd = line.upper()[cite: 2]
            
            # Help
            if cmd in ("?", "H", "HELP"):[cite: 2]
                help_text = (
                    "\r\n--- Mailbox Commands ---\r\n"
                    "L           - List all messages\r\n"
                    "LM          - List messages addressed to you\r\n"
                    "R <num>     - Read message by number\r\n"
                    "SP <call>   - Send a private message\r\n"
                    "SR <num>    - Send reply to a specific message\r\n"
                    "KM <num>    - Kill/delete your message\r\n"
                    "B, BYE, Q   - Disconnect\r\n\r\n"
                )[cite: 2]
                self._send_listener_data(help_text + prompt)[cite: 2]

            # List All (L)
            elif cmd == "L":[cite: 2]
                resp = "\r\nMsg #   From       To         Date         Subject\r\n"[cite: 2]
                resp += "-" * 55 + "\r\n"[cite: 2]
                if not self.inbox_msgs:[cite: 2]
                    resp += "(No messages in mailbox)\r\n"[cite: 2]
                else:
                    for i, m in enumerate(self.inbox_msgs):[cite: 2]
                        m_id = str(m.get("id", i + 1)).ljust(7)[cite: 2]
                        m_from = str(m.get("from", "N/A"))[:9].ljust(10)[cite: 2]
                        m_to = str(m.get("to", my_call))[:9].ljust(10)[cite: 2]
                        m_date = str(m.get("date", ""))[:12].ljust(12)[cite: 2]
                        m_subj = str(m.get("subj", "(No Subject)"))[:25][cite: 2]
                        resp += f"{m_id} {m_from} {m_to} {m_date} {m_subj}\r\n"[cite: 2]
                self._send_listener_data(resp + "\r\n" + prompt)[cite: 2]

            # List Mine (LM)
            elif cmd == "LM":[cite: 2]
                caller_base = self.remote_call.split('-')[0].upper()[cite: 2]
                resp = f"\r\nMessages addressed to {self.remote_call}:\r\n"[cite: 2]
                resp += "Msg #   From       Date         Subject\r\n"[cite: 2]
                resp += "-" * 50 + "\r\n"[cite: 2]
                matched = [
                    m for m in self.inbox_msgs[cite: 2]
                    if str(m.get("to", "")).strip().upper() in (self.remote_call, caller_base)[cite: 2]
                ]
                if not matched:[cite: 2]
                    resp += "(No messages for your callsign)\r\n"[cite: 2]
                else:
                    for i, m in enumerate(matched):[cite: 2]
                        m_id = str(m.get("id", i + 1)).ljust(7)[cite: 2]
                        m_from = str(m.get("from", "N/A"))[:9].ljust(10)[cite: 2]
                        m_date = str(m.get("date", ""))[:12].ljust(12)[cite: 2]
                        m_subj = str(m.get("subj", "(No Subject)"))[:25][cite: 2]
                        resp += f"{m_id} {m_from} {m_date} {m_subj}\r\n"[cite: 2]
                self._send_listener_data(resp + "\r\n" + prompt)[cite: 2]

            # Read (R <num>)
            elif cmd.startswith("R ") or (cmd.startswith("R") and len(cmd) > 1 and cmd[1:].isdigit()):[cite: 2]
                num_str = cmd[2:].strip() if cmd.startswith("R ") else cmd[1:].strip()[cite: 2]
                matched = next((m for m in self.inbox_msgs if str(m.get("id")) == num_str), None)[cite: 2]
                if matched:[cite: 2]
                    msg_body = (
                        f"\r\nMessage #{num_str}\r\n"
                        f"From:    {matched.get('from', 'N/A')}\r\n"
                        f"To:      {matched.get('to', my_call)}\r\n"
                        f"Date:    {matched.get('date', 'N/A')}\r\n"
                        f"Subject: {matched.get('subj', '')}\r\n"
                        f"{'-'*45}\r\n"
                        f"{matched.get('body', '')}\r\n"
                        f"{'-'*45}\r\n\r\n"
                    )[cite: 2]
                    self._send_listener_data(msg_body + prompt)[cite: 2]
                else:
                    self._send_listener_data(f"\r\nMessage #{num_str} not found.\r\n\r\n{prompt}")[cite: 2]

            # Send Reply (SR <msg#>)
            elif cmd.startswith("SR ") or (cmd.startswith("SR") and len(cmd) > 2 and cmd[2:].isdigit()):[cite: 2]
                num_str = cmd[3:].strip() if cmd.startswith("SR ") else cmd[2:].strip()[cite: 2]
                matched = next((m for m in self.inbox_msgs if str(m.get("id")) == num_str), None)[cite: 2]
                if matched:[cite: 2]
                    orig_from = matched.get("from", "").strip().upper()[cite: 2]
                    dest_call = orig_from if orig_from and orig_from != "BBS" else my_call[cite: 2]
                    orig_subj = matched.get("subj", "").strip()[cite: 2]
                    reply_subj = orig_subj if orig_subj.upper().startswith("RE:") else f"RE: {orig_subj}"[cite: 2]
                    
                    self.mb_rx_msg = {
                        "from": self.remote_call,[cite: 2]
                        "to": dest_call,[cite: 2]
                        "subj": reply_subj,[cite: 2]
                        "body": "",[cite: 2]
                        "type": "SP"[cite: 2]
                    }
                    self.mb_state = "SP_BODY"[cite: 2]
                    self._send_listener_data(
                        f"\r\nReplying to Message #{num_str} (To: {dest_call})\r\n"
                        f"Subject: {reply_subj}\r\n"
                        f"Enter message text. End with /EX or Ctrl+Z on a new line:\r\n"
                    )[cite: 2]
                else:
                    self._send_listener_data(f"\r\nMessage #{num_str} not found.\r\n\r\n{prompt}")[cite: 2]

            # Send Personal Message (SP <call>)
            elif cmd.startswith("SP ") or cmd.startswith("SB "):[cite: 2]
                dest_call = cmd.split(maxsplit=1)[1].strip().upper()[cite: 2]
                if not dest_call:[cite: 2]
                    self._send_listener_data(f"\r\nError: Destination callsign required.\r\n{prompt}")[cite: 2]
                    return
                self.mb_rx_msg = {
                    "from": self.remote_call,[cite: 2]
                    "to": dest_call,[cite: 2]
                    "subj": "",[cite: 2]
                    "body": "",[cite: 2]
                    "type": "SP" if cmd.startswith("SP") else "SB"[cite: 2]
                }
                self.mb_state = "SP_SUBJ"[cite: 2]
                self._send_listener_data("Enter Subject: ")[cite: 2]

            # Kill/Delete Message (KM <num>)
            elif cmd.startswith("KM ") or (cmd.startswith("KM") and len(cmd) > 2 and cmd[2:].isdigit()):[cite: 2]
                num_str = cmd[3:].strip() if cmd.startswith("KM ") else cmd[2:].strip()[cite: 2]
                matched = next((m for m in self.inbox_msgs if str(m.get("id")) == num_str), None)[cite: 2]
                if matched:[cite: 2]
                    caller_base = self.remote_call.split('-')[0].upper()[cite: 2]
                    m_from = str(matched.get("from", "")).strip().upper()[cite: 2]
                    m_to = str(matched.get("to", "")).strip().upper()[cite: 2]

                    if self.remote_call in (m_from, m_to) or caller_base in (m_from, m_to) or my_call in (m_from, m_to):[cite: 2]
                        self.inbox_msgs.remove(matched)[cite: 2]
                        self.trash_msgs.append(matched)[cite: 2]
                        self._save_data()[cite: 2]
                        self.after(0, self._update_folder_counts)[cite: 2]
                        self.after(0, lambda: self._on_folder_select(None))[cite: 2]
                        self._send_listener_data(f"\r\nMessage #{num_str} killed.\r\n\r\n{prompt}")[cite: 2]
                    else:
                        self._send_listener_data(f"\r\nAccess Denied: Not addressed to or sent by {self.remote_call}.\r\n\r\n{prompt}")[cite: 2]
                else:
                    self._send_listener_data(f"\r\nMessage #{num_str} not found.\r\n\r\n{prompt}")[cite: 2]

            # Disconnect / Logoff
            elif cmd in ("B", "BYE", "Q", "QUIT"):[cite: 2]
                self._send_listener_data(f"\r\n73 de {my_call}. Disconnecting link...\r\n")[cite: 2]
                time.sleep(1.0)[cite: 2]
                try:
                    if self.listener_cmd_sock:[cite: 2]
                        self.listener_cmd_sock.sendall(b"DISCONNECT\r")[cite: 2]
                except Exception:
                    pass[cite: 2]

            else:
                self._send_listener_data(f"\r\nUnknown command '{line}'. Type H or ? for help.\r\n\r\n{prompt}")[cite: 2]

        # STATE: Awaiting Subject
        elif self.mb_state == "SP_SUBJ":[cite: 2]
            self.mb_rx_msg["subj"] = line if line else "No Subject"[cite: 2]
            self.mb_state = "SP_BODY"[cite: 2]
            self._send_listener_data("\r\nEnter message text. End with /EX or Ctrl+Z on a new line:\r\n")[cite: 2]

        # STATE: Collecting Body Lines until /EX
        elif self.mb_state == "SP_BODY":[cite: 2]
            if line.upper() in ("/EX", "\x1a", "EX"):[cite: 2]
                next_id = str(len(self.inbox_msgs) + 1)[cite: 2]
                self.mb_rx_msg["id"] = next_id[cite: 2]
                self.mb_rx_msg["date"] = time.strftime("%m/%d %H:%M")[cite: 2]
                self.inbox_msgs.append(dict(self.mb_rx_msg))[cite: 2]
                self._save_data()[cite: 2]
                
                self.after(0, self._update_folder_counts)[cite: 2]
                self.after(0, lambda: self._on_folder_select(None))[cite: 2]

                self.term_print(f"\n[+] Mailbox saved message #{next_id} from {self.remote_call} to {self.mb_rx_msg['to']}!\n")[cite: 2]
                self._send_listener_data(f"\r\nMessage #{next_id} stored successfully.\r\n\r\n{prompt}")[cite: 2]
                self.mb_state = "CMD"[cite: 2]
                self.mb_rx_msg = {}[cite: 2]
            else:
                if self.mb_rx_msg["body"]:[cite: 2]
                    self.mb_rx_msg["body"] += "\n" + line[cite: 2]
                else:
                    self.mb_rx_msg["body"] = line[cite: 2]

    # ----------------------------------------------------
    # SOCKET & BUFFER UTILITIES
    # ----------------------------------------------------
    def _send_data(self, txt):
        if self.data_sock and not self.abort_requested:[cite: 2]
            self.data_sock.sendall(txt.encode("latin-1"))[cite: 2]

    def _recv_data_until_prompt(self, timeout=15.0, quiet_delay=1.5):
        buffer = ""[cite: 2]
        start_t = time.time()[cite: 2]
        last_rx_time = 0[cite: 2]
        prompt_seen_time = None[cite: 2]

        if self.data_sock:[cite: 2]
            self.data_sock.settimeout(0.2)[cite: 2]

        while time.time() - start_t < timeout:[cite: 2]
            if self.abort_requested:[cite: 2]
                break
            try:
                chunk = self.data_sock.recv(2048).decode("latin-1", errors="ignore")[cite: 2]
                if chunk:[cite: 2]
                    buffer += chunk[cite: 2]
                    self.term_print(chunk)[cite: 2]
                    last_rx_time = time.time()[cite: 2]

                    tail = buffer.strip()[cite: 2]
                    if tail.endswith(">") or tail.endswith("?") or tail.endswith(":") or tail.endswith("Command:"):[cite: 2]
                        if prompt_seen_time is None:[cite: 2]
                            prompt_seen_time = time.time()[cite: 2]
                    else:
                        prompt_seen_time = None[cite: 2]
            except socket.timeout:
                now = time.time()[cite: 2]
                if prompt_seen_time and (now - last_rx_time >= quiet_delay):[cite: 2]
                    break
                if buffer and (last_rx_time > 0) and (now - last_rx_time >= 2.5):[cite: 2]
                    break
            except Exception:
                break[cite: 2]

        return buffer[cite: 2]

    def manual_disconnect(self):
        self.abort_requested = True[cite: 2]
        self.update_status("Aborting transmission...", "red")[cite: 2]
        self.term_print("\n[!] Disconnect button pressed: Terminating RF connection...\n")[cite: 2]
        threading.Thread(target=self._force_disconnect, daemon=True).start()[cite: 2]

    def _force_disconnect(self):
        try:
            if self.cmd_sock:[cite: 2]
                try:
                    self.cmd_sock.sendall(b"ABORT\r")[cite: 2]
                    time.sleep(0.1)[cite: 2]
                    self.cmd_sock.sendall(b"DISCONNECT\r")[cite: 2]
                except Exception:
                    pass[cite: 2]

            if self.data_sock:[cite: 2]
                try:
                    self.data_sock.sendall(b"B\r")[cite: 2]
                except Exception:
                    pass[cite: 2]
        except Exception:
            pass[cite: 2]
        finally:
            self._disconnect_vara()[cite: 2]

    def _disconnect_vara(self):
        try:
            if self.data_sock:[cite: 2]
                self.data_sock.close()[cite: 2]
                self.data_sock = None[cite: 2]
            if self.cmd_sock:[cite: 2]
                self.cmd_sock.close()[cite: 2]
                self.cmd_sock = None[cite: 2]
        except Exception:
            pass[cite: 2]

    def _reset_ui_buttons(self):
        self.after(0, lambda: self.btn_send_rcv.config(state=tk.NORMAL))[cite: 2]
        self.after(0, lambda: self.btn_manual_conn.config(state=tk.NORMAL))[cite: 2]
        self.after(0, lambda: self.btn_disconnect.config(state=tk.DISABLED))[cite: 2]
        self.after(0, lambda: self.btn_listen.config(state=tk.NORMAL))[cite: 2]


if __name__ == "__main__":
    app = VaraBBSClient()[cite: 2]
    app.mainloop()[cite: 2]