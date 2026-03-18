#!/usr/bin/env python3
"""tickle — self-hosted static game portal admin server.

Python stdlib only. No pip, no frameworks.
Serves admin UI, provides JSON API, generates static HTML.
"""

import http.server
import json
import os
import re
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path

PORT = int(os.environ.get('TICKLE_PORT', 8080))
ADMIN_PORT = int(os.environ.get('TICKLE_ADMIN_PORT', 8081))
SINGLE_PORT = os.environ.get('TICKLE_SINGLE_PORT', '') == '1'
BASE = Path(__file__).resolve().parent
OUTPUT = BASE / 'output'
TEMPLATES = BASE / 'templates'
STATIC = BASE / 'static'
ADMIN = BASE / 'admin'

# ═══════════════════════════════════════════════════════
#  THEMES
# ═══════════════════════════════════════════════════════

THEMES = {
    'default': None,  # uses shared.css as-is
    'lighter': {
        '--bg': '#1a1a2e', '--bg-raised': '#222240', '--bg-card': '#2a2a48',
        '--bg-card-hover': '#32325a', '--border': '#3a3a60', '--border-hover': '#505080',
        '--accent': '#fa5c5c', '--accent-secondary': '#ffbd5c', '--accent-cool': '#5cc8ff',
        '--accent-green': '#5cff8a', '--accent-jam': '#c07aff',
        '--text': '#eeeeee', '--text-dim': '#a0a0b8', '--text-muted': '#6a6a88',
        '--tag-bg': '#2e2e50',
    },
    'usnes': {
        '--bg': '#2c2137', '--bg-raised': '#382a45', '--bg-card': '#3e3050',
        '--bg-card-hover': '#4a3a5e', '--border': '#5a4870', '--border-hover': '#7a6890',
        '--accent': '#d4a0ff', '--accent-secondary': '#ffdd57', '--accent-cool': '#7ec8e3',
        '--accent-green': '#7dda58', '--accent-jam': '#e070c0',
        '--text': '#f0e6ff', '--text-dim': '#b8a0d0', '--text-muted': '#7a6890',
        '--tag-bg': '#3a2e4a',
    },
    'modernintendo': {
        '--bg': '#f5f5f5', '--bg-raised': '#ffffff', '--bg-card': '#ffffff',
        '--bg-card-hover': '#f0f0f0', '--border': '#e0e0e0', '--border-hover': '#c8c8c8',
        '--accent': '#e60012', '--accent-secondary': '#c47b00', '--accent-cool': '#0ab5cd',
        '--accent-green': '#00a651', '--accent-jam': '#7b61ff',
        '--text': '#2d2d2d', '--text-dim': '#666666', '--text-muted': '#999999',
        '--tag-bg': '#f0f0f0',
        '--topbar-bg': 'rgba(255,255,255,0.92)',
        '--splash-bg': '#e8e8e8',
        '--overlay-bg': 'rgba(245,245,245,0.95)',
    },
    'megadriveblue': {
        '--bg': '#0a0a1e', '--bg-raised': '#0e1230', '--bg-card': '#121840',
        '--bg-card-hover': '#182050', '--border': '#1e2860', '--border-hover': '#2e3880',
        '--accent': '#00b4ff', '--accent-secondary': '#ffd700', '--accent-cool': '#00e5ff',
        '--accent-green': '#00e676', '--accent-jam': '#8060ff',
        '--text': '#e0e8ff', '--text-dim': '#8090c0', '--text-muted': '#4060a0',
        '--tag-bg': '#141c42',
    },
    'genesisred': {
        '--bg': '#1a0a0a', '--bg-raised': '#2a1010', '--bg-card': '#341818',
        '--bg-card-hover': '#402020', '--border': '#5a2828', '--border-hover': '#7a3838',
        '--accent': '#ff3030', '--accent-secondary': '#ffd700', '--accent-cool': '#ff6060',
        '--accent-green': '#00e676', '--accent-jam': '#ff60a0',
        '--text': '#ffe0e0', '--text-dim': '#c08080', '--text-muted': '#804040',
        '--tag-bg': '#2e1414',
    },
    'playstationish': {
        '--bg': '#0d1117', '--bg-raised': '#161b22', '--bg-card': '#1c2230',
        '--bg-card-hover': '#242c3c', '--border': '#2a3444', '--border-hover': '#3a4a5e',
        '--accent': '#0070d1', '--accent-secondary': '#00bcd4', '--accent-cool': '#4fc3f7',
        '--accent-green': '#66bb6a', '--accent-jam': '#7c4dff',
        '--text': '#e8eaed', '--text-dim': '#8899aa', '--text-muted': '#556677',
        '--tag-bg': '#1a2230',
    },
    'ogxb': {
        '--bg': '#0e0e0e', '--bg-raised': '#1a1a1a', '--bg-card': '#222222',
        '--bg-card-hover': '#2a2a2a', '--border': '#333333', '--border-hover': '#4a4a4a',
        '--accent': '#107c10', '--accent-secondary': '#9bc83a', '--accent-cool': '#2d7d2d',
        '--accent-green': '#107c10', '--accent-jam': '#7c4dff',
        '--text': '#f0f0f0', '--text-dim': '#a0a0a0', '--text-muted': '#666666',
        '--tag-bg': '#1e1e1e',
    },
    'win98': {
        '--bg': '#008080', '--bg-raised': '#c0c0c0', '--bg-card': '#c0c0c0',
        '--bg-card-hover': '#d4d4d4', '--border': '#808080', '--border-hover': '#404040',
        '--accent': '#1a1aaa', '--accent-secondary': '#808000', '--accent-cool': '#008080',
        '--accent-green': '#008000', '--accent-jam': '#800080',
        '--text': '#000000', '--text-dim': '#404040', '--text-muted': '#808080',
        '--tag-bg': '#d4d4d4',
        '--topbar-bg': '#1a1aaa',
        '--splash-bg': '#c0c0c0',
        '--overlay-bg': 'rgba(192,192,192,0.95)',
        '--font-display': "'MS Sans Serif', 'DM Sans', sans-serif",
        '--font-body': "'MS Sans Serif', 'DM Sans', sans-serif",
        '--card-radius': '0px',
    },
}

def get_theme_raw_css(theme_name):
    """Return raw CSS string overriding CSS vars for the given theme."""
    if not theme_name or theme_name == 'default':
        return ''
    theme = THEMES.get(theme_name)
    if not theme:
        return ''
    overrides = '; '.join(f'{k}: {v}' for k, v in theme.items())
    extra = ''
    # Light themes need extra rules that can't be expressed as variable overrides
    if theme_name == 'nintendo':
        extra = (
            '.game-splash::before { display: none; }'
            '.splash-title { -webkit-text-fill-color: var(--accent); background: none; }'
            '.hero h1 .highlight { -webkit-text-fill-color: var(--accent); background: none; }'
        )
    elif theme_name == 'win98':
        extra = (
            '.topbar { backdrop-filter: none; }'
            '.site-logo { color: #ffffff !important; }'
            '.topbar-nav a { color: #ffffff; }'
            '.topbar-nav a:hover { color: #ffff00; background: transparent; }'
            '.game-card { border: 2px outset #dfdfdf; box-shadow: none; }'
            '.game-card:hover { transform: none; box-shadow: 2px 2px 0 #000; }'
            '.hero h1 .highlight { -webkit-text-fill-color: #ffffff; background: none; }'
            '.hero p { color: #e0e0e0; }'
            '.game-splash::before { display: none; }'
            '.splash-title { -webkit-text-fill-color: var(--accent); background: none; }'
            '.sidebar-section, .content-section { border: 2px outset #dfdfdf; border-radius: 0; }'
            '.play-btn { border-radius: 0; border: 2px outset #dfdfdf; box-shadow: none; }'
        )
    return f':root {{ {overrides} }} {extra}'

def get_theme_css(theme_name):
    """Return a <style> block overriding CSS vars for the given theme."""
    css = get_theme_raw_css(theme_name)
    if not css:
        return ''
    return f'<style>{css}</style>'

def get_bg_pattern_html(site, prefix='./'):
    """Return the background pattern div HTML based on site config."""
    pattern = site.get('bg_pattern', 'squares')
    if pattern == 'none':
        return '<div class="bg-pattern" data-pattern="none"></div>'
    if pattern == 'image':
        bg_image = site.get('bg_image', '')
        mode = site.get('bg_image_mode', 'fill')
        if bg_image:
            return f'<div class="bg-pattern" data-pattern="image" data-mode="{mode}" style="background-image:url(\'{prefix}{bg_image}\')"></div>'
        return '<div class="bg-pattern" data-pattern="squares"></div>'
    return f'<div class="bg-pattern" data-pattern="{pattern}"></div>'

# ═══════════════════════════════════════════════════════
#  DATA HELPERS
# ═══════════════════════════════════════════════════════

def read_json(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def get_site_config():
    config = read_json(OUTPUT / 'site.json')
    if config is None:
        return None
    return config

def save_site_config(config):
    write_json(OUTPUT / 'site.json', config)

def default_site_config(name='My Games', title='My Game Portal', tagline='', author=''):
    return {
        'site_name': name,
        'site_title': title,
        'site_tagline': tagline or 'A personal collection of games and experiments.',
        'site_url': '',
        'site_author': author or name,
        'site_badge': '\U0001f579\ufe0f Self-hosted indie corner',
        'site_badge_emoji': '',
        'nav_links': [
            {'label': 'Games', 'url': '/', 'active': True},
        ],
        'footer_links': [],
        'footer_text': f'\u00a9 {name}',
    }

def get_games():
    data = read_json(OUTPUT / 'games.json')
    return data if isinstance(data, list) else []

def save_games(games):
    write_json(OUTPUT / 'games.json', games)

def find_game(slug):
    for g in get_games():
        if g.get('slug') == slug:
            return g
    return None

def slugify(text):
    s = text.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s

# ═══════════════════════════════════════════════════════
#  TEMPLATE ENGINE
# ═══════════════════════════════════════════════════════

def render_template(template_str, context):
    """Simple template engine:
    - {{field}} → value from context
    - {{site.field}} → value from context['site']
    - <!--IF:field-->...<!--ENDIF:field--> → conditional block
    - <!--LOOP:array-->...<!--ENDLOOP:array--> → repeat for each item
    - <!--LOOP_ITEM:prop--> → property of current loop item
    """
    result = template_str

    # Process loops first (they contain other markers)
    result = _process_loops(result, context)

    # Process conditionals
    result = _process_conditionals(result, context)

    # Process simple replacements
    result = _process_replacements(result, context)

    return result

def _resolve_value(key, context):
    """Resolve a dotted key like 'site.site_name' from context."""
    parts = key.split('.')
    val = context
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p, '')
        else:
            return ''
    return val

def _is_truthy(key, context):
    val = _resolve_value(key, context)
    if val is None or val == '' or val == [] or val is False:
        return False
    return True

def _process_loops(text, context):
    pattern = r'<!--LOOP:([\w.]+)-->(.*?)<!--ENDLOOP:\1-->'
    def replacer(m):
        key = m.group(1)
        body = m.group(2)
        items = _resolve_value(key, context)
        if not isinstance(items, list):
            return ''
        parts = []
        for item in items:
            rendered = body
            # Replace LOOP_ITEM:prop
            def item_replacer(im):
                prop = im.group(1)
                if isinstance(item, dict):
                    return str(item.get(prop, ''))
                return str(item)
            rendered = re.sub(r'<!--LOOP_ITEM:([\w]+)-->', item_replacer, rendered)
            parts.append(rendered)
        return ''.join(parts)
    return re.sub(pattern, replacer, text, flags=re.DOTALL)

def _process_conditionals(text, context):
    pattern = r'<!--IF:([\w.]+)-->(.*?)<!--ENDIF:\1-->'
    def replacer(m):
        key = m.group(1)
        body = m.group(2)
        if _is_truthy(key, context):
            return body
        return ''
    # Process from inside out (nested conditionals)
    prev = None
    while prev != text:
        prev = text
        text = re.sub(pattern, replacer, text, flags=re.DOTALL)
    return text

def _process_replacements(text, context):
    def replacer(m):
        key = m.group(1)
        val = _resolve_value(key, context)
        if isinstance(val, (list, dict)):
            return ''
        return str(val) if val is not None else ''
    return re.sub(r'\{\{([\w.]+)\}\}', replacer, text)

# ═══════════════════════════════════════════════════════
#  STATIC SITE GENERATOR
# ═══════════════════════════════════════════════════════

STATUS_LABELS = {
    'released': 'Released',
    'in-dev': 'In Dev',
    'prototype': 'Prototype',
    'jam': 'Game Jam',
}

TYPE_LABELS = {
    'game': 'Games',
    'game-asset': 'Game Assets',
    'tool': 'Tools',
    'album': 'Albums & Soundtracks',
    'physical-game': 'Physical Games',
    'comic': 'Comics',
    'book': 'Books',
    '3d-print': "3D Print"
}

