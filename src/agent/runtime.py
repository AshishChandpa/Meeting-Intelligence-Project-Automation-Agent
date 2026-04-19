"""Runtime helpers for executing the LangGraph workflow with checkpoints and progress events."""

from __future__ import annotations

import time
from typing import Any, Callable

from langchain_core.messages import BaseMessage
from langgraph.types import Command, StateSnapshot

from agent.checkpoints import create_checkpointer
from agent.config import settings
from agent.graph import build_graph
from agent.streaming import emit_stream_event, use_stream_callback

RuntimeCallback = Callable[[str, dict[str, Any]], None]

NODE_PROGRESS = {
    "parse_transcript": 15,
    "review_extraction": 20,
    "apply_corrections": 25,
    "generate_questions": 35,
    "review_clarification": 40,
    "process_answer": 45,
    "draft_sow": 60,
    "review_sow": 65,
    "revise_sow": 70,
    "generate_sprint_plan": 82,
    "review_sprint": 86,
    "adjust_sprint_plan": 88,
    "review_jira": 95,
    "sync_to_jira": 100,
}

checkpointer = create_checkpointer(settings)
graph = build_graph(checkpointer=checkpointer)


def thread_config(project_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": project_id}}


def _message_preview(value: Any) -> str:
    if isinstance(value, BaseMessage):
        return str(value.content)[:180]
    if isinstance(value, list) and value:
        head = value[0]
        if isinstance(head, BaseMessage):
            return str(head.content)[:180]
    return ""


def _interrupt_payload(snapshot: StateSnapshot) -> list[dict[str, Any]]:
    payloads = []
    for interrupt in getattr(snapshot, "interrupts", ()) or ():
        value = interrupt.value
        if isinstance(value, dict):
            payload = dict(value)
        else:
            payload = {"message": str(value)}
        payload["interrupt_id"] = getattr(interrupt, "id", None) or getattr(interrupt, "interrupt_id", None)
        payloads.append(payload)
    return payloads


def snapshot_to_runtime_meta(snapshot: StateSnapshot) -> dict[str, Any]:
    configurable = getattr(snapshot, "config", {}).get("configurable", {})
    return {
        "graph_checkpoint_id": configurable.get("checkpoint_id"),
        "graph_next_nodes": list(getattr(snapshot, "next", ()) or ()),
        "pending_interrupts": _interrupt_payload(snapshot),
        "last_checkpoint_at": time.time(),
    }


def sync_project_with_graph(project: dict[str, Any]) -> dict[str, Any]:
    snapshot = graph.get_state(thread_config(project["id"]))
    project["state"].update(dict(snapshot.values))
    project["state"].update(snapshot_to_runtime_meta(snapshot))
    return project


def run_graph(project_id: str, *, initial_state: dict[str, Any] | None = None, resume_value: Any | None = None, callback: RuntimeCallback | None = None) -> StateSnapshot:
    config = thread_config(project_id)
    input_value: Any = initial_state if initial_state is not None else Command(resume=resume_value)

    with use_stream_callback(callback):
        emit_stream_event(
            "stage_progress",
            {
                "message": "Running workflow...",
                "progress": 5,
                "project_id": project_id,
            },
        )
        for chunk in graph.stream(input_value, config=config, stream_mode="updates"):
            if not isinstance(chunk, dict):
                continue
            for node_name, update in chunk.items():
                payload = update if isinstance(update, dict) else {"value": str(update)}
                emit_stream_event(
                    "graph_node_finished",
                    {
                        "project_id": project_id,
                        "node": node_name,
                        "stage": payload.get("current_stage"),
                        "message": _message_preview(payload.get("messages")) or f"Node {node_name} completed",
                        "progress": NODE_PROGRESS.get(node_name),
                    },
                )

    snapshot = graph.get_state(config)
    emit_stream_event(
        "checkpoint_saved",
        {
            "project_id": project_id,
            **snapshot_to_runtime_meta(snapshot),
        },
    )
    interrupts = _interrupt_payload(snapshot)
    if interrupts:
        emit_stream_event(
            "interrupt",
            {
                "project_id": project_id,
                "current_stage": dict(snapshot.values).get("current_stage"),
                "interrupts": interrupts,
                "message": interrupts[0].get("message", "Awaiting human input"),
            },
        )
    return snapshot


def update_graph_state(project_id: str, values: dict[str, Any], *, as_node: str | None = None) -> dict[str, Any]:
    graph.update_state(thread_config(project_id), values, as_node=as_node)
    snapshot = graph.get_state(thread_config(project_id))
    return snapshot_to_runtime_meta(snapshot)


def delete_graph_thread(project_id: str) -> None:
    delete_thread = getattr(checkpointer, "delete_thread", None)
    if callable(delete_thread):
        delete_thread(project_id)

