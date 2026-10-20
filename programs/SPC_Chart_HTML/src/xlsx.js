// Minimal .xlsx / .xlsm / .ods / .csv / HTML-table reader: every sheet as rows of cells (number, string, Date or null).
// Formula cells give the value Excel saved with the file. Needs pako (inflateRaw) for zip entries.
// copy(): the same workbook with some cells changed and rows/cells coloured (the original file is never written).
(function () {
  'use strict';

  function unzip(buf) {
    var u8 = new Uint8Array(buf), dv = new DataView(buf), eocd = -1;
    for (var i = u8.length - 22; i >= Math.max(0, u8.length - 65557); i--) {
      if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    }
    if (eocd < 0) throw new Error('엑셀 파일 형식이 아닙니다 (zip 끝을 찾지 못함)');
    var count = dv.getUint16(eocd + 10, true), p = dv.getUint32(eocd + 16, true), files = {};
    var dec = new TextDecoder('utf-8'), index = {};
    for (var k = 0; k < count; k++) {
      if (dv.getUint32(p, true) !== 0x02014b50) throw new Error('엑셀 파일이 손상되었거나 저장 중입니다');
      var method = dv.getUint16(p + 10, true), size = dv.getUint32(p + 20, true);
      var nameLen = dv.getUint16(p + 28, true), extraLen = dv.getUint16(p + 30, true), commentLen = dv.getUint16(p + 32, true);
      var local = dv.getUint32(p + 42, true), name = dec.decode(u8.subarray(p + 46, p + 46 + nameLen));
      files[name] = {method: method, size: size, local: local, crc: dv.getUint32(p + 16, true), usize: dv.getUint32(p + 24, true), order: k};
      index[partKey(name)] = name;
      p += 46 + nameLen + extraLen + commentLen;
    }
    function get(name) { return files[index[partKey(name)]]; }
    return {
      files: files,
      raw: function (name) {
        var f = get(name);
        var start = f.local + 30 + dv.getUint16(f.local + 26, true) + dv.getUint16(f.local + 28, true);
        return u8.subarray(start, start + f.size);
      },
      has: function (name) { return !!get(name); },
      text: function (name) {
        var f = get(name);
        if (!f) return null;
        var start = f.local + 30 + dv.getUint16(f.local + 26, true) + dv.getUint16(f.local + 28, true);
        var data = u8.subarray(start, start + f.size);
        if (f.method === 8) data = window.pako.inflateRaw(data);
        else if (f.method !== 0) throw new Error('지원하지 않는 압축 방식: ' + f.method);
        return dec.decode(data);
      }
    };
  }

  // Part names are found without regard to case, '\' separators or a leading '/' (issue #25: an
  // exporter's zip that Excel opens but whose names differ from Excel's own).
  function partKey(name) { return name.replace(/\\/g, '/').replace(/^(\.?\/)+/, '').toLowerCase(); }

  function xml(text) {
    var doc = new DOMParser().parseFromString(text, 'application/xml');
    if (doc.getElementsByTagName('parsererror').length) throw new Error('엑셀 내부 XML을 읽지 못했습니다');
    return doc;
  }

  function tags(node, name) { return node.getElementsByTagNameNS('*', name); }

  function child(node, name) {
    for (var c = node.firstElementChild; c; c = c.nextElementSibling) if (c.localName === name) return c;
    return null;
  }

  // Text of a shared/inline string without phonetic runs (rPh).
  function stringText(si) {
    var out = '';
    (function walk(n) {
      for (var c = n.firstElementChild; c; c = c.nextElementSibling) {
        if (c.localName === 'rPh') continue;
        if (c.localName === 't') out += c.textContent;
        else walk(c);
      }
    })(si);
    return out;
  }

  function resolve(base, target) {
    if (target.charAt(0) === '/') return target.slice(1);
    var parts = base.split('/');
    parts.pop();
    target.split('/').forEach(function (s) {
      if (s === '..') parts.pop();
      else if (s && s !== '.') parts.push(s);
    });
    return parts.join('/');
  }

  var DATE_IDS = {14: 1, 15: 1, 16: 1, 17: 1, 18: 1, 19: 1, 20: 1, 21: 1, 22: 1, 45: 1, 46: 1, 47: 1};

  function isDateFormat(code) {
    var s = code.replace(/"[^"]*"/g, '').replace(/\[[^\]]*\]/g, '').replace(/\\./g, '');
    return /[ymdhs]/i.test(s) && !/^general$/i.test(s);
  }

  function colIndex(ref) {
    var n = 0;
    for (var i = 0; i < ref.length; i++) {
      var c = ref.charCodeAt(i);
      if (c < 65 || c > 90) break;
      n = n * 26 + (c - 64);
    }
    return n - 1;
  }

  function relsPath(part) {
    var i = part.lastIndexOf('/');
    return part.slice(0, i + 1) + '_rels/' + part.slice(i + 1) + '.rels';
  }

  // [{id, type (last word of the Type URI), target (part name)}] of a part's .rels file.
  function relsOf(zip, part) {
    var text = zip.text(relsPath(part)), out = [];
    if (!text) return out;
    var rs = tags(xml(text), 'Relationship');
    for (var i = 0; i < rs.length; i++) {
      if (/^external$/i.test(rs[i].getAttribute('TargetMode') || '')) continue;
      out.push({id: rs[i].getAttribute('Id'), type: (rs[i].getAttribute('Type') || '').split('/').pop(),
                target: resolve(part, (rs[i].getAttribute('Target') || '').replace(/\\/g, '/'))});
    }
    return out;
  }

  function entryList(zip) {
    var names = Object.keys(zip.files);
    return names.slice(0, 8).join(', ') + (names.length > 8 ? ' 외 ' + (names.length - 8) + '개' : '');
  }

  // Workbook part and the parts it points to. Excel finds the workbook through _rels/.rels, not by its name.
  function parts(zip) {
    var wb = null;
    relsOf(zip, '').forEach(function (r) { if (!wb && r.type === 'officeDocument' && zip.has(r.target)) wb = r.target; });
    if (!wb) {
      var ct = zip.text('[Content_Types].xml'), m = ct && /PartName="([^"]+)"[^>]*ContentType="[^"]*spreadsheetml\.(sheet|template)\.main[^"]*"/i.exec(ct);
      if (m && zip.has(m[1])) wb = partKey(m[1]);
    }
    if (!wb) wb = Object.keys(zip.files).map(partKey).filter(function (n) { return /(^|\/)workbook\d*\.xml$/.test(n); })[0] || null;
    if (!wb) {
      if (Object.keys(zip.files).map(partKey).some(function (n) { return /\.bin$/.test(n) && /workbook/.test(n); }))
        throw new Error('엑셀 바이너리 통합 문서(.xlsb)는 읽을 수 없습니다. Excel에서 .xlsx로 다른 이름으로 저장해 주세요');
      throw new Error('엑셀 통합 문서(.xlsx)가 아닙니다 — 파일 안에 workbook 부분이 없습니다 (안에 든 것: ' + entryList(zip) + ')');
    }
    var out = {workbook: wb, rels: relsOf(zip, wb), styles: null, shared: null};
    out.rels.forEach(function (r) {
      if (r.type === 'styles' && !out.styles) out.styles = r.target;
      if (r.type === 'sharedStrings' && !out.shared) out.shared = r.target;
    });
    var dir = wb.slice(0, wb.lastIndexOf('/') + 1);
    if (!out.styles && zip.has(dir + 'styles.xml')) out.styles = dir + 'styles.xml';
    if (!out.shared && zip.has(dir + 'sharedStrings.xml')) out.shared = dir + 'sharedStrings.xml';
    return out;
  }

  function readXlsx(buf) {
    var zip = unzip(buf);
    if (zip.has('content.xml') && /opendocument\.spreadsheet/.test(zip.text('mimetype') || '')) return readOds(zip);
    var pt = parts(zip), wbPath = pt.workbook;
    var wb = xml(zip.text(wbPath));
    var pr = tags(wb, 'workbookPr')[0], date1904 = pr && /^(1|true)$/.test(pr.getAttribute('date1904') || '');
    var rels = {};
    for (var i = 0; i < pt.rels.length; i++) rels[pt.rels[i].id] = pt.rels[i].target;
    var shared = [], sst = pt.shared && zip.text(pt.shared);
    if (sst) {
      var sis = tags(xml(sst), 'si');
      for (i = 0; i < sis.length; i++) shared.push(stringText(sis[i]));
    }
    var dateStyle = [], styles = pt.styles && zip.text(pt.styles);
    if (styles) {
      var sd = xml(styles), custom = {}, nf = tags(sd, 'numFmt');
      for (i = 0; i < nf.length; i++) custom[nf[i].getAttribute('numFmtId')] = nf[i].getAttribute('formatCode') || '';
      var xfsNode = tags(sd, 'cellXfs')[0];
      if (xfsNode) {
        for (var x = xfsNode.firstElementChild; x; x = x.nextElementSibling) {
          var id = +x.getAttribute('numFmtId');
          dateStyle.push(!!DATE_IDS[id] || (custom[id] !== undefined && isDateFormat(custom[id])));
        }
      }
    }
    var sheets = [], sheetNodes = tags(wb, 'sheet');
    for (i = 0; i < sheetNodes.length; i++) {
      var s = sheetNodes[i], rid = sheetRid(s);
      var path = rels[rid] || resolve(wbPath, 'worksheets/sheet' + (i + 1) + '.xml');
      var text = zip.text(path);
      if (text === null) continue;
      sheets.push({name: s.getAttribute('name'), path: path, rows: readSheet(xml(text), shared, dateStyle, date1904)});
    }
    return sheets;
  }

  // r:id of a <sheet>, also in Strict Open XML (another namespace) or with another prefix.
  function sheetRid(s) {
    for (var i = 0; i < s.attributes.length; i++) {
      var a = s.attributes[i];
      if (a.localName === 'id' && a.namespaceURI && /relationships$/.test(a.namespaceURI)) return a.value;
    }
    return s.getAttribute('r:id');
  }

  // OpenDocument spreadsheet (.ods, or an .ods saved with an .xlsx name): every table as rows.
  function readOds(zip) {
    var doc = xml(zip.text('content.xml')), sheets = [], tables = tags(doc, 'table');
    function attr(n, name) {
      for (var i = 0; i < n.attributes.length; i++) if (n.attributes[i].localName === name) return n.attributes[i].value;
      return null;
    }
    for (var t = 0; t < tables.length; t++) {
      var rows = [], rowNodes = tags(tables[t], 'table-row');
      for (var r = 0; r < rowNodes.length && rows.length < 1048576; r++) {
        var row = [];
        for (var c = rowNodes[r].firstElementChild; c; c = c.nextElementSibling) {
          if (c.localName !== 'table-cell' && c.localName !== 'covered-table-cell') continue;
          var type = attr(c, 'value-type'), val = null;
          if (type === 'float' || type === 'percentage' || type === 'currency') val = +attr(c, 'value');
          else if (type === 'date') { var m = /^(\d+)-(\d+)-(\d+)(?:T(\d+):(\d+):(\d+))?/.exec(attr(c, 'date-value') || ''); if (m) val = new Date(+m[1], m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0)); }
          else if (type === 'boolean') val = attr(c, 'boolean-value') === 'true' ? 'TRUE' : 'FALSE';
          else if (type) val = Array.prototype.map.call(tags(c, 'p'), function (p) { return p.textContent; }).join('\n') || null;
          var rep = Math.min(+(attr(c, 'number-columns-repeated') || 1), 16384);
          if (val === null && !c.nextElementSibling) break;  // trailing empty cells
          for (var k = 0; k < rep; k++) row.push(val);
        }
        var rrep = Math.min(+(attr(rowNodes[r], 'number-rows-repeated') || 1), 1048576);
        if (!row.length && r === rowNodes.length - 1) break;
        for (k = 0; k < rrep && (row.length || k < 1); k++) rows.push(row.slice());
      }
      while (rows.length && !rows[rows.length - 1].some(function (v) { return v !== null; })) rows.pop();
      sheets.push({name: attr(tables[t], 'name') || ('Sheet' + (t + 1)), rows: rows});
    }
    return sheets;
  }

  function readSheet(doc, shared, dateStyle, date1904) {
    var rows = [], rowNodes = tags(doc, 'row');
    for (var r = 0; r < rowNodes.length; r++) {
      var rn = rowNodes[r], ri = rn.getAttribute('r') ? +rn.getAttribute('r') - 1 : rows.length, row = [], col = 0;
      for (var c = rn.firstElementChild; c; c = c.nextElementSibling) {
        if (c.localName !== 'c') continue;
        var ref = c.getAttribute('r');
        if (ref) col = colIndex(ref);
        var t = c.getAttribute('t') || 'n', v = child(c, 'v'), val = null;
        if (t === 's') val = v ? shared[+v.textContent] : null;
        else if (t === 'inlineStr') { var is = child(c, 'is'); val = is ? stringText(is) : null; }
        else if (t === 'str' || t === 'e') val = v ? v.textContent : null;
        else if (t === 'd') { val = v ? new Date(v.textContent.replace(/Z$/, '')) : null; if (val && isNaN(val)) val = v.textContent; }
        else if (t === 'b') val = v ? (v.textContent === '1' ? 'TRUE' : 'FALSE') : null;
        else if (v && v.textContent !== '') {
          val = +v.textContent;
          if (dateStyle[+(c.getAttribute('s') || 0)] && isFinite(val)) val = serialToDate(val, date1904);
        }
        if (typeof val === 'string' && val === '') val = null;
        row[col] = val;
        col++;
      }
      for (var k = 0; k < row.length; k++) if (row[k] === undefined) row[k] = null;
      rows[ri] = row;
    }
    for (var q = 0; q < rows.length; q++) if (!rows[q]) rows[q] = [];
    return rows;
  }

  // Excel serial day -> Date shown in local time with the same wall-clock digits Excel shows.
  function serialToDate(v, date1904) {
    var ms = Math.round((v + (date1904 ? 1462 : 0) - 25569) * 86400000);
    var d = new Date(ms);
    return new Date(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds());
  }

  function decodeText(buf) {
    var u8 = new Uint8Array(buf);
    try {
      return new TextDecoder('utf-8', {fatal: true}).decode(u8).replace(/^﻿/, '');
    } catch (e) {
      return new TextDecoder('euc-kr').decode(u8);  // Korean Excel saves CSV in CP949
    }
  }

  function readCsv(buf) {
    var text = decodeText(buf), first = text.split(/\r?\n/, 1)[0];
    var delim = [',', '\t', ';'].reduce(function (best, d) { return first.split(d).length > first.split(best).length ? d : best; }, ',');
    var rows = [], row = [], cell = '', q = false;
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      if (q) {
        if (ch === '"') { if (text.charAt(i + 1) === '"') { cell += '"'; i++; } else q = false; }
        else cell += ch;
      } else if (ch === '"') q = true;
      else if (ch === delim) { row.push(cell); cell = ''; }
      else if (ch === '\n' || ch === '\r') {
        if (ch === '\r' && text.charAt(i + 1) === '\n') i++;
        row.push(cell); rows.push(row); row = []; cell = '';
      } else cell += ch;
    }
    if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
    return [{name: 'CSV', rows: rows.map(function (r) {
      return r.map(function (s) {
        s = s.trim();
        if (s === '') return null;
        var n = s.replace(/,/g, '');
        return /^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(n) ? +n : s;
      });
    })}];
  }

  // Some systems save an HTML table with an .xls/.xlsx name; Excel opens it, so read it too.
  function looksHtml(buf) {
    var head = new TextDecoder('latin1').decode(new Uint8Array(buf, 0, Math.min(buf.byteLength, 4096)));
    return /^(\xef\xbb\xbf)?\s*</.test(head) && /<(html|table|!doctype)/i.test(head);
  }

  function readHtml(buf) {
    var doc = new DOMParser().parseFromString(decodeText(buf), 'text/html'), best = null;
    Array.prototype.forEach.call(doc.querySelectorAll('table'), function (t) { if (!best || t.rows.length > best.rows.length) best = t; });
    if (!best) throw new Error('파일 안에 표가 없습니다');
    var rows = Array.prototype.map.call(best.rows, function (tr) {
      return Array.prototype.map.call(tr.cells, function (td) {
        var s = td.textContent.replace(/\u00a0/g, ' ').trim();
        if (s === '') return null;
        var n = s.replace(/,/g, '');
        return /^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(n) ? +n : s;
      });
    });
    return [{name: 'Sheet1', rows: rows}];
  }

  // name decides the format; buf is an ArrayBuffer.
  function read(name, buf) {
    if (/\.(csv|txt|tsv)$/i.test(name)) return readCsv(buf);
    if (/\.html?$/i.test(name) || looksHtml(buf)) return readHtml(buf);
    if (/\.xls$/i.test(name)) throw new Error('.xls(예전 형식)는 읽을 수 없습니다. Excel에서 .xlsx로 다른 이름으로 저장해 주세요');
    return readXlsx(buf);
  }

  // ---------- writing a copy ----------
  var CRC = (function () {
    var t = new Uint32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c >>> 0;
    }
    return t;
  })();
  function crc32(u8) {
    var c = 0xffffffff;
    for (var i = 0; i < u8.length; i++) c = CRC[(c ^ u8[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  // entries: [{name, data (Uint8Array, stored)} or {name, raw, method, crc, usize} (copied as compressed)]
  function zip(entries) {
    var enc = new TextEncoder(), parts = [], central = [], offset = 0;
    entries.forEach(function (e) {
      var name = enc.encode(e.name), data = e.raw || e.data;
      var method = e.raw ? e.method : 0, crc = e.raw ? e.crc : crc32(e.data), usize = e.raw ? e.usize : e.data.length;
      var h = new DataView(new ArrayBuffer(30));
      h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint16(6, 0x0800, true); h.setUint16(8, method, true);
      h.setUint16(10, 0, true); h.setUint16(12, 0x21, true);
      h.setUint32(14, crc, true); h.setUint32(18, data.length, true); h.setUint32(22, usize, true);
      h.setUint16(26, name.length, true); h.setUint16(28, 0, true);
      var c = new DataView(new ArrayBuffer(46));
      c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true); c.setUint16(8, 0x0800, true); c.setUint16(10, method, true);
      c.setUint16(12, 0, true); c.setUint16(14, 0x21, true);
      c.setUint32(16, crc, true); c.setUint32(20, data.length, true); c.setUint32(24, usize, true);
      c.setUint16(28, name.length, true); c.setUint32(42, offset, true);
      parts.push(new Uint8Array(h.buffer), name, data);
      central.push(new Uint8Array(c.buffer), name);
      offset += 30 + name.length + data.length;
    });
    var size = 0;
    central.forEach(function (p) { size += p.length; });
    var end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true); end.setUint16(8, entries.length, true); end.setUint16(10, entries.length, true);
    end.setUint32(12, size, true); end.setUint32(16, offset, true);
    var all = parts.concat(central, [new Uint8Array(end.buffer)]), total = 0;
    all.forEach(function (p) { total += p.length; });
    var out = new Uint8Array(total), at = 0;
    all.forEach(function (p) { out.set(p, at); at += p.length; });
    return out;
  }

  var NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
  var FILL = {yellow: 'FFFFFF00', red: 'FFFF0000'};

  function colRef(i) {
    var s = '';
    for (i++; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + (i - 1) % 26) + s;
    return s;
  }

  function serialize(doc) {
    var s = new XMLSerializer().serializeToString(doc);
    return /^<\?xml/.test(s) ? s : '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + s;
  }

  // Add yellow and red fills to styles.xml; style(orig, colour) gives the cellXfs index of orig with that fill.
  function styler(doc) {
    var fills = tags(doc, 'fills')[0], xfs = tags(doc, 'cellXfs')[0], made = {}, fillId = {};
    Object.keys(FILL).forEach(function (k) {
      var f = doc.createElementNS(NS, 'fill'), p = doc.createElementNS(NS, 'patternFill'), fg = doc.createElementNS(NS, 'fgColor'), bg = doc.createElementNS(NS, 'bgColor');
      p.setAttribute('patternType', 'solid');
      fg.setAttribute('rgb', FILL[k]);
      bg.setAttribute('indexed', '64');
      p.appendChild(fg); p.appendChild(bg); f.appendChild(p); fills.appendChild(f);
      fillId[k] = fills.children.length - 1;
    });
    fills.setAttribute('count', fills.children.length);
    return function (orig, colour) {
      var key = (orig || 0) + colour;
      if (made[key] === undefined) {
        var base = xfs.children[orig || 0], xf = base ? base.cloneNode(true) : doc.createElementNS(NS, 'xf');
        if (!base) { xf.setAttribute('numFmtId', '0'); xf.setAttribute('fontId', '0'); xf.setAttribute('borderId', '0'); }
        xf.setAttribute('fillId', fillId[colour]);
        xf.setAttribute('applyFill', '1');
        xfs.appendChild(xf);
        xfs.setAttribute('count', xfs.children.length);
        made[key] = xfs.children.length - 1;
      }
      return made[key];
    };
  }

  // Patch one sheet of an .xlsx/.xlsm: edits [{row (1-based Excel row), col (0-based), value}], yellow [Excel rows].
  function copyXlsx(buf, sheetPath, edits, yellow) {
    var z = unzip(buf), changed = {}, pt = parts(z);
    var styleText = pt.styles && z.text(pt.styles);
    if (!styleText) throw new Error('엑셀 서식(styles.xml)이 없는 파일이라 색을 넣을 수 없습니다');
    var sdoc = xml(styleText), style = styler(sdoc), doc = xml(z.text(sheetPath));
    var rowsByNum = {}, rowNodes = tags(doc, 'row');
    for (var i = 0; i < rowNodes.length; i++) rowsByNum[rowNodes[i].getAttribute('r')] = rowNodes[i];
    var editAt = {};
    edits.forEach(function (e) { editAt[e.row + ':' + e.col] = e; });
    function cellsOf(rn) {
      var out = {}, col = 0;
      for (var c = rn.firstElementChild; c; c = c.nextElementSibling) {
        if (c.localName !== 'c') continue;
        if (c.getAttribute('r')) col = colIndex(c.getAttribute('r'));
        out[col++] = c;
      }
      return out;
    }
    var yellowSet = {};
    yellow.forEach(function (r) { yellowSet[r] = 1; });
    Object.keys(yellowSet).forEach(function (r) {
      var rn = rowsByNum[r];
      if (!rn) return;
      rn.setAttribute('s', style(+(rn.getAttribute('s') || 0), 'yellow'));
      rn.setAttribute('customFormat', '1');
      var cells = cellsOf(rn);
      Object.keys(cells).forEach(function (col) {
        if (!editAt[r + ':' + col]) cells[col].setAttribute('s', style(+(cells[col].getAttribute('s') || 0), 'yellow'));
      });
    });
    edits.forEach(function (e) {
      var rn = rowsByNum[e.row];
      if (!rn) throw new Error(e.row + '행을 엑셀 파일에서 찾지 못했습니다');
      var c = cellsOf(rn)[e.col];
      if (!c) throw new Error(colRef(e.col) + e.row + ' 칸을 엑셀 파일에서 찾지 못했습니다');
      c.removeAttribute('t');
      while (c.firstChild) c.removeChild(c.firstChild);  // drop formula / inline string
      var v = doc.createElementNS(NS, 'v');
      v.textContent = String(e.value);
      c.appendChild(v);
      c.setAttribute('s', style(+(c.getAttribute('s') || 0), 'red'));
    });
    // changed / drop are keyed by partKey (the zip may spell names differently, issue #25)
    changed[partKey(sheetPath)] = serialize(doc);
    changed[partKey(pt.styles)] = serialize(sdoc);
    // Excel rebuilds the calculation chain; recalculate formulas that used the changed cells.
    var drop = {};
    pt.rels.forEach(function (r) { if (r.type === 'calcChain') drop[partKey(r.target)] = 1; });
    var ct = z.text('[Content_Types].xml');
    if (ct) changed['[content_types].xml'] = ct.replace(/<Override[^>]*PartName="[^"]*calcChain\.xml"[^>]*\/>/i, '');
    var rels = z.text(relsPath(pt.workbook));
    if (rels) changed[partKey(relsPath(pt.workbook))] = rels.replace(/<Relationship[^>]*Target="[^"]*calcChain\.xml"[^>]*\/>/i, '');
    var wb = z.text(pt.workbook);
    if (/<calcPr\b/.test(wb)) changed[partKey(pt.workbook)] = wb.replace(/<calcPr\b/, '<calcPr fullCalcOnLoad="1"').replace(/(<calcPr fullCalcOnLoad="1"[^>]*?)\sfullCalcOnLoad="[^"]*"/, '$1');
    var enc = new TextEncoder(), entries = [];
    Object.keys(z.files).sort(function (a, b) { return z.files[a].order - z.files[b].order; }).forEach(function (name) {
      var key = partKey(name);
      if (drop[key]) return;
      if (changed[key] !== undefined) entries.push({name: name, data: enc.encode(changed[key])});
      else { var f = z.files[name]; entries.push({name: name, raw: z.raw(name), method: f.method, crc: f.crc, usize: f.usize}); }
    });
    return zip(entries);
  }

  function xmlEsc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }

  // New one-sheet .xlsx from rows (for CSV / HTML-table / demo sources).
  function buildXlsx(rows, sheetName, edits, yellow) {
    var editAt = {}, yellowSet = {};
    edits.forEach(function (e) { editAt[e.row + ':' + e.col] = e; });
    yellow.forEach(function (r) { yellowSet[r] = 1; });
    var x = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="' + NS + '"><sheetData>';
    rows.forEach(function (row, ri) {
      var r = ri + 1, ys = yellowSet[r];
      x += '<row r="' + r + '"' + (ys ? ' s="1" customFormat="1"' : '') + '>';
      for (var c = 0; c < row.length; c++) {
        var e = editAt[r + ':' + c], v = e ? e.value : row[c], s = e ? 2 : (ys ? 1 : 0), ref = colRef(c) + r, sa = s ? ' s="' + s + '"' : '';
        if (v === null || v === undefined) { if (s) x += '<c r="' + ref + '"' + sa + '/>'; continue; }
        if (v instanceof Date) v = v.getFullYear() + '-' + ('0' + (v.getMonth() + 1)).slice(-2) + '-' + ('0' + v.getDate()).slice(-2) + ' ' + ('0' + v.getHours()).slice(-2) + ':' + ('0' + v.getMinutes()).slice(-2) + ':' + ('0' + v.getSeconds()).slice(-2);
        if (typeof v === 'number' && isFinite(v)) x += '<c r="' + ref + '"' + sa + '><v>' + v + '</v></c>';
        else x += '<c r="' + ref + '"' + sa + ' t="inlineStr"><is><t xml:space="preserve">' + xmlEsc(v) + '</t></is></c>';
      }
      x += '</row>';
    });
    x += '</sheetData></worksheet>';
    var fill = function (rgb) { return '<fill><patternFill patternType="solid"><fgColor rgb="' + rgb + '"/><bgColor indexed="64"/></patternFill></fill>'; };
    var files = {
      '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
      '_rels/.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
      'xl/workbook.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="' + NS + '" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="' + xmlEsc(String(sheetName || 'Sheet1').slice(0, 31).replace(/[\\\/?*\[\]:]/g, '_')) + '" sheetId="1" r:id="rId1"/></sheets></workbook>',
      'xl/_rels/workbook.xml.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
      'xl/styles.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<styleSheet xmlns="' + NS + '"><fonts count="1"><font><sz val="11"/><name val="맑은 고딕"/></font></fonts><fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>' + fill(FILL.yellow) + fill(FILL.red) + '</fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="2" borderId="0" xfId="0" applyFill="1"/><xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1"/></cellXfs></styleSheet>',
      'xl/worksheets/sheet1.xml': x
    };
    var enc = new TextEncoder();
    return zip(Object.keys(files).map(function (name) { return {name: name, data: enc.encode(files[name])}; }));
  }

  function sheetName(name) { return String(name || 'Sheet').replace(/[\\\/?*\[\]:]/g, '_').slice(0, 31) || 'Sheet'; }

  // New .xlsx with several sheets and a few cell styles (OCAP 삭제 양식, issue #28).
  // sheets: [{name, rows: [[cell]], widths: [column width]}], cell = value or {v: value, s: style name}.
  var BOOK_STYLE = {title: 1, head: 2, cell: 3, text: 4, group: 5, small: 6, option: 7};
  function book(sheets) {
    var used = {};
    sheets.forEach(function (sh) {
      var n = sheetName(sh.name), k = 2;
      while (used[n.toLowerCase()]) n = sheetName(sh.name).slice(0, 27) + ' (' + k++ + ')';
      used[n.toLowerCase()] = 1;
      sh.safe = n;
    });
    var files = {}, ct = '', wbRels = '', wbSheets = '';
    sheets.forEach(function (sh, i) {
      var x = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="' + NS + '">';
      if (sh.widths) x += '<cols>' + sh.widths.map(function (w, c) { return '<col min="' + (c + 1) + '" max="' + (c + 1) + '" width="' + w + '" customWidth="1"/>'; }).join('') + '</cols>';
      x += '<sheetData>';
      sh.rows.forEach(function (row, ri) {
        var r = ri + 1;
        x += '<row r="' + r + '">';
        (row || []).forEach(function (cell, c) {
          var v = cell && typeof cell === 'object' && !(cell instanceof Date) ? cell.v : cell;
          var s = cell && typeof cell === 'object' && cell.s ? BOOK_STYLE[cell.s] : 0, ref = colRef(c) + r, sa = s ? ' s="' + s + '"' : '';
          if (v instanceof Date) v = v.getFullYear() + '-' + ('0' + (v.getMonth() + 1)).slice(-2) + '-' + ('0' + v.getDate()).slice(-2) + ' ' + ('0' + v.getHours()).slice(-2) + ':' + ('0' + v.getMinutes()).slice(-2) + ':' + ('0' + v.getSeconds()).slice(-2);
          if (v === null || v === undefined || v === '') { if (s) x += '<c r="' + ref + '"' + sa + '/>'; }
          else if (typeof v === 'number' && isFinite(v)) x += '<c r="' + ref + '"' + sa + '><v>' + v + '</v></c>';
          else x += '<c r="' + ref + '"' + sa + ' t="inlineStr"><is><t xml:space="preserve">' + xmlEsc(v) + '</t></is></c>';
        });
        x += '</row>';
      });
      x += '</sheetData></worksheet>';
      files['xl/worksheets/sheet' + (i + 1) + '.xml'] = x;
      ct += '<Override PartName="/xl/worksheets/sheet' + (i + 1) + '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>';
      wbRels += '<Relationship Id="rId' + (i + 1) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet' + (i + 1) + '.xml"/>';
      wbSheets += '<sheet name="' + xmlEsc(sh.safe) + '" sheetId="' + (i + 1) + '" r:id="rId' + (i + 1) + '"/>';
    });
    var thin = '<left style="thin"><color auto="1"/></left><right style="thin"><color auto="1"/></right><top style="thin"><color auto="1"/></top><bottom style="thin"><color auto="1"/></bottom><diagonal/>';
    files['[Content_Types].xml'] = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' + ct + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>';
    files['_rels/.rels'] = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>';
    files['xl/workbook.xml'] = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="' + NS + '" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + wbSheets + '</sheets></workbook>';
    files['xl/_rels/workbook.xml.rels'] = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + wbRels + '<Relationship Id="rId' + (sheets.length + 1) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>';
    // xf 1 title (bold, centre), 2 head (grey fill, border, centre), 3 cell (border, centre), 4 text (border, left, wrap),
    // 5 group (centre, no border), 6 small (border, left, 9 pt), 7 option (light blue fill, left, 9 pt)
    files['xl/styles.xml'] = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<styleSheet xmlns="' + NS + '"><fonts count="4"><font><sz val="11"/><name val="맑은 고딕"/></font><font><b/><sz val="11"/><name val="맑은 고딕"/></font><font><sz val="10"/><name val="맑은 고딕"/></font><font><sz val="9"/><name val="맑은 고딕"/></font></fonts>' +
      '<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFAEAAAA"/><bgColor indexed="64"/></patternFill></fill>' +
      '<fill><patternFill patternType="solid"><fgColor rgb="FFDDEBF7"/><bgColor indexed="64"/></patternFill></fill></fills>' +
      '<borders count="2"><border/><border>' + thin + '</border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="8">' +
      '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
      '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>' +
      '<xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>' +
      '<xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>' +
      '<xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>' +
      '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>' +
      '<xf numFmtId="0" fontId="3" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>' +
      '<xf numFmtId="0" fontId="3" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>' +
      '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>';
    var enc = new TextEncoder();
    return zip(Object.keys(files).map(function (name) { return {name: name, data: enc.encode(files[name])}; }));
  }

  // src: {buf, name, sheetPath} for an .xlsx/.xlsm, or {rows, sheetName} for anything else.
  function copy(src, edits, yellow) {
    if (src.buf && src.sheetPath) return copyXlsx(src.buf, src.sheetPath, edits, yellow);
    return buildXlsx(src.rows, src.sheetName, edits, yellow);
  }

  window.XLSXLite = {read: read, copy: copy, book: book, serialToDate: serialToDate};
})();
