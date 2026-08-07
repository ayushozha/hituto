import { DeepgramClient } from "@deepgram/sdk";

type SpeakSocket = Awaited<ReturnType<DeepgramClient["speak"]["v1"]["connect"]>>;
type ListenSocket = Awaited<ReturnType<DeepgramClient["listen"]["v2"]["connect"]>>;

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export class DeepgramSpeech {
  private socket: SpeakSocket | undefined;
  private context: AudioContext | undefined;
  private nextAudioTime = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private decodeChain: Promise<void> = Promise.resolve();
  private flushedResolve: (() => void) | undefined;
  private generation = 0;

  async prewarm(): Promise<void> {
    this.context ??= new AudioContext({ sampleRate: 24_000 });
    if (this.context.state === "suspended") await this.context.resume();
  }

  async connect(token: string, model: string): Promise<void> {
    await this.prewarm();
    if (this.socket) return;
    const client = new DeepgramClient({ accessToken: token });
    const socket = await client.speak.v1.connect({
      Authorization: `Bearer ${token}`,
      model: model as never,
      encoding: "linear16",
      sample_rate: "24000",
      reconnectAttempts: 2,
    });
    socket.on("message", (message) => this.handleMessage(message as unknown));
    socket.on("error", (error) => this.flushedResolve?.());
    socket.on("close", () => {
      if (this.socket === socket) this.socket = undefined;
      this.flushedResolve?.();
      this.flushedResolve = undefined;
    });
    socket.connect();
    await socket.waitForOpen();
    this.socket = socket;
  }

  isConnected(): boolean {
    return Boolean(this.socket && this.socket.readyState === 1);
  }

  async speak(text: string): Promise<void> {
    const socket = this.socket;
    if (!socket) return;
    await this.prewarm();
    const generation = ++this.generation;
    const flushed = new Promise<void>((resolve) => {
      this.flushedResolve = resolve;
    });
    socket.sendText({ type: "Speak", text });
    socket.sendFlush({ type: "Flush" });
    await flushed;
    await this.decodeChain;
    if (generation !== this.generation || !this.context) return;
    const remaining = Math.max(0, this.nextAudioTime - this.context.currentTime);
    await sleep(remaining * 1000 + 30);
  }

  interrupt(): void {
    this.generation += 1;
    this.flushedResolve?.();
    this.flushedResolve = undefined;
    if (this.socket) {
      try {
        this.socket.sendClear({ type: "Clear" });
      } catch {
        // The socket may already be reconnecting. Local audio still stops below.
      }
    }
    for (const source of this.sources) {
      try {
        source.stop();
      } catch {
        // A source that already ended is harmless.
      }
    }
    this.sources.clear();
    this.nextAudioTime = this.context?.currentTime ?? 0;
  }

  async pause(): Promise<void> {
    await this.context?.suspend();
  }

  async resume(): Promise<void> {
    await this.context?.resume();
  }

  close(): void {
    this.interrupt();
    this.socket?.close();
    this.socket = undefined;
    void this.context?.close();
    this.context = undefined;
  }

  private handleMessage(message: unknown): void {
    if (message instanceof Blob || message instanceof ArrayBuffer) {
      this.decodeChain = this.decodeChain.then(async () => {
        const bytes = message instanceof Blob ? await message.arrayBuffer() : message;
        this.schedulePcm(bytes);
      });
      return;
    }
    if (typeof message === "object" && message !== null && "type" in message) {
      const type = String((message as { type: unknown }).type);
      if (type === "Flushed") {
        this.flushedResolve?.();
        this.flushedResolve = undefined;
      }
    }
  }

  private schedulePcm(bytes: ArrayBuffer): void {
    const context = this.context;
    if (!context || bytes.byteLength < 2) return;
    const samples = new Int16Array(bytes.slice(0, bytes.byteLength - (bytes.byteLength % 2)));
    const audioBuffer = context.createBuffer(1, samples.length, 24_000);
    const channel = audioBuffer.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) channel[index] = samples[index] / 32_768;
    const source = context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(context.destination);
    source.onended = () => this.sources.delete(source);
    const startAt = Math.max(context.currentTime + 0.025, this.nextAudioTime);
    this.nextAudioTime = startAt + audioBuffer.duration;
    this.sources.add(source);
    source.start(startAt);
  }
}

interface ListenerCallbacks {
  onSpeechStart: () => void;
  onTranscript: (transcript: string, final: boolean) => void;
  onError: (message: string) => void;
}

export class DeepgramListener {
  private socket: ListenSocket | undefined;
  private recorder: MediaRecorder | undefined;
  private stream: MediaStream | undefined;

  async start(token: string, callbacks: ListenerCallbacks): Promise<void> {
    if (this.socket) return;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const mimeType = ["audio/webm;codecs=opus", "audio/webm"]
        .find((candidate) => MediaRecorder.isTypeSupported(candidate));
      if (!mimeType) throw new Error("This browser cannot record WebM Opus audio for live transcription.");

      const client = new DeepgramClient({ accessToken: token });
      const socket = await client.listen.v2.connect({
        Authorization: `Bearer ${token}`,
        model: "flux-general-en",
        eot_threshold: 0.72,
        eot_timeout_ms: 1_600,
        numerals: "true",
        keyterm: ["SAT", "quadratic", "coefficient", "hypotenuse", "semicolon"],
        reconnectAttempts: 2,
      });
      socket.on("message", (message) => {
        if (message.type !== "TurnInfo") return;
        if (message.event === "StartOfTurn") callbacks.onSpeechStart();
        if (message.transcript) callbacks.onTranscript(message.transcript, message.event === "EndOfTurn");
      });
      socket.on("error", (error) => callbacks.onError(error.message));
      socket.connect();
      await socket.waitForOpen();
      this.socket = socket;

      this.recorder = new MediaRecorder(this.stream, { mimeType });
      this.recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size > 0 && this.socket) this.socket.sendMedia(event.data);
      });
      this.recorder.start(80);
    } catch (error) {
      this.stop();
      throw error;
    }
  }

  stop(): void {
    if (this.recorder?.state !== "inactive") this.recorder?.stop();
    this.recorder = undefined;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = undefined;
    if (this.socket) {
      try {
        this.socket.sendCloseStream({ type: "CloseStream" });
      } catch {
        // Closing a failed connection is best-effort.
      }
      this.socket.close();
      this.socket = undefined;
    }
  }
}
