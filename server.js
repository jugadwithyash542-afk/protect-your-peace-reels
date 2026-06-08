import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { exec } from 'child_process';
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

  // Run the generator, renderer, and upload pipeline scripts
  const cmd = `node scripts/generate-marketing-script.mjs "${query}" && python3 scripts/render_captioned_video.py && python3 scripts/upload_pipeline.py`;
  
  exec(cmd, { cwd: __dirname }, (error, stdout, stderr) => {
    if (error) {
      console.error(`Error executing generation command: ${error.message}`);
      console.error(stderr);
      return res.status(500).json({
        success: false,
        error: error.message,
        details: stderr
      });
    }

    console.log(`[Render Server] Reel generated successfully!`);
    console.log(stdout);

    // Verify output files exist
    const videoPath = 'generated-audio/rendered_reel_latest.mp4';
    if (fs.existsSync(path.join(__dirname, videoPath))) {
      return res.json({
        success: true,
        videoUrl: `/generated-audio/rendered_reel_latest.mp4`,
        scriptUrl: `/generated-audio/marketing-script-latest.md`,
        stdout
      });
    } else {
      return res.status(500).json({
        success: false,
        error: 'Video file was not generated.',
        stdout,
        details: stderr
      });
    }
  });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[Render Server] Listening on port ${PORT}`);
});
