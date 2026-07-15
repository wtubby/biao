const fs = require('fs');
const path = require('path');

const FIXTURES_PATH = path.join(__dirname, '.fixtures.json');

/**
 * 运行期同步读取种子数据生成的 project_id。
 * 故意不在测试文件顶层用 require('./.fixtures.json')：
 * 那样会在 Playwright 收集测试文件时就同步读取该文件，
 * 而这个文件是 playwright.config.js 的 webServer.command
 * （build:frontend -> seed_e2e_fixtures.py -> uvicorn）异步生成的，
 * 两者时序没有强保证，会出现文件还没写出来就被 require 的竞态。
 * 放到每个 test() 内部调用，保证读取发生在 webServer ready 之后。
 */
function loadFixtures() {
  if (!fs.existsSync(FIXTURES_PATH)) {
    throw new Error(
      `找不到 ${FIXTURES_PATH}，请确认 playwright 的 webServer 命令里 ` +
      '"python3 scripts/seed_e2e_fixtures.py" 已经成功跑过（或手动先跑一遍这条命令）。',
    );
  }
  return JSON.parse(fs.readFileSync(FIXTURES_PATH, 'utf-8'));
}

module.exports = { loadFixtures };