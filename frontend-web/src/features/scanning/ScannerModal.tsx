import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "../../core/api/apiContext";
import { faText as t } from "../../core/localization/i18n";
import { useOptionalOffline } from "../../core/offline/offlineContext";
import { Modal } from "../../shared/components/overlays";
import { Badge, Button, TextInput } from "../../shared/components/primitives";
import { Icon } from "../../shared/components/Icon";
import { createFieldOpsService, type ScanResult } from "../maintenance/fieldOpsService";
import {
  listCameras,
  preferredCamera,
  startScanner,
  type CameraOption,
  type ScannerHandle,
  type Symbology,
} from "./codeScanner";
import { isResolvable, parseScan, scanTargetPath, type ScanKind } from "./scanCodes";

/**
 * مودال اسکن — one scanner for the whole maintenance module.
 *
 * Behaviour that the previous device-only modal did not have:
 *
 * * **It works in every browser.** The decoder is bundled (see
 *   `codeScanner.ts`), so Firefox and iOS Safari scan too.
 * * **It reads linear barcodes**, because asset tags printed before QR
 *   existed are Code 39/128 and nobody is re-labelling a refinery.
 * * **It resolves any target** — equipment, work order, spare part or
 *   location — through one server endpoint, so a technician scans whatever
 *   is in front of them instead of picking the right scanner first.
 * * **It still works offline** for QR deep links, which carry the target in
 *   the code itself. Business codes need the server, and the modal says so
 *   plainly rather than spinning.
 */

export interface ScannerModalProps {
  open: boolean;
  onClose: () => void;
  /**
   * Called with the resolved target. Return `true` to keep the modal open
   * (e.g. a page that collects several scans). When omitted, the modal
   * navigates to the target's page.
   */
  onResolved?: (result: ScanResult) => boolean | void;
  /** Limit what the caller will accept; others are reported as not found. */
  expect?: ScanKind;
  title?: string;
}

const kindLabel = (kind: string): string => {
  switch (kind) {
    case "device":
      return t("scan.kind.device");
    case "workOrder":
      return t("scan.kind.workOrder");
    case "sparePart":
      return t("scan.kind.sparePart");
    case "location":
      return t("scan.kind.location");
    default:
      return "";
  }
};

/** Short, non-intrusive feedback that a code was read. */
const confirmHaptics = (): void => {
  try {
    navigator.vibrate?.(60);
  } catch {
    /* vibration is a nicety, never a requirement */
  }
};

