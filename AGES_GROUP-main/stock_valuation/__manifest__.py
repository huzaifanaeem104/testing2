{
    'name': 'Stock Valuation Report',
    'version': '18.0.1.0',
    'author': 'Ali Muiz',
    'license': 'LGPL-3',
    'category': 'Inventory',
    'summary': 'Stock Valuation Report',
    'depends': [
        'sale',
        'base',
        'sale_management',
        'contacts',
        'report_xlsx',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',

        # Wizard Form + Action + Menu
        'views/stock_valuation_report_wizard_view.xml',
        'views/stock_valuation_report_menu.xml',

        # XLSX Report Action
        'views/stock_valuation_xml.xml',

        # (Optional) If you ever add QWEB
        # 'views/branch_transfer_note_report_xml.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
