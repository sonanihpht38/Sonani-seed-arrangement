// ===================== Standard action buttons =====================
// One place that defines what "Add / Edit / Delete / Save / ..." look and behave
// like, so every screen uses the same icon, colour, and wording. Each wrapper
// spreads through all antd ButtonProps (size, loading, disabled, block, ...), so
// row-action buttons just pass `size="small"`.
//
// DeleteButton bakes in the confirmation step (toastify) — deletes are always
// confirmed, consistently, without each screen re-implementing it.

import type { ReactNode } from "react";
import { Button } from "antd";
import type { ButtonProps } from "antd";
import {
  FiPlus, FiEdit2, FiTrash2, FiSave, FiRefreshCw, FiEye, FiX,
} from "./icons";
import { confirmToast } from "../lib/notify";

// Callers pick the semantic button, not its type/danger/icon.
type BtnProps = Omit<ButtonProps, "type" | "danger" | "icon">;

export function AddButton({ children = "Add", ...rest }: BtnProps) {
  return <Button type="primary" icon={<FiPlus />} {...rest}>{children}</Button>;
}

export function EditButton({ children = "Edit", ...rest }: BtnProps) {
  return <Button icon={<FiEdit2 />} {...rest}>{children}</Button>;
}

export function SaveButton({ children = "Save", ...rest }: BtnProps) {
  return <Button type="primary" icon={<FiSave />} {...rest}>{children}</Button>;
}

export function CancelButton({ children = "Cancel", ...rest }: BtnProps) {
  return <Button icon={<FiX />} {...rest}>{children}</Button>;
}

export function RefreshButton({ children = "Refresh", ...rest }: BtnProps) {
  return <Button icon={<FiRefreshCw />} {...rest}>{children}</Button>;
}

export function ViewButton({ children = "View", ...rest }: BtnProps) {
  return <Button icon={<FiEye />} {...rest}>{children}</Button>;
}

interface DeleteButtonProps extends BtnProps {
  /** Called only after the user confirms. */
  onConfirm: () => void;
  /** Confirmation prompt shown in the toast. */
  confirm?: string;
  children?: ReactNode;
}

export function DeleteButton({
  onConfirm,
  confirm = "Are you sure you want to delete this? This cannot be undone.",
  children = "Delete",
  ...rest
}: DeleteButtonProps) {
  return (
    <Button danger icon={<FiTrash2 />} {...rest} onClick={() => confirmToast(confirm, onConfirm)}>
      {children}
    </Button>
  );
}

/** Generic labelled button for actions without a dedicated wrapper (Manage,
 *  Revoke, Assign, ...). Keeps styling consistent; caller supplies icon/type. */
export function ActionButton({ children, ...rest }: ButtonProps) {
  return <Button {...rest}>{children}</Button>;
}
