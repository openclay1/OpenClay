// sketch.js — OpenClay p5.js clay interface
// A living clay organism that thinks with you.
// Connects to local Ollama via clay_server.py

let clayPoints = [];
let numPoints = 120;
let baseRadius;
let state = "idle"; // idle | listening | thinking | speaking | recording | muted | executing
let inputText = "";
let responseText = "";
let displayedText = "";
let charIndex = 0;
let thinkingStart = 0;
let breathPhase = 0;
let particles = [];
let cursorBlink = 0;
let hintOpacity = 255;
let filePulse = 0;
let canvasStatus = ""; // "Escuchando..." | "Procesando..." | ""
let canvasStatusAlpha = 0;
let meshActive = false;
let logPulse = 0; // log write indicator pulse
let heartbeatPulse = 0; // expands blob when first token arrives
let _thinkingTextIdx = 0;
const THINKING_TEXTS = ["pensando...", "thinking...", "réfléchis...", "pensando..."];
let execResultData = null; // data from last sandbox execution
let execResultTimer = 0;

// Task engine state
let activeTask = null; // {id, goal, step, current_step}
let taskPulsePhase = 0;
let taskCompletePulse = 0; // celebration pulse on completion

// Agent morph animation
let morphProgress = 1; // 0→1 during color transition
let morphFrom = [224, 100, 56];
let morphTo = [224, 100, 56];

// Smooth animation
let targetCY, currentCY, targetRadius, currentRadius;
let animInited = false;

// Colors — warm clay earth
const BG = [22, 19, 16];
const SURFACE = [27, 24, 20];
let CLAY_BASE = [224, 100, 56]; // now mutable for agent color changes
const TEXT_CLR = [206, 200, 192];
const MUTED_CLR = [122, 116, 104];
const MESH_GREEN = [39, 174, 96];

function setup() {
  let canvas = createCanvas(windowWidth, windowHeight);
  canvas.parent("canvas-container");
  baseRadius = min(width, height) * 0.16;
  for (let i = 0; i < numPoints; i++) {
    clayPoints.push({
      angle: map(i, 0, numPoints, 0, TWO_PI),
      baseR: baseRadius, r: baseRadius,
      noiseOff: random(1000),
    });
  }
  textFont("Satoshi, Inter, system-ui, sans-serif");
  baseRadius = 0;
}

// Called from HTML — bridges unified appState
function setClayState(newState) {
  if (newState === 'listening') {
    state = "recording";
    canvasStatus = "Escuchando...";
    canvasStatusAlpha = 255;
  } else if (newState === 'muted') {
    state = "muted";
    canvasStatus = "";
  } else if (newState === 'thinking') {
    state = "thinking";
    canvasStatus = "";
  } else if (newState === 'speaking') {
    state = "speaking";
    canvasStatus = "";
  } else if (newState === 'executing') {
    state = "executing";
    canvasStatus = "Ejecutando...";
    canvasStatusAlpha = 255;
  } else {
    state = "idle";
    canvasStatus = "";
  }
}

// Called from HTML
function handleSend() {
  let input = document.getElementById('clay-input');
  let text = input.value.trim();
  if (!text || state === "thinking") return;
  inputText = text;
  input.value = "";
  hintOpacity = 0;
  state = "thinking";
  thinkingStart = millis();
  responseText = ""; displayedText = ""; charIndex = 0;
  canvasStatus = "";
  for (let i = 0; i < 15; i++) particles.push(makeParticle(width/2, currentCY || height*0.35));

  // Track user message in history
  if (typeof addToHistory === 'function') addToHistory('user', text);

  askOllama(inputText);
}

function triggerPulse() { filePulse = 1.0; }
function triggerLogPulse() { logPulse = 1.0; }

// ─── Agent color morphing ───
function hexToRgb(hex) {
  hex = hex.replace('#', '');
  return [parseInt(hex.substring(0,2),16), parseInt(hex.substring(2,4),16), parseInt(hex.substring(4,6),16)];
}

function triggerAgentMorph(colorHex) {
  morphFrom = [...CLAY_BASE];
  morphTo = hexToRgb(colorHex);
  morphProgress = 0;
  // Burst of particles for the transition
  for (let i = 0; i < 20; i++) {
    particles.push(makeParticle(width/2 + random(-baseRadius,baseRadius),
      (currentCY||height*0.35) + random(-baseRadius,baseRadius)));
  }
}

