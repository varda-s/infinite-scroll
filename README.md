# Instagram Reel Tracker

Track Instagram Reel viewing time from an iPhone mirror feed, print a live reel receipt, and review replay/history in a web dashboard.

## What This App Does

- Runs a NiceGUI web app at `http://127.0.0.1:8080`.
- Starts and manages `uxplay` automatically from Python (no second terminal needed).
- Generates a rotating 4-digit AirPlay PIN for pairing.
- Accepts only **ReelTracker** mirror sources (booth mode, one mirrored device at a time).
- Lets operator/user manually click **Start Session** and **Stop Session**.
- Auto-detects reel transitions while session is running.
- Tracks per-reel duration and total session time in real time.
- Shows a live receipt stream during active session.
- Stores session data in SQLite.
- Stores reel screenshots and generates a replay video that mimics receipt printing.
- Session history updates automatically (no refresh button required).
- Session history includes:
  - stats cards
  - searchable table with preview/status/actions
  - replay + receipt text modal
  - charts for day-level and time-of-day usage

## Supported Mirroring Mode

This project is configured for a kiosk/booth workflow:

- Supported: **AirPlay to `ReelTracker` (uxplay)**
- Not used for booth detection: macOS iPhone Mirroring app / QuickTime mirror windows

Code path intentionally filters to ReelTracker-compatible mirror sources.

## Prerequisites

- macOS (Apple Silicon or Intel)
- Python `3.10+`
- iPhone with Screen Mirroring / AirPlay capability
- Xcode Command Line Tools
- `uxplay` available either:
  - at `/Users/amanagarwal/Desktop/Stanford/UxPlay/uxplay`, or
  - on `PATH` as `uxplay`

## Installation

```bash
git clone <your-repo-url>
cd infinite-scroll

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` includes `google-genai`, which is required for Gemini-based reel categorization.
On a new laptop, if categorization shows `Unclassified` for every reel, first make sure the app is running from this virtualenv after the install above.

## Install / Build UxPlay (Homebrew + Source Build)

### 1. Install macOS build tools

```bash
xcode-select --install
```

### 2. Install required Homebrew dependencies

```bash
brew update
brew install cmake pkg-config openssl@3 libplist glib gobject-introspection gstreamer
```

### 3. Build UxPlay from source

```bash
cd /Users/amanagarwal/Desktop/Stanford
git clone https://github.com/antimof/UxPlay.git
cd UxPlay
cmake -DCMAKE_BUILD_TYPE=Release .
make -j"$(sysctl -n hw.ncpu)"
```

### 4. Install (optional)

If you want `uxplay` globally available on `PATH`:

```bash
sudo make install
```

Note: this project already checks `/Users/amanagarwal/Desktop/Stanford/UxPlay/uxplay` first, so global install is optional.

### 5. Verify UxPlay works

```bash
/Users/amanagarwal/Desktop/Stanford/UxPlay/uxplay -h
```

Manual smoke test:

```bash
/Users/amanagarwal/Desktop/Stanford/UxPlay/uxplay -n "ReelTracker" -fps 120 -pin 1234
```

You should see `ReelTracker` as an AirPlay target on iPhone.

## Run The App

From this project directory:

```bash
source venv/bin/activate
python -m src.main
```

The app starts at:

- [http://127.0.0.1:8080](http://127.0.0.1:8080)

On startup, the app ensures pairing is ready before serving UI.

## iPhone Mirroring (How To Pair)

1. Start the app and open the dashboard.
2. Wait for the UI to show a pairing PIN (status badge / Devices panel).
3. On iPhone, open **Control Center → Screen Mirroring**.
4. Select **`ReelTracker`**.
5. Enter the PIN shown in UI.
6. Confirm UI shows **Device Paired**.

## Session Workflow

1. Pair iPhone to `ReelTracker`.
2. Click **Start Session**.
3. Open Instagram Reels on phone and scroll.
4. Watch live updates:
   - current reel number
   - current reel timer
   - total reels/time
   - live receipt cards
5. End by:
   - clicking **Stop Session**, or
   - disconnecting mirror

After session end, pairing is rotated so next user gets a fresh PIN.

## Output / Storage

- Database: `data/reel_tracker.db`
- Session screenshots: `output/sessions/session_<id>/reel_<nnnn>.png`
- Replay videos: `output/replays/session_<id>.mp4`
- Replay metadata: `output/replays/session_<id>.json`
- UxPlay logs:
  - `output/uxplay.stdout.log`
  - `output/uxplay.stderr.log`

## Replay Format

Session replay is rendered as a receipt-style print animation:

- header print
- per-reel timing hold
- per-reel printed block with screenshot centered
- session summary print

Video is normalized to browser-friendly H.264 for UI playback.

## CLI Mode (Optional)

```bash
# Run CLI mode
python -m src.main --cli

# CLI with mock capture source
python -m src.main --cli --mock-capture /path/to/video_or_images

# List detected mirror devices
python -m src.main --list-devices

# List USB printers
python -m src.main --list-printers
```

## Testing

```bash
# all tests
pytest

# targeted replay/media tests
pytest -q tests/unit/test_replay_service.py tests/unit/test_media_paths.py

# orchestrator regression test for reel numbering
pytest -q tests/integration/test_orchestrator.py::TestOrchestratorIntegration::test_reel_number_advances_from_current_reel_not_completed_count
```

## Troubleshooting

### `Failed to initialize ReelTracker pairing`

- Confirm `uxplay` is installed and runnable.
- Confirm the binary is at expected path or on `PATH`.
- Check logs in `output/uxplay.stderr.log`.

### `source .../gst-env` not found

- This is expected for Homebrew `gstreamer` installs.
- Do not use `gst-env` for this setup.
- Use the Homebrew dependencies listed above and run `uxplay` directly.

### `gst-plugin-scanner` / `libglib` / `gi.repository.Gst` warnings

- Reinstall core GStreamer/GLib packages:

```bash
brew reinstall glib gobject-introspection gstreamer
```

### ReelTracker not visible on iPhone

- Ensure app is running.
- Ensure Mac/iPhone are on the same network for AirPlay.
- If needed, click **Reset Pairing** in UI.

### PIN keeps re-prompting

- Make sure you are selecting `ReelTracker` (not another mirror target).
- Reset pairing in UI and retry with the latest PIN.

### Device shows disconnected unexpectedly

- Keep mirror stream active.
- If stream drops, pairing rotates by design; reconnect with fresh PIN.

### Replay or screenshots not loading

- Confirm files exist under `output/`.
- Hard refresh browser.
- Restart app if route state is stale.

## Project Structure

- `src/main.py`: app entrypoint (UI + CLI)
- `src/ui/app.py`: NiceGUI routing and dashboard composition
- `src/ui/services/device_service.py`: pairing/device polling lifecycle
- `src/ui/services/tracking_service.py`: session orchestration bridge
- `src/orchestrator.py`: capture loop + reel detection + tracker integration
- `src/detection/reel_detector.py`: reel transition detection logic
- `src/ui/services/replay_service.py`: replay generation
- `src/ui/database/`: SQLModel schema/repositories
