import { useMemo, useState, type ReactNode } from "react";
import { useLocalization } from "../../core/localization/localizationContext";
import { Button, EmptyState, ErrorState, IconButton, LoadingState } from "./primitives";
import { Icon } from "./Icon";

export interface DataTableColumn<T> {
  key: string;
  label: string;
  accessor?: (row: T) => string | number;
  render?: (row: T) => ReactNode;
  sortable?: boolean;
  hideable?: boolean;
  width?: string;
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  rowKey: (row: T) => string;
  search?: string;
  pageSize?: number;
  loading?: boolean;
  error?: { title: string; description: string };
  empty?: { title: string; description?: string; action?: ReactNode };
  toolbar?: ReactNode;
  bulkActions?: ReactNode | ((selectedRows: T[]) => ReactNode);
  onRowClick?: (row: T) => void;
  exportName?: string;
}

type SortDirection = "asc" | "desc";

const downloadCsv = <T,>(rows: T[], columns: DataTableColumn<T>[], fileName: string): void => {
  const escape = (value: string | number): string => `"${String(value).replaceAll('"', '""')}"`;
  const header = columns.map((column) => escape(column.label)).join(",");
  const lines = rows.map((row) => columns.map((column) => escape(column.accessor?.(row) ?? "")).join(","));
  const blob = new Blob([[header, ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${fileName}.csv`;
  link.click();
  URL.revokeObjectURL(url);
};

export function DataTable<T>({ columns, data, rowKey, search = "", pageSize = 6, loading = false, error, empty, toolbar, bulkActions, onRowClick, exportName = "tekarai-export" }: DataTableProps<T>): JSX.Element {
  const { t } = useLocalization();
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [page, setPage] = useState(1);
  const [visibleKeys, setVisibleKeys] = useState(() => new Set(columns.filter((column) => column.hideable !== false).map((column) => column.key)));
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showColumns, setShowColumns] = useState(false);

  const visibleColumns = columns.filter((column) => visibleKeys.has(column.key));
  const filteredData = useMemo(() => {
    const query = search.trim().toLowerCase();
    const filtered = query.length === 0 ? data : data.filter((row) => columns.some((column) => String(column.accessor?.(row) ?? "").toLowerCase().includes(query)));
    if (!sortKey) return filtered;
    const column = columns.find((item) => item.key === sortKey);
    if (!column) return filtered;
    return [...filtered].sort((left, right) => {
      const a = String(column.accessor?.(left) ?? "").toLowerCase();
      const b = String(column.accessor?.(right) ?? "").toLowerCase();
      const result = a.localeCompare(b, undefined, { numeric: true });
      return sortDirection === "asc" ? result : -result;
    });
  }, [columns, data, search, sortDirection, sortKey]);
  const pageCount = Math.max(1, Math.ceil(filteredData.length / pageSize));
  const safePage = Math.min(page, pageCount);
  const pageRows = filteredData.slice((safePage - 1) * pageSize, safePage * pageSize);
  const pageKeys = pageRows.map(rowKey);
  const allPageSelected = pageKeys.length > 0 && pageKeys.every((key) => selected.has(key));
  const selectedRows = data.filter((row) => selected.has(rowKey(row)));

  const toggleSort = (key: string): void => {
    if (sortKey === key) setSortDirection((direction) => direction === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDirection("asc"); }
  };
  const toggleRow = (key: string): void => setSelected((current) => { const next = new Set(current); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  const togglePage = (): void => setSelected((current) => { const next = new Set(current); pageKeys.forEach((key) => allPageSelected ? next.delete(key) : next.add(key)); return next; });
  const toggleColumn = (key: string): void => setVisibleKeys((current) => { const next = new Set(current); if (next.has(key)) { if (next.size > 1) next.delete(key); } else next.add(key); return next; });

  if (loading) return <LoadingState label={t("common.loading")} />;
  if (error) return <ErrorState title={error.title} description={error.description} />;
  if (data.length === 0) return <EmptyState icon="table" title={empty?.title ?? t("common.noResults")} description={empty?.description} action={empty?.action} />;

  return <div className="table-shell">
    <div className="table-toolbar">
      <div className="table-toolbar__left">{selected.size > 0 && <span className="selection-count">{selected.size} {t("common.selected")}</span>}{bulkActions && selected.size > 0 && (typeof bulkActions === "function" ? bulkActions(selectedRows) : bulkActions)}</div>
      <div className="table-toolbar__right">
        {toolbar}
        <div className="table-menu-wrap"><Button variant="ghost" size="sm" icon="table" onClick={() => setShowColumns((open) => !open)} aria-expanded={showColumns}>Columns</Button>{showColumns && <div className="table-menu" role="menu">{columns.filter((column) => column.hideable !== false).map((column) => <label key={column.key} className="table-menu__item"><input type="checkbox" checked={visibleKeys.has(column.key)} onChange={() => toggleColumn(column.key)} />{column.label}</label>)}</div>}</div>
        <Button variant="ghost" size="sm" icon="download" onClick={() => downloadCsv(filteredData, visibleColumns, exportName)}>{t("common.export")}</Button>
      </div>
    </div>
    <div className="table-scroll"><table className="data-table"><thead><tr><th className="data-table__check"><input type="checkbox" aria-label="Select all rows on page" checked={allPageSelected} onChange={togglePage} /></th>{visibleColumns.map((column) => <th key={column.key} style={{ width: column.width }}>{column.sortable ? <button type="button" className="sort-button" onClick={() => toggleSort(column.key)}>{column.label}<Icon name={sortKey === column.key && sortDirection === "desc" ? "chevronDown" : "chevronUp"} size={13} /></button> : column.label}</th>)}</tr></thead><tbody>{pageRows.map((row) => <tr key={rowKey(row)} className={onRowClick ? "is-clickable" : ""} onClick={() => onRowClick?.(row)}><td className="data-table__check" onClick={(event) => event.stopPropagation()}><input type="checkbox" aria-label={`Select row ${rowKey(row)}`} checked={selected.has(rowKey(row))} onChange={() => toggleRow(rowKey(row))} /></td>{visibleColumns.map((column) => <td key={column.key}>{column.render ? column.render(row) : column.accessor?.(row)}</td>)}</tr>)}</tbody></table></div>
    <div className="table-pagination"><span>{t("common.page")} {safePage} {t("common.of")} {pageCount} · {filteredData.length} {t("common.selected")}</span><div className="table-pagination__actions"><IconButton icon="chevronLeft" label={t("common.previous")} disabled={safePage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} /><IconButton icon="chevronRight" label={t("common.next")} disabled={safePage >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))} /></div></div>
  </div>;
}
