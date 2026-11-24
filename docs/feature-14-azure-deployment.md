# Feature 14: First Azure Deployment

**Cloud deployment extension - after Feature 13: GHCR image publishing**

Run the AI Logistics Assistant on Azure Container Apps and verify it through
an HTTPS website address. This is a protected learning demo, not yet a
multi-user production service.

**Status:** planned. This guide does not mean resources have been created.
Follow the steps in order; do not run resource-creation commands before approval.

## What You'll Build

| Artifact | What it does |
|---|---|
| Azure Container App | Runs the existing application image |
| Container Apps environment | Provides the hosting boundary and networking configuration |
| Resource group | Groups this demo's Azure resources for management and cleanup |
| Bicep infrastructure files | Describe the approved resources so setup is repeatable |
| Secret and access configuration | Supplies the Groq key and protects app features |
| Deployment notes | Record the image digest, URL, validation results, costs, and recovery steps |

No new AI capability is required. Text chat and document retrieval move from
local execution to cloud hosting. Vision, shared databases, and automated Azure
releases remain separate work.

## Connection to Earlier Features

| Earlier feature | What we reuse |
|---|---|
| Conversation memory | Existing session behavior, with restart-related data loss acknowledged |
| Document ingestion and retrieval | Embedding model and Chroma search |
| Smart routing | Selection between direct answers, RAG, and hybrid retrieval |
| Production design | Logs and health endpoint |
| Containerization | Existing Docker image and non-root runtime |
| GHCR publishing (Feature 13) | Published image, without rebuilding it differently for Azure |

The roadmap's earlier phase labels are separate from feature numbering.
This lesson implements the first-deployment milestone in
[PRODUCTION_ROADMAP.md](PRODUCTION_ROADMAP.md).

## New Concepts

| Concept | Meaning in this feature |
|---|---|
| Subscription | Azure billing and access boundary |
| Region | Geographical location where resources run |
| Resource group | Named group of related resources; not a server |
| Container Apps | Managed service that starts and runs our container |
| Ingress | Configuration that forwards web requests to our app |
| Replica | One running copy of the app |
| Secret reference | Supplies a protected value to the app without putting it in the image |
| Bicep | Azure infrastructure-as-code language |
| Image digest | Content fingerprint that selects exact image contents |
| Revision | A version of the Container App configuration |

```text
GHCR image -> Azure Container Apps -> Our Python application
                                          |
Browser -------- HTTPS -------------------+
                                          |
                                          +-> Chroma: document retrieval
                                          +-> Groq: answer generation
```

Azure runs our Python code. Groq runs the language model. The embedding model
runs inside our app, so container memory still matters.

## Before You Start

- Use the `ai-logistics-assistant` repository, not a bootcamp starter or solution.
- Have permission to use the intended Azure subscription.
- Confirm the published GHCR image and record its digest.
- Use a valid Groq key stored securely, never pasted into this guide.
- Use only synthetic or explicitly approved demo documents.
- Review existing working-tree changes before creating a feature branch.

Suggested branch when implementation begins: `feature/azure-container-apps`.
Creating this guide does not create that branch or approve commits and pushes.

## Your Task

### Step 1 - Sign in and confirm the subscription

Run these in PowerShell when beginning the lesson:

```powershell
az version
az login
az account list --query "[].{Name:name,Id:id,Default:isDefault}" --output table
```

Choose the authorized subscription. Replace the placeholder before running:

```powershell
az account set --subscription "<approved-subscription-id>"
az account show --query "{Name:name,Id:id}" --output table
```

These commands authenticate and select the target; they do not deploy the app.
Do not publish account details or credentials in deployment notes.

**Checkpoint:** the intended subscription is selected.

### Step 2 - Check the app before creating resources

Inspect the existing [Dockerfile](../Dockerfile), [configuration](../app/config.py),
and [embedding loader](../app/embeddings.py).

- Verify startup and the actual browser UI in the packaged image.
- Check that text generation uses Groq rather than a laptop's Ollama server.
- Test model download/loading in a fresh container; measure memory and startup time.
- Confirm certificate verification is not disabled in cloud configuration.
- Identify the access protection required for sensitive read/write/admin routes.
- Decide how the UI will authenticate without exposing a shared key in JavaScript.
- Keep unsupported vision functionality clearly unavailable.

**Checkpoint:** required fixes, resource needs, and demo limitations are recorded.
Do not select a memory size solely from an example.

### Step 3 - Review the Azure plan and cost

Prepare the subscription, region, resource group, Container Apps environment,
app configuration, logging destination, and cost estimate.

Start with at most one replica because sessions and tasks are process-local.
Choose whether the minimum is zero or one:

- **Zero:** can stop while idle; the next request may wait for startup.
- **One:** avoids intentionally scaling to zero but still permits restarts and
  replacement. It does not make memory durable.

Include hosting, logs, storage if used, and separate Groq usage. Check current
pricing and quotas. Budget alerts notify; they do not guarantee a spending cap.

**Approval gate 1:** approve the plan before generating infrastructure files
or making the planned deployment-related application changes.

### Step 4 - Prepare the approved infrastructure and access changes

