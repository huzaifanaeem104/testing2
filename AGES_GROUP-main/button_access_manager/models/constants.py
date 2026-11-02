# -*- coding: utf-8 -*-

# Catalog of common cross-model actions. Each entry is:
#   (field_name, checkbox_label, button_type, [technical_name aliases], [matching visible labels])
#
# Server-side blocking is exact per alias (the real method / action name).
# Visual hiding for framework items uses view attributes and CSS classes,
# not translated labels. Object-button labels are admin reference only.
GLOBAL_ACTIONS = [
    ('restrict_new', 'New / Create', 'create',
        [''], ['New']),
    ('restrict_delete', 'Delete', 'delete',
        [''], ['Delete']),
    ('restrict_duplicate', 'Duplicate', 'duplicate',
        [''], ['Duplicate']),
    ('restrict_import', 'Import', 'import',
        [''], ['Import']),
    ('restrict_export', 'Export', 'export',
        [''], ['Export']),
    ('restrict_archive', 'Archive / Unarchive', 'object',
        ['action_archive', 'action_unarchive', 'toggle_active'],
        ['Archive', 'Unarchive', 'Archive']),
    ('restrict_print', 'Print (all reports)', 'report',
        [''], ['Print']),
    ('restrict_cancel', 'Cancel', 'object',
        ['action_cancel', 'button_cancel'],
        ['Cancel', 'Cancel']),
    ('restrict_reset_draft', 'Reset to Draft / Set to Quotation', 'object',
        ['action_draft', 'button_draft', 'action_set_to_draft'],
        ['Reset to Draft', 'Set to Quotation', 'Reset to Draft']),
    ('restrict_confirm', 'Confirm / Validate', 'object',
        ['action_confirm', 'button_confirm', 'button_validate', 'action_validate'],
        ['Confirm', 'Confirm', 'Validate', 'Validate']),
    ('restrict_post', 'Post (Confirm Invoices & Bills)', 'object',
        ['action_post'], ['Post']),
    ('restrict_lock', 'Lock', 'object',
        ['action_lock'], ['Lock']),
    ('restrict_unlock', 'Unlock', 'object',
        ['action_unlock'], ['Unlock']),
    ('restrict_send_email', 'Send by Email', 'object',
        ['action_quotation_send', 'action_invoice_sent', 'action_send_mail'],
        ['Send by Email', 'Send', 'Send by Email']),
    ('restrict_done', 'Mark Done / Close', 'object',
        ['action_done', 'action_close'], ['Done', 'Close']),
]

# Global (all-models) rules are skipped on these. A model-specific rule still applies.
FRAMEWORK_PREFIXES = (
    'mail.',
    'ir.',
    'bus.',
    'base_import.',
    'button.access.',
    'access.profile',
    'access.block.',
    'web_tour.',
    'discuss.',
    'res.users.settings',
    'res.device',
)

FRAMEWORK_MODELS = {
    'res.users.settings',
    'res.users.settings.volumes',
    'res.users.apikeys',
    'res.users.apikeys.description',
    'res.users.log',
    'res.device.log',
}

BUTTON_TYPE_SELECTION = [
    ('create', 'New / Create'),
    ('delete', 'Delete'),
    ('duplicate', 'Duplicate'),
    ('import', 'Import'),
    ('export', 'Export'),
    ('object', 'Object Button (calls a model method)'),
    ('action', 'Action Button (opens a window action)'),
    ('report', 'Print / Report'),
    ('other', 'Other / Custom'),
]

METHOD_TO_BUTTON_TYPE = {
    'create': 'create',
    'unlink': 'delete',
    'copy': 'duplicate',
    'export_data': 'export',
    'name_create': 'create',
}

ARCHIVE_METHODS = frozenset({'action_archive', 'action_unarchive', 'toggle_active'})


PROTECTED_MENU_XMLIDS = (
    'base.menu_administration',
    'base.menu_management',
    'base.menu_users',
    'button_access_manager.menu_access_profile_root',
)

MENU_HIDE_TOKEN_PARAM = 'button_access_manager.menu_hide_token'
PROTECTED_MENU_PARAM = 'button_access_manager.protected_menu_xmlids'


def extra_allowlist(env):
    """Extra technical models from Settings (comma-separated ir.config_parameter)."""
    cache = getattr(env.cr, '_button_access_extra_allowlist', None)
    if cache is None:
        raw = ''
        try:
            raw = env['ir.config_parameter'].sudo().get_param(
                'button_access_manager.extra_allowlist', '') or ''
        except Exception:
            raw = ''
        cache = {part.strip() for part in raw.split(',') if part.strip()}
        env.cr._button_access_extra_allowlist = cache
    return cache


def extra_protected_menus(env):
    """Extra protected menu xmlids from Settings (comma-separated)."""
    cache = getattr(env.cr, '_button_access_extra_protected_menus', None)
    if cache is None:
        raw = ''
        try:
            raw = env['ir.config_parameter'].sudo().get_param(
                PROTECTED_MENU_PARAM, '') or ''
        except Exception:
            raw = ''
        cache = tuple(part.strip() for part in raw.split(',') if part.strip())
        env.cr._button_access_extra_protected_menus = cache
    return cache


def protected_menu_xmlids(env):
    return PROTECTED_MENU_XMLIDS + extra_protected_menus(env)


def protected_menu_ids(env):
    ids = set()
    for xmlid in protected_menu_xmlids(env):
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec is not None and getattr(rec, '_name', None) == 'ir.ui.menu' and rec.id:
            ids.add(rec.id)
    return ids


def is_framework_model(env, model_name):
    """Return True for technical / chatter / wizard models that global rules must not break."""
    if not model_name:
        return False
    if model_name in FRAMEWORK_MODELS or model_name in extra_allowlist(env):
        return True
    if any(model_name.startswith(prefix) for prefix in FRAMEWORK_PREFIXES):
        return True
    try:
        Model = env[model_name]
    except KeyError:
        return False
    return bool(getattr(Model, '_transient', False))
