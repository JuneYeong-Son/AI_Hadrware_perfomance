# GPU-Perf Backend

FastAPI service for the GPU measurement apps. It provides three things:

1. **Accounts** — signup / login / logout (JWT bearer tokens).
2. **Measurement provenance** — every machine gets a shareable code and a
   server-only signing secret, so a shared benchmark result can be verified as
   genuine and untampered.
3. **Cross-user analytics** — pooled TFLOPS statistics, leaderboards, and your
   own percentile, per GPU model and measurement protocol.

## Run it

```bash
cd application/backend
python -m venv .venv
.venv/Scripts/activate        # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000/docs** for the interactive Swagger UI.

**Production deploy** (managed hosting + Postgres) and desktop packaging are
covered in [`packaging/README.md`](../../packaging/README.md); the repo-root
[`render.yaml`](../../render.yaml) one-click-deploys this backend via the
included [`Dockerfile`](Dockerfile).

### Configuration (environment variables)

| Variable | Default | Notes |
|---|---|---|
| `GPUPERF_SECRET_KEY` | dev key | **Set a random ≥32-byte value in production.** Rotating it invalidates all tokens. |
| `GPUPERF_DATABASE_URL` | `sqlite:///./gpuperf.db` | Any SQLAlchemy URL (e.g. Postgres) works. |
| `GPUPERF_TOKEN_TTL_MIN` | `43200` (30 days) | Access-token lifetime. |
| `GPUPERF_CORS_ORIGINS` | `*` | Comma-separated allowlist, or `*` for any origin. |

## API overview

### Auth — `/api/auth`
| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/signup` | – | Create account, returns a token |
| POST | `/login` | – | Exchange email+password for a token |
| POST | `/logout` | ✔ | Bump `token_version` → every existing token for the user becomes invalid |
| GET | `/me` | ✔ | Current user |

Logout is enforced **server-side** (not just client-side token deletion): each
user has a `token_version`, embedded in every token as `tv`. Logout increments
it, so any previously issued token fails the check on the next request.

### Devices — `/api/devices`
| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/register` | ✔ | Register a machine by its `fingerprint` (a **client-side** hash of a stable hardware id such as the GPU UUID — the raw id never reaches the server). Returns a shareable `public_code` like `NV-8WWJ-T288`. Idempotent per (owner, fingerprint). |
| GET | `` | ✔ | List my machines |

### Measurements — `/api/measurements`, `/api/verify`
| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/measurements` | ✔ | Submit a result for one of your registered machines. The server hashes the core fields and signs them with the device secret (HMAC-SHA256), returning a shareable `verify_code` like `M-9H2V-ZB92`. |
| GET | `/api/measurements` | ✔ | My results |
| GET | `/api/verify/{verify_code}` | – (public) | Canonical, tamper-evident view of one shared result |
| GET | `/api/verify/device/{public_code}` | – (public) | All verified results for one machine |

**How provenance works.** The server is the source of truth. A buyer who
receives a `verify_code` (or a machine's `public_code`) calls the public verify
endpoint and reads the canonical numbers straight from the server. If a shared
report, screenshot, or PDF claims different figures than the verify endpoint
returns, it is forged. The HMAC `signature` binds each result to the specific
machine that produced it.

### Analytics — `/api/analytics`
| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/models?protocol_id=` | – | Per-model stats: count, avg, median, p10, p90, max TFLOPS |
| GET | `/leaderboard?gpu_name=&protocol_id=&limit=` | – | Top results |
| GET | `/me/percentile?measurement_id=` | ✔ | Where your result ranks among peers with the same GPU + protocol |

**Comparability.** Results are only pooled within the same `protocol_id` and
only when `reliability == "valid"` — the same rule the measurement engine uses,
so two numbers are never compared unless they came from an identical workload.

## Data model

- **User** — email, display name, bcrypt password hash, `token_version`.
- **Device** — owner, hardware `fingerprint`, shareable `public_code`, per-device
  `hmac_secret` (never leaves the server).
- **Measurement** — owner, device, GPU name, dtype, matrix size, `protocol_id`,
  achieved / peak TFLOPS, reliability, environment (driver/torch/cuda),
  telemetry summary, `payload_hash`, `signature`, `verify_code`.

## Notes / next steps

- Tables are auto-created on startup (MVP). Add **Alembic** migrations before
  production.
- `bcrypt` for passwords, `PyJWT` (HS256) for tokens.
- Desktop integration (login screen, "upload result" button, a client that
  hashes the GPU UUID and posts to `/api/measurements`) is the next piece to
  wire into `application/gpu_measurer/desktop/`.
