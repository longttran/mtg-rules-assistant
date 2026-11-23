"""Interactive CLI: python cli.py   (add --trace to see tool calls)."""

import argparse
import json

from dotenv import load_dotenv

from mtg_assistant import RulesAgent


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="MTG rules assistant")
    parser.add_argument("--trace", action="store_true", help="print tool calls and token usage")
    args = parser.parse_args()

    agent = RulesAgent()
    print("Ask a Magic rules question (blank line to quit).")
    while True:
        question = input("\n> ").strip()
        if not question:
            break
        result = agent.ask(question)
        print(f"\n{result.answer}")
        if args.trace:
            print("\n--- trace ---")
            print(json.dumps({"tool_calls": result.tool_calls, "usage": result.usage}, indent=2))


if __name__ == "__main__":
    main()
