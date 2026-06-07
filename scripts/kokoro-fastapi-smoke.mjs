const API_BASE = process.env.KOKORO_FASTAPI_BASE ?? "http://127.0.0.1:8880";

async function main() {
  // PAST: Premium audio generation had no dedicated health check, so a missing TTS server would only show up after a user clicked Generate.
  // ISSUE: That makes the pipeline feel broken even when the frontend and script generator are working correctly.
  // PRESENT: This smoke test sends a tiny OpenAI-compatible speech request to Kokoro-FastAPI and verifies audio bytes come back.
  // RATIONALE: A focused command separates server availability from UI bugs and confirms the production voice path before longer scripts are rendered.
  const response = await fetch(`${API_BASE}/v1/audio/speech`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "kokoro",
      input: "Hey girl. This is the premium voice pipeline test.",
      voice: "af_bella(2)+af_sky(1)",
      response_format: "mp3",
      speed: 1,
      stream: false,
      volume_multiplier: 1.08,
    }),
  }).catch((error) => {
    throw new Error(`Kokoro-FastAPI is not reachable at ${API_BASE}. Start it with npm run tts:fastapi. ${error.message}`);
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Kokoro-FastAPI failed: ${response.status} ${body.slice(0, 500)}`);
  }

  const bytes = await response.arrayBuffer();
  if (bytes.byteLength < 1000) {
    throw new Error(`Kokoro-FastAPI returned too little audio data: ${bytes.byteLength} bytes.`);
  }

  console.log(`Kokoro-FastAPI audio smoke passed: ${bytes.byteLength.toLocaleString()} bytes.`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
