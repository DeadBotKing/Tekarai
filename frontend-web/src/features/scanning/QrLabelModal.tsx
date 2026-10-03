import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import { faText as t } from "../../core/localization/i18n";
import { Modal } from "../../shared/components/overlays";
import { Button } from "../../shared/components/primitives";
import { scanQrPayload, type ScanKind } from "./scanCodes";

/**
 * برچسب QR — printable label for any scannable target.
 *
 * The device profile already had one; work orders had none, which is why a
 * technician could not scan the paper order in their hand to open it. This
 * component is deliberately generic: a kind, an id, a caption.
 *
 * Error correction is set to `M` and the module size kept large, because
 * these labels end up oily, scratched and photographed at an angle.
 */
export function QrLabelModal({
  open,
  onClose,
  kind,
  targetId,
  title,
  caption,
  subtitle,
}: {
  open: boolean;
  onClose: () => void;
  kind: ScanKind;
  targetId: string;
  title?: string;
  caption: string;
  subtitle?: string;
}): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [payload, setPayload] = useState("");

  useEffect(() => {
    if (!open || !targetId) return;
    const value = scanQrPayload(kind, targetId);
    setPayload(value);
    const canvas = canvasRef.current;
    if (!canvas) return;
    void QRCode.toCanvas(canvas, value, {
      width: 240,
      margin: 1,
      errorCorrectionLevel: "M",
      color: { dark: "#0f172a", light: "#ffffff" },
    });
  }, [kind, open, targetId]);

  const print = (): void => {
    document.body.classList.add("printing-qr-label");
    window.print();
    window.setTimeout(() => document.body.classList.remove("printing-qr-label"), 200);
  };

  const download = (): void => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const link = document.createElement("a");
    link.download = `tekarai-${kind}-${targetId}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  };

  return (
    <Modal
      open={open}
      title={title ?? t("qr.title")}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.close")}
          </Button>
          <Button variant="secondary" onClick={download}>
            {t("qr.download")}
          </Button>
          <Button variant="primary" onClick={print}>
            {t("qr.print")}
          </Button>
        </>
      }
    >
      <div className="qr-label-wrap" dir="rtl">
        <div className="qr-label">
          <div className="qr-label__head">
            <strong>{caption}</strong>
            {subtitle && <span>{subtitle}</span>}
          </div>
          <canvas ref={canvasRef} className="qr-label__canvas" aria-label={t("qr.title")} />
          <small dir="ltr">{payload}</small>
        </div>
        <p className="muted-cell">{t("qr.hint")}</p>
      </div>
    </Modal>
  );
}
