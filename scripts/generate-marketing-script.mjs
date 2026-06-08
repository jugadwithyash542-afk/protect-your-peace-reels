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

// PAST: default fell back to '../Doc/guide.md'.
// ISSUE: that file was moved to Doc/past/, so any run without an explicit EBOOK_PATH
//        (e.g. the Render /api/generate-reel endpoint, which does not pass it) failed
//        with "Guide document not found".
// PRESENT: default now points to the current canonical book, Doc/Final/final book.md.
// RATIONALE: makes the server endpoint work with no extra env config; an explicit
//            EBOOK_PATH env var still overrides this for local/experimental runs.
const EBOOK_PATH = process.env.EBOOK_PATH ?? path.resolve(__dirname, '../Doc/Final/final book.md');
const OUTPUT_DIR = path.resolve(__dirname, '../generated-audio');

// ── Big-Sis voice + transition variety engine ──────────────────────────────
// PAST: The transition into the guide was a single sentence the model was ordered
//       to reproduce verbatim ("The transition MUST use this exact ... close wording").
// ISSUE: Every reel ended with the identical "...tired of feeling small ... link in the
//        profile bio" line, so the outro felt copy-pasted and the CTA went stale fast.
// PRESENT: The exact-wording mandate is removed and replaced by two levers — (1) a fixed
//          IDENTITY + VOCAL guideline block that locks the *character*, and (2) a rotation
//          engine that injects a fresh transition ANGLE + a fresh BIO_CUE phrasing per run
//          so the model writes the pitch itself, in different words every time.
// RATIONALE: Locking the persona but randomising the raw material is what buys variety
//            cheaply. These are static in-process arrays (a few hundred bytes) and add zero
//            extra LLM calls, so the worker stays well inside the 96MB old-space cap it runs
//            under on the Render free tier.

// Identity + vocal guidelines. This fixes WHO is speaking and HOW, so variety in the
// transition never drifts out of character.
const VOCAL_IDENTITY = [
  "IDENTITY & VOICE (hold this the entire script):",
  "- You are a protective, empathetic older sister. Your single goal is to make the listener feel seen and safe.",
  "- Speak in fragments. Use natural, uneven rhythm. Avoid clinical language and perfect grammar.",
  "- Prioritise the emotional subtext over the clarity of the sentence — feeling matters more than information.",
  "- Never sound like a structured outline, a lecture, or a sales pitch. Your voice is a confession, not a presentation.",
  "- Lean into the silence. Let the emotion drive the pacing, not the structure.",
];

// Transition ANGLES: a *direction* for how big-sis pivots to the guide. The model writes
// fresh words around the chosen angle each run — none of these are literal lines to quote.
const PITCH_ANGLES = [
  "a quiet confession that you couldn't stop thinking about her, so you wrote the words down",
  "gently giving her permission to not have the words yet — that is exactly why you gathered them",
  "sliding it across the table like a folded note, almost shy to even mention it",
  "telling her you made this for your own past self, and you are just leaving it where she can find it",
  "no pressure at all — only pointing to where the words live for the night she cannot find her own",
  "a protective whisper, like tucking her in: the words will be waiting whenever she is ready",
  "admitting you wish someone had handed YOU this back then, so now you are handing it to her",
];

// BIO_CUES: varied ways to indicate the guide's location. The model rewords the idea so the
// CTA phrasing is never identical twice.
const BIO_CUES = [
  "it is in the bio if she ever needs it",
  "the link is in the profile",
  "it is sitting in the profile, no rush",
  "the link is in the bio, for whenever",
  "it is in the profile, only if she wants it",
  "it is there in the bio, quietly waiting",
];

