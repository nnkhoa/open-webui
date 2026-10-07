from __future__ import annotations

import re
from pathlib import Path

import yaml

from .. import messages
from ..errors import RegistryError

NAME_KEY_PATTERN = re.compile(r'[\W_]+')


def customer_name_key(name: str) -> str:
    return NAME_KEY_PATTERN.sub(' ', name.upper()).strip()


def load_customer_aliases(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as e:
        raise RegistryError(messages.REGISTRY_INVALID_YAML.format(file=path.name, error=e)) from None
    aliases: dict[str, str] = {}
    for entry in raw.get('customer_aliases') or []:
        if not isinstance(entry, dict) or not entry.get('name') or not entry.get('customer_code'):
            raise RegistryError(messages.REGISTRY_INVALID_CUSTOMER_ALIAS.format(file=path.name))
        aliases[customer_name_key(str(entry['name']))] = str(entry['customer_code']).strip()
    return aliases
