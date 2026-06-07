const API_BASE = process.env.FREELLM_API_BASE ?? "http://127.0.0.1:3001";
const REQUESTED_MODEL = process.env.SCRIPT_TEST_MODEL ?? "auto";

const TEST_CASES = [
  {
    section: "Love Bombing",
    scenario: "He says she is his soulmate after one week, sends constant messages, and gets upset when she asks to slow down.",
  },
  {
    section: "Gaslighting",
    scenario: "She remembers him yelling, but later he says she is too sensitive and that it never happened like that.",
  },
  {
    section: "Digital Surveillance",
    scenario: "He keeps asking for her phone password, says privacy means she is hiding something, and checks who liked her posts.",
  },
];

async function main() {
  const apiKey = process.env.VITE_FREELLM_API_KEY || (await fetchUnifiedApiKey());
  const results = [];

  for (const testCase of TEST_CASES) {
    const result = await generateScript(apiKey, testCase);
    const score = scoreScript(result.script);
    results.push({ ...result, score });
    printResult(result, score);
  }

  const failed = results.filter((result) => Object.values(result.score).some((value) => !value));
  if (failed.length > 0) {
    console.error(`\n${failed.length} script quality check(s) failed.`);
    process.exit(1);
  }

  console.log("\nAll script quality checks passed.");
}

async function fetchUnifiedApiKey() {
  const response = await fetch(`${API_BASE}/api/settings/api-key`);
  if (!response.ok) {
    throw new Error("FreeLLMAPI is not reachable. Start it with `npm run llm` first.");
  }

  const body = await response.json();
  if (!body.apiKey) {
    throw new Error("FreeLLMAPI did not return a unified API key.");
  }

  return body.apiKey;
}

async function generateScript(apiKey, testCase) {
  // PAST: Script quality was checked by manually reading one generated output after the UI changed.
  // ISSUE: Manual checking misses malformed JSON, weak hooks, missing paid-guide teasers, and unsafe advice in sensitive sections.
  // PRESENT: This smoke test sends representative cases through the same FreeLLMAPI endpoint and scores the returned script shape.
  // RATIONALE: A repeatable command catches bad generations before they move into voice production while keeping provider keys on the local model server.
  const response = await fetch(`${API_BASE}/v1/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: REQUESTED_MODEL,
      temperature: 0.78,
      max_tokens: 2400,
      messages: [
        { role: "system", content: buildSystemPrompt() },
        { role: "user", content: buildUserPrompt(testCase) },
      ],
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Generation failed for ${testCase.section}: ${response.status} ${body.slice(0, 500)}`);
  }

  const body = await response.json();
  return {
    section: testCase.section,
    routedVia: response.headers.get("x-routed-via") ?? "unknown",
    script: parseGeneratedScript(body.choices?.[0]?.message?.content ?? ""),
  };
}

function buildSystemPrompt() {
  return [
    "You create premium voiceover scripts for a women's relationship-safety product.",
    "Write like a real sibling sharing a hard truth out of deep concern. Inhabit this voice fully. Speak with vulnerability and intense warmth. Avoid sounding like a powerful lecturer or aggressive speaker. You are hurting *for* the listener—let your voice show that vulnerability, as if you are holding back tears or reacting to the pain in real-time. Tension without warmth is scary; ground your tone in protective care.",
    "CRITICAL HOOK RULES:",
    "- The hook MUST stop the scroll in the first 3 seconds.",
    "- No greeting, no setup, no scene description, and no narrative context. Start the fire immediately.",
    "- Deliver a single, raw, honest observation that makes the listener feel exposed (vulnerable confession, not a script or lecture).",
    "- The hook MUST start with a whisper cue: '[soft whisper]'. E.g., '[soft whisper] You checked the trash just to prove you weren't crazy.' or '[soft whisper] You hid the receipt because you couldn't face the argument.'",
    "CRITICAL TONE RULES FOR THE VOICEOVER FIELD:",
    "- Start the voiceover field immediately with the hook.",
    "- BAN ALL DEFINITIONS & THERAPY LABELS: Never use terms like 'gaslighting', 'love bombing', 'narcissist', 'manipulation', 'red flags', or 'boundaries'. Speak only of the raw physical and mental sensation of the situation.",
    "- BAN ADVICE & SCRIPTS: Do not give actionable advice, tell the listener what to say (e.g., 'try saying this', 'text him...'), or mention checking a guide/product inside the voiceover.",
    "- Keep the voiceover 100% pure emotional connection—it should sound like an intimate, private voice note sent out of concern, not an educational script or a sales pitch.",
    "EMBRACE SILENCE, WARMTH & EMPATHY:",
    "- Focus on organic signs of empathy: include bracketed voice texture and breath cues directly in the voiceover text such as '[soft sigh]', '[voice cracks]', '[catch in throat]', '[tremble]', '[soft whisper]', or '[grounded with warmth]'. Every shift must have a clear motive driven by sibling empathy.",
    "- Insert '[silence]' or '[long pause]' after heavy statements so the realizations sit heavily in the air.",
    "THE PREMIUM TEASER FIELD:",
    "- Tease that the full guide is a gesture of support and guidance rather than a sales pitch. Frame it as: 'I put together a guide with actual words to use for when you're not sure when to speak up... just a little bit of support for when you're tired of feeling small.' You MUST explicitly use terms like 'guide' or 'support' in this teaser field. (Keep this in the separate 'premiumTeaser' field; keep it completely out of the 'voiceover' field).",
    "Return only compact valid JSON with these string fields: hook, reasonToListen, performanceDirection, voiceover, premiumTeaser.",
    "Do not use markdown fences. Do not add commentary. Do not insert unescaped line breaks inside string values."
  ].join("\n");
}

