{
    'name': 'Grain Canje Triangular',
    'summary': 'Gestión completa de contratos y aplicaciones de canje de granos (productor → acopio → proveedor)',
    'version': '16.0.1.0.0',
    'author': 'Marcos Hache Odoo',
    'license': 'LGPL-3',
    'application': False,
    'installable': True,
    'depends': ['account', 'product', 'mail', 'stock', 'base'],
    'data': [
        'views/res_company_view.xml',
        'views/res_config_settings_view.xml',

        'wizard/register_grain_lpg_wizard_view.xml',
        'wizard/register_grain_lsg_wizard_view.xml',
        'wizard/grain_netting_wizard_view.xml',

        'views/grain_liquidation_views.xml',
        'views/grain_liquidation_vendor_bill_fix.xml',
        'views/grain_liquidation_menu.xml',

        'views/account_move_out_invoice_canje.xml',
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/sequence_canje_contract.xml',
        'wizard/apply_grain_canje_view.xml',
        'views/grain_canje_contract_view.xml',
        'views/account_move_view.xml',
        'views/grain_canje_analysis_views.xml',
        'reports/report_grain_canje_contract.xml',
    ],
}
