# One-time scripts

Each script applied one change to the original `~/firely-learning` working copy on 7 October 2026. Before patching, it backed up the file and checked the code it expected to find. The results are already part of `worklist/` and `converters/`, so none of these scripts is needed to build or run the platform. They are kept as a record of how the local portal, the batch export and its diagnostics evolved. Each one deliberately targets the original folder, not this repository.

| Script | Change |
|---|---|
| `firely_local_portal_setup.py` | Create a protected local Firely snapshot and point the reviewer portal at it (no AWS calls) |
| `firely_portal_diagnostics.py` | Add safe diagnostics to the authenticated verification route |
| `firely_portal_reference_fix.py` | Compare local patient references exactly in the bridge comparator |
| `firely_lab_update.py` | Load the synthetic lab update through the converter and refresh the protected snapshot |
| `firely_install_portal_export.py` | Add the batch download route behind the reviewer login |
| `firely_export_diagnostics.py` | Add export validation diagnostics, keeping every check |
| `firely_export_meta_fix.py` | Fix the converted-metadata comparison without changing source data |
