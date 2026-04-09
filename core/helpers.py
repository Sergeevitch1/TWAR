# core/helpers.py
from core.permissions import ALL_PERMISSIONS, PermissionCategory, RolePermissionRecord

def get_permission_categories():
    """Возвращает список категорий прав для шаблонов"""
    return [{'code': cat.value[0], 'name': cat.value[1]} for cat in PermissionCategory]

def get_permissions_for_role(role: str):
    """Возвращает права для роли, сгруппированные по категориям"""
    return RolePermissionRecord.get_permissions_by_category(role)