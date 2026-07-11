from __future__ import annotations

import asyncio
import time
from pathlib import Path

from aiohttp import ClientSession
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink
from blinkpy.helpers.util import json_load

from src.fridgechef.security import ensure_fresh_file


async def _login_blink(session: ClientSession, auth_file: Path) -> Blink:
    """Authenticate with Blink and reuse a local auth file when available."""
    blink = Blink(session=session)

    if auth_file.exists():
        auth_data = await json_load(str(auth_file))
        blink.auth = Auth(auth_data, session=session)

    try:
        await blink.start()
    except BlinkTwoFARequiredError:
        print("Two-factor authentication is required. Enter the code in the console when prompted.")
        await blink.prompt_2fa()

    await blink.save(str(auth_file))
    return blink


async def capture_blink_photo(auth_file: str, output_file: str, max_stale_seconds: int = 120) -> Path:
    """Capture one fresh image from the first available internal camera."""
    started_at = time.time()
    auth_path = Path(auth_file)
    output_path = Path(output_file)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.parent.mkdir(parents=True, exist_ok=True)

    async with ClientSession() as session:
        blink = await _login_blink(session, auth_path)
        if not blink.cameras:
            raise RuntimeError("No camera was found in the configured account.")

        camera_name = list(blink.cameras.keys())[0]
        camera = blink.cameras[camera_name]

        await camera.snap_picture()
        await asyncio.sleep(8)
        await blink.refresh(force=True)
        await camera.image_to_file(str(output_path))

    ensure_fresh_file(output_path, started_at, max_stale_seconds)
    return output_path


def capture_blink_photo_sync(auth_file: str, output_file: str, max_stale_seconds: int = 120) -> Path:
    """Synchronous wrapper used by Streamlit and simple scripts."""
    return asyncio.run(capture_blink_photo(auth_file, output_file, max_stale_seconds))
