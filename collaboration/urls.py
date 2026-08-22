from django.urls import path

from . import views

app_name = 'collaboration'

urlpatterns = [
    path('my-work/', views.my_work, name='my_work'),

    path('tasks/', views.task_list, name='task_list'),
    path('tasks/assign/', views.task_create, name='task_create'),
    path('tasks/<int:pk>/complete/', views.task_complete, name='task_complete'),
    path('tasks/<int:pk>/cancel/', views.task_cancel, name='task_cancel'),

    path('meetings/', views.meeting_list, name='meeting_list'),
    path('meetings/call/', views.meeting_create, name='meeting_create'),
    path('meetings/<int:pk>/cancel/', views.meeting_cancel, name='meeting_cancel'),

    path('messages/', views.message_inbox, name='message_inbox'),
    path('messages/<int:user_id>/', views.conversation, name='conversation'),
]
