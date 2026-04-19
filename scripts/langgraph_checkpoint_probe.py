"""Small helper to inspect LangGraph interrupt/checkpoint behaviour locally."""

from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver


class S(TypedDict):
    x: int


def a(state: S):
    return {"x": 1}


def review(state: S):
    val = interrupt({"stage": "x", "message": "demo"})
    return Command(goto="done") if val == "go" else Command(goto="done")


def done(state: S):
    return {"x": 2}


builder = StateGraph(S)
builder.add_node("a", a)
builder.add_node("review", review)
builder.add_node("done", done)
builder.set_entry_point("a")
builder.add_edge("a", "review")
builder.add_edge("done", END)
graph = builder.compile(checkpointer=MemorySaver())
config = {"configurable": {"thread_id": "t1"}}

out = graph.invoke({"x": 0}, config=config)
print("invoke_out", out)
snap = graph.get_state(config)
print("snapshot_type", type(snap))
print("values", snap.values)
print("next", snap.next)
print("config", snap.config)
print("interrupts", snap.interrupts)
print("interrupt_type", type(snap.interrupts[0]) if snap.interrupts else None)
if snap.interrupts:
    intr = snap.interrupts[0]
    print("interrupt_dir", [a for a in dir(intr) if not a.startswith('_')])
    print("interrupt_repr", intr)
    print("interrupt_value", getattr(intr, 'value', None))
res = graph.invoke(Command(resume="go"), config=config)
print("resume_out", res)
snap2 = graph.get_state(config)
print("values2", snap2.values)
print("next2", snap2.next)
print("interrupts2", snap2.interrupts)


