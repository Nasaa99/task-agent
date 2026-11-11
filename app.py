"""TaskAgent - user interface (Flask web app).

The user types a natural language request. The LLM turns it into a plan,
the plan is validated, and the executor runs it. Plans that contain a
delete are sent back to the user for confirmation before anything runs.
"""
from flask import Flask, jsonify, render_template, request

import agent
import llm

app = Flask(__name__)
agent.init_db()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/state")
def state():
    return jsonify(agent.get_state())


@app.route("/api/agent", methods=["POST"])
def run_agent():
    data = request.get_json(force=True)
    request_text = (data.get("request") or "").strip()

    # Step 2 of the confirmation flow: the user confirmed a plan that
    # contains a delete, so validate it again and run it as-is.
    if data.get("confirmed") and data.get("plan"):
        actions, error = agent.validate_plan(data["plan"])
        if error:
            return jsonify({"error": error}), 400
        results = agent.execute_plan(request_text or "confirmed plan", actions)
        return jsonify({"results": results, "state": agent.get_state()})

    if not request_text:
        return jsonify({"error": "Type a request first"}), 400

    # 1. Get a plan: Gemini if a key is set, otherwise the demo parser
    plan, error = llm.get_plan(request_text, agent.state_as_text())
    source = "Gemini"
    if plan is None:
        print(f"LLM unavailable ({error}), using demo parser")
        plan = agent.fallback_plan(request_text)
        source = "demo parser (no API key or API down)"

    # 2. Validate the plan before anything runs
    actions, error = agent.validate_plan(plan)
    if error:
        agent.log_action(request_text, "validate", error, "rejected")
        return jsonify({"error": error, "source": source}), 400

    # 3. Safety check: deletes need the user's confirmation first
    if agent.needs_confirmation(actions):
        return jsonify({
            "needs_confirmation": True,
            "plan": {"actions": actions},
            "source": source,
            "message": "This plan deletes something. Review it and confirm to continue.",
        })

    # 4. Execute and report back
    results = agent.execute_plan(request_text, actions)
    return jsonify({"plan": {"actions": actions}, "results": results,
                    "source": source, "state": agent.get_state()})


if __name__ == "__main__":
    app.run(debug=True, port=5002)
