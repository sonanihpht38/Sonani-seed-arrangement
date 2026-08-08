// ===================== FRONTEND: generic CRUD screen =====================
// The ~200 lines every list screen used to hand-assemble, once:
//   Card + search + permission-gated toolbar + server-paginated DataGrid +
//   Modal(antd Form) + create/update/delete mutations + column-level RBAC.
//
// A feature screen becomes:
//   <CrudResource<Department>
//     form="hr_departments" title="Departments" queryKey="hr-departments"
//     resource={departmentsApi}
//     columns={[{ field: "name" }, { field: "is_active", headerName: "Active" }]}
//     renderForm={() => (<>
//       <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
//     </>)}
//   />

import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Card, Form, Input, Modal, Pagination, Space } from "antd";
import type { FormInstance } from "antd";
import type { ColDef } from "ag-grid-community";

import type { ListParams } from "../api/types";
import type { ResourceApi } from "../api/resource";
import { useListQuery } from "../api/hooks";
import { useCrud } from "../hooks/useCrud";
import { useAuth } from "../features/auth/useAuth";
import { applyColumnVisibility, useVisibleColumns } from "../features/access/useVisibleColumns";
import { exportToCsv } from "../lib/exportCsv";
import { DataGrid } from "./DataGrid";
import { AddButton, ActionButton, DeleteButton, EditButton } from "./buttons";

export interface CrudResourceProps<T extends { id: number }> {
  /** RBAC form code — gates toolbar/row actions via can() and columns via
   *  the grid-column permissions. */
  form: string;
  title: string;
  /** React Query cache key prefix (invalidated after each mutation). */
  queryKey: string;
  resource: ResourceApi<T>;
  columns: ColDef<T>[];
  /** Fields of the create/edit modal. `editing` is null when creating. */
  renderForm: (form: FormInstance, editing: T | null) => ReactNode;
  /** Map form values -> API body (defaults to the raw form values). */
  toInput?: (values: Record<string, unknown>, editing: T | null) => unknown;
  /** Map a row -> the modal's initial values (defaults to the row itself). */
  toFormValues?: (row: T) => Record<string, unknown>;
  /** Extra fixed query params (e.g. a parent filter). */
  extraParams?: ListParams;
  searchPlaceholder?: string;
  pageSize?: number;
  gridHeight?: number;
  /** Extra toolbar content (right side, before Add). */
  extraToolbar?: ReactNode;
  /** Extra per-row actions rendered before Edit/Delete. */
  rowActions?: (row: T) => ReactNode;
  /** CSV export columns ({key, header}); enables the Export button when the
   *  user has the export permission. */
  exportColumns?: Array<{ key: string; header: string }>;
  /** Disable row deletion (e.g. rows with protective server rules). */
  canDeleteRow?: (row: T) => boolean;
}

export function CrudResource<T extends { id: number }>({
  form: formCode,
  title,
  queryKey,
  resource,
  columns,
  renderForm,
  toInput,
  toFormValues,
  extraParams,
  searchPlaceholder = "Search…",
  pageSize = 20,
  gridHeight = 480,
  extraToolbar,
  rowActions,
  exportColumns,
  canDeleteRow,
}: CrudResourceProps<T>) {
  const { can } = useAuth();
  const [antdForm] = Form.useForm();
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(pageSize);
  const [q, setQ] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<T | null>(null);

  // DRF SearchFilter's query param — TenantCrudViewSet modules declare
  // `search_fields` and get toolbar search for free.
  const params: ListParams = { page, page_size: size, ...(q ? { search: q } : {}), ...extraParams };
  const listQ = useListQuery<T>(queryKey, `${resource.basePath}/`, params);
  const { create, update, remove } = useCrud<T>(queryKey, resource);
  const visibleQ = useVisibleColumns(formCode);

  const openCreate = () => {
    setEditing(null);
    antdForm.resetFields();
    setModalOpen(true);
  };
  const openEdit = (row: T) => {
    setEditing(row);
    antdForm.resetFields();
    antdForm.setFieldsValue(toFormValues ? toFormValues(row) : (row as Record<string, unknown>));
    setModalOpen(true);
  };
  const submit = async () => {
    const values = await antdForm.validateFields();
    const body = toInput ? toInput(values, editing) : values;
    if (editing) await update.mutateAsync({ id: editing.id, body: body as Partial<T> });
    else await create.mutateAsync(body as T);
    setModalOpen(false);
  };

  const gridColumns = useMemo(() => {
    const cols = applyColumnVisibility(columns, visibleQ.data);
    if (!rowActions && !can(formCode, "edit") && !can(formCode, "delete")) return cols;
    const actions: ColDef<T> = {
      headerName: "Actions",
      colId: "__actions",
      sortable: false,
      filter: false,
      minWidth: 180,
      cellRenderer: (p: { data?: T }) =>
        p.data ? (
          <Space>
            {rowActions?.(p.data)}
            {can(formCode, "edit") && (
              <EditButton size="small" onClick={() => openEdit(p.data as T)} />
            )}
            {can(formCode, "delete") && (canDeleteRow ? canDeleteRow(p.data) : true) && (
              <DeleteButton size="small" onConfirm={() => remove.mutate((p.data as T).id)} />
            )}
          </Space>
        ) : null,
    };
    return [...cols, actions];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [columns, visibleQ.data, can, formCode, rowActions, canDeleteRow]);

  const rows = listQ.data?.results ?? [];
  const total = listQ.data?.total ?? 0;

  return (
    <Card
      title={title}
      extra={
        <Space>
          <Input.Search
            allowClear
            placeholder={searchPlaceholder}
            style={{ width: 240 }}
            onSearch={(value) => { setQ(value.trim()); setPage(1); }}
          />
          {exportColumns && can(formCode, "export") && (
            <ActionButton onClick={() => exportToCsv(`${queryKey}.csv`, rows as Record<string, unknown>[], exportColumns)}>
              Export
            </ActionButton>
          )}
          {extraToolbar}
          {can(formCode, "create") && <AddButton onClick={openCreate} />}
        </Space>
      }
    >
      <DataGrid<T>
        rowData={rows}
        columnDefs={gridColumns}
        loading={listQ.isPending}
        height={gridHeight}
        paginated={false}
      />
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
        <Pagination
          current={page}
          pageSize={size}
          total={total}
          showSizeChanger
          showTotal={(t) => `${t} total`}
          onChange={(p, s) => { setPage(p); setSize(s); }}
        />
      </div>

      <Modal
        title={editing ? `Edit ${title}` : `New ${title}`}
        open={modalOpen}
        onOk={submit}
        confirmLoading={create.isPending || update.isPending}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Form form={antdForm} layout="vertical" preserve={false}>
          {renderForm(antdForm, editing)}
        </Form>
      </Modal>
    </Card>
  );
}
