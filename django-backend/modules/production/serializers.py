# ===================== API LAYER: serializers =====================
# Validates the seed-import request. The result is a computed summary dict
# (imported / skipped / batches created), returned as-is by the view.

from rest_framework import serializers

from .models import SeedPlate


class SeedPlateSerializer(serializers.ModelSerializer):
    """MST_SeedPlate — the plate-name inventory master (Plate Master form)."""

    class Meta:
        model = SeedPlate
        fields = ["plate_id", "plate_name", "diameter", "is_active", "is_used", "is_released"]
        read_only_fields = ["plate_id", "is_used", "is_released"]


class BatchSerializer(serializers.Serializer):
    """A batch with its seed count — for the Batch Selection screen."""

    batch_id = serializers.UUIDField()
    batch_no = serializers.CharField(allow_null=True)
    seed_count = serializers.IntegerField()
    is_active = serializers.BooleanField()


class SeedImportRequestSerializer(serializers.Serializer):
    """The uploaded datasheet — Excel only (defence in depth; the UI also blocks
    non-Excel files before upload)."""

    file = serializers.FileField()

    def validate_file(self, f):
        if not f.name.lower().endswith((".xlsx", ".xls")):
            raise serializers.ValidationError("Only Excel files (.xlsx, .xls) are allowed.")
        return f
