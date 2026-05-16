/**
 * Lightweight CSV exporter for the Reports module.
 *
 * Intentionally no external dependency — the input shape is always a flat
 * array of records and the headers are explicit so consumers stay in control
 * of column order and labels.
 */

type CsvValue = string | number | boolean | null | undefined;

export interface CsvColumn<TRow> {
  header: string;
  /** Returns the cell value for a row. Falsy values become empty strings. */
  accessor: (row: TRow) => CsvValue;
}

function escapeCell(value: CsvValue): string {
  if (value === null || value === undefined) {
    return '';
  }
  const str = String(value);
  // RFC 4180: wrap in quotes when the cell contains a comma, quote, or newline,
  // and double up any embedded quotes.
  if (/[",\n\r]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

export function toCsv<TRow>(rows: TRow[], columns: CsvColumn<TRow>[]): string {
  const header = columns.map((c) => escapeCell(c.header)).join(',');
  const body = rows
    .map((row) =>
      columns.map((col) => escapeCell(col.accessor(row))).join(',')
    )
    .join('\n');
  return body.length ? `${header}\n${body}` : header;
}

/**
 * Triggers a browser download of the given CSV string.
 *
 * The filename is suffixed with today's ISO date when no override is supplied
 * (e.g. `sales-trends.csv` → `sales-trends-2026-05-14.csv`).
 */
export function downloadCsv(
  filename: string,
  csv: string,
  options: { stampDate?: boolean } = { stampDate: true }
): void {
  let finalName = filename;
  if (options.stampDate !== false) {
    const today = new Date().toISOString().slice(0, 10);
    finalName = filename.endsWith('.csv')
      ? filename.replace(/\.csv$/, `-${today}.csv`)
      : `${filename}-${today}.csv`;
  }

  // Prepend a BOM so Excel opens UTF-8 CSVs correctly.
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = finalName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/** Convenience: build + download in a single call. */
export function exportCsv<TRow>(
  filename: string,
  rows: TRow[],
  columns: CsvColumn<TRow>[]
): void {
  downloadCsv(filename, toCsv(rows, columns));
}
