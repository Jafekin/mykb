"""Portable defaults, optional local JSON config, and environment overrides."""
import json
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
local_path = PROJECT / 'config.local.json'
LOCAL = json.loads(local_path.read_text(encoding='utf-8')) if local_path.exists() else {}

def setting(name, default, *legacy):
    for key in ('MYKB_' + name.upper(), *legacy):
        if key in os.environ:
            return os.environ[key]
    return LOCAL.get(name, default)

def project_path(value):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else PROJECT / path).resolve()

CONTENT_ROOT = project_path(setting('content_root', str(PROJECT / 'knowledge-base'), 'LLMFORGE_CONTENT'))
NOTES_ROOT = project_path(setting('notes_root', str(CONTENT_ROOT / 'note'), 'JAFEKIN_NOTES'))
HOST = setting('host', '127.0.0.1')
PORT = int(setting('port', 4173))
SITE_NAME = str(setting('site_name', 'MyKB'))
SITE_LOGO = str(setting('site_logo', '/logo.svg'))
