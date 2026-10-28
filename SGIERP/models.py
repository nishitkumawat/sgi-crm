from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import random
import string


# ============================================================
# MANUFACTURING PROCESS
# ============================================================
class Process(models.Model):
    """Configurable manufacturing processes (Raw Stock, Cutting, CNC, Completed, etc.)"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    is_completed_process = models.BooleanField(
        default=False,
        help_text="Mark this as the special 'Completed' process. Only one process should have this flag."
    )
    order = models.PositiveIntegerField(default=0, help_text="Display order in process flow")
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sgi_processes_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sgi_process'
        verbose_name = 'Manufacturing Process'
        verbose_name_plural = 'Manufacturing Processes'
        ordering = ['order', 'name']
        indexes = [
            models.Index(fields=['order'], name='sgi_process_order_idx'),
            models.Index(fields=['is_active'], name='sgi_process_is_active_idx'),
            models.Index(fields=['is_completed_process'], name='sgi_process_is_completed_idx'),
        ]

    def __str__(self):
        return self.name


# ============================================================
# INVENTORY ITEM (Master)
# ============================================================
class Item(models.Model):
    """Master record for each inventory item type."""
    UNIT_CHOICES = [
        ('pcs', 'Pieces'),
        ('kg', 'Kilograms'),
        ('m', 'Meters'),
        ('mtr', 'Meters'),
        ('mt', 'Metric Ton'),
        ('lt', 'Litres'),
        ('l', 'Liters'),
        ('ml', 'Milliliters'),
        ('gm', 'Grams'),
        ('ton', 'Ton'),
        ('nos', 'Numbers'),
        ('sets', 'Sets'),
        ('boxes', 'Boxes'),
        ('packs', 'Packs'),
        ('rolls', 'Rolls'),
        ('sqft', 'Square Feet'),
        ('sqm', 'Square Meters'),
        ('bundle', 'Bundle'),
        ('bag', 'Bag'),
        ('dozen', 'Dozen'),
        ('pair', 'Pair'),
    ]

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=100, blank=True, default='')
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='pcs')
    image = models.ImageField(upload_to='sgierp/items/', null=True, blank=True)
    min_stock_level = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sgi_items_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sgi_item'
        verbose_name = 'Inventory Item'
        verbose_name_plural = 'Inventory Items'
        ordering = ['code']
        indexes = [
            models.Index(fields=['code'], name='sgi_item_code_idx'),
            models.Index(fields=['is_active'], name='sgi_item_is_active_idx'),
            models.Index(fields=['category'], name='sgi_item_category_idx'),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def total_quantity(self):
        """Total quantity across all process entries."""
        from django.db.models import Sum
        result = self.process_entries.aggregate(total=Sum('quantity'))
        return result['total'] or 0

    def completed_quantity(self):
        """Total quantity in Completed process."""
        from django.db.models import Sum
        completed = Process.objects.filter(is_completed_process=True).first()
        if not completed:
            return 0
        result = self.process_entries.filter(
            process=completed
        ).aggregate(total=Sum('quantity'))
        return result['total'] or 0

    def in_production_quantity(self):
        """Total quantity in non-Completed processes."""
        from django.db.models import Sum
        completed = Process.objects.filter(is_completed_process=True).first()
        qs = self.process_entries.all()
        if completed:
            qs = qs.exclude(process=completed)
        result = qs.aggregate(total=Sum('quantity'))
        return result['total'] or 0


# ============================================================
# ASSIGNEE (Workers / Staff — separate from auth users)
# ============================================================
class Assignee(models.Model):
    """Workers or staff members who can be assigned stock entries / tasks.
    Not an auth user — just a name + optional metadata."""
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True, default='')
    department = models.CharField(max_length=100, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sgi_assignees_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sgi_assignee'
        verbose_name = 'Assignee'
        verbose_name_plural = 'Assignees'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name'], name='sgi_assignee_name_idx'),
            models.Index(fields=['is_active'], name='sgi_assignee_is_active_idx'),
        ]

    def __str__(self):
        return self.name


# ============================================================
# ITEM PROCESS (Simple inventory tracking per process)
# ============================================================
class ItemProcess(models.Model):
    """
    Simple model to track item quantities per process.
    One record per item+process combination.
    """
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='process_entries')
    process = models.ForeignKey(Process, on_delete=models.PROTECT, related_name='item_entries')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    assigned_to = models.ForeignKey(
        Assignee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_items'
    )
    assigned_at = models.DateTimeField(null=True, blank=True, help_text="When this entry was last assigned")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sgi_item_process'
        verbose_name = 'Item Process'
        verbose_name_plural = 'Item Processes'
        unique_together = ['item', 'process']
        ordering = ['item__code', 'process__order', 'process__name']
        indexes = [
            models.Index(fields=['item', 'process'], name='sgi_item_process_idx'),
            models.Index(fields=['quantity'], name='sgi_item_process_qty_idx'),
            models.Index(fields=['updated_at'], name='sgi_item_process_updated_idx'),
        ]

    def __str__(self):
        return f"{self.item.code} | {self.quantity} {self.item.unit} in {self.process.name}"


# ============================================================
# STOCK HISTORY (Track all stock movements)
# ============================================================
class StockHistory(models.Model):
    """History of all stock movements and assignments."""
    MOVEMENT_TYPE_CHOICES = [
        ('add', 'Add Stock'),
        ('move', 'Move Stock'),
        ('convert', 'Convert Item'),
        ('dispatch', 'Dispatch Consumption'),
        ('adjustment', 'Manual Adjustment'),
    ]

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='stock_history')
    to_item = models.ForeignKey(
        Item, on_delete=models.PROTECT, null=True, blank=True,
        related_name='stock_history_as_target', help_text="Target item for conversions"
    )
    from_process = models.ForeignKey(
        Process, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='history_from', help_text="Source process (null for initial stock)"
    )
    to_process = models.ForeignKey(
        Process, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='history_to', help_text="Destination process (null for conversions)"
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE_CHOICES, default='move')
    
    # Assignment tracking
    from_assignee = models.ForeignKey(
        Assignee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='history_from_assigned', help_text="Assignee at source"
    )
    to_assignee = models.ForeignKey(
        Assignee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='history_to_assigned', help_text="Assignee at destination"
    )
    
    # Snapshot fields
    item_code_snapshot = models.CharField(max_length=50)
    item_name_snapshot = models.CharField(max_length=200)
    to_item_code_snapshot = models.CharField(max_length=50, blank=True, default='')
    to_item_name_snapshot = models.CharField(max_length=200, blank=True, default='')
    unit_snapshot = models.CharField(max_length=10)
    from_process_name = models.CharField(max_length=100, blank=True, default='')
    to_process_name = models.CharField(max_length=100, blank=True, default='')
    from_assignee_name = models.CharField(max_length=200, blank=True, default='')
    to_assignee_name = models.CharField(max_length=200, blank=True, default='')
    
    # Metadata
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements_performed'
    )
    remarks = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sgi_stock_history'
        verbose_name = 'Stock History'
        verbose_name_plural = 'Stock History'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at'], name='sgi_stock_hist_created_idx'),
            models.Index(fields=['item'], name='sgi_stock_hist_item_idx'),
            models.Index(fields=['from_process'], name='sgi_stock_hist_from_idx'),
            models.Index(fields=['to_process'], name='sgi_stock_hist_to_idx'),
            models.Index(fields=['movement_type'], name='sgi_stock_hist_type_idx'),
        ]

    def __str__(self):
        return f"{self.movement_type}: {self.item_code_snapshot} ({self.quantity} {self.unit_snapshot}) from {self.from_process_name or 'Initial'} to {self.to_process_name}"


# ============================================================
# MACHINE MASTER
# ============================================================
class Machine(models.Model):
    """Master record for a machine product."""
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    image = models.ImageField(upload_to='sgierp/machines/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sgi_machines_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sgi_machine'
        verbose_name = 'Machine'
        verbose_name_plural = 'Machines'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


# ============================================================
# MACHINE BOM
# ============================================================
class MachineBOM(models.Model):
    """Bill of Materials — component requirements per machine."""
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='bom_items')
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='bom_entries')
    quantity_required = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'sgi_machine_bom'
        verbose_name = 'Machine BOM Entry'
        verbose_name_plural = 'Machine BOM Entries'
        unique_together = [['machine', 'item']]

    def __str__(self):
        return f"{self.machine.code}: {self.item.code} × {self.quantity_required}"


# ============================================================
# MACHINE DISPATCH
# ============================================================
class MachineDispatch(models.Model):
    """Dispatch header — records each dispatch transaction."""
    machine = models.ForeignKey(Machine, on_delete=models.PROTECT, related_name='dispatches')
    machine_count = models.PositiveIntegerField(default=1)
    customer_name = models.CharField(max_length=200, blank=True, default='')
    dispatch_date = models.DateTimeField(default=timezone.now)
    invoice_reference = models.CharField(max_length=100, blank=True, default='')
    dispatched_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sgi_dispatches'
    )
    remarks = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sgi_machine_dispatch'
        verbose_name = 'Machine Dispatch'
        verbose_name_plural = 'Machine Dispatches'
        ordering = ['-dispatch_date']

    def __str__(self):
        return f"Dispatch #{self.id}: {self.machine_count}× {self.machine.name} on {self.dispatch_date.date()}"


# ============================================================
# DISPATCH COMPONENT (per-item consumption record)
# ============================================================
class DispatchComponent(models.Model):
    """
    Records which item was consumed, from which process entry, in a dispatch.
    Snapshotted at dispatch time so later BOM edits don't alter history.
    """
    dispatch = models.ForeignKey(MachineDispatch, on_delete=models.CASCADE, related_name='components')
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='dispatch_components')
    source_entry = models.ForeignKey(
        ItemProcess, on_delete=models.PROTECT, related_name='dispatch_consumptions',
        null=True, blank=True
    )
    quantity_consumed = models.DecimalField(max_digits=12, decimal_places=2)
    # Snapshot fields
    item_code_snapshot = models.CharField(max_length=50)
    item_name_snapshot = models.CharField(max_length=200)
    unit_snapshot = models.CharField(max_length=10)

    class Meta:
        db_table = 'sgi_dispatch_component'
        verbose_name = 'Dispatch Component'
        verbose_name_plural = 'Dispatch Components'

    def __str__(self):
        return f"Dispatch #{self.dispatch_id}: {self.item_code_snapshot} × {self.quantity_consumed}"


# ============================================================
# OTP TOKEN (for password reset)
# ============================================================
class OTPToken(models.Model):
    """6-digit OTP for password reset. Single-use, 5-minute expiry."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sgi_otp_tokens')
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempt_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'sgi_otp_token'
        verbose_name = 'OTP Token'
        verbose_name_plural = 'OTP Tokens'

    def __str__(self):
        return f"OTP for {self.user.username} (used={self.is_used})"

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at and self.attempt_count < 5

    @classmethod
    def generate_for_user(cls, user):
        """Invalidate previous OTPs and create a fresh one."""
        cls.objects.filter(user=user, is_used=False).update(is_used=True)
        otp_value = ''.join(random.choices(string.digits, k=6))
        expires = timezone.now() + timezone.timedelta(minutes=5)
        return cls.objects.create(user=user, otp=otp_value, expires_at=expires)


