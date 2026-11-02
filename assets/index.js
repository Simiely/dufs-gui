/* Dufs GUI 网页皮肤 —— 自研前端，不依赖 dufs 内置的 index.js。
 *
 * 为什么自研：dufs 的 --assets 只做"逐个覆盖"，如果我们不提供 index.js，
 * 它会回退到内置版本，而内置 JS 依赖内置 index.html 的 DOM 结构；
 * 我们拿不到那份 HTML 的稳定契约，所以干脆全部自己实现，避免版本耦合。
 *
 * 数据来源：dufs 把目录数据以 base64(JSON) 注入 #index-data。
 * 结构（IndexData）：
 *   kind, href, uri_prefix, allow_upload, allow_delete, allow_search,
 *   allow_archive, dir_exists, auth, user, paths[]
 *   paths[i]: { path_type: Dir|SymlinkDir|File|SymlinkFile, name, mtime(ms), size }
 */

(function () {
  'use strict';

  // ---------- 取数 ----------
  var raw = '';
  var el = document.getElementById('index-data');
  if (el) raw = (el.textContent || '').trim();

  var DATA;
  try {
    // escape/unescape 组合用于处理 atob 输出里的非 ASCII（中文文件名）
    DATA = JSON.parse(decodeURIComponent(escape(atob(raw))));
  } catch (e) {
    fatal('无法解析目录数据：' + e.message);
    return;
  }

  if (!DATA || DATA.kind !== 'Index') {
    // 编辑器 / 查看器等其它模式不在本皮肤支持范围内，回落到最朴素的表现
    fatal('当前页面模式（' + (DATA && DATA.kind) + '）不在自定义皮肤的支持范围内，' +
          '请在「网页美化界面」关闭后使用 dufs 默认界面。');
    return;
  }

  var PREFIX = DATA.uri_prefix || '';
  var HREF = DATA.href || '/';

  // ---------- 工具 ----------
  function q(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function isDir(p) { return p.path_type === 'Dir' || p.path_type === 'SymlinkDir'; }

  function fullUrl(pathPart) {
    // uri_prefix 形如 "/files"，href 形如 "/sub/"，name 相对当前目录
    return PREFIX + pathPart;
  }

  function fmtSize(n) {
    if (n === null || n === undefined) return '-';
    if (n < 1024) return n + ' B';
    var u = ['KB', 'MB', 'GB', 'TB'];
    var v = n / 1024, i = 0;
    while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return (v < 10 ? v.toFixed(1) : Math.round(v)) + ' ' + u[i];
  }

  function fmtTime(ms) {
    if (!ms) return '-';
    var d = new Date(ms);
    var p = function (x) { return (x < 10 ? '0' : '') + x; };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) +
           ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function fatal(msg) {
    var box = q('error-box');
    if (box) { box.hidden = false; box.textContent = msg; }
    var t = q('paths-body');
    if (t) t.innerHTML = '';
  }

  function toast(msg) {
    var box = q('error-box');
    if (!box) return;
    box.hidden = false;
    box.textContent = msg;
    setTimeout(function () { box.hidden = true; }, 4000);
  }

  // ---------- 面包屑 ----------
  function renderBreadcrumb() {
    var nav = q('breadcrumb');
    if (!nav) return;
    var parts = HREF.split('/').filter(function (x) { return x !== ''; });
    var html = '<a class="crumb" href="' + esc(fullUrl('/')) + '">首页</a>';
    var acc = '';
    for (var i = 0; i < parts.length; i++) {
      acc += '/' + parts[i];
      var last = (i === parts.length - 1);
      html += '<span class="sep">/</span>';
      html += last
        ? '<span class="crumb current">' + esc(decodeURIComponent(parts[i])) + '</span>'
        : '<a class="crumb" href="' + esc(fullUrl(acc + '/')) + '">' +
          esc(decodeURIComponent(parts[i])) + '</a>';
    }
    nav.innerHTML = html;
  }

  // ---------- 文件列表 ----------
  var sortKey = 'name';
  var sortAsc = true;

  function sortPaths(list) {
    var dirs = list.filter(isDir), files = list.filter(function (p) { return !isDir(p); });
    function cmp(a, b) {
      var r;
      if (sortKey === 'mtime') r = (a.mtime || 0) - (b.mtime || 0);
      else if (sortKey === 'size') r = (a.size || 0) - (b.size || 0);
      else r = String(a.name).localeCompare(String(b.name), 'zh-Hans-CN');
      return sortAsc ? r : -r;
    }
    // 目录永远排在前面
    return dirs.sort(cmp).concat(files.sort(cmp));
  }

  function renderPaths() {
    var list = (DATA.paths || []).slice();
    var body = q('paths-body');
    var empty = q('empty-folder');
    if (!body) return;

    if (!list.length) {
      body.innerHTML = '';
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    var html = '';

    // 返回上级
    if (HREF && HREF !== '/') {
      var parent = HREF.replace(/\/[^/]*\/?$/, '') || '/';
      html += '<tr class="row-up">' +
        '<td class="col-name"><a class="path dir" href="' + esc(fullUrl(parent + '/')) + '">' +
        '<span class="ico">↩</span>返回上级</a></td>' +
        '<td class="col-mtime">-</td><td class="col-size">-</td><td class="col-actions"></td></tr>';
    }

    sortPaths(list).forEach(function (p) {
      var d = isDir(p);
      var href = fullUrl(HREF + encodeURIComponent(p.name) + (d ? '/' : ''));
      var ico = d ? '📁' : '📄';
      var cls = d ? 'path dir' : 'path file';

      var acts = '';
      if (d) {
        if (DATA.allow_archive) {
          acts += '<a class="act" href="' + esc(href + '?zip') + '" title="打包下载">⤓</a>';
        }
      } else {
        acts += '<a class="act" href="' + esc(href) + '" download title="下载">⤓</a>';
      }
      if (DATA.allow_delete) {
        acts += '<button type="button" class="act danger" data-del="' +
                esc(HREF + p.name) + '" title="删除">✕</button>';
      }

      html += '<tr>' +
        '<td class="col-name"><a class="' + cls + '" href="' + esc(href) + '">' +
          '<span class="ico">' + ico + '</span>' +
          '<span class="nm">' + esc(p.name) + '</span></a></td>' +
        '<td class="col-mtime">' + fmtTime(p.mtime) + '</td>' +
        '<td class="col-size">' + (d ? (p.size != null ? p.size + ' 项' : '-') : fmtSize(p.size)) + '</td>' +
        '<td class="col-actions">' + acts + '</td>' +
      '</tr>';
    });

    body.innerHTML = html;

    Array.prototype.forEach.call(body.querySelectorAll('[data-del]'), function (b) {
      b.addEventListener('click', function () {
        if (!confirm('确定删除「' + b.getAttribute('data-del') + '」？')) return;
        doDelete(b.getAttribute('data-del'));
      });
    });
  }

  function doDelete(path) {
    fetch(fullUrl(path), { method: 'DELETE', credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        location.reload();
      })
      .catch(function (e) { toast('删除失败：' + e.message); });
  }

  // ---------- 排序表头 ----------
  function bindSort() {
    Array.prototype.forEach.call(document.querySelectorAll('th.sortable'), function (th) {
      th.addEventListener('click', function () {
        var k = th.getAttribute('data-sort');
        if (sortKey === k) sortAsc = !sortAsc;
        else { sortKey = k; sortAsc = true; }
        renderPaths();
      });
    });
  }

  // ---------- 上传 ----------
  var uploads = [];

  function renderUploaders() {
    var wrap = q('uploaders');
    var body = q('uploaders-body');
    if (!wrap || !body) return;
    wrap.hidden = uploads.length === 0;
    body.innerHTML = uploads.map(function (u) {
      return '<tr><td>' + esc(u.name) + '</td>' +
        '<td><div class="bar"><div class="bar-in" style="width:' + u.pct + '%"></div></div>' +
        '<span class="pct">' + u.pct + '%</span></td>' +
        '<td class="col-status">' + esc(u.status) + '</td></tr>';
    }).join('');
  }

  function uploadOne(file) {
    var rec = { name: file.name, pct: 0, status: '等待' };
    uploads.push(rec);
    renderUploaders();

    var url = fullUrl(HREF + encodeURIComponent(file.name));
    var xhr = new XMLHttpRequest();
    xhr.open('PUT', url, true);
    xhr.upload.onprogress = function (e) {
      if (e.lengthComputable) {
        rec.pct = Math.round(e.loaded * 100 / e.total);
        rec.status = '上传中';
        renderUploaders();
      }
    };
    xhr.onload = function () {
      if (xhr.status >= 200 && xhr.status < 300) {
        rec.pct = 100; rec.status = '完成';
        renderUploaders();
        setTimeout(function () {
          uploads = uploads.filter(function (x) { return x !== rec; });
          renderUploaders();
          location.reload();
        }, 500);
      } else {
        rec.status = '失败 ' + xhr.status;
        renderUploaders();
      }
    };
    xhr.onerror = function () { rec.status = '网络错误'; renderUploaders(); };
    xhr.send(file);
  }

  function startUpload(files) {
    if (!files || !files.length) return;
    Array.prototype.forEach.call(files, uploadOne);
  }

  function bindUpload() {
    var btn = q('btn-upload');
    var input = q('file-input');
    if (btn && input) {
      btn.addEventListener('click', function () { input.click(); });
      input.addEventListener('change', function () {
        startUpload(input.files);
        input.value = '';
      });
    }

    // 拖拽上传
    var dz = q('dropzone');
    var depth = 0;
    window.addEventListener('dragenter', function (e) {
      e.preventDefault(); depth++;
      if (DATA.allow_upload && dz) dz.classList.add('on');
    });
    window.addEventListener('dragleave', function () {
      depth--;
      if (depth <= 0 && dz) { dz.classList.remove('on'); depth = 0; }
    });
    window.addEventListener('dragover', function (e) { e.preventDefault(); });
    window.addEventListener('drop', function (e) {
      e.preventDefault();
      if (dz) dz.classList.remove('on');
      depth = 0;
      if (!DATA.allow_upload) { toast('未开启上传权限'); return; }
      if (e.dataTransfer && e.dataTransfer.files) startUpload(e.dataTransfer.files);
    });
  }

  // ---------- 其它操作 ----------
  function bindActions() {
    var mkdir = q('btn-mkdir');
    if (mkdir) {
      mkdir.addEventListener('click', function () {
        var name = prompt('新文件夹名称');
        if (!name) return;
        fetch(fullUrl(HREF + encodeURIComponent(name) + '/'), {
          method: 'MKCOL', credentials: 'same-origin'
        }).then(function (r) {
          if (!r.ok && r.status !== 405) throw new Error('HTTP ' + r.status);
          location.reload();
        }).catch(function (e) { toast('创建失败：' + e.message); });
      });
    }

    var zip = q('btn-zip');
    if (zip) {
      zip.addEventListener('click', function () {
        location.href = fullUrl(HREF + '?zip');
      });
    }

    var si = q('search-input');
    var sb = q('searchbar');
    if (si && sb) {
      si.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        var v = si.value.trim();
        if (!v) return;
        location.href = fullUrl(HREF + '?q=' + encodeURIComponent(v));
      });
    }
  }

  // ---------- 按权限显隐 ----------
  function applyPerms() {
    var up = q('btn-upload'), mk = q('btn-mkdir'), zp = q('btn-zip'),
        sb = q('searchbar'), box = q('userbox');
    if (up) up.hidden = !DATA.allow_upload;
    if (mk) mk.hidden = !DATA.allow_upload;
    if (zp) zp.hidden = !DATA.allow_archive;
    if (sb) sb.hidden = !DATA.allow_search;
    if (box) {
      if (DATA.auth && DATA.user) {
        box.innerHTML = '<span class="user">👤 ' + esc(DATA.user) + '</span>';
      } else {
        box.innerHTML = '';
      }
    }
  }

  // ---------- 启动 ----------
  renderBreadcrumb();
  applyPerms();
  renderPaths();
  bindSort();
  bindUpload();
  bindActions();
})();
