"""Action interpreter / executor.

Takes a plan (from the LLM, or from the small rule-based demo parser below),
validates it against a whitelist of allowed actions, and executes the
actions in a SQLite database. Every action is logged for auditability.
Deleting is a destructive operation, so it only runs after the user
confirms it in the UI.
"""
import ast
import logging
import operator
import os
import re
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("AGENT_DB", os.path.join(BASE_DIR, "agent.db"))

logger = logging.getLogger("taskagent")
logger.setLevel(logging.INFO)
logger.propagate = False
_handler = logging.FileHandler(os.path.join(BASE_DIR, "agent.log"))
_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
logger.addHandler(_handler)

DESTRUCTIVE = {"delete_todo", "delete_note"}

# What each action is allowed to carry. Anything else is rejected.
ACTION_FIELDS = {
    "create_todo": {"title": str},
    "list_todos": {},
    "complete_todo": {"id": int},
    "delete_todo": {"id": int},
    "create_note": {"title": str, "content": str},
    "list_notes": {},
    "delete_note": {"id": int},
    "calculate": {"expression": str},
    "word_count": {"text": str},
    "get_datetime": {},
}


# ---------- storage ----------

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS todos "
                     "(id INTEGER PRIMARY KEY, title TEXT, done INTEGER DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS notes "
                     "(id INTEGER PRIMARY KEY, title TEXT, content TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS action_log "
                     "(id INTEGER PRIMARY KEY, time TEXT, request TEXT, "
                     "action TEXT, detail TEXT, status TEXT)")


def get_state():
    with connect() as conn:
        todos = [dict(r) for r in conn.execute("SELECT * FROM todos ORDER BY id")]
        notes = [dict(r) for r in conn.execute("SELECT * FROM notes ORDER BY id")]
        logs = [dict(r) for r in conn.execute(
            "SELECT time, action, detail, status FROM action_log ORDER BY id DESC LIMIT 8")]
    return {"todos": todos, "notes": notes, "logs": logs}


def state_as_text():
    state = get_state()
    todos = [{"id": t["id"], "title": t["title"]} for t in state["todos"]]
    notes = [{"id": n["id"], "title": n["title"]} for n in state["notes"]]
    return f"Current todos: {todos}\nCurrent notes: {notes}"


def log_action(request_text, action, detail, status):
    logger.info(f"request={request_text!r} action={action} detail={detail!r} status={status}")
    with connect() as conn:
        conn.execute(
            "INSERT INTO action_log (time, request, action, detail, status) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().strftime("%I:%M %p"), request_text, action, detail, status),
        )


# ---------- validation (safety) ----------

def validate_plan(plan):
    """Return (clean_actions, error). Rejects anything off the whitelist."""
    if not isinstance(plan, dict) or not isinstance(plan.get("actions"), list):
        return None, "Plan is not in the expected format"
    if len(plan["actions"]) == 0:
        return None, "I don't know how to do that with my available actions"
    if len(plan["actions"]) > 5:
        return None, "That plan has too many actions (max 5)"

    clean = []
    for step in plan["actions"]:
        if not isinstance(step, dict) or step.get("action") not in ACTION_FIELDS:
            return None, f"Unknown action: {step.get('action') if isinstance(step, dict) else step}"
        action = {"action": step["action"]}
        for field, field_type in ACTION_FIELDS[step["action"]].items():
            value = step.get(field)
            # bool is a subclass of int in Python, so check ids extra carefully
            if field_type is int and (not isinstance(value, int) or isinstance(value, bool)):
                return None, f"{step['action']} needs a numeric id"
            if field_type is str and (not isinstance(value, str) or not value.strip()):
                return None, f"{step['action']} needs a {field}"
            if field_type is str and len(value) > 500:
                return None, f"{field} is too long"
            action[field] = value.strip() if field_type is str else value
        clean.append(action)
    return clean, None


def needs_confirmation(actions):
    return any(a["action"] in DESTRUCTIVE for a in actions)


# ---------- safe calculator (no eval) ----------

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
       ast.USub: operator.neg}


