# Instagram Reel Tracker

Track your Instagram Reel scrolling and print receipts showing how much time you spent on each reel.

## Architecture: Connectors

The app uses a **connector pattern** to bridge your phone to the application. Each connector:
- Captures the phone screen
- Detects when a reel scrolling session starts
- Detects when the user scrolls to the next reel

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CONNECTOR LAYER                              │
│                                                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │              BaseCapture (Interface)                         │   │
│   │  - capture_screen() → PIL Image                              │   │
│   │  - get_foreground_app() → App info                           │   │
│   │  - connect() / disconnect()                                  │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│              ┌───────────────┴───────────────┐                      │
│              ▼                               ▼                      │
│   ┌─────────────────────┐         ┌─────────────────────┐          │
│   │   MirrorCapture     │         │    MockCapture      │          │
│   │   (iPhone → Mac)    │         │    (Testing)        │          │
│   │                     │         │                     │          │
│   │  Uses QuickTime to  │         │  Uses video files   │          │
│   │  mirror iPhone      │         │  or image dirs      │          │
│   └─────────────────────┘         └─────────────────────┘          │
│                                                                      │
│   Future connectors can be added by implementing BaseCapture        │
└─────────────────────────────────────────────────────────────────────┘
```

### Current Connector: iPhone-to-Mac Mirroring

The primary connector supports two mirroring methods:

#### Option 1: iPhone Mirroring (Wireless - Recommended)

**Requirements:** macOS 15 (Sequoia) or later, iOS 18 or later, same Apple ID on both devices

1. **Open iPhone Mirroring** app on your Mac (in Applications)
2. Follow the setup prompts if this is your first time
3. Your iPhone screen appears wirelessly on your Mac!

Benefits:
- Completely wireless - no cable needed
- Built into macOS, no extra software
- Low latency, high quality

#### Option 2: QuickTime Player (USB Fallback)

**Requirements:** Any macOS version, USB cable

This approach:
- Requires no developer mode or special setup on iPhone
- Just needs a USB cable and trust confirmation
- Works with any iPhone

## Quick Start

### 1. Clone and Install

```bash
# Clone the repository
git clone <repository-url>
cd infinite-scroll

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

The database is automatically created on first run in the `data/` directory.

### 2. Connect Your iPhone

**No developer mode required!** Choose one of these methods:

#### Wireless (macOS 15+ / iOS 18+)

1. **Open iPhone Mirroring** app on your Mac
2. Your iPhone screen appears wirelessly!
3. Session will auto-start when you open Instagram Reels

#### USB (Any macOS)

1. **Plug your iPhone into your Mac via USB cable**
2. **Tap "Trust"** when your iPhone asks "Trust This Computer?"
3. **Open QuickTime Player** on your Mac
4. Go to **File → New Movie Recording**
5. Click the **small arrow** next to the record button
6. Select your **iPhone** under "Camera"
7. Your iPhone screen now appears in QuickTime!

### 3. Start the App

```bash
source venv/bin/activate
python -m src.main
```

Open **http://localhost:8080** in your browser.

### 4. Start Tracking

1. Your iPhone should appear in the **Devices** panel as a "Screen Mirror"
2. Select your printer (Mock for on-screen, Rongta for thermal printer)
3. Click **"Start Session"**
4. Open Instagram on your iPhone and scroll through Reels
5. Watch the receipts build in real-time!
6. Click **"Stop Session"** when done

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Your iPhone   │────▶│ QuickTime Mirror│────▶│   Reel Tracker  │
│   (Instagram)   │ USB │   (on your Mac) │     │   (this app)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │  Receipt Printer│
                                                │  (or on-screen) │
                                                └─────────────────┘
```

The app:
1. Captures your iPhone screen from the QuickTime window
2. Detects when you scroll to a new Reel (using image analysis / perceptual hashing)
3. Times how long you spend on each Reel
4. Prints a receipt showing your scrolling habits

## Reel Detection

The connector provides screen captures that are analyzed to detect:

1. **Session Start**: When the user enters Instagram Reels mode
2. **New Reel**: When the user scrolls to the next reel (detected via perceptual hash comparison)
3. **Session End**: When the user leaves Reels mode

### Auto Session Detection (Mirror Mode)

When using screen mirroring (iPhone Mirroring or QuickTime), the app uses **content-based detection** to automatically:

- **Detect when you open Reels**: Analyzes screen content for vertical video patterns
- **Detect when you leave Reels**: Notices dramatic content changes or screen lock
- **Track reel changes**: Uses perceptual hashing (pHash) to detect scrolling

This means you don't need to manually start/stop sessions - just open Instagram Reels and start scrolling!

**How it works:**
- Vertical aspect ratio (9:16) detection
- High entropy content analysis (video vs static UI)
- Perceptual hash comparison for reel transitions
- Black screen detection for session end

This detection logic is built on top of the connector's `capture_screen()` method and works identically for both wireless and USB mirroring.

## Dashboard

```
+----------------------------------------------------------+
|               INSTAGRAM REEL TRACKER                       |
+----------------------------------------------------------+
|                                                            |
|  +----------------+  +----------------------------------+  |
|  |    DEVICES     |  |         LIVE SESSION             |  |
|  +----------------+  +----------------------------------+  |
|  | iPhone         |  |  Status: Recording               |  |
|  | (Screen Mirror)|  |  Reel #: 5  |  Time: 12.3s       |  |
|  |                |  |  Total: 5 reels  |  2m 45s       |  |
|  +----------------+  +----------------------------------+  |
|  |    PRINTER     |  |  +----------------------------+  |  |
|  +----------------+  |  |     LIVE RECEIPT          |  |  |
|  | (*) Mock       |  |  | ========================  |  |  |
|  | ( ) Rongta     |  |  | INSTAGRAM REEL TRACKER    |  |  |
|  +----------------+  |  | Session: 2024-01-15...    |  |  |
|  | [Start Session]|  |  | REEL #5                   |  |  |
|  | [Stop Session] |  |  | Time: 8.2s                |  |  |
|  +----------------+  |  +----------------------------+  |  |
+----------------------------------------------------------+
```

## Sample Receipt

```
==========================================
        INSTAGRAM REEL TRACKER
