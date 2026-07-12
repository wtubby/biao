import {
  useState, useEffect, useCallback, useMemo, useRef,
  Card, Button, Table, Form, Input, InputNumber, Select,
  Upload, Tag, Space, message, Spin, Popconfirm, Alert, Typography, Row, Col,
  Modal, Divider, ConfigProvider, Tree, Progress, List, Badge, Popover,
  Menu, Radio, Drawer, Tooltip, Tabs,
  Dragger, Option, Title, Text, Password,
  APP_LOCALE, APP_THEME,
} from '../globals.js';

function MetricCard({ label, value, sub, accent = 'blue' }) {
  return (
    <div className={`metric-card metric-card--${accent}`}>
      <div className="metric-card-value">{value}</div>
      <div className="metric-card-label">{label}</div>
      {sub && <div className="metric-card-sub">{sub}</div>}
    </div>
  );
}
export { MetricCard };
