interface MaterialIconProps {
  /** Google Fonts Material Symbols ikon adı, örn. "villa", "explore". */
  name: string;
  size?: number;
  className?: string;
}

/**
 * Google Fonts'taki Material Symbols (Outlined) fontunu kullanan ikon —
 * index.html'de yüklenen "Material Symbols Outlined" font-face'e bağlı.
 */
export function MaterialIcon({ name, size = 20, className = "" }: MaterialIconProps) {
  return (
    <span
      aria-hidden="true"
      className={`material-symbols-outlined select-none leading-none ${className}`}
      style={{
        fontSize: size,
        fontVariationSettings: `'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' ${size}`,
      }}
    >
      {name}
    </span>
  );
}
