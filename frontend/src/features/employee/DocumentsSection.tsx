import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorState, Spinner } from '@/components/states'
import { Button } from '@/components/ui/button'
import { api, errorMessage, newIdempotencyKey } from '@/lib/api'
import { fileSize, formatDate } from '@/lib/format'
import { DOCUMENT_ACCEPT, fileError, formData } from '@/lib/upload'
import type { EmployeeDocument } from '@/lib/types'

export function DocumentsSection({ employeeId, isAdmin }: { employeeId: number; isAdmin: boolean }) {
  const client = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [removing, setRemoving] = useState<EmployeeDocument | null>(null)
  const key = ['documents', employeeId]
  const documents = useQuery({
    queryKey: key,
    queryFn: () => api<EmployeeDocument[]>(`/employees/${employeeId}/documents`),
  })

  const upload = useMutation({
    // One key per chosen file: a retry of the same upload is stored only once.
    mutationFn: ({ file, idempotencyKey }: { file: File; idempotencyKey: string }) =>
      api<EmployeeDocument>(`/employees/${employeeId}/documents`, { method: 'POST', body: formData(file), idempotencyKey }),
    onSuccess: () => {
      toast.success('Document uploaded')
      return client.invalidateQueries({ queryKey: key })
    },
  })
  const remove = useMutation({
    mutationFn: (doc: EmployeeDocument) => api<void>(`/employees/${employeeId}/documents/${doc.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Document removed')
      setRemoving(null)
      return client.invalidateQueries({ queryKey: key })
    },
  })

  function pick(file: File | undefined) {
    if (!file) return
    const problem = fileError(file, 'document')
    if (problem) toast.error(problem)
    else upload.mutate({ file, idempotencyKey: newIdempotencyKey() })
  }

  async function download(doc: EmployeeDocument) {
    try {
      const { url } = await api<{ url: string }>(`/employees/${employeeId}/documents/${doc.id}/download`)
      // The link is short-lived and sent as an attachment, so this downloads without leaving the page.
      window.location.assign(url)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <section className="rounded-xl border border-border">
      <div className="flex min-h-[3.375rem] items-center gap-2 border-b border-border px-5 py-3.5">
        <h2 className="flex-1 text-md font-semibold">Documents</h2>
        {isAdmin && (
          <>
            <input
              ref={input}
              type="file"
              accept={DOCUMENT_ACCEPT}
              className="hidden"
              aria-label="Choose a document to upload"
              onChange={(e) => {
                pick(e.target.files?.[0])
                e.target.value = ''
              }}
            />
            <Button variant="outline" size="sm" disabled={upload.isPending} onClick={() => input.current?.click()}>
              {upload.isPending && <Spinner />}
              Upload
            </Button>
          </>
        )}
      </div>

      {documents.isError ? (
        <div className="p-4">
          <ErrorState error={documents.error} onRetry={documents.refetch} />
        </div>
      ) : documents.isPending ? (
        <p className="px-5 py-4.5 text-muted">Loading documents…</p>
      ) : documents.data.length === 0 ? (
        <p className="px-5 py-4.5 text-muted">No documents yet.</p>
      ) : (
        <ul>
          {documents.data.map((doc) => (
            <li key={doc.id} className="flex items-center gap-3 border-b border-border px-5 py-3 last:border-b-0">
              <span className="grid size-9 shrink-0 place-items-center rounded-md bg-subtle text-[0.6875rem] font-semibold text-muted">
                {doc.content_type === 'application/pdf' ? 'PDF' : doc.content_type === 'image/png' ? 'PNG' : 'JPG'}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{doc.file_name}</span>
                <span className="block text-sm text-muted">
                  {fileSize(doc.size_bytes)}, added by {doc.uploaded_by_name} on {formatDate(doc.uploaded_at)}
                </span>
              </span>
              <Button variant="ghost" size="sm" onClick={() => download(doc)}>
                Download
              </Button>
              {isAdmin && (
                <Button variant="ghost" size="sm" className="text-error hover:text-error" onClick={() => setRemoving(doc)}>
                  Remove
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="border-t border-border px-5 pt-2.5 pb-3.5 text-sm text-muted">
        PDF, JPG or PNG, up to 10 MB each. {!isAdmin && 'Only HR Admins can upload or remove documents.'}
      </p>

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={`Remove ${removing?.file_name ?? ''}?`}
        description="It is hidden right away and deleted from storage after 30 days."
        action="Remove"
        pending={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing)}
      />
    </section>
  )
}
