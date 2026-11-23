"""Offline tests: Bedrock and Scryfall are faked, so these run free in CI."""

import copy
from unittest.mock import patch

import pytest

from mtg_assistant import RulesAgent
from mtg_assistant import tools


class FakeBedrock:
    """Returns a scripted sequence of Converse responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))  # snapshot; the agent keeps mutating messages
        return self.responses.pop(0)


def tool_use_response(name, tool_input, tool_use_id="t1"):
    return {
        "stopReason": "tool_use",
        "usage": {"inputTokens": 100, "outputTokens": 20},
        "output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": tool_use_id, "name": name, "input": tool_input}}
        ]}},
    }


def text_response(text):
    return {
        "stopReason": "end_turn",
        "usage": {"inputTokens": 150, "outputTokens": 40},
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
    }


FAKE_CARD = {"name": "Questing Beast", "oracle_text": "Vigilance, deathtouch, haste", "keywords": ["Deathtouch"]}


def test_agent_calls_tool_then_answers():
    fake = FakeBedrock([
        tool_use_response("get_card", {"name": "questing beast"}),
        text_response("Questing Beast has deathtouch."),
    ])
    agent = RulesAgent(model_id="test-model", client=fake)
    with patch.dict(tools.TOOLS["get_card"], {"fn": lambda name: FAKE_CARD}):
        result = agent.ask("Does Questing Beast have deathtouch?")

    assert result.answer == "Questing Beast has deathtouch."
    assert result.tool_calls == [{"name": "get_card", "input": {"name": "questing beast"}, "ok": True}]
    assert result.usage == {"inputTokens": 250, "outputTokens": 60}
    # Second request must carry the tool result back to the model
    last_msg = fake.calls[1]["messages"][-1]
    assert last_msg["content"][0]["toolResult"]["status"] == "success"


def test_tool_error_is_reported_not_raised():
    fake = FakeBedrock([
        tool_use_response("get_card", {"name": "Totally Fake Card"}),
        text_response("I couldn't find a card called Totally Fake Card."),
    ])
    agent = RulesAgent(model_id="test-model", client=fake)
    def not_found(name):
        raise tools.ToolError("No card found")

    with patch.dict(tools.TOOLS["get_card"], {"fn": not_found}):
        result = agent.ask("What does Totally Fake Card do?")

    assert result.tool_calls[0]["ok"] is False
    assert fake.calls[1]["messages"][-1]["content"][0]["toolResult"]["status"] == "error"


def test_stops_after_max_turns():
    fake = FakeBedrock([tool_use_response("get_card", {"name": "x"}, f"t{i}") for i in range(10)])
    agent = RulesAgent(model_id="test-model", client=fake)
    with patch.dict(tools.TOOLS["get_card"], {"fn": lambda name: FAKE_CARD}):
        result = agent.ask("loop forever")
    assert result.stop_reason == "max_turns"


def test_missing_model_id_raises(monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    with pytest.raises(RuntimeError, match="BEDROCK_MODEL_ID"):
        RulesAgent(client=object())


def test_summarize_double_faced_card():
    card = {
        "name": "Delver of Secrets // Insectile Aberration",
        "type_line": "Creature — Human Wizard // Creature — Human Insect",
        "card_faces": [
            {"name": "Delver of Secrets", "oracle_text": "At the beginning of your upkeep..."},
            {"name": "Insectile Aberration", "oracle_text": "Flying"},
        ],
    }
    summary = tools._summarize_card(card)
    assert [f["name"] for f in summary["faces"]] == ["Delver of Secrets", "Insectile Aberration"]
