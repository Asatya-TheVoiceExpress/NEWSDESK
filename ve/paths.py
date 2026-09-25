import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _absolute(path, base):
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(os.path.abspath(base), path))


def _config(app_dir):
    if not app_dir:
        return {}
    try:
        with open(os.path.join(app_dir, 'config.json'), encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _resolve(env_names, cfg_key, default, app_dir):
    for name in env_names:
        value = os.environ.get(name)
        if value:
            return _absolute(value, ROOT)
    value = _config(app_dir).get(cfg_key) if cfg_key else None
    if value:
        return _absolute(value, app_dir)
    return default


def db_path(app_dir=None, env=('DB_PATH',)):
    return _resolve(env, 'db_path', os.path.join(ROOT, 'voice_express.db'), app_dir)


def uploads_path(app_dir=None):
    return _resolve(('UPLOADS_PATH',), 'media_path', os.path.join(ROOT, 'static', 'uploads'), app_dir)


def static_root(app_dir=None):
    return _resolve(('DTP_STATIC_ROOT',), None, os.path.join(ROOT, 'static'), app_dir)


def media_path(app_dir=None):
    return _resolve(('MEDIA_PATH',), None, os.path.join(static_root(app_dir), 'media'), app_dir)


def publications_path(app_dir=None):
    return _resolve(('PUBLICATIONS_PATH',), 'publications_path',
                    os.path.join(static_root(app_dir), 'publications'), app_dir)