function setClayAccent(colorHex) {
  let rgb = hexToRgb(colorHex);
  CLAY_BASE[0] = rgb[0]; CLAY_BASE[1] = rgb[1]; CLAY_BASE[2] = rgb[2];
  morphFrom = [...rgb]; morphTo = [...rgb]; morphProgress = 1;
}

// ─── Workflow send (called from index.html) ───
function handleSendRaw(text, workflowPrompt) {
  let combined = workflowPrompt + '\n\n' + text;
  let input = document.getElementById('clay-input');
  if (input) input.value = '';
  inputText = text;
  hintOpacity = 0;
  state = "thinking";
  thinkingStart = millis();
  responseText = ""; displayedText = ""; charIndex = 0;
  canvasStatus = "";
  for (let i = 0; i < 15; i++) particles.push(makeParticle(width/2, currentCY || height*0.35));
  if (typeof addToHistory === 'function') addToHistory('user', text);
  askOllama(combined);
}

// ─── Show execution result on canvas ───
function showExecResult(data) {
  execResultData = data;
  execResultTimer = 300; // ~5 seconds at 60fps
  state = "speaking";
  if (data.ok) {
    responseText = "✅ Ejecución exitosa:\n" + (data.stdout || '(sin output)');
  } else {
    responseText = "❌ Error en ejecución:\n" + (data.error || data.stderr || 'Unknown error');
  }
  displayedText = ""; charIndex = 0;
}

// ─── Task engine canvas integration ───
function updateActiveTask(taskInfo) {
  // Called from index.html status polling
  if (!taskInfo && activeTask) {
    // Task just finished — celebration pulse
    taskCompletePulse = 1.0;
    activeTask = null;
  } else {
    activeTask = taskInfo;
  }
}

function triggerTaskComplete() {
  taskCompletePulse = 1.0;
  // Big burst of particles
  for (let i = 0; i < 30; i++) {
    particles.push(makeParticle(
      width/2 + random(-baseRadius*1.5, baseRadius*1.5),
      (currentCY||height*0.35) + random(-baseRadius*1.5, baseRadius*1.5)
    ));
  }
}

// Legacy bridge — still called if setClayState isn't available
function setRecordingState(recording) {
  state = recording ? "recording" : "idle";
}

async function askOllama(prompt) {
  const demoThinkStart = Date.now();
  // Expose abort controller so toggleMute() can cancel streaming
  const _ctrl = new AbortController();
  window._streamAbortController = _ctrl;
  try {
    const resp = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
      signal: _ctrl.signal,
    });
    if (!resp.ok) throw new Error("Server error: " + resp.status);

    // Check if JSON response (agentic mode or command)
    const contentType = resp.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await resp.json();
      if (data.command) {
        responseText = "Modo cambiado a: " + data.mode;
        state = "speaking"; return;
      }
      if (data.response) {
        // Demo Mode: hold thinking state for at least 2s so blob looks alive on camera
        if (window.demoMode) {
          const elapsed = Date.now() - demoThinkStart;
          if (elapsed < 2000) await new Promise(r => setTimeout(r, 2000 - elapsed));
        }
        responseText = data.response;
        state = "speaking";
        if (typeof addToHistory === 'function') addToHistory('assistant', data.response);
        if (typeof speakText === 'function') speakText(responseText);
        return;
      }
    }

    // Streaming response
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let fullText = "";
    let _firstToken = true;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const lines = decoder.decode(value, { stream: true }).split("\n").filter(l => l.trim());
      for (const line of lines) {
        try {
          const data = JSON.parse(line);
          if (data.response) {
            if (_firstToken) { heartbeatPulse = 1.0; _firstToken = false; }
            fullText += data.response; responseText = fullText;
          }
          if (data.done) {
            // Demo Mode: minimum 2s thinking before speaking
            if (window.demoMode) {
              const elapsed = Date.now() - demoThinkStart;
              if (elapsed < 2000) await new Promise(r => setTimeout(r, 2000 - elapsed));
            }
            state = "speaking";
          }
        } catch (e) {}
      }
    }
    if (state !== "speaking") state = "speaking";
    if (typeof addToHistory === 'function') addToHistory('assistant', fullText);
    if (typeof speakText === 'function') speakText(fullText);
  } catch (err) {
    if (err && err.name === 'AbortError') {
      // User cancelled — stay quiet, just return to idle
      if (state === 'thinking') state = 'idle';
      return;
    }
    responseText = "No pude conectar con el modelo local.\nVerifica que Ollama este corriendo.";
    state = "speaking";
  } finally {
    if (window._streamAbortController === _ctrl) window._streamAbortController = null;
  }
}

