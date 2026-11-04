import { organizationBranding } from '../../app/configuration/organizationBranding';
import './OrganizationBrand.css';

/** The organization's supplied artwork, distinct from the Tekarai product logo. */
export function OrganizationBrand(): JSX.Element {
  return <span className="organization-brand" aria-label={organizationBranding.name}>
    <img src={organizationBranding.logoSrc} alt={`لوگوی ${organizationBranding.name}`} width={118} height={32}
      draggable={false} onContextMenu={(event) => event.preventDefault()} onDragStart={(event) => event.preventDefault()} />
    <strong>{organizationBranding.name}</strong>
  </span>;
}
