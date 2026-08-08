// All user messaging + confirmations go through react-toastify (per project
// convention). `notify.*` are one-liners for success/error/info; `confirmToast`
// renders an inline toast with Confirm / Cancel buttons for destructive actions
// so we never block on a native window.confirm.

import { toast, type Id } from "react-toastify";
import { Button, Space } from "antd";

export const notify = {
  success: (msg: string) => toast.success(msg),
  error: (msg: string) => toast.error(msg),
  info: (msg: string) => toast.info(msg),
  warning: (msg: string) => toast.warning(msg),
};

interface ConfirmOptions {
  okText?: string;
  cancelText?: string;
  danger?: boolean;
}

/** Show a confirmation toast; runs `onConfirm` only if the user clicks Confirm. */
export function confirmToast(
  message: string,
  onConfirm: () => void,
  { okText = "Confirm", cancelText = "Cancel", danger = true }: ConfirmOptions = {},
): Id {
  return toast(
    ({ closeToast }) => (
      <div>
        <div style={{ marginBottom: 10 }}>{message}</div>
        <Space style={{ display: "flex", justifyContent: "flex-end" }}>
          <Button size="small" onClick={closeToast}>
            {cancelText}
          </Button>
          <Button
            size="small"
            type="primary"
            danger={danger}
            onClick={() => {
              closeToast?.();
              onConfirm();
            }}
          >
            {okText}
          </Button>
        </Space>
      </div>
    ),
    { autoClose: false, closeOnClick: false, closeButton: false, draggable: false },
  );
}
