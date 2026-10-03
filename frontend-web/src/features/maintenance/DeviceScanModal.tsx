import { useNavigate } from "react-router-dom";
import { faText as t } from "../../core/localization/i18n";
import { ScannerModal } from "../scanning/ScannerModal";
import { deviceProfilePath } from "./deviceQr";

/**
 * اسکن تجهیز — the equipment-register entry point.
 *
 * Kept as a named component because the devices page (and its tests) know
 * it, but the implementation is now the shared `ScannerModal`: same bundled
 * decoder, same barcode support, restricted to equipment so that scanning a
 * work order here does not silently navigate somewhere unexpected.
 */
export function DeviceScanModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}): JSX.Element {
  const navigate = useNavigate();
  return (
    <ScannerModal
      open={open}
      onClose={onClose}
      expect="device"
      title={t("registry.scan.title")}
      onResolved={(result) => {
        navigate(result.route || deviceProfilePath(result.id));
      }}
    />
  );
}
