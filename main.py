"""
Entry point.

Data sources:
  python main.py                     -> mock OSDU data (default)
  python main.py --las <folder>      -> real LAS files from a folder
                                        (e.g. downloaded Volve wells)

When you get real OSDU sandbox access, add a RealOSDUClient
implementing client_interfaces.base.OSDUClient and wire it in here the
same way - nothing in ui/ or models/ changes.
"""

import argparse
import sys
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def build_client(args):
    if args.las:
        from client_interfaces.las_client import LASFileClient
        client = LASFileClient(args.las)
        for fname, err in client.load_errors:
            print(f"warning: could not load {fname}: {err}", file=sys.stderr)
        if not client.search_wells():
            print(f"No usable LAS files found in {args.las}", file=sys.stderr)
            sys.exit(1)
        return client

    from client_interfaces.mock_client import MockOSDUClient
    return MockOSDUClient()


def main():
    parser = argparse.ArgumentParser(description="OSDU Well Log Viewer")
    parser.add_argument("--las", metavar="FOLDER",
                        help="load real well logs from a folder of LAS files")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = MainWindow(build_client(args))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
