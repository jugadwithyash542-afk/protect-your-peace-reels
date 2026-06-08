import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { exec, spawn, execSync } from 'child_process';
import fs from 'fs';

// Limit glibc memory arena creation to prevent memory fragmentation OOM
process.env.MALLOC_ARENA_MAX = '2';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Boot-time python dependency installation check
const pythonPackagesDir = path.join(__dirname, 'python_packages');
if (!fs.existsSync(pythonPackagesDir) || fs.readdirSync(pythonPackagesDir).length === 0) {
  console.log("[Python Deps] Local python_packages directory is missing or empty. Installing...");
  try {
    const log = execSync(`python3 -m pip install -r requirements.txt --target ./python_packages 2>&1`).toString();
    console.log("[Python Deps] Successfully installed python dependencies locally!");
    fs.writeFileSync(path.join(__dirname, 'install.log'), log);
  } catch (error) {
    const log = error.stdout ? error.stdout.toString() : error.message;
    console.error("[Python Deps] Failed to install python dependencies:\n", log);
    fs.writeFileSync(path.join(__dirname, 'install.log'), "ERROR:\n" + log);
  }
} else {
  console.log("[Python Deps] Local python_packages directory already exists and is not empty.");
}

// Environment variables loaded from .env automatically

// Load environment variables from root .env manually
const dotenvPath = path.resolve(__dirname, '.env');
if (fs.existsSync(dotenvPath)) {
  const dotenvContent = fs.readFileSync(dotenvPath, 'utf-8');
  for (const line of dotenvContent.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const match = trimmed.match(/^([^=]+)=(.*)$/);
    if (match) {
      const key = match[1].trim();
      let val = match[2].trim();
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1);
      }
      if (!process.env[key]) {
        process.env[key] = val;
      }
    }
  }
}

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

// Serve static generated media files
app.use('/generated-audio', express.static(path.join(__dirname, 'generated-audio')));

// Serve index.html and other static landing page files
app.use(express.static(path.join(__dirname, 'landing-page')));

// Ensure generated-audio directory exists on boot
const genAudioDir = path.join(__dirname, 'generated-audio');
if (!fs.existsSync(genAudioDir)) {
  fs.mkdirSync(genAudioDir, { recursive: true });
}

// Diagnostic API endpoints (allow unauthenticated GET for pipeline monitoring)
app.get('/api/pipeline-log', (req, res) => {
  const logPath = path.join(__dirname, 'generated-audio/pipeline.log');
  if (fs.existsSync(logPath)) {
    res.setHeader('Content-Type', 'text/plain');
    return res.sendFile(logPath);
  } else {
    return res.status(404).send('No pipeline log found.');
  }
});

app.get('/api/pipeline-log-tail', (req, res) => {
  const logPath = path.join(__dirname, 'generated-audio/pipeline.log');
  if (fs.existsSync(logPath)) {
    try {
      const content = fs.readFileSync(logPath, 'utf-8');
      const tail = content.slice(-10000); // Get last 10KB
      res.setHeader('Content-Type', 'text/plain');
      return res.send(tail);
    } catch (err) {
      return res.status(500).send('Error reading log file: ' + err.message);
    }
  } else {
    return res.status(404).send('No log file found.');
  }
});

app.get('/api/list-files', (req, res) => {
  const dirPath = path.join(__dirname, 'generated-audio');
  if (!fs.existsSync(dirPath)) {
    return res.json({ exists: false, files: [] });
  }
  const files = fs.readdirSync(dirPath).map(file => {
    const stats = fs.statSync(path.join(dirPath, file));
    return {
      name: file,
      size: stats.size,
      mtime: stats.mtime
    };
  });
  return res.json({ exists: true, files });
});

