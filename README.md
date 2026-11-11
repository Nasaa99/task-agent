# TaskAgent

A simple AI agent that turns plain English into real actions. You type one sentence, an LLM turns it into a short plan, the app checks the plan, then runs it. Built with Python, Flask, SQLite, and the Gemini API for CS4680 Prompt Engineering (Assignment 4).

Live demo: https://task-agent-9p7p.onrender.com

Note: the live demo runs on Render's free tier, so if it has been sitting idle it can take up to a minute to wake up on the first load. Just wait for it or refresh once.

## What it can do

- Todos: add, list, complete, delete
- Notes: save, list, delete
- Quick math (checked safely, never with eval)
- Word count and current date/time

Deletes always ask for confirmation first. One request can hold several actions, like "add a todo to study for my exam and save a note that it covers chapters 4 to 6".

## How it works

- `llm.py` sends the request to Gemini with the prompt in `prompts/agent_prompt.txt` and gets back a JSON plan. Temporary errors (429, 503, 504) are retried, then a backup model is tried. With no API key, a small rule-based parser takes over so the app still works, and the page shows which one made the plan.
- `agent.py` checks the plan against a whitelist of 10 allowed actions and runs it on a SQLite database. Every action is written to an activity log.
- `app.py` is the web page: type a request, see the results, your todos and notes, and recent activity.

The design follows Lecture 12: the LLM is the brain, the executor is the actor, and the JSON plan is the command language between them. The current todos and notes go into the prompt so the model uses real ids instead of guessing.

## Prompt engineering

The prompt uses a persona (a planner that only outputs plans), one fixed JSON shape, and three examples. Rules: only the 10 allowed actions, at most 5 actions per plan, never invent ids, return an empty plan for anything it cannot do. The app never trusts the model output, it re-checks every plan before running it.

## Safety

- Whitelist: unknown actions are rejected and logged
- Deletes stop and ask the user to confirm before anything runs
- Math is solved by walking the expression tree, no eval
- Errors show as plain messages in the page instead of crashing

## Run it locally

Needs Python 3.9 or newer.

```bash
git clone https://github.com/Nasaa99/task-agent.git
cd task-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5002 in your browser.

Optional: for real Gemini answers, get a free key at [Google AI Studio](https://aistudio.google.com/apikey) and put it in a `.env` file in the project folder:

```
GEMINI_API_KEY=your_key_here
```

Without a key the app runs in demo mode. Run the checks with `python test_agent.py`.

## Deploy

The repo has a `render.yaml`. On Render, choose New, then Blueprint, select this repo, set the service plan to free, and add your `GEMINI_API_KEY` as an environment variable. On the free tier the database resets when the service restarts, which is fine for a demo.
