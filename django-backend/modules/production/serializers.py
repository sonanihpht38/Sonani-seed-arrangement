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

    def validate_plate_name(self, value):
        """A plate name must be unique, because the name IS the identifier.

        MST_SeedPlate carries no unique constraint on PlateName — it is an
        unmanaged table whose DDL we do not own — and PlateService.assign
        resolves a name with `get_or_create(plate_name=...)`. Two rows sharing a
        name therefore make that call raise MultipleObjectsReturned: a 500 on
        the one action that commits inventory. It also makes "which physical
        plate is this?" unanswerable, which is the question the master exists to
        answer.

        Nothing enforced this before because plates were only ever added from
        Plate Master, one screen, deliberately. Now that a plate can also be
        created mid-assign from Arrangement History, two people naming a plate
        for the same job is an ordinary Tuesday — so the guard has to be here,
        on the serializer both doors already go through, rather than in either
        screen.
        """
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("A plate name is required.")
        clash = SeedPlate.objects.filter(plate_name__iexact=name)
        if self.instance is not None:  # an edit may keep its own name
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(f'A plate named "{name}" already exists.')
        return name


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