def safe_calculate(expression):
    def solve(node):
        if isinstance(node, ast.Expression):
            return solve(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            if isinstance(node.op, ast.Pow) and abs(solve(node.right)) > 10:
                raise ValueError("Exponent too big")
            return OPS[type(node.op)](solve(node.left), solve(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
            return OPS[type(node.op)](solve(node.operand))
        raise ValueError("Not a plain math expression")

    return solve(ast.parse(expression, mode="eval"))


# ---------- executor ----------

def run_action(action):
    """Run one validated action. Returns a result message for the user."""
    name = action["action"]
    with connect() as conn:
        if name == "create_todo":
            cur = conn.execute("INSERT INTO todos (title) VALUES (?)", (action["title"],))
            return f"Added todo #{cur.lastrowid}: {action['title']}"
        if name == "list_todos":
            rows = conn.execute("SELECT * FROM todos ORDER BY id").fetchall()
            if not rows:
                return "You have no todos"
            return "Todos: " + "; ".join(
                f"#{r['id']} {r['title']}" + (" (done)" if r["done"] else "") for r in rows)
        if name == "complete_todo":
            cur = conn.execute("UPDATE todos SET done = 1 WHERE id = ?", (action["id"],))
            if cur.rowcount == 0:
                raise ValueError(f"No todo with id {action['id']}")
            return f"Marked todo #{action['id']} as done"
        if name == "delete_todo":
            cur = conn.execute("DELETE FROM todos WHERE id = ?", (action["id"],))
            if cur.rowcount == 0:
                raise ValueError(f"No todo with id {action['id']}")
            return f"Deleted todo #{action['id']}"
        if name == "create_note":
            cur = conn.execute("INSERT INTO notes (title, content) VALUES (?, ?)",
                               (action["title"], action["content"]))
            return f"Saved note #{cur.lastrowid}: {action['title']}"
        if name == "list_notes":
            rows = conn.execute("SELECT * FROM notes ORDER BY id").fetchall()
            if not rows:
                return "You have no notes"
            return "Notes: " + "; ".join(f"#{r['id']} {r['title']}" for r in rows)
        if name == "delete_note":
            cur = conn.execute("DELETE FROM notes WHERE id = ?", (action["id"],))
            if cur.rowcount == 0:
                raise ValueError(f"No note with id {action['id']}")
            return f"Deleted note #{action['id']}"
        if name == "calculate":
            result = safe_calculate(action["expression"])
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            return f"{action['expression']} = {result}"
        if name == "word_count":
            return f"That text has {len(action['text'].split())} words"
        if name == "get_datetime":
            return "It is " + datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    raise ValueError(f"Unknown action: {name}")


def execute_plan(request_text, actions):
    results = []
    for action in actions:
        try:
            message = run_action(action)
            results.append({"action": action["action"], "status": "done", "message": message})
            log_action(request_text, action["action"], message, "done")
        except Exception as e:
            results.append({"action": action["action"], "status": "error", "message": str(e)})
            log_action(request_text, action["action"], str(e), "error")
    return results


# ---------- demo parser ----------
# Used only when there is no API key (or the API is down), so the app can
# always be tried and demoed. Handles the simple, common requests.

def _clean(text):
    return text.strip().strip(".").strip()


def _cap(text):
    # Capitalize the first letter only, so "CS4680" stays "CS4680"
    return text[:1].upper() + text[1:] if text else text


def _todo_title(part):
    for prefix in ("add a todo to ", "add todo to ", "add a task to ", "add task to ",
                   "remind me to ", "add a todo ", "add todo "):
        if part.lower().startswith(prefix):
            part = part[len(prefix):]
            break
    return _cap(_clean(part))


def fallback_plan(request_text):
    text = request_text.strip()
    low = text.lower()
    actions = []

    m = re.search(r"delete (?:todo|task) (?:#|number )?(\d+)", low)
    if m:
        return {"actions": [{"action": "delete_todo", "id": int(m.group(1))}]}
    m = re.search(r"delete note (?:#|number )?(\d+)", low)
    if m:
        return {"actions": [{"action": "delete_note", "id": int(m.group(1))}]}
    m = re.search(r"(?:complete|finish|check off|mark done) (?:todo|task) (?:#|number )?(\d+)", low)
    if m:
        return {"actions": [{"action": "complete_todo", "id": int(m.group(1))}]}
    if "what time" in low or "what day" in low or "today's date" in low:
        return {"actions": [{"action": "get_datetime"}]}

    m = re.search(r"([\d.]+)\s*(?:percent|%) of ([\d.]+)", low)
    if m:
        return {"actions": [{"action": "calculate",
                              "expression": f"{m.group(2)} * {float(m.group(1)) / 100}"}]}
    m = re.search(r"(?:calculate|what is|how much is)\s+([\d\s\.\+\-\*/\(\)%]+)\??$", low)
    if m and any(op in m.group(1) for op in "+-*/%"):
        return {"actions": [{"action": "calculate", "expression": m.group(1).strip()}]}

    if "count the words" in low or low.startswith("word count"):
        words = text.split(":", 1)[-1] if ":" in text else text
        return {"actions": [{"action": "word_count", "text": _clean(words)}]}

    # Requests joined by "and": handle one todo and/or one note per part.
    # Checks run on the lowercase copy, but titles keep the original casing.
    original_parts = re.split(r"\s+and\s+", text)
    for part, original in zip(low.split(" and "), original_parts):
        part = part.strip()
        original = original.strip()
        if "list" in part or "show" in part:
            if "note" in part:
                actions.append({"action": "list_notes"})
            elif "todo" in part or "task" in part:
                actions.append({"action": "list_todos"})
        elif "note" in part:
            content = original
            for prefix in ("save a note that ", "add a note that ", "save a note ",
                           "add a note ", "note that ", "note "):
                if content.lower().startswith(prefix):
                    content = content[len(prefix):]
                    break
            actions.append({"action": "create_note", "title": "Note",
                            "content": _cap(_clean(content))})
        elif "todo" in part or "task" in part or "remind me" in part:
            actions.append({"action": "create_todo", "title": _todo_title(original)})

    return {"actions": actions}
