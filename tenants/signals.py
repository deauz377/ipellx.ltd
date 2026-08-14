from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import TenantModel
from .middleware import get_current_tenant


@receiver(pre_save)
def set_tenant(sender, instance, **kwargs):
    if isinstance(instance, TenantModel) and hasattr(instance, 'tenant') and not instance.tenant:
        tenant = get_current_tenant()
        if tenant:
            instance.tenant = tenant