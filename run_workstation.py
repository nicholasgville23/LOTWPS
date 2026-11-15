from __future__ import annotations

import argparse
import tkinter as tk

from lotwps.config import env_override, load_config
from lotwps.ui import LOTWPSApp


def main() -> int:
    parser = argparse.ArgumentParser(description="KLOT LOTWPS / LOTIEM text workstation and BMH lab console")
    parser.add_argument("--config", default="config.json", help="Local JSON configuration file")
    args = parser.parse_args()
    config = env_override(load_config(args.config))
    root = tk.Tk()
    LOTWPSApp(root, config)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
