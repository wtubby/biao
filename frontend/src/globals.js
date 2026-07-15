const { useState, useEffect, useCallback, useMemo, useRef, useImperativeHandle, forwardRef, lazy, Suspense } = React;
const {
  Card, Button, Table, Form, Input, InputNumber, Select,
  Upload, Tag, Space, message, Spin, Popconfirm, Alert, Typography, Row, Col,
  Modal, Divider, ConfigProvider, Tree, Progress, List, Badge, Popover,
  Menu, Radio, Drawer, Tooltip, Tabs, Dropdown, Slider, Switch, Checkbox,
} = antd;
const { Dragger } = Upload;
const { Option } = Select;
const { Title, Text } = Typography;
const { Password } = Input;
const APP_LOCALE = (antd.locales && antd.locales.zh_CN) || undefined;
const APP_THEME = {
  token: {
    colorPrimary: '#2563eb',
    colorPrimaryHover: '#1d4ed8',
    colorSuccess: '#16a34a',
    colorError: '#dc2626',
    colorWarning: '#f97316',
    colorInfo: '#2563eb',
    colorText: '#0f172a',
    colorTextSecondary: '#64748b',
    colorBorder: '#cbd5e1',
    colorBgContainer: '#ffffff',
    colorBgLayout: '#f8fafc',
    borderRadius: 8,
    borderRadiusLG: 12,
    borderRadiusSM: 6,
    controlHeight: 34,
    fontFamily: "'Plus Jakarta Sans', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    fontSize: 14,
  },
  components: {
    Button: {
      primaryShadow: '0 1px 2px rgba(37, 99, 235, 0.2)',
      fontWeight: 600,
    },
    Menu: {
      itemBg: 'transparent',
      subMenuItemBg: 'transparent',
      itemSelectedBg: 'rgba(37, 99, 235, 0.12)',
      itemHoverBg: 'rgba(255, 255, 255, 0.45)',
      itemSelectedColor: '#2563eb',
      itemColor: '#1e3a5f',
      darkItemBg: 'transparent',
      darkSubMenuItemBg: 'transparent',
      darkItemSelectedBg: 'rgba(37, 99, 235, 0.12)',
      darkItemHoverBg: 'rgba(255, 255, 255, 0.45)',
      itemBorderRadius: 6,
      itemMarginInline: 0,
    },
    Table: {
      headerBg: '#e9eef5',
      headerColor: '#1e3a5f',
      rowHoverBg: '#eff6ff',
      borderColor: '#cbd5e1',
    },
  },
};
export {
  useState, useEffect, useCallback, useMemo, useRef, useImperativeHandle, forwardRef, lazy, Suspense,
  Card, Button, Table, Form, Input, InputNumber, Select,
  Upload, Tag, Space, message, Spin, Popconfirm, Alert, Typography, Row, Col,
  Modal, Divider, ConfigProvider, Tree, Progress, List, Badge, Popover,
  Menu, Radio, Drawer, Tooltip, Tabs, Dropdown, Slider, Switch, Checkbox,
  Dragger, Option, Title, Text, Password,
  APP_LOCALE, APP_THEME,
};
