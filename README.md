# VARA HF/FM Mail & Terminal Client (v2.5)

A standalone, lightweight Python and Tkinter client for VARA HF and VARA FM modems. Provides automated packet message forwarding, an interactive live terminal, personal mailbox hosting, and station management.

---

## What's New in Version 2.5

* **Per-Station Dwell Timing**: Save dedicated dwell times on a per-station basis. Stations requiring extended delays due to challenging HF band conditions or path latencies retain their custom values automatically.


* **Dynamic Target Sync**: Selecting a BBS from the dropdown immediately populates that station's digipeater path and stored dwell interval.


* **Clean Text Composer**: Removed all background spellchecking and dictionary routines for a streamlined, responsive compose window with native text editing and context controls.


* **Backward-Compatible Storage**: Seamlessly loads existing `varabbs_data.json` databases, assigning defaults where station-specific dwell times are not yet defined.



---

## Core Capabilities

* **Dual-Mode VARA Support**: Pre-configured port selections and bandwidth defaults for VARA HF (ports 8358/8359, BW500) and VARA FM (ports 8300/8301, NARROW).


* **Automated Send/Recv Engine**: Connects, handles node routing, fetches unread mail using `RM`, and dispatches queued outbox messages using configurable dwell pacing and `/EX` termination.


* **Interactive Live Terminal**: Full type-ahead terminal session featuring one-click node and BBS commands (`N`, `R`, `L`, `S`, `CHAT`, `BBS`, `LM`, `RM`, `KM`, `B`). Double-click any message number in the terminal log to pull and read the message.


* **Mailbox Standby Mode**: Operates as a local personal mailbox on the air. Remote callers can connect, read waiting traffic (`LM`/`R`), compose personal messages (`SP`), send replies (`SR`), and disconnect (`B`).


* **Full Message Management**: Organize traffic across Inbox, Drafts, Outbox, Sent, and Trash folders with persistent message retention.


* **Custom Station Signatures**: Multi-line signature block configured to append automatically to outbound messages.


* **Theme Customization**: Integrated Light and Dark mode toggle.



---

## Prerequisites

* Python 3.8 or newer


* Tkinter support installed (`python3-tk` on Debian/Ubuntu/Raspberry Pi OS)


* An active instance of VARA HF or VARA FM running locally or over the LAN



No additional external Python packages (`pip`) are required.

---

## Installation & Launch

1. Save `varabbs_2.py` in your station operations directory.


2. Launch the client:
```bash
python3 varabbs_2.py

```


3. Enter your station callsign in **My Callsign**.


4. Set the **Modem Host IP** (default: `127.0.0.1` or the IP of your radio machine).


5. Select **Modem Type** (`HF` or `FM`) to load the proper command/data ports and default dwell times.



---

## Station & Dwell Configuration

1. In the **Target BBS** field, enter or select a callsign.


2. Set optional relay paths in the **Via Digi** field (e.g., `DIGI1` or `DIGI1 DIGI2`).


3. Enter the desired turnaround delay in **Dwell (s)** (e.g., `20.0` for HF conditions, `1.5` for local FM).


4. Click **`[+] Add`** to commit the settings for that station.


5. To remove a station, select it from the dropdown and click **`[-] Del`**.



All station profiles, mailbox items, outbox traffic, and station signatures persist automatically to `varabbs_data.json` upon exit.

---

## Operating Procedures

### Outbound Auto Session

1. Compose a message via **New Message** and click **Queue to Outbox**.


2. Choose the destination station from **Target BBS**.


3. Click **Send/Recv**. The client handles RF linking, switch navigation, message downloads, and queued transmissions sequentially.



### Live Terminal Session

1. Select the destination station and click **Connect (Term)**.


2. Monitor responses live in the terminal window.


3. Send interactive commands using the input box or the quick-command buttons on the left.


4. Click **Disconnect** to terminate the link cleanly.



### Mailbox Standby

1. Verify **My Callsign** and modem connectivity.


2. Click **Mailbox Standby**. The modem enters listen mode and will automatically service incoming RF connects directed to your station callsign.



---

## Author & Attribution

Designed and maintained by Glenn (N3MEL) for amateur radio emergency communications and digital data networking.