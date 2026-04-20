import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, FileText, Folder, Upload } from 'lucide-react'
import { toast } from 'sonner'
import {
  getWorkspaceFile,
  getWorkspaceTree,
  ingestWorkspaceFiles,
  putWorkspaceFile,
} from '@/api/workspace'
import { useAppStore } from '@/stores/useAppStore'
import type { WorkspaceNode } from '@/types/api'

const LTM_SECTIONS = ['decisions', 'research', 'people', 'concepts', 'patterns'] as const
type LtmSection = (typeof LTM_SECTIONS)[number]

// ---------------------------------------------------------------------------
// File tree node
// ---------------------------------------------------------------------------

function TreeNode({
  node,
  selectedPath,
  onSelect,
  depth,
}: {
  node: WorkspaceNode
  selectedPath: string | null
  onSelect: (path: string) => void
  depth: number
}) {
  const [open, setOpen] = useState(depth < 2)

  if (node.type === 'file') {
    return (
      <button
        onClick={() => onSelect(node.path)}
        className={[
          'flex w-full items-center gap-1.5 rounded px-2 py-0.5 text-left text-xs',
          selectedPath === node.path
            ? 'bg-zinc-700 text-zinc-100'
            : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200',
        ].join(' ')}
        style={{ paddingLeft: `${8 + depth * 12}px` }}
      >
        <FileText size={11} className="flex-shrink-0 text-zinc-500" />
        {node.name}
      </button>
    )
  }

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1 rounded px-2 py-0.5 text-left text-xs
                   text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
        style={{ paddingLeft: `${8 + depth * 12}px` }}
      >
        {open ? (
          <ChevronDown size={11} className="flex-shrink-0" />
        ) : (
          <ChevronRight size={11} className="flex-shrink-0" />
        )}
        <Folder size={11} className="flex-shrink-0 text-zinc-500" />
        {node.name}
      </button>
      {open && node.children && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              selectedPath={selectedPath}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Ingestion panel
// ---------------------------------------------------------------------------

function IngestPanel({
  projectId,
  onDone,
}: {
  projectId: number
  onDone: () => void
}) {
  const qc = useQueryClient()
  const [section, setSection] = useState<LtmSection>('decisions')
  const [files, setFiles] = useState<File[]>([])
  const fileRef = useRef<HTMLInputElement>(null)

  const ingestMutation = useMutation({
    mutationFn: () => ingestWorkspaceFiles(projectId, section, files),
    onSuccess: (result) => {
      const imported = result.imported.length
      const skipped = result.skipped.length
      if (imported > 0) {
        toast.success(`Imported ${imported} file${imported !== 1 ? 's' : ''} into ${section}`)
        void qc.invalidateQueries({ queryKey: ['workspaceTree', projectId] })
        void qc.invalidateQueries({ queryKey: ['notifications'] })
      }
      if (skipped > 0) {
        toast.warning(`${skipped} file${skipped !== 1 ? 's' : ''} skipped — see details`)
      }
      if (result.errors.length > 0) {
        toast.error(`${result.errors.length} error(s) during import`)
      }
      setFiles([])
      if (fileRef.current) fileRef.current.value = ''
      if (imported > 0) onDone()
    },
    onError: (err) =>
      toast.error(`Import failed: ${err instanceof Error ? err.message : String(err)}`),
  })

  return (
    <div className="space-y-3 rounded-lg border border-zinc-700 bg-zinc-900 p-4">
      <h3 className="text-sm font-medium text-zinc-200">Import to Brain</h3>
      <p className="text-xs text-zinc-500">
        Upload .md files directly into a long-term memory section. Files are imported as-is — no
        LLM processing. Max 512 KB per file.
      </p>

      <div className="space-y-2">
        <label className="block text-xs text-zinc-400">Section</label>
        <select
          value={section}
          onChange={(e) => setSection(e.target.value as LtmSection)}
          className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5
                     text-xs text-zinc-200 outline-none focus:border-zinc-500"
        >
          {LTM_SECTIONS.map((s) => (
            <option key={s} value={s}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <label className="block text-xs text-zinc-400">Markdown files</label>
        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".md,text/markdown"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          className="w-full text-xs text-zinc-400 file:mr-2 file:rounded file:border-0
                     file:bg-zinc-700 file:px-2 file:py-1 file:text-xs file:text-zinc-200
                     file:cursor-pointer"
        />
        {files.length > 0 && (
          <p className="text-xs text-zinc-500">
            {files.length} file{files.length !== 1 ? 's' : ''} selected
          </p>
        )}
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => ingestMutation.mutate()}
          disabled={files.length === 0 || ingestMutation.isPending}
          className="flex items-center gap-1.5 rounded bg-zinc-700 px-3 py-1.5 text-xs
                     text-zinc-200 hover:bg-zinc-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Upload size={11} />
          {ingestMutation.isPending ? 'Importing…' : 'Import'}
        </button>
        <button
          onClick={onDone}
          className="rounded px-3 py-1.5 text-xs text-zinc-500 hover:text-zinc-300"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// File editor panel
// ---------------------------------------------------------------------------

function FileEditor({
  projectId,
  path,
}: {
  projectId: number
  path: string
}) {
  const [editMode, setEditMode] = useState(false)
  const [draft, setDraft] = useState('')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['workspaceFile', projectId, path],
    queryFn: () => getWorkspaceFile(projectId, path),
    staleTime: 30_000,
  })

  const saveMutation = useMutation({
    mutationFn: () => putWorkspaceFile(projectId, path, draft),
    onSuccess: () => {
      toast.success('Saved')
      setEditMode(false)
    },
    onError: (err) =>
      toast.error(`Save failed: ${err instanceof Error ? err.message : String(err)}`),
  })

  const handleEdit = () => {
    setDraft(data?.content ?? '')
    setEditMode(true)
  }

  const handleCancel = () => {
    setEditMode(false)
    setDraft('')
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <span className="text-xs text-zinc-600">Loading…</span>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex h-full items-center justify-center">
        <span className="text-xs text-zinc-600">Failed to load file.</span>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex flex-shrink-0 items-center justify-between border-b border-zinc-800 px-4 py-2">
        <span className="font-mono text-xs text-zinc-500">{path}</span>
        <div className="flex gap-2">
          {editMode ? (
            <>
              <button
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className="rounded bg-zinc-700 px-3 py-1 text-xs text-zinc-200
                           hover:bg-zinc-600 disabled:opacity-50"
              >
                {saveMutation.isPending ? 'Saving…' : 'Save'}
              </button>
              <button
                onClick={handleCancel}
                className="rounded px-3 py-1 text-xs text-zinc-500 hover:text-zinc-300"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              onClick={handleEdit}
              className="rounded bg-zinc-800 px-3 py-1 text-xs text-zinc-400
                         hover:bg-zinc-700 hover:text-zinc-200"
            >
              Edit
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      {editMode ? (
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="flex-1 resize-none bg-zinc-950 p-4 font-mono text-xs
                     text-zinc-200 outline-none"
          spellCheck={false}
        />
      ) : (
        <pre className="flex-1 overflow-auto p-4 font-mono text-xs text-zinc-300 whitespace-pre-wrap break-words">
          {data?.content}
        </pre>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Brain() {
  const activeProjectId = useAppStore((s) => s.activeProjectId)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [showIngest, setShowIngest] = useState(false)

  const { data: tree, isLoading } = useQuery({
    queryKey: ['workspaceTree', activeProjectId],
    queryFn: () => getWorkspaceTree(activeProjectId!),
    enabled: activeProjectId !== null,
    staleTime: 30_000,
  })

  if (activeProjectId === null) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-zinc-600">No project selected.</p>
      </div>
    )
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: tree + import button */}
      <aside className="flex w-56 flex-shrink-0 flex-col border-r border-zinc-800 bg-zinc-950">
        <div className="flex flex-shrink-0 items-center justify-between border-b border-zinc-800 px-3 py-3">
          <span className="text-sm font-medium text-zinc-300">Brain</span>
          <button
            onClick={() => setShowIngest((v) => !v)}
            title="Import files"
            className={[
              'rounded p-1 transition-colors',
              showIngest
                ? 'bg-zinc-700 text-zinc-200'
                : 'text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300',
            ].join(' ')}
          >
            <Upload size={13} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          {isLoading ? (
            <p className="px-3 text-xs text-zinc-600">Loading…</p>
          ) : !tree || tree.nodes.length === 0 ? (
            <p className="px-3 text-xs text-zinc-600">No workspace files found.</p>
          ) : (
            tree.nodes.map((node) => (
              <TreeNode
                key={node.path}
                node={node}
                selectedPath={selectedPath}
                onSelect={setSelectedPath}
                depth={0}
              />
            ))
          )}
        </div>
      </aside>

      {/* Right: editor or ingest panel */}
      <main className="flex flex-1 flex-col overflow-hidden bg-zinc-950">
        {showIngest ? (
          <div className="flex-1 overflow-y-auto p-6">
            <IngestPanel
              projectId={activeProjectId}
              onDone={() => setShowIngest(false)}
            />
          </div>
        ) : selectedPath ? (
          <FileEditor projectId={activeProjectId} path={selectedPath} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3">
            <p className="text-sm text-zinc-600">Select a file to read or edit.</p>
            <button
              onClick={() => setShowIngest(true)}
              className="flex items-center gap-1.5 rounded border border-zinc-800 px-3 py-1.5
                         text-xs text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
            >
              <Upload size={11} />
              Import markdown files
            </button>
          </div>
        )}
      </main>
    </div>
  )
}
