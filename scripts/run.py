"""Run the built Deadzone app with the project Python and LAN-capable server."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None, *, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--check", action="store_true", help="check launch files without starting a server")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Choose a port from 1 to 65535.")
    python = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    required = (python, root / "web/dist/index.html", root / "ml/models/detector.pt")
    if not all(path.is_file() for path in required):
        print("Setup is incomplete. Run python scripts/setup.py first.")
        return 1
    if args.check:
        print("Launch files ready.")
        return 0
    print(f"Open http://localhost:{args.port}. Use Phone in the top bar for the LAN join link. Ctrl+C stops the server.", flush=True)
    try:
        return subprocess.call([str(python), "-m", "deadzone", "--port", str(args.port)], cwd=root / "server")
    except KeyboardInterrupt:
        return 130
    except OSError:
        print("The project Python could not start. Run setup again.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
