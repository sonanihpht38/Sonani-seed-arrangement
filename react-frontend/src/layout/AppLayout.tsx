// Authenticated shell. The sidebar menu is built DYNAMICALLY from the backend
// catalogue (/access/catalogue -> module groups -> forms): each visible form
// becomes a menu entry whose icon comes from the form's stored `icon` value and
// whose target is the form's `route`. Groups render as headings. Items the user
// can't view (can(form.code)) are hidden; the server still enforces access.
//
// Adding a screen is data, not code: declare a FormDef with an icon + route in
// the module's catalogue.py, run `sync_catalogue`, and it appears here.

import { useEffect, useMemo, useRef, useState } from "react";
import { Layout, Menu, Avatar, Dropdown, Typography, Spin, Button, Space, theme } from "antd";
import type { MenuProps } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../features/auth/useAuth";
import { accessApi } from "../features/access/accessApi";
import { Logo, LogoMark } from "../components/Logo";
import { AppIcon, FiUser, FiLogOut, FiMenu } from "../components/icons";
import { NotificationBell } from "../features/notifications/NotificationBell";
import { colors } from "../theme";
import "./sidebar.css";

const { Header, Sider, Content } = Layout;

export function AppLayout() {
  const { user, logout, can } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const { token } = theme.useToken();

  const catalogueQ = useQuery({ queryKey: ["catalogue"], queryFn: accessApi.catalogue });

  // Build the menu from the catalogue: each module group is a COLLAPSIBLE submenu
  // (own expand/collapse chevron) whose children are the forms the user can view.
  // De-dupe forms that share a route so a screen appears once. When the whole
  // Sider is collapsed, only the group icons show and hovering pops the children.
  const items: MenuProps["items"] = useMemo(() => {
    // Menu keys are the routes and must be globally unique. De-dupe by route
    // across ALL groups (a route can be reused by several forms / in >1 group);
    // the first occurrence wins so each screen appears once.
    const seen = new Set<string>();
    return (catalogueQ.data ?? [])
      .map((group) => {
        const children = group.forms
          .filter((f) => f.is_active && f.route && can(f.code))
          .filter((f) => (seen.has(f.route) ? false : (seen.add(f.route), true)))
          .map((f) => ({ key: f.route, icon: <AppIcon name={f.icon} size={18} />, label: f.name }));
        return children.length
          ? {
              key: `group:${group.code}`,
              icon: <AppIcon name={group.icon} size={18} />,
              label: group.name,
              children, // presence of children => antd renders a collapsible submenu
            }
          : null;
      })
      .filter(Boolean) as MenuProps["items"];
  }, [catalogueQ.data, can]);

  // Which group submenus are expanded. Open them all once the catalogue loads;
  // after that the user's manual expand/collapse is respected.
  const [openKeys, setOpenKeys] = useState<string[]>([]);
  const openedOnce = useRef(false);
  useEffect(() => {
    if (catalogueQ.data && !openedOnce.current) {
      setOpenKeys(catalogueQ.data.map((g) => `group:${g.code}`));
      openedOnce.current = true;
    }
  }, [catalogueQ.data]);

  const selectedKey = location.pathname;

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed} trigger={null}
        theme="light" width={240} style={{ borderRight: `1px solid ${colors.border}` }}>
        {/* Brand: the wordmark carries the product name, so there is no separate
            text heading. Collapsed, the Sider is 80px — too narrow for a 4.4:1
            wordmark — so the mark alone stands in. */}
        <div style={{ height: 56, margin: "12px 16px", display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "flex-start", overflow: "hidden" }}>
          {collapsed ? <LogoMark size={28} /> : <Logo height={36} />}
        </div>
        {catalogueQ.isLoading ? (
          <div style={{ display: "grid", placeItems: "center", padding: 24 }}>
            <Spin />
          </div>
        ) : (
          <Menu
            theme="light"
            mode="inline"
            selectedKeys={[selectedKey]}
            openKeys={collapsed ? undefined : openKeys}
            onOpenChange={(keys) => setOpenKeys(keys as string[])}
            items={items}
            onClick={({ key }) => { if (!key.startsWith("group:")) navigate(key); }}
            style={{ borderInlineEnd: "none" }}
          />
        )}
      </Sider>

      <Layout>
        <Header style={{ background: token.colorBgContainer, borderBottom: `1px solid ${colors.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", paddingInline: 16 }}>
          <Button
            type="text"
            aria-label="Toggle menu"
            icon={<FiMenu size={20} />}
            onClick={() => setCollapsed((c) => !c)}
          />
          <Space size="large">
            <NotificationBell />
            <Dropdown
              menu={{
                items: [{ key: "logout", icon: <FiLogOut />, label: "Sign out", onClick: logout }],
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <Avatar size="small" icon={<FiUser />} />
                <Typography.Text strong>{user?.full_name || user?.username}</Typography.Text>
                {user?.is_superuser && <Typography.Text type="secondary">(admin)</Typography.Text>}
              </div>
            </Dropdown>
          </Space>
        </Header>

        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
