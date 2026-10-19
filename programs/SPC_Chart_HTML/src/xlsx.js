// Minimal .xlsx / .xlsm / .csv reader: every sheet as rows of cells (number, string, Date or null).
// Formula cells give the value Excel saved with the file. Needs pako (inflateRaw) for zip entries.
(function () {
  'use strict';

  function unzip(buf) {
    var u8 = new Uint8Array(buf), dv = new DataView(buf), eocd = -1;
    for (var i = u8.length - 22; i >= Math.max(0, u8.length - 65557); i--) {
      if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    }
    if (eocd < 0) throw new Error('엑셀 파일 형식이 아닙니다 (zip 끝을 찾지 못함)');
    var count = dv.getUint16(eocd + 10, true), p = dv.getUint32(eocd + 16, true), files = {};
    var dec = new TextDecoder('utf-8');
    for (var k = 0; k < count; k++) {
      if (dv.getUint32(p, true) !== 0x02014b50) throw new Error('엑셀 파일이 손상되었거나 저장 중입니다');
      var method = dv.getUint16(p + 10, true), size = dv.getUint32(p + 20, true);
      var nameLen = dv.getUint16(p + 28, true), extraLen = dv.getUint16(p + 30, true), commentLen = dv.getUint16(p + 32, true);
      var local = dv.getUint32(p + 42, true), name = dec.decode(u8.subarray(p + 46, p + 46 + nameLen));
      files[name.replace(/^\//, '')] = {method: method, size: size, local: local};
      p += 46 + nameLen + extraLen + commentLen;
    }
    return {
      has: function (name) { return !!files[name]; },
      text: function (name) {
        var f = files[name];
        if (!f) return null;
        var start = f.local + 30 + dv.getUint16(f.local + 26, true) + dv.getUint16(f.local + 28, true);
        var data = u8.subarray(start, start + f.size);
        if (f.method === 8) data = window.pako.inflateRaw(data);
        else if (f.method !== 0) throw new Error('지원하지 않는 압축 방식: ' + f.method);
        return dec.decode(data);
      }
    };
  }

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

  function readXlsx(buf) {
    var zip = unzip(buf);
    var wbPath = 'xl/workbook.xml';
    if (!zip.has(wbPath)) throw new Error('엑셀 통합 문서(.xlsx)가 아닙니다. .xls 파일은 Excel에서 .xlsx로 저장해 주세요');
    var wb = xml(zip.text(wbPath));
    var pr = tags(wb, 'workbookPr')[0], date1904 = pr && /^(1|true)$/.test(pr.getAttribute('date1904') || '');
    var rels = {}, relText = zip.text('xl/_rels/workbook.xml.rels');
    if (relText) {
      var rs = tags(xml(relText), 'Relationship');
      for (var i = 0; i < rs.length; i++) rels[rs[i].getAttribute('Id')] = resolve(wbPath, rs[i].getAttribute('Target'));
    }
    var shared = [], sst = zip.text('xl/sharedStrings.xml');
    if (sst) {
      var sis = tags(xml(sst), 'si');
      for (i = 0; i < sis.length; i++) shared.push(stringText(sis[i]));
    }
    var dateStyle = [], styles = zip.text('xl/styles.xml');
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
      var s = sheetNodes[i], rid = s.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'id') || s.getAttribute('r:id');
      var path = rels[rid] || ('xl/worksheets/sheet' + (i + 1) + '.xml');
      var text = zip.text(path);
      if (text === null) continue;
      sheets.push({name: s.getAttribute('name'), rows: readSheet(xml(text), shared, dateStyle, date1904)});
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

  // name decides the format; buf is an ArrayBuffer.
  function read(name, buf) {
    if (/\.(csv|txt|tsv)$/i.test(name)) return readCsv(buf);
    if (/\.xls$/i.test(name)) throw new Error('.xls(예전 형식)는 읽을 수 없습니다. Excel에서 .xlsx로 다른 이름으로 저장해 주세요');
    return readXlsx(buf);
  }

  window.XLSXLite = {read: read, serialToDate: serialToDate};
})();
