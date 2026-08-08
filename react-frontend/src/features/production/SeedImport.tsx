// ===================== FRONTEND: Seed Import =====================
// Step 1 of the plate-arrangement workflow. Upload a seed datasheet (.xlsx / .xls
// ONLY) and post it to the production module, which parses the sheet, auto-creates
// any new batches, skips duplicate stock numbers, and inserts the new rows into
// TRN_SeedData. The result (imported / skipped / batches created) is shown here.
// The Import action is gated on the seed_import form's "save" permission.
//
// Expected Excel columns (positional, row 1 = header):
//   BatchNo · StockNo · Pcs · Cts · Length · Width · Height

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Card, Space, Upload, Button, Tag, Alert, Statistic, Row, Col, Typography, Empty } from "antd";
import type { UploadProps } from "antd";
import type { ColDef } from "ag-grid-community";
import { useAuth } from "../auth/useAuth";
import { productionApi } from "./productionApi";
import type { ImportResult, SkippedSeed } from "./types";
import { DataGrid } from "../../components/DataGrid";
import { FiUpload, FiCheck, FiInfo, FiArrowRight } from "../../components/icons";
import { notify } from "../../lib/notify";
import { colors, alpha } from "../../theme";

const { Text } = Typography;
const EXCEL_EXT = /\.(xlsx|xls)$/i;

const reasonTag = (r: string) => (
  <Tag color={r === "Entry already exists" ? "orange" : "red"}>{r}</Tag>
);

export function SeedImport() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const canImport = can("seed_import", "save");

  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);

  const importMut = useMutation({
    mutationFn: (f: File) => productionApi.importSeeds(f),
    onSuccess: (data) => {
      setResult(data);
      notify.success(`Imported ${data.imported} seed${data.imported === 1 ? "" : "s"}.`);
    },
    onError: (e) => notify.error(e instanceof Error ? e.message : "Import failed"),
  });

  // Accept Excel only; reject anything else before it enters the list, and return
  // false so antd never auto-uploads — we POST manually on the Import click.
  const beforeUpload: UploadProps["beforeUpload"] = (f) => {
    if (!EXCEL_EXT.test(f.name)) {
      notify.error("Only Excel files (.xlsx, .xls) are allowed.");
      return Upload.LIST_IGNORE;
    }
    setFile(f);
    setResult(null);
    return false;
  };

  const clear = () => {
    setFile(null);
    setResult(null);
  };

  const skippedCols: ColDef<SkippedSeed>[] = useMemo(() => [
    { headerName: "Stock No", field: "stock_no", flex: 1 },
    { headerName: "Batch No", field: "batch_no", maxWidth: 180 },
    {
      headerName: "Reason", field: "reason", flex: 1,
      cellRenderer: (p: { value: string }) => reasonTag(p.value),
    },
  ], []);

  return (
    <Space direction="vertical" size="large" style={{ display: "flex" }}>
      <Card title="Seed Import">
        <Alert
          showIcon
          icon={<FiInfo size={18} style={{ color: colors.primary }} />}
          style={{ marginBottom: 16, background: alpha(colors.primary, 0.06), border: `1px solid ${alpha(colors.primary, 0.2)}` }}
          message="Excel format (columns in this order, row 1 = header)"
          description={<Text code>BatchNo · StockNo · Pcs · Cts · Length · Width · Height</Text>}
        />

        <Upload.Dragger
          multiple={false}
          maxCount={1}
          accept=".xlsx,.xls"
          beforeUpload={beforeUpload}
          onRemove={clear}
          disabled={importMut.isPending}
          fileList={file ? [{ uid: "1", name: file.name, status: "done" }] : []}
        >
          <p className="ant-upload-drag-icon" style={{ display: "flex", justifyContent: "center" }}>
            <FiUpload size={40} />
          </p>
          <p className="ant-upload-text">Click or drag an Excel file to upload</p>
          <p className="ant-upload-hint">Only .xlsx / .xls files are accepted.</p>
        </Upload.Dragger>

        <Space style={{ marginTop: 16 }}>
          <Button
            type="primary"
            icon={<FiUpload />}
            loading={importMut.isPending}
            disabled={!file || !canImport}
            onClick={() => file && importMut.mutate(file)}
          >
            {importMut.isPending ? "Importing…" : "Import"}
          </Button>
          {file && !importMut.isPending && <Button icon={<FiCheck />} onClick={clear}>Clear</Button>}
        </Space>
        {!canImport && (
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">You don't have permission to import seeds.</Text>
          </div>
        )}
      </Card>

      {result && (
        <Card title="Import result">
          <Row gutter={32}>
            <Col>
              <Statistic title="Imported" value={result.imported} valueStyle={{ color: colors.primary }} />
            </Col>
            <Col>
              <Statistic title="Skipped" value={result.skipped_count} valueStyle={{ color: result.skipped_count ? colors.danger : undefined }} />
            </Col>
            <Col>
              <Statistic title="Batches" value={result.batches.length} />
            </Col>
          </Row>

          {result.batches.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Text strong>Batches ({result.batches.length})</Text>
              <Row gutter={[12, 12]} style={{ marginTop: 8 }}>
                {result.batches.map((b) => (
                  <Col key={b.batch_no ?? "—"} xs={24} sm={12} md={8} lg={6}>
                    <div style={{ border: `1px solid ${colors.border}`, borderRadius: 8, padding: "10px 12px", background: colors.surface, height: "100%" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                        <Text strong style={{ flex: 1, minWidth: 0 }} ellipsis={{ tooltip: b.batch_no || "—" }}>{b.batch_no || "—"}</Text>
                        {b.is_new
                          ? <Tag style={{ margin: 0, background: colors.primary, color: "#fff", border: "none" }}>new</Tag>
                          : <Tag style={{ margin: 0 }}>existing</Tag>}
                      </div>
                      <Text type="secondary">{b.imported_count} seed{b.imported_count === 1 ? "" : "s"}</Text>
                    </div>
                  </Col>
                ))}
              </Row>
            </div>
          )}

          <div style={{ marginTop: 16 }}>
            <Text strong>Skipped rows</Text>
            {result.skipped.length > 0 ? (
              <div style={{ marginTop: 8 }}>
                <DataGrid rowData={result.skipped} columnDefs={skippedCols} height={280} />
              </div>
            ) : (
              <Empty description="No rows were skipped." image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </div>
        </Card>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <Button
          type="primary"
          onClick={() => navigate("/production/batch-selection")}
          style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
        >
          Next: Batch Selection <FiArrowRight />
        </Button>
      </div>
    </Space>
  );
}
