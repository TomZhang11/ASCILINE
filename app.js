/**
 * ASCILINE ENGINE - Core Logic
 * =========================================
 * Handles WebSocket communication, frame buffering, 
 * and dual-mode rendering (Canvas/DOM).
 */

const player    = document.getElementById('ascii-player');
const canvas    = document.getElementById('ascii-canvas');
const ctx       = canvas.getContext('2d');
const statusEl  = document.getElementById('status');
const container = document.getElementById('player-container');
const overlay   = document.getElementById('play-overlay');

// ── STATE ──
let state = 'IDLE'; // IDLE | PLAYING | DISSOLVING
let ws = null;
const frameBuffer = [];
const BUFFER_SIZE = 4;
let targetFps = 24;
let frameInterval = 1000 / targetFps;
let renderMode = 1;

// Grid & Dimensions
let gridCols = 0, gridRows = 0;
let charWidth = 0, charHeight = 0;
let xPos = null, yPos = null;

// Timing & Metrics
let lastRenderTime = 0;
let frameCount = 0, currentFps = 0, lastFpsUpdate = 0;
let lastFrameView = null; // Stored for the ripple effect

// Character Lookup Table (optimization)
const CHAR_LUT = new Array(128);
for (let i = 0; i < 128; i++) CHAR_LUT[i] = String.fromCharCode(i);

/**
 * Pre-calculates positions and scales canvas for high-performance rendering.
 */
function buildCanvas(cols, rows) {
    gridCols = cols;
    gridRows = rows;
    ctx.font = 'bold 8px Courier New';
    charWidth = Math.ceil(ctx.measureText('M').width);
    charHeight = 8;

    canvas.width  = cols * charWidth;
    canvas.height = rows * charHeight;
    canvas.style.display = 'block';
    player.style.display = 'none';

    container.style.minWidth  = canvas.width + 'px';
    container.style.minHeight = canvas.height + 'px';

    ctx.font = 'bold 8px Courier New';
    ctx.textBaseline = 'top';

    xPos = new Float32Array(cols);
    yPos = new Float32Array(rows);
    for (let c = 0; c < cols; c++) xPos[c] = c * charWidth;
    for (let r = 0; r < rows; r++) yPos[r] = r * charHeight;
}

/**
 * Initiates WebSocket connection and stream handling.
 */
function startStream() {
    if (state !== 'IDLE') return;
    state = 'PLAYING';
    overlay.classList.add('hidden');
    statusEl.textContent = 'Connecting...';
    statusEl.style.color = 'var(--accent-color)';

    frameBuffer.length = 0;
    lastFrameView = null;
    frameCount = 0;
    currentFps = 0;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);
    ws.binaryType = 'arraybuffer';

    ws.onmessage = (event) => {
        if (state !== 'PLAYING') return;

        if (typeof event.data === 'string') {
            if (event.data.startsWith('INIT:')) {
                const p = event.data.split(':');
                targetFps = parseFloat(p[1]);
                frameInterval = 1000 / targetFps;
                renderMode = parseInt(p[2]);
                if (renderMode > 1) {
                    buildCanvas(parseInt(p[3]), parseInt(p[4]));
                } else {
                    player.style.display = 'block';
                    canvas.style.display = 'none';
                }
                return;
            }
            frameBuffer.push(event.data);
        } else {
            frameBuffer.push(event.data);
        }

        // Buffer Overflow Protection
        while (frameBuffer.length > BUFFER_SIZE * 3) frameBuffer.shift();

        // Start render loop once buffered
        if (frameBuffer.length >= BUFFER_SIZE && lastRenderTime === 0) {
            lastRenderTime = performance.now();
            lastFpsUpdate = lastRenderTime;
            requestAnimationFrame(renderFrame);
        }
    };

    ws.onopen = () => {
        statusEl.textContent = 'Buffering...';
    };

    ws.onclose = () => {
        if (state === 'PLAYING') {
            statusEl.textContent = 'Stream Ended.';
            statusEl.style.color = '#888';
            setTimeout(() => resetToIdle(), 1500);
        }
    };

    ws.onerror = () => {
        statusEl.textContent = 'Connection Error!';
        statusEl.style.color = '#ff0000';
        setTimeout(() => resetToIdle(), 2000);
    };
}

/**
 * Main render loop using requestAnimationFrame.
 */