app.get('/api/debug-env', (req, res) => {
  const expectedToken = process.env.API_KEY || process.env.FREELLM_API_KEY;
  const token = req.query.apikey || req.query.apiKey;
  if (!token || token !== expectedToken) {
    return res.status(401).send('Unauthorized');
  }

  const commands = [
    'whoami',
    'which python3',
    'python3 --version',
    'which pip3',
    'pip3 --version',
    'ls -la generated-audio || true',
    'ls -la || true',
    'tail -n 100 generated-audio/pipeline.log || true',
    'ls -la python_packages || true',
    'python3 -c "import sys; sys.path.insert(0, \'./python_packages\'); import requests; print(requests.__file__)"'
  ];
  let output = "";
  for (const cmd of commands) {
    try {
      const stdout = execSync(cmd).toString();
      output += `=== ${cmd} ===\n${stdout}\n\n`;
    } catch (err) {
      output += `=== ${cmd} ===\nERROR: ${err.message}\nStderr: ${err.stderr ? err.stderr.toString() : ''}\n\n`;
    }
  }
  res.setHeader('Content-Type', 'text/plain');
  res.send(output);
});

// API endpoint to generate and render the reel (supports both GET and POST)
app.all('/api/generate-reel', (req, res) => {
  // Support both headers (Bearer) and query parameters (apikey)
  const authHeader = req.headers.authorization;
  const tokenFromHeader = authHeader ? authHeader.replace(/^Bearer\s+/i, '') : null;
  const tokenFromQuery = req.query.apikey || req.query.apiKey;
  const token = tokenFromHeader || tokenFromQuery;

  const expectedToken = process.env.API_KEY || process.env.FREELLM_API_KEY;

  if (!token || token !== expectedToken) {
    return res.status(401).json({ success: false, error: 'Unauthorized. Invalid or missing API key.' });
  }

  // Support both body and query parameters for options
  const query = req.query.query || req.body.query || 'random';
  console.log(`[Render Server] Generating reel with query: ${query}`);

  const logPath = path.join(__dirname, 'generated-audio/pipeline.log');
  const timestamp = new Date().toISOString();
  fs.writeFileSync(logPath, `=== PIPELINE STARTED: ${timestamp} (query: ${query}) ===\n\n`);

  // Run the generator, renderer, and upload pipeline scripts in a memory-bounded shell
  const cmd = `node --max-old-space-size=96 scripts/generate-marketing-script.mjs "${query}" && python3 scripts/render_captioned_video.py && python3 scripts/upload_pipeline.py`;
  
  const [shell, args] = process.platform === 'win32' ? ['cmd.exe', ['/s', '/c', cmd]] : ['/bin/sh', ['-c', cmd]];
  const child = spawn(shell, args, { cwd: __dirname });

  let stdoutData = "";
  let stderrData = "";

  child.stdout.on('data', (data) => {
    const text = data.toString();
    process.stdout.write(text); // Pipe logs directly to Render console stream
    fs.appendFileSync(logPath, text); // Save log to disk
    stdoutData += text;
    if (stdoutData.length > 50000) {
      stdoutData = stdoutData.slice(-50000); // Limit buffer memory footprint to 50KB
    }
  });

  child.stderr.on('data', (data) => {
    const text = data.toString();
    process.stderr.write(text); // Pipe error logs directly to Render console stream
    fs.appendFileSync(logPath, text); // Save log to disk
    stderrData += text;
    if (stderrData.length > 50000) {
      stderrData = stderrData.slice(-50000); // Limit buffer memory footprint to 50KB
    }
  });

  child.on('close', (code) => {
    const closeTime = new Date().toISOString();
    fs.appendFileSync(logPath, `\n=== PIPELINE FINISHED: ${closeTime} (exit code: ${code}) ===\n`);

    if (code !== 0) {
      console.error(`[Render Server] Command execution failed with exit code: ${code}`);
      return res.status(500).json({
        success: false,
        error: `Command failed with exit code ${code}`,
        details: stderrData
      });
    }

    console.log(`[Render Server] Reel generated and published successfully!`);

    // Verify output files exist
    const videoPath = 'generated-audio/rendered_reel_latest.mp4';
    if (fs.existsSync(path.join(__dirname, videoPath))) {
      return res.json({
        success: true,
        videoUrl: `/generated-audio/rendered_reel_latest.mp4`,
        scriptUrl: `/generated-audio/marketing-script-latest.md`,
        stdout: stdoutData
      });
    } else {
      return res.status(500).json({
        success: false,
        error: 'Video file was not generated.',
        stdout: stdoutData,
        details: stderrData
      });
    }
  });
});

