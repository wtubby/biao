// @ts-check
const { spawnSync } = require('child_process');
const path = require('path');

/**
 * globalSetup 在 Playwright 生命周期里的顺序是：globalSetup -> webServer -> 测试用例。
 * 跟 webServer.command 不一样，globalSetup 不受 reuseExistingServer 影响，
 * 不管端口是不是已经被一个手动起的后端占用了，这一步都一定会跑一遍，
 * 保证 tests/e2e/.fixtures.json 一定存在。
 */
module.exports = async function globalSetup() {
  const repoRoot = path.resolve(__dirname, '..', '..');
  const script = path.join('scripts', 'seed_e2e_fixtures.py');

  // Windows 上 python3 不一定在 PATH 里（很多官方安装包只注册 python），
  // 依次尝试，第一个能跑通的就用它。
  const candidates = ['python3', 'python', 'py'];
  let lastError = null;

  for (const cmd of candidates) {
    const result = spawnSync(cmd, [script], {
      cwd: repoRoot,
      stdio: 'inherit',
      shell: process.platform === 'win32', // Windows 下部分 launcher（如 py）需要走 shell 解析
    });
    if (!result.error && result.status === 0) {
      console.log(`[globalSetup] 种子数据已生成（使用解释器: ${cmd}）`);
      return;
    }
    lastError = result.error || new Error(`退出码 ${result.status}`);
  }

  throw new Error(
    `[globalSetup] 依次尝试 ${candidates.join('/')} 运行 ${script} 均失败，` +
    `最后一次错误：${lastError}\n` +
    '请确认本机能在命令行直接跑通 "python scripts/seed_e2e_fixtures.py"（先手动跑一遍排查依赖/解释器问题）。',
  );
};