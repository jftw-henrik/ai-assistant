const input = document.getElementById("input");
const status = document.getElementById("status");
const statusIcon = document.getElementById("status-icon");
const submitHint = document.getElementById("submit-hint");
const panel = document.getElementById("panel");

const CAPTURE_TIMEOUT_MS = 10_000;
const SUCCESS_HIDE_MS = 700;

let captureUrl =
  "https://ai-assistant-production-45e5.up.railway.app/capture/async";
let isLoading = false;

function setStatus(text, kind = "default") {
  status.textContent = text;
  status.className = `status${kind === "default" ? "" : ` ${kind}`}`;
}

function hideStatusIcon() {
  statusIcon.className = "status-icon hidden";
  statusIcon.innerHTML = "";
}

function showCheckmark() {
  statusIcon.className = "status-icon checkmark";
  statusIcon.innerHTML = `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle class="checkmark-circle" cx="12" cy="12" r="10" />
      <path class="checkmark-path" d="M7 12.5l3 3 7-7" />
    </svg>
  `;
}

function setLoading(loading) {
  isLoading = loading;
  input.disabled = loading;
  submitHint.classList.toggle("hidden", loading);
  if (loading) {
    hideStatusIcon();
    setStatus("Sending…", "loading");
  }
}

function resetStatus() {
  hideStatusIcon();
  setStatus("Capture tasks, ideas, or deadlines.", "default");
}

function focusInput() {
  input.focus();
  const end = input.value.length;
  input.setSelectionRange(end, end);
}

function replayAnimation() {
  panel.style.animation = "none";
  panel.offsetHeight;
  panel.style.animation = "";
}

function formatError(err) {
  if (err?.name === "AbortError") {
    return "Request timed out. Could not reach server.";
  }
  if (err?.message) {
    return err.message;
  }
  return "Could not reach server.";
}

function isAcceptedResponse(response, body) {
  if (!response.ok) {
    return false;
  }
  if (body.startsWith("❌")) {
    return false;
  }
  return body === "Accepted" || body.startsWith("Accepted");
}

async function fetchCaptureAsync(text) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), CAPTURE_TIMEOUT_MS);

  try {
    const response = await fetch(captureUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });

    const body = (await response.text()).trim();
    return { response, body };
  } finally {
    clearTimeout(timeoutId);
  }
}

async function submit() {
  const text = input.value.trim();
  if (!text || isLoading) return;

  setLoading(true);

  try {
    const { response, body } = await fetchCaptureAsync(text);

    if (!isAcceptedResponse(response, body)) {
      const message = body || `Request failed (${response.status}).`;
      console.error("Capture async rejected:", { status: response.status, body: message });
      setStatus(message.startsWith("❌") ? message : `❌ ${message}`, "error");
      return;
    }

    input.value = "";
    showCheckmark();
    setStatus("Sent! ✅", "success");
    setTimeout(() => {
      window.quickCapture.hidePanel();
    }, SUCCESS_HIDE_MS);
  } catch (err) {
    console.error("Capture async fetch error:", err);
    setStatus(`❌ ${formatError(err)}`, "error");
  } finally {
    setLoading(false);
    if (!input.value.trim()) {
      return;
    }
    focusInput();
  }
}

input.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    window.quickCapture.hidePanel();
    return;
  }

  if (event.key === "Enter" && (event.metaKey || !event.shiftKey)) {
    event.preventDefault();
    submit();
  }
});

window.quickCapture.onPanelShown(() => {
  replayAnimation();
  resetStatus();
  setLoading(false);
  focusInput();
});

window.quickCapture
  .getCaptureUrl()
  .then((url) => {
    if (url) captureUrl = url;
  })
  .catch((err) => {
    console.error("Failed to load capture URL:", err);
  });

resetStatus();
focusInput();
