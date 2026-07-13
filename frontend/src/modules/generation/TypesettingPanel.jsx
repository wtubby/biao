import {
  Select, Checkbox, InputNumber, Button, Text,
} from '../../globals.js';

function AlignButtons({ value, disabled, onChange }) {
  const options = [
    { value: 'left', label: '左对齐' },
    { value: 'center', label: '居中' },
    { value: 'right', label: '右对齐' },
  ];
  return (
    <div className="typesetting-align-group">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          className={`typesetting-align-btn${value === opt.value ? ' is-active' : ''}`}
          disabled={disabled}
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function TypesettingPanel({
  typesetting,
  options,
  disabled = false,
  saving = false,
  onChange,
  onReset,
}) {
  if (!typesetting || !options) return null;

  const levels = options.levels || [];
  const fonts = options.fonts || [];
  const fontSizes = options.font_sizes || [];
  const numberFormats = options.number_formats || [];

  const patchLevel = (levelKey, patch) => {
    onChange({
      ...typesetting,
      [levelKey]: {
        ...(typesetting[levelKey] || {}),
        ...patch,
      },
    });
  };

  return (
    <div className="typesetting-panel">
      <div className="typesetting-panel-header">
        <Text strong>自定义排版参数</Text>
        <Button
          type="link"
          size="small"
          disabled={disabled || saving}
          onClick={onReset}
        >
          恢复默认
        </Button>
      </div>
      <div className="typesetting-table-wrap">
        <table className="typesetting-table">
          <thead>
            <tr>
              <th>级别</th>
              <th>编号格式</th>
              <th>字体</th>
              <th>字号</th>
              <th>对齐方式</th>
              <th>加粗</th>
              <th>颜色</th>
              <th>首行缩进</th>
            </tr>
          </thead>
          <tbody>
            {levels.map(({ key, label }) => {
              const row = typesetting[key] || {};
              const isBody = key === 'body';
              return (
                <tr key={key}>
                  <td className="typesetting-level-label">{label}</td>
                  <td>
                    <Select
                      size="small"
                      className="typesetting-select"
                      disabled={disabled || saving || isBody}
                      value={row.number_format || 'none'}
                      options={numberFormats}
                      onChange={(v) => patchLevel(key, { number_format: v })}
                    />
                  </td>
                  <td>
                    <Select
                      size="small"
                      className="typesetting-select"
                      disabled={disabled || saving}
                      value={row.font || '宋体'}
                      options={fonts.map((f) => ({ value: f, label: f }))}
                      onChange={(v) => patchLevel(key, { font: v })}
                    />
                  </td>
                  <td>
                    <Select
                      size="small"
                      className="typesetting-select"
                      disabled={disabled || saving}
                      value={row.font_size || '小四'}
                      options={fontSizes.map((f) => ({ value: f, label: f }))}
                      onChange={(v) => patchLevel(key, { font_size: v })}
                    />
                  </td>
                  <td>
                    <AlignButtons
                      value={row.align || 'left'}
                      disabled={disabled || saving}
                      onChange={(v) => patchLevel(key, { align: v })}
                    />
                  </td>
                  <td className="typesetting-cell-center">
                    <Checkbox
                      checked={!!row.bold}
                      disabled={disabled || saving}
                      onChange={(e) => patchLevel(key, { bold: e.target.checked })}
                    />
                  </td>
                  <td>
                    {isBody ? (
                      <span className="typesetting-muted">—</span>
                    ) : (
                      <input
                        type="color"
                        className="typesetting-color-input"
                        disabled={disabled || saving}
                        value={row.color || '#000000'}
                        onChange={(e) => patchLevel(key, { color: e.target.value })}
                      />
                    )}
                  </td>
                  <td>
                    <InputNumber
                      size="small"
                      className="typesetting-indent-input"
                      min={0}
                      max={8}
                      disabled={disabled || saving}
                      value={row.first_line_indent ?? 0}
                      onChange={(v) => patchLevel(key, { first_line_indent: v ?? 0 })}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Text type="secondary" className="typesetting-hint">
        导出 Word 时按上表应用标题编号、字体与段落格式；首行缩进单位为字符数。
      </Text>
    </div>
  );
}

export { TypesettingPanel };
