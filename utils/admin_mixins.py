"""Shared Django admin helpers."""


class NoEditAdminMixin:
    """Let staff view and delete patient records in the admin, but never create or edit them.

    Delete stays allowed so removing a user can cascade to their health data.
    """

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