export function ScannerModal({
  open,
  onClose,
  onResolved,
  expect,
  title,
}: ScannerModalProps): JSX.Element {
  const navigate = useNavigate();
  const api = useApiClient();
  const offline = useOptionalOffline();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const handleRef = useRef<ScannerHandle | null>(null);
  const busyRef = useRef(false);
  const [manual, setManual] = useState("");
  const [message, setMessage] = useState("");
  const [engine, setEngine] = useState<"native" | "zxing" | "">("");
  const [cameras, setCameras] = useState<CameraOption[]>([]);
  const [cameraId, setCameraId] = useState("");
  const [torchOn, setTorchOn] = useState(false);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [live, setLive] = useState(false);
  const [resolving, setResolving] = useState(false);

  const isOnline = offline?.isOnline ?? true;

  const deliver = useCallback(
    (result: ScanResult): void => {
      confirmHaptics();
      const keepOpen = onResolved?.(result);
      if (onResolved && keepOpen !== true) onClose();
      if (!onResolved) {
        onClose();
        if (result.route) navigate(result.route);
      }
    },
    [navigate, onClose, onResolved],
  );

  /**
   * One scanned string → a target.
   *
   * Offline, a deep-link QR is enough on its own; a business code is not,
   * and pretending otherwise would send the technician to a blank page.
   */
  const handleCode = useCallback(
    async (text: string, symbology: Symbology): Promise<void> => {
      if (busyRef.current) return;
      const intent = parseScan(text);
      if (!isResolvable(intent)) {
        setMessage(t("scan.unknown"));
        return;
      }
      busyRef.current = true;
      setResolving(true);
      setMessage(t("scan.resolving"));
      try {
        if (!isOnline) {
          if (intent.kind && intent.id) {
            deliver({
              kind: intent.kind,
              id: intent.id,
              code: intent.code,
              title: "",
              subtitle: "",
              route: scanTargetPath(intent.kind, intent.id),
              status: "",
              symbology,
              scannedText: text,
            });
            setMessage(t("scan.offlineResolved"));
            return;
          }
          setMessage(t("scan.offlineUnresolvable"));
          return;
        }
        const service = createFieldOpsService(api);
        const result = await service.resolveScan(text, symbology);
        if (expect && result.kind !== expect) {
          setMessage(t("scan.notFound"));
          return;
        }
        deliver(result);
      } catch {
        setMessage(t("scan.notFound"));
      } finally {
        setResolving(false);
        // Let the camera settle before accepting the next frame, otherwise a
        // label still in view fires the same scan a dozen times.
        window.setTimeout(() => {
          busyRef.current = false;
        }, 1200);
      }
    },
    [api, deliver, expect, isOnline],
  );

  const stop = useCallback((): void => {
    handleRef.current?.stop();
    handleRef.current = null;
    setLive(false);
    setTorchOn(false);
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setMessage(t("scan.starting"));

    const begin = async (): Promise<void> => {
      const video = videoRef.current;
      if (!video) return;
      try {
        const handle = await startScanner({
          video,
          deviceId: cameraId || undefined,
          onResult: (text, symbology) => {
            void handleCode(text, symbology);
          },
        });
        if (cancelled) {
          handle.stop();
          return;
        }
        handleRef.current = handle;
        setEngine(handle.engine);
        setTorchAvailable(handle.torchAvailable);
        setLive(true);
        setMessage("");
        // Labels only become readable after permission is granted, so the
        // camera list is fetched here rather than on mount.
        const found = await listCameras();
        if (!cancelled && found.length > 0) {
          setCameras(found);
          if (!cameraId) setCameraId(preferredCamera(found));
        }
      } catch {
        if (!cancelled) {
          setLive(false);
          setMessage(t("scan.denied"));
        }
      }
    };
    void begin();

    return () => {
      cancelled = true;
      stop();
    };
  }, [cameraId, handleCode, open, stop]);

  useEffect(() => {
    if (!open) {
      setManual("");
      setMessage("");
      busyRef.current = false;
    }
  }, [open]);

  const switchCamera = (): void => {
    if (cameras.length < 2) return;
    const index = cameras.findIndex((camera) => camera.deviceId === cameraId);
    const next = cameras[(index + 1) % cameras.length];
    stop();
    setCameraId(next.deviceId);
  };

  const toggleTorch = async (): Promise<void> => {
    const handle = handleRef.current;
    if (!handle?.torchAvailable) return;
    const next = !torchOn;
    try {
      await handle.setTorch(next);
      setTorchOn(next);
    } catch {
      setTorchAvailable(false);
    }
  };

  return (
    <Modal
      open={open}
      title={title ?? t("scan.title")}
      onClose={onClose}
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t("common.close")}
        </Button>
      }
    >
      <div className="scan-panel" dir="rtl">
        <p className="muted-cell">{t("scan.subtitle")}</p>
        <div className={`scan-panel__camera ${live ? "" : "scan-panel__camera--idle"}`}>
          <video ref={videoRef} playsInline muted aria-label={t("scan.title")} />
          {live && <div className="scan-panel__reticle" aria-hidden="true" />}
          {!live && <p className="muted-cell">{t("scan.hintCamera")}</p>}
        </div>
        <div className="scan-panel__tools">
          {engine && (
            <Badge tone={engine === "native" ? "success" : "info"}>
              {engine === "native" ? t("scan.engineNative") : t("scan.engineZxing")}
            </Badge>
          )}
          {!isOnline && <Badge tone="warning">{t("offline.offline")}</Badge>}
          {torchAvailable && (
            <Button
              variant={torchOn ? "primary" : "secondary"}
              size="sm"
              onClick={() => void toggleTorch()}
            >
              <Icon name="sun" /> {t("scan.torch")}
            </Button>
          )}
          {cameras.length > 1 && (
            <Button variant="secondary" size="sm" onClick={switchCamera}>
              <Icon name="refresh" /> {t("scan.switchCamera")}
            </Button>
          )}
        </div>
        {message && (
          <p className={`scan-panel__message ${resolving ? "scan-panel__message--busy" : ""}`}>
            {message}
          </p>
        )}
        <form
          className="scan-panel__manual"
          onSubmit={(event) => {
            event.preventDefault();
            if (manual.trim()) void handleCode(manual.trim(), "manual");
          }}
        >
          <TextInput
            label={t("scan.manualLabel")}
            value={manual}
            onChange={(event) => setManual(event.target.value)}
            placeholder={t("scan.placeholder")}
            dir="ltr"
          />
          <Button variant="primary" size="sm" type="submit" disabled={!manual.trim()}>
            {t("scan.go")}
          </Button>
        </form>
      </div>
    </Modal>
  );
}

export { kindLabel };
