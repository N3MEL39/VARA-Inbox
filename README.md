```markdown
# VARA HF/FM & Telnet Mail/Terminal Client

An automated Mailbox, Terminal, and Station Management client designed for **VARA HF**, **VARA FM**, and **Telnet BBS** nodes (such as LinBPQ / BPQ32). Built with Python and Tkinter, it provides a complete interface for message routing, node navigation, automated mail polling, personal mailbox hosting, and hardware radio CAT/PTT management.

---

## Client Versions: `varabbshl40.py` vs. `varabbs.py`

Choose the script that matches your operating environment and station layout:

| Feature / Scenario | `varabbshl40.py` (Hamlib Integrated) | `varabbs.py` (Standalone / Remote Host) |
| :--- | :--- | :--- |
| **Typical Station Setup** | **Single PC (All-in-One):** The Python client, the VARA HF modem, and hardware transceiver serial connections all run directly on the same local Windows machine. | **Cross-Platform / Networked:** Runs on Windows, Linux, or macOS where VARA modems or Telnet nodes run on another machine across the LAN, or where rig control is not handled locally. |
| **Hamlib Requirement** | **Local Radio Control:** Hamlib (`rigctld`) is **only needed if both the VARA HF modem and this client code are running on the very same machine** where the radio COM port is physically connected. | **No Hamlib Needed:** Bypasses local CAT/PTT management entirely. Modem audio PTT and rig tuning are managed directly by the remote host or dedicated hardware. |
| **CAT & PTT Handling** | **Embedded `rigctld` Daemon:** Manages local COM port sharing, software-relayed CAT PTT bursts, hardware autotune triggers, and digital passband filter switching. | **External / Offloaded:** Operates purely over network sockets to communicate with remote modem ports and Telnet hosts. |

---

## What's New

### 1. Direct Telnet Gateway Integration
* **Automated Node Authentication:** Built-in Telnet engine handles initial terminal negotiations, strips Telnet IAC command bytes, and detects BPQ/Node login challenges (`user:`, `call:`, `password:`).
* **Single-Dispatch Login Guard:** Prevents rapid re-triggering of credentials during buffered line echoes, preventing node brute-force lockouts.
* **Smart BBS Subsystem Handoff:**
  * **Automated (`Send/Recv`):** Connects to the host, waits 2 seconds following password acceptance, dispatches `BBS\r\n`, waits for the BBS prompt, and triggers `RM` to read unread mail into the Inbox.
  * **Interactive (`Connect (Term)`):** Automatically logs into the node and immediately transitions into the `BBS>` subsystem upon password acceptance.

### 2. High-Performance Display Pipeline (Zero-Latency Engine)
* **`TCP_NODELAY` Socket Optimization:** Nagle’s algorithm is explicitly disabled on both command and data sockets, eliminating buffering lag on short packets, frame bursts, and telemetry updates.
* **Non-Blocking Serial Polling:** Polling intervals in manual sessions operate at low latency (20 ms), preventing sequential socket delays between data chunks and telemetry status queries.
* **Lightweight Terminal Updates:** Switched buffer updates to Tkinter's idle scheduler with direct `yview_moveto(1.0)` alignment, preventing full-window layout recalculation bottlenecks during dense packet streams.
* **Light-Mode Terminal Readout:** High-contrast light terminal display (white background with dark green/black monospaced text) for enhanced visibility.

### 3. Dynamic Full-Screen Terminal Toggle
* **Expand / Restore Workspace:** A dedicated **Full Terminal Screen** button at the top toolbar allows collapsing the Received Messages pane to maximize live terminal and monitor space, with one-click restoration.

### 4. Automatic Terminal `RM` Capture
* **Interactive Message Ingestion:** Issuing an `RM` (Read Mine) command inside an interactive **Connect (Term)** session automatically captures output lines until the prompt returns, parses the raw messages, deposits them into the local Inbox database, and updates folder counts in real time.

### 5. Mode-Adaptive Tool Panels
* **Dynamic Menu Filtering:** Selecting **VARA FM** or **Telnet** link modes cleanly disables irrelevant HF hardware tools (Hamlib CAT Setup and ATU Meters & Tune) from the interface, while keeping **Station Setup**, **HTML Forms**, and the **Quick Reference Guide** available.

---

## Core Capabilities

* **Multi-Mode Engine:** Seamlessly toggle between **VARA HF** (Ports `8358`/`8359`), **VARA FM** (Ports `8300`/`8301`), and **Telnet** (Port `8015` or custom).
* **Automated BBS Session (`Send/Recv`):** Connects, monitors for node switches, enforces station dwell timers, runs `RM` to download unread traffic, delivers queued Outbox messages using `/EX`, and initiates graceful logoffs (`B`).
* **Interactive Terminal (`Connect (Term)`):** Terminal view with type-ahead entry, macro buttons (`N`, `R`, `L`, `S`, `U`, `CHAT`, `BBS`, `B`, `LM`, `RM`, `KM`), and double-click cached message previews.
* **Standby Personal Mailbox (`Mailbox Standby`):** Listens for incoming RF callers, serves custom welcome banners, accepts unread requests (`LM`), facilitates message reads (`R <id>`), private replies (`SR <id>`), message deletions (`KM <id>`), and deposits incoming traffic.
* **Comprehensive Folder Management:** Inbox, Drafts, Outbox, Sent, and Trash with message drafting, contact history, and station signature insertion.
* **Live Modem Telemetry Indicators:** Top-level indicator LEDs displaying **PWR** (Socket Link), **CONN** (Link Established), **DCD** (Carrier/Traffic Detected), and **TX** (Transmitting).

---

## Prerequisites & Downloads

1. **Python 3.8+**
   * Standard library only (`tkinter`, `socket`, `threading`, `subprocess`, `json`, `queue`). No external `pip` packages required.

2. **Modems & Nodes**
   * **VARA HF / VARA FM:** Installed and configured with appropriate audio interfaces on a local or remote Windows PC.
   * **Telnet Node:** An accessible LinBPQ / BPQ32 node or packet switch running a Telnet server.

3. **Hamlib (`rigctld`)** *(Required only for `varabbshl40.py` when running client and VARA HF locally)*
   * **Important Note on Hamlib:** Hamlib is **only needed if the VARA HF modem and this client code are running from the exact same machine**. If your radio interface and VARA modem reside on a remote computer, Hamlib is not required on the client machine.
   * Download the 64-bit Windows setup (`hamlib-w64-*.exe`) or zip archive from [Hamlib Releases on GitHub](https://github.com/Hamlib/Hamlib/releases).
   * Standard auto-detected locations:
     * `C:\Program Files (x86)\hamlib\bin\rigctld.exe`
     * `C:\Program Files\hamlib\bin\rigctld.exe`
     * `C:\hamlib\bin\rigctld.exe`
     * `C:\WSJT\wsjtx\bin\rigctld.exe`

---

## Installation & Setup

1. **Choose Your Script:**
   * Run `varabbshl40.py` if your transceiver is cabled to this PC and you are running both this code and the VARA HF modem on the same local machine.
   * Run `varabbs.py` on standalone workstations (Windows, Linux, or macOS) interfacing with remote Windows VARA modems or Telnet hosts across your local network.

2. **Launch the Application:**
   ```bash
   # Desktop with local Hamlib CAT
   python varabbshl40.py

   # Desktop Standalone / Remote host
   python varabbs.py

