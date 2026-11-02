/**
 * 网页皮肤端到端验证（jsdom）—— 基于 dufs 官方assets。
 *
 * 背景：早期版本手写了一整套 index.html/index.js，等于在猜 dufs 的内部契约
 *（数据节点写法、IndexData 字段、DOM class、权限判定），
 * 结果表现为"上传 / 下载 / 预览全部失效"且 dufs 端不报错。
 *
 * 现改为官方推荐做法：完整搬运官方 assets，只覆盖 index.css 的 CSS 变量。
 * 本脚本用 jsdom 真实执行官方 index.js，验证：
 *   1. index.html 用的是官方结构（template#index-data）
 *   2. 目录数据能解析、文件行能渲染
 *   3. 下载链接存在（.control.download 被启用）
 *   4. 上传控件存在且绑定了 change → PUT
 *   5. 编辑器（预览）元素存在
 *
 * 运行：node tools/check_skin.js      （需 npm i jsdom）
 */
'use strict';

const fs = require('fs');
const path = require('path');

let JSDOM;
try {
  JSDOM = require('jsdom').JSDOM;
} catch (e) {
  console.log('SKIP: jsdom 未安装（npm i jsdom 后本检查才会真正执行）');
  process.exit(0);
}

const ASSETS = path.resolve(__dirname, '..', 'assets');
const read = (f) => fs.readFileSync(path.join(ASSETS, f), 'utf8');

const html = read('index.html');
const js = read('index.js');

const DATA = {
  kind: 'Index', href: '/', uri_prefix: '',
  allow_upload: true, allow_delete: true, allow_search: true,
  allow_archive: true, dir_exists: true, auth: false, user: null,
  paths: [
    { path_type: 'Dir', name: '子目录', mtime: 1730000000000, size: 3 },
    { path_type: 'File', name: '报告.pdf', mtime: 1730000000000, size: 123456 },
  ],
};
const b64 = (o) => Buffer.from(JSON.stringify(o), 'utf8').toString('base64');

// dufs 会先替换占位符，再返回 HTML；这里模拟该过程。
// 官方 index.html 用 <script src="__ASSETS_PREFIX__index.js">，
// jsdom 不加载外部资源，因此内联注入官方 JS 以保证等价执行。
const page = html
  .split('__ASSETS_PREFIX__').join('')
  .replace('__INDEX_DATA__', b64(DATA))
  .replace('<script src="index.js"></script>', `<script>${js}</script>`);

let failures = 0;
const check = (name, cond, extra) => {
  console.log(`${cond ? '✅' : '❌'} ${name}`);
  if (!cond) { failures++; if (extra) console.log('    ' + extra); }
};

// 1) 必须是官方结构：数据放在 <template id="index-data">
check('使用官方结构 template#index-data',
  /<template id="index-data">/.test(html),
  'index.html 不是官方版本');

// 2) index.html 必须引用官方 index.js（否则交互逻辑会缺失）
check('引用官方 index.js',
  /<script src="__ASSETS_PREFIX__index\.js"><\/script>/.test(html));

// 3) 占位符：__INDEX_DATA__ 必须唯一
check('__INDEX_DATA__ 全文唯一',
  html.split('__INDEX_DATA__').length - 1 === 1,
  `实际 ${html.split('__INDEX_DATA__').length - 1} 次`);

// 4) 官方 index.js 必须随包提供（HTML 与 JS 需同版本）
check('随包提供官方 index.js', fs.existsSync(path.join(ASSETS, 'index.js')));
check('随包提供 index.css 且含深色覆盖',
  /DufsGui 深色皮肤/.test(read('index.css')));

// ---- 真实执行 ----
// 官方 index.js 在 DOMContentLoaded 里初始化，必须等页面 load 完再断言，
// 否则所有元素都还是 hidden、行数为 0 —— 这曾让检查脚本误报失败。
const dom = new JSDOM(page, {
  runScripts: 'dangerously', url: 'http://127.0.0.1:5000/', pretendToBeVisual: true,
});
const w = dom.window;

async function run() {
  const d = w.document;

  // 5) 文件行渲染出来了
  const rows = d.querySelectorAll('.paths-table tbody tr');
  check('文件列表已渲染', rows.length === 2, `实际 ${rows.length} 行`);

  // 6) 官方 JS 应生成 path 链接（点击即下载 / 进入目录）
  const links = d.querySelectorAll('.paths-table tbody tr a[href]');
  check('生成文件/目录链接', links.length >= 2, `实际 ${links.length}`);
  check('链接指向正确文件',
    !!Array.from(links).find((a) => a.getAttribute('href').includes('%E6%8A%A5%E5%91%8A.pdf')),
    Array.from(links).map((a) => a.getAttribute('href')).join(', '));

  // 7) 下载控件：官方 JS 会按权限移除 hidden
  const dl = d.querySelector('.control.download');
  check('下载控件已启用（无 hidden）', !!dl && !dl.className.includes('hidden'),
    dl && dl.className);

  // 8) 上传控件：同样应被启用
  const up = d.querySelector('.control.upload-file');
  const fileInput = d.getElementById('file');
  check('上传控件已启用（无 hidden）', !!up && !up.className.includes('hidden'),
    up && up.className);
  check('file input 存在', !!fileInput);

  // 9) 触发上传应发出 PUT
  const calls = [];
  const RealXHR = w.XMLHttpRequest;
  w.XMLHttpRequest = function () {
    this.open = function (m, u) { calls.push({ m, u }); };
    this.upload = { addEventListener: function () {} };
    this.setRequestHeader = function () {};
    this.send = function () {};
    this.addEventListener = function () {};
    this.getAllResponseHeaders = function () { return ''; };
  };
  try {
    Object.defineProperty(fileInput, 'files', { value: [{ name: '我的 报告.pdf', size: 10 }] });
    fileInput.dispatchEvent(new w.Event('change'));
  } catch (e) { /* jsdom 限制 */ }
  // 官方上传链路有异步分支（>20MB 走可恢复上传，先 HEAD 探测），
  // 这里必须等一拍再断言，否则会误判为"没发请求"。
  await new Promise((r) => setTimeout(r, 300));
  w.XMLHttpRequest = RealXHR;
  const put = calls.find((c) => c.m === 'PUT');
  check('上传发出 PUT 请求', !!put, JSON.stringify(calls));

  // 10) 预览 / 编辑
  check('编辑器元素存在（支撑预览/编辑）', !!d.getElementById('editor'));

  console.log(failures === 0 ? '\n全部通过' : `\n${failures} 项失败`);
  process.exit(failures === 0 ? 0 : 1);
}

if (w.document.readyState === 'complete') run();
else w.addEventListener('load', run);
