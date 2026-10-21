import { Icon, type IconName } from "./Icon";

type StickerTone = "blue" | "sage" | "sand";
export type ContextStickerKind =
  | "task"
  | "workOrder"
  | "corrective"
  | "preventive"
  | "inspection"
  | "maintenance"
  | "dashboard"
  | "guide"
  | "complete";
export type ContextStickerSize = "xs" | "sm" | "md";

const stickerLook: Record<ContextStickerKind, { icon: IconName; tone: StickerTone }> = {
  task: { icon: "checkSquare", tone: "blue" },
  workOrder: { icon: "briefcase", tone: "sage" },
  corrective: { icon: "activity", tone: "blue" },
  preventive: { icon: "calendar", tone: "sage" },
  inspection: { icon: "shield", tone: "sand" },
  maintenance: { icon: "cpu", tone: "sage" },
  dashboard: { icon: "grid", tone: "sage" },
  guide: { icon: "book", tone: "blue" },
  complete: { icon: "checkCircle", tone: "sage" },
};

export function ContextSticker({
  kind,
  size = "md",
  className = "",
}: {
  kind: ContextStickerKind;
  size?: ContextStickerSize;
  className?: string;
}): JSX.Element {
  const look = stickerLook[kind];
  const iconSize = size === "xs" ? 13 : size === "sm" ? 18 : 29;

  return (
    <span
      className={`context-sticker context-sticker--${look.tone} context-sticker--${size} ${className}`.trim()}
      aria-hidden="true"
    >
      <span className="context-sticker__paper"><Icon name={look.icon} size={iconSize} /></span>
      {size === "md" && (
        <>
          <span className="context-sticker__spark"><Icon name="sparkles" size={13} /></span>
          <span className="context-sticker__dot" />
        </>
      )}
    </span>
  );
}
