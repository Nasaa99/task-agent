# TaskAgent

A simple AI agent that turns plain English requests into real actions. Built with Python, Flask, SQLite, and the Gemini API for CS4680 Prompt Engineering (Assignment 4: AI Agent Project).

## The Problem

Keeping track of small tasks usually means opening three different apps: one for a to-do list, one for notes, and a calculator for quick math. It is a small thing, but the switching adds up, and a normal to-do app cannot understand a sentence like "remind me to study for my exam and save a note that it covers chapters 4 to 6" and do both parts at once.

TaskAgent takes one natural language request, has an LLM turn it into a short plan of actions, checks the plan for safety, and then actually runs it.

## What It Can Do

| Action | What happens |
| --- | --- |
| create_todo | Adds a to-do item |
| list_todos | Shows all to-dos |
| complete_todo | Marks a to-do as done |
| delete_todo | Deletes a to-do (asks for confirmation first) |
| create_note | Saves a note |
| list_notes | Shows all notes |
| delete_note | Deletes a note (asks for confirmation first) |
| calculate | Does math with a safe expression checker, never `eval` |
| word_count | Counts the words in a piece of text |
| get_datetime | Tells the current date and time |

## How It Works

The project is split into the three parts the assignment asks for:

1. **LLM Integration Module** (`llm.py`)
   Connects to the Gemini API, fills in the prompt template, and asks for the plan in JSON mode. If Gemini returns a 429 (rate limit) or 503 (model busy), it retries, then tries a backup model once. If there is no API key or the API is down, the app falls back to a small rule-based parser in `agent.py` so it can always be tried and demoed. The UI shows which one made the plan.

2. **Action Interpreter / Executor** (`agent.py`)
   Parses the plan JSON, validates it, and runs each action against a SQLite database. Results are shown back to the user one by one, so a plan that partly fails still reports what worked.

3. **User Interface** (`app.py`, `templates/`, `static/`)
   A simple web page: type a request, see what happened, and see your current todos, notes, and recent activity update on the same page.

This follows the pattern from Lecture 12: the LLM is the **brain**, and the executor is the **actor** that turns the model's text output into real actions. The JSON plan is the command language between them, the same role the DSL plays in the lecture's file organizer: a small fixed set of commands, where each action maps to exactly one executor function. Like in the lecture, the app also sends the model a summary of the current state (my todos and notes, with ids) so its commands refer to real things, and it stops to ask before doing anything destructive.

## Prompt Engineering

The prompt lives in `prompts/agent_prompt.txt`. It uses:

- **Persona:** the model is told it is TaskAgent, a planner that only outputs plans and never runs anything itself.
- **Template / structured output:** the model must answer in one fixed JSON shape, `{"actions": [...]}`, with Gemini's JSON mode on as a backup, so the app can parse every response the same way.
- **Few-shot examples:** three request-to-plan examples, including one where the model has to find the right todo id from the current list instead of guessing.
- **Context in the prompt:** the current todos and notes (with ids) are pasted into the prompt, so requests like "delete the todo about groceries" resolve to a real id.
- **Rules as guardrails:** only the 10 allowed actions, at most 5 actions per plan, never invent ids, and return an empty plan for anything it cannot do.

The important lesson from testing: the LLM output is never trusted directly. The app re-checks every plan against a whitelist before running it, which is what makes the agent safe to let act.

## Error Handling and Safety

- **Whitelist validation:** every action, field, and type is checked before execution. Unknown actions (for example, if the model ever suggested running a system command) are rejected and logged.
- **Confirmation for destructive actions:** if a plan contains a delete, nothing runs until the user reviews the plan and clicks confirm.
- **Safe math:** calculations are solved by walking the parsed expression tree with only `+ - * / % **` allowed. No `eval`, no code execution.
- **Graceful errors:** a bad id, an unsupported request, or a down API all return a plain message in the UI instead of crashing.
- **Audit log:** every action (and every rejected plan) is written to `agent.log` and to an `action_log` table, and the last 8 entries show in the UI under Recent activity.

## How to Run

**1. Get a Gemini API key** (optional, the app works without one in demo mode)

Go to [Google AI Studio](https://aistudio.google.com/apikey), sign in, and click **Create API key**.

**2. Set up the project**

Requires Python 3.9 or newer.

```bash
git clone https://github.com/Nasaa99/task-agent.git
cd task-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Create the `.env` file**

Create a file named `.env` in the project folder with your key:

```
GEMINI_API_KEY=your_key_here
```

`.env` is in `.gitignore`, so your key is never committed.

**4. Start the app**

```bash
python app.py
```

Open http://localhost:5002 in your browser.

## Requests to Try

- `Add a todo to study for my CS4680 exam and save a note that the exam covers chapters 4 to 6`
- `What is 15 percent of 240?`
- `Show my todos`
- `Complete todo 1`
- `Delete todo 1` (watch it stop and ask for confirmation)
- `Book me a flight to Hawaii` (not an allowed action, so it is rejected)

`sample_output.json` is a real response captured from the first request above.

## Testing

```bash
python test_agent.py
```

This checks the parser, the whitelist validation (including rejecting a fake `run_command` action), plan execution, the delete confirmation flag, and the logging, all against a throwaway database.

## Deploy on Render

This repo includes a `render.yaml`, so deployment is a few clicks:

1. Push the repo to GitHub.
2. On [Render](https://render.com), choose **New > Blueprint** and select this repo.
3. Add your `GEMINI_API_KEY` when Render asks for it (it is marked `sync: false`, so it is never stored in the repo).
4. Render builds and gives you a public URL. Without a key the deployed app still runs in demo mode.

Note: on Render's free tier the SQLite file resets when the service restarts, so todos and notes do not persist forever. That is fine for a demo.
