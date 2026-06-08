import fs from 'fs';
import path from 'path';
import readline from 'readline';
import { fileURLToPath } from 'url';
import { execSync, spawn } from 'child_process';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load environment variables from root .env manually
const dotenvPath = path.resolve(__dirname, '../.env');
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

const API_BASE = process.env.FREELLM_API_BASE ?? "http://127.0.0.1:3001";

const EBOOK_PATH = process.env.EBOOK_PATH ?? path.resolve(__dirname, '../Doc/guide.md');
const OUTPUT_DIR = path.resolve(__dirname, '../generated-audio');

// Meta headings to exclude from parsing
const META_HEADINGS = new Set([
  "Protect Your Peace",
  "The WhatsApp-Ready Boundary, Red Flag, and Self-Respect Script Kit for Women Who Are Tired of Over-Giving",
  "Start Here: Your Quick-Start Roadmap",
  "Why This Is Different From Free Advice Online",
  "Hard-Conversation Workflow & Tone Explainer",
  "Printable Bonus Pages",
  "Table Of Contents",
  "How To Use This Guide"
]);

async function main() {
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  console.log(`Reading guide document from: ${EBOOK_PATH}...`);
  if (!fs.existsSync(EBOOK_PATH)) {
    console.error(`Guide document not found at: ${EBOOK_PATH}`);
    process.exit(1);
  }
  const ebookContent = fs.readFileSync(EBOOK_PATH, 'utf-8');

  console.log("Parsing sections...");
  const sections = parseEbookSections(ebookContent);
  if (sections.length === 0) {
    console.error("No valid sections found in ebook/guide.");
    process.exit(1);
  }

  const query = process.argv[2];
  let selectedSection = null;

  if (query && query.toLowerCase() === 'random') {
    selectedSection = getRandomSection(sections);
  } else if (query) {
    // Exact or partial match
    selectedSection = sections.find(s => s.title.toLowerCase().includes(query.toLowerCase()));
    if (!selectedSection) {
      console.warn(`No section matched "${query}". Falling back to selection list.`);
    }
  }

  if (!selectedSection) {
    selectedSection = await promptUserForSection(sections);
  }

  console.log(`\nSelected Section: "${selectedSection.title}"`);
  console.log(`Context length: ${selectedSection.content.length} characters`);

  // Ensure local proxy is running
  await ensureFreeLlmApiRunning();

  // Fetch API key from local proxy
  console.log("\nFetching unified API key...");
  let apiKey = process.env.VITE_FREELLM_API_KEY || process.env.FREELLM_API_KEY;
  if (!apiKey) {
    try {
      const keyResponse = await fetch(`${API_BASE}/api/settings/api-key`);
      if (keyResponse.ok) {
        const body = await keyResponse.json();
        apiKey = body.apiKey;
      }
    } catch (err) {
      console.warn("Could not reach FreeLLMAPI to fetch API key. Make sure it is running.");
    }
  }

  if (!apiKey) {
    console.error("API Key not found. Please start the server or set VITE_FREELLM_API_KEY environment variable.");
    process.exit(1);
  }

  console.log("Generating marketing script via Gemini...");
  const scriptData = await generateMarketingScript(apiKey, selectedSection);

  // Clean filename representation of section
  const safeTitle = selectedSection.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

  const mdFilename = `marketing-script-${safeTitle}.md`;
  const wavFilename = `marketing-voiceover-${safeTitle}.wav`;

  const mdPath = path.resolve(OUTPUT_DIR, mdFilename);
  const latestMdPath = path.resolve(OUTPUT_DIR, 'marketing-script-latest.md');
  
  const mdContent = [
    `# Ebook-Driven Marketing Script: ${selectedSection.title}`,
    "",
    `- **Ebook Source Section:** [${selectedSection.title}](file://${EBOOK_PATH})`,
    `- **Model:** Gemini 3.1 Flash (via FreeLLMAPI)`,
    `- **Audio File:** [${wavFilename}](file://${path.resolve(OUTPUT_DIR, wavFilename)})`,
    "",
    "## Hook (Reels/TikTok 3-Second Scroll-Stopper)",
    scriptData.hook,
    "",
    "## Core Value Point",
    scriptData.lesson,
    "",
    "## Sisterly Support & Transition",
    scriptData.pitch,
    "",
    "## Spoken Voiceover",
    `*(${scriptData.performanceDirection})*`,
    "",
    scriptData.voiceover
  ].join("\n");

  fs.writeFileSync(mdPath, mdContent);
  fs.writeFileSync(latestMdPath, mdContent);
  console.log(`Saved markdown script to: ${mdPath}`);
  console.log(`Saved shortcut to: ${latestMdPath}`);

  console.log("\nSynthesizing voiceover audio via Gemini 3.1 Flash TTS (with auto-retry backoff)...");
  const wavPath = path.resolve(OUTPUT_DIR, wavFilename);
  const latestWavPath = path.resolve(OUTPUT_DIR, 'marketing-voiceover-latest.wav');

  let attempt = 1;
  const maxAttempts = 5;

  while (attempt <= maxAttempts) {
    console.log(`Attempt ${attempt}/${maxAttempts}: Requesting audio...`);
    try {
      const audioResponse = await fetch(`${API_BASE}/v1/audio/speech`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          input: scriptData.voiceover,
          voice: "Kore",
          model: "gemini-3.1-flash-tts-preview"
        })
      });

      if (audioResponse.ok) {
        const arrayBuf = await audioResponse.arrayBuffer();
        const buffer = Buffer.from(arrayBuf);

        fs.writeFileSync(wavPath, buffer);
        fs.writeFileSync(latestWavPath, buffer);
        console.log(`Saved audio WAV to: ${wavPath}`);
        console.log(`Saved shortcut to: ${latestWavPath}`);
        console.log(`Audio size: ${buffer.length.toLocaleString()} bytes`);
        
        const durationSec = (buffer.length - 44) / 48000;
        console.log(`Estimated duration: ${durationSec.toFixed(2)} seconds`);
        break;
      } else {
        const errText = await audioResponse.text();
        console.warn(`Attempt ${attempt} failed with status ${audioResponse.status}: ${errText}`);
        if (audioResponse.status === 429 && attempt < maxAttempts) {
          console.log("Waiting 95 seconds for the rate limit window to clear...");
          await new Promise(resolve => setTimeout(resolve, 95000));
        } else {
          process.exit(1);
        }
      }
    } catch (err) {
      console.error(`Attempt ${attempt} error:`, err);
      if (attempt < maxAttempts) {
        console.log("Waiting 10 seconds before retrying...");
        await new Promise(resolve => setTimeout(resolve, 10000));
      } else {
        process.exit(1);
      }
    }
    attempt++;
  }

  // Convert and mix background audio
  const bgMusicName = process.env.BG_MUSIC_NAME || 'bg-minimal-piano.wav';
  let wavBgPath = path.resolve(__dirname, `../public/${bgMusicName}`);

  // Fallback to legacy/custom bg folder if the public track isn't found
  if (!fs.existsSync(wavBgPath)) {
    const m4aBgPath = path.resolve(__dirname, '../bg/i was only temporary.m4a');
    const legacyWavBgPath = path.resolve(__dirname, '../bg/i was only temporary.wav');
    if (fs.existsSync(m4aBgPath)) {
      console.log(`\nFound legacy background audio: bg/i was only temporary.m4a`);
      if (!fs.existsSync(legacyWavBgPath)) {
        console.log("Converting background audio to compatible 24kHz Mono WAV format...");
        try {
          execSync(`afconvert -f WAVE -d LEI16@24000 -c 1 "${m4aBgPath}" "${legacyWavBgPath}"`);
          console.log("Successfully converted background audio.");
        } catch (err) {
          console.error("Failed to convert background audio using afconvert:", err.message);
        }
      }
      if (fs.existsSync(legacyWavBgPath)) {
        wavBgPath = legacyWavBgPath;
      }
    }
  }

  const latestMixedWavPath = path.resolve(OUTPUT_DIR, 'mixed-voiceover-latest.wav');

  if (fs.existsSync(wavBgPath)) {
    console.log(`\nUsing background music: ${wavBgPath}`);
    console.log("Mixing background music with voiceover...");
    const mixedWavPath = path.resolve(OUTPUT_DIR, `mixed-voiceover-${safeTitle}.wav`);
    const mixScriptPath = path.resolve(__dirname, 'mix_wav_files.py');
    try {
      execSync(`python3 "${mixScriptPath}" "${wavPath}" "${wavBgPath}" "${mixedWavPath}" 0.15`);
      fs.copyFileSync(mixedWavPath, latestMixedWavPath);
      console.log(`Saved mixed audio to: ${mixedWavPath}`);
      console.log(`Saved mixed shortcut to: ${latestMixedWavPath}`);
    } catch (err) {
      console.error("Failed to mix audio files:", err.message);
      console.log("Falling back: Copying unmixed voiceover to mixed-voiceover-latest.wav...");
      fs.copyFileSync(wavPath, latestMixedWavPath);
    }
  } else {
    console.warn(`\nBackground music not found at ${wavBgPath} and no legacy fallback found. Skipping mixing.`);
    console.log("Copying unmixed voiceover to mixed-voiceover-latest.wav...");
    fs.copyFileSync(wavPath, latestMixedWavPath);
  }
}

