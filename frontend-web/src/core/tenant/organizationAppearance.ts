import { useEffect, useState } from 'react';
import { useApiClient } from '../api/apiContext';
import { useAuth } from '../auth/authContext';
import { organizationBranding } from '../../app/configuration/organizationBranding';

export interface RuntimeAppearance { tenantCode?: string; displayName: string; logoData: string; primaryColor: string; theme: string; revision: number }
export function useOrganizationAppearance(code?: string, enabled = true): RuntimeAppearance {
  const api = useApiClient();
  const { session } = useAuth();
  const fallback = { displayName: organizationBranding.name as string, logoData: organizationBranding.logoSrc as string, primaryColor:'#214d3d',theme:'warm',revision:0 };
  const [appearance, setAppearance] = useState<RuntimeAppearance>(fallback);
  useEffect(() => {
    let active = true;
    const load = () => {
      if (!enabled) return;
      const path = session && !code ? 'organization-appearance/current' : `organization-appearance/${encodeURIComponent(code || 'platform')}`;
      api.get<RuntimeAppearance | null>(path, {retry:0}).then(value => {
        if (active && value?.displayName && /^#[0-9a-f]{6}$/i.test(value.primaryColor)) {
          setAppearance({...value,logoData:value.logoData || (value.tenantCode === 'platform' && value.revision === 0 ? organizationBranding.logoSrc : '')});
        }
      }).catch(() => {});
    };
    setAppearance(fallback);load();
    window.addEventListener('tekarai:appearance-updated', load);
    return () => {active=false;window.removeEventListener('tekarai:appearance-updated',load);};
  }, [api, session?.user.id, code, enabled]);
  return appearance;
}

export function useOrganizationTheme(appearance: RuntimeAppearance, enabled = true): void {
  useEffect(() => {
    if (!enabled) return;
    const root = document.documentElement;
    const names = ['--primary','--primary-strong','--primary-soft','--primary-rgb','--info'];
    const before = names.map(name => root.style.getPropertyValue(name));
    const oldTheme = root.dataset.orgTheme;
    const color = appearance.primaryColor;
    const rgb = [1,3,5].map(i => parseInt(color.slice(i,i+2),16));
    const dark = '#' + rgb.map(n => Math.round(n * .8).toString(16).padStart(2,'0')).join('');
    root.style.setProperty('--primary',color);root.style.setProperty('--primary-strong',dark);
    root.style.setProperty('--primary-soft',color+'18');root.style.setProperty('--primary-rgb',rgb.join(' '));
    root.style.setProperty('--info',color);root.dataset.orgTheme=appearance.theme;
    return () => { names.forEach((name,index) => before[index] ? root.style.setProperty(name,before[index]) : root.style.removeProperty(name)); if(oldTheme) root.dataset.orgTheme=oldTheme;else delete root.dataset.orgTheme; };
  }, [appearance.primaryColor,appearance.theme,enabled]);
}
