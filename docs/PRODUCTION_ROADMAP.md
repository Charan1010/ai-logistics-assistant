# Production Roadmap - AI Logistics Assistant

**Goal:** run the chatbot on Azure, automate updates, then improve reliability
and support more users.

**Next step:** sign in to Azure and confirm the subscription we are authorized
to use. No Azure app has been deployed yet.

**Step-by-step guide:** [Feature 14: First Azure Deployment](feature-14-azure-deployment.md).
Feature 13 covered GHCR publishing; Feature 15 will cover real RAG evaluations.

## 1. Current state

- The app supports chat, document retrieval, agents, and configurable language
  model providers.
- [ci.yml](../.github/workflows/ci.yml) runs software checks and unit tests.
- [eval.yml](../.github/workflows/eval.yml) tests AI answers against ten example
  questions. The real-model step runs only when the Groq secret is present.
- [deploy.yml](../.github/workflows/deploy.yml) builds and publishes the Docker
  image to GitHub Container Registry (GHCR). It does not yet run it in Azure.
- Published image: `ghcr.io/charan1010/ai-logistics-assistant`.

A **Docker image** packages the application and its dependencies. A **container**
is a running instance of that image. GHCR stores the image; Azure will run it
and provide a website address.

## 2. Deployment choice

We will use **Azure Container Apps**, a managed service that runs containers
without requiring us to maintain the underlying servers. It fits our existing
Docker image and avoids the additional complexity of Kubernetes.

```text
Browser -> HTTPS -> Python app on Azure Container Apps
                       |
                       +-> Chroma: retrieve relevant document text
                       |
                       +-> Groq: generate the answer
```

Azure hosts our application; Groq hosts the language model. The embedding model
used for document search runs inside our application, so we still need to
measure its processor and memory requirements.

The initial deployment will support text chat and document retrieval with
approved demo data. Vision currently depends on Ollama separately and needs
additional work before it can be included.

## 3. First deployment

### Step 1 - Select the Azure account and subscription

Sign in using **Azure CLI**, the command-line tool for managing Azure.
Confirm the intended subscription before making changes.

- **Account:** the identity used to sign in.
- **Subscription:** the billing and access boundary for our resources.
- **Region:** the geographical location where the app runs.
- **Resource group:** a named group of related resources, used for management
  and cleanup.

**Complete when:** the intended subscription is confirmed and we have permission
to use it. Signing in does not create hosting resources.

### Step 2 - Check deployment readiness

Check application startup, memory use, model downloads, storage, and access
controls. Separate required fixes from limitations acceptable for a demo.

Specific checks:

- Groq works without a local Ollama server.
- A fresh container can obtain and load the embedding model.
- The cloud configuration does not enable the insecure certificate-verification
  workaround in [embeddings.py](../app/embeddings.py).
- Protected features cannot be used without authorization.
- Document retrieval works with a known sample document.

**Complete when:** required changes and the supported demo features are clear.

### Step 3 - Review the design and cost

Choose the region, processor and memory allocation, storage approach, and
logging setup. Estimate hosting, storage, logs, and separate Groq charges.

Start with at most one **replica**, meaning one running copy of the app, because
conversation and task state are not shared between copies.

Decide whether to use **scale-to-zero**, which stops the app when idle to reduce
compute charges. The next request may wait for startup, called a **cold start**.
Free allowances must be checked; budget alerts are not hard spending caps.

**Complete when:** you approve the design and cost estimate before infrastructure
files are generated.

### Step 4 - Prepare configuration and access protection

Use **Bicep** to describe Azure resources in files. This is infrastructure as
code: a repeatable, reviewable setup rather than a series of manual portal changes.

After approval:

- Configure the image and HTTPS access to the app on port `8000`.
- Store the Groq key as an Azure secret and reference it through an environment
  variable. Never include it in Git, the image, or browser code.
- Protect sensitive read, write, and administrative endpoints in a way that
  also works with the browser UI. CORS is not authentication.