function draw() {
  background(BG);
  breathPhase += 0.015;

  if (!animInited) {
    let fullR = min(width, height) * 0.192;
    targetCY = height * 0.35; currentCY = height * 0.35;
    targetRadius = fullR; currentRadius = 0;
    animInited = true;
  }

  // Morph CLAY_BASE color smoothly between agents
  if (morphProgress < 1) {
    morphProgress = min(1, morphProgress + 0.02);
    let ease = morphProgress * morphProgress * (3 - 2 * morphProgress); // smoothstep
    CLAY_BASE[0] = lerp(morphFrom[0], morphTo[0], ease);
    CLAY_BASE[1] = lerp(morphFrom[1], morphTo[1], ease);
    CLAY_BASE[2] = lerp(morphFrom[2], morphTo[2], ease);
  }

  let fullR = min(width, height) * 0.192;
  if (state === "speaking" || (state === "thinking" && responseText.length > 0)) {
    targetRadius = fullR * 0.5; targetCY = height * 0.18;
  } else if (state === "thinking") {
    targetRadius = fullR; targetCY = height * 0.32;
  } else if (state === "recording") {
    targetRadius = fullR * 1.05; targetCY = height * 0.35;
  } else if (state === "muted") {
    targetRadius = fullR * 0.85; targetCY = height * 0.35;
  } else if (state === "executing") {
    // Executing: geometric/focused — compact, pulsing
    targetRadius = fullR * 0.7; targetCY = height * 0.32;
  } else {
    targetRadius = fullR; targetCY = height * 0.35;
  }

  // File pulse
  if (filePulse > 0) { targetRadius = fullR * (1 + filePulse * 0.15); filePulse *= 0.92; if (filePulse < 0.01) filePulse = 0; }

  // Heartbeat pulse — decays after first token arrives
  if (heartbeatPulse > 0) { heartbeatPulse *= 0.88; if (heartbeatPulse < 0.01) heartbeatPulse = 0; }

  currentCY = lerp(currentCY, targetCY, 0.06);
  currentRadius = lerp(currentRadius, targetRadius, 0.06);
  baseRadius = currentRadius;
  let cx = width / 2, cy = currentCY;

  drawGlow(cx, cy);
  drawClay(cx, cy);
  updateParticles();

  if (state === "idle") drawIdleState(cx, cy);
  else if (state === "recording") drawRecordingState(cx, cy);
  else if (state === "thinking") drawThinkingState(cx, cy);
  else if (state === "speaking") drawSpeakingState(cx, cy);
  else if (state === "muted") drawMutedState(cx, cy);
  else if (state === "executing") drawExecutingState(cx, cy);

  if (inputText && state !== "idle" && state !== "recording" && state !== "muted") drawQuestionEcho(cx);

  // Log write indicator — small pulsing dot near top-right
  if (logPulse > 0) {
    logPulse *= 0.95;
    if (logPulse < 0.01) logPulse = 0;
    noStroke();
    fill(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], logPulse * 200);
    ellipse(width - 30, 28, 6 + logPulse * 6);
    fill(TEXT_CLR[0], TEXT_CLR[1], TEXT_CLR[2], logPulse * 150);
    textAlign(RIGHT, CENTER); textSize(8);
    text("log", width - 38, 28);
  }

  // Canvas status text (Escuchando... / Procesando...)
  if (canvasStatusAlpha > 0 && canvasStatus) {
    drawCanvasStatus(cx, cy);
  }
  if (!canvasStatus && canvasStatusAlpha > 0) canvasStatusAlpha = max(0, canvasStatusAlpha - 5);

  // Mesh indicator
  if (meshActive) drawMeshIndicator();

  // Task indicator
  if (activeTask) {
    taskPulsePhase += 0.03;
    drawTaskIndicator(cx, cy);
  }

  // Task complete celebration
  if (taskCompletePulse > 0) {
    taskCompletePulse *= 0.96;
    if (taskCompletePulse < 0.01) taskCompletePulse = 0;
    // Expanding ring
    noFill();
    stroke(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], taskCompletePulse * 200);
    strokeWeight(2 + taskCompletePulse * 3);
    let ringR = baseRadius * (1.5 + (1 - taskCompletePulse) * 2);
    ellipse(cx, cy, ringR * 2);
  }

  cursorBlink += 0.05;
}

