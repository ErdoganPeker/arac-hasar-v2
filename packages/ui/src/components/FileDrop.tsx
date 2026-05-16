import { useCallback, useRef, useState, type ReactNode } from 'react';
import { Upload, X } from 'lucide-react';
import { cn } from '../utils/cn';

/**
 * Generic file dropzone with a react-dropzone-compatible API surface.
 * Implemented on top of the native HTML5 drag-and-drop API so no extra dep is required.
 *
 * Differences vs react-dropzone:
 *   - `accept` is a comma-separated MIME string (browser-native form), not the object form
 *   - No fancy filesystem-access fallback; relies on <input type="file">
 */

export interface FileDropError {
  code: 'file-too-large' | 'too-many-files' | 'invalid-type';
  message: string;
  file?: File;
}

interface Props {
  onFiles: (files: File[]) => void;
  onError?: (error: FileDropError) => void;
  /** Comma-separated accept string, e.g. `"image/jpeg,image/png,image/webp"` */
  accept?: string;
  /** Max bytes per file. Default 12 MB. */
  maxSize?: number;
  maxFiles?: number;
  multiple?: boolean;
  disabled?: boolean;
  className?: string;
  hint?: string;
  children?: ReactNode;
}

const DEFAULT_ACCEPT = 'image/jpeg,image/png,image/webp';
const DEFAULT_MAX_SIZE = 12 * 1024 * 1024; // 12 MB
const DEFAULT_MAX_FILES = 10;

export function FileDrop({
  onFiles,
  onError,
  accept = DEFAULT_ACCEPT,
  maxSize = DEFAULT_MAX_SIZE,
  maxFiles = DEFAULT_MAX_FILES,
  multiple = true,
  disabled,
  className,
  hint,
  children,
}: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const acceptList = accept
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

  const matchesAccept = useCallback(
    (file: File): boolean => {
      if (acceptList.length === 0) return true;
      return acceptList.some((rule) => {
        if (rule.startsWith('.')) return file.name.toLowerCase().endsWith(rule.toLowerCase());
        if (rule.endsWith('/*')) {
          const prefix = rule.slice(0, -1); // keep trailing slash
          return file.type.startsWith(prefix);
        }
        return file.type === rule;
      });
    },
    [acceptList],
  );

  const validate = useCallback(
    (files: File[]): { ok: File[]; error: FileDropError | null } => {
      if (files.length > maxFiles) {
        return {
          ok: [],
          error: {
            code: 'too-many-files',
            message: `En fazla ${maxFiles} dosya yükleyebilirsin.`,
          },
        };
      }
      for (const f of files) {
        if (!matchesAccept(f)) {
          return {
            ok: [],
            error: {
              code: 'invalid-type',
              message: `Desteklenmeyen dosya türü: ${f.name}`,
              file: f,
            },
          };
        }
        if (f.size > maxSize) {
          const mb = Math.round((maxSize / (1024 * 1024)) * 10) / 10;
          return {
            ok: [],
            error: {
              code: 'file-too-large',
              message: `Dosya çok büyük: ${f.name} (>${mb}MB)`,
              file: f,
            },
          };
        }
      }
      return { ok: files, error: null };
    },
    [maxFiles, matchesAccept, maxSize],
  );

  const handleFiles = useCallback(
    (list: FileList | null) => {
      if (!list || list.length === 0) return;
      const files = Array.from(list);
      const { ok, error: err } = validate(files);
      if (err) {
        setError(err.message);
        onError?.(err);
        return;
      }
      setError(null);
      onFiles(ok);
    },
    [onFiles, onError, validate],
  );

  return (
    <div className={cn('w-full', className)}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          if (disabled) return;
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          if (disabled) return;
          e.preventDefault();
          setIsDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        className={cn(
          'flex w-full flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-10 text-center transition-colors',
          isDragging
            ? 'border-brand-500 bg-brand-50'
            : 'border-slate-300 bg-white hover:border-brand-400 hover:bg-slate-50',
          disabled && 'cursor-not-allowed opacity-60',
        )}
      >
        {children ?? (
          <>
            <div className="rounded-full bg-brand-100 p-3">
              <Upload className="h-6 w-6 text-brand-700" aria-hidden />
            </div>
            <div>
              <div className="font-semibold text-slate-900">
                Dosyaları sürükle bırak veya tıkla
              </div>
              <div className="mt-1 text-sm text-slate-500">
                {hint ??
                  `${acceptList.join(', ')} — maks. ${Math.round(maxSize / (1024 * 1024))}MB / dosya`}
              </div>
            </div>
          </>
        )}
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
