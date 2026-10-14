// Client-side checks that mirror the server's (PDF/JPG/PNG, ≤ 10 MB), so mistakes show at once.

export const MAX_FILE_BYTES = 10 * 1024 * 1024
export const DOCUMENT_ACCEPT = '.pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png'
export const PHOTO_ACCEPT = '.jpg,.jpeg,.png,image/jpeg,image/png'

const DOCUMENT_TYPES = ['application/pdf', 'image/jpeg', 'image/png']
const PHOTO_TYPES = ['image/jpeg', 'image/png']

export function fileError(file: File, kind: 'document' | 'photo'): string | null {
  const types = kind === 'photo' ? PHOTO_TYPES : DOCUMENT_TYPES
  if (!types.includes(file.type)) {
    return kind === 'photo' ? 'Choose a JPG or PNG image.' : 'Choose a PDF, JPG or PNG file.'
  }
  if (file.size > MAX_FILE_BYTES) return 'This file is larger than 10 MB. Choose a smaller file.'
  if (file.size === 0) return 'This file is empty.'
  return null
}

export function formData(file: File): FormData {
  const body = new FormData()
  body.append('file', file)
  return body
}
