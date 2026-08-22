"""Screens for the stock workflows.

Views never write stock themselves -- they collect input, then hand off to
inventory.services / workflow_services, which own the ledger and the audit
trail. A view that touched quantity directly would be the one place the
history could go missing.
"""
from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tenants.decorators import role_required

from .models import (
    GoodsReceipt, Location, Product, StockCount, StockCountLine,
    StockLevel, StockMovement, StockTransfer,
)
from .services import (
    StockError, expiring_batches, low_stock_queryset, out_of_stock_queryset,
    stock_products, stock_value,
)
from .stock_forms import (
    GoodsReceiptForm, GoodsReceiptLineForm, LocationForm, StockCountRejectForm,
    StockCountStartForm, StockTransferForm,
)
from .workflow_services import (
    approve_count, approve_transfer, cancel_receipt, cancel_transfer,
    confirm_receipt, dispatch_transfer, receive_transfer, reject_count,
    start_count, submit_count,
)

ZERO = Decimal('0')

# Who may move stock. INVENTORY_MANAGER is the role this module exists for.
STOCK_ROLES = ('OWNER', 'MANAGER', 'INVENTORY_MANAGER')
# Read-only additionally includes the Accountant, who needs stock valuation
# for the books without being able to change quantities.
VIEW_ROLES = STOCK_ROLES + ('ACCOUNTANT',)

EXPIRY_HORIZON_DAYS = 30


# ---------------------------------------------------------------------------
# Command Centre
# ---------------------------------------------------------------------------

@role_required(*VIEW_ROLES)
def command_centre(request):
    """One screen answering "what needs my attention in the store today"."""
    tenant = request.user.tenant
    today = timezone.localdate()

    products = stock_products(tenant)
    total_products = products.count()

    # These three come from inventory.services so the Owner's dashboard, the
    # Inventory Overview and this screen cannot drift apart.
    low_stock = list(low_stock_queryset(tenant))
    out_of_stock = list(out_of_stock_queryset(tenant))
    total_stock_value = stock_value(tenant)

    expiring = expiring_batches(tenant, within_days=EXPIRY_HORIZON_DAYS)
    expired, expiring_soon = [], []
    for level in expiring:
        (expired if level.batch.expiry_date < today else expiring_soon).append(level)

    movements_today = StockMovement.objects.filter(tenant=tenant, created_at__date=today)
    received_today = movements_today.filter(
        movement_type__in=[StockMovement.RECEIVE, StockMovement.OPENING],
    ).aggregate(t=Sum('quantity_delta'))['t'] or ZERO
    sold_today = movements_today.filter(
        movement_type=StockMovement.SALE,
    ).aggregate(t=Sum('quantity_delta'))['t'] or ZERO

    pending_transfers = StockTransfer.objects.filter(
        tenant=tenant, status__in=StockTransfer.OPEN_STATUSES,
    ).select_related('product', 'source', 'destination')
    pending_receipts = GoodsReceipt.objects.filter(
        tenant=tenant, status=GoodsReceipt.DRAFT,
    ).select_related('supplier', 'location')
    open_counts = StockCount.objects.filter(
        tenant=tenant, status__in=[StockCount.DRAFT, StockCount.SUBMITTED],
    ).select_related('location')

    # Movement volume over the last 30 days tells fast from slow far better
    # than current stock level does.
    window_start = today - timezone.timedelta(days=30)
    sold_by_product = {
        row['product']: abs(row['t'])
        for row in StockMovement.objects.filter(
            tenant=tenant, movement_type=StockMovement.SALE, created_at__date__gte=window_start,
        ).values('product').annotate(t=Sum('quantity_delta'))
    }
    ranked = sorted(products, key=lambda p: sold_by_product.get(p.pk, ZERO), reverse=True)
    fast_moving = [p for p in ranked if sold_by_product.get(p.pk, ZERO) > ZERO][:5]
    slow_moving = [p for p in ranked if sold_by_product.get(p.pk, ZERO) == ZERO][:5]

    return render(request, 'inventory/command_centre.html', {
        'today': today,
        'total_products': total_products,
        'stock_value': total_stock_value,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'healthy_count': total_products - len(low_stock) - len(out_of_stock),
        'expired': expired,
        'expiring_soon': expiring_soon,
        'expiry_horizon': EXPIRY_HORIZON_DAYS,
        'received_today': received_today,
        'sold_today': abs(sold_today),
        'pending_transfers': pending_transfers,
        'pending_receipts': pending_receipts,
        'open_counts': open_counts,
        'fast_moving': [(p, sold_by_product.get(p.pk, ZERO)) for p in fast_moving],
        'slow_moving': slow_moving,
        'recent_movements': StockMovement.objects.filter(tenant=tenant).select_related(
            'product', 'location', 'user')[:12],
        'locations': Location.objects.filter(tenant=tenant, is_active=True),
        'can_edit': request.user.has_role(*STOCK_ROLES),
    })


