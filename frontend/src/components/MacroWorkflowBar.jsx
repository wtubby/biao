import { MACRO_WORKFLOW_STEPS } from '../constants/macroWorkflow.js';
import { Icon } from './icons.jsx';

function MacroWorkflowBar({ steps }) {
  const items = steps || MACRO_WORKFLOW_STEPS.map((step, index) => ({
    ...step,
    index,
    isCurrent: index === 0,
    isDone: false,
    accessible: true,
  }));

  return (
    <nav className="macro-workflow-bar" aria-label="主流程进度">
      {items.map((step, idx) => (
        <div key={step.key} className="macro-workflow-item-wrap">
          <div
            className={[
              'macro-workflow-item',
              step.isCurrent ? 'is-current' : '',
              step.isDone ? 'is-done' : '',
              !step.accessible && !step.isCurrent && !step.isDone ? 'is-locked' : '',
            ].filter(Boolean).join(' ')}
          >
            <span className="macro-workflow-num" aria-hidden="true">
              {step.isDone ? <Icon name="success" size={14} /> : idx + 1}
            </span>
            <span className="macro-workflow-label">{step.label}</span>
          </div>
          {idx < items.length - 1 && (
            <span className={`macro-workflow-connector${step.isDone ? ' is-done' : ''}`} aria-hidden="true" />
          )}
        </div>
      ))}
    </nav>
  );
}

export { MacroWorkflowBar };
