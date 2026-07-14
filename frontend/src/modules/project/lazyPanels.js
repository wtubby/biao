import { lazy } from '../../globals.js';

function named(importFn, exportName) {
  return lazy(() => importFn().then((m) => ({ default: m[exportName] })));
}

const TenderDetailPanel = named(() => import('../confirm/TenderDetailPanel.jsx'), 'TenderDetailPanel');
const OutlineEditor = named(() => import('../outline/OutlineEditor.jsx'), 'OutlineEditor');
const GenerationPanel = named(() => import('../generation/GenerationPanel.jsx'), 'GenerationPanel');
const PreviewExport = named(() => import('../export/PreviewExport.jsx'), 'PreviewExport');
const SourcePreviewPane = named(() => import('../parse/SourcePreviewPane.jsx'), 'SourcePreviewPane');
const ParseProgressPanel = named(() => import('../parse/ParseProgressPanel.jsx'), 'ParseProgressPanel');

export {
  TenderDetailPanel,
  OutlineEditor,
  GenerationPanel,
  PreviewExport,
  SourcePreviewPane,
  ParseProgressPanel,
};
