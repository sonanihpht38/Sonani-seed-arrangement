# Scaffold a new ERP module on the standard stack:
#   backend : TenantModel+AuditModel models, TenantCrudViewSet views, router
#             urls, catalogue.py, contract tests (modules/<name>/...)
#   frontend: resource API + <CrudResource> screen + routes.ts
#             (react-frontend/src/features/<name>/..., with --frontend)
#
# Usage:
#   python manage.py startmodule hr \
#       --group "HR:Human Resources:users:30" \
#       --resource Department --resource LeaveRequest --frontend
#
# Resource spec: ModelName[:form_code[:Plural Label]] — defaults derive the
# form code "<module>_<plural_snake>" and label from the model name.
#
# The command prints the three manual wiring steps at the end (INSTALLED_APPS,
# config/urls.py include, frontend route registry) — explicit wiring beats
# magic imports for debuggability.

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

BACKEND_ROOT = Path(__file__).resolve().parents[4]          # django-backend/
FRONTEND_ROOT = BACKEND_ROOT.parent / "react-frontend"


def camel_to_snake(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def plural(snake):
    if snake.endswith("y") and snake[-2] not in "aeiou":
        return snake[:-1] + "ies"
    if snake.endswith(("s", "x", "z", "ch", "sh")):
        return snake + "es"
    return snake + "s"


class Command(BaseCommand):
    help = "Scaffold a new module (backend + optional frontend) on the standard ERP stack."

    def add_arguments(self, parser):
        parser.add_argument("name", help="module package name, e.g. 'hr'")
        parser.add_argument("--group", required=True,
                            help="menu group 'CODE:Label[:icon[:sort]]', e.g. 'HR:Human Resources:users:30'")
        parser.add_argument("--resource", action="append", required=True, dest="resources",
                            help="repeatable: ModelName[:form_code[:Plural Label]]")
        parser.add_argument("--frontend", action="store_true",
                            help="also scaffold react-frontend/src/features/<name>/")
        parser.add_argument("--force", action="store_true", help="overwrite existing files")

    # ------------------------------------------------------------------ helpers
    def _write(self, path, content, force):
        if path.exists() and not force:
            raise CommandError(f"{path} already exists (use --force to overwrite)")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        self.stdout.write(f"  + {path.relative_to(BACKEND_ROOT.parent)}")

    def _parse_resources(self, module, specs):
        out = []
        for spec in specs:
            parts = spec.split(":")
            model = parts[0].strip()
            if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", model):
                raise CommandError(f"Model name must be PascalCase: {model!r}")
            snake = camel_to_snake(model)
            plural_snake = plural(snake)
            form_code = (parts[1].strip() if len(parts) > 1 and parts[1].strip()
                         else f"{module}_{plural_snake}")
            label = (parts[2].strip() if len(parts) > 2 and parts[2].strip()
                     else plural_snake.replace("_", " ").title())
            out.append({
                "model": model, "snake": snake, "plural_snake": plural_snake,
                "kebab": plural_snake.replace("_", "-"), "form_code": form_code,
                "label": label,
            })
        return out

    # ------------------------------------------------------------------ handle
    def handle(self, *args, **options):
        module = options["name"].strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", module):
            raise CommandError(f"Module name must be a python identifier: {module!r}")
        gparts = options["group"].split(":")
        if len(gparts) < 2:
            raise CommandError("--group must be 'CODE:Label[:icon[:sort]]'")
        group = {"code": gparts[0].strip(), "label": gparts[1].strip(),
                 "icon": gparts[2].strip() if len(gparts) > 2 else "grid",
                 "sort": int(gparts[3]) if len(gparts) > 3 else 50}
        resources = self._parse_resources(module, options["resources"])
        force = options["force"]

        mdir = BACKEND_ROOT / "modules" / module
        self._backend(module, group, resources, mdir, force)
        if options["frontend"]:
            self._frontend(module, group, resources, force)
        self._print_wiring(module, options["frontend"])

    # ------------------------------------------------------------------ backend
    def _backend(self, module, group, resources, mdir, force):
        cls = module.capitalize()
        self._write(mdir / "__init__.py", "", force)
        self._write(mdir / "apps.py", (
            "from django.apps import AppConfig\n\n\n"
            f"class {cls}Config(AppConfig):\n"
            f'    name = "modules.{module}"\n'
        ), force)

        models = [
            "# ============================ DOMAIN LAYER ============================\n"
            f"# {group['label']} module — models on the canonical ERP bases:\n"
            "# TenantModel (tenant FK + scoped manager) + AuditModel (audit columns).\n\n"
            "from django.db import models\n\n"
            "from modules.core.models import AuditModel, TenantModel\n\n"
        ]
        for r in resources:
            models.append(
                f"class {r['model']}(TenantModel, AuditModel):\n"
                f"    name = models.CharField(max_length=200)\n"
                f"    description = models.TextField(blank=True)\n"
                f"    is_active = models.BooleanField(default=True)\n\n"
                f"    class Meta:\n"
                f'        db_table = "{module}_{r["snake"]}"\n'
                f'        ordering = ["id"]\n\n'
                f"    def __str__(self):\n"
                f"        return self.name\n\n\n"
            )
        self._write(mdir / "models.py", "".join(models).rstrip() + "\n", force)

        ser = [
            "# ===================== APPLICATION LAYER: serializers =====================\n\n"
            "from rest_framework import serializers\n\n"
            f"from .models import {', '.join(r['model'] for r in resources)}\n\n\n"
        ]
        for r in resources:
            ser.append(
                f"class {r['model']}Serializer(serializers.ModelSerializer):\n"
                f"    class Meta:\n"
                f"        model = {r['model']}\n"
                f'        fields = ["id", "name", "description", "is_active", "created_at", "updated_at"]\n'
                f'        read_only_fields = ["created_at", "updated_at"]\n\n\n'
            )
        self._write(mdir / "serializers.py", "".join(ser).rstrip() + "\n", force)

        views = [
            "# ============================= API LAYER =============================\n"
            "# TenantCrudViewSet provides: form-code RBAC, tenant scoping, ownership\n"
            "# stamping, and the standard paginated list envelope.\n\n"
            "from modules.core.viewsets import TenantCrudViewSet\n\n"
            f"from .models import {', '.join(r['model'] for r in resources)}\n"
            f"from .serializers import {', '.join(r['model'] + 'Serializer' for r in resources)}\n\n\n"
        ]
        for r in resources:
            views.append(
                f"class {r['model']}ViewSet(TenantCrudViewSet):\n"
                f'    form_code = "{r["form_code"]}"\n'
                f"    queryset = {r['model']}.objects.all()\n"
                f"    serializer_class = {r['model']}Serializer\n"
                f'    search_fields = ["name", "description"]\n\n\n'
            )
        self._write(mdir / "views.py", "".join(views).rstrip() + "\n", force)

        urls = [
            "from rest_framework.routers import DefaultRouter\n\n"
            f"from .views import {', '.join(r['model'] + 'ViewSet' for r in resources)}\n\n"
            "router = DefaultRouter()\n"
        ]
        for r in resources:
            urls.append(f'router.register("{r["kebab"]}", {r["model"]}ViewSet, basename="{r["plural_snake"]}")\n')
        urls.append("\nurlpatterns = router.urls\n")
        self._write(mdir / "urls.py", "".join(urls), force)

        cat = [
            f"# Navigation/RBAC surface of the {module} module.\n"
            "from modules.core.catalogue import ColumnDef, FormDef, GroupDef\n\n"
            "GROUPS = [\n"
            f'    GroupDef("{group["code"]}", "{group["label"]}", icon="{group["icon"]}", sort_order={group["sort"]}),\n'
            "]\n\n"
            "FORMS = [\n"
        ]
        for i, r in enumerate(resources, start=1):
            cat.append(
                f'    FormDef("{r["form_code"]}", "{r["label"]}", icon="folder",\n'
                f'            route="/{module}/{r["kebab"]}", sort_order={i * 10}, group="{group["code"]}",\n'
                f"            columns=[\n"
                f'                ColumnDef("name", "Name"), ColumnDef("description", "Description"),\n'
                f'                ColumnDef("is_active", "Active"),\n'
                f"            ]),\n"
            )
        cat.append("]\n")
        self._write(mdir / "catalogue.py", "".join(cat), force)

        tests = [
            "# Module contract tests — every TenantCrudViewSet resource must pass these\n"
            "# (auth, RBAC, envelope shape, tenant isolation). See modules/core/testing.py.\n\n"
            "from django.test import TestCase\n\n"
            "from modules.core.testing import CrudContractTestMixin\n\n"
            f"from .models import {', '.join(r['model'] for r in resources)}\n\n\n"
        ]
        for r in resources:
            tests.append(
                f"class {r['model']}ContractTests(CrudContractTestMixin, TestCase):\n"
                f'    base_url = "/api/{module}/{r["kebab"]}/"\n'
                f'    form_code = "{r["form_code"]}"\n\n'
                f"    def make_instance(self, tenant, **kwargs):\n"
                f'        return {r["model"]}.all_objects.create(tenant_id=tenant.id, name="Row", **kwargs)\n\n'
                f"    def create_payload(self):\n"
                f'        return {{"name": "New row", "description": ""}}\n\n\n'
            )
        self._write(mdir / "tests.py", "".join(tests).rstrip() + "\n", force)

    # ------------------------------------------------------------------ frontend
    def _frontend(self, module, group, resources, force):
        fdir = FRONTEND_ROOT / "src" / "features" / module

        types = [f"// DTOs for the {module} module.\n\n"]
        for r in resources:
            types.append(
                f"export interface {r['model']} {{\n"
                "  id: number;\n  name: string;\n  description: string;\n"
                "  is_active: boolean;\n  created_at: string;\n  updated_at: string;\n}\n\n"
            )
        self._write(fdir / "types.ts", "".join(types).rstrip() + "\n", force)

        apis = [
            f"// Resource APIs for the {module} module (standard envelope CRUD).\n"
            'import { makeResourceApi } from "../../api/resource";\n'
            f"import type {{ {', '.join(r['model'] for r in resources)} }} from \"./types\";\n\n"
        ]
        for r in resources:
            camel = r["plural_snake"].split("_")
            camel = camel[0] + "".join(w.title() for w in camel[1:])
            r["api_name"] = f"{camel}Api"
            apis.append(f'export const {r["api_name"]} = makeResourceApi<{r["model"]}>("/{module}/{r["kebab"]}");\n')
        self._write(fdir / f"{module}Api.ts", "".join(apis), force)

        for r in resources:
            screen = (
                f"// {r['label']} — standard CRUD screen on <CrudResource>.\n"
                'import { Form, Input, Switch } from "antd";\n'
                'import { CrudResource } from "../../components/CrudResource";\n'
                f'import {{ {r["api_name"]} }} from "./{module}Api";\n'
                f'import type {{ {r["model"]} }} from "./types";\n\n'
                f"export function {r['model']}s() {{\n"
                f"  return (\n"
                f"    <CrudResource<{r['model']}>\n"
                f'      form="{r["form_code"]}"\n'
                f'      title="{r["label"]}"\n'
                f'      queryKey="{module}-{r["kebab"]}"\n'
                f"      resource={{{r['api_name']}}}\n"
                f"      columns={{[\n"
                f'        {{ field: "name", headerName: "Name" }},\n'
                f'        {{ field: "description", headerName: "Description" }},\n'
                f'        {{ field: "is_active", headerName: "Active", maxWidth: 110,\n'
                f'          valueFormatter: (p) => (p.value ? "Yes" : "No") }},\n'
                f"      ]}}\n"
                f"      exportColumns={{[\n"
                f'        {{ key: "name", header: "Name" }},\n'
                f'        {{ key: "description", header: "Description" }},\n'
                f'        {{ key: "is_active", header: "Active" }},\n'
                f"      ]}}\n"
                f"      renderForm={{() => (\n"
                f"        <>\n"
                f'          <Form.Item name="name" label="Name" rules={{[{{ required: true }}]}}>\n'
                f"            <Input />\n"
                f"          </Form.Item>\n"
                f'          <Form.Item name="description" label="Description">\n'
                f"            <Input.TextArea rows={{2}} />\n"
                f"          </Form.Item>\n"
                f'          <Form.Item name="is_active" label="Active" valuePropName="checked" initialValue={{true}}>\n'
                f"            <Switch />\n"
                f"          </Form.Item>\n"
                f"        </>\n"
                f"      )}}\n"
                f"    />\n"
                f"  );\n"
                f"}}\n"
            )
            self._write(fdir / f"{r['model']}s.tsx", screen, force)

        routes = [
            f"// Route entries for the {module} feature (see routes/registry.ts).\n"
            'import { lazy } from "react";\n'
            'import type { RouteEntry } from "../../routes/registry";\n\n'
            f"export const {module}Routes: RouteEntry[] = [\n"
        ]
        for r in resources:
            routes.append(
                f'  {{ form: "{r["form_code"]}", path: "{module}/{r["kebab"]}", '
                f'Component: lazy(() => import("./{r["model"]}s").then((m) => ({{ default: m.{r["model"]}s }}))) }},\n'
            )
        routes.append("];\n")
        self._write(fdir / "routes.ts", "".join(routes), force)

    # ------------------------------------------------------------------ wiring
    def _print_wiring(self, module, frontend):
        self.stdout.write(self.style.SUCCESS("\nScaffold complete. Manual wiring steps:"))
        self.stdout.write(
            f'  1. config/settings/base.py  -> add "modules.{module}" to LOCAL_APPS\n'
            f'  2. config/urls.py           -> path("api/{module}/", include("modules.{module}.urls"))\n'
        )
        if frontend:
            self.stdout.write(
                f"  3. src/routes/registry.ts   -> import {{ {module}Routes }} from "
                f'"../features/{module}/routes"; spread into ROUTES\n'
            )
        self.stdout.write(
            "\nThen: python manage.py makemigrations "
            f"{module} && python manage.py migrate && python manage.py sync_catalogue"
        )
