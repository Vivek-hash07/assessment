# Transaction Webhook Service

A FastAPI demo that accepts transaction webhooks, stores them in PostgreSQL,
and exposes their status. The webhook endpoint persists each transaction
before returning `202 Accepted`; a background worker simulates a slow operation
and marks the record processed after the configured delay.

> **Simulation only:** the worker now waits for 30 seconds in the background,
> then marks the transaction `PROCESSED`. It does not call a real payment
> provider or update a ledger. The transaction is persisted before the HTTP
> acknowledgment, so a database outage can delay or fail the request; an
> absolute 500 ms response-time guarantee is not possible when the database or
> network is slow.

## Requirements and current behavior

| Requirement | Current behavior |
| --- | --- |
| `POST /v1/webhooks/transactions` returns `202` | Implemented after the PostgreSQL insert succeeds. |
| Acknowledge within 500 ms | The handler does no simulated processing and performs one database insert, but end-to-end timing depends on PostgreSQL/network/host latency; a hard 500 ms guarantee is not possible. |
| Process after about 30 seconds | The worker starts processing after its next poll and simulates the operation with a 30-second async sleep before marking the record processed. |
| Prevent duplicate transaction processing | Implemented using `transaction_id` as the primary key and `ON CONFLICT DO NOTHING`. A repeat webhook is acknowledged, but does not update the original transaction. |
| Persist transaction status and timestamps | Implemented in PostgreSQL. Pending records remain available across application restarts. |
| Retry worker failures | The worker logs failures; a claimed record becomes eligible again when its lease expires. The lease is configured to exceed the simulated delay. A real external operation must itself be idempotent because retries can repeat it. |
| Public deployment and endpoint | `render.yaml` configures a Render Blueprint, but deployment still requires connecting the repository, setting `DATABASE_URL`, and completing a successful deploy. |

Other behavior to know:

- `GET /` returns `{"status":"HEALTHY","current_time":"..."}`. It is a liveness response and does not check database health.
- `GET /v1/transactions/{transaction_id}` returns a one-element JSON array, or `404` if no record exists. `processed_at` is `null` until the worker completes the record.
- Amounts must be positive; currency must be three characters and is stored uppercase.
- Webhook signature verification is not implemented. Do not expose this demo to real payment traffic without authenticating provider requests.

## API

### Health check

```http
GET /
```

Example response:

```json
{
  "status": "HEALTHY",
  "current_time": "2024-01-15T10:30:00Z"
}
```

### Submit a transaction webhook

```http
POST /v1/webhooks/transactions
Content-Type: application/json
```

Request:

```json
{
  "transaction_id": "txn_abc123def456",
  "source_account": "acc_user_789",
  "destination_account": "acc_merchant_456",
  "amount": 1500,
  "currency": "INR"
}
```

Response: `202 Accepted`

```json
{"status":"accepted"}
```

Invalid payloads receive FastAPI's `422 Unprocessable Entity` response. A
duplicate `transaction_id` also receives `202`; it does not create another
database record or reset the original record's processing delay.

### Retrieve transaction status

```http
GET /v1/transactions/txn_abc123def456
```

Example response:

```json
[
  {
    "transaction_id": "txn_abc123def456",
    "source_account": "acc_user_789",
    "destination_account": "acc_merchant_456",
    "amount": 1500.0,
    "currency": "INR",
    "status": "PROCESSING",
    "created_at": "2024-01-15T10:30:00Z",
    "processed_at": null
  }
]
```

The status changes to `PROCESSED` and `processed_at` is populated after the
worker handles the record. A missing transaction returns `404 Not Found`.

## Run locally

Requirements: Python 3.10 or later and access to a PostgreSQL database.

From the project root (the directory containing `app/`):

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `DATABASE_URL` to your PostgreSQL connection string. Do
not commit `.env` or publish database credentials. Optional settings and their
defaults:

| Variable | Default | Description |
| --- | --- | --- |
| `PROCESSING_DELAY_SECONDS` | `30` | Simulated background processing duration. |
| `LEASE_SECONDS` | `120` | Time a worker owns a claimed record before another attempt can claim it. |
| `CLAIM_BATCH_SIZE` | `10` | Maximum records claimed in one worker poll. |
| `POLL_INTERVAL_SECONDS` | `1` | Idle wait between polls when there are no due records. |

Start the application:

```bash
uvicorn app.main:app --reload
```

The app creates the transaction table on startup. Interactive API
documentation is available at `http://localhost:8000/docs`.

## Test

### With curl

```bash
curl http://localhost:8000/

curl -i -X POST http://localhost:8000/v1/webhooks/transactions \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"txn_abc123def456","source_account":"acc_user_789","destination_account":"acc_merchant_456","amount":1500,"currency":"INR"}'

curl http://localhost:8000/v1/transactions/txn_abc123def456
sleep 32
curl http://localhost:8000/v1/transactions/txn_abc123def456
```

The first status lookup should show `PROCESSING`; after approximately 30
seconds plus the worker poll interval, it should show `PROCESSED`. Send the
same POST again to exercise duplicate handling; the status endpoint should
still return one record.

### With Postman

Import
[`postman/Transaction Webhook Service.postman_collection.json`](postman/Transaction%20Webhook%20Service.postman_collection.json).
Set the collection's `base_url` variable to the running service (default:
`http://localhost:8000`) and run **Health check**, **Submit transaction
webhook**, and **Get transaction status**. Run the status request again after
about 32 seconds. Change the `transaction_id` collection variable to test with
a fresh transaction.

## Deploy (Render + Neon)

The included [`render.yaml`](render.yaml) defines the build and start commands
for a Render Blueprint. To deploy:

1. Create a PostgreSQL database (for example, on Neon) and copy its connection
   string without sharing it publicly.
2. In Render, create a **Blueprint** from this GitHub repository and confirm
   the service configuration from `render.yaml`.
3. Set the service's `DATABASE_URL` environment variable to the PostgreSQL
   connection string.
4. Deploy. The start command must be lowercase:
   `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
5. After deployment succeeds, use the HTTPS URL assigned by Render for the
   API examples. This repository does not include a verified live service URL.

If you already created a Render Web Service manually, edit **Settings →
Build & Deploy → Start Command** and replace the failing
`Uvicorn app.main:app --reload` with the lowercase command above, then redeploy.
The log's `Uvicorn: command not found` error occurs because shell commands are
case-sensitive; the installed executable is `uvicorn`, not `Uvicorn`. The
`--reload` option is for local development and should not be used in the
production start command.

Free hosting tiers may sleep when idle and have cold-start latency; this
implementation does not promise a 500 ms acknowledgment in those conditions.

## Technical choices

- **FastAPI** provides async request handling, payload validation, and OpenAPI
  documentation.
- **PostgreSQL** stores transactions and acts as the durable work queue.
- **Idempotency** uses a primary key on `transaction_id` and an
  `ON CONFLICT DO NOTHING` insert.
- **Background processing** uses a PostgreSQL-backed queue. The worker claims
  records with `FOR UPDATE SKIP LOCKED` and a lease, then simulates a
  30-second operation. Pending work survives application restarts and can be
  retried after a worker interruption.

The worker runs in the FastAPI application process. For production, consider
running workers separately, adding webhook signature verification and
monitoring, implementing the actual idempotent transaction operation, and
marking a record processed only after that operation succeeds.
