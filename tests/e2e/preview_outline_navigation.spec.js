// @ts-check
const { test, expect } = require('@playwright/test');
const { loadFixtures } = require('./loadFixtures');

/**
 * 交互路径 3：从"预览"页用浏览器前进/后退跳回"大纲"再跳回来，
 * 验证章节数据、锁定状态显示是否一致（不会因为组件重新挂载/卸载
 * 而丢失/错乱已加载的章节列表、锁定标记）。
 *
 * 种子数据：done 状态项目，带 1 个已锁定的父节点 + 1 个已生成正文的叶子章节。
 */
test.describe('预览页与大纲页之间前进后退', () => {
  test('预览 -> 大纲 -> 预览：章节标题与生成状态保持一致', async ({ page }) => {
    const { done_project_id: projectId } = loadFixtures();

    await page.goto(`/#/projects/${projectId}/preview`);
    await expect(page.locator('.workspace-menu-label', { hasText: '预览与导出' })).toBeVisible({ timeout: 10_000 });

    // 记录预览页里看到的章节标题列表（用种子数据里的叶子标题做锚点）
    await expect(page.getByText('施工总体部署').first()).toBeVisible({ timeout: 10_000 });

    // 浏览器前进导航到大纲页（用 SPA 内导航模拟点击侧边栏，再用真实历史栈操作）
    await page.goto(`/#/projects/${projectId}/outline`);
    await expect(page.locator('.workspace-menu-label', { hasText: '大纲编辑' })).toBeVisible({ timeout: 10_000 });

    // 大纲已锁定时默认停在"锁定"这一步的摘要视图，不直接显示章节树；
    // 要看到具体章节标题，需要点步骤导航条上的"深化审核"切回去
    // （注意：不能用"返回深化审核，检查绑定"那个按钮——那个只在
    // 校验未通过且尚未锁定时才会渲染，已锁定场景下条件恒为假）
    await expect(page.getByText('大纲已锁定', { exact: true })).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: '深化审核' }).click();

    // 大纲页应显示同一章节，且锁定标记正确（种子数据里根节点 is_locked=1）
    await expect(page.getByText('施工总体部署').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('已锁定').first()).toBeVisible({ timeout: 10_000 });

    // 真实后退回预览页
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`#/projects/${projectId}/preview$`));
    await expect(page.locator('.workspace-menu-label', { hasText: '预览与导出' })).toBeVisible({ timeout: 10_000 });

    // 后退回来之后，章节标题应该还在、没有变成空列表或者报错
    await expect(page.getByText('施工总体部署').first()).toBeVisible({ timeout: 10_000 });

    // 再前进回大纲页，验证前进也不会丢数据（同样需要先切回深化审核才能看到树）
    await page.goForward();
    await expect(page).toHaveURL(new RegExp(`#/projects/${projectId}/outline$`));
    await expect(page.getByText('大纲已锁定', { exact: true })).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: '深化审核' }).click();
    await expect(page.getByText('施工总体部署').first()).toBeVisible({ timeout: 10_000 });
  });

  test('前进后退过程中不应出现未捕获的前端异常', async ({ page }) => {
    const { done_project_id: projectId } = loadFixtures();
    const errors = [];
    page.on('pageerror', (err) => errors.push(String(err)));

    await page.goto(`/#/projects/${projectId}/preview`);
    await expect(page.locator('.workspace-menu-label', { hasText: '预览与导出' })).toBeVisible({ timeout: 10_000 });

    await page.goto(`/#/projects/${projectId}/outline`);
    await page.goBack();
    await page.goForward();
    await page.goBack();

    expect(errors, `前进/后退过程中出现异常：${errors.join('; ')}`).toHaveLength(0);
  });
});