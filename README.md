# VARA HF/FM Mail & Terminal Client

An automated Mailbox, Terminal, and Station Management client designed for **VARA HF** and **VARA FM** modems. Built with Python and Tkinter, it provides an interface for message queuing, station navigation, node switching, personal mailbox hosting, and optional hardware radio CAT/PTT management.

---

## Client Versions: `varabbshl.py` vs. `varabbs.py`

Choose the script that matches your station layout and operating environment:

| Feature / Scenario | `varabbshl.py` (Hamlib Integrated) | `varabbs.py` (Split / Standalone) |
| :--- | :--- | :--- |
| **Typical Station Setup** | **Single PC (All-in-One):** The Python client and VARA modems run on the same Windows PC directly connected to the radio. | **Network / Cross-Platform:** The Python client runs on one system (e.g., Linux / Raspberry Pi OS) while VARA modems run on a dedicated Windows machine. |
| **CAT & PTT Handling** | **Embedded Hamlib (`rigctld`):** Intercepts VARA telemetry to execute serial CAT PTT commands, radio filter selection, and dial frequency tuning directly. | **External / Offloaded:** No internal Hamlib engine. PTT and rig control are handled natively by the VARA installation on the Windows PC or via standard radio interface hardware (e.g., soundcard VOX, RA-board PTT). |
| **Host Operating System** | Primarily Windows (where local COM ports and `rigctld.exe` reside alongside VARA). | Linux, macOS, or Windows (ideal for low-power Linux terminals accessing remote Windows VARA modems over LAN). |

---

## What's New

### 1. Live Modem Dashboard Indicators (LEDs)

* **Real-Time DCD Detection:** An asynchronous background telemetry monitor maintains an active connection to the VARA command port (`8358`/`8300`), reflecting channel activity (**BUSY ON / OFF**, **DCD ON / OFF**) in real time whether in an active session, in standby, or monitoring frequency.
* **Status LEDs:** Top-level indicators for **PWR** (Modem Link), **CONN** (RF Link Established), **DCD** (Carrier/Traffic Detected), and **TX** (Modem Audio Burst).

### 2. Embedded Hamlib Hardware CAT & PTT Control (`varabbshl.py`)

* **Direct Panel Controls:** Dedicated **Start Hamlib** and **Stop Hamlib** buttons on the left-hand HF panel allow launching and stopping the background `rigctld` daemon on demand.
* **Automatic COM Port Release:** Automatically sends the quit command (`q`) and terminates any active `rigctld` process when closing the application or stopping the daemon, freeing serial COM ports for other software.
* **Radio Filter Selection:** One-click digital passband filter radio buttons:
  * **F1 (3.0k):** 3000 Hz wide passband for maximum throughput.
  * **F2 (2.4k):** 2400 Hz standard digital filter.
  * **F3 (500):** 500 Hz narrow passband for crowded conditions.
* **Automated CAT PTT Intercept:** Intercepts VARA HF `PTT ON` and `PTT OFF` telemetry over TCP and relays immediate CAT PTT (`T 1` / `T 0`) commands to the radio.

### 3. Independent Rig & CAT Settings Storage

* **Decoupled Radio Tuning:** Dial frequency, filter selection, radio model, COM port, and baud rate settings are stored independently at the root station level and are not overwritten when switching station contacts.
* **Updated Quick Frequency Presets:** Quick-tuning buttons configured for primary digital dial frequencies:
  * **7103.20 kHz** (40m)
  * **3596.00 kHz** (80m)
  * **14106.50 kHz** (20m)

---

## Core Capabilities

* **Dual Mode VARA Engine:** Seamless toggling between **VARA HF** (Ports `8358`/`8359`, `BW500`/`BW2300`/`BW2750`) and **VARA FM** (Ports `8300`/`8301`, `NARROW`/`WIDE`).
* **Automated BBS Session (`Send/Recv`):** Automatically connects, checks for node switches, applies station dwell delays, runs `RM` to download unread mail into your Inbox, transmits queued Outbox messages using `/EX`, and cleanly logs off (`B`).
* **Interactive Terminal (`Connect (Term)`):** Live interactive console supporting type-ahead entry, common node command shortcuts (`N`, `R`, `L`, `S`, `U`, `CHAT`, `BBS`, `B`), and double-click message loading.
* **Standby Personal Mailbox (`Mailbox Standby`):** Listens for incoming RF connections, greets remote callers, lists unread messages (`LM`), allows remote retrieval (`R <id>`), handles private replies (`SR <id>`), and receives incoming RF messages.
* **Full Message Management:** Inbox, Drafts, Outbox, Sent, and Trash with message drafting, contact history, and station signature insertion.
* **Station Directory & Per-Station Dwell:** Save target BBS callsigns, digipeater routes (`VIA DIGI`), and individual station dwell timers.
* **Emergency Forms Link:** Quick-access button for the online National Traffic System (NTS) and Skywarn HTML forms suite.
* **Theme Support:** One-click Light and Dark mode UI toggle.

