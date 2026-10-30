/** Official Umi access hook; no demo role check or localStorage authorization. */
export default function access(initialState: { permissions?: string[] } | undefined) {
  const permissions = new Set(initialState?.permissions ?? []);
  return {
    canReadOverview:permissions.has('overview:read'), canReadUsers:permissions.has('users:read'),
    canReadMemberships:permissions.has('memberships:read'),canReadJobs:permissions.has('jobs:read'),
    canReadBilling:permissions.has('billing:read'),canReadAudit:permissions.has('audit:read'),canReadSystem:permissions.has('system:read'),
    canReadSupport:permissions.has('support:read'),
    canReadAdvanced:permissions.has('audit:read')||permissions.has('system:read'),
  };
}
