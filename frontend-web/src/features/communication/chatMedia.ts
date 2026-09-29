// ابزارهای رسانه‌ی چت — آماده‌سازی عکس (کوچک‌سازی برای دمو) و ضبط پیام صوتی.
// الگوی ذخیره: حالت زنده = آپلود به MEDIA بک‌اند؛ حالت دمو = dataURL در بدنه‌ی پیام.

export interface PreparedImage {
  dataUrl: string;
  sizeBytes: number;
  width: number;
  height: number;
}

/** خواندن فایل به dataURL */
export const blobToDataUrl = (blob: Blob): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });

/** کوچک‌سازی عکس روی canvas تا حجمش برای حالت دمو (localStorage) منطقی بماند */
export const prepareImage = async (file: File, maxDim = 1280, quality = 0.82): Promise<PreparedImage> => {
  const sourceUrl = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const element = new Image();
      element.onload = () => resolve(element);
      element.onerror = () => reject(new Error("image-decode"));
      element.src = sourceUrl;
    });
    const scale = Math.min(1, maxDim / Math.max(image.width, image.height));
    const width = Math.max(1, Math.round(image.width * scale));
    const height = Math.max(1, Math.round(image.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("canvas-unavailable");
    context.drawImage(image, 0, 0, width, height);
    const dataUrl = canvas.toDataURL("image/jpeg", quality);
    const base64Length = dataUrl.length - dataUrl.indexOf(",") - 1;
    return { dataUrl, sizeBytes: Math.round((base64Length * 3) / 4), width, height };
  } finally {
    URL.revokeObjectURL(sourceUrl);
  }
};

export interface VoiceRecording {
  blob: Blob;
  mimeType: string;
  seconds: number;
}

/** ضبط‌کننده‌ی ویس با MediaRecorder — start/stop و خروجی Blob */
export class VoiceRecorder {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private startedAt = 0;

  static isSupported(): boolean {
    return typeof MediaRecorder !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);
  }

  async start(): Promise<void> {
    if (!VoiceRecorder.isSupported()) throw new Error("recorder-unsupported");
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", ""];
    const mimeType = candidates.find((candidate) => candidate === "" || MediaRecorder.isTypeSupported(candidate)) ?? "";
    this.recorder = mimeType ? new MediaRecorder(this.stream, { mimeType }) : new MediaRecorder(this.stream);
    this.chunks = [];
    this.recorder.ondataavailable = (event) => {
      if (event.data.size > 0) this.chunks.push(event.data);
    };
    this.startedAt = Date.now();
    this.recorder.start(200);
  }

  /** توقف و برگرداندن نتیجه — استریم میکروفون در هر دو مسیر آزاد می‌شود */
  stop(): Promise<VoiceRecording> {
    return new Promise((resolve, reject) => {
      if (!this.recorder) {
        reject(new Error("recorder-not-started"));
        return;
      }
      const recorder = this.recorder;
      recorder.onstop = () => {
        this.release();
        const mimeType = recorder.mimeType || "audio/webm";
        resolve({
          blob: new Blob(this.chunks, { type: mimeType }),
          mimeType,
          seconds: Math.max(1, Math.round((Date.now() - this.startedAt) / 1000)),
        });
      };
      recorder.onerror = () => {
        this.release();
        reject(new Error("recorder-failed"));
      };
      recorder.stop();
    });
  }

  cancel(): void {
    try {
      this.recorder?.stop();
    } catch {
      // ignore — release happens below regardless
    }
    this.chunks = [];
    this.release();
  }

  private release(): void {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.recorder = null;
  }
}

/** تبدیل Blob به File برای مسیر آپلود زنده */
export const blobToFile = (blob: Blob, fileName: string, mimeType: string): File =>
  new File([blob], fileName, { type: mimeType });

export const formatClock = (totalSeconds: number): string => {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
};
