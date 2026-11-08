import { organizationBranding } from '../../app/configuration/organizationBranding';
import './OrganizationBrand.css';

/** The organization's supplied artwork, distinct from the Tekarai product logo. */
export function OrganizationBrand({ appearance }: { appearance?: { displayName: string; logoData: string } } = {}): JSX.Element {
  const name = appearance?.displayName ?? organizationBranding.name;
  const logo = appearance ? appearance.logoData : organizationBranding.logoSrc;
  return <span className="organization-brand" aria-label={name}>
    {logo && <img src={logo} alt={`لوگوی ${name}`} width={118} height={32}
      draggable={false} onContextMenu={(event) => event.preventDefault()} onDragStart={(event) => event.preventDefault()} />}
    <strong>{name}</strong>
  </span>;
}
