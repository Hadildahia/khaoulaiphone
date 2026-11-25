"""Read an iPhone's camera roll through the Windows Shell.

When an iPhone is plugged in and trusted, Windows exposes it as a camera
(Windows Portable Devices) using its own built-in driver. That means no
iTunes and no Apple software are needed to read photos and videos.

Typical path in File Explorer:  This PC > Apple iPhone > Internal Storage > DCIM > 100APPLE
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator, List

import pythoncom
import pywintypes
from win32comext.shell import shell, shellcon

APPLE_USB_VENDOR = "vid_05ac"  # Apple's USB vendor id, appears in the device path
BHID_STREAM = pywintypes.IID("{1CEBB3AB-7C10-499A-A417-92CA16C4CB83}")

PHOTO_EXTS = {".heic", ".heif", ".jpg", ".jpeg", ".png", ".gif", ".dng", ".tif", ".tiff", ".webp"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".hevc"}
MEDIA_EXTS = PHOTO_EXTS | VIDEO_EXTS

ENUM_FLAGS = (
    shellcon.SHCONTF_FOLDERS | shellcon.SHCONTF_NONFOLDERS | shellcon.SHCONTF_INCLUDEHIDDEN
)

LOCKED_HELP = (
    "Your iPhone is connected, but its photos aren't visible yet. "
    "Unlock the iPhone, tap Trust on the pop-up, then press Refresh."
)


class DeviceError(Exception):
    """A problem the user can fix (locked phone, not trusted, unplugged)."""


@dataclass
class Device:
    name: str
    pidl: list  # absolute shell ID list


@dataclass
class Entry:
    name: str
    pidl: list
    is_folder: bool


@dataclass
class MediaFile:
    name: str       # real file name, e.g. IMG_0042.HEIC
    subfolder: str  # e.g. 100APPLE
    pidl: list

    @property
    def is_video(self) -> bool:
        return os.path.splitext(self.name)[1].lower() in VIDEO_EXTS


def _bind(abs_pidl: list):
    desktop = shell.SHGetDesktopFolder()
    return desktop.BindToObject(abs_pidl, None, shell.IID_IShellFolder)


def _list(abs_pidl: list) -> Iterator[Entry]:
    """List the direct children of a shell folder."""
    folder = _bind(abs_pidl)
    enum = folder.EnumObjects(0, ENUM_FLAGS)
    if enum is None:
        return
    for rel in enum:
        name = folder.GetDisplayNameOf(rel, shellcon.SHGDN_INFOLDER)
        attrs = folder.GetAttributesOf([rel], shellcon.SFGAO_FOLDER | shellcon.SFGAO_STREAM)
        is_folder = bool(attrs & shellcon.SFGAO_FOLDER) and not (attrs & shellcon.SFGAO_STREAM)
        yield Entry(name, abs_pidl + rel, is_folder)


def _real_filename(abs_pidl: list, fallback: str) -> str:
    """Get the file name with its extension, even if Explorer hides extensions."""
    try:
        from win32comext.propsys import pscon

        item = shell.SHCreateItemFromIDList(abs_pidl, shell.IID_IShellItem2)
        name = item.GetString(pscon.PKEY_FileName)
        if name:
            return name
    except Exception:
        pass
    return fallback


def find_iphones() -> List[Device]:
    """Return every Apple device that appears under This PC."""
    desktop = shell.SHGetDesktopFolder()
    pc_pidl = shell.SHGetSpecialFolderLocation(0, shellcon.CSIDL_DRIVES)
    pc = desktop.BindToObject(pc_pidl, None, shell.IID_IShellFolder)
    devices: List[Device] = []
    enum = pc.EnumObjects(0, shellcon.SHCONTF_FOLDERS)
    if enum is None:
        return devices
    for rel in enum:
        name = pc.GetDisplayNameOf(rel, shellcon.SHGDN_NORMAL)
        try:
            path = pc.GetDisplayNameOf(rel, shellcon.SHGDN_FORPARSING).lower()
        except pywintypes.com_error:
            path = ""
        if APPLE_USB_VENDOR in path or "iphone" in name.lower():
            devices.append(Device(name, pc_pidl + rel))
    return devices


def find_dcim(device: Device) -> list:
    """Locate the DCIM folder (usually inside 'Internal Storage')."""
    for storage in _list(device.pidl):
        if not storage.is_folder:
            continue
        for entry in _list(storage.pidl):
            if entry.is_folder and entry.name.upper() == "DCIM":
                return entry.pidl
    raise DeviceError(LOCKED_HELP)


def scan_media(device: Device, should_stop=lambda: False) -> Iterator[MediaFile]:
    """Yield every photo and video in the camera roll."""
    dcim = find_dcim(device)
    for sub in _list(dcim):
        if should_stop():
            return
        if not sub.is_folder:
            continue
        for f in _list(sub.pidl):
            if f.is_folder:
                continue
            name = _real_filename(f.pidl, f.name)
            if os.path.splitext(name)[1].lower() in MEDIA_EXTS:
                yield MediaFile(name, sub.name, f.pidl)


def open_stream(media: MediaFile):
    """Open a file on the iPhone for reading (returns a COM IStream)."""
    item = shell.SHCreateItemFromIDList(media.pidl, shell.IID_IShellItem)
    return item.BindToHandler(None, BHID_STREAM, pythoncom.IID_IStream)
