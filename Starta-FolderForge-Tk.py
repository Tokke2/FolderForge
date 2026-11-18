#!/usr/bin/env python3
"""Explicit legacy Tk reserve. Never mix Qt/Tk event loops in one process."""
import os
from pathlib import Path
from updater import launch_portable

if __name__ == '__main__':
    os.environ['FOLDERFORGE_GUI'] = 'tk'
    launch_portable(Path(__file__).resolve().parent)
