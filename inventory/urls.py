from django.urls import path
from . import views

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
]