function drawGlow(cx, cy) {
  noStroke();
  let pulseSize = state === "thinking" ? baseRadius * 2.8 + sin(breathPhase*3)*35
    : state === "recording" ? baseRadius * 3.0 + sin(breathPhase*1.5)*20
    : state === "muted" ? baseRadius * 1.8
    : state === "executing" ? baseRadius * 2.2 + sin(breathPhase*5)*18
    : baseRadius * 2.4 + sin(breathPhase)*12;

  // Heartbeat burst on first token
  if (heartbeatPulse > 0) pulseSize += heartbeatPulse * baseRadius * 0.8;

  let layers = 7;
  for (let i = layers; i > 0; i--) {
    let a = map(i, layers, 0, 4, 22);
    if (state === "thinking") a *= 2.2;
    else if (state === "speaking") a *= 1.4;
    if (state === "recording") { fill(200, 50, 50, a * 1.5); }
    else if (state === "muted") { fill(MUTED_CLR[0], MUTED_CLR[1], MUTED_CLR[2], a * 0.6); }
    else { fill(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], a); }
    ellipse(cx, cy, pulseSize * (i/layers) * 2);
  }
}

function drawClay(cx, cy) {
  for (let p of clayPoints) {
    let targetR = baseRadius;
    let nv = noise(p.noiseOff + frameCount * 0.008) - 0.5;
    if (state === "thinking") {
      targetR += (noise(p.noiseOff + frameCount*0.065)-0.5) * baseRadius * 0.38;
      targetR += sin(p.angle*3 + frameCount*0.13) * baseRadius * 0.1;
      if (heartbeatPulse > 0) targetR += heartbeatPulse * baseRadius * 0.25;
    } else if (state === "speaking") {
      targetR += sin(p.angle*2 + breathPhase*2) * baseRadius * 0.06 + nv * baseRadius * 0.08;
    } else if (state === "recording") {
      targetR += sin(breathPhase*1.5 + p.angle*4) * baseRadius * 0.1 + nv * baseRadius * 0.1;
    } else if (state === "executing") {
      // Executing: geometric/angular — more structured deformations
      let facets = 6;
      let facetAngle = floor(p.angle / (TWO_PI / facets)) * (TWO_PI / facets);
      let facetBlend = 0.6 + 0.4 * cos((p.angle - facetAngle) * facets);
      targetR *= facetBlend;
      targetR += sin(breathPhase * 4 + p.angle * facets) * baseRadius * 0.04;
    } else if (state === "muted") {
      // Muted: very subtle, calm deformation
      targetR += nv * baseRadius * 0.03;
    } else {
      targetR += sin(breathPhase + p.angle*2) * baseRadius * 0.04 + nv * baseRadius * 0.06;
    }
    p.r = lerp(p.r, targetR, 0.08);
    p.noiseOff += 0.003;
  }
  noStroke();
  if (state === "recording") {
    fill(200, 70, 50);
  } else if (state === "muted") {
    fill(160, 90, 65);
  } else if (state === "executing") {
    // Executing: slightly brighter, electric feel
    fill(min(255, CLAY_BASE[0]+30), min(255, CLAY_BASE[1]+20), CLAY_BASE[2]);
  } else {
    fill(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2]);
  }
  beginShape();
  for (let i = 0; i <= numPoints; i++) {
    let p = clayPoints[i % numPoints];
    curveVertex(cx + cos(p.angle)*p.r, cy + sin(p.angle)*p.r);
  }
  let p0 = clayPoints[0], p1 = clayPoints[1];
  curveVertex(cx + cos(p0.angle)*p0.r, cy + sin(p0.angle)*p0.r);
  curveVertex(cx + cos(p1.angle)*p1.r, cy + sin(p1.angle)*p1.r);
  endShape();
  // Inner highlight
  let hl = state === "muted" ? [140, 100, 80, 50] : [CLAY_BASE[0]+20, CLAY_BASE[1]+15, CLAY_BASE[2]+10, 80];
  fill(hl[0], hl[1], hl[2], hl[3]);
  beginShape();
  for (let i = 0; i <= numPoints; i++) {
    let p = clayPoints[i % numPoints];
    curveVertex(cx + cos(p.angle)*p.r*0.7, cy + sin(p.angle)*p.r*0.7);
  }
  curveVertex(cx + cos(p0.angle)*p0.r*0.7, cy + sin(p0.angle)*p0.r*0.7);
  curveVertex(cx + cos(p1.angle)*p1.r*0.7, cy + sin(p1.angle)*p1.r*0.7);
  endShape();
}

