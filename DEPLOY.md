# Production Deployment — Zero-Shot Agent / UP Police Analyst

## Quick Start (Docker Compose)
1. Copy `.env.example` to `.env.production` and set exactly ONE provider key.
2. From the repo root:
   - `ops/deploy.sh`
   - `ops/logs.sh`
   - `ops/health.sh`
   - `ops/stop.sh`

## Environment
- `PORT` defaults to `8001`
- `UP_ANALYST_UPLOAD_ROOT` defaults to `/app/data/uploads`
- Data is preserved through the `./data` bind mount

## Image
- Built from `Dockerfile`
- Tagged as `abhishek-harness/api:${TAG:-latest}`
