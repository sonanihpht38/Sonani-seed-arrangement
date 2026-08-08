// Top-bar notification bell: unread badge + a popover list. Polls the unread
// count so newly-arrived notifications surface without a refresh.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Popover, Button, List, Typography, Empty, Tag, Spin } from "antd";
import { useNavigate } from "react-router-dom";
import { FiBell, FiCheck } from "../../components/icons";
import { notificationsApi, type AppNotification, type NotificationLevel } from "./notificationsApi";

const LEVEL_COLOR: Record<NotificationLevel, string> = {
  info: "blue", success: "green", warning: "gold", error: "red",
};

export function NotificationBell() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  // Poll the count every 30s; refetch the list whenever the popover opens.
  const countQ = useQuery({
    queryKey: ["notif-count"],
    queryFn: notificationsApi.unreadCount,
    refetchInterval: 30_000,
  });
  const listQ = useQuery({
    queryKey: ["notif-list"],
    queryFn: notificationsApi.list,
    enabled: open,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["notif-count"] });
    qc.invalidateQueries({ queryKey: ["notif-list"] });
  };

  const markRead = useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id),
    onSuccess: invalidate,
  });
  const markAll = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: invalidate,
  });

  const unread = countQ.data?.count ?? 0;

  function onItemClick(n: AppNotification) {
    if (!n.is_read) markRead.mutate(n.id);
    if (n.link) { setOpen(false); navigate(n.link); }
  }

  const content = (
    <div style={{ width: 340, maxHeight: 420, overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <Typography.Text strong>Notifications</Typography.Text>
        <Button type="link" size="small" icon={<FiCheck />} disabled={!unread || markAll.isPending}
          onClick={() => markAll.mutate()}>
          Mark all read
        </Button>
      </div>
      {listQ.isLoading ? (
        <div style={{ textAlign: "center", padding: 24 }}><Spin /></div>
      ) : (listQ.data?.length ?? 0) === 0 ? (
        <Empty description="No notifications" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          size="small"
          dataSource={listQ.data ?? []}
          renderItem={(n) => (
            <List.Item
              onClick={() => onItemClick(n)}
              style={{
                cursor: "pointer", alignItems: "flex-start",
                background: n.is_read ? undefined : "rgba(75,73,172,0.06)",
                paddingInline: 8, borderRadius: 6,
              }}
            >
              <List.Item.Meta
                title={
                  <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <Tag color={LEVEL_COLOR[n.level]} style={{ marginInlineEnd: 0 }}>{n.level}</Tag>
                    <Typography.Text strong={!n.is_read}>{n.title}</Typography.Text>
                  </span>
                }
                description={
                  <>
                    {n.message && <div style={{ fontSize: 12 }}>{n.message}</div>}
                    <div style={{ fontSize: 11, color: "#9aa0ac" }}>{new Date(n.created_at).toLocaleString()}</div>
                  </>
                }
              />
            </List.Item>
          )}
        />
      )}
    </div>
  );

  return (
    <Popover content={content} trigger="click" open={open} onOpenChange={setOpen}
      placement="bottomRight" arrow={false}>
      <Badge count={unread} size="small" offset={[-2, 4]}>
        <Button type="text" aria-label="Notifications" icon={<FiBell size={18} />} />
      </Badge>
    </Popover>
  );
}
