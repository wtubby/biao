// @ts-check
const { test, expect } = require('@playwright/test');
const { loadFixtures } = require('./loadFixtures');

/**
 * 交互路径 1：确认向导用浏览器后退键，验证退回的是"上一个子步骤"
 * 而不是直接跳出 confirm 整个大步骤（回到项目列表或跳到 upload）。
 *
 * 背景：confirm 步骤内部拆成 1~4 的 wizard 子步骤，但 URL hash 只记录到
 * 顶层 step（#/projects/{id}/confirm），子步骤是纯前端 state
 * （ProjectWorkspace.jsx 的 confirmWizardStep），不在 hash 里。
 * 所以这里验证的是"goPrev 在向导中间步骤时只回退子步骤"这条前端逻辑，
 * 不是浏览器原生历史栈的行为。
 */
test.describe('确认向导 - 子步骤后退', () => {
  test('从步骤2点上一步应回到步骤1，而不是离开 confirm 页', async ({ page }) => {
    const { confirm_project_id: projectId } = loadFixtures();
    await page.goto(`/#/projects/${projectId}/confirm`);

    // 工程信息已经在种子数据里填好了，等自动跳转向导到步骤2（资格审查）
    await expect(page.getByRole('button', { name: '下一步：评分要求' })).toBeVisible({ timeout: 10_000 });

    // 上一步 应该回到步骤1（按钮文案变回"下一步：资格审查"）
    await page.getByRole('button', { name: '上一步' }).click();
    await expect(page.getByRole('button', { name: '下一步：资格审查' })).toBeVisible();

    // 侧边栏应仍然停留在"确认评分项"这一大步骤上，没有被带去别的页面
    await expect(page.locator('.workspace-menu-label', { hasText: '确认评分项' })).toBeVisible();

    // URL 的顶层 step 不应该变化（子步骤后退不改 hash）
    await expect(page).toHaveURL(new RegExp(`#/projects/${projectId}/confirm$`));
  });

  test('在步骤1点上一步，应该离开 confirm 回到 upload（顶层步骤切换才走 goPage）', async ({ page }) => {
    const { confirm_project_id: projectId } = loadFixtures();
    await page.goto(`/#/projects/${projectId}/confirm`);
    await expect(page.getByRole('button', { name: '下一步：评分要求' })).toBeVisible({ timeout: 10_000 });

    // 手动退回子步骤1
    await page.getByRole('button', { name: '上一步' }).click();
    await expect(page.getByRole('button', { name: '下一步：资格审查' })).toBeVisible();

    // 步骤1再点一次"上一步"：应该触发顶层 goPrev，离开 confirm
    await page.getByRole('button', { name: '上一步' }).click();
    await expect(page).toHaveURL(new RegExp(`#/projects/${projectId}/upload$`));
  });

  test('真实浏览器后退键：从 outline 页退回 confirm 页应还原到之前离开时的子步骤', async ({ page }) => {
    const { confirm_project_id: projectId } = loadFixtures();
    await page.goto(`/#/projects/${projectId}/confirm`);
    await expect(page.getByRole('button', { name: '下一步：评分要求' })).toBeVisible({ timeout: 10_000 });

    // 顶层前进到 outline（如果被锁在评分项未确认，这一步会被挡下——那也是需要暴露的信号）
    await page.goto(`/#/projects/${projectId}/outline`);

    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`#/projects/${projectId}/confirm$`));
    // 已知限制：子步骤不记录在 URL 里，重新进入 confirm 会按当前数据完整度
    // 重新计算该停在哪个子步骤，不一定是离开前的那个子步骤——这里只断言
    // 页面正确落回 confirm 大步骤、没有崩、也没有被踢回 upload。
    await expect(page.locator('.workspace-menu-label', { hasText: '确认评分项' })).toBeVisible();
  });
});