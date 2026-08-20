from django.urls import path, reverse_lazy
from django.contrib.auth.views import (
    LoginView, LogoutView,
    PasswordResetView, PasswordResetDoneView,
    PasswordResetConfirmView, PasswordResetCompleteView,
)
from . import views
from .forms import RoleAwareLoginForm

app_name = 'core'

urlpatterns = [
    path('login/', LoginView.as_view(template_name='core/login.html', authentication_form=RoleAwareLoginForm), name='login'),
    path('signup/', views.signup, name='signup'),
    path('signup/check-email/', views.signup_check_email, name='signup_check_email'),
    path('signup/verify/<uidb64>/<token>/', views.verify_email, name='verify_email'),
    path('signup/resend-verification/', views.resend_verification, name='resend_verification'),
    path('subscribe/', views.subscribe, name='subscribe'),
    path('logout/', LogoutView.as_view(next_page='core:login'), name='logout'),
    path('account/', views.account_settings, name='account_settings'),

    path(
        'password-reset/',
        PasswordResetView.as_view(
            template_name='core/password_reset.html',
            email_template_name='core/password_reset_email.html',
            subject_template_name='core/password_reset_subject.txt',
            success_url=reverse_lazy('core:password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        PasswordResetDoneView.as_view(template_name='core/password_reset_done.html'),
        name='password_reset_done',
    ),
    path(
        'password-reset/confirm/<uidb64>/<token>/',
        PasswordResetConfirmView.as_view(
            template_name='core/password_reset_confirm.html',
            success_url=reverse_lazy('core:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'password-reset/complete/',
        PasswordResetCompleteView.as_view(template_name='core/password_reset_complete.html'),
        name='password_reset_complete',
    ),
]
