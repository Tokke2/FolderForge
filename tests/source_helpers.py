"""View actual extracted definitions for existing display-independent AST tests."""
from pathlib import Path


def app_source():
    return '\n'.join(Path(name).read_text(encoding='utf-8')
                     for name in ('folder.pyw', 'app_core.py', 'instance_lock.py', 'os_startup.py'))
