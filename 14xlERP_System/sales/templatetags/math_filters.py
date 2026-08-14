from django import template

register = template.Library()


@register.filter(name='mul')
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (TypeError, ValueError):
        return 0
