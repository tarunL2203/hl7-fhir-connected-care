# One-time patch scripts

Each script applied one change to the original `~/firely-learning` working copy on 7 October 2026 (it backs up the file it patches, then checks the patched code). Their results are already in `worklist/` and `analytics/`, so running them is not part of setup. They are kept as a record of how the portal export, diagnostics and reference checks evolved.

| Script | Change |
|---|---|
| `firely_local_portal_setup.py` | Create a protected local Firely snapshot and patch the reviewer portal (no AWS calls) |
| `firely_install_portal_export.py` | Add a batch download route behind the reviewer login |
| `firely_portal_diagnostics.py` | Add safe diagnostics to the authenticated verification route |
| `firely_portal_reference_fix.py` | Exact local patient-reference equivalence in the bridge comparator |
| `firely_export_diagnostics.py` | Safe export validation diagnostics; all validation checks kept |
| `firely_export_meta_fix.py` | Fix the converted-metadata comparison without changing source data |