EMULATOR_CORES = {
    'nes':           {'core': 'fceumm',           'label': 'NES'},
    'snes':          {'core': 'snes9x',           'label': 'SNES'},
    'genesis':       {'core': 'genesis_plus_gx',  'label': 'Sega Genesis'},
    'gb':            {'core': 'gambatte',          'label': 'Game Boy'},
    'gbc':           {'core': 'gambatte',          'label': 'Game Boy Color'},
    'gba':           {'core': 'mgba',             'label': 'Game Boy Advance'},
    'n64':           {'core': 'mupen64plus_next', 'label': 'Nintendo 64'},
    'ps1':           {'core': 'pcsx_rearmed',     'label': 'PlayStation'},
    'arcade':        {'core': 'fbneo',            'label': 'Arcade (FBNeo)'},
    'mastersystem':  {'core': 'genesis_plus_gx',  'label': 'Master System'},
    'gamegear':      {'core': 'genesis_plus_gx',  'label': 'Game Gear'},
    'segacd':        {'core': 'genesis_plus_gx',  'label': 'Sega CD'},
}

SOCIAL_ICONS = {
    'twitter': '<path d="M22 4s-.7 2.1-2 3.4c1.6 10-9.4 17.3-18 11.6 2.2.1 4.4-.6 6-2C3 15.5.5 9.6 3 5c2.2 2.6 5.6 4.1 9 4-.9-4.2 4-6.6 7-3.8 1.1 0 3-1.2 3-1.2z"/>',
    'bluesky': '<path d="M12 2C7 5.5 4 9.5 4 12.5c0 4 2.5 5 4.5 4.5-1 2.5-4 3-4 3s6 1 8-3c2 4 8 3 8 3s-3-.5-4-3c2 .5 4.5-.5 4.5-4.5C21 9.5 17 5.5 12 2z"/>',
    'mastodon': '<path d="M21.3 14.5c-.3 1.5-2.7 3.2-5.4 3.5-1.4.2-2.8.3-4.3.2-2.4-.1-4.3-.7-4.3-.7v.8c.3 2.3 2.4 2.5 4.4 2.5 2 0 3.6-.5 3.6-.5l.1 1.7s-1.3.7-3.7.8c-1.3.1-2.9-.1-4.8-.6C3.3 21 2.7 17 2.6 13v-3c0-4 2.6-5.2 2.6-5.2C6.5 4.2 9.6 4 12.8 4h.1c3.2 0 6.3.2 7.6.8 0 0 2.6 1.2 2.6 5.2 0 0 0 2.9-.3 4.5zM18 8.5c0-1-.3-1.8-.8-2.4-.6-.6-1.3-.9-2.2-.9-1 0-1.8.4-2.3 1.2l-.5.8-.5-.8C11.2 5.6 10.4 5.2 9.4 5.2c-.9 0-1.6.3-2.2.9-.5.6-.8 1.4-.8 2.4v5h2V8.7c0-1 .4-1.5 1.3-1.5 1 0 1.4.6 1.4 1.8V12h2V9c0-1.2.5-1.8 1.4-1.8.9 0 1.3.5 1.3 1.5v4.8h2z"/>',
    'youtube': '<path d="M22.5 6.4a2.8 2.8 0 00-2-2C18.9 4 12 4 12 4s-6.9 0-8.5.4a2.8 2.8 0 00-2 2A29.3 29.3 0 001 12a29.3 29.3 0 00.5 5.6 2.8 2.8 0 002 2c1.6.4 8.5.4 8.5.4s6.9 0 8.5-.4a2.8 2.8 0 002-2A29.3 29.3 0 0023 12a29.3 29.3 0 00-.5-5.6zM9.8 15.5V8.5l5.6 3.5z"/>',
    'twitch': '<path d="M3.5 2L2 5.5V20h5v3h3l3-3h4l5-5V2zM18 12l-3 3h-4l-3 3v-3H5V4h13z"/><path d="M14 7v5M18 7v5"/>',
    'discord': '<path d="M20.3 4.7a19.5 19.5 0 00-4.8-1.5 14.2 14.2 0 00-.6 1.3 18 18 0 00-5.4 0 14.2 14.2 0 00-.6-1.3A19.5 19.5 0 004 4.7 20 20 0 00.5 17.2a19.7 19.7 0 006 3 14.8 14.8 0 001.3-2.1 12.7 12.7 0 01-2-.9l.5-.4a14 14 0 0011.9 0l.5.4a12.8 12.8 0 01-2 .9 14.8 14.8 0 001.3 2.1 19.6 19.6 0 006-3A20 20 0 0020.3 4.7zM8.3 14.7c-1.1 0-2-.5-2-2s.9-2 2-2 2 .5 2 2-.8 2-2 2zm7.4 0c-1.1 0-2-.5-2-2s.9-2 2-2 2 .5 2 2-.9 2-2 2z"/>',
    'github': '<path d="M12 2C6.5 2 2 6.5 2 12c0 4.4 2.9 8.2 6.8 9.5.5.1.7-.2.7-.5v-1.7c-2.8.6-3.4-1.3-3.4-1.3-.4-1.1-1.1-1.4-1.1-1.4-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.5 2.3 1.1 2.8.8.1-.6.3-1.1.6-1.3-2.2-.3-4.5-1.1-4.5-5 0-1.1.4-2 1-2.7-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.7 1a9.4 9.4 0 015 0c1.9-1.3 2.7-1 2.7-1 .5 1.4.2 2.4.1 2.7.6.7 1 1.6 1 2.7 0 3.9-2.3 4.7-4.5 5 .4.3.7.9.7 1.9v2.8c0 .3.2.6.7.5A10 10 0 0022 12c0-5.5-4.5-10-10-10z"/>',
    'gitlab': '<path d="M22.7 12.4L12 22.2 1.3 12.4a.8.8 0 01-.1-.8l1.5-4.6 2.9-9a.4.4 0 01.8 0l2.9 9h5.4l2.9-9a.4.4 0 01.8 0l2.9 9 1.5 4.6a.8.8 0 01-.1.8z"/>',
    'reddit': '<circle cx="12" cy="12" r="10"/><path d="M16.5 13.5c0 .8-.4 1.5-1 2-.6.5-1.5.8-2.5.8s-1.9-.3-2.5-.8c-.6-.5-1-1.2-1-2" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="8.5" cy="11" r="1.5"/><circle cx="15.5" cy="11" r="1.5"/><path d="M18.5 8.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3zM15.5 4l3 1.5"/>',
    'instagram': '<rect x="2" y="2" width="20" height="20" rx="5" ry="5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="17.5" cy="6.5" r="1.5"/>',
    'tiktok': '<path d="M16.6 5.8A4.3 4.3 0 0115 2h-3.5v13.5a2.8 2.8 0 01-2.8 2.8 2.8 2.8 0 01-2.8-2.8A2.8 2.8 0 018.7 12.7V9.1a6.3 6.3 0 00-1 0A6.3 6.3 0 001.5 15.5a6.3 6.3 0 006.3 6.3 6.3 6.3 0 006.3-6.3V9.3a7.8 7.8 0 004.5 1.4V7.2a4.3 4.3 0 01-2-1.4z"/>',
    'facebook': '<path d="M18 2h-3a5 5 0 00-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 011-1h3z"/>',
    'linkedin': '<path d="M16 8a6 6 0 016 6v7h-4v-7a2 2 0 00-4 0v7h-4v-7a6 6 0 016-6zM2 9h4v12H2z"/><circle cx="4" cy="4" r="2"/>',
    'threads': '<path d="M16.7 10.2c-.1 0-.2-.1-.3-.1-.5-2.2-2-3.4-4.3-3.4-1.6 0-2.9.7-3.6 2l1.5.9c.5-.9 1.3-1.3 2.2-1.3 1.1 0 1.8.4 2.1 1.3-1-.2-2-.2-2.9 0-2 .4-3.3 1.6-3.2 3.2.1 1.7 1.6 2.8 3.4 2.7 1.4 0 2.5-.6 3.1-1.6.4-.7.6-1.5.6-2.6.9.5 1.5 1.3 1.6 2.4.1 1.8-.9 3.5-3.8 3.5-3.2 0-5.1-1.6-5.1-5.2 0-3.6 1.9-5.2 5.1-5.2 3.3 0 5.2 1.7 5.2 5.2v.2c0 .1 0 .1-1.6 0zm-3.4 2.5c-.1.9-.9 1.6-2 1.6-.8 0-1.5-.4-1.5-1.1 0-.8.6-1.3 1.7-1.5.5-.1 1.1-.1 1.8 0v1z"/>',
    'lemmy': '<circle cx="12" cy="8" r="4" fill="none" stroke="currentColor" stroke-width="2"/><path d="M6 20v-2a6 6 0 0112 0v2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="7" cy="6" r="2"/><circle cx="17" cy="6" r="2"/>',
    'pixelfed': '<circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="18" cy="6" r="1.5"/>',
    'peertube': '<polygon points="5,3 19,12 5,21"/><line x1="12" y1="3" x2="12" y2="21" stroke="currentColor" stroke-width="2"/>',
    'matrix': '<rect x="3" y="3" width="18" height="18" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="8.5" cy="9.5" r="1.5"/><circle cx="15.5" cy="9.5" r="1.5"/><circle cx="8.5" cy="14.5" r="1.5"/><circle cx="15.5" cy="14.5" r="1.5"/>',
    'steam': '<path d="M12 2a10 10 0 00-9.8 8.1l5.2 2.2a2.8 2.8 0 011.6-.5h.1l2.4-3.5v-.1a3.8 3.8 0 113.8 3.8h-.1l-3.4 2.5v.1a2.9 2.9 0 01-5.7.6L2.2 13.5A10 10 0 1012 2z"/>',
    'itchio': '<path d="M3.1 2.5C2.3 3 1 4.6 1 5.5v1.1c0 1.3 1.2 2.4 2.4 2.4 1.3 0 2.4-1.1 2.4-2.4 0 1.3 1 2.4 2.3 2.4s2.4-1.1 2.4-2.4c0 1.3 1 2.4 2.4 2.4 1.3 0 2.3-1.1 2.3-2.4 0 1.3 1.1 2.4 2.4 2.4 1.3 0 2.4-1.1 2.4-2.4V5.5c0-.9-1.3-2.5-2.1-3H3.1zm.5 8.5v8c0 1.5.4 2.5 2.3 2.5h12.2c1.9 0 2.3-1 2.3-2.5V11c-.7.3-1.4.5-2.1.5-.8 0-1.5-.3-2.1-.7-.5.4-1.3.7-2.2.7-.9 0-1.6-.3-2.1-.7-.5.4-1.3.7-2.2.7-.9 0-1.6-.3-2.1-.7-.6.4-1.3.7-2.1.7-.7 0-1.5-.2-2.1-.5zm5 2.5h6.8v3.3H8.6z"/>',
    'website': '<circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10A15.3 15.3 0 0112 2z" fill="none" stroke="currentColor" stroke-width="2"/>',
    'email': '<rect x="2" y="4" width="20" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M22 4L12 13 2 4" fill="none" stroke="currentColor" stroke-width="2"/>',
    'rss': '<circle cx="6" cy="18" r="2"/><path d="M4 4a16 16 0 0116 16" fill="none" stroke="currentColor" stroke-width="2"/><path d="M4 11a9 9 0 019 9" fill="none" stroke="currentColor" stroke-width="2"/>',
}

SOCIAL_LABELS = {
    'bluesky': 'Bluesky', 'mastodon': 'Mastodon',
    'youtube': 'YouTube', 'twitch': 'Twitch', 'discord': 'Discord',
    'github': 'GitHub', 'gitlab': 'GitLab', 'reddit': 'Reddit',
    'instagram': 'Instagram', 'tiktok': 'TikTok', 'facebook': 'Facebook',
    'linkedin': 'LinkedIn', 'threads': 'Threads', 'lemmy': 'Lemmy',
    'pixelfed': 'Pixelfed', 'peertube': 'PeerTube', 'matrix': 'Matrix',
    'steam': 'Steam', 'itchio': 'itch.io', 'website': 'Website',
    'email': 'Email', 'rss': 'RSS','twitter': 'Twitter',
}

def build_social_icons_html(social_links, max_icons=15):
    """Build social icon link HTML. Max 15 (5 per row, 3 rows)."""
    if not social_links:
        return ''
    html = ''
    count = 0
    for link in social_links:
        if count >= max_icons:
            break
        platform = link.get('platform', '')
        url = link.get('url', '')
        if not platform or not url:
            continue
        svg_inner = SOCIAL_ICONS.get(platform, SOCIAL_ICONS.get('website', ''))
        label = SOCIAL_LABELS.get(platform, platform)
        html += (f'<a href="{url}" class="social-icon" target="_blank" rel="noopener" title="{label}">'
                 f'<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20">{svg_inner}</svg>'
                 f'</a>')
        count += 1
    return html

