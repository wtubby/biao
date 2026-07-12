function OutlineStepNum({ num, active, done }) {
  const bg = done
    ? 'var(--color-success)'
    : active
      ? 'var(--color-accent)'
      : 'var(--color-border)';
  const color = done || active ? '#fff' : 'var(--color-text-secondary)';
  return (
    <div
      className={`outline-step-num${done ? ' is-done' : ''}${active ? ' is-active' : ''}`}
      style={{
        width: 30, height: 30, borderRadius: '50%', background: bg,
        color, display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontWeight: 700, fontSize: 15, flexShrink: 0, marginTop: 2,
      }}
    >
      {done ? '✓' : num}
    </div>
  );
}

function OutlineStepRow({
  num, active, done, title, subtitle, children,
  expanded = true, onToggle, summary,
}) {
  // 仅当前阶段展开；点标题/摘要切到该阶段，不再做「再点收起」双轨导航
  const canSwitch = typeof onToggle === 'function';
  const isExpanded = expanded;

  return (
    <div className={`outline-step-row${isExpanded ? ' is-expanded' : ' is-collapsed'}${active ? ' is-active' : ''}${done ? ' is-done' : ''}`}>
      <OutlineStepNum num={num} active={active || isExpanded} done={done} />
      <div className="outline-step-body">
        <button
          type="button"
          className="outline-step-header"
          onClick={canSwitch && !isExpanded ? onToggle : undefined}
          disabled={!canSwitch}
          aria-expanded={isExpanded}
        >
          <div className="outline-step-header-text">
            <div className={`outline-step-title${active || done || isExpanded ? '' : ' is-muted'}`}>
              {title}
            </div>
            {subtitle && isExpanded && (
              <div className="outline-step-subtitle">{subtitle}</div>
            )}
            {!isExpanded && summary && (
              <div className="outline-step-summary">{summary}</div>
            )}
          </div>
          {canSwitch && !isExpanded && (
            <span className="outline-step-chevron" aria-hidden="true">
              ▾
            </span>
          )}
        </button>
        {isExpanded && (
          <div className="outline-step-content">
            {children}
          </div>
        )}
      </div>
    </div>
  );
}

function OutlineStepNav({ steps, current, onSelect }) {
  return (
    <nav className="outline-step-nav" aria-label="大纲策划步骤">
      {steps.map((step) => {
        const isCurrent = step.num === current;
        const isDone = !!step.done;
        return (
          <button
            key={step.num}
            type="button"
            className={`outline-step-nav-item${isCurrent ? ' is-current' : ''}${isDone ? ' is-done' : ''}`}
            onClick={() => onSelect(step.num)}
            aria-current={isCurrent ? 'step' : undefined}
          >
            <span className="outline-step-nav-num">{isDone && !isCurrent ? '✓' : step.num}</span>
            <span className="outline-step-nav-label">{step.shortTitle || step.title}</span>
          </button>
        );
      })}
    </nav>
  );
}

function PillSwitch({
  switchClass,
  pillClass,
  role = 'tablist',
  ariaLabel,
  options,
  value,
  onChange,
  disabled,
  loading,
  itemRole = 'tab',
  renderExtra,
  isOptionDisabled,
  getOptionTitle,
}) {
  return (
    <div className={switchClass}>
      <div className={`${pillClass}s`} role={role} aria-label={ariaLabel}>
        {options.map((opt) => {
          const unavailable = isOptionDisabled?.(opt) || false;
          const selected = value === opt.key;
          return (
            <button
              key={opt.key}
              type="button"
              role={itemRole}
              {...(itemRole === 'tab'
                ? { 'aria-selected': selected }
                : { 'aria-checked': selected })}
              className={`${pillClass}${selected ? ' is-active' : ''}`}
              disabled={disabled || loading || unavailable}
              title={getOptionTitle?.(opt)}
              onClick={() => onChange(opt.key)}
            >
              {opt.label}
              {renderExtra?.(opt, selected)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function DirectorySourceSwitch({ value, onChange, disabled, loading, previews }) {
  const options = [
    { key: 'score_points', label: '按招标评分点生成' },
    { key: 'reference_format', label: '按参考格式生成' },
  ];

  return (
    <div data-fg="dir-source" style={{ marginBottom: 12 }}>
      <PillSwitch
        switchClass="directory-source-switch"
        pillClass="directory-source-pill"
        role="tablist"
        ariaLabel="目录生成依据"
        options={options}
        value={value}
        onChange={onChange}
        disabled={disabled}
        loading={loading}
        itemRole="tab"
        // 两种来源始终可切换：无自动数据时仍可手写/粘贴，不可因 available=false 禁用
        getOptionTitle={(opt) => {
          const preview = previews?.[opt.key];
          if (preview?.available && preview.count > 0) {
            return `可自动填入 ${preview.count} 个章节`;
          }
          return preview?.hint || undefined;
        }}
        renderExtra={(opt, selected) => {
          const preview = previews?.[opt.key];
          if (!(preview?.available && preview.count > 0 && !selected)) return null;
          return <span className="directory-source-pill-count">{preview.count}</span>;
        }}
      />
    </div>
  );
}

function DisplayModeSwitch({ value, onChange, disabled, loading }) {
  const options = [
    { key: 'compact', label: '精简版' },
    { key: 'full', label: '满血版' },
  ];

  return (
    <div data-fg="dir-display-mode">
      <PillSwitch
        switchClass="display-mode-switch"
        pillClass="display-mode-pill"
        role="radiogroup"
        ariaLabel="生成档位"
        options={options}
        value={value}
        onChange={onChange}
        disabled={disabled}
        loading={loading}
        itemRole="radio"
      />
    </div>
  );
}

export {
  OutlineStepRow,
  OutlineStepNav,
  DirectorySourceSwitch,
  DisplayModeSwitch,
};