@role_required(*VIEW_ROLES)
def movement_history(request):
    """The audit trail, filterable. Read-only by design: history is corrected
    by recording a compensating movement, never by editing the past."""
    tenant = request.user.tenant
    movements = StockMovement.objects.filter(tenant=tenant).select_related(
        'product', 'location', 'user', 'batch')

    product_id = request.GET.get('product')
    location_id = request.GET.get('location')
    movement_type = request.GET.get('type')
    start = request.GET.get('start')
    end = request.GET.get('end')

    if product_id:
        movements = movements.filter(product_id=product_id)
    if location_id:
        movements = movements.filter(location_id=location_id)
    if movement_type:
        movements = movements.filter(movement_type=movement_type)
    if start:
        movements = movements.filter(created_at__date__gte=start)
    if end:
        movements = movements.filter(created_at__date__lte=end)

    return render(request, 'inventory/movement_history.html', {
        'movements': movements[:300],
        'products': Product.objects.filter(tenant=tenant).order_by('name'),
        'locations': Location.objects.filter(tenant=tenant).order_by('name'),
        'movement_types': StockMovement.MOVEMENT_TYPE_CHOICES,
        'selected': {
            'product': product_id, 'location': location_id,
            'type': movement_type, 'start': start, 'end': end,
        },
    })


@role_required(*VIEW_ROLES)
def stock_by_location(request):
    """Where everything actually is -- the view multi-location exists for."""
    tenant = request.user.tenant
    levels = StockLevel.objects.filter(
        tenant=tenant, quantity__gt=ZERO,
    ).select_related('product', 'location', 'batch').order_by('location__name', 'product__name')

    location_id = request.GET.get('location')
    if location_id:
        levels = levels.filter(location_id=location_id)

    return render(request, 'inventory/stock_by_location.html', {
        'levels': levels,
        'locations': Location.objects.filter(tenant=tenant, is_active=True).order_by('name'),
        'selected_location': location_id,
    })


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

@role_required(*STOCK_ROLES)
def location_list(request):
    tenant = request.user.tenant
    locations = Location.objects.filter(tenant=tenant).order_by('-is_default', 'name')
    for location in locations:
        location.on_hand = StockLevel.objects.filter(
            location=location).aggregate(t=Sum('quantity'))['t'] or ZERO
    return render(request, 'inventory/location_list.html', {'locations': locations})


@role_required(*STOCK_ROLES)
def location_create(request):
    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid():
            location = form.save(commit=False)
            location.tenant = request.user.tenant
            location.save()
            messages.success(request, f'Location "{location.name}" added.')
            return redirect('inventory:location_list')
    else:
        form = LocationForm()
    return render(request, 'inventory/location_form.html', {'form': form, 'title': 'Add Location'})


@role_required(*STOCK_ROLES)
def location_edit(request, pk):
    location = get_object_or_404(Location, pk=pk)
    if request.method == 'POST':
        form = LocationForm(request.POST, instance=location)
        if form.is_valid():
            form.save()
            messages.success(request, 'Location updated.')
            return redirect('inventory:location_list')
    else:
        form = LocationForm(instance=location)
    return render(request, 'inventory/location_form.html',
                  {'form': form, 'title': 'Edit Location', 'location': location})


