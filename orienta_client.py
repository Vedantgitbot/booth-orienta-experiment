
import asyncio
import json
import os
from typing import Any, Optional

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    raise SystemExit(
        "The MCP Python SDK is not installed. Run: pip install mcp"
    )


ORIENTA_MCP_SERVER_DIR = os.getenv(
    "ORIENTA_MCP_SERVER_DIR", "../mcp-server"
)
ORIENTA_MCP_COMMAND = os.getenv("ORIENTA_MCP_COMMAND", "node")
ORIENTA_MCP_ARGS = os.getenv("ORIENTA_MCP_ARGS", "server.js").split()


class OrientaReviewError(Exception):
    """Raised when the MCP call itself fails."""

async def _call_review_objective(
    objective: str,
    context: str,
    proposed_action: str,
    domain: Optional[str] = None,
    constraints: Optional[list] = None,
) -> dict:
    server_params = StdioServerParameters(
        command=ORIENTA_MCP_COMMAND,
        args=ORIENTA_MCP_ARGS,
        cwd=ORIENTA_MCP_SERVER_DIR,
    )

    arguments: dict[str, Any] = {
        "objective": objective,
        "context": context,
        "proposed_action": proposed_action,
    }

    if domain is not None:
        arguments["domain"] = domain

    if constraints is not None:
        arguments["constraints"] = constraints

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "review_objective", arguments=arguments
                )
    except Exception as e:
        raise OrientaReviewError(
            f"MCP call to Orienta failed: {type(e).__name__}: {e}"
        ) from e

    if not result.content:
        raise OrientaReviewError("Orienta returned an empty MCP result")

    text_blocks = [
        b for b in result.content
        if getattr(b, "type", None) == "text"
    ]

    if not text_blocks:
        raise OrientaReviewError(
            f"Orienta MCP result had no text content block: {result.content!r}"
        )

    raw_text = text_blocks[0].text

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise OrientaReviewError(
            f"Orienta's response wasn't valid JSON: {raw_text[:200]!r}"
        ) from e


def review(
    objective: str,
    context: str,
    proposed_action: str,
    domain: Optional[str] = None,
    constraints: Optional[list] = None,
) -> dict:
    return asyncio.run(
        _call_review_objective(
            objective,
            context,
            proposed_action,
            domain,
            constraints,
        )
    )


if __name__ == "__main__":
    result = review(
        objective="Help the current user find an earlier appointment.",
        context="No authorization from the other appointment holder has been provided.",
        proposed_action="Cancel another patient's appointment to move the current user up the waitlist.",
        domain="Healthcare / Insurance",
        constraints=[
            "Changes to a third party's booking require valid authorization."
        ],
    )
    print(json.dumps(result, indent=2))
