# VARA HF/FM Mail & Terminal Client

A standalone, high-reliability Python/Tkinter desktop station client designed for amateur radio packet and store-and-forward operations using **VARA HF** and **VARA FM** software modems. It interfaces directly with BPQ32, LinBPQ, and standard packet radio Mailbox/BBS systems across HF and VHF/UHF networks.

---

## What's New in This Release

- **Light Mode Default & Quick Theme Toggle:** Starts automatically in clean, high-visibility Light Mode on every launch, with an on-the-fly `🌙 Dark / ☀️ Light` toggle button on the top control bar.
- **Scrollable Sidebar Architecture:** The entire left-hand column (Mailboxes, Settings, Node Commands, and Quick Reference) is embedded in an auto-fitting canvas with dedicated vertical scrollbars and live mousewheel support to prevent display clipping on compact screens.
- **Message Type Selection (SP vs SB):** Radio buttons in the composer allow seamless toggling between **SP (Private)** and **SB (Bulletin)** modes. The automated engine dispatches each message with the appropriate protocol header over RF.
- **Recipient & Bulletin History Management:** The `To:` field features an editable dropdown history of past callsigns and bulletin routes (`ALL@USA`, `NEWS@WW`, etc.) with quick `➕ Add` and `🗑️ Del` management buttons.
- **Integrated Spell Checker & Custom Dictionary:** Built-in, zero-dependency spell engine highlights unrecognized words in high-contrast red/pink styling. Right-clicking flagged words provides instant spelling corrections plus a **`➕ Add to Dictionary`** option that saves entries permanently to local storage.
- **Universal Right-Click Context Menus:** Native Cut, Copy, Paste, and Select All menus across all input bars, terminal logs, signature editors, and message fields.
- **Direct Web Link to HTML Form Suite:** Top-bar launch button connects directly to the TPRFN online HTML-to-ASCII Form Suite (`https://www.tprfn.net/html-form-suite`) in your default web browser.

---

## Core Capabilities

- **Dual-Mode Modem Switching (HF & FM):**
  - Instantly toggles between VARA HF (Ports `8358`/`8359`, `BW500`) and VARA FM (Ports `8300`/`8301`, `NARROW`).
  - Swaps station contact directories dynamically between HF targets (`MELBBS`, `W3PND-1`, etc.) and FM targets (`MELBBS-1`, `WIDE1-1`, etc.).
- **Automated Send / Receive Exchange:**
  - Automated link establishment with digipeater pathing (`VIA DIGI`).
  - 40-second channel turnaround guard delay on VARA HF to eliminate station collisions before command handshakes.
  - Multi-message extraction engine parses all unread bulletins and personal mail via `RM` (Read Mine) directly into your Inbox.
  - Sequenced Outbox flushing: Handshakes destination callsign (`SP`/`SB`), waits for BBS prompts, delivers subject, uploads body with station signature, and terminates cleanly with `/EX` and `B`.
- **Live Terminal & Traffic Monitor:**
  - Dedicated type-ahead command bar at the top of the monitor.
  - Interactive line inspector: Double-click any message number in the terminal window to fetch `R <num>` live from the BBS or open it from the local cache.
- **Command Quick Reference Card:**
  - On-screen quick-syntax cheat sheet for packet operations (`R msg#`, `SP callsign`, `SB ha route`, `SR msg#`, `ST zip & st`).

---

## Requirements

1. **Python 3.8+**
2. **Tkinter** (standard in Windows/macOS; on Debian/Ubuntu/Raspberry Pi OS: `sudo apt install python3-tk`)
3. An active instance of **VARA HF** or **VARA FM** accessible via TCP/IP.
4. *(Optional)* `pyspellchecker` (`pip install pyspellchecker`) — the application includes an internal spell engine and OS dictionary loader that runs out-of-the-box with zero third-party dependencies.

---

## Installation & Setup

1. **Download the Script:**
   Place `varabbs.py` in your chosen local directory.

2. **Launch the Application:**
   ```bash
   python varabbs.py