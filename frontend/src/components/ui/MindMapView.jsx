import React from 'react';

export function mindmapMarkdown(root, depth = 0) {
  if (!root) return '';
  // Export labels literally in a list, without allowing multiline Markdown structure.
  const label = String(root.label || '').replace(/[\r\n]+/g, ' ').replace(/([\\`*_{}\[\]<>#!|~])/g, '\\$1');
  return [`${'  '.repeat(depth)}- ${label}`, ...(root.children || []).map((child) => mindmapMarkdown(child, depth + 1))].join('\n');
}

function MindMapNode({ node }) {
  return <li>{node.children?.length
    ? <details open><summary>{node.label}</summary><ul>{node.children.map((child, index) => <MindMapNode key={index} node={child} />)}</ul></details>
    : <span className="mindmap-view__leaf">{node.label}</span>}</li>;
}

export default function MindMapView({ root }) {
  return <div className="mindmap-view" aria-label="思维导图主题结构"><ul><MindMapNode node={root} /></ul></div>;
}
