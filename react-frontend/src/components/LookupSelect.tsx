// ===================== Reusable lookup box (dropdown) =====================
// One place that defines how every "lookup" select looks and behaves, so the
// whole app is consistent — callers just pass `options` (or `mode`, `value`,
// `onChange`, …). Key behaviours baked in here:
//   * popupMatchSelectWidth={false} — the dropdown grows to fit its content, so
//     option labels are never truncated ("Plann…"), however narrow the box is.
//   * showSearch + optionFilterProp="label" — type-to-filter on the visible text.
//   * a sensible minimum width; callers can still pass `style` to widen / fill.

import { Select } from "antd";
import type { SelectProps } from "antd";

export function LookupSelect({ style, ...props }: SelectProps) {
  return (
    <Select
      showSearch
      optionFilterProp="label"
      popupMatchSelectWidth={false}
      style={{ minWidth: 140, ...style }}
      {...props}
    />
  );
}
