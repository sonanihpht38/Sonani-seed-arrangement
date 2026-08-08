// ===================== FRONTEND: CRUD mutations hook =====================
// The standard create/update/remove trio for a resource: success toast +
// query invalidation baked in. Errors are toasted globally by queryClient.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ResourceApi } from "../api/resource";
import { notify } from "../lib/notify";

export function useCrud<T, TInput = Partial<T>>(
  queryKey: string,
  resource: ResourceApi<T, TInput>,
  labels?: { created?: string; updated?: string; deleted?: string },
) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: [queryKey] });

  const create = useMutation({
    mutationFn: (body: TInput) => resource.create(body),
    onSuccess: () => { notify.success(labels?.created ?? "Created."); invalidate(); },
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<TInput> }) => resource.update(id, body),
    onSuccess: () => { notify.success(labels?.updated ?? "Saved."); invalidate(); },
  });
  const remove = useMutation({
    mutationFn: (id: number) => resource.remove(id),
    onSuccess: () => { notify.success(labels?.deleted ?? "Deleted."); invalidate(); },
  });

  return { create, update, remove, invalidate };
}
