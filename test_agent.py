"""Quick checks for the agent, without the server or an API key.

Run: python test_agent.py
Uses a throwaway database so it never touches your real todos/notes.
"""
import os

os.environ["AGENT_DB"] = "/tmp/test_task_agent.db"
if os.path.exists("/tmp/test_task_agent.db"):
    os.remove("/tmp/test_task_agent.db")

import agent

agent.init_db()

# 1. The demo parser turns plain English into the right plans
plan = agent.fallback_plan("Add a todo to study for my CS4680 exam and save a note that the exam covers chapters 4 to 6")
assert plan["actions"][0] == {"action": "create_todo", "title": "Study for my CS4680 exam"}, plan
assert plan["actions"][1]["action"] == "create_note", plan

plan = agent.fallback_plan("What is 15 percent of 240?")
assert plan["actions"][0]["action"] == "calculate", plan

# 2. Validation rejects actions that are not on the whitelist
actions, error = agent.validate_plan({"actions": [{"action": "run_command", "command": "rm -rf /"}]})
assert actions is None and "Unknown action" in error, error

# 3. Executing a plan really changes the database
actions, error = agent.validate_plan({"actions": [
    {"action": "create_todo", "title": "Study for my CS4680 exam"},
    {"action": "calculate", "expression": "240 * 0.15"},
]})
results = agent.execute_plan("test request", actions)
assert results[0]["status"] == "done" and "Added todo #1" in results[0]["message"], results
assert results[1]["message"] == "240 * 0.15 = 36", results
assert agent.get_state()["todos"][0]["title"] == "Study for my CS4680 exam"

# 4. A delete is flagged as needing confirmation
actions, error = agent.validate_plan({"actions": [{"action": "delete_todo", "id": 1}]})
assert agent.needs_confirmation(actions) is True

# 5. Everything got logged
assert len(agent.get_state()["logs"]) >= 2

print("All checks passed")
