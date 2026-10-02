# VARA HF/FM Mail & Terminal Client (v3.0)

A lightweight, zero-dependency Python and Tkinter workstation client for VARA HF and VARA FM modems. Designed for packet radio operators, hub stations, and emergency communications nets, this application combines automated store-and-forward message routing, an interactive type-ahead terminal, an integrated personal mailbox (PBBS), and per-station RF dwell tuning.

---

## What's New in Version 3.0

* **Direct Local PBBS Messaging ("Deposit to PBBS")**: Create and file messages addressed to other stations directly into your local PBBS storage without routing through an external BBS. Remote operators connecting to your station in Mailbox Standby are immediately notified of pending traffic and can pull it using standard `LM` and `R` commands.


* **Per-Station RF Dwell Tuning**: Configure and store dedicated turnaround dwell intervals on a per-station basis to accommodate difficult HF propagation, high latency, or rapid FM paths.


* **Clean Text Composer Engine**: Removed all background dictionary lookups, spellchecking overhead, and redline tags in favor of a lean, native editing environment with standard copy/paste context menus.


* **Dynamic Target Synchronization**: Switching target stations in the dropdown automatically reloads and populates that station's digipeater routing and specific dwell timings.


* **Streamlined UI Header**: Updated interface title banner to reflect version 3.0 station standards.

---

## Key Features

* **Dual Modem Profiles**: Instant preset switching between VARA HF (ports 8358/8359, BW500/BW2300/BW2750) and VARA FM (ports 8300/8301, NARROW/WIDE).


* **Automated Batch Sessions**: Connects to remote nodes/switches, enters the BBS subsystem, downloads unread messages with `RM`, and dispatches queued Outbox messages using `/EX` termination and configurable turnaround pacing.


* **Interactive Live Terminal**: Full duplex type-ahead monitor supporting quick node/BBS commands (`N`, `R`, `L`, `S`, `CHAT`, `BBS`, `LM`, `RM`, `KM`, `B`) and double-click message number extraction.


* **Inbound Mailbox Hosting (PBBS Standby)**: Operates your station as an open or personal mailbox. Remote callers can connect via RF, view welcome bulletins, list personal mail (`LM`), read messages (`R <num>`), deposit private messages (`SP`), post bulletins (`SB`), reply to existing traffic (`SR <num>`), or delete their messages (`KM <num>`).


* **Folder Management**: Local storage categorized across Inbox, Drafts, Outbox, Sent, and Trash with automated JSON synchronization (`varabbs_data.json`).


* **HTML Forms Integration**: Quick access to TPRFN online radiogram and emergency forms suite.


* **Light / Dark Themes**: Instant palette toggling tailored for day or night station operation.



---

## System Requirements

* Python 3.8 or higher


* Tkinter (`python3-tk` on Debian/Ubuntu/Raspberry Pi OS)


* VARA HF (v1.4.0+) or VARA FM (v4.3.0+) modem software running locally or accessible across the local network



No external third-party Python modules (`pip`) are required.

---

## Installation & Setup

1. Place `varabbs.py` in your chosen working directory.


2. Start the application:
```bash
python varabbs.py

```


3. Enter your station callsign in **My Callsign** (e.g., `N3MEL`).


4. Set the **Modem Host IP** (default: `127.0.0.1` or the remote host IP running the modem).


5. Select the **Modem Type** (`HF` or `FM`). The software will automatically configure default command ports, data ports, and default dwell timings.



---

## Operating Instructions

### Depositing Messages for Local Callers (PBBS)

1. Click **New Message**.


2. Enter the recipient's callsign in **To Callsign** and fill out the **Subject** and **Body**.


3. Click **Deposit to PBBS**. The message is filed directly into your local database.


4. Enable **Mailbox Standby** on the top toolbar.


5. When the recipient station connects to your station via RF, your station alerts them that unread traffic is waiting. They retrieve it by sending `LM` followed by `R <msg_num>`.



### Dispatching Outbound Messages to a Remote BBS

1. Click **New Message**.


2. Enter the destination callsign/distribution address, subject, and text.


3. Click **Queue to Outbox (Remote BBS)**.


4. Select the target BBS from the **Target BBS** dropdown.


5. Click **Send/Recv**. The client connects to the BBS, pulls new unread mail via `RM`, sends each queued item, and files completed transfers into **Sent**.



### Managing Station Profiles & Dwell Settings

1. Select or type a station callsign into **Target BBS**.


2. Specify digipeater paths in **Via Digi** (e.g., `DIGI1` or `DIGI1 DIGI2`) if routing through repeaters or switches.


3. Adjust **Dwell (s)** to provide sufficient transmit/receive turnaround delay (e.g., `20.0` for HF paths with latency or slow relays, `1.5` for direct VHF/UHF FM).


4. Click **`[+] Add`** to save or update the profile.



---

## Data Storage

All runtime data, station dwell tables, message folders, and configuration parameters are automatically saved to `varabbs_data.json` in the application directory upon shutdown.
