"""Detect Instagram app in the foreground."""

from dataclasses import dataclass
from enum import Enum, auto


class AppState(Enum):
    """Current state of the Instagram app."""

    NOT_RUNNING = auto()
    RUNNING_BACKGROUND = auto()
    RUNNING_FOREGROUND = auto()
    REELS_MODE = auto()


@dataclass
class ForegroundAppInfo:
    """Information about the current foreground app."""

    package_name: str  # Android package or iOS bundle ID
    activity_name: str | None = None  # Android activity
    is_instagram: bool = False
    is_reels_mode: bool = False


class AppDetector:
    """Detect Instagram app and its state."""

    INSTAGRAM_PACKAGE_ANDROID = "com.instagram.android"
    INSTAGRAM_BUNDLE_IOS = "com.burbn.instagram"

    # Known Instagram activities that indicate reels mode
    REELS_ACTIVITIES = [
        "clips",
        "reels",
        "ReelsViewerFragment",
        "ClipsViewerFragment",
    ]

    def __init__(
        self,
        android_package: str = INSTAGRAM_PACKAGE_ANDROID,
        ios_bundle_id: str = INSTAGRAM_BUNDLE_IOS,
    ) -> None:
        """Initialize app detector.

        Args:
            android_package: Android package name for Instagram.
            ios_bundle_id: iOS bundle ID for Instagram.
        """
        self.android_package = android_package
        self.ios_bundle_id = ios_bundle_id

    def is_instagram_package(self, package_name: str) -> bool:
        """Check if package/bundle ID is Instagram.

        Args:
            package_name: Package name or bundle ID to check.

        Returns:
            True if it's Instagram.
        """
        return package_name in (self.android_package, self.ios_bundle_id)

    def is_reels_activity(self, activity_name: str | None) -> bool:
        """Check if activity name suggests reels mode.

        Args:
            activity_name: Activity or view controller name.

        Returns:
            True if it appears to be reels mode.
        """
        if not activity_name:
            return False

        activity_lower = activity_name.lower()
        return any(reel_keyword in activity_lower for reel_keyword in self.REELS_ACTIVITIES)

    def detect_from_info(self, app_info: ForegroundAppInfo) -> AppState:
        """Detect Instagram state from app info.

        Args:
            app_info: Information about the foreground app.

        Returns:
            Current state of Instagram.
        """
        if not self.is_instagram_package(app_info.package_name):
            return AppState.NOT_RUNNING

        if app_info.is_reels_mode or self.is_reels_activity(app_info.activity_name):
            return AppState.REELS_MODE

        return AppState.RUNNING_FOREGROUND

    def parse_android_dumpsys(self, dumpsys_output: str) -> ForegroundAppInfo | None:
        """Parse Android dumpsys output to get foreground app info.

        Args:
            dumpsys_output: Output from `adb shell dumpsys activity activities`.

        Returns:
            ForegroundAppInfo or None if parsing fails.
        """
        # Look for mResumedActivity line
        for line in dumpsys_output.split("\n"):
            if "mResumedActivity" in line or "topResumedActivity" in line:
                # Format: mResumedActivity: ActivityRecord{...} com.package/com.package.Activity
                parts = line.split()
                for part in parts:
                    if "/" in part and "." in part:
                        # Found package/activity format
                        package_activity = part.strip("{}")
                        if "/" in package_activity:
                            package, activity = package_activity.split("/", 1)
                            return ForegroundAppInfo(
                                package_name=package,
                                activity_name=activity,
                                is_instagram=self.is_instagram_package(package),
                                is_reels_mode=self.is_reels_activity(activity),
                            )
        return None
