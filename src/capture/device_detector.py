"""Auto-detect connected iPhone via screen mirroring."""

from src.capture.base import DeviceType, DeviceInfo


class DeviceDetector:
    """Detect connected iPhones via screen mirroring."""

    @staticmethod
    def detect_mirror_devices() -> list[DeviceInfo]:
        """Detect ReelTracker booth mirrors (uxplay/GStreamer).

        This intentionally excludes iPhone Mirroring/QuickTime and other mirrors.

        Returns:
            List of detected mirror sources as DeviceInfo.
        """
        devices = []

        try:
            from src.capture.mirror_capture import MirrorDetector

            mirrors = MirrorDetector.detect_reeldetector_windows()

            for mirror in mirrors:
                # Only expose devices that appear to have an active mirrored stream.
                if not MirrorDetector.is_stream_active(mirror):
                    continue

                devices.append(
                    DeviceInfo(
                        device_type=DeviceType.IOS,
                        device_id=f"mirror:{mirror.app_name}:{mirror.window_name}",
                        device_name=f"{mirror.window_name} (Screen Mirror)",
                        model=mirror.app_name,
                        connection_type="mirror",
                    )
                )

        except ImportError:
            pass
        except Exception:
            pass

        # Booth mode supports one mirrored participant at a time.
        return devices[:1]

    @classmethod
    def detect_all_devices(cls) -> list[DeviceInfo]:
        """Detect all connected devices via screen mirroring.

        Returns:
            List of all detected devices.
        """
        return cls.detect_mirror_devices()

    @classmethod
    def get_preferred_device(cls) -> DeviceInfo | None:
        """Get the preferred device to use.

        Returns:
            DeviceInfo of preferred device, or None if no devices found.
        """
        devices = cls.detect_all_devices()
        return devices[0] if devices else None
