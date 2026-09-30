```markdown
# VARA HF/FM Mail Client & Personal Mailbox Station

A zero-dependency Python/Tkinter client and automated host station designed for amateur radio operators using VARA HF and VARA FM software modems[cite: 5].

The software operates in two distinct operational roles:
1. **Outbound BBS Client:** Dials remote packet/Winlink BBS systems and nodes either manually or through automated batch processing to send queued traffic and retrieve unread personal messages (`RM`)[cite: 5].
2. **Inbound Personal Mailbox Host (Standby Mode):** Turns your station into an interactive mini-BBS over RF using `LISTEN ON`[cite: 5]. Connecting stations receive a welcome banner, unread mail alerts, and a command shell supporting listing, reading, replying to, and posting traffic[cite: 5].

---

## Key Features

### Inbound Mailbox Host (`Mailbox Standby`)
* **Background Listener:** Manages background sockets to the VARA modem, sets your callsign (`MYCALL`), and enables `LISTEN ON`[cite: 5].
* **Automatic Unread Mail Notification:** When an RF station connects, the mailbox checks stored messages for traffic addressed to the caller's callsign or base callsign[cite: 5]. If messages exist, the station is alerted in the greeting:
  ```text
  *** YOU HAVE 1 MESSAGE(S) WAITING IN THIS MAILBOX ***
  Type LM to list your messages or R <num> to read.

```

* **Interactive Command Parser:** Over-the-air shell supporting standard packet commands:


* `L`: Lists all stored messages.


* `LM`: Lists only messages addressed to the connecting station.


* `R <num>`: Reads message `<num>`.


* `SR <num>`: Sends a reply to message `<num>`. Automatically addresses the original sender, prefixes the subject with `RE: `, and prompts for body text.


* `SP <call>` / `SB <route>`: Initiates a private message or bulletin. Prompts for subject and text, ending with `/EX` on a new line.


* `KM <num>`: Deletes message `<num>` (permitted if caller is sender, recipient, or local sysop).


* `B` / `BYE` / `Q`: Sends a 73 greeting and terminates the connection.




* **Direct Database Synchronization:** Inbound traffic posted via `SP` or `SR` is immediately saved to the local database, refreshing GUI tables and folder counters.



### Outbound Client Operations

* **Automated Send/Recv Engine:** Handles node-to-BBS switching, downloads unread messages via `RM`, parses them into your Inbox, transmits queued Outbox items ending with `/EX`, and disconnects.


* **Live Interactive Terminal:** Provides manual console operation with type-ahead buffering and side-by-side quick-command buttons (`N`, `R`, `L`, `S`, `U`, `CHAT`, `BBS`, `B`, `LM`, `RM`, `KM`).


* **Double-Click Retrieval:** Double-clicking any message number in the live terminal log automatically issues an `R <num>` read command to the remote system.


* **Collision Protection:** Outbound calls automatically suspend background listening to prevent port conflicts on the modem.



### Station Controls & Usability

* **Per-Mode Dwell Timing:** Independent dwell delay inputs (in seconds) for HF and FM modes. Caches and persists adjustments directly to storage when swapping modes.


* **Automatic Preset Swapping:** Selecting **HF** or **FM** adjusts port defaults (`8358`/`8359` vs. `8300`/`8301`), bandwidth selectors (`BW500` vs. `NARROW`), dwell times, and contact lists.


* **Offline Spell Checker:** Built-in spell checking with right-click suggestions and a persistent personal dictionary.


* **Folder Hierarchy:** Full folder sorting (**Inbox**, **Drafts**, **Outbox**, **Sent**, **Trash**) with message previewing and status counters.


* **ASCII Interface:** Clean labels avoid font-encoding and `??` display artifacts across different operating systems.


* **TPRFN Form Suite Launcher:** Opens the online HTML-to-ASCII Radiogram and Skywarn form generator directly in your browser.



---

## Requirements

* **Python:** 3.8 or higher.
* **Tkinter:** Included with standard Python on Windows/macOS; install `python3-tk` on Linux.
* **Modem Software:**
* [VARA HF](https://rosmodem.wordpress.com/) (Default command port `8358`, data port `8359`)


* [VARA FM](https://rosmodem.wordpress.com/) (Default command port `8300`, data port `8301`)





---

## Installation & Setup

1. **Clone or Download the Script:**
```bash
git clone [https://github.com/](https://github.com/)<your-username>/varabbs-station.git
cd varabbs-station

```


2. **Install Tkinter (Linux only):**
```bash
sudo apt update
sudo apt install python3-tk

```


3. **Modem Verification:**
* Open VARA HF or VARA FM.
* Under **Settings -> Setup**, ensure command/data ports match your configuration (e.g., `8300`/`8301` for FM, `8358`/`8359` for HF).


* If accepting incoming connections in Standby mode, check **Allow VARA to accept incoming connections**.


4. **Launch the Application:**
```bash
python3 varabbs_2.py

```


*(Or run your renamed script file).*

---

## Configuration Reference (Left Sidebar)

* **Modem Type:** Toggle between `HF` and `FM`. This automatically swaps the active contact list, ports, bandwidth choices, and dwell timing.


* **My Callsign:** Enter your callsign and optional SSID (e.g., `N3MEL` or `N3MEL-2`).


* **Modem Host IP:** Set to `127.0.0.1` for a local modem, or the LAN IP (e.g., `192.168.86.34`) if running across a network.


* **Cmd / Data Ports:** TCP stream ports for control and data (defaults to `8300`/`8301` for FM, `8358`/`8359` for HF).


* **Dwell (s):** Wait time in seconds before command dispatch and between outbound packets (e.g., `20.0` for HF, `1.5` for FM). Automatically saved per mode.


* **Bandwidth / Mode:** Select `BW500`, `BW2300`, or `BW2750` on HF; select `NARROW` or `WIDE` on FM.


* **Station Signature:** Up to 6 lines of text automatically appended to outgoing messages.



---

## Mailbox Over-The-Air Command Set

Remote stations connecting to your station while in **Mailbox Standby** mode have access to the following commands:

| Command | Syntax | Description |
| --- | --- | --- |
| **Help** | `?` or `H` | Displays command syntax reference.

 |
| **List All** | `L` | Lists all messages currently stored in the mailbox.

 |
| **List Mine** | `LM` | Lists only messages addressed to the connecting station's callsign.

 |
| **Read** | `R <num>` | Displays the complete header and body of message `<num>`.

 |
| **Send Reply** | `SR <num>` | Replies to message `<num>`. Automatically addresses the original sender, prefixes `RE: ` to the subject, and prompts for text ending with `/EX`.

 |
| **Send Personal** | `SP <call>` | Sends a private message to `<call>`. Prompts for subject and body, ending with `/EX`.

 |
| **Send Bulletin** | `SB <route>` | Posts a bulletin. Prompts for subject and body, ending with `/EX`.

 |
| **Kill Message** | `KM <num>` | Deletes message `<num>` if the caller is the sender or recipient.

 |
| **Disconnect** | `B`, `BYE`, `Q` | Sends a logoff greeting and drops the RF connection.

 |

---

## File Structure & Persistence

All operational parameters, mailbox messages, contact records, user dictionary terms, and window dimensions are automatically managed in `varabbs_data.json`:

```text
varabbs-station/
|-- varabbs_2.py          # Primary application executable
|-- varabbs_data.json     # Station database & settings persistence
`-- README.md             # Operational documentation

```

If `varabbs_data.json` is deleted or missing, the software generates a clean fallback configuration with default ports (`8300`/`8301`), FM mode, default contacts, and empty message queues.

```

```