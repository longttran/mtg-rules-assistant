# MTG Rules Assistant

A Magic: The Gathering rules assistant built on **Claude via AWS Bedrock** (Converse API with tool use). It answers card and interaction questions by looking up official Oracle text and rulings from the [Scryfall API](https://scryfall.com/docs/api), and it says so when it can't find something instead of making it up.

## Architecture

```
User ──> Streamlit / CLI ──> RulesAgent (tool-use loop, max 6 turns)
                                 │
                                 ├──> Bedrock Converse API (Claude, temperature 0)
                                 │
                                 └──> Tools ──> Scryfall API
                                       ├─ get_card          (Oracle text)
                                       ├─ get_card_rulings  (official rulings)
                                       └─ search_cards      (Scryfall query syntax)
```

Every answer returns a **trace** (tool calls, errors, token usage) for debugging and evals.

## Run it (Windows / PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install "botocore[crt]"       # required for aws login credential provider
cp .env.example .env              # set BEDROCK_MODEL_ID and AWS_REGION
aws login                         # browser-based login for the new AWS experience
python cli.py --trace             # or: streamlit run app.py
pytest                            # offline tests, no AWS needed
python evals/run_evals.py         # live evals against the model
```

### Environment (.env)

```
AWS_REGION=us-east-2
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
```

Use a cross-region inference profile ID (with `us.` prefix) — base model IDs are not
supported for on-demand invocation in this account.

### SSL note (corporate / Norton networks)

If `aws login` fails with `SSL: CERTIFICATE_VERIFY_FAILED`, your network is doing SSL
inspection. Export the intercepting CA certificate from the Windows cert store and append
it to the certifi bundle, then point the AWS CLI at it:

```powershell
aws configure set ca_bundle "<path-to-certifi>\cacert.pem"
```

## Design decisions

- **Grounding over memory:** the system prompt requires a tool lookup before describing any card, and quoting the text used.
- **Tool errors go back to the model** as `status: error` rather than crashing, so it can tell the user a card wasn't found.
- **Bounded loop:** at most 6 model turns per question to cap cost and avoid tool-call loops.
- **Offline tests:** Bedrock and Scryfall are faked in `tests/`, so CI is free and doesn't need credentials.

## What's working

- CLI (`python cli.py --trace`) and Streamlit web UI (`streamlit run app.py`) both working.
- 5/5 unit tests passing (offline, no AWS needed).
- 4/4 live evals passing (`python evals/run_evals.py`).
- Deployed model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` in `us-east-2`.

## Known gaps / next steps

- **RAG over Comprehensive Rules** — in progress, see below.
- Single-turn questions only; no conversation memory.
- No auth or rate limiting on the UI.

## RAG over Comprehensive Rules — in progress

Goal: ingest the full MTG Comprehensive Rules (~963 KB text file) into a Bedrock Knowledge
Base so the assistant can answer rules questions beyond individual card lookups.

### What's been set up

| Resource | Name / ID | Status |
|---|---|---|
| S3 bucket | `mtg-rules-assistant-kb-565950324050` | ✅ Created, rules file uploaded |
| IAM role | `AmazonBedrockExecutionRoleForKB-mtg-rules` | ✅ Created with S3 + Bedrock model policies |
| OpenSearch Serverless collection | `mtg-rules-kb` (`a6gghypuxlw255e4yyqf`) | ✅ ACTIVE in `us-east-2` |
| OpenSearch encryption policy | `mtg-rules-kb-enc` | ✅ Created |
| OpenSearch data access policy | `mtg-rules-kb-access` | ✅ Created |
| Vector index | `mtg-rules-index` | ❌ Blocked — see below |
| Bedrock Knowledge Base | — | ⏳ Not yet created |

### Blocker: vector index creation

The vector index (`mtg-rules-index`) needs to be created inside the OpenSearch Serverless
collection before the Knowledge Base can be built. CLI/SDK calls are blocked by a 401/403
from AOSS — the managed account puts roles under a `/managed/` path prefix that AOSS
access policy matching doesn't handle correctly.

**Workaround (next session):** create the index manually via the OpenSearch Dashboards UI:

1. Go to the OpenSearch Service console in `us-east-2`
2. Click **Serverless → Collections → mtg-rules-kb**
3. Open the collection endpoint → **Dev Tools**
4. Run:

```json
PUT mtg-rules-index
{
  "settings": { "index": { "knn": true } },
  "mappings": {
    "properties": {
      "bedrock-knowledge-base-default-vector": {
        "type": "knn_vector",
        "dimension": 1024,
        "method": { "name": "hnsw", "engine": "faiss", "parameters": {} }
      },
      "AMAZON_BEDROCK_TEXT_CHUNK": { "type": "text" },
      "AMAZON_BEDROCK_METADATA": { "type": "text", "index": false }
    }
  }
}
```

### Remaining steps after index creation

1. Attach `aoss:APIAccessAll` permission on the collection to the KB IAM role
2. Create the Bedrock Knowledge Base (VECTOR type, Titan Embeddings V2, OpenSearch storage config)
3. Create the S3 data source pointing at `mtg-rules-assistant-kb-565950324050`
4. Run ingestion and wait for `COMPLETE`
5. Verify with a test `retrieve` query
6. Wire the KB ID into the agent so it can query the rules during tool calls

### Why Managed KB wasn't used

Bedrock Managed Knowledge Base (`type: MANAGED`) is not available in `us-east-2` and the
account SCP blocks Bedrock operations in other regions, so the customer-managed path with
OpenSearch Serverless is required.