app.all('/api/test-step', (req, res) => {
  const authHeader = req.headers.authorization;
  const tokenFromHeader = authHeader ? authHeader.replace(/^Bearer\s+/i, '') : null;
  const tokenFromQuery = req.query.apikey || req.query.apiKey;
  const token = tokenFromHeader || tokenFromQuery;
  const expectedToken = process.env.API_KEY || process.env.FREELLM_API_KEY;

  if (!token || token !== expectedToken) {
    return res.status(401).json({ success: false, error: 'Unauthorized.' });
  }

  const step = req.query.step || 'generate';
  let cmd = '';
  if (step === 'generate') {
    cmd = `node --max-old-space-size=96 scripts/generate-marketing-script.mjs "random"`;
  } else if (step === 'render') {
    cmd = `python3 scripts/render_captioned_video.py`;
  } else if (step === 'upload') {
    cmd = `python3 scripts/upload_pipeline.py`;
  } else if (step === 'install_deps') {
    cmd = `python3 -m pip install -r requirements.txt --target ./python_packages`;
  } else {
    return res.status(400).send('Invalid step');
  }

  console.log(`[Render Server] Running test step: ${step}`);
  const logPath = path.join(__dirname, 'generated-audio/pipeline.log');
  fs.writeFileSync(logPath, `=== TEST STEP: ${step} STARTED ===\n\n`);

  const [shell, args] = process.platform === 'win32' ? ['cmd.exe', ['/s', '/c', cmd]] : ['/bin/sh', ['-c', cmd]];
  const child = spawn(shell, args, { cwd: __dirname });

  let stdoutData = "";
  let stderrData = "";

  child.stdout.on('data', (data) => {
    const text = data.toString();
    process.stdout.write(text);
    fs.appendFileSync(logPath, text);
    stdoutData += text;
  });

  child.stderr.on('data', (data) => {
    const text = data.toString();
    process.stderr.write(text);
    fs.appendFileSync(logPath, text);
    stderrData += text;
  });

  child.on('close', (code) => {
    fs.appendFileSync(logPath, `\n=== TEST STEP: ${step} FINISHED (exit code: ${code}) ===\n`);
    return res.json({ success: code === 0, code, stdout: stdoutData, stderr: stderrData });
  });
});

// ── A/B STRATEGY ROUTES ───────────────────────────────────────────────────────
// PRESENT: short URLs (/t/t1 .. /t/tN) each run a named hypothesis preset end-to-end and
//          post live, so different content/retention strategies can be tested and compared.
// RATIONALE: pairs with scripts/fetch_reels.py + strategy_log.csv to attribute engagement
//            (skip rate, saves) back to the exact strategy that produced each reel.

// Read strategies.json per request so presets can be edited without a server restart.
function loadStrategies() {
  try {
    return JSON.parse(fs.readFileSync(path.join(__dirname, 'strategies.json'), 'utf-8'));
  } catch (e) {
    console.error('[Strategies] Failed to read strategies.json:', e.message);
    return {};
  }
}

// Auth check, mirroring /api/generate-reel (these routes post live, so they stay protected).
function isAuthorized(req) {
  const authHeader = req.headers.authorization;
  const tokenFromHeader = authHeader ? authHeader.replace(/^Bearer\s+/i, '') : null;
  const token = tokenFromHeader || req.query.apikey || req.query.apiKey;
  const expected = process.env.API_KEY || process.env.FREELLM_API_KEY;
  return Boolean(token && token === expected);
}

