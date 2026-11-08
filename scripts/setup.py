"""Install Deadzone in its own virtual environment and build the web app."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def python_path(root):
    return root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main(argv=None, *, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check an existing installation without installing")
    args = parser.parse_args(argv)
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if sys.version_info < (3, 11) or sys.maxsize <= 2**32 or not npm:
        print("Install 64-bit Python 3.11 or newer and Node.js 20 or newer, then try again.")
        return 1
    python = python_path(root)
    if not (root / "ml/models/detector.pt").is_file():
        print("The trained model is missing. Restore ml/models/detector.pt from the repository.")
        return 1
    try:
        if args.check:
            if not python.is_file() or not (root / "web/dist/index.html").is_file():
                print("Setup is incomplete. Run python scripts/setup.py first.")
                return 1
        else:
            if not python.is_file():
                if (root / ".venv").exists():
                    print("The existing .venv is incomplete. Repair it before running setup again.")
                    return 1
                print("Creating the project virtual environment...", flush=True)
                venv.EnvBuilder(with_pip=True).create(root / ".venv")
            subprocess.run([str(python), "-m", "pip", "install", "-r", str(root / "server/requirements.txt")], check=True)
            subprocess.run([str(python), "-m", "pip", "install", "torch", "torchvision",
                            "--index-url", "https://download.pytorch.org/whl/cpu"], check=True)
            subprocess.run([npm, "ci"], cwd=root / "web", check=True)
            subprocess.run([npm, "run", "build"], cwd=root / "web", check=True)
        # Direct model construction checks CPU inference without loading .env or
        # changing any optional runtime flags the operator may have selected.
        subprocess.run([str(python), "-c", "import torch, torchvision; "
            "from deadzone.robot.perception import Detector, DEFAULT_MODEL; "
            "detector = Detector(DEFAULT_MODEL); assert detector.score('pos_0001.png') is not None; print('CPU detector ready.')"], cwd=root / "server", check=True)
    except (OSError, subprocess.CalledProcessError):
        print("Setup did not finish. Check the failed step above, then run it again.")
        return 1
    print("Ready. Start with: python scripts/run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
