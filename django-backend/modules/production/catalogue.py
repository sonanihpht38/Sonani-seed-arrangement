# Navigation/RBAC surface of the production (diamond plate-arrangement) module.
# Group + form codes, icons and sort order mirror the source module so existing
# role grants keyed on these form codes carry over unchanged.
#
# The seven workflow forms run in order (Seed Import → Download); Arrangement
# History and Plate Master sit between them by sort_order, as they did before.
from modules.core.catalogue import FormDef, GroupDef

GROUPS = [
    GroupDef("PRODUCTION", "Production", icon="package", sort_order=80),
]

FORMS = [
    FormDef("seed_import", "Seed Import", icon="database",
            route="/production/seed-import", sort_order=10, group="PRODUCTION"),
    FormDef("arrangement_history", "Arrangement History", icon="chart",
            route="/production/arrangements", sort_order=12, group="PRODUCTION"),
    FormDef("plate_master", "Plate Master", icon="grid",
            route="/production/plate-master", sort_order=15, group="PRODUCTION"),
    FormDef("batch_selection", "Batch Selection", icon="folder",
            route="/production/batch-selection", sort_order=20, group="PRODUCTION"),
    FormDef("criteria_input", "Criteria Input", icon="settings",
            route="/production/criteria", sort_order=30, group="PRODUCTION"),
    FormDef("processing_option", "Processing Option", icon="grid",
            route="/production/processing-option", sort_order=40, group="PRODUCTION"),
    FormDef("result_generation", "Result Generation", icon="chart",
            route="/production/result", sort_order=50, group="PRODUCTION"),
    FormDef("finalization", "Finalization", icon="shield",
            route="/production/finalize", sort_order=60, group="PRODUCTION"),
    FormDef("download", "Download", icon="file",
            route="/production/download", sort_order=70, group="PRODUCTION"),
]
