from .auth import login_view, logout_view, forgot_password_view, verify_otp_view, reset_password_view, signup_view
from .dashboard import dashboard
from .inventory import (
    item_catalog, inventory_list, item_create, item_edit, item_detail, item_delete, add_stock, inventory_entry_delete,
    stock_move_view, completed_stock, stock_history, item_groups, process_wise_stock, assignee_wise_stock,
)
from .machines import machine_list, machine_create, machine_edit, machine_detail
from .dispatch import dispatch_list, dispatch_create, dispatch_detail, dispatch_challan
from .challan import challan_list, challan_create, challan_detail, challan_print
from .settings import settings_view, process_create_edit, process_delete, user_list, user_create_edit, assignee_create_edit, assignee_delete
from .common import error_view, custom_404, custom_500, custom_403

__all__ = [
    'login_view', 'logout_view', 'forgot_password_view', 'verify_otp_view', 'reset_password_view', 'signup_view',
    'dashboard',
    'item_catalog', 'inventory_list', 'item_create', 'item_edit', 'item_detail', 'item_delete', 'add_stock', 'inventory_entry_delete', 'stock_move_view', 'completed_stock', 'stock_history', 'item_groups', 'process_wise_stock', 'assignee_wise_stock',
    'machine_list', 'machine_create', 'machine_edit', 'machine_detail',
    'dispatch_list', 'dispatch_create', 'dispatch_detail', 'dispatch_challan',
    'challan_list', 'challan_create', 'challan_detail', 'challan_print',
    'settings_view', 'process_create_edit', 'process_delete', 'user_list', 'user_create_edit', 'assignee_create_edit', 'assignee_delete',
    'error_view',
]
