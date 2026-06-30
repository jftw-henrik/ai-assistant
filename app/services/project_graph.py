import json
import logging
import re
import uuid
from datetime import date
from typing import Any

from groq import APIError as GroqAPIError
from groq import Groq

from app.config import get_settings
from app.models.project_graph import (
    GraphNode,
    NodeType,
    ProjectGraph,
    ProjectResolution,
    Relationship,
)

logger = logging.getLogger(__name__)

INFER_PROJECTS_PROMPT = """You infer semantic project clusters from a Trello board graph.

Today's date: {today}

You receive open cards (names, descriptions, labels, list names).
Group related cards into inferred projects/subprojects even when Trello lists do not define them.

Examples:
- Ring Skatteverket, Bokio, Deskjockeys, Företagskonto -> project "Starta AB / Företag" (area: company)
- Cubase lane bugs, MIDI macros, Key Editor -> project "Cubase / Studio workflow" (area: work or music)

Return ONLY valid JSON:
{{
  "projects": [
    {{
      "name": "project name",
      "area": "work|company|home|personal|music|finance|admin",
      "member_card_ids": ["trello card ids"],
      "reasoning": "why these cluster together"
    }}
  ],
  "relationships": [
    {{
      "source_card_id": "trello card id",
      "target_project_name": "project name",
      "relationship_type": "belongs_to|related_to|depends_on|blocks|follows_up|duplicates",
      "confidence": 0.0,
      "reasoning": "short"
    }}
  ]
}}

Rules:
- Only use card ids from the input.
- Create 2-8 meaningful projects when possible; singleton cards can stay unclustered.
- Prefer stable, human-readable project names.
- area should reflect the dominant theme of the cluster.
"""


RESOLVE_PROJECT_PROMPT = """You resolve which project a new voice/text input belongs to.

Today's date: {today}

You receive user input and a project graph summary (inferred projects, tasks, relationships).
Pick the best project match and how to handle the input.

Return ONLY valid JSON:
{{
  "project_name": "best project name",
  "matched_node_id": "project node id or null",
  "matched_card_id": "existing trello card id if input clearly updates an existing card, else null",
  "confidence": 0.0,
  "reasoning": "short explanation",
  "suggested_action": "update_existing|create_task_under_project|create_new_project|ask_clarification",
  "area": "work|company|home|personal|music|finance|admin",
  "target_list": "Work|FIRMOR|To Do|In Progress"
}}

Rules:
- company/finance/admin business tasks -> area company, target_list FIRMOR
- client/music/professional work -> area work or music, target_list Work
- personal/home -> area personal or home, target_list To Do
- update_existing only when input clearly refers to an existing card in the graph
- create_task_under_project when input fits a known project but is a new task
- create_new_project when input starts a clearly new initiative
- ask_clarification when ambiguous
- confidence >= 0.8 only when very sure
"""


class ProjectGraphError(Exception):
    """Raised when project graph operations fail."""


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "project"


def _infer_task_type(card: dict[str, Any]) -> NodeType:
    name = card.get("name", "").lower()
    labels = [label.lower() for label in card.get("labels", [])]
    if card.get("due"):
        return "deadline"
    if "idea" in labels or name.startswith("idea:"):
        return "idea"
    if any(word in name for word in ("ring", "call", "email", "kontakt")):
        return "contact"
    return "task"


def build_graph_from_trello(snapshot: dict[str, Any]) -> ProjectGraph:
    """Build a structural graph from Trello lists and cards."""
    nodes: list[GraphNode] = []
    relationships: list[Relationship] = []

    for trello_list in snapshot.get("lists", []):
        list_id = f"list:{trello_list['id']}"
        nodes.append(
            GraphNode(
                id=list_id,
                name=trello_list["name"],
                node_type="system",
                trello_list_id=trello_list["id"],
                inferred=False,
            )
        )

    for card in snapshot.get("cards", []):
        card_node_id = f"card:{card['id']}"
        list_node_id = f"list:{card.get('list_id')}" if card.get("list_id") else None
        nodes.append(
            GraphNode(
                id=card_node_id,
                name=card["name"],
                node_type=_infer_task_type(card),
                description=card.get("desc") or None,
                due=card.get("due"),
                labels=card.get("labels", []),
                list_name=card.get("list_name"),
                trello_card_id=card["id"],
                trello_list_id=card.get("list_id"),
                inferred=False,
            )
        )
        if list_node_id:
            relationships.append(
                Relationship(
                    id=f"rel:{uuid.uuid4().hex[:12]}",
                    source_id=card_node_id,
                    target_id=list_node_id,
                    relationship_type="belongs_to",
                    confidence=1.0,
                    inferred=False,
                    reasoning="Card is on Trello list",
                )
            )

    return ProjectGraph(
        nodes=nodes,
        relationships=relationships,
        board_id=snapshot.get("board_id"),
    )


