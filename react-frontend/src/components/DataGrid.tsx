// Reusable AG Grid (Community) wrapper with our house defaults: quartz theme,
// sortable/filterable/resizable columns, client-side pagination. Feature screens
// just pass `rowData` + `columnDefs`.

import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";

// Default grid height: FILL the viewport rather than a fixed box.
//
// 360 px showed ten rows and left a screen's worth of white space underneath on
// anything bigger than a laptop. A taller fixed number only moves the problem —
// it overflows the short screens instead. This leaves room for the app chrome
// and gives the rest to the rows:
//
//   header 64 + Content margins 48 + card head ~56 + card padding ~48
//   + a screen's alert/toolbar ~104  ≈  320
//
// minHeight keeps it usable when the viewport is short; below that the page
// scrolls, which is the right failure.
const FILL_HEIGHT = "calc(100vh - 320px)";
const MIN_HEIGHT = 380;

interface DataGridProps<T> {
  rowData: T[];
  columnDefs: ColDef<T>[];
  /** Number of px, or any CSS length. Defaults to filling the viewport. */
  height?: number | string;
  /** Floor for the fill height, so a short screen still shows useful rows. */
  minHeight?: number;
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
  height = FILL_HEIGHT,
  minHeight = MIN_HEIGHT,
  pageSize = 10,
  loading = false,
  onRowClicked,
  paginated = true,
  autoHeight = false,
}: DataGridProps<T>) {
  return (
    <div
      className="ag-theme-quartz"
      style={{ width: "100%", ...(autoHeight ? {} : { height, minHeight }) }}
    >
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
        // 100 added: a taller grid only shows more rows if the PAGE can supply
        // them. At a page size of 10 the extra height is just blank space below
        // the tenth row.
        paginationPageSizeSelector={paginated ? [10, 25, 50, 100] : undefined}
        animateRows
        loading={loading}
        onRowClicked={onRowClicked ? (e) => e.data && onRowClicked(e.data) : undefined}
        rowStyle={onRowClicked ? { cursor: "pointer" } : undefined}
      />
    </div>
  );
}
