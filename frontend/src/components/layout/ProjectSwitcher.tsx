import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Check, ChevronDown } from 'lucide-react'
import { Link } from 'react-router-dom'
import { listProjects } from '@/api/projects'
import { useAppStore } from '@/stores/useAppStore'

export function ProjectSwitcher() {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const activeProjectId = useAppStore((s) => s.activeProjectId)
  const setActiveProjectId = useAppStore((s) => s.setActiveProjectId)

  const { data: projects } = useQuery({
    queryKey: ['projects', 'active'],
    queryFn: () => listProjects('active'),
  })

  const activeProject = projects?.find((p) => p.id === activeProjectId)

  // Close on outside click
  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) document.addEventListener('mousedown', handleOutside)
    return () => document.removeEventListener('mousedown', handleOutside)
  }, [open])

  return (
    <div className="relative w-full" ref={containerRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 rounded-md
                   bg-zinc-800 hover:bg-zinc-700 text-zinc-100 text-sm font-medium
                   transition-colors"
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span className="truncate">{activeProject?.name ?? 'Loading…'}</span>
        <ChevronDown className="w-4 h-4 text-zinc-400 flex-shrink-0 ml-2" />
      </button>

      {open && (
        <div
          className="absolute top-full left-0 right-0 mt-1 z-50
                     bg-zinc-800 border border-zinc-700 rounded-md shadow-lg py-1"
          role="listbox"
        >
          {projects?.map((project) => (
            <button
              key={project.id}
              role="option"
              aria-selected={project.id === activeProjectId}
              onClick={() => {
                setActiveProjectId(project.id)
                setOpen(false)
              }}
              className="w-full flex items-center justify-between px-3 py-2
                         text-sm text-zinc-200 hover:bg-zinc-700"
            >
              <span className="truncate">{project.name}</span>
              {project.id === activeProjectId && (
                <Check className="w-3 h-3 text-zinc-400 flex-shrink-0 ml-2" />
              )}
            </button>
          ))}

          <div className="border-t border-zinc-700 mt-1 pt-1">
            <Link
              to="/projects"
              onClick={() => setOpen(false)}
              className="flex items-center px-3 py-2 text-sm text-zinc-400
                         hover:text-zinc-200 hover:bg-zinc-700"
            >
              Manage projects
              <ArrowRight className="w-3 h-3 ml-1" />
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}
