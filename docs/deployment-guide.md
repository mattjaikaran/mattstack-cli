# mattstack deployment guide

Select a deployment target in your scaffold YAML:

```yaml
name: my-app
type: fullstack
backend:
  framework: django-ninja
  task_backend: celery
frontend:
  framework: react-rsbuild-kibo
deployment: railway
```

Run `mattstack init --config project.yaml`. Use the generated provider recipe
for exact commands, variable names, image paths, and secret setup.

## Supported combinations

Generation rejects these combinations before it writes a project:

- Backend-only or Next.js with Cloudflare. Choose Docker or another API host.
- Next.js fullstack with Render. Choose a provider with the generated container
  routing contract, or deploy the frontend and API separately.
- Frontend-only with Railway, AWS, GCP, Hetzner, or self-hosted. Choose Docker,
  Render, Fly.io, DigitalOcean, or Cloudflare.

B2B presets keep their explicit frontend/router selection. Do not substitute
an unrelated B2B frontend with different auth and organization endpoints.

## Generated recipes

| Target | Files and runtime contract |
|---|---|
| Docker | Root dev/prod Compose files; repo-root builds through `docker/backend/Dockerfile` and `docker/frontend/Dockerfile` |
| Railway | `.railway/railway.ts` and pinned `.railway/package.json`; IaC database references, selected workers, and operator secrets |
| Render | `render.yaml`; database bindings, generated secrets, workers, and static frontend rewrites before SPA fallback |
| Fly.io | `fly.toml`; fullstack also emits `fly.frontend.toml` with a separate frontend app and private Flycast API upstream |
| DigitalOcean | App Platform specification; internal API upstream for static frontends and path-preserving ingress for Next.js |
| AWS | `ecs-task-definition.json` and Copilot service manifests; fullstack frontend/API containers and selected worker commands |
| GCP | `service.yaml` for Cloud Run and `workerpool-*.yaml` for selected task processes; fullstack frontend ingress with API sidecar |
| Hetzner | Production Compose override and Caddy configuration for TLS termination |
| Self-hosted | Production Compose override, nginx template, certificates, and systemd recipe |
| Cloudflare | Pages frontend recipe plus Caddy/Compose API deployment for supported static fullstack configurations |

App Engine is not generated. Railway IaC needs CLI 5.42.1 or later, login, and
a linked project. Pin and install its local IaC package with Bun.

## Production prerequisites

1. Run `make setup` and commit any dependency lock updates. Renaming preserves
   editable-project and workspace names in existing text locks. Older sources
   that need dependency upgrades print the affected manifest and setup command.
2. Copy `.env.production.example` to the ignored `.env.production`, or set the
   same variables through your provider's secret manager.
3. Replace every placeholder. Use independent secret/signing keys. The backend
   entrypoint rejects empty, short, placeholder, equal signing secrets, and
   unresolved platform references with a fix and verification command.
4. Configure the real database. Django reads `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
   `DB_HOST`, and `DB_PORT`; `DATABASE_URL` alone does not configure Django.
5. Set frontend origins and allowed hosts. FastAPI origins use a JSON list,
   for example `["https://app.example.com"]`. FastAPI production also requires
   a non-localhost `WEBAUTHN_RP_ID` and HTTPS `WEBAUTHN_ORIGIN`.
6. For selected realtime or S3 profiles, set their additional secrets. S3
   needs bucket, region, access key, and secret. Do not commit these values.
7. Build from the repository root, deploy the selected worker processes, apply
   migrations, and verify the API, frontend, admin, and media paths you use.

The production image starts through `app-entrypoint`. It applies the selected
production mode before `serve` or a worker command. `APP_PORT` takes precedence
over a provider's `PORT` for sidecars. Run `app-entrypoint health` inside the
backend container to exercise its actual local health endpoint.

## TLS and health probes

Ninja enables `USE_TLS` behind the generated TLS edges. Only the three public
health routes bypass SSL redirects; admin and staff detail routes still
redirect. Host validation remains active. Fresh published-source clones receive
the same narrow settings change during initialization.

AWS recipes leave `USE_TLS` off until you configure an HTTPS listener. Then set
`USE_TLS=true` and preserve forwarded-proto headers. Docker's local plain-HTTP
recipe does not enable TLS. Do not expose either plain-HTTP recipe as a secure
public deployment.

Railway allows its documented `healthcheck.railway.app` probe Host. Fly and
Cloud Run configure explicit probe headers. AWS can allow only its own task IP
from ECS metadata; failed discovery stops startup. Render allows its external
hostname and localhost probe; this Host behavior is based on staff/community
reports and still needs a live provider check.

DigitalOcean's Django probe is TCP-only. It proves that the port accepts a
connection, not application or dependency health. Verify the HTTP API after
deployment. A readiness response of 503 is a dependency failure, not success.

For Fly fullstack, follow both app recipes and allocate the private Flycast
address before deploying the frontend. Flycast is HTTP-only inside its private
network; the frontend app provides the public HTTPS edge.

## Verification boundary

Local proof covers production Ninja startup, migrations, Caddy HTTPS health and
admin/static routing, HSTS, health Host validation, queue consumption, and S3
upload/readback. Provider schemas and local IaC validation do not prove a live
cloud deployment.

No billable cloud deployment has been run. Railway variable resolution, Render
rewrites/probes, Flycast networking, DigitalOcean private bindings, AWS IAM/ALB
and service discovery, GCP IAM/WorkerPool availability, and Cloudflare DNS/Pages
still require an authorized account and a real deployment smoke. Keep issue
[#9](https://github.com/mattjaikaran/mattstack-cli/issues/9) open for that evidence.
