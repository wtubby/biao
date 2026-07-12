import { Suspense, Spin } from '../globals.js';

function PageSuspense({ children, tip = '加载模块…' }) {
  return (
    <Suspense fallback={(
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 240, padding: 48 }}>
        <Spin size="large" tip={tip} />
      </div>
    )}
    >
      {children}
    </Suspense>
  );
}

export { PageSuspense };
