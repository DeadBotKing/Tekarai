import type { IScannerControls } from "@zxing/browser";
import type { BarcodeFormat } from "@zxing/library";

/**
 * خواندن کد — دوربین به متن.
 *
 * Why two engines:
 *
 * * `BarcodeDetector` is a native, GPU-assisted decoder. Where it exists
 *   (Chrome/Android, Safari 17+) it is dramatically cheaper on battery than
 *   decoding frames in JavaScript — and a technician's phone is on battery
 *   all shift.
 * * It does **not** exist on Firefox, on older iOS Safari, or on desktop
 *   Safari before 17. The previous implementation stopped there and told the
 *   user «پشتیبانی نمی‌شود», which made scanning a Chrome-only feature.
 *
 * So: use the native decoder when it supports *every* symbology we print,
 * otherwise fall back to ZXing, which is bundled with the app (no CDN — the
 * scanner has to work in a basement with no network, which is exactly when
 * people scan). One interface, `ScannerHandle`, hides which engine won.
 *
 * The engine choice itself is a pure function, `chooseEngine`, so the
 * decision is unit-testable without a camera.
 *
 * ZXing is loaded with a dynamic `import()`, so its ~250 kB stays out of the
 * first paint. A technician on site waits for the login screen on a bad
 * connection far more often than they open the scanner, and the chunk is
 * cached by the service worker the first time either way.
 */

/** Symbologies we print and therefore must read. */
export const REQUIRED_FORMATS = [
  "qr_code",
  "code_128",
  "code_39",
  "ean_13",
  "ean_8",
  "itf",
  "data_matrix",
] as const;

export type Symbology = (typeof REQUIRED_FORMATS)[number] | "manual" | "unknown";

export type ScanEngine = "native" | "zxing";

/** Native decoder wins only if it reads everything we might print. */
export function chooseEngine(nativeFormats: readonly string[] | null): ScanEngine {
  if (!nativeFormats || nativeFormats.length === 0) return "zxing";
  const supported = new Set(nativeFormats.map((value) => value.toLowerCase()));
  return REQUIRED_FORMATS.every((format) => supported.has(format)) ? "native" : "zxing";
}

/** Built after the library loads — `BarcodeFormat` is a runtime enum. */
const zxingFormatNames = (
  formats: typeof BarcodeFormat,
): Partial<Record<number, Symbology>> => ({
  [formats.QR_CODE]: "qr_code",
  [formats.CODE_128]: "code_128",
  [formats.CODE_39]: "code_39",
  [formats.EAN_13]: "ean_13",
  [formats.EAN_8]: "ean_8",
  [formats.ITF]: "itf",
  [formats.DATA_MATRIX]: "data_matrix",
});

const zxingFormats = (formats: typeof BarcodeFormat): number[] => [
  formats.QR_CODE,
  formats.DATA_MATRIX,
  formats.CODE_128,
  formats.CODE_39,
  formats.EAN_13,
  formats.EAN_8,
  formats.UPC_A,
  formats.UPC_E,
  formats.ITF,
];

export interface BarcodeDetectorInstance {
  detect: (source: CanvasImageSource) => Promise<Array<{ rawValue: string; format?: string }>>;
}
export interface BarcodeDetectorConstructor {
  new (options?: { formats?: string[] }): BarcodeDetectorInstance;
  getSupportedFormats: () => Promise<string[]>;
}

export const nativeDetector = (): BarcodeDetectorConstructor | undefined =>
  typeof window === "undefined"
    ? undefined
    : (window as { BarcodeDetector?: BarcodeDetectorConstructor }).BarcodeDetector;

/**
 * Pull the decoder chunk into the cache while the device still has signal.
 *
 * Without this, a technician who opens the scanner for the first time in a
 * basement gets a dynamic import that cannot be fetched. Run on idle, after
 * the app is interactive, and ignore every failure.
 */
export function prefetchDecoder(): void {
  if (typeof window === "undefined") return;
  const load = (): void => {
    void import("@zxing/browser").catch(() => undefined);
  };
  const idle = (window as { requestIdleCallback?: (cb: () => void) => number })
    .requestIdleCallback;
  if (idle) idle(load);
  else window.setTimeout(load, 4000);
}

export interface ScannerHandle {
  engine: ScanEngine;
  /** True when the active camera track exposes a torch capability. */
  torchAvailable: boolean;
  setTorch: (on: boolean) => Promise<void>;
  stop: () => void;
}

export interface StartScannerOptions {
  video: HTMLVideoElement;
  /** `undefined` lets the browser pick; we ask for the rear camera. */
  deviceId?: string;
  onResult: (text: string, symbology: Symbology) => void;
  onError?: (error: unknown) => void;
}

export interface CameraOption {
  deviceId: string;
  label: string;
}

/** Cameras the browser will admit to, after permission has been granted. */
export async function listCameras(): Promise<CameraOption[]> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.enumerateDevices) return [];
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices
      .filter((device) => device.kind === "videoinput")
      .map((device, index) => ({
        deviceId: device.deviceId,
        label: device.label || `دوربین ${index + 1}`,
      }));
  } catch {
    return [];
  }
}

