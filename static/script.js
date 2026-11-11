const form = document.getElementById("agent-form");
const input = document.getElementById("request");
const runBtn = document.getElementById("run-btn");
const statusEl = document.getElementById("status");
const confirmBox = document.getElementById("confirm-box");
const confirmText = document.getElementById("confirm-text");
const resultsSection = document.getElementById("results-section");
const resultsEl = document.getElementById("results");

let pendingPlan = null;
let pendingRequest = "";

function renderState(state) {
  const todos = document.getElementById("todos");
  todos.innerHTML = state.todos.length
    ? state.todos.map(t => `<li class="${t.done ? "done-item" : ""}">#${t.id} ${t.title}</li>`).join("")
    : '<li class="empty">No todos yet</li>';

  const notes = document.getElementById("notes");
  notes.innerHTML = state.notes.length
    ? state.notes.map(n => `<li>#${n.id} <b>${n.title}</b>: ${n.content}</li>`).join("")
    : '<li class="empty">No notes yet</li>';

  const logs = document.getElementById("logs");
  logs.innerHTML = state.logs.length
    ? state.logs.map(l => `<li>${l.time} - ${l.action} (${l.status}): ${l.detail}</li>`).join("")
    : '<li class="empty">Nothing yet</li>';
}

function showResults(results) {
  resultsSection.classList.remove("hidden");
  resultsEl.innerHTML = results.map(r =>
    `<li class="${r.status === "error" ? "result-error" : ""}">${r.action}: ${r.message}</li>`).join("");
}

async function loadState() {
  const res = await fetch("/api/state");
  renderState(await res.json());
}

async function sendRequest(body) {
  const res = await fetch("/api/agent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;

  runBtn.disabled = true;
  confirmBox.classList.add("hidden");
  resultsSection.classList.add("hidden");
  statusEl.textContent = "Planning...";

  const data = await sendRequest({ request: text });
  runBtn.disabled = false;

  if (data.error) {
    statusEl.textContent = "Error: " + data.error;
    loadState();
    return;
  }
  if (data.needs_confirmation) {
    pendingPlan = data.plan;
    pendingRequest = text;
    const steps = data.plan.actions.map(a => a.action).join(", ");
    confirmText.textContent = data.message + " Plan: " + steps;
    confirmBox.classList.remove("hidden");
    statusEl.textContent = "Waiting for your confirmation (plan by " + data.source + ")";
    return;
  }
  statusEl.textContent = "Done. Plan by " + data.source;
  showResults(data.results);
  renderState(data.state);
});

document.getElementById("confirm-btn").addEventListener("click", async () => {
  confirmBox.classList.add("hidden");
  statusEl.textContent = "Running confirmed plan...";
  const data = await sendRequest({ request: pendingRequest, plan: pendingPlan, confirmed: true });
  pendingPlan = null;
  if (data.error) {
    statusEl.textContent = "Error: " + data.error;
    return;
  }
  statusEl.textContent = "Done";
  showResults(data.results);
  renderState(data.state);
});

document.getElementById("cancel-btn").addEventListener("click", () => {
  confirmBox.classList.add("hidden");
  pendingPlan = null;
  statusEl.textContent = "Cancelled. Nothing was run.";
});

document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => {
    input.value = chip.textContent;
    input.focus();
  });
});

loadState();
