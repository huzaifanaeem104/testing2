# -*- coding: utf-8 -*-


def clip_project_name(name):
    """Show the short project title, not the repeated 'NAME | ROLE | - NAME | ROLE' form."""
    if not name:
        return ''
    text = str(name).strip()
    if ' / ' in text:
        prefix = text.split(' / ', 1)[0]
        if '|' not in prefix:
            text = text.rsplit(' / ', 1)[-1].strip()
    if '|' in text:
        text = text.split('|', 1)[0].strip()
    if ' - ' in text:
        left, right = text.split(' - ', 1)
        if left.strip().casefold() == right.strip().casefold():
            text = left.strip()
    return text