/** Prefer a rear/environment camera — labels are the only hint we get. */
export function preferredCamera(cameras: readonly CameraOption[]): string {
  const rear = cameras.find((camera) =>
    /back|rear|environment|پشت/i.test(camera.label),
  );
  return (rear ?? cameras[cameras.length - 1])?.deviceId ?? "";
}

const torchOf = (stream: MediaStream | null): MediaStreamTrack | null => {
  const track = stream?.getVideoTracks()[0] ?? null;
  if (!track) return null;
  const capabilities = (
    track.getCapabilities as (() => MediaTrackCapabilities & { torch?: boolean }) | undefined
  )?.call(track);
  return capabilities?.torch ? track : null;
};

const videoConstraints = (deviceId?: string): MediaStreamConstraints => ({
  video: deviceId
    ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
    : { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
  audio: false,
});

/**
 * Start decoding into `options.video`. Resolves once the camera is live;
 * rejects when permission is denied or no camera exists, so the caller can
 * fall back to manual entry instead of showing a dead black rectangle.
 */
export async function startScanner(options: StartScannerOptions): Promise<ScannerHandle> {
  const Detector = nativeDetector();
  let engine: ScanEngine = "zxing";
  if (Detector) {
    try {
      engine = chooseEngine(await Detector.getSupportedFormats());
    } catch {
      engine = "zxing";
    }
  }

  if (engine === "native" && Detector) {
    return startNative(Detector, options);
  }
  return startZxing(options);
}

async function startNative(
  Detector: BarcodeDetectorConstructor,
  { video, deviceId, onResult, onError }: StartScannerOptions,
): Promise<ScannerHandle> {
  const stream = await navigator.mediaDevices.getUserMedia(videoConstraints(deviceId));
  video.srcObject = stream;
  video.setAttribute("playsinline", "true");
  await video.play();

  const detector = new Detector({ formats: [...REQUIRED_FORMATS] });
  let stopped = false;
  let frame = 0;

  const tick = async (): Promise<void> => {
    if (stopped) return;
    try {
      const codes = await detector.detect(video);
      const first = codes[0];
      if (first?.rawValue) {
        onResult(String(first.rawValue), (first.format ?? "unknown") as Symbology);
      }
    } catch (error) {
      // A frame that cannot be decoded is the normal case, not an error;
      // only surface it if the caller asked for diagnostics.
      onError?.(error);
    }
    if (!stopped) frame = window.requestAnimationFrame(() => void tick());
  };
  void tick();

  const torchTrack = torchOf(stream);
  return {
    engine: "native",
    torchAvailable: Boolean(torchTrack),
    setTorch: async (on: boolean) => {
      await torchTrack?.applyConstraints({
        advanced: [{ torch: on } as MediaTrackConstraintSet],
      });
    },
    stop: () => {
      stopped = true;
      if (frame) window.cancelAnimationFrame(frame);
      stream.getTracks().forEach((track) => track.stop());
      video.srcObject = null;
    },
  };
}

async function startZxing({
  video,
  deviceId,
  onResult,
  onError,
}: StartScannerOptions): Promise<ScannerHandle> {
  const [{ BrowserMultiFormatReader }, { BarcodeFormat: formats, DecodeHintType }] =
    await Promise.all([import("@zxing/browser"), import("@zxing/library")]);

  const hints = new Map<number, unknown>();
  hints.set(DecodeHintType.POSSIBLE_FORMATS, zxingFormats(formats));
  // TRY_HARDER costs CPU but reads the scuffed, curved, half-lit labels that
  // live on real equipment. Worth it: a scan that fails is a trip back to
  // the office.
  hints.set(DecodeHintType.TRY_HARDER, true);

  const reader = new BrowserMultiFormatReader(hints as never, {
    delayBetweenScanAttempts: 120,
    delayBetweenScanSuccess: 900,
  });
  const names = zxingFormatNames(formats);

  let controls: IScannerControls | null = null;
  const stream = await navigator.mediaDevices.getUserMedia(videoConstraints(deviceId));
  video.setAttribute("playsinline", "true");
  controls = await reader.decodeFromStream(stream, video, (result, error) => {
    if (result) {
      onResult(result.getText(), names[result.getBarcodeFormat()] ?? "unknown");
      return;
    }
    if (error && error.name !== "NotFoundException") onError?.(error);
  });

  const torchTrack = torchOf(stream);
  return {
    engine: "zxing",
    torchAvailable: Boolean(torchTrack),
    setTorch: async (on: boolean) => {
      await torchTrack?.applyConstraints({
        advanced: [{ torch: on } as MediaTrackConstraintSet],
      });
    },
    stop: () => {
      controls?.stop();
      stream.getTracks().forEach((track) => track.stop());
      video.srcObject = null;
    },
  };
}
