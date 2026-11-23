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
- RAG over the MTG Comprehensive Rules via Bedrock Knowledge Base + OpenSearch Serverless (`search_rules` tool).

## Known gaps / next steps

- Single-turn questions only; no conversation memory.
- No auth or rate limiting on the UI.

## RAG over Comprehensive Rules — ✅ Complete

The MTG Comprehensive Rules (~963 KB) are ingested into a Bedrock Knowledge Base backed by
OpenSearch Serverless. The agent uses the `search_rules` tool to look up rules text,
keyword definitions, and game mechanics before answering rules questions.

### AWS resources

| Resource | Name / ID |
|---|---|
| S3 bucket | `mtg-rules-assistant-kb-565950324050` |
| IAM role | `AmazonBedrockExecutionRoleForKB-mtg-rules` |
| OpenSearch Serverless collection | `mtg-rules-kb` (`a6gghypuxlw255e4yyqf`) |
| Bedrock Knowledge Base | `mtg-comprehensive-rules` (`Q10WCVYIPC`) |
| Embedding model | `amazon.titan-embed-text-v2:0` |
| Chunking | Hierarchical (1500 / 300 tokens, 60 token overlap) |

### Why Managed KB wasn't used

Bedrock Managed Knowledge Base (`type: MANAGED`) is not available in `us-east-2` and the
account SCP blocks Bedrock operations in other regions, so the customer-managed path with
OpenSearch Serverless is used instead.
