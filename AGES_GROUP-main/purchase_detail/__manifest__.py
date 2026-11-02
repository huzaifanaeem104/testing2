{
    'name': 'Purchase Detail Report',
    'version': '18.0.1.0',
    'author': 'Ali Muiz',
    'license': 'LGPL-3',
    'category': 'Inventory',
    'summary': 'Purchase Detail Report',
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
        'views/purchase_detail_report_wizard_view.xml',
        'views/purchase_detail_report_menu.xml',

        # XLSX Report Action
        'views/purchase_detail_xml.xml',

        # HTML Preview Report
        'report/purchase_detail_report_html.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
