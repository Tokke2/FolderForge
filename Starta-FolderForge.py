#!/usr/bin/env python3
"""Portable entry point. Uses existing Python; never installs or upgrades it."""
from pathlib import Path
from updater import launch_portable

if __name__ == '__main__':
    launch_portable(Path(__file__).resolve().parent)
