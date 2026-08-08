// Minimal client-side CSV export — download the given rows as a .csv file.

interface Column {
  key: string;
  header: string;
}

export function exportToCsv(filename: string, rows: Record<string, unknown>[], columns: Column[]) {
  const escape = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = columns.map((c) => escape(c.header)).join(",");
  const body = rows.map((r) => columns.map((c) => escape(r[c.key])).join(",")).join("\n");
  const csv = `${header}\n${body}`;

  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