# ---------------------------------------------------------------------------
# Receiving
# ---------------------------------------------------------------------------

@role_required(*VIEW_ROLES)
def receipt_list(request):
    receipts = GoodsReceipt.objects.filter(
        tenant=request.user.tenant,
    ).select_related('supplier', 'location', 'received_by')
    return render(request, 'inventory/receipt_list.html', {
        'receipts': receipts, 'can_edit': request.user.has_role(*STOCK_ROLES),
    })


@role_required(*STOCK_ROLES)
def receipt_create(request):
    tenant = request.user.tenant
    if request.method == 'POST':
        form = GoodsReceiptForm(request.POST, tenant=tenant)
        if form.is_valid():
            receipt = form.save(commit=False)
            receipt.tenant = tenant
            receipt.received_by = request.user
            receipt.save()
            messages.success(request, 'Delivery started. Add what arrived, then confirm it.')
            return redirect('inventory:receipt_detail', pk=receipt.pk)
    else:
        form = GoodsReceiptForm(tenant=tenant)
    return render(request, 'inventory/receipt_form.html', {'form': form})


@role_required(*VIEW_ROLES)
def receipt_detail(request, pk):
    receipt = get_object_or_404(GoodsReceipt, pk=pk)
    tenant = request.user.tenant
    can_edit = request.user.has_role(*STOCK_ROLES)

    line_form = GoodsReceiptLineForm(tenant=tenant)
    if request.method == 'POST' and can_edit:
        if not receipt.is_editable:
            messages.error(request, 'This delivery has already been dealt with.')
            return redirect('inventory:receipt_detail', pk=receipt.pk)
        line_form = GoodsReceiptLineForm(request.POST, tenant=tenant)
        if line_form.is_valid():
            line = line_form.save(commit=False)
            line.tenant = tenant
            line.receipt = receipt
            line.save()
            messages.success(request, 'Line added.')
            return redirect('inventory:receipt_detail', pk=receipt.pk)

    return render(request, 'inventory/receipt_detail.html', {
        'receipt': receipt,
        'lines': receipt.lines.select_related('product'),
        'line_form': line_form,
        'can_edit': can_edit,
    })


@role_required(*STOCK_ROLES)
def receipt_confirm(request, pk):
    receipt = get_object_or_404(GoodsReceipt, pk=pk)
    if request.method == 'POST':
        try:
            confirm_receipt(receipt, user=request.user)
        except StockError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, 'Delivery confirmed and stock updated.')
        return redirect('inventory:receipt_detail', pk=receipt.pk)
    return render(request, 'inventory/receipt_confirm.html', {
        'receipt': receipt, 'lines': receipt.lines.select_related('product'),
    })


@role_required(*STOCK_ROLES)
def receipt_cancel(request, pk):
    receipt = get_object_or_404(GoodsReceipt, pk=pk)
    if request.method == 'POST':
        try:
            cancel_receipt(receipt, user=request.user)
        except StockError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, 'Delivery cancelled.')
        return redirect('inventory:receipt_list')
    return render(request, 'inventory/receipt_cancel.html', {'receipt': receipt})


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------

@role_required(*VIEW_ROLES)
def transfer_list(request):
    transfers = StockTransfer.objects.filter(
        tenant=request.user.tenant,
    ).select_related('product', 'source', 'destination', 'requested_by')
    return render(request, 'inventory/transfer_list.html', {
        'transfers': transfers, 'can_edit': request.user.has_role(*STOCK_ROLES),
    })


@role_required(*STOCK_ROLES)
def transfer_create(request):
    tenant = request.user.tenant
    if request.method == 'POST':
        form = StockTransferForm(request.POST, tenant=tenant)
        if form.is_valid():
            transfer = form.save(commit=False)
            transfer.tenant = tenant
            transfer.requested_by = request.user
            transfer.save()
            messages.success(request, 'Transfer requested. It moves stock once dispatched.')
            return redirect('inventory:transfer_list')
    else:
        form = StockTransferForm(tenant=tenant)
    return render(request, 'inventory/transfer_form.html', {'form': form})


