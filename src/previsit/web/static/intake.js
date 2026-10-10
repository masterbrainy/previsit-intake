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
    if (!text) return;
    const div = document.createElement("div");
    div.className = `bubble ${who}`;
    div.textContent = text;
    chat.appendChild(div);
    div.scrollIntoView({ behavior: "smooth", block: "end" });
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

  const handle = async (response) => {
    const data = await response.json().catch(() => ({ error: "Something went wrong. Please try again." }));
    if (!response.ok || data.error) {
      setBusy(false, data.error || data.detail || "Something went wrong. Please try again.");
      return;
    }
    if (data.patient_text) addBubble("patient", data.patient_text);
    addBubble("agent", data.agent_text);
    play(data.audio);
    setBusy(false);
    if (data.ended) done.hidden = false;
  };

  const post = async (path, form, message) => {
    setBusy(true, message);
    form.append("speak", speak.checked ? "true" : "false");
    try {
      await handle(await fetch(`${base}/${path}`, { method: "POST", body: form }));
    } catch {
      setBusy(false, "Connection problem. Please check your internet and try again.");
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
    const form = new FormData();
    form.append("text", text);
    post("turn", form, "Thinking…");
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
        post("turn", form, "Listening…");
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
