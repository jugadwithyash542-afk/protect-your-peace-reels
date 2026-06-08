import React from "react";
import { createRoot } from "react-dom/client";
import { Copy, Download, Loader2, Mic2, RefreshCcw, Send, Sparkles, Volume2 } from "lucide-react";
import { KokoroTTS } from "kokoro-js";
import "./styles.css";

const MODEL_ID = "onnx-community/Kokoro-82M-v1.0-ONNX";
const FREELLM_API_BASE = import.meta.env.VITE_FREELLM_API_BASE ?? "http://127.0.0.1:3001";
const FREELLM_API_KEY = import.meta.env.VITE_FREELLM_API_KEY ?? "";
const KOKORO_FASTAPI_BASE = import.meta.env.VITE_KOKORO_FASTAPI_BASE ?? "http://127.0.0.1:8880";

// ── Big-Sis voice + teaser variety engine ──────────────────────────────────
// PAST: premiumTeaser was steered by a single hardcoded example ("Frame it as: '...feeling small'").
// ISSUE: the teaser converged on the same wording every generation, so the CTA felt copy-pasted.
// PRESENT: a fixed IDENTITY block locks the persona; a rotating angle + bio cue is injected per run
//          so the model writes a fresh teaser each time.
// RATIONALE: same lever as the Render pipeline — lock the character, randomise the raw material.
//            Pure shared-codebase JS, OTA-deployable, no native changes.
const VOCAL_IDENTITY: string[] = [
  "IDENTITY & VOICE (hold this the entire script):",
  "- You are a protective, empathetic older sister. Your single goal is to make the listener feel seen and safe.",
  "- Speak in fragments. Use natural, uneven rhythm. Avoid clinical language and perfect grammar.",
  "- Prioritise the emotional subtext over the clarity of the sentence — feeling matters more than information.",
  "- Never sound like a structured outline, a lecture, or a sales pitch. Your voice is a confession, not a presentation.",
  "- Lean into the silence. Let the emotion drive the pacing, not the structure.",
];

const PITCH_ANGLES: string[] = [
  "a quiet confession that you couldn't stop thinking about her, so you wrote the words down",
  "gently giving her permission to not have the words yet — that is exactly why you gathered them",
  "sliding it across the table like a folded note, almost shy to even mention it",
  "telling her you made this for your own past self, and you are just leaving it where she can find it",
  "no pressure at all — only pointing to where the words live for the night she cannot find her own",
  "a protective whisper, like tucking her in: the words will be waiting whenever she is ready",
  "admitting you wish someone had handed YOU this back then, so now you are handing it to her",
];

const BIO_CUES: string[] = [
  "it is in the bio if she ever needs it",
  "the link is in the profile",
  "it is sitting in the profile, no rush",
  "the link is in the bio, for whenever",
  "it is in the profile, only if she wants it",
  "it is there in the bio, quietly waiting",
];

const pick = <T,>(arr: readonly T[]): T => arr[Math.floor(Math.random() * arr.length)];

const VOICES = [
  {
    id: "af_bella",
    label: "Bella",
    detail: "Warm American female voice",
  },
  {
    id: "af_nicole",
    label: "Nicole",
    detail: "Soft American female voice",
  },
] as const;

type VoiceId = (typeof VOICES)[number]["id"];
type KokoroEngine = Awaited<ReturnType<typeof KokoroTTS.from_pretrained>>;
type GeneratedAudio = {
  blobUrl: string;
  fileName: string;
  label: string;
};
type ScriptSection = (typeof SCRIPT_SECTIONS)[number];
type ScriptModelId = (typeof SCRIPT_MODELS)[number]["id"];
type VoiceBackend = "preview" | "premium" | "gemini";
type PremiumVoiceId = (typeof PREMIUM_VOICES)[number]["id"];
type GeminiVoiceId = (typeof GEMINI_VOICES)[number]["id"];
type GeminiModelId = (typeof GEMINI_MODELS)[number]["id"];
type AudioFormat = (typeof AUDIO_FORMATS)[number];
type GeneratedScript = {
  hook: string;
  reasonToListen: string;
  performanceDirection: string;
  voiceover: string;
  premiumTeaser: string;
  fullText: string;
};

