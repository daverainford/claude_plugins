"""Shared helpers for the PostToolUse hook scripts. Standard library only."""
import json
import sys


def read_event():
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def file_path(event):
    return (event.get("tool_input") or {}).get("file_path", "") or ""


def written_text(event):
    """The text this tool call wrote: full content for Write, new strings for Edit/MultiEdit."""
    tool_input = event.get("tool_input") or {}
    if "content" in tool_input:
        return tool_input["content"] or ""
    if "new_string" in tool_input:
        return tool_input["new_string"] or ""
    return "\n\n".join(e.get("new_string", "") for e in tool_input.get("edits", []))


def emit(message):
    # additionalContext is injected into the model's context without blocking the tool call.
    json.dump(
        {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message}},
        sys.stdout,
    )
    sys.exit(0)
