# Portfolio Model Assumptions Workbook Reference

`portfolio_data.xlsx` is the canonical source of portfolio model assumptions for the backend simulation engine.

Do not edit alternate copies in Desktop, Downloads, OneDrive, Google Drive, frontend folders, or Antigravity brain/scratch folders.

All assumption changes must be made to this workbook in the backend repo, reviewed, tested, committed, pushed, and redeployed.

Production Railway uses the Git-tracked workbook bundled with the backend deployment unless the backend storage architecture is explicitly changed in the future.

Do not change the workbook contents without a separate approved workbook-change task.

## Future Improvement & API Exposure

In future releases, the backend API can be extended to dynamically expose:
* Ingested workbook filename
* Workbook version / date stamp
* Workbook SHA-256 hash or checksum

This metadata will allow the frontend to confirm alignment and track when the underlying workbook assumptions are updated.