const SCRIPT_SECTIONS = [
  "Love Bombing",
  "Gaslighting",
  "Isolation",
  "Guilt Tripping",
  "Silent Treatment",
  "Future Faking",
  "Negging",
  "Playing the Victim",
  "Breadcrumbing",
  "Hot-and-Cold Behavior",
  "Triangulation",
  "Intimidation and Threats",
  "Financial Control",
  "Digital Surveillance",
] as const;

const SCRIPT_MODELS = [
  {
    id: "auto",
    label: "Auto premium",
    detail: "Router picks the best available model",
  },
  {
    id: "gemini-2.5-flash",
    label: "Gemini 2.5 Flash",
    detail: "Strong emotional copy and long context",
  },
  {
    id: "deepseek/deepseek-v3.1:free",
    label: "DeepSeek V3.1",
    detail: "Good structure and reasoning",
  },
  {
    id: "moonshotai/kimi-k2:free",
    label: "Kimi K2",
    detail: "Strong natural-language drafting",
  },
  {
    id: "z-ai/glm-4.5-air:free",
    label: "GLM 4.5 Air",
    detail: "Fast fallback for simple scripts",
  },
] as const;

const PREMIUM_VOICES = [
  {
    id: "af_bella(2)+af_sky(1)",
    label: "Bella + Sky",
    detail: "Warm lead voice with a lighter lift for emotional scripts",
  },
  {
    id: "af_heart",
    label: "Heart",
    detail: "Soft, intimate narration for safety and reassurance",
  },
  {
    id: "af_bella",
    label: "Bella",
    detail: "Clear warm voice for direct educational scripts",
  },
  {
    id: "af_sky",
    label: "Sky",
    detail: "Airy voice for gentle social clips",
  },
] as const;

const GEMINI_VOICES = [
  {
    id: "Kore",
    label: "Kore",
    detail: "Warm, supportive female voice",
  },
  {
    id: "Puck",
    label: "Puck",
    detail: "Friendly, engaging narration",
  },
  {
    id: "Aoede",
    label: "Aoede",
    detail: "Clear, expressive female voice",
  },
  {
    id: "Charon",
    label: "Charon",
    detail: "Calm, reassuring voice",
  },
  {
    id: "Fenrir",
    label: "Fenrir",
    detail: "Deep, steady voice",
  },
] as const;

const GEMINI_MODELS = [
  {
    id: "gemini-3.1-flash-tts-preview",
    label: "Gemini 3.1 Flash TTS",
    detail: "High-fidelity expressive Text-to-Speech model",
  },
  {
    id: "gemini-2.5-flash",
    label: "Gemini 2.5 Flash Native Audio Dialog",
    detail: "Native multimodal audio generation model",
  },
  {
    id: "gemini-3.1-flash-live-preview",
    label: "Gemini 3 Flash Live",
    detail: "Low-latency live conversation audio model",
  },
] as const;

const AUDIO_FORMATS = ["mp3", "wav", "opus", "flac"] as const;

const starterScript =
  "Write or paste your voiceover script here. Choose Bella or Nicole, then generate the voice on the right.";

