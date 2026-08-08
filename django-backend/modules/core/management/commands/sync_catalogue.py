# Sync the code-declared catalogue (modules/*/catalogue.py) into the DB tables
# the sidebar + RBAC read (acc_module_group / acc_form / acc_grid_column).
#
#   python manage.py sync_catalogue            # upsert (create + update)
#   python manage.py sync_catalogue --check    # report drift, exit 1 (CI gate)
#   python manage.py sync_catalogue --prune    # also deactivate DB forms/columns
#                                              # that no module declares anymore
#                                              # (never deletes — permission rows survive)

from django.core.management.base import BaseCommand
from django.db import transaction

from modules.access.models import Form, GridColumn, ModuleGroup
from modules.core.catalogue import collect_catalogues


class Command(BaseCommand):
    help = "Upsert the per-module catalogue.py declarations into the form/menu tables."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true",
                            help="Report code<->DB drift and exit non-zero; write nothing.")
        parser.add_argument("--prune", action="store_true",
                            help="Deactivate DB forms/columns absent from code.")

    @transaction.atomic
    def handle(self, *args, **options):
        groups, forms = collect_catalogues()
        drift = []

        db_groups = {g.code: g for g in ModuleGroup.objects.all()}
        for g in groups.values():
            current = db_groups.get(g.code)
            desired = {"name": g.name, "icon": g.icon, "sort_order": g.sort_order}
            if current is None:
                drift.append(f"+ group {g.code}")
                if not options["check"]:
                    db_groups[g.code] = ModuleGroup.objects.create(code=g.code, **desired)
            else:
                changed = {k: v for k, v in desired.items() if getattr(current, k) != v}
                if changed:
                    drift.append(f"~ group {g.code}: {', '.join(changed)}")
                    if not options["check"]:
                        for k, v in changed.items():
                            setattr(current, k, v)
                        current.save(update_fields=list(changed))

        db_forms = {f.code: f for f in Form.objects.select_related("module_group")}
        for f in forms.values():
            current = db_forms.get(f.code)
            desired = {"name": f.name, "icon": f.icon, "route": f.route,
                       "sort_order": f.sort_order, "is_active": True}
            if current is None:
                drift.append(f"+ form {f.code}")
                if not options["check"]:
                    db_forms[f.code] = Form.objects.create(
                        code=f.code, module_group=db_groups[f.group], **desired)
            else:
                changed = {k: v for k, v in desired.items() if getattr(current, k) != v}
                if current.module_group.code != f.group:
                    changed["module_group"] = db_groups.get(f.group)
                if changed:
                    drift.append(f"~ form {f.code}: {', '.join(changed)}")
                    if not options["check"]:
                        for k, v in changed.items():
                            setattr(current, k, v)
                        current.save(update_fields=list(changed))

        for f in forms.values():
            form_row = db_forms.get(f.code)
            if form_row is None:  # --check on a not-yet-created form
                for c in f.columns:
                    drift.append(f"+ column {f.code}.{c.key}")
                continue
            db_cols = {c.key: c for c in form_row.columns.all()}
            for position, c in enumerate(f.columns, start=1):
                current = db_cols.get(c.key)
                desired = {"label": c.label, "sort_order": position, "is_active": True}
                if current is None:
                    drift.append(f"+ column {f.code}.{c.key}")
                    if not options["check"]:
                        GridColumn.objects.create(form=form_row, key=c.key, **desired)
                else:
                    changed = {k: v for k, v in desired.items() if getattr(current, k) != v}
                    if changed:
                        drift.append(f"~ column {f.code}.{c.key}: {', '.join(changed)}")
                        if not options["check"]:
                            for k, v in changed.items():
                                setattr(current, k, v)
                            current.save(update_fields=list(changed))
            if options["prune"]:
                declared = {c.key for c in f.columns}
                # Only prune columns when the module declares its column list;
                # an empty columns tuple means "not managed via catalogue".
                if declared:
                    for key, col in db_cols.items():
                        if key not in declared and col.is_active:
                            drift.append(f"- column {f.code}.{key} (deactivated)")
                            if not options["check"]:
                                col.is_active = False
                                col.save(update_fields=["is_active"])

        if options["prune"]:
            for code, form_row in db_forms.items():
                if code not in forms and form_row.is_active:
                    drift.append(f"- form {code} (deactivated)")
                    if not options["check"]:
                        form_row.is_active = False
                        form_row.save(update_fields=["is_active"])

        if not drift:
            self.stdout.write(self.style.SUCCESS("Catalogue in sync — no changes."))
            return
        for line in drift:
            self.stdout.write(f"  {line}")
        if options["check"]:
            self.stderr.write(self.style.ERROR(f"Catalogue drift: {len(drift)} difference(s)."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(f"Catalogue synced ({len(drift)} change(s))."))
