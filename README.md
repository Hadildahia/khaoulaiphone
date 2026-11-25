# iPhone Photo Transfer

Copy photos and videos from an iPhone to a Windows PC over a USB cable.
No iTunes, no Apple Devices app, no iCloud, no drivers to install.

It uses the camera driver that's already built into Windows, so it works on
any Windows 10 or 11 PC.

## How to use

1. Plug the iPhone into the PC with a USB cable.
2. Unlock the iPhone and tap **Trust** when it asks.
3. Open `iPhonePhotoTransfer.exe`.
4. Choose where to save (default: `Pictures\iPhone`) and click **Copy photos and videos**.

Files are saved in the same folders as on the phone (`100APPLE`, `101APPLE`, …)
with their original dates. Running it again only copies new files.

## iPhone settings that make it work better

- **Settings › Photos › Transfer to Mac or PC → Keep Originals.**
  "Automatic" makes the iPhone convert every photo during the copy, which is
  slow and can cause random errors.
- If **Settings › Photos › Optimize iPhone Storage** is on, many full-size
  photos live only in iCloud. The phone can only hand over what it actually
  stores, so turn on **Download and Keep Originals** first if you want everything.

HEIC photos open in Windows once the free "HEIF Image Extensions" is installed
from the Microsoft Store.

## Run from source

```
pip install -r requirements.txt
python main.py
```

## Build the .exe

Every push to `main` builds the app on GitHub Actions. Open the **Actions** tab,
click the latest run, and download **iPhonePhotoTransfer** at the bottom.

To publish a release:

```
git tag v0.1.0
git push origin v0.1.0
```

The .exe then appears under **Releases**.

## Troubleshooting

| What you see | What to do |
|---|---|
| "No iPhone found" | Use a cable that carries data (not charge-only), unlock the phone, press Refresh |
| "Photos aren't visible yet" | Unlock the iPhone and tap Trust, then press Refresh |
| Some files fail | Set Transfer to Mac or PC to Keep Originals, then run again (only failed files get retried) |
| Copy stops when the screen locks | Keep the iPhone unlocked during big transfers |

## Project layout

```
main.py                      entry point
iphone_transfer/device.py    finds the iPhone and reads its camera roll (Windows Shell / WPD)
iphone_transfer/transfer.py  copy logic: skip existing, safe .part files, cancel
iphone_transfer/gui.py       the window
.github/workflows/build.yml  builds the .exe on GitHub
```

## Ideas for later

- Convert HEIC to JPG while copying
- Organize by year and month using the photo's date
- Choose a date range to copy
