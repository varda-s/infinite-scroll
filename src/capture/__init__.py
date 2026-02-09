"""Connectors for phone-to-app connectivity.

Connectors are the bridge between a phone and this application. Each connector
implements the BaseCapture interface to provide:
- Screen capture from the connected device
- Foreground app detection (when possible)
- Session start/stop detection capabilities

Available Connectors:
- MirrorCapture: iPhone-to-Mac mirroring via QuickTime (recommended)
- MockCapture: Testing with video files or image directories

Future connectors can be added by implementing the BaseCapture interface.
"""

from src.capture.base import BaseCapture, DeviceInfo, DeviceType, ForegroundApp
from src.capture.device_detector import DeviceDetector
from src.capture.mirror_capture import MirrorCapture
from src.capture.mock_capture import MockCapture

__all__ = [
    "BaseCapture",
    "DeviceInfo",
    "DeviceType",
    "ForegroundApp",
    "DeviceDetector",
    "MirrorCapture",
    "MockCapture",
]
