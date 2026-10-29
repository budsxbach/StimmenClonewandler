/* StimmenClonewandler – Oberfläche (reines JavaScript, keine externen Bibliotheken).
   Alle Anfragen gehen an denselben lokalen Server (localhost). */

"use strict";

const state = {
  status: null,
  recordings: [],
  results: [],
  masterId: null,
  masterProfile: null,
  baseVoice: null,
  voices: [],
  presets: [],
  job: null,
  jobTimer: null,
  jobStart: 0,
  lastJobId: null,
  recorder: {
    active: false,
    ctx: null,
    stream: null,
    source: null,
    processor: null,
    buffers: [],
    startedAt: 0,
    timer: null,
    raf: null,
    peak: 0,
    clipped: 0,
  },
  compare: { a: null, b: null, audioA: null, audioB: null },
};

const EXAMPLE_TEXT =
  "Setz dich einen Moment hin und atme ruhig. Manche Dinge brauchen Zeit, " +
  "und das ist in Ordnung. Ich erzähle dir eine kleine Geschichte aus einer " +
  "stillen Gegend, in der der Nebel über den Feldern liegt und die alten " +
  "Wege noch niemandem gehören.";

/* ------------------------------------------------------------------ */
/* Kleine Helfer                                                       */
/* ------------------------------------------------------------------ */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fmtDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function fmtSeconds(seconds) {
  const value = Number(seconds) || 0;
  return `${value.toFixed(value < 10 ? 1 : 0)} s`;
}

function fmtBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function fmtDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return escapeHtml(iso);
  return date.toLocaleString("de-DE", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function toast(message, isError = false) {
  const box = $("#toast");
  box.textContent = message;
  box.classList.toggle("is-error", !!isError);
  box.classList.remove("hidden");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => box.classList.add("hidden"), 5200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body && !(options.body instanceof FormData)
      ? { "Content-Type": "application/json" }
      : undefined,
    ...options,
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    payload = null;
  }
  if (!response.ok || (payload && payload.ok === false)) {
    const message = (payload && payload.error) || `Anfrage fehlgeschlagen (${response.status}).`;
    const error = new Error(message);
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload || {};
}

/* ------------------------------------------------------------------ */
/* Navigations-Tabs                                                    */
/* ------------------------------------------------------------------ */

function initTabs() {
  $$(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      $$(".tab").forEach((other) => {
        other.classList.toggle("is-active", other === tab);
        other.setAttribute("aria-selected", other === tab ? "true" : "false");
      });
      $$(".tab-panel").forEach((panel) => {
        panel.classList.toggle("is-active", panel.id === `tab-${tab.dataset.tab}`);
      });
      if (tab.dataset.tab === "system") loadStatus(true);
    });
  });
}

/* ------------------------------------------------------------------ */
/* Status, Hardware, Modelle                                           */
/* ------------------------------------------------------------------ */

function renderStatus() {
  const status = state.status;
  if (!status) return;
  const pill = $("#status-pill");

  if (status.ready) {
    pill.className = "pill pill-ok";
    pill.textContent = "Bereit – Spracherzeugung möglich";
  } else if (status.system && !status.system.sufficient) {
    pill.className = "pill pill-err";
    pill.textContent = "Hardware reicht nicht aus";
  } else {
    pill.className = "pill pill-warn";
    pill.textContent = "Eingeschränkt – Modell/Engine fehlt";
  }

  // Hardware
  const system = status.system || {};
  const cells = [
    ["Prozessor-Kerne", system.cpu_cores ?? "?"],
    ["Arbeitsspeicher frei", system.ram_available_mb != null ? `${system.ram_available_mb} MB` : "unbekannt"],
    ["Arbeitsspeicher gesamt", system.ram_total_mb != null ? `${system.ram_total_mb} MB` : "unbekannt"],
    ["Freier Speicher", system.disk_free_mb != null ? `${system.disk_free_mb} MB` : "?"],
    ["Betriebssystem", system.os || "?"],
    ["Python", system.python || "?"],
  ];
  $("#hardware-grid").innerHTML = cells.map(([key, value]) => `
    <div class="cell"><div class="k">${escapeHtml(key)}</div><div class="v">${escapeHtml(value)}</div></div>
  `).join("");

  $("#hardware-messages").innerHTML = (status.messages || []).map((message) => {
    const cls = message.severity === "error" ? "alert-error"
      : message.severity === "warn" ? "alert-warn" : "alert-info";
    return `<div class="alert ${cls}">${escapeHtml(message.text)}</div>`;
  }).join("");

  // Engines
  const piper = status.piper || {};
  const ort = status.onnxruntime || {};
  const xtts = status.xtts || {};
  const engineCells = [
    ["Piper (Sprach-Engine)", piper.available ? `installiert${piper.version ? ` (${piper.version})` : ""}` : "fehlt", piper.available ? "ok" : "bad"],
    ["onnxruntime", ort.available ? ort.version : "fehlt", ort.available ? "ok" : "bad"],
    ["Deutsche Stimmen", String(status.german_voice_count ?? 0), (status.german_voice_count ? "ok" : "warn")],
    ["XTTS-Stimmkopie", xtts.present ? "Modell vorhanden" : (xtts.available ? "bereit" : "nicht verfügbar"), xtts.available ? "ok" : "warn"],
    ["Grafikprozessor nötig", "nein", "ok"],
    ["Netzwerkzugriff", "keiner", "ok"],
  ];
  $("#engine-grid").innerHTML = engineCells.map(([key, value, cls]) => `
    <div class="cell"><div class="k">${escapeHtml(key)}</div>
      <div class="v ${cls || ""}">${escapeHtml(value)}</div></div>
  `).join("");

  // Modellverwaltung
  const voices = status.voices || [];
  $("#voices-table").innerHTML = voices.length ? voices.map((voice) => {
    const usable = voice.usable !== false;
    return `
      <div class="item">
        <div class="item-head">
          <div class="item-title">
            <strong>${escapeHtml(voice.name)}</strong>
            <span class="tag">${escapeHtml(voice.language || "?")}</span>
            ${voice.quality ? `<span class="tag">${escapeHtml(voice.quality)}</span>` : ""}
            ${voice.is_german ? '<span class="tag tag-master">Deutsch</span>' : ""}
          </div>
          <span class="badge">${voice.size_mb ? `${voice.size_mb} MB` : ""}</span>
        </div>
        <div class="metrics">
          <div class="metric"><span class="k">Samplerate</span><span class="v">${voice.sample_rate ? `${voice.sample_rate} Hz` : "?"}</span></div>
          <div class="metric"><span class="k">Sprecher</span><span class="v">${voice.num_speakers ?? "?"}</span></div>
          <div class="metric"><span class="k">Datei</span><span class="v">${escapeHtml(voice.filename)}</span></div>
        </div>
        ${usable ? "" : `<div class="alert alert-error">${escapeHtml(voice.error || "Stimme nicht nutzbar")}</div>`}
      </div>`;
  }).join("") : `
    <p class="empty-state">Kein Sprachmodell gefunden. Lege eine deutsche Piper-Stimme
      (<code>*.onnx</code> + <code>*.onnx.json</code>) in <code>data/modelle/piper</code>.<br><br>
      Einmalig im Terminal herunterladen (mit Internet):<br>
      <code>.venv/bin/python -m app.voice_setup de_DE-thorsten-medium</code></p>`;

  // Speicher
  const storage = status.storage || {};
  $("#storage-grid").innerHTML = `
    <div class="cell"><div class="k">Datenordner</div><div class="v">${escapeHtml(status.paths?.data || "")}</div></div>
    <div class="cell"><div class="k">Modelle</div><div class="v">${escapeHtml(status.paths?.piper || "")}</div></div>
    <div class="cell"><div class="k">Aufnahmen</div><div class="v">${fmtBytes(storage.aufnahmen_bytes)}</div></div>
    <div class="cell"><div class="k">Ergebnisse</div><div class="v">${fmtBytes(storage.ergebnisse_bytes)}</div></div>
    <div class="cell"><div class="k">Modelle belegt</div><div class="v">${fmtBytes(storage.modelle_bytes)}</div></div>
  `;

  renderVoiceSelect();
  renderPresetSelect();
  renderEngineHint();
  applyRecommendedMode();
}

