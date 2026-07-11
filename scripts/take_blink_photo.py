from __future__ import annotations

import argparse

from src.fridgechef.blink_camera import capture_blink_photo_sync


def main() -> None:
    """Capture one photo from the configured internal camera."""
    parser = argparse.ArgumentParser(description="Capture one internal camera photo for FridgeChef AI")
    parser.add_argument("--auth-file", default=r"C:\FridgeChef\blink_auth.json")
    parser.add_argument("--output", default=r"C:\FridgeChef\photos\blink_latest.jpg")
    parser.add_argument("--max-stale-seconds", type=int, default=120)
    args = parser.parse_args()

    output = capture_blink_photo_sync(args.auth_file, args.output, args.max_stale_seconds)
    print(f"New photo saved: {output}")


if __name__ == "__main__":
    main()
