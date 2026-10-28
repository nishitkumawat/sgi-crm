"""SGIERP URL configuration — mounted at /sgi_erp/"""
from django.urls import path
from SGIERP.views import (
    login_view, logout_view, forgot_password_view, verify_otp_view, reset_password_view, signup_view,
    dashboard,
    item_catalog, inventory_list, item_create, item_edit, item_detail, item_delete, add_stock, inventory_entry_delete, stock_move_view, completed_stock, stock_history, item_groups, process_wise_stock, assignee_wise_stock,
    machine_list, machine_create, machine_edit, machine_detail,
    dispatch_list, dispatch_create, dispatch_detail, dispatch_challan,
    challan_list, challan_create, challan_detail, challan_print,
    settings_view, process_create_edit, process_delete, user_list, user_create_edit, assignee_create_edit, assignee_delete,
    error_view,
)

app_name = 'sgierp'

urlpatterns = [
    # ---- Auth ----
    path('auth/login/', login_view, name='login'),
    path('auth/logout/', logout_view, name='logout'),
    path('auth/signup/', signup_view, name='signup'),
    path('auth/forgot-password/', forgot_password_view, name='forgot_password'),
    path('auth/verify-otp/', verify_otp_view, name='verify_otp'),
    path('auth/reset-password/', reset_password_view, name='reset_password'),

    # ---- Dashboard ----
    path('', dashboard, name='dashboard'),
    path('dashboard/', dashboard, name='dashboard_alt'),

    # ---- Inventory ----
    path('catalog/', item_catalog, name='item_catalog'),
    path('inventory/', inventory_list, name='inventory'),
    path('inventory/add/', add_stock, name='add_stock'),
    path('inventory/entry/<int:entry_id>/delete/', inventory_entry_delete, name='inventory_entry_delete'),
    path('catalog/add/', item_create, name='item_create'),
    path('catalog/item/<int:item_id>/', item_detail, name='item_detail'),
    path('catalog/item/<int:item_id>/edit/', item_edit, name='item_edit'),
    path('catalog/item/<int:item_id>/delete/', item_delete, name='item_delete'),
    path('inventory/move/', stock_move_view, name='stock_move'),
    path('inventory/completed/', completed_stock, name='completed_stock'),
    path('inventory/history/', stock_history, name='stock_history'),
    path('inventory/groups/', item_groups, name='item_groups'),
    path('inventory/by-process/', process_wise_stock, name='process_wise_stock'),
    path('inventory/by-assignee/', assignee_wise_stock, name='assignee_wise_stock'),

    # ---- Machines ----
    path('machines/', machine_list, name='machine_list'),
    path('machines/add/', machine_create, name='machine_create'),
    path('machines/<int:machine_id>/', machine_detail, name='machine_detail'),
    path('machines/<int:machine_id>/edit/', machine_edit, name='machine_edit'),

    # ---- Dispatch ----
    path('dispatch/', dispatch_list, name='dispatch_list'),
    path('dispatch/new/', dispatch_create, name='dispatch_create'),
    path('dispatch/<int:dispatch_id>/', dispatch_detail, name='dispatch_detail'),
    path('dispatch/<int:dispatch_id>/challan/', dispatch_challan, name='dispatch_challan'),

    # ---- Challans ----
    path('challans/', challan_list, name='challan_list'),
    path('challans/new/', challan_create, name='challan_create'),
    path('challans/<int:challan_id>/', challan_detail, name='challan_detail'),
    path('challans/<int:challan_id>/print/', challan_print, name='challan_print'),

    # ---- Admin / Settings ----
    path('settings/', settings_view, name='settings'),
    path('settings/processes/', settings_view, name='settings_processes'),
    path('settings/assignees/', settings_view, name='settings_assignees'),
    path('settings/users/', user_list, name='settings_users'),
    path('settings/process/add/', process_create_edit, name='process_create'),
    path('settings/process/<int:process_id>/edit/', process_create_edit, name='process_edit'),
    path('settings/process/<int:process_id>/delete/', process_delete, name='process_delete'),
    path('settings/users/add/', user_create_edit, name='user_create'),
    path('settings/users/<int:user_id>/edit/', user_create_edit, name='user_edit'),
    path('settings/assignee/add/', assignee_create_edit, name='assignee_create'),
    path('settings/assignee/<int:assignee_id>/edit/', assignee_create_edit, name='assignee_edit'),
    path('settings/assignee/<int:assignee_id>/delete/', assignee_delete, name='assignee_delete'),

    # ---- Error Handling ----
    path('error/<int:error_code>/', error_view, name='error'),
    path('error/', error_view, name='error_default'),
]