function renderVoiceSelect() {
  const select = $("#tts-voice");
  const voices = (state.status?.voices || []).filter((voice) => voice.usable !== false);
  if (!voices.length) {
    select.innerHTML = '<option value="">Kein Modell vorhanden</option>';
    select.disabled = true;
    $("#voice-hint").innerHTML =
      "Es liegt kein Sprachmodell vor. Einmalig im Terminal herunterladen (mit Internet): "
      + '<code>.venv/bin/python -m app.voice_setup de_DE-thorsten-medium</code>'
      + " – danach hier auf „Erneut prüfen“.";
    return;
  }
  select.disabled = false;
  const current = select.value;
  select.innerHTML = voices.map((voice) => {
    const label = `${voice.name}${voice.is_german ? " (Deutsch)" : ""}`;
    return `<option value="${escapeHtml(voice.name)}">${escapeHtml(label)}</option>`;
  }).join("");
  const exists = voices.some((voice) => voice.name === current);
  if (exists) select.value = current;
  const selected = voices.find((voice) => voice.name === select.value) || voices[0];
  renderSpeakerSelect(selected);
  const parts = selected
    ? [`Lokales Modell · ${selected.dataset || "unbekannter Datensatz"} · ${selected.sample_rate || "?"} Hz`]
    : [];
  if (selected && selected.is_german === false) {
    parts.push("Achtung: kein deutsches Modell, Aussprache kann fehlerhaft sein.");
  }
  if (selected && selected.license) {
    parts.push(selected.commercial_use
      ? `Lizenz ${selected.license} – für Videos mit Geldverdienst erlaubt`
        + (selected.attribution ? ` (${selected.attribution}).` : ".")
      : `Lizenz ${selected.license} – NICHT für Videos mit Geldverdienst erlaubt.`);
  }
  $("#voice-hint").textContent = parts.join(" · ");
}

function renderSpeakerSelect(voice) {
  const field = $("#speaker-field");
  const select = $("#tts-speaker");
  const nextButton = $("#btn-next-speaker");
  if (!field || !select) return;

  const speakers = voice && voice.speaker_id_map ? Object.entries(voice.speaker_id_map) : [];
  if (!voice || speakers.length <= 1) {
    field.classList.add("hidden");
    nextButton.classList.add("hidden");
    select.innerHTML = "";
    return;
  }

  field.classList.remove("hidden");
  nextButton.classList.remove("hidden");
  const current = select.value;
  select.innerHTML = speakers.map(([name, id]) =>
    `<option value="${id}">${escapeHtml(name)} (#${id})</option>`
  ).join("");
  if (speakers.some(([, id]) => String(id) === current)) select.value = current;
}

function initAudition() {
  const button = $("#btn-audition");
  const nextButton = $("#btn-next-speaker");
  const status = $("#audition-status");
  const audio = $("#audition-audio");

  const start = async () => {
    const voice = $("#tts-voice").value;
    if (!voice) {
      toast("Es liegt kein Sprachmodell vor.", true);
      return;
    }
    const speakerValue = $("#tts-speaker").value;
    const payload = {
      voice,
      speaker_id: speakerValue === "" ? null : Number(speakerValue),
      preset: $("#tts-preset").value,
      intensity: Number($("#tts-intensity").value) / 100,
      tempo: Number($("#tts-tempo").value) / 100,
      pitch_semitones: Number($("#tts-pitch").value),
      slow_mode: $("#tts-slow").checked,
      threads: Number($("#tts-threads").value),
    };
    button.disabled = true;
    nextButton.disabled = true;
    status.textContent = "Hörprobe wird erzeugt …";
    try {
      const response = await api("/api/audition", { method: "POST", body: JSON.stringify(payload) });
      const jobId = response.job.id;
      const poll = setInterval(async () => {
        try {
          const info = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
          const job = info.job;
          status.textContent = job.stage || "läuft …";
          if (job.status === "fertig") {
            clearInterval(poll);
            audio.src = `/api/jobs/${encodeURIComponent(jobId)}/audio?t=${Date.now()}`;
            audio.classList.remove("hidden");
            audio.play().catch(() => {});
            status.textContent = `fertig · ${job.result.duration_s} s`;
          } else if (job.status === "fehler") {
            clearInterval(poll);
            status.textContent = "";
            toast(job.error || "Hörprobe fehlgeschlagen.", true);
          }
        } catch (error) {
          clearInterval(poll);
          status.textContent = "";
          toast(error.message, true);
        } finally {
          if (!document.querySelector("#audition-audio").paused) {
            button.disabled = false;
            nextButton.disabled = false;
          }
        }
      }, 600);
      setTimeout(() => { button.disabled = false; nextButton.disabled = false; }, 4000);
    } catch (error) {
      status.textContent = "";
      button.disabled = false;
      nextButton.disabled = false;
      toast(error.message, true);
    }
  };

  button.addEventListener("click", start);
  nextButton.addEventListener("click", () => {
    const select = $("#tts-speaker");
    if (select.options.length < 2) return;
    select.selectedIndex = (select.selectedIndex + 1) % select.options.length;
    start();
  });
}

function renderPresetSelect() {
  const select = $("#tts-preset");
  const presets = state.presets || [];
  if (!presets.length) return;
  const current = select.value;
  select.innerHTML = presets.map((preset) =>
    `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.label)}</option>`
  ).join("");
  const fallback = state.status?.default_preset || presets[0].id;
  select.value = presets.some((preset) => preset.id === current) ? current : fallback;
  renderPresetDescription();
}