@role_required(*STOCK_ROLES)
def transfer_action(request, pk, action):
    """Approve / dispatch / receive / cancel, each guarded by the service.

    POST-only: these move real stock, and a link a browser could prefetch
    must never be able to dispatch a lorry.
    """
    transfer = get_object_or_404(StockTransfer, pk=pk)
    if request.method != 'POST':
        return redirect('inventory:transfer_list')

    handlers = {
        'approve': (approve_transfer, 'Transfer approved.'),
        'dispatch': (dispatch_transfer, 'Dispatched. Stock has left the source.'),
        'receive': (receive_transfer, 'Received. Stock is now at the destination.'),
    }
    try:
        if action == 'cancel':
            cancel_transfer(transfer, user=request.user,
                            reason=request.POST.get('reason', '').strip())
            messages.success(request, 'Transfer cancelled.')
        elif action in handlers:
            handler, note = handlers[action]
            handler(transfer, user=request.user)
            messages.success(request, note)
        else:
            messages.error(request, 'Unknown action.')
    except StockError as exc:
        messages.error(request, str(exc))
    return redirect('inventory:transfer_list')


# ---------------------------------------------------------------------------
# Stock counts
# ---------------------------------------------------------------------------

@role_required(*VIEW_ROLES)
def count_list(request):
    counts = StockCount.objects.filter(
        tenant=request.user.tenant,
    ).select_related('location', 'started_by')
    return render(request, 'inventory/count_list.html', {
        'counts': counts, 'can_edit': request.user.has_role(*STOCK_ROLES),
    })


@role_required(*STOCK_ROLES)
def count_start(request):
    tenant = request.user.tenant
    if request.method == 'POST':
        form = StockCountStartForm(request.POST, tenant=tenant)
        if form.is_valid():
            count = start_count(
                tenant=tenant, location=form.cleaned_data['location'], user=request.user,
            )
            messages.success(request, 'Count started. Enter what you actually find on the shelf.')
            return redirect('inventory:count_detail', pk=count.pk)
    else:
        form = StockCountStartForm(tenant=tenant)
    return render(request, 'inventory/count_start.html', {'form': form})


@role_required(*VIEW_ROLES)
def count_detail(request, pk):
    count = get_object_or_404(StockCount, pk=pk)
    can_edit = request.user.has_role(*STOCK_ROLES)

    if request.method == 'POST' and can_edit and count.is_editable:
        # Saves the whole sheet at once: a stock take is filled in as one pass
        # down the shelf, not one row at a time.
        for line in count.lines.all():
            raw = request.POST.get(f'physical_{line.pk}', '').strip()
            line.physical_quantity = Decimal(raw) if raw else None
            line.reason = request.POST.get(f'reason_{line.pk}', '')
            line.note = request.POST.get(f'note_{line.pk}', '')[:255]
            line.save(update_fields=['physical_quantity', 'reason', 'note'])
        messages.success(request, 'Count saved.')
        return redirect('inventory:count_detail', pk=count.pk)

    return render(request, 'inventory/count_detail.html', {
        'count': count,
        'lines': count.lines.select_related('product'),
        'reason_choices': StockCountLine.REASON_CHOICES,
        'can_edit': can_edit,
    })


@role_required(*STOCK_ROLES)
def count_action(request, pk, action):
    count = get_object_or_404(StockCount, pk=pk)
    if request.method != 'POST':
        return redirect('inventory:count_detail', pk=count.pk)
    try:
        if action == 'submit':
            submit_count(count, user=request.user)
            messages.success(request, 'Count submitted for approval.')
        elif action == 'approve':
            approve_count(count, user=request.user)
            messages.success(request, 'Count approved. Stock adjusted and recorded.')
        elif action == 'reject':
            form = StockCountRejectForm(request.POST)
            reason = form.cleaned_data['reason'] if form.is_valid() else 'Rejected'
            reject_count(count, user=request.user, reason=reason)
            messages.success(request, 'Count rejected. No stock was changed.')
        else:
            messages.error(request, 'Unknown action.')
    except StockError as exc:
        messages.error(request, str(exc))
    return redirect('inventory:count_detail', pk=count.pk)