- Check whether GHCR needs pull credentials before adding any.
- Validate the Bicep and review **what-if**, a preview of proposed Azure changes.

**Complete when:** configuration validation and access tests pass, and the
resource-change preview is reviewed.

### Step 5 - Approve and deploy

Confirm the subscription, region, resources, and cost again. Get separate
approval to create the resources, then deploy.

Use an image **digest** (`sha256:...`) to identify the exact image contents.
Tags such as `latest` or `sha-<commit>` can be reassigned.

**Complete when:** Azure runs the selected image and provides an HTTPS address.

### Step 6 - Verify the live application

- Open the UI and check `/api/health`.
- Confirm unauthorized requests to protected features are rejected.
- Check the selected provider through authorized access to `/api/status`.
- Send a real chat request and receive an answer.
- Upload an approved sample document and verify retrieval against its content.
- Inspect startup and request logs.
- Restart the app and check its behavior against the agreed storage limitations.

**Complete when:** access protection, chat, and retrieval work. A successful
health response alone does not prove these features work.

### Step 7 - Document operation and cleanup

Record the website address, deployed image, resources, logs, costs, and steps
to restore a previous working version.

Document cleanup for the exact demo resources. Deleting a resource group also
deletes its contents, so inspect it and confirm before deletion.

**Complete when:** we can diagnose a failed request, restore a working version,
and remove the demo safely.

### First-demo limitations

| Limitation | Effect | Later improvement |
|---|---|---|
| Sessions and tasks are in memory | Lost on process restart | Durable database |
| Chroma uses local container storage | Uploaded knowledge may be lost on container replacement | Suitable durable storage |
| At most one running copy | Limited concurrent capacity | Shared state before adding replicas |
| Fresh containers may lack model files | Slow first document request | Tested model download/cache strategy |
| Vision depends on Ollama | Not included initially | Separate vision-provider support |

Keeping one replica running does not prevent restart-related data loss. A
network file share is not automatically safe for SQLite-backed Chroma; storage
compatibility must be checked.

## 4. Next after deployment: make CI test real retrieval

After the first protected deployment, fix the evaluation pipeline before using
it to approve automatic releases. The live retrieval check in Step 6 is still
required for the first deployment.

### Give CI its own test data and embedding model

GitHub-hosted runners do not have our laptop's Chroma database or Docker volume.
A volume with the same name on another machine does not share its contents.
CI should build an isolated test database, not connect to production data.

1. Commit small synthetic documents with known facts, such as test warehouse
   hours and return policies.
2. Load `all-MiniLM-L6-v2`. Installing SentenceTransformers installs the library;
   loading the model downloads its weights if they are not cached.
3. Pin the model revision and use it for both document and query embeddings.
   Cache model files separately from pip packages, with a cache key tied to the
   model revision. A cache miss must still work through a normal download.
4. Embed the test documents and insert their chunks into a temporary Chroma
   database. Python can access this directory directly; Docker is not required.
5. Run questions against that database, then discard it. Never modify the
   developer's local database or a production collection.

### Fix and strengthen the evaluation

- Fix the search adapters in [run_eval_ci.py](../tests/run_eval_ci.py) and the
  evaluation endpoint in [main.py](../app/main.py): embed the question, pass
  `n_results`, and return the text-chunk shape expected by the harness.
- Remove silent search-error fallbacks. Log the error and fail the affected
  evaluation case rather than answering without context and reporting success.
- Record `query_type`, `needs_retrieval`, `confidence`, chosen route, whether
  search was attempted, and retrieved chunk IDs/counts.
- Test general questions that skip retrieval, document questions that retrieve,
  and low-confidence questions that take the hybrid path.
- Check expected source documents and known answer facts, not just classification
  or words such as "warehouse". Add a no-answer case to test unsupported claims.
- Keep focused tests of routing and adapters separate from real-model evaluations:
  controlled tests prove branch behavior; live evaluations measure model behavior.
- Save a per-case report with answers and failure reasons for these synthetic
  cases. Do not log credentials or real user documents.