def build_card_html(game):
    """Build a single game card HTML for the portal grid."""
    slug = game.get('slug', '')
    title = game.get('title', slug)
    status = game.get('status', 'in-dev')
    status_label = STATUS_LABELS.get(status, status)
    tags = game.get('tags', [])
    game_dir = OUTPUT / 'games' / slug
    cover = game.get('cover', '')
    if cover and not (game_dir / cover).is_file():
        cover = ''
    icon = game.get('icon', '')
    if icon and not (game_dir / icon).is_file():
        icon = ''
    img = cover or icon

    # Build image
    if img:
        img_html = f'<img src="games/{slug}/{img}" alt="{title}" loading="lazy">'
    else:
        letter = title[0] if title else '?'
        img_html = (f'<div style="width:100%;height:100%;display:flex;align-items:center;'
                    f'justify-content:center;background:var(--bg-raised);">'
                    f'<span style="font-family:\'Silkscreen\',cursive;font-size:2rem;'
                    f'color:var(--text-muted);">{letter}</span></div>')

    tags_html = ''.join(f'<span class="card-tag">{t}</span>' for t in tags[:4])
    platform = game.get('platform', '')
    author = game.get('author', '')
    desc = game.get('description', '')
    engine = game.get('engine', '')

    genre = game.get('genre', '').lower()
    return f'''<a href="games/{slug}/index.html" class="game-card" data-type="{game.get('type', 'game')}" data-title="{title.lower()}" data-tags="{','.join(t.lower() for t in tags)}" data-genre="{genre}">
    <div class="card-image">
      {img_html}
      <span class="status-badge {status}">{status_label}</span>
      {f'<span class="platform-badge">{platform}</span>' if platform else ''}
    </div>
    <div class="card-body">
      <div class="card-title">{title}</div>
      {f'<div class="card-author">by {author}</div>' if author else ''}
      {f'<div class="card-desc">{desc}</div>' if desc else ''}
      {f'<div class="card-tags">{tags_html}</div>' if tags_html else ''}
    </div>
    <div class="card-footer">
      <span class="engine">{f'<span class="engine-dot"></span> {engine}' if engine else ''}</span>
      <span class="play-indicator">{'View' if game.get('type', 'game') in ('3d-print', 'book', 'comic', 'album', 'physical-game', 'game-asset') else 'Play'} &rarr;</span>
    </div>
  </a>'''

def generate_portal(site, games):
    """Generate the portal index.html."""
    template = (TEMPLATES / 'portal.html').read_text()

    # Build cards HTML server-side
    visible_games = [g for g in games if g.get('visible', True)]
    # Sort by date descending
    visible_games.sort(key=lambda g: g.get('date_updated', g.get('date_created', '')), reverse=True)
    if visible_games:
        cards_html = '\n'.join(build_card_html(g) for g in visible_games)
    else:
        cards_html = (
            '<a href="admin" class="game-card" style="text-align:center;justify-content:center;min-height:200px;">'
            '<div class="card-body">'
            '<h3 class="card-title" style="font-size:1rem;">No games yet</h3>'
            '<p class="card-desc">Head to the admin panel to add your first game.</p>'
            '</div></a>'
        )

    # Build site_title_html — apply highlight to site_name within site_title
    site_title = site.get('site_title', site.get('site_name', ''))
    site_name = site.get('site_name', '')
    if site_name and site_name.lower() in site_title.lower():
        idx = site_title.lower().index(site_name.lower())
        before = site_title[:idx]
        word = site_title[idx:idx+len(site_name)]
        after = site_title[idx+len(site_name):]
        site_title_html = f'{before}<span class="highlight">{word}</span>{after}'
    else:
        site_title_html = f'<span class="highlight">{site_title}</span>'

    # Prepare nav_links with active_class and fix URLs for static site
    # Convert absolute paths to relative so pages work on file:/// too
    nav_links = []
    for link in site.get('nav_links', []):
        link_copy = dict(link)
        link_copy['active_class'] = 'active' if link.get('active') else ''
        url = link_copy.get('url', '')
        if url == '/':
            link_copy['url'] = './index.html'
        elif url.startswith('/') and not url.startswith('//'):
            link_copy['url'] = '.' + url
        nav_links.append(link_copy)

    # OG image for portal: use cover of first visible game with a cover
    site_url = site.get('site_url', '')
    og_portal_image = ''
    for g in visible_games:
        if g.get('cover'):
            og_portal_image = f"{site_url}/games/{g['slug']}/{g['cover']}"
            break

    rss_url = f"{site_url}/rss.xml" if site_url else ''

    # Only show filter tabs if there are multiple game types
    types = set(g.get('type', 'game') for g in visible_games)
    show_filters = '1' if len(types) > 1 else ''
    # Build filter tabs HTML from actual types present
    filter_tabs_html = '<button class="filter-tab active" data-filter="all" onclick="setFilter(\'all\', this)">All</button>'
    for t in TYPE_LABELS:
        if t in types:
            label = TYPE_LABELS[t]
            filter_tabs_html += f'<button class="filter-tab" data-filter="{t}" onclick="setFilter(\'{t}\', this)">{label}</button>'

    # Logo: image or text
    logo_img = site.get('site_logo_image', '')
    if logo_img:
        site_logo_html = f'<img src="./{logo_img}" alt="{site_name}">'
    else:
        site_logo_html = site_name or site_title

    # Build browse panel HTML (tags + genres with counts)
    show_browse_panel = '1' if site.get('show_browse_panel') else ''
    tags_browse_html = ''
    genres_browse_html = ''
    if show_browse_panel:
        tag_counts = {}
        genre_counts = {}
        for g in visible_games:
            for t in g.get('tags', []):
                t_lower = t.lower().strip()
                if t_lower:
                    tag_counts[t_lower] = tag_counts.get(t_lower, 0) + 1
            for genre_str in (g.get('genre', '') or '').split(','):
                genre_str = genre_str.strip()
                if genre_str:
                    g_lower = genre_str.lower()
                    genre_counts[g_lower] = genre_counts.get(g_lower, 0) + 1

        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)

        def build_browse_items(items, cls, param):
            if not items:
                return ''
            visible_items = items[:8]
            overflow_items = items[8:]
            html = ''
            for name, count in visible_items:
                html += f'<a href="?{param}={name}" class="{cls}" data-{param}="{name}">{name} <span class="browse-count">{count}</span></a>'
            if overflow_items:
                html += '<div class="browse-overflow hidden">'
                for name, count in overflow_items:
                    html += f'<a href="?{param}={name}" class="{cls}" data-{param}="{name}">{name} <span class="browse-count">{count}</span></a>'
                html += '</div>'
                html += '<button class="browse-toggle" onclick="this.previousElementSibling.classList.toggle(\'hidden\');this.textContent=this.previousElementSibling.classList.contains(\'hidden\')?\'Browse all\':\'Show less\'">Browse all</button>'
            return html

        tags_browse_html = build_browse_items(sorted_tags, 'browse-tag', 'tag')
        genres_browse_html = build_browse_items(sorted_genres, 'browse-genre', 'genre')

    context = {
        'site': {**site, 'nav_links': nav_links, 'site_title_html': site_title_html},
        'site_logo_html': site_logo_html,
        'bg_pattern_html': get_bg_pattern_html(site, './'),
        'game_cards': cards_html,
        'og_portal_image': og_portal_image,
        'rss_url': rss_url,
        'show_filters': show_filters,
        'filter_tabs_html': filter_tabs_html,
        'support_links': site.get('support_links', []),
        'theme_css': get_theme_css(site.get('theme', '')),
        'show_browse_panel': show_browse_panel,
        'tags_browse_html': tags_browse_html,
        'genres_browse_html': genres_browse_html,
        'social_heading': site.get('social_heading', 'Socials'),
        'social_icons_html': build_social_icons_html(site.get('social_links', [])),
        'social_icons_inline': '1' if (not show_browse_panel and site.get('social_links') and site.get('support_links')) else '',
        'social_icons_standalone': '1' if (not show_browse_panel and site.get('social_links') and not site.get('support_links')) else '',
    }

    return render_template(template, context)

TEMPLATE_MAP = {
    '3d-print': '3d-print.html',
    # Future: 'book': 'book.html', 'audio': 'audio.html'
}