function renderAdaptHint() {
  const checkbox = $("#tts-adapt");
  const hint = $("#adapt-hint");
  if (!checkbox || !hint) return;
  const base = state.baseVoice;
  if (base && base.present) {
    checkbox.disabled = false;
    const profile = base.profile || {};
    const name = base.recording?.name || "Referenzaufnahme";
    hint.textContent =
      `Ausgangsstimme: „${name}“ · gemessene Sprechlage ≈ ${Math.round(profile.median_f0_hz)} Hz `
      + `(${profile.pitch_class}). Die Modellstimme wird auf diese Lage gezogen (max. ±4 Halbtöne). `
      + "Das ist keine Stimmkopie, sondern eine Angleichung der Tonhöhe.";
  } else {
    checkbox.checked = false;
    checkbox.disabled = true;
    hint.textContent =
      "Keine Ausgangsstimme verfügbar: "
      + (base?.reason || "Es ist keine Master-Aufnahme mit messbarer Stimmlage festgelegt.")
      + " Lege im Tab „Aufnahmen“ eine Aufnahme als Master fest.";
  }
}

function renderPresetDescription() {
  const preset = (state.presets || []).find((item) => item.id === $("#tts-preset").value);
  $("#preset-description").textContent = preset ? preset.description : "";
}

function renderEngineHint() {
  const engine = $("#tts-engine").value;
  const hint = $("#engine-hint");
  if (engine === "xtts") {
    const xtts = state.status?.xtts || {};
    if (!xtts.available) {
      const missing = (xtts.missing || []).join(", ") || 'PyTorch + Coqui TTS (pip install "coqui-tts[cpu]") und das XTTS-v2-Modell (python -m app.voice_setup --xtts)';
      hint.innerHTML = `<span class="alert alert-warn">Eigene Stimmkopie ist auf diesem Laptop nicht ausführbar. Es fehlt: ${escapeHtml(missing)}. `
        + `Die App verweigert dann ehrlich die Ausgabe – sie behauptet nie, eine Kopie sei fertig.</span>`;
    } else {
      hint.innerHTML = `<span class="alert alert-info">XTTS-v2 ist ~1,9 GB groß, braucht ~4 GB Arbeitsspeicher und ist auf einer reinen CPU oft 5–30× langsamer als Echtzeit. `
        + `Ein einzelner Satz kann mehrere Minuten dauern – bitte nur die eigene Stimme als Referenz verwenden.</span>`;
    }
  } else {
    hint.textContent = "Piper ist klein, CPU-freundlich und für diesen Laptop empfohlen.";
  }
}

function applyRecommendedMode() {
  const recommended = state.status?.recommended_mode;
  if (!recommended) return;
  const slow = $("#tts-slow");
  if (recommended.slow_mode && slow.dataset.userTouched !== "1") {
    slow.checked = true;
  }
  const threads = $("#tts-threads");
  if (threads.dataset.userTouched !== "1" && recommended.slow_mode) {
    threads.value = "1";
  }
}

async function loadStatus(refresh = false) {
  try {
    const payload = refresh
      ? await api("/api/status/refresh", { method: "POST" })
      : await api("/api/status");
    state.status = payload;
    state.presets = payload.presets || [];
    renderStatus();
    if (refresh) toast("Status neu geprüft.");
  } catch (error) {
    const pill = $("#status-pill");
    pill.className = "pill pill-err";
    pill.textContent = "Server nicht erreichbar";
    toast(error.message, true);
  }
}

/* ------------------------------------------------------------------ */
/* Aufnahmen                                                           */
/* ------------------------------------------------------------------ */

function analysisBadges(record) {
  const analysis = record.analysis || {};
  const alerts = [];
  if (analysis.error) {
    alerts.push(`<div class="alert alert-warn">Analyse nicht möglich: ${escapeHtml(analysis.error)}</div>`);
  }
  (analysis.warnings || []).forEach((warning) => {
    const cls = warning.severity === "error" ? "alert-error"
      : warning.severity === "warn" ? "alert-warn" : "alert-info";
    alerts.push(`<div class="alert ${cls}">${escapeHtml(warning.text)}</div>`);
  });
  return alerts.join("");
}

function metricsHtml(record) {
  const info = record.info || {};
  const analysis = record.analysis || {};
  const channels = info.channels === 1 ? "Mono" : info.channels === 2 ? "Stereo" : `${info.channels || "?"} Kanäle`;
  const peak = analysis.peak_dbfs != null ? `${analysis.peak_dbfs.toFixed(1)} dBFS` : "–";
  const rms = analysis.rms_dbfs != null ? `${analysis.rms_dbfs.toFixed(1)} dBFS` : "–";
  const noise = analysis.snr_db != null
    ? `${analysis.snr_db.toFixed(0)} dB · ${analysis.noise_label || ""}`
    : "–";
  return `
    <div class="metrics">
      <div class="metric"><span class="k">Samplerate</span><span class="v">${info.sample_rate ? `${info.sample_rate} Hz` : "?"}</span></div>
      <div class="metric"><span class="k">Kanäle</span><span class="v">${escapeHtml(channels)}</span></div>
      <div class="metric"><span class="k">Dauer</span><span class="v">${fmtDuration(info.duration_s)}</span></div>
      <div class="metric"><span class="k">Bittiefe</span><span class="v">${info.bits ? `${info.bits} Bit` : "?"}</span></div>
      <div class="metric"><span class="k">Spitzenpegel</span><span class="v">${peak}</span></div>
      <div class="metric"><span class="k">Lautheit</span><span class="v">${rms}</span></div>
      <div class="metric"><span class="k">Stimme/Geräusch</span><span class="v">${escapeHtml(noise)}</span></div>
      <div class="metric"><span class="k">Übersteuerung</span><span class="v">${
        analysis.clipping
          ? `${analysis.clipped_samples ?? 0} Werte`
          : "keine erkannt"
      }</span></div>
    </div>`;
}

function renderRecordings() {
  const list = $("#recordings-list");
  const empty = $("#recordings-empty");
  $("#recording-count").textContent = String(state.recordings.length);

  if (!state.recordings.length) {
    list.innerHTML = "";
    empty.classList.remove("hidden");
  } else {
    empty.classList.add("hidden");
    list.innerHTML = state.recordings.map((record) => {
      const isMaster = record.is_master;
      return `
        <div class="item ${isMaster ? "is-master" : ""}">
          <div class="item-head">
            <div class="item-title">
              <strong>${escapeHtml(record.name || "Aufnahme")}</strong>
              <span class="tag ${record.kind === "aufnahme" ? "tag-mic" : ""}">
                ${record.kind === "aufnahme" ? "Mikrofon" : "Import"}
              </span>
              ${isMaster ? '<span class="tag tag-master">Master</span>' : ""}
              <span class="time">${fmtDate(record.created_at)} · ${fmtBytes(record.size_bytes)}</span>
            </div>
          </div>
          ${metricsHtml(record)}
          ${analysisBadges(record)}
          <audio controls preload="none" src="/api/recordings/${encodeURIComponent(record.id)}/audio"></audio>
          <div class="item-actions">
            <button class="btn btn-small btn-outline" data-action="master" data-id="${record.id}">
              ${isMaster ? "Master neu aufbereiten" : "Als Master festlegen"}
            </button>
            <a class="btn btn-small btn-ghost" href="/api/recordings/${encodeURIComponent(record.id)}/download">Herunterladen</a>
            <button class="btn btn-small btn-ghost" data-action="reanalyze" data-id="${record.id}">Neu analysieren</button>
            <button class="btn btn-small btn-danger" data-action="delete" data-id="${record.id}">Löschen</button>
          </div>
        </div>`;
    }).join("");
  }

  renderMaster();
  renderCompareSelects();
}

