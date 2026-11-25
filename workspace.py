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

    def selected_profile(self):
        profiles = self.templates.list_templates()
        for name in (self.config.last_template, self.config.default_template):
            if name in profiles:
                return name
        return next(iter(profiles))

    def remember_profile(self, name):
        self.require_lock()
        if name not in self.templates.list_templates():
            raise ValueError('Vald profil saknas.')
        if self.config.last_template == name:
            return
        # Persist ONLY the choice; do not save unrelated in-progress settings.
        current = read_json_safe(self.settings_file, self.raw)
        result = dict(current) if isinstance(current, dict) else dict(self.raw)
        result['last_template'] = name
        if not atomic_write_json(self.settings_file, result):
            raise OSError('Senast använda profil kunde inte sparas.')
        self.raw = result
        self.config.last_template = name

    def profile_root(self, template=None):
        """Legacy templates inherit the global path; profiles store their own path."""
        selected = template or self.config.default_template
        if selected not in self.templates.list_templates():
            raise ValueError('Vald profil/mall saknas.')
        root = self.config.save_root
        if selected not in self.templates._builtin:
            path = self.templates.directory / (NameValidator.sanitize(selected) + '.json')
            data = read_json_safe(path, {})
            if isinstance(data, dict) and data.get('name') == selected and 'save_root' in data:
                root = data['save_root']
        if not isinstance(root, str) or not root.strip() or not Path(root).is_absolute():
            raise ValueError('Profilens sparplats är ogiltig. Välj en fullständig sökväg under Mallar.')
        return Path(root)

    def save_profile(self, name, structure, save_root):
        self.require_lock()
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Ange ett profilnamn.')
        self.templates.save_template(name.strip(), structure, save_root=save_root)

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

    def create_project(self, name, items, template=None):
        self.require_lock()
        path = create_project_tree(self.profile_root(template), name, items)
        self.history.add(path)
        return path
