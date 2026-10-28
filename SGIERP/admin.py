from django.contrib import admin
from .models import (
    Process, Item, ItemProcess,
    Machine, MachineBOM, MachineDispatch, DispatchComponent,
    OTPToken, ERPUserProfile
)


@admin.register(Process)
class ProcessAdmin(admin.ModelAdmin):
    list_display = ['name', 'order', 'is_active', 'is_completed_process']
    list_editable = ['order', 'is_active']
    search_fields = ['name']


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'category', 'unit', 'is_active', 'created_at']
    search_fields = ['code', 'name', 'category']
    list_filter = ['is_active', 'unit', 'category']


@admin.register(ItemProcess)
class ItemProcessAdmin(admin.ModelAdmin):
    list_display = ['item', 'process', 'quantity', 'assigned_to', 'updated_at']
    list_filter = ['process']
    search_fields = ['item__code', 'item__name']
    raw_id_fields = ['item', 'process', 'assigned_to']


class MachineBOMInline(admin.TabularInline):
    model = MachineBOM
    extra = 1
    raw_id_fields = ['item']


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_active', 'created_at']
    search_fields = ['code', 'name']
    inlines = [MachineBOMInline]


class DispatchComponentInline(admin.TabularInline):
    model = DispatchComponent
    extra = 0
    readonly_fields = ['item', 'source_entry', 'quantity_consumed',
                       'item_code_snapshot', 'item_name_snapshot']


@admin.register(MachineDispatch)
class MachineDispatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'machine', 'machine_count', 'customer_name', 'dispatch_date', 'dispatched_by']
    list_filter = ['machine', 'dispatch_date']
    inlines = [DispatchComponentInline]
    readonly_fields = ['created_at']


@admin.register(ERPUserProfile)
class ERPUserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'department', 'is_erp_active']
    list_filter = ['role', 'is_erp_active']
    search_fields = ['user__username', 'user__email', 'user__first_name']