function renderMaster() {
  const box = $("#master-box");
  const master = state.recordings.find((record) => record.is_master);
  if (!master) {
    box.className = "master-box empty";
    box.innerHTML = '<p class="muted">Noch keine Master-Aufnahme festgelegt. Wähle oben bei einer Aufnahme „Als Master festlegen“.</p>';
    return;
  }
  box.className = "master-box is-set";
  const analysis = master.analysis || {};
  const profile = state.masterProfile?.reference?.voice_profile || null;
  const suggestion = profile && profile.suggested_preset
    ? (state.presets || []).find((preset) => preset.id === profile.suggested_preset)
    : null;

  const profileBlock = profile ? `
    <h3>Grobe Stimm-Analyse der Referenz</h3>
    <div class="metrics">
      <div class="metric"><span class="k">Sprechlage</span><span class="v">${escapeHtml(profile.pitch_class || "?")}</span></div>
      <div class="metric"><span class="k">Grundfrequenz</span><span class="v">${
        profile.median_f0_hz ? `${Math.round(profile.median_f0_hz)} Hz` : "nicht messbar"
      }</span></div>
      <div class="metric"><span class="k">Schwankung</span><span class="v">${escapeHtml(profile.roughness || "?")}</span></div>
      <div class="metric"><span class="k">Messfenster</span><span class="v">${
        profile.voiced_ratio != null ? `${Math.round(profile.voiced_ratio * 100)} % stimmhaft` : "–"
      }</span></div>
    </div>
    <div class="alert alert-info">${escapeHtml(profile.summary || "")}</div>
    ${suggestion ? `<div class="alert alert-ok">
        Empfohlener Stil: <strong>${escapeHtml(suggestion.label)}</strong>
        · Intensität ${Math.round((profile.suggested_intensity ?? 1) * 100)} %
        · Tempo ${Math.round((profile.suggested_tempo ?? 1) * 100)} %
      </div>
      <button class="btn btn-small btn-outline" id="btn-apply-style">Diesen Stil übernehmen</button>` : ""}
    <p class="hint">${escapeHtml(profile.honest_note || "")}</p>
  ` : "";

  box.innerHTML = `
    <div class="item-title">
      <strong>${escapeHtml(master.name || "Master")}</strong>
      <span class="tag tag-master">Master</span>
    </div>
    <div class="metrics">
      <div class="metric"><span class="k">Dauer</span><span class="v">${fmtDuration(master.info?.duration_s)}</span></div>
      <div class="metric"><span class="k">Samplerate</span><span class="v">${master.info?.sample_rate || "?"} Hz</span></div>
      <div class="metric"><span class="k">Stimme/Geräusch</span><span class="v">${analysis.snr_db != null ? `${analysis.snr_db.toFixed(0)} dB` : "–"}</span></div>
    </div>
    <audio controls preload="none" src="/api/master/reference?v=${encodeURIComponent(master.created_at || "")}"></audio>
    <div class="item-actions">
      <a class="btn btn-small btn-outline" href="/api/master/reference?download=1">Master-WAV herunterladen</a>
      <button class="btn btn-small btn-ghost" id="btn-clear-master">Master-Auswahl aufheben</button>
    </div>
    ${profileBlock}
    <div class="alert alert-ok">
      <strong>Ausgangsstimme aktiv:</strong> Bei der Sprachausgabe wird die Stimmlage der
      Modellstimme an diese Aufnahme angeglichen (Schalter „Stimmlage an meine
      Ausgangsstimme anpassen“).
    </div>
    <p class="hint">Für die Sprachausgabe mit Piper wird die Master-Aufnahme nicht benötigt.
      Sie ist die Referenz für die optionale eigene Stimmkopie (XTTS) und für die grobe Stimm-Analyse.</p>
  `;

  const clear = $("#btn-clear-master");
  if (clear) {
    clear.addEventListener("click", async () => {
      if (!confirm("Master-Auswahl wirklich aufheben? Die Originalaufnahme bleibt erhalten.")) return;
      await api("/api/master", { method: "DELETE" });
      await loadRecordings();
      toast("Master-Auswahl aufgehoben.");
    });
  }

  const apply = $("#btn-apply-style");
  if (apply && profile) {
    apply.addEventListener("click", () => {
      const presetSelect = $("#tts-preset");
      if ((state.presets || []).some((preset) => preset.id === profile.suggested_preset)) {
        presetSelect.value = profile.suggested_preset;
        renderPresetDescription();
      }
      const intensity = $("#tts-intensity");
      intensity.value = String(Math.round((profile.suggested_intensity ?? 1) * 100));
      $("#out-intensity").textContent = `${intensity.value} %`;
      const tempo = $("#tts-tempo");
      tempo.value = String(Math.round((profile.suggested_tempo ?? 1) * 100));
      $("#out-tempo").textContent = `${tempo.value} %`;
      $$(".tab").forEach((other) => {
        other.classList.toggle("is-active", other.dataset.tab === "sprache");
        other.setAttribute("aria-selected", other.dataset.tab === "sprache" ? "true" : "false");
      });
      $$(".tab-panel").forEach((panel) => {
        panel.classList.toggle("is-active", panel.id === "tab-sprache");
      });
      toast("Stil-Empfehlung aus deiner Referenzaufnahme übernommen.");
    });
  }
}

async function loadRecordings() {
  try {
    const payload = await api("/api/recordings");
    state.recordings = payload.recordings || [];
    state.masterId = payload.master_id || null;
    if (state.status) state.status.storage = payload.storage;
    try {
      const masterPayload = await api("/api/master");
      state.masterProfile = masterPayload.present ? masterPayload : null;
      state.baseVoice = masterPayload.base_voice || null;
    } catch (error) {
      state.masterProfile = null;
      state.baseVoice = null;
    }
    renderRecordings();
    renderAdaptHint();
  } catch (error) {
    toast(error.message, true);
  }
}

async function uploadFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".wav")) {
    toast("Bitte eine WAV-Datei auswählen (PCM). Andere Formate bitte vorher umwandeln.", true);
    return;
  }
  const progress = $("#upload-progress");
  progress.classList.remove("hidden");
  try {
    const form = new FormData();
    form.append("file", file, file.name);
    const payload = await api("/api/recordings/upload", { method: "POST", body: form });
    toast(`„${payload.recording.name}“ importiert.`);
    await loadRecordings();
    state.status = null;
    loadStatus();
  } catch (error) {
    toast(error.message, true);
  } finally {
    progress.classList.add("hidden");
    $("#file-input").value = "";
  }
}

