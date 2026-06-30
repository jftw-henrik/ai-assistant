from typing import Literal

from pydantic import BaseModel, Field

from app.models.brain import Area

NodeType = Literal[
    "project",
    "subproject",
    "task",
    "idea",
    "deadline",
    "contact",
    "system",
]

RelationshipType = Literal[
    "belongs_to",
    "blocks",
    "depends_on",
    "duplicates",
    "follows_up",
    "related_to",
]

ProjectResolutionAction = Literal[
    "update_existing",
    "create_task_under_project",
    "create_new_project",
    "ask_clarification",
]


class GraphNode(BaseModel):
    id: str
    name: str
    node_type: NodeType
    description: str | None = None
    due: str | None = None
    labels: list[str] = Field(default_factory=list)
    list_name: str | None = None
    trello_card_id: str | None = None
    trello_list_id: str | None = None
    area: Area | None = None
    inferred: bool = False


class ProjectNode(GraphNode):
    node_type: Literal["project", "subproject"] = "project"


class TaskNode(GraphNode):
    node_type: Literal["task", "idea", "deadline", "contact", "system"] = "task"


class Relationship(BaseModel):
    id: str
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    inferred: bool = False
    reasoning: str = ""


class ProjectGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    board_id: str | None = None

    def node_by_id(self, node_id: str) -> GraphNode | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def projects(self) -> list[GraphNode]:
        return [node for node in self.nodes if node.node_type in {"project", "subproject"}]

    def tasks(self) -> list[GraphNode]:
        return [node for node in self.nodes if node.node_type not in {"project", "subproject", "system"}]

    def to_summary(self) -> dict:
        return {
            "projects": [
                {
                    "id": node.id,
                    "name": node.name,
                    "area": node.area,
                    "inferred": node.inferred,
                }
                for node in self.projects()
            ],
            "tasks": [
                {
                    "id": node.id,
                    "name": node.name,
                    "node_type": node.node_type,
                    "list_name": node.list_name,
                    "labels": node.labels,
                    "trello_card_id": node.trello_card_id,
                    "project_ids": [
                        rel.target_id
                        for rel in self.relationships
                        if rel.source_id == node.id
                        and rel.relationship_type == "belongs_to"
                        and rel.target_id.startswith("project:")
                    ],
                }
                for node in self.tasks()
            ],
            "relationships": [
                {
                    "source_id": rel.source_id,
                    "target_id": rel.target_id,
                    "type": rel.relationship_type,
                    "inferred": rel.inferred,
                }
                for rel in self.relationships
            ],
        }


class ProjectResolution(BaseModel):
    project_name: str
    matched_node_id: str | None = None
    matched_card_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    reasoning: str = ""
    suggested_action: ProjectResolutionAction = "create_task_under_project"
    area: Area | None = None
    target_list: str | None = None
