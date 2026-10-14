// Fields shared by "Add employee" and "Edit details".
import { Field } from '@/components/Field'
import { Input, NativeSelect } from '@/components/ui/input'
import { label } from '@/lib/format'
import type { Meta } from '@/lib/types'

import type { EmployeeForm, FormErrors } from './employeeForm'

interface Props {
  form: EmployeeForm
  onChange: (changes: Partial<EmployeeForm>) => void
  meta: Meta
  errors: FormErrors
}

export function EmployeeFields({ form, onChange, meta, errors }: Props) {
  const text = (key: keyof EmployeeForm, title: string, type = 'text') => (
    <Field id={key} label={title} error={errors[key]}>
      <Input
        id={key}
        type={type}
        value={form[key]}
        aria-invalid={!!errors[key]}
        onChange={(e) => onChange({ [key]: e.target.value })}
      />
    </Field>
  )

  return (
    <div className="grid gap-x-4 sm:grid-cols-2">
      {text('first_name', 'First name')}
      {text('last_name', 'Last name')}
      <div className="sm:col-span-2">{text('email', 'Work email', 'email')}</div>

      <Field id="job_title" label="Job title" error={errors.job_title}>
        <Input
          id="job_title"
          list="job-titles"
          value={form.job_title}
          aria-invalid={!!errors.job_title}
          onChange={(e) => onChange({ job_title: e.target.value })}
        />
        <datalist id="job-titles">
          {meta.job_titles.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
      </Field>
      <Field id="job_level" label="Level" error={errors.job_level}>
        <NativeSelect id="job_level" value={form.job_level} aria-invalid={!!errors.job_level} onChange={(e) => onChange({ job_level: e.target.value })}>
          <option value="">Choose a level</option>
          {meta.levels.map((l) => (
            <option key={l} value={l}>
              Level {l}
            </option>
          ))}
        </NativeSelect>
      </Field>

      <Field id="department_id" label="Department" error={errors.department_id}>
        <NativeSelect
          id="department_id"
          value={form.department_id}
          aria-invalid={!!errors.department_id}
          onChange={(e) => onChange({ department_id: e.target.value })}
        >
          <option value="">Choose a department</option>
          {meta.departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <Field id="country_code" label="Country" error={errors.country_code}>
        <NativeSelect
          id="country_code"
          value={form.country_code}
          aria-invalid={!!errors.country_code}
          onChange={(e) => onChange({ country_code: e.target.value })}
        >
          <option value="">Choose a country</option>
          {meta.countries.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name}
            </option>
          ))}
        </NativeSelect>
      </Field>

      {text('city', 'City (optional)')}
      {text('hire_date', 'Joined on', 'date')}

      <Field id="employment_type" label="Employment type">
        <NativeSelect id="employment_type" value={form.employment_type} onChange={(e) => onChange({ employment_type: e.target.value })}>
          {meta.employment_types.map((t) => (
            <option key={t} value={t}>
              {label(t)}
            </option>
          ))}
        </NativeSelect>
      </Field>
      {form.employment_type === 'part_time' ? (
        <Field id="fte" label="Share of full time" hint="0.5 means half-time" error={errors.fte}>
          <Input id="fte" inputMode="decimal" value={form.fte} aria-invalid={!!errors.fte} onChange={(e) => onChange({ fte: e.target.value })} />
        </Field>
      ) : (
        <div />
      )}

      <Field id="gender" label="Gender (optional)" hint="Shown only on the employee page. Not used in lists, exports or Insights.">
        <NativeSelect id="gender" value={form.gender} onChange={(e) => onChange({ gender: e.target.value })}>
          <option value="">Not recorded</option>
          {meta.genders.map((g) => (
            <option key={g} value={g}>
              {label(g)}
            </option>
          ))}
        </NativeSelect>
      </Field>
    </div>
  )
}