function parseEbookSections(content) {
  const lines = content.split('\n');
  const sections = [];
  let currentSection = null;

  for (const line of lines) {
    if (line.startsWith('## ')) {
      const title = line.slice(3).trim();
      if (META_HEADINGS.has(title)) {
        continue;
      }

      if (currentSection) {
        sections.push(currentSection);
      }

      currentSection = {
        title,
        content: ""
      };
    } else if (currentSection) {
      currentSection.content += line + "\n";
    }
  }

  if (currentSection) {
    sections.push(currentSection);
  }

  // Trim content and filter out empty sections
  return sections
    .map(s => ({ title: s.title, content: s.content.trim() }))
    .filter(s => s.content.length > 50);
}

async function promptUserForSection(sections) {
  console.log("\n=== Ebook Sections Available ===");
  sections.forEach((s, idx) => {
    console.log(`${String(idx + 1).padStart(2)}. ${s.title}`);
  });
  console.log(" 0. [Random Section]");

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  return new Promise((resolve) => {
    rl.question("\nChoose a section number: ", (answer) => {
      rl.close();
      const num = parseInt(answer.trim(), 10);
      if (isNaN(num) || num < 0 || num > sections.length) {
        console.log("Invalid selection. Choosing a random section.");
        resolve(getRandomSection(sections));
      } else if (num === 0) {
        resolve(getRandomSection(sections));
      } else {
        resolve(sections[num - 1]);
      }
    });
  });
}

