import {
  useState, useEffect, useCallback, useMemo, useRef,
  Card, Button, Table, Form, Input, InputNumber, Select,
  Upload, Tag, Space, message, Spin, Popconfirm, Alert, Typography, Row, Col,
  Modal, Divider, ConfigProvider, Tree, Progress, List, Badge, Popover,
  Menu, Radio, Drawer, Tooltip, Tabs,
  Dragger, Option, Title, Text, Password,
  APP_LOCALE, APP_THEME,
} from '../globals.js';

const ICON_PATHS = {
  bolt: <><path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" fill="currentColor" /></>,
  upload: <><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" strokeWidth="1.5" fill="none" /><path d="M14 2v6h6M12 18v-6M9 15l3-3 3 3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" /></>,
  check: <><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" fill="none" /><path d="M8 12l2.5 2.5L16 9" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" /></>,
  facts: <><rect x="4" y="3" width="16" height="18" rx="2" stroke="currentColor" strokeWidth="1.5" fill="none" /><path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></>,
  outline: <><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></>,
  generate: <><path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" fill="currentColor" /></>,
  preview: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" stroke="currentColor" strokeWidth="1.5" fill="none" /><circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" fill="none" /></>,
  clipboard: <><rect x="6" y="4" width="12" height="16" rx="2" stroke="currentColor" strokeWidth="1.5" fill="none" /><path d="M9 4V3a1 1 0 011-1h4a1 1 0 011 1v1" stroke="currentColor" strokeWidth="1.5" fill="none" /></>,
  warning: <><path d="M12 3L2 20h20L12 3z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" /><path d="M12 10v4M12 17h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></>,
  success: <><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" fill="none" /><path d="M8 12l2.5 2.5L16 9" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" /></>,
  error: <><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" fill="none" /><path d="M9 9l6 6M15 9l-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></>,
  loading: <><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" fill="none" strokeDasharray="28 10" /></>,
  pending: <><circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.5" fill="none" /></>,
  chevronUp: <><path d="M6 14l6-6 6 6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" /></>,
  chevronDown: <><path d="M6 10l6 6 6-6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" /></>,
  list: <><rect x="5" y="4" width="14" height="16" rx="2" stroke="currentColor" strokeWidth="1.5" fill="none" /><path d="M9 9h6M9 13h6M9 17h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></>,
  settings: <><circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" fill="none" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></>,
};

function Icon({ name, size = 16, className, style }) {
  const content = ICON_PATHS[name];
  if (!content) return null;
  return (
    <svg
      className={className}
      style={style}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      {content}
    </svg>
  );
}

function ChapterStatusIcon({ status }) {
  const map = {
    green: { name: 'success', cls: 'status-dot--green' },
    yellow: { name: 'warning', cls: 'status-dot--yellow' },
    red: { name: 'error', cls: 'status-dot--red' },
    generating: { name: 'loading', cls: 'status-dot--generating' },
  };
  const item = map[status] || { name: 'pending', cls: 'status-dot--pending' };
  return (
    <span className={`status-dot ${item.cls}`}>
      <Icon name={item.name} size={16} />
    </span>
  );
}
export { Icon, ChapterStatusIcon, ICON_PATHS };