function initUpload() {
  const drop = $("#dropzone");
  const input = $("#file-input");
  drop.addEventListener("click", () => input.click());
  drop.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.click();
    }
  });
  input.addEventListener("change", () => uploadFile(input.files[0]));
  ["dragenter", "dragover"].forEach((name) => {
    drop.addEventListener(name, (event) => {
      event.preventDefault();
      drop.classList.add("is-over");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    drop.addEventListener(name, (event) => {
      event.preventDefault();
      drop.classList.remove("is-over");
    });
  });
  drop.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0];
    uploadFile(file);
  });
}

function initRecordingListActions() {
  $("#recordings-list").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const { action, id } = button.dataset;
    const record = state.recordings.find((item) => item.id === id);

    if (action === "delete") {
      if (!confirm(`Aufnahme „${record?.name || id}“ endgültig von diesem Laptop löschen?`)) return;
      try {
        await api(`/api/recordings/${encodeURIComponent(id)}`, { method: "DELETE" });
        toast("Aufnahme gelöscht.");
        await loadRecordings();
      } catch (error) {
        toast(error.message, true);
      }
      return;
    }

    if (action === "reanalyze") {
      try {
        button.disabled = true;
        await api(`/api/recordings/${encodeURIComponent(id)}/reanalyze`, { method: "POST" });
        await loadRecordings();
        toast("Aufnahme neu analysiert.");
      } catch (error) {
        toast(error.message, true);
      } finally {
        button.disabled = false;
      }
      return;
    }

    if (action === "master") {
      try {
        button.disabled = true;
        button.textContent = "Wird aufbereitet …";
        const payload = await api(`/api/recordings/${encodeURIComponent(id)}/master`, {
          method: "POST",
          body: JSON.stringify({ cleanup: true }),
        });
        const notes = payload.notes || [];
        const problem = notes.find((note) => note.severity === "error")
          || notes.find((note) => note.severity === "warn");
        toast(
          problem ? problem.text
            : `Master-Aufnahme aus „${payload.recording_name}“ erstellt (${payload.duration_s} s).`,
          problem && problem.severity === "error"
        );
        await loadRecordings();
        loadStatus(true);
      } catch (error) {
        toast(error.message, true);
      } finally {
        button.disabled = false;
        button.textContent = "Als Master festlegen";
      }
    }
  });
}

/* ------------------------------------------------------------------ */
/* Mikrofonaufnahme                                                    */
/* ------------------------------------------------------------------ */

function encodeWavMono(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeText = (offset, text) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }
  return new Blob([view], { type: "audio/wav" });
}

async function startRecording() {
  const recorder = state.recorder;
  if (recorder.active) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    toast("Dieser Browser unterstützt keine Mikrofonaufnahme. Bitte Chrome, Edge oder Firefox verwenden.", true);
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) {
      throw new Error("Dieser Browser unterstützt Web-Audio nicht. Bitte importiere stattdessen eine WAV-Datei.");
    }
    const ctx = new Ctx();
    if (typeof ctx.createScriptProcessor !== "function") {
      await ctx.close();
      throw new Error(
        "Dieser Browser kann keine Rohaufnahme bereitstellen. Bitte eine WAV-Datei importieren oder Chrome/Edge/Firefox verwenden."
      );
    }
    const source = ctx.createMediaStreamSource(stream);
    const processor = ctx.createScriptProcessor(4096, 1, 1);

    recorder.buffers = [];
    recorder.peak = 0;
    recorder.clipped = 0;
    recorder.startedAt = Date.now();
    recorder.ctx = ctx;
    recorder.stream = stream;
    recorder.source = source;
    recorder.processor = processor;
    recorder.active = true;

    processor.onaudioprocess = (event) => {
      const channel = event.inputBuffer.getChannelData(0);
      recorder.buffers.push(new Float32Array(channel));
      let blockPeak = 0;
      for (let i = 0; i < channel.length; i += 1) {
        const value = Math.abs(channel[i]);
        if (value > blockPeak) blockPeak = value;
        if (value >= 0.999) recorder.clipped += 1;
      }
      if (blockPeak > recorder.peak) recorder.peak = blockPeak;
    };
    source.connect(processor);
    processor.connect(ctx.destination);

    $("#btn-record").classList.add("recording");
    $("#btn-record").disabled = true;
    $("#btn-stop-record").disabled = false;
    $("#record-status").textContent = `Aufnahme läuft · ${Math.round(ctx.sampleRate)} Hz · Mono`;
    $("#record-timer").textContent = "00:00";

    recorder.timer = setInterval(() => {
      const seconds = (Date.now() - recorder.startedAt) / 1000;
      $("#record-timer").textContent = fmtDuration(seconds);
      if (seconds > 180) stopRecording(true);
    }, 250);

    const drawMeter = () => {
      if (!recorder.active) return;
      const percent = Math.min(100, Math.round(recorder.peak * 100));
      const fill = $("#meter-fill");
      fill.style.width = `${percent}%`;
      fill.classList.toggle("hot", recorder.peak > 0.96);
      recorder.peak *= 0.92;
      recorder.raf = requestAnimationFrame(drawMeter);
    };
    drawMeter();
  } catch (error) {
    const reason = error && error.name === "NotAllowedError"
      ? "Der Zugriff auf das Mikrofon wurde abgelehnt. Bitte im Browser erlauben."
      : `Mikrofon nicht verfügbar: ${error.message || error.name}`;
    $("#record-status").textContent = reason;
    toast(reason, true);
  }
}

async function stopRecording(autoStopped = false) {
  const recorder = state.recorder;
  if (!recorder.active) return;
  recorder.active = false;
  clearInterval(recorder.timer);
  cancelAnimationFrame(recorder.raf);

  const sampleRate = recorder.ctx ? recorder.ctx.sampleRate : 44100;
  try {
    recorder.stream.getTracks().forEach((track) => track.stop());
    recorder.processor.disconnect();
    recorder.source.disconnect();
    await recorder.ctx.close();
  } catch (error) {
    /* Aufräumen darf nicht blockieren */
  }

  $("#btn-record").classList.remove("recording");
  $("#btn-record").disabled = false;
  $("#btn-stop-record").disabled = true;
  $("#meter-fill").style.width = "0%";
  $("#meter-fill").classList.remove("hot");

  const total = recorder.buffers.reduce((sum, chunk) => sum + chunk.length, 0);
  const seconds = total / sampleRate;
  if (total === 0 || seconds < 0.4) {
    $("#record-status").textContent = "Die Aufnahme war zu kurz. Bitte erneut versuchen.";
    $("#record-timer").textContent = "00:00";
    return;
  }

  const merged = new Float32Array(total);
  let offset = 0;
  recorder.buffers.forEach((chunk) => {
    merged.set(chunk, offset);
    offset += chunk.length;
  });

  const clippedRatio = recorder.clipped / total;
  let statusText = `Aufnahme bereit · ${seconds.toFixed(1)} s · ${sampleRate} Hz`;
  if (clippedRatio > 0.0005) {
    statusText += " · Achtung: Übersteuerung erkannt, bitte leiser sprechen.";
  }
  $("#record-status").textContent = statusText;

  const blob = encodeWavMono(merged, sampleRate);
  const name = $("#record-name").value.trim()
    || `Mikrofonaufnahme ${new Date().toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}`;

  try {
    $("#record-status").textContent = "Aufnahme wird lokal gespeichert …";
    const form = new FormData();
    form.append("file", blob, "aufnahme.wav");
    form.append("name", name);
    await api("/api/recordings/mic", { method: "POST", body: form });
    $("#record-name").value = "";
    toast(`Aufnahme „${name}“ lokal gespeichert.`);
    await loadRecordings();
    if (state.status) loadStatus(true);
  } catch (error) {
    $("#record-status").textContent = "Speichern fehlgeschlagen.";
    toast(error.message, true);
  }

  if (autoStopped) toast("Aufnahme nach 3 Minuten automatisch beendet.");
}

