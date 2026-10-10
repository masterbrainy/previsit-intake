(() => {
  const base = window.INTAKE.base;
  const chat = document.getElementById("chat");
  const status = document.getElementById("status");
  const mic = document.getElementById("mic");
  const textForm = document.getElementById("textForm");
  const textInput = document.getElementById("text");
  const speak = document.getElementById("speak");
  const done = document.getElementById("done");
  let busy = false;
  let recorder = null;
  let chunks = [];
  let player = null;

  const addBubble = (who, text) => {
    const div = document.createElement("div");
    div.className = `bubble ${who}`;
    div.textContent = text;
    chat.appendChild(div);
    div.scrollIntoView({ behavior: "smooth", block: "end" });
    return div;
  };

  // "…" shown while the assistant's reply is being prepared and checked.
  let typing = null;
  const showTyping = () => {
    if (!typing) typing = addBubble("agent typing", "…");
  };
  const hideTyping = () => {
    if (typing) typing.remove();
    typing = null;
  };

  const setBusy = (value, message = "") => {
    busy = value;
    status.textContent = message;
    mic.disabled = value;
    textForm.querySelector("button").disabled = value;
  };

  const play = (b64) => {
    if (!b64 || !speak.checked) return;
    if (player) player.pause();
    player = new Audio(`data:audio/mpeg;base64,${b64}`);
    player.play().catch(() => {});
  };

  // A patient bubble whose turn failed gets a retry link that resends the same form.
  const markFailed = (bubble, path, form, message) => {
    if (!bubble) return;
    bubble.classList.add("failed");
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "retry";
    retry.textContent = "Not sent · tap to retry";
    retry.addEventListener("click", () => {
      if (busy) return;
      retry.remove();
      bubble.classList.remove("failed");
      post(path, form, message, bubble);
    });
    bubble.appendChild(retry);
  };

  const handle = async (response, bubble, path, form, message) => {
    const data = await response.json().catch(() => ({ error: "Something went wrong. Please try again." }));
    hideTyping();
    if (!response.ok || data.error) {
      setBusy(false, data.error || data.detail || "Something went wrong. Please try again.");
      markFailed(bubble, path, form, message);
      return;
    }
    // Typed answers are already on screen; a voice answer's bubble gets its transcribed text now.
    if (bubble && data.patient_text) bubble.textContent = data.patient_text;
    if (data.agent_text) addBubble("agent", data.agent_text);
    play(data.audio);
    setBusy(false);
    textInput.focus();
    if (data.ended) done.hidden = false;
    // Two-step read-back: the holding line is showing; fetch the summary straight away.
    if (data.follow_up) post("readback", new FormData(), "Putting together the main points…");
  };

  const post = async (path, form, message, bubble = null) => {
    setBusy(true, message);
    showTyping();
    if (!form.has("speak")) form.append("speak", speak.checked ? "true" : "false");
    try {
      await handle(await fetch(`${base}/${path}`, { method: "POST", body: form }), bubble, path, form, message);
    } catch {
      hideTyping();
      setBusy(false, "Connection problem. Please check your internet and try again.");
      markFailed(bubble, path, form, message);
    }
  };

  textForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = textInput.value.trim();
    if (busy) {
      status.textContent = "Still working on your last answer. One moment…";
      return;
    }
    if (!text) return;
    textInput.value = "";
    textInput.focus();
    const bubble = addBubble("patient", text); // shown straight away, before the server replies
    const form = new FormData();
    form.append("text", text);
    post("turn", form, "", bubble);
  });

  const stopRecording = () => {
    if (recorder && recorder.state === "recording") recorder.stop();
  };

  mic.addEventListener("click", async () => {
    if (busy) return;
    if (recorder && recorder.state === "recording") return stopRecording();
    if (!navigator.mediaDevices?.getUserMedia) {
      status.textContent = "Voice isn't available in this browser. Please type instead.";
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (player) player.pause();
      chunks = [];
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (event) => event.data.size && chunks.push(event.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        mic.classList.remove("recording");
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        if (blob.size < 1000) return setBusy(false, "That was very short. Tap the microphone and try again.");
        const form = new FormData();
        form.append("audio", blob, "turn.webm");
        post("turn", form, "", addBubble("patient", "🎙 …"));
      };
      recorder.start();
      mic.classList.add("recording");
      status.textContent = "Recording… tap the microphone again when you've finished.";
    } catch {
      status.textContent = "I couldn't use the microphone. Please allow it, or type instead.";
    }
  });

  post("start", new FormData(), "Connecting…");
})();
