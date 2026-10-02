# Local project instructions

## API structure

- `/api/v1/user/...` — endpoints for regular users (members)
- `/api/v1/admin/...` — endpoints for admins (mess managers)

Put new or changed endpoints under the prefix that matches who calls them, and keep the Flutter app's endpoint constants (`mess-management/lib/config/util/app_constants.dart`) in sync.