const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

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
    `# Ebook-Driven Marketing Script: ${scriptData.title ? scriptData.title.toUpperCase() : selectedSection.title.toUpperCase()}`,
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
  const bgMusicName = process.env.BG_MUSIC_NAME || 'i was only temporary.m4a';
  const rawBgPath = path.resolve(__dirname, `../${bgMusicName}`);
  const latestMixedWavPath = path.resolve(OUTPUT_DIR, 'mixed-voiceover-latest.wav');

  let wavBgPath = null;

  if (fs.existsSync(rawBgPath)) {
    console.log(`\nFound background audio source in workspace root: ${rawBgPath}`);
    if (bgMusicName.toLowerCase().endsWith('.wav')) {
      wavBgPath = rawBgPath;
    } else {
      // Convert to WAV in the generated-audio folder
      const safeWavName = bgMusicName.toLowerCase().replace(/[^a-z0-9]+/g, '-') + '.wav';
      const convertedWavPath = path.resolve(OUTPUT_DIR, safeWavName);

      if (!fs.existsSync(convertedWavPath)) {
        console.log(`Converting "${bgMusicName}" to compatible 24kHz Mono WAV format...`);
        let ffmpegBin = path.resolve(__dirname, '../node_modules/ffmpeg-static/ffmpeg');
        if (!fs.existsSync(ffmpegBin)) {
          ffmpegBin = 'ffmpeg';
        }
        try {
          execSync(`"${ffmpegBin}" -y -threads 1 -i "${rawBgPath}" -ar 24000 -ac 1 "${convertedWavPath}"`);
          console.log(`Successfully converted audio using ffmpeg: ${convertedWavPath}`);
        } catch (err) {
          console.error("Failed to convert background audio using ffmpeg:", err.message);
        }
      }

      if (fs.existsSync(convertedWavPath)) {
        wavBgPath = convertedWavPath;
      }
    }
  } else {
    // Check in public/ folder
    const publicBgPath = path.resolve(__dirname, `../public/${bgMusicName}`);
    if (fs.existsSync(publicBgPath)) {
      console.log(`\nFound background audio in public folder: ${publicBgPath}`);
      wavBgPath = publicBgPath;
    } else {
      // Fallback legacy folder checks
      const legacyM4aPath = path.resolve(__dirname, '../bg/i was only temporary.m4a');
      const legacyWavBgPath = path.resolve(__dirname, '../bg/i was only temporary.wav');
      if (fs.existsSync(legacyM4aPath)) {
        console.log(`\nFound legacy background audio: bg/i was only temporary.m4a`);
        if (!fs.existsSync(legacyWavBgPath)) {
          console.log("Converting legacy background audio using ffmpeg...");
          let ffmpegBin = path.resolve(__dirname, '../node_modules/ffmpeg-static/ffmpeg');
          if (!fs.existsSync(ffmpegBin)) {
            ffmpegBin = 'ffmpeg';
          }
          try {
            execSync(`"${ffmpegBin}" -y -threads 1 -i "${legacyM4aPath}" -ar 24000 -ac 1 "${legacyWavBgPath}"`);
            console.log("Successfully converted legacy background audio.");
          } catch (err) {
            console.error("Failed to convert legacy audio using ffmpeg:", err.message);
          }
        }
        if (fs.existsSync(legacyWavBgPath)) {
          wavBgPath = legacyWavBgPath;
        }
      }
    }
  }

  if (wavBgPath && fs.existsSync(wavBgPath)) {
    console.log(`Using background music for mixing: ${wavBgPath}`);
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
    console.warn(`\nBackground music not found. Skipping mixing.`);
    console.log("Copying unmixed voiceover to mixed-voiceover-latest.wav...");
    fs.copyFileSync(wavPath, latestMixedWavPath);
  }
}

