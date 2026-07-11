from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "automation" / "config.yaml"


def valid_email(email: str) -> bool:
    """Validate optional notification addresses before sending anything."""
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""))


def main() -> None:
    """Run a small local automation flow that can be expanded later with UiPath."""
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

    if not cfg.get("automation_enabled"):
        print("Automation is disabled in config.yaml")
        return

    engine = cfg.get("automation_engine", "python").lower()
    if engine == "uipath":
        print("UiPath mode is selected. Start the REFramework process from UiPath Studio or Assistant.")
        return

    photo_file = ROOT / cfg.get("blink", {}).get("output_file", "photos/blink_latest.jpg")

    if cfg.get("blink", {}).get("take_photo", True):
        print("Capturing a new internal camera photo...")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "take_blink_photo.py")], check=False)

    if not photo_file.exists():
        print("No internal camera photo is available. The web app can still continue with manual input or an uploaded image.")
    else:
        age = time.time() - photo_file.stat().st_mtime
        max_age = int(cfg.get("blink", {}).get("max_photo_age_seconds", 120))
        if age > max_age:
            print(f"A photo exists, but it is older than expected: {int(age)} seconds.")
        else:
            print(f"Recent internal camera photo found: {photo_file}")

    if cfg.get("send_email") and not valid_email(cfg.get("email_to", "")):
        print("The configured email address is not valid. The automation will continue without sending email.")

    print("Automation completed.")


if __name__ == "__main__":
    main()
