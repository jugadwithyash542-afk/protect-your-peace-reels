import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { exec, spawn } from 'child_process';
import fs from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

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
  const cmd = `node scripts/generate-marketing-script.mjs "${query}" && python3 scripts/render_captioned_video.py && python3 scripts/upload_pipeline.py`;
  
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
    cmd = `node scripts/generate-marketing-script.mjs "random"`;
  } else if (step === 'render') {
    cmd = `python3 scripts/render_captioned_video.py`;
  } else if (step === 'upload') {
    cmd = `python3 scripts/upload_pipeline.py`;
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

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[Render Server] Listening on port ${PORT}`);
});
