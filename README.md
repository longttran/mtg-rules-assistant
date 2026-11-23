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

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # set BEDROCK_MODEL_ID
aws configure               # or AWS SSO
python cli.py --trace       # or: streamlit run app.py
pytest                      # offline tests, no AWS needed
```

## Design decisions

- **Grounding over memory:** the system prompt requires a tool lookup before describing any card, and quoting the text used.
- **Tool errors go back to the model** as `status: error` rather than crashing, so it can tell the user a card wasn't found.
- **Bounded loop:** at most 6 model turns per question to cap cost and avoid tool-call loops.
- **Offline tests:** Bedrock and Scryfall are faked in `tests/`, so CI is free and doesn't need credentials.

## Known gaps / next steps

- No retrieval over the full Comprehensive Rules (would add RAG with Bedrock Knowledge Bases).
- Single-turn questions only; no conversation memory.
- Evals in `evals/golden.json` are a starting set and are run by hand against the live model.
- No auth or rate limiting on the UI.
