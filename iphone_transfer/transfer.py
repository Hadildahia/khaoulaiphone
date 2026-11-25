"""Copy photos and videos from the iPhone to a folder on the PC."""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Tuple

import pythoncom

from . import device as dev

CHUNK = 1024 * 1024  # 1 MB


class Cancelled(Exception):
    pass


@dataclass
class Summary:
    found: int = 0
    copied: int = 0
    skipped: int = 0
    bytes_copied: int = 0
    cancelled: bool = False
    failed: List[Tuple[str, str]] = field(default_factory=list)


def _copy_one(media: dev.MediaFile, dest_root: Path, cancel: threading.Event) -> int | None:
    """Copy one file. Returns bytes written, or None if it was already there."""
    target_dir = dest_root / media.subfolder
    target = target_dir / media.name
    if target.exists():
        return None

    target_dir.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    stream = dev.open_stream(media)
    written = 0
    try:
        with open(part, "wb") as out:
            while True:
                if cancel.is_set():
                    raise Cancelled()
                data = stream.Read(CHUNK)
                if not data:
                    break
                out.write(data)
                written += len(data)
        part.replace(target)  # only complete files get their real name
    except BaseException:
        part.unlink(missing_ok=True)
        raise

    # Keep the original date so files sort correctly in Explorer.
    try:
        modified = stream.Stat()[3]
        ts = modified.timestamp()
        os.utime(target, (ts, ts))
    except Exception:
        pass
    return written


def run_transfer(
    device: dev.Device,
    dest_root: Path,
    cancel: threading.Event,
    report: Callable[..., None],
) -> Summary:
    """Scan the camera roll, then copy everything not already on the PC.

    report(kind, ...) sends updates to the interface:
      ("status", text) ("log", text) ("progress", done, total)
    """
    pythoncom.CoInitialize()
    summary = Summary()
    try:
        report("status", "Looking for photos and videos…")
        files: List[dev.MediaFile] = []
        for media in dev.scan_media(device, cancel.is_set):
            files.append(media)
            if len(files) % 200 == 0:
                report("status", f"Found {len(files)} files so far…")
        if cancel.is_set():
            summary.cancelled = True
            return summary

        summary.found = len(files)
        videos = sum(1 for f in files if f.is_video)
        report("log", f"Found {len(files) - videos} photos and {videos} videos.")

        for i, media in enumerate(files, 1):
            report("status", f"Copying {media.name} ({i} of {len(files)})")
            try:
                written = _copy_one(media, dest_root, cancel)
            except Cancelled:
                summary.cancelled = True
                break
            except Exception as exc:  # keep going; report at the end
                summary.failed.append((media.name, str(exc)))
                report("log", f"Couldn't copy {media.name}: {exc}")
            else:
                if written is None:
                    summary.skipped += 1
                else:
                    summary.copied += 1
                    summary.bytes_copied += written
            report("progress", i, len(files))
        return summary
    finally:
        pythoncom.CoUninitialize()
