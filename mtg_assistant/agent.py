"""Tool-use agent loop on the AWS Bedrock Converse API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import boto3

from .tools import TOOLS, ToolError, run_tool

SYSTEM_PROMPT = """You are a Magic: The Gathering rules assistant.

Rules you must follow:
- Always look cards up with your tools before describing them. Never answer from memory about a card's text.
- Quote the relevant Oracle text or ruling when you explain an interaction.
- If a tool says a card wasn't found, say so plainly. Never invent cards, text or rulings.
- If the answer depends on Comprehensive Rules you can't look up, say what you're unsure of.
- Keep answers short: the answer first, then the supporting card text."""

MAX_TURNS = 6


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # trace for evals
    stop_reason: str = ""
    usage: dict[str, int] = field(default_factory=dict)


class RulesAgent:
    def __init__(self, model_id: str | None = None, region: str | None = None, client=None):
        self.model_id = model_id or os.environ.get("BEDROCK_MODEL_ID")
        if not self.model_id:
            raise RuntimeError(
                "Set BEDROCK_MODEL_ID (copy the model or inference-profile ID from the "
                "Bedrock console's model catalog)."
            )
        self.client = client or boto3.client(
            "bedrock-runtime", region_name=region or os.environ.get("AWS_REGION", "us-west-2")
        )
        self.tool_config = {"tools": [{"toolSpec": t["spec"]} for t in TOOLS.values()]}

    def ask(self, question: str) -> AgentResult:
        messages: list[dict[str, Any]] = [{"role": "user", "content": [{"text": question}]}]
        result = AgentResult(answer="")
        usage = {"inputTokens": 0, "outputTokens": 0}

        for _ in range(MAX_TURNS):
            resp = self.client.converse(
                modelId=self.model_id,
                system=[{"text": SYSTEM_PROMPT}],
                messages=messages,
                toolConfig=self.tool_config,
                inferenceConfig={"maxTokens": 1024, "temperature": 0},
            )
            for k in usage:
                usage[k] += resp.get("usage", {}).get(k, 0)

            message = resp["output"]["message"]
            messages.append(message)
            result.stop_reason = resp.get("stopReason", "")

            if result.stop_reason != "tool_use":
                result.answer = "".join(b.get("text", "") for b in message["content"]).strip()
                break

            tool_results = []
            for block in message["content"]:
                if "toolUse" not in block:
                    continue
                call = block["toolUse"]
                trace = {"name": call["name"], "input": call["input"]}
                try:
                    output = run_tool(call["name"], call["input"])
                    status, content = "success", [{"json": output}]
                    trace["ok"] = True
                except (ToolError, TypeError) as exc:
                    status, content = "error", [{"text": str(exc)}]
                    trace["ok"] = False
                    trace["error"] = str(exc)
                result.tool_calls.append(trace)
                tool_results.append(
                    {"toolResult": {"toolUseId": call["toolUseId"], "content": content, "status": status}}
                )
            messages.append({"role": "user", "content": tool_results})
        else:
            result.answer = "Sorry, I couldn't finish that lookup. Try rephrasing the question."
            result.stop_reason = "max_turns"

        result.usage = usage
        return result
