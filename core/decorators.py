# core/decorators.py
from functools import wraps
from flask import flash, redirect, url_for, request
from flask_login import current_user
from core.permissions import user_has_permission, ALL_PERMISSIONS

def require_permission(permission_code: str, redirect_to: str = 'core.index', message: str = None):
    """Декоратор: требует наличие конкретного права"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login_steam', next=request.url))
            if not user_has_permission(current_user, permission_code):
                flash(message or f'❌ Недостаточно прав: {ALL_PERMISSIONS.get(permission_code, {}).name}', 'error')
                return redirect(url_for(redirect_to))
            return f(*args, **kwargs)
        return wrapped
    return decorator

def require_any_permission(permission_codes: list, **kwargs):
    """Требует хотя бы одно право из списка"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login_steam', next=request.url))
            if not any(user_has_permission(current_user, code) for code in permission_codes):
                flash(kwargs.get('message', '❌ Недостаточно прав'), 'error')
                return redirect(url_for(kwargs.get('redirect_to', 'core.index')))
            return f(*args, **kwargs)
        return wrapped
    return decorator

def require_all_permissions(permission_codes: list, **kwargs):
    """Требует все права из списка"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login_steam', next=request.url))
            if not all(user_has_permission(current_user, code) for code in permission_codes):
                flash(kwargs.get('message', '❌ Недостаточно прав'), 'error')
                return redirect(url_for(kwargs.get('redirect_to', 'core.index')))
            return f(*args, **kwargs)
        return wrapped
    return decorator