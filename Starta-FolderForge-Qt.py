"""Explicit optional Qt client. Normal FolderForge launchers remain unchanged."""
import sys


def main():
    try:
        if '--preview' in sys.argv:
            from qt_preview import run
        else:
            from qt_app import run
    except ImportError as exc:
        print('Qt-prototypen kunde inte laddas: ' + str(exc), file=sys.stderr)
        print('Använd den vanliga Tk-startfilen. Inget har installerats eller ändrats.\n'
              'Valfritt, endast enligt IT-policy: installera requirements-qt.txt manuellt\n'
              'i en separat Python-miljö. Se docs/QT_PROTOTYP.md.', file=sys.stderr)
        return 1
    return run()


if __name__ == '__main__':
    raise SystemExit(main())
