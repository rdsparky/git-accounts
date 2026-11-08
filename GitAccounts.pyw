#! python3
# Double-click to open Git Accounts (no console window). Requires Python 3.10+ (standard library only).
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gitaccounts.gui import main  # noqa: E402

main(sys.argv[1] if len(sys.argv) > 1 else None)
