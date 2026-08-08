from django.contrib import admin

from .models import Form, ModuleGroup, Role, RoleFormPermission, UserRole


class FormInline(admin.TabularInline):
    model = Form
    extra = 0


@admin.register(ModuleGroup)
class ModuleGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "sort_order")
    inlines = [FormInline]


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "tenant_id", "is_system")


admin.site.register(Form)
admin.site.register(UserRole)
admin.site.register(RoleFormPermission)
