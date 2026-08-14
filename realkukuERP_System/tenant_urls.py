from django.urls import path, include

urlpatterns = [
    path('', include('dashboard.urls')),
    path('inventory/', include('inventory.urls')),
    path('sales/', include('sales.urls')),
    path('customers/', include('customers.urls')),
    path('expenses/', include('expenses.urls')),
    path('chama/', include('chama.urls')),
]