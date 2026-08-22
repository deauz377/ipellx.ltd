from django.urls import path
from . import stock_views, views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_overview, name='inventory_overview'),
    path('products/', views.product_list, name='product_list'),
    path('products/add/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('products/export/csv/', views.product_export_csv, name='product_export_csv'),
    path('products/import/csv/', views.product_import_csv, name='product_import_csv'),
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/add/', views.supplier_create, name='supplier_create'),

    # --- Stock control -----------------------------------------------------
    path('stock/', stock_views.command_centre, name='command_centre'),
    path('stock/movements/', stock_views.movement_history, name='movement_history'),
    path('stock/by-location/', stock_views.stock_by_location, name='stock_by_location'),

    path('stock/locations/', stock_views.location_list, name='location_list'),
    path('stock/locations/add/', stock_views.location_create, name='location_create'),
    path('stock/locations/<int:pk>/edit/', stock_views.location_edit, name='location_edit'),

    path('stock/receipts/', stock_views.receipt_list, name='receipt_list'),
    path('stock/receipts/new/', stock_views.receipt_create, name='receipt_create'),
    path('stock/receipts/<int:pk>/', stock_views.receipt_detail, name='receipt_detail'),
    path('stock/receipts/<int:pk>/confirm/', stock_views.receipt_confirm, name='receipt_confirm'),
    path('stock/receipts/<int:pk>/cancel/', stock_views.receipt_cancel, name='receipt_cancel'),

    path('stock/transfers/', stock_views.transfer_list, name='transfer_list'),
    path('stock/transfers/new/', stock_views.transfer_create, name='transfer_create'),
    path('stock/transfers/<int:pk>/<str:action>/', stock_views.transfer_action, name='transfer_action'),

    path('stock/counts/', stock_views.count_list, name='count_list'),
    path('stock/counts/start/', stock_views.count_start, name='count_start'),
    path('stock/counts/<int:pk>/', stock_views.count_detail, name='count_detail'),
    path('stock/counts/<int:pk>/<str:action>/', stock_views.count_action, name='count_action'),
]
