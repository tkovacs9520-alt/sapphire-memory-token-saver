
ENABLED = True
EMOJI = '🧠'

AVAILABLE_FUNCTIONS = ['session_log', 'session_summarize', 'session_commit', 'session_status']

SETTINGS = {
    'PIPELINE_SUMMARIZE_THRESHOLD': 10,
    'PIPELINE_MAX_NOTE_LENGTH': 500,
}
SETTINGS_HELP = {
    'PIPELINE_SUMMARIZE_THRESHOLD': 'Number of turns before triggering a summarize reminder (default 10)',
    'PIPELINE_MAX_NOTE_LENGTH': 'Max character length for each turn note (default 500)',
}

TOOLS = [
    {
        "type": "function",
        "is_local": True,
        "function": {
            "name": "session_log",
            "description": "Log a condensed turn summary to the session buffer. Call ONCE per complete exchange — after the user's message and your FULL response (including all tool calls) are finished. Do NOT call mid-response, mid-tool-chain, or multiple times per turn. One exchange = one log entry. Keep notes tight: decisions, entities, action items, open threads. Drop pleasantries and filler.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note": {
                        "type": "string",
                        "description": "Condensed 1-3 sentence summary of what happened this exchange"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session identifier for isolation. Defaults to 'default'. Use chat name or topic slug."
                    }
                },
                "required": ["note"]
            }
        }
    },
    {
        "type": "function",
        "is_local": True,
        "function": {
            "name": "session_summarize",
            "description": "Store a compressed summary of the session so far. Call when session_log signals threshold reached, or manually anytime. YOU write the summary from the buffer — aggressive compression. This REPLACES the previous summary, it does not accumulate. Clears the turn buffer after saving.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Your aggressively compressed summary. Keep: key entities, decisions made, action items, unresolved threads, important context. Drop: greetings, repetition, tangents, filler."
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session identifier. Defaults to 'default'."
                    }
                },
                "required": ["summary"]
            }
        }
    },
    {
        "type": "function",
        "is_local": True,
        "function": {
            "name": "session_commit",
            "description": "Push the current session summary into long-term knowledge for persistent cross-persona access. Call when user types /commit. Returns formatted content — you MUST then call save_knowledge(category='session_memory', content=<returned content>) to complete the commit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session identifier. Defaults to 'default'."
                    },
                    "tag": {
                        "type": "string",
                        "description": "Topic tag for retrieval (e.g. 'marketing-strategy', 'subcontractor-vetting')"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "is_local": True,
        "function": {
            "name": "session_status",
            "description": "Check the current state of a session buffer — turn count, whether a summary exists, pending turns, last activity. Use to orient after a chat reset or when resuming work.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session identifier. Defaults to 'default'."
                    }
                },
                "required": []
            }
        }
    }
]

import json
import os
from datetime import datetime

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(PLUGIN_DIR, 'sessions')


def _ensure_dirs():
    os.makedirs(SESSION_DIR, exist_ok=True)


def _safe_id(session_id):
    return "".join(c if c.isalnum() or c in '-_' else '_' for c in session_id)


def _session_path(session_id):
    return os.path.join(SESSION_DIR, f"{_safe_id(session_id)}.json")


def _load_session(session_id):
    path = _session_path(session_id)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "session_id": session_id,
        "created": datetime.now().isoformat(),
        "turns": [],
        "turn_count": 0,
        "total_turns_ever": 0,
        "summary": None,
        "last_summarized_at": None,
        "last_committed_at": None
    }