# ============================================================
# CHALLAN (Material Transfer Document)
# ============================================================
class Challan(models.Model):
    """Challan for material transfer to external parties."""
    CHALLAN_TYPE_CHOICES = [
        ('outward', 'Outward - Sending Material'),
        ('inward', 'Inward - Receiving Material'),
    ]

    challan_number = models.CharField(max_length=50, unique=True)
    challan_type = models.CharField(max_length=20, choices=CHALLAN_TYPE_CHOICES, default='outward')
    party_name = models.CharField(max_length=200, help_text="Company/Party name")
    party_address = models.TextField(blank=True, default='')
    party_contact = models.CharField(max_length=100, blank=True, default='')
    assignee = models.ForeignKey(
        Assignee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='challans'
    )
    date = models.DateField()
    remarks = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='challans_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sgi_challan'
        verbose_name = 'Challan'
        verbose_name_plural = 'Challans'
        ordering = ['-date', '-challan_number']

    def __str__(self):
        return f"{self.challan_number} - {self.party_name}"


class ChallanItem(models.Model):
    """Items included in a challan."""
    challan = models.ForeignKey(Challan, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='challan_items')
    process = models.ForeignKey(
        'Process', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='challan_items'
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=10)
    remarks = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        db_table = 'sgi_challan_item'
        verbose_name = 'Challan Item'
        verbose_name_plural = 'Challan Items'

    def __str__(self):
        return f"{self.item.code} × {self.quantity} {self.unit}"


# ============================================================
# ERP USER PROFILE (extends Django User)
# ============================================================
class ERPUserProfile(models.Model):
    """
    Extra ERP-specific fields for Django Users.
    We extend Django's built-in User instead of creating a separate table.
    """
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('operator', 'Operator'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='erp_profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='operator')
    department = models.CharField(max_length=100, blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    is_erp_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sgi_erp_user_profile'
        verbose_name = 'ERP User Profile'
        verbose_name_plural = 'ERP User Profiles'

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def display_name(self):
        full = self.user.get_full_name()
        return full if full else self.user.username
