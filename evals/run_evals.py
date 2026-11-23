"""Run golden evals against the live model and report results."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from mtg_assistant.agent import RulesAgent

GOLDEN_PATH = Path(__file__).parent / "golden.json"


def check(case: dict, result) -> tuple[bool, list[str]]:
    failures = []

    # Check expected tools were called
    tools_used = {c["name"] for c in result.tool_calls}
    for tool in case.get("expect_tools", []):
        if tool not in tools_used:
            failures.append(f"expected tool '{tool}' was not called (called: {tools_used or 'none'})")

    answer_lower = result.answer.lower()

    # All of these must appear in the answer
    for phrase in case.get("expect_in_answer", []):
        if phrase.lower() not in answer_lower:
            failures.append(f"expected '{phrase}' in answer")

    # At least one of these must appear in the answer
    any_phrases = case.get("expect_in_answer_any", [])
    if any_phrases and not any(p.lower() in answer_lower for p in any_phrases):
        failures.append(f"expected one of {any_phrases} in answer")

    return len(failures) == 0, failures


def main():
    cases = json.loads(GOLDEN_PATH.read_text())
    agent = RulesAgent()

    passed = 0
    failed = 0

    print(f"Running {len(cases)} evals against {agent.model_id}\n")
    print("-" * 60)

    for case in cases:
        print(f"[{case['id']}]")
        print(f"  Q: {case['question']}")

        result = agent.ask(case["question"])

        ok, failures = check(case, result)

        tools_called = [c["name"] for c in result.tool_calls]
        tokens = result.usage.get("inputTokens", 0) + result.usage.get("outputTokens", 0)
        print(f"  Tools: {tools_called or 'none'}")
        print(f"  Tokens: {tokens}")
        print(f"  Answer: {result.answer[:120]}{'...' if len(result.answer) > 120 else ''}")

        if ok:
            print(f"  PASS")
            passed += 1
        else:
            print(f"  FAIL")
            for f in failures:
                print(f"    - {f}")
            failed += 1

        print()

    print("-" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(cases)}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