---

## Prerequisites & Downloads

1. **Python 3.8+**
   * Standard library modules only (`tkinter`, `socket`, `threading`, `subprocess`, `json`, `queue`). No external `pip` packages required.

2. **VARA HF and/or VARA FM Modem**
   * Installed and configured with your sound card interfaces (running locally or remotely on a Windows host).

3. **Hamlib (`rigctld`)** *(Required only for `varabbshl.py`)*
   * Official GitHub releases: [Hamlib Releases on GitHub](https://github.com/Hamlib/Hamlib/releases)
   * Download the 64-bit Windows setup (`hamlib-w64-*.exe`) or zip archive (`hamlib-w64-*.zip`).
   * Standard auto-detected paths:
     * `C:\Program Files (x86)\hamlib\bin\rigctld.exe`
     * `C:\Program Files\hamlib\bin\rigctld.exe`
     * `C:\hamlib\bin\rigctld.exe`
     * `C:\WSJT\wsjtx\bin\rigctld.exe`

---

## Installation & Setup

1. **Choose Your Script:**
   * Run `varabbshl.py` if your transceiver is cabled to this PC and you require integrated Hamlib CAT/PTT.
   * Run `varabbs.py` if you run the GUI on Linux or a remote PC and tunnel commands to a remote Windows VARA box.

2. **Launch the Application:**
   ```bash
   python varabbshl.py
   # or
   python varabbs.py

```

*(Creates `varabbs_data.json` automatically on first launch to persist station profiles, mailboxes, and hardware settings).*

3. **Configure Station Parameters:**
* Enter your callsign in **My Callsign** (e.g., `N3MEL`).
* Set **Modem Host IP** to `127.0.0.1` for local modems, or the remote Windows machine's IP (e.g., `192.168.1.50`).
* Verify ports match your modem configuration:
* **HF:** Cmd `8358` / Data `8359`
* **FM:** Cmd `8300` / Data `8301`




4. **Configure Radio CAT / PTT (`varabbshl.py` only):**
* Click **CAT Setup** on the top toolbar.
* Check **Enable Hamlib CAT & PTT Control**.
* Select your radio model (e.g., `Icom IC-7300 (3073)`).
* Set your transceiver's **Serial COM Port** (e.g., `COM3`) and **Baud Rate** (e.g., `19200`).
* Click **Save & Apply**.
* Under **HF Setup & VFO CAT Tuning** in the left sidebar, click **Start Hamlib** and verify `CAT: Online` is displayed.



---

## Operating Instructions

### Sending & Receiving Mail (Automated)

1. Compose a message using **New Message**, set the type (`SP` or `SB`), add a recipient and subject, and click **Queue to Outbox (Remote BBS)**.
2. Select your **Target BBS** from the dropdown (or enter a callsign and optional digipeater).
3. If operating on HF via `varabbshl.py`, select your desired passband filter (**F1**, **F2**, or **F3**) and frequency using the preset buttons or direct entry.
4. Click **Send/Recv**. The software manages connection, message polling, delivery, and disconnect automatically.

### Interactive Terminal Operation

1. Select the destination station.
2. Click **Connect (Term)**.
3. Use the terminal entry box or side buttons (`Nodes`, `Routes`, `Links`, `Users`, `Chat`, `BBS`) to interact with the remote system.
4. Double-click any message number in the terminal window to fetch and read it.
5. Click **Disconnect** or send `B` to terminate the session.

### Personal Mailbox Standby

1. When not in an active session, click **Mailbox Standby**.
2. The modem enters listen mode (`LISTEN ON`).
3. When connected by an incoming station, the client serves the station banner, unread alerts, and accepts commands (`L`, `LM`, `R`, `SP`, `SR`, `KM`, `B`).

---

## File Structure

```text
├── varabbshl.py          # All-in-one client with integrated Hamlib rig/PTT control
├── varabbs.py            # Streamlined client for cross-platform/remote Windows VARA hosts
└── varabbs_data.json     # Station profiles, mailboxes, and hardware settings (auto-generated)

```

```

```