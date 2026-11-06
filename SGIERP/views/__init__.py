from .auth import login_view, logout_view, forgot_password_view, verify_otp_view, reset_password_view, signup_view
from .dashboard import dashboard
from .inventory import (
    table_pdf_export, item_catalog, item_catalog_pdf, inventory_list, item_create, item_edit, item_detail, item_delete, add_stock, inventory_entry_delete,
    stock_move_view, completed_stock, rejected_stock, stock_history, item_groups, process_wise_stock, assignee_wise_stock, process_history, assignee_history,
)
from .machines import machine_list, machine_create, machine_edit, machine_detail, machine_bom_export, machine_delete
from .dispatch import dispatch_list, dispatch_create, dispatch_detail, dispatch_challan, dispatch_delete
from .challan import challan_list, challan_create, challan_detail, challan_print
from .settings import settings_view, process_create_edit, process_delete, user_list, user_create_edit, assignee_create_edit, assignee_delete, save_erp_config, change_delete_passcode
from .common import error_view, custom_404, custom_500, custom_403

__all__ = [
    'login_view', 'logout_view', 'forgot_password_view', 'verify_otp_view', 'reset_password_view', 'signup_view',
    'dashboard',
    'table_pdf_export', 'item_catalog', 'item_catalog_pdf', 'inventory_list', 'item_create', 'item_edit', 'item_detail', 'item_delete', 'add_stock', 'inventory_entry_delete', 'stock_move_view', 'completed_stock', 'rejected_stock', 'stock_history', 'item_groups', 'process_wise_stock', 'assignee_wise_stock', 'process_history', 'assignee_history',
    'machine_list', 'machine_create', 'machine_edit', 'machine_detail', 'machine_bom_export', 'machine_delete',
    'dispatch_list', 'dispatch_create', 'dispatch_detail', 'dispatch_challan', 'dispatch_delete',
    'challan_list', 'challan_create', 'challan_detail', 'challan_print',
    'settings_view', 'process_create_edit', 'process_delete', 'user_list', 'user_create_edit', 'assignee_create_edit', 'assignee_delete', 'save_erp_config', 'change_delete_passcode',
    'error_view',
]
