// @ts-check
const { test, expect } = require('@playwright/test');
const { loadFixtures } = require('./loadFixtures');

/**
 * 交互路径 2：生成过程中刷新页面。
 *
 * 种子数据里的项目 status 直接是 'generating'（跳过真实解析/LLM 调用），
 * 不会有真实的 SSE 事件推送过来，但这正好用来验证"刷新后重连"这段
 * 纯前端逻辑本身：
 *   1. 页面刷新后，GenerationPanel 里 `projectStatus === 'generating'` 的
 *      resume-on-mount effect 应该重新触发，重新建立 SSE 连接（不是傻等）。
 *   2. 进度条不应该在刷新后瞬间显示错误/为空的数值导致布局跳动或崩溃。
 *   3. 页面不应该因为「没有真实事件」而卡死在 loading 转圈。
 */
test.describe('生成中刷新页面', () => {
  test('刷新后仍显示为"生成中"状态，且不报错、不卡在加载态', async ({ page }) => {
    const { generating_project_id: projectId } = loadFixtures();

    /** @type {string[]} */
    const consoleErrors = [];
    page.on('pageerror', (err) => consoleErrors.push(String(err)));

    await page.goto(`/#/projects/${projectId}/generate`);

    // 页面应该正确落在"内容生成"这一步，而不是因为 status='generating'
    // 又没有真实事件而被误判成别的状态
    await expect(page.locator('.workspace-menu-label', { hasText: '内容生成' })).toBeVisible({ timeout: 10_000 });

    // 暂停按钮出现，说明前端认定当前处于批量生成中
    await expect(page.getByRole('button', { name: '暂停生成' })).toBeVisible({ timeout: 10_000 });

    // 真实刷新整个页面（不是 SPA 内导航），模拟用户按 F5
    await page.reload();

    // 刷新后：不应该白屏卡在"正在恢复页面…"超过合理时间
    await expect(page.locator('text=正在恢复页面')).toHaveCount(0, { timeout: 15_000 });

    // 刷新后应该重新识别出项目仍在生成中，重新显示暂停按钮
    await expect(page.getByRole('button', { name: '暂停生成' })).toBeVisible({ timeout: 10_000 });

    // 进度条数字应该是合法的 "N / M" 格式，不是 "NaN / undefined" 之类
    const progressText = await page.locator('.generation-progress-label').innerText();
    expect(progressText).toMatch(/\d+\s*\/\s*\d+/);

    expect(consoleErrors, `刷新后出现未捕获异常：${consoleErrors.join('; ')}`).toHaveLength(0);
  });

  test('刷新后 SSE 应重新发起连接请求（验证前端确实重连，不是死连接）', async ({ page }) => {
    const { generating_project_id: projectId } = loadFixtures();

    await page.goto(`/#/projects/${projectId}/generate`);
    await expect(page.getByRole('button', { name: '暂停生成' })).toBeVisible({ timeout: 10_000 });

    let streamRequestCountAfterReload = 0;
    page.on('request', (req) => {
      if (req.url().includes(`/projects/${projectId}/stream`)) {
        streamRequestCountAfterReload += 1;
      }
    });

    await page.reload();
    await expect(page.getByRole('button', { name: '暂停生成' })).toBeVisible({ timeout: 10_000 });

    // 给一点时间让 EventSource 真正建立连接
    await page.waitForTimeout(1000);

    expect(
      streamRequestCountAfterReload,
      '刷新后没有发起新的 /stream SSE 请求，说明重连逻辑没有触发',
    ).toBeGreaterThan(0);
  });
});