function getRandomSection(sections) {
  const idx = Math.floor(Math.random() * sections.length);
  return sections[idx];
}

async function generateMarketingScript(apiKey, section) {
  const systemPrompt = [
    "You create supportive, raw, and nurturing reels/TikTok scripts for a women's relationship-safety and self-respect guide.",
    "Write like a real sibling sharing a hard truth out of deep concern. Inhabit this voice fully. Speak with vulnerability and intense warmth. Avoid sounding like a powerful lecturer or aggressive speaker. You are hurting *for* the listener—let your voice show that vulnerability, as if you are holding back tears or reacting to the pain in real-time. Tension without warmth is scary; ground your tone in protective care.",
    "CRITICAL HOOK RULES:",
    "- The hook MUST stop the scroll in the first 3 seconds.",
    "- No greeting, no setup, no scene description, and no narrative context. Start the fire immediately.",
    "- Deliver a single, raw, honest observation that makes the listener feel exposed (vulnerable confession, not a script or lecture).",
    "- The hook MUST start with a whisper cue: '[soft whisper]'. E.g., '[soft whisper] You checked the trash just to prove you weren't crazy.' or '[soft whisper] You hid the receipt because you couldn't face the argument.'",
    "CRITICAL SUPPORT TRANSITION AND GUIDE REVELATION RULES:",
    "- Avoid a hard sales pitch. Keep the tone deeply nurturing, protecting, and completely non-commercial.",
    "- Do NOT treat the guide/offer like a separate chapter, pitch, or sales transaction. Instead, make the transition a gentle, seamless gesture of support.",
    "- The goal is to make the listener feel deeply seen, validated, and supported first. Only then, transition into the guidance portion as an act of sibling help.",
    "- Do NOT mention pricing (no '$9.99', no 'launch price', no regular value), and do NOT use commercial/transactional terms like 'buy', 'purchase', 'limited-time offer', or 'checkout'.",
    "- The transition MUST use this exact sentiment and close wording (grounded with warmth): '[grounded with warmth] I spent a lot of time thinking about how to actually stop this, so I put together a guide with the actual words to use for when you're not sure when to speak up. This is just a little bit of support for when you're tired of feeling small or lacking the words to say. If you need it, the link is in the profile bio.'",
    "CRITICAL TONE RULES FOR THE VOICEOVER FIELD:",
    "- Start the voiceover field immediately with the hook.",
    "- BAN ALL DEFINITIONS & THERAPY LABELS: Never use terms like 'gaslighting', 'love bombing', 'narcissist', 'manipulation', 'red flags', or 'boundaries'. Speak only of the raw physical and mental sensation of the situation.",
    "- BAN ADVICE & SCRIPTS inside the body of the voiceover: Do not give general advice, tell the listener what to say inside the teaching body; focus on the realization of their situation. Save the script recommendations for the transition/outro at the very end.",
    "EMBRACE SILENCE, WARMTH & EMPATHY:",
    "- Focus on organic signs of empathy: include bracketed voice texture and breath cues directly in the voiceover text such as '[soft sigh]', '[voice cracks]', '[catch in throat]', '[tremble]', '[soft whisper]', or '[grounded with warmth]'. Every shift must have a clear motive driven by sibling empathy.",
    "- Insert '[silence]' or '[long pause]' after heavy statements so the realizations sit heavily in the air.",
    "Return only compact valid JSON with these string fields: hook, lesson, pitch, performanceDirection, voiceover.",
    "Do not use markdown fences. Do not add commentary. Do not insert unescaped line breaks inside string values."
  ].join("\n");

  const userPrompt = [
    `Section Title: ${section.title}`,
    `Ebook Section Text Context:\n${section.content}`,
    "",
    "Create a script pack based on the ebook content.",
    "hook: scroll-stopping mind-reading hook line starting with '[soft whisper]', delivering a single raw, honest observation that makes the listener feel exposed (no greetings/scene setup).",
    "lesson: short value teaching lesson based directly on the book context, helping them recognize the situation.",
    "pitch: supportive transition to the guide, explaining that I spent a lot of time thinking about how to actually stop this and put together a guide with actual words for when she's not sure when to speak up, offered purely as support for when she's tired of feeling small or lacking the words to say. No sales pitch, no pricing.",
    "performanceDirection: short note on the vocal shifts, focusing on the sibling warmth, vulnerability, and empathy.",
    "voiceover: spoken script. MUST start immediately with the hook (beginning with '[soft whisper]'). Deliver the hook, then the value lesson, then transition seamlessly into the supportive transition (pitch). The transition at the end MUST continue the same sibling warmth, care, and protective tone. Do NOT break character or sound like a commercial. Use sibling warmth and dynamic shifts (using '[soft whisper]' for raw moments, '[voice cracks]/[soft sigh]' for vulnerability, and '[grounded with warmth]' for protective truth, driven by clear motives) and embrace silence (use '[silence]' or '[long pause]'). Avoid any consistent melody.",
  ].join("\n");

  const response = await fetch(`${API_BASE}/v1/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "auto",
      temperature: 0.78,
      max_tokens: 2400,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt },
      ],
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Script generation failed: ${response.status} ${text}`);
  }

  const completion = await response.json();
  const content = completion.choices[0].message.content;
  return parseGeneratedScript(content);
}