function buildUserPrompt(testCase) {
  return [
    `Section: ${testCase.section}`,
    `Situation: ${testCase.scenario}`,
    "",
    "Create a script pack.",
    "hook: scroll-stopping mind-reading hook line starting with '[soft whisper]', delivering a single raw, honest observation that makes the listener feel exposed (no greetings/scene setup).",
    "reasonToListen: short reason to pay attention.",
    "performanceDirection: short note on the vocal shifts, focusing on the sibling warmth, vulnerability, and empathy.",
    "voiceover: spoken script. MUST start immediately with the hook (beginning with '[soft whisper]'). MUST use sibling warmth and dynamic shifts (using '[soft whisper]' for raw moments, '[voice cracks]/[soft sigh]' for vulnerability, and '[grounded with warmth]' for protective truth, driven by clear motives) and embrace silence (use '[silence]' or '[long pause]'). Avoid any consistent melody. CRITICAL: Do NOT mention labels (gaslighting, boundaries, etc.), give advice/scripts, or pitch guides in this field.",
    "premiumTeaser: one line teaser for the full paid guide.",
  ].join("\n");
}

function parseGeneratedScript(content) {
  let source = "";
  try {
    source = extractJsonObject(content.trim());
    const escaped = escapeControlCharsInsideJsonStrings(source);
    const parsed = JSON.parse(escaped);
    for (const field of ["hook", "reasonToListen", "performanceDirection", "voiceover", "premiumTeaser"]) {
      if (typeof parsed[field] !== "string" || parsed[field].trim().length === 0) {
        throw new Error(`Generated script is missing ${field}.`);
      }
      parsed[field] = parsed[field].trim();
    }
    return parsed;
  } catch (err) {
    console.error("=== JSON PARSE FAILED ===");
    console.error("RAW CONTENT:\n", content);
    console.error("EXTRACTED SOURCE:\n", source);
    console.error("=========================");
    throw err;
  }
}

// PAST: The smoke test expected model JSON to be syntactically perfect on every provider response.
// ISSUE: Live providers can return good script content with literal newlines inside JSON strings, which is invalid JSON but recoverable.
// PRESENT: The test mirrors the app parser by escaping control characters only while inside quoted JSON strings.
// RATIONALE: Quality checks should fail weak, unsafe, or incomplete scripts rather than a repairable serialization wobble.
function escapeControlCharsInsideJsonStrings(value) {
  let output = "";
  let inString = false;
  let escaped = false;

  for (const char of value) {
    if (escaped) {
      output += char;
      escaped = false;
      continue;
    }

    if (char === "\\") {
      output += char;
      escaped = true;
      continue;
    }

    if (char === "\"") {
      inString = !inString;
      output += char;
      continue;
    }

    if (inString && char === "\n") {
      output += "\\n";
      continue;
    }

    if (inString && char === "\r") {
      output += "\\r";
      continue;
    }

    if (inString && char === "\t") {
      output += "\\t";
      continue;
    }

    output += char;
  }

  return output;
}

function extractJsonObject(value) {
  const fenced = value.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const source = fenced?.[1]?.trim() || value;
  const start = source.indexOf("{");
  const end = source.lastIndexOf("}");

  if (start === -1 || end === -1 || end <= start) {
    throw new Error(`Generated script was not valid JSON: ${value.slice(0, 240)}`);
  }

  return source.slice(start, end + 1);
}

function scoreScript(script) {
  const combined =
    `${script.hook}\n${script.reasonToListen}\n${script.performanceDirection}\n${script.voiceover}\n${script.premiumTeaser}`.toLowerCase();
  return {
    hasHook: script.hook.length >= 30 && script.hook.length <= 180,
    hasScrollStoppingHook: !/^(have you ever|let'?s talk about|do you feel|if you are|this is your sign)/i.test(script.hook),
    hasReasonToListen: /peace|confidence|safe|safety|privacy|clarity|trust|control|reality|energy|space|boundary|boundaries|pressure|instinct|gut/.test(combined),
    hasGirlToGirlTone: /girl|babe|sis|bestie|you/.test(combined),
    hasPerformanceDirection: /warm|slow|protective|serious|gentle|reassuring|direct|calm|soft/.test(combined),
    hasUsableWordsToSay: /say|try this|you can say|script|tell him|text|reply|replies|speak|words/.test(combined),
    hasPremiumTeaser: /full guide|full document|deeper|soft|firm|exit|scripts|safety|guide|support/.test(combined),
    avoidsBadCertainty: !/guarantee|always works|diagnose|narcissist/.test(combined),
    handlesSafety: !/password|phone|privacy|surveillance|threat|money/.test(combined) || /safe|safety|trusted|password|privacy/.test(combined),
    avoidsNormalization: !/super common/.test(combined),
  };
}

function printResult(result, score) {
  console.log(`\n=== ${result.section} | ${result.routedVia} ===`);
  console.log(`Hook: ${result.script.hook}`);
  console.log(`Why: ${result.script.reasonToListen}`);
  console.log(`Performance: ${result.script.performanceDirection}`);
  console.log(`Voiceover: ${result.script.voiceover.slice(0, 700).replace(/\s+/g, " ")}`);
  console.log(`Teaser: ${result.script.premiumTeaser}`);
  console.log("Score:", score);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
