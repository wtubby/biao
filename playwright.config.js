// @ts-check
const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
  globalSetup: require.resolve('./tests/e2e/globalSetup.js'),
  fullyParallel: false, // 项目状态是共享 sqlite 里的数据，避免并发用例互相踩状态
  retries: 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:3333',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    // 造数据已经挪到 globalSetup 里（不受 reuseExistingServer 影响，一定会跑）。
    // 这里只负责构建前端产物 + 启动后端；如果 3333 端口已经有一个手动起的
    // 后端在跑，会直接复用，不会重复启动（见 reuseExistingServer）。
    // 必须用项目 venv，系统 python 缺 jieba 等依赖。
    command:
      process.platform === 'win32'
        ? 'npm run build:frontend && .\\venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 3333'
        : 'npm run build:frontend && ./venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 3333',
    url: 'http://127.0.0.1:3333/',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