function renderFrame(now) {
    if (state !== 'PLAYING') return;
    requestAnimationFrame(renderFrame);

    const elapsed = now - lastRenderTime;
    if (elapsed < frameInterval) return;

    // FPS Counter
    frameCount++;
    if (now - lastFpsUpdate >= 1000) {
        currentFps = frameCount;
        frameCount = 0;
        lastFpsUpdate = now;
        let modeText = 'B&W';
        const modes = { 2: '512 Color', 3: '32K Color', 4: '262K Color', 5: '16M Ultra' };
        modeText = modes[renderMode] || 'B&W';
        statusEl.textContent = `FPS: ${currentFps}/${Math.round(targetFps)} | Buf: ${frameBuffer.length} | ${modeText}`;
    }

    if (frameBuffer.length === 0) return;
    lastRenderTime = now;

    const frame = frameBuffer.shift();

    if (renderMode === 1) {
        player.textContent = frame;
    } else {
        const view = new Uint8Array(frame);
        lastFrameView = view; 

        ctx.fillStyle = '#050505';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.font = 'bold 8px Courier New';
        ctx.textBaseline = 'top';

        let col = 0, row = 0, prevPacked = -1;
        for (let idx = 0; idx < view.length; idx += 4) {
            const packed = (view[idx+1] << 16) | (view[idx+2] << 8) | view[idx+3];
            if (packed !== prevPacked) {
                ctx.fillStyle = `rgb(${view[idx+1]},${view[idx+2]},${view[idx+3]})`;
                prevPacked = packed;
            }
            ctx.fillText(CHAR_LUT[view[idx]], xPos[col], yPos[row]);
            col++;
            if (col >= gridCols) { col = 0; row++; }
        }
    }
}

/**
 * Visual Effect: Ripple Dissolve
 * Triggered on click during playback.
 */
function triggerRipple(clickX, clickY) {
    if (!lastFrameView || renderMode === 1) {
        resetToIdle();
        return;
    }

    state = 'DISSOLVING';
    if (ws) { ws.onclose = null; ws.close(); ws = null; }

    const fv = lastFrameView;
    const rippleSpeed = 400;       
    const waveFront   = 70;        
    const maxShake    = 6;         
    const maxDist = Math.sqrt(canvas.width * canvas.width + canvas.height * canvas.height);
    const startTime = performance.now();

    statusEl.textContent = '';

    function animateRipple(now) {
        const elapsed = (now - startTime) / 1000;
        const radius = elapsed * rippleSpeed;

        if (radius > maxDist + waveFront + 20) {
            resetToIdle();
            return;
        }

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.font = 'bold 8px Courier New';
        ctx.textBaseline = 'top';

        let col = 0, row = 0;

        for (let idx = 0; idx < fv.length; idx += 4) {
            const px = xPos[col];
            const py = yPos[row];
            const dx = px - clickX;
            const dy = py - clickY;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (dist > radius) {
                ctx.globalAlpha = 1;
                ctx.fillStyle = `rgb(${fv[idx+1]},${fv[idx+2]},${fv[idx+3]})`;
                ctx.fillText(CHAR_LUT[fv[idx]], px, py);
            } else if (dist > radius - waveFront) {
                const progress = (radius - dist) / waveFront; 
                const shake = Math.sin(progress * Math.PI) * maxShake;
                const ox = (Math.random() - 0.5) * shake * 2;
                const oy = (Math.random() - 0.5) * shake * 2;

                ctx.globalAlpha = 1 - progress;
                ctx.fillStyle = `rgb(${fv[idx+1]},${fv[idx+2]},${fv[idx+3]})`;
                ctx.fillText(CHAR_LUT[fv[idx]], px + ox, py + oy);
            }

            col++;
            if (col >= gridCols) { col = 0; row++; }
        }

        ctx.globalAlpha = 1;
        requestAnimationFrame(animateRipple);
    }

    requestAnimationFrame(animateRipple);
}

function resetToIdle() {
    state = 'IDLE';
    if (ws) { ws.onclose = null; ws.close(); ws = null; }
    frameBuffer.length = 0;
    lastRenderTime = 0;
    lastFrameView = null;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    player.textContent = '';
    overlay.classList.remove('hidden');
    statusEl.textContent = 'Ready';
    statusEl.style.color = 'rgba(255,255,255,0.6)';
}

// ── EVENT LISTENERS ──
overlay.addEventListener('click', (e) => {
    e.stopPropagation();
    startStream();
});

container.addEventListener('click', (e) => {
    if (state !== 'PLAYING') return;

    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const clickX = (e.clientX - rect.left) * scaleX;
    const clickY = (e.clientY - rect.top) * scaleY;

    triggerRipple(clickX, clickY);
});
