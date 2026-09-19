#!/usr/bin/env python3
"""Run Wisp's face.

    python run_face.py                 # windowed preview (Mac)
    python run_face.py --fullscreen    # how it runs on the Pi
    python run_face.py --size 1200x720 # bigger preview window
"""
import sys

from wisp_face.app import main

if __name__ == "__main__":
    sys.exit(main())
