// @ts-check
const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
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
    // 跑之前先重建前端产物 + 造 E2E 用的项目数据，再启动后端（后端同时托管前端静态文件）
    command:
      'npm run build:frontend && python3 scripts/seed_e2e_fixtures.py && python3 -m uvicorn main:app --host 127.0.0.1 --port 3333',
    url: 'http://127.0.0.1:3333/',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});