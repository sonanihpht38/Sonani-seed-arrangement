// ===================== FRONTEND: Plate Master =====================
// Plate-name inventory master (MST_SeedPlate). Users enter the plates they own
// (name + diameter). At finalize time the plate names are picked from this pool,
// and their ISUsed / IsReleased status shows here. Gated on the plate_master form.

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, Space, Tag, Modal, Form, Input, InputNumber, Switch } from "antd";
import type { ColDef } from "ag-grid-community";
import { useAuth } from "../auth/useAuth";
import { productionApi } from "./productionApi";
import type { SeedPlate } from "./types";
import { DataGrid } from "../../components/DataGrid";
import { AddButton, EditButton, DeleteButton } from "../../components/buttons";
import { notify } from "../../lib/notify";

const activeTag = (v: boolean) => <Tag color={v ? "green" : "red"}>{v ? "active" : "inactive"}</Tag>;
const statusTag = (p: SeedPlate) =>
  p.is_used && !p.is_released
    ? <Tag color="orange">in use</Tag>
    : <Tag color="blue">available</Tag>;

export function PlateMaster() {
  const { can } = useAuth();
  const canSave = can("plate_master", "save");
  const canUpdate = can("plate_master", "update");
  const canDelete = can("plate_master", "delete");
  const qc = useQueryClient();
  const [modal, setModal] = useState<SeedPlate | "new" | null>(null);
  const [form] = Form.useForm();

  const platesQ = useQuery({ queryKey: ["plate-master"], queryFn: productionApi.listPlateMaster });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["plate-master"] });

  const saveMut = useMutation({
    mutationFn: (v: { plate_name: string; diameter?: number | null; is_active: boolean; plate_id?: number }) =>
      v.plate_id ? productionApi.updatePlate(v.plate_id, v) : productionApi.createPlate(v),
    onSuccess: () => { notify.success("Plate saved"); setModal(null); form.resetFields(); invalidate(); },
    onError: (e) => notify.error(e instanceof Error ? e.message : "Save failed"),
  });
  const delMut = useMutation({
    mutationFn: (id: number) => productionApi.deletePlate(id),
    onSuccess: () => { notify.success("Plate deleted"); invalidate(); },
    onError: (e) => notify.error(e instanceof Error ? e.message : "Delete failed"),
  });

  function open(p: SeedPlate | "new") {
    setModal(p);
    form.setFieldsValue(
      p === "new"
        ? { plate_name: "", diameter: null, is_active: true }
        : { plate_name: p.plate_name, diameter: p.diameter, is_active: p.is_active },
    );
  }

  const cols: ColDef<SeedPlate>[] = useMemo(() => [
    { headerName: "Plate name", field: "plate_name", flex: 1 },
    { headerName: "Diameter (mm)", field: "diameter", maxWidth: 160 },
    { headerName: "Active", field: "is_active", maxWidth: 120, cellRenderer: (p: { value: boolean }) => activeTag(p.value) },
    { headerName: "Status", maxWidth: 140, cellRenderer: (p: { data: SeedPlate }) => statusTag(p.data) },
    {
      headerName: "Actions", minWidth: 200, sortable: false, filter: false,
      cellRenderer: (p: { data: SeedPlate }) => (
        <Space size={4}>
          {canUpdate && <EditButton size="small" onClick={() => open(p.data)} />}
          {canDelete && (
            <DeleteButton size="small" confirm={`Delete plate "${p.data.plate_name}"?`}
              onConfirm={() => delMut.mutate(p.data.plate_id)} />
          )}
        </Space>
      ),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [canUpdate, canDelete]);

  return (
    <Space direction="vertical" size="large" style={{ display: "flex" }}>
      <Card
        title="Plate Master"
        loading={platesQ.isLoading}
        extra={canSave && <AddButton onClick={() => open("new")}>New plate</AddButton>}
      >
        <DataGrid rowData={platesQ.data ?? []} columnDefs={cols} />
      </Card>

      <Modal
        title={modal === "new" ? "New plate" : "Edit plate"}
        open={Boolean(modal)}
        onCancel={() => setModal(null)}
        onOk={() => form.submit()}
        confirmLoading={saveMut.isPending}
        okText="Save"
      >
        <Form
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={(v) => saveMut.mutate({ ...v, plate_id: modal !== "new" && modal ? modal.plate_id : undefined })}
        >
          <Form.Item name="plate_name" label="Plate name" rules={[{ required: true, message: "Required" }]}>
            <Input placeholder="e.g. P1-90" maxLength={50} />
          </Form.Item>
          <Form.Item name="diameter" label="Diameter (mm)">
            <InputNumber min={0} step={1} style={{ width: "100%" }} placeholder="e.g. 90" />
          </Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