function drawIdleState(cx, cy) {
  if (hintOpacity > 0) {
    fill(MUTED_CLR[0], MUTED_CLR[1], MUTED_CLR[2], hintOpacity);
    noStroke(); textAlign(CENTER, CENTER); textSize(13);
    text("todo es local  /  everything is local", cx, cy + baseRadius + 40);
    hintOpacity = max(0, hintOpacity - 0.3);
  }
}

function drawRecordingState(cx, cy) {
  fill(200, 70, 50, 180 + sin(breathPhase*3)*75);
  noStroke(); textAlign(CENTER, CENTER); textSize(14);
  text("\uD83D\uDD34 Escuchando... / Listening...", cx, cy + baseRadius + 40);
}

function drawMutedState(cx, cy) {
  fill(MUTED_CLR[0], MUTED_CLR[1], MUTED_CLR[2], 120);
  noStroke(); textAlign(CENTER, CENTER); textSize(12);
  text("\uD83D\uDD07 silenciado", cx, cy + baseRadius + 40);
}

function drawCanvasStatus(cx, cy) {
  canvasStatusAlpha = min(255, canvasStatusAlpha + 10);
  fill(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], canvasStatusAlpha * 0.8);
  noStroke(); textAlign(CENTER, CENTER); textSize(12);
  text(canvasStatus, cx, cy + baseRadius + 60);
}

function drawThinkingState(cx, cy) {
  let elapsed = (millis() - thinkingStart) / 1000;

  // Rotate THINKING_TEXTS every 4 seconds (240 frames at 60fps)
  _thinkingTextIdx = floor(elapsed / 4) % THINKING_TEXTS.length;

  // Fade between rotations — alpha dips at the transition boundary
  let posInCycle = (elapsed % 4) / 4; // 0→1 within each 4s window
  let fadeAlpha = posInCycle < 0.1 ? map(posInCycle, 0, 0.1, 0, 200)
                : posInCycle > 0.85 ? map(posInCycle, 0.85, 1, 200, 0)
                : 200;

  // Orbiting dots
  for (let i = 0; i < 3; i++) {
    let dotAngle = breathPhase*3 + (TWO_PI/3)*i;
    let dotR = baseRadius + 25 + sin(breathPhase*2+i)*8;
    fill(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], map(sin(breathPhase*4+i*2),-1,1,120,255));
    noStroke(); ellipse(cx + cos(dotAngle)*dotR, cy + sin(dotAngle)*dotR, 7);
  }

  // Main thinking text — 16px, rotating language
  let thinkLabel = elapsed >= 30
    ? (floor(elapsed / 4) % 2 === 0 ? "casi listo..." : "almost there...")
    : THINKING_TEXTS[_thinkingTextIdx];

  fill(MUTED_CLR[0], MUTED_CLR[1], MUTED_CLR[2], fadeAlpha);
  textAlign(CENTER, CENTER); textSize(16);
  text(thinkLabel, cx, cy + baseRadius + 40);

  // Elapsed seconds counter
  fill(MUTED_CLR[0], MUTED_CLR[1], MUTED_CLR[2], 120);
  textSize(11);
  text(floor(elapsed) + "s", cx, cy + baseRadius + 62);

  if (responseText.length > 0) drawResponseText(cx, cy);
}

function drawSpeakingState(cx, cy) { drawResponseText(cx, cy); }

function drawResponseText(cx, cy) {
  // Demo Mode: slow typewriter (~1 char per frame). Normal: 3 chars per frame.
  const charStep = (window.demoMode) ? 1 : 3;
  if (charIndex < responseText.length) {
    charIndex = min(charIndex + charStep, responseText.length);
    displayedText = responseText.substring(0, charIndex);
  }
  let textBoxY = cy + baseRadius + 25;
  let textBoxW = min(width * 0.88, 580);
  let textBoxX = cx - textBoxW / 2;
  let panelH = max(60, height - textBoxY - 110);

  fill(SURFACE[0], SURFACE[1], SURFACE[2], 235);
  stroke(55, 51, 48, 80); strokeWeight(1);
  rect(textBoxX - 12, textBoxY - 8, textBoxW + 24, panelH, 10);

  noStroke(); fill(TEXT_CLR);
  textAlign(LEFT, TOP);
  textSize(min(13, width * 0.032));
  textLeading(min(20, width * 0.05));
  text(displayedText, textBoxX, textBoxY, textBoxW, panelH - 12);

  if (charIndex < responseText.length) {
    fill(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], map(sin(cursorBlink*8),-1,1,0,255));
    noStroke(); ellipse(textBoxX + 6, textBoxY + panelH - 16, 5, 5);
  }
}

