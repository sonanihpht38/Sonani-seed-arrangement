// ===================== Icon management (react-icons) =====================
// One place that owns iconography. We use the Feather set (react-icons/fi) for a
// consistent look. `ICONS` is the registry the pickers offer and that stored
// module-group/form `icon` values resolve against; `AppIcon` renders one by name.
//
// Fixed UI icons (buttons, nav, login) are re-exported here too, so the rest of
// the app imports icons from this module — not directly from a vendor package.

import type { ComponentType } from "react";
import {
  FiSettings, FiShield, FiUsers, FiUser, FiLock, FiSearch, FiPlus, FiEdit2,
  FiTrash2, FiSave, FiX, FiRefreshCw, FiEye, FiCopy, FiCode, FiBarChart2,
  FiFolder, FiBox, FiKey, FiGrid, FiHome, FiFileText, FiDatabase, FiDollarSign,
  FiShoppingCart, FiTruck, FiClipboard, FiCalendar, FiMail, FiLogOut, FiPackage,
  FiMenu, FiDownload, FiUpload, FiBell, FiCheck, FiStar, FiArchive,
  FiInfo, FiArrowRight, FiZap,
} from "react-icons/fi";

type IconCmp = ComponentType<{ size?: number; className?: string }>;

// Selectable icons (registry). Keys are the values stored on module groups/forms.
export const ICONS: Record<string, IconCmp> = {
  settings: FiSettings,
  admin: FiShield,
  shield: FiShield,
  users: FiUsers,
  user: FiUser,
  chart: FiBarChart2,
  report: FiBarChart2,
  api: FiCode,
  key: FiKey,
  folder: FiFolder,
  module: FiBox,
  package: FiPackage,
  grid: FiGrid,
  home: FiHome,
  file: FiFileText,
  database: FiDatabase,
  finance: FiDollarSign,
  sales: FiShoppingCart,
  inventory: FiTruck,
  tasks: FiClipboard,
  calendar: FiCalendar,
  mail: FiMail,
  check: FiCheck,
};

export const ICON_NAMES = Object.keys(ICONS);

/** Render a registry icon by name; falls back to a neutral box for unknowns. */
export function AppIcon({ name, size = 16 }: { name?: string | null; size?: number }) {
  const Cmp = (name && ICONS[name]) || FiBox;
  return <Cmp size={size} />;
}

// Fixed UI icons re-exported so the app imports iconography from one module.
export {
  FiSettings, FiShield, FiUsers, FiUser, FiLock, FiSearch, FiPlus, FiEdit2,
  FiTrash2, FiSave, FiX, FiRefreshCw, FiEye, FiCopy, FiCode, FiGrid, FiLogOut,
  FiMenu, FiDownload, FiUpload, FiBell, FiCheck, FiCalendar, FiStar, FiArchive,
  FiInfo, FiArrowRight, FiPackage, FiZap,
};
