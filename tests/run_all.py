#!/usr/bin/env python3
"""Run every test module in its own process.

Each one drives pygame's display, and the app-loop tests call pygame.quit(),
so keeping them separate avoids cross-test interference.
"""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    failed = []
    for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
        name = os.path.basename(path)
        print(f"\n=== {name} ===")
        r = subprocess.run([sys.executable, path], env=env,
                           capture_output=True, text=True)
        for line in r.stdout.splitlines():
            if line.strip() and "pygame" not in line.lower() and "ALSA" not in line:
                print(line)
        if r.returncode:
            failed.append(name)
            print(r.stderr[-2000:])
    print("\n" + ("FAILED: " + ", ".join(failed) if failed else "All tests passed."))
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
