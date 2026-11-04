import "./BrandLogo.css";

/** Approved cursive TK + gear identity. A light plate keeps it legible on the green rail. */
export function BrandLogo({ large = false }: { large?: boolean }): JSX.Element {
  return <span className={`brand-mark tekarai-logo${large ? " tekarai-logo--large" : ""}`}
    onContextMenu={(event) => event.preventDefault()}
    onDragStart={(event) => event.preventDefault()}>
    <img src="/branding/tk-gear-logo.png" alt="لوگوی تکارای" width={large ? 84 : 52} height={large ? 60 : 38} draggable={false} />
  </span>;
}
