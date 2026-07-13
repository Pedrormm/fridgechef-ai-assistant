from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path

try:
    from aiohttp import ClientSession
    from blinkpy.auth import Auth, BlinkTwoFARequiredError
    from blinkpy.blinkpy import Blink
    from blinkpy.helpers.util import json_load
except Exception:  # pragma: no cover - optional dependency for camera users
    ClientSession = None
    Auth = None
    BlinkTwoFARequiredError = Exception
    Blink = None
    json_load = None

from src.fridgechef.security import ensure_fresh_file


def _file_digest(path: Path) -> str:
    """Return a stable digest for a captured image without loading huge files repeatedly."""
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_new_capture_file(path: str | Path, started_at: float, max_stale_seconds: int, previous_digest: str = "") -> None:
    """Validate that the camera produced a fresh image for this request.

    Checking only that a file exists is not enough for a fridge camera workflow:
    an old image may still be present from a previous run. The modification time
    confirms that the file was written after the current click, while the digest
    check prevents silently reusing exactly the same cached file.
    """
    output_path = Path(path)
    ensure_fresh_file(output_path, started_at, max_stale_seconds)
    if previous_digest and _file_digest(output_path) == previous_digest:
        raise RuntimeError("La cámara no ha entregado una foto nueva. Revisa la conexión y vuelve a intentarlo.")


async def _login_blink(session: ClientSession, auth_file: Path) -> Blink:
    """Authenticate with Blink and reuse a local auth file when available."""
    if Blink is None or Auth is None or json_load is None:
        raise RuntimeError("La integración con la cámara interna no está instalada en este entorno.")
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
    previous_digest = _file_digest(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.parent.mkdir(parents=True, exist_ok=True)

    if ClientSession is None:
        raise RuntimeError("La integración con la cámara interna no está instalada en este entorno.")

    async with ClientSession() as session:
        blink = await _login_blink(session, auth_path)
        if not blink.cameras:
            raise RuntimeError("No he encontrado ninguna cámara interna configurada en la cuenta.")

        camera_name = list(blink.cameras.keys())[0]
        camera = blink.cameras[camera_name]

        await camera.snap_picture()
        await asyncio.sleep(8)
        await blink.refresh(force=True)
        await camera.image_to_file(str(output_path))

    ensure_new_capture_file(output_path, started_at, max_stale_seconds, previous_digest)
    return output_path


def capture_blink_photo_sync(auth_file: str, output_file: str, max_stale_seconds: int = 120) -> Path:
    """Synchronous wrapper used by Streamlit and simple scripts."""
    return asyncio.run(capture_blink_photo(auth_file, output_file, max_stale_seconds))
