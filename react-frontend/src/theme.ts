// ============================ Design System ============================
// Single source of truth for Sonani's visual language, based on the Skydash
// palette. Components reference these tokens (via the antd ConfigProvider) — no
// hardcoded hexes. Keep the palette small and calm: 5 brand colors + neutrals.

export const colors = {
  // ---- Brand palette (Skydash) ----
  primary: "#4B49AC",       // violet-blue — primary actions, active nav, links
  primaryLight: "#98BDFF",  // sail blue — secondary / soft accent
  info: "#7DA0FA",          // light blue — informational
  violet: "#7978E9",        // supporting violet — accents, charts
  danger: "#F3797E",        // tonys pink — destructive / errors

  // ---- Neutrals ----
  bg: "#f5f6fa",            // app / page background
  surface: "#ffffff",       // cards, sider, header
  text: "#1f2430",          // primary text
  textMuted: "#6c7383",     // secondary text
  border: "#eceef3",        // hairlines
};

/** hex -> rgba() with alpha, for subtle tints (hover/selected states). */
export function alpha(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

// antd ConfigProvider theme — the "reuse" layer: setting these once restyles
// every antd component (buttons, links, tags, menu, inputs, ...) consistently.
export const antdTheme = {
  token: {
    colorPrimary: colors.primary,
    colorInfo: colors.info,
    colorError: colors.danger,
    colorLink: colors.primary,
    colorTextBase: colors.text,
    colorBgLayout: colors.bg,
    borderRadius: 8,
    fontFamily:
      "'Segoe UI', Roboto, -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif",
  },
  components: {
    Layout: {
      siderBg: colors.surface,
      headerBg: colors.surface,
      bodyBg: colors.bg,
      triggerBg: colors.surface,
      triggerColor: colors.textMuted,
    },
    Menu: {
      // Skydash sidebar: solid violet pill for the active item (white text/icon),
      // muted grey idle items, soft violet hover, comfortable row height.
      itemColor: "#4c5566",
      itemHoverColor: colors.primary,
      itemHoverBg: alpha(colors.primary, 0.08),
      itemSelectedColor: "#ffffff",
      itemSelectedBg: colors.primary,
      itemActiveBg: alpha(colors.primary, 0.12),
      itemBorderRadius: 8,
      itemHeight: 46,
      itemMarginInline: 12,
      itemMarginBlock: 4,
      iconSize: 18,
      iconMarginInlineEnd: 12,
      groupTitleColor: "#9aa0ac",
      groupTitleFontSize: 11,
    },
    Card: {
      borderRadiusLG: 12,
      headerBg: "transparent",
      headerFontSize: 16,
    },
    Button: {
      controlHeight: 36,
      primaryShadow: "none",
      fontWeight: 500,
    },
  },
};
