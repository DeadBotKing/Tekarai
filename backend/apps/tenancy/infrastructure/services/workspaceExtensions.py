"""Developer-owned registry. Never accept Python/JS/URLs uploaded through the panel.

Add an installed extension here, implement its APIs with normal permissions and
same-tenant checks, and register its React component in workspaceExtensions.tsx.
Example metadata (not an installed capability):
{'code':'laboratory','label':'آزمایشگاه','route':'/app/extensions/laboratory',
 'actionPrefixes':['extension.laboratory.'],'apiPrefixes':['extensions/laboratory'],
 'permissions':['extension.laboratory.view'],'requires':[]}
"""
EXTENSIONS = ()