function parseGeneratedScript(content) {
  const jsonText = extractJsonObject(content.trim());
  const escaped = escapeControlCharsInsideJsonStrings(jsonText);
  return JSON.parse(escaped);
}

function extractJsonObject(value) {
  const fenced = value.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const source = fenced?.[1]?.trim() || value;
  const start = source.indexOf("{");
  const end = source.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) {
    throw new Error(`Invalid JSON format.`);
  }
  return source.slice(start, end + 1);
}

function escapeControlCharsInsideJsonStrings(value) {
  let output = "";
  let inString = false;
  let escaped = false;
  for (const char of value) {
    if (escaped) { output += char; escaped = false; continue; }
    if (char === "\\") { output += char; escaped = true; continue; }
    if (char === "\"") { inString = !inString; output += char; continue; }
    if (inString && char === "\n") { output += "\\n"; continue; }
    if (inString && char === "\r") { output += "\\r"; continue; }
    if (inString && char === "\t") { output += "\\t"; continue; }
    output += char;
  }
  return output;
}

async function ensureFreeLlmApiRunning() {
  // If API_BASE is a remote service (not localhost/127.0.0.1), we skip local spawning checks.
  if (!API_BASE.includes('127.0.0.1') && !API_BASE.includes('localhost')) {
    console.log(`[Proxy check] Using remote FreeLLMAPI base: ${API_BASE}`);
    return;
  }

  const checkUrl = `${API_BASE}/api/settings/api-key`;
  try {
    const res = await fetch(checkUrl);
    if (res.ok) {
      return; // Already running
    }
  } catch (err) {
    // Not running, proceed to spawn it
  }

  console.log("FreeLLMAPI is not running. Starting local server in the background...");
  const child = spawn('npm', ['run', 'llm'], {
    cwd: path.resolve(__dirname, '..'),
    detached: true,
    stdio: 'ignore'
  });
  child.unref();

  const startTime = Date.now();
  while (Date.now() - startTime < 15000) {
    try {
      const res = await fetch(checkUrl);
      if (res.ok) {
        console.log("FreeLLMAPI is now online and responsive!");
        return;
      }
    } catch (err) {
      // Keep waiting
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  console.warn("⚠️ FreeLLMAPI check timed out or returned unauthorized. Continuing anyway...");
}

main().catch(console.error);