Generate Bicep files under `infra/` in the application repository, after approval.
Exact file names and parameters are chosen with the plan.

Configure:

- The image by digest, not only the mutable `latest` tag.
- HTTPS ingress forwarding to port `8000`.
- Groq settings and an environment-variable reference to the stored secret.
- A lightweight health probe using `/api/health`.
- The approved memory, replica limits, logging, and storage choices.
- Registry pull credentials only if the image actually requires them.

Implement the approved access controls and their tests. Protect sensitive reads
as well as writes. Restrict CORS where needed, but do not treat it as authentication.

Validate Bicep and review Azure's **what-if** preview of resource changes.
Inspect the preview; it is not proof that the app itself will work.

**Checkpoint:** configuration validates, access tests pass, and the preview
contains only the intended resources.

### Step 5 - Approve resource creation and deploy

Present the final subscription, region, resource group, resource changes, and
cost estimate.

**Approval gate 2:** explicitly approve resource creation. Approval to write
Bicep is not approval to deploy it.

Then run the deployment command generated for that approved plan. Azure pulls
the selected GHCR image and starts it. Record the image digest, app revision,
and resulting HTTPS address.

Azure does not read our local [docker-compose.yml](../docker-compose.yml).
Its named Chroma volume, environment file, and host Ollama address do not
automatically transfer to the cloud.

**Checkpoint:** the container starts and an HTTPS address is available.

## Run It and Verify

### Step 6 - Test the deployed application

Use the actual address returned by deployment:

```powershell
$appUrl = "https://<deployed-app-hostname>"
Invoke-RestMethod -Uri "$appUrl/api/health"
```

Expect `status: healthy`. This only checks basic responsiveness.

Before Azure deployment, the `build-and-push` job in
[deploy.yml](../.github/workflows/deploy.yml) builds the candidate image once,
loads it into Docker on the runner, and starts it by image ID. It checks health,
the root HTML content type, and the application title before pushing the same
image under the generated GHCR tags. Failed checks prevent publication; there
is no second build. Software tests remain in CI.
The smoke check needs no model API keys and does not test JavaScript execution,
Groq, embeddings, retrieval, or Azure. Actual deployment still needs live checks.
These changes must be pushed and the publishing workflow executed to verify
the container; editing the workflow locally does not establish a passing run.

Then verify through the browser and the approved authentication flow:

| Test | Expected result |
|---|---|
| Open the UI | Page and its assets load |
| Call a protected API without authorization | Access is rejected |
| Inspect `/api/status` with authorization | Intended provider/model configuration is reported |
| Ask a general logistics question | A real Groq answer returns |
| Upload a small synthetic warehouse policy | Ingestion completes |
| Search for a fact in that policy | Matching source text is returned |
| Ask Smart Chat about the policy | Routing, retrieved sources, and answer agree with the document |
| Inspect logs | Startup and request outcomes are visible without exposing secrets |
| Perform an agreed controlled restart | Data behavior matches the accepted limitations |

The existing CI evaluation has a broken retrieval adapter and does not load
test documents. A green evaluation is not a substitute for these live checks.
Repairing that evaluation is the next follow-up, before automatic Azure releases.

## Storage and Memory in This Feature

| Data | First-demo behavior |
|---|---|
| Conversations and task state | In RAM; lost on process restart |
| Chroma chunks and vectors | Local container storage unless the approved plan adds suitable persistence |
| Local Docker volume | Stays on the local Docker host; not copied to Azure |
| Embedding model files | A fresh container may need a download if no cache is available |

Use disposable demo documents and expect to re-upload after replacement if
storage is ephemeral. A network file share is not automatically safe for
SQLite-backed Chroma. Durable production storage is a later design step.

## Operation and Cleanup

### Step 7 - Record how to operate the demo

- Locate container startup errors and request logs.
- Record how to deploy or reactivate a known-good revision and verify it.
- Record the resources and where to review charges.
- Document cleanup for the exact approved resource group.
- Inspect the group's contents and get confirmation before deleting it:
  deletion also removes contained resources and data.

Restoring an old app revision does not recover lost conversations or undo
database changes. Do not claim rollback works until the procedure is tested.

## Definition of Done

- [ ] Subscription, region, design, and cost were reviewed.
- [ ] Infrastructure files were approved before generation.
- [ ] Resource creation received separate approval.
- [ ] An identified image digest runs at the HTTPS address.
- [ ] Unauthorized access to protected features is rejected.
- [ ] Browser, real chat, ingestion, search, and document-answer checks pass.
- [ ] Restart-related data limitations are demonstrated and documented.
- [ ] Logs, recovery procedure, and cleanup instructions are available.
- [ ] Changes are ready for review; nothing is committed or pushed without approval.

## Next Feature

**Feature 15: Real RAG Evaluation in CI**

Build a temporary Chroma database from synthetic documents, download/cache a
pinned embedding model, fix the search adapter, and assert retrieval sources
and answer facts. After that, automate Azure releases with enforced quality gates.

Durable storage, background jobs, safe concurrency, and multi-replica scaling
follow in the [production roadmap](PRODUCTION_ROADMAP.md).