function initRecorder() {
  $("#btn-record").addEventListener("click", startRecording);
  $("#btn-stop-record").addEventListener("click", () => stopRecording(false));
  window.addEventListener("beforeunload", (event) => {
    if (state.recorder.active) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
}

/* ------------------------------------------------------------------ */
/* Vergleich                                                           */
/* ------------------------------------------------------------------ */

function allAudioSources() {
  const recordings = state.recordings.map((record) => ({
    id: `rec:${record.id}`,
    label: `Aufnahme · ${record.name}`,
    url: `/api/recordings/${encodeURIComponent(record.id)}/audio`,
    meta: `${record.info?.sample_rate || "?"} Hz · ${fmtDuration(record.info?.duration_s)} · ${
      record.info?.channels === 1 ? "Mono" : "Stereo"}`,
  }));
  const results = state.results.map((result) => ({
    id: `res:${result.id}`,
    label: `Ergebnis · ${result.name}`,
    url: `/api/results/${encodeURIComponent(result.id)}/audio`,
    meta: `${result.info?.sample_rate || "?"} Hz · ${fmtDuration(result.info?.duration_s)} · ${
      result.voice || result.engine || ""}`,
  }));
  return [...recordings, ...results];
}

function renderCompareSelects() {
  const sources = allAudioSources();
  ["a", "b"].forEach((side) => {
    const select = $(`#compare-${side}`);
    const previous = select.value;
    if (!sources.length) {
      select.innerHTML = '<option value="">keine Dateien vorhanden</option>';
      $(`#compare-${side}-meta`).textContent = "–";
      return;
    }
    select.innerHTML = sources.map((source) =>
      `<option value="${escapeHtml(source.id)}">${escapeHtml(source.label)}</option>`
    ).join("");
    if (sources.some((source) => source.id === previous)) select.value = previous;
    else if (side === "b" && sources.length > 1) select.value = sources[1].id;
    updateCompareMeta(side);
  });
}

function updateCompareMeta(side) {
  const id = $(`#compare-${side}`).value;
  const source = allAudioSources().find((item) => item.id === id);
  $(`#compare-${side}-meta`).textContent = source ? `${source.meta} · ${source.label}` : "–";
}

function playSource(id, onEnded) {
  const source = allAudioSources().find((item) => item.id === id);
  if (!source) return null;
  const audio = new Audio(source.url);
  audio.addEventListener("ended", () => { if (onEnded) onEnded(); });
  audio.play().catch((error) => toast(`Wiedergabe nicht möglich: ${error.message}`, true));
  return audio;
}

function initCompare() {
  ["a", "b"].forEach((side) => {
    $(`#compare-${side}`).addEventListener("change", () => updateCompareMeta(side));
    $(`#btn-play-${side}`).addEventListener("click", () => {
      if (state.compare.audioA) state.compare.audioA.pause();
      if (state.compare.audioB) state.compare.audioB.pause();
      const audio = playSource($(`#compare-${side}`).value);
      state.compare[side === "a" ? "audioA" : "audioB"] = audio;
    });
  });
  $("#btn-play-ab").addEventListener("click", () => {
    if (state.compare.audioA) state.compare.audioA.pause();
    if (state.compare.audioB) state.compare.audioB.pause();
    const aId = $("#compare-a").value;
    const bId = $("#compare-b").value;
    state.compare.audioA = playSource(aId, () => {
      state.compare.audioB = playSource(bId);
    });
  });
  $("#btn-stop-compare").addEventListener("click", () => {
    if (state.compare.audioA) state.compare.audioA.pause();
    if (state.compare.audioB) state.compare.audioB.pause();
  });
}

/* ------------------------------------------------------------------ */
/* Sprachausgabe                                                       */
/* ------------------------------------------------------------------ */

function initTtsControls() {
  const text = $("#tts-text");
  const updateCount = () => {
    $("#char-count").textContent = `${text.value.length} / 4000 Zeichen`;
  };
  text.addEventListener("input", updateCount);
  updateCount();

  $("#btn-example").addEventListener("click", () => {
    text.value = EXAMPLE_TEXT;
    updateCount();
  });

  $("#tts-preset").addEventListener("change", renderPresetDescription);
  $("#tts-engine").addEventListener("change", renderEngineHint);
  $("#tts-voice").addEventListener("change", renderVoiceSelect);

  $("#tts-intensity").addEventListener("input", (event) => {
    $("#out-intensity").textContent = `${event.target.value} %`;
  });

  $("#tts-tempo").addEventListener("input", (event) => {
    const value = Number(event.target.value) / 100;
    const label = value < 0.95 ? "langsamer" : value > 1.05 ? "schneller" : "normal";
    $("#out-tempo").textContent = `${label} (${Math.round(value * 100)} %)`;
  });

  const pitchSlider = $("#tts-pitch");
  if (pitchSlider) {
    pitchSlider.addEventListener("input", (event) => {
      const value = Number(event.target.value);
      $("#out-pitch").textContent = `${value > 0 ? "+" : ""}${value.toFixed(1).replace(".0", "")} Halbtöne`;
    });
  }

  $("#tts-slow").addEventListener("change", (event) => {
    event.target.dataset.userTouched = "1";
    $("#tts-threads").value = event.target.checked ? "1" : "2";
    $("#tts-threads").dataset.userTouched = "1";
  });
  $("#tts-threads").addEventListener("change", (event) => {
    event.target.dataset.userTouched = "1";
  });

  initAudition();
  $("#btn-speak").addEventListener("click", startSynthesis);
  $("#btn-cancel-job").addEventListener("click", cancelJob);
  $("#btn-save-result").addEventListener("click", saveResult);
}

function collectTtsPayload() {
  const speakerValue = $("#tts-speaker") ? $("#tts-speaker").value : "";
  const payload = {
    speaker_id: speakerValue === "" ? null : Number(speakerValue),
    text: $("#tts-text").value.trim(),
    engine: $("#tts-engine").value,
    voice: $("#tts-voice").value || null,
    preset: $("#tts-preset").value,
    intensity: Number($("#tts-intensity").value) / 100,
    tempo: Number($("#tts-tempo").value) / 100,
    slow_mode: $("#tts-slow").checked,
    threads: Number($("#tts-threads").value),
    adapt_pitch: $("#tts-adapt").checked,
    pitch_semitones: Number($("#tts-pitch").value),
  };
  return payload;
}

function setJobUi(running) {
  $("#btn-speak").disabled = running;
  $("#btn-cancel-job").disabled = !running;
  $("#tts-progress").classList.toggle("hidden", !running && !state.job);
}

function showTtsError(message) {
  const box = $("#tts-error");
  box.textContent = message;
  box.classList.remove("hidden");
}

function clearTtsError() {
  $("#tts-error").classList.add("hidden");
  $("#tts-error").textContent = "";
}

async function startSynthesis() {
  clearTtsError();
  const payload = collectTtsPayload();
  if (!payload.text) {
    showTtsError("Bitte einen Text eingeben, der vorgelesen werden soll.");
    return;
  }
  $("#btn-speak").disabled = true;
  $("#tts-progress").classList.remove("hidden");
  $("#tts-progress-fill").style.width = "0%";
  $("#tts-stage").textContent = "Auftrag wird gestartet …";
  $("#tts-elapsed").textContent = "0 s";
  state.jobStart = Date.now();
  $("#btn-cancel-job").disabled = false;

  try {
    const response = await api("/api/tts", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.job = response.job;
    state.lastJobId = response.job.id;
    pollJob(response.job.id);
  } catch (error) {
    $("#btn-speak").disabled = false;
    $("#btn-cancel-job").disabled = true;
    $("#tts-progress").classList.add("hidden");
    showTtsError(error.message);
    toast("Sprachausgabe nicht gestartet.", true);
  }
}

function pollJob(jobId) {
  clearInterval(state.jobTimer);
  state.jobTimer = setInterval(async () => {
    try {
      const payload = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
      const job = payload.job;
      state.job = job;
      $("#tts-progress-fill").style.width = `${job.progress}%`;
      $("#tts-stage").textContent = job.stage || "Läuft …";
      $("#tts-elapsed").textContent = `${Math.round((Date.now() - state.jobStart) / 1000)} s`;
      renderBenchmarkProgress(job);

      if (job.status === "fertig") {
        clearInterval(state.jobTimer);
        finishJob(job);
      } else if (job.status === "fehler") {
        clearInterval(state.jobTimer);
        failJob(job);
      } else if (job.status === "abgebrochen") {
        clearInterval(state.jobTimer);
        $("#btn-speak").disabled = false;
        $("#btn-cancel-job").disabled = true;
        $("#tts-stage").textContent = "Abgebrochen – es wurde keine Datei gespeichert.";
      }
    } catch (error) {
      clearInterval(state.jobTimer);
      $("#btn-speak").disabled = false;
      $("#btn-cancel-job").disabled = true;
      showTtsError(error.message);
    }
  }, 700);
}

function finishJob(job) {
  $("#btn-speak").disabled = false;
  $("#btn-cancel-job").disabled = true;
  $("#tts-progress-fill").style.width = "100%";
  $("#tts-stage").textContent = "Fertig – lokal erzeugt.";

  if (job.kind === "benchmark") {
    const meta = job.result || {};
    const result = $("#benchmark-result");
    if (meta.realtime_factor) {
      result.textContent =
        `Ergebnis: ${meta.compute_seconds} s Rechenzeit für ${meta.duration_s} s Audio ` +
        `(${meta.realtime_factor}× Echtzeit). ` +
        (meta.realtime_factor < 0.4
          ? "Für längere Texte ist der langsame CPU-Modus sinnvoll."
          : "Dieser Laptop rechnet zügig genug.");
    } else {
      result.textContent = "Test abgeschlossen.";
    }
    $("#benchmark-progress").classList.add("hidden");
    loadStatus(true);
    return;
  }

  const meta = job.result || {};
  const card = $("#tts-result-card");
  card.classList.remove("hidden");
  const audio = $("#tts-result-audio");
  audio.src = `/api/jobs/${encodeURIComponent(job.id)}/audio?t=${Date.now()}`;
  audio.load();

  const isClone = !!meta.is_clone;
  $("#result-badge").textContent = isClone ? "lokal mit Referenzstimme erzeugt" : "lokal erzeugt";
  $("#result-badge").className = `badge ${isClone ? "badge-gold" : "badge-gold"}`;

  const rows = [
    ["Stimme", meta.voice || "–"],
    ["Verfahren", isClone ? "XTTS-v2 (eigene Referenz)" : "Piper (CPU)"],
    ["Stil", meta.preset_label || meta.preset || "–"],
    ["Dauer", `${meta.duration_s ?? "?"} s`],
    ["Samplerate", `${meta.sample_rate ?? "?"} Hz`],
    ["Rechenzeit", `${meta.compute_seconds ?? "?"} s`],
    ["Rechentempo", meta.realtime_factor ? `${meta.realtime_factor}× Echtzeit` : "–"],
    ["CPU-Modus", meta.slow_mode ? "langsam / schonend" : "normal"],
  ];
  if (meta.pitch && (meta.pitch.adapted || Math.abs(meta.pitch.applied_semitones || 0) >= 0.05)) {
    const p = meta.pitch;
    const parts = [];
    if (p.reference_f0_hz) parts.push(`Ziel ${Math.round(p.reference_f0_hz)} Hz`);
    if (p.model_f0_hz) parts.push(`Modell ${Math.round(p.model_f0_hz)} Hz`);
    parts.push(`${p.applied_semitones > 0 ? "+" : ""}${p.applied_semitones} Halbtöne`);
    rows.push(["Stimmlage", `${parts.join(" · ")}${p.adapted ? " (an Ausgangsstimme angeglichen)" : " (manuell)"}`]);
  } else if (meta.pitch && meta.pitch.reason) {
    rows.push(["Stimmlage", `nicht angepasst – ${meta.pitch.reason}`]);
  }
  $("#tts-result-meta").innerHTML = rows.map(([key, value]) => `
    <div class="cell"><div class="k">${escapeHtml(key)}</div><div class="v">${escapeHtml(value)}</div></div>
  `).join("") + (meta.note ? `<div class="cell" style="grid-column:1/-1">
      <div class="k">Hinweis</div><div class="v">${escapeHtml(meta.note)}</div></div>` : "");

  $("#save-status").textContent = "Noch nicht gespeichert – die Datei liegt vorerst nur temporär bereit.";
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  toast("Sprachausgabe fertig. Bitte anhören und bei Bedarf speichern.");
}

function failJob(job) {
  $("#btn-speak").disabled = false;
  $("#btn-cancel-job").disabled = true;
  if (job.kind === "benchmark") {
    $("#benchmark-progress").classList.add("hidden");
    $("#benchmark-result").textContent = `Test fehlgeschlagen: ${job.error || "unbekannter Fehler"}`;
    toast("Geschwindigkeitstest fehlgeschlagen.", true);
    return;
  }
  $("#tts-progress").classList.add("hidden");
  const message = job.error || "Unbekannter Fehler.";
  showTtsError(
    `${message}\n\nEs wurde keine Ergebnisdatei erzeugt. Bitte die Hinweise im Tab „System & Modell“ prüfen.`
  );
  toast("Sprachausgabe fehlgeschlagen – es wurde nichts gespeichert.", true);
  if (job.result && job.result.trace) console.warn(job.result.trace);
  loadStatus(true);
}

async function cancelJob() {
  if (!state.job) return;
  try {
    await api(`/api/jobs/${encodeURIComponent(state.job.id)}/cancel`, { method: "POST" });
    toast("Abbruch angefordert. Der laufende Rechenschritt endet, sobald er fertig ist.");
  } catch (error) {
    toast(error.message, true);
  }
}

async function saveResult() {
  if (!state.lastJobId) return;
  const name = $("#result-name").value.trim();
  try {
    $("#btn-save-result").disabled = true;
    const payload = await api("/api/results", {
      method: "POST",
      body: JSON.stringify({ job_id: state.lastJobId, name }),
    });
    $("#save-status").textContent = `Gespeichert als „${payload.result.name}“ in data/ergebnisse.`;
    $("#result-name").value = "";
    toast("WAV-Datei lokal gespeichert.");
    await loadResults();
  } catch (error) {
    toast(error.message, true);
  } finally {
    $("#btn-save-result").disabled = false;
  }
}

/* ------------------------------------------------------------------ */
/* Ergebnisse                                                          */
/* ------------------------------------------------------------------ */

function renderResults() {
  const list = $("#results-list");
  $("#result-count").textContent = String(state.results.length);
  const empty = $("#results-empty");
  if (!state.results.length) {
    empty.classList.remove("hidden");
    list.innerHTML = "";
    return;
  }
  empty.classList.add("hidden");
  list.innerHTML = state.results.map((result) => `
    <div class="item">
      <div class="item-head">
        <div class="item-title">
          <strong>${escapeHtml(result.name)}</strong>
          <span class="tag ${result.is_clone ? "tag-master" : ""}">${result.is_clone ? "Referenzstimme" : "Piper"}</span>
          <span class="time">${fmtDate(result.created_at)} · ${fmtBytes(result.size_bytes)}</span>
        </div>
      </div>
      <div class="metrics">
        <div class="metric"><span class="k">Dauer</span><span class="v">${fmtDuration(result.info?.duration_s)}</span></div>
        <div class="metric"><span class="k">Samplerate</span><span class="v">${result.info?.sample_rate || "?"} Hz</span></div>
        <div class="metric"><span class="k">Stil</span><span class="v">${escapeHtml(result.preset_label || result.preset || "–")}</span></div>
        <div class="metric"><span class="k">Stimme</span><span class="v">${escapeHtml(result.voice || "–")}</span></div>
        <div class="metric"><span class="k">Rechenzeit</span><span class="v">${result.compute_seconds != null ? `${result.compute_seconds} s` : "–"}</span></div>
        <div class="metric"><span class="k">CPU-Modus</span><span class="v">${result.slow_mode ? "langsam" : "normal"}</span></div>
      </div>
      <audio controls preload="none" src="/api/results/${encodeURIComponent(result.id)}/audio"></audio>
      <div class="item-actions">
        <a class="btn btn-small btn-outline" href="/api/results/${encodeURIComponent(result.id)}/download">WAV herunterladen</a>
        <button class="btn btn-small btn-danger" data-action="delete-result" data-id="${result.id}">Löschen</button>
      </div>
      ${result.text ? `<p class="hint">Text: ${escapeHtml(result.text.slice(0, 220))}${result.text.length > 220 ? " …" : ""}</p>` : ""}
    </div>
  `).join("");
}

async function loadResults() {
  try {
    const payload = await api("/api/results");
    state.results = payload.results || [];
    renderResults();
    renderCompareSelects();
  } catch (error) {
    toast(error.message, true);
  }
}

function initResultActions() {
  $("#results-list").addEventListener("click", async (event) => {
    const button = event.target.closest('[data-action="delete-result"]');
    if (!button) return;
    const id = button.dataset.id;
    if (!confirm("Diese Ergebnisdatei endgültig von diesem Laptop löschen?")) return;
    try {
      await api(`/api/results/${encodeURIComponent(id)}`, { method: "DELETE" });
      toast("Ergebnis gelöscht.");
      await loadResults();
    } catch (error) {
      toast(error.message, true);
    }
  });
}

/* ------------------------------------------------------------------ */
/* Benchmark                                                           */
/* ------------------------------------------------------------------ */

function renderBenchmarkProgress(job) {
  if (!job || job.kind !== "benchmark") return;
  $("#benchmark-progress").classList.remove("hidden");
  $("#benchmark-fill").style.width = `${job.progress}%`;
  $("#benchmark-stage").textContent = job.stage || "Läuft …";
}

function initBenchmark() {
  $("#btn-benchmark").addEventListener("click", async () => {
    const button = $("#btn-benchmark");
    try {
      button.disabled = true;
      $("#benchmark-result").textContent = "";
      $("#benchmark-progress").classList.remove("hidden");
      const payload = await api("/api/benchmark", {
        method: "POST",
        body: JSON.stringify({
          slow_mode: $("#tts-slow").checked,
          threads: Number($("#tts-threads").value),
          voice: $("#tts-voice").value || null,
        }),
      });
      state.jobStart = Date.now();
      pollJob(payload.job.id);
    } catch (error) {
      $("#benchmark-result").textContent = error.message;
      $("#benchmark-progress").classList.add("hidden");
    } finally {
      button.disabled = false;
    }
  });
}

/* ------------------------------------------------------------------ */
/* Start                                                               */
/* ------------------------------------------------------------------ */

async function refreshAll() {
  await loadStatus();
  await loadRecordings();
  await loadResults();
}

function init() {
  initTabs();
  initUpload();
  initRecorder();
  initRecordingListActions();
  initCompare();
  initTtsControls();
  initResultActions();
  initBenchmark();
  $("#btn-refresh-status").addEventListener("click", () => loadStatus(true));

  refreshAll();
  // Status regelmäßig aktualisieren, damit neue Modelle erkannt werden
  setInterval(() => {
    if (document.visibilityState === "visible") loadStatus();
  }, 60000);
}

document.addEventListener("DOMContentLoaded", init);

/* Kleiner Haken ausschließlich für automatisierte Oberflächentests.
   Er ändert das Verhalten der App nicht und enthält keine Daten. */
window.__scw = { state, finishJob, failJob };
