# Project Brief: Starling Bank Synchronisation Service for Actual Budget

## Overview

### Project Name

**actual-starling-sync**

### Purpose

Develop a lightweight, self-hosted synchronisation service that imports transaction data from the Starling Bank Customer API into a self-hosted Actual Budget instance.

The application is intended to replace the functionality normally provided by GoCardless Bank Sync, which is currently unavailable for new users. The service should operate autonomously on a configurable schedule, providing reliable, idempotent transaction synchronisation without requiring manual intervention.

Real-time synchronisation is **not** a project goal. Reliability, simplicity and maintainability take precedence over low-latency updates.

---

# Objectives

The service shall:

* Authenticate securely with the Starling Bank Customer API.
* Retrieve newly posted transactions.
* Avoid importing duplicate transactions.
* Import transactions into Actual Budget.
* Maintain synchronisation state between executions.
* Recover automatically from temporary API or network failures.
* Run unattended inside a Docker container.

The project should be suitable for long-term self-hosted operation.

---

# Design Philosophy

The project should follow several guiding principles.

## Single Responsibility

This application is **not** an accounting system.

It is solely responsible for moving transaction data between two systems.

Accounting logic, reconciliation, budgeting and categorisation remain the responsibility of Actual Budget.

---

## Stateless Processing

Each synchronisation cycle should behave as though it could be the first after a restart.

Persistent state should be limited to the minimum information required to determine where the previous successful synchronisation completed.

---

## Idempotency

The synchronisation process must be completely idempotent.

Running the synchronisation repeatedly without new transactions must never create duplicates.

Starling transaction identifiers should be treated as immutable unique identifiers.

---

## Simplicity First

The preferred architecture is intentionally conservative.

Avoid introducing unnecessary infrastructure such as:

* FastAPI
* Celery
* Redis
* RabbitMQ
* Kubernetes
* Message queues

Unless a clear requirement emerges, a scheduled Python worker is sufficient.

---

# High-Level Architecture

```
+--------------------+
| Starling API       |
+--------------------+
          |
          |
          ▼
+--------------------+
| Python Sync Worker |
+--------------------+
          |
          |
          ▼
+--------------------+
| Actual Budget      |
+--------------------+
```

The worker periodically polls Starling, determines which transactions are new, and imports them into Actual Budget.

---

# Functional Requirements

## Starling Integration

The application shall:

* Authenticate using Starling Personal Access Tokens.
* Retrieve transaction history.
* Support incremental synchronisation.
* Handle API pagination where required.
* Respect API rate limits.
* Retry transient failures using exponential backoff.

---

## Synchronisation

Each synchronisation cycle should:

1. Load previous synchronisation state.
2. Request transactions newer than the previous checkpoint.
3. Validate received data.
4. Normalise transaction fields.
5. Detect duplicates.
6. Import new transactions into Actual Budget.
7. Persist updated synchronisation state.

---

## State Management

Persistent state should include:

* last successful synchronisation timestamp
* last processed transaction identifier
* optional import statistics

The implementation should use SQLite by default.

The storage abstraction should allow migration to PostgreSQL in the future if required.

---

## Error Handling

Recoverable failures include:

* temporary network failures
* HTTP timeouts
* API rate limiting
* temporary Actual Budget unavailability

These should trigger retries.

Unrecoverable failures should:

* log the error
* terminate the current synchronisation
* leave synchronisation state unchanged

---

## Logging

Structured logging should be used throughout.

Log entries should include:

* synchronisation start
* synchronisation finish
* transactions processed
* transactions imported
* duplicates skipped
* API failures
* retry attempts
* execution duration

JSON formatted logs are preferred.

---

# Docker Requirements

The application shall be distributed as a single Docker image.

Container behaviour:

* starts automatically
* executes scheduled synchronisation
* remains running
* supports graceful shutdown
* supports restart by Docker

Configuration shall be entirely environment-variable driven.

No configuration should require rebuilding the container.

---

# Configuration

Configuration should include:

```
STARLING_ACCESS_TOKEN

ACTUAL_SERVER_URL

ACTUAL_SYNC_PASSWORD

SYNC_INTERVAL_MINUTES

LOG_LEVEL

DATABASE_PATH

TIMEZONE
```

Configuration should support Docker secrets where appropriate.

---

# Suggested Project Structure

```
actual-starling-sync/

    app/

        starling/
            client.py
            models.py

        actual/
            client.py

        sync/
            worker.py
            state.py
            scheduler.py

        database/
            models.py

        config.py

        logging.py

        main.py

    tests/

    Dockerfile

    docker-compose.yml

    requirements.txt

    README.md
```

---

# Technology Stack

Preferred technologies:

| Component   | Technology   |
| ----------- | ------------ |
| Language    | Python 3.13+ |
| HTTP        | httpx        |
| Data Models | Pydantic     |
| Database    | SQLite       |
| ORM         | SQLAlchemy   |
| Logging     | structlog    |
| Retry Logic | tenacity     |
| Container   | Docker       |

The project should minimise dependencies wherever possible.

---

# Non-Functional Requirements

The service should:

* be fully typed
* pass Ruff linting
* pass mypy type checking
* include unit tests for core synchronisation logic
* avoid global mutable state
* use dependency injection where practical
* be modular and easily extensible

---

# Future Enhancements (Out of Scope)

The initial implementation should not attempt to implement the following, but the architecture should not prevent them later.

Potential future enhancements include:

* merchant enrichment
* automatic categorisation rules
* multiple Starling accounts
* support for additional banks
* webhook support if Starling provides suitable events
* Prometheus metrics
* health endpoint
* notification integrations
* scheduled reconciliation reports
* Open Banking provider abstraction

---

# Deliverables

The completed project should include:

* fully documented source code
* Docker image
* Docker Compose example
* installation guide
* configuration documentation
* developer documentation
* unit tests
* sample environment file
* example logging output

---

# Success Criteria

The project will be considered complete when:

* A fresh Actual Budget installation can be connected to a Starling account.
* New transactions are imported automatically.
* Repeated synchronisations produce no duplicates.
* The service recovers gracefully from temporary failures.
* Deployment consists only of configuring environment variables and running Docker Compose.