def enrich_graph_with_semantic_projects(graph: ProjectGraph) -> ProjectGraph:
    """Infer semantic project clusters and add project nodes + relationships."""
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    cards = [
        {
            "id": node.trello_card_id,
            "name": node.name,
            "description": node.description or "",
            "labels": node.labels,
            "list_name": node.list_name,
            "due": node.due,
        }
        for node in graph.tasks()
        if node.trello_card_id
    ]

    if not cards:
        return graph

    payload = {"cards": cards}
    prompt = INFER_PROJECTS_PROMPT.format(today=date.today().isoformat())

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
            ],
        )
    except GroqAPIError as exc:
        logger.exception("Project graph inference Groq API request failed")
        raise ProjectGraphError("Project graph inference unavailable") from exc

    raw = completion.choices[0].message.content
    if not raw:
        raise ProjectGraphError("Empty project graph inference response")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Invalid project graph inference payload: %s", raw)
        raise ProjectGraphError("Invalid project graph inference output") from exc

    project_id_by_name: dict[str, str] = {}
    new_nodes = list(graph.nodes)
    new_relationships = list(graph.relationships)

    for project in data.get("projects", []):
        name = project.get("name")
        if not name:
            continue
        project_id = f"project:{_slugify(name)}"
        project_id_by_name[name] = project_id
        new_nodes.append(
            GraphNode(
                id=project_id,
                name=name,
                node_type="project",
                area=project.get("area"),
                inferred=True,
            )
        )
        for card_id in project.get("member_card_ids", []):
            card_node_id = f"card:{card_id}"
            if not graph.node_by_id(card_node_id):
                continue
            new_relationships.append(
                Relationship(
                    id=f"rel:{uuid.uuid4().hex[:12]}",
                    source_id=card_node_id,
                    target_id=project_id,
                    relationship_type="belongs_to",
                    confidence=0.85,
                    inferred=True,
                    reasoning=project.get("reasoning", "Semantic project cluster"),
                )
            )

    for rel in data.get("relationships", []):
        source_card_id = rel.get("source_card_id")
        target_name = rel.get("target_project_name")
        if not source_card_id or not target_name:
            continue
        project_id = project_id_by_name.get(target_name, f"project:{_slugify(target_name)}")
        if project_id not in project_id_by_name:
            project_id_by_name[target_name] = project_id
            new_nodes.append(
                GraphNode(
                    id=project_id,
                    name=target_name,
                    node_type="project",
                    inferred=True,
                )
            )
        source_id = f"card:{source_card_id}"
        if not graph.node_by_id(source_id):
            continue
        new_relationships.append(
            Relationship(
                id=f"rel:{uuid.uuid4().hex[:12]}",
                source_id=source_id,
                target_id=project_id,
                relationship_type=rel.get("relationship_type", "belongs_to"),
                confidence=float(rel.get("confidence", 0.7)),
                inferred=True,
                reasoning=rel.get("reasoning", ""),
            )
        )

    enriched = ProjectGraph(
        nodes=new_nodes,
        relationships=new_relationships,
        board_id=graph.board_id,
    )
    logger.info(
        "project graph enriched projects=%d relationships=%d",
        len(enriched.projects()),
        len(enriched.relationships),
    )
    return enriched


def resolve_project_for_input(text: str, graph: ProjectGraph) -> ProjectResolution:
    """Resolve which project an input belongs to using the project graph."""
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    payload = {
        "input": text.strip(),
        "graph": graph.to_summary(),
    }
    prompt = RESOLVE_PROJECT_PROMPT.format(today=date.today().isoformat())

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
            ],
        )
    except GroqAPIError as exc:
        logger.exception("Project resolution Groq API request failed")
        raise ProjectGraphError("Project resolution unavailable") from exc

    raw = completion.choices[0].message.content
    if not raw:
        raise ProjectGraphError("Empty project resolution response")

    try:
        resolution = ProjectResolution.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Invalid project resolution payload: %s", raw)
        raise ProjectGraphError("Invalid project resolution output") from exc

    logger.info(
        "project resolution project=%r matched_node=%s confidence=%.2f action=%s area=%s target_list=%s reasoning=%s",
        resolution.project_name,
        resolution.matched_node_id,
        resolution.confidence,
        resolution.suggested_action,
        resolution.area,
        resolution.target_list,
        resolution.reasoning,
    )
    return resolution