function drawQuestionEcho(cx) {
  fill(MUTED_CLR[0], MUTED_CLR[1], MUTED_CLR[2], 150);
  textAlign(CENTER, CENTER); textSize(11);
  let y = currentCY - baseRadius - 25;
  text("\u201C" + inputText + "\u201D", cx, y, min(width*0.7, 480));
}

function drawExecutingState(cx, cy) {
  // Geometric spinner around the blob
  let segments = 6;
  for (let i = 0; i < segments; i++) {
    let a = (TWO_PI / segments) * i + breathPhase * 4;
    let r = baseRadius + 20;
    let len = 12 + sin(breathPhase * 6 + i * 1.5) * 6;
    let x1 = cx + cos(a) * r;
    let y1 = cy + sin(a) * r;
    let x2 = cx + cos(a) * (r + len);
    let y2 = cy + sin(a) * (r + len);
    stroke(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], 150 + sin(breathPhase*5+i)*80);
    strokeWeight(2);
    line(x1, y1, x2, y2);
  }
  noStroke();
  fill(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], 180 + sin(breathPhase*5)*75);
  textAlign(CENTER, CENTER); textSize(12);
  text("⚙ ejecutando...", cx, cy + baseRadius + 40);
}

function drawTaskIndicator(cx, cy) {
  // Top-left indicator showing active task
  let x = 16, y = meshActive ? 50 : 28;

  // Pulsing dot
  noStroke();
  let pulse = sin(taskPulsePhase * 3) * 0.3 + 0.7;
  fill(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], 200 * pulse);
  ellipse(x + 4, y, 6 + pulse * 2);

  // Label
  fill(TEXT_CLR[0], TEXT_CLR[1], TEXT_CLR[2], 160);
  textAlign(LEFT, CENTER); textSize(8);
  text("tarea", x + 12, y);

  // Step counter
  if (activeTask && activeTask.step !== undefined) {
    fill(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], 140);
    textSize(7);
    text("paso " + activeTask.step, x + 12, y + 11);
  }

  // Goal preview (truncated)
  if (activeTask && activeTask.goal) {
    fill(MUTED_CLR[0], MUTED_CLR[1], MUTED_CLR[2], 100);
    textSize(7);
    let goalPreview = activeTask.goal.substring(0, 30) + (activeTask.goal.length > 30 ? "..." : "");
    text(goalPreview, x + 12, y + 22);
  }
}

function drawMeshIndicator() {
  // Small green dot + text at top-left
  noStroke();
  fill(MESH_GREEN[0], MESH_GREEN[1], MESH_GREEN[2], 180 + sin(breathPhase*2)*40);
  ellipse(24, 28, 7);
  fill(MESH_GREEN[0], MESH_GREEN[1], MESH_GREEN[2], 120);
  textAlign(LEFT, CENTER); textSize(9);
  text("mesh", 32, 28);
}

function makeParticle(x, y) {
  return { x, y, vx: random(-2,2), vy: random(-3,-0.5), life: 1.0,
    decay: random(0.005,0.02), size: random(3,7) };
}

function updateParticles() {
  noStroke();
  for (let i = particles.length-1; i >= 0; i--) {
    let p = particles[i];
    p.x += p.vx; p.y += p.vy; p.vy += 0.01; p.life -= p.decay;
    if (p.life <= 0) { particles.splice(i,1); continue; }
    fill(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], p.life*150);
    ellipse(p.x, p.y, p.size*p.life);
  }
  if (state === "thinking" && frameCount % 10 === 0) {
    particles.push(makeParticle(width/2 + random(-baseRadius,baseRadius),
      currentCY + random(-baseRadius,baseRadius)));
  }
  if (state === "executing" && frameCount % 6 === 0) {
    // Faster, more focused particles for execution
    let a = random(TWO_PI);
    particles.push(makeParticle(width/2 + cos(a)*baseRadius, currentCY + sin(a)*baseRadius));
  }
}

function windowResized() {
  resizeCanvas(windowWidth, windowHeight);
  baseRadius = min(width, height) * 0.16;
}
