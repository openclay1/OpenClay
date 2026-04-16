// sketch.js — OpenClay p5.js clay interface
// A living clay organism that thinks with you.
// Connects to local Ollama via clay_server.py

let clayPoints = [];
let numPoints = 120;
let baseRadius;
let state = "idle"; // idle | listening | thinking | speaking | recording | muted
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

// Smooth animation
let targetCY, currentCY, targetRadius, currentRadius;
let animInited = false;

// Colors — warm clay earth
const BG = [22, 19, 16];
const SURFACE = [27, 24, 20];
const CLAY_BASE = [224, 100, 56];
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

// Legacy bridge — still called if setClayState isn't available
function setRecordingState(recording) {
  state = recording ? "recording" : "idle";
}

async function askOllama(prompt) {
  try {
    const resp = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
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
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const lines = decoder.decode(value, { stream: true }).split("\n").filter(l => l.trim());
      for (const line of lines) {
        try {
          const data = JSON.parse(line);
          if (data.response) { fullText += data.response; responseText = fullText; }
          if (data.done) state = "speaking";
        } catch (e) {}
      }
    }
    if (state !== "speaking") state = "speaking";
    if (typeof addToHistory === 'function') addToHistory('assistant', fullText);
    if (typeof speakText === 'function') speakText(fullText);
  } catch (err) {
    responseText = "No pude conectar con el modelo local.\nVerifica que Ollama este corriendo.";
    state = "speaking";
  }
}

function draw() {
  background(BG);
  breathPhase += 0.015;

  if (!animInited) {
    let fullR = min(width, height) * 0.16;
    targetCY = height * 0.35; currentCY = height * 0.35;
    targetRadius = fullR; currentRadius = 0;
    animInited = true;
  }

  let fullR = min(width, height) * 0.16;
  if (state === "speaking" || (state === "thinking" && responseText.length > 0)) {
    targetRadius = fullR * 0.5; targetCY = height * 0.18;
  } else if (state === "thinking") {
    targetRadius = fullR; targetCY = height * 0.32;
  } else if (state === "recording") {
    targetRadius = fullR * 1.05; targetCY = height * 0.35;
  } else if (state === "muted") {
    // Muted: contract slightly
    targetRadius = fullR * 0.85; targetCY = height * 0.35;
  } else {
    targetRadius = fullR; targetCY = height * 0.35;
  }

  // File pulse
  if (filePulse > 0) { targetRadius = fullR * (1 + filePulse * 0.15); filePulse *= 0.92; if (filePulse < 0.01) filePulse = 0; }

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

  if (inputText && state !== "idle" && state !== "recording" && state !== "muted") drawQuestionEcho(cx);

  // Canvas status text (Escuchando... / Procesando...)
  if (canvasStatusAlpha > 0 && canvasStatus) {
    drawCanvasStatus(cx, cy);
  }
  if (!canvasStatus && canvasStatusAlpha > 0) canvasStatusAlpha = max(0, canvasStatusAlpha - 5);

  // Mesh indicator
  if (meshActive) drawMeshIndicator();

  cursorBlink += 0.05;
}

function drawGlow(cx, cy) {
  noStroke();
  let pulseSize = state === "thinking" ? baseRadius * 2.5 + sin(breathPhase*3)*30
    : state === "recording" ? baseRadius * 2.8 + sin(breathPhase*1.5)*20
    : state === "muted" ? baseRadius * 1.8
    : baseRadius * 2.2 + sin(breathPhase)*10;
  for (let i = 5; i > 0; i--) {
    let a = map(i, 5, 0, 3, 15);
    if (state === "thinking") a *= 1.8;
    if (state === "recording") { fill(200, 50, 50, a * 1.5); }
    else if (state === "muted") { fill(MUTED_CLR[0], MUTED_CLR[1], MUTED_CLR[2], a * 0.6); }
    else { fill(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], a); }
    ellipse(cx, cy, pulseSize * (i/5) * 2);
  }
}

function drawClay(cx, cy) {
  for (let p of clayPoints) {
    let targetR = baseRadius;
    let nv = noise(p.noiseOff + frameCount * 0.008) - 0.5;
    if (state === "thinking") {
      targetR += (noise(p.noiseOff + frameCount*0.04)-0.5) * baseRadius * 0.35;
      targetR += sin(p.angle*3 + frameCount*0.08) * baseRadius * 0.08;
    } else if (state === "speaking") {
      targetR += sin(p.angle*2 + breathPhase*2) * baseRadius * 0.06 + nv * baseRadius * 0.08;
    } else if (state === "recording") {
      targetR += sin(breathPhase*1.5 + p.angle*4) * baseRadius * 0.1 + nv * baseRadius * 0.1;
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
    // Desaturated clay — shift hue toward brown/gray
    fill(160, 90, 65);
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
  for (let i = 0; i < 3; i++) {
    let dotAngle = breathPhase*3 + (TWO_PI/3)*i;
    let dotR = baseRadius + 25 + sin(breathPhase*2+i)*8;
    fill(CLAY_BASE[0], CLAY_BASE[1], CLAY_BASE[2], map(sin(breathPhase*4+i*2),-1,1,100,255));
    noStroke(); ellipse(cx + cos(dotAngle)*dotR, cy + sin(dotAngle)*dotR, 7);
  }
  fill(MUTED_CLR[0], MUTED_CLR[1], MUTED_CLR[2], 180);
  textAlign(CENTER, CENTER); textSize(12);
  let dots = ".".repeat(floor(elapsed*2) % 4);
  text("pensando" + dots, cx, cy + baseRadius + 40);
  if (responseText.length > 0) drawResponseText(cx, cy);
}

function drawSpeakingState(cx, cy) { drawResponseText(cx, cy); }

function drawResponseText(cx, cy) {
  if (charIndex < responseText.length) {
    charIndex = min(charIndex + 3, responseText.length);
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
}

function windowResized() {
  resizeCanvas(windowWidth, windowHeight);
  baseRadius = min(width, height) * 0.16;
}