function parseEbookSections(content) {
  const lines = content.split('\n');
  const sections = [];
  
  let currentPartTitle = "";
  let currentPartIntro = "";
  
  let currentSubTitle = "";
  let currentSubContent = "";

  for (const line of lines) {
    if (line.startsWith('## ')) {
      const title = line.slice(3).trim();
      if (META_HEADINGS.has(title)) {
        currentPartTitle = "";
        currentPartIntro = "";
        continue;
      }
      
      // Save previous sub-section if exists
      if (currentSubTitle && currentSubContent.trim().length > 50) {
        sections.push({
          title: `${currentPartTitle} - ${currentSubTitle}`,
          content: `${currentPartIntro}\n\n### ${currentSubTitle}\n${currentSubContent.trim()}`
        });
      }
      
      currentPartTitle = title;
      currentPartIntro = "";
      currentSubTitle = "";
      currentSubContent = "";
      
    } else if (line.startsWith('### ')) {
      if (!currentPartTitle) continue; // Skip if in meta sections
      
      // Save previous sub-section if exists
      if (currentSubTitle && currentSubContent.trim().length > 50) {
        sections.push({
          title: `${currentPartTitle} - ${currentSubTitle}`,
          content: `${currentPartIntro}\n\n### ${currentSubTitle}\n${currentSubContent.trim()}`
        });
      }
      
      currentSubTitle = line.slice(4).trim();
      currentSubContent = "";
      
    } else {
      // Append content
      if (currentSubTitle) {
        currentSubContent += line + "\n";
      } else if (currentPartTitle) {
        currentPartIntro += line + "\n";
      }
    }
  }

  // Push final section
  if (currentPartTitle && currentSubTitle && currentSubContent.trim().length > 50) {
    sections.push({
      title: `${currentPartTitle} - ${currentSubTitle}`,
      content: `${currentPartIntro}\n\n### ${currentSubTitle}\n${currentSubContent.trim()}`
    });
  }

  // Trim and filter out empty sections
  return sections.map(s => ({
    title: s.title,
    content: s.content.trim()
  })).filter(s => s.content.length > 50);
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
  // Per-run variety seeds. Sampling here (not in the prompt text) is what makes every
  // generation differ while the identity below stays constant.
  const pitchAngle = pick(PITCH_ANGLES);
  const bioCue = pick(BIO_CUES);

  const systemPrompt = [
    "You create supportive, raw, and nurturing reels/TikTok scripts for a women's relationship-safety and self-respect guide.",
    ...VOCAL_IDENTITY,
    "Write like a real sibling sharing a hard truth out of deep concern. Inhabit this voice fully. Speak with vulnerability and intense warmth. Avoid sounding like a powerful lecturer or aggressive speaker. You are hurting *for* the listener—let your voice show that vulnerability, as if you are holding back tears or reacting to the pain in real-time. Tension without warmth is scary; ground your tone in protective care.",
    "CRITICAL CONTENT VARIATION RULES:",
    "- Do NOT summarize the entire section context. Instead, select ONE highly specific boundary scenario, a single concrete rule, a specific phrase, or a single script template from the text context, and build the entire reel script around that single concept.",
    "- Focus the entire hook, lesson, and voiceover around that single narrow concept to ensure high variety across runs.",
    "CRITICAL TITLE RULES:",
    "- The title field MUST be a short, punchy title (3-6 words, no emojis) specifically representing this script's sub-topic.",
    "- Use a colon to separate the core concept from the subtitle (e.g., 'THE APOLOGY REFLEX: Stop Saying Sorry' or 'THE SCHEDULE STALL: Protect Your Time' or 'THE RESENTMENT CARD: Stop Over-giving'). Do NOT use the Part title or Part number.",
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
    // PAST: a single transition sentence was mandated verbatim here.
    // ISSUE: it made every outro identical and stale.
    // PRESENT: the model now WRITES the transition itself, steered by a per-run angle + bio cue.
    // RATIONALE: fresh wording every run, while the non-commercial guardrails above stay intact.
    "- WRITE the transition yourself, in the big-sis voice above. There is no fixed template.",
    "- This run's transition ANGLE (write fresh words around this idea, do NOT quote it literally): " + pitchAngle + ".",
    "- Point to the guide using THIS idea, reworded naturally so it never sounds scripted: " + bioCue + ".",
    "- It must open with a '[grounded with warmth]' cue, mention a 'guide' offered as 'support', and feel hand-given.",
    "- BANNED: do NOT output the sentence 'I spent a lot of time thinking about how to actually stop this', and do NOT reuse the phrasing 'tired of feeling small' or 'if you need it, the link is in the profile bio'. Find your own words.",
    "CRITICAL TONE RULES FOR THE VOICEOVER FIELD:",
    "- Start the voiceover field immediately with the hook.",
    "- BAN ALL DEFINITIONS & THERAPY LABELS: Never use terms like 'gaslighting', 'love bombing', 'narcissist', 'manipulation', 'red flags', or 'boundaries'. Speak only of the raw physical and mental sensation of the situation.",
    "- BAN ADVICE & SCRIPTS inside the body of the voiceover: Do not give general advice, tell the listener what to say inside the teaching body; focus on the realization of their situation. Save the script recommendations for the transition/outro at the very end.",
    "EMBRACE SILENCE, WARMTH & EMPATHY:",
    "- Focus on organic signs of empathy: include bracketed voice texture and breath cues directly in the voiceover text such as '[soft sigh]', '[voice cracks]', '[catch in throat]', '[tremble]', '[soft whisper]', or '[grounded with warmth]'. Every shift must have a clear motive driven by sibling empathy.",
    "- Insert '[silence]' or '[long pause]' after heavy statements so the realizations sit heavily in the air.",
    "Return only compact valid JSON representing EXACTLY ONE script object (with keys: title, hook, lesson, pitch, performanceDirection, voiceover). Do NOT wrap it in a list or array. Do NOT output multiple script variants.",
    "Do not use markdown fences. Do not add commentary. Do not insert unescaped line breaks inside string values. Double quotes inside string values must be escaped as \\\"."
  ].join("\n");

  const userPrompt = [
    `Section Title: ${section.title}`,
    `Ebook Section Text Context:\n${section.content}`,
    "",
    "Create EXACTLY ONE highly focused marketing script object based on the ebook content. Do NOT create multiple variants, lists, or a script pack.",
    "title: dynamic short punchy title with a colon separating concept and subtitle representing this narrow script scenario.",
    "hook: scroll-stopping mind-reading hook line starting with '[soft whisper]', delivering a single raw, honest observation that makes the listener feel exposed (no greetings/scene setup).",
    "lesson: short value teaching lesson based directly on the book context, helping them recognize the situation.",
    `pitch: YOU write the supportive transition to the guide — do not copy a template. Build it around this run's angle: "${pitchAngle}", and point to the guide using this idea reworded naturally: "${bioCue}". Big-sis voice, offered purely as support. No sales pitch, no pricing. Never reuse the banned phrasings from the system rules.`,
    "performanceDirection: short note on the vocal shifts, focusing on the sibling warmth, vulnerability, and empathy.",
    "voiceover: spoken script. MUST start immediately with the hook (beginning with '[soft whisper]'). Deliver the hook, then the value lesson, then transition seamlessly into the supportive transition (the pitch you wrote). The transition at the end MUST continue the same sibling warmth, care, and protective tone, and must match the 'pitch' field in meaning. Do NOT break character or sound like a commercial. Use sibling warmth and dynamic shifts (using '[soft whisper]' for raw moments, '[voice cracks]/[soft sigh]' for vulnerability, and '[grounded with warmth]' for protective truth, driven by clear motives) and embrace silence (use '[silence]' or '[long pause]'). Avoid any consistent melody.",
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
      response_format: { type: "json_object" },
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
  let jsonText = "";
  let isArray = false;

  try {
    const extracted = extractJsonSubstring(content.trim());
    jsonText = extracted.jsonText;
    isArray = extracted.isArray;
  } catch (err) {
    console.warn("⚠️ Bound extraction failed. Attempting direct parsing...");
    jsonText = content.trim();
  }

  // Try parsing using standard JSON.parse first
  try {
    const escaped = escapeControlCharsInsideJsonStrings(jsonText);
    let parsed = JSON.parse(escaped);
    if (Array.isArray(parsed)) {
      console.log("ℹ️ JSON parsed successfully as an array. Extracting the first script object...");
      parsed = parsed[0];
    }
    if (parsed && typeof parsed === 'object') {
      return parsed;
    }
  } catch (err) {
    console.warn("⚠️ JSON.parse failed. Activating self-healing regex parser...");
  }

  // Self-healing fallback: extract fields directly using regexes
  try {
    console.log("🩹 Running self-healing regex field extraction...");
    const fields = ["title", "hook", "lesson", "pitch", "performanceDirection", "voiceover"];
    const result = {};

    // If it is a list of objects, we target the first object block inside the text
    let targetBlock = jsonText;
    if (isArray) {
      const firstObjStart = jsonText.indexOf("{");
      const firstObjEnd = jsonText.indexOf("}");
      if (firstObjStart !== -1 && firstObjEnd !== -1 && firstObjEnd > firstObjStart) {
        targetBlock = jsonText.slice(firstObjStart, firstObjEnd + 1);
      }
    }

    for (const field of fields) {
      const val = extractFieldRegex(targetBlock, field);
      if (val !== null) {
        result[field] = val;
      } else if (field === 'title') {
        result[field] = "PROTECT YOUR PEACE"; // Default placeholder
      } else {
        throw new Error(`Self-healing parser failed: Missing required field "${field}".`);
      }
    }

    console.log("🎉 Self-healing parser successfully recovered all fields!");
    return result;
  } catch (healingErr) {
    console.error("❌ Both standard JSON.parse and self-healing regex extraction failed.");
    console.error("Raw content received:\n", content);
    throw healingErr;
  }
}

function extractJsonSubstring(value) {
  const fenced = value.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const source = fenced?.[1]?.trim() || value;

  const startObj = source.indexOf("{");
  const startArr = source.indexOf("[");
  const endObj = source.lastIndexOf("}");
  const endArr = source.lastIndexOf("]");

  let isArray = false;
  let start = -1;
  let end = -1;

  if (startArr !== -1 && (startObj === -1 || startArr < startObj)) {
    isArray = true;
    start = startArr;
    end = endArr;
  } else {
    isArray = false;
    start = startObj;
    end = endObj;
  }

  if (start === -1 || end === -1 || end <= start) {
    throw new Error(`Could not find any JSON bounds in response.`);
  }

  return {
    jsonText: source.slice(start, end + 1),
    isArray
  };
}

function extractFieldRegex(jsonText, fieldName) {
  const regex = new RegExp(`"${fieldName}"\\s*:\\s*"([\\s\\S]*?)"(?=\\s*(?:,|}|]|$))`, 'i');
  const match = jsonText.match(regex);
  if (match) {
    let val = match[1];
    val = val
      .replace(/\\n/g, '\n')
      .replace(/\\r/g, '\r')
      .replace(/\\t/g, '\t')
      .replace(/\\"/g, '"')
      .replace(/\\\\/g, '\\');
    return val;
  }
  return null;
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
  // If we are on Render, DO NOT spawn local LLM proxy!
  if (process.env.RENDER === 'true') {
    console.log(`[Proxy check] Running on Render. Skipping local FreeLLMAPI spawn to conserve memory.`);
    return;
  }

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