def _save_session(session_id, data):
    _ensure_dirs()
    path = _session_path(session_id)
    data["last_updated"] = datetime.now().isoformat()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _list_sessions():
    _ensure_dirs()
    sessions = []
    for fname in os.listdir(SESSION_DIR):
        if fname.endswith('.json'):
            fpath = os.path.join(SESSION_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                sessions.append({
                    "id": data.get("session_id", fname.replace('.json', '')),
                    "turns": data.get("turn_count", 0),
                    "has_summary": data.get("summary") is not None,
                    "updated": data.get("last_updated", "unknown")
                })
            except (json.JSONDecodeError, KeyError):
                pass
    return sessions


def execute(function_name, arguments, config, plugin_settings=None):
    _ensure_dirs()
    settings = plugin_settings or {}
    threshold = int(settings.get('PIPELINE_SUMMARIZE_THRESHOLD', 10))
    max_note = int(settings.get('PIPELINE_MAX_NOTE_LENGTH', 500))

    # ── SESSION_LOG ──────────────────────────────────────────
    if function_name == 'session_log':
        note = arguments.get('note', '').strip()
        session_id = arguments.get('session_id', 'default').strip()

        if not note:
            return "Error: note cannot be empty.", False

        if len(note) > max_note:
            note = note[:max_note] + "..."

        session = _load_session(session_id)

        turn_entry = {
            "turn": session["turn_count"] + 1,
            "ts": datetime.now().strftime('%H:%M'),
            "note": note
        }

        session["turns"].append(turn_entry)
        session["turn_count"] += 1
        session["total_turns_ever"] = session.get("total_turns_ever", 0) + 1
        _save_session(session_id, session)

        count = session["turn_count"]
        turns_since = count % threshold

        if turns_since == 0 and count > 0:
            buffer_text = "\n".join(
                f"[{t['turn']}] ({t['ts']}) {t['note']}" for t in session['turns']
            )
            existing_summary = session.get("summary", "")
            summary_block = ""
            if existing_summary:
                summary_block = f"\n--- EXISTING SUMMARY ---\n{existing_summary}\n--- END EXISTING SUMMARY ---\n"

            return (
                f"Turn {count} logged [{session_id}]. "
                f"SUMMARIZE NOW — {threshold}-turn threshold reached.\n"
                f"{summary_block}"
                f"\n--- TURN BUFFER ({len(session['turns'])} turns) ---\n"
                f"{buffer_text}\n"
                f"--- END BUFFER ---\n\n"
                f"Compress everything above (existing summary + new turns) into one tight summary. "
                f"Call session_summarize now.",
                True
            )
        else:
            remaining = threshold - turns_since
            return (
                f"Turn {count} logged [{session_id}]. "
                f"({remaining} until next summarize cycle)"
                + (f" | Summary active: {len(session.get('summary', '') or '')} chars" if session.get('summary') else ""),
                True
            )

    # ── SESSION_SUMMARIZE ────────────────────────────────────
    elif function_name == 'session_summarize':
        summary = arguments.get('summary', '').strip()
        session_id = arguments.get('session_id', 'default').strip()

        if not summary:
            return "Error: summary cannot be empty.", False

        session = _load_session(session_id)
        cleared_count = len(session.get("turns", []))
        session["summary"] = summary
        session["last_summarized_at"] = datetime.now().isoformat()
        session["turns"] = []
        session["turn_count"] = 0
        _save_session(session_id, session)

        return (
            f"Summary saved [{session_id}]. {cleared_count} turns cleared from buffer. "
            f"Summary: {len(summary)} chars. "
            f"Total session turns: {session.get('total_turns_ever', 0)}. "
            f"Buffer reset to 0. Ready for next cycle.\n"
            f"Type /commit when ready to push to long-term memory.",
            True
        )

    # ── SESSION_COMMIT ───────────────────────────────────────
    elif function_name == 'session_commit':
        session_id = arguments.get('session_id', 'default').strip()
        tag = arguments.get('tag', '').strip()

        session = _load_session(session_id)

        summary = session.get("summary")
        pending = session.get("turns", [])

        if not summary and not pending:
            return "Nothing to commit. No summary and no pending turns in this session.", False

        parts = []
        parts.append(f"# Session: {session_id}")
        parts.append(f"Committed: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        parts.append(f"Total turns: {session.get('total_turns_ever', 0)}")
        if tag:
            parts.append(f"Tag: {tag}")
        parts.append("")

        if summary:
            parts.append(f"## Summary\n{summary}")

        if pending:
            parts.append(f"\n## Pending turns ({len(pending)})")
            for t in pending:
                parts.append(f"[{t['turn']}] ({t.get('ts', '?')}) {t['note']}")

        commit_content = "\n".join(parts)

        session["last_committed_at"] = datetime.now().isoformat()
        session["summary"] = None
        session["turns"] = []
        session["turn_count"] = 0
        session["total_turns_ever"] = 0
        _save_session(session_id, session)

        return (
            f"SESSION READY FOR COMMIT [{session_id}].\n"
            f"Call save_knowledge(category='session_memory', content=<below>) now:\n\n"
            f"---COMMIT---\n{commit_content}\n---END COMMIT---",
            True
        )

    # ── SESSION_STATUS ───────────────────────────────────────
    elif function_name == 'session_status':
        session_id = arguments.get('session_id', '').strip()

        if session_id:
            session = _load_session(session_id)
            status_parts = [
                f"Session: {session['session_id']}",
                f"Created: {session.get('created', 'unknown')}",
                f"Pending turns: {len(session.get('turns', []))}",
                f"Turn count (this cycle): {session.get('turn_count', 0)}",
                f"Total turns (all time): {session.get('total_turns_ever', 0)}",
                f"Has summary: {'Yes (' + str(len(session['summary'])) + ' chars)' if session.get('summary') else 'No'}",
                f"Last summarized: {session.get('last_summarized_at', 'never')}",
                f"Last committed: {session.get('last_committed_at', 'never')}",
                f"Last updated: {session.get('last_updated', 'unknown')}",
            ]
            if session.get("turns"):
                status_parts.append(f"\nRecent turns:")
                for t in session["turns"][-5:]:
                    status_parts.append(f"  [{t['turn']}] ({t.get('ts', '?')}) {t['note']}")
            if session.get("summary"):
                preview = session["summary"][:200]
                if len(session["summary"]) > 200:
                    preview += "..."
                status_parts.append(f"\nSummary preview:\n{preview}")

            return "\n".join(status_parts), True
        else:
            sessions = _list_sessions()
            if not sessions:
                return "No active sessions found.", True
            lines = ["Active sessions:"]
            for s in sessions:
                summ_flag = " [has summary]" if s["has_summary"] else ""
                lines.append(f"  • {s['id']} — {s['turns']} pending turns{summ_flag} (updated: {s['updated']})")
            return "\n".join(lines), True

    return f"Unknown function: {function_name}", False
