import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { EmployeeDocument } from '@/lib/types'
import { type ApiRoutes, mockApi, renderApp } from '@tests/support/utils'

import { DocumentsSection } from '@/features/employee/DocumentsSection'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const DOC: EmployeeDocument = {
  id: 3, file_name: 'offer-letter.pdf', content_type: 'application/pdf', size_bytes: 248_000,
  uploaded_by_name: 'Priya Sharma', uploaded_at: '2026-04-01T09:00:00Z',
}

function setup(routes: ApiRoutes, isAdmin = true) {
  const fetchMock = mockApi({ 'GET /employees/7/documents': [DOC], ...routes })
  renderApp(<DocumentsSection employeeId={7} isAdmin={isAdmin} />)
  // Lets the tests pick a file the input's `accept` would hide, to check the app's own check.
  return { fetchMock, user: userEvent.setup({ applyAccept: false }) }
}

const pdf = () => new File(['%PDF-1.7'], 'contract.pdf', { type: 'application/pdf' })
const sent = (fetchMock: ReturnType<typeof mockApi>, method: string) => fetchMock.mock.calls.filter(([, init]) => init?.method === method)

describe('Documents', () => {
  it('lists documents with type, size and who added them', async () => {
    setup({})
    expect(await screen.findByText('offer-letter.pdf')).toBeInTheDocument()
    expect(screen.getByText('PDF')).toBeInTheDocument()
    expect(screen.getByText('242 KB, added by Priya Sharma on 1 Apr 2026')).toBeInTheDocument()
  })

  it('uploads a chosen file once, with an idempotency key', async () => {
    const { fetchMock, user } = setup({ 'POST /employees/7/documents': () => ({ status: 201, body: DOC }) })
    await screen.findByText('offer-letter.pdf')
    await user.upload(screen.getByLabelText('Choose a document to upload'), pdf())
    await vi.waitFor(() => expect(sent(fetchMock, 'POST')).toHaveLength(1))
    const [, init] = sent(fetchMock, 'POST')[0]
    expect((init!.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy()
    expect((init!.body as FormData).get('file')).toBeInstanceOf(File)
  })

  it('refuses a file of the wrong type before uploading', async () => {
    const error = vi.spyOn(toast, 'error')
    const { fetchMock, user } = setup({})
    await screen.findByText('offer-letter.pdf')
    await user.upload(screen.getByLabelText('Choose a document to upload'), new File(['<svg/>'], 'x.svg', { type: 'image/svg+xml' }))
    expect(error).toHaveBeenCalledWith('Choose a PDF, JPG or PNG file.')
    expect(sent(fetchMock, 'POST')).toHaveLength(0)
  })

  it('tells the person when a download link cannot be made', async () => {
    const error = vi.spyOn(toast, 'error')
    const { user } = setup({
      'GET /employees/7/documents/3/download': () => ({ status: 404, body: { error: { message: 'Document not found.' } } }),
    })
    await user.click(await screen.findByRole('button', { name: 'Download' }))
    await vi.waitFor(() => expect(error).toHaveBeenCalledWith('Document not found.'))
  })

  it('removes a document after confirming', async () => {
    let removed = false
    const { fetchMock, user } = setup({
      'GET /employees/7/documents': () => ({ body: removed ? [] : [DOC] }),
      'DELETE /employees/7/documents/3': () => {
        removed = true
        return { status: 204 }
      },
    })
    await user.click(await screen.findByRole('button', { name: 'Remove' }))
    expect(screen.getByRole('heading', { name: 'Remove offer-letter.pdf?' })).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: 'Remove' }).at(-1)!)
    expect(await screen.findByText('No documents yet.')).toBeInTheDocument()
    expect(sent(fetchMock, 'DELETE')).toHaveLength(1)
  })

  it('Cancel on the confirmation keeps the document', async () => {
    const { fetchMock, user } = setup({})
    await user.click(await screen.findByRole('button', { name: 'Remove' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(sent(fetchMock, 'DELETE')).toHaveLength(0)
  })

  it('HR Viewers can download but not upload or remove', async () => {
    setup({}, false)
    expect(await screen.findByRole('button', { name: 'Download' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Upload' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull()
  })

  it('shows a load error with a retry', async () => {
    setup({ 'GET /employees/7/documents': () => ({ status: 500, body: { error: { message: 'Storage is down' } } }) })
    expect(await screen.findByText('Storage is down')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