function App() {
  const [section, setSection] = React.useState<ScriptSection>("Love Bombing");
  const [scenario, setScenario] = React.useState(
    "He is moving too fast, saying huge romantic things, and making her feel guilty when she asks to slow down.",
  );
  const [scriptLength, setScriptLength] = React.useState("60");
  const [scriptModel, setScriptModel] = React.useState<ScriptModelId>("auto");
  const [generatedScript, setGeneratedScript] = React.useState<GeneratedScript | null>(null);
  const [script, setScript] = React.useState(starterScript);
  const [voiceBackend, setVoiceBackend] = React.useState<VoiceBackend>("gemini");
  const [voice, setVoice] = React.useState<VoiceId>("af_bella");
  const [premiumVoice, setPremiumVoice] = React.useState<PremiumVoiceId>("af_bella(2)+af_sky(1)");
  const [geminiVoice, setGeminiVoice] = React.useState<GeminiVoiceId>("Kore");
  const [geminiModel, setGeminiModel] = React.useState<GeminiModelId>("gemini-3.1-flash-tts-preview");
  const [audioFormat, setAudioFormat] = React.useState<AudioFormat>("mp3");
  const [volume, setVolume] = React.useState(1.08);
  const [speed, setSpeed] = React.useState(1);
  const [status, setStatus] = React.useState("Voice ready");
  const [scriptStatus, setScriptStatus] = React.useState("Script ready");
  const [isGeneratingScript, setIsGeneratingScript] = React.useState(false);
  const [isLoadingModel, setIsLoadingModel] = React.useState(false);
  const [isGenerating, setIsGenerating] = React.useState(false);
  const [audio, setAudio] = React.useState<GeneratedAudio | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [scriptError, setScriptError] = React.useState<string | null>(null);
  const ttsRef = React.useRef<KokoroEngine | null>(null);

  React.useEffect(() => {
    return () => {
      if (audio?.blobUrl) URL.revokeObjectURL(audio.blobUrl);
    };
  }, [audio]);

  const selectedVoice = VOICES.find((item) => item.id === voice) ?? VOICES[0];
  const selectedPremiumVoice = PREMIUM_VOICES.find((item) => item.id === premiumVoice) ?? PREMIUM_VOICES[0];
  const selectedGeminiVoice = GEMINI_VOICES.find((item) => item.id === geminiVoice) ?? GEMINI_VOICES[0];
  const activeVoiceLabel =
    voiceBackend === "gemini"
      ? selectedGeminiVoice.label
      : voiceBackend === "premium"
      ? selectedPremiumVoice.label
      : selectedVoice.label;
  const activeVoiceDetail =
    voiceBackend === "gemini"
      ? selectedGeminiVoice.detail
      : voiceBackend === "premium"
      ? selectedPremiumVoice.detail
      : selectedVoice.detail;
  const canGenerate = script.trim().length > 0 && !isLoadingModel && !isGenerating;
  const canGenerateScript = scenario.trim().length > 0 && !isGeneratingScript;

  async function generateScript() {
    const scenarioText = scenario.trim();
    if (!scenarioText) {
      setScriptError("Add a situation before generating a script.");
      return;
    }

    setScriptError(null);
    setIsGeneratingScript(true);
    setScriptStatus("Generating hook");

    try {
      // PAST: Script ideas were written manually in markdown notes, so every new section needed a fresh human draft.
      // ISSUE: That does not scale into a pipeline because voice generation can only work after someone separately creates usable copy.
      // PRESENT: The app now sends a structured script brief to the standalone FreeLLMAPI chat endpoint and expects a clean JSON script pack back.
      // RATIONALE: Keeping generation in one shared web flow lets a hookable script move straight into Kokoro voice generation without exposing provider keys or changing native code.
      const output = await createPremiumScript({
        section,
        scenario: scenarioText,
        scriptLength,
        model: scriptModel,
      });
      setGeneratedScript(output);
      setScript(output.voiceover);
      setScriptStatus("Script generated");
    } catch (cause) {
      console.error(cause);
      setScriptError(cause instanceof Error ? cause.message : "Script generation failed.");
      setScriptStatus("Generation failed");
    } finally {
      setIsGeneratingScript(false);
    }
  }

  async function getTts() {
    if (ttsRef.current) return ttsRef.current;

    setIsLoadingModel(true);
    setStatus("Loading Kokoro model");
    try {
      // PAST: A TTS tool often sends text to a remote API and waits for a hosted voice result.
      // ISSUE: That creates unnecessary latency, privacy concerns, and a backend dependency for a simple script-to-voice desk.
      // PRESENT: Kokoro-82M-v1.0-ONNX loads once in the browser through kokoro-js with the q8 WASM runtime.
      // RATIONALE: The model remains OTA-friendly because all behavior lives in shared web code while still giving local Bella/Nicole generation.
      ttsRef.current = await KokoroTTS.from_pretrained(MODEL_ID, {
        dtype: "q8",
        device: "wasm",
      });
      return ttsRef.current;
    } finally {
      setIsLoadingModel(false);
    }
  }

  async function generateVoice() {
    const text = script.trim();
    if (!text) {
      setError("Add a script before generating voice.");
      return;
    }

    setError(null);
    setIsGenerating(true);
    setStatus(`Generating ${activeVoiceLabel}`);

    try {
      const output =
        voiceBackend === "gemini"
          ? await generateGeminiAudio({
              text,
              voice: geminiVoice,
              model: geminiModel,
            })
          : voiceBackend === "premium"
          ? await generatePremiumAudio({
              text,
              voice: premiumVoice,
              speed,
              format: audioFormat,
              volume,
            })
          : await generatePreviewAudio({
              text,
              voice,
              speed,
            });
      const blob = output.blob;
      const nextUrl = URL.createObjectURL(blob);
      setAudio((current) => {
        if (current?.blobUrl) URL.revokeObjectURL(current.blobUrl);
        return {
          blobUrl: nextUrl,
          fileName: output.fileName,
          label: output.label,
        };
      });
      setStatus("Voice ready");
    } catch (cause) {
      console.error(cause);
      setError(cause instanceof Error ? cause.message : "Voice generation failed.");
      setStatus("Generation failed");
    } finally {
      setIsGenerating(false);
    }
  }

  async function generatePreviewAudio(input: { text: string; voice: VoiceId; speed: number }) {
    const tts = await getTts();
    // PAST: Voice selection could be hidden in separate scripts or require changing constants before each run.
    // ISSUE: That makes side-by-side writing slow because every script tweak needs a code edit or terminal command.
    // PRESENT: The UI passes the selected Kokoro preview voice id directly into browser generation for each request.
    // RATIONALE: Bella and Nicole stay one click apart, so quick draft playback remains available even without the premium server.
    const output = await tts.generate(input.text, {
      voice: input.voice,
      speed: input.speed,
    });
    return {
      blob: audioToWavBlob(output),
      fileName: `kokoro-preview-${input.voice}-${Date.now()}.wav`,
      label: "Preview WAV",
    };
  }

  async function generatePremiumAudio(input: {
    text: string;
    voice: PremiumVoiceId;
    speed: number;
    format: AudioFormat;
    volume: number;
  }) {
    // PAST: The production path depended on browser WASM output, which only gave us a quick local WAV and made long-form generation heavier on the frontend.
    // ISSUE: Premium scripts need longer audio, downloadable formats, voice blends, and steadier generation than a browser-only preview can comfortably provide.
    // PRESENT: Premium mode calls Kokoro-FastAPI's OpenAI-compatible /v1/audio/speech endpoint with a voice mix, output format, speed, and volume multiplier.
    // RATIONALE: This keeps the script-to-audio pipeline modular: FreeLLMAPI writes the copy, Kokoro-FastAPI renders the voice, and the React app only orchestrates the workflow.
    const response = await fetch(`${KOKORO_FASTAPI_BASE}/v1/audio/speech`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "kokoro",
        input: input.text,
        voice: input.voice,
        response_format: input.format,
        speed: input.speed,
        stream: false,
        volume_multiplier: input.volume,
      }),
    });

    if (!response.ok) {
      const message = await response.text().catch(() => response.statusText);
      throw new Error(`Start Kokoro-FastAPI on port 8880. ${message.slice(0, 220)}`);
    }

    return {
      blob: await response.blob(),
      fileName: `kokoro-premium-${input.voice.replace(/[^a-z0-9]+/gi, "-")}-${Date.now()}.${input.format}`,
      label: `Premium ${input.format.toUpperCase()}`,
    };
  }

  async function generateGeminiAudio(input: { text: string; voice: GeminiVoiceId; model: GeminiModelId }) {
    const apiKey = await getFreeLlmApiKey();
    const response = await fetch(`${FREELLM_API_BASE}/v1/audio/speech`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        input: input.text,
        voice: input.voice,
        model: input.model,
      }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({ error: { message: response.statusText } }));
      throw new Error(body.error?.message ?? `Gemini TTS failed with HTTP ${response.status}`);
    }

    const blob = await response.blob();
    return {
      blob,
      fileName: `gemini-tts-${input.voice.toLowerCase()}-${Date.now()}.wav`,
      label: "Gemini WAV",
    };
  }

  function resetScript() {
    setScript("");
    setStatus("Ready");
    setError(null);
  }

  async function copyGeneratedScript() {
    if (!generatedScript) return;
    await navigator.clipboard.writeText(generatedScript.fullText);
    setScriptStatus("Copied");
  }

  return (
    <main className="appShell">
      <section className="scriptPane" aria-label="Script generator and editor">
        <div className="paneHeader">
          <div>
            <p className="eyebrow">Script pipeline</p>
            <h1>Hook To Voice Desk</h1>
          </div>
          <button className="iconButton" onClick={resetScript} title="Clear script" type="button">
            <RefreshCcw size={18} />
          </button>
        </div>

        <div className="generatorPanel" aria-label="Script generation controls">
          <div className="fieldGrid">
            <label>
              <span>Section</span>
              <select value={section} onChange={(event) => setSection(event.target.value as ScriptSection)}>
                {SCRIPT_SECTIONS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Length</span>
              <select value={scriptLength} onChange={(event) => setScriptLength(event.target.value)}>
                <option value="30">30 sec</option>
                <option value="60">60 sec</option>
                <option value="90">90 sec</option>
                <option value="120">2 min</option>
                <option value="180">3 min</option>
              </select>
            </label>
            <label>
              <span>Model</span>
              <select value={scriptModel} onChange={(event) => setScriptModel(event.target.value as ScriptModelId)}>
                {SCRIPT_MODELS.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="scenarioField">
            <span>Situation she is facing</span>
            <textarea
              value={scenario}
              onChange={(event) => setScenario(event.target.value)}
              placeholder="Example: She feels confused because he apologizes sweetly, then repeats the same behavior..."
              spellCheck="true"
            />
          </label>

          <button className="generateButton" disabled={!canGenerateScript} onClick={generateScript} type="button">
            {isGeneratingScript ? <Loader2 className="spin" size={19} /> : <Sparkles size={19} />}
            {isGeneratingScript ? "Generating script" : "Generate hook script"}
          </button>

          {scriptError ? <p className="errorText">{scriptError}</p> : <p className="voiceDetail">{scriptStatus}</p>}
        </div>

        {generatedScript ? (
          <div className="generatedSummary" aria-label="Generated script summary">
            <div>
              <p className="eyebrow">Hook</p>
              <strong>{generatedScript.hook}</strong>
            </div>
            <p>{generatedScript.reasonToListen}</p>
            <p>{generatedScript.performanceDirection}</p>
            <p>{generatedScript.premiumTeaser}</p>
            <button className="secondaryButton" onClick={copyGeneratedScript} type="button">
              <Copy size={17} />
              Copy full script pack
            </button>
          </div>
        ) : null}

        <textarea
          className="voiceScriptEditor"
          value={script}
          onChange={(event) => setScript(event.target.value)}
          placeholder="Paste your script here..."
          spellCheck="true"
        />

        <div className="scriptMeta">
          <span>{script.trim().length.toLocaleString()} chars</span>
          <span>{Math.max(1, Math.ceil(script.trim().split(/\s+/).filter(Boolean).length / 150))} min read</span>
        </div>
      </section>

      <section className="voicePane" aria-label="Voice generator">
        <div className="paneHeader">
          <div>
            <p className="eyebrow">Voice</p>
            <h2>{activeVoiceLabel}</h2>
          </div>
          <div className="statusBadge">{status}</div>
        </div>

        <div className="modeSwitch" role="radiogroup" aria-label="Audio backend">
          <button
            className={voiceBackend === "gemini" ? "modeButton active" : "modeButton"}
            onClick={() => setVoiceBackend("gemini")}
            role="radio"
            aria-checked={voiceBackend === "gemini"}
            type="button"
          >
            Gemini TTS
          </button>
          <button
            className={voiceBackend === "premium" ? "modeButton active" : "modeButton"}
            onClick={() => setVoiceBackend("premium")}
            role="radio"
            aria-checked={voiceBackend === "premium"}
            type="button"
          >
            Premium server
          </button>
          <button
            className={voiceBackend === "preview" ? "modeButton active" : "modeButton"}
            onClick={() => setVoiceBackend("preview")}
            role="radio"
            aria-checked={voiceBackend === "preview"}
            type="button"
          >
            Browser preview
          </button>
        </div>

        {voiceBackend === "gemini" ? (
          <div className="voiceList" role="radiogroup" aria-label="Gemini TTS voices">
            {GEMINI_VOICES.map((item) => (
              <button
                key={item.id}
                className={item.id === geminiVoice ? "voiceOption active" : "voiceOption"}
                onClick={() => setGeminiVoice(item.id)}
                role="radio"
                aria-checked={item.id === geminiVoice}
                type="button"
              >
                <span className="voiceIcon">
                  <Mic2 size={18} />
                </span>
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.id}</small>
                </span>
              </button>
            ))}
          </div>
        ) : voiceBackend === "premium" ? (
          <div className="voiceList" role="radiogroup" aria-label="Kokoro FastAPI voices">
            {PREMIUM_VOICES.map((item) => (
              <button
                key={item.id}
                className={item.id === premiumVoice ? "voiceOption active" : "voiceOption"}
                onClick={() => setPremiumVoice(item.id)}
                role="radio"
                aria-checked={item.id === premiumVoice}
                type="button"
              >
                <span className="voiceIcon">
                  <Mic2 size={18} />
                </span>
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.id}</small>
                </span>
              </button>
            ))}
          </div>
        ) : (
          <div className="voiceList" role="radiogroup" aria-label="Kokoro preview voices">
            {VOICES.map((item) => (
              <button
                key={item.id}
                className={item.id === voice ? "voiceOption active" : "voiceOption"}
                onClick={() => setVoice(item.id)}
                role="radio"
                aria-checked={item.id === voice}
                type="button"
              >
                <span className="voiceIcon">
                  <Mic2 size={18} />
                </span>
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.id}</small>
                </span>
              </button>
            ))}
          </div>
        )}

        {voiceBackend === "premium" ? (
          <label className="selectControl">
            <span>Output format</span>
            <select value={audioFormat} onChange={(event) => setAudioFormat(event.target.value as AudioFormat)}>
              {AUDIO_FORMATS.map((format) => (
                <option key={format} value={format}>
                  {format.toUpperCase()}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {voiceBackend === "gemini" ? (
          <label className="selectControl">
            <span>Gemini Model</span>
            <select value={geminiModel} onChange={(event) => setGeminiModel(event.target.value as GeminiModelId)}>
              {GEMINI_MODELS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {voiceBackend !== "gemini" ? (
          <label className="speedControl">
            <span>
              <Volume2 size={18} />
              Speed
            </span>
            <strong>{speed.toFixed(2)}x</strong>
            <input
              type="range"
              min="0.75"
              max="1.25"
              step="0.01"
              value={speed}
              onChange={(event) => setSpeed(Number(event.target.value))}
            />
          </label>
        ) : null}

        {voiceBackend === "premium" ? (
          <label className="speedControl">
            <span>
              <Volume2 size={18} />
              Voice lift
            </span>
            <strong>{volume.toFixed(2)}x</strong>
            <input
              type="range"
              min="0.85"
              max="1.35"
              step="0.01"
              value={volume}
              onChange={(event) => setVolume(Number(event.target.value))}
            />
          </label>
        ) : null}

        <button className="generateButton" disabled={!canGenerate} onClick={generateVoice} type="button">
          {isLoadingModel || isGenerating ? <Loader2 className="spin" size={19} /> : <Send size={19} />}
          {isLoadingModel ? "Loading model" : isGenerating ? "Generating voice" : `Generate ${voiceBackend === "premium" ? "premium audio" : "preview voice"}`}
        </button>

        <div className="outputPanel">
          {audio ? (
            <>
              <audio controls src={audio.blobUrl} />
              <a className="downloadButton" href={audio.blobUrl} download={audio.fileName}>
                <Download size={18} />
                Download {audio.label}
              </a>
            </>
          ) : (
            <div className="emptyOutput">
              <Mic2 size={34} />
              <p>Generated voice appears here.</p>
            </div>
          )}
        </div>

        {error ? <p className="errorText">{error}</p> : <p className="voiceDetail">{activeVoiceDetail}</p>}
      </section>
    </main>
  );
}

async function createPremiumScript(input: { section: string; scenario: string; scriptLength: string; model: string }) {
  const apiKey = await getFreeLlmApiKey();
  // Per-run teaser variety seeds — sampled here so each generation differs while the persona holds.
  const teaserAngle = pick(PITCH_ANGLES);
  const teaserBioCue = pick(BIO_CUES);
  const response = await fetch(`${FREELLM_API_BASE}/v1/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: input.model,
      temperature: 0.78,
      max_tokens: getScriptTokenBudget(input.scriptLength),
      messages: [
        {
          role: "system",
          content: buildScriptSystemPrompt(teaserAngle, teaserBioCue),
        },
        {
          role: "user",
          content: buildScriptUserPrompt(input, teaserAngle, teaserBioCue),
        },
      ],
    }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: { message: response.statusText } }));
    throw new Error(body.error?.message ?? `FreeLLMAPI failed with HTTP ${response.status}`);
  }

  const completion = await response.json();
  const content = completion?.choices?.[0]?.message?.content;
  if (typeof content !== "string" || !content.trim()) {
    throw new Error("FreeLLMAPI returned an empty script.");
  }

  return parseGeneratedScript(content);
}

function getScriptTokenBudget(scriptLength: string) {
  const seconds = Number(scriptLength);
  if (seconds >= 180) return 4200;
  if (seconds >= 120) return 3200;
  if (seconds >= 90) return 2400;
  return 2000;
}

async function getFreeLlmApiKey() {
  if (FREELLM_API_KEY) return FREELLM_API_KEY;

  const response = await fetch(`${FREELLM_API_BASE}/api/settings/api-key`);
  if (!response.ok) {
    throw new Error("Start FreeLLMAPI on port 3001 or set VITE_FREELLM_API_KEY.");
  }

  const body = (await response.json()) as { apiKey?: string };
  if (!body.apiKey) {
    throw new Error("FreeLLMAPI did not return a unified API key.");
  }

  return body.apiKey;
}

function buildScriptSystemPrompt(teaserAngle: string, teaserBioCue: string) {
  // PAST: The hook was a bit descriptive and slow, and the prompt allowed a setup or greeting.
  // ISSUE: The first 3 seconds are what stops the scroll. Any setup, scene description, or greeting slows down the hook. It needs to be an immediate, whisper-led punch.
  // PRESENT: Rewrote rules to mandate that the hook starts directly with a [soft whisper], delivering a single honest observation that makes the listener feel exposed (confessional style).
  // RATIONALE: Starts the fire immediately and engages the listener on a visceral, vulnerable level from the very first word.
  return [
    "You create premium voiceover scripts for a women's relationship-safety product.",
    ...VOCAL_IDENTITY,
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
    // PAST: a single example sentence was given as the frame, so the teaser converged on it.
    // ISSUE: every teaser read the same ("...tired of feeling small").
    // PRESENT: the model writes the teaser itself, steered by a per-run angle + bio cue.
    // RATIONALE: fresh wording each run; the 'guide'/'support', non-commercial guardrails stay.
    "- Tease the full guide as a gesture of support, never a sales pitch. WRITE it yourself — there is no fixed template.",
    "- This run's teaser ANGLE (write fresh words around this idea, do NOT quote it): " + teaserAngle + ".",
    "- Point to where the guide lives using THIS idea, reworded naturally: " + teaserBioCue + ".",
    "- You MUST still use a word like 'guide' or 'support'. Keep this in the 'premiumTeaser' field only; keep it completely out of the 'voiceover' field.",
    "- BANNED: do NOT reuse 'tired of feeling small' or 'I put together a guide with actual words to use'. Find your own words.",
    "Return only compact valid JSON with these string fields: hook, reasonToListen, performanceDirection, voiceover, premiumTeaser.",
    "Do not use markdown fences. Do not add commentary. Do not insert unescaped line breaks inside string values."
  ].join("\n");
}

function buildScriptUserPrompt(
  input: { section: string; scenario: string; scriptLength: string; model: string },
  teaserAngle: string,
  teaserBioCue: string,
) {
  return [
    `Section: ${input.section}`,
    `Situation: ${input.scenario}`,
    "",
    "Create a script pack.",
    "hook: scroll-stopping mind-reading hook line starting with '[soft whisper]', delivering a single raw, honest observation that makes the listener feel exposed (no greetings/scene setup).",
    "reasonToListen: short reason to pay attention.",
    "performanceDirection: short note on the vocal shifts, focusing on the sibling warmth, vulnerability, and empathy.",
    "voiceover: spoken script. MUST start immediately with the hook (beginning with '[soft whisper]'). MUST use sibling warmth and dynamic shifts (using '[soft whisper]' for raw moments, '[voice cracks]/[soft sigh]' for vulnerability, and '[grounded with warmth]' for protective truth, driven by clear motives) and embrace silence (use '[silence]' or '[long pause]'). Avoid any consistent melody. CRITICAL: Do NOT mention labels (gaslighting, boundaries, etc.), give advice/scripts, or pitch guides in this field.",
    `premiumTeaser: one fresh line for the full guide, written in the big-sis voice. Build it around this run's angle: "${teaserAngle}", and point to the guide using this idea reworded naturally: "${teaserBioCue}". Use a word like 'guide' or 'support'. Never reuse the banned phrasings.`,
  ].join("\n");
}

function parseGeneratedScript(content: string): GeneratedScript {
  const trimmed = content.trim();
  const jsonText = extractJsonObject(trimmed);
  const parsed = JSON.parse(escapeControlCharsInsideJsonStrings(jsonText)) as Partial<GeneratedScript>;
  const hook = normalizeGeneratedField(parsed.hook);
  const reasonToListen = normalizeGeneratedField(parsed.reasonToListen);
  const performanceDirection = normalizeGeneratedField(parsed.performanceDirection);
  const voiceover = normalizeGeneratedField(parsed.voiceover);
  const premiumTeaser = normalizeGeneratedField(parsed.premiumTeaser);

  if (!hook || !reasonToListen || !performanceDirection || !voiceover || !premiumTeaser) {
    throw new Error("Generated script is missing a required section.");
  }

  return {
    hook,
    reasonToListen,
    performanceDirection,
    voiceover,
    premiumTeaser,
    fullText: [
      `Hook: ${hook}`,
      `Why listen: ${reasonToListen}`,
      `Performance: ${performanceDirection}`,
      "",
      voiceover,
      "",
      `Paid guide teaser: ${premiumTeaser}`,
    ].join("\n"),
  };
}

function extractJsonObject(value: string) {
  const fenced = value.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const source = fenced?.[1]?.trim() || value;
  const start = source.indexOf("{");
  const end = source.lastIndexOf("}");

  if (start === -1 || end === -1 || end <= start) {
    throw new Error("Generated script was not valid JSON.");
  }

  return source.slice(start, end + 1);
}

function normalizeGeneratedField(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

// PAST: The script parser assumed every model would return perfectly escaped JSON after being instructed to do so.
// ISSUE: Some providers still insert literal line breaks inside JSON string values, which makes otherwise usable scripts fail before they reach voice generation.
// PRESENT: Before JSON.parse, control characters found inside quoted JSON strings are escaped while the rest of the payload is left untouched.
// RATIONALE: This keeps the pipeline strict about required fields but tolerant of common LLM formatting drift.
function escapeControlCharsInsideJsonStrings(value: string) {
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

function audioToWavBlob(audio: unknown) {
  if (audio instanceof Blob) {
    return audio;
  }

  const maybeAudio = audio as {
    toBlob?: () => Blob;
    blob?: Blob;
    audio?: Float32Array | number[];
    sampling_rate?: number;
    sample_rate?: number;
  };

  if (typeof maybeAudio.toBlob === "function") {
    return maybeAudio.toBlob();
  }

  if (maybeAudio.blob instanceof Blob) {
    return maybeAudio.blob;
  }

  if (maybeAudio.audio) {
    // PAST: Some audio libraries only expose raw PCM samples, leaving the browser without a playable file wrapper.
    // ISSUE: An <audio> element cannot reliably play naked Float32 samples or download them as a voice file.
    // PRESENT: Raw Kokoro samples are encoded into a small WAV container when a Blob helper is not available.
    // RATIONALE: This keeps the output panel dependable across kokoro-js runtime shapes without adding a server conversion step.
    return encodeWav(maybeAudio.audio, maybeAudio.sampling_rate ?? maybeAudio.sample_rate ?? 24000);
  }

  throw new Error("Kokoro returned audio in an unsupported format.");
}

function encodeWav(samples: Float32Array | number[], sampleRate: number) {
  const pcm = Float32Array.from(samples);
  const bytesPerSample = 2;
  const dataSize = pcm.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true);
  view.setUint16(32, bytesPerSample, true);
  view.setUint16(34, 8 * bytesPerSample, true);
  writeString(view, 36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (const sample of pcm) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += bytesPerSample;
  }

  return new Blob([view], { type: "audio/wav" });
}

function writeString(view: DataView, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
