// Base UI component barrel exports.
// All primitives live in /components/ui/ and are re-exported here so that
// consumers can `import { Button, Modal } from '@/components/ui'`.

// Existing components
export { default as Button }       from './Button';
export { default as GlassSurface } from './GlassSurface';
export { default as StatCard }     from './StatCard';
export { default as ErrorBanner }  from './ErrorBanner';

// New base components
export { default as Badge }        from './Badge';
export { default as ProgressBar }  from './ProgressBar';
export { default as Input }        from './Input';
export { default as Select }       from './Select';
export { default as Modal }        from './Modal';
export { default as Tooltip }      from './Tooltip';
export { default as TabsGroup }    from './TabsGroup';
export { default as Dropdown }     from './Dropdown';

export { default as CountUp } from './CountUp';
export { default as Card } from './Card';
export { default as AnimatedSection } from './AnimatedSection';
export { default as Spinner, Skeleton } from './Spinner';
export { default as CommandPalette, useCommandPalette } from './CommandPalette';

// CategoryChip re-exports — the file hosts TWO components
// (CategoryChip + CategoryDot). Both surface via this barrel so
// callers can `import { CategoryChip, CategoryDot } from
// '@/components/ui'`. The activity page uses CategoryDot for
// list-item colour swatches; settings + accounts use CategoryChip.
export { CategoryChip, CategoryDot } from './CategoryChip';
