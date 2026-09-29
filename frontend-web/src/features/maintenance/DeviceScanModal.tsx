import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { faText as t } from "../../core/localization/i18n";
import { Modal } from "../../shared/components/overlays";
import { Button, TextInput } from "../../shared/components/primitives";
import { deviceProfilePath, parseDeviceScan } from "./deviceQr";

/** ظرفیت BarcodeDetector هنوز در lib.dom تایپ‌اسکریپت نیست — حداقال امضا. */
interface BarcodeDetectorInstance {
  detect: (source: CanvasImageSource) => Promise<Array<{ rawValue: string }>>;
}
interface BarcodeDetectorConstructor {
  new (options?: { formats?: string[] }): BarcodeDetectorInstance;
  getSupportedFormats: () => Promise<string[]>;
}
const barcodeDetectorOf = (): BarcodeDetectorConstructor | undefined =>
  (window as { BarcodeDetector?: BarcodeDetectorConstructor }).BarcodeDetector;

export function DeviceScanModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}): JSX.Element {
  const navigate = useNavigate();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [manual, setManual] = useState("");
  const [message, setMessage] = useState("");
  const [cameraActive, setCameraActive] = useState(false);

  const go = (text: string, closeOnSuccess = true): boolean => {
    const deviceId = parseDeviceScan(text);
    if (!deviceId) {
      setMessage(t("registry.scan.invalid"));
      return false;
    }
    if (closeOnSuccess) onClose();
    navigate(deviceProfilePath(deviceId));
    return true;
  };

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    let stream: MediaStream | null = null;
    let frame = 0;

    const stopAll = (): void => {
      if (frame) window.cancelAnimationFrame(frame);
      stream?.getTracks().forEach((track) => track.stop());
    };

    const start = async (): Promise<void> => {
      const Detector = barcodeDetectorOf();
      if (typeof Detector !== "function") {
        setMessage(t("registry.scan.unsupported"));
        return;
      }
      try {
        const formats = await Detector.getSupportedFormats();
        if (!formats.includes("qr_code")) {
          setMessage(t("registry.scan.unsupported"));
          return;
        }
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
        });
        if (cancelled) {
          stopAll();
          return;
        }
        const video = videoRef.current;
        if (!video) return;
        video.srcObject = stream;
        await video.play();
        setCameraActive(true);
        const detector = new Detector({ formats: ["qr_code"] });
        const tick = async (): Promise<void> => {
          if (cancelled) return;
          try {
            const codes = await detector.detect(video);
            if (codes.length > 0 && go(String(codes[0].rawValue))) {
              cancelled = true;
              stopAll();
              return;
            }
          } catch {
            /* خواندن هر فریم می‌تواند بی‌نتیجه بماند؛ فریم بعدی */
          }
          frame = window.requestAnimationFrame(() => void tick());
        };
        void tick();
      } catch {
        // دوربین در دسترس نیست یا مجوز رد شد — ورود دستی پایین همان مودال می‌ماند.
        setMessage(t("registry.scan.unsupported"));
      }
    };
    void start();

    return () => {
      cancelled = true;
      stopAll();
      setCameraActive(false);
      setMessage("");
      setManual("");
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <Modal
      open={open}
      title={t("registry.scan.title")}
      onClose={onClose}
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t("common.close")}
        </Button>
      }
    >
      <div className="scan-panel" dir="rtl">
        <div className={`scan-panel__camera ${cameraActive ? "" : "scan-panel__camera--idle"}`}>
          <video ref={videoRef} playsInline muted aria-label={t("registry.scan.title")} />
          {!cameraActive && <p className="muted-cell">{t("registry.scan.hintCamera")}</p>}
        </div>
        {message && <p className="scan-panel__message">{message}</p>}
        <form
          className="scan-panel__manual"
          onSubmit={(event) => {
            event.preventDefault();
            go(manual);
          }}
        >
          <TextInput
            label={t("registry.scan.manualLabel")}
            value={manual}
            onChange={(event) => setManual(event.target.value)}
            placeholder={t("registry.scan.placeholder")}
            dir="ltr"
          />
          <Button variant="primary" size="sm" type="submit" disabled={!manual.trim()}>
            {t("registry.scan.go")}
          </Button>
        </form>
      </div>
    </Modal>
  );
}
