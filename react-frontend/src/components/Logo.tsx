// Brand assets.
//
// `Logo` is the full wordmark (faceted mark + "SONANI") from public/erp-logo.png.
// It replaces the old inline-SVG mark + text heading everywhere the brand is
// shown at full width: the sidebar header and the auth cards.
//
// `LogoMark` is that same mark alone, still inline SVG. The wordmark is 528x120
// (4.4:1), so it cannot render legibly in the 80px collapsed sidebar rail — the
// mark stands in there.

/** Full wordmark. Width follows the image's 4.4:1 aspect from the given height. */
export function Logo({ height = 40 }: { height?: number }) {
  return (
    <img
      src="/erp-logo.png"
      alt="Sonani Seed Arrangement"
      // Height drives the size; width: auto preserves the aspect ratio, and
      // max-width keeps it inside a narrow container (e.g. the 240px sidebar)
      // rather than overflowing it.
      style={{ height, width: "auto", maxWidth: "100%", display: "block", objectFit: "contain" }}
    />
  );
}

interface LogoMarkProps {
  size?: number;
  title?: string;
}

/** The mark on its own — for places too narrow for the wordmark. */
export function LogoMark({ size = 40, title = "Sonani" }: LogoMarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" role="img" aria-label={title}>
      <title>{title}</title>
      {/* Star tips */}
      <polygon points="50,4 38,29.2 62,29.2" fill="#f5821f" />
      <polygon points="86,34 62,29.2 74,50" fill="#e8442c" />
      <polygon points="86,66 74,50 62,70.8" fill="#f7c31c" />
      <polygon points="50,96 62,70.8 38,70.8" fill="#3b4ea0" />
      <polygon points="14,66 38,70.8 26,50" fill="#ec6aa0" />
      <polygon points="14,34 26,50 38,29.2" fill="#3aa9e0" />
      {/* Inner ring facets (around the white core) */}
      <polygon points="38,29.2 62,29.2 50,50" fill="#5bc8f5" />
      <polygon points="62,29.2 74,50 50,50" fill="#f5821f" />
      <polygon points="74,50 62,70.8 50,50" fill="#ec6aa0" />
      <polygon points="62,70.8 38,70.8 50,50" fill="#e8442c" />
      <polygon points="38,70.8 26,50 50,50" fill="#f7c31c" />
      <polygon points="26,50 38,29.2 50,50" fill="#3b4ea0" />
      {/* White core */}
      <polygon points="62,50 56,39.6 44,39.6 38,50 44,60.4 56,60.4" fill="#ffffff" />
    </svg>
  );
}
