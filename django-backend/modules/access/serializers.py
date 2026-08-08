# ===================== APPLICATION LAYER: serializers (DTOs) =====================
# Only the navigation catalogue is serialized over the API now. Role and
# permission rows are written by `sync_catalogue` / `seed_demo` / the Django
# admin, never by a DRF endpoint.
from rest_framework import serializers

from .models import Form, ModuleGroup


class FormSerializer(serializers.ModelSerializer):
    class Meta:
        model = Form
        fields = ["id", "code", "name", "icon", "route", "sort_order", "is_active"]


class ModuleGroupSerializer(serializers.ModelSerializer):
    forms = FormSerializer(many=True, read_only=True)

    class Meta:
        model = ModuleGroup
        fields = ["id", "code", "name", "icon", "sort_order", "forms"]
