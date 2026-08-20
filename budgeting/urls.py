from django.urls import path

from . import views

app_name = 'budgeting'

urlpatterns = [
    path('', views.budgeting_dashboard, name='dashboard'),
    path('budgets/', views.budget_list, name='budget_list'),
    path('budgets/add/', views.budget_create, name='budget_create'),
    path('budgets/<int:pk>/', views.budget_detail, name='budget_detail'),
    path('budgets/<int:pk>/edit/', views.budget_edit, name='budget_edit'),
    path('budgets/<int:pk>/delete/', views.budget_delete, name='budget_delete'),
    path('report/', views.budget_report, name='budget_report'),
    path('report/csv/', views.budget_report_csv, name='budget_report_csv'),
]
