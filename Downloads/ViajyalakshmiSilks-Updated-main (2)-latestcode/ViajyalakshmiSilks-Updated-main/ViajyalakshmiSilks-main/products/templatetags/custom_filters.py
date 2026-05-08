from django import template

register = template.Library()

@register.filter
def multiply(value, arg):
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return ''

@register.filter
def subtract(value, arg):
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def get_item(dictionary, key):
    if not dictionary:
        return None
    return dictionary.get(key)
@register.filter
def calculate_tax(value, tax_percentage):
    try:
        return round(float(value) * float(tax_percentage) / 100, 2)
    except (ValueError, TypeError):
        return 0

@register.filter
def calculate_total_with_tax(value, tax_percentage):
    try:
        tax = float(value) * float(tax_percentage) / 100
        return round(float(value) + tax, 2)
    except (ValueError, TypeError):
        return value

@register.filter
def extract_tax(value, tax_percentage):
    try:
        val = float(value)
        pct = float(tax_percentage)
        if pct > 0:
            tax = val - (val / (1 + (pct / 100)))
            return round(tax, 2)
        return 0
    except (ValueError, TypeError):
        return 0