```

*(Creates `varabbs_data.json` automatically on first launch).*

3. **Configure Station Parameters:**
* Click **Sta Setup** on the left panel (or open Station Setup from the top toolbar).
* **Callsign:** Enter your station callsign (e.g., `N3MEL`).
* **Target BBS:** Set the default destination callsign (e.g., `BPQ-BBS` or `N3MEL-2`).
* **Modem Host / IP:** Set to `127.0.0.1` for local modems, or the IP address of your remote station PC (e.g., `192.168.1.50`).
* **Telnet Parameters:** Enter the Telnet IP, port (`8015`), node username, and password.


4. **Configure Radio CAT / PTT (`varabbshl40.py` only - Local Single-Machine Setup):**
* *Skip this section entirely if the client and VARA HF modem are on different machines.*
* Select **HF** mode, then click **Cat Setup** on the left panel.
* Check **Enable Hamlib CAT & PTT Control**.
* Choose your transceiver model (e.g., `Icom IC-7300 (3073)`), serial COM port, and baud rate.
* Click **Save & Apply**, then click **Start Hamlib** on the left HF panel to confirm `CAT: Online`.



---

## Operating Instructions

### Sending & Receiving Mail (Automated)

1. Click **New Message**, set the message type (`SP` for Private, `SB` for Bulletin), add the recipient callsign and subject, and select **Queue to Outbox (Remote BBS)**.
2. Select your link mode (**TELNET**, **FM**, or **HF**).
3. Confirm the **Target BBS** in the top bar.
4. Click **Send/Recv**. The client establishes the connection, handles node and BBS navigation, waits for station prompts, runs `RM`, deposits incoming mail into the **Inbox**, posts Outbox drafts, and logs off gracefully.

### Interactive Terminal Operation

1. Enter your target destination in **Target BBS** (and optional digipeater route in **Via**).
2. Click **Connect (Term)**.
3. Use the top type-ahead box or macro buttons (`Nodes`, `Routes`, `Links`, `Users`, `Chat`, `BBS`, `LM`, `RM`, `KM`) to interact with the station.
4. If you run `RM` manually, any unread messages printed to the terminal are parsed and saved to your Inbox automatically.
5. Double-click any message number or line in the terminal to view cached contents or fetch the message directly.
6. Click **Disconnect** or send `B` to terminate the session.

### Personal Mailbox Standby (VARA RF)

1. Switch to **FM** or **HF** mode and click **Mailbox Standby**.
2. The modem enters listen mode (`LISTEN ON`).
3. Remote stations connecting to your station callsign receive personal greeting banners, mail notifications, and can list or retrieve messages addressed to them.

---

## File Structure

```text
├── varabbshl40.py        # Desktop client with integrated Hamlib rig control, zero-latency engine & Telnet
├── varabbs.py            # Streamlined desktop client for standalone/remote Windows VARA & Telnet
└── varabbs_data.json     # Station profiles, mailboxes, and hardware configuration (auto-generated)

```

```

### Immediate Concrete Next Steps
1. Overwrite your local `README.md` with the updated Markdown above.
2. If distributing the package alongside `varabbshl40.py` and `varabbs.py`, ensure `varabbs_data.json` is added to your `.gitignore` to prevent station-specific callsign details and passwords from being committed.

```