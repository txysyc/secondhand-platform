from catalog.models import Category


def get_active_categories():
    return Category.objects.filter(is_active=True).order_by("id")
