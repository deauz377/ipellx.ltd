from django.urls import path
from . import views

urlpatterns = [
    path('', views.overview, name='dashboard_overview'),
    path('search/', views.global_search, name='dashboard_search'),
    path('team/', views.team_activity, name='team_activity'),
    path('team/add/', views.add_team_member, name='team_add_member'),
]
