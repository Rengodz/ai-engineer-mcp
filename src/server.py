from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from src.database import init_db, search

SERVER_NAME = "ai-engineering-hub-knowledge"
SERVER_VERSION = "1.0.0"

TOOL_DEFINITION = types.Tool(
    name="search_knowledge",
    title="Recherche dans ai-engineering-hub",
    description=(
        "Recherche plein texte (SQLite FTS5) dans les fichiers Python, Markdown "
        "et texte du dépôt ai-engineering-hub. Renvoie les extraits les plus "
        "pertinents avec leur chemin et leur score."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Requête plein texte (mots-clés, expression ou opérateurs FTS5).",
                "minLength": 1,
            },
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de résultats à renvoyer.",
                "minimum": 1,
                "maximum": 50,
                "default": 5,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)


def format_results(query: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return (
            f"Aucun résultat pour « {query} ». "
            "Essayez des mots-clés plus généraux ou vérifiez que la base a été indexée."
        )

    blocks = [f"{len(results)} résultat(s) pour « {query} » :"]
    for index, result in enumerate(results, start=1):
        snippet = " ".join((result.get("snippet") or "").split())
        blocks.append(
            "\n".join(
                [
                    f"[{index}] {result.get('title', 'Sans titre')}",
                    f"    Chemin : {result.get('path', 'inconnu')}",
                    f"    Extrait : {snippet or '(aucun extrait)'}",
                    f"    Score BM25 : {result.get('rank', 0):.4f}",
                ]
            )
        )
    return "\n\n".join(blocks)


async def list_tools(_context: Any, _params: Any) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[TOOL_DEFINITION])


async def call_tool(_context: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
    if params.name != "search_knowledge":
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=f"Outil inconnu : {params.name}. Outil disponible : search_knowledge.",
                )
            ],
            isError=True,
        )

    arguments = params.arguments or {}
    query = str(arguments.get("query", "")).strip()
    if not query:
        return types.CallToolResult(
            content=[
                types.TextContent(type="text", text="Le paramètre « query » est obligatoire.")
            ],
            isError=True,
        )

    try:
        limit = int(arguments.get("limit", 5))
    except (TypeError, ValueError):
        limit = 5

    try:
        results = search(query, limit=limit)
        text = format_results(query, results)
        is_error = False
    except Exception as exc:
        text = f"Erreur lors de la recherche : {exc}"
        is_error = True

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        isError=is_error,
    )


server = Server(
    SERVER_NAME,
    version=SERVER_VERSION,
    instructions=(
        "Serveur de connaissances local du dépôt ai-engineering-hub. "
        "Utilisez search_knowledge pour retrouver du code, des tutoriels et des notes."
    ),
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)


async def main() -> None:
    init_db().close()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
