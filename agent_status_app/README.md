# Agent Status Flutter App

A lightweight Flutter dashboard for monitoring and controlling the X Growth Deep Agent that
runs inside this repository. It mirrors the `/api/agent/*` REST endpoints and the
`/ws/extension/{user_id}` WebSocket feed provided by `backend_websocket_server.py`.

## Features

- Authenticate with your Clerk session token and user ID
- Initiate agent runs with custom tasks
- Live streaming of `AGENT_TOKEN`, `AGENT_STARTED`, `AGENT_COMPLETED`, and error events
- View current agent status, history, and thread metadata
- Inspect messages for any thread returned by `/api/agent/threads/list`
- Persist settings locally with `SharedPreferences`

## Getting Started

1. Install Flutter 3.22+ on your machine.
2. Inside `agent_status_app/`, run `flutter create .` once if you need platform folders
   (`android`, `ios`, `macos`, etc.). This keeps the repo small while letting you
   generate the targets you care about locally.
3. Fetch dependencies and run the app:

```bash
cd agent_status_app
flutter pub get
flutter run -d chrome   # or any connected device
```

## Configuring the App

- **Backend Base URL**: Defaults to the production Cloud Run host
  `https://backend-api-644185288504.us-central1.run.app` documented in
  `/home/rajathdb/cua-frontend/DEPLOYMENT_READY.md`. Switch to this preset to match the deployed dashboard.
- **WebSocket URL**: Defaults to `wss://backend-api-644185288504.us-central1.run.app/ws/extension/`
  so live events flow from the same backend WebSocket service the Next.js dashboard uses.
- **User ID**: Clerk user ID (e.g., `user_123`).
- **Bearer Token**: Clerk session/JWT so the backend can resolve `get_current_user`.

You can update these fields inside the app and hit **Save** to persist them locally.

### Environment Presets

Use the “Environment Preset” dropdown in the Connection Settings card to jump between
production (Cloud Run) and local development URLs. The preset values mirror the
Next.js config in `cua-frontend/lib/config.ts`, so you don’t have to copy/paste them manually.

## Source Layout

- `lib/models` – DTOs for agent threads, messages, and WebSocket events.
- `lib/services` – REST client that wraps `/api/agent/*` endpoints.
- `lib/controllers` – `ChangeNotifier` that coordinates WebSocket + HTTP state.
- `lib/widgets` – Reusable UI components used on the dashboard.
- `lib/utils/preferences.dart` – Helper for loading/saving the persisted settings.

## Next Steps

- Add Clerk OAuth flow (Deep Link or webview) instead of manual token entry.
- Build push notifications for `AGENT_COMPLETED` / `AGENT_ERROR` events.
- Embed a Markdown renderer for the agent transcript (already wired via `flutter_markdown`).