def generate_game_page(site, game):
    """Generate a single game page."""
    game_type = game.get('type', 'game')
    template_file = TEMPLATE_MAP.get(game_type, 'game.html')
    template = (TEMPLATES / template_file).read_text()

    slug = game.get('slug', '')
    game_dir = OUTPUT / 'games' / slug

    status = game.get('status', 'in-dev')
    author = game.get('author', site.get('site_author', ''))
    tags = game.get('tags', [])

    # Validate file references exist on disk — skip missing ones
    icon = game.get('icon', '')
    if icon and not (game_dir / icon).is_file():
        icon = ''
    cover = game.get('cover', '')
    if cover and not (game_dir / cover).is_file():
        cover = ''
    game_file = game.get('game_file', '')
    if game_file and not (game_dir / game_file).is_file():
        game_file = ''

    # Auto-patch Unity HTML for fullscreen iframe if not already patched
    engine_lower = game.get('engine', '').lower()
    if game_file and 'unity' in engine_lower:
        gf_path = game_dir / game_file
        if gf_path.is_file():
            html_content = gf_path.read_text()
            is_unity_html = ('UnityLoader' in html_content or 'unityContainer' in html_content
                             or 'emscripten' in html_content or 'unity-canvas' in html_content)
            if is_unity_html and 'tickle-patched' not in html_content:
                inject = (
                    '<!-- tickle-patched -->\n'
                    '<style>\n'
                    '  html, body { margin: 0; padding: 0; overflow: hidden; width: 100%; height: 100%; }\n'
                    '  .webgl-content, #unityContainer, .template-wrap { width: 100% !important; height: 100% !important; }\n'
                    '  #unityContainer canvas, canvas.emscripten, #unity-canvas { width: 100% !important; height: 100% !important; }\n'
                    '  .footer, .header, .title, .logo, .fullscreen { display: none !important; }\n'
                    '</style>\n'
                )
                # Strip hardcoded canvas dimensions (e.g. width="640px" height="480px")
                html_content = re.sub(
                    r'(<canvas[^>]*?)(\s+width="[^"]*")([^>]*?>)',
                    r'\1\3', html_content)
                html_content = re.sub(
                    r'(<canvas[^>]*?)(\s+height="[^"]*")([^>]*?>)',
                    r'\1\3', html_content)
                html_content = html_content.replace('</head>', inject + '</head>')
                gf_path.write_text(html_content)
                # Also patch TemplateData/style.css if present alongside
                style_path = gf_path.parent / 'TemplateData' / 'style.css'
                if style_path.is_file():
                    css = style_path.read_text()
                    if 'translate(-50%, -50%)' in css:
                        css = css.replace(
                            'position: absolute; top: 50%; left: 50%; -webkit-transform: translate(-50%, -50%); transform: translate(-50%, -50%);',
                            'position: absolute; inset: 0; width: 100%; height: 100%;'
                        )
                        style_path.write_text(css)

    # Build tags HTML
    tags_html = ''.join(f'<a href="../../index.html?tag={t}" class="tag">{t}</a>' for t in tags)

    # Build screenshots HTML — only include files that exist
    screenshots = [s for s in game.get('screenshots', []) if (game_dir / 'screenshots' / s).is_file()]
    screenshots_html = ''.join(
        f'<img src="screenshots/{s}" alt="Screenshot" class="screenshot-thumb" onclick="openLightbox({i})" data-ss-index="{i}">'
        for i, s in enumerate(screenshots)
    )

    # Build screenshots JS array for lightbox
    screenshots_js = ', '.join(f"'screenshots/{s}'" for s in screenshots)

    # Fix nav_links URLs for static site (game pages are 2 levels deep)
    # Convert absolute paths to relative so pages work on file:/// too
    nav_links = []
    for link in site.get('nav_links', []):
        link_copy = dict(link)
        url = link_copy.get('url', '')
        if url == '/':
            link_copy['url'] = '../../index.html'
        elif url.startswith('/') and not url.startswith('//'):
            link_copy['url'] = '../..' + url
        nav_links.append(link_copy)

    # Format dates for display (e.g. "2026-03-11" → "Mar 11, 2026")
    date_created_display = ''
    date_updated_display = ''
    try:
        dc = game.get('date_created', '')
        if dc:
            d = date.fromisoformat(dc)
            date_created_display = d.strftime('%b %d, %Y')
        du = game.get('date_updated', '')
        if du and du != dc:
            d = date.fromisoformat(du)
            date_updated_display = d.strftime('%b %d, %Y')
    except (ValueError, TypeError):
        pass

    # OG image fallback: if no cover, use icon as OG image
    site_url = site.get('site_url', '')
    og_image_fallback = ''
    if not cover and icon:
        og_image_fallback = f"{site_url}/games/{slug}/{icon}"

    # Logo: image or text
    logo_img = site.get('site_logo_image', '')
    site_name = site.get('site_name', '')
    if logo_img:
        site_logo_html = f'<img src="../../{logo_img}" alt="{site_name}">'
    else:
        site_logo_html = site_name or site.get('site_title', '')

    # Build credits HTML: name becomes a link if url is provided
    credits = game.get('credits', [])
    credits_html_parts = []
    for c in credits:
        role = c.get('role', '').strip()
        name = c.get('name', '').strip()
        url = c.get('url', '').strip()
        if not role:
            role = name
            name = ''
        name_html = ''
        if name:
            if url:
                name_html = f'<a href="{url}" target="_blank" rel="noopener">{name}</a>'
            else:
                name_html = name
        credits_html_parts.append(
            f'<tr><td>{role}</td><td>{name_html}</td></tr>'
        )
    credits_html = ''.join(credits_html_parts)

    # Pre-process downloads: compute href and attrs for template
    downloads = []
    for d in game.get('downloads', []):
        dl = dict(d)
        if d.get('url'):
            dl['href'] = d['url']
            dl['attrs'] = 'target="_blank" rel="noopener"'
        else:
            dl['href'] = d.get('file', '')
            dl['attrs'] = 'download'
        downloads.append(dl)

    context = {
        'site': {**site, 'nav_links': nav_links},
        'site_logo_html': site_logo_html,
        'bg_pattern_html': get_bg_pattern_html(site, '../../'),
        **game,
        'credits': credits,
        'credits_html': credits_html,
        'downloads': downloads,
        'icon': icon,
        'cover': cover,
        'game_file': game_file,
        'author': author,
        'status_label': STATUS_LABELS.get(status, status),
        'tags_html': tags_html,
        'screenshots_html': screenshots_html,
        'screenshots_js': screenshots_js,
        'og_image_fallback': og_image_fallback,
        'date_created_display': date_created_display,
        'date_updated_display': date_updated_display,
        'youtube_hero': normalize_youtube_url(game.get('youtube_url', '')) if (not game_file and game.get('youtube_url')) else '',
        'youtube_trailer': normalize_youtube_url(game.get('youtube_url', '')) if (game_file and game.get('youtube_url')) else '',
        'cover_hero': cover if (not game_file and not game.get('youtube_url') and cover) else '',
        'placeholder_hero': '1' if (not game_file and not game.get('youtube_url') and not cover) else '',
        'support_links': site.get('support_links', []),
        'theme_css': get_theme_css(site.get('theme', '')),
    }

    # EmulatorJS support — emulator_core stores a system key (e.g. 'genesis'),
    # resolved here to the actual EmulatorJS core name (e.g. 'genesis_plus_gx')
    emulator_key = game.get('emulator_core', '')
    emulator_info = EMULATOR_CORES.get(emulator_key, {})
    emulator_core = emulator_info.get('core', emulator_key)
    emulator_system = emulator_info.get('label', emulator_key)
    is_emulator = bool(emulator_key and game_file)
    context['is_emulator'] = '1' if is_emulator else ''
    context['is_iframe_game'] = '1' if (game_file and not is_emulator) else ''
    context['emulator_core'] = emulator_core
    context['emulator_system'] = emulator_system

    # Type-specific context
    if game_type == '3d-print':
        model_files = game.get('model_files', [])
        # Collect all viewable STL files that exist on disk
        viewable_models = []
        for mf in model_files:
            f = mf.get('file', '')
            if f.lower().endswith('.stl') and (game_dir / f).is_file():
                viewable_models.append(f)
        viewer_file = viewable_models[0] if viewable_models else ''
        context['viewer_file'] = viewer_file
        # Build JS array of all viewable model paths for carousel
        context['viewer_models_js'] = ', '.join(f"'{f}'" for f in viewable_models)
        # Build JS array of model filenames for labels
        context['viewer_labels_js'] = ', '.join(
            f"'{f.split('/')[-1]}'" for f in viewable_models
        )
        context['viewer_model_count'] = len(viewable_models)
        # Model downloads (only if models_downloadable)
        if game.get('models_downloadable', True) and model_files:
            model_downloads = []
            for mf in model_files:
                f = mf.get('file', '')
                if (game_dir / f).is_file():
                    ext = f.rsplit('.', 1)[-1].upper() if '.' in f else 'FILE'
                    model_downloads.append({
                        'href': f,
                        'label': mf.get('filename', f.split('/')[-1]),
                        'size': mf.get('size', ''),
                    })
            context['model_downloads'] = model_downloads
        else:
            context['model_downloads'] = []
        # Relabel fields
        context['category'] = game.get('genre', '')
        context['license'] = game.get('input_methods', '')
        # Hero fallbacks for 3d-print (no game_file, no youtube)
        context['cover_hero'] = cover if (not viewer_file and cover) else ''
        context['placeholder_hero'] = '1' if (not viewer_file and not cover) else ''
        # Clear game-specific fields that don't apply
        context['game_file'] = ''
        context['youtube_hero'] = ''
        context['youtube_trailer'] = ''
        # YouTube video for 3d-print (shows below the viewer)
        yt = game.get('youtube_url', '')
        context['youtube_video'] = normalize_youtube_url(yt) if yt else ''

    return render_template(template, context)

def generate_all():
    """Generate the entire static site."""
    site = get_site_config()
    if not site:
        return {'error': 'No site.json config found. Set up site first.'}

    games = get_games()
    results = []

    # Copy shared.css
    os.makedirs(OUTPUT, exist_ok=True)
    shutil.copy2(STATIC / 'shared.css', OUTPUT / 'shared.css')
    results.append('shared.css')

    # Generate portal
    portal_html = generate_portal(site, games)
    (OUTPUT / 'index.html').write_text(portal_html)
    results.append('index.html')

    # Generate RSS feed
    rss_xml = generate_rss(site, games)
    (OUTPUT / 'rss.xml').write_text(rss_xml)
    results.append('rss.xml')

    # Generate each game page
    for game in games:
        if not game.get('visible', True):
            continue
        slug = game.get('slug')
        if not slug:
            continue
        game_dir = OUTPUT / 'games' / slug
        os.makedirs(game_dir, exist_ok=True)
        page_html = generate_game_page(site, game)
        (game_dir / 'index.html').write_text(page_html)
        results.append(f'games/{slug}/index.html')

    return {'generated': results, 'count': len(results)}

def generate_single(slug):
    """Generate a single game page + regenerate portal (since visibility/metadata affects it)."""
    site = get_site_config()
    if not site:
        return {'error': 'No site.json config found.'}
    game = find_game(slug)
    if not game:
        return {'error': f'Game not found: {slug}'}

    results = []

    # Regenerate the game page
    game_dir = OUTPUT / 'games' / slug
    os.makedirs(game_dir, exist_ok=True)
    page_html = generate_game_page(site, game)
    (game_dir / 'index.html').write_text(page_html)
    results.append(f'games/{slug}/index.html')

    # Regenerate portal and RSS (game visibility/metadata may have changed)
    games = get_games()
    portal_html = generate_portal(site, games)
    (OUTPUT / 'index.html').write_text(portal_html)
    results.append('index.html')

    rss_xml = generate_rss(site, games)
    (OUTPUT / 'rss.xml').write_text(rss_xml)
    results.append('rss.xml')

    return {'generated': results}

def normalize_youtube_url(url):
    """Convert any YouTube URL format to a privacy-enhanced embed URL."""
    if not url:
        return ''
    # Extract video ID from various formats
    video_id = ''
    if 'youtu.be/' in url:
        # https://youtu.be/VIDEO_ID or https://youtu.be/VIDEO_ID?params
        parts = url.split('youtu.be/')[-1]
        video_id = parts.split('?')[0].split('&')[0].strip('/')
    elif 'youtube.com/watch' in url:
        # https://www.youtube.com/watch?v=VIDEO_ID
        import urllib.parse as up
        parsed = up.urlparse(url)
        qs = up.parse_qs(parsed.query)
        video_id = qs.get('v', [''])[0]
    elif 'youtube.com/embed/' in url or 'youtube-nocookie.com/embed/' in url:
        # Already an embed URL — extract ID and re-normalize
        parts = url.split('/embed/')[-1]
        video_id = parts.split('?')[0].split('&')[0].strip('/')
    if not video_id:
        return url
    return f'https://www.youtube-nocookie.com/embed/{video_id}'

