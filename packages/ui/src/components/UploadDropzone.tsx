import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Upload, X, ImageIcon } from 'lucide-react';
import { cn } from '../utils/cn';

interface Props {
  onFiles: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
  maxFiles?: number;
  maxSizeMb?: number;
  className?: string;
  hint?: string;
}

export function UploadDropzone({
  onFiles,
  accept = 'image/jpeg,image/png,image/webp',
  multiple = true,
  maxFiles = 10,
  maxSizeMb = 12,
  className,
  hint = 'JPG, PNG, WEBP — maks. 12MB / dosya',
}: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validate = useCallback(
    (files: File[]): { ok: File[]; error: string | null } => {
      if (files.length > maxFiles) {
        return { ok: [], error: `En fazla ${maxFiles} dosya yükleyebilirsin.` };
      }
      const maxBytes = maxSizeMb * 1024 * 1024;
      const oversized = files.find((f) => f.size > maxBytes);
      if (oversized) {
        return { ok: [], error: `Dosya çok büyük: ${oversized.name} (>${maxSizeMb}MB)` };
      }
      const wrongType = files.find((f) => !f.type.startsWith('image/'));
      if (wrongType) {
        return { ok: [], error: `Görüntü değil: ${wrongType.name}` };
      }
      return { ok: files, error: null };
    },
    [maxFiles, maxSizeMb],
  );

  const handleFiles = useCallback(
    (list: FileList | null) => {
      if (!list) return;
      const files = Array.from(list);
      const { ok, error: err } = validate(files);
      if (err) {
        setError(err);
        return;
      }
      setError(null);
      onFiles(ok);
    },
    [onFiles, validate],
  );

  return (
    <div className={cn('w-full', className)}>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        className={cn(
          'flex w-full flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-10 text-center transition-colors',
          isDragging
            ? 'border-brand-500 bg-brand-50'
            : 'border-slate-300 bg-white hover:border-brand-400 hover:bg-slate-50',
        )}
      >
        <div className="rounded-full bg-brand-100 p-3">
          <Upload className="h-6 w-6 text-brand-700" aria-hidden />
        </div>
        <div>
          <div className="font-semibold text-slate-900">
            Görüntüleri sürükle bırak veya tıkla
          </div>
          <div className="mt-1 text-sm text-slate-500">{hint}</div>
        </div>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        className="sr-only"
        onChange={(e) => handleFiles(e.target.files)}
      />
      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-800 ring-1 ring-red-200">
          <X className="mt-0.5 h-4 w-4 flex-none" aria-hidden />
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="ml-auto text-xs underline"
          >
            kapat
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Generate stable object URLs for File[] and revoke them on cleanup to
 * avoid memory leaks. Each File gets one URL for its lifetime in the list.
 */
function useFilePreviewUrls(files: File[]): string[] {
  // Cache URL per File reference; rebuild whenever files array identity changes.
  const urls = useMemo(
    () => files.map((f) => (f.type.startsWith('image/') ? URL.createObjectURL(f) : '')),
    [files],
  );

  useEffect(() => {
    return () => {
      urls.forEach((u) => {
        if (u) URL.revokeObjectURL(u);
      });
    };
  }, [urls]);

  return urls;
}

export function FilePreview({
  files,
  onRemove,
  className,
}: {
  files: File[];
  onRemove?: (index: number) => void;
  className?: string;
}) {
  const urls = useFilePreviewUrls(files);
  if (files.length === 0) return null;
  return (
    <div className={cn('grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4', className)}>
      {files.map((f, i) => {
        const url = urls[i];
        const isImage = f.type.startsWith('image/');
        return (
          <div key={i} className="relative aspect-square overflow-hidden rounded-lg bg-slate-100">
            {isImage && url ? (
              // Blob URLs cannot be served by next/image optimizer; render
              // raw <img>. URL.revokeObjectURL cleanup is handled by
              // useFilePreviewUrls above.
              // eslint-disable-next-line @next/next/no-img-element
              <img src={url} alt={f.name} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center">
                <ImageIcon className="h-8 w-8 text-slate-400" aria-hidden />
              </div>
            )}
            {onRemove && (
              <button
                type="button"
                onClick={() => onRemove(i)}
                className="absolute right-1 top-1 rounded-full bg-black/60 p-1 text-white hover:bg-black/80"
                aria-label={`${f.name} kaldır`}
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
