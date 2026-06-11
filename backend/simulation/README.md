# Portfolio Model Assumptions Workbook Reference

`portfolio_data.xlsx` is the canonical source of portfolio model assumptions for the backend simulation engine.

Do not edit alternate copies in Desktop, Downloads, OneDrive, Google Drive, frontend folders, or Antigravity brain/scratch folders.

All assumption changes must be made to this workbook in the backend repo, reviewed, tested, committed, pushed, and redeployed.

Production Railway uses the Git-tracked workbook bundled with the backend deployment unless the backend storage architecture is explicitly changed in the future.

Do not change the workbook contents without a separate approved workbook-change task.

## Current Workbook Metadata Exposure

The canonical workbook is `backend/simulation/portfolio_data.xlsx`.
The backend `/health` endpoint dynamically exposes the following metadata:
- Filename
- Relative path
- SHA-256 hash
- File size (bytes)
- Last modified UTC timestamp
- Availability status

The workbook itself remains the source of assumptions. Updating workbook contents is a separate controlled task and should not be done casually.