def xml_escape(s):
    """Escape special characters for XML content."""
    return (str(s)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&apos;'))

def to_rfc2822(date_str):
    """Convert YYYY-MM-DD to RFC 2822 date string for RSS pubDate."""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return d.strftime('%a, %d %b %Y 00:00:00 +0000')
    except (ValueError, TypeError):
        return ''

def generate_rss(site, games):
    """Generate RSS 2.0 feed XML for all visible games."""
    site_url = site.get('site_url', '').rstrip('/')
    site_title = xml_escape(site.get('site_title', site.get('site_name', 'Games')))
    site_desc = xml_escape(site.get('site_tagline', ''))
    now_rfc = datetime.now(UTC).strftime('%a, %d %b %Y %H:%M:%S +0000')
    feed_link = f"{site_url}/" if site_url else ''

    visible = [g for g in games if g.get('visible', True) and g.get('slug')]
    visible.sort(key=lambda g: g.get('date_created', ''), reverse=True)

    # Channel image: use cover of first game that has one
    channel_image = ''
    for g in visible:
        if g.get('cover') and site_url:
            img_url = xml_escape(f"{site_url}/games/{g['slug']}/{g['cover']}")
            channel_image = f"""    <image>
      <url>{img_url}</url>
      <title>{site_title}</title>
      <link>{xml_escape(feed_link)}</link>
    </image>"""
            break

    items = []
    for game in visible:
        slug = game['slug']
        title = xml_escape(game.get('title', slug))
        desc = xml_escape(game.get('description', ''))
        link = f"{site_url}/games/{slug}/" if site_url else f"/games/{slug}/"
        pub_date = to_rfc2822(game.get('date_created', ''))

        # Cover image as enclosure
        enclosure = ''
        cover = game.get('cover', '')
        if cover and site_url:
            cover_url = xml_escape(f"{site_url}/games/{slug}/{cover}")
            enclosure = f'      <enclosure url="{cover_url}" type="image/png" length="0"/>'

        # Tags as categories — deduplicate, preserve order
        seen = set()
        unique_tags = []
        for t in game.get('tags', []):
            if t not in seen:
                seen.add(t)
                unique_tags.append(t)
        categories = '\n'.join(
            f'      <category>{xml_escape(t)}</category>'
            for t in unique_tags
        )

        parts = [
            f'      <title>{title}</title>',
            f'      <link>{xml_escape(link)}</link>',
            f'      <guid isPermaLink="true">{xml_escape(link)}</guid>',
            f'      <description>{desc}</description>',
        ]
        if pub_date:
            parts.append(f'      <pubDate>{pub_date}</pubDate>')
        if enclosure:
            parts.append(enclosure)
        if categories:
            parts.append(categories)

        items.append('    <item>\n' + '\n'.join(parts) + '\n    </item>')

    items_xml = '\n'.join(items)

    atom_self = ''
    if site_url:
        atom_self = f'    <atom:link href="{xml_escape(site_url)}/rss.xml" rel="self" type="application/rss+xml"/>'

    channel_parts = [
        f'    <title>{site_title}</title>',
        f'    <link>{xml_escape(feed_link)}</link>',
        f'    <description>{site_desc}</description>',
        f'    <language>en</language>',
        f'    <lastBuildDate>{now_rfc}</lastBuildDate>',
    ]
    if atom_self:
        channel_parts.append(atom_self)
    if channel_image:
        channel_parts.append(channel_image)

    channel_xml = '\n'.join(channel_parts)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
{channel_xml}
{items_xml}
  </channel>
</rss>
"""

# ═══════════════════════════════════════════════════════
#  MULTIPART FORM PARSER
# ═══════════════════════════════════════════════════════

def parse_multipart(body, content_type):
    """Parse multipart/form-data. Returns dict of {field: value_or_file_info}."""
    boundary = None
    for part in content_type.split(';'):
        part = part.strip()
        if part.startswith('boundary='):
            boundary = part[9:].strip('"')
            break
    if not boundary:
        return {}

    boundary_bytes = ('--' + boundary).encode()
    end_boundary = (boundary_bytes + b'--')

    parts = body.split(boundary_bytes)
    result = {}

    for part in parts:
        if not part or part.strip() == b'--' or part == b'\r\n':
            continue
        part = part.lstrip(b'\r\n')
        if part.startswith(b'--'):
            continue

        # Split headers from body
        header_end = part.find(b'\r\n\r\n')
        if header_end == -1:
            continue
        headers_raw = part[:header_end].decode('utf-8', errors='replace')
        file_data = part[header_end+4:]
        # Remove trailing \r\n
        if file_data.endswith(b'\r\n'):
            file_data = file_data[:-2]

        # Parse Content-Disposition
        name = None
        filename = None
        for line in headers_raw.split('\r\n'):
            if line.lower().startswith('content-disposition:'):
                for param in line.split(';'):
                    param = param.strip()
                    if param.startswith('name='):
                        name = param[5:].strip('"')
                    elif param.startswith('filename='):
                        filename = param[9:].strip('"')

        if name:
            if filename:
                result[name] = {'filename': filename, 'data': file_data}
            else:
                result[name] = file_data.decode('utf-8', errors='replace')

    return result

# ═══════════════════════════════════════════════════════
#  HTTP SERVER
# ═══════════════════════════════════════════════════════

def guess_type(name):
    """Guess MIME type from file extension."""
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    types = {
        'html': 'text/html; charset=utf-8',
        'css': 'text/css; charset=utf-8',
        'js': 'application/javascript; charset=utf-8',
        'json': 'application/json; charset=utf-8',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif': 'image/gif',
        'svg': 'image/svg+xml',
        'ico': 'image/x-icon',
        'webp': 'image/webp',
        'wasm': 'application/wasm',
        'pck': 'application/octet-stream',
        'zip': 'application/zip',
        'woff': 'font/woff',
        'woff2': 'font/woff2',
        'ttf': 'font/ttf',
        'xml': 'text/xml; charset=utf-8',
    }
    return types.get(ext, 'application/octet-stream')


def _allowed_origins():
    """Build the set of origins allowed for CORS."""
    origins = set()
    for host in ('localhost', '127.0.0.1'):
        origins.add(f'http://{host}:{PORT}')
        origins.add(f'http://{host}:{ADMIN_PORT}')
    return origins

ALLOWED_ORIGINS = None  # lazily built on first request

def _check_origin(origin):
    """Return the origin to echo back if allowed, else None."""
    global ALLOWED_ORIGINS
    if ALLOWED_ORIGINS is None:
        ALLOWED_ORIGINS = _allowed_origins()
    if origin and origin in ALLOWED_ORIGINS:
        return origin
    return None


class PublicHandler(http.server.BaseHTTPRequestHandler):
    """Serves only output/ files. No admin, no API."""

    def do_GET(self):
        self._serve()

    def do_HEAD(self):
        self._serve(head=True)

    def _setup_page(self):
        """Return an HTML page directing the user to the admin panel."""
        admin_port = ADMIN_PORT if not SINGLE_PORT else PORT
        return (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>tickle</title>'
            '<style>'
            'body{background:#0c0c14;color:#e2e2ee;font-family:"DM Sans",sans-serif;'
            'display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}'
            '.box{text-align:center;max-width:480px;padding:2rem;}'
            'h1{font-family:"Silkscreen",monospace;color:#ff6b6b;font-size:2rem;margin:0 0 1rem;}'
            'p{color:#8888a8;line-height:1.6;margin:0 0 1.5rem;}'
            'a{color:#ff6b6b;text-decoration:none;border:1px solid #262640;'
            'padding:0.6rem 1.5rem;border-radius:6px;display:inline-block;}'
            'a:hover{border-color:#ff6b6b;background:#1f1f34;}'
            '</style></head><body><div class="box">'
            '<h1>tickle</h1>'
            '<p>This site hasn\'t been set up yet.<br>'
            'Head to the admin panel to get started.</p>'
            f'<a href="http://localhost:{admin_port}/admin">Open Admin Panel</a>'
            '</div></body></html>'
        )

    def _serve(self, head=False):
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        # Resolve against output/
        rel = path.lstrip('/')
        if not rel or rel.endswith('/'):
            rel += 'index.html'
        target = (OUTPUT / rel).resolve()
        # Prevent path traversal
        if not str(target).startswith(str(OUTPUT)):
            self.send_error(403)
            return
        if not target.is_file():
            # Show setup page if the site hasn't been generated yet
            if not (OUTPUT / 'index.html').is_file():
                data = self._setup_page().encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(data))
                self.end_headers()
                if not head:
                    self.wfile.write(data)
                return
            self.send_error(404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', guess_type(target.name))
        self.send_header('Content-Length', len(data))
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass  # silent — public port doesn't need request logs


class TickleHandler(http.server.BaseHTTPRequestHandler):

    def _send_cors_headers(self):
        """Send CORS headers only for allowed origins."""
        origin = self.headers.get('Origin')
        allowed = _check_origin(origin)
        if allowed:
            self.send_header('Access-Control-Allow-Origin', allowed)
            self.send_header('Access-Control-Allow-Credentials', 'true')

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, msg, status=400):
        self.send_json({'error': msg}, status)

    def send_file(self, path, content_type=None):
        if not path.is_file():
            self.send_error_json('Not found', 404)
            return
        data = path.read_bytes()
        if content_type is None:
            content_type = self._guess_type(path.name)
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(data))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _guess_type(self, name):
        return guess_type(name)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        return self.rfile.read(length) if length > 0 else b''

    def _read_json_body(self):
        body = self._read_body()
        try:
            return json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return None

    def _route(self, method):
        """Route the request. Returns True if handled."""
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path).rstrip('/')

        # API routes
        if path.startswith('/api'):
            return self._handle_api(method, path)

        # Admin port root — redirect to /admin
        if path == '' and not SINGLE_PORT:
            self.send_response(302)
            self.send_header('Location', '/admin')
            self.end_headers()
            return True

        # Admin UI — /admin and /admin/*
        if path == '/admin':
            self.send_file(ADMIN / 'index.html')
            return True
        if path.startswith('/admin/'):
            admin_path = ADMIN / path[len('/admin/'):].lstrip('/')
            if admin_path.is_file():
                self.send_file(admin_path)
                return True

        # Preview — /preview/* (banner overlay)
        if path.startswith('/preview'):
            return self._serve_preview(path)

        # Live site — serve output/ at root
        return self._serve_live_site(path)

    def _serve_preview(self, path):
        """Serve output/ files with preview banner."""
        rel = path[len('/preview'):].lstrip('/')
        if rel == '':
            rel = 'index.html'
        file_to_serve = self._resolve_output_path(rel)
        if file_to_serve:
            if file_to_serve.suffix == '.html' and file_to_serve.name == 'index.html':
                self._serve_preview_html(file_to_serve)
            else:
                self.send_file(file_to_serve)
            return True
        self.send_error_json('Not found', 404)
        return True

    def _serve_live_site(self, path):
        """Serve output/ files at root — the actual live site."""
        # In dual-port mode, the admin port should not serve the live site
        # (only /admin, /api, and /preview are accessible)
        if not SINGLE_PORT:
            self.send_response(302)
            self.send_header('Location', '/admin')
            self.end_headers()
            return True
        rel = path.lstrip('/')
        if rel == '':
            # If no site generated yet, redirect to admin setup
            if not (OUTPUT / 'index.html').is_file():
                self.send_response(302)
                self.send_header('Location', '/admin')
                self.end_headers()
                return True
            rel = 'index.html'
        file_to_serve = self._resolve_output_path(rel)
        if file_to_serve:
            self.send_file(file_to_serve)
            return True
        self.send_error_json('Not found', 404)
        return True

    def _resolve_output_path(self, rel):
        """Resolve a relative path to a file in output/."""
        out_path = OUTPUT / rel
        if out_path.is_file():
            return out_path
        idx = out_path / 'index.html'
        if idx.is_file():
            return idx
        return None

    def _handle_api(self, method, path):
        # ── Site config ──
        if path == '/api/site':
            if method == 'GET':
                config = get_site_config()
                if config is None:
                    self.send_json({'exists': False, '_public_port': PORT, '_admin_port': ADMIN_PORT})
                else:
                    config['_public_port'] = PORT
                    config['_admin_port'] = ADMIN_PORT
                    self.send_json(config)
                return True
            elif method == 'PUT':
                data = self._read_json_body()
                if not data:
                    self.send_error_json('Invalid JSON')
                    return True
                save_site_config(data)
                # On first setup (or any save), generate portal so site is live
                generate_all()
                self.send_json({'ok': True})
                return True

        # ── Theme CSS ──
        theme_match = re.match(r'^/api/theme-css/([a-z0-9-]+)$', path)
        if theme_match and method == 'GET':
            css = get_theme_raw_css(theme_match.group(1))
            self.send_json({'css': css})
            return True

        # ── Site logo upload ──
        if path == '/api/site/upload-logo' and method == 'POST':
            content_type = self.headers.get('Content-Type', '')
            body = self._read_body()
            parts = parse_multipart(body, content_type)
            if 'file' not in parts or not isinstance(parts['file'], dict):
                self.send_error_json('No file uploaded')
                return True
            file_info = parts['file']
            filename = file_info['filename']
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'png'
            logo_name = f'site-logo.{ext}'
            os.makedirs(OUTPUT, exist_ok=True)
            (OUTPUT / logo_name).write_bytes(file_info['data'])
            # Update site config
            config = get_site_config() or {}
            config['site_logo_image'] = logo_name
            save_site_config(config)
            self.send_json({'ok': True, 'filename': logo_name})
            return True

        # ── Site logo delete ──
        if path == '/api/site/delete-logo' and method == 'POST':
            config = get_site_config() or {}
            old_logo = config.get('site_logo_image', '')
            if old_logo:
                logo_path = OUTPUT / old_logo
                if logo_path.is_file():
                    logo_path.unlink()
            config['site_logo_image'] = ''
            save_site_config(config)
            self.send_json({'ok': True})
            return True

        # ── Background image upload ──
        if path == '/api/site/upload-bg' and method == 'POST':
            content_type = self.headers.get('Content-Type', '')
            body = self._read_body()
            parts = parse_multipart(body, content_type)
            if 'file' not in parts or not isinstance(parts['file'], dict):
                self.send_error_json('No file uploaded')
                return True
            file_info = parts['file']
            filename = file_info['filename']
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'png'
            bg_name = f'site-bg.{ext}'
            os.makedirs(OUTPUT, exist_ok=True)
            (OUTPUT / bg_name).write_bytes(file_info['data'])
            config = get_site_config() or {}
            config['bg_image'] = bg_name
            save_site_config(config)
            self.send_json({'ok': True, 'filename': bg_name})
            return True

        # ── Background image delete ──
        if path == '/api/site/delete-bg' and method == 'POST':
            config = get_site_config() or {}
            old_bg = config.get('bg_image', '')
            if old_bg:
                bg_path = OUTPUT / old_bg
                if bg_path.is_file():
                    bg_path.unlink()
            config['bg_image'] = ''
            save_site_config(config)
            self.send_json({'ok': True})
            return True

        # ── Games list ──
        if path == '/api/games':
            if method == 'GET':
                self.send_json(get_games())
                return True
            elif method == 'POST':
                data = self._read_json_body()
                title = (data.get('title') or '').strip() if data else ''
                if not title:
                    self.send_error_json('Title is required')
                    return True
                data['title'] = title
                slug = data.get('slug') or slugify(title)
                # Check uniqueness
                if find_game(slug):
                    self.send_error_json(f'Game with slug "{slug}" already exists')
                    return True
                game = {
                    'slug': slug,
                    'title': data['title'],
                    'author': data.get('author', ''),
                    'description': data.get('description', ''),
                    'long_description': data.get('long_description', ''),
                    'engine': data.get('engine', ''),
                    'engine_version': data.get('engine_version', ''),
                    'platform': data.get('platform', 'web'),
                    'status': data.get('status', 'in-dev'),
                    'type': data.get('type', 'game'),
                    'genre': data.get('genre', ''),
                    'tags': data.get('tags', []),
                    'controls': data.get('controls', []),
                    'made_with': data.get('made_with', ''),
                    'input_methods': data.get('input_methods', ''),
                    'version': data.get('version', ''),
                    'date_created': str(date.today()),
                    'date_updated': str(date.today()),
                    'icon': data.get('icon', ''),
                    'cover': data.get('cover', ''),
                    'screenshots': data.get('screenshots', []),
                    'game_file': data.get('game_file', ''),
                    'downloads': data.get('downloads', []),
                    'credits': data.get('credits', []),
                    'links': data.get('links', []),
                    'itch_url': data.get('itch_url', ''),
                    'youtube_url': data.get('youtube_url', ''),
                    'visible': data.get('visible', True),
                }
                # Create game folder
                game_dir = OUTPUT / 'games' / slug
                os.makedirs(game_dir, exist_ok=True)
                os.makedirs(game_dir / 'screenshots', exist_ok=True)
                # Save
                games = get_games()
                games.append(game)
                save_games(games)
                self.send_json(game, 201)
                return True

        # ── Single game ──
        game_match = re.match(r'^/api/games/([a-z0-9-]+)$', path)
        if game_match:
            slug = game_match.group(1)
            if method == 'GET':
                game = find_game(slug)
                if not game:
                    self.send_error_json('Game not found', 404)
                else:
                    self.send_json(game)
                return True
            elif method == 'PUT':
                data = self._read_json_body()
                if not data:
                    self.send_error_json('Invalid JSON')
                    return True
                games = get_games()
                found = False
                for i, g in enumerate(games):
                    if g.get('slug') == slug:
                        # Merge fields
                        for k, v in data.items():
                            if k != 'slug':  # Don't allow slug changes
                                g[k] = v
                        g['date_updated'] = str(date.today())
                        found = True
                        break
                if not found:
                    self.send_error_json('Game not found', 404)
                    return True
                save_games(games)
                self.send_json(games[i])
                return True
            elif method == 'DELETE':
                games = get_games()
                new_games = [g for g in games if g.get('slug') != slug]
                if len(new_games) == len(games):
                    self.send_error_json('Game not found', 404)
                    return True
                save_games(new_games)
                # Delete game folder from disk
                game_dir = OUTPUT / 'games' / slug
                if game_dir.is_dir():
                    shutil.rmtree(game_dir)
                self.send_json({'ok': True, 'deleted': slug})
                return True

        # ── File upload ──
        upload_match = re.match(r'^/api/games/([a-z0-9-]+)/upload$', path)
        if upload_match and method == 'POST':
            slug = upload_match.group(1)
            game = find_game(slug)
            if not game:
                self.send_error_json('Game not found', 404)
                return True

            content_type = self.headers.get('Content-Type', '')
            body = self._read_body()
            parts = parse_multipart(body, content_type)

            upload_type = parts.get('type', 'game')
            game_dir = OUTPUT / 'games' / slug
            os.makedirs(game_dir, exist_ok=True)

            if 'file' not in parts or not isinstance(parts['file'], dict):
                self.send_error_json('No file uploaded')
                return True

            file_info = parts['file']
            filename = file_info['filename']
            file_data = file_info['data']

            if upload_type == 'screenshot':
                ss_dir = game_dir / 'screenshots'
                os.makedirs(ss_dir, exist_ok=True)
                existing = game.get('screenshots', [])
                num = len(existing) + 1
                if num > 6:
                    self.send_error_json('Maximum 6 screenshots')
                    return True
                ext = filename.rsplit('.', 1)[-1] if '.' in filename else 'png'
                new_name = f'{num:02d}.{ext}'
                (ss_dir / new_name).write_bytes(file_data)
                existing.append(new_name)
                self._update_game_field(slug, 'screenshots', existing)
                self.send_json({'ok': True, 'filename': new_name})

            elif upload_type == 'icon':
                ext = filename.rsplit('.', 1)[-1] if '.' in filename else 'png'
                icon_name = f'{slug}.icon.{ext}'
                (game_dir / icon_name).write_bytes(file_data)
                self._update_game_field(slug, 'icon', icon_name)
                self.send_json({'ok': True, 'filename': icon_name})

            elif upload_type == 'cover':
                ext = filename.rsplit('.', 1)[-1] if '.' in filename else 'png'
                cover_name = f'{slug}.{ext}'
                (game_dir / cover_name).write_bytes(file_data)
                self._update_game_field(slug, 'cover', cover_name)
                self.send_json({'ok': True, 'filename': cover_name})

            elif upload_type == 'build':
                # Game build — extract into webgl/ subfolder
                webgl_dir = game_dir / 'webgl'
                os.makedirs(webgl_dir, exist_ok=True)
                if filename.lower().endswith('.zip'):
                    extracted = extract_build_zip(file_data, webgl_dir)
                    # Auto-detect engine after extraction
                    detection = detect_engine(webgl_dir)
                    updates = {}
                    if detection.get('detected'):
                        updates['engine'] = detection['engine']
                        if detection.get('game_file'):
                            updates['game_file'] = 'webgl/' + detection['game_file']
                        # Auto-patch Unity for fullscreen iframe
                        if detection['engine'] == 'unity':
                            patch_unity_for_fullscreen(webgl_dir)
                    if updates:
                        games = get_games()
                        for g in games:
                            if g.get('slug') == slug:
                                g.update(updates)
                                g['date_updated'] = str(date.today())
                                break
                        save_games(games)
                    self.send_json({
                        'ok': True,
                        'extracted': extracted,
                        'detection': detection,
                    })
                else:
                    safe_name = re.sub(r'[^\w.\-]', '_', filename)
                    (webgl_dir / safe_name).write_bytes(file_data)
                    self.send_json({'ok': True, 'filename': 'webgl/' + safe_name})

            elif upload_type == 'model':
                # 3D model file — save to models/ subfolder
                models_dir = game_dir / 'models'
                os.makedirs(models_dir, exist_ok=True)
                safe_name = re.sub(r'[^\w.\-]', '_', filename)
                (models_dir / safe_name).write_bytes(file_data)
                # Compute human-readable size
                size_bytes = len(file_data)
                if size_bytes >= 1024 * 1024:
                    size_str = f'{size_bytes / (1024*1024):.1f}MB'
                else:
                    size_str = f'{size_bytes / 1024:.0f}KB'
                # Add to model_files list
                model_files = game.get('model_files', [])
                model_files.append({
                    'file': f'models/{safe_name}',
                    'size': size_str,
                    'filename': safe_name,
                })
                updates = {'model_files': model_files}
                # Auto-set viewer_file to first .stl if not already set
                if not game.get('viewer_file'):
                    if safe_name.lower().endswith('.stl'):
                        updates['viewer_file'] = f'models/{safe_name}'
                games = get_games()
                for g in games:
                    if g.get('slug') == slug:
                        g.update(updates)
                        g['date_updated'] = str(date.today())
                        break
                save_games(games)
                self.send_json({'ok': True, 'filename': safe_name, 'size': size_str})

            elif upload_type == 'rom':
                # ROM file for EmulatorJS — save to game folder root
                safe_name = re.sub(r'[^\w.\-]', '_', filename)
                (game_dir / safe_name).write_bytes(file_data)
                self._update_game_field(slug, 'game_file', safe_name)
                self.send_json({'ok': True, 'filename': safe_name})

            elif upload_type == 'download':
                # Downloadable binary — save to downloads/ subfolder
                dl_dir = game_dir / 'downloads'
                os.makedirs(dl_dir, exist_ok=True)
                safe_name = re.sub(r'[^\w.\-]', '_', filename)
                (dl_dir / safe_name).write_bytes(file_data)
                # Get platform from form field
                platform = parts.get('platform', 'other')
                size_mb = f'{len(file_data) / (1024*1024):.1f}MB'
                # Add to downloads list
                downloads = game.get('downloads', [])
                downloads.append({
                    'platform': platform,
                    'file': f'downloads/{safe_name}',
                    'size': size_mb,
                })
                self._update_game_field(slug, 'downloads', downloads)
                self.send_json({'ok': True, 'filename': safe_name, 'size': size_mb})

            else:
                # Generic file
                safe_name = re.sub(r'[^\w.\-]', '_', filename)
                (game_dir / safe_name).write_bytes(file_data)
                if upload_type == 'game':
                    self._update_game_field(slug, 'game_file', safe_name)
                self.send_json({'ok': True, 'filename': safe_name})

            return True

        # ── List files in game folder ──
        files_match = re.match(r'^/api/games/([a-z0-9-]+)/files$', path)
        if files_match and method == 'GET':
            slug = files_match.group(1)
            game_dir = OUTPUT / 'games' / slug
            if not game_dir.is_dir():
                self.send_json([])
                return True
            # Exclude cover/icon media from the build file list
            game = find_game(slug)
            media = set()
            if game:
                if game.get('cover'):
                    media.add(game['cover'])
                if game.get('icon'):
                    media.add(game['icon'])
            files = list_game_files(game_dir, exclude_media=media)
            self.send_json(files)
            return True

        # ── Delete file from game folder ──
        if files_match and method == 'DELETE':
            slug = files_match.group(1)
            game_dir = OUTPUT / 'games' / slug
            body = self._read_body()
            if not body:
                self.send_error_json('Missing request body')
                return True
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                self.send_error_json('Invalid JSON')
                return True
            rel_path = data.get('file', '')
            if not rel_path or '..' in rel_path or rel_path.startswith('/'):
                self.send_error_json('Invalid file path')
                return True
            target = (game_dir / rel_path).resolve()
            # Ensure target is inside game_dir
            if not str(target).startswith(str(game_dir.resolve())):
                self.send_error_json('Invalid file path')
                return True
            if not target.is_file():
                self.send_error_json('File not found', 404)
                return True
            target.unlink()
            # Remove empty parent dirs up to game_dir
            parent = target.parent
            while parent != game_dir.resolve() and parent != game_dir:
                try:
                    parent.rmdir()  # only removes if empty
                    parent = parent.parent
                except OSError:
                    break
            # If deleted file was the game_file, clear it
            game = find_game(slug)
            if game and game.get('game_file') == rel_path:
                self._update_game_field(slug, 'game_file', '')
            self.send_json({'ok': True})
            return True

        # ── Generate ──
        if path == '/api/generate' and method == 'POST':
            result = generate_all()
            self.send_json(result)
            return True

        gen_match = re.match(r'^/api/generate/([a-z0-9-]+)$', path)
        if gen_match and method == 'POST':
            slug = gen_match.group(1)
            # Check if update_date flag is set
            body = self._read_body()
            update_date = False
            if body:
                try:
                    data = json.loads(body)
                    update_date = data.get('update_date', False)
                except (json.JSONDecodeError, ValueError):
                    pass
            if update_date:
                game = find_game(slug)
                if game:
                    game['date_updated'] = str(date.today())
                    save_games(get_games())
            result = generate_single(slug)
            self.send_json(result)
            return True

        # ── Engine detection ──
        detect_match = re.match(r'^/api/detect-engine/([a-z0-9-]+)$', path)
        if detect_match and method == 'GET':
            slug = detect_match.group(1)
            game_dir = OUTPUT / 'games' / slug
            # Check webgl/ subfolder first (new uploads), fall back to game_dir (legacy)
            webgl_dir = game_dir / 'webgl'
            if webgl_dir.is_dir():
                result = detect_engine(webgl_dir)
                if result.get('detected') and result.get('game_file'):
                    result['game_file'] = 'webgl/' + result['game_file']
            else:
                result = detect_engine(game_dir)
            self.send_json(result)
            return True

        # ── Itch.io import ──
        if path == '/api/import/itch' and method == 'POST':
            data = self._read_json_body()
            if not data or not data.get('url'):
                self.send_error_json('URL is required')
                return True
            result = scrape_itch_game(data['url'])
            if result.get('error'):
                status = 502 if 'fetch' in result['error'].lower() else 400
                if '404' in result['error'] or 'not found' in result['error'].lower():
                    status = 404
                elif 'rate limit' in result['error'].lower():
                    status = 429
                self.send_json(result, status)
            else:
                self.send_json(result)
            return True

        if path == '/api/import/itch/confirm' and method == 'POST':
            data = self._read_json_body()
            if not data or not data.get('game'):
                self.send_error_json('Game data is required')
                return True

            game_data = data['game']
            slug = game_data.get('slug', '')
            if not slug:
                self.send_error_json('Slug is required')
                return True

            # Check slug uniqueness
            if find_game(slug):
                self.send_error_json(f'Game with slug "{slug}" already exists', 409)
                return True

            # Create game entry
            game = {
                'slug': slug,
                'title': game_data.get('title', slug),
                'author': game_data.get('author', ''),
                'description': game_data.get('description', ''),
                'long_description': game_data.get('long_description', ''),
                'engine': game_data.get('engine', ''),
                'engine_version': '',
                'platform': game_data.get('platform', 'web'),
                'status': game_data.get('status', 'in-dev'),
                'type': game_data.get('type', 'game'),
                'genre': game_data.get('genre', ''),
                'tags': game_data.get('tags', []),
                'controls': [],
                'made_with': game_data.get('made_with', ''),
                'input_methods': game_data.get('input_methods', ''),
                'version': '',
                'date_created': str(date.today()),
                'date_updated': str(date.today()),
                'icon': '',
                'cover': '',
                'screenshots': [],
                'game_file': '',
                'downloads': [],
                'credits': [],
                'links': [],
                'itch_url': game_data.get('itch_url', ''),
                'youtube_url': game_data.get('youtube_url', ''),
                'visible': True,
            }

            # Create game folder
            game_dir = OUTPUT / 'games' / slug
            os.makedirs(game_dir, exist_ok=True)
            os.makedirs(game_dir / 'screenshots', exist_ok=True)

            # Download icon
            icon_url = data.get('icon_url', '')
            if icon_url:
                ext = 'png'
                if '.jpg' in icon_url or '.jpeg' in icon_url:
                    ext = 'jpg'
                icon_name = f'{slug}.icon.{ext}'
                if itch_download_image(icon_url, str(game_dir / icon_name)):
                    game['icon'] = icon_name

            # Download cover image
            cover_url = data.get('cover_url', '')
            if cover_url:
                ext = 'png'
                if '.jpg' in cover_url or '.jpeg' in cover_url:
                    ext = 'jpg'
                elif '.gif' in cover_url:
                    ext = 'gif'
                elif '.webp' in cover_url:
                    ext = 'webp'
                cover_name = f'{slug}.{ext}'
                if itch_download_image(cover_url, str(game_dir / cover_name)):
                    game['cover'] = cover_name

            # Download screenshots
            screenshot_urls = data.get('screenshot_urls', [])
            for i, ss_url in enumerate(screenshot_urls[:6]):
                ext = 'png'
                if '.jpg' in ss_url or '.jpeg' in ss_url:
                    ext = 'jpg'
                elif '.gif' in ss_url:
                    ext = 'gif'
                ss_name = f'{i+1:02d}.{ext}'
                if itch_download_image(ss_url, str(game_dir / 'screenshots' / ss_name)):
                    game['screenshots'].append(ss_name)

            # Save to games.json
            games = get_games()
            games.append(game)
            save_games(games)

            self.send_json({'ok': True, 'game': game}, 201)
            return True

        if path == '/api/import/itch/profile' and method == 'POST':
            data = self._read_json_body()
            if not data or not data.get('url'):
                self.send_error_json('URL is required')
                return True
            result = scrape_itch_profile(data['url'])
            if result.get('error'):
                status = 404 if 'not found' in result['error'].lower() else 502
                self.send_json(result, status)
            else:
                self.send_json(result)
            return True

        # ── Analytics hit ──
        hit_match = re.match(r'^/api/hit/([a-z0-9-]+)$', path)
        if hit_match and method == 'GET':
            slug = hit_match.group(1)
            games = get_games()
            for g in games:
                if g.get('slug') == slug:
                    g['views'] = g.get('views', 0) + 1
                    save_games(games)
                    self.send_json({'views': g['views']})
                    return True
            self.send_json({'views': 0})
            return True

        self.send_error_json('API endpoint not found', 404)
        return True


    def _serve_preview_html(self, path):
        """Serve an HTML page with preview banner injected."""
        html = path.read_text()
        banner = (
            '<div id="tickle-preview-banner" style="'
            'position:fixed;top:0;left:0;right:0;z-index:99999;'
            'background:rgba(254,202,87,0.95);color:#0c0c14;'
            'text-align:center;padding:6px 16px;font-family:\'DM Mono\',monospace;'
            'font-size:0.75rem;font-weight:600;letter-spacing:0.5px;'
            'display:flex;align-items:center;justify-content:center;gap:12px;'
            '">'
            '<span>PREVIEW MODE</span>'
            '<span style="font-weight:400;opacity:0.7;">This is a local preview &mdash; not the live site</span>'
            '<a href="/admin" style="color:#0c0c14;text-decoration:underline;margin-left:auto;font-weight:400;"'
            '>&larr; Back to Admin</a>'
            '<button onclick="this.parentElement.remove()" style="'
            'background:none;border:none;color:#0c0c14;cursor:pointer;'
            'font-size:1rem;line-height:1;opacity:0.5;margin-left:4px;'
            '">&times;</button>'
            '</div>'
            '<style>body{padding-top:33px;}</style>'
        )
        # Inject after <body> tag
        html = html.replace('<body>', '<body>' + banner, 1)
        data = html.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(data))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _update_game_field(self, slug, field, value):
        games = get_games()
        for g in games:
            if g.get('slug') == slug:
                g[field] = value
                g['date_updated'] = str(date.today())
                break
        save_games(games)

    # HTTP method handlers
    def do_GET(self):
        self._route('GET')

    def do_POST(self):
        self._route('POST')

    def do_PUT(self):
        self._route('PUT')

    def do_DELETE(self):
        self._route('DELETE')

    def do_HEAD(self):
        self._route('GET')

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, fmt, *args):
        try:
            # Standard request log: "METHOD /path HTTP/1.1", status, size
            if args and isinstance(args[0], str) and ' ' in args[0]:
                parts = args[0].split()
                method = parts[0]
                path_str = parts[1] if len(parts) > 1 else ''
                status = str(args[1]) if len(args) > 1 else ''
                if status.startswith('2'):
                    color = '\033[32m'
                elif status.startswith('4'):
                    color = '\033[33m'
                else:
                    color = '\033[0m'
                print(f'{color}{method} {path_str} \u2192 {status}\033[0m')
            else:
                print(fmt % args if args else fmt)
        except Exception:
            print(fmt % args if args else fmt)


def extract_build_zip(zip_data, game_dir):
    """Extract a zip file into the game directory. Returns list of extracted files.
    If the zip has a single top-level directory, extracts its contents directly
    into game_dir (strip the wrapper folder).
    """
    extracted = []
    with zipfile.ZipFile(BytesIO(zip_data)) as zf:
        names = zf.namelist()
        # Check for single wrapper directory
        top_dirs = set()
        for n in names:
            parts = n.split('/')
            if parts[0]:
                top_dirs.add(parts[0])

        strip_prefix = ''
        if len(top_dirs) == 1:
            candidate = top_dirs.pop() + '/'
            # Only strip if most files are under this prefix
            if all(n.startswith(candidate) or n == candidate.rstrip('/') for n in names if n):
                strip_prefix = candidate

        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if strip_prefix and name.startswith(strip_prefix):
                name = name[len(strip_prefix):]
            if not name:
                continue
            # Security: prevent path traversal
            if '..' in name or name.startswith('/'):
                continue
            target = game_dir / name
            os.makedirs(target.parent, exist_ok=True)
            with zf.open(info) as src:
                target.write_bytes(src.read())
            extracted.append(name)

    return extracted


def list_game_files(game_dir, prefix='', exclude_media=None):
    """List files in game directory recursively. Returns list of relative paths.
    exclude_media: set of filenames (cover, icon) to skip from the build file list.
    """
    files = []
    skip = {'index.html', 'screenshots', 'downloads', 'models'}
    if exclude_media is None:
        exclude_media = set()
    for entry in sorted(game_dir.iterdir()):
        rel = f'{prefix}{entry.name}' if not prefix else f'{prefix}/{entry.name}'
        if not prefix and (entry.name in skip or entry.name in exclude_media):
            continue
        if entry.is_file():
            size = entry.stat().st_size
            files.append({'name': rel, 'size': size})
        elif entry.is_dir():
            files.extend(list_game_files(entry, rel, exclude_media))
    return files


def patch_unity_for_fullscreen(game_dir):
    """Auto-patch Unity WebGL export to fill its container (iframe).
    Modifies the TemplateData/style.css and the game HTML to use 100% sizing
    instead of Unity's default fixed/centered layout.
    """
    patched = []

    # Patch TemplateData/style.css if it exists
    style_path = game_dir / 'TemplateData' / 'style.css'
    if style_path.is_file():
        css = style_path.read_text()
        # Replace the centering transform with full-size
        if 'translate(-50%, -50%)' in css:
            css = css.replace(
                'position: absolute; top: 50%; left: 50%; -webkit-transform: translate(-50%, -50%); transform: translate(-50%, -50%);',
                'position: absolute; inset: 0; width: 100%; height: 100%;'
            )
            style_path.write_text(css)
            patched.append('TemplateData/style.css')

    # Patch the game HTML to make unityContainer fill viewport
    for f in game_dir.iterdir():
        if f.suffix == '.html' and f.name != 'index.html':
            html = f.read_text()
            if 'unityContainer' in html and 'tickle-patched' not in html:
                # Inject fullscreen styles into <head>
                inject = (
                    '<!-- tickle-patched -->\n'
                    '<style>\n'
                    '  html, body { margin: 0; padding: 0; overflow: hidden; width: 100%; height: 100%; }\n'
                    '  .webgl-content, #unityContainer { width: 100% !important; height: 100% !important; }\n'
                    '  #unityContainer canvas { width: 100% !important; height: 100% !important; }\n'
                    '  .webgl-content .footer { display: none; }\n'
                    '</style>\n'
                )
                html = html.replace('</head>', inject + '</head>')
                f.write_text(html)
                patched.append(f.name)

    return patched


def detect_engine(game_dir):
    """Scan game folder and detect engine type."""
    if not game_dir.is_dir():
        return {'engine': None, 'reason': 'Directory not found'}

    files = [f.name for f in game_dir.iterdir()]
    files_lower = [f.lower() for f in files]

    # Godot: look for .pck + .wasm + .html
    has_pck = any(f.endswith('.pck') for f in files_lower)
    has_wasm = any(f.endswith('.wasm') for f in files_lower)
    has_html = any(f.endswith('.html') and f != 'index.html' for f in files_lower)

    if has_pck and has_wasm:
        game_file = next((f for f in files if f.lower().endswith('.html') and f.lower() != 'index.html'), None)
        return {'engine': 'godot', 'game_file': game_file, 'detected': True}

    # Unity: look for Build/ directory
    build_dir = game_dir / 'Build'
    if build_dir.is_dir():
        build_files = [f.name for f in build_dir.iterdir()]
        has_framework = any(f.endswith('.framework.js') for f in build_files)
        has_loader = any('UnityLoader' in f for f in build_files) or has_framework
        if has_loader:
            game_file = next((f for f in files if f.lower().endswith('.html') and f.lower() != 'index.html'), None)
            return {'engine': 'unity', 'game_file': game_file, 'detected': True}

    return {'engine': None, 'detected': False}


# ═══════════════════════════════════════════════════════
#  ITCH.IO IMPORTER
# ═══════════════════════════════════════════════════════

def parse_itch_url(url):
    """Parse an itch.io URL into (author, slug) or (author, None) for profiles."""
    url = url.strip().rstrip('/')
    parsed = urllib.parse.urlparse(url)

    # Format: https://author.itch.io/game-slug or https://author.itch.io
    host = parsed.hostname or ''
    if host.endswith('.itch.io'):
        author = host[:-len('.itch.io')]
        path_parts = [p for p in parsed.path.strip('/').split('/') if p]
        slug = path_parts[0] if path_parts else None
        return (author, slug)

    # Format: https://itch.io/profile/author (profile page)
    if host == 'itch.io' and '/profile/' in parsed.path:
        parts = parsed.path.strip('/').split('/')
        idx = parts.index('profile') if 'profile' in parts else -1
        if idx >= 0 and idx + 1 < len(parts):
            return (parts[idx + 1], None)

    return (None, None)


def itch_fetch(url, timeout=15):
    """Fetch a URL with a proper User-Agent. Returns bytes or raises."""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; tickle-importer/1.0)',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def itch_download_image(url, dest_path):
    """Download an image from a URL to a local path."""
    try:
        data = itch_fetch(url)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, 'wb') as f:
            f.write(data)
        return True
    except Exception:
        return False


class ItchGamePageParser(HTMLParser):
    """Extract metadata from an itch.io game page HTML."""

    def __init__(self):
        super().__init__()
        self.meta = {}
        self.screenshots = []
        self.tags = []
        self.info_rows = {}
        self.downloads = []

        # State tracking
        self._in_formatted_desc = False
        self._formatted_desc_depth = 0
        self._formatted_desc_parts = []
        self._in_info_panel = False
        self._info_panel_depth = 0
        self._in_info_tr = False
        self._info_td_count = 0
        self._info_label = ''
        self._info_value_parts = []
        self._in_tag_link = False
        self._tag_parts = []
        self._in_upload = False
        self._upload_name = ''
        self._upload_platforms = []
        self._upload_size = ''
        self._in_upload_name = False
        self._in_file_size = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # Meta tags (og:title, og:description, og:image)
        if tag == 'meta':
            prop = attrs_dict.get('property', '') or attrs_dict.get('name', '')
            content = attrs_dict.get('content', '')
            if prop in ('og:title', 'og:description', 'og:image'):
                self.meta[prop] = content

        # YouTube embed
        if tag == 'iframe':
            src = attrs_dict.get('src', '')
            if 'youtube.com/embed/' in src or 'youtu.be/' in src:
                # Normalize to https and use privacy-enhanced domain
                if src.startswith('//'):
                    src = 'https:' + src
                src = src.replace('www.youtube.com/embed/', 'www.youtube-nocookie.com/embed/')
                self.meta['youtube'] = src

        # Favicon / icon link
        if tag == 'link':
            rel = attrs_dict.get('rel', '')
            if 'icon' in rel and 'apple' not in rel:
                href = attrs_dict.get('href', '')
                if href and 'img.itch.zone' in href:
                    self.meta['icon'] = href

        # Screenshots: <a data-image_lightbox> with /original/ href
        if tag == 'a' and attrs_dict.get('data-image_lightbox'):
            href = attrs_dict.get('href', '')
            if 'img.itch.zone' in href and '/original/' in href:
                self.screenshots.append(href)

        # Formatted description div
        if tag == 'div' and 'formatted_description' in attrs_dict.get('class', ''):
            self._in_formatted_desc = True
            self._formatted_desc_depth = 1
            return

        if self._in_formatted_desc:
            # Void elements don't increase depth (they have no closing tag)
            void_tags = {'br', 'img', 'hr', 'input', 'meta', 'link'}
            if tag not in void_tags:
                self._formatted_desc_depth += 1
            # Convert some tags to simple HTML
            if tag in ('p', 'br'):
                self._formatted_desc_parts.append(f'<{tag}>')
            elif tag in ('strong', 'b', 'em', 'i', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4'):
                self._formatted_desc_parts.append(f'<{tag}>')
            elif tag == 'a':
                href = attrs_dict.get('href', '#')
                self._formatted_desc_parts.append(f'<a href="{href}">')

        # Info panel: <div class="game_info_panel_widget"> contains a <table>
        if tag == 'div' and 'game_info_panel_widget' in attrs_dict.get('class', ''):
            self._in_info_panel = True
            self._info_panel_depth = 0
        if self._in_info_panel and tag == 'div':
            self._info_panel_depth += 1
        if self._in_info_panel and tag == 'tr':
            self._in_info_tr = True
            self._info_td_count = 0
            self._info_label = ''
            self._info_value_parts = []
        if self._in_info_tr and tag == 'td':
            self._info_td_count += 1

        # Tag links (absolute URLs on itch.io) — skip if inside info panel
        # (genre links in the info panel also use /games/tag- URLs)
        href = attrs_dict.get('href', '')
        if tag == 'a' and '/games/tag-' in href and not self._in_info_panel:
            self._in_tag_link = True
            self._tag_parts = []

        # Upload rows
        if tag == 'div' and 'upload' in attrs_dict.get('class', '').split():
            self._in_upload = True
            self._upload_name = ''
            self._upload_platforms = []
            self._upload_size = ''
        if self._in_upload:
            if tag == 'strong' and 'name' in attrs_dict.get('class', ''):
                self._in_upload_name = True
            if tag == 'span' and 'file_size' in attrs_dict.get('class', ''):
                self._in_file_size = True
            if tag == 'span' and 'icon':
                icon_class = attrs_dict.get('class', '')
                for platform in ('windows8', 'apple', 'tux', 'android'):
                    if f'icon-{platform}' in icon_class:
                        mapped = {'windows8': 'windows', 'apple': 'macos', 'tux': 'linux', 'android': 'android'}
                        self._upload_platforms.append(mapped.get(platform, platform))

    def handle_endtag(self, tag):
        if self._in_formatted_desc:
            self._formatted_desc_depth -= 1
            if self._formatted_desc_depth <= 0:
                self._in_formatted_desc = False
            elif tag in ('p', 'strong', 'b', 'em', 'i', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'a'):
                self._formatted_desc_parts.append(f'</{tag}>')

        if self._in_info_tr and tag == 'tr':
            self._in_info_tr = False
            if self._info_label and self._info_value_parts:
                key = self._info_label.strip().rstrip(':').lower()
                # Filter out standalone commas (itch.io puts commas as text between <a> tags)
                parts = [p for p in self._info_value_parts if p.strip(',').strip()]
                val = ', '.join(parts)
                if val:
                    self.info_rows[key] = val
        if self._in_info_panel and tag == 'div':
            self._info_panel_depth -= 1
            if self._info_panel_depth <= 0:
                self._in_info_panel = False
                self._in_info_tr = False
        if self._in_info_panel and tag == 'table':
            self._in_info_panel = False
            self._in_info_tr = False

        if self._in_tag_link and tag == 'a':
            self._in_tag_link = False
            text = ''.join(self._tag_parts).strip()
            if text:
                self.tags.append(text.lower())

        if self._in_upload and tag == 'div':
            if self._upload_name:
                self.downloads.append({
                    'name': self._upload_name,
                    'platforms': self._upload_platforms,
                    'size': self._upload_size,
                })
            self._in_upload = False

        if self._in_upload_name and tag == 'strong':
            self._in_upload_name = False
        if self._in_file_size and tag == 'span':
            self._in_file_size = False

    def handle_data(self, data):
        if self._in_formatted_desc:
            self._formatted_desc_parts.append(data)

        if self._in_info_tr:
            stripped = data.strip()
            if stripped:
                if self._info_td_count <= 1:
                    self._info_label += stripped
                else:
                    self._info_value_parts.append(stripped)

        if self._in_tag_link:
            self._tag_parts.append(data)

        if self._in_upload_name:
            self._upload_name += data.strip()
        if self._in_file_size:
            self._upload_size += data.strip()

    def get_long_description(self):
        return ''.join(self._formatted_desc_parts).strip()


class ItchProfilePageParser(HTMLParser):
    """Extract game list from an itch.io profile/creator page."""

    def __init__(self):
        super().__init__()
        self.games = []
        self._in_game_cell = False
        self._game_cell_depth = 0
        self._current_game = {}
        self._in_title_div = False
        self._in_title_link = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classes = attrs_dict.get('class', '')

        # Game cell container
        if tag == 'div' and 'game_cell' in classes.split():
            self._in_game_cell = True
            self._game_cell_depth = 1
            self._current_game = {}
            return

        if self._in_game_cell:
            self._game_cell_depth += 1

            # Title is inside <div class="game_title"><a href="...">Title</a></div>
            if tag == 'div' and 'game_title' in classes:
                self._in_title_div = True
            if self._in_title_div and tag == 'a':
                href = attrs_dict.get('href', '')
                if href:
                    self._current_game['url'] = href
                self._in_title_link = True

            # Thumbnail: <img data-lazy_src="..." class="lazy_loaded">
            if tag == 'img':
                src = attrs_dict.get('data-lazy_src', '') or attrs_dict.get('src', '')
                if src and 'img.itch.zone' in src and not self._current_game.get('thumb_url'):
                    self._current_game['thumb_url'] = src

    def handle_endtag(self, tag):
        if self._in_title_link and tag == 'a':
            self._in_title_link = False
        if self._in_title_div and tag == 'div':
            self._in_title_div = False

        if self._in_game_cell:
            self._game_cell_depth -= 1
            if self._game_cell_depth <= 0:
                self._in_game_cell = False
                if self._current_game.get('url') and self._current_game.get('title'):
                    self.games.append(dict(self._current_game))

    def handle_data(self, data):
        if self._in_title_link:
            text = data.strip()
            if text:
                self._current_game['title'] = text


STATUS_MAP = {
    'released': 'released',
    'in development': 'in-dev',
    'prototype': 'prototype',
    'on hold': 'in-dev',
    'canceled': 'in-dev',
    'devlog': 'in-dev',
}


def scrape_itch_game(url):
    """Scrape metadata from a single itch.io game page."""
    author, slug = parse_itch_url(url)
    if not author or not slug:
        return {'error': 'Invalid itch.io game URL'}

    warnings = []
    game_data = {'slug': slug, 'itch_url': url, 'author': author}

    # 1. Try data.json first (lightweight)
    data_url = f'https://{author}.itch.io/{slug}/data.json'
    try:
        raw = itch_fetch(data_url)
        dj = json.loads(raw)
        if dj.get('title'):
            game_data['title'] = dj['title']
        if dj.get('cover_image'):
            game_data['_cover_url'] = dj['cover_image']
    except Exception:
        warnings.append('data.json not available, using HTML only')

    # 2. Fetch + parse full HTML page
    page_url = f'https://{author}.itch.io/{slug}'
    try:
        html_bytes = itch_fetch(page_url)
        html = html_bytes.decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        code = e.code
        if code == 404:
            return {'error': f'Game not found: {page_url}'}
        elif code == 429:
            return {'error': 'Rate limited by itch.io. Try again in a minute.'}
        return {'error': f'itch.io returned HTTP {code}'}
    except Exception as e:
        return {'error': f'Failed to fetch page: {str(e)}'}

    parser = ItchGamePageParser()
    parser.feed(html)

    # Merge HTML data
    if parser.meta.get('og:title') and not game_data.get('title'):
        game_data['title'] = parser.meta['og:title']
    if parser.meta.get('og:description'):
        game_data['description'] = parser.meta['og:description']
    if parser.meta.get('og:image') and not game_data.get('_cover_url'):
        game_data['_cover_url'] = parser.meta['og:image']
    if parser.meta.get('icon'):
        game_data['_icon_url'] = parser.meta['icon']
    if parser.meta.get('youtube'):
        game_data['youtube_url'] = parser.meta['youtube']

    long_desc = parser.get_long_description()
    if long_desc:
        game_data['long_description'] = long_desc

    # Info panel fields
    info = parser.info_rows
    if info.get('status'):
        game_data['status'] = STATUS_MAP.get(info['status'].lower(), 'in-dev')
    if info.get('genre'):
        game_data['genre'] = info['genre']
    if info.get('made with'):
        game_data['made_with'] = info['made with']
    if info.get('inputs'):
        game_data['input_methods'] = info['inputs']
    if info.get('platforms'):
        game_data['platform'] = info['platforms']
    if info.get('author') and not game_data.get('author'):
        game_data['author'] = info['author']

    # Merge tags from both tag links and info panel rows
    all_tags = list(parser.tags)
    info_tags_str = info.get('tags', '')
    if info_tags_str:
        for t in info_tags_str.split(','):
            t = t.strip().lower()
            if t:
                all_tags.append(t)
    if all_tags:
        # Deduplicate while preserving order, exclude genre (already a separate field)
        genre_lower = game_data.get('genre', '').lower()
        seen = set()
        unique_tags = []
        for t in all_tags:
            if t not in seen and t != genre_lower:
                seen.add(t)
                unique_tags.append(t)
        game_data['tags'] = unique_tags
    if parser.screenshots:
        game_data['_screenshot_urls'] = parser.screenshots
    if parser.downloads:
        game_data['downloads'] = [
            {'platform': d['platforms'][0] if d['platforms'] else 'other',
             'file': d['name'], 'size': d['size']}
            for d in parser.downloads if d.get('name')
        ]

    # Defaults
    game_data.setdefault('title', slug.replace('-', ' ').title())
    game_data.setdefault('status', 'released')
    game_data.setdefault('type', 'game')

    return {'ok': True, 'game': game_data, 'warnings': warnings}


def scrape_itch_profile(url):
    """Scrape the list of games from an itch.io profile page."""
    author, _ = parse_itch_url(url)
    if not author:
        return {'error': 'Invalid itch.io profile URL'}

    profile_url = f'https://{author}.itch.io'
    try:
        html_bytes = itch_fetch(profile_url)
        html = html_bytes.decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {'error': f'Profile not found: {author}'}
        return {'error': f'itch.io returned HTTP {e.code}'}
    except Exception as e:
        return {'error': f'Failed to fetch profile: {str(e)}'}

    parser = ItchProfilePageParser()
    parser.feed(html)

    if not parser.games:
        return {'error': 'No games found on profile page'}

    return {'ok': True, 'games': parser.games}


# ═══════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════

if __name__ == '__main__':
    # Ensure output directory exists
    os.makedirs(OUTPUT, exist_ok=True)
    os.makedirs(OUTPUT / 'games', exist_ok=True)

    if SINGLE_PORT:
        # Single-port mode: everything on one port (legacy behavior)
        admin_server = http.server.HTTPServer(('', PORT), TickleHandler)
        print(f'\033[1m')
        print(f'  tickle — self-hosted game portal (single-port mode)')
        print(f'  ──────────────────────────────────────────────────')
        print(f'  http://0.0.0.0:{PORT}')
        print(f'\033[0m')
        try:
            admin_server.serve_forever()
        except KeyboardInterrupt:
            print('\nShutting down.')
            admin_server.shutdown()
    else:
        # Dual-port mode: public site on PORT, admin on ADMIN_PORT
        public_server = http.server.HTTPServer(('', PORT), PublicHandler)
        admin_server = http.server.HTTPServer(('', ADMIN_PORT), TickleHandler)

        print(f'\033[1m')
        print(f'  tickle — self-hosted game portal')
        print(f'  ────────────────────────────────')
        print(f'  Public site:  http://0.0.0.0:{PORT}')
        print(f'  Admin panel:  http://0.0.0.0:{ADMIN_PORT}')
        print(f'\033[0m')

        # Run public server in a daemon thread
        public_thread = threading.Thread(target=public_server.serve_forever, daemon=True)
        public_thread.start()

        try:
            admin_server.serve_forever()
        except KeyboardInterrupt:
            print('\nShutting down.')
            admin_server.shutdown()
            public_server.shutdown()
