/** Display-only deployment branding; does not change tenant IDs, users or permissions.
 * For a future deployment, set its branding/code here. Set singleOrganization=false
 * to restore the existing tenant field and selector without removing multi-tenancy.
 */
export const organizationBranding = {
  singleOrganization: true,
  defaultTenantCode: 'platform',
  name: 'داروسازی روناک',
  logoSrc: '/branding/ronak.jpg',
} as const;
