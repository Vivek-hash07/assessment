# Transaction Webhook Service

A FastAPI demo that accepts transaction webhooks, stores them in PostgreSQL,
and exposes their status. The webhook endpoint inserts the transaction and
returns `202 Accepted`; a background worker later marks eligible records as
processed.

> **Implementation status:** the configured 30-second delay is a durable
> `process_after` timestamp: the worker waits until that time before handling
> a record. The current `process_transaction` function is a placeholder/no-op;
> no external payment or ledger operation is performed. The worker then marks
> the record `PROCESSED`. This demonstrates deferred processing and status
> tracking, but is not a complete payment-processing integration.

## Requirements and current behavior

| Requirement | Current behavior |
| --- | --- |
| `POST /v1/webhooks/transactions` returns `202` | Implemented. The handler waits for the PostgreSQL insert before returning. |
| Acknowledge within 500 ms | Not guaranteed. Processing is outside the request, but database connection/insert latency is synchronous and has no 500 ms timeout. |
| Process after about 30 seconds | The default 30-second delay is stored in PostgreSQL; after it expires, the worker runs the placeholder and marks the transaction processed. Polling can add up to about one second. |
| Prevent duplicate transaction processing | Implemented using `transaction_id` as the primary key and `ON CONFLICT DO NOTHING`. A repeat webhook is acknowledged, but does not update the original transaction. |
| Persist transaction status and timestamps | Implemented in PostgreSQL. Pending records remain available across application restarts. |
| Retry worker failures | The worker logs failures; a claimed record becomes eligible again when its lease expires. Processing is not exactly-once, so any real external operation must itself be idempotent. |
| Public deployment and endpoint | No public service URL is configured in this repository. Deployment instructions are provided below; deploy the service and replace the example URL before sharing it. |

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
| `PROCESSING_DELAY_SECONDS` | `30` | Delay before a transaction is eligible for the worker. |
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

The first status lookup should show `PROCESSING`; after the delay and worker
poll, it should show `PROCESSED`. Send the same POST again to exercise
duplicate handling; the status endpoint should still return one record.

### With Postman

Import
[`postman/Transaction Webhook Service.postman_collection.json`](postman/Transaction%20Webhook%20Service.postman_collection.json).
Set the collection's `base_url` variable to the running service (default:
`http://localhost:8000`) and run **Health check**, **Submit transaction
webhook**, and **Get transaction status**. Run the status request again after
about 32 seconds. Change the `transaction_id` collection variable to test with
a fresh transaction.

## Deploy (Render + Neon example)

The repository does not include a deployed endpoint; these are example
deployment steps:

1. Create a PostgreSQL database (for example, on Neon) and keep its connection
   string private.
2. Create a Render Web Service connected to your repository.
3. Configure the build command as `pip install -r requirements.txt`.
4. Configure the start command as
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
5. Add `DATABASE_URL` as a Render environment variable.
6. After deployment, use the service's assigned HTTPS URL in the API examples
   above. Verify the URL is publicly reachable before advertising it.

Free hosting tiers may sleep when idle and have cold-start latency; this
implementation does not promise a 500 ms acknowledgment in those conditions.

## Technical choices

- **FastAPI** provides async request handling, payload validation, and OpenAPI
  documentation.
- **PostgreSQL** stores transactions and acts as the durable work queue.
- **Idempotency** uses a primary key on `transaction_id` and an
  `ON CONFLICT DO NOTHING` insert.
- **Deferred work** uses a persisted `process_after` timestamp. The worker
  claims due records with `FOR UPDATE SKIP LOCKED` and a lease, which supports
  recovery after a worker interruption and avoids two workers claiming the
  same row simultaneously.

The worker runs in the FastAPI application process. For production, consider
running workers separately, adding webhook signature verification, monitoring,
and implementing the actual idempotent transaction operation before marking a
record processed.
