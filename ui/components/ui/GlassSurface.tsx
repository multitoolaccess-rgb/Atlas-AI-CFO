export default function GlassSurface({
  children,
  className = '',
  borderColor,
}: {
  children: React.ReactNode;
  className?: string;
  borderColor?: string;
}) {
  return (
    <div
      className={`glass-surface p-6 rounded-xl flex flex-col justify-between h-32 ${
        borderColor
          ? `border-l-4 border-l-${borderColor}`
          : ''
      } ${className}`}
    >
      {children}
    </div>
  );
}