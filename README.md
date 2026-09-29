# VARA HF/FM Mail & Terminal Client

A standalone, lightweight Python/Tkinter desktop client designed for amateur radio store-and-forward packet operations over **VARA HF** and **VARA FM** software modems. It connects directly to BPQ32, LinBPQ, and standard packet radio Mailbox/BBS systems.

---

## Features

- **Dual-Mode Operation (HF & FM):**
  - Instant port, bandwidth, and contact list swapping between VARA HF (Ports 8358/8359) and VARA FM (Ports 8300/8301).
- **Automated Send/Receive Exchange:**
  - Connects to remote BBS stations with digipeater routing support (`VIA DIGI`).
  - Gated turnarounds: Strict prompt handshaking with a 40-second dwell on VARA HF to ensure clean, non-colliding channel clearances.
  - Automates mailbox retrieval using `RM` (Read Mine) and batch dispatches queued Outbox messages using `SP <callsign>`.
- **Interactive Live Terminal Monitor:**
  - Live ASCII RF traffic monitoring with color-coded operational states.
  - Top-mounted **Type-Ahead** input bar for manual command entry.
  - **Double-Click to Read:** Double-click any message number in the terminal log to immediately fetch `R <num>` from the BBS or open it from local cache.
- **Node & BBS Quick-Action Panel:**
  - 3-column quick-dispatch panel for common BPQ Node and Mailbox commands (`Nodes`, `Routes`, `Links`, `Stats`, `Users`, `Chat`, `BBS`, `Leave`, `List`, `LM`, `RM`, `KM`).
  - On-screen syntax reference for manual packet routing (`SP`, `SB`, `SR`, `ST`).
- **Full Mailbox Management & Persistence:**
  - Local JSON storage for `Inbox`, `Drafts`, `Outbox`, `Sent`, and `Trash`.
  - Resizable split view between the mail table and terminal log.
  - Window size memory and startup auto-maximization.

---

## Requirements

1. **Python 3.8+**
2. **Tkinter** (included by default on Windows/macOS; on Linux: `sudo apt install python3-tk`)
3. A running instance of **VARA HF** or **VARA FM** reachable over TCP/IP.

---

## Installation & Setup

1. **Clone or Download the Repository:**
   Place `varabbs.py` into your working directory.

2. **Run the Application:**
   ```bash
   python varabbs.py
   ```
   *(On Windows, you can double-click `varabbs.py` or create a desktop shortcut).*

3. **Initial Configuration:**
   - **My Callsign:** Enter your callsign and SSID in the left settings pane (default: `N3MEL`).
   - **Modem Host IP:** Set the IP of the machine running your VARA modem (default: `192.168.86.34` or `127.0.0.1` if local).
   - **Ports:** Defaults are preconfigured for VARA HF (`8358`/`8359`) and VARA FM (`8300`/`8301`).
   - **Station Signature:** Edit the 6-line signature box. It will automatically attach to outbound messages.

---

## Operational Guide

### 1. Automated Send / Receive
1. Select your target station from the **Target BBS** dropdown (e.g., `MELBBS`, `W3PND-1`).
2. If digipeating, enter the intermediate hop in the **Via Digi** field (e.g., `W3PND-2`).
3. Click **📥 Send/Recv**.
4. The client will:
   - Establish the RF link.
   - Detect and navigate BPQ node switches into the BBS mail engine.
   - Wait for the remote prompt and pause for channel quiet time (40s on HF).
   - Fetch unread messages via `RM` and populate your **Inbox**.
   - Transmit queued Outbox messages using formatted `SP <call>` envelopes ending with `/EX`.
   - Send `B` and drop the radio link cleanly.

### 2. Manual Terminal Sessions
1. Click **⚡ Connect (Term)** to initiate an open, interactive CLI link.
2. Type commands in the top **Type-Ahead** bar and press `Enter`.
3. Use the **Node & BBS Commands** buttons on the left sidebar to issue one-click inquiries (`Nodes`, `Users`, `List`, etc.).
4. Double-click any listed message number directly on the terminal screen to request and read it.
5. Click **⏹️ Disconnect** or send `B` to terminate the session.

### 3. Composing Messages
1. Click **✏️ New Message**.
2. Enter the destination callsign and subject.
3. Type the body text (your station signature is auto-appended).
4. Choose **Save as Draft** or **Queue to Outbox**. Queued messages are automatically transmitted on the next **Send/Recv** pass.

---

## Storage & File Layout

```text
├── varabbs.py           # Main application client
└── varabbs_data.json     # Auto-generated JSON database (contacts, messages, layout)
```