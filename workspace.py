"""Shared storage facade for the opt-in Qt client; requires the production lock."""
from pathlib import Path

from app_core import (AppSettings, NameValidator, StructureEngine, TemplateManager,
                      create_project_tree, normalize_plate_name, strip_root_level)
from historik import ProjectHistory, atomic_write_json, read_json_safe
from settings import BASE_DIR


class Workspace:
    def __init__(self, lock, base=BASE_DIR):
        if not lock.is_primary:
            raise RuntimeError('Instanslåset måste vara taget innan data öppnas')
        self.lock = lock
        self.base = Path(base)
        self.settings_file = self.base / 'data/settings.json'
        raw = read_json_safe(self.settings_file, {})
        self.raw = raw if isinstance(raw, dict) else {}
        self.config = AppSettings.from_dict(self.raw)
        self.templates = TemplateManager(self.base / 'data/templates')
        self.history = ProjectHistory(self.base / 'data/history.json')

    def require_lock(self):
        if not self.lock.is_primary:
            raise RuntimeError('Instanslåset är inte längre taget')

    def save_settings(self):
        self.require_lock()
        # Preserve unknown keys for compatibility with Tk and future versions.
        result = dict(self.raw)
        result.update(self.config.to_dict())
        if not atomic_write_json(self.settings_file, result):
            raise OSError('Inställningarna kunde inte sparas')
        self.raw = result

    def prepare_project(self, name, template=None, custom_structure=None):
        self.require_lock()
        if self.config.plate_mode:
            name, _ = normalize_plate_name(name)
        name = NameValidator.sanitize(name).upper()
        structure = custom_structure
        if structure is None:
            templates = self.templates.list_templates()
            selected = template or self.config.default_template
            if selected not in templates:
                raise ValueError('Vald mall saknas. Välj en befintlig mall.')
            structure = templates[selected]
        _, items = StructureEngine.parse_structure_text(structure)
        items, _ = strip_root_level(items, name)
        return name, items

    def create_project(self, name, items):
        self.require_lock()
        path = create_project_tree(self.config.save_root, name, items)
        self.history.add(path)
        return path
