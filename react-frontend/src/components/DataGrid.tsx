// Reusable AG Grid (Community) wrapper with our house defaults: quartz theme,
// sortable/filterable/resizable columns, client-side pagination. Feature screens
// just pass `rowData` + `columnDefs`.

import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";

interface DataGridProps<T> {
  rowData: T[];
  columnDefs: ColDef<T>[];
  height?: number;
  pageSize?: number;
  loading?: boolean;
  /** Optional: called with the row's data when a row is clicked. When set, rows
   *  show a pointer cursor. */
  onRowClicked?: (data: T) => void;
  /** Set false to disable AG Grid's client-side pagination — e.g. when the data
   *  is already a server-fed page. Defaults to true. */
  paginated?: boolean;
  /** Grow to fit every row (no fixed height / vertical scrollbar). Ignores `height`. */
  autoHeight?: boolean;
}

export function DataGrid<T>({
  rowData,
  columnDefs,
  height = 360,
  pageSize = 10,
  loading = false,
  onRowClicked,
  paginated = true,
  autoHeight = false,
}: DataGridProps<T>) {
  return (
    <div className="ag-theme-quartz" style={{ width: "100%", ...(autoHeight ? {} : { height }) }}>
      <AgGridReact<T>
        rowData={rowData}
        columnDefs={columnDefs}
        // flex fills the width when there's room; minWidth stops columns from
        // shrinking into each other — once totals exceed the width, AG Grid shows
        // a horizontal scrollbar instead of overlapping/truncating content.
        defaultColDef={{ sortable: true, filter: true, resizable: true, flex: 1, minWidth: 140 }}
        domLayout={autoHeight ? "autoHeight" : "normal"}
        pagination={paginated}
        paginationPageSize={pageSize}
        paginationPageSizeSelector={paginated ? [10, 25, 50] : undefined}
        animateRows
        loading={loading}
        onRowClicked={onRowClicked ? (e) => e.data && onRowClicked(e.data) : undefined}
        rowStyle={onRowClicked ? { cursor: "pointer" } : undefined}
      />
    </div>
  );
}