==========================================
  Session started: 2024-01-15 14:30:22
------------------------------------------

  REEL #1
------------------------------------------
  [ASCII art of screenshot]
------------------------------------------
  Time spent: 12.5s
------------------------------------------

  REEL #2
  ...

==========================================
           SESSION COMPLETE
==========================================
  Total reels viewed: 15
  Total time: 3m 45s
  Avg time per reel: 15.0s
------------------------------------------
      THANK YOU FOR SCROLLING!

   Maybe go outside for a bit? :)
------------------------------------------
==========================================
```

## Using a Thermal Printer

The app supports Rongta thermal receipt printers:

1. Connect the printer via USB
2. Turn on the printer
3. Select **"Rongta"** in the Printer panel
4. Start a session and scroll!

If the printer isn't detected, use Mock mode to test on-screen first.

## Troubleshooting

### iPhone not showing in Devices panel?

1. Make sure QuickTime is open with your iPhone mirroring
2. The QuickTime window must be visible (not minimized)
3. Refresh the page or restart the app

**Debug what windows are detected:**
```bash
python3 -c "from src.capture.mirror_capture import MirrorDetector; print(MirrorDetector.debug_all_windows())"
```

### QuickTime not showing my iPhone?

1. Disconnect and reconnect the USB cable
2. Unlock your iPhone
3. Tap **"Trust"** if the trust prompt appears
4. In QuickTime, click the dropdown arrow next to record and select your iPhone

### No reels detected when scrolling?

- Make sure you're in the **Reels tab** (full-screen vertical video mode)
- The app only tracks when you're actively viewing Reels
- Try scrolling slowly at first

### Session won't start?

- Wait for your device to appear in the Devices panel
- The Start button is disabled until a device is detected

## CLI Mode

For power users:

```bash
# CLI mode with mock printer
python -m src.main --cli

# CLI mode with Rongta printer
python -m src.main --cli --printer rongta

# Test without a phone (uses sample images/video)
python -m src.main --cli --mock-capture ./assets/test_images/
python -m src.main --cli --mock-capture ./test_video.mp4

# List connected devices
python -m src.main --list-devices

# List USB printers
python -m src.main --list-printers
```

## Adding New Connectors

To add support for a new phone connection method:

1. Create a new class that implements `BaseCapture` (see `src/capture/base.py`)
2. Implement the required methods:
   - `capture_screen()`: Return a PIL Image of the phone screen
   - `get_foreground_app()`: Return info about the current app (if possible)
   - `connect()` / `disconnect()`: Handle connection lifecycle
3. Register the connector in `src/capture/__init__.py`

Example connector interface:

```python
from src.capture.base import BaseCapture, DeviceInfo, ForegroundApp
from PIL import Image

class MyNewConnector(BaseCapture):
    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        ...

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        ...

    def connect(self) -> bool:
        """Establish connection. Return True on success."""
        ...

    def disconnect(self) -> None:
        """Close connection."""
        ...

    def capture_screen(self) -> Image.Image | None:
        """Capture and return the current screen."""
        ...

    def get_foreground_app(self) -> ForegroundApp | None:
        """Get foreground app info (optional)."""
        ...
```

## Requirements

- **macOS** (required for screen mirroring)
  - macOS 15+ (Sequoia) for wireless iPhone Mirroring
  - Any macOS version for QuickTime USB mirroring
- **Python 3.10+**
- **iPhone**
  - iOS 18+ for wireless iPhone Mirroring
  - Any iOS version for QuickTime USB mirroring
  - USB cable only needed for QuickTime method
- **Rongta printer** (optional, for physical receipts)

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest tests/ -v

# Format code
black src/ tests/

# Lint
ruff check src/ tests/
```

## License

MIT License
