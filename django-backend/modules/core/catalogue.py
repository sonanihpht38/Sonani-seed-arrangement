# ===================== SHARED / CROSS-CUTTING: catalogue contract =====================
# Every module declares its navigation/RBAC surface in a `catalogue.py` next to
# its models:
#
#     from modules.core.catalogue import GroupDef, FormDef, ColumnDef
#     GROUPS = [GroupDef("HR", "Human Resources", icon="users", sort_order=30)]
#     FORMS = [FormDef("leave_request", "Leave Requests", icon="calendar",
#                      route="/hr/leaves", sort_order=10, group="HR",
#                      columns=[ColumnDef("employee", "Employee")])]
#
# `sync_catalogue` upserts these into acc_module_group / acc_form /
# acc_grid_column (and can --check for drift or --prune stale forms).
# Code is the source of truth; the DB is the runtime cache the sidebar reads.

import importlib
import importlib.util
from dataclasses import dataclass, field

from django.apps import apps


@dataclass(frozen=True)
class ColumnDef:
    key: str
    label: str


@dataclass(frozen=True)
class FormDef:
    code: str
    name: str
    icon: str = ""
    route: str = ""
    sort_order: int = 0
    group: str = ""
    columns: tuple = field(default=())

    def __post_init__(self):
        object.__setattr__(self, "columns", tuple(self.columns))


@dataclass(frozen=True)
class GroupDef:
    code: str
    name: str
    icon: str = ""
    sort_order: int = 0


class CatalogueError(Exception):
    pass


def collect_catalogues():
    """Import every modules.* app's catalogue.py and return (groups, forms).

    Validates: unique group codes (identical duplicates tolerated), unique form
    codes across ALL modules, and that each form references a declared group.
    """
    groups, forms = {}, {}
    form_owner = {}
    for app in apps.get_app_configs():
        if not app.name.startswith("modules."):
            continue
        if importlib.util.find_spec(f"{app.name}.catalogue") is None:
            continue
        mod = importlib.import_module(f"{app.name}.catalogue")
        for g in getattr(mod, "GROUPS", []):
            if g.code in groups and groups[g.code] != g:
                raise CatalogueError(
                    f"Group '{g.code}' declared differently in more than one module "
                    f"(second definition in {app.name})."
                )
            groups[g.code] = g
        for f in getattr(mod, "FORMS", []):
            if f.code in forms:
                raise CatalogueError(
                    f"Form code '{f.code}' declared in both {form_owner[f.code]} and {app.name}."
                )
            forms[f.code] = f
            form_owner[f.code] = app.name
    for f in forms.values():
        if f.group not in groups:
            raise CatalogueError(
                f"Form '{f.code}' references unknown group '{f.group}'. "
                f"Declare it in some module's GROUPS."
            )
    return groups, forms
