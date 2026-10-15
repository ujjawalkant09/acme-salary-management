import { describe, expect, it } from 'vitest'

import { fileError, formData, MAX_FILE_BYTES } from './upload'

function file(type: string, size = 100, name = 'f') {
  const f = new File(['x'], name, { type })
  Object.defineProperty(f, 'size', { value: size })
  return f
}

describe('upload checks', () => {
  it('accepts PDF, JPG and PNG documents', () => {
    for (const type of ['application/pdf', 'image/jpeg', 'image/png']) expect(fileError(file(type), 'document')).toBeNull()
  })

  it('accepts only images as photos', () => {
    expect(fileError(file('image/png'), 'photo')).toBeNull()
    expect(fileError(file('application/pdf'), 'photo')).toBe('Choose a JPG or PNG image.')
  })

  it('refuses other types, files over 10 MB and empty files', () => {
    expect(fileError(file('text/html'), 'document')).toBe('Choose a PDF, JPG or PNG file.')
    expect(fileError(file('image/svg+xml'), 'photo')).toBe('Choose a JPG or PNG image.')
    expect(fileError(file('application/pdf', MAX_FILE_BYTES), 'document')).toBeNull()
    expect(fileError(file('application/pdf', MAX_FILE_BYTES + 1), 'document')).toMatch(/larger than 10 MB/)
    expect(fileError(file('application/pdf', 0), 'document')).toBe('This file is empty.')
  })

  it('sends the file as the "file" field', () => {
    const f = file('application/pdf')
    expect(formData(f).get('file')).toBe(f)
  })
})
