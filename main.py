"""Entry point: python main.py"""
import sys

if sys.platform != "win32":
    sys.exit("iPhone Photo Transfer runs on Windows only.")

from iphone_transfer.gui import main

if __name__ == "__main__":
    main()
