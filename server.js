import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { exec } from 'child_process';
import fs from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

// Serve static generated media files
app.use('/generated-audio', express.static(path.join(__dirname, 'generated-audio')));

// Serve index.html and other static landing page files
app.use(express.static(path.join(__dirname, 'landing-page')));

// API endpoint to generate and render the reel
app.post('/api/generate-reel', (req, res) => {
  const authHeader = req.headers.authorization;
  const expectedToken = process.env.API_KEY || process.env.FREELLM_API_KEY;

  if (!authHeader || authHeader.replace(/^Bearer\s+/i, '') !== expectedToken) {
    return res.status(401).json({ success: false, error: 'Unauthorized. Invalid or missing API key.' });
  }

  const query = req.body.query || 'random';
  console.log(`[Render Server] Generating reel with query: ${query}`);

  // Run the generator and renderer script
  const cmd = `node scripts/generate-marketing-script.mjs "${query}" && python3 scripts/render_captioned_video.py`;
  
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