// Shared generate -> render -> upload runner. The existing /api/generate-reel is left untouched
// to avoid any regression; this helper backs only the strategy routes and injects extra env.
function runReelPipeline({ query, extraEnv = {}, strategyId = null }, res) {
  const logPath = path.join(__dirname, 'generated-audio/pipeline.log');
  const label = strategyId ? `strategy: ${strategyId}, ` : '';
  fs.writeFileSync(logPath, `=== PIPELINE STARTED: ${new Date().toISOString()} (${label}query: ${query}) ===\n\n`);

  const cmd = `node --max-old-space-size=96 scripts/generate-marketing-script.mjs "${query}" && python3 scripts/render_captioned_video.py && python3 scripts/upload_pipeline.py`;
  const [shell, args] = process.platform === 'win32' ? ['cmd.exe', ['/s', '/c', cmd]] : ['/bin/sh', ['-c', cmd]];
  const child = spawn(shell, args, { cwd: __dirname, env: { ...process.env, ...extraEnv } });

  let stdoutData = '';
  let stderrData = '';
  child.stdout.on('data', (data) => {
    const text = data.toString();
    process.stdout.write(text);
    fs.appendFileSync(logPath, text);
    stdoutData += text;
    if (stdoutData.length > 50000) stdoutData = stdoutData.slice(-50000);
  });
  child.stderr.on('data', (data) => {
    const text = data.toString();
    process.stderr.write(text);
    fs.appendFileSync(logPath, text);
    stderrData += text;
    if (stderrData.length > 50000) stderrData = stderrData.slice(-50000);
  });
  child.on('close', (code) => {
    fs.appendFileSync(logPath, `\n=== PIPELINE FINISHED: ${new Date().toISOString()} (exit code: ${code}) ===\n`);
    if (code !== 0) {
      return res.status(500).json({ success: false, strategy: strategyId, error: `Command failed with exit code ${code}`, details: stderrData });
    }
    const videoPath = 'generated-audio/rendered_reel_latest.mp4';
    if (fs.existsSync(path.join(__dirname, videoPath))) {
      return res.json({
        success: true,
        strategy: strategyId,
        videoUrl: '/generated-audio/rendered_reel_latest.mp4',
        scriptUrl: '/generated-audio/marketing-script-latest.md',
        stdout: stdoutData
      });
    }
    return res.status(500).json({ success: false, strategy: strategyId, error: 'Video file was not generated.', stdout: stdoutData, details: stderrData });
  });
}

// List available strategies (read-only metadata, no auth needed).
app.get('/api/strategies', (req, res) => {
  const strategies = loadStrategies();
  const out = {};
  for (const [id, s] of Object.entries(strategies)) {
    if (id.startsWith('_')) continue;
    out[id] = { label: s.label, hypothesis: s.hypothesis };
  }
  res.json({ success: true, strategies: out });
});

// Run a strategy preset end-to-end and POST live. e.g. GET /t/t3?apikey=YOUR_KEY
app.all('/t/:id', (req, res) => {
  if (!isAuthorized(req)) {
    return res.status(401).json({ success: false, error: 'Unauthorized. Invalid or missing API key.' });
  }
  const id = req.params.id;
  const strat = loadStrategies()[id];
  if (!strat || id.startsWith('_')) {
    return res.status(404).json({ success: false, error: `Unknown strategy '${id}'. See /api/strategies.` });
  }
  console.log(`[Strategy ${id}] ${strat.label} — full pipeline + live post`);
  const extraEnv = {
    STRAT_ID: id,
    STRAT_HOOK_ANGLE: strat.hookAngle || '',
    STRAT_OPEN_STYLE: strat.openStyle || 'grounded',
    STRAT_MAX_WORDS: String(strat.maxWords || 90),
    STRAT_HOOK_CARD_SECS: String(strat.hookCardSecs != null ? strat.hookCardSecs : 2.0)
  };
  runReelPipeline({ query: strat.section || 'random', extraEnv, strategyId: id }, res);
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[Render Server] Listening on port ${PORT}`);
});
