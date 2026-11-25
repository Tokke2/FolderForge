"""Explicit Qt entry; ordinary launchers also use Qt now."""
import sys


def main():
    if '--preview' in sys.argv:
        from qt_preview import run
        return run()
    from gui_entry import main as start
    return start()


if __name__ == '__main__':
    raise SystemExit(main())
