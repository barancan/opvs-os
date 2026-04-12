import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, X } from 'lucide-react'
import { toast } from 'sonner'
import {
  addLinearLink,
  createProject,
  listProjects,
  removeLinearLink,
  updateProject,
} from '@/api/projects'
import { Button } from '@/components/ui/button'
import type { LinearLink, Project, ProjectUpdate } from '@/types/api'

// ---------------------------------------------------------------------------
// Active project card
// ---------------------------------------------------------------------------

function ProjectCard({ project }: { project: Project }) {
  const qc = useQueryClient()
  const [editingName, setEditingName] = useState(false)
  const [nameValue, setNameValue] = useState(project.name)
  const [descValue, setDescValue] = useState(project.description ?? '')
  const [showLinkForm, setShowLinkForm] = useState(false)
  const [newLinkId, setNewLinkId] = useState('')
  const [newLinkName, setNewLinkName] = useState('')

  const invalidateProjects = () => {
    void qc.invalidateQueries({ queryKey: ['projects'] })
  }

  const updateMutation = useMutation({
    mutationFn: (data: ProjectUpdate) => updateProject(project.id, data),
    onSuccess: invalidateProjects,
    onError: (err) =>
      toast.error(`Update failed: ${err instanceof Error ? err.message : String(err)}`),
  })

  const addLinkMutation = useMutation({
    mutationFn: () =>
      addLinearLink(project.id, {
        linear_project_id: newLinkId.trim(),
        linear_project_name: newLinkName.trim(),
      }),
    onSuccess: () => {
      invalidateProjects()
      setNewLinkId('')
      setNewLinkName('')
      setShowLinkForm(false)
      toast.success('Linear link added')
    },
    onError: (err) =>
      toast.error(`Add link failed: ${err instanceof Error ? err.message : String(err)}`),
  })

  const removeLinkMutation = useMutation({
    mutationFn: (linkId: number) => removeLinearLink(project.id, linkId),
    onSuccess: () => {
      invalidateProjects()
      toast.success('Linear link removed')
    },
    onError: (err) =>
      toast.error(`Remove link failed: ${err instanceof Error ? err.message : String(err)}`),
  })

  const handleNameBlur = () => {
    setEditingName(false)
    const trimmed = nameValue.trim()
    if (trimmed && trimmed !== project.name) {
      updateMutation.mutate({ name: trimmed })
    } else {
      setNameValue(project.name)
    }
  }

  const handleDescBlur = () => {
    if (descValue !== (project.description ?? '')) {
      updateMutation.mutate({ description: descValue })
    }
  }

  const handleArchive = () => {
    updateMutation.mutate({ status: 'archived' })
    toast.success('Project archived')
  }

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-4 space-y-3">
      {/* Name + Archive button */}
      <div className="flex items-start justify-between gap-2">
        {editingName ? (
          <input
            autoFocus
            value={nameValue}
            onChange={(e) => setNameValue(e.target.value)}
            onBlur={handleNameBlur}
            onKeyDown={(e) => {
              if (e.key === 'Enter') e.currentTarget.blur()
              if (e.key === 'Escape') {
                setNameValue(project.name)
                setEditingName(false)
              }
            }}
            className="flex-1 bg-transparent text-sm font-medium text-zinc-100
                       border-b border-zinc-500 outline-none pb-0.5"
          />
        ) : (
          <button
            onClick={() => setEditingName(true)}
            className="text-sm font-medium text-zinc-100 hover:text-white text-left"
            title="Click to edit name"
          >
            {project.name}
          </button>
        )}
        <button
          onClick={handleArchive}
          disabled={updateMutation.isPending}
          className="text-xs text-zinc-500 hover:text-zinc-300 shrink-0 disabled:opacity-50"
        >
          Archive
        </button>
      </div>

      {/* Slug */}
      <p className="text-xs text-zinc-600">
        Slug:{' '}
        <code className="text-zinc-500 bg-zinc-800 px-1 py-0.5 rounded">{project.slug}</code>
      </p>

      {/* Description */}
      <input
        value={descValue}
        onChange={(e) => setDescValue(e.target.value)}
        onBlur={handleDescBlur}
        placeholder="Add a description…"
        className="w-full bg-transparent text-xs text-zinc-400 placeholder:text-zinc-600
                   border-b border-transparent hover:border-zinc-700 focus:border-zinc-500
                   outline-none pb-0.5"
      />

      {/* Linear links */}
      <div className="space-y-1.5">
        <p className="text-xs font-medium text-zinc-500">Linear links</p>

        {project.linear_links.length === 0 ? (
          <p className="text-xs text-zinc-700">None linked</p>
        ) : (
          <ul className="space-y-1">
            {project.linear_links.map((link: LinearLink) => (
              <li key={link.id} className="flex items-center justify-between">
                <span className="text-xs text-zinc-400">{link.linear_project_name}</span>
                <button
                  onClick={() => removeLinkMutation.mutate(link.id)}
                  disabled={removeLinkMutation.isPending}
                  className="text-zinc-600 hover:text-zinc-400 disabled:opacity-50"
                  aria-label={`Remove ${link.linear_project_name}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </li>
            ))}
          </ul>
        )}

        {showLinkForm ? (
          <div className="space-y-1.5 pt-1">
            <input
              value={newLinkId}
              onChange={(e) => setNewLinkId(e.target.value)}
              placeholder="Linear project ID"
              className="w-full text-xs bg-zinc-800 border border-zinc-700 rounded
                         px-2 py-1 text-zinc-200 placeholder:text-zinc-600
                         outline-none focus:border-zinc-500"
            />
            <input
              value={newLinkName}
              onChange={(e) => setNewLinkName(e.target.value)}
              placeholder="Linear project name"
              className="w-full text-xs bg-zinc-800 border border-zinc-700 rounded
                         px-2 py-1 text-zinc-200 placeholder:text-zinc-600
                         outline-none focus:border-zinc-500"
            />
            <div className="flex gap-1">
              <button
                onClick={() => addLinkMutation.mutate()}
                disabled={!newLinkId.trim() || !newLinkName.trim() || addLinkMutation.isPending}
                className="text-xs px-2 py-1 rounded bg-zinc-700 text-zinc-200
                           hover:bg-zinc-600 disabled:opacity-50"
              >
                Add
              </button>
              <button
                onClick={() => {
                  setShowLinkForm(false)
                  setNewLinkId('')
                  setNewLinkName('')
                }}
                className="text-xs px-2 py-1 rounded text-zinc-500 hover:text-zinc-300"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowLinkForm(true)}
            className="text-xs text-zinc-600 hover:text-zinc-400"
          >
            + Add Linear link
          </button>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Archived project card
// ---------------------------------------------------------------------------

function ArchivedProjectCard({ project }: { project: Project }) {
  const qc = useQueryClient()

  const unarchiveMutation = useMutation({
    mutationFn: () => updateProject(project.id, { status: 'active' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Project unarchived')
    },
    onError: (err) =>
      toast.error(`Unarchive failed: ${err instanceof Error ? err.message : String(err)}`),
  })

  return (
    <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3">
      <div>
        <p className="text-sm text-zinc-400">{project.name}</p>
        <p className="text-xs text-zinc-600">{project.slug}</p>
      </div>
      <button
        onClick={() => unarchiveMutation.mutate()}
        disabled={unarchiveMutation.isPending}
        className="text-xs text-zinc-500 hover:text-zinc-300 disabled:opacity-50"
      >
        Unarchive
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Create project form
// ---------------------------------------------------------------------------

function CreateProjectForm() {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const createMutation = useMutation({
    mutationFn: () =>
      createProject({ name: name.trim(), description: description.trim() || undefined }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Project created')
      setName('')
      setDescription('')
    },
    onError: (err) =>
      toast.error(`Create failed: ${err instanceof Error ? err.message : String(err)}`),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    createMutation.mutate()
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <h2 className="text-sm font-medium text-zinc-300">New project</h2>
      <div className="space-y-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Project name"
          required
          className="w-full bg-zinc-800 border border-zinc-700 rounded-md
                     px-3 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-600
                     outline-none focus:border-zinc-500"
        />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional)"
          rows={2}
          className="w-full bg-zinc-800 border border-zinc-700 rounded-md
                     px-3 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-600
                     outline-none focus:border-zinc-500 resize-none"
        />
      </div>
      <Button
        type="submit"
        size="sm"
        disabled={!name.trim() || createMutation.isPending}
      >
        {createMutation.isPending ? 'Creating…' : 'Create project'}
      </Button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Projects() {
  const [archivedOpen, setArchivedOpen] = useState(false)

  const { data: activeProjects = [], isLoading: loadingActive } = useQuery({
    queryKey: ['projects', 'active'],
    queryFn: () => listProjects('active'),
  })

  const { data: archivedProjects = [] } = useQuery({
    queryKey: ['projects', 'archived'],
    queryFn: () => listProjects('archived'),
  })

  return (
    <div className="flex flex-col h-full p-6 gap-6 overflow-y-auto">
      <h1 className="text-xl font-semibold text-zinc-100 flex-shrink-0">Projects</h1>

      {/* Create form */}
      <CreateProjectForm />

      {/* Active projects */}
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-zinc-400">Active projects</h2>
        {loadingActive ? (
          <p className="text-xs text-zinc-600">Loading…</p>
        ) : activeProjects.length === 0 ? (
          <p className="text-xs text-zinc-600">No active projects.</p>
        ) : (
          <div className="grid gap-3">
            {activeProjects.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        )}
      </section>

      {/* Archived projects (collapsible) */}
      {archivedProjects.length > 0 && (
        <section className="space-y-3">
          <button
            onClick={() => setArchivedOpen((v) => !v)}
            className="flex items-center gap-1 text-sm font-medium text-zinc-500 hover:text-zinc-300"
          >
            {archivedOpen ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
            Archived projects ({archivedProjects.length})
          </button>

          {archivedOpen && (
            <div className="space-y-2">
              {archivedProjects.map((project) => (
                <ArchivedProjectCard key={project.id} project={project} />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  )
}
