
export function str(v) { return String(v ?? ""); }

export const ACTIONS = {
  "select-email": (api, a) => api.helpers.selectEmail(str(a.id)),
  "delete-email": (api, a) => api.fns.deleteEmail(str(a.id)),
  "new-matter": (api) => api.fns.addMatterBatch(),
  "sort-folders": (api) => api.fns.toggleFolderSort(),
  "draft-send": (api) => api.fns.sendClientDraft(),
  "toggle-folder": (api, a) => api.fns.toggleFolder(str(a.id)),
  "select-folder": (api, a) => api.fns.selectFolder(str(a.id)),
  "extract-zip": (api, a) => api.fns.extractZip(str(a.id)),
  "preview-name": (api, a) => api.fns.previewDocumentByName(str(a.name)),
  "preview-node": (api, a) => {
    const email = api.fns.activeEmail();
    const node = email && email.workspace.root ? api.fns.findNode(email.workspace.root, str(a.id)) : null;
    if (node) api.fns.previewDocumentByName(node.name);
  },
  "modal-close": (api) => api.fns.closeModal(),

  "reset-all": (api) => api.fns.resetAllCases(),
  "close-case": (api, a) => api.fns.closeCase(str(a.kind)),
  "caseflow-next": (api) => api.fns.caseflowNext(api.fns.activeEmail()),
  "stage-jump": (api, a) => api.fns.advanceSelectedMatter(str(a.value)),
};

export function handlerFor(type) {
  return ACTIONS[type] || null;
}
