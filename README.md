# opvs OS

Local-first PM operating system. Runs as a background daemon on macOS.

## First-time setup

```sh
./scripts/setup.sh
./scripts/install-daemon.sh
```

Then open http://localhost:5173 and configure your API keys in Settings.

## Development (hot reload, no daemon)

```sh
./scripts/dev.sh
```

## Daemon management

```sh
# Install / reinstall
./scripts/install-daemon.sh

# Remove (backend will no longer auto-start)
./scripts/uninstall-daemon.sh
```

## Logs

```sh
tail -f logs/backend.log       # stdout
tail -f logs/backend.error.log # stderr
```

## Architecture

The backend runs as a macOS LaunchAgent (`com.opvs.backend`), starting on login and restarting
on crash. The frontend is served by the backend from `frontend/dist/` in production, or by
Vite's dev server on port 5173 in development.

See `workspace/CLAUDE.md` for workspace conventions and agent rules.