```text
Synthetic documents -> Embed -> Temporary Chroma database
                                      ^
Test question -> Classify -> Embed -> Search -> Context + question -> Groq
                    |
                    +-> General question: Groq without document retrieval
```

**Complete when:** a known document question retrieves the expected source and
answers from it; broken retrieval, missing required context, and wrong facts
fail their cases. Required retrieval checks must block releases independently
of the overall score, so general-question passes cannot hide broken RAG.

## 5. Automate deployment from GitHub

After the first deployment and retrieval-evaluation fixes, extend the workflow:

```text
Merge -> Software tests + AI evaluations -> Build candidate once
      -> Container health + HTML checks -> Publish the same tested image
      -> Deploy exact image digest -> Test live app -> Keep or roll back
```

- **Continuous integration:** check code changes automatically.
- **Continuous delivery:** prepare a version for release.
- **Continuous deployment:** update the running app automatically after checks.

Before enabling automatic releases:

1. Require the intended checks on every release path. Manual and version-tag
   publishing currently bypass the normal workflow gate check.
2. Require the retrieval checks from Section 4. Missing evaluation credentials
   must block a release, not silently skip the required quality checks.
3. Use **OpenID Connect (OIDC)** so the authorized GitHub workflow receives
   short-lived Azure credentials instead of storing an Azure password.
4. Test the live application after deployment and implement recovery.

A Container App **revision** is a version of its configuration. **Rollback**
returns traffic to a known-good version; it does not restore lost data or undo
database changes.

**Complete when:** checked changes reach the website, failed checks block
releases, and recovery from a failed deployment has been tested.

## 6. Make each component production-ready

These follow the protected demo; they are not all prerequisites for the first
deployment. Production readiness means meeting explicit reliability, security,
capacity, and recovery requirements, not simply adding more services.

### A. Put each kind of data in appropriate storage

**Durable** means data survives app replacement. **Shared** means multiple app
copies can access it. Our in-memory dictionaries provide neither.

| Data | Current storage | Production direction | Verification |
|---|---|---|---|
| Conversations and messages | Python session dictionary | PostgreSQL with user/session ownership, transactions, and stable message ordering | History survives restart and concurrent messages are not lost |
| Agent tasks and progress | Python task dictionary | Durable task records in PostgreSQL plus a reliable job queue | Another worker can recover interrupted work without duplicating completed actions |
| Retrieval history and feedback | Python retrieval-memory list | Shared database records with retention rules; derive digests from those records | History is available across replicas and deletions follow retention policy |
| Original uploaded files | No durable raw-file archive in this plan yet | Object storage, such as Azure Blob Storage, with document IDs recorded in the database | Original files can be recovered and reprocessed |
| Chunks and vectors | Local Chroma files | Evaluate PostgreSQL with pgvector or a supported networked vector service; store model/index version and access metadata | Retrieval survives app replacement and enforces user access filters |
| Cache and shared rate limits | Process-local state | Redis where needed, with expiration and atomic rate-limit updates | Requests across replicas obey the same limits; cache loss does not lose conversations |
| Metrics and operational logs | Local logs and process counters | Central monitoring service with retention and sensitive-data filtering | Failures remain diagnosable after a container is replaced |

Chunk text may stay with vectors or in PostgreSQL; splitting them is not
mandatory. Keep document IDs consistent across stores and make deletion remove
the file, chunks, vectors, and affected cache entries. Add backups and test a
restore; persistence alone is not a backup.

### B. Handle concurrent requests safely

**Concurrency** means requests overlap. One async Python worker can overlap
network waits, but it does not make CPU-heavy embedding work non-blocking.

- Use async network calls and reuse HTTP/database connection pools.
- Move blocking parsing and embedding work off the web request event loop into
  bounded workers. Batch embeddings where it improves measured throughput.
- Limit simultaneous model calls, uploads, and jobs. Queue excess work or return
  an explicit overload response instead of exhausting memory.
- Protect shared updates with database transactions and unique constraints.
  Define message ordering for simultaneous requests in the same session.
- Use an **idempotency key**, an identifier for a logical operation, so retries
  do not create duplicate uploads or repeat an external agent action.

**Complete when:** simultaneous chat/upload tests do not stall unrelated requests,
lose messages, exceed configured concurrency limits, or duplicate actions.

### C. Process large documents and long agent jobs separately

```text
Upload -> Store original file + job record -> Return job ID
                         |
                         v
                    Job queue -> Worker -> Parse -> Embed -> Index
                                      |
                                      +-> Update progress/result in database
```

The browser checks progress by job ID rather than holding one request open.
Use durable job delivery, bounded retries, and a failed-job queue for inspection.
Persist the job record and reliably arrange queue delivery so a crash between
those steps cannot leave accepted work permanently unprocessed.

Workers must tolerate redelivery. Use document/version IDs to prevent duplicate
chunks and expose a new index version only when ingestion is complete.
External actions need their own deduplication or reconciliation; a queue does
not guarantee an action runs exactly once.

**Complete when:** killing a worker mid-job allows safe recovery, and failed
uploads show a clear status rather than disappearing or appearing complete.

### D. Scale app copies only after state is shared

Once durable/shared state is in place, the web app can be **stateless**: any
replica can handle the next request without needing the previous replica's RAM.

- Add replicas behind Azure's request routing and scale web and job workers
  independently.
- Set limits based on load tests, database connections, provider quotas, and cost.
  More replicas do not increase Groq's quota.
- Measure memory per worker: loading an embedding model in each process can
  multiply memory use. Consider separate embedding workers if measurements justify it.
- Test graceful shutdown and interrupted requests during replacement.

**Complete when:** two or more replicas share conversations correctly and meet an
agreed latency/error target under load, including when one replica is stopped.

### E. Make model calls reliable and measurable

- Apply timeouts, bounded retries with backoff, and provider concurrency limits.
  Retry transient failures, not invalid requests or authentication failures.
- Stream answers for responsiveness, while tracking failed or interrupted streams.
- Version prompts, generation-model settings, and embedding models. A changed
  embedding model requires a compatible new index, not mixed vectors.
- Expand evaluations for retrieval, grounded answers, tools, and no-answer cases.
- Track tokens, cost, response time, and user feedback. Scope caches by user
  permissions, document version, and model/prompt version.

**Complete when:** provider outages produce explicit errors without uncontrolled
retries, and model/prompt changes pass quality and cost checks before release.

### F. Protect users and operate the service

- Authenticate users and enforce ownership on every document, search, session,
  and task operation. Do not trust a caller-supplied tenant ID by itself.
- Keep databases private where practical; grant the app only needed permissions.
  Rotate secrets and validate upload sizes/types.
- Treat retrieved text as untrusted input, restrict agent tool permissions, and
  require confirmation for consequential actions.
- Collect request IDs and timings across retrieval, model calls, and jobs.
  Alert on errors, slow requests, queue backlog, and spending.
- Separate basic **liveness** (process responds) from **readiness** (can accept
  work). Do not make every probe issue a billable LLM call.
- Use separate test and production data, scan images, deploy by digest, and test
  rollback with backward-compatible database changes.
- Define acceptable downtime and data loss; test backups, restores, and incident
  procedures against those requirements.

**Complete when:** cross-user access tests fail safely, alerts detect simulated
failures, and a restore/recovery exercise meets the agreed targets.

### Implementation order

1. Protected deployment and live verification.
2. Real retrieval evaluations, then gated automatic deployment.
3. Durable storage and user-level access controls.
4. Reliable jobs and concurrency controls.
5. Load-tested replicas and caching where measurements justify them.
6. Ongoing quality, monitoring, and recovery improvements.

Basic access protection and logs start with the first deployment; the later
steps deepen them. No production customer-data claim until durability, access,
and recovery checks are satisfied.

## 7. Working approach

For each step: explain the relevant concepts, make a focused change, verify
the result, then review it. Commit, push, and resource creation require the
appropriate approval.

**Immediate next action: Azure sign-in and subscription confirmation.**